"""Semantic retrieval through an authenticated OpenAI-compatible embedding API.

Vectors are stored next to the chunks; search filters on the same validity dates
as the keyword search and is fused with it in ``store.search``.

  python -m src.lawbase.dense build      embed every indexed chunk that has no vector yet (resumable)

The model and dimension that produced the stored vectors are kept in ``chunk_vec_meta``. When the configured
embedding model changes (for example a corpus built with bge-m3, 1024 dimensions, served with a 4096-dimension
API model), search skips the semantic part instead of failing, and ``build`` discards the old vectors and
embeds the corpus again with the current model.
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request

import numpy as np

from ..runtime_config import env
from .llm import USER_AGENT

MODEL = env('AGENT3_EMBED_MODEL', 'nvidia/nemotron-3.5-embed-8b:free')
URL = env('AGENT3_EMBED_BASE_URL', 'https://openrouter.ai/api/v1')
SCHEMA = 'CREATE TABLE IF NOT EXISTS chunk_vec(chunk_id TEXT PRIMARY KEY, vec BLOB)'
META_SCHEMA = 'CREATE TABLE IF NOT EXISTS chunk_vec_meta(key TEXT PRIMARY KEY, value TEXT)'
_cache = {}

def _cohere_rerank_scores(query: str, texts: list[str], timeout: int = 120) -> list[float]:
    key = env('AGENT3_RERANK_API_KEY') or env('AGENT3_API_KEY')
    if not key:
        raise RuntimeError('Chưa cấu hình AGENT3_RERANK_API_KEY cho reranker API.')
    endpoint = env('AGENT3_RERANK_URL', 'https://api.cohere.com/v2/rerank')
    body = dict(model=env('AGENT3_RERANK_MODEL', 'rerank-v3.5'), query=query, documents=texts, top_n=len(texts))
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}', 'User-Agent': USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode('utf-8', 'replace')
        raise RuntimeError(f'Rerank API trả HTTP {exc.code}: {detail[:240]}') from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'Không gọi được rerank API tại {endpoint}: {exc}') from exc
    results = payload.get('results')
    if not isinstance(results, list):
        raise RuntimeError('Rerank API không trả về results hợp lệ.')
    scores = [0.0] * len(texts)
    for row in results:
        index = row.get('index')
        if isinstance(index, int) and 0 <= index < len(scores):
            scores[index] = float(row.get('relevance_score', 0.0))
    return scores


def rerank_scores(query: str, texts: list[str]) -> list[float]:
    """Use the configured API reranker."""
    return _cohere_rerank_scores(query, texts)


def _openai_embed(texts: list[str], timeout: int, base_url: str, model: str, api_key: str) -> np.ndarray:
    endpoint = base_url.rstrip('/')
    if not endpoint.endswith('/embeddings'):
        endpoint += '/embeddings'
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(dict(model=model, input=texts)).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}', 'User-Agent': USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode('utf-8', 'replace')
        raise RuntimeError(f'Embedding API trả HTTP {exc.code}: {detail[:240]}') from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'Không gọi được embedding API tại {base_url}: {exc}') from exc
    rows = payload.get('data')
    if not isinstance(rows, list) or not rows:
        raise RuntimeError('Embedding API không trả về data hợp lệ.')
    rows = sorted(rows, key=lambda row: row.get('index', 0))
    return np.asarray([row['embedding'] for row in rows], dtype=np.float32)


def current_model() -> str:
    return env('AGENT3_EMBED_MODEL', MODEL) or MODEL


def embed(texts: list[str], timeout: int = 300) -> np.ndarray:
    if len(texts) > 64:                                   # the server rejects very large batches
        return np.vstack([embed(texts[k:k + 64], timeout) for k in range(0, len(texts), 64)])
    provider = (env('AGENT3_EMBED_PROVIDER', 'openai') or 'openai').lower()
    model = current_model()
    base_url = env('AGENT3_EMBED_BASE_URL', URL) or URL
    if provider not in ('openai', 'openai-compatible', 'openrouter'):
        raise RuntimeError(f'Nhà cung cấp embedding không được hỗ trợ: {provider}')
    api_key = env('AGENT3_EMBED_API_KEY') or env('AGENT3_API_KEY') or env('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('Chưa cấu hình AGENT3_EMBED_API_KEY cho embedding API.')
    v = _openai_embed(texts, timeout, base_url, model, api_key)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def _meta(db) -> dict:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chunk_vec_meta'").fetchone():
        return {}
    return dict(db.execute('SELECT key, value FROM chunk_vec_meta').fetchall())


def _stored_dim(db) -> int | None:
    """Dimension of the stored vectors: from the metadata, else the most common blob size (corpora built before it)."""
    meta = _meta(db)
    if meta.get('dim'):
        return int(meta['dim'])
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chunk_vec'").fetchone():
        return None
    row = db.execute('SELECT length(vec) AS n, COUNT(*) AS c FROM chunk_vec GROUP BY n ORDER BY c DESC LIMIT 1').fetchone()
    return row[0] // 4 if row else None


def build(db_path, batch: int = 64, progress=print):
    """Embed every indexed chunk without a vector. Vectors from another model or dimension are discarded first."""
    db = sqlite3.connect(db_path, timeout=60)
    try:
        db.execute(SCHEMA)
        db.execute(META_SCHEMA)
        model = current_model()
        meta, old_dim = _meta(db), _stored_dim(db)
        have = db.execute('SELECT COUNT(*) FROM chunk_vec').fetchone()[0]
        todo = db.execute("""SELECT c.chunk_id, c.path, c.text FROM chunks c JOIN documents d USING(doc_id)
                             LEFT JOIN chunk_vec v USING(chunk_id) WHERE d.indexed=1 AND v.chunk_id IS NULL""").fetchall()
        if not todo and (not have or meta.get('model') == model):
            return 0
        dim = embed(['kiểm tra số chiều'], timeout=120).shape[1]
        if have and (meta.get('model') != model or old_dim != dim):
            if progress:
                progress(f'vectơ cũ ({meta.get("model") or "không rõ mô hình"}, {old_dim} chiều) không khớp {model} ({dim} chiều): dựng lại')
            db.execute('DELETE FROM chunk_vec')
            todo = db.execute("""SELECT c.chunk_id, c.path, c.text FROM chunks c JOIN documents d USING(doc_id)
                                 WHERE d.indexed=1""").fetchall()
        db.executemany('INSERT OR REPLACE INTO chunk_vec_meta VALUES(?,?)', [('model', model), ('dim', str(dim))])
        db.commit()
        t0 = time.time()
        for k in range(0, len(todo), batch):
            part = todo[k:k + batch]
            vecs = embed([f'{p}\n{t}'[:2000] for _, p, t in part])
            db.executemany('INSERT OR REPLACE INTO chunk_vec VALUES(?,?)', [(cid, v.tobytes()) for (cid, _, _), v in zip(part, vecs)])
            db.commit()
            if progress and (k // batch) % 20 == 0:
                progress(f'{k + len(part)}/{len(todo)} đoạn, {time.time() - t0:.0f} giây')
        return len(todo)
    finally:
        db.close()
        _cache.pop('chunk_vec', None)


def _matrix(db, table='chunk_vec'):
    """All vectors of the stored dimension in memory once per process (27k x 4096 floats is about 440 MB)."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
        return None, None
    dim = _stored_dim(db)
    n = db.execute(f'SELECT COUNT(*) FROM {table} WHERE length(vec)=?', (dim * 4,)).fetchone()[0] if dim else 0
    if not n:
        return None, None
    c = _cache.setdefault(table, {})
    if (c.get('n'), c.get('dim')) != (n, dim):
        rows = db.execute(f'SELECT chunk_id, vec FROM {table} WHERE length(vec)=?', (dim * 4,)).fetchall()
        c.update(n=n, dim=dim, ids=[r[0] for r in rows],
                 mat=np.frombuffer(b''.join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), dim))
    return c['ids'], c['mat']


def nearest(db, query: str, k: int = 60) -> list[tuple[str, float]]:
    """(chunk_id, cosine) of the k nearest chunks, or [] when no usable vectors exist or the embedding API fails.

    Vectors made by another model are never compared with the query: a different dimension would raise,
    and the same dimension from a different model would give meaningless scores."""
    try:
        meta = _meta(db)
        if meta.get('model') and meta['model'] != current_model():
            return []
        ids, mat = _matrix(db)
        if ids is None:
            return []
        q = embed([query], timeout=60)[0]
        if q.shape[0] != mat.shape[1]:
            return []
        sims = mat @ q
    except Exception:  # noqa: BLE001 - semantic search is optional; keyword search still answers
        return []
    top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
    return sorted(((ids[i], float(sims[i])) for i in top), key=lambda x: -x[1])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    from .sync import DEFAULT_DB
    if sys.argv[1:] == ['build']:
        print('đã thêm', build(DEFAULT_DB), 'vectơ')
