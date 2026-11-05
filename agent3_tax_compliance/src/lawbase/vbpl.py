"""vbpl.vn adapter: discover documents from the sitemap, parse metadata and the provision tree from a document page.

A document page is server-rendered (Next.js). Its flight payload carries the document record (number, type, issue date,
effective from and to, validity status) and the full text as HTML where every paragraph has a stable id and a class:
prov-chapter, prov-section, prov-article, prov-clause, prov-item, prov-content. Only pages allowed by robots.txt are read.
"""
import html as htmllib
import json
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree

LEVEL = {'prov-chapter': 1, 'prov-section': 2, 'prov-article': 3, 'prov-clause': 4, 'prov-item': 5}
SM = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


@dataclass
class Provision:
    prov_id: str
    level: int            # 1 chapter, 2 section, 3 article, 4 clause, 5 point
    label: str            # "Chương II", "Điều 16", "Khoản 2", "Điểm a"
    heading: str
    text: str             # own text plus following content paragraphs
    parent: str | None
    order: int


@dataclass
class ParsedDoc:
    doc_id: str
    url: str
    meta: dict
    provisions: list[Provision] = field(default_factory=list)
    structure: str = 'marked'      # marked | heuristic | none
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- discovery
def parse_sitemap(xml_bytes: bytes) -> list[tuple[str, str]]:
    root = ElementTree.fromstring(xml_bytes)
    out = []
    for url in root.iter(f'{SM}url'):
        loc, mod = url.findtext(f'{SM}loc'), url.findtext(f'{SM}lastmod') or ''
        if loc and '/van-ban/chi-tiet/' in loc and '/en/' not in loc:
            out.append((loc.strip(), mod.strip()))
    return out


def slug(url: str) -> str:
    return url.rsplit('/chi-tiet/', 1)[-1]


