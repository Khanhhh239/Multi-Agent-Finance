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
from .noise_policy import (name_key, name_similarity, evidence_id, independent_requests,
                           vendor_fulfilment, outside_schedule, RobustAmounts,
                           recurring_exception, assign_noise_points)
from .spec_policy import bank_identity, identity_matches, PeriodPayments, manual_close_evidence
from .payment_evidence import PaymentEvidence
from .authority_policy import ApprovalAuthority
from .evidence_policy import EvidencePolicy, SOURCES as EVIDENCE_SOURCES, REQUIRED as EVIDENCE_REQUIRED, required_columns

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
               C1=1, C2=20, C3=8, C4=8, E1=20, E2=20, E3=3, E4=3, F1=8, F2=8, F3=3,
               P1=20, T1=8, T2=20)
HARD_TRIGGERS = {'B1', 'B7', 'C2', 'E1', 'E2', 'P1', 'T2'}
DEFAULT_CONFIG = dict(short_days=3, long_days=30, short_total_ratio=.85,
                      near_low=.8, near_high=.99, near_count=3,
                      baseline_min=20, round_z=2., vendor_new_days=90,
                      dormant_days=180, bank_change_days=14, close_days=5,
                      advance_grace_days=0, operational_score=7,
                      materiality_vnd_by_company={}, high_approval_vnd=50_000_000,
                      fuzzy_similarity=.85, recurrence_cap=3)
DEFAULT_CONFIG['enable_graph'] = True
DEFAULT_CONFIG.update(noise_policy='phase2', amount_baseline='log_mad', robust_z=3.5)
DEFAULT_CONFIG.update(spec_policy='phase3', near_period='calendar_month', amount_tail='upper')
DEFAULT_CONFIG.update(evidence_policy='phase4', receivable_overdue_days=60)
INPUT_TABLES = ('companies', 'employees', 'vendors', 'customers', 'calendar',
                'entity_links', 'attendance', 'vendor_status_history',
                'bank_account_changes', 'advances', 'advance_events', 'transactions')
OPTIONAL_INPUT_TABLES = ('payroll_entitlements', 'supplier_payment_agreements', 'procurement_links',
                         'transaction_documents', 'payment_requests', 'operating_schedules', 'recurring_payments',
                         'vendor_payment_schedules', 'approval_authorities', 'approval_authority_coverage',
                         'journal_audit_log', 'closing_periods', 'materiality_policies')
OPTIONAL_INPUT_TABLES += tuple(EVIDENCE_SOURCES)


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
            reader = csv.DictReader(stream)
            if name in EVIDENCE_SOURCES and set(required_columns(name))-set(reader.fieldnames or []):
                raise ValueError(f'Incomplete evidence schema: {path.name}')
            tables[name] = list(reader)
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


def long_installment_exception(row, group, invoice_history, contract_history, agreements, staff, now, window_rule='A2'):
    """Exempt only the actual A2 window; all-time totals still constrain it."""
    def documented(payments):
        return all(int(r['support_doc_count']) > 0 and
                   r.get('support_docs_observed_at', r['posted_at']) <= now for r in payments)
    number = normalize(row['invoice_number'])
    gross = int(row['invoice_gross_vnd'])
    invoice_group = [r for r in group if r['company_id'] == row['company_id'] and
        r['vendor_id'] == row['vendor_id'] and normalize(r['invoice_number']) == number]
    same_invoice = bool(number and invoice_group)
    cumulative = sum(int(r['amount_vnd']) for r in invoice_history) + int(row['amount_vnd'])
    consistent = all(int(r['invoice_gross_vnd']) == gross for r in invoice_history)
    if documented([*invoice_group, row]) and same_invoice and gross > 0 and consistent and cumulative <= gross:
        return f'Các đợt của hóa đơn hiện tại trong cửa sổ {window_rule} có hồ sơ, tổng toàn lịch sử chưa vượt hóa đơn', dict(
            basis='invoice', invoice_number=row['invoice_number'], invoice_gross_vnd=gross,
            cumulative_paid_vnd=cumulative,
            installment_window_ids=[r['transaction_id'] for r in invoice_group] + [row['transaction_id']],
            other_window_ids=[r['transaction_id'] for r in group if r not in invoice_group],
            historical_payment_ids=[r['transaction_id'] for r in invoice_history])
    contract = row.get('contract_id', '')
    contract_group = [r for r in group if r.get('contract_id') == contract and
        r['company_id'] == row['company_id'] and r['vendor_id'] == row['vendor_id']]
    same_contract = bool(contract)
    records = [r for r in agreements if r.get('contract_id') == contract]
    agreement = max(records, key=lambda r: (r['observed_at'], r['agreement_id']), default=None)
    current_invoice_cap_ok = not number or (gross > 0 and consistent and cumulative <= gross)
    if documented([*contract_group, row]) and same_contract and current_invoice_cap_ok and agreement and approved_evidence(agreement, staff, row['company_id'], now):
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
                installment_window_ids=[r['transaction_id'] for r in contract_group] + [row['transaction_id']],
                other_window_ids=[r['transaction_id'] for r in group if r not in contract_group],
                historical_payment_ids=[r['transaction_id'] for r in contract_history])
    return '', dict(basis='no_valid_installment_evidence', same_invoice=same_invoice,
                    same_contract=same_contract, invoice_cumulative_paid_vnd=cumulative)


