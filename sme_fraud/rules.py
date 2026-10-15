"""Causal, explainable rule baseline for rule_class_1.md. No truth inputs."""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict, deque
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from .features import FEATURE_DESCRIPTIONS, Stream, UnionFind, build_features
from .generate import parse as _parse
from .temporal_evidence import (BankChangeHistory, ObservedVersions, bank_change_state,
                                approved_evidence, paid_leave_entitlement)

parse = lru_cache(maxsize=150000)(_parse)

RULE_NAMES = {
    'A1': 'Chia nhỏ cùng người nhận trong 3 ngày',
    'A2': 'Chia nhỏ cùng người lập/người nhận trong 30 ngày',
    'A3': 'Chia nhỏ qua cụm người nhận liên kết',
    'A4': 'Người lập có nhiều khoản cận hạn mức',
    'A5': 'Số tiền tròn lệch baseline lịch sử',
    'A6': 'Thanh toán làm tròn vượt hóa đơn gốc',
    'B1': 'Tài khoản hoặc căn cước NCC trùng nhân viên',
    'B2': 'Thông tin hoặc người đại diện NCC liên kết nhân viên',
    'B3': 'NCC mới thành lập nhận giao dịch lớn đầu tiên',
    'B4': 'Trạng thái người phát hành hóa đơn rủi ro',
    'B5': 'Nhiều NCC chung thông tin định danh',
    'B6': 'NCC ngủ đông nhận khoản lớn',
    'B7': 'Đổi tài khoản gần ngày thanh toán chưa xác minh',
    'C1': 'Lập hoặc duyệt ngoài lịch vận hành',
    'C2': 'Tự duyệt vượt quyền được cấp',
    'C3': 'Duyệt dưới 60 giây ở cấp thẩm quyền cao',
    'C4': 'Thao tác trong kỳ nghỉ phép chính thức',
    'D1': 'Benford chữ số đầu', 'D2': 'Benford chữ số thứ hai',
    'D3': 'Hai chữ số đầu sát hạn mức', 'D4': 'Đuôi số đặc biệt vượt baseline',
    'D5': 'MAD chữ số đầu', 'D6': 'Benford theo phân đoạn',
    'E1': 'Lương không có chấm công hoặc bằng chứng thay thế',
    'E2': 'Lương sau chấm dứt hợp đồng',
    'E3': 'Tên NCC tương tự', 'E4': 'NCC trùng định danh',
    'F1': 'Điều chỉnh thủ công sát khóa sổ và trọng yếu',
    'F2': 'Quản lý ghi đè quy trình', 'F3': 'Khoảng trống/trùng số chứng từ',
    'F4': 'Doanh thu/công nợ kéo dài chưa đối chiếu tiền',
    'P1': 'Thanh toán vượt tổng giá trị cùng hóa đơn',
    'T1': 'Tạm ứng còn dư nợ quá hạn', 'T2': 'Xóa nợ tạm ứng thiếu hồ sơ',
}
WEIGHTS = dict(A1=8, A2=4, A3=8, A4=3, A5=3, A6=8,
               B1=20, B2=8, B3=8, B4=10, B5=3, B6=8, B7=20,
               C1=1, C2=20, C3=8, E1=20, E3=3, E4=3, F1=8,
               P1=20, T1=8, T2=20)
HARD_TRIGGERS = {'B1', 'B7', 'C2', 'E1', 'P1', 'T2'}
DEFAULT_CONFIG = dict(short_days=3, long_days=30, short_total_ratio=.85,
                      near_low=.8, near_high=.99, near_count=3,
                      baseline_min=20, round_z=2., vendor_new_days=90,
                      dormant_days=180, bank_change_days=14, close_days=5,
                      advance_grace_days=0, operational_score=7,
                      materiality_vnd_by_company={}, high_approval_vnd=50_000_000,
                      fuzzy_similarity=.85, recurrence_cap=3)
DEFAULT_CONFIG['enable_graph'] = True
INPUT_TABLES = ('companies', 'employees', 'vendors', 'customers', 'calendar',
                'entity_links', 'attendance', 'vendor_status_history',
                'bank_account_changes', 'advances', 'advance_events', 'transactions')
OPTIONAL_INPUT_TABLES = ('payroll_entitlements', 'supplier_payment_agreements')


