"""Score a report against labels.json of a synthetic workspace: per-code precision and recall, exact-match rate.

Only meaningful on generated data with known answers; it is not an accuracy claim about real enterprises.
"""
import json
from collections import defaultdict
from pathlib import Path

from .models import Report


def evaluate(report: Report, labels_path: Path) -> dict:
    labels = json.loads(Path(labels_path).read_text(encoding='utf-8'))
    key_of = {i.file: i.key for i in report.invoices}
    predicted = defaultdict(set)
    for it in report.items:
        for k in it.invoice_keys:
            predicted[k].add(it.code)
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    rows = []
    expected_all = {key_of.get(f, f'missing:{f}'): set(v['expected']) for f, v in labels['files'].items()}
    expected_all.update({k: set(v) for k, v in labels.get('portal_only', {}).items()})
    for key, exp in sorted(expected_all.items()):
        got = predicted.get(key, set())
        for c in exp & got:
            tp[c] += 1
        for c in got - exp:
            fp[c] += 1
        for c in exp - got:
            fn[c] += 1
        rows.append(dict(key=key, expected=sorted(exp), predicted=sorted(got), ok=exp == got))
    for key, got in predicted.items():                     # items on keys that have no label at all
        if key not in expected_all:
            for c in got:
                fp[c] += 1
            rows.append(dict(key=key, expected=[], predicted=sorted(got), ok=False))
    codes = sorted(set(tp) | set(fp) | set(fn))
    per_code = {c: dict(tp=tp[c], fp=fp[c], fn=fn[c],
                        precision=round(tp[c] / (tp[c] + fp[c]), 3) if tp[c] + fp[c] else None,
                        recall=round(tp[c] / (tp[c] + fn[c]), 3) if tp[c] + fn[c] else None) for c in codes}
    return dict(invoices=len(rows), exact_match=sum(r['ok'] for r in rows), per_code=per_code,
                mismatches=[r for r in rows if not r['ok']])
