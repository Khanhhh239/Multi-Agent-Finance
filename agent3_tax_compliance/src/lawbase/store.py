"""SQLite legal corpus: documents, provision tree, retrieval chunks with an FTS5 index, snapshots and change log."""
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from .validity import SCHEMA as VALIDITY_SCHEMA
from .vbpl import ParsedDoc, chunks

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(doc_id TEXT PRIMARY KEY, url TEXT, slug TEXT, lastmod TEXT, doc_num TEXT, title TEXT, doc_type TEXT,
  doc_type_code TEXT, issue_date TEXT, eff_from TEXT, eff_to TEXT, status_code TEXT, status_name TEXT, structure TEXT, notes TEXT,
  n_provisions INTEGER, n_chunks INTEGER, html_sha256 TEXT, fetched_at TEXT, core INTEGER DEFAULT 0, indexed INTEGER DEFAULT 1,
  review_status TEXT DEFAULT 'UNREVIEWED');
CREATE TABLE IF NOT EXISTS provisions(doc_id TEXT, prov_id TEXT, level INTEGER, label TEXT, heading TEXT, text TEXT, parent TEXT,
  ord INTEGER, text_sha256 TEXT, PRIMARY KEY(doc_id, prov_id));
CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, doc_id TEXT, prov_id TEXT, path TEXT, text TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, path, text, folded, bigrams,
  tokenize="unicode61 remove_diacritics 0");
