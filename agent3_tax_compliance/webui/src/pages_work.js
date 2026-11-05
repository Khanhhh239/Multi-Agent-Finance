// Overview, data intake and the review queue.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loadWorkspaces, loading, money, needWorkspace, notice, post, put,
  state, store, table, tag } from './core.js';
import { aiToolbar, explainBox } from './pages_ai.js';
import { deadlineBanner, freshBanner, nextSteps, sellerWatch, toast } from './ux.js';

const itemId = (it) => `${it.code}|${it.invoice_keys.join(',')}`;

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageOverview() {
  if (!state.ws) {
    state.schema ||= await api('/api/schema');
    app().innerHTML = `<h1 class="page">Bắt đầu</h1>
      <p class="lead">Agent 3 đọc hóa đơn điện tử, sao kê ngân hàng và bảng kê của doanh nghiệp, đối chiếu với luật thuế theo đúng ngày, rồi chỉ ra khoản thuế có nguy cơ bị loại, căn cứ và việc cần làm. Mọi dữ liệu xử lý trên máy này.</p>
      <div class="grid2"><div class="panel"><h3>Tạo hồ sơ doanh nghiệp</h3><form id="new-ws"><div class="form-grid">
      ${state.schema.profile.map((f) => field(f, f.type === 'choice' ? f.choices[0][0] : '')).join('')}</div>
      <div class="bar">${button('Tạo hồ sơ', 'primary', 'type="submit"')}</div><div id="new-ws-msg"></div></form></div>
      <div class="panel"><h3>Xem thử với dữ liệu mô phỏng</h3><p class="muted">Một doanh nghiệp mô phỏng có hóa đơn, sao kê của hai ngân hàng và bảng kê, cài sẵn các tình huống rủi ro để thử toàn bộ luồng.</p>
      ${button('Tạo doanh nghiệp mô phỏng', 'tertiary', 'id="demo"')}<div id="demo-msg"></div></div></div>`;
    $('#new-ws').onsubmit = async (e) => {
      e.preventDefault();
      const profile = Object.fromEntries(new FormData(e.target).entries());
      profile.industry = (profile.industry || '').split(';').map((s) => s.trim()).filter(Boolean);
      try {
        const r = await post('/api/workspaces', { profile });
        state.ws = r.id; store.set('agent3.ws', r.id); await loadWorkspaces(); location.hash = '#/nap';
      } catch (err) { $('#new-ws-msg').innerHTML = notice('error', 'Không tạo được hồ sơ', err.message); }
    };
    $('#demo').onclick = async () => {
      $('#demo-msg').innerHTML = loading('Đang tạo dữ liệu mô phỏng');
      const r = await post('/api/demo');
      state.ws = r.id; store.set('agent3.ws', r.id); await loadWorkspaces();
      await post(`/api/workspaces/${r.id}/run`); rerender();
    };
    return;
  }
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const rep = await loadReport();
  const t = rep?.totals;
  const files = ws.files;
  const period = rep?.meta.period ? ` Dữ liệu từ ${dmy(rep.meta.period[0])} đến ${dmy(rep.meta.period[1])}.` : '';
  app().innerHTML = `<h1 class="page">${esc(ws.name)}</h1><p class="lead">MST ${esc(ws.tax_code)}.${ws.simulated ? ' Dữ liệu mô phỏng, không phải doanh nghiệp thật.' : ''}${rep ? ` Phân tích ngày ${dmy(rep.meta.as_of)}.${period}` : ''}</p>
    <div id="fresh"></div><div id="watch"></div>${deadlineBanner(rep, rep ? new Date(rep.meta.as_of) : new Date())}<div id="next"></div>
    <div class="kpis">
      <div class="kpi"><span class="label">Thuế đầu vào có nguy cơ bị loại</span><span class="value risk">${t ? money(t.at_risk_vat) : '—'}</span><span class="sub">${t ? `${t.at_risk_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Ước tính phạt tối đa nếu bị xác định khai sai</span><span class="value">${t ? money(t.penalty_estimate) : '—'}</span><span class="sub">${t ? `${Math.round(t.penalty_rate * 100)}% số thuế khai thiếu` : ''}</span></div>
      <div class="kpi"><span class="label">Cần người xem xét</span><span class="value warn">${t ? money(t.review_vat) : '—'}</span><span class="sub">${t ? `${t.review_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Có thể đang bỏ sót khấu trừ</span><span class="value">${t ? money(t.opportunity_vat) : '—'}</span><span class="sub">hóa đơn trên cổng thuế chưa có tệp</span></div>
    </div>
    <div class="bar">${button('Chạy phân tích', 'primary', 'id="run"')}${rep ? `<a class="cds--btn cds--btn--tertiary cds--btn--md" href="/api/workspaces/${esc(state.ws)}/report.html" target="_blank" rel="noopener">Mở báo cáo để in</a><a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/hoa-don.xlsx">Xuất danh sách hóa đơn</a><a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/quyet-dinh.xlsx">Xuất nhật ký quyết định</a>` : ''}<span id="run-msg"></span></div>
    <div class="grid2"><div><h2 class="section">Việc lớn nhất cần xử lý</h2>
      ${table(['Trạng thái', 'Hóa đơn', 'Lý do', { label: 'Số tiền', num: true }], (rep?.items || []).slice(0, 6).map((it) => {
        const inv = invoiceOf(it.invoice_keys[0]);
        return `<tr class="clickable" data-go="#/viec"><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0])}<div class="muted small">${esc(inv?.seller_name || '')}</div></td><td>${esc(it.title)}</td><td class="num">${money(it.amount)}</td></tr>`;
      }), rep ? 'Không có khoản nào.' : 'Chưa phân tích.')}</div>
      <div><h2 class="section">Dữ liệu đã nạp</h2><div class="panel">
      <dl class="kv"><dt>Hóa đơn mua vào</dt><dd>${files.purchase_xml} tệp</dd><dt>Hóa đơn bán ra</dt><dd>${files.sales_xml} tệp</dd><dt>Sao kê</dt><dd>${files.bank} tệp</dd><dt>Bảng kê cổng thuế</dt><dd>${files.portal_list ? 'có' : 'chưa có'}</dd></dl>
      ${button('Nạp thêm dữ liệu', 'ghost', 'data-go="#/nap"')}</div>
      <h2 class="section">Hạn gần nhất</h2>${table(['Kỳ', 'Hạn', 'Tình trạng'], (rep?.calendar || []).slice(-3).reverse().map((c) => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}</td><td>${esc(c.status)}</td></tr>`), 'Chưa có.')}</div></div>`;
  freshBanner($('#fresh'));
  sellerWatch($('#watch'), rep);
  nextSteps(ws, rep).then((h) => { const el = $('#next'); if (el) el.innerHTML = h; });
  $('#run').onclick = async () => {
    $('#run-msg').innerHTML = loading('Đang phân tích');
    try { await post(`/api/workspaces/${state.ws}/run`); await loadWorkspaces(); rerender(); } catch (err) { $('#run-msg').innerHTML = notice('error', 'Phân tích không chạy được', err.message); }
  };
}

export async function pageReview() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Việc cần xử lý</h1>${notice('info', 'Chưa phân tích', 'Chạy phân tích ở trang Tổng quan.')}`; return; }
  const filter = hashParams().get('loc') || 'all';
  const months = [...new Set(rep.invoices.filter((i) => i.issue_date).map((i) => i.issue_date.slice(0, 7)))].sort();
  const items = rep.items.filter((it) => filter === 'all' || it.status === filter);
  const count = (s) => rep.items.filter((i) => i.status === s).length;
  app().innerHTML = `<h1 class="page">Việc cần xử lý</h1><p class="lead">Xếp theo số tiền. Mở từng dòng để xem căn cứ và ghi quyết định; mọi quyết định cần chứng từ và tên người duyệt, và được ghi lại.</p>
    <div id="fresh"></div><div id="ai-tools"></div>
    <div class="bar">${[['all', `Tất cả (${rep.items.length})`], ['AT_RISK', `Có nguy cơ (${count('AT_RISK')})`], ['REVIEW', `Cần xem xét (${count('REVIEW')})`], ['OPPORTUNITY', `Bỏ sót (${count('OPPORTUNITY')})`]]
      .map(([k, l]) => `<a class="cds--btn cds--btn--${k === filter ? 'secondary' : 'ghost'} cds--btn--sm" href="#/viec?loc=${k}">${esc(l)}</a>`).join('')}
      <input class="cds--text-input filter-input" id="q" placeholder="Tìm số hóa đơn, người bán, lý do" aria-label="Tìm việc">
      <select class="cds--select-input filter-select" id="month" aria-label="Lọc theo tháng"><option value="">Mọi tháng</option>${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}</select>
      <span class="muted small" id="shown"></span>
      <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${esc(state.ws)}/export/viec-can-xu-ly.xlsx">Xuất Excel</a></div>
    <div class="bulk" id="bulk" hidden><span id="bulk-n"></span>
      <select class="cds--select-input filter-select" id="bulk-action" aria-label="Quyết định hàng loạt"></select>
      <input class="cds--text-input filter-input" id="bulk-ev" placeholder="Chứng từ hoặc lý do chung">
      <input class="cds--text-input filter-input" id="bulk-by" placeholder="Người duyệt" value="${esc(store.get('agent3.reviewer') || '')}">
      ${button('Ghi cho các việc đã chọn', 'primary', 'id="bulk-go"')}</div>
    ${table(['', 'Trạng thái', 'Hóa đơn', 'Người bán', 'Lý do', { label: 'Số tiền', num: true }], items.map((it) => {
      const inv = invoiceOf(it.invoice_keys[0]);
      return `<tr class="clickable" tabindex="0" data-item="${rep.items.indexOf(it)}" data-month="${(inv?.issue_date || '').slice(0, 7)}" data-text="${esc(`${invLabel(inv)} ${inv?.seller_name || ''} ${it.title} ${it.detail}`.toLowerCase())}"><td class="pickcell">${(it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length ? `<input type="checkbox" class="bulk-pick" data-idx="${rep.items.indexOf(it)}" aria-label="Chọn">` : ''}</td><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0])}<div class="muted small">${dmy(inv?.issue_date)}</div></td>
        <td>${esc(inv?.seller_name || '')}</td><td><span class="cell-title">${esc(it.title)}</span><div class="muted small">${esc(it.detail)}</div></td><td class="num">${money(it.amount)}</td></tr>`;
    }))}`;
  const rows = [...app().querySelectorAll('[data-item]')];
  const picks = [...app().querySelectorAll('.bulk-pick')];
  const syncBulk = () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    $('#bulk').hidden = !chosen.length;
    if (!chosen.length) return;
    $('#bulk-n').textContent = `Đã chọn ${chosen.length} việc`;
    const common = chosen.map(decisionChoices).reduce((acc, ch) => acc.filter(([v]) => ch.some(([w]) => w === v)));
    $('#bulk-action').innerHTML = common.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
  };
  picks.forEach((c) => { c.onclick = (e) => e.stopPropagation(); c.onchange = syncBulk; });
  $('#bulk-go').onclick = async () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    const body = { invoice_keys: [...new Set(chosen.map((x) => x.invoice_keys[0]))], action: $('#bulk-action').value, evidence: $('#bulk-ev').value.trim(), by: $('#bulk-by').value.trim() };
    if (!body.action || !body.evidence || !body.by) { toast('Cần quyết định, chứng từ hoặc lý do và người duyệt', '', 'error'); return; }
    store.set('agent3.reviewer', body.by);
    try { const r = await post(`/api/workspaces/${state.ws}/decisions/bulk`, body); toast(`Đã ghi ${r.decisions} quyết định`, `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`); rerender(); }
    catch (err) { toast('Không ghi được', err.message, 'error'); }
  };
  rows.forEach((tr) => {
    tr.onclick = () => openItem(rep.items[Number(tr.dataset.item)], Number(tr.dataset.item));
    tr.onkeydown = (e) => { if (e.key === 'Enter') tr.click(); };
  });
  const applyFilter = () => {
    const q = $('#q').value.trim().toLowerCase(); const m = $('#month').value;
    let n = 0;
    rows.forEach((tr) => { const ok = (!q || tr.dataset.text.includes(q)) && (!m || tr.dataset.month === m); tr.hidden = !ok; n += ok; });
    $('#shown').textContent = q || m ? `${n} việc khớp` : '';
  };
  $('#q').oninput = applyFilter; $('#month').onchange = applyFilter;
  aiToolbar($('#ai-tools'));
  freshBanner($('#fresh'));
  let want = null;
  try { want = sessionStorage.getItem('agent3.openNext'); sessionStorage.removeItem('agent3.openNext'); } catch { /* private mode */ }
  if (want) {
    const idx = rep.items.findIndex((it) => itemId(it) === want);
    if (idx >= 0) openItem(rep.items[idx], idx);
  }
  const deep = hashParams().get('open');                 // link to one item: #/viec?open=R12_ITEM_PURPOSE (first of that code)
  if (deep && !want) {
    const idx = rep.items.findIndex((it) => it.code === deep || itemId(it) === deep);
    if (idx >= 0) openItem(rep.items[idx], idx);
  }
}

