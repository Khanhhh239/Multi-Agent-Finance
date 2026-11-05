"""Which documents a newer document ends, read from the newer document's own text.

The status field on the source site lags: an act replaced years ago may still read "partly expired", and a consolidated text
carries no effective dates at all. The authoritative statement is the "effect" clause of the replacing act, for example
"Luật Quản lý thuế số 38/2019/QH14 ... hết hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành". This module finds
those clauses, resolves the document numbers they name against the corpus, and records an end date with the clause as its
basis. Rules, all deterministic:

* Two wordings are read: "... hết hiệu lực ..." and "<this act> thay thế | bãi bỏ: a) Nghị định số ...; b) ..." (the form used by
  the 2026 implementing decrees and circulars). In the second, a point that starts with "Điều", "khoản", "điểm" or a head that
  says "nội dung", "các quy định tại" repeals only part of a document and becomes a note; "thay thế mẫu số ..." is ignored.
* Only clauses of documents that are themselves indexed and have an effective date are read.
* A clause whose subject is a part of a document ("Điều 51 của Luật ...", "khoản 2 Điều 3 ...") is recorded as a note for the
  reviewer and never ends the whole document.
* A clause that ends a whole document but keeps an exception ("..., trừ quy định tại khoản 1 Điều 53 của Luật này") still ends
  it; the exception text is kept with the record because it usually concerns transitional cases.
* Acts named as having amended the ending act ("... đã được sửa đổi, bổ sung theo Luật số 26/2012/QH13, Luật số 48/2024/QH15")
  end with it only when they are dedicated amending acts of that one act: the title says "sửa đổi" and names that act and no
  other. A main act that also amended a few articles of it (48/2024/QH15 above is the VAT law) or an act amending several
  laws keeps its validity; the mention is kept as a note.
* The end date is the explicit date in the clause when there is one, otherwise the effective date of the replacing document.
* A consolidated text ("văn bản hợp nhất") inherits the end date of the act it consolidates, named in its title.
* When several clauses end the same document, the earliest date wins.
* Inside an act that amends other acts, an article "Sửa đổi, bổ sung một số điều của Luật X [số N]" belongs to its target: the act
  numbered N, or else the act named "Luật X" with the latest effective date not after the amending act's own. When that target
  has ended, every provision of the article is stale from the same date (table stale_provisions); articles amending acts still
  in force stay searchable.
"""
import re
import sqlite3
import unicodedata
from dataclasses import dataclass

NUM = r'\d+[a-z]?/(?:\d{4}/)?[A-ZĐ][A-ZĐ0-9]*(?:-[A-ZĐ0-9]+)*'
NUM_RE = re.compile(rf'(?<![\w/])({NUM})(?![\w/])')
EXPIRE_RE = re.compile(r'hết\s+hiệu\s+lực', re.I)
PART_RE = re.compile(r'^(?:\d+\.\s*|[a-zđ]\)\s*)?(?:riêng\s+)?(?:các\s+)?(?:quy\s+định\s+tại\s+)?(?:các\s+)?(?:Điều|điều|khoản|Khoản|điểm|Điểm|Chương|chương|Mục|mục|Phụ\s+lục|phụ\s+lục)\b')
AMEND_RE = re.compile(r'sửa\s+đổi,?\s+bổ\s+sung[^;(]*?(?:theo|bởi|tại)\s+(.*?)(?:\(sau\s+đây|$)', re.I | re.S)
DATE_RE = re.compile(r'kể\s+từ\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', re.I)
SCHEMA = """
CREATE TABLE IF NOT EXISTS validity(doc_id TEXT PRIMARY KEY, eff_to TEXT, by_doc_id TEXT, by_prov_id TEXT, by_doc_num TEXT, path TEXT,
  exception TEXT, quote TEXT);
CREATE TABLE IF NOT EXISTS validity_notes(doc_id TEXT, by_doc_id TEXT, by_prov_id TEXT, by_doc_num TEXT, kind TEXT, quote TEXT);
CREATE TABLE IF NOT EXISTS stale_provisions(doc_id TEXT, prov_id TEXT, ended_on TEXT, target_doc_id TEXT, target_num TEXT,
  PRIMARY KEY(doc_id, prov_id));
"""


