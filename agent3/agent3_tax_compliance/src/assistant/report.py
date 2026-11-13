"""Step 8 output: the report the accountant reads (HTML), a Markdown summary, and machine-readable JSON."""
import dataclasses
import html
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Report

STATUS_VI = {'AT_RISK': 'Có nguy cơ bị loại', 'REVIEW': 'Cần xem xét', 'OPPORTUNITY': 'Có thể đang bỏ sót', 'INFO': 'Thông tin'}
METHOD_VI = {'ACCOUNT': 'đúng tài khoản người bán', 'NAME_OR_TAX_ID': 'tên hoặc mã số thuế người bán', 'INVOICE_NUMBER': 'số hóa đơn trong nội dung',
             'SPLIT_PAYMENTS': 'trả nhiều lần', 'COMBINED_PAYMENT': 'một lần trả nhiều hóa đơn', 'AMOUNT_ONLY': 'chỉ trùng số tiền',
             'DECISION': 'người duyệt xác nhận'}


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, date):
        return o.isoformat()
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    raise TypeError(type(o))


def to_json(report: Report) -> str:
    return json.dumps(dataclasses.asdict(report), default=_default, ensure_ascii=False, indent=2)


def money(v) -> str:
    if v is None:
        return 'Chưa đủ dữ liệu'
    return f'{Decimal(v):,.0f}'.replace(',', '.') + ' đ'


def _inv_label(report, key):
    inv = next((i for i in report.invoices if i.key == key and not i.duplicate_of), None) or next((i for i in report.invoices if i.key == key), None)
    if not inv:
        return key, '', ''
    return inv.display, inv.seller_name or inv.seller_tax_id or '', inv.issue_date.strftime('%d/%m/%Y') if inv.issue_date else ''