export function decisionChoices(it) {
  const payment = /^R0[123]_/.test(it.code);
  const out = [];
  if (payment) out.push(['PAYMENT_EVIDENCE_ATTACHED', 'Đã có chứng từ thanh toán không dùng tiền mặt']);
  if (it.status === 'REVIEW') out.push(['CONFIRMED_OK', 'Đã kiểm tra, không có vấn đề (ghi rõ đã kiểm tra gì)']);
  out.push(['NOT_CLAIMED', 'Không kê khai khấu trừ hóa đơn này']);
  return out;
}
const decisionHelp = (it) => (/^R0[123]_/.test(it.code) || it.status === 'REVIEW' ? ''
  : 'Với loại rủi ro này, chứng từ thanh toán không khắc phục được; cần hóa đơn thay thế hoặc điều chỉnh từ người bán, hoặc không kê khai.');

async function exposureBox(el, index) {
  try {
    const ex = await api(`/api/workspaces/${state.ws}/exposure`);
    const e = ex[index];
    if (!e) return;
    el.innerHTML = `<div class="panel exposure"><h3>Nên xử lý thế nào để ít thiệt hại nhất</h3>${e.declared
      ? `<table class="mini"><tr><td>Tự khai bổ sung và nộp ngay</td><td class="num"><strong>${money(Number(e.amount) + Number(e.interest))}</strong></td><td class="muted small">thuế ${money(e.amount)} và tiền chậm nộp ${money(e.interest)} (${e.days_late} ngày kể từ hạn ${dmy(e.due)}); không bị phạt khai sai</td></tr>
        <tr><td>Để cơ quan thuế phát hiện</td><td class="num risk-text"><strong>${money(Number(e.amount) + Number(e.interest) + Number(e.penalty))}</strong></td><td class="muted small">thêm phạt 20% ${money(e.penalty)}, tiền chậm nộp tiếp tục tăng mỗi ngày</td></tr></table>`
      : `<p>Kỳ của hóa đơn này chưa đến hạn khai (${dmy(e.due)}): xử lý xong trước khi nộp tờ khai thì không phát sinh phạt hay tiền chậm nộp.</p>`}
      <div class="cite">${e.basis.filter(Boolean).map(esc).join('<br>')}</div></div>`;
  } catch { el.innerHTML = ''; }
}

