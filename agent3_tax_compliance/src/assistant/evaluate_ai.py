"""Measure the AI layer on hand-labelled data with the local model. Prints real numbers; nothing is tuned on this set.

  python -m src.assistant.evaluate_ai lines      A1 line purpose (precision and recall of the review flag)
  python -m src.assistant.evaluate_ai explain WS A4 share of explanations that pass the number check, on a workspace report
"""
import json
import sys
import time
from pathlib import Path

from . import ai

PROJECT = Path(__file__).resolve().parents[2]


def lines(batch=5, name='line_purpose'):
    spec = json.loads((PROJECT / f'configs/assistant/eval/{name}.json').read_text(encoding='utf-8'))
    model = ai.AI()
    rows, t0 = [], time.time()
    items = spec['lines']
    for k in range(0, len(items), batch):
        chunk = items[k:k + batch]
        out = ai.classify_lines(model, dict(seller_name='Người bán thử', descriptions=[x[0] for x in chunk]), spec['industry'])
        flagged = {x['line'] for x in ai.flagged(out['labels'])}
        for (name, want), lab in zip(chunk, out['labels']):
            rows.append(dict(line=name, want=want, got=name in flagged, verified=lab['verified'], category=lab['category'], reason=lab['reason']))
    scored = [r for r in rows if r['want'] is not None]
    tp = sum(r['want'] and r['got'] for r in scored)
    fp = sum((not r['want']) and r['got'] for r in scored)
    fn = sum(r['want'] and not r['got'] for r in scored)
    for r in rows:
        mark = '' if r['want'] is None else ('ĐÚNG' if r['want'] == r['got'] else 'SAI')
        print(f'{mark:5} cờ={str(r["got"]):5} nhãn={str(r["want"]):5} {r["category"]:20} {r["line"]} | {r["reason"][:90]}')
    res = dict(lines=len(rows), scored=len(scored), accuracy=round(sum(r['want'] == r['got'] for r in scored) / len(scored), 3),
               precision=round(tp / (tp + fp), 3) if tp + fp else None, recall=round(tp / (tp + fn), 3) if tp + fn else None,
               false_flags_on_business_items=fp, unverified=sum(not r['verified'] for r in rows), seconds=round(time.time() - t0, 1))
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
    {'lines': lambda: lines(name=sys.argv[2] if len(sys.argv) > 2 else 'line_purpose'), 'explain': lambda: explain(sys.argv[2])}[sys.argv[1]]()
