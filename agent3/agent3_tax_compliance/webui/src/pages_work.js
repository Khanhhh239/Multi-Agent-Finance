// Overview, data intake and the review queue.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loadWorkspaces, loading, money, needWorkspace, notice, post, put,
  state, store, table, tag } from './core.js';
import { aiToolbar, explainBox } from './pages_ai.js';
import { pageWelcome } from './pages_config.js';
import { deadlineBanner, freshBanner, nextSteps, sellerWatch, toast } from './ux.js';
import { bindDialog, closeDialog } from './interactions.js';

const itemId = (it) => `${it.code}|${it.invoice_keys.join(',')}`;

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageOverview() {
  if (!state.ws) { await pageWelcome(); return; }
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const rep = await loadReport();
  const t = rep?.totals;
  const files = ws.files;
  const period = rep?.meta.period ? ` Dữ liệu từ ${dmy(rep.meta.period[0])} đến ${dmy(rep.meta.period[1])}.` : '';
  app().innerHTML = `<span class="eyebrow">Tổng quan thuế</span><h1 class="page">${esc(ws.name)}</h1><div class="context-line"><span>MST ${esc(ws.tax_code)}</span><span>${rep ? `Phân tích ngày ${dmy(rep.meta.as_of)}` : 'Chưa có kết quả phân tích'}</span>${period ? `<span>${period.trim()}</span>` : ''}</div>${ws.simulated ? '<p class="lead">Dữ liệu mô phỏng, không phải doanh nghiệp thật.</p>' : ''}
    <div id="fresh"></div><div id="watch"></div>${deadlineBanner(rep, rep ? new Date(rep.meta.as_of) : new Date())}
    <div class="kpis">
      <div class="kpi"><span class="label">Thuế đầu vào có nguy cơ bị loại</span><span class="value risk">${t ? money(t.at_risk_vat) : '—'}</span><span class="sub">${t ? `${t.at_risk_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Ước tính phạt tối đa nếu bị xác định khai sai</span><span class="value">${t ? money(t.penalty_estimate) : '—'}</span><span class="sub">${t ? `${Math.round(t.penalty_rate * 100)}% số thuế khai thiếu` : ''}</span></div>
      <div class="kpi"><span class="label">Cần người xem xét</span><span class="value warn">${t ? money(t.review_vat) : '—'}</span><span class="sub">${t ? `${t.review_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Có thể đang bỏ sót khấu trừ</span><span class="value">${t ? money(t.opportunity_vat) : '—'}</span><span class="sub">hóa đơn trên cổng thuế chưa có tệp</span></div>
    </div>
    <div class="bar">${button('Chạy phân tích', 'primary', 'id="run"')}${rep ? `<details class="quick-export"><summary>Xuất và in báo cáo</summary><a class="cds--btn cds--btn--tertiary cds--btn--md" href="/api/workspaces/${esc(state.ws)}/report.html" target="_blank" rel="noopener">Mở báo cáo để in</a><a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/hoa-don.xlsx">Xuất danh sách hóa đơn</a><a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/quyet-dinh.xlsx">Xuất nhật ký quyết định</a></details>` : ''}<span id="run-msg"></span></div>
    <div class="quick-links"><a href="#/so-lieu">Số liệu thuế GTGT theo kỳ</a><a href="#/lich">Lịch thuế</a><a href="#/ngan-hang">Giao dịch ngân hàng</a><a href="#/giai-trinh">Soạn giải trình</a><a href="#/luat">Kho luật và tin luật mới</a></div>
    <div class="grid2"><div><h2 class="section">Việc lớn nhất cần xử lý</h2>
      ${table(['Trạng thái', 'Hóa đơn', 'Lý do', { label: 'Số tiền', num: true }], (rep?.items || []).slice(0, 6).map((it) => {
        const inv = invoiceOf(it.invoice_keys[0]);
        return `<tr class="clickable" data-go="#/viec"><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0])}<div class="muted small">${esc(inv?.seller_name || '')}</div></td><td>${esc(it.title)}</td><td class="num">${money(it.amount)}</td></tr>`;
      }), rep ? 'Không có khoản nào.' : 'Chưa phân tích.')}</div>
      <div><h2 class="section">Dữ liệu đã nạp</h2><div class="panel">
      <dl class="kv"><dt>Hóa đơn mua vào</dt><dd>${files.purchase_xml} tệp</dd><dt>Hóa đơn bán ra</dt><dd>${files.sales_xml} tệp</dd><dt>Sao kê</dt><dd>${files.bank} tệp</dd><dt>Bảng kê cổng thuế</dt><dd>${files.portal_list ? 'có' : 'chưa có'}</dd></dl>
      ${button('Nạp thêm dữ liệu', 'ghost', 'data-go="#/nap"')}</div>
      <h2 class="section">Hạn gần nhất</h2>${table(['Kỳ', 'Hạn', 'Tình trạng'], (rep?.calendar || []).slice(-3).reverse().map((c) => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}</td><td>${esc(c.status)}</td></tr>`), 'Chưa có.')}</div></div><div id="next"></div>`;
  freshBanner($('#fresh'));
  sellerWatch($('#watch'), rep);
  nextSteps(ws, rep).then((h) => { const el = $('#next'); if (el) el.innerHTML = h; });
  $('#run').onclick = async () => {
    const run = $('#run'); const message = $('#run-msg'); run.disabled = true;
    message.innerHTML = loading('Đang phân tích');
    try { await post(`/api/workspaces/${state.ws}/run`); await loadWorkspaces(); rerender(); }
    catch (err) { if (message.isConnected && err.name !== 'AbortError') message.innerHTML = notice('error', 'Phân tích không chạy được', err.message); }
    finally { if (run.isConnected) run.disabled = false; }
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
      <select class="cds--select-input filter-select" id="group" aria-label="Lọc theo vấn đề"></select>
      <select class="cds--select-input filter-select" id="month" aria-label="Lọc theo tháng"><option value="">Mọi tháng</option>${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}</select>
      <span class="muted small" id="shown" role="status"></span>${button('Xóa bộ lọc', 'ghost', 'id="reset-filters"')}
      <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${esc(state.ws)}/export/viec-can-xu-ly.xlsx">Xuất Excel</a></div>
    <div class="bulk" id="bulk" hidden><span id="bulk-n"></span>
      <select class="cds--select-input filter-select" id="bulk-action" aria-label="Quyết định hàng loạt"></select>
      <input class="cds--text-input filter-input" id="bulk-ev" aria-label="Chứng từ hoặc lý do chung" placeholder="Chứng từ hoặc lý do chung">
      <input class="cds--text-input filter-input" id="bulk-by" aria-label="Người duyệt" placeholder="Người duyệt" value="${esc(store.get('agent3.reviewer') || '')}">
      ${button('Ghi cho các việc đã chọn', 'primary', 'id="bulk-go"')}</div>
    <div id="list"></div>`;
  // Grouped by issue first, then a paged list: stays usable with hundreds or thousands of invoices.
  const PAGE = 50;
  let shown = PAGE;
  let code = hashParams().get('nhom') || '';
  const idxOf = new Map(rep.items.map((it, i) => [it, i]));
  const textOf = (it) => { const inv = invoiceOf(it.invoice_keys[0]); return `${invLabel(inv)} ${inv?.seller_name || ''} ${it.title} ${it.detail}`.toLowerCase(); };
  const monthOf = (it) => (invoiceOf(it.invoice_keys[0])?.issue_date || '').slice(0, 7);
  const groups = {};
  items.forEach((it) => { const g = groups[it.code] ||= { title: it.title, status: it.status, n: 0, amount: 0 }; g.n += 1; g.amount += Number(it.amount || 0); });
  const paintGroups = () => {
    const opts = Object.entries(groups).sort((x, y) => y[1].amount - x[1].amount || y[1].n - x[1].n);
    $('#group').innerHTML = `<option value="">Mọi vấn đề</option>${opts.map(([c, g]) => `<option value="${esc(c)}" ${c === code ? 'selected' : ''}>${esc(g.title)} (${g.n})</option>`).join('')}`;
  };
  const rowTpl = (it) => {
    const inv = invoiceOf(it.invoice_keys[0]);
    const i = idxOf.get(it);
    return `<tr class="clickable" tabindex="0" data-item="${i}"><td class="pickcell">${(it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length ? `<input type="checkbox" class="bulk-pick" data-idx="${i}" aria-label="Chọn">` : ''}</td><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0] || '')}<div class="muted small">${dmy(inv?.issue_date)}</div></td>
      <td>${esc(inv?.seller_name || '')}</td><td><span class="cell-title">${esc(it.title)}</span><div class="muted small">${esc(it.detail)}</div></td><td class="num">${money(it.amount)}</td></tr>`;
  };
  let picks = [];
  const syncBulk = () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    $('#bulk').hidden = !chosen.length;
    if (!chosen.length) return;
    $('#bulk-n').textContent = `Đã chọn ${chosen.length} việc`;
    const common = chosen.map(decisionChoices).reduce((acc, ch) => acc.filter(([v]) => ch.some(([w]) => w === v)));
    $('#bulk-action').innerHTML = common.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
  };
  const paint = () => {
    const q = $('#q').value.trim().toLowerCase(); const m = $('#month').value;
    const view = items.filter((it) => (!code || it.code === code) && (!q || textOf(it).includes(q)) && (!m || monthOf(it) === m));
    $('#shown').textContent = q || m || code ? `${view.length} việc khớp` : `${view.length} việc`;
    $('#list').innerHTML = table(['', 'Trạng thái', 'Hóa đơn', 'Người bán', 'Lý do', { label: 'Số tiền', num: true }], view.slice(0, shown).map(rowTpl), 'Không có việc nào khớp.')
      + (view.length > shown ? `<div class="bar"><span class="muted small">Đang hiện ${shown} trên ${view.length} việc</span>${button(`Hiện thêm ${Math.min(PAGE, view.length - shown)} việc`, 'ghost', 'id="more"')}${button('Hiện tất cả', 'ghost', 'id="all"')}</div>` : '');
    picks = [...app().querySelectorAll('.bulk-pick')];
    picks.forEach((c) => { c.onclick = (e) => e.stopPropagation(); c.onchange = syncBulk; });
    app().querySelectorAll('[data-item]').forEach((tr) => {
      tr.onclick = () => openItem(rep.items[Number(tr.dataset.item)], Number(tr.dataset.item));
      tr.onkeydown = (e) => { if (e.target === tr && ['Enter', ' '].includes(e.key)) { e.preventDefault(); tr.click(); } };
    });
    if ($('#more')) $('#more').onclick = () => { shown += PAGE; paint(); };
    if ($('#all')) $('#all').onclick = () => { shown = view.length; paint(); };
    syncBulk();
  };
  $('#group').onchange = () => { code = $('#group').value; shown = PAGE; paint(); };
  $('#bulk-go').onclick = async () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    const body = { invoice_keys: [...new Set(chosen.map((x) => x.invoice_keys[0]))], action: $('#bulk-action').value, evidence: $('#bulk-ev').value.trim(), by: $('#bulk-by').value.trim() };
    if (!body.action || !body.evidence || !body.by) { toast('Cần quyết định, chứng từ hoặc lý do và người duyệt', '', 'error'); return; }
    store.set('agent3.reviewer', body.by);
    const submit = $('#bulk-go'); submit.disabled = true;
    try { const r = await post(`/api/workspaces/${state.ws}/decisions/bulk`, body); toast(`Đã ghi ${r.decisions} quyết định`, `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`); rerender(); }
    catch (err) { if (submit.isConnected) { toast('Không ghi được', err.message, 'error'); submit.disabled = false; } }
  };
  $('#q').oninput = () => { shown = PAGE; paint(); }; $('#month').onchange = () => { shown = PAGE; paint(); };
  $('#reset-filters').onclick = () => {
    if (filter !== 'all') { location.hash = '#/viec'; return; }
    $('#q').value = ''; $('#month').value = ''; code = ''; $('#group').value = ''; shown = PAGE; paint();
  };
  paintGroups(); paint();
  aiToolbar($('#ai-tools')).catch((err) => { const el = $('#ai-tools'); if (el && err.name !== 'AbortError') el.innerHTML = notice('info', 'Trợ lý AI chưa sẵn sàng', 'Bạn vẫn có thể xem chứng từ và xử lý công việc.'); });
  freshBanner($('#fresh'));
  let want = null;
  try { want = sessionStorage.getItem('agent3.openNext'); sessionStorage.removeItem('agent3.openNext'); } catch { /* private mode */ }
  if (want) {
    const idx = rep.items.findIndex((it) => itemId(it) === want);
    if (idx >= 0) openItem(rep.items[idx], idx);
  }
  const deep = hashParams().get('open');                 // link to one item: #/viec?open=R12_ITEM_PURPOSE (first of that code)
  if (deep && !want) {
    const idx = rep.items.findIndex((it) => it.code === deep || itemId(it) === deep || it.invoice_keys.includes(deep));
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
  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-labelledby="drawer-title"><button class="cds--btn cds--btn--ghost cds--btn--sm close" id="close" type="button">Đóng</button>
    <h2 id="drawer-title">${esc(it.title)}</h2>${tag(it.status)}<div id="plain" style="margin-top:1rem"></div>
    <h3 class="section" style="margin-top:1.5rem">Hóa đơn</h3>
    <dl class="kv"><dt>Số hóa đơn</dt><dd>${esc(invLabel(inv) || it.invoice_keys[0])}</dd><dt>Người bán</dt><dd>${esc(inv?.seller_name || '')} <span class="muted">MST ${esc(inv?.seller_tax_id || '')}</span></dd>
    <dt>Ngày lập</dt><dd>${dmy(inv?.issue_date)}</dd><dt>Tổng thanh toán</dt><dd>${money(inv?.gross)}</dd><dt>Thuế giá trị gia tăng</dt><dd>${money(inv?.vat)}</dd>
    <dt>Chứng từ ngân hàng</dt><dd>${match ? `${match.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}. ${esc(match.note)}` : 'Chưa ghép được'}</dd><dt>Tệp</dt><dd class="mono">${esc(inv?.file || '')}</dd></dl>
    <div id="exposure"></div><h3>Chi tiết</h3><p>${esc(it.detail)}</p><h3>Việc cần làm</h3><p>${esc(it.action)}</p>
    <h3>Căn cứ</h3><ul>${it.basis.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
    ${canDecide ? `<h3 class="section">Ghi quyết định</h3><div id="suggest"></div><form id="decide"><div class="form-grid">
      ${field({ key: 'action', label: 'Quyết định', type: 'choice', required: true, choices: decisionChoices(it), help: decisionHelp(it) }, decisionChoices(it)[0][0])}
      ${field({ key: 'evidence', label: 'Chứng từ hoặc lý do', required: true, example: 'Ủy nhiệm chi số 5521 ngày 05/09/2026' })}
      ${field({ key: 'by', label: 'Người duyệt', required: true, example: 'Kế toán trưởng' }, store.get('agent3.reviewer') || '')}</div>
      <div class="bar">${button('Lưu và mở việc tiếp theo', 'primary', 'type="submit" data-next="1"')}${button('Lưu', 'secondary', 'type="submit"')}<span id="dmsg"></span></div></form>` : ''}</aside>`;
  bindDialog();
  if (Number.isInteger(index)) explainBox($('#plain'), index);
  if (it.status === 'AT_RISK' && Number.isInteger(index)) exposureBox($('#exposure'), index);
  const form = $('#decide');
  if (form) {
    const drawer = $('.drawer');
    api(`/api/workspaces/${state.ws}/decisions/suggest?key=${encodeURIComponent(it.invoice_keys[0])}&code=${encodeURIComponent(it.code)}`).then((r) => {
      const s = r.suggestion;
      if (!s || !drawer.isConnected) return;
      const ok = decisionChoices(it).some(([v]) => v === s.action);
      if (!ok) return;
      $('#suggest').innerHTML = `<div class="banner banner-info"><div><strong>Gợi ý từ quyết định trước</strong><div class="small">${esc(s.because)}</div></div>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="use-sugg">Điền theo gợi ý</button></div>`;
      $('#use-sugg').onclick = () => {
        form.querySelector('[name=action]').value = s.action;
        form.querySelector('[name=evidence]').value = '';
        form.querySelector('[name=evidence]').placeholder = `Lần trước: ${s.evidence}`;
        if (!form.querySelector('[name=by]').value) form.querySelector('[name=by]').value = s.by;
        form.querySelector('[name=evidence]').focus();
      };
    }).catch(() => {});
    form.onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      store.set('agent3.reviewer', d.by);
      const goNext = e.submitter && e.submitter.dataset.next;
      const open = state.report.items.filter((x) => (x.status === 'AT_RISK' || x.status === 'REVIEW') && itemId(x) !== itemId(it) && !x.invoice_keys.includes(it.invoice_keys[0]));
      const after = open[open.indexOf(open.find((x) => state.report.items.indexOf(x) > index)) ] || open[0];
      $('#dmsg').innerHTML = '<span class="muted">Đang lưu và chạy lại...</span>';
      const message = $('#dmsg');
      const buttons = [...form.querySelectorAll('button[type="submit"]')];
      buttons.forEach((b) => { b.disabled = true; });
      try {
        const r = await post(`/api/workspaces/${state.ws}/decisions`, { ...d, invoice_key: it.invoice_keys[0] });
        toast('Đã lưu quyết định', `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`);
        if (goNext && after) { try { sessionStorage.setItem('agent3.openNext', itemId(after)); } catch { /* private mode */ } }
        closeDialog(); rerender();
      }
      catch (err) { if (form.isConnected) { message.innerHTML = notice('error', 'Không lưu được', err.message); buttons.forEach((b) => { b.disabled = false; }); } }
    };
  }
}