function openItem(it, index) {
  const inv = invoiceOf(it.invoice_keys[0]);
  const match = state.report.matches.find((m) => m.invoice_keys.includes(it.invoice_keys[0]));
  const canDecide = (it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length > 0;
  const payment = /^R0[123]_/.test(it.code);
  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-label="Chi tiết"><button class="cds--btn cds--btn--ghost cds--btn--sm close" id="close" type="button">Đóng</button>
    <h2>${esc(it.title)}</h2>${tag(it.status)}<div id="plain" style="margin-top:1rem"></div>
    <h3 class="section" style="margin-top:1.5rem">Hóa đơn</h3>
    <dl class="kv"><dt>Số hóa đơn</dt><dd>${esc(invLabel(inv) || it.invoice_keys[0])}</dd><dt>Người bán</dt><dd>${esc(inv?.seller_name || '')} <span class="muted">MST ${esc(inv?.seller_tax_id || '')}</span></dd>
    <dt>Ngày lập</dt><dd>${dmy(inv?.issue_date)}</dd><dt>Tổng thanh toán</dt><dd>${money(inv?.gross)}</dd><dt>Thuế giá trị gia tăng</dt><dd>${money(inv?.vat)}</dd>
    <dt>Chứng từ ngân hàng</dt><dd>${match ? `${match.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}. ${esc(match.note)}` : 'Chưa ghép được'}</dd><dt>Tệp</dt><dd class="mono">${esc(inv?.file || '')}</dd></dl>
    <div id="exposure"></div><h3>Chi tiết</h3><p>${esc(it.detail)}</p><h3>Việc cần làm</h3><p>${esc(it.action)}</p>
    <h3>Căn cứ</h3><ul>${it.basis.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
    ${canDecide ? `<h3 class="section">Ghi quyết định</h3><form id="decide"><div class="form-grid">
      ${field({ key: 'action', label: 'Quyết định', type: 'choice', required: true, choices: decisionChoices(it), help: decisionHelp(it) }, decisionChoices(it)[0][0])}
      ${field({ key: 'evidence', label: 'Chứng từ hoặc lý do', required: true, example: 'Ủy nhiệm chi số 5521 ngày 05/09/2026' })}
      ${field({ key: 'by', label: 'Người duyệt', required: true, example: 'Kế toán trưởng' }, store.get('agent3.reviewer') || '')}</div>
      <div class="bar">${button('Lưu và mở việc tiếp theo', 'primary', 'type="submit" data-next="1"')}${button('Lưu', 'secondary', 'type="submit"')}<span id="dmsg"></span></div></form>` : ''}</aside>`;
  $('#close').onclick = () => { $('#modal-root').innerHTML = ''; };
  if (Number.isInteger(index)) explainBox($('#plain'), index);
  if (it.status === 'AT_RISK' && Number.isInteger(index)) exposureBox($('#exposure'), index);
  const form = $('#decide');
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      store.set('agent3.reviewer', d.by);
      const goNext = e.submitter && e.submitter.dataset.next;
      const open = state.report.items.filter((x) => (x.status === 'AT_RISK' || x.status === 'REVIEW') && itemId(x) !== itemId(it) && !x.invoice_keys.includes(it.invoice_keys[0]));
      const after = open[open.indexOf(open.find((x) => state.report.items.indexOf(x) > index)) ] || open[0];
      $('#dmsg').innerHTML = '<span class="muted">Đang lưu và chạy lại...</span>';
      try {
        const r = await post(`/api/workspaces/${state.ws}/decisions`, { ...d, invoice_key: it.invoice_keys[0] });
        toast('Đã lưu quyết định', `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`);
        if (goNext && after) { try { sessionStorage.setItem('agent3.openNext', itemId(after)); } catch { /* private mode */ } }
        $('#modal-root').innerHTML = ''; rerender();
      }
      catch (err) { $('#dmsg').innerHTML = notice('error', 'Không lưu được', err.message); }
    };
  }
}