def slug_year(s: str) -> int | None:
    years = [int(y) for y in re.findall(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', s)]
    return years[0] if years else None


def in_scope(url: str, scope: dict) -> tuple[bool, bool]:
    """(selected, is_core)."""
    s = slug(url)
    core = any(c in s for c in scope['core_slug_contains'])
    if core:
        return True, True
    if not any(k in s for k in scope['include_slug_any']) or any(k in s for k in scope['exclude_slug_any']):
        return False, False
    if not any(s.startswith(t) for t in scope['include_types']):
        return False, False
    y = slug_year(s)
    if s.startswith('luat') or s.startswith('van-ban-hop-nhat'):
        return True, False
    return (y is None or y >= scope['min_year']), False


# ----------------------------------------------------------------------------- page parsing
def flight_text(page_html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page_html, flags=re.S)
    out = []
    for c in chunks:
        try:
            out.append(json.loads('"' + c + '"'))
        except json.JSONDecodeError:
            continue
    return ''.join(out)


def _json_object_at(text: str, start: int):
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == '\\' and not esc)
            if ch == '"' and not esc:
                in_str = False
            elif ch != '\\':
                esc = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError('unterminated object')


def parse_meta(flight: str) -> dict:
    i = flight.find('"initialDoc":{')
    if i < 0:
        raise ValueError('document record not found')
    doc = _json_object_at(flight, i + len('"initialDoc":'))
    status = doc.get('effStatus') or {}
    dtype = doc.get('docType') or {}
    day = lambda v: v[:10] if v else None  # noqa: E731
    return dict(doc_id=str(doc.get('id')), doc_num=doc.get('docNum'), title=doc.get('title'), doc_type=dtype.get('name'),
                doc_type_code=dtype.get('code'), doc_group=doc.get('docGroup'), issue_date=day(doc.get('issueDate')),
                eff_from=day(doc.get('effFrom')), eff_to=day(doc.get('effTo')), status_name=status.get('name'),
                status_code=status.get('code'), file_name=doc.get('documentContentFileName'))


def _clean(fragment: str) -> str:
    t = re.sub(r'<br\s*/?>', ' ', fragment)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', htmllib.unescape(t)).strip()


ARTICLE = re.compile(r'^(Điều\s+(\d+[a-zđ]?))\s*[.:]?\s*(.*)$', re.I)
CHAPTER = re.compile(r'^(Chương\s+[IVXLCDM\d]+)\s*[.:]?\s*(.*)$', re.I)
SECTION = re.compile(r'^(Mục\s+\d+)\s*[.:]?\s*(.*)$', re.I)
CLAUSE = re.compile(r'^(\d+[a-zđ]?)\s*[.)]\s*(.*)$')
ITEM = re.compile(r'^([a-zđ]{1,2}\d?)\s*\)\s*(.*)$')


def _label(level: int, text: str) -> tuple[str, str]:
    for lv, rx, fmt in ((1, CHAPTER, None), (2, SECTION, None), (3, ARTICLE, None)):
        if level == lv:
            m = rx.match(text)
            if m:
                return m.group(1), m.groups()[-1]
            return text[:40], ''
    if level == 4:
        m = CLAUSE.match(text)
        return (f'Khoản {m.group(1)}', '') if m else ('Khoản ?', '')
    if level == 5:
        m = ITEM.match(text)
        return (f'Điểm {m.group(1)}', '') if m else ('Điểm ?', '')
    return '', ''


PARA = re.compile(r'<(p|div|li|td)\b([^>]*)>(.*?)</\1>', flags=re.S | re.I)


def _attr(attrs: str, name: str):
    m = re.search(rf'\b{name}\s*=\s*"([^"]*)"', attrs)
    return m.group(1) if m else None


def _paragraphs(flight: str) -> list[tuple[str | None, str | None, str]]:
    """(id, provision class, text) for every paragraph-like element, attribute order independent."""
    out = []
    for n, (tag, attrs, frag) in enumerate(PARA.findall(flight)):
        if tag.lower() != 'p' and re.search(r'<(p|div|li|td)\b', frag, flags=re.I):
            continue                                       # container: its children are listed separately
        cls = next((c for c in (_attr(attrs, 'class') or '').split() if c.startswith('prov-')), None)
        text = _clean(frag)
        if text:
            out.append((_attr(attrs, 'id') or f'p{n}', cls, text))
    return out


def _infer_level(text: str) -> int | None:
    if CHAPTER.match(text):
        return 1
    if SECTION.match(text):
        return 2
    if ARTICLE.match(text):
        return 3
    if CLAUSE.match(text) and len(text) > 3:
        return 4
    if ITEM.match(text):
        return 5
    return None


def parse_provisions(flight: str) -> tuple[list[Provision], str, list[str]]:
    paras = _paragraphs(flight)
    marked = any(cls for _, cls, _ in paras)
    if not paras:
        return [], 'none', ['trang không có toàn văn (chỉ có tệp đính kèm); chưa nạp nội dung']
    out, stack, seen = [], [], set()
    for order, (pid, cls, text) in enumerate(paras):
        level = LEVEL.get(cls) if marked else _infer_level(text)
        if level is None:
            if out:
                out[-1].text += ' ' + text                 # content belongs to the deepest open node, which is the last one
            continue
        if pid in seen:
            pid = f'{pid}#{order}'
        seen.add(pid)
        while stack and stack[-1].level >= level:
            stack.pop()
        label, heading = _label(level, text)
        p = Provision(pid, level, label, heading, text, stack[-1].prov_id if stack else None, order)
        out.append(p)
        stack.append(p)
    notes = [] if marked else ['không có đánh dấu điều khoản; cấu trúc suy ra từ đầu đoạn (Chương, Mục, Điều, khoản, điểm)']
    return out, 'marked' if marked else 'heuristic', notes


def check_quality(provs: list[Provision]) -> list[str]:
    """Top-level article numbers should run 1..n. Articles quoted inside amending clauses are not top level."""
    by_id = {p.prov_id: p for p in provs}
    nums = []
    for p in provs:
        parent = by_id.get(p.parent)
        if p.level == 3 and (parent is None or parent.level <= 2):
            m = re.match(r'Điều\s+(\d+)', p.label)
            if m:
                nums.append(int(m.group(1)))
    if not provs:
        return []
    if not nums:
        return ['không tìm thấy điều nào']
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    return [f'thiếu điều {missing[:10]}{"..." if len(missing) > 10 else ""}'] if missing else []


def parse_page(url: str, page_html: str) -> ParsedDoc:
    flight = flight_text(page_html)
    meta = parse_meta(flight)
    provs, structure, notes = parse_provisions(flight)
    notes += check_quality(provs)
    return ParsedDoc(meta['doc_id'], url, meta, provs, structure, notes)


# ----------------------------------------------------------------------------- chunks for retrieval
def _split_long(text: str, max_chars: int) -> list[str]:
    """Split at sentence ends (then at semicolons, then hard) so no piece exceeds max_chars and nothing is dropped."""
    if len(text) <= max_chars:
        return [text]
    parts, cur = [], ''
    for sent in re.split(r'(?<=[.;:])\s+', text):
        while len(sent) > max_chars:
            if cur:
                parts.append(cur)
                cur = ''
            cut = sent.rfind(' ', 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars   # cut at a space; hard cut only for a word longer than half a chunk
            parts.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if len(cur) + len(sent) + 1 > max_chars and cur:
            parts.append(cur)
            cur = sent
        else:
            cur = f'{cur} {sent}'.strip()
    if cur:
        parts.append(cur)
    return parts


def chunks(doc: ParsedDoc, max_chars: int = 1400) -> list[dict]:
    """One chunk per clause with its points, or per article without clauses; longer units are split, never truncated.

    Every piece carries the location path (document > chapter > article > clause) and the article heading, so a
    retrieved piece is self-explaining. The concatenation of pieces equals the source text of the unit.
    """
    by_id = {p.prov_id: p for p in doc.provisions}
    kids = {}
    for p in doc.provisions:
        kids.setdefault(p.parent, []).append(p)

    def path(p):
        parts = []
        while p is not None:
            parts.append(f'{p.label}. {p.heading}'.strip(' .') if p.level == 3 and p.heading else p.label)
            p = by_id.get(p.parent)
        return list(reversed(parts))

    def subtree(p):
        return [p] + [d for k in kids.get(p.prov_id, []) for d in subtree(k)]

    head = f'{doc.meta.get("doc_type") or ""} {doc.meta.get("doc_num") or ""}'.strip()
    out = []
    articles = [p for p in doc.provisions if p.level == 3]
    roots = articles or [p for p in doc.provisions if p.parent is None]
    covered = set()
    for art in roots:
        clauses = [k for k in kids.get(art.prov_id, []) if k.level == 4]
        others = [d for k in kids.get(art.prov_id, []) if k.level != 4 for d in subtree(k)]
        if not clauses:
            units = [(art, [art] + others)]
        else:
            units = [(c, subtree(c)) for c in clauses]
            if others or len(art.text) > len(f'{art.label}. {art.heading}') + 5:
                units.insert(0, (art, [art] + others))     # lead-in text and points that sit outside any clause
        for unit, nodes in units:
            covered.update(n.prov_id for n in nodes)
            prefix = f'{art.label}. {art.heading}: ' if (unit is not art and art.heading) else ''
            body = ' '.join(n.text for n in nodes)
            for j, piece in enumerate(_split_long(body, max_chars - len(prefix))):
                out.append(dict(chunk_id=f'{doc.doc_id}:{unit.prov_id}:{j}', doc_id=doc.doc_id, prov_id=unit.prov_id,
                                path=f'{head} > ' + ' > '.join(path(unit)), text=prefix + piece, prefix_len=len(prefix), unit_text=body))
    rest = [p for p in doc.provisions if p.prov_id not in covered and p.level > 2 and not any(a.prov_id == p.prov_id for a in roots)]
    for p in rest:                                         # nodes outside any article (rare): kept, not dropped
        for j, piece in enumerate(_split_long(p.text, max_chars)):
            out.append(dict(chunk_id=f'{doc.doc_id}:{p.prov_id}:{j}', doc_id=doc.doc_id, prov_id=p.prov_id,
                            path=f'{head} > ' + ' > '.join(path(p)), text=piece, prefix_len=0, unit_text=p.text))
    return out


def coverage_errors(doc: ParsedDoc, max_chars: int = 1400) -> list[str]:
    """Invariant: for every unit, the pieces without their prefix join back to the unit text, and every provision is in a unit."""
    cs = chunks(doc, max_chars)
    units = {}
    for c in cs:
        units.setdefault(c['prov_id'], [c['unit_text'], []])[1].append(c['text'][c['prefix_len']:])
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()  # noqa: E731
    dense = lambda s: re.sub(r'\s+', '', s)  # noqa: E731  every character present, in order; whitespace carries no meaning
    errors = [f'{pid}: ghép lại không khớp' for pid, (body, pieces) in units.items() if dense(''.join(pieces)) != dense(body)]
    joined = norm(' '.join(body for body, _ in units.values()))
    prefixes = {c['text'][:c['prefix_len']] for c in cs if c['prefix_len']}

    def heading_only(p):                       # "Điều N. Tên điều" with clauses below: carried by every clause prefix
        return p.level == 3 and f'{p.label}. {p.heading}: ' in prefixes and len(norm(p.text)) <= len(p.label) + len(p.heading) + 6

    errors += [f'{p.label} ({p.prov_id}) không nằm trong đoạn nào' for p in doc.provisions
               if p.level >= 3 and norm(p.text) not in joined and not heading_only(p)]
    if any(len(c['text']) > max_chars for c in cs):
        errors.append('có đoạn vượt độ dài tối đa')
    return errors
