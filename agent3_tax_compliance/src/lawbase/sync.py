"""One command to bring the legal corpus up to date: discover, fetch new or changed pages, parse, check, store, snapshot."""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .fetch import FetchError, PoliteFetcher
from .store import Corpus
from .check_refs import check as check_ruleset
from .validity import derive
from .vbpl import in_scope, parse_page, parse_sitemap, slug, slug_year

PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_SCOPE = PROJECT / 'configs/lawbase/scope.json'
DEFAULT_DB = PROJECT / 'data/lawbase/legal_corpus.sqlite3'
DEFAULT_CACHE = PROJECT / 'data/lawbase/cache'
DEFAULT_RULESET = PROJECT / 'configs/assistant/ruleset_2026_11_draft.json'


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
    validity: dict = field(default_factory=dict)
    ruleset_broken: list = field(default_factory=list)


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


LOCK_STALE_SECONDS = 15 * 60


def lock_path(db_path: Path) -> Path:
    return Path(db_path).with_suffix('.sync.lock')


def running_sync(db_path: Path = DEFAULT_DB) -> dict | None:
    """The sync in progress, from any process, or None. A lock not touched for 15 minutes is treated as abandoned."""
    p = lock_path(db_path)
    try:
        info = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return info if time.time() - p.stat().st_mtime < LOCK_STALE_SECONDS else None


def index_decision(meta: dict, core: bool, scope: dict) -> tuple[bool, str]:
    """Whether a stored document is searchable. Everything fetched is kept for audit; only the searchable set is limited."""
    if core:
        return True, ''
    if meta.get('eff_to') and meta['eff_to'] < scope['keep_expired_after']:
        return False, f'hết hiệu lực từ {meta["eff_to"]}, trước mốc {scope["keep_expired_after"]}'
    year = int((meta.get('issue_date') or '0000')[:4] or 0)
    if year and year < scope['min_year']:
        # The status field is unreliable for old texts, so only an act of the National Assembly still marked in force is kept.
        if (meta.get('doc_type') or '').startswith('Luật') and (meta.get('status_name') or '').startswith('Còn hiệu lực'):
            return True, ''
        return False, f'ban hành năm {year}, trước năm {scope["min_year"]}'
    return True, ''


def sync(scope_path: Path = DEFAULT_SCOPE, db_path: Path = DEFAULT_DB, cache_dir: Path = DEFAULT_CACHE, limit: int | None = None,
         core_only: bool = False, fetcher: PoliteFetcher | None = None, progress=None, reparse: bool = False) -> SyncReport:
    scope = json.loads(Path(scope_path).read_text(encoding='utf-8'))
    src = scope['source']
    fetcher = fetcher or PoliteFetcher(src['user_agent'], src['min_interval_seconds'], cache_dir)
    lock = lock_path(db_path)
    if running_sync(db_path):
        raise RuntimeError(f'một lần đồng bộ khác đang chạy ({lock})')
    corpus = Corpus(db_path)
    rep = SyncReport()
    lock.write_text(json.dumps(dict(pid=os.getpid(), started=time.time(), done=0)), encoding='utf-8')
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
            searchable, why = index_decision(doc.meta, core, scope)
            if why:
                doc.notes.append(f'không đưa vào tìm kiếm: {why}')
            changes = corpus.upsert(doc, slug(loc), mod, hashlib.sha256(raw).hexdigest(), core, index=searchable)
            corpus.log(loc, 'OK', f'{len(doc.provisions)} điều khoản')
            rep.fetched += 1
            done += 1
            if doc.notes:
                rep.quality.append(dict(doc=doc.meta['doc_num'], notes=doc.notes, structure=doc.structure))
            rep.changes += [(doc.doc_id, k, t) for k, t in changes]
            if progress:
                progress(done, doc.meta)
            lock.write_text(json.dumps(dict(pid=os.getpid(), started=time.time(), done=done, last=doc.meta.get('doc_num'))), encoding='utf-8')
            if done % 20 == 0:
                corpus.db.commit()
        corpus.db.commit()
        rep.validity = derive(corpus.db)
        rep.changes += [(doc_id, 'VALIDITY', f'hết hiệu lực theo văn bản thay thế: {old or "chưa có"} -> {new or "bỏ"}')
                        for doc_id, old, new in rep.validity['changed']]
        corpus.db.commit()
        if DEFAULT_RULESET.exists():                    # a law change that breaks a rule's basis must be visible at once
            rep.ruleset_broken = [r for r in check_ruleset(DEFAULT_RULESET, db_path) if r['ok'] is False]
            rep.changes += [(None, 'RULESET_REF_BROKEN', f'{r["parameter"]} {r["ref"]} tại {r.get("day")}: {r["detail"]}') for r in rep.ruleset_broken]
        rep.snapshot_id = corpus.snapshot(rep.changes, dict(fetched=rep.fetched, unchanged=rep.unchanged, failed=len(rep.failed),
                                                            ended_by_later_act=rep.validity['ended']))
        return rep
    finally:
        corpus.close()
        lock.unlink(missing_ok=True)
