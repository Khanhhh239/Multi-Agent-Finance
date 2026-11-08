"""Shared catalogs in configs/assistant/catalog: lists every enterprise uses and an administrator may extend from the
protected settings page, never by editing code.

  policy_presets   internal spending policies offered when an enterprise is set up
  ai_categories    item groups the line classifier chooses from
  holidays         public days off that move a tax deadline
  law_topics       topics that make a new legal document relevant to a small or medium enterprise
  chat_domains     the answer domains of the question assistant (router, help page and evaluation read it)

Each save is validated, gets a new version stamp and is recorded in data/catalog_history.json (who, when, what changed).
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DIR = PROJECT / 'configs/assistant/catalog'
HISTORY = PROJECT / 'data/catalog_history.json'
NAMES = ('policy_presets', 'ai_categories', 'holidays', 'law_topics', 'chat_domains')
ID = re.compile(r'^[A-Z][A-Z0-9_]{1,40}$')
_cache = {}


class CatalogError(ValueError):
    pass


def path(name: str) -> Path:
    if name not in NAMES:
        raise CatalogError(f'không có danh mục {name}')
    return DIR / f'{name}.json'


def load(name: str) -> dict:
    p = path(name)
    mtime = p.stat().st_mtime
    hit = _cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text(encoding='utf-8'))
    _cache[name] = (mtime, data)
    return data


# ----------------------------------------------------------------------------- validation
def _text(v, what, maxlen=400):
    if not isinstance(v, str) or not v.strip() or len(v) > maxlen:
        raise CatalogError(f'{what}: cần chữ, không rỗng, tối đa {maxlen} ký tự')
    return v.strip()


def _validate_policy_presets(d):
    seen = set()
    out = []
    for p in d.get('presets', []):
        pid = _text(p.get('id'), 'mã quy định', 40).upper()
        if not ID.match(pid) or pid in seen:
            raise CatalogError(f'mã quy định {pid} không hợp lệ hoặc bị trùng (chữ in hoa, số, gạch dưới)')
        seen.add(pid)
        q = dict(id=pid, flag=_text(p.get('flag'), f'nội dung nhắc của {pid}'), group=(p.get('group') or 'Chung').strip()[:60],
                 recommended=bool(p.get('recommended')))
        q['for'] = sorted({str(x).strip()[:2] for x in p.get('for', []) if re.match(r'^\d{2}', str(x).strip())})
        if p.get('min_gross') not in (None, ''):
            q['min_gross'] = int(p['min_gross'])
            if q['min_gross'] < 0:
                raise CatalogError(f'số tiền của {pid} phải không âm')
        words = [w.strip() for w in p.get('description_contains', []) if str(w).strip()]
        if words:
            q['description_contains'] = words[:30]
        out.append(q)
    return dict(d, presets=out)


def _validate_ai_categories(d):
    system = set(d.get('system', ['CA_NHAN', 'KHONG_RO']))
    seen, out = set(), []
    for c in d.get('categories', []):
        cid = _text(c.get('id'), 'mã nhóm', 40).upper()
        if not ID.match(cid) or cid in seen or cid.startswith('RIENG_'):
            raise CatalogError(f'mã nhóm {cid} không hợp lệ, bị trùng, hoặc dùng tiền tố RIENG_ dành cho nhóm riêng của doanh nghiệp')
        seen.add(cid)
        out.append(dict(id=cid, description=_text(c.get('description'), f'mô tả nhóm {cid}', 300)))
    missing = system - seen
    if missing:
        raise CatalogError(f'không được xóa nhóm hệ thống: {", ".join(sorted(missing))}')
    return dict(d, categories=out)


def _validate_holidays(d):
    fixed = []
    for f in d.get('fixed', []):
        m, dd = int(f['month']), int(f['day'])
        date(2000, m, dd)
        fixed.append(dict(month=m, day=dd, name=_text(f.get('name'), 'tên ngày lễ', 80)))
    years = {}
    for y, rows in (d.get('years') or {}).items():
        if not re.match(r'^20\d{2}$', str(y)):
            raise CatalogError(f'năm {y} không hợp lệ')
        out = []
        for r in rows:
            day = date.fromisoformat(str(r['date']))
            if str(day.year) != str(y):
                raise CatalogError(f'ngày {day} không thuộc năm {y}')
            out.append(dict(date=day.isoformat(), name=_text(r.get('name'), 'tên ngày nghỉ', 120), verified=bool(r.get('verified', True))))
        years[str(y)] = sorted(out, key=lambda r: r['date'])
    return dict(d, fixed=fixed, years=years)


def _validate_law_topics(d):
    topics = [_text(t, 'chủ đề', 200) for t in d.get('topics', []) if str(t).strip()]
    if not topics:
        raise CatalogError('cần ít nhất một chủ đề')
    return dict(d, topics=topics, keywords=[str(w).strip() for w in d.get('keywords', []) if str(w).strip()],
                noise=[str(w).strip() for w in d.get('noise', []) if str(w).strip()])


def _validate_chat_domains(d):
    from .chat.handlers import HANDLERS
    groups = {g['id'] for g in d.get('groups', [])}
    ids = set()
    for x in d.get('domains', []):
        if x.get('id') not in HANDLERS:
            raise CatalogError(f'miền {x.get("id")} chưa có hàm trả lời; chỉ sửa được câu ví dụ và mô tả của miền đã có')
        if x['id'] in ids:
            raise CatalogError(f'miền {x["id"]} bị trùng')
        ids.add(x['id'])
        if x.get('group') not in groups:
            raise CatalogError(f'nhóm {x.get("group")} của miền {x["id"]} không có')
        _text(x.get('title'), f'tên miền {x["id"]}', 120)
        _text(x.get('what'), f'mô tả miền {x["id"]}', 600)
        x['examples'] = [e.strip() for e in x.get('examples', []) if str(e).strip()]
        if len(x['examples']) < 3:
            raise CatalogError(f'miền {x["id"]} cần ít nhất 3 câu ví dụ')
    missing = set(HANDLERS) - ids
    if missing:
        raise CatalogError(f'thiếu miền: {", ".join(sorted(missing))}')
    return d


VALIDATORS = dict(policy_presets=_validate_policy_presets, ai_categories=_validate_ai_categories, holidays=_validate_holidays,
                  law_topics=_validate_law_topics, chat_domains=_validate_chat_domains)


def save(name: str, data: dict, by: str) -> dict:
    if not by or not str(by).strip():
        raise CatalogError('cần tên người sửa')
    try:
        clean = VALIDATORS[name](json.loads(json.dumps(data)))
    except CatalogError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise CatalogError(f'dữ liệu không hợp lệ: {e}')
    old = load(name)
    clean['version'] = datetime.now().strftime('%Y-%m-%d.%H%M%S')
    path(name).write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding='utf-8')
    hist = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
    hist.append(dict(catalog=name, at=datetime.now().isoformat(timespec='seconds'), by=str(by).strip()[:80], old_version=old.get('version'),
                     new_version=clean['version'], summary=_summary(name, old, clean)))
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(hist[-500:], ensure_ascii=False, indent=1), encoding='utf-8')
    if name == 'chat_domains':
        from .chat import engine
        engine._router = None
    return clean


def _summary(name, old, new):
    key = dict(policy_presets='presets', ai_categories='categories', chat_domains='domains').get(name)
    if key:
        a, b = {x['id'] for x in old.get(key, [])}, {x['id'] for x in new.get(key, [])}
        changed = sorted(x['id'] for x in new.get(key, []) if x['id'] in a and x != next(o for o in old[key] if o['id'] == x['id']))
        return dict(added=sorted(b - a), removed=sorted(a - b), changed=changed)
    if name == 'holidays':
        a = {r['date'] for rows in old.get('years', {}).values() for r in rows}
        b = {r['date'] for rows in new.get('years', {}).values() for r in rows}
        return dict(added=sorted(b - a), removed=sorted(a - b))
    return dict(topics=len(new.get('topics', [])))


def history(name: str | None = None) -> list:
    hist = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
    return [h for h in hist if name is None or h['catalog'] == name][::-1]


# ----------------------------------------------------------------------------- readers used by the pipeline
def days_off() -> set:
    """(month, day) of fixed holidays and the dated days off of every year in the catalog."""
    h = load('holidays')
    fixed = {(f['month'], f['day']) for f in h.get('fixed', [])}
    dated = {date.fromisoformat(r['date']) for rows in h.get('years', {}).values() for r in rows}
    return fixed, dated


def policy_presets() -> list:
    return load('policy_presets')['presets']


def ai_categories() -> dict:
    return {c['id']: c['description'] for c in load('ai_categories')['categories']}


def law_alerts(db_path, today: date, days_back: int = 150, days_ahead: int = 180) -> list:
    """Documents that took or lose effect around today and concern a small or medium enterprise. Relevance: the title is
    compared with the topic descriptions by meaning (bge-m3); when the embedding server is down, by the keyword list."""
    from datetime import timedelta
    from ..extraction.xml_context import fold
    from ..lawbase.store import Corpus
    t = load('law_topics')
    lo, hi = (today - timedelta(days=days_back)).isoformat(), (today + timedelta(days=days_ahead)).isoformat()
    c = Corpus(db_path)
    try:
        new = [dict(r, kind='EFFECTIVE') for r in c.db.execute(
            """SELECT d.doc_id, d.doc_type, d.doc_num, d.title, d.eff_from AS day, d.url FROM documents d
               WHERE d.indexed=1 AND d.doc_type IN ('Luật','Nghị định','Thông tư','Nghị quyết') AND d.eff_from BETWEEN ? AND ?
               ORDER BY d.eff_from DESC""", (lo, hi))]
        ended = [dict(r, kind='ENDED') for r in c.db.execute(
            """SELECT d.doc_id, d.doc_type, d.doc_num, d.title, v.eff_to AS day, d.url, v.by_doc_num FROM validity v JOIN documents d USING(doc_id)
               WHERE v.eff_to BETWEEN ? AND ? AND d.doc_type NOT LIKE 'Văn bản hợp nhất%' ORDER BY v.eff_to DESC""", (lo, hi))]
    finally:
        c.close()
    rows = [r for r in new + ended if not any(w in fold(r['title']) for w in t.get('noise', []))]
    if not rows:
        return []
    try:
        from ..lawbase.dense import embed
        tv = embed(t['topics'])
        dv = embed([r['title'][:500] for r in rows])
        sims = (dv @ tv.T).max(axis=1)
        for r, s in zip(rows, sims):
            r['relevance'] = round(float(s), 3)
            r['method'] = 'meaning'
        rows = [r for r in rows if r['relevance'] >= 0.55]
    except Exception:  # noqa: BLE001 - keyword fallback, said in the row
        for r in rows:
            r['relevance'] = sum(w in fold(r['title']) for w in t.get('keywords', []))
            r['method'] = 'keywords'
        rows = [r for r in rows if r['relevance'] > 0]
    return sorted(rows, key=lambda r: (-r['relevance'], r['day']))
