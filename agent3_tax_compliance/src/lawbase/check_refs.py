"""Check every legal reference of the assistant ruleset against the corpus.

A reference is (document number, article, clause or None). Several documents can share a number (consolidated texts are
numbered per year), so a reference is resolved at the dates it is used: the start of the parameter's period (or the check
date when the period is open at the start) and, for an open-ended period, the check date. At each date there must be a
document with that number that is in force (own dates, end date read from a replacing act) and contains the provision.
Anything else is reported, so a law change shows up as a failed check instead of a silently stale rule.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path


def _in_force(db, doc_id: str, day: str) -> bool:
    r = db.execute("""SELECT COALESCE(d.eff_from, d.issue_date, '0000') <= ? AND (d.eff_to IS NULL OR d.eff_to > ?)
                      AND (v.eff_to IS NULL OR v.eff_to > ?) FROM documents d LEFT JOIN validity v USING(doc_id) WHERE d.doc_id=?""",
                   (day, day, day, doc_id)).fetchone()
    return bool(r and r[0])


def _has_provision(db, doc_id: str, article: str, clause: str | None) -> str | None:
    """prov_id of the article (or of the clause inside it), or None."""
    rows = db.execute('SELECT prov_id, level, label, parent FROM provisions WHERE doc_id=? ORDER BY ord', (doc_id,)).fetchall()
    arts = [r for r in rows if r[1] == 3 and (r[2] or '').strip() == article]
    for a in arts:
        if clause is None:
            return a[0]
        for r in rows:
            if r[3] == a[0] and (r[2] or '').strip() == clause:
                return r[0]
    return None


def check(ruleset_path: Path, db_path: Path, today: date | None = None) -> list[dict]:
    today = (today or date.today()).isoformat()
    rs = json.loads(Path(ruleset_path).read_text(encoding='utf-8'))
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    out = []
    try:
        for name, periods in rs['parameters'].items():
            for per in periods:
                refs = per.get('refs') or []
                if not refs:
                    out.append(dict(parameter=name, period=(per.get('from'), per.get('to')), ref=None, ok=False if per.get('to') is None else None,
                                    detail='không có căn cứ trong kho (chỉ có nguồn thứ cấp)' if per.get('to') is None else
                                    'kỳ đã qua, căn cứ thứ cấp; không kiểm'))
                    continue
                days = sorted({per.get('from') or today} | ({today} if per.get('to') is None or per['to'] > today else set()))
                days = [d for d in days if per.get('to') is None or d < per['to']]
                for num, article, clause in refs:
                    docs = [r[0] for r in db.execute('SELECT doc_id FROM documents WHERE doc_num=?', (num,))]
                    for day in days:
                        hits = [(d, _has_provision(db, d, article, clause)) for d in docs if _in_force(db, d, day)]
                        hits = [(d, p) for d, p in hits if p]
                        if hits:
                            url = db.execute('SELECT url FROM documents WHERE doc_id=?', (hits[0][0],)).fetchone()[0]
                            out.append(dict(parameter=name, period=(per.get('from'), per.get('to')), ref=[num, article, clause], day=day,
                                            ok=True, doc_id=hits[0][0], prov_id=hits[0][1], url=url, ambiguous=len(hits) > 1))
                        else:
                            why = 'không có văn bản số này trong kho' if not docs else 'không có văn bản số này còn hiệu lực và chứa điều khoản này'
                            ended = db.execute('SELECT v.eff_to, v.by_doc_num FROM validity v WHERE v.doc_id IN (%s)' % ','.join('?' * len(docs)),
                                               docs).fetchall() if docs else []
                            if ended:
                                why += '; ' + ', '.join(f'hết hiệu lực từ {e} theo {b}' for e, b in ended)
                            out.append(dict(parameter=name, period=(per.get('from'), per.get('to')), ref=[num, article, clause], day=day,
                                            ok=False, detail=why))
    finally:
        db.close()
    return out
