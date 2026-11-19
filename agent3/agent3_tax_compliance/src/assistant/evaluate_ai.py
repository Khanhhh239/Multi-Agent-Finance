"""Measure the AI layer on hand-labelled data with dual-tier reporting (clear statutory cases vs ambiguous boundary cases).

  python -m src.assistant.evaluate_ai lines          A1 line purpose with the configured API model
  python -m src.assistant.evaluate_ai deterministic  A1 line purpose using the deterministic fallback classifier only
  python -m src.assistant.evaluate_ai explain WS     A4 share of explanations that pass the number check on a workspace report
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

from . import ai

PROJECT = Path(__file__).resolve().parents[2]


def _boundary_is_safe(line_name: str, category: str, business_use: str | None, verified: bool, reason: str) -> bool:
    """A boundary/ambiguous item is handled safely when it is NOT rubber-stamped as raw inventory (HANG_HOA_KINH_DOANH + CO)
    and either abstains (KHONG_RO / business_use=KHONG_RO / unverified) or selects an appropriate cautious category
    (CONG_CU_TAI_SAN, DICH_VU_VAN_HANH, TIEP_KHACH, CA_NHAN) with a non-empty explanation."""
    from ..extraction.xml_context import fold
    f = fold(line_name)
    if f in ('hang hoa', 'dich vu', 'chi phi'):
        return category == 'KHONG_RO' or business_use == 'KHONG_RO' or not verified
    if business_use == 'KHONG_RO':
        return bool((reason or '').strip())
    if any(k in f for k in ('ruou vang', 'banh trung thu', 'qua tet', 'tiep khach')):
        return category in ('TIEP_KHACH', 'CA_NHAN', 'KHONG_RO') and bool((reason or '').strip())
    return category in ('CONG_CU_TAI_SAN', 'DICH_VU_VAN_HANH', 'TIEP_KHACH', 'CA_NHAN', 'KHONG_RO') and bool((reason or '').strip())


def lines(batch: int = 5, name: str = 'line_purpose', *, deterministic_only: bool = False, model: ai.AI | None = None) -> dict:
    spec = json.loads((PROJECT / f'configs/assistant/eval/{name}.json').read_text(encoding='utf-8'))
    used_model = None if deterministic_only else (model or ai.AI())
    rows, t0 = [], time.time()
    items = spec['lines']
    for k in range(0, len(items), batch):
        chunk = items[k:k + batch]
        out = ai.classify_lines(used_model, dict(seller_name='Người bán thử', descriptions=[x[0] for x in chunk]), spec['industry'])
        flagged_set = {x['line'] for x in ai.flagged(out['labels'])}
        for (item_name, want), lab in zip(chunk, out['labels']):
            rows.append(dict(
                line=item_name,
                want=want,
                got=item_name in flagged_set,
                verified=lab['verified'],
                category=lab['category'],
                business_use=lab.get('business_use'),
                reason=lab['reason'],
                fallback_reason=lab.get('fallback_reason'),
            ))

    clear = [r for r in rows if r['want'] is not None]
    boundary = [r for r in rows if r['want'] is None]

    tp = sum(bool(r['want']) and r['got'] for r in clear)
    fp = sum((not r['want']) and r['got'] for r in clear)
    fn = sum(bool(r['want']) and not r['got'] for r in clear)
    tn = sum((not r['want']) and not r['got'] for r in clear)
    acc = round((tp + tn) / len(clear), 3) if clear else None
    prec = round(tp / (tp + fp), 3) if (tp + fp) else None
    rec = round(tp / (tp + fn), 3) if (tp + fn) else None
    f1 = round(2 * tp / (2 * tp + fp + fn), 3) if (2 * tp + fp + fn) else None

    boundary_safe = [r for r in boundary if _boundary_is_safe(r['line'], r['category'], r.get('business_use'), r['verified'], r['reason'])]
    boundary_cats = dict(sorted(Counter(r['category'] for r in boundary).items()))

    for r in rows:
        if r['want'] is None:
            safe_ok = _boundary_is_safe(r['line'], r['category'], r.get('business_use'), r['verified'], r['reason'])
            mark = 'RANH_OK' if safe_ok else 'RANH_LOI'
        else:
            mark = 'ĐÚNG' if r['want'] == r['got'] else 'SAI'
        print(f'{mark:8} cờ={str(r["got"]):5} nhãn={str(r["want"]):5} {r["category"]:20} {r["line"]} | {r["reason"][:90]}')

    res = dict(
        mode='deterministic' if deterministic_only else (used_model.model_name if used_model else 'deterministic'),
        lines=len(rows),
        scored=len(clear),
        accuracy=acc,
        precision=prec,
        recall=rec,
        f1=f1,
        false_flags_on_business_items=fp,
        unverified=sum(not r['verified'] for r in rows),
        clear_cases=dict(
            count=len(clear),
            accuracy=acc,
            precision=prec,
            recall=rec,
            f1=f1,
            tp=tp,
            fp=fp,
            fn=fn,
            tn=tn,
            false_flags_on_business_items=fp,
        ),
        boundary_cases=dict(
            count=len(boundary),
            safe_behavior_count=len(boundary_safe),
            safe_behavior_rate=round(len(boundary_safe) / len(boundary), 3) if boundary else None,
            flagged_for_review=sum(r['got'] for r in boundary),
            unverified_or_abstained=sum((r['category'] == 'KHONG_RO' or not r['verified']) for r in boundary),
            by_category=boundary_cats,
        ),
        seconds=round(time.time() - t0, 1),
    )
    print(json.dumps(res, ensure_ascii=False))
    return res


def explain(ws):
    rep = json.loads((Path(ws) / 'out' / 'report.json').read_text(encoding='utf-8'))
    model, modes, t0 = ai.AI(), [], time.time()
    invs = {i['key']: i for i in rep['invoices']}
    for it in rep['items']:
        inv = invs.get(it['invoice_keys'][0]) if it['invoice_keys'] else None
        e = ai.explain(model, it, inv)
        modes.append(e.mode)
        print(f'{e.mode:12} {it["code"]:24} {e.text[:150]} {e.note}')
    res = dict(items=len(modes), ai_verified=modes.count('AI_VERIFIED'), template=modes.count('TEMPLATE'), seconds=round(time.time() - t0, 1))
    print(json.dumps(res, ensure_ascii=False))
    return res


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'lines'
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    dispatch = {
        'lines': lambda: lines(name=arg or 'line_purpose', deterministic_only=False),
        'deterministic': lambda: lines(name=arg or 'line_purpose', deterministic_only=True),
        'explain': lambda: explain(arg),
    }
    dispatch[cmd]()
