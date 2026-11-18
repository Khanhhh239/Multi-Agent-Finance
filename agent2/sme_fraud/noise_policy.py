"""Rule-only domain evidence and scoring roles; no truth/partition input."""
from collections import defaultdict, deque
from datetime import timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
import math
import re
from statistics import median
import unicodedata

from .generate import parse
from .temporal_evidence import approved_evidence, employee_at

VN = timezone(timedelta(hours=7))
_PROTECTED_VN_CO_RE = re.compile(r'\bCƠ\b')
_NON_ALNUM_RE = re.compile(r'[^A-Z0-9]')
_SYNTHETIC_PARTNER_RE = re.compile(r'CONGTYMOPHONGDOITAC\d+\Z')
_DOTTED_INITIALS_RE = re.compile(r'\b(?:[A-Z]\.){2,}[A-Z]?\b')
_ENGLISH_CO_SUFFIX_RE = re.compile(
    r'(?:(?:&|AND)\s+CO[.,]*\s*\Z|\bCO[.,]*\s+(?:LTD|LIMITED|INC|INCORPORATED|LLC|CORP|CORPORATION)\b|\bCO\.,\s*|\bCO\.\s*\Z)'
)
_LEGAL_ENTITY_RE = re.compile(
    r'\b(?:'
    r'CONG\s+TY|CTY|DOANH\s+NGHIEP\s+TU\s+NHAN|DNTN|HO\s+KINH\s+DOANH|HKD|'
    r'TRACH\s+NHIEM\s+HUU\s+HAN|TNHH|MOT\s+THANH\s+VIEN|MTV|1TV|'
    r'CO\s+PHAN|CP|CHI\s+NHANH|'
    r'JSC|LLC|LTD|LIMITED|INC|INCORPORATED|CORPORATION|CORP|COMPANY'
    r')\b'
)
_VN_BOILERPLATE_RE = re.compile(
    r'\b(?:'
    r'THUONG\s+MAI|DICH\s+VU|XAY\s+DUNG|SAN\s+XUAT|XUAT\s+NHAP\s+KHAU|'
    r'DAU\s+TU|PHAT\s+TRIEN|TONG\s+HOP|TU\s+VAN|VAN\s+TAI|KY\s+THUAT|'
    r'TM\s*DV|SX\s*TM|TM|DV|XD|SX|XNK'
    r')\b'
)
_VN_CO_FOLLOWERS_RE = re.compile(r'\bCO\s+(?:KHI|DIEN|SO|GIOI|HOC|CAU|TU|NANG)\b')


@lru_cache(maxsize=65536)
def name_key(value):
    raw = str(value or '').strip().upper().replace('Đ', 'D')
    # Protect Vietnamese "CƠ" (e.g., "CƠ KHÍ", "CƠ ĐIỆN", "CƠ SỞ") before NFD stripping.
    protected = _PROTECTED_VN_CO_RE.sub('__VN_CO__', raw)
    text = ''.join(c for c in unicodedata.normalize('NFD', protected) if unicodedata.category(c) != 'Mn')
    joined_check = _NON_ALNUM_RE.sub('', text.replace('__VN_CO__', 'CO'))
    if _SYNTHETIC_PARTNER_RE.fullmatch(joined_check) or not re.search('[A-Z]', joined_check):
        return '', 'synthetic_or_uninformative_name'
    text = _DOTTED_INITIALS_RE.sub(lambda m: m.group(0).replace('.', ''), text)
    # Protect common ASCII-only Vietnamese "CO KHI / CO DIEN / CO SO / CO GIOI" compounds too.
    text = _VN_CO_FOLLOWERS_RE.sub(lambda m: '__VN_CO__ ' + m.group(0).split(None, 1)[1], text)
    # Strip English "Co., Ltd" / "& Co" patterns without touching Vietnamese "CƠ".
    text = _ENGLISH_CO_SUFFIX_RE.sub(' ', text)
    text = re.sub(r'[.,;/\\()\[\]"\'-]+', ' ', text)
    text = _LEGAL_ENTITY_RE.sub(' ', text)
    # Also strip trailing standalone English "CO" at end of string (never "__VN_CO__").
    text = re.sub(r'\bCO\s*\Z', ' ', text)
    stripped_boilerplate = _VN_BOILERPLATE_RE.sub(' ', text)
    restored = stripped_boilerplate.replace('__VN_CO__', 'CO')
    key = _NON_ALNUM_RE.sub('', restored)
    if len(key) < 3:
        return '', 'insufficient_distinctive_name'
    return key, ''