def to_markdown(report: Report) -> str:
    t, m = report.totals, report.meta
    lines = [f'# Báo cáo rủi ro thuế: {m["company"]}', '',
             f'Ngày lập: {m["as_of"]:%d/%m/%Y}. Bộ luật: {m["ruleset_version"]} ({m["ruleset_status"]}).' + (' **Dữ liệu mô phỏng.**' if m['simulated'] else ''), '',
             f'- Thuế đầu vào có nguy cơ bị loại: **{money(t["at_risk_vat"])}** ({t["at_risk_invoices"]} hóa đơn)',
             f'- Ước tính phạt tối đa nếu bị xác định khai sai ({t["penalty_rate"] * 100:.0f}%): {money(t["penalty_estimate"])}',
             f'- Cần xem xét: {money(t["review_vat"])} ({t["review_invoices"]} hóa đơn)',
             f'- Có thể đang bỏ sót khấu trừ: {money(t["opportunity_vat"])}', '',
             '| Trạng thái | Mã | Hóa đơn | Người bán | Số tiền | Lý do | Việc cần làm |', '|---|---|---|---|---:|---|---|']
    for it in report.items:
        label, seller, _ = _inv_label(report, it.invoice_keys[0]) if it.invoice_keys else ('', '', '')
        lines.append(f'| {STATUS_VI[it.status]} | {it.code} | {label} | {seller} | {money(it.amount)} | {it.title}. {it.detail} | {it.action} |')
    lines += ['', '## Hạn kê khai', ''] + [f'- {c["period"]}: {c["due"]:%d/%m/%Y} ({c["status"]})' for c in report.calendar]
    lines += ['', '## Giới hạn', ''] + [f'- {x}' for x in m['limitations']]
    return '\n'.join(lines) + '\n'


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#5f6368;--line:#e2e2de;--risk:#b3261e;--review:#9a6700;--ok:#1e7a46;--opp:#1a5fb4}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;--muted:#a3a29c;--line:#34342f;--risk:#f2b8b5;--review:#f0c674;--ok:#8fd19e;--opp:#9cc3ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.muted{color:var(--muted)}.banner{border:1px solid var(--review);color:var(--review);padding:8px 12px;border-radius:8px;margin:12px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi.risk b{color:var(--risk)}.kpi.review b{color:var(--review)}.kpi.opp b{color:var(--opp)}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);background:var(--bg)}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid currentColor;white-space:nowrap}
.AT_RISK{color:var(--risk)}.REVIEW{color:var(--review)}.OPPORTUNITY{color:var(--opp)}.INFO{color:var(--muted)}
details summary{cursor:pointer;color:var(--muted)}ul{margin:6px 0 0 18px;padding:0}code{font-size:12px}
"""


def to_html(report: Report) -> str:
    e = html.escape
    t, m = report.totals, report.meta
    rows = []
    for it in report.items:
        label, seller, day = _inv_label(report, it.invoice_keys[0]) if it.invoice_keys else ('', '', '')
        basis = ''.join(f'<li>{e(b)}</li>' for b in it.basis)
        rows.append(f'<tr><td><span class="tag {it.status}">{STATUS_VI[it.status]}</span></td><td>{e(label)}<div class="muted">{e(day)}</div></td>'
                    f'<td>{e(seller)}</td><td class="num">{money(it.amount)}</td><td><b>{e(it.title)}</b><div class="muted">{e(it.detail)}</div></td>'
                    f'<td>{e(it.action)}<details><summary>Căn cứ</summary><ul>{basis}</ul></details></td></tr>')
    by_method = {}
    for mt in report.matches:
        by_method[(mt.status, mt.method)] = by_method.get((mt.status, mt.method), 0) + len(mt.invoice_keys)
    match_rows = ''.join(f'<tr><td>{"Đã ghép" if s == "MATCHED" else "Mơ hồ"}</td><td>{e(METHOD_VI[mm])}</td><td class="num">{n}</td></tr>'
                         for (s, mm), n in sorted(by_method.items()))
    cal_rows = ''.join(f'<tr><td>{e(c["period"])}</td><td>{c["due"]:%d/%m/%Y}</td><td>{e(c["status"])}</td><td class="muted">{e(c["basis"])}. {e(c["note"])}</td></tr>'
                       for c in report.calendar)
    flags = ''.join(f'<tr><td>{e(_inv_label(report, f.invoice_keys[0])[0])}</td><td>{e(f.title)}</td></tr>' for f in report.policy_flags)
    limits = ''.join(f'<li>{e(x)}</li>' for x in m['limitations'] + [f'Tệp không đọc được: {u}' for u in m['unreadable']])
    period = f'{m["period"][0]:%d/%m/%Y} đến {m["period"][1]:%d/%m/%Y}' if m['period'] else 'không có'
    c = m['counts']
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo rủi ro thuế</title><style>{CSS}</style></head><body><main>
<h1>Báo cáo rủi ro thuế: {e(m['company'])}</h1>
<div class="muted">MST {e(m['tax_code'])}. Dữ liệu từ {period}. Ngày lập {m['as_of']:%d/%m/%Y}.</div>
{'<div class="banner">Dữ liệu mô phỏng, không phải doanh nghiệp thật.</div>' if m['simulated'] else ''}
<div class="banner">Bộ luật {e(m['ruleset_version'])} đang ở trạng thái {e(m['ruleset_status'])}. {e(m['ruleset_note'])}</div>
<div class="kpis">
<div class="kpi risk">Thuế đầu vào có nguy cơ bị loại<b>{money(t['at_risk_vat'])}</b><span class="muted">{t['at_risk_invoices']} hóa đơn</span></div>
<div class="kpi risk">Ước tính phạt tối đa nếu bị xác định khai sai<b>{money(t['penalty_estimate'])}</b><span class="muted">{t['penalty_rate'] * 100:.0f}%; {e(t['penalty_basis'])}</span></div>
<div class="kpi review">Cần xem xét<b>{money(t['review_vat'])}</b><span class="muted">{t['review_invoices']} hóa đơn</span></div>
<div class="kpi opp">Có thể đang bỏ sót khấu trừ<b>{money(t['opportunity_vat'])}</b><span class="muted">hóa đơn trên cổng chưa có tệp</span></div>
</div>
<h2>Việc cần xử lý, xếp theo số tiền</h2>
<div class="wrap"><table><thead><tr><th>Trạng thái</th><th>Hóa đơn</th><th>Người bán</th><th>Số tiền</th><th>Lý do</th><th>Việc cần làm</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6">Không có khoản nào.</td></tr>'}</tbody></table></div>
<h2>Ghép hóa đơn với sao kê</h2>
<p class="muted">{c['purchase_invoices']} hóa đơn mua vào, {c['bank_transactions']} giao dịch ngân hàng.</p>
<div class="wrap"><table><thead><tr><th>Kết quả</th><th>Cách ghép</th><th>Số hóa đơn</th></tr></thead><tbody>{match_rows}</tbody></table></div>
<h2>Hạn nộp tờ khai thuế giá trị gia tăng</h2>
<div class="wrap"><table><thead><tr><th>Kỳ</th><th>Hạn</th><th>Tình trạng</th><th>Căn cứ</th></tr></thead><tbody>{cal_rows}</tbody></table></div>
<h2>Cờ theo chính sách nội bộ</h2>
<div class="wrap"><table><thead><tr><th>Hóa đơn</th><th>Cờ</th></tr></thead><tbody>{flags or '<tr><td colspan="2">Không có.</td></tr>'}</tbody></table></div>
<h2>Giới hạn và truy vết</h2><ul>{limits}</ul>
<p class="muted">Mã băm dữ liệu đầu vào: <code>{m['input_sha256']}</code>. Cùng dữ liệu và cùng bộ luật cho cùng báo cáo.</p>
</main></body></html>"""


def write(report: Report, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = dict(json=out_dir / 'report.json', markdown=out_dir / 'report.md', html=out_dir / 'report.html')
    # Render everything before publishing; JSON is the commit marker read by the API.
    content = dict(json=to_json(report), markdown=to_markdown(report), html=to_html(report))
    for kind in ('markdown', 'html', 'json'):
        tmp = paths[kind].with_suffix(paths[kind].suffix + '.tmp')
        tmp.write_text(content[kind], encoding='utf-8')
        tmp.replace(paths[kind])
    return paths
