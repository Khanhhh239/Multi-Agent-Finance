"""Router evaluation on configs/assistant/eval/chat_router.json.

  python -m src.assistant.chat.evaluate [dev|holdout|all] [workspace]

Checks per question: the chosen domain (NONE = must refuse), and every parameter the item states (period, invoice
number, issue, seller, top_n). Prints accuracy per split and every miss.
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

from .. import pipeline
from .params import extract
from .router import PROJECT, Router

EVAL = PROJECT / 'configs/assistant/eval/chat_router.json'


def run(split='dev', ws=PROJECT / 'data/eval_ws/saoviet', as_of=date(2026, 11, 6), router=None, out=print):
    src = EVAL.with_name(f'chat_router_{split}.json') if split in ('holdout2', 'holdout3') else EVAL
    items = [x for x in json.loads(src.read_text(encoding='utf-8'))['items'] if split == 'all' or x['split'] == split]
    rep = pipeline.run(Path(ws), pipeline.DEFAULT_RULESET, as_of)
    router = router or Router()
    ok_dom = ok_all = 0
    methods = {}
    misses = []
    t0 = time.time()
    for x in items:
        p = extract(x['q'], rep, router.catalog, as_of)
        r = router.route(x['q'], p)
        got = r.domain or 'NONE'
        if got == 'by_issue' and not p.issue:
            p.issue, p.issue_name = router.issue_by_meaning(x['q'])
        methods[r.method] = methods.get(r.method, 0) + 1
        errs = []
        if got != x['domain']:
            errs.append(f'miền {got} (cần {x["domain"]})')
        if 'period' in x and p.period.to_dict() != {**x['period'], **({} if 'year' in x['period'] else {'year': p.period.year})}:
            errs.append(f'kỳ {p.period.to_dict()} (cần {x["period"]})')
        if 'invoice_number' in x and x['invoice_number'] not in p.invoice_numbers:
            errs.append(f'số hóa đơn {p.invoice_numbers}')
        if 'issue' in x and x['issue'] not in p.issue:
            errs.append(f'loại vấn đề {p.issue}')
        if 'seller' in x and not (p.seller_text and x['seller'] in __import__('src.extraction.xml_context', fromlist=['fold']).fold(p.seller_text)):
            errs.append(f'người bán {p.seller_text}')
        if 'top_n' in x and p.top_n != x['top_n']:
            errs.append(f'top_n {p.top_n}')
        ok_dom += got == x['domain']
        ok_all += not errs
        if errs:
            misses.append(f'  {x["q"]} -> {"; ".join(errs)} [{r.method} {r.score:.3f} {[c["domain"] for c in r.candidates[:3]]}]')
    n = len(items)
    out(f'{split}: {n} câu; đúng miền {ok_dom}/{n} ({ok_dom / n:.1%}); đúng cả tham số {ok_all}/{n} ({ok_all / n:.1%}); '
        f'cách định tuyến {methods}; {time.time() - t0:.1f} giây')
    for m in misses:
        out(m)
    return dict(n=n, domain=ok_dom, all=ok_all, methods=methods, misses=misses)


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'dev', *(sys.argv[2:3] or []))
