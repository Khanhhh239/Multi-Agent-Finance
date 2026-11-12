"""One function per answer domain. Every number comes from the analysis report, the ruleset or the legal corpus;
no model writes a number. Each answer says what it covered (period, data loaded) and where the user can act.
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..report import STATUS_VI, money
from ..rules import load_ruleset, param
from .. import accounting, decisions as decision_store

ZERO = Decimal(0)


@dataclass
class ChatAnswer:
    domain: str | None
    text: str
    rows: list = field(default_factory=list)          # optional table: list of dicts with the same keys
    columns: list = field(default_factory=list)       # [(key, header)]
    facts: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    links: list = field(default_factory=list)         # [(label, '#/route')]
    branch: str = 'DATA'                               # DATA | POLICY | JUDGMENT | DATA+POLICY | HELP | REFUSED


# ----------------------------------------------------------------------------- shared helpers
def _invoices(rep, role=None, period=None):
    return [i for i in rep.invoices if not i.duplicate_of and (role is None or i.role == role)
            and (period is None or period.is_all or period.contains(i.issue_date))]


def _inv_by_key(rep):
    return {i.key: i for i in rep.invoices}


def _item_date(rep, it, by_key, txns):
    if it.invoice_keys and it.invoice_keys[0] in by_key:
        return by_key[it.invoice_keys[0]].issue_date
    if it.evidence:
        t = txns.get(it.evidence[0])
        if t:
            return t.booked
    return None


def _items(rep, period=None, statuses=None, codes=None):
    by_key, txns = _inv_by_key(rep), {t.txn_id: t for t in rep.transactions}
    out = []
    for it in rep.items:
        if statuses and it.status not in statuses:
            continue
        if codes and not any(it.code.startswith(c) for c in codes):
            continue
        if period is not None and not period.is_all and not period.contains(_item_date(rep, it, by_key, txns)):
            continue
        out.append(it)
    return out


def _per_invoice_risk(items):
    per = {}
    for it in items:
        k = it.invoice_keys[0] if it.invoice_keys else f'{it.code}:{it.detail}'
        if '#dup:' in k:
            continue
        per[k] = max(per.get(k, ZERO), it.amount)
    return per


def _inv_label(rep, key):
    i = _inv_by_key(rep).get(key)
    if not i:
        return key.replace('|', ' / ')
    return f'số {i.number} của {i.seller_name if i.role == "PURCHASE" else i.buyer_name}'


def _scope(period):
    return period.label if period is not None else 'toàn bộ dữ liệu'


def _no_data(what='hóa đơn', domain=None):
    return ChatAnswer(domain, f'Chưa có {what} nào trong dữ liệu đã nạp. Vào Nạp dữ liệu để tải tệp lên trước.', links=[('Nạp dữ liệu', '#/nap')])


def _cite(s: dict) -> str:
    return '; '.join(f'{c["doc_num"]}, {c["path"].split(" > ", 1)[-1]}' for c in s['citations'])


# ----------------------------------------------------------------------------- TONG_QUAN
def risk_total(ctx, p, q):
    rep = ctx.report
    if not rep.invoices:
        return _no_data(domain='risk_total')
    at = _items(rep, p.period, ('AT_RISK',))
    rv = _items(rep, p.period, ('REVIEW',))
    scoped = accounting.data(rep)
    keys = {i.key for i in _invoices(rep, None, p.period)}
    scoped['invoices'] = [i for i in scoped['invoices'] if i['key'] in keys]
    categories = accounting.buckets(scoped)
    per = {i.key: i.vat or ZERO for i in rep.invoices if categories.get(i.key) == 'AT_RISK'}
    per_rv = {i.key: i.vat or ZERO for i in rep.invoices if categories.get(i.key) == 'REVIEW'}
    groups = defaultdict(lambda: [0, set()])
    for it in at + rv:
        groups[(STATUS_VI[it.status], it.title)][0] += 1
        groups[(STATUS_VI[it.status], it.title)][1].update(it.invoice_keys)
    # Reasons overlap, so this table reports counts; monetary totals above are disjoint.
    rows = [dict(status=s, issue=t, count=n) for (s, t), (n, _) in sorted(groups.items())]
    total = accounting.totals(scoped, load_ruleset(ctx.ruleset_path), ctx.as_of)['at_risk_vat']
    if not per and not per_rv:
        text = f'Trong {_scope(p.period)}: không có hóa đơn nào có nguy cơ hoặc cần xem xét theo các luật đang chạy.'
    else:
        text = (f'Trong {_scope(p.period)}: thuế GTGT đầu vào có nguy cơ bị loại là {money(total)} trên {len(per)} hóa đơn; '
                f'thêm {len(per_rv)} khoản cần xem xét. Chia theo lý do (một hóa đơn có thể có nhiều lý do):')
    return ChatAnswer('risk_total', text, rows, [('status', 'Mức'), ('issue', 'Lý do'), ('count', 'Số cảnh báo')],
                      facts=[dict(scope=_scope(p.period), at_risk=str(total) if total is not None else None, invoices=sorted(per), review=sorted(per_rv))],
                      links=[('Mở Việc cần xử lý', '#/viec')])


def missed_deduction(ctx, p, q):
    rep = ctx.report
    if rep.meta['counts'].get('portal_rows') is None:
        return ChatAnswer('missed_deduction', 'Chưa nạp bảng kê hóa đơn mua vào từ cổng thuế nên chưa biết có hóa đơn bị bỏ sót hay không. '
                          'Tải bảng kê trên cổng hóa đơn điện tử (một lần cho cả kỳ) rồi nạp vào.', links=[('Nạp dữ liệu', '#/nap')])
    its = [it for it in rep.items if it.status == 'OPPORTUNITY']
    if not p.period.is_all:
        its = [it for it in its if p.period.contains(_portal_date(it))]
    rows = [dict(invoice=it.invoice_keys[0].replace('|', ' / ') if it.invoice_keys else '', amount=money(it.amount), action=it.action) for it in its]
    total = sum((it.amount for it in its), ZERO)
    text = (f'Trong {_scope(p.period)}: {len(its)} hóa đơn có trên bảng kê cổng thuế nhưng chưa có tệp XML, thuế có thể đang bỏ sót {money(total)}.'
            if its else f'Trong {_scope(p.period)}: mọi hóa đơn trên bảng kê cổng thuế đều đã có trong dữ liệu.')
    return ChatAnswer('missed_deduction', text, rows, [('invoice', 'Người bán / ký hiệu / số'), ('amount', 'Thuế'), ('action', 'Việc cần làm')],
                      facts=[dict(count=len(its), amount=str(total))])


def _portal_date(it):
    import re
    m = re.search(r'(20\d{2})-(\d{2})-(\d{2})', it.detail or '')
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def top_risks(ctx, p, q):
    rep = ctx.report
    n = p.top_n or 5
    best = {}
    for it in _items(rep, p.period, ('AT_RISK', 'REVIEW')):
        k = it.invoice_keys[0] if it.invoice_keys else f'{it.code}:{it.detail}'
        if k not in best or (it.status != 'AT_RISK', -it.amount) < (best[k].status != 'AT_RISK', -best[k].amount):
            best[k] = it
    order = sorted(best.items(), key=lambda kv: (kv[1].status != 'AT_RISK', -kv[1].amount))[:n]
    if not order:
        return ChatAnswer('top_risks', f'Trong {_scope(p.period)}: không có hóa đơn nào có nguy cơ hoặc cần xem xét.')
    rows = [dict(invoice=_inv_label(rep, k) if it.invoice_keys else it.detail[:80], status=STATUS_VI[it.status], amount=money(it.amount),
                 why=it.title, action=it.action) for k, it in order]
    return ChatAnswer('top_risks', f'{len(rows)} khoản nên xử lý trước trong {_scope(p.period)}, xếp theo mức độ rồi số thuế:', rows,
                      [('invoice', 'Hóa đơn'), ('status', 'Mức'), ('amount', 'Thuế'), ('why', 'Lý do'), ('action', 'Việc cần làm')],
                      facts=[dict(keys=[k for k, _ in order])], links=[('Mở Việc cần xử lý', '#/viec')])


def by_issue(ctx, p, q):
    rep = ctx.report
    if not p.issue:
        names = '; '.join(it['name'] for it in ctx.catalog.get('issues', []))
        return ChatAnswer('by_issue', f'Chưa xác định được loại vấn đề trong câu hỏi. Các loại có thể hỏi: {names}.', branch='HELP')
    its = [it for it in _items(rep, None if any(c.startswith('R09_UN') for c in p.issue) else p.period, None, p.issue) if it.status != 'INFO']
    done = [it for it in _items(rep, p.period, ('INFO',), p.issue)]
    if not its:
        extra = ''
        if any(c.startswith('R12') for c in p.issue) and not (ctx.workspace / 'ai' / 'line_labels.json').exists():
            extra = ' Lưu ý: chưa chạy "Phân loại dòng hàng" nên hệ thống chưa xét hàng hóa có phục vụ kinh doanh không.'
        if any(c.startswith('R08') for c in p.issue) and not getattr(ctx.pack, 'reference_lists', None):
            extra = ' Lưu ý: chưa nhập danh sách rủi ro nào (trang quản trị), nên chưa so được.'
        if any(c.startswith('R09') for c in p.issue) and rep.meta['counts'].get('portal_rows') is None:
            extra = ' Lưu ý: chưa nạp bảng kê cổng thuế nên chưa so được.'
        if any(c.startswith(('R01', 'R02', 'R03')) for c in p.issue) and not rep.transactions:
            extra = ' Lưu ý: chưa nạp sao kê ngân hàng.'
        return ChatAnswer('by_issue', f'Trong {_scope(p.period)}: không có khoản nào đang mở thuộc loại "{p.issue_name}"'
                          + (f' ({len(done)} khoản đã được người duyệt xử lý).' if done else '.') + extra)
    rows = [dict(invoice=_inv_label(rep, it.invoice_keys[0]) if it.invoice_keys else it.detail[:80], status=STATUS_VI[it.status],
                 amount=money(it.amount), detail=(it.detail or it.title)[:160]) for it in its]
    total = sum(_per_invoice_risk([it for it in its if it.status == 'AT_RISK']).values(), ZERO)
    return ChatAnswer('by_issue', f'Trong {_scope(p.period)}: {len(its)} khoản thuộc loại "{p.issue_name}"'
                      + (f', thuế có nguy cơ {money(total)}' if total else '') + f'. Việc cần làm: {its[0].action}.', rows,
                      [('invoice', 'Hóa đơn'), ('status', 'Mức'), ('amount', 'Thuế'), ('detail', 'Chi tiết')],
                      facts=[dict(codes=p.issue, count=len(its), amount=str(total))], citations=sorted({b for it in its for b in it.basis}),
                      links=[('Mở Việc cần xử lý', '#/viec')])


# ----------------------------------------------------------------------------- TRA_CUU
def invoice_lookup(ctx, p, q):
    rep = ctx.report
    if not p.invoice_numbers:
        return ChatAnswer('invoice_lookup', 'Hãy ghi số hóa đơn cần tra, ví dụ: "hóa đơn số 125 có vấn đề gì?".', branch='HELP')
    found = [i for i in rep.invoices if i.number and i.number.isdigit() and str(int(i.number)) in p.invoice_numbers and not i.duplicate_of]
    if not found:
        return ChatAnswer('invoice_lookup', f'Không có hóa đơn số {", ".join(p.invoice_numbers)} trong dữ liệu đã nạp. '
                          'Kiểm tra lại số, hoặc nạp tệp XML của hóa đơn đó.')
    parts, facts, cites = [], [], set()
    for inv in found:
        its = [it for it in rep.items if inv.key in it.invoice_keys]
        mt = next((m for m in rep.matches if inv.key in m.invoice_keys), None)
        pay = ('đã ghép được chứng từ ngân hàng' if mt and mt.status == 'MATCHED' else
               'có giao dịch cùng số tiền cần xác nhận' if mt else 'chưa ghép được chứng từ ngân hàng')
        who = f'của {inv.seller_name}' if inv.role == 'PURCHASE' else f'bán cho {inv.buyer_name}'
        head = (f'Hóa đơn {inv.display} {who}, ngày {inv.issue_date:%d/%m/%Y}, tổng thanh toán {money(inv.gross or 0)}'
                f' (thuế {money(inv.vat or 0)}), {pay}.')
        if its:
            desc = ' '.join(f'{STATUS_VI[it.status]}: {it.title.lower()}' + (f' ({money(it.amount)})' if it.amount else '') + '.' for it in its)
            parts.append(f'{head} {desc} Việc cần làm: {its[0].action}.')
            cites |= {b for it in its for b in it.basis}
        else:
            parts.append(f'{head} Không có cảnh báo nào theo các luật đang chạy.')
        facts.append(dict(key=inv.key, items=[it.code for it in its]))
    ans = ChatAnswer('invoice_lookup', ' '.join(parts), facts=facts, citations=sorted(cites),
                     links=[('Xem trong Việc cần xử lý', f'#/viec?open={found[0].key}')])
    return ans


def seller_lookup(ctx, p, q):
    rep = ctx.report
    if not p.seller:
        return ChatAnswer('seller_lookup', 'Không xác định được người bán trong câu hỏi, hoặc người bán đó không có trong dữ liệu. Hãy ghi mã số thuế '
                          'hoặc phần tên riêng của người bán (ví dụ "Phương Nam", không cần "Công ty TNHH").', branch='HELP')
    invs = [i for i in _invoices(rep, 'PURCHASE', p.period) if i.seller_tax_id == p.seller]
    keys = {i.key for i in invs}
    its = [it for it in rep.items if keys & set(it.invoice_keys) and it.status != 'INFO']
    risk = sum(_per_invoice_risk([it for it in its if it.status == 'AT_RISK']).values(), ZERO)
    rows = [dict(invoice=i.display, day=f'{i.issue_date:%d/%m/%Y}' if i.issue_date else '', gross=money(i.gross or 0),
                 issues='; '.join(sorted({it.title for it in its if i.key in it.invoice_keys})) or 'không có cảnh báo') for i in invs]
    text = (f'{p.seller_text} (mã số thuế {p.seller}) trong {_scope(p.period)}: {len(invs)} hóa đơn, tổng thanh toán '
            f'{money(sum((i.gross or 0) for i in invs))}, thuế đầu vào {money(sum((i.vat or 0) for i in invs))}; '
            f'{len({k for it in its for k in it.invoice_keys if k in keys})} hóa đơn có cảnh báo, thuế có nguy cơ {money(risk)}.')
    return ChatAnswer('seller_lookup', text, rows, [('invoice', 'Hóa đơn'), ('day', 'Ngày'), ('gross', 'Tổng tiền'), ('issues', 'Cảnh báo')],
                      facts=[dict(seller=p.seller, invoices=len(invs), risk=str(risk))])


def top_sellers(ctx, p, q):
    rep = ctx.report
    invs = _invoices(rep, 'PURCHASE', p.period)
    if not invs:
        return _no_data('hóa đơn mua vào', 'top_sellers')
    risk = _per_invoice_risk(_items(rep, p.period, ('AT_RISK',)))
    agg = defaultdict(lambda: dict(name='', n=0, gross=ZERO, risk=ZERO))
    for i in invs:
        a = agg[i.seller_tax_id]
        a['name'] = i.seller_name or i.seller_tax_id
        a['n'] += 1
        a['gross'] += i.gross or 0
        a['risk'] += risk.get(i.key, ZERO)
    key = (lambda kv: -kv[1]['gross']) if p.rank_by == 'amount' else (lambda kv: (-kv[1]['risk'], -kv[1]['gross']))
    order = sorted(agg.items(), key=key)[:p.top_n or 5]
    rows = [dict(seller=a['name'], tax=t, n=a['n'], gross=money(a['gross']), risk=money(a['risk'])) for t, a in order]
    by = 'tổng tiền mua' if p.rank_by == 'amount' else 'thuế có nguy cơ, rồi tới tổng tiền mua'
    return ChatAnswer('top_sellers', f'Người bán xếp theo {by}, {_scope(p.period)}:', rows,
                      [('seller', 'Người bán'), ('tax', 'Mã số thuế'), ('n', 'Số hóa đơn'), ('gross', 'Tổng tiền'), ('risk', 'Thuế có nguy cơ')])


# ----------------------------------------------------------------------------- SO_LIEU
def _period_key(d, quarterly):
    return f'Quý {(d.month - 1) // 3 + 1}/{d.year}' if quarterly else f'Tháng {d.month:02d}/{d.year}'


def _vat_rows(ctx, period):
    return {r['period']: dict(r, input=r['input_vat'], output=r['output_vat'], risk=r['at_risk']) for r in _vat_view(ctx, period)['rows']}


def _vat_view(ctx, period):
    rep = accounting.data(ctx.report)
    keys = {i.key for i in _invoices(ctx.report, None, period)}
    rep['invoices'] = [i for i in rep['invoices'] if i['key'] in keys]
    return accounting.vat_summary(rep, dict(filing_period=ctx.pack.filing_period, vat_method=ctx.pack.vat_method), ctx.declared())


def purchase_summary(ctx, p, q):
    rep = ctx.report
    invs = _invoices(rep, 'PURCHASE', p.period)
    if not invs:
        return _no_data('hóa đơn mua vào', 'purchase_summary')
    risk = _per_invoice_risk(_items(rep, p.period, ('AT_RISK',)))
    net, vat = sum((i.net or 0) for i in invs), sum((i.vat or 0) for i in invs)
    at = sum((risk.get(i.key, ZERO) for i in invs), ZERO)
    rows = [dict(period=k, n=r['purchases'], vat=money(r['input']), risk=money(r['risk']), safe=money(r['no_alert_vat']))
            for k, r in _vat_rows(ctx, p.period).items() if r['purchases']]
    return ChatAnswer('purchase_summary', f'Mua vào trong {_scope(p.period)}: {len(invs)} hóa đơn, tiền hàng trước thuế {money(net)}, '
                      f'thuế GTGT đầu vào {money(vat)}; trong đó có nguy cơ bị loại {money(at)}. '
                      'Không tính bản nhập trùng; phần không kê khai và chờ xem xét được tách ở trang GTGT.', rows,
                      [('period', 'Kỳ'), ('n', 'Số hóa đơn'), ('vat', 'Thuế đầu vào'), ('risk', 'Có nguy cơ'), ('safe', 'Chưa phát hiện cảnh báo')],
                      facts=[dict(n=len(invs), net=str(net), vat=str(vat), at_risk=str(at))])


def sales_summary(ctx, p, q):
    rep = ctx.report
    invs = _invoices(rep, 'SALE', p.period)
    if not invs:
        return _no_data('hóa đơn bán ra', 'sales_summary')
    net, vat = sum((i.net or 0) for i in invs), sum((i.vat or 0) for i in invs)
    cust = defaultdict(lambda: [0, ZERO, ''])
    for i in invs:
        c = cust[i.buyer_tax_id or i.buyer_name]
        c[0] += 1
        c[1] += i.net or 0
        c[2] = i.buyer_name or i.buyer_tax_id or 'không rõ'
    rows = [dict(customer=c[2], n=c[0], net=money(c[1])) for c in sorted(cust.values(), key=lambda c: -c[1])[:p.top_n or 5]]
    return ChatAnswer('sales_summary', f'Bán ra trong {_scope(p.period)}: {len(invs)} hóa đơn, doanh thu trước thuế {money(net)}, '
                      f'thuế GTGT đầu ra {money(vat)}. Khách hàng theo doanh thu:', rows,
                      [('customer', 'Khách hàng'), ('n', 'Số hóa đơn'), ('net', 'Doanh thu trước thuế')],
                      facts=[dict(n=len(invs), net=str(net), vat=str(vat))])


def vat_payable(ctx, p, q):
    view = _vat_view(ctx, p.period)
    if view['calculation_status'] == 'UNSUPPORTED_DIRECT':
        return ChatAnswer('vat_payable', view['note'], facts=[dict(vat_method='DIRECT', calculation_status='UNSUPPORTED_DIRECT')], links=[('Mở Số liệu thuế GTGT', '#/so-lieu')])
    if not view['rows']:
        return _no_data(domain='vat_payable')
    rows = []
    def balance(value):
        if value is None:
            return 'Chưa đủ dữ liệu'
        return ('Đầu ra vượt đầu vào ' if value >= 0 else 'Đầu vào vượt đầu ra ') + money(abs(value))
    for r in view['rows']:
        rows.append(dict(period=r['period'], output=money(r['output_vat']), input=money(r['no_alert_vat']),
                         review=money(r['review_vat']), excluded=money(r['not_claimed_vat']),
                         without_review=balance(r['scenario_without_review']), with_review=balance(r['scenario_with_review'])))
    last = view['rows'][-1]
    text = (f'{last["period"]}: chưa tính phần chờ duyệt: {balance(last["scenario_without_review"])}; '
            f'giả định phần chờ duyệt được chấp nhận: {balance(last["scenario_with_review"])}. ' + view['note'])
    return ChatAnswer('vat_payable', text, rows, [('period', 'Kỳ'), ('output', 'Thuế đầu ra'), ('input', 'Chưa phát hiện cảnh báo'),
                                                 ('review', 'Chờ duyệt'), ('excluded', 'Không kê khai'), ('without_review', 'Chưa tính chờ duyệt'), ('with_review', 'Nếu chờ duyệt được chấp nhận')],
                      facts=[dict(period=r['period'], net_min=str(r['net_min']) if r['net_min'] is not None else None,
                                  net_max=str(r['net_max']) if r['net_max'] is not None else None) for r in view['rows']],
                      links=[('Mở Số liệu thuế GTGT', '#/so-lieu')])


# ----------------------------------------------------------------------------- THANH_TOAN
def bank_matching(ctx, p, q):
    rep = ctx.report
    if not rep.transactions:
        return ChatAnswer('bank_matching', 'Chưa nạp sao kê ngân hàng nên chưa đối chiếu được thanh toán. Nạp sao kê (Excel, CSV hoặc MT940) trước.',
                          links=[('Nạp dữ liệu', '#/nap')])
    rs = load_ruleset(ctx.ruleset_path)
    thr = Decimal(str(param(rs, 'NON_CASH_THRESHOLD', ctx.as_of)[0]))
    invs = [i for i in _invoices(rep, 'PURCHASE', p.period) if (i.gross or 0) >= thr]
    keys = {i.key for i in invs}
    matched = {k for m in rep.matches if m.status == 'MATCHED' for k in m.invoice_keys} & keys
    amb = {k for m in rep.matches if m.status == 'AMBIGUOUS' for k in m.invoice_keys} & keys - matched
    none = keys - matched - amb
    rows = [dict(invoice=_inv_label(rep, k), state='cần xác nhận' if k in amb else 'chưa thấy thanh toán') for k in sorted(amb | none)]
    outs = [t for t in rep.transactions if t.direction == 'OUT' and (p.period.is_all or p.period.contains(t.booked))]
    return ChatAnswer('bank_matching', f'Trong {_scope(p.period)}: {len(invs)} hóa đơn mua vào từ ngưỡng {money(thr)}; {len(matched)} đã ghép được chứng từ ngân hàng, '
                      f'{len(amb)} có giao dịch cùng số tiền cần xác nhận, {len(none)} chưa thấy thanh toán trong sao kê. '
                      f'Sao kê có {len(outs)} giao dịch chi trong kỳ.', rows, [('invoice', 'Hóa đơn'), ('state', 'Tình trạng')],
                      facts=[dict(matched=len(matched), ambiguous=len(amb), unmatched=len(none))], links=[('Mở Việc cần xử lý', '#/viec')])


def receipts_no_invoice(ctx, p, q):
    rep = ctx.report
    if not rep.transactions or not _invoices(rep, 'SALE'):
        return ChatAnswer('receipts_no_invoice', 'Cần nạp cả sao kê ngân hàng và hóa đơn bán ra thì mới đối chiếu được tiền khách trả.',
                          links=[('Nạp dữ liệu', '#/nap')])
    its = [it for it in _items(rep, p.period, None, ['R14']) if it.status != 'INFO']
    rows = [dict(detail=it.detail) for it in its]
    text = ((f'Trong {_scope(p.period)}: {len(its)} khoản tiền khách trả chưa đối chiếu được với hóa đơn bán ra. Việc cần làm: {its[0].action}.')
            if its else f'Trong {_scope(p.period)}: mọi khoản tiền vào đều khớp với hóa đơn bán ra cùng số tiền.')
    return ChatAnswer('receipts_no_invoice', text, rows, [('detail', 'Khoản tiền')], citations=sorted({b for it in its for b in it.basis}))


# ----------------------------------------------------------------------------- HAN_PHAT
def deadlines(ctx, p, q):
    rep = ctx.report
    cal = rep.calendar
    if not cal:
        return ChatAnswer('deadlines', 'Chưa có hóa đơn nên chưa xác định được kỳ khai và hạn nộp.')
    if not p.period.is_all:
        tag = (f'quý {p.period.quarter}/{p.period.year}' if p.period.quarter else f'tháng {p.period.month:02d}/{p.period.year}' if p.period.month
               else f'{p.period.year}')
        sel = [c for c in cal if tag in c['period'].lower()]
        cal = sel or cal
    upcoming = [c for c in cal if c['due'] >= ctx.as_of]
    nxt = upcoming[0] if upcoming else cal[-1]
    rows = [dict(period=c['period'], due=f'{c["due"]:%d/%m/%Y}', status=c['status'], note=c.get('note', '')) for c in cal]
    return ChatAnswer('deadlines', f'{"Hạn gần nhất" if upcoming else "Hạn gần nhất đã qua"}: {nxt["period"]}, ngày {nxt["due"]:%d/%m/%Y} ({nxt["status"]}). '
                      f'Doanh nghiệp khai thuế GTGT {"theo quý" if ctx.pack.filing_period == "QUARTER" else "theo tháng"}.', rows,
                      [('period', 'Nghĩa vụ'), ('due', 'Hạn'), ('status', 'Tình trạng'), ('note', 'Ghi chú')],
                      citations=sorted({c['basis'] for c in cal}))


def penalty_exposure(ctx, p, q):
    values = accounting.exposure(ctx.report, load_ruleset(ctx.ruleset_path))
    allowed = {i.finding_id for i in _items(ctx.report, p.period, ('AT_RISK',))}
    unique = {r['invoice_key']: r for r in values.values() if r['finding_id'] in allowed}
    rows = [dict(invoice=_inv_label(ctx.report, k), amount=money(r['amount']) if r['amount'] is not None else None,
                 days=r['days_late'], interest=money(r['interest']) if r['interest'] is not None else None,
                 penalty=money(r['penalty']) if r['penalty'] is not None else None) for k, r in unique.items()]
    return ChatAnswer('penalty_exposure', accounting.EXPOSURE_NOTE, rows,
                      [('invoice', 'Hóa đơn'), ('amount', 'Thuế theo giả định'), ('days', 'Ngày sau hạn lịch'),
                       ('interest', 'Chậm nộp theo giả định'), ('penalty', 'Phạt theo giả định')],
                      facts=list(unique.values()), citations=sorted({b for r in unique.values() for b in r['basis']}))


def what_if_evidence(ctx, p, q):
    rep = ctx.report
    keys = [i.key for i in rep.invoices if i.number and i.number.isdigit() and str(int(i.number)) in p.invoice_numbers and not i.duplicate_of]
    if not keys:
        return ChatAnswer('what_if_evidence', 'Hãy ghi số hóa đơn cần giả định, ví dụ: "nếu bổ sung chứng từ chuyển khoản cho hóa đơn 125 thì còn bao nhiêu?".'
                          if not p.invoice_numbers else f'Không có hóa đơn số {", ".join(p.invoice_numbers)} trong dữ liệu.', branch='HELP')
    from .. import pipeline
    extra = {k: dict(invoice_key=k, action='PAYMENT_EVIDENCE_ATTACHED', evidence='GIẢ ĐỊNH (chưa có chứng từ thật)', by='câu hỏi giả định') for k in keys}
    after = pipeline.run(ctx.workspace, ctx.ruleset_path, ctx.as_of, extra).totals
    before = rep.totals
    delta = before['at_risk_vat'] - after['at_risk_vat']
    note = '' if delta else ' Số không đổi vì vấn đề của các hóa đơn này không phải do thiếu chứng từ chuyển khoản.'
    return ChatAnswer('what_if_evidence', f'Giả định có chứng từ chuyển khoản cho {len(keys)} hóa đơn ({", ".join(_inv_label(rep, k) for k in keys)}): '
                      f'thuế có nguy cơ giảm từ {money(before["at_risk_vat"])} xuống {money(after["at_risk_vat"])} (giảm {money(delta)}).{note} '
                      'Đây là kết quả chạy lại với giả định, không ghi vào dữ liệu.',
                      facts=[dict(invoice_keys=keys, before=str(before['at_risk_vat']), after=str(after['at_risk_vat']))])


# ----------------------------------------------------------------------------- VIEC_LAM
def next_actions(ctx, p, q):
    rep = ctx.report
    if not rep.invoices:
        return ChatAnswer('next_actions', 'Bước đầu tiên: nạp hóa đơn mua vào (XML), sao kê ngân hàng và bảng kê cổng thuế ở trang Nạp dữ liệu.',
                          links=[('Nạp dữ liệu', '#/nap')])
    open_its = _items(rep, p.period, ('AT_RISK', 'REVIEW', 'OPPORTUNITY'))
    upcoming = [c for c in rep.calendar if c['due'] >= ctx.as_of]
    groups = defaultdict(lambda: [0, ZERO, ''])
    for it in open_its:
        g = groups[it.title]
        g[0] += 1
        g[1] += it.amount
        g[2] = it.action
    rows = [dict(work=t, n=n, amount=money(a), action=act) for t, (n, a, act) in sorted(groups.items(), key=lambda kv: -kv[1][1])]
    text = f'Còn {len(open_its)} việc chưa xử lý trong {_scope(p.period)}.'
    if upcoming:
        text += f' Hạn gần nhất: {upcoming[0]["period"]} ngày {upcoming[0]["due"]:%d/%m/%Y} ({upcoming[0]["status"]}).'
    c = rep.meta['counts']
    missing = [w for w, n in (('sao kê ngân hàng', c['bank_transactions']), ('bảng kê cổng thuế', c['portal_rows']), ('hóa đơn bán ra', c['sales_invoices'])) if not n]
    if missing:
        text += f' Nên nạp thêm: {", ".join(missing)}.'
    if rows:
        text += ' Xử lý theo thứ tự trong bảng (số tiền lớn trước):'
    return ChatAnswer('next_actions', text, rows, [('work', 'Việc'), ('n', 'Số khoản'), ('amount', 'Thuế liên quan'), ('action', 'Cách xử lý')],
                      links=[('Mở Việc cần xử lý', '#/viec')])


def data_status(ctx, p, q):
    rep = ctx.report
    c = rep.meta['counts']
    per = rep.meta.get('period')
    text = (f'Đã nạp {c["purchase_invoices"]} hóa đơn mua vào, {c["sales_invoices"]} hóa đơn bán ra, {c["bank_transactions"]} giao dịch ngân hàng, '
            + (f'bảng kê cổng thuế {c["portal_rows"]} dòng' if c['portal_rows'] is not None else 'chưa có bảng kê cổng thuế')
            + (f'; hóa đơn từ {per[0]:%d/%m/%Y} đến {per[1]:%d/%m/%Y}' if per else '') + '.')
    bad = rep.meta.get('unreadable') or []
    if bad:
        text += f' Có {len(bad)} tệp không đọc được (xem bảng).'
    months_inv = sorted({(i.issue_date.year, i.issue_date.month) for i in rep.invoices if i.issue_date})
    months_bank = {(t.booked.year, t.booked.month) for t in rep.transactions}
    gap = [f'{m:02d}/{y}' for y, m in months_inv if (y, m) not in months_bank]
    if rep.transactions and gap:
        text += f' Sao kê chưa có các tháng: {", ".join(gap)}.'
    elif not rep.transactions:
        text += ' Chưa có sao kê ngân hàng: mọi hóa đơn từ ngưỡng sẽ hiện là chưa có chứng từ thanh toán.'
    dups = [i for i in rep.invoices if i.duplicate_of]
    if dups:
        text += f' {len(dups)} tệp là bản trùng của hóa đơn đã có (không tính hai lần).'
    rows = [dict(file=str(b)[:160]) for b in bad]
    return ChatAnswer('data_status', text, rows, [('file', 'Tệp không đọc được')], links=[('Nạp dữ liệu', '#/nap')])


def decisions_log(ctx, p, q):
    ds = decision_store.history(ctx.workspace)
    if not ds:
        return ChatAnswer('decisions_log', 'Chưa có quyết định nào được ghi nhận. Quyết định được ghi khi người duyệt xử lý một việc trong trang Việc cần xử lý.',
                          links=[('Mở Việc cần xử lý', '#/viec')])
    names = {'PAYMENT_EVIDENCE_ATTACHED': 'đã bổ sung chứng từ', 'NOT_CLAIMED': 'không kê khai khấu trừ', 'CONFIRMED_OK': 'xác nhận không có vấn đề'}
    rows = [dict(invoice=_inv_label(ctx.report, d.get('invoice_key', d.get('subject', ''))), action=names.get(d['action'], d['action']), evidence=d.get('evidence', ''),
                 by=d.get('by', ''), at=d.get('at', d.get('decided_at', ''))) for d in ds]
    cnt = defaultdict(int)
    for d in ds:
        cnt[names.get(d['action'], d['action'])] += 1
    return ChatAnswer('decisions_log', f'Đã ghi {len(ds)} quyết định: ' + '; '.join(f'{v} {k}' for k, v in cnt.items()) + '.', rows,
                      [('invoice', 'Hóa đơn'), ('action', 'Quyết định'), ('evidence', 'Chứng từ, lý do'), ('by', 'Người duyệt'), ('at', 'Thời điểm')])


def company_profile(ctx, p, q):
    pk = ctx.pack
    pols = '; '.join(x.flag for x in getattr(pk, 'policies', []) or []) or 'chưa bật quy định nào'
    method = getattr(pk, 'vat_method', None)
    text = (f'{pk.legal_name}, mã số thuế {pk.tax_code}. '
            + (f'Phương pháp tính thuế GTGT: {"khấu trừ" if method in (None, "DEDUCTION", "KHAU_TRU") else method}. ' )
            + f'Kỳ khai: {"theo quý" if pk.filing_period == "QUARTER" else "theo tháng"}; năm tài chính kết thúc tháng {getattr(pk, "fiscal_year_end_month", 12)}. '
            f'Ngành nghề: {"; ".join(getattr(pk, "industry", []) or []) or "chưa khai"}. Quy định chi tiêu đang áp dụng: {pols}. '
            'Muốn sửa, vào trang quản trị (cần mật khẩu).')
    return ChatAnswer('company_profile', text)


# ----------------------------------------------------------------------------- LUAT
def law_question(ctx, p, q):
    grounded = ctx.law(q)
    if grounded is None:
        return ChatAnswer('law_question', 'Chưa có kho luật trên máy nên không trả lời được câu hỏi về quy định.', branch='POLICY')
    if grounded.mode == 'ABSTAIN':
        return ChatAnswer('law_question', 'Kho luật không có căn cứ đủ để trả lời câu này, nên trợ lý không trả lời. ' + grounded.note,
                          facts=[grounded.to_dict()], branch='POLICY')
    prefix = '' if grounded.mode == 'LLM_VERIFIED' else 'Trích nguyên văn các điều khoản liên quan nhất (câu trả lời của mô hình không qua kiểm tra căn cứ): '
    return ChatAnswer('law_question', prefix + ' '.join(f'{s["text"]} [{_cite(s)}]' for s in grounded.sentences),
                      facts=[grounded.to_dict()], citations=sorted({_cite(s) for s in grounded.sentences}), branch='POLICY')


def law_updates(ctx, p, q):
    rows = ctx.law_alerts()
    if rows is None:
        return ChatAnswer('law_updates', 'Chưa có kho luật trên máy.', branch='POLICY')
    rows = rows[:10]
    if not rows:
        return ChatAnswer('law_updates', 'Kho luật không có văn bản về thuế, hóa đơn, kế toán doanh nghiệp nào vừa hoặc sắp thay đổi hiệu lực.', branch='POLICY')
    out = [dict(doc=f'{r["doc_type"]} {r["doc_num"]}', title=r['title'][:140], change='có hiệu lực' if r['kind'] == 'EFFECTIVE' else 'hết hiệu lực',
                day=date.fromisoformat(r['day'][:10]).strftime('%d/%m/%Y') if r.get('day') else '') for r in rows]
    return ChatAnswer('law_updates', f'{len(out)} văn bản liên quan đến doanh nghiệp vừa hoặc sắp thay đổi hiệu lực (theo kho luật đã đồng bộ):', out,
                      [('doc', 'Văn bản'), ('title', 'Trích yếu'), ('change', 'Thay đổi'), ('day', 'Ngày')], branch='POLICY',
                      links=[('Mở Tin luật mới', '#/tin-luat')])


def judgment(ctx, p, q):
    rs = load_ruleset(ctx.ruleset_path)
    thr = param(rs, 'NON_CASH_THRESHOLD', ctx.as_of)
    refs = ctx.law(q)
    ok = refs is not None and refs.mode != 'ABSTAIN'
    text = ('Câu này cần người có chuyên môn kết luận theo hồ sơ thực tế; trợ lý không kết luận được hay không được. Các điều kiện thường phải xét: '
            'khoản chi thực tế phát sinh và phục vụ hoạt động kinh doanh; có hóa đơn, chứng từ hợp pháp; '
            f'từ {money(thr[0])} phải có chứng từ thanh toán không dùng tiền mặt; không thuộc nhóm khoản chi không được trừ. '
            'Hãy chuẩn bị hóa đơn, chứng từ thanh toán, giấy tờ chứng minh mục đích chi.')
    if ok:
        text += ' Điều khoản liên quan trong kho luật: ' + ' '.join(f'{s["text"]} ({_cite(s)})' for s in refs.sentences)
    return ChatAnswer('judgment', text, facts=[refs.to_dict()] if refs else [], branch='JUDGMENT',
                      citations=[thr[1]] + (sorted({_cite(s) for s in refs.sentences}) if ok else []))


def help_(ctx, p, q):
    groups = {g['id']: g['title'] for g in ctx.catalog['groups']}
    return ChatAnswer('help', 'Trợ lý trả lời được các loại câu hỏi dưới đây. Bấm "Trợ lý trả lời được gì" để xem câu ví dụ của từng loại.',
                      [dict(group=groups[d['group']], title=d['title'], what=d['what']) for d in ctx.catalog['domains'] if d['id'] != 'help'],
                      [('group', 'Nhóm'), ('title', 'Loại câu hỏi'), ('what', 'Trả lời được')], branch='HELP')


HANDLERS = dict(risk_total=risk_total, missed_deduction=missed_deduction, top_risks=top_risks, by_issue=by_issue,
                invoice_lookup=invoice_lookup, seller_lookup=seller_lookup, top_sellers=top_sellers, purchase_summary=purchase_summary,
                sales_summary=sales_summary, vat_payable=vat_payable, bank_matching=bank_matching, receipts_no_invoice=receipts_no_invoice,
                deadlines=deadlines, penalty_exposure=penalty_exposure, what_if_evidence=what_if_evidence, next_actions=next_actions,
                data_status=data_status, decisions_log=decisions_log, company_profile=company_profile, law_question=law_question,
                law_updates=law_updates, judgment=judgment, help=help_)
