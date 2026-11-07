"""The controlled AI layer: the local model proposes, deterministic checks verify, a person approves, everything is logged.

Every task follows the same contract (see Part 13 of the design notes):
* the model gets only facts computed by the rules (amounts, codes, candidates) and answers in a fixed JSON schema;
* a verifier rejects any output that names an unknown id, adds a number that is not in the facts, or leaves the label set;
* rejected or unavailable output falls back to a deterministic template, so the product works without the model;
* outputs are cached by a hash of task, version and input, so rerunning the analysis costs nothing.

Tasks: explain (A4), classify_lines (A1), bank_proposals (A2), draft_letter (A3). Grounded law answers (A5, A6) reuse
src/lawbase/rag.py, which has the same contract.
"""
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ..extraction.xml_context import fold, similarity
from ..lawbase.llm import ContextOverflow, LLMUnavailable, Ollama
from ..lawbase.rag import norm, numbers

PROJECT = Path(__file__).resolve().parents[2]
CACHE = PROJECT / 'data/ai_cache.sqlite3'
MODEL = 'qwen3:8b'


def vn_money(v) -> str:
    return f'{int(Decimal(str(v))):,}'.replace(',', '.') + ' đồng' if v not in (None, '') else ''


class AI:
    """One door to the model, with a cache. llm may be any object with chat(system, user, schema, num_predict)."""

    def __init__(self, llm=None, cache_path: Path = CACHE):
        self.llm = llm or Ollama(MODEL)
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.cache_path)
        db.execute('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, task TEXT, created TEXT, output TEXT, stats TEXT)')
        db.commit()
        db.close()

    def ask(self, task: str, version: str, system: str, payload: dict, schema: dict, num_predict: int = 700) -> tuple[dict, dict]:
        user = json.dumps(payload, ensure_ascii=False, default=str)
        key = hashlib.sha256(f'{task}|{version}|{MODEL}|{system}|{user}'.encode()).hexdigest()
        db = sqlite3.connect(self.cache_path)
        try:
            row = db.execute('SELECT output, stats FROM cache WHERE key=?', (key,)).fetchone()
            if row:
                return json.loads(row[0]), dict(json.loads(row[1]), cached=True)
            raw, stats = self.llm.chat(system, user, schema, num_predict=num_predict)
            out = json.loads(raw)
            db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?)', (key, task, datetime.now().isoformat(timespec='seconds'),
                                                                       json.dumps(out, ensure_ascii=False), json.dumps(stats)))
            db.commit()
            return out, stats
        finally:
            db.close()


def _num_ok(text: str, allowed_texts: list[str]) -> set:
    """Numbers in text that do not appear in any allowed text (thousand separators and leading zeros ignored)."""
    norm = lambda ns: {re.sub(r'[.,](?=\d{3}(?!\d))', '', n) for n in ns}  # noqa: E731
    return norm(numbers(text)) - norm(numbers(' '.join(allowed_texts)))


# ----------------------------------------------------------------------------- A4: plain explanation
EXPLAIN_SYSTEM = """Bạn giúp chủ doanh nghiệp nhỏ hiểu một cảnh báo thuế. Viết 2 đến 4 câu tiếng Việt đơn giản, không thuật ngữ:
chuyện gì xảy ra với hóa đơn này, vì sao có thể mất tiền, và việc cụ thể cần làm ngay.
Quy tắc bắt buộc: chỉ dùng thông tin trong dữ kiện; mọi con số phải chép đúng như trong dữ kiện; không thêm mức phạt, ngày,
điều luật hay con số nào khác; không khẳng định chắc chắn bị phạt. Trả về JSON {"text": "..."}."""
EXPLAIN_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text']}


@dataclass
class Explanation:
    text: str
    mode: str          # AI_VERIFIED | TEMPLATE
    note: str = ''


