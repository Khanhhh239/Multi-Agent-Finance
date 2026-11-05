"""One command to bring the legal corpus up to date: discover, fetch new or changed pages, parse, check, store, snapshot."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .fetch import FetchError, PoliteFetcher
from .store import Corpus
from .vbpl import in_scope, parse_page, parse_sitemap, slug, slug_year

PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_SCOPE = PROJECT / 'configs/lawbase/scope.json'
DEFAULT_DB = PROJECT / 'data/lawbase/legal_corpus.sqlite3'
DEFAULT_CACHE = PROJECT / 'data/lawbase/cache'


@dataclass
class SyncReport:
    discovered: int = 0
    selected: int = 0
    fetched: int = 0
    unchanged: int = 0
    failed: list = field(default_factory=list)
    quality: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    snapshot_id: int | None = None


def discover(fetcher: PoliteFetcher, scope: dict) -> list[tuple[str, str, bool]]:
    today = date.today().isoformat()
    found = []
    for shard in scope['source']['central_shards']:
        url = f'{scope["source"]["base"]}/sitemap/{shard}.xml'
        found += parse_sitemap(fetcher.get(url, cache_key=f'{url}@{today}'))
    out = []
    for loc, mod in found:
        ok, core = in_scope(loc, scope)
        if ok:
            out.append((loc, mod, core))
    out.sort(key=lambda x: (not x[2], -(slug_year(slug(x[0])) or 0), x[0]))
    return out, len(found)


def sync(scope_path: Path = DEFAULT_SCOPE, db_path: Path = DEFAULT_DB, cache_dir: Path = DEFAULT_CACHE, limit: int | None = None,
         core_only: bool = False, fetcher: PoliteFetcher | None = None, progress=None, reparse: bool = False) -> SyncReport:
    scope = json.loads(Path(scope_path).read_text(encoding='utf-8'))
    src = scope['source']
    fetcher = fetcher or PoliteFetcher(src['user_agent'], src['min_interval_seconds'], cache_dir)
    corpus = Corpus(db_path)
    rep = SyncReport()
    try:
        targets, rep.discovered = discover(fetcher, scope)
        if core_only:
            targets = [t for t in targets if t[2]]
        rep.selected = len(targets)
        done = 0
        for loc, mod, core in targets:
            if limit is not None and done >= limit:
                break
            stored_mod, _ = corpus.lastmod(loc)
            if stored_mod and stored_mod == mod and not reparse:
                rep.unchanged += 1
                continue
            try:
                raw = fetcher.get(loc, cache_key=f'{loc}@{mod}')
                doc = parse_page(loc, raw.decode('utf-8', 'replace'))
            except (FetchError, ValueError) as e:
                rep.failed.append(dict(url=loc, error=str(e)[:200]))
                corpus.log(loc, 'FAILED', str(e)[:200])
                continue
            expired_old = bool(doc.meta['eff_to'] and doc.meta['eff_to'] < scope['keep_expired_after'])
            changes = corpus.upsert(doc, slug(loc), mod, hashlib.sha256(raw).hexdigest(), core, index=not expired_old)
            corpus.log(loc, 'OK', f'{len(doc.provisions)} điều khoản')
            rep.fetched += 1
            done += 1
            if doc.notes:
                rep.quality.append(dict(doc=doc.meta['doc_num'], notes=doc.notes, structure=doc.structure))
            rep.changes += [(doc.doc_id, k, t) for k, t in changes]
            if progress:
                progress(done, doc.meta)
            if done % 20 == 0:
                corpus.db.commit()
        rep.snapshot_id = corpus.snapshot(rep.changes, dict(fetched=rep.fetched, unchanged=rep.unchanged, failed=len(rep.failed)))
        return rep
    finally:
        corpus.close()
