"""Persist a card's measured test result and experimental decision log."""
import argparse,json,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--card',required=True)
    p.add_argument('--xml',required=True)
    p.add_argument('--summary',required=True)
    p.add_argument('--decision',required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    suite=ET.parse(root/args.xml).getroot().find('testsuite')
    if suite is None: raise SystemExit('Missing test suite.')
    record={k:float(suite.attrib[k]) if k=='time' else int(suite.attrib[k]) for k in ('tests','failures','errors','skipped','time')}
    if record['failures'] or record['errors']: raise SystemExit('Cannot record a successful card with failed tests.')
    record.update(card=args.card,notice='công thức chưa được kế toán duyệt (G0.7 mở)',
                  measured_at_utc=datetime.now(timezone.utc).isoformat(),xml=args.xml,
                  summary=args.summary,decision=args.decision)
    path=root/'docs/5_handoff/measurements'/f"{args.card.lower().replace('.','_')}_tests.json"
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    with (root/'docs/5_handoff/PROGRESS.md').open('a',encoding='utf-8') as f:
        f.write(f"\n### {args.card} — P1 thử nghiệm\n\n{args.summary}\n\nToàn bộ test trước commit: **{record['tests']-record['skipped']} passed, {record['skipped']} skipped**, {record['time']:.2f} giây; `{args.xml}`. công thức chưa được kế toán duyệt (G0.7 mở).\n")
    with (root/'docs/5_handoff/DECISIONS.md').open('a',encoding='utf-8') as f:
        f.write(f"\n| 2026-10-16 | {args.card} thử nghiệm | {args.decision.replace('|','/')} | {args.summary.replace('|','/')} | công thức chưa được kế toán duyệt (G0.7 mở); không chứng nhận pilot |\n")
    print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__': main()