def explain(ai: AI | None, item: dict, invoice: dict | None) -> Explanation:
    facts = dict(canh_bao=item['title'], chi_tiet=item.get('detail', ''), viec_can_lam=item.get('action', ''),
                 so_thue_lien_quan=vn_money(item.get('amount')) if item.get('amount') else '',
                 hoa_don=dict(so=invoice.get('display') or invoice.get('number'), nguoi_ban=invoice.get('seller_name'),
                              ngay=str(invoice.get('issue_date') or ''), tong_thanh_toan=vn_money(invoice.get('gross')),
                              thue=vn_money(invoice.get('vat'))) if invoice else None)
    template = f'{item["title"]}. {item.get("action", "")}'.strip()
    if ai is None:
        return Explanation(template, 'TEMPLATE', 'không bật mô hình')
    try:
        out, _ = ai.ask('explain', 'v1', EXPLAIN_SYSTEM, facts, EXPLAIN_SCHEMA, 400)
    except (LLMUnavailable, ContextOverflow, json.JSONDecodeError) as e:
        return Explanation(template, 'TEMPLATE', f'mô hình không dùng được: {type(e).__name__}')
    text = (out.get('text') or '').strip()
    extra = _num_ok(text, [json.dumps(facts, ensure_ascii=False)])
    if not text or len(text) > 900:
        return Explanation(template, 'TEMPLATE', 'mô hình trả lời rỗng hoặc quá dài')
    if extra:
        return Explanation(template, 'TEMPLATE', f'mô hình thêm số không có trong dữ kiện {sorted(extra)}; dùng câu mẫu')
    return Explanation(text, 'AI_VERIFIED')


# ----------------------------------------------------------------------------- A1: line purpose
CATEGORIES_DEFAULT = {
    'HANG_HOA_KINH_DOANH': 'hàng mua để bán lại, nguyên vật liệu cho sản xuất',
    'CONG_CU_TAI_SAN': 'máy móc, công cụ, thiết bị, tài sản dùng cho hoạt động kinh doanh',
    'DICH_VU_VAN_HANH': 'điện, nước, viễn thông, thuê mặt bằng, vận chuyển, sửa chữa, văn phòng phẩm, phần mềm',
    'TIEP_KHACH': 'ăn uống, quà tặng, tiếp khách, hội nghị',
    'CA_NHAN': 'đồ dùng cá nhân hoặc gia đình, hàng xa xỉ, không thấy phục vụ kinh doanh',
    'KHONG_RO': 'tên hàng quá chung chung, không đủ để nhận định',
}
def _categories():
    """Item groups from the shared catalog (admin page); the built-in list only when the catalog cannot be read."""
    try:
        from .catalog import ai_categories
        return ai_categories() or CATEGORIES_DEFAULT
    except Exception:  # noqa: BLE001
        return CATEGORIES_DEFAULT


CATEGORIES = CATEGORIES_DEFAULT
CLASSIFY_SYSTEM_HEAD = """Bạn là kế toán thuế. Với từng dòng hàng trên một hóa đơn mua vào của doanh nghiệp, chọn đúng một nhóm và cho biết
hàng đó có phục vụ hoạt động của doanh nghiệp hay không (CO, KHONG, KHONG_RO). Lý do ngắn, phải nhắc tới tên hàng.
Phục vụ hoạt động của doanh nghiệp gồm cả hàng đúng ngành nghề lẫn mọi chi phí vận hành: văn phòng và đồ dùng văn phòng, phần mềm,
dịch vụ thuê ngoài, xe và phương tiện, sửa chữa, bảo dưỡng, bảo hiểm, bảo hộ lao động, kho bãi. Ngành nghề chỉ dùng để nhận ra hàng
lạ so với hoạt động. Chỉ trả KHONG khi hàng rõ ràng dành cho cá nhân, gia đình, giải trí, chăm sóc sắc đẹp hoặc xa xỉ.
Chỉ nhận định từ tên hàng, người bán và ngành nghề trong dữ kiện; không suy diễn thêm. Khi không đủ thông tin, chọn KHONG_RO.
Các nhóm: {cats}
Trả về JSON {"lines": [{"index": số thứ tự dòng, "category": nhóm, "business_use": "CO|KHONG|KHONG_RO", "reason": "..."}]}."""
CLASSIFY_SCHEMA = {'type': 'object', 'properties': {'lines': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'index': {'type': 'integer'}, 'category': {'type': 'string', 'enum': list(CATEGORIES)},
    'business_use': {'type': 'string', 'enum': ['CO', 'KHONG', 'KHONG_RO']}, 'reason': {'type': 'string'}},
    'required': ['index', 'category', 'business_use', 'reason']}}}, 'required': ['lines']}