@dataclass
class Finding:
    target: str          # document number as written
    kind: str            # FULL | PARTIAL
    eff_to: str | None
    exception: str
    quote: str
    role: str = 'primary'  # primary | amending
    name: str = ''        # name of the ending act as written in the clause, for checking amending acts


def norm_num(num: str) -> str:
    return re.sub(r'\s+', '', num).upper().replace('Ð', 'Đ')


def segments(text: str) -> list[str]:
    """Split a clause into statements: one statement per ';' or sentence end, keeping document numbers intact."""
    parts = re.split(r';\s+|(?<=[^\d/])\.\s+(?=[A-ZĐÀ-Ỹ])|\./\.', text)
    return [p.strip() for p in parts if p and p.strip()]


def read_clause(text: str, own_eff_from: str | None) -> list[Finding]:
    out = []
    for seg in segments(text):
        m = EXPIRE_RE.search(seg)
        if not m:
            continue
        subject, rest = seg[:m.start()], seg[m.end():]
        nums = NUM_RE.findall(subject)
        if not nums:
            continue
        d = DATE_RE.search(rest)
        eff_to = f'{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}' if d else own_eff_from
        if PART_RE.match(subject.strip()):
            out.append(Finding(nums[-1], 'PARTIAL', eff_to, '', seg[:600]))
            continue
        exception = ''
        e = re.search(r',?\s*trừ\s+(.*)$', rest, re.S)
        if e:
            exception = e.group(1).strip()[:400]
        nm = re.search(r'(?:Luật|Nghị\s+định|Thông\s+tư|Pháp\s+lệnh|Nghị\s+quyết)\s+(.*?)\s+số\s+' + re.escape(nums[0]), subject)
        name = nm.group(1) if nm else ''
        out.append(Finding(nums[0], 'FULL', eff_to, exception, seg[:600]))
        a = AMEND_RE.search(subject)
        for n in dict.fromkeys(NUM_RE.findall(a.group(1)) if a else []):
            if n != nums[0]:
                out.append(Finding(n, 'FULL', eff_to, exception, seg[:600], role='amending', name=name))
    return out


TYPE_WORD = re.compile(r'\b(?:luat|nghi dinh|thong tu|phap lenh)\b')


def fold(s: str) -> str:
    t = unicodedata.normalize('NFD', (s or '').replace('đ', 'd').replace('Đ', 'D'))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).lower().strip()


def dedicated_amendment(title: str, ended_name: str) -> bool:
    """'Luật Sửa đổi, bổ sung một số Điều của Luật Thuế thu nhập cá nhân số 26/2012/QH13' amends 'Thuế thu nhập cá nhân' only."""
    t, n = fold(title), fold(ended_name)
    if 'sua doi' not in t or not n or n not in t:
        return False
    return len(TYPE_WORD.findall(t.split(' ', 1)[1] if ' ' in t else '')) == 1


REPLACE_HEAD_RE = re.compile(r'(?:Luật|Nghị\s+định|Thông\s+tư|Nghị\s+quyết|Quyết\s+định|Pháp\s+lệnh)\s+này\s+(?:thay\s+thế|bãi\s+bỏ)\s*(.*)$', re.I | re.S)
PARTIAL_REST_RE = re.compile(r'^[:\s]*(?:nội\s+dung|các\s+quy\s+định|quy\s+định|một\s+số|các\s+điều|các\s+khoản|các\s+điểm|điều|khoản|điểm|'
                             r'mẫu|các\s+mẫu|cụm\s+từ|phụ\s+lục|các\s+phụ\s+lục)\b', re.I)