class KnownGraph:
    """Current identity slots, with replaceable edges and as-of evidence paths.

    A (company, source, kind) slot has one current bank/phone/representative.
    Empty targets are retained as tombstones so old mirrored links cannot return.
    At the same observed timestamp a master snapshot outranks its link mirror.
    """
    def __init__(self):
        self.groups = defaultdict(UnionFind)
        self.adjacency = defaultdict(lambda: defaultdict(dict))
        self.current = defaultdict(dict)
        self.dirty = set()

    @staticmethod
    @lru_cache(maxsize=100000)
    def node(value, kind):
        return f'{kind}:{normalize(value, kind)}'

    def replace(self, cid, left, right, at, kind, *, master=False):
        if not left or left.endswith(':'):
            return
        if right and right.endswith(':'):
            right = ''
        slot = (left, kind)
        previous = self.current[cid].get(slot)
        rank = (at, int(master))
        if previous:
            previous_rank, previous_edge = previous
            if rank < previous_rank:
                return
            if rank == previous_rank:
                if right != previous_edge['target']:
                    raise ValueError(f'Conflicting graph identity at {at}: {cid}/{left}/{kind}')
                return
        edge = dict(source=left, target=right, link_type=kind, observed_at=at)
        self.current[cid][slot] = (rank, edge)
        self.dirty.add(cid)

    def group(self, cid):
        # Union-find cannot split a component. Rebuild only after source changes,
        # after the entire observation batch, from the surviving current edges.
        if cid in self.dirty:
            group, adjacency = UnionFind(), defaultdict(dict)
            for _, edge in self.current[cid].values():
                left, right = edge['source'], edge['target']
                if not right:
                    continue
                group.join(left, right)
                adjacency[left][right] = edge
                adjacency[right][left] = edge
            self.groups[cid], self.adjacency[cid] = group, adjacency
            self.dirty.remove(cid)
        return self.groups[cid]

    def revoke(self, cid, left, right, at, kind):
        previous = self.current[cid].get((left, kind))
        # A cancellation naming an old value must not cancel its replacement.
        # An empty target explicitly clears the entire current identity slot.
        if right and previous and previous[1]['target'] not in {'', right}:
            return
        self.replace(cid, left, '', at, kind)

    def path(self, cid, start, targets, max_depth=6):
        self.group(cid)
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
        'B1': 'Master riêng; cảnh báo trên chi NCC qua tiền/ngân hàng. Đọc bank_code/recipient_bank_code/national_id nếu có; số TK thực thiếu mã ngân hàng chỉ là đối chiếu chưa xác nhận.',
        'B4': 'Lịch sử trạng thái tổng hợp theo observed_at; chưa kết nối cổng thuế/ngành nghề.',
        'B7': 'Có lịch đổi TK/callback/người duyệt; chưa có nguồn email BEC.',
        'E3': 'SequenceMatcher trên tên chuẩn hóa là proxy, không phải Levenshtein/Jaro-Winkler.',
        'F1': 'Cần journal_audit_log, closing_periods và materiality_policies đã biết/được duyệt. Proxy adjustment/cuối tháng/hạn mức chỉ là chẩn đoán 0 điểm.',
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
    if cfg['noise_policy'] not in {'legacy', 'phase2'} or cfg['amount_baseline'] not in {'raw', 'log_mad'} or cfg['robust_z'] <= 0:
        raise ValueError('Invalid noise policy/baseline')
    phase2 = cfg['noise_policy'] == 'phase2'
    if cfg['spec_policy'] not in {'legacy', 'phase3'} or cfg['near_period'] not in {'calendar_month', 'rolling_30d'} or cfg['amount_tail'] != 'upper':
        raise ValueError('Invalid business definition policy; only upper-tail A5 is supported')
    phase3 = cfg['spec_policy'] == 'phase3'
    if cfg['evidence_policy'] not in {'disabled', 'phase4'} or cfg['receivable_overdue_days'] < 0:
        raise ValueError('Invalid evidence policy')
    evidence_policy = EvidencePolicy(tables, cfg) if cfg['evidence_policy'] == 'phase4' else None
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
    procurement = Stream(tables.get('procurement_links', []))
    known_procurement = {}
    documents = ObservedVersions(tables.get('transaction_documents', []), 'record_id')
    schedules_by_company = defaultdict(list)
    for record in tables.get('operating_schedules', []):
        schedules_by_company[record['company_id']].append(record)
    recurring = ObservedVersions(tables.get('recurring_payments', []), 'pattern_id')
    journal_audits = ObservedVersions(tables.get('journal_audit_log', []), 'audit_id')
    closing_periods = ObservedVersions(tables.get('closing_periods', []), 'closing_id')
    materiality_policies = ObservedVersions(tables.get('materiality_policies', []), 'policy_id')
    period_payments = PeriodPayments()
    payment_evidence = PaymentEvidence(tables)
    approval_authority = ApprovalAuthority(tables)
    robust_amounts = RobustAmounts()
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
    vendor_economics = defaultdict(list)
    moments = defaultdict(lambda: [0, 0., 0.])
    previous_risk = defaultdict(deque)
    companies = {r['company_id']: r for r in tables['companies']}
    holidays = {r['date'] for r in tables['calendar'] if int(r.get('is_holiday', 1))}
    scores, hits, master_name_quality, master_identity_findings = [], [], [], []
    identity_seen = set()
    for now, batch_iter in groupby(rows, key=lambda r: r['posted_at']):
        batch = list(batch_iter)
        batch_payment_keys = Counter(PeriodPayments.key(r) for r in batch if int(r['is_financial_entry']) and r['payment_channel'] in {'bank', 'cash'})
        at = parse(now)
        changed_vendor_ids, staff_changed_companies = set(), set()
        for name, stream in masters.items():
            for item in stream.until(now):
                cid = item['company_id']
                if name == 'employees':
                    staff_changed_companies.add(cid)
                else:
                    changed_vendor_ids.add(item['vendor_id'])
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
                        similarity = name_similarity(item['name'], other['name']) if phase2 else SequenceMatcher(None, normalize(item['name']), normalize(other['name'])).ratio()
                        if similarity is not None and similarity > cfg['fuzzy_similarity']:
                            fuzzy_matches[key][other_id] = round(similarity, 4)
                            fuzzy_matches[other_id][key] = round(similarity, 4)
                    if phase2:
                        _, issue = name_key(item['name'])
                        if issue:
                            master_name_quality.append(dict(company_id=cid, vendor_id=key, recorded_at=item['recorded_at'],
                                                            name=item['name'], issue=issue))
                # Each master row is a snapshot, including cleared identity fields.
                # Mirrored links at/before this version must not resurrect old data.
                for field in ('bank_account', 'phone', 'representative_id'):
                    if field == 'representative_id' and field not in item:
                        continue
                    kind = 'representative' if field == 'representative_id' else field
                    token = bank_identity(item.get(field, ''), item.get('bank_code', '')) if phase3 and field == 'bank_account' else item.get(field, '')
                    right_kind = 'entity' if kind == 'representative' else kind
                    target = graph.node(token, right_kind) if normalize(token, right_kind) else ''
                    graph.replace(cid, graph.node(key, 'entity'), target,
                                  item['recorded_at'], kind, master=True)
        if phase3:
            for vendor_id, vendor in vendors.items():
                if vendor_id not in changed_vendor_ids and vendor['company_id'] not in staff_changed_companies:
                    continue
                matches, ambiguous = identity_matches(vendor, staff)
                if matches or ambiguous:
                    proof = dict(vendor_id=vendor_id, matches=matches, ambiguous_employee_ids=ambiguous,
                                 vendor_bank_account=vendor.get('bank_account', ''), vendor_bank_code=vendor.get('bank_code', ''),
                                 vendor_national_id=vendor.get('national_id', ''),
                                 vendor_recorded_at=vendor['recorded_at'],
                                 employee_recorded_at={e: staff[e]['recorded_at'] for e in sorted(set(ambiguous) | {e for ids in matches.values() for e in ids})})
                    key = evidence_id('B1_master', vendor['company_id'], proof)
                    if key not in identity_seen:
                        identity_seen.add(key)
                        master_identity_findings.append(dict(rule_id='B1', evidence_id=key, company_id=vendor['company_id'],
                            observed_at=now, scoring_role='master_quality', points=0, evidence=proof))
        for edge in links.until(now):
            if edge['link_type'] not in {'bank_account', 'phone', 'representative'}:
                continue
            status = edge.get('status', 'active') or 'active'
            if status not in {'active', 'revoked', 'deleted', 'inactive'}:
                raise ValueError(f'Invalid graph link status: {status}')
            right_kind = 'entity' if edge['link_type'] == 'representative' else edge['link_type']
            target = bank_identity(edge['target_id'], edge.get('bank_code', '')) if phase3 and right_kind == 'bank_account' else edge['target_id']
            right = graph.node(target, right_kind) if normalize(target, right_kind) else ''
            source = graph.node(edge['source_id'], 'entity')
            if status == 'active':
                graph.replace(edge['company_id'], source, right, edge['observed_at'], edge['link_type'])
            elif not edge['target_id'] or right:
                graph.revoke(edge['company_id'], source, right, edge['observed_at'], edge['link_type'])
        bank_changes.advance(now)
        entitlements.advance(now)
        agreements.advance(now)
        documents.advance(now)
        recurring.advance(now)
        journal_audits.advance(now)
        closing_periods.advance(now)
        materiality_policies.advance(now)
        payment_evidence.advance(now, batch)
        for record in procurement.until(now):
            known_procurement[record['transaction_id']] = record
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
                a1_scope, a1_excluded, a1_proof = payment_evidence.scope(row, short, now) if phase2 else (short, [], None)
                a2_scope, a2_excluded, a2_proof = payment_evidence.scope(row, same_maker, now) if phase2 else (same_maker, [], None)
                request_id = (a1_proof or {}).get('request_id', '')
                strict_purchase = phase2 and payment_evidence.strong_purchase_for(row)
                if phase2 and not strict_purchase:
                    a1_scope, a1_excluded, request_id = independent_requests(row, short, known_procurement, staff, now)
                    a2_scope, a2_excluded, _ = independent_requests(row, same_maker, known_procurement, staff, now)
                if phase2:
                    if strict_purchase:
                        exception = 'Hồ sơ nghĩa vụ chi đã duyệt, gắn đúng giao dịch và tổng tiền chưa vượt trần' if a1_proof else ''
                        installment_evidence = a1_proof or dict(basis='no_valid_bound_payment_evidence')
                    else:
                        exception, installment_evidence = long_installment_exception(row, short, previous_invoice,
                            contract_payments[(cid, vid, row.get('contract_id', ''))], agreements.records(cid, vid), staff, now, 'A1')
                else:
                    installment_evidence = {}
                raw_a1 = candidate and short and sum(int(r['amount_vnd']) for r in short) + amount >= cfg['short_total_ratio'] * limit
                scoped_a1 = candidate and a1_scope and sum(int(r['amount_vnd']) for r in a1_scope) + amount >= cfg['short_total_ratio'] * limit
                if raw_a1:
                    independent_a1 = bool(a1_excluded) and not scoped_a1
                    emit('A1', dict(count=len(short) + 1, total_vnd=sum(int(r['amount_vnd']) for r in short) + amount,
                                   approval_limit_vnd=limit, window_days=cfg['short_days'],
                                   evaluated_transaction_ids=[r['transaction_id'] for r in a1_scope] + [tid],
                                   installment_check=installment_evidence, excluded_independent_obligations=a1_excluded,
                                   excluded_independent_requests=a1_excluded, request_id=request_id),
                         [r['transaction_id'] for r in short], suppressed=exception or ('Đơn mua/yêu cầu chi độc lập đã có chứng từ xác minh' if independent_a1 else ''))
                raw_a2 = candidate and len(same_maker) >= 2 and sum(int(r['amount_vnd']) for r in same_maker) + amount >= limit
                scoped_a2 = candidate and len(a2_scope) >= 2 and sum(int(r['amount_vnd']) for r in a2_scope) + amount >= limit
                if raw_a2:
                    if strict_purchase:
                        long_exception = 'Hồ sơ nghĩa vụ chi đã duyệt, gắn đúng giao dịch và tổng tiền chưa vượt trần' if a2_proof else ''
                        installment_evidence = a2_proof or dict(basis='no_valid_bound_payment_evidence')
                    else:
                        long_exception, installment_evidence = long_installment_exception(
                            row, same_maker, previous_invoice,
                            contract_payments[(cid, vid, row.get('contract_id', ''))],
                            agreements.records(cid, vid), staff, now)
                    independent_a2 = bool(a2_excluded) and not scoped_a2
                    emit('A2', dict(count=len(same_maker) + 1, total_vnd=sum(int(r['amount_vnd']) for r in same_maker) + amount,
                                   approval_limit_vnd=limit, window_days=cfg['long_days'],
                                   evaluated_transaction_ids=[r['transaction_id'] for r in a2_scope] + [tid],
                                   installment_check=installment_evidence, excluded_independent_obligations=a2_excluded,
                                   excluded_independent_requests=a2_excluded, request_id=(a2_proof or {}).get('request_id', request_id)),
                         [r['transaction_id'] for r in same_maker], suppressed=long_exception or ('Đơn mua/yêu cầu chi độc lập đã có chứng từ xác minh' if independent_a2 else ''))
                g, node = graph.group(cid), graph.node(vid, 'entity')
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
                short_network = [r for r in network if (at - parse(r['posted_at'])).total_seconds() <= cfg['short_days'] * 86400]
                short_others = {r['vendor_id'] for r in short_network} - {vid}
                short_total = sum(int(r['amount_vnd']) for r in short_network) + amount
                short_branch = phase3 and short_others and short_total >= cfg['short_total_ratio'] * limit
                long_branch = other_vendors and len(network) >= 2 and total_network >= limit
                if cfg['enable_graph'] and candidate and (short_branch or long_branch):
                    chosen = short_network if short_branch else network
                    chosen_others = short_others if short_branch else other_vendors
                    emit('A3', dict(vendor_ids=sorted(chosen_others | {vid}), total_vnd=short_total if short_branch else total_network,
                                   approval_limit_vnd=limit, window_days=cfg['short_days'] if short_branch else cfg['long_days'],
                                   branch='short_2_85pct' if short_branch else 'long_3_100pct', linkage='bank_phone_representative'),
                         [r['transaction_id'] for r in chosen],
                         graph.path(cid, node, {graph.node(x, 'entity') for x in chosen_others}))
                if previous_invoice and gross > 0 and total_invoice > gross + 1:
                    emit('P1', dict(invoice_number=row['invoice_number'], invoice_gross_vnd=gross,
                                    cumulative_paid_vnd=total_invoice, excess_vnd=total_invoice - gross),
                         [r['transaction_id'] for r in previous_invoice])
                if gross > 0 and gross % 1000 and amount % 1000 == 0 and amount > gross + 1:
                    emit('A6', dict(payment_vnd=amount, invoice_gross_vnd=gross, difference_vnd=amount - gross))
            creator_rows = creator_payments[(cid, maker)]
            calendar_month = phase3 and cfg['near_period'] == 'calendar_month'
            while creator_rows and (creator_rows[0]['posted_at'][:7] != now[:7] if calendar_month else (at - parse(creator_rows[0]['posted_at'])).total_seconds() > 30 * 86400):
                creator_rows.popleft()
            is_disbursement = financial and row['payment_channel'] in {'bank', 'cash'} and row['txn_type'] != 'customer_receipt'
            bound_payment_proof = payment_evidence.exemption(row, now) if phase3 and is_disbursement else None
            a4_exception = bound_payment_proof or (period_payments.exception(row, entitlements.records(cid, eid),
                recurring.records(cid, vid or eid or None), staff, now) if phase3 and is_disbursement and not row['vendor_id'] else '')
            if phase3 and not bound_payment_proof and batch_payment_keys[PeriodPayments.key(row)] > 1:
                a4_exception = ''  # Cannot assign a single monthly budget to simultaneous payments independently.
            near = is_disbursement and not a4_exception and cfg['near_low'] <= amount / limit <= cfg['near_high']
            near_rows = [r for r in creator_rows if not r.get('_a4_exception') and cfg['near_low'] <= int(r['amount_vnd']) / int(r['approval_limit_vnd']) <= cfg['near_high']]
            if near and len(near_rows) + 1 >= cfg['near_count']:
                emit('A4', dict(count=len(near_rows) + 1, period=now[:7] if calendar_month else 'rolling_30d',
                               window_days=None if calendar_month else 30, low=cfg['near_low'], high=cfg['near_high'],
                               excluded_payment_ids=[r['transaction_id'] for r in creator_rows if r.get('_a4_exception')],
                               current_payment_exception=a4_exception or None),
                     [r['transaction_id'] for r in near_rows])
            baseline_key = (cid, row['txn_type'], vid)
            fallback_key = (cid, row['txn_type'], '')
            num, mean, m2 = moments[baseline_key]
            if num < cfg['baseline_min']:
                num, mean, m2 = moments[fallback_key]
                baseline_key = fallback_key
            sd = math.sqrt(m2 / max(1, num - 1))
            if phase2 and cfg['amount_baseline'] == 'log_mad':
                amount_signal, amount_evidence = robust_amounts.evaluate(row, cfg['baseline_min'], cfg['robust_z'])
            else:
                amount_signal = bool(num >= cfg['baseline_min'] and sd > 0 and (amount - mean) / sd > cfg['round_z'])
                amount_evidence = dict(method='raw_mean_sd', baseline_rows=num, baseline_mean_vnd=round(mean),
                    baseline_sd_vnd=round(sd), z=round((amount-mean)/sd, 4) if sd else None, scope=list(baseline_key))
            if financial and amount % 1000 == 0 and amount_signal:
                recurring_id = recurring_exception(recurring.records(cid, vid or eid or None), row, staff, now) if phase2 else ''
                emit('A5', dict(**amount_evidence, recurring_pattern_id=recurring_id, tail='upper'),
                     suppressed='Khoản định kỳ đúng thỏa thuận đã duyệt/as-of' if recurring_id else '')
            disclosed = bool(v and v.get('related_party_disclosed_at') and v['related_party_disclosed_at'] <= now)
            if v:
                vendor_outflow = financial and row['payment_channel'] in {'bank', 'cash'} and str(row['credit_account']).startswith(('111', '112')) and bool(vid)
                b1_matches, b1_ambiguous = identity_matches(v, staff, row['recipient_account'], row.get('recipient_bank_code', '')) if phase3 and vendor_outflow else ({}, [])
                direct_bank = set(b1_matches.get('bank_identity', [])) if phase3 else employee_index[(cid, 'bank_account', recipient)] if recipient and payment else set()
                national = set(b1_matches.get('national_id', [])) if phase3 else employee_index[(cid, 'national_id', normalize(v.get('national_id')))] if v.get('national_id') else set()
                if direct_bank or national:
                    emit('B1', dict(employee_ids=sorted(direct_bank | national), recipient_account=row['recipient_account'],
                                    related_party_disclosed=disclosed, scope='vendor_cash_outflow' if phase3 else 'legacy',
                                    matches=b1_matches, ambiguous_employee_ids=b1_ambiguous,
                                    recipient_bank_code=row.get('recipient_bank_code', '')), weight=4 if disclosed else None)
                    if disclosed:
                        current_hits[-1]['hard_trigger'] = 0
                elif phase3 and b1_ambiguous:
                    emit('B1', dict(employee_ids=b1_ambiguous, recipient_account=row['recipient_account'],
                        evidence_status='bank_institution_missing', recipient_bank_code=row.get('recipient_bank_code', '')), weight=0)
                    current_hits[-1].update(hard_trigger=0, scoring_role='context')
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
                first_history = vendor_economics[(cid, vid)] if phase3 else history_amounts
                age = (at - parse(v['registered_at'])).days
                type_moments = moments[fallback_key]
                large = amount >= limit or (type_moments[0] >= cfg['baseline_min'] and amount > type_moments[1] + 2 * math.sqrt(type_moments[2] / max(1, type_moments[0] - 1)))
                if (financial or not phase3) and not first_history and 0 <= age < cfg['vendor_new_days'] and large:
                    fulfilled, fulfilment = vendor_fulfilment(documents.records(cid, vid), row, staff, now) if phase2 else (False, [])
                    emit('B3', dict(vendor_age_days=age, amount_vnd=amount, large_reference_limit_vnd=limit,
                                   first_basis='observed_economic_entry' if phase3 else 'cash_payment_history',
                                   history_scope='available_observation_window_not_lifetime'),
                         suppressed=('Hóa đơn, đơn mua/hợp đồng và giao nhận/nghiệm thu đã xác minh' if fulfilled else '') if phase2 else
                         ('Có xác nhận giao nhận và hồ sơ' if int(row['goods_receipt_verified']) and int(row['support_doc_count']) >= 2 else ''))
                    if phase2:
                        current_hits[-1]['evidence'].update(verified_documents=fulfilment,
                            legacy_document_count=int(row['support_doc_count']), goods_receipt_flag=int(row['goods_receipt_verified']),
                            evidence_status='verified_fulfilment' if fulfilled else 'needs_typed_fulfilment_evidence')
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
                    if phase2:
                        current_hits[-1].update(aliases=['E4'], evidence_id=evidence_id('vendor_overlap', cid,
                            dict(vendor_ids=evidence['vendor_ids'], tokens={field: normalize(v.get(field), field) for field in duplicates})))
                        current_hits[-1]['evidence'].update(overlap_kind='shared_address_only' if weak else 'shared_bank_or_phone',
                            declared_vendor_ids=sorted(x for x in evidence['vendor_ids'] if vendors[x].get('related_party_disclosed_at') and vendors[x]['related_party_disclosed_at'] <= now))
                    else:
                        emit('E4', evidence, weight=1 if weak else 3)
                if payment and len(history_amounts) >= cfg['baseline_min']:
                    idle = (at - parse(history_amounts[-1][0])).days
                    values = sorted(item[1] for item in history_amounts)
                    p90 = values[math.ceil(.9 * len(values)) - 1]
                    if idle >= cfg['dormant_days'] and amount > p90:
                        schedule = payment_evidence.dormancy_exception(row, now) if phase3 else None
                        emit('B6', dict(idle_days=idle, prior_p90_vnd=p90, amount_vnd=amount,
                                        payment_schedule=schedule),
                             suppressed='Khoản thanh toán theo mùa/năm có lịch duyệt và tổng kỳ trong trần' if schedule else '')
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
            if phase2:
                schedule_rows = schedules_by_company[cid]
                made_outside, maker_schedule = outside_schedule(row['created_at'], 'maker', companies[cid], user, schedule_rows, staff, holidays)
                approver = staff.get(row['approver_id'], user)
                checker_rows = schedules_by_company[cid]
                approved_outside, checker_schedule = outside_schedule(row['approved_at'], 'checker', companies[cid], approver, checker_rows, staff, holidays)
            else:
                made_outside, approved_outside = outside(row['created_at']), outside(row['approved_at'])
                maker_schedule = checker_schedule = 'company_default'
            if made_outside or approved_outside:
                emit('C1', dict(created_at=row['created_at'], approved_at=row['approved_at'],
                               saturday_operations=int(companies[cid]['saturday_operations']),
                               created_outside=int(made_outside), approved_outside=int(approved_outside),
                               maker_schedule_id=maker_schedule, checker_schedule_id=checker_schedule))
            self_approved = maker == row['approver_id']
            permitted = amount <= int(user['self_approval_limit_vnd'])
            if self_approved:
                authority = approval_authority.self_approval(row, staff) if phase3 else dict(mode='legacy_fallback')
                explicit_permitted = authority.get('permitted') if authority['mode'] == 'authority_matrix' else None
                permitted = explicit_permitted if explicit_permitted is not None else permitted
                emit('C2', dict(amount_vnd=amount, self_approval_limit_vnd=int(user['self_approval_limit_vnd']),
                                authority_check=authority),
                     suppressed=('Trong quyền tự duyệt/ủy quyền đã được phê duyệt' if explicit_permitted else
                                 'Trong hạn mức tự duyệt đã biết' if permitted else ''))
            seconds = (parse(row['approved_at']) - parse(row['created_at'])).total_seconds()
            if 0 <= seconds < 60:
                checker = approval_authority.checker_level(row, staff) if phase3 else dict(mode='legacy_fallback')
                explicit_high = (checker.get('status') == 'authorized' and
                                 checker.get('authority_level') in {'high', 'executive'})
                if explicit_high or (checker['mode'] == 'legacy_fallback' and amount >= cfg['high_approval_vnd']):
                    emit('C3', dict(approval_seconds=seconds, amount_vnd=amount,
                                    high_approval_vnd=cfg['high_approval_vnd'], authority_check=checker,
                                    authority_basis='explicit_matrix' if explicit_high else 'amount_proxy'))
            if row['txn_type'] == 'payroll' and feature['attendance_known'] and not feature['attendance_days'] and not feature['alternative_work_evidence']:
                entitlement = paid_leave_entitlement(entitlements.records(cid, eid), row, staff, now)
                emit('E1', dict(employee_id=eid, payroll_period=row['payroll_period'], attendance_days=0,
                               alternative_work_evidence=0, recipient_employee_bank_count=feature['recipient_employee_bank_count'],
                               paid_leave_entitlement=dict(entitlement) if entitlement else None),
                     suppressed='Nghỉ hưởng lương có quyền chi đã duyệt và bằng chứng cho đúng kỳ/số tiền' if entitlement else '')
            close_distance = calendar.monthrange(at.year, at.month)[1] - at.day
            materiality = int(cfg['materiality_vnd_by_company'].get(cid, limit))
            confirmed_close = manual_close_evidence(row, journal_audits.records(cid, maker), closing_periods.records(cid, None),
                materiality_policies.records(cid, None), staff, now, cfg['close_days']) if phase3 and financial else None
            if confirmed_close:
                emit('F1', confirmed_close)
            elif row['txn_type'] == 'adjustment' and close_distance < cfg['close_days'] and amount > materiality:
                emit('F1', dict(days_before_close=close_distance, amount_vnd=amount, materiality_vnd=materiality,
                               manual_proxy='txn_type=adjustment', evidence_status='unconfirmed_proxy',
                               required_sources=['journal_audit_log', 'closing_periods', 'materiality_policies'],
                               materiality_basis='config_proxy' if cid in cfg['materiality_vnd_by_company'] else 'creator_approval_limit_proxy'), weight=0 if phase3 else None,
                     suppressed='Trong quyền tự duyệt và có hồ sơ đối chiếu' if self_approved and permitted and int(row['support_doc_count']) >= 2 else '')
                if phase3:
                    current_hits[-1]['scoring_role'] = 'context'
            if row['advance_id'] and feature['advance_open_fraction'] > 0 and feature['advance_overdue_days'] > cfg['advance_grace_days']:
                emit('T1', dict(advance_id=row['advance_id'], overdue_days=feature['advance_overdue_days'],
                               open_fraction=feature['advance_open_fraction'], extension_known=feature['advance_extension_known']),
                     suppressed='Xóa nợ có hồ sơ tại thời điểm ghi sổ' if row['txn_type'] == 'advance_writeoff' and int(row['evidence_on_file']) else '')
            if row['txn_type'] == 'advance_writeoff' and not int(row['evidence_on_file']):
                emit('T2', dict(advance_id=row['advance_id'], evidence_on_file=0,
                               prior_balance_fraction=feature['advance_open_fraction']))
            if evidence_policy:
                for check in evidence_policy.checks(row, staff, now):
                    emit(check['rule_id'], check['evidence'], weight=None if check['confirmed'] else 0, suppressed=check['suppressed'])
                    current_hits[-1]['scoring_role'] = check['role']
                    if check['rule_id'] == 'E2':
                        current_hits[-1]['hard_trigger'] = int(check['confirmed'] and not check['suppressed'])
                evidence_policy.snapshot(cid, staff, now)
            # Correlated checks share a scoring family: B5/E4 cannot double-count.
            if phase2:
                for hit in current_hits:
                    hit.update(intrinsic_points=hit['points'], scoring_role='master_quality' if hit['rule_id'] in {'B5', 'E4', 'E3'} else
                               'context' if hit['rule_id'] in {'C1', 'A5', 'B3'} else hit.get('scoring_role', 'transaction'))
                    hit.setdefault('evidence_id', evidence_id(hit['rule_id'], cid, dict(transaction_id=tid, evidence=hit['evidence'])))
                assign_noise_points(current_hits, cfg['operational_score'])
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
            case_entity = graph.group(cid).root(node) if vid else f'employee:{eid}' if eid else f'maker:{maker}'
            result = dict(transaction_id=tid, company_id=cid, posted_at=now, rule_score=score,
                          base_score=base_score, recurrence_points=recurrence, rule_ids='|'.join(codes),
                          hard_trigger=int(hard), priority=priority, operational_alert=int(score >= cfg['operational_score']),
                          case_entity=case_entity, explanation_vi='; '.join(RULE_NAMES[c] for c in codes),
                          known_risky_prior_ids=[x[1] for x in prior_risk])
            scores.append(result)
            hits.extend(current_hits)
            batch_scores.append(result)
            result['_a4_exception'] = a4_exception
        # Commit after the timestamp batch: equal-time payments cannot see each other.
        for row, result in zip(batch, batch_scores):
            cid, vid, maker = row['company_id'], row['vendor_id'], row['creator_id']
            amount = int(row['amount_vnd'])
            if int(row['is_financial_entry']) and vid:
                vendor_economics[(cid, vid)].append(row['transaction_id'])
            period_payments.commit(row)
            payment_evidence.commit(row)
            if row['txn_type'] == 'vendor_payment':
                histories[cid].append(row)
                recipient_payments[(cid, normalize(row['recipient_account'], 'bank_account'))].append(row)
                vendor_windows[(cid, vid)].append(row)
                invoice_payments[(cid, vid, normalize(row['invoice_number']))].append(row)
                if row.get('contract_id'):
                    contract_payments[(cid, vid, row['contract_id'])].append(row)
                vendor_amounts[(cid, vid)].append((now, amount))
            if int(row['is_financial_entry']):
                robust_amounts.commit(row)
                for key in {(cid, row['txn_type'], vid), (cid, row['txn_type'], '')}:
                    moment = moments[key]
                    moment[0] += 1
                    delta = amount - moment[1]
                    moment[1] += delta / moment[0]
                    moment[2] += delta * (amount - moment[1])
            if int(row['is_financial_entry']) and row['payment_channel'] in {'bank', 'cash'} and row['txn_type'] != 'customer_receipt':
                creator_payments[(cid, maker)].append({**row, '_a4_exception': result['_a4_exception']})
            del result['_a4_exception']
            if result['operational_alert']:
                previous_risk[(cid, vid or row['employee_id'] or maker)].append((now, row['transaction_id']))
    coverage = rule_coverage()
    for record in coverage:
        record['spec_policy'] = cfg['spec_policy']
        if record['rule_id'] in EVIDENCE_REQUIRED:
            required = EVIDENCE_REQUIRED[record['rule_id']]
            cutoff = rows[-1]['posted_at'] if rows else ''
            counts = {name: sum(r['observed_at'] <= cutoff for r in tables.get(name, [])) for name in required}
            record.update(required_sources=counts, evidence_policy=cfg['evidence_policy'])
            if evidence_policy and any(counts.values()):
                record.update(status='partial', note='Đã hỗ trợ nguồn phiên bản/as-of; cần đủ bằng chứng từng đối tượng, không suy diễn từ dữ liệu thiếu.')
            if record['rule_id'] == 'F4':
                record['scope'] = 'source_diagnostic'
        if record['rule_id'] == 'F1' and phase3:
            record['scoring_role'] = 'transaction_when_confirmed_else_zero_point_context'
    if phase2:
        for record in coverage:
            record.setdefault('scoring_role', 'master_quality' if record['rule_id'] in {'B5', 'E4', 'E3'} else 'context' if record['rule_id'] in {'C1', 'A5', 'B3'} else 'transaction')
            if record['scoring_role'] == 'master_quality':
                record['note'] += ' Kiểm tra master riêng, không cộng điểm giao dịch; B5/E4 chung evidence.'
    return dict(scores=scores, hits=hits, coverage=coverage, config=cfg, master_name_quality=master_name_quality,
                master_identity_findings=master_identity_findings, evidence_findings=evidence_policy.findings if evidence_policy else [])
