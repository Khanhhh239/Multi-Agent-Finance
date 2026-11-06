"""Choose the answer domain of a question.

Stage 1, semantic: the question is embedded (bge-m3, local). A logistic-regression head trained on the embedded example
questions of configs/assistant/catalog/chat_domains.json (hand-written examples plus model-written paraphrases that passed
a consistency filter, SetFit-style head on frozen embeddings) gives a probability per domain.
Stage 2, structure: parameters written in the question settle the cases the meaning alone cannot (an invoice number
together with 'if ... evidence' is a what-if; a named issue type turns a risk question into a list by issue).
Stage 3, model: when stage 1 is not clear (low score or two domains close), a small local model (qwen3:4b instruct)
chooses among the catalog ids or NONE, constrained by a JSON schema. Its choice is accepted only inside the stage-1
shortlist, so it cannot jump to an unrelated domain.
When nothing is clear the router refuses and the answer lists what can be asked: it never guesses.
"""
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ...extraction.xml_context import fold

PROJECT = Path(__file__).resolve().parents[3]
CATALOG = PROJECT / 'configs/assistant/catalog/chat_domains.json'
INDEX = PROJECT / 'data/chat_index.npz'
ROUTER_MODEL = 'qwen3:8b'      # measured on the dev split: 8b 58/59, 4b instruct 55/59 as tie-breaker

ACCEPT = 0.55        # stage-1 probability accepted without the model
MARGIN = 0.20        # and ahead of the runner-up by at least this
FLOOR = 0.02         # domains below this probability are not offered to the model
SHORTLIST = 5


def load_catalog(path: Path = CATALOG) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass
class Route:
    domain: str | None                   # None = refuse
    method: str                          # SEMANTIC | STRUCTURE | MODEL | REFUSED | KEYWORD_FALLBACK
    score: float = 0.0
    candidates: list = field(default_factory=list)
    note: str = ''

    def to_dict(self):
        return dict(domain=self.domain, method=self.method, score=round(self.score, 3), candidates=self.candidates, note=self.note)


