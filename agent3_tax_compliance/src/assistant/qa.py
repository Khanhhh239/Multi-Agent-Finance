"""Questions on the enterprise's own data. Three branches: DATA, POLICY, JUDGMENT.

Intent detection is rule-based in this version. Answers are built only from report facts and ruleset metadata;
every number in an answer comes from the pipeline. A language model may later rephrase the text but must not
add numbers or conclusions (same contract as src/explanation_v2).
"""
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..extraction.xml_context import fold
from . import pipeline
from .models import Report
from .report import STATUS_VI, money
from .rules import load_ruleset, param


@dataclass
class Answer:
    branch: str
    text: str
    facts: list = field(default_factory=list)
    citations: list = field(default_factory=list)


@dataclass
class Context:
    workspace: Path
    ruleset_path: Path
    as_of: date
    report: Report
    lawbase_db: Path | None = None     # when set, policy and judgment questions are answered from the legal corpus
    llm: object = None                 # optional client for grounded answers (default: local qwen3:8b through Ollama)


def _lawbase(ctx: Context, question: str):
    if not ctx.lawbase_db or not Path(ctx.lawbase_db).exists():
        return None
    from ..lawbase import rag
    from ..lawbase.store import Corpus
    corpus = Corpus(ctx.lawbase_db)
    try:
        return rag.answer(corpus, question, ctx.as_of, ctx.llm)
    finally:
        corpus.close()


def _cite(s: dict) -> str:
    return '; '.join(f'{c["doc_num"]}, {c["path"].split(" > ", 1)[-1]}' for c in s['citations'])


def _month(q: str):
    m = re.search(r'thang\s*(\d{1,2})(?:\s*/\s*(\d{4}))?', q)
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else None) if m else None


def _numbers(q: str):
    return [str(int(n)) for n in re.findall(r'(?:hoa don|hd|so)\s*(?:so\s*)?(\d{1,8})', q)] + \
        [str(int(n)) for n in re.findall(r'(?<![\d])(\d{3,8})(?![\d])', re.sub(r'(?:hoa don|hd|so)\s*(?:so\s*)?\d{1,8}', ' ', q))]


def _inv(report, key):
    return next((i for i in report.invoices if i.key == key and not i.duplicate_of), None)


