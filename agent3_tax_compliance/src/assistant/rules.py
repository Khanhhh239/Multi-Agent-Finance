"""Step 5-6: dated rules and money at risk. Parameters are chosen by the invoice issue date from a versioned ruleset.

Every item carries its basis and the ruleset version; the whole ruleset is DRAFT until a tax expert signs it.
"""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..extraction.xml_context import MIN_HISTORY, amount_outlier, fold, similarity
from .models import InvoiceFact, Match, RiskItem
from .pack import Pack

def vn(n) -> str:
    return f'{n:,.0f}'.replace(',', '.')


INTEGRITY_BASIS = 'Lá chắn dữ liệu của khung cố định: chữ ký số, số học, số tiền bằng chữ, cấu trúc (không phải điều luật)'


def load_ruleset(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('status') not in ('DRAFT', 'APPROVED'):
        raise ValueError('ruleset status must be DRAFT or APPROVED')
    return data


def param(ruleset: dict, name: str, on: date | None):
    """(value, basis) of the parameter version in force on the date; None when no version covers it."""
    if on is None:
        return None
    for v in ruleset['parameters'][name]:
        if (v['from'] is None or date.fromisoformat(v['from']) <= on) and (v['to'] is None or on < date.fromisoformat(v['to'])):
            return v['value'], v['basis']
    return None


LOW_VOLUME_MAX_NUMBER, LOW_VOLUME_FROM_MONTH, LOW_VOLUME_MIN_GROSS = 10, 4, Decimal(20_000_000)


def _item(ruleset, code, status, invoices, amount, basis, detail='', evidence=(), suffix=''):
    meta = ruleset['rules'][code + suffix] if code + suffix in ruleset['rules'] else ruleset['rules'][code]
    tag = f'[{ruleset["status"]}, {ruleset["version"]}]'
    return RiskItem(code=code + suffix, status=status, title=meta['title'], invoice_keys=tuple(i.key if hasattr(i, 'key') else i for i in invoices),
                    amount=amount, basis=tuple(basis) + (tag,), action=meta['action'], detail=detail, evidence=tuple(evidence))


def evaluate(invoices: list[InvoiceFact], matches: list[Match], pack: Pack, ruleset: dict, unreadable: list[str],
             portal: list[dict] | None) -> tuple[list[RiskItem], list[RiskItem]]:
    items, flags = [], []
    purchases = [i for i in invoices if i.role == 'PURCHASE']
    originals = [i for i in purchases if not i.duplicate_of]
    by_key = {i.key: i for i in originals}
    matched = {k for m in matches if m.status == 'MATCHED' for k in m.invoice_keys}
    ambiguous = {k: m for m in matches if m.status == 'AMBIGUOUS' for k in m.invoice_keys}
    vat = lambda i: i.vat or Decimal(0)  # noqa: E731
    deduction = pack.vat_method == 'DEDUCTION'

    for f in unreadable:
        items.append(_item(ruleset, 'R04_INVOICE_INTEGRITY', 'REVIEW', [f'file:{f.split(":")[0]}'], Decimal(0), [INTEGRITY_BASIS],
                           detail=f'Không đọc được tệp: {f}'))
    for i in purchases:
        if i.guard_errors:
            items.append(_item(ruleset, 'R04_INVOICE_INTEGRITY', 'AT_RISK', [i], vat(i), [INTEGRITY_BASIS],
                               detail='Lỗi: ' + ', '.join(c.replace('XML_CHECK_', '') for c in i.guard_errors), evidence=(i.file,)))
        if i.duplicate_of:
            items.append(_item(ruleset, 'R05_DUPLICATE', 'AT_RISK', [i], vat(i), ['Một hóa đơn chỉ được khấu trừ một lần'],
                               detail=f'Tệp {i.file} trùng với {i.duplicate_of}', evidence=(i.file, i.duplicate_of)))

    for i in originals:                                   # replacement and adjustment references
        if i.related and i.related['key'] in by_key:
            orig = by_key[i.related['key']]
            if i.related['nature'] == '1':
                items.append(_item(ruleset, 'R06_REPLACED_ORIGINAL', 'AT_RISK', [orig], vat(orig), ['Hóa đơn bị thay thế không còn giá trị khấu trừ (thứ cấp)'],
                                   detail=f'{orig.display} bị thay thế bởi {i.display}', evidence=(orig.file, i.file)))
            else:
                items.append(_item(ruleset, 'R06_ADJUSTED', 'REVIEW', [orig, i], Decimal(0), ['Hóa đơn điều chỉnh làm thay đổi số kê khai (thứ cấp)'],
                                   detail=f'{i.display} điều chỉnh {orig.display}'))

    own = pack.tax_code.replace('-', '')
    for i in originals:                                   # buyer block against the enterprise profile
        buyer = (i.buyer_tax_id or '').replace('-', '')
        if buyer != own and buyer[:10] != own[:10]:
            items.append(_item(ruleset, 'R07_BUYER_TAX_ID', 'AT_RISK', [i], vat(i), ['Hóa đơn phải ghi đúng mã số thuế người mua (thứ cấp)'],
                               detail=f'Mã số thuế người mua trên hóa đơn: {i.buyer_tax_id or "không có"}; hồ sơ: {pack.tax_code}'))
            continue
        problems = []
        if i.buyer_name and similarity(i.buyer_name, pack.legal_name) < 0.8:
            problems.append(f'tên "{i.buyer_name}" khác "{pack.legal_name}"')
        if pack.registered_address and i.buyer_address and similarity(i.buyer_address, pack.registered_address) < 0.6:
            problems.append('địa chỉ khác hồ sơ')
        if problems:
            items.append(_item(ruleset, 'R07_BUYER_NAME', 'REVIEW', [i], vat(i), ['Hồ sơ doanh nghiệp trong gói thích ứng'], detail='; '.join(problems)))

    for i in originals:                                   # reference lists (published risky enterprises)
        for ref in pack.reference_lists:
            if i.seller_tax_id in ref.tax_ids:
                items.append(_item(ruleset, 'R08_RISKY_SELLER', 'REVIEW', [i], vat(i), [f'{ref.name} ({ref.source})'],
                                   detail=f'Danh sách tính đến ngày {ref.as_of.isoformat()}'))

    override = pack.thresholds['non_cash_threshold_override']
    small_by_day = defaultdict(list)
    for i in originals:                                   # payment evidence
        if not i.gross or not i.issue_date:
            continue
        p = param(ruleset, 'NON_CASH_THRESHOLD', i.issue_date)
        threshold = min(Decimal(p[0]), override) if override is not None else Decimal(p[0])
        basis = [p[1]] + ([f'Ngưỡng nội bộ thấp hơn: {override}'] if override is not None and override < Decimal(p[0]) else [])
        if i.gross >= threshold:
            if i.key in matched:
                continue
            if not deduction:
                items.append(_item(ruleset, 'R01_PAYMENT_EVIDENCE', 'INFO', [i], Decimal(0), basis,
                                   detail='Doanh nghiệp không khấu trừ thuế đầu vào; vẫn ảnh hưởng chi phí được trừ thuế thu nhập doanh nghiệp'))
            elif i.key in ambiguous:
                m = ambiguous[i.key]
                items.append(_item(ruleset, 'R03_AMBIGUOUS_PAYMENT', 'REVIEW', [i], vat(i), basis, detail=m.note, evidence=m.txn_ids))
            else:
                items.append(_item(ruleset, 'R01_PAYMENT_EVIDENCE', 'AT_RISK', [i], vat(i), basis,
                                   detail=f'Tổng thanh toán {vn(i.gross)} đồng, ngưỡng {vn(threshold)} đồng; nhãn trên hóa đơn: {i.payment_label or "không ghi"}'))
        else:
            small_by_day[(i.seller_tax_id, i.issue_date, threshold, p[1])].append(i)
    for (seller, day, threshold, basis), group in sorted(small_by_day.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        total = sum(i.gross for i in group)
        if len(group) < 2 or total < threshold:
            continue
        for i in group:
            if i.key in matched or not deduction:
                continue
            status, code = ('REVIEW', 'R03_AMBIGUOUS_PAYMENT') if i.key in ambiguous else ('AT_RISK', 'R02_SAME_DAY_CUMULATIVE')
            items.append(_item(ruleset, code, status, [i], vat(i), [basis],
                               detail=f'{len(group)} hóa đơn của cùng người bán ngày {day.isoformat()}, tổng {vn(total)} đồng'))

    if portal is not None:                                # portal list reconciliation
        portal_keys = {r['key']: r for r in portal}
        for i in originals:
            if i.key not in portal_keys:
                items.append(_item(ruleset, 'R09_NOT_ON_PORTAL', 'REVIEW', [i], vat(i), ['Bảng kê hóa đơn mua vào tải từ cổng hóa đơn điện tử']))
        for k, r in sorted(portal_keys.items()):
            if k not in by_key:
                items.append(_item(ruleset, 'R09_UNCAPTURED', 'OPPORTUNITY', [k], r['vat'] or Decimal(0),
                                   ['Bảng kê hóa đơn mua vào tải từ cổng hóa đơn điện tử'], detail=r['source']))

    history = defaultdict(list)                           # vendor outliers (statistical, never money at risk)
    for i in sorted(originals, key=lambda x: (x.issue_date or date.min, x.key)):
        prior = history[i.seller_tax_id]
        if i.gross and len(prior) >= MIN_HISTORY and amount_outlier(prior, i.gross):
            items.append(_item(ruleset, 'R11_VENDOR_OUTLIER', 'REVIEW', [i], Decimal(0), ['Thống kê trên lịch sử của chính doanh nghiệp'],
                               detail=f'{vn(i.gross)} đồng so với {len(prior)} hóa đơn trước của người bán'))
        if i.gross:
            prior.append(i.gross)

    # Low-volume seller (signal, never money at risk). Invoice numbers restart at 1 every 1 January within each symbol
    # (Phụ lục, mục 2 điểm a Nghị định 254/2026/NĐ-CP), so a small number late in the year means the seller has issued very
    # few invoices under that symbol: a pattern of invoice-issuing shell companies described in the VAT-fraud literature.
    for i in originals:
        if i.role != 'PURCHASE' or not i.issue_date or not (i.number or '').isdigit() or not i.gross:
            continue
        if int(i.number) <= LOW_VOLUME_MAX_NUMBER and i.issue_date.month >= LOW_VOLUME_FROM_MONTH and i.gross >= LOW_VOLUME_MIN_GROSS:
            items.append(_item(ruleset, 'R13_LOW_VOLUME_SELLER', 'REVIEW', [i], Decimal(0),
                               ['Phụ lục, mục 2 điểm a Nghị định 254/2026/NĐ-CP: số hóa đơn bắt đầu từ số 1 vào ngày 01/01 hàng năm, liên tục trong cùng ký hiệu (văn bản gốc, vbpl.vn)',
                                'Dấu hiệu rủi ro tham khảo nghiên cứu phát hiện hóa đơn khống, không phải quy định xử phạt'],
                               detail=f'hóa đơn số {int(i.number)} của ký hiệu {i.template or ""}{i.symbol or ""} lập ngày {i.issue_date:%d/%m/%Y}, '
                                      f'trị giá {vn(i.gross)} đồng: người bán mới lập khoảng {int(i.number)} hóa đơn của ký hiệu này trong năm'))

    for i in originals:                                   # internal policies: add flags only
        for pol in pack.policies:
            if pol.min_gross is not None and (i.gross or 0) < pol.min_gross:
                continue
            if pol.seller_tax_ids and i.seller_tax_id not in pol.seller_tax_ids:
                continue
            if pol.description_contains and not any(fold(w) in fold(' '.join(i.descriptions)) for w in pol.description_contains):
                continue
            flags.append(RiskItem(code=f'POLICY_{pol.policy_id}', status='INFO', title=pol.flag, invoice_keys=(i.key,), amount=Decimal(0),
                                  basis=('Chính sách nội bộ trong gói thích ứng (chỉ thêm cờ, không đổi kết quả luật)',), action=pol.flag))
    return items, flags


def totals(items: list[RiskItem], ruleset: dict, as_of: date) -> dict:
    at_risk, review, opportunity = {}, {}, Decimal(0)
    for it in items:
        key = it.invoice_keys[0] if it.invoice_keys else it.code
        if it.status == 'AT_RISK':
            at_risk[key] = max(at_risk.get(key, Decimal(0)), it.amount)
        elif it.status == 'REVIEW':
            review[key] = max(review.get(key, Decimal(0)), it.amount)
        elif it.status == 'OPPORTUNITY':
            opportunity += it.amount
    review = {k: v for k, v in review.items() if k not in at_risk}
    rate, basis = param(ruleset, 'UNDERDECLARATION_PENALTY_RATE', as_of)
    total = sum(at_risk.values(), Decimal(0))
    return dict(at_risk_vat=total, at_risk_invoices=len(at_risk), penalty_rate=Decimal(rate),
                penalty_estimate=(total * Decimal(rate)).quantize(Decimal(1)), penalty_basis=basis,
                review_vat=sum(review.values(), Decimal(0)), review_invoices=len(review), opportunity_vat=opportunity,
                by_code={c: sum(1 for it in items if it.code == c) for c in sorted({it.code for it in items})})