def classify_lines(ai: AI, invoice: dict, industry: list[str], extra: tuple = ()) -> dict:
    """Labels for the lines of one purchase invoice. Lines whose label fails verification are returned as UNVERIFIED.
    extra: the enterprise's own business categories (name, description); they count as business use."""
    lines = [d for d in invoice.get('descriptions', []) if d]
    base = _categories()
    cats = dict(base)
    for name, desc in extra:
        cats['RIENG_' + fold(name).upper().replace(' ', '_')[:30]] = f'{desc} (nhóm riêng của doanh nghiệp, phục vụ kinh doanh)'
    head = CLASSIFY_SYSTEM_HEAD.replace('{cats}', '; '.join(f'{k}: {v}' for k, v in base.items()))
    system = head if not extra else head.replace(
        'Trả về JSON', 'Nhóm riêng của doanh nghiệp: ' + '; '.join(f'{k}: {v}' for k, v in cats.items() if k.startswith('RIENG_')) + '\nTrả về JSON')
    schema = {**CLASSIFY_SCHEMA, 'properties': {'lines': {'type': 'array', 'items': {
        **CLASSIFY_SCHEMA['properties']['lines']['items'], 'properties': {**CLASSIFY_SCHEMA['properties']['lines']['items']['properties'],
                                                                        'category': {'type': 'string', 'enum': list(cats)}}}}}}
    payload = dict(nganh_nghe_dang_ky=industry or ['không ghi'], nguoi_ban=invoice.get('seller_name'),
                   dong_hang=[dict(index=i, ten_hang=d) for i, d in enumerate(lines)])
    out, stats = ai.ask('classify_lines', 'v2', system, payload, schema, 120 + 90 * len(lines))
    got = {}
    for r in out.get('lines', []):
        i = r.get('index')
        if not isinstance(i, int) or not 0 <= i < len(lines) or i in got:
            continue
        name_tokens = {t for t in fold(lines[i]).split() if len(t) > 2}
        ok = r.get('category') in cats and r.get('business_use') in ('CO', 'KHONG', 'KHONG_RO') and r.get('reason') \
            and (not name_tokens or name_tokens & set(fold(r['reason']).split()))
        got[i] = dict(line=lines[i], category=r.get('category'), business_use=r.get('business_use'), reason=(r.get('reason') or '')[:300],
                      verified=bool(ok))
    labels = [got.get(i, dict(line=d, category='KHONG_RO', business_use='KHONG_RO', reason='mô hình không trả lời dòng này', verified=False))
              for i, d in enumerate(lines)]
    return dict(model=MODEL, version='v2', labels=labels, cached=stats.get('cached', False))


def flagged(labels: list[dict]) -> list[dict]:
    """Lines that become a review item: verified labels saying the purchase does not look like business use."""
    return [x for x in labels if x['verified'] and (x['business_use'] == 'KHONG' or x['category'] == 'CA_NHAN')]


# ----------------------------------------------------------------------------- A2: free-text bank descriptions
BANK_SYSTEM = """Bạn đọc nội dung một giao dịch chuyển khoản của doanh nghiệp và danh sách hóa đơn ứng viên có cùng số tiền.
Hãy cho biết nội dung chuyển khoản nhắc tới người bán nào. Chép nguyên văn đoạn chữ trong nội dung chuyển khoản dùng để nhận ra
(name_in_text). Nếu nội dung không nhắc tới người bán nào trong danh sách, trả candidate = -1. Không đoán.
Trả về JSON {"candidate": số thứ tự ứng viên hoặc -1, "name_in_text": "...", "reason": "..."}."""
BANK_SCHEMA = {'type': 'object', 'properties': {'candidate': {'type': 'integer'}, 'name_in_text': {'type': 'string'}, 'reason': {'type': 'string'}},
               'required': ['candidate', 'name_in_text', 'reason']}


