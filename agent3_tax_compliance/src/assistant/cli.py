"""Command line for the tax-risk assistant.

  python -m src.assistant.cli synth    --out WORKSPACE
  python -m src.assistant.cli run      --workspace WORKSPACE [--as-of YYYY-MM-DD] [--ruleset FILE]
  python -m src.assistant.cli ask      --workspace WORKSPACE "câu hỏi"
  python -m src.assistant.cli impact   --workspace WORKSPACE --ruleset-after FILE
  python -m src.assistant.cli evaluate --workspace WORKSPACE
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import impact, pipeline, qa, report, synth
from .evaluate import evaluate
from .report import money


def _as_of(args, ws):
    if args.as_of:
        return date.fromisoformat(args.as_of)
    labels = Path(ws) / 'labels.json'
    if labels.exists():                       # synthetic workspaces carry their reference date
        return date.fromisoformat(json.loads(labels.read_text(encoding='utf-8'))['as_of'])
    return date.today()


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(prog='assistant')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('synth')
    s.add_argument('--out', required=True)
    s.add_argument('--seed', type=int, default=7)
    for name in ('run', 'ask', 'impact', 'evaluate'):
        c = sub.add_parser(name)
        c.add_argument('--workspace', required=True)
        c.add_argument('--as-of')
        c.add_argument('--ruleset', default=str(pipeline.DEFAULT_RULESET))
        if name == 'ask':
            c.add_argument('question')
        if name == 'impact':
            c.add_argument('--ruleset-after', required=True)
    a = p.parse_args(argv)

    if a.cmd == 'synth':
        print(json.dumps(synth.generate(Path(a.out), a.seed), ensure_ascii=False))
        return 0
    ws = Path(a.workspace)
    as_of = _as_of(a, ws)
    rep = pipeline.run(ws, Path(a.ruleset), as_of)
    if a.cmd == 'run':
        paths = report.write(rep, ws / 'out')
        t = rep.totals
        print(f'Thuế có nguy cơ: {money(t["at_risk_vat"])} trên {t["at_risk_invoices"]} hóa đơn; cần xem xét {t["review_invoices"]} hóa đơn; '
              f'có thể bỏ sót {money(t["opportunity_vat"])}.')
        print('Báo cáo:', paths['html'])
    elif a.cmd == 'ask':
        from ..lawbase.sync import DEFAULT_DB as LAWBASE_DB
        ans = qa.answer(a.question, qa.Context(ws, Path(a.ruleset), as_of, rep, LAWBASE_DB if LAWBASE_DB.exists() else None))
        print(f'[{ans.branch}] {ans.text}')
        for c in ans.citations:
            print('  căn cứ:', c)
    elif a.cmd == 'impact':
        after = pipeline.run(ws, Path(a.ruleset_after), as_of)
        res = impact.compare(rep, after)
        print(f'{res["ruleset_before"]} -> {res["ruleset_after"]}: thuế có nguy cơ {money(res["at_risk_before"])} -> {money(res["at_risk_after"])}')
        for ch in res['changes']:
            print(f'  {ch["invoice"]} {ch["seller"]}: thêm {ch["added"]} bỏ {ch["removed"]} ({money(ch["at_risk_before"])} -> {money(ch["at_risk_after"])})')
    elif a.cmd == 'evaluate':
        res = evaluate(rep, ws / 'labels.json')
        print(f'Khớp hoàn toàn {res["exact_match"]}/{res["invoices"]} hóa đơn')
        for code, m in res['per_code'].items():
            print(f'  {code}: đúng {m["tp"]}, báo oan {m["fp"]}, bỏ sót {m["fn"]}')
        for r in res['mismatches']:
            print('  LỆCH', r)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
