"""The question-answering entry point: parameters, route, handler, and the record of how the answer was reached.

Every answer carries `understood` (the domain title and the parameters read), so the person sees how the question was
understood and can pick another domain from `alternatives` when it was misunderstood.
"""
import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..pack import load_pack
from .handlers import HANDLERS, ChatAnswer
from .params import extract
from .router import Router, load_catalog

_router = None


def router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router


@dataclass
class ChatContext:
    workspace: Path
    ruleset_path: Path
    as_of: date
    report: object
    lawbase_db: Path | None = None
    llm: object = None
    catalog: dict = field(default_factory=load_catalog)

    @property
    def pack(self):
        if not hasattr(self, '_pack'):
            self._pack = load_pack(self.workspace / 'pack.json')
        return self._pack

    def law(self, question: str):
        if not self.lawbase_db or not Path(self.lawbase_db).exists():
            return None
        from ...lawbase import rag
        from ...lawbase.store import Corpus
        c = Corpus(self.lawbase_db)
        try:
            return rag.answer(c, question, self.as_of, self.llm)
        finally:
            c.close()

    def law_alerts(self):
        if not self.lawbase_db or not Path(self.lawbase_db).exists():
            return None
        from ..catalog import law_alerts
        return law_alerts(self.lawbase_db, self.as_of)

    def declared(self) -> dict:
        p = self.workspace / 'declared.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def answer(question: str, ctx: ChatContext, domain: str | None = None) -> dict:
    """domain: set when the person picked a domain after a misunderstanding; the router is then skipped."""
    r = router()
    p = extract(question, ctx.report, ctx.catalog, ctx.as_of)
    if domain:
        if domain not in HANDLERS:
            raise ValueError(f'unknown domain {domain}')
        from .router import Route
        route = Route(domain, 'CHOSEN_BY_USER', 1.0, [])
    else:
        route = r.route(question, p)
    if route.domain == 'by_issue' and not p.issue:
        p.issue, p.issue_name = r.issue_by_meaning(question)
    if route.domain is None:
        ans = ChatAnswer(None, 'Câu hỏi này nằm ngoài các loại câu trợ lý trả lời được, hoặc chưa đủ rõ để trả lời chắc chắn, nên trợ lý không đoán. '
                         'Xem danh sách "Trợ lý trả lời được gì" để chọn cách hỏi, hoặc chọn một loại gần đúng bên dưới.', branch='REFUSED')
    else:
        ans = HANDLERS[route.domain](ctx, p, question)
    d = r.domains.get(route.domain or '', {})
    out = dataclasses.asdict(ans)
    out['columns'] = [list(c) for c in ans.columns]
    out['links'] = [list(x) for x in ans.links]
    out['route'] = route.to_dict()
    out['understood'] = dict(title=d.get('title'), period=p.period.label if not p.period.is_all else None,
                             invoice_numbers=p.invoice_numbers or None, seller=p.seller_text, issue=p.issue_name, top_n=p.top_n)
    out['alternatives'] = [dict(domain=c['domain'], title=r.domains[c['domain']]['title']) for c in route.candidates
                           if c['domain'] != route.domain and c['domain'] in r.domains][:3]
    return json.loads(json.dumps(out, default=lambda o: str(o) if isinstance(o, (Decimal, date)) else o.__dict__))


def guide(catalog: dict | None = None) -> dict:
    """The help page: every domain grouped, with what it answers, its limits and example questions. Generated from the
    same catalog the router uses, so the guide cannot list a domain the assistant does not handle."""
    cat = catalog or load_catalog()
    groups = []
    for g in cat['groups']:
        ds = [dict(id=d['id'], title=d['title'], what=d['what'], limits=d.get('limits', ''), examples=d.get('guide', []))
              for d in cat['domains'] if d['group'] == g['id'] and d['id'] in HANDLERS]
        if ds:
            groups.append(dict(id=g['id'], title=g['title'], domains=ds))
    return dict(version=cat['version'], groups=groups)


def suggestions(ctx: ChatContext, limit: int = 6) -> list[str]:
    """Questions built from this enterprise's own data, so every suggestion has an answer here."""
    rep = ctx.report
    out = []
    if not rep.invoices:
        return ['Trợ lý trả lời được những gì?', 'Điều kiện khấu trừ thuế GTGT đầu vào là gì?', 'Hạn nộp tờ khai thuế GTGT theo quý là khi nào?']
    latest = max(i.issue_date for i in rep.invoices if i.issue_date)
    quarterly = ctx.pack.filing_period == 'QUARTER'
    period = f'quý {(latest.month - 1) // 3 + 1}/{latest.year}' if quarterly else f'tháng {latest.month}/{latest.year}'
    out.append(f'Thuế có nguy cơ bị loại {period} là bao nhiêu?')
    top = next((it for it in rep.items if it.status == 'AT_RISK' and it.invoice_keys), None)
    by_key = {i.key: i for i in rep.invoices}
    if top and by_key.get(top.invoice_keys[0]) and by_key[top.invoice_keys[0]].number:
        out.append(f'Vì sao hóa đơn số {int(by_key[top.invoice_keys[0]].number)} bị cảnh báo?')
    up = [c for c in rep.calendar if c['due'] >= ctx.as_of]
    if up:
        out.append('Hạn nộp tờ khai gần nhất là khi nào?')
    codes = {it.code for it in rep.items if it.status in ('AT_RISK', 'REVIEW')}
    if any(c.startswith('R01') for c in codes):
        out.append('Hóa đơn nào chưa có chứng từ chuyển khoản?')
    if any(c.startswith('R05') for c in codes):
        out.append('Có hóa đơn nào bị nhập trùng không?')
    out.append('Hôm nay nên làm gì trước?')
    if any(i.role == 'SALE' for i in rep.invoices):
        out.append(f'Thuế GTGT phải nộp {period} ước tính bao nhiêu?')
    out.append('Điều kiện khấu trừ thuế GTGT đầu vào là gì?')
    return list(dict.fromkeys(out))[:limit]
