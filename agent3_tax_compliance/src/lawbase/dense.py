"""Semantic retrieval with bge-m3 served by the local Ollama. Vectors are stored next to the chunks; search filters on the
same validity dates as the keyword search and is fused with it in store.search (hybrid).

  python -m src.lawbase.dense build      embed every indexed chunk that has no vector yet (resumable)
"""
import json
import sqlite3
import sys
import time
import urllib.request

import numpy as np

MODEL = 'bge-m3'
URL = 'http://127.0.0.1:11434/api/embed'
SCHEMA = 'CREATE TABLE IF NOT EXISTS chunk_vec(chunk_id TEXT PRIMARY KEY, vec BLOB)'
_cache = {}


def embed(texts: list[str], timeout: int = 300) -> np.ndarray:
    req = urllib.request.Request(URL, data=json.dumps(dict(model=MODEL, input=texts)).encode(), headers={'Content-Type': 'application/json'})
    out = json.loads(urllib.request.urlopen(req, timeout=timeout).read())['embeddings']
    v = np.asarray(out, dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def build(db_path, batch: int = 32, progress=print):
    db = sqlite3.connect(db_path, timeout=60)
    db.execute(SCHEMA)
    todo = db.execute("""SELECT c.chunk_id, c.path, c.text FROM chunks c JOIN documents d USING(doc_id)
                         LEFT JOIN chunk_vec v USING(chunk_id) WHERE d.indexed=1 AND v.chunk_id IS NULL""").fetchall()
    t0 = time.time()
    for k in range(0, len(todo), batch):
        part = todo[k:k + batch]
        vecs = embed([f'{p}\n{t}'[:2000] for _, p, t in part])
        db.executemany('INSERT OR REPLACE INTO chunk_vec VALUES(?,?)', [(cid, v.tobytes()) for (cid, _, _), v in zip(part, vecs)])
        db.commit()
        if progress and (k // batch) % 20 == 0:
            progress(f'{k + len(part)}/{len(todo)} đoạn, {time.time() - t0:.0f} giây')
    db.close()
    _cache.clear()
    return len(todo)


def _matrix(db):
    """All vectors in memory once per process (27k x 1024 floats, about 110 MB)."""
    n = db.execute('SELECT COUNT(*) FROM chunk_vec').fetchone()[0] if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='chunk_vec'").fetchone() else 0
    if not n:
        return None, None
    if _cache.get('n') != n:
        rows = db.execute('SELECT chunk_id, vec FROM chunk_vec').fetchall()
        _cache.update(n=n, ids=[r[0] for r in rows], mat=np.frombuffer(b''.join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1))
    return _cache['ids'], _cache['mat']


def nearest(db, query: str, k: int = 60) -> list[tuple[str, float]]:
    """(chunk_id, cosine) of the k nearest chunks, or [] when no vectors are built or the model is not running."""
    ids, mat = _matrix(db)
    if ids is None:
        return []
    try:
        q = embed([query], timeout=60)[0]
    except Exception:  # noqa: BLE001 - semantic search is optional; keyword search still answers
        return []
    sims = mat @ q
    top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
    return sorted(((ids[i], float(sims[i])) for i in top), key=lambda x: -x[1])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    from .sync import DEFAULT_DB
    if sys.argv[1:] == ['build']:
        print('đã thêm', build(DEFAULT_DB), 'vectơ')