def read_replace_clause(head: str, items: list[tuple[str, str]], own_eff_from: str | None) -> list[tuple[Finding, str | None]]:
    """A clause "<this act> thay thế|bãi bỏ ..." with the replaced acts inline or as lettered points (children).
    Only the first document number of each point is the target; numbers in its description are not."""
    m = REPLACE_HEAD_RE.search(head)
    e = EXPIRE_RE.search(head)
    if m:
        rest = m.group(1).strip()
    elif e and head.rstrip().endswith(':') and not NUM_RE.search(head[:e.start()]):
        rest = ':'                                       # "... các Nghị định sau đây hết hiệu lực thi hành:" + lettered points
    else:
        return []
    partial = bool(PARTIAL_REST_RE.match(rest))
    if re.match(r'^[:\s]*(?:mẫu|các\s+mẫu|cụm\s+từ)', rest, re.I):
        return []                                        # forms or wording, not documents
    d = DATE_RE.search(head)
    eff_to = f'{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}' if d else own_eff_from
    pieces = [(rest, None)] if NUM_RE.search(rest) and not rest.rstrip().endswith(':') else [(t, p) for p, t in items]
    out = []
    for text, prov in pieces:
        body = re.sub(r'^\s*[a-zđ]\)\s*', '', text or '')
        nums = NUM_RE.findall(body)
        if not nums:
            continue
        kind = 'PARTIAL' if partial or PART_RE.match(body) or re.match(r'^(?:Các\s+|các\s+)?(?:điểm|khoản|Điều|Bỏ\s+cụm\s+từ)', body) else 'FULL'
        out.append((Finding(nums[0], kind, eff_to, '', body[:600]), prov))
    return out


def consolidated_base(title: str) -> str | None:
    """'Văn bản hợp nhất số 29/VBHN-VPQH Luật Quản lý thuế số 38/2019/QH14' -> '38/2019/QH14'."""
    nums = [n for n in NUM_RE.findall(title or '') if 'VBHN' not in n.upper()]
    return nums[0] if nums else None


AMEND_ARTICLE_RE = re.compile(r'sửa\s+đổi,?\s+bổ\s+sung[^.;:]{0,60}?\bcủa\s+(Luật|Nghị\s+định|Thông\s+tư|Pháp\s+lệnh)\s+([^,;:.()]+?)'
                              rf'(?:\s+số\s+({NUM}))?(?=\s*(?:[,;:.()]|như\s+sau|$))', re.I)


def act_name(title: str) -> str:
    """'Luật Quản lý thuế số 38/2019/QH14' -> 'luat quan ly thue'."""
    return fold(re.split(r'\s+số\s+', title or '', maxsplit=1)[0])


def stale_articles(db: sqlite3.Connection, ends: dict) -> list[tuple]:
    """(doc_id, prov_id, ended_on, target_doc_id, target_num) for every provision under an article that amends an ended act."""
    docs = {r[0]: r for r in db.execute('SELECT doc_id, doc_num, title, eff_from, eff_to, doc_type FROM documents')}
    by_num = {}
    for d in docs.values():
        if d[1]:
            by_num.setdefault(norm_num(d[1]), []).append(d[0])

    def end_of(doc_id):
        cands = [x for x in (docs[doc_id][4], ends.get(doc_id)) if x]
        return min(cands) if cands else None

    out = []
    amending = [d for d in docs.values() if 'sua doi' in fold(d[2]) and d[3]]
    for a_id, _, _, a_from, _, _ in amending:
        provs = db.execute('SELECT prov_id, level, text, parent FROM provisions WHERE doc_id=? ORDER BY ord', (a_id,)).fetchall()
        children = {}
        for pid, _, _, parent in provs:
            children.setdefault(parent, []).append(pid)
        for pid, level, text, _ in provs:
            if level != 3:
                continue
            m = AMEND_ARTICLE_RE.search((text or '')[:400])
            if not m:
                continue
            kind, name, num = m.group(1), m.group(2), m.group(3)
            if num:
                targets = [t for t in by_num.get(norm_num(num), []) if t != a_id]
            else:
                want = fold(f'{kind} {name}')
                same = [d for d in docs.values() if d[0] != a_id and act_name(d[2]) == want and d[3] and d[3] <= a_from]
                targets = [max(same, key=lambda d: d[3])[0]] if same else []
            if len(targets) != 1 or not end_of(targets[0]):
                continue
            t = targets[0]
            stack = [pid]
            while stack:
                cur = stack.pop()
                out.append((a_id, cur, end_of(t), t, docs[t][1]))
                stack += children.get(cur, [])
    return out