def name_similarity(left, right):
    a, _ = name_key(left)
    b, _ = name_key(right)
    return SequenceMatcher(None, a, b).ratio() if a and b else None


def evidence_id(kind, company, evidence):
    payload = json.dumps([kind, company, evidence], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return kind + '_' + hashlib.sha256(payload.encode()).hexdigest()[:20]


def verified_document(record, staff, company, now):
    verified = record.get('verified_at', '')
    verifier = employee_at(staff, record.get('verifier_id'), verified)
    return bool(record.get('company_id') == company and record.get('status') == 'verified' and record.get('evidence_id') and verified and
                verified <= record['observed_at'] <= now and verifier and
                verifier['company_id'] == company and verifier['recorded_at'] <= verified)


def independent_requests(row, group, links, staff, now):
    """A project/name/ID string alone never exempts a disbursement."""
    def link_for(tx):
        record = links.get(tx['transaction_id'])
        if record and record.get('vendor_id') == tx['vendor_id'] and record.get('request_id') and record.get('purchase_order_id') and verified_document(record, staff, row['company_id'], now):
            return record
        return None
    current = link_for(row)
    if not current:
        return group, [], ''
    retained, excluded = [], []
    for tx in group:
        record = link_for(tx)
        if record and record['request_id'] != current['request_id'] and record['purchase_order_id'] != current['purchase_order_id']:
            excluded.append(dict(transaction_id=tx['transaction_id'], request_id=record['request_id'],
                                 purchase_order_id=record['purchase_order_id'], evidence_id=record['evidence_id']))
        else:
            retained.append(tx)
    return retained, excluded, current['request_id']


def vendor_fulfilment(documents, row, staff, now):
    valid = [r for r in documents if r.get('transaction_id') == row['transaction_id'] and
             r.get('vendor_id') == row['vendor_id'] and verified_document(r, staff, row['company_id'], now)]
    kinds = {r.get('document_type') for r in valid}
    complete = 'invoice' in kinds and bool(kinds & {'goods_receipt', 'service_acceptance'}) and bool(kinds & {'purchase_order', 'contract'})
    return complete, [dict(document_type=r['document_type'], evidence_id=r['evidence_id'], verified_at=r['verified_at']) for r in valid]


def outside_schedule(timestamp, action, company, employee, schedules, staff, holidays):
    dt = parse(timestamp)
    if dt.utcoffset() is not None:
        dt = dt.astimezone(VN)
    employee = employee_at(staff, employee['employee_id'], timestamp)
    versions = {}
    for record in sorted(schedules, key=lambda r: r['observed_at']):
        if record['observed_at'] <= timestamp:
            versions[record['schedule_id']] = record
    matching = []
    for record in versions.values():
        if not employee or employee['company_id'] != company['company_id']:
            continue
        if record.get('employee_id') and record['employee_id'] != employee['employee_id']:
            continue
        if record.get('role') and record['role'] != employee['role']:
            continue
        if record.get('action', 'all') not in {'all', action}:
            continue
        if not record.get('effective_from', '') <= timestamp <= record.get('effective_to', '9999'):
            continue
        if not approved_evidence(record, staff, company['company_id'], timestamp):
            continue
        matching.append(record)
    # An employee/action-specific schedule takes precedence over a company one.
    if matching:
        best = max((bool(r.get('employee_id')), bool(r.get('role')), r.get('action') == action) for r in matching)
        matching = [r for r in matching if (bool(r.get('employee_id')), bool(r.get('role')), r.get('action') == action) == best]
        for record in matching:
            weekdays = {int(value) for value in str(record['weekdays']).split(',')}
            start, end = record['start_time'], record['end_time']
            clock = dt.strftime('%H:%M')
            if start <= end:
                allowed = dt.weekday() in weekdays and start <= clock < end
            else:
                allowed = (dt.weekday() in weekdays and clock >= start or (dt.weekday()-1)%7 in weekdays and clock < end)
            if dt.date().isoformat() in holidays and not int(record.get('holiday_work_allowed', 0)):
                allowed = False
            if allowed:
                return False, record['schedule_id']
        return True, 'explicit_schedule'
    saturday = dt.weekday() == 5 and int(company['saturday_operations'])
    return (dt.hour < 8 or dt.hour >= 19 or dt.date().isoformat() in holidays or dt.weekday() >= 5 and not saturday), 'company_default'


class RobustAmounts:
    def __init__(self, days=180, maximum=256):
        self.days, self.maximum = days, maximum
        self.history = defaultdict(deque)

    def key(self, row):
        entity = row['vendor_id'] or row['employee_id'] or row['customer_id'] or row.get('department', '')
        category = row.get('expense_category') or row.get('accounting_purpose') or row['debit_account']
        return row['company_id'], row['txn_type'], entity, category

    def evaluate(self, row, minimum, threshold):
        queue = self.history[self.key(row)]
        now = parse(row['posted_at'])
        while queue and (now-parse(queue[0][0])).total_seconds() > self.days*86400:
            queue.popleft()
        if len(queue) < minimum:
            return False, dict(method='log_median_mad', baseline_rows=len(queue), status='insufficient_history', scope=list(self.key(row)))
        values = [x[1] for x in queue]
        center = median(values)
        mad = median(abs(v-center) for v in values)
        scale = max(.25, mad / .6744897501960817)
        z = (math.log1p(int(row['amount_vnd']))-center)/scale
        return z > threshold, dict(method='log_median_mad', baseline_rows=len(values), median_log_amount=center,
            mad_log_amount=mad, scale_floor=.25, robust_z=z, threshold=threshold, scope=list(self.key(row)), status='evaluated')

    def commit(self, row):
        queue = self.history[self.key(row)]
        queue.append((row['posted_at'], math.log1p(int(row['amount_vnd']))))
        while len(queue) > self.maximum:
            queue.popleft()


def recurring_exception(patterns, row, staff, now):
    for record in patterns:
        if (record.get('txn_type') == row['txn_type'] and record.get('vendor_id', '') == row['vendor_id'] and
                record.get('employee_id', '') == row['employee_id'] and
                record.get('effective_from', '') <= now <= record.get('effective_to', '9999') and
                approved_evidence(record, staff, row['company_id'], now) and
                abs(int(row['amount_vnd'])-int(record['expected_amount_vnd'])) <= int(record.get('tolerance_vnd', 0))):
            return record['pattern_id']
    return ''


def assign_noise_points(hits, threshold):
    """Context cannot promote an unsupported pattern into an operational case."""
    anchors = [h for h in hits if h.get('scoring_role', 'transaction') == 'transaction' and h['points'] >= threshold]
    for hit in hits:
        role = hit.get('scoring_role', 'transaction')
        if role == 'master_quality':
            hit['points'] = 0
            hit['score_reason'] = 'Kiểm tra master, không cộng điểm giao dịch'
        elif role == 'context' and not anchors:
            hit['points'] = 0
            hit['score_reason'] = 'Giữ ngữ cảnh; cần bằng chứng giao dịch độc lập đủ mức cảnh báo'
        elif role == 'context':
            independent = [h for h in anchors if not (hit['rule_id'] == 'A5' and h['rule_id'].startswith('A'))]
            if not independent:
                hit['points'] = 0
                hit['score_reason'] = 'Tín hiệu số tiền trùng nguồn với kiểm tra hạn mức'
            else:
                hit['score_reason'] = 'Ngữ cảnh hỗ trợ bằng chứng giao dịch đã có'
                hit['anchor_rule_ids'] = sorted({h['rule_id'] for h in independent})
        if not hit['points']:
            hit['hard_trigger'] = 0