@lru_cache(maxsize=100000)
def normalize(value, kind='text'):
    """Preserve identifiers/leading zeros; never turn missing values into matches."""
    value = str(value or '').strip().upper().replace('Đ', 'D')
    value = ''.join(c for c in unicodedata.normalize('NFD', value)
                    if unicodedata.category(c) != 'Mn')
    value = re.sub(r'[^A-Z0-9]', '', value)
    if kind == 'phone' and value.isdigit():
        if value.startswith('0084') and len(value) == 13:
            value = '0' + value[4:]
        elif value.startswith('84') and len(value) == 11:
            value = '0' + value[2:]
    return value


def load_inputs(directory: Path):
    """Explicit whitelist: labels/splits cannot enter the detector."""
    meta = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    tables = {}
    for name in INPUT_TABLES:
        path = directory / f'{name}.csv'
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta['files'][path.name]['sha256']:
            raise ValueError(f'Input checksum differs from dataset manifest: {path.name}')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            tables[name] = list(csv.DictReader(stream))
    for name in OPTIONAL_INPUT_TABLES:
        path = directory / f'{name}.csv'
        if not path.exists():
            tables[name] = []
            continue
        entry = meta['files'].get(path.name)
        if not entry or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Optional evidence checksum missing/differs: {path.name}')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            tables[name] = list(csv.DictReader(stream))
    feature_path = directory / 'features.csv'
    # Cached causal features are an existing dataset artifact, not label-derived.
    entry = meta['files']['features.csv']
    expected_hash = entry.get('sha256') if isinstance(entry, dict) else entry
    if hashlib.sha256(feature_path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('features.csv checksum differs from dataset manifest')
    with feature_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['transaction_id', *FEATURE_DESCRIPTIONS]:
            raise ValueError('Feature schema differs from the explicit causal allowlist')
        features = [{k: v if k == 'transaction_id' else float(v) for k, v in row.items()}
                    for row in reader]
    return tables, features, meta


def long_installment_exception(row, group, invoice_history, contract_history, agreements, staff, now):
    """Exempt only the actual A2 window; all-time totals still constrain it."""
    scoped = [*group, row]
    documented = all(int(r['support_doc_count']) > 0 and
                     r.get('support_docs_observed_at', r['posted_at']) <= now for r in scoped)
    number = normalize(row['invoice_number'])
    gross = int(row['invoice_gross_vnd'])
    same_invoice = bool(number) and all(r['company_id'] == row['company_id'] and
        r['vendor_id'] == row['vendor_id'] and normalize(r['invoice_number']) == number for r in scoped)
    cumulative = sum(int(r['amount_vnd']) for r in invoice_history) + int(row['amount_vnd'])
    consistent = all(int(r['invoice_gross_vnd']) == gross for r in invoice_history)
    if documented and same_invoice and gross > 0 and consistent and cumulative <= gross:
        return 'Các đợt cùng hóa đơn trong cửa sổ A2, có hồ sơ và tổng toàn lịch sử chưa vượt hóa đơn', dict(
            basis='invoice', invoice_number=row['invoice_number'], invoice_gross_vnd=gross,
            cumulative_paid_vnd=cumulative,
            historical_payment_ids=[r['transaction_id'] for r in invoice_history])
    contract = row.get('contract_id', '')
    same_contract = bool(contract) and all(r.get('contract_id') == contract and
        r['company_id'] == row['company_id'] and r['vendor_id'] == row['vendor_id'] for r in scoped)
    records = [r for r in agreements if r.get('contract_id') == contract]
    agreement = max(records, key=lambda r: (r['observed_at'], r['agreement_id']), default=None)
    current_invoice_cap_ok = not number or (gross > 0 and consistent and cumulative <= gross)
    if documented and same_contract and current_invoice_cap_ok and agreement and approved_evidence(agreement, staff, row['company_id'], now):
        total = sum(int(r['amount_vnd']) for r in contract_history) + int(row['amount_vnd'])
        ceiling = int(agreement.get('total_vnd', 0))
        by_invoice = defaultdict(list)
        for payment in [*contract_history, row]:
            if normalize(payment['invoice_number']):
                by_invoice[normalize(payment['invoice_number'])].append(payment)
        invoice_caps_ok = all(int(payments[-1]['invoice_gross_vnd']) > 0 and
            all(int(r['invoice_gross_vnd']) == int(payments[-1]['invoice_gross_vnd']) for r in payments) and
            sum(int(r['amount_vnd']) for r in payments) <= int(payments[-1]['invoice_gross_vnd'])
            for payments in by_invoice.values())
        if total <= ceiling and ceiling > 0 and invoice_caps_ok:
            return 'Các đợt cùng hợp đồng đã duyệt, có hồ sơ và tổng chưa vượt hợp đồng/hóa đơn', dict(
                basis='contract', contract_id=contract, agreement_id=agreement['agreement_id'],
                observed_at=agreement['observed_at'], approved_at=agreement['approved_at'],
                evidence_id=agreement['evidence_id'], total_vnd=ceiling, cumulative_paid_vnd=total,
                historical_payment_ids=[r['transaction_id'] for r in contract_history])
    return '', dict(basis='no_valid_installment_evidence', same_invoice=same_invoice,
                    same_contract=same_contract, invoice_cumulative_paid_vnd=cumulative)


class KnownGraph:
    """As-of, company-scoped strong links with readable BFS evidence paths."""
    def __init__(self):
        self.groups = defaultdict(UnionFind)
        self.adjacency = defaultdict(lambda: defaultdict(dict))

    @staticmethod
    @lru_cache(maxsize=100000)
    def node(value, kind):
        return f'{kind}:{normalize(value, kind)}'

    def add(self, cid, left, right, at, kind):
        if not left or not right or left.endswith(':') or right.endswith(':'):
            return
        self.groups[cid].join(left, right)
        edge = dict(source=left, target=right, link_type=kind, observed_at=at)
        self.adjacency[cid][left][right] = edge
        self.adjacency[cid][right][left] = edge

    def path(self, cid, start, targets, max_depth=6):
        pending, seen = deque([(start, [])]), {start}
        while pending:
            node, path = pending.popleft()
            if node in targets and node != start:
                return path
            if len(path) >= max_depth:
                continue
            for other, edge in sorted(self.adjacency[cid][node].items()):
                if other not in seen:
                    seen.add(other)
                    pending.append((other, path + [edge]))
        return []


def rule_coverage():
    """Coverage is capability, not a claim that no hits means no fraud."""
    gaps = {
        'C4': 'Thiếu lịch nghỉ phép theo ngày và log thao tác; approved_leave_days tổng tháng không đủ.',
        'E2': 'Thiếu ngày chấm dứt HĐLĐ, kỳ công và loại khoản quyết toán cuối cùng.',
        'F2': 'Thiếu log override, quyền đặc biệt và luồng phê duyệt chuẩn.',
        'F3': 'ID giao dịch ngẫu nhiên không phải số chứng từ; thiếu sổ đăng ký số/hủy chứng từ.',
        'F4': 'Thiếu liên kết thu tiền-hóa đơn, hạn thanh toán và giải trình công nợ.',
    }
    partial = {
        'A3': 'Gom TK/SĐT/người đại diện; địa chỉ chung đơn lẻ chỉ là tín hiệu yếu B5/E4.',
        'B1': 'Đối chiếu TK ngân hàng; chưa có CCCD và mã ngân hàng để phân biệt số trùng giữa ngân hàng.',
        'B4': 'Lịch sử trạng thái tổng hợp theo observed_at; chưa kết nối cổng thuế/ngành nghề.',
        'B7': 'Có lịch đổi TK/callback/người duyệt; chưa có nguồn email BEC.',
        'E3': 'SequenceMatcher trên tên chuẩn hóa là proxy, không phải Levenshtein/Jaro-Winkler.',
        'F1': 'txn_type=adjustment là proxy thủ công; trọng yếu theo config hoặc hạn mức người lập.',
        'D3': 'Hai chữ số đầu cận hạn mức theo từng người lập; sàng lọc thống kê, không chứng minh ý đồ.',
        'D4': 'Dùng baseline đuôi thực nghiệm kỳ trước thay giả định đuôi phân bố đều.',
    }
    return [dict(rule_id=code, group=code[0], name=name,
                 source='rule_class_1.md' if code[0] not in 'PT' else 'original_six_fraud_families',
                 status='not_evaluable' if code in gaps else 'partial' if code in partial else 'implemented',
                 note=gaps.get(code, partial.get(code, '')),
                 scope='aggregate_diagnostic' if code.startswith('D') else 'transaction')
            for code, name in RULE_NAMES.items()]


def score_rules(tables, config=None, features=None):
    if set(config or {}) - set(DEFAULT_CONFIG):
        raise ValueError(f'Unknown rule config keys: {set(config) - set(DEFAULT_CONFIG)}')
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if cfg['short_days'] <= 0 or cfg['long_days'] < cfg['short_days']:
        raise ValueError('Invalid rule windows')
    if not 0 < cfg['near_low'] <= cfg['near_high'] < 1:
        raise ValueError('Invalid near-limit range')
    rows = sorted(tables['transactions'], key=lambda r: (r['posted_at'], r['transaction_id']))
    features = build_features(tables) if features is None else features
    feature_map = {r['transaction_id']: r for r in features}
    if len(feature_map) != len(features) or set(feature_map) != {r['transaction_id'] for r in rows}:
        raise ValueError('Causal features must map one-to-one to observations')
    masters = {name: Stream(tables[name], 'recorded_at') for name in ('employees', 'vendors')}
    links = Stream(tables['entity_links'])
    bank_changes = BankChangeHistory(tables['bank_account_changes'])
    entitlements = ObservedVersions(tables.get('payroll_entitlements', []), 'entitlement_id')
    agreements = ObservedVersions(tables.get('supplier_payment_agreements', []), 'agreement_id')
    staff, vendors = {}, {}
    fuzzy_matches = defaultdict(dict)
    employee_index = defaultdict(set)
    vendor_index = defaultdict(set)
    graph = KnownGraph()
    histories = defaultdict(deque)
    recipient_payments = defaultdict(deque)
    vendor_windows = defaultdict(deque)
    company_vendors = defaultdict(set)
    creator_payments = defaultdict(deque)
    invoice_payments = defaultdict(list)
    contract_payments = defaultdict(list)
    vendor_amounts = defaultdict(list)
    moments = defaultdict(lambda: [0, 0., 0.])
    previous_risk = defaultdict(deque)
    companies = {r['company_id']: r for r in tables['companies']}
    holidays = {r['date'] for r in tables['calendar'] if int(r.get('is_holiday', 1))}
    scores, hits = [], []
    for now, batch_iter in groupby(rows, key=lambda r: r['posted_at']):
        batch = list(batch_iter)
        at = parse(now)
        for name, stream in masters.items():
            for item in stream.until(now):
                cid = item['company_id']
                key = item['employee_id'] if name == 'employees' else item['vendor_id']
                target, index = (staff, employee_index) if name == 'employees' else (vendors, vendor_index)
                old = target.get(key)
                for field in ('bank_account', 'phone', 'address', 'national_id'):
                    if old:
                        index[(cid, field, normalize(old.get(field), field))].discard(key)
                    token = normalize(item.get(field), field)
                    if token:
                        index[(cid, field, token)].add(key)
                target[key] = item
                if name == 'vendors':
                    company_vendors[cid].add(key)
                    fuzzy_matches[key].clear()
                    for other_id, other in vendors.items():
                        if other_id == key or other['company_id'] != cid:
                            continue
                        fuzzy_matches[other_id].pop(key, None)
                        similarity = SequenceMatcher(None, normalize(item['name']), normalize(other['name'])).ratio()
                        if similarity > cfg['fuzzy_similarity']:
                            fuzzy_matches[key][other_id] = round(similarity, 4)
                            fuzzy_matches[other_id][key] = round(similarity, 4)
                # Master matches themselves are evidence, including datasets without entity_links.
                for field in ('bank_account', 'phone'):
                    if item.get(field):
                        graph.add(cid, graph.node(key, 'entity'), graph.node(item[field], field),
                                  item['recorded_at'], field)
        for edge in links.until(now):
            if edge['link_type'] not in {'bank_account', 'phone', 'representative'}:
                continue
            right_kind = 'entity' if edge['link_type'] == 'representative' else edge['link_type']
            graph.add(edge['company_id'], graph.node(edge['source_id'], 'entity'),
                      graph.node(edge['target_id'], right_kind), edge['observed_at'], edge['link_type'])
        bank_changes.advance(now)
        entitlements.advance(now)
        agreements.advance(now)
        batch_scores = []
        for row in batch:
            tid, cid = row['transaction_id'], row['company_id']
            vid, eid, maker = row['vendor_id'], row['employee_id'], row['creator_id']
            amount, limit = int(row['amount_vnd']), int(row['approval_limit_vnd'])
            if amount < 0 or limit <= 0:
                raise ValueError(f'Invalid amount/approval limit: {tid}')
            feature = feature_map[tid]
            v, user = vendors.get(vid), staff.get(maker)
            if not user or user['company_id'] != cid:
                raise ValueError(f'Unknown or cross-company maker at scoring time: {tid}')
            payment = row['txn_type'] == 'vendor_payment'
            financial = int(row['is_financial_entry']) == 1
            recipient = normalize(row['recipient_account'], 'bank_account')
            entity = vid or eid or maker
            risk_key = (cid, entity)
            records = histories[cid]
            while records and (at - parse(records[0]['posted_at'])).total_seconds() > cfg['long_days'] * 86400:
                records.popleft()
            prior_risk = previous_risk[risk_key]
            while prior_risk and (at - parse(prior_risk[0][0])).total_seconds() > 30 * 86400:
                prior_risk.popleft()
            current_hits = []

            def emit(code, evidence, related=(), path=(), weight=None, suppressed=''):
                current_hits.append(dict(transaction_id=tid, company_id=cid, detected_at=now,
                    rule_id=code, rule_name=RULE_NAMES[code], points=0 if suppressed else WEIGHTS.get(code, 0) if weight is None else weight,
                    hard_trigger=int(code in HARD_TRIGGERS and not suppressed), suppressed_reason=suppressed,
                    evidence=evidence, related_transaction_ids=sorted(set(related)), graph_path=list(path)))

            # The current observation participates; every other observation is strictly earlier.
            if payment and recipient:
                same_queue = recipient_payments[(cid, recipient)]
                while same_queue and (at - parse(same_queue[0]['posted_at'])).total_seconds() > cfg['long_days'] * 86400:
                    same_queue.popleft()
                same = [r for r in same_queue if int(r['amount_vnd']) < int(r['approval_limit_vnd'])]
                short = [r for r in same if (at - parse(r['posted_at'])).total_seconds() <= cfg['short_days'] * 86400]
                same_maker = [r for r in same if r['creator_id'] == maker]
                candidate = amount < limit
                invoice_key = (cid, vid, normalize(row['invoice_number']))
                previous_invoice = invoice_payments[invoice_key]
                gross = int(row['invoice_gross_vnd'])
                total_invoice = sum(int(r['amount_vnd']) for r in previous_invoice) + amount
                same_invoice_short = bool(short and all(normalize(r['invoice_number']) == invoice_key[2]
                                                       and r['vendor_id'] == vid for r in short))
                documented_installment = (same_invoice_short and gross > 0 and total_invoice <= gross
                                          and int(row['support_doc_count']) > 0)
                exception = 'Các đợt cùng hóa đơn, có hồ sơ và tổng chưa vượt giá trị hóa đơn' if documented_installment else ''
                if candidate and short and sum(int(r['amount_vnd']) for r in short) + amount >= cfg['short_total_ratio'] * limit:
                    emit('A1', dict(count=len(short) + 1, total_vnd=sum(int(r['amount_vnd']) for r in short) + amount,
                                   approval_limit_vnd=limit, window_days=cfg['short_days']),
                         [r['transaction_id'] for r in short], suppressed=exception)
                if candidate and len(same_maker) >= 2 and sum(int(r['amount_vnd']) for r in same_maker) + amount >= limit:
                    long_exception, installment_evidence = long_installment_exception(
                        row, same_maker, previous_invoice,
                        contract_payments[(cid, vid, row.get('contract_id', ''))],
                        agreements.records(cid, vid), staff, now)
                    emit('A2', dict(count=len(same_maker) + 1, total_vnd=sum(int(r['amount_vnd']) for r in same_maker) + amount,
                                   approval_limit_vnd=limit, window_days=cfg['long_days'],
                                   installment_check=installment_evidence),
                         [r['transaction_id'] for r in same_maker], suppressed=long_exception)
                g, node = graph.groups[cid], graph.node(vid, 'entity')
                connected = {other for other in company_vendors[cid]
                             if cfg['enable_graph'] and g.root(graph.node(other, 'entity')) == g.root(node)}
                network = []
                if len(connected) > 1:
                    for other in connected:
                        queue = vendor_windows[(cid, other)]
                        while queue and (at - parse(queue[0]['posted_at'])).total_seconds() > cfg['long_days'] * 86400:
                            queue.popleft()
                        network.extend(r for r in queue if int(r['amount_vnd']) < int(r['approval_limit_vnd']))
                other_vendors = {r['vendor_id'] for r in network} - {vid}
                total_network = sum(int(r['amount_vnd']) for r in network) + amount
                if cfg['enable_graph'] and candidate and other_vendors and len(network) >= 2 and total_network >= limit:
                    emit('A3', dict(vendor_ids=sorted(other_vendors | {vid}), total_vnd=total_network,
                                   approval_limit_vnd=limit, window_days=cfg['long_days']),
                         [r['transaction_id'] for r in network],
                         graph.path(cid, node, {graph.node(x, 'entity') for x in other_vendors}))
                if previous_invoice and gross > 0 and total_invoice > gross + 1:
                    emit('P1', dict(invoice_number=row['invoice_number'], invoice_gross_vnd=gross,
                                    cumulative_paid_vnd=total_invoice, excess_vnd=total_invoice - gross),
                         [r['transaction_id'] for r in previous_invoice])
                if gross > 0 and gross % 1000 and amount % 1000 == 0 and amount > gross + 1:
                    emit('A6', dict(payment_vnd=amount, invoice_gross_vnd=gross, difference_vnd=amount - gross))
            creator_rows = creator_payments[(cid, maker)]
            while creator_rows and (at - parse(creator_rows[0]['posted_at'])).total_seconds() > 30 * 86400:
                creator_rows.popleft()
            is_disbursement = financial and row['payment_channel'] in {'bank', 'cash'} and row['txn_type'] != 'customer_receipt'
            near = is_disbursement and cfg['near_low'] <= amount / limit <= cfg['near_high']
            near_rows = [r for r in creator_rows if cfg['near_low'] <= int(r['amount_vnd']) / int(r['approval_limit_vnd']) <= cfg['near_high']]
            if near and len(near_rows) + 1 >= cfg['near_count']:
                emit('A4', dict(count=len(near_rows) + 1, window_days=30, low=cfg['near_low'], high=cfg['near_high']),
                     [r['transaction_id'] for r in near_rows])
            baseline_key = (cid, row['txn_type'], vid)
            fallback_key = (cid, row['txn_type'], '')
            num, mean, m2 = moments[baseline_key]
            if num < cfg['baseline_min']:
                num, mean, m2 = moments[fallback_key]
                baseline_key = fallback_key
            sd = math.sqrt(m2 / max(1, num - 1))
            if financial and num >= cfg['baseline_min'] and sd > 0 and amount % 1000 == 0 and (amount - mean) / sd > cfg['round_z']:
                emit('A5', dict(baseline_rows=num, baseline_mean_vnd=round(mean), baseline_sd_vnd=round(sd),
                               z=round((amount - mean) / sd, 4), scope=list(baseline_key)))
            disclosed = bool(v and v.get('related_party_disclosed_at') and v['related_party_disclosed_at'] <= now)
            if v:
                direct_bank = employee_index[(cid, 'bank_account', recipient)] if recipient and payment else set()
                national = employee_index[(cid, 'national_id', normalize(v.get('national_id')))] if v.get('national_id') else set()
                if direct_bank or national:
                    emit('B1', dict(employee_ids=sorted(direct_bank | national), recipient_account=row['recipient_account'],
                                    related_party_disclosed=disclosed), weight=4 if disclosed else None)
                    if disclosed:
                        current_hits[-1]['hard_trigger'] = 0
                matches = {field: sorted(employee_index[(cid, field, normalize(v.get(field), field))])
                           for field in ('phone', 'address') if normalize(v.get(field), field)}
                matches = {k: value for k, value in matches.items() if value}
                targets = {graph.node(e, 'entity') for e, employee in staff.items() if employee['company_id'] == cid}
                path = graph.path(cid, graph.node(vid, 'entity'), targets) if cfg['enable_graph'] else []
                if matches or path:
                    emit('B2', dict(direct_matches=matches, field_count=len(matches), related_party_disclosed=disclosed),
                         path=path, weight=8 if len(matches) >= 2 or path else 3,
                         suppressed='Bên liên quan đã công bố trước giao dịch' if disclosed else '')
                history_amounts = vendor_amounts[(cid, vid)]
                age = (at - parse(v['registered_at'])).days
                type_moments = moments[fallback_key]
                large = amount >= limit or (type_moments[0] >= cfg['baseline_min'] and amount > type_moments[1] + 2 * math.sqrt(type_moments[2] / max(1, type_moments[0] - 1)))
                if not history_amounts and 0 <= age < cfg['vendor_new_days'] and large:
                    emit('B3', dict(vendor_age_days=age, amount_vnd=amount, large_reference_limit_vnd=limit),
                         suppressed='Có xác nhận giao nhận và hồ sơ' if int(row['goods_receipt_verified']) and int(row['support_doc_count']) >= 2 else '')
                if feature['registry_risky_at_invoice']:
                    emit('B4', dict(invoice_issued_at=row['invoice_issued_at'], risky_at_invoice=1,
                                   registry_risky_now=int(feature['registry_risky_now'])))
                elif feature['registry_risky_now']:
                    emit('B4', dict(invoice_issued_at=row['invoice_issued_at'], risky_at_invoice=0, registry_risky_now=1),
                         weight=3, suppressed='Hóa đơn trước trạng thái rủi ro, có xác nhận giao nhận' if int(row['goods_receipt_verified']) else '')
                duplicates = {field: sorted(vendor_index[(cid, field, normalize(v.get(field), field))] - {vid})
                              for field in ('bank_account', 'phone', 'address') if normalize(v.get(field), field)}
                duplicates = {k: value for k, value in duplicates.items() if value}
                if duplicates:
                    evidence = dict(shared_fields=duplicates, vendor_ids=sorted({vid} | {x for value in duplicates.values() for x in value}))
                    weak = set(duplicates) == {'address'}
                    emit('B5', evidence, weight=1 if weak else 3)
                    emit('E4', evidence, weight=1 if weak else 3)
                if payment and len(history_amounts) >= cfg['baseline_min']:
                    idle = (at - parse(history_amounts[-1][0])).days
                    values = sorted(item[1] for item in history_amounts)
                    p90 = values[math.ceil(.9 * len(values)) - 1]
                    if idle >= cfg['dormant_days'] and amount > p90:
                        emit('B6', dict(idle_days=idle, prior_p90_vnd=p90, amount_vnd=amount))
                change = bank_changes.current(cid, vid, now)
                recent, verified = bank_change_state(change, row, staff, now, cfg['bank_change_days'])
                if payment and recent:
                    emit('B7', dict(change_id=change['change_id'], effective_at=change['effective_at'],
                                    observed_at=change['observed_at'],
                                    verified_at=change['verified_at'], approver_id=change['approver_id']),
                         suppressed='Callback và người duyệt độc lập đã xác minh trước thanh toán' if verified else '')
                similar = [(value, key) for key, value in fuzzy_matches[vid].items()]
                if similar:
                    emit('E3', dict(matched_vendor_count=len(similar), top_matches=sorted(similar, reverse=True)[:5],
                                    algorithm='difflib.SequenceMatcher', threshold=cfg['fuzzy_similarity']))
            def outside(timestamp):
                dt = parse(timestamp)
                saturday_allowed = dt.weekday() == 5 and int(companies[cid]['saturday_operations'])
                return (dt.hour < 8 or dt.hour >= 19 or dt.date().isoformat() in holidays
                        or dt.weekday() >= 5 and not saturday_allowed)
            if outside(row['created_at']) or outside(row['approved_at']):
                emit('C1', dict(created_at=row['created_at'], approved_at=row['approved_at'],
                               saturday_operations=int(companies[cid]['saturday_operations'])))
            self_approved = maker == row['approver_id']
            permitted = amount <= int(user['self_approval_limit_vnd'])
            if self_approved:
                emit('C2', dict(amount_vnd=amount, self_approval_limit_vnd=int(user['self_approval_limit_vnd'])),
                     suppressed='Trong hạn mức tự duyệt đã biết' if permitted else '')
            seconds = (parse(row['approved_at']) - parse(row['created_at'])).total_seconds()
            if 0 <= seconds < 60 and amount >= cfg['high_approval_vnd']:
                emit('C3', dict(approval_seconds=seconds, amount_vnd=amount, high_approval_vnd=cfg['high_approval_vnd']))
            if row['txn_type'] == 'payroll' and feature['attendance_known'] and not feature['attendance_days'] and not feature['alternative_work_evidence']:
                entitlement = paid_leave_entitlement(entitlements.records(cid, eid), row, staff, now)
                emit('E1', dict(employee_id=eid, payroll_period=row['payroll_period'], attendance_days=0,
                               alternative_work_evidence=0, recipient_employee_bank_count=feature['recipient_employee_bank_count'],
                               paid_leave_entitlement=dict(entitlement) if entitlement else None),
                     suppressed='Nghỉ hưởng lương có quyền chi đã duyệt và bằng chứng cho đúng kỳ/số tiền' if entitlement else '')
            close_distance = calendar.monthrange(at.year, at.month)[1] - at.day
            materiality = int(cfg['materiality_vnd_by_company'].get(cid, limit))
            if row['txn_type'] == 'adjustment' and close_distance < cfg['close_days'] and amount > materiality:
                emit('F1', dict(days_before_close=close_distance, amount_vnd=amount, materiality_vnd=materiality,
                               manual_proxy='txn_type=adjustment'),
                     suppressed='Trong quyền tự duyệt và có hồ sơ đối chiếu' if self_approved and permitted and int(row['support_doc_count']) >= 2 else '')
            if row['advance_id'] and feature['advance_open_fraction'] > 0 and feature['advance_overdue_days'] > cfg['advance_grace_days']:
                emit('T1', dict(advance_id=row['advance_id'], overdue_days=feature['advance_overdue_days'],
                               open_fraction=feature['advance_open_fraction'], extension_known=feature['advance_extension_known']),
                     suppressed='Xóa nợ có hồ sơ tại thời điểm ghi sổ' if row['txn_type'] == 'advance_writeoff' and int(row['evidence_on_file']) else '')
            if row['txn_type'] == 'advance_writeoff' and not int(row['evidence_on_file']):
                emit('T2', dict(advance_id=row['advance_id'], evidence_on_file=0,
                               prior_balance_fraction=feature['advance_open_fraction']))
            # Correlated checks share a scoring family: B5/E4 cannot double-count.
            family_points = {}
            for hit in current_hits:
                group = 'master_duplicate' if hit['rule_id'] in {'B5', 'E4', 'E3'} else hit['rule_id'][0]
                family_points[group] = max(family_points.get(group, 0), hit['points'])
            base_score = sum(family_points.values())
            recurrence = min(cfg['recurrence_cap'], len(prior_risk)) if base_score >= cfg['operational_score'] else 0
            hard = any(h['hard_trigger'] for h in current_hits)
            score = base_score + recurrence
            codes = sorted(h['rule_id'] for h in current_hits if h['points'] > 0)
            priority = 'cao_nhat' if hard else 'cao' if score >= 14 else 'trung_binh' if score >= cfg['operational_score'] else 'thap'
            node = graph.node(vid, 'entity') if vid else ''
            # Roots may evolve; case grouping is diagnostic, never a feature/label input.
            case_entity = graph.groups[cid].root(node) if vid else f'employee:{eid}' if eid else f'maker:{maker}'
            result = dict(transaction_id=tid, company_id=cid, posted_at=now, rule_score=score,
                          base_score=base_score, recurrence_points=recurrence, rule_ids='|'.join(codes),
                          hard_trigger=int(hard), priority=priority, operational_alert=int(score >= cfg['operational_score']),
                          case_entity=case_entity, explanation_vi='; '.join(RULE_NAMES[c] for c in codes),
                          known_risky_prior_ids=[x[1] for x in prior_risk])
            scores.append(result)
            hits.extend(current_hits)
            batch_scores.append(result)
        # Commit after the timestamp batch: equal-time payments cannot see each other.
        for row, result in zip(batch, batch_scores):
            cid, vid, maker = row['company_id'], row['vendor_id'], row['creator_id']
            amount = int(row['amount_vnd'])
            if row['txn_type'] == 'vendor_payment':
                histories[cid].append(row)
                recipient_payments[(cid, normalize(row['recipient_account'], 'bank_account'))].append(row)
                vendor_windows[(cid, vid)].append(row)
                invoice_payments[(cid, vid, normalize(row['invoice_number']))].append(row)
                if row.get('contract_id'):
                    contract_payments[(cid, vid, row['contract_id'])].append(row)
                vendor_amounts[(cid, vid)].append((now, amount))
            if int(row['is_financial_entry']):
                for key in {(cid, row['txn_type'], vid), (cid, row['txn_type'], '')}:
                    moment = moments[key]
                    moment[0] += 1
                    delta = amount - moment[1]
                    moment[1] += delta / moment[0]
                    moment[2] += delta * (amount - moment[1])
            if int(row['is_financial_entry']) and row['payment_channel'] in {'bank', 'cash'} and row['txn_type'] != 'customer_receipt':
                creator_payments[(cid, maker)].append(row)
            if result['operational_alert']:
                previous_risk[(cid, vid or row['employee_id'] or maker)].append((now, row['transaction_id']))
    return dict(scores=scores, hits=hits, coverage=rule_coverage(), config=cfg)
