"""Shared Decimal accounting projections. These are data scenarios, not a tax return."""
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json

ZERO = Decimal(0)
EXPOSURE_NOTE = ('Kịch bản giả định các khoản có nguy cơ đã được kê khai khấu trừ và gây thiếu thuế. '
                 'Chưa xác nhận tình trạng kê khai/nộp; số ngày tính theo hạn lịch, không phải kết luận xử phạt hay miễn phạt.')
NOTE = ('Số liệu tham khảo từ hóa đơn đã nạp, chưa gồm số chuyển kỳ trước và điều chỉnh trên tờ khai. '
        'Phần chờ xem xét được tách hai kịch bản; chưa phát hiện cảnh báo không có nghĩa đã được chứng nhận khấu trừ.')


def data(rep):
    return asdict(rep) if is_dataclass(rep) else rep


def period_key(day, kind):
    d = str(day)
    return f'{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}' if kind == 'QUARTER' else d[:7]


def period_label(key):
    return f'Quý {key[-1]}/{key[:4]}' if '-Q' in key else f'Tháng {key[5:7]}/{key[:4]}'


def identify(items):
    for it in items:
        if not it.txn_ids and it.code.startswith('R14'):
            it.txn_ids = tuple(it.evidence)
        raw = [it.code, sorted(it.invoice_keys), sorted(it.txn_ids), sorted(it.basis), sorted(it.evidence), it.detail]
        it.finding_id = hashlib.sha256(json.dumps(raw).encode()).hexdigest()[:32]


def buckets(rep):
    rep = data(rep)
    findings = {}
    for it in rep['items']:
        if it['status'] in ('AT_RISK', 'REVIEW'):
            for key in it['invoice_keys']:
                findings.setdefault(key, set()).add(it['status'])
    excluded = set(rep['meta'].get('not_claimed_keys', []))
    out = {}
    for inv in rep['invoices']:
        if inv.get('duplicate_of') or inv['role'] != 'PURCHASE':
            continue
        key = inv['key']
        statuses = findings.get(key, set())
        out[key] = 'NOT_CLAIMED' if key in excluded else 'AT_RISK' if 'AT_RISK' in statuses else 'REVIEW' if 'REVIEW' in statuses else 'NO_ALERT'
    return out


def vat_summary(rep, profile, declared=None):
    rep = data(rep)
    kind = profile.get('filing_period', 'MONTH')
    method = profile.get('vat_method', 'DEDUCTION')
    groups = buckets(rep)
    rows = {}
    for inv in rep['invoices']:
        if inv.get('duplicate_of') or not inv.get('issue_date'):
            continue
        key = period_key(inv['issue_date'], kind)
        row = rows.setdefault(key, dict(period_key=key, period=period_label(key), output_vat=ZERO, input_vat=ZERO,
                                        sales=0, purchases=0, at_risk=ZERO, review=0, review_vat=ZERO,
                                        not_claimed_vat=ZERO, no_alert_vat=ZERO, missing_vat=0, missing_fields=[]))
        row['sales' if inv['role'] == 'SALE' else 'purchases'] += 1
        if inv.get('vat') is None:
            row['missing_vat'] += 1
            row['missing_fields'].append('output_vat' if inv['role'] == 'SALE' else 'input_vat')
            if inv['role'] == 'PURCHASE':
                row['missing_fields'].append({'NOT_CLAIMED': 'not_claimed_vat', 'AT_RISK': 'at_risk', 'REVIEW': 'review_vat', 'NO_ALERT': 'no_alert_vat'}[groups[inv['key']]])
            continue
        vat = Decimal(str(inv['vat']))
        if inv['role'] == 'SALE':
            row['output_vat'] += vat
        else:
            row['input_vat'] += vat
            group = groups[inv['key']]
            field = {'NOT_CLAIMED': 'not_claimed_vat', 'AT_RISK': 'at_risk', 'REVIEW': 'review_vat', 'NO_ALERT': 'no_alert_vat'}[group]
            row[field] += vat
            row['review'] += int(group == 'REVIEW')
    previous = None
    for key, row in sorted(rows.items()):
        supported = method == 'DEDUCTION' and not row['missing_vat']
        a = row['output_vat'] - row['no_alert_vat']
        b = a - row['review_vat']
        row.update(net_min=min(a, b) if supported else None, net_max=max(a, b) if supported else None,
                   scenario_without_review=a if supported else None, scenario_with_review=b if supported else None,
                   input_safe=row['no_alert_vat'] if supported else None,
                   net=a if supported and a == b else None,
                   calculation_status='UNSUPPORTED_DIRECT' if method != 'DEDUCTION' else 'INCOMPLETE' if row['missing_vat'] else 'SCENARIOS')
        row['risk_change'] = row['at_risk'] - previous if previous is not None and 'at_risk' not in row['missing_fields'] else None
        previous = row['at_risk'] if 'at_risk' not in row['missing_fields'] else None
        dec = (declared or {}).get(key) or (declared or {}).get(row['period'])
        row['declared'] = dec
        row['diff_output'] = Decimal(str(dec['output_vat'])) - row['output_vat'] if dec and 'output_vat' in dec and 'output_vat' not in row['missing_fields'] else None
        row['diff_input'] = Decimal(str(dec['input_vat'])) - row['no_alert_vat'] if dec and 'input_vat' in dec and supported else None
        for missing in row.pop('missing_fields'):
            row[missing] = None
    return dict(schema_version=2, vat_method=method, period_kind=kind, rows=[rows[k] for k in sorted(rows)],
                calculation_status='SCENARIOS' if method == 'DEDUCTION' else 'UNSUPPORTED_DIRECT',
                note=NOTE if method == 'DEDUCTION' else 'Chưa hỗ trợ tính thuế theo phương pháp trực tiếp. ' + NOTE)


