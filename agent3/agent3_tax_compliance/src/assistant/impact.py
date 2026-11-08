"""Step 9: law-change impact. Run the same data under two rulesets and list what changes, per invoice."""
from decimal import Decimal

from .models import Report


def _per_invoice(report: Report) -> dict:
    out = {}
    for it in report.items:
        for k in it.invoice_keys:
            rec = out.setdefault(k, dict(codes=set(), at_risk=Decimal(0)))
            rec['codes'].add(it.code)
            if it.status == 'AT_RISK':
                rec['at_risk'] = max(rec['at_risk'], it.amount)
    return out


def compare(before: Report, after: Report) -> dict:
    a, b = _per_invoice(before), _per_invoice(after)
    changes = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k, dict(codes=set(), at_risk=Decimal(0))), b.get(k, dict(codes=set(), at_risk=Decimal(0)))
        if x['codes'] != y['codes'] or x['at_risk'] != y['at_risk']:
            inv = next((i for i in after.invoices if i.key == k), None)
            changes.append(dict(key=k, invoice=inv.display if inv else k, seller=inv.seller_name if inv else '',
                                added=sorted(y['codes'] - x['codes']), removed=sorted(x['codes'] - y['codes']),
                                at_risk_before=x['at_risk'], at_risk_after=y['at_risk']))
    return dict(ruleset_before=before.meta['ruleset_version'], ruleset_after=after.meta['ruleset_version'], changes=changes,
                at_risk_before=before.totals['at_risk_vat'], at_risk_after=after.totals['at_risk_vat'],
                delta=after.totals['at_risk_vat'] - before.totals['at_risk_vat'])