def bank_proposals(ai: AI, txns: list[dict], invoices: list[dict], used_txns: set, settled: set, days_after: int = 90) -> list[dict]:
    """Rules pick the candidates (exact amount, date window, both still open); the model only reads the free text; the
    verifier requires the quoted name to be in the bank text and to resemble the chosen seller. Output: proposals."""
    out = []
    open_inv = [i for i in invoices if i['key'] not in settled and i.get('gross') is not None and i.get('issue_date')]
    for t in txns:
        if t['direction'] != 'OUT' or t['txn_id'] in used_txns:
            continue
        amount = Decimal(str(t['amount']))
        booked = datetime.fromisoformat(str(t['booked'])).date()
        cands = [i for i in open_inv if abs(Decimal(str(i['gross'])) - amount) <= 1
                 and -5 <= (booked - datetime.fromisoformat(str(i['issue_date'])).date()).days <= days_after]
        if not cands:
            continue
        text = ' '.join(x for x in (t.get('description'), t.get('counterparty_name')) if x)
        payload = dict(noi_dung_chuyen_khoan=t.get('description'), ten_doi_ung=t.get('counterparty_name'), so_tien=vn_money(amount),
                       ung_vien=[dict(so_thu_tu=k, nguoi_ban=c['seller_name'], so_hoa_don=c.get('number'), ngay=str(c['issue_date']))
                                 for k, c in enumerate(cands)])
        try:
            res, _ = ai.ask('bank_link', 'v1', BANK_SYSTEM, payload, BANK_SCHEMA, 200)
        except (LLMUnavailable, ContextOverflow, json.JSONDecodeError):
            break
        k, quoted = res.get('candidate', -1), (res.get('name_in_text') or '').strip()
        if not isinstance(k, int) or not 0 <= k < len(cands) or not quoted:
            continue
        inv = cands[k]
        in_text = fold(quoted) and fold(quoted) in fold(text)
        sim = max(similarity(quoted, inv['seller_name'] or ''),
                  similarity(quoted, re.sub(r'(?i)c[oô]ng ty|tnhh|c[oổ] ph[aầ]n|cp|mtv|th[uư][oơ]ng m[aạ]i|d[iị]ch v[uụ]', ' ', inv['seller_name'] or '')))
        generic = {'cong', 'ty', 'tnhh', 'co', 'phan', 'cp', 'mtv', 'thuong', 'mai', 'dich', 'vu', 'san', 'xuat', 'tm', 'dv'}
        qwords = [w for w in fold(quoted).split() if w not in generic]
        name_words = set(fold(inv['seller_name'] or '').split())
        # every distinctive word of the quoted phrase is a word of the seller's name ("nhat tin" in "Bảo trì Hệ thống Nhất Tín"),
        # which a character-level similarity underrates when the name is long
        contained = bool(qwords) and all(w in name_words for w in qwords) and sum(len(w) for w in qwords) >= 5
        if in_text and (sim >= 0.34 or contained):
            out.append(dict(txn_id=t['txn_id'], invoice_key=inv['key'], seller_name=inv['seller_name'], invoice_number=inv.get('number'),
                            amount=str(amount), booked=str(booked), description=t.get('description'), counterparty_name=t.get('counterparty_name'),
                            name_in_text=quoted, similarity=round(sim, 2), reason=(res.get('reason') or '')[:240], source=t.get('source')))
    return out


# ----------------------------------------------------------------------------- A3: explanation letter
LETTER_SYSTEM = """Bạn soạn bản nháp thư giải trình của doanh nghiệp gửi cơ quan thuế, văn phong hành chính, lịch sự, ngắn gọn.
Chỉ dùng các dữ kiện (mã F...) và đoạn văn bản pháp luật (mã P...) được cung cấp. Mỗi đoạn thư phải ghi các mã đã dùng.
Mọi con số, số hóa đơn, ngày phải chép đúng từ dữ kiện hoặc nội dung công văn; không tự thêm. Không cam kết thay doanh nghiệp
điều không có trong dữ kiện. Không tự kết luận việc kê khai là đúng hay sai, không diễn giải luật: chỉ trình bày sự việc, chứng từ
và trích nguyên văn điều khoản. Đoạn nào dùng mã P thì trường "quote" phải là một câu chép nguyên văn từ đoạn văn bản đó.
Trả về JSON {"paragraphs": [{"text": "...", "fact_ids": ["F1"], "passage_ids": ["P1"], "quote": ""}]}."""
LETTER_SCHEMA = {'type': 'object', 'properties': {'paragraphs': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'text': {'type': 'string'}, 'fact_ids': {'type': 'array', 'items': {'type': 'string'}},
    'passage_ids': {'type': 'array', 'items': {'type': 'string'}}, 'quote': {'type': 'string'}},
    'required': ['text', 'fact_ids', 'passage_ids', 'quote']}}}, 'required': ['paragraphs']}


