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

# Cross-encoder reranker (AITeamVN/Vietnamese_Reranker, local copy in models/); optional, off when the folder is missing.
from pathlib import Path as _Path  # noqa: E402
RERANK_DIR = _Path(__file__).resolve().parents[2] / 'models/Vietnamese_Reranker'
_st = {}


def rerank_scores(query: str, texts: list[str]) -> list[float]:
    """Cross-encoder relevance (AITeamVN/Vietnamese_Reranker, a fine-tune of bge-reranker-v2-m3).

    The model waits in main memory and borrows the GPU only while scoring (about 1 GB, under a second), then gives it
    back: kept resident it pushed the answering model (qwen3:8b, same 6 GB card) half onto the CPU and answers took
    two to three times longer."""
    import torch
    if 'rr' not in _st:
        from sentence_transformers import CrossEncoder
        _st['rr'] = CrossEncoder(str(RERANK_DIR), device='cpu', max_length=512)
        _st['rr'].model.half()
    m = _st['rr']
    pairs = [(query, t) for t in texts]
    if not torch.cuda.is_available():
        m.model.float()
        return [float(x) for x in m.predict(pairs, batch_size=16, show_progress_bar=False)]
    try:
        m.model.to('cuda')
        m._target_device = torch.device('cuda')
        out = m.predict(pairs, batch_size=16, show_progress_bar=False)
    finally:
        m.model.to('cpu')
        m._target_device = torch.device('cpu')
        torch.cuda.empty_cache()
    return [float(x) for x in out]


def embed(texts: list[str], timeout: int = 300) -> np.ndarray:
    if len(texts) > 64:                                   # the server rejects very large batches
        return np.vstack([embed(texts[k:k + 64], timeout) for k in range(0, len(texts), 64)])
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
    _cache.pop('chunk_vec', None)
    return len(todo)


def _matrix(db, table='chunk_vec'):
    """All vectors in memory once per process (27k x 1024 floats, about 110 MB)."""
    n = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() else 0
    if not n:
        return None, None
    c = _cache.setdefault(table, {})
    if c.get('n') != n:
        rows = db.execute(f'SELECT chunk_id, vec FROM {table}').fetchall()
        c.update(n=n, ids=[r[0] for r in rows], mat=np.frombuffer(b''.join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1))
    return c['ids'], c['mat']


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
