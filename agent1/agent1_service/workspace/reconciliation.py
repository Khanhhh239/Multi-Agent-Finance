"""Adapt the existing T9 flow, scorer and encrypted ledger to company datasets.

Imported receipts remain observed receipts. New T9 decisions and their payment
rows commit atomically; proposals and rejections never change invoice balances.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import uuid

import pandas as pd

from agent1.adaptive.data import (SCHEMAS, IDS, MONEY_FIELDS, ACCOUNTING, as_of, effective_data, fingerprint,
                                 merge_import, parse_rows, validate_dataset, vnd, _payment_links, payment_target)
from agent1.reconciliation._thang.allocation import Config
from agent1.reconciliation._thang.constrained import allocate
from agent1.reconciliation._thang.matching import Config as ScoreConfig, normalize, references, score
from agent1.reconciliation.ledger import DecisionLedger
from agent1.reconciliation.pipeline import LINK_COLUMNS, NON_AR, day, today


REASONS = {
    'unknown_party': 'Chưa xác định khách hàng',
    'reference_conflict': 'Số hóa đơn hoặc khách hàng trong nội dung bị xung đột',
    'remittance_conflict': 'Bảng kê thanh toán không khớp chứng từ',
    'reference_or_remittance_risk': 'Tham chiếu chưa đủ để phân biệt các hóa đơn',
    'ambiguous_subset': 'Có nhiều nhóm hóa đơn cùng khớp số tiền',
    'no_exact_subset': 'Chưa có nhóm hóa đơn khớp số tiền',
    'group_pool_overflow': 'Quá nhiều hóa đơn cần đối chiếu',
    'flow_component_overflow': 'Nhóm đối soát vượt giới hạn xử lý tự động',
    'remittance_overflow': 'Bảng kê thanh toán vượt dư nợ',
    'flow_nonunique': 'Có nhiều phương án phân bổ hợp lệ',
    'flow_infeasible': 'Chưa tìm được phương án thỏa các ràng buộc',
    'no_cash_flow': 'Chưa xác định được phần tiền phân bổ',
    'unique_transport': 'Có một phương án phân bổ thỏa ràng buộc; cần đối chiếu chứng từ',
    'non_ar_bank_movement': 'Khoản thu không thuộc công nợ khách hàng',
    'rejected': 'Kế toán đã từ chối; có thể phân bổ thủ công khi có bằng chứng mới',
}

EDITABLE_KINDS = ('invoices', 'bank', 'payments', 'statements', 'actions', 'outflows')


def correction_time():
    return today() + pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').strftime('T%H:%M:%S.%f+07:00')


def editable_fields(kind):
    if kind not in EDITABLE_KINDS:
        raise ValueError('Bảng này không hỗ trợ sửa nguồn')
    return [k for k in SCHEMAS[kind] if k not in (IDS[kind], 'known_at', 'record_version')]


def dataset_batches(data):
    version = fingerprint(data)
    return {
        'company_datasets': [dict(id=version, data=data, created_at=datetime.now(timezone.utc).isoformat())],
        'company_dataset_active': [dict(id='active', version=version,
                                       counts={k: len(data.get(k, [])) for k in SCHEMAS})],
    }, dict(version=version)


class WorkspaceSource:
    proposal_kind = 'company_t9_proposals'

    def __init__(self, store, firm, data, *, payment_ids=None):
        self.store, self.firm, self.data = store, firm, data
        self.ledger = DecisionLedger(store, firm, prefix='company_')
        self.payment_ids = payment_ids or {}

    def reviews(self):
        return self.store.get(self.firm, 'company_t9_reviews')

    def protected_payments(self):
        return {pid for r in self.reviews() if r['action'] == 'accepted' for pid in r['payment_ids']}

    def validate_managed(self, gold=None):
        """Prevent CSV edits/deletes from bypassing a recorded decision/reversal."""
        gold = self.ledger.gold(today()) if gold is None else gold
        active = {r['decision_id']: r for r in gold['decisions'] if r['status'] == 'committed'}
        receipts = {r['payment_id']: r for r in self.data.get('payments', [])}
        expected = {}
        invoices = {r['invoice_id']: r for r in self.data.get('invoices', [])}
        banks = {r['bank_id']: r for r in self.data.get('bank', [])}
        recorded_banks = {r['id']: r for r in gold.get('banks', [])}
        ledger_inv = {r['id']: r for r in gold['invoices']}
        ledger_pay = {r['id']: r for r in gold['payments']}
        for tid, recorded in recorded_banks.items():
            bank = banks.get(tid)
            if bank and (bank['account'] != recorded['account_id']
                         or bank['date'] != recorded['effective_on']
                         or vnd(bank['amount']) != recorded['amount_minor']
                         or bank['direction'] != ('in' if recorded['direction'] == 'credit' else 'out')
                         or bank.get('currency', 'VND') != recorded['currency']
                         or tid in ledger_pay and bank.get('customer_id') not in (None, '', ledger_pay[tid]['party_id'])):
                raise ValueError('Tài khoản, ngày, số tiền và khách của dòng sao kê đã ghi ledger là bất biến, kể cả sau khi đảo; cần xử lý chứng từ nguồn riêng')
        for iid, recorded in ledger_inv.items():
            invoice = invoices.get(iid)
            if invoice and (invoice['customer_id'] != recorded['party_id'] or invoice['issue_date'] != recorded['effective_on']):
                raise ValueError('Mã hóa đơn đã ghi ledger không được đổi khách hoặc ngày lập, kể cả sau khi đảo; cần xử lý chứng từ nguồn riêng')
        for review in self.reviews():
            if review['action'] != 'accepted' or review['decision_id'] not in active:
                continue
            for pid, allocation in zip(review['payment_ids'], active[review['decision_id']]['allocations'], strict=True):
                expected[pid] = review['decision_id']
                row = receipts.get(pid, {})
                if (row.get('t9_decision_id') != review['decision_id']
                        or row.get('invoice_id') != allocation['invoice_id']
                        or row.get('bank_id') != allocation['payment_id']
                        or vnd(row.get('amount', 0)) != allocation['amount_minor']
                        or row.get('known_at') != review['known_at']):
                    raise ValueError('Phân bổ T9 đã duyệt không được sửa/xóa bằng CSV; hãy đảo quyết định trước')
                invoice, bank = invoices.get(row['invoice_id']), banks.get(row['bank_id'])
                original_i, original_p = ledger_inv[allocation['invoice_id']], ledger_pay[allocation['payment_id']]
                if (not invoice or not bank or invoice['customer_id'] != original_i['party_id']
                        or bank.get('customer_id') not in (None, '', original_p['party_id'])
                        or bank['date'] != original_p['effective_on']
                        or row.get('payment_date') != bank['date']
                        or vnd(bank['amount']) != original_p['amount_minor']
                        or bank['direction'] != 'in' or bank.get('component') == 'cash_sale'
                        or bank.get('cash_flow_class') in NON_AR
                        or bank['date'] < invoice['issue_date']):
                    raise ValueError('Nguồn của phân bổ T9 đã đổi; hãy đảo quyết định trước khi sửa chứng từ')
        if any(r.get('t9_decision_id') != expected.get(pid) for pid, r in receipts.items()
               if r.get('t9_decision_id') or pid in expected):
            raise ValueError('Thanh toán T9 không khớp Accepted Ledger')
        if any(pid in receipts and pid not in expected for pid in self.protected_payments()):
            raise ValueError('Mã thanh toán của quyết định đã đảo không được sử dụng lại')

    def view(self, cutoff):
        cutoff = day(cutoff)
        data = effective_data(self.data, cutoff)
        invoices = [r for r in data['invoices'] if r['known_at'] <= cutoff and day(r['issue_date']) <= cutoff]
        banks = [dict(r, txn_id=r['bank_id'], value_date=r['date'], account_id=r['account'])
                 for r in data.get('bank', []) if r['known_at'] <= cutoff and r['date'] <= cutoff]
        receipts = [r for r in data.get('payments', []) if r['known_at'] <= cutoff and r['payment_date'] <= cutoff]
        paid = Counter()
        links = []
        customers = {r['invoice_id']: r['customer_id'] for r in invoices}
        gold = self.ledger.gold(cutoff)
        recorded_parties = {r['id']: r['party_id'] for r in gold['payments']}
        parties = defaultdict(set)
        for r in receipts:
            paid[r['invoice_id']] += vnd(r['amount'])
            if r.get('bank_id') and r['invoice_id'] in customers:
                parties[r['bank_id']].add(customers[r['invoice_id']])
            links.append(dict(txn_id=r.get('bank_id', ''), invoice_id=r['invoice_id'],
                              est_pay_date=r['payment_date'], known_at=r['known_at'],
                              amount=vnd(r['amount']), amount_minor=vnd(r['amount']),
                              decision_id=r.get('t9_decision_id'), method='accepted_receipt', evidence_type='observed'))
        for bank in banks:
            known = parties[bank['txn_id']]
            if bank['txn_id'] in recorded_parties:
                known.add(recorded_parties[bank['txn_id']])
            if len(known) > 1 or bank.get('customer_id') and known and known != {bank['customer_id']}:
                raise ValueError('Một dòng sao kê đang phân bổ chéo khách hàng; đối chiếu nguồn trước')
            if known and not bank.get('customer_id'):
                bank['customer_id'] = next(iter(known))
        written = {r['invoice_id'] for r in data.get('actions', [])
                   if r['kind'] == 'write_off' and r['known_at'] <= cutoff and r['date'] <= cutoff}
        rows = []
        for r in invoices:
            gross = vnd(r['amount'])
            remaining = gross - paid[r['invoice_id']]
            if remaining < 0:
                raise ValueError('Tổng phân bổ vượt công nợ hiệu lực')
            number = r.get('invoice_no')
            rows.append(dict(r, invoice_no=number if isinstance(number, str) and number else r['invoice_id'],
                             amount_gross=gross, amount_gross_minor=gross, credit_note=0,
                             amount_open_minor=0 if r['invoice_id'] in written else remaining,
                             closure_type='writeoff' if r['invoice_id'] in written else 'open' if remaining else 'paid'))
        frame = pd.DataFrame(rows).astype(object)
        frame = frame.where(pd.notna(frame), None)
        linked = pd.DataFrame(links, columns=LINK_COLUMNS)
        return dict(invoices=frame, bank=banks, links=linked, gold=gold,
                    snapshot_hash=fingerprint(dict(dataset=fingerprint(self.data), ledger=gold['snapshot_hash'])), cutoff=cutoff)

    def rejected_banks(self):
        banks = {r['bank_id']: fingerprint(r) for r in self.data.get('bank', [])}
        return {r['bank_id']: r for r in self.reviews() if r['action'] == 'rejected'
                and r['bank_hash'] == banks.get(r['bank_id'])}

    def propose(self, cutoff):
        self.validate_managed()
        view = self.view(cutoff)
        rows = view['invoices'].to_dict('records')
        invoices = [dict(tenant_id=self.firm, id=r['invoice_id'], invoice_number=r['invoice_no'],
                         party_id=r['customer_id'], side='AR', currency='VND',
                         amount_minor=r['amount_open_minor'], issued_on=day(r['issue_date']))
                    for r in rows if r['amount_open_minor'] > 0 and r['closure_type'] == 'open']
        names = defaultdict(set)
        for r in rows:
            if r.get('customer_name'):
                names[normalize(r['customer_name'])].add(r['customer_id'])
        used = Counter()
        for r in view['links'].to_dict('records'):
            used[r['txn_id']] += r['amount_minor']
        payments, ignored = [], []
        rejected = self.rejected_banks()
        for bank in view['bank']:
            tid = bank['txn_id']
            remaining = vnd(bank['amount']) - used[tid]
            if remaining <= 0 or bank['direction'] != 'in':
                continue
            if bank.get('component') == 'cash_sale' or bank.get('cash_flow_class') in NON_AR:
                ignored.append(dict(payment_id=tid, status='unmatched', reason='non_ar_bank_movement', unallocated_minor=remaining))
                continue
            if tid in rejected:
                ignored.append(dict(payment_id=tid, status='rejected', reason='rejected', unallocated_minor=remaining,
                                    reviewed_by=rejected[tid]['reviewed_by'], note=rejected[tid]['note']))
                continue
            party = bank.get('customer_id', '')
            exact = names.get(normalize(bank.get('counterparty', '')), set())
            if not party and len(exact) == 1:
                party = next(iter(exact))
            payments.append(dict(tenant_id=self.firm, id=tid, side='AR', party_id=party, currency='VND',
                                 amount_minor=remaining, payment_on=bank['date'], reference=bank.get('memo', '')))
        result = allocate(invoices, payments, Config(max_age_days=3650))
        result['decisions'].extend(ignored)
        result.update(snapshot_hash=view['snapshot_hash'], cutoff=day(cutoff), run_id=uuid.uuid4().hex,
                      created_at=datetime.now(timezone.utc).isoformat())
        # Reuse the existing heuristic scorer for ordering human suggestions.
        # Scores never disambiguate a nonunique transport or become cash labels.
        by_id = {r['invoice_id']: r for r in rows if r['amount_open_minor'] > 0 and r['closure_type'] == 'open'}
        by_party, by_amount = defaultdict(list), defaultdict(list)
        for r in by_id.values():
            by_party[r['customer_id']].append(r)
            by_amount[r['amount_open_minor']].append(r)
        edge_ids = defaultdict(set)
        for _, tid, iid in result['candidate_edges']:
            edge_ids[tid].add(iid)
        bank_by_id = {r['txn_id']: r for r in view['bank']}
        payment_by_id = {r['id']: r for r in payments}
        allocations_by_bank = defaultdict(list)
        for allocation in result['allocations']:
            allocations_by_bank[allocation['payment_id']].append(allocation)
        result['cases'] = []
        for decision in result['decisions']:
            tid = decision['payment_id']
            bank = bank_by_id[tid]
            party = payment_by_id.get(tid, {}).get('party_id', bank.get('customer_id', ''))
            pool = {iid: by_id[iid] for iid in sorted(edge_ids[tid])[:200] if iid in by_id}
            for r in by_party.get(party, []) or by_amount.get(vnd(bank['amount']) - used[tid], []):
                if len(pool) >= 200:
                    break
                pool[r['invoice_id']] = r
            ranked = []
            for r in pool.values():
                if day(r['issue_date']) > bank['date'] or party and party != r['customer_id']:
                    continue
                b = dict(reference=bank.get('memo', ''), counterparty=bank.get('counterparty', ''),
                         customer_id=party, booked_on=bank['date'])
                i = dict(invoice_id=r['invoice_no'], customer_name=r.get('customer_name') or '', due_on=day(r['due_date']))
                ref = references(b, i)
                amount_match = r['amount_open_minor'] == vnd(bank['amount']) - used[tid]
                value = 1.0 if ref else round(.8 * score(b, i, ScoreConfig()) + .2 * int(amount_match), 4)
                evidence = [text for flag, text in ((ref, 'Khớp số hóa đơn'), (bool(party), 'Cùng khách hàng'),
                                                    (amount_match, 'Khớp số tiền còn lại')) if flag]
                ranked.append(dict(invoice_id=r['invoice_id'], customer_id=r['customer_id'],
                                   amount_open_minor=r['amount_open_minor'], score=value,
                                   evidence=evidence or ['Đối chiếu ngày và nội dung chứng từ']))
            ranked.sort(key=lambda r: (-r['score'], r['invoice_id']))
            result['cases'].append(dict(decision, bank_id=tid, account=bank['account'], date=bank['date'],
                                        available_minor=vnd(bank['amount']) - used[tid],
                                        memo=bank.get('memo', ''), reason_text=REASONS.get(decision['reason'], decision['reason']),
                                        candidates=ranked[:10], candidate_limit=200,
                                        allocations=allocations_by_bank[tid]))
        return result

    def check_review(self, proposal, txn_ids):
        if (proposal['cutoff'] != today() or proposal['ledger_sequence'] != len(self.ledger.events())
                or proposal['snapshot_hash'] != self.view(today())['snapshot_hash']):
            raise ValueError('Đề xuất đã cũ; cần chạy đối soát lại')
        if txn_ids & self.rejected_banks().keys():
            raise ValueError('Giao dịch đã bị từ chối; cần phân bổ thủ công với bằng chứng mới')

    def accept_batches(self, allocations, decision, actor, note, proposal_id):
        self.validate_managed()
        stamp = correction_time()
        banks = {r['bank_id']: r for r in self.data.get('bank', [])}
        rows = []
        for a in allocations:
            pid = self.payment_ids.get((a['txn_id'], a['invoice_id']), 'T9-' + fingerprint([decision, a])[:32])
            if any(r['payment_id'] == pid for r in self.data.get('payments', [])):
                raise ValueError('Mã thanh toán đã tồn tại')
            rows.append(dict(payment_id=pid, bank_id=a['txn_id'], invoice_id=a['invoice_id'], amount=a['amount_minor'],
                             payment_date=banks[a['txn_id']]['date'], known_at=today(), known_at_time=stamp,
                             t9_decision_id=decision))
        staged = merge_import(self.data, 'payments', rows)
        batches, fields = dataset_batches(staged)
        batches['company_t9_reviews'] = [dict(id=decision, action='accepted', decision_id=decision,
                                            reviewed_by=actor, note=note, proposal_id=proposal_id,
                                            known_at=today(), created_at=stamp,
                                            payment_ids=[r['payment_id'] for r in rows])]
        return batches, fields

    def reverse_batches(self, decision_id, actor, note):
        stamp = correction_time()
        review = next((r for r in self.reviews() if r['action'] == 'accepted' and r['decision_id'] == decision_id), None)
        if not review:
            raise ValueError('Không có quyết định phân bổ của Workspace')
        staged = deepcopy(self.data)
        removed = set(review['payment_ids'])
        history = staged.setdefault('record_history', {}).setdefault('payments', list(staged.get('payments', [])))
        staged['payments'] = [r for r in staged.get('payments', []) if r['payment_id'] not in removed]
        history.extend(dict(payment_id=pid, known_at=today(), known_at_time=stamp, _deleted=True) for pid in sorted(removed))
        validate_dataset(staged)
        batches, fields = dataset_batches(staged)
        identifier = 'R-' + fingerprint([decision_id, len(self.ledger.events())])[:32]
        batches['company_t9_reviews'] = [dict(id=identifier, action='reversed', decision_id=decision_id,
                                            reviewed_by=actor, note=note, known_at=today(),
                                            created_at=stamp)]
        return batches, fields

    def reject(self, key, proposal_id, bank_id, actor, note):
        actor, note = actor.strip(), note.strip()
        if not actor or not note:
            raise ValueError('Từ chối cần người xử lý và lý do')
        request_hash = fingerprint(dict(action='reject', proposal_id=proposal_id, bank_id=bank_id, actor=actor, note=note))
        with self.store.lock:
            cached = self.ledger.cached(key, request_hash)
            if cached:
                return cached
            proposal = self.store.one(self.firm, self.proposal_kind, proposal_id)
            if not proposal or bank_id not in {r['bank_id'] for r in proposal['cases']}:
                raise ValueError('Không tìm thấy giao dịch trong đề xuất')
            self.check_review(proposal, {bank_id})
            bank = next(r for r in self.data['bank'] if r['bank_id'] == bank_id)
            identifier = 'J-' + fingerprint([key, request_hash])[:32]
            record = dict(id=identifier, action='rejected', proposal_id=proposal_id, bank_id=bank_id,
                          bank_hash=fingerprint(bank), reviewed_by=actor, note=note, known_at=today(),
                          created_at=correction_time())
            return self.ledger.transact(key, [], request_hash=request_hash,
                                        batches={'company_t9_reviews': [record]}, result_fields=dict(review_id=identifier))

    def history(self):
        gold = self.ledger.gold(today())
        reviews = self.reviews()
        accepted = {r['decision_id']: r for r in reviews if r['action'] == 'accepted'}
        reversed_by = {r['decision_id']: r for r in reviews if r['action'] == 'reversed'}
        result = []
        for decision in gold['decisions']:
            record = accepted.get(decision['decision_id'], {})
            result.append(dict(decision, **{k: record.get(k, '') for k in ('reviewed_by', 'note', 'known_at', 'created_at')},
                               reversal=reversed_by.get(decision['decision_id'])))
        for r in reviews:
            if r['action'] == 'rejected':
                result.append(dict(r, status='rejected', decision_id=r['id'], allocations=[]))
            elif r['action'] == 'corrected':
                result.append(dict(r, status='corrected', decision_id=r['id'], allocations=[]))
        def ordering(row):
            stamp = (row.get('reversal') or row).get('created_at') or row['known_at']
            parsed = pd.Timestamp(stamp)
            if parsed.tzinfo is None:
                parsed = parsed.tz_localize('Asia/Ho_Chi_Minh')
            return row['known_at'], parsed.timestamp(), row['decision_id']
        return sorted(result, key=ordering, reverse=True)

    def correction_record(self, kind, identifier):
        fields = editable_fields(kind)
        row = next((r for r in self.data.get(kind, []) if r[IDS[kind]] == identifier), None)
        if row is None:
            raise ValueError('Không tìm thấy bản ghi của doanh nghiệp')
        if kind == 'payments' and row.get('t9_decision_id'):
            raise ValueError('Khoản phân bổ do T9 tạo: dùng Đảo quyết định rồi ghép lại, hoặc sửa hóa đơn/sao kê nguồn')
        return dict(kind=kind, identifier=identifier,
                    values={k: str(row[k]) if k in MONEY_FIELDS and k in row else row.get(k, '') for k in fields},
                    fields=fields, base_hash=fingerprint(self.data))

    def _stage_correction(self, changes, actor, note, correction_id, stamp):
        if not actor.strip() or not note.strip():
            raise ValueError('Sửa nguồn cần tên người xử lý và lý do / bằng chứng')
        if not changes or len(changes) > 20:
            raise ValueError('Mỗi lần sửa từ 1 đến 20 bản ghi')
        staged, edits, seen = deepcopy(self.data), [], set()
        seed_invoices, seed_banks = set(), set()
        critical_i = {'customer_id', 'issue_date', 'amount', 'currency', 'amount_net', 'vat', 'seller_mst',
                      'buyer_mst', 'symbol', 'invoice_no', 'adjustment_type', 'adjusts_invoice_id',
                      'adjusts_symbol', 'adjusts_invoice_no', 'adjusts_issue_date'}
        critical_b = {'account', 'date', 'direction', 'amount', 'currency', 'customer_id', 'component', 'cash_flow_class'}
        for change in changes:
            kind, identifier, values = change['kind'], change['identifier'], change['values']
            record = self.correction_record(kind, identifier)
            if (kind, identifier) in seen or not values or set(values) - set(record['fields']):
                raise ValueError('Bản ghi trùng, không có nội dung sửa hoặc có trường không được sửa')
            if any(not isinstance(v, (str, int, type(None))) or isinstance(v, bool) for v in values.values()):
                raise ValueError('Nhập giá trị sửa bằng chữ hoặc số nguyên; ngày dùng YYYY-MM-DD, tiền VND nguyên')
            seen.add((kind, identifier))
            before = next(r for r in self.data[kind] if r[IDS[kind]] == identifier)
            raw = {k: before.get(k, '') for k in SCHEMAS[kind]}
            raw.update(values, known_at=today())
            if kind == 'invoices':
                raw['record_version'] = str(before.get('record_version', 1) + 1)
            parsed, errors, _ = parse_rows(pd.DataFrame([raw]), kind, {k:k for k in raw}, '%Y-%m-%d', 'plain')
            if errors or not parsed:
                raise ValueError('; '.join(e['column'] + ': ' + e['message'] for e in errors))
            after = {k:v for k,v in before.items() if k not in SCHEMAS[kind]}
            after.update(parsed[0], known_at=today(), known_at_time=stamp, correction_id=correction_id)
            def comparable(value):
                return '' if value is None else value
            changed = [k for k in record['fields'] if comparable(before.get(k, '')) != comparable(after.get(k, ''))]
            if not changed:
                raise ValueError('Bản ghi ' + identifier + ' chưa có thay đổi')
            if kind == 'invoices':
                after['revision'] = before.get('revision', 1) + 1
                if ACCOUNTING <= after.keys():
                    # Original file evidence stays in the old version. The new
                    # canonical facts explicitly cite the reviewed correction.
                    for field in ('source_ids', 'source_versions', 'source_payloads', 'source_lineage'):
                        after[field] = deepcopy(before.get(field, {}))
                    after['source_ids']['workspace_correction'] = identifier
                    after['source_versions']['workspace_correction'] = after['record_version']
                    after['source_payloads']['workspace_correction'] = {k:after[k] for k in SCHEMAS[kind] if k in after}
                    after['source_lineage']['workspace_correction'] = dict(reference=note, reviewed_by=actor, correction_id=correction_id)
                    after['sources'] = sorted(set(before.get('sources', [])) | {'workspace_correction'})
                    after['source_file'] = 'workspace-correction:' + correction_id
                    after['source_row'] = 1
                    after['source_sha256'] = fingerprint(dict(values=values, reviewed_by=actor, note=note))
            edits.append(dict(kind=kind, identifier=identifier, before=before, after=after, changed_fields=changed))
            if kind == 'invoices' and set(changed) & critical_i:
                seed_invoices.add(identifier)
            elif kind == 'bank' and set(changed) & critical_b:
                seed_banks.add(identifier)
            elif kind == 'payments':
                seed_invoices.update((before['invoice_id'], after['invoice_id']))
                seed_banks.update(r['bank_id'] for r in (before, after) if r.get('bank_id'))

        links = _payment_links(self.data.get('invoices', []))
        family = lambda iid: payment_target(iid, links)
        affected_families = {family(iid) for iid in seed_invoices}
        gold = self.ledger.gold(today())
        active = [d for d in gold['decisions'] if d['status'] == 'committed']
        for receipt in self.data.get('payments', []):
            if family(receipt['invoice_id']) in affected_families and receipt.get('bank_id'):
                seed_banks.add(receipt['bank_id'])
        affected_decisions = {}
        while True:
            added = False
            for decision in active:
                if decision['decision_id'] in affected_decisions:
                    continue
                if any(a['payment_id'] in seed_banks or family(a['invoice_id']) in affected_families for a in decision['allocations']):
                    affected_decisions[decision['decision_id']] = decision
                    seed_banks.update(a['payment_id'] for a in decision['allocations'])
                    added = True
            if not added:
                break
        removed_payments = [r for r in self.data.get('payments', [])
                            if r.get('bank_id') in seed_banks or family(r['invoice_id']) in affected_families]
        removed_actions = [r for r in self.data.get('actions', []) if family(r['invoice_id']) in affected_families]

        def replace(kind, row, *, deleted=False):
            identifier = row[IDS[kind]]
            history = staged.setdefault('record_history', {}).setdefault(kind, deepcopy(staged.get(kind, [])))
            staged[kind] = [r for r in staged.get(kind, []) if r[IDS[kind]] != identifier]
            history.append(dict(row))
            if not deleted:
                staged[kind].append(dict(row))

        for kind, rows in (('payments', removed_payments), ('actions', removed_actions)):
            for row in rows:
                replace(kind, {IDS[kind]:row[IDS[kind]], 'known_at':today(), 'known_at_time':stamp,
                               '_deleted':True, 'correction_id':correction_id}, deleted=True)
        for edit in edits:
            replace(edit['kind'], edit['after'])
        # Validate the whole amended dataset, including lifecycle identities,
        # imported receipts and statement opening/movement/closing balances.
        validate_dataset(staged)
        full = [r for r in staged.get('invoices', []) if ACCOUNTING <= r.keys()]
        business_keys = [(r['seller_mst'], r['symbol'], r['invoice_no']) for r in full]
        if len(set(business_keys)) != len(business_keys):
            raise ValueError('Bản sửa trùng MST/ký hiệu/số của hóa đơn khác')
        commands, review_rows = [], []
        for did in sorted(affected_decisions):
            commands.append(dict(tenant_id=self.firm, action='reverse', decision_id=did,
                                 effective_on=today(), available_on=today(), reviewed_by=actor, note=note))
            review_rows.append(dict(id=correction_id + ':' + did, action='reversed', decision_id=did,
                                    reviewed_by=actor, note=note, known_at=today(), created_at=stamp, correction_id=correction_id))
        corrected_banks = []
        for edit in edits:
            if edit['kind'] == 'bank' and set(edit['changed_fields']) & critical_b:
                r = edit['after']
                corrected_banks.append(dict(tenant_id=self.firm, id=r['bank_id'], currency='VND',
                    account_id=r['account'], direction='credit' if r['direction'] == 'in' else 'debit',
                    amount_minor=vnd(r['amount']), effective_on=r['date'], source_ref=correction_id))
        commands.append(dict(tenant_id=self.firm, action='correct_source', correction_id=correction_id,
            effective_on=today(), available_on=today(), reviewed_by=actor, note=note,
            reset_invoices=sorted(r['id'] for r in gold['invoices'] if family(r['id']) in affected_families),
            reset_payments=sorted(seed_banks), banks=corrected_banks))
        prospective = self.ledger._gold(self.ledger.events() + commands, today())
        WorkspaceSource(self.store, self.firm, staged).validate_managed(prospective)
        summary = dict(changes=[dict(kind=e['kind'], identifier=e['identifier'], changed_fields=e['changed_fields'],
                       before={k:e['before'].get(k, '') for k in editable_fields(e['kind'])},
                       after={k:e['after'].get(k, '') for k in editable_fields(e['kind'])}) for e in edits],
                       affected_decisions=list(affected_decisions.values()),
                       affected_payments=removed_payments, affected_actions=removed_actions)
        return staged, commands, review_rows, summary

    def preview_correction(self, changes, actor, note):
        identifier, stamp = 'C-' + uuid.uuid4().hex, correction_time()
        staged, _, _, summary = self._stage_correction(changes, actor.strip(), note.strip(), identifier, stamp)
        result = dict(id=identifier, kind='source_correction', changes_input=changes, reviewed_by=actor.strip(), note=note.strip(),
                      base_hash=fingerprint(self.data), ledger_sequence=len(self.ledger.events()),
                      created_at=stamp, created_on=today(), **summary)
        return result, staged

    def commit_correction(self, preview, key, *, validate_scope=None):
        request_hash = fingerprint(dict(action='correct_source', preview_id=preview['id'],
                                        reviewed_by=preview['reviewed_by'], note=preview['note']))
        cached = self.ledger.cached(key, request_hash)
        if cached:
            return cached
        if (preview['created_on'] != today() or preview['base_hash'] != fingerprint(self.data)
                or preview['ledger_sequence'] != len(self.ledger.events())):
            raise ValueError('Dữ liệu hoặc ledger đã đổi; xem trước bản sửa lại')
        stamp = correction_time()
        staged, commands, reviews, summary = self._stage_correction(preview['changes_input'], preview['reviewed_by'],
            preview['note'], preview['id'], stamp)
        if validate_scope:
            validate_scope(staged)
        batches, result = dataset_batches(staged)
        reviews.append(dict(id=preview['id'], action='corrected', correction_id=preview['id'], reviewed_by=preview['reviewed_by'],
            note=preview['note'], known_at=today(), created_at=stamp, before_version=preview['base_hash'],
            after_version=result['version'], changes=summary['changes'], affected_payments=summary['affected_payments'],
            affected_actions=summary['affected_actions'], reversed_decisions=[d['decision_id'] for d in summary['affected_decisions']]))
        batches['company_t9_reviews'] = reviews
        return self.ledger.transact(key, commands, request_hash=request_hash, batches=batches,
            result_fields=dict(result, correction_id=preview['id'], reversed_count=len(summary['affected_decisions']),
                               released_payments=len(summary['affected_payments']), created_at=stamp))
