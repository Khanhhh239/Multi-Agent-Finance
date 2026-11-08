"""Legal corpus commands.

  python -m src.lawbase.cli sync [--limit N] [--core-only]
  python -m src.lawbase.cli status
  python -m src.lawbase.cli search "câu hỏi" [--as-of YYYY-MM-DD] [-k 5]
  python -m src.lawbase.cli show 108/2025/QH15 [--article 16]
  python -m src.lawbase.cli changes
  python -m src.lawbase.cli check-ruleset  mọi căn cứ của bộ luật trợ lý phải mở được điều khoản còn hiệu lực
  python -m src.lawbase.cli validity      văn bản bị văn bản sau chấm dứt hiệu lực, kèm điều khoản căn cứ
"""
import argparse
import json
import sys
from datetime import date

from .store import Corpus
from .sync import DEFAULT_DB, sync
from .validity import derive


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(prog='lawbase')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sync')
    s.add_argument('--limit', type=int)
    s.add_argument('--core-only', action='store_true')
    s.add_argument('--reparse', action='store_true', help='phân tích lại từ bộ nhớ đệm, không tải lại')
    sub.add_parser('status')
    q = sub.add_parser('search')
    q.add_argument('query')
    q.add_argument('--as-of')
    q.add_argument('-k', type=int, default=5)
    sh = sub.add_parser('show')
    sh.add_argument('doc_num')
    sh.add_argument('--article')
    sub.add_parser('changes')
    sub.add_parser('check-ruleset')
    v = sub.add_parser('validity')
    v.add_argument('--recompute', action='store_true')
    a = p.parse_args(argv)

    if a.cmd == 'sync':
        rep = sync(limit=a.limit, core_only=a.core_only, reparse=a.reparse,
                   progress=lambda n, m: print(f'{n:4d} {m["doc_type"]} {m["doc_num"]} | {m["status_name"]} | hiệu lực {m["eff_from"]}', flush=True))
        print(json.dumps(dict(discovered=rep.discovered, selected=rep.selected, fetched=rep.fetched, unchanged=rep.unchanged,
                              failed=len(rep.failed), quality_issues=len(rep.quality), changes=len(rep.changes), snapshot=rep.snapshot_id,
                              ended_by_later_act=rep.validity.get('ended')),
                         ensure_ascii=False))
        for f in rep.failed[:10]:
            print('LỖI', f)
        return 0
    c = Corpus(DEFAULT_DB)
    try:
        if a.cmd == 'status':
            print(json.dumps(c.stats(), ensure_ascii=False, indent=2))
        elif a.cmd == 'search':
            for r in c.search(a.query, date.fromisoformat(a.as_of) if a.as_of else date.today(), a.k):
                print(f'[{r["rank"]:.2f}] {r["path"]}  ({r["status_name"]}, hiệu lực {r["eff_from"]})\n    {r["text"][:300]}')
        elif a.cmd == 'show':
            d = c.db.execute('SELECT * FROM documents WHERE doc_num=? ORDER BY issue_date DESC', (a.doc_num,)).fetchone()
            if not d:
                print('Không có văn bản này trong kho')
                return 1
            print(f'{d["doc_type"]} {d["doc_num"]}: {d["title"]}\nBan hành {d["issue_date"]}, hiệu lực {d["eff_from"]} đến {d["eff_to"]}, {d["status_name"]}\n{d["url"]}')
            rows = c.db.execute('SELECT * FROM provisions WHERE doc_id=? ORDER BY ord', (d['doc_id'],)).fetchall()
            show, inside = a.article is None, False
            for r in rows:
                if a.article:
                    if r['level'] == 3:
                        inside = r['label'] == f'Điều {a.article}'
                    if r['level'] < 3:
                        inside = False
                if show or inside:
                    print('  ' * (r['level'] - 1) + r['text'][:400])
        elif a.cmd == 'check-ruleset':
            from .check_refs import check
            from .sync import DEFAULT_RULESET
            rows = check(DEFAULT_RULESET, DEFAULT_DB)
            for r in rows:
                mark = {True: 'ĐẠT', False: 'LỖI', None: 'BỎ QUA'}[r['ok']]
                print(f'{mark:6} {r["parameter"]} {r["period"]} {r.get("ref") or ""} {r.get("day") or ""} {r.get("detail") or r.get("url")}')
            return 1 if any(r['ok'] is False for r in rows) else 0
        elif a.cmd == 'validity':
            if a.recompute:
                print(json.dumps({k: v for k, v in derive(c.db).items() if k != 'changed'}, ensure_ascii=False))
            for r in c.db.execute('SELECT d.doc_type, d.doc_num, v.eff_to, v.by_doc_num, v.path, v.exception FROM validity v JOIN documents d USING(doc_id) '
                                  'ORDER BY v.eff_to DESC'):
                exc = f' | ngoại lệ: {r["exception"][:120]}' if r['exception'] else ''
                print(f'{r["doc_type"]} {r["doc_num"]} hết hiệu lực {r["eff_to"]} theo {r["by_doc_num"]} {r["path"] or ""}{exc}')
        elif a.cmd == 'changes':
            for r in c.db.execute('SELECT ch.*, d.doc_num FROM changes ch LEFT JOIN documents d USING(doc_id) ORDER BY snapshot_id DESC LIMIT 50'):
                print(r['snapshot_id'], r['kind'], r['doc_num'], r['detail'])
    finally:
        c.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
