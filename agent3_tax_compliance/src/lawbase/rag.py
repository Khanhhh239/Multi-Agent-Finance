"""Grounded legal answers: retrieve dated provisions, pack them within a measured budget, let the local model draft, verify.

Contract (enforced in code, not only in the prompt):
  * the model sees only the packed passages, each with a short id [P1]..[Pn];
  * every answer sentence must cite passage ids from that list and give a verbatim quote found in a cited passage;
  * every number in a sentence must appear in its cited passages;
  * failing sentences are dropped; if nothing survives, the answer falls back to verbatim excerpts (EXTRACTIVE);
  * weak retrieval or a model abstention gives ABSTAIN. No sentence reaches the user without a checked source.
"""
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date

from .llm import CHARS_PER_TOKEN, ContextOverflow, LLMUnavailable, Ollama
from .store import Corpus

SYSTEM = (
    'Bạn là trợ lý tra cứu pháp luật thuế Việt Nam. Chỉ được dùng các đoạn văn bản [P1], [P2]... được cung cấp. '
    'Không dùng hiểu biết bên ngoài, không suy diễn, không bịa số liệu hay số hiệu văn bản. '
    'Mỗi câu trả lời phải ghi mã đoạn làm căn cứ trong trường sources và chép nguyên văn cụm từ làm căn cứ vào trường quote '
    '(chép đúng từng chữ, không sửa). Nếu các đoạn không đủ để trả lời, đặt abstain = true và ghi trong trường missing điều còn thiếu. '
    'Trả lời bằng tiếng Việt, ngắn gọn, mỗi câu một ý.')

SCHEMA = {
    'type': 'object',
    'properties': {
        'abstain': {'type': 'boolean'},
        'answer': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'text': {'type': 'string'}, 'sources': {'type': 'array', 'items': {'type': 'string'}}, 'quote': {'type': 'string'}},
            'required': ['text', 'sources', 'quote']}},
        'missing': {'type': 'string'}},
    'required': ['abstain', 'answer']}

NUMBER = re.compile(r'\d+(?:[.,]\d+)*\s*%?')


def norm(s: str) -> str:
    s = unicodedata.normalize('NFC', s or '').replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    return re.sub(r'\s+', ' ', s).strip().lower()


def numbers(s: str) -> set[str]:
    """Numbers as written, with leading zeros of the integer part removed ("03 tỷ" and "3 tỷ" are the same number)."""
    out = set()
    for n in NUMBER.findall(s or ''):
        n = re.sub(r'\s+', '', n)
        out.add(re.sub(r'^0+(?=\d)', '', n))
    return out


@dataclass
class Passage:
    pid: str
    doc_num: str
    doc_type: str
    path: str
    url: str
    eff_from: str | None
    status: str | None
    text: str
    partial: bool = False


@dataclass
class RagAnswer:
    question: str
    as_of: str
    mode: str                         # LLM_VERIFIED | EXTRACTIVE | ABSTAIN
    sentences: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    passages: list = field(default_factory=list)
    note: str = ''
    stats: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def pack(corpus: Corpus, question: str, as_of: date, k: int = 8, budget_tokens: int = 7000) -> list[Passage]:
    """Top units in rank order until the token budget is used. A unit too long for the rest of the budget is replaced by
    its best-matching piece, marked partial; nothing is cut silently."""
    hits = corpus.search(question, as_of, k)
    budget = int(budget_tokens * CHARS_PER_TOKEN)
    out, used = [], 0
    for h in hits:
        full = corpus.unit_text(h['doc_id'], h['prov_id'])
        text, partial = (full, False) if used + len(full) <= budget else (h['text'], True)
        if used + len(text) > budget:
            continue
        url = corpus.db.execute('SELECT url FROM documents WHERE doc_id=?', (h['doc_id'],)).fetchone()[0]
        out.append(Passage(f'P{len(out) + 1}', h['doc_num'], h['doc_type'], h['path'], url, h['eff_from'], h['status_name'], text, partial))
        used += len(text) + len(h['path']) + 80
    return out