def answer(question: str, ctx: Context) -> Answer:
    q = fold(question)
    r = ctx.report
    nums = _numbers(q)

    if any(w in q for w in ('tiep khach', 'co duoc tru', 'chi phi hop ly', 'hop ly khong', 'duoc tinh vao chi phi')) and not nums:
        ruleset = load_ruleset(ctx.ruleset_path)
        thr = param(ruleset, 'NON_CASH_THRESHOLD', ctx.as_of)
        refs = _lawbase(ctx, question)
        extra = []
        if refs and refs.mode != 'ABSTAIN':
            extra = [f'{s["text"]} ({_cite(s)})' for s in refs.sentences]
        return Answer('JUDGMENT', ('Câu hỏi này cần người có chuyên môn kết luận; hệ thống không tự trả lời được hay không. '
                      'Các điều kiện thường phải xét: khoản chi thực tế phát sinh và phục vụ sản xuất kinh doanh; có hóa đơn, chứng từ hợp pháp; '
                      f'từ {money(thr[0])} phải có chứng từ thanh toán không dùng tiền mặt; không thuộc nhóm khoản chi không được trừ. '
                      'Hãy chuẩn bị hóa đơn, chứng từ thanh toán và giấy tờ chứng minh mục đích chi, rồi hỏi chuyên gia thuế.')
                      + (' Các điều khoản liên quan trong kho luật: ' + ' '.join(extra) if extra else ''),
                      facts=[refs.to_dict()] if refs else [],
                      citations=[thr[1], 'Điều 9 và Điều 10 Nghị định 320/2025/NĐ-CP (văn bản hợp nhất 19/VBHN-BTC) về khoản chi được trừ và không được trừ'])

    if 'neu' in q and any(w in q for w in ('bo sung', 'chung tu', 'chuyen khoan', 'uy nhiem chi')) and nums:
        keys = [i.key for i in r.invoices if i.number and i.number.isdigit() and str(int(i.number)) in nums and not i.duplicate_of]
        if not keys:
            return Answer('DATA', 'Không tìm thấy hóa đơn có số đã nêu trong dữ liệu.')
        extra = {k: dict(invoice_key=k, action='PAYMENT_EVIDENCE_ATTACHED', evidence='GIẢ ĐỊNH (chưa có chứng từ thật)', by='câu hỏi giả định')
                 for k in keys}
        after = pipeline.run(ctx.workspace, ctx.ruleset_path, ctx.as_of, extra).totals
        before = r.totals
        delta = before['at_risk_vat'] - after['at_risk_vat']
        return Answer('DATA', f'Giả định bổ sung chứng từ chuyển khoản cho {len(keys)} hóa đơn: thuế có nguy cơ giảm từ '
                      f'{money(before["at_risk_vat"])} xuống {money(after["at_risk_vat"])} (giảm {money(delta)}). '
                      'Đây là kết quả chạy lại với giả định, chưa phải chứng từ thật.',
                      facts=[dict(invoice_keys=keys, before=str(before['at_risk_vat']), after=str(after['at_risk_vat']))])

    if nums and ('hoa don' in q or 'hd' in q.split()):
        found = [i for i in r.invoices if i.number and i.number.isdigit() and str(int(i.number)) in nums and not i.duplicate_of]
        if not found:
            return Answer('DATA', 'Không tìm thấy hóa đơn có số đã nêu trong dữ liệu.')
        parts, facts = [], []
        for inv in found:
            its = [it for it in r.items if inv.key in it.invoice_keys]
            mt = next((m for m in r.matches if inv.key in m.invoice_keys), None)
            pay = 'đã ghép được chứng từ ngân hàng' if mt and mt.status == 'MATCHED' else ('có giao dịch cùng số tiền cần xác nhận' if mt else 'chưa ghép được chứng từ ngân hàng')
            if its:
                desc = '; '.join(f'{STATUS_VI[it.status].lower()}: {it.title.lower()} ({money(it.amount)})' for it in its)
                parts.append(f'Hóa đơn {inv.display} của {inv.seller_name}, ngày {inv.issue_date:%d/%m/%Y}, tổng {money(inv.gross or 0)}, {pay}. {desc}. '
                             f'Việc cần làm: {its[0].action}.')
            else:
                parts.append(f'Hóa đơn {inv.display} của {inv.seller_name}, ngày {inv.issue_date:%d/%m/%Y}, tổng {money(inv.gross or 0)}, {pay}; '
                             'không có cảnh báo nào trong phạm vi các luật đang chạy (luật ở trạng thái nháp).')
            facts.append(dict(key=inv.key, items=[it.code for it in its]))
        return Answer('DATA', ' '.join(parts), facts=facts, citations=sorted({b for it in r.items for inv in found if inv.key in it.invoice_keys for b in it.basis}))

    if any(w in q for w in ('nguoi ban', 'nha cung cap', 'ncc')):
        digits = re.findall(r'\d{10,13}', q)
        sellers = {i.seller_tax_id: i.seller_name for i in r.invoices if i.role == 'PURCHASE'}
        hit = [t for t in sellers if t in digits] or [t for t, n in sellers.items() if n and fold(n) and any(w in q for w in fold(n).split() if len(w) > 3)
                                                      and sum(w in q for w in fold(n).split()) >= 2]
        if not hit:
            return Answer('DATA', 'Không xác định được người bán trong câu hỏi; hãy ghi mã số thuế hoặc tên đầy đủ.')
        tax = hit[0]
        invs = [i for i in r.invoices if i.seller_tax_id == tax and not i.duplicate_of]
        its = [it for it in r.items if any(i.key in it.invoice_keys for i in invs)]
        risk = sum((it.amount for it in its if it.status == 'AT_RISK'), Decimal(0))
        return Answer('DATA', f'{sellers[tax]} (MST {tax}): {len(invs)} hóa đơn, tổng {money(sum((i.gross or 0) for i in invs))}; '
                      f'{len(its)} cảnh báo, thuế có nguy cơ {money(risk)}. ' + '; '.join(sorted({it.title for it in its})),
                      facts=[dict(seller=tax, invoices=len(invs), items=[it.code for it in its])])

    if any(w in q for w in ('bao nhieu', 'tong', 'nguy co', 'rui ro', 'bi loai')) and any(w in q for w in ('nguy co', 'rui ro', 'bi loai', 'khau tru')):
        month = _month(q)
        its = [it for it in r.items if it.status == 'AT_RISK']
        if month:
            keep = {i.key for i in r.invoices if i.issue_date and i.issue_date.month == month[0] and (month[1] is None or i.issue_date.year == month[1])}
            its = [it for it in its if it.invoice_keys[0] in keep]
        per = {}
        for it in its:
            per[it.invoice_keys[0]] = max(per.get(it.invoice_keys[0], Decimal(0)), it.amount)
        scope = f'tháng {month[0]}' if month else 'toàn bộ dữ liệu'
        groups = {}
        for it in its:
            groups[it.title] = groups.get(it.title, 0) + 1
        detail = '; '.join(f'{n} khoản: {t.lower()}' for t, n in sorted(groups.items(), key=lambda kv: -kv[1]))
        return Answer('DATA', f'Trong {scope}, thuế đầu vào có nguy cơ bị loại là {money(sum(per.values(), Decimal(0)))} trên {len(per)} hóa đơn. {detail}.',
                      facts=[dict(scope=scope, invoices=sorted(per), amount=str(sum(per.values(), Decimal(0))))])

    if any(w in q for w in ('han nop', 'han ke khai', 'khi nao nop', 'to khai', 'deadline', 'han chot')):
        rows = '; '.join(f'{c["period"]}: hạn {c["due"]:%d/%m/%Y} ({c["status"]})' for c in r.calendar)
        return Answer('DATA', f'Hạn nộp tờ khai thuế giá trị gia tăng theo kỳ khai trong hồ sơ: {rows}. {r.calendar[0]["note"] if r.calendar else ""}',
                      citations=[r.calendar[0]['basis']] if r.calendar else [])

    policy_words = ('dieu kien', 'quy dinh', 'la gi', 'nguong', 'luat', 'muc phat', 'bi phat', 'thue suat', 'thoi han', 'tien cham nop',
                    'thoi diem lap', 'nghi dinh', 'thong tu')
    if any(w in q for w in policy_words):
        grounded = _lawbase(ctx, question)
        if grounded is not None:
            if grounded.mode == 'ABSTAIN':
                return Answer('POLICY', 'Kho luật không có căn cứ đủ để trả lời câu này. ' + grounded.note, facts=[grounded.to_dict()])
            prefix = '' if grounded.mode == 'LLM_VERIFIED' else 'Trích nguyên văn (mô hình không trả lời được hoặc không qua kiểm tra): '
            return Answer('POLICY', prefix + ' '.join(f'{s["text"]} [{_cite(s)}]' for s in grounded.sentences),
                          facts=[grounded.to_dict()], citations=sorted({_cite(s) for s in grounded.sentences}))
        ruleset = load_ruleset(ctx.ruleset_path)
        thr = param(ruleset, 'NON_CASH_THRESHOLD', ctx.as_of)
        return Answer('POLICY', f'Theo bộ luật đang dùng (trạng thái {ruleset["status"]}): hóa đơn mua vào từ {money(thr[0])} phải có chứng từ '
                      'thanh toán không dùng tiền mặt để được khấu trừ thuế đầu vào; mua nhiều lần trong ngày cùng người bán thì cộng dồn. '
                      'Với câu hỏi chính sách rộng hơn, nên tra Chatbot AI của Cục Thuế trên eTax Mobile và đối chiếu văn bản gốc.',
                      citations=[thr[1]])

    return Answer('DATA', 'Tôi trả lời được các câu: "tháng 9 có bao nhiêu thuế có nguy cơ bị loại", "hóa đơn số 123 có vấn đề gì", '
                  '"người bán <mã số thuế> có rủi ro gì", "nếu bổ sung chứng từ chuyển khoản cho hóa đơn 123 thì còn bao nhiêu", '
                  '"hạn nộp tờ khai", "điều kiện khấu trừ là gì".')