def letter_facts(report: dict, keys: list[str]) -> list[dict]:
    facts = []
    add = lambda kind, text: facts.append(dict(id=f'F{len(facts) + 1}', kind=kind, text=text))  # noqa: E731
    invs = {i['key']: i for i in report['invoices']}
    txns = {t['txn_id']: t for t in report['transactions']}
    for k in keys:
        i = invs.get(k)
        if not i:
            continue
        add('invoice', f'Hóa đơn ký hiệu {i.get("template") or ""}{i.get("symbol") or ""} số {i.get("number")} ngày {i.get("issue_date")} của '
                       f'{i.get("seller_name")} (mã số thuế {i.get("seller_tax_id")}), tổng thanh toán {vn_money(i.get("gross"))}, '
                       f'thuế giá trị gia tăng {vn_money(i.get("vat"))}, nội dung: {"; ".join(i.get("descriptions", [])[:3])}')
        for m in report['matches']:
            if k in m['invoice_keys']:
                for tid in m['txn_ids']:
                    t = txns.get(tid)
                    if t:
                        add('payment', f'Giao dịch ngân hàng ngày {t["booked"]}, số tiền {vn_money(t["amount"])}, nội dung "{t["description"]}", '
                                       f'đối ứng {t.get("counterparty_name") or ""} ({t["source"]})')
                if m.get('method') == 'DECISION' or not m['txn_ids']:
                    add('decision', f'Chứng từ thanh toán do người duyệt xác nhận: {m.get("note")}')
        for it in report['items']:
            if k in it['invoice_keys']:
                add('finding', f'Kết quả rà soát: {it["title"]}. {it.get("detail", "")}')
    return facts


def template_letter(company: dict, facts: list[dict], request_text: str) -> list[dict]:
    head = f'Kính gửi: Cơ quan thuế quản lý. {company.get("legal_name")} (mã số thuế {company.get("tax_code")}) xin giải trình như sau.'
    body = [dict(text=f['text'] + '.', fact_ids=[f['id']], passage_ids=[]) for f in facts if f['kind'] in ('invoice', 'payment', 'decision')]
    tail = 'Doanh nghiệp gửi kèm hóa đơn điện tử, chứng từ thanh toán và các tài liệu liên quan trong hồ sơ đính kèm.'
    return [dict(text=head, fact_ids=[], passage_ids=[])] + body + [dict(text=tail, fact_ids=[], passage_ids=[])]


def draft_letter(ai: AI | None, company: dict, facts: list[dict], passages: list[dict], request_text: str) -> dict:
    """Paragraphs kept only when every cited id exists and every number appears in the cited material or the request."""
    by_id = {f['id']: f['text'] for f in facts} | {p['pid']: f'{p["path"]} {p["doc_num"]} {p["text"]}' for p in passages}
    if ai is None:
        return dict(mode='TEMPLATE', paragraphs=template_letter(company, facts, request_text), dropped=[], note='không bật mô hình')
    payload = dict(doanh_nghiep=dict(ten=company.get('legal_name'), ma_so_thue=company.get('tax_code')), cong_van=request_text[:3000],
                   du_kien=[dict(ma=f['id'], noi_dung=f['text']) for f in facts],
                   van_ban=[dict(ma=p['pid'], dieu_khoan=p['path'], noi_dung=p['text'][:1200]) for p in passages])
    try:
        out, stats = ai.ask('letter', 'v2', LETTER_SYSTEM, payload, LETTER_SCHEMA, 1400)
    except (LLMUnavailable, ContextOverflow, json.JSONDecodeError) as e:
        return dict(mode='TEMPLATE', paragraphs=template_letter(company, facts, request_text), dropped=[], note=f'mô hình không dùng được: {type(e).__name__}')
    kept, dropped = [], []
    allowed_free = [request_text, company.get('legal_name') or '', company.get('tax_code') or '']
    for p in out.get('paragraphs', []):
        ids = [x.strip('[] ') for x in p.get('fact_ids', []) + p.get('passage_ids', [])]
        unknown = [x for x in ids if x not in by_id]
        if unknown:
            dropped.append(dict(text=p.get('text', ''), reason=f'mã không tồn tại: {unknown}'))
            continue
        extra = _num_ok(p.get('text', ''), [by_id[x] for x in ids] + allowed_free)
        if extra:
            dropped.append(dict(text=p.get('text', ''), reason=f'số không có trong dữ kiện: {sorted(extra)}'))
            continue
        pids = [x.strip('[] ') for x in p.get('passage_ids', [])]
        quote = (p.get('quote') or '').strip()
        if pids and (len(quote) < 20 or norm(quote) not in norm(' '.join(by_id[x] for x in pids))):
            dropped.append(dict(text=p.get('text', ''), reason='nhắc điều khoản nhưng không trích đúng nguyên văn'))
            continue
        kept.append(dict(text=p.get('text', '').strip(), fact_ids=p.get('fact_ids', []), passage_ids=pids, quote=quote if pids else ''))
    if not kept:
        return dict(mode='TEMPLATE', paragraphs=template_letter(company, facts, request_text), dropped=dropped,
                    note='không đoạn nào của mô hình qua được kiểm tra; dùng thư mẫu')
    return dict(mode='AI_VERIFIED', paragraphs=kept, dropped=dropped, note='', stats=stats)