def render(passages: list[Passage]) -> str:
    return '\n\n'.join(f'[{p.pid}] {p.path} | hiệu lực từ {p.eff_from or "không ghi"} | {p.status or "không ghi tình trạng"}'
                       f'{" | (một phần của khoản)" if p.partial else ""}\n{p.text}' for p in passages)


def verify(raw: str, passages: list[Passage]) -> tuple[list, list, bool, str]:
    data = json.loads(raw)
    by_id = {p.pid: p for p in passages}
    kept, dropped = [], []
    for s in data.get('answer', []):
        text, srcs, quote = s.get('text', ''), [x.strip('[] ') for x in s.get('sources', [])], s.get('quote', '')
        cited = [by_id[x] for x in srcs if x in by_id]
        if not cited or len(cited) != len(srcs):
            dropped.append(dict(text=text, reason='mã đoạn không có trong ngữ cảnh'))
            continue
        body = ' '.join(p.text for p in cited)
        if not quote or norm(quote) not in norm(body):
            dropped.append(dict(text=text, reason='trích dẫn không khớp nguyên văn'))
            continue
        extra = numbers(text) - numbers(' '.join(f'{p.path} {p.doc_num} {p.text}' for p in cited))   # document number lives in the path
        if extra:
            dropped.append(dict(text=text, reason=f'số không có trong căn cứ: {sorted(extra)}'))
            continue
        kept.append(dict(text=text, quote=quote, sources=srcs,
                         citations=[dict(pid=p.pid, doc_num=p.doc_num, path=p.path, url=p.url) for p in cited]))
    return kept, dropped, bool(data.get('abstain')), data.get('missing', '')


def answer(corpus: Corpus, question: str, as_of: date | None = None, llm: Ollama | None = None, min_coverage: float = 0.35,
           k: int = 8, budget_tokens: int = 7000) -> RagAnswer:
    as_of = as_of or date.today()
    passages = pack(corpus, question, as_of, k, budget_tokens)
    res = RagAnswer(question, as_of.isoformat(), 'ABSTAIN', passages=[asdict(p) for p in passages])
    top = corpus.search(question, as_of, 1)
    res.stats['retrieval_top_coverage'] = round(top[0]['coverage'], 3) if top else 0
    if not passages or res.stats['retrieval_top_coverage'] < min_coverage:
        res.note = 'Kho văn bản không có đoạn đủ liên quan để trả lời; hãy hỏi chuyên gia hoặc tra Chatbot AI của Cục Thuế.'
        return res
    llm = llm or Ollama()
    user = f'Ngày áp dụng: {as_of:%d/%m/%Y}\nCâu hỏi: {question}\n\nCác đoạn văn bản:\n{render(passages)}'
    try:
        raw, stats = llm.chat(SYSTEM, user, SCHEMA)
        res.stats.update(stats)
        kept, dropped, abstain, missing = verify(raw, passages)
    except (LLMUnavailable, ContextOverflow, json.JSONDecodeError) as e:
        kept, dropped, abstain, missing = [], [], False, ''
        res.note = f'Không dùng được mô hình ({type(e).__name__}: {str(e)[:160]}); trả về nguyên văn các đoạn liên quan.'
    res.dropped = dropped
    if abstain and not kept:
        res.mode, res.note = 'ABSTAIN', (missing or 'Mô hình xác định các đoạn chưa đủ căn cứ.')
    elif kept:
        res.mode, res.sentences = 'LLM_VERIFIED', kept
    else:
        res.mode = 'EXTRACTIVE'
        res.note = res.note or 'Không câu nào của mô hình qua được kiểm tra căn cứ; trả về nguyên văn các đoạn liên quan nhất.'
        res.sentences = [dict(text=p.text[:600] + ('...' if len(p.text) > 600 else ''), quote=p.text[:200], sources=[p.pid],
                              citations=[dict(pid=p.pid, doc_num=p.doc_num, path=p.path, url=p.url)]) for p in passages[:2]]
    return res