class Router:
    def __init__(self, catalog: dict | None = None, embed=None, llm=None, index_path: Path = INDEX):
        self.catalog = catalog or load_catalog()
        self.domains = {d['id']: d for d in self.catalog['domains']}
        self._embed = embed
        self._llm = llm
        self.index_path = Path(index_path)
        self.ex_domain, self.ex_vecs = None, None

    # ------------------------------------------------------------------ embeddings
    def embed(self, texts):
        if self._embed is None:
            from ...lawbase.dense import embed
            self._embed = embed
        return self._embed(texts)

    def _index(self):
        if self.ex_vecs is not None:
            return
        rows = [(d['id'], t) for d in self.catalog['domains'] for t in d['examples'] + d.get('examples_generated', []) + d.get('guide', [])
                if '<' not in t]
        key = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:16]
        if self.index_path.exists():
            z = np.load(self.index_path, allow_pickle=False)
            if str(z['key']) == key:
                self.ex_domain, self.ex_vecs = list(z['domain']), z['vecs']
                return
        vecs = self.embed([t for _, t in rows])
        self.ex_domain, self.ex_vecs = [d for d, _ in rows], vecs
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.index_path, key=np.array(key), domain=np.array(self.ex_domain), vecs=vecs)
        except OSError:
            pass

    def _head(self):
        if getattr(self, 'clf', None) is None:
            from sklearn.linear_model import LogisticRegression
            self._index()
            self.clf = LogisticRegression(C=32, max_iter=5000).fit(self.ex_vecs, np.array(self.ex_domain))
        return self.clf

    def scores(self, question: str) -> list[tuple[str, float]]:
        clf = self._head()
        v = self.embed([question])[0]
        pr = clf.predict_proba(v[None, :])[0]
        return sorted(((str(d), float(x)) for d, x in zip(clf.classes_, pr)), key=lambda kv: -kv[1])

    # ------------------------------------------------------------------ model tie-break
    def _ask_model(self, question: str, shortlist: list[str]) -> str | None:
        if self._llm is None:
            from ...lawbase.llm import Ollama
            self._llm = Ollama(ROUTER_MODEL, num_ctx=4096, timeout=120)
        options = shortlist + ['NONE']
        system = ('Bạn phân loại câu hỏi của kế toán doanh nghiệp vào đúng một loại. Chỉ chọn trong danh sách. '
                  'Câu hỏi về số liệu, hóa đơn, người bán, hạn nộp, tiền phạt của chính doanh nghiệp là loại dữ liệu; '
                  'câu hỏi luật quy định thế nào nói chung là law_question; hỏi một khoản cụ thể có được trừ hay không là judgment. '
                  'Không liên quan đến thuế, hóa đơn, kế toán của doanh nghiệp thì chọn NONE. Trả về JSON {"domain": "..."}.')
        user = 'Các loại:\n' + '\n'.join(f'- {d}: {self.domains[d]["title"]}. {self.domains[d]["what"]}' for d in shortlist) + \
               f'\n- NONE: ngoài phạm vi\n\nCâu hỏi: {question}'
        schema = {'type': 'object', 'properties': {'domain': {'type': 'string', 'enum': options}}, 'required': ['domain']}
        raw, _ = self._llm.chat(system, user, schema, num_predict=30)
        d = json.loads(raw).get('domain')
        return d if d in options else None

    # ------------------------------------------------------------------ structure
    @staticmethod
    def _structure(q: str, params, ranked: list[tuple[str, float]]) -> str | None:
        top = ranked[0][0]
        has_num = bool(params.invoice_numbers)
        if has_num and any(w in q for w in ('neu', 'gia su', 'gia dinh')) and any(
                w in q for w in ('chung tu', 'chuyen khoan', 'uy nhiem chi', 'thanh toan', 'ngan hang')):
            return 'what_if_evidence'
        if params.invoice_numbers_found and top in ('by_issue', 'risk_total', 'top_risks', 'bank_matching') and 'hoa don' in q:
            return 'invoice_lookup'
        if params.seller and not params.invoice_numbers_found and top not in (
                'what_if_evidence', 'law_question', 'law_updates', 'judgment', 'deadlines', 'help', 'company_profile'):
            return 'seller_lookup'
        if params.seller and top in ('purchase_summary', 'by_issue', 'risk_total', 'decisions_log', 'invoice_lookup') and not params.invoice_numbers_found:
            return 'seller_lookup'
        if params.issue and top in ('risk_total', 'top_risks') and not any(w in q for w in ('tong', 'bao nhieu tien')):
            return 'by_issue'
        return None

    def route(self, question: str, params=None) -> Route:
        q = fold(question)
        try:
            ranked = self.scores(question)
        except Exception as e:  # noqa: BLE001 - embedding server down: say so, use the plain word fallback
            return self._fallback(q, f'không gọi được mô hình nhúng: {e}')
        cands = [dict(domain=d, score=round(s, 3)) for d, s in ranked[:SHORTLIST]]
        top, s1 = ranked[0]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        if params is not None:
            forced = self._structure(q, params, ranked)
            if forced:
                return Route(forced, 'STRUCTURE', s1, cands)
        if s1 >= ACCEPT and s1 - s2 >= MARGIN:
            return Route(top, 'SEMANTIC', s1, cands)
        shortlist = [d for d, s in ranked[:SHORTLIST] if s >= FLOOR]
        try:
            pick = self._ask_model(question, shortlist)
        except Exception as e:  # noqa: BLE001
            if s1 >= 0.4 and s1 - s2 >= 0.15:
                return Route(top, 'SEMANTIC', s1, cands, f'mô hình phân loại không chạy ({e}); dùng điểm ngữ nghĩa')
            return Route(None, 'REFUSED', s1, cands, f'câu hỏi chưa rõ và mô hình phân loại không chạy ({e})')
        if pick in (None, 'NONE'):
            return Route(None, 'REFUSED', s1, cands, 'mô hình phân loại xác định câu hỏi ngoài phạm vi')
        return Route(pick, 'MODEL', dict(ranked)[pick], cands)

    def _fallback(self, q: str, note: str) -> Route:
        words = lambda t: set(fold(t).split())  # noqa: E731
        qa = words(q)
        best, score = None, 0.0
        for d in self.catalog['domains']:
            for ex in d['examples']:
                e = words(ex)
                s = len(qa & e) / max(1, len(e))
                if s > score:
                    best, score = d['id'], s
        if score >= 0.6:
            return Route(best, 'KEYWORD_FALLBACK', score, [], note)
        return Route(None, 'REFUSED', score, [], note)

    def issue_by_meaning(self, question: str) -> tuple[list, str | None]:
        """When a list-by-issue question names no issue in known words, pick the closest issue description."""
        issues = self.catalog.get('issues', [])
        if not issues:
            return [], None
        try:
            vecs = self.embed([question] + [it['name'] for it in issues])
        except Exception:  # noqa: BLE001
            return [], None
        sims = vecs[1:] @ vecs[0]
        k = int(np.argmax(sims))
        return (list(issues[k]['codes']), issues[k]['name']) if sims[k] >= 0.55 else ([], None)