def totals(rep, ruleset, as_of):
    from .rules import param
    rep = data(rep)
    groups = buckets(rep)
    by_key = {i['key']: i for i in rep['invoices'] if not i.get('duplicate_of')}
    series = {}
    amounts = {'AT_RISK': ZERO, 'REVIEW': ZERO}
    missing = {'AT_RISK': 0, 'REVIEW': 0}
    for key, group in groups.items():
        if group not in amounts:
            continue
        inv = by_key[key]
        amount = Decimal(str(inv['vat'])) if inv.get('vat') is not None else ZERO
        missing[group] += int(inv.get('vat') is None)
        amounts[group] += amount
        # Keep undated amounts visible instead of silently losing them from the chart.
        month = str(inv['issue_date'])[:7] if inv.get('issue_date') else 'undated'
        entry = series.setdefault(month, dict(k=month, AT_RISK=ZERO, REVIEW=ZERO, total=ZERO))
        entry[group] += amount
        entry['total'] += abs(amount)
    rate, basis = param(ruleset, 'UNDERDECLARATION_PENALTY_RATE', as_of)
    items = rep['items']
    for entry in series.values():
        entry['total'] = abs(entry['AT_RISK']) + abs(entry['REVIEW'])
    return dict(at_risk_vat=amounts['AT_RISK'] if not missing['AT_RISK'] else None, review_vat=amounts['REVIEW'] if not missing['REVIEW'] else None,
                missing_vat_invoices=sum(missing.values()),
                at_risk_invoices=sum(g == 'AT_RISK' for g in groups.values()),
                review_invoices=sum(g == 'REVIEW' for g in groups.values()),
                open_findings=sum(i['status'] in ('AT_RISK', 'REVIEW') for i in items),
                review_transactions=len({t for i in items if i['status'] == 'REVIEW' for t in i.get('txn_ids', [])}),
                opportunity_vat=sum((Decimal(str(i['amount'])) for i in items if i['status'] == 'OPPORTUNITY'), ZERO),
                penalty_rate=Decimal(rate), penalty_basis=basis,
                penalty_estimate=(max(ZERO, amounts['AT_RISK']) * Decimal(rate)).quantize(Decimal(1)) if not missing['AT_RISK'] else None,
                series=[series[k] for k in sorted(series)],
                by_code={c: sum(i['code'] == c for i in items) for c in sorted({i['code'] for i in items})})


def exposure(rep, ruleset):
    from .rules import param
    rep = data(rep)
    as_of = date.fromisoformat(str(rep['meta']['as_of']))
    kind = rep['meta'].get('filing_period', 'MONTH')
    dues = {c['period_key']: date.fromisoformat(str(c['due'])) for c in rep['calendar'] if c.get('obligation') == 'VAT'}
    rate, basis = param(ruleset, 'UNDERDECLARATION_PENALTY_RATE', as_of)
    late = param(ruleset, 'LATE_PAYMENT_RATE_PER_DAY', as_of)
    invs = {i['key']: i for i in rep['invoices']}
    groups = buckets(rep)
    out = {}
    for n, it in enumerate(rep['items']):
        if it['status'] != 'AT_RISK' or not it['invoice_keys']:
            continue
        inv = invs.get(it['invoice_keys'][0])
        if not inv or inv.get('duplicate_of') or not inv.get('issue_date') or groups.get(inv['key']) != 'AT_RISK':
            continue
        due = dues.get(period_key(inv['issue_date'], kind))
        days = max(0, (as_of - due).days) if due else None
        amount = Decimal(str(inv['vat'])) if inv.get('vat') is not None else None
        out[n] = dict(invoice_key=inv['key'], finding_id=it['finding_id'], amount=amount, due=due,
                      days_late=days, overdue=as_of > due if due else None, declared=None,
                      filing_status='UNKNOWN', scenario=True,
                      interest=(amount * Decimal(late[0]) * days).quantize(Decimal(1)) if amount is not None and amount >= 0 and days is not None and late else None,
                      penalty=(amount * Decimal(rate)).quantize(Decimal(1)) if amount is not None and amount >= 0 else None,
                      basis=[basis, late[1] if late else ''],
                      note='Kịch bản giả định khoản thuế này đã được khấu trừ và phát sinh thiếu thuế; chưa xác nhận đã kê khai/nộp. Không phải kết luận xử phạt.')
    return out