CREATE TABLE IF NOT EXISTS snapshots(snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, docs INTEGER, digest TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS changes(snapshot_id INTEGER, doc_id TEXT, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS fetch_log(at TEXT, url TEXT, outcome TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""
STOP = {'của', 'và', 'các', 'là', 'được', 'cho', 'theo', 'này', 'đối', 'với', 'trong', 'những', 'một', 'khi', 'thì', 'về', 'tại', 'từ',
        'đến', 'hoặc', 'nếu', 'có', 'như', 'đã', 'sẽ', 'do', 'bị', 'để', 'gì', 'nào', 'ạ', 'à', 'thế', 'sao', 'bao', 'nhiêu', 'tôi', 'mình'}


def fold(text: str) -> str:
    t = unicodedata.normalize('NFD', (text or '').replace('đ', 'd').replace('Đ', 'D'))
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn').lower()


def tokens(text: str) -> list[str]:
    return re.findall(r'\w+', unicodedata.normalize('NFC', text or '').lower())


def bigrams(toks: list[str]) -> str:
    return ' '.join(a + b for a, b in zip(toks, toks[1:]))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def polarity_clash(question: str, path: str) -> str | None:
    """The provision's heading negates a phrase the question asks about positively, e.g. the question says "khai sai dẫn
    đến thiếu số thuế" and the article is about "khai sai không dẫn đến thiếu số thuế". Returns the phrase, or None.
    Word overlap and cross-encoders both rate such pairs as close; the penalties differ completely."""
    q = f' {fold(question)} '
    head = fold(path.split(' > ')[-2] if ' > ' in path else path)
    for m in re.finditer(r'\bkhong ((?:[a-z]+ ){2,4}[a-z]+)', head):
        words = m.group(1).split()[:4]
        phrase = ' '.join(words[:3])
        if f' {phrase} ' in q and f' khong {phrase} ' not in q:
            return phrase
    return None


class Corpus:
    hybrid = True                                        # semantic retrieval (bge-m3) fused with keywords; set per instance
    # cross-encoder over the top candidates: on 54 questions it raised first-place hits from 39 to 45 (bge-m3 hybrid alone);
    # (a Vietnamese fine-tuned embedding was measured too and did not beat bge-m3, so it was dropped). Off without the model folder.
    rerank = (Path(__file__).resolve().parents[2] / 'models/Vietnamese_Reranker').exists()

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=60)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA busy_timeout=60000')
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='validity'").fetchone():
            self.db.executescript(SCHEMA + VALIDITY_SCHEMA)
        try:                                                # readers do not block the sync writer; switching needs a lock,
            if self.db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':   # so only switch once
                self.db.execute('PRAGMA journal_mode=WAL')
        except sqlite3.OperationalError:
            pass

    def close(self):
        self.db.close()

    def lastmod(self, doc_url: str):
        r = self.db.execute('SELECT lastmod, doc_id FROM documents WHERE url=?', (doc_url,)).fetchone()
        return (r['lastmod'], r['doc_id']) if r else (None, None)

    def log(self, url, outcome, note=''):
        self.db.execute('INSERT INTO fetch_log VALUES(?,?,?,?)', (now(), url, outcome, note))

    def upsert(self, doc: ParsedDoc, slug: str, lastmod: str, html_sha256: str, core: bool, index: bool) -> list[tuple[str, str]]:
        """Insert or replace one document; returns (kind, detail) changes against the stored version."""
        m, db = doc.meta, self.db
        old = db.execute('SELECT * FROM documents WHERE doc_id=?', (doc.doc_id,)).fetchone()
        old_prov = {r['prov_id']: r['text_sha256'] for r in db.execute('SELECT prov_id, text_sha256 FROM provisions WHERE doc_id=?', (doc.doc_id,))}
        changes = []
        if old is None:
            changes.append(('NEW', f'{m["doc_type"]} {m["doc_num"]}: {m["title"]}'))
        else:
            if (old['status_code'], old['eff_to']) != (m['status_code'], m['eff_to']):
                changes.append(('STATUS', f'{old["status_name"]} -> {m["status_name"]}; hết hiệu lực {old["eff_to"]} -> {m["eff_to"]}'))
        new_prov = {}
        db.execute('DELETE FROM provisions WHERE doc_id=?', (doc.doc_id,))
        for p in doc.provisions:
            h = hashlib.sha256(p.text.encode()).hexdigest()
            new_prov[p.prov_id] = h
            db.execute('INSERT OR REPLACE INTO provisions VALUES(?,?,?,?,?,?,?,?,?)',
                       (doc.doc_id, p.prov_id, p.level, p.label, p.heading, p.text, p.parent, p.order, h))
        if old is not None:
            edited = [k for k in new_prov if k in old_prov and old_prov[k] != new_prov[k]]
            added, removed = set(new_prov) - set(old_prov), set(old_prov) - set(new_prov)
            if edited or added or removed:
                changes.append(('TEXT', f'{len(edited)} đoạn đổi, {len(added)} thêm, {len(removed)} bỏ'))
        db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id=?)', (doc.doc_id,))
        db.execute('DELETE FROM chunks WHERE doc_id=?', (doc.doc_id,))
        cs = chunks(doc) if index else []
        for c in cs:
            toks = tokens(c['text'])
            db.execute('INSERT INTO chunks VALUES(?,?,?,?,?)', (c['chunk_id'], c['doc_id'], c['prov_id'], c['path'], c['text']))
            db.execute('INSERT INTO chunks_fts VALUES(?,?,?,?,?)', (c['chunk_id'], c['path'], c['text'], fold(c['text']), bigrams(toks)))
        db.execute('INSERT OR REPLACE INTO documents(doc_id,url,slug,lastmod,doc_num,title,doc_type,doc_type_code,issue_date,eff_from,eff_to,'
                   'status_code,status_name,structure,notes,n_provisions,n_chunks,html_sha256,fetched_at,core,indexed,review_status) '
                   'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,COALESCE((SELECT review_status FROM documents WHERE doc_id=?),"UNREVIEWED"))',
                   (doc.doc_id, doc.url, slug, lastmod, m['doc_num'], m['title'], m['doc_type'], m['doc_type_code'], m['issue_date'],
                    m['eff_from'], m['eff_to'], m['status_code'], m['status_name'], doc.structure, json.dumps(doc.notes, ensure_ascii=False),
                    len(doc.provisions), len(cs), html_sha256, now(), int(core), int(index), doc.doc_id))
        if changes and old is not None and old['review_status'] == 'REVIEWED':
            db.execute('UPDATE documents SET review_status="NEEDS_REREVIEW" WHERE doc_id=?', (doc.doc_id,))
        return changes

    def snapshot(self, changes: list[tuple[str, str, str]], summary: dict) -> int:
        rows = self.db.execute('SELECT doc_id, html_sha256 FROM documents ORDER BY doc_id').fetchall()
        digest = hashlib.sha256('\n'.join(f'{r[0]}:{r[1]}' for r in rows).encode()).hexdigest()
        cur = self.db.execute('INSERT INTO snapshots(created_at, docs, digest, summary) VALUES(?,?,?,?)',
                              (now(), len(rows), digest, json.dumps(summary, ensure_ascii=False)))
        sid = cur.lastrowid
        self.db.executemany('INSERT INTO changes VALUES(?,?,?,?)', [(sid, d, k, t) for d, k, t in changes])
        self.db.commit()
        return sid

    # ------------------------------------------------------------------ retrieval
    TYPE_BOOST = {'Văn bản hợp nhất': 1.25, 'Luật': 1.15, 'Nghị quyết': 1.05, 'Nghị định': 1.1, 'Thông tư': 1.0, 'Thông tư liên tịch': 0.95}

    def search(self, query: str, as_of: date | None = None, k: int = 8, doc_ids: list[str] | None = None) -> list[dict]:
        toks = [t for t in tokens(query) if t not in STOP]
        if not toks:
            return []
        folded = [fold(t) for t in toks]
        terms = sorted(set(toks) | set(folded) | set(bigrams(toks).split()))
        match = ' OR '.join('"' + t.replace('"', '') + '"' for t in terms)
        sql = ('SELECT c.chunk_id, c.doc_id, c.prov_id, c.path, c.text, d.doc_num, d.title, d.doc_type, d.eff_from, d.eff_to, d.status_name, '
               'd.review_status, d.issue_date, v.eff_to AS ended_on, v.by_doc_num AS ended_by, '
               'bm25(chunks_fts, 0, 2.0, 1.0, 0.6, 1.6) AS score FROM chunks_fts JOIN chunks c USING(chunk_id) '
               'JOIN documents d ON d.doc_id=c.doc_id LEFT JOIN validity v ON v.doc_id=d.doc_id '
               'LEFT JOIN stale_provisions s ON s.doc_id=c.doc_id AND s.prov_id=c.prov_id WHERE chunks_fts MATCH ?')
        args = [match]
        if as_of:
            # A document without an effective date (typically a consolidated text) counts from its issue date.
            # An end date read from a replacing act (table validity) counts as much as the one the source site gives.
            sql += (" AND COALESCE(d.eff_from, d.issue_date, '0000') <= ? AND (d.eff_to IS NULL OR d.eff_to > ?)"
                    " AND (v.eff_to IS NULL OR v.eff_to > ?) AND (s.ended_on IS NULL OR s.ended_on > ?)")
            args += [as_of.isoformat()] * 4
        if doc_ids:
            sql += f' AND c.doc_id IN ({",".join("?" * len(doc_ids))})'
            args += doc_ids
        filters_sql, filters_args = sql.split('WHERE chunks_fts MATCH ?', 1)[1], args[1:]
        sql += ' ORDER BY score LIMIT 200'
        rows = [dict(r) for r in self.db.execute(sql, args)]
        dense = {}
        if self.hybrid:
            from .dense import nearest
            dense = dict(nearest(self.db, query, 60))
            missing = [cid for cid in dense if cid not in {r['chunk_id'] for r in rows}]
            if missing:                                   # semantic candidates the keyword index missed, same date filters
                extra = ('SELECT c.chunk_id, c.doc_id, c.prov_id, c.path, c.text, d.doc_num, d.title, d.doc_type, d.eff_from, d.eff_to, d.status_name, '
                         'd.review_status, d.issue_date, v.eff_to AS ended_on, v.by_doc_num AS ended_by, 0.0 AS score FROM chunks c '
                         'JOIN documents d ON d.doc_id=c.doc_id LEFT JOIN validity v ON v.doc_id=d.doc_id '
                         'LEFT JOIN stale_provisions s ON s.doc_id=c.doc_id AND s.prov_id=c.prov_id '
                         f'WHERE c.chunk_id IN ({",".join("?" * len(missing))}) AND d.indexed=1' + filters_sql)
                rows += [dict(r) for r in self.db.execute(extra, missing + filters_args)]
        for r in rows:                                   # bm25 is negative: more negative is better
            r['rank'] = -r['score'] * self.TYPE_BOOST.get(r['doc_type'], 0.9)
            if as_of and r['status_name'] and 'Hết hiệu lực toàn bộ' in r['status_name'] and not r['eff_to']:
                r['rank'] *= 0.3                         # expired with unknown end date: keep but push down
        q_uni, q_bi = set(toks), set(bigrams(toks).split())
        for r in rows:                                   # rerank: how much of the question the chunk actually covers
            ct = tokens(r['path'] + ' ' + r['text'])
            c_uni, c_bi = set(ct), set(bigrams(ct).split())
            r['coverage'] = (len(q_uni & c_uni) / len(q_uni) + 2 * (len(q_bi & c_bi) / len(q_bi) if q_bi else 0)) / 3
        top = max((r['rank'] for r in rows), default=1) or 1
        if dense:
            lo, hi = min(dense.values()), max(dense.values())
            for r in rows:                               # weights fixed before measuring, not tuned on the held-out set
                d = (dense[r['chunk_id']] - lo) / (hi - lo) if r['chunk_id'] in dense and hi > lo else 0.0
                r['rank'] = 0.25 * r['rank'] / top + 0.35 * d + 0.4 * r['coverage']
        else:
            for r in rows:
                r['rank'] = 0.4 * r['rank'] / top + 0.6 * r['coverage']
        rows.sort(key=lambda r: -r['rank'])
        if self.rerank and rows:
            from .dense import rerank_scores
            head = rows[:30]
            try:
                sc = rerank_scores(query, [f"{r['path']}\n{r['text']}"[:1500] for r in head])
                lo, hi = min(sc), max(sc)
                for r, s in zip(head, sc):               # date and type logic stay; the cross-encoder decides most of the order
                    r['rank'] = 0.7 * ((s - lo) / (hi - lo) if hi > lo else 0) + 0.3 * r['rank']
                    if polarity_clash(query, r['path']):   # cross-encoders miss negation ("không dẫn đến thiếu thuế")
                        r['rank'] *= 0.3
                rows = sorted(head, key=lambda r: -r['rank']) + rows[30:]
            except Exception:  # noqa: BLE001 - the reranker is optional
                pass
        out, seen, versions = [], set(), {}
        for r in rows:                                   # one entry per clause: split pieces of the same unit are merged later
            key = (r['doc_id'], r['prov_id'])
            if key in seen:
                continue
            seen.add(key)
            # The same provision is often present in the original act and in one or more consolidated texts:
            # keep one entry, from the most recently issued document, at the best rank of the group.
            tail = r['path'].split(' > ', 1)[-1]
            tail = re.sub(r'^(?:Chương|CHƯƠNG|Mục)[^>]*> ', '', tail)
            vkey = (re.sub(r'.*?(Điều \d+[a-zđ]?)', r'', tail, count=1), fold(r['text'][:160]))
            if vkey in versions:
                kept = versions[vkey]
                if (r['issue_date'] or '') > (kept['issue_date'] or ''):
                    r['rank'] = kept['rank']
                    out[out.index(kept)] = r
                    versions[vkey] = r
                continue
            versions[vkey] = r
            out.append(r)
        return out[:k]

    def unit_text(self, doc_id: str, prov_id: str) -> str:
        """All pieces of one clause in order, joined: what the model reads for that clause."""
        rows = self.db.execute('SELECT chunk_id, text FROM chunks WHERE doc_id=? AND prov_id=?', (doc_id, prov_id)).fetchall()
        return ' '.join(r[1] for r in sorted(rows, key=lambda r: int(r[0].rsplit(':', 1)[1])))

    def stats(self) -> dict:
        q = lambda s: self.db.execute(s).fetchone()[0]  # noqa: E731
        return dict(documents=q('SELECT COUNT(*) FROM documents'), indexed=q('SELECT COUNT(*) FROM documents WHERE indexed=1'),
                    provisions=q('SELECT COUNT(*) FROM provisions'), chunks=q('SELECT COUNT(*) FROM chunks'),
                    in_force=q("SELECT COUNT(*) FROM documents d LEFT JOIN validity v USING(doc_id) WHERE d.indexed=1 AND d.status_name LIKE 'Còn hiệu lực%' "
                              "AND v.eff_to IS NULL AND (d.eff_to IS NULL OR d.eff_to > date('now'))"),
                    with_issues=q("SELECT COUNT(*) FROM documents WHERE notes != '[]'"),
                    ended_by_later_act=q('SELECT COUNT(*) FROM validity'),
                    last_snapshot=dict(self.db.execute('SELECT * FROM snapshots ORDER BY snapshot_id DESC LIMIT 1').fetchone() or {}))