def derive(db: sqlite3.Connection) -> dict:
    """Recompute the validity tables from the stored text. Returns counts and the list of documents whose end date changed."""
    db.executescript(SCHEMA)
    before = dict(db.execute('SELECT doc_id, eff_to FROM validity').fetchall())
    by_num, titles = {}, {}
    for doc_id, num, title in db.execute('SELECT doc_id, doc_num, title FROM documents WHERE doc_num IS NOT NULL'):
        by_num.setdefault(norm_num(num), []).append(doc_id)
        titles[doc_id] = title or ''
    rows = db.execute("""SELECT p.doc_id, p.prov_id, p.text, d.doc_num, d.eff_from, d.title FROM provisions p JOIN documents d USING(doc_id)
                         WHERE d.indexed=1 AND d.eff_from IS NOT NULL AND p.text LIKE '%hiệu lực%'""").fetchall()
    full, notes = {}, []
    for doc_id, prov_id, text, doc_num, eff_from, title in rows:
        if not EXPIRE_RE.search(text):
            continue
        path = ''
        for f in read_clause(text, eff_from):
            for target in by_num.get(norm_num(f.target), []):
                if target == doc_id:
                    continue
                if f.kind == 'PARTIAL':
                    notes.append((target, doc_id, prov_id, doc_num, 'PARTIAL', f.quote))
                    continue
                if f.role == 'amending' and not dedicated_amendment(titles.get(target, ''), f.name):
                    notes.append((target, doc_id, prov_id, doc_num, 'AMENDING_KEPT', f.quote))
                    continue
                cur = full.get(target)
                if f.eff_to and (cur is None or f.eff_to < cur[0]):
                    full[target] = (f.eff_to, doc_id, prov_id, doc_num, path, f.exception, f.quote)
    # "Nghị định này thay thế: a) Nghị định số 126/2020/NĐ-CP ...; b) ..." and "Thông tư này bãi bỏ: ..."
    heads = db.execute("""SELECT p.doc_id, p.prov_id, p.text, d.doc_num, d.eff_from FROM provisions p JOIN documents d USING(doc_id)
                          WHERE d.indexed=1 AND d.eff_from IS NOT NULL AND (p.text LIKE '%này thay thế%' OR p.text LIKE '%này bãi bỏ%'
                                OR p.text LIKE '%hết hiệu lực%:')""").fetchall()
    for doc_id, prov_id, text, doc_num, eff_from in heads:
        items = db.execute('SELECT prov_id, text FROM provisions WHERE doc_id=? AND parent=? ORDER BY ord', (doc_id, prov_id)).fetchall()
        for f, item_prov in read_replace_clause(text, [(p, t) for p, t in items], eff_from):
            for target in by_num.get(norm_num(f.target), []):
                if target == doc_id:
                    continue
                if f.kind == 'PARTIAL':
                    notes.append((target, doc_id, item_prov, doc_num, 'PARTIAL', f.quote))
                    continue
                cur = full.get(target)
                if f.eff_to and (cur is None or f.eff_to < cur[0]):
                    full[target] = (f.eff_to, doc_id, item_prov, doc_num, '', f.exception, f.quote)
    # consolidated texts follow the act they consolidate
    for doc_id, title in db.execute("SELECT doc_id, title FROM documents WHERE doc_num LIKE '%VBHN%'").fetchall():
        base = consolidated_base(title)
        for b in by_num.get(norm_num(base), []) if base else []:
            if b in full and doc_id not in full:
                eff_to, by_doc, by_prov, by_num_s, _, exc, quote = full[b]
                full[doc_id] = (eff_to, by_doc, by_prov, by_num_s, f'hợp nhất của {base}', exc, quote)
    db.execute('DELETE FROM validity')
    db.execute('DELETE FROM validity_notes')
    db.execute('DELETE FROM stale_provisions')
    db.executemany('INSERT INTO validity VALUES(?,?,?,?,?,?,?,?)', [(k, *v) for k, v in full.items()])
    db.executemany('INSERT INTO validity_notes VALUES(?,?,?,?,?,?)', notes)
    stale = stale_articles(db, {k: v[0] for k, v in full.items()})
    db.executemany('INSERT OR REPLACE INTO stale_provisions VALUES(?,?,?,?,?)', stale)
    db.commit()
    changed = [(k, before.get(k), v[0]) for k, v in full.items() if before.get(k) != v[0]]
    changed += [(k, before[k], None) for k in before if k not in full]
    return dict(ended=len(full), partial_notes=len(notes), stale_provisions=len(stale), changed=changed)
