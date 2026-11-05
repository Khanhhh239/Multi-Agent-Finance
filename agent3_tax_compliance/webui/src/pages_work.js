// Overview, data intake and the review queue.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loadWorkspaces, loading, money, needWorkspace, notice, post, put,
  state, store, table, tag } from './core.js';

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
    ${rep ? '' : notice('info', 'Chưa có kết quả phân tích', 'Nạp hóa đơn và sao kê rồi bấm Chạy phân tích.')}
    <div class="kpis">
      <div class="kpi"><span class="label">Thuế đầu vào có nguy cơ bị loại</span><span class="value risk">${t ? money(t.at_risk_vat) : '—'}</span><span class="sub">${t ? `${t.at_risk_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Ước tính phạt tối đa nếu bị xác định khai sai</span><span class="value">${t ? money(t.penalty_estimate) : '—'}</span><span class="sub">${t ? `${Math.round(t.penalty_rate * 100)}% số thuế khai thiếu` : ''}</span></div>
      <div class="kpi"><span class="label">Cần người xem xét</span><span class="value warn">${t ? money(t.review_vat) : '—'}</span><span class="sub">${t ? `${t.review_invoices} hóa đơn` : ''}</span></div>
      <div class="kpi"><span class="label">Có thể đang bỏ sót khấu trừ</span><span class="value">${t ? money(t.opportunity_vat) : '—'}</span><span class="sub">hóa đơn trên cổng thuế chưa có tệp</span></div>
    </div>
    <div class="bar">${button('Chạy phân tích', 'primary', 'id="run"')}${rep ? `<a class="cds--btn cds--btn--tertiary cds--btn--md" href="/api/workspaces/${esc(state.ws)}/report.html" target="_blank" rel="noopener">Mở báo cáo để in</a>` : ''}<span id="run-msg"></span></div>
    <div class="grid2"><div><h2 class="section">Việc lớn nhất cần xử lý</h2>
      ${table(['Trạng thái', 'Hóa đơn', 'Lý do', { label: 'Số tiền', num: true }], (rep?.items || []).slice(0, 6).map((it) => {
        const inv = invoiceOf(it.invoice_keys[0]);
        return `<tr class="clickable" data-go="#/viec"><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0])}<div class="muted small">${esc(inv?.seller_name || '')}</div></td><td>${esc(it.title)}</td><td class="num">${money(it.amount)}</td></tr>`;
      }), rep ? 'Không có khoản nào.' : 'Chưa phân tích.')}</div>
      <div><h2 class="section">Dữ liệu đã nạp</h2><div class="panel">
      <dl class="kv"><dt>Hóa đơn mua vào</dt><dd>${files.purchase_xml} tệp</dd><dt>Hóa đơn bán ra</dt><dd>${files.sales_xml} tệp</dd><dt>Sao kê</dt><dd>${files.bank} tệp</dd><dt>Bảng kê cổng thuế</dt><dd>${files.portal_list ? 'có' : 'chưa có'}</dd></dl>
      ${button('Nạp thêm dữ liệu', 'ghost', 'data-go="#/nap"')}</div>
      <h2 class="section">Hạn gần nhất</h2>${table(['Kỳ', 'Hạn', 'Tình trạng'], (rep?.calendar || []).slice(-3).reverse().map((c) => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}</td><td>${esc(c.status)}</td></tr>`), 'Chưa có.')}</div></div>`;
  $('#run').onclick = async () => {
    $('#run-msg').innerHTML = loading('Đang phân tích');
    try { await post(`/api/workspaces/${state.ws}/run`); await loadWorkspaces(); rerender(); } catch (err) { $('#run-msg').innerHTML = notice('error', 'Phân tích không chạy được', err.message); }
  };
}

export async function pageIntake() {
  if (needWorkspace()) return;
  state.schema ||= await api('/api/schema');
  const pack = await api(`/api/workspaces/${state.ws}/pack`);
  const step = hashParams().get('b') || 'ho-so';
  const kinds = state.schema.files.filter((f) => f.folder);
  const steps = [['ho-so', 'Hồ sơ'], ...kinds.map((f) => [f.key, f.label]), ['chay', 'Chạy phân tích']];
  let body = '';
  if (step === 'ho-so') {
    body = `<form id="profile"><div class="form-grid">${state.schema.profile.map((f) => field(f, pack.profile[f.key] ?? '')).join('')}</div>
      <div class="bar">${button('Lưu hồ sơ', 'primary', 'type="submit"')}<span id="pmsg"></span></div></form>`;
  } else if (step === 'chay') {
    body = `<p>Khi đã nạp xong, chạy phân tích để xem khoản có nguy cơ, việc cần làm và hạn nộp.</p>${button('Chạy phân tích', 'primary', 'id="run2"')}<div id="r2"></div>`;
  } else {
    const spec = kinds.find((f) => f.key === step);
    const files = await api(`/api/workspaces/${state.ws}/files/${step}`);
    body = `<div class="grid2"><div><div class="drop" id="drop"><input type="file" id="file" multiple accept="${esc(spec.accept.join(','))}" class="cds--visually-hidden">
      ${button('Chọn tệp', 'primary', 'id="pick"')}<span class="muted">hoặc kéo thả vào đây. Nhận: ${esc(spec.accept.join(', '))}</span></div><div id="up"></div>
      <h2 class="section">Tệp đã có (${files.length})</h2>${table(['Tên tệp', ''], files.slice(0, 200).map((n) => `<tr><td class="mono">${esc(n)}</td><td>${step === 'bank' ? button('Nhận dạng cột', 'ghost', `data-suggest="${esc(n)}"`) : ''}</td></tr>`), 'Chưa có tệp.')}
      <div id="suggest"></div></div>
      <div class="panel"><h3>Lấy tệp ở đâu</h3><ol>${spec.how.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
      ${spec.pitfalls.length ? `<h3>Lưu ý</h3><ul>${spec.pitfalls.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}</div></div>`;
  }
  app().innerHTML = `<h1 class="page">Nạp dữ liệu</h1><p class="lead">Doanh nghiệp tự xuất tệp từ cổng hóa đơn điện tử, ngân hàng điện tử và phần mềm đang dùng, rồi nạp vào đây. Hệ thống không đăng nhập thay doanh nghiệp.</p>
    <nav class="steps">${steps.map(([k, l], i) => `<a href="#/nap?b=${k}" class="${k === step ? 'on' : ''}"><span class="n">${i + 1}</span>${esc(l)}</a>`).join('')}</nav>${body}`;
  if (step === 'ho-so') {
    $('#profile').onsubmit = async (e) => {
      e.preventDefault();
      const prof = Object.fromEntries(new FormData(e.target).entries());
      prof.industry = (prof.industry || '').split(';').map((s) => s.trim()).filter(Boolean);
      try { await put(`/api/workspaces/${state.ws}/pack`, { ...pack, profile: { ...pack.profile, ...prof } }); $('#pmsg').innerHTML = notice('success', 'Đã lưu hồ sơ'); await loadWorkspaces(); }
      catch (err) { $('#pmsg').innerHTML = notice('error', 'Không lưu được', err.message); }
    };
  } else if (step === 'chay') {
    $('#run2').onclick = async () => {
      $('#r2').innerHTML = loading('Đang phân tích');
      try { await post(`/api/workspaces/${state.ws}/run`); location.hash = '#/'; } catch (err) { $('#r2').innerHTML = notice('error', 'Lỗi', err.message); }
    };
  } else {
    const input = $('#file');
    const send = async (fileList) => {
      const out = [];
      for (const f of fileList) {
        $('#up').innerHTML = loading(`Đang tải ${f.name}`);
        try { const r = await api(`/api/workspaces/${state.ws}/files/${step}?name=${encodeURIComponent(f.name)}`, { method: 'PUT', body: f }); out.push(`${f.name}: ${r.saved.length} tệp`); }
        catch (err) { out.push(`${f.name}: ${err.message}`); }
      }
      await loadWorkspaces();
      await pageIntake();
      $('#up').innerHTML = notice('info', 'Kết quả tải lên', out.join('; '));
    };
    $('#pick').onclick = () => input.click();
    input.onchange = () => send(input.files);
    const drop = $('#drop');
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); send(e.dataTransfer.files); };
    app().querySelectorAll('[data-suggest]').forEach((b) => { b.onclick = () => suggestBank(b.dataset.suggest); });
  }
}

async function suggestBank(name) {
  const box = $('#suggest');
  box.innerHTML = loading('Đang nhận dạng cột');
  const labels = { date: 'Ngày', debit: 'Ghi nợ (tiền ra)', credit: 'Ghi có (tiền vào)', description: 'Nội dung', counterparty_account: 'Tài khoản đối ứng', counterparty_name: 'Tên đối ứng' };
  try {
    const s = await post(`/api/workspaces/${state.ws}/bank/suggest?name=${encodeURIComponent(name)}`);
    box.innerHTML = `<h2 class="section">Ánh xạ cột đề xuất cho ${esc(name)}</h2>
      <p class="muted">Dòng tiêu đề số ${s.header_row}. Kiểm tra bản xem trước, đặt tên mẫu (thường là tên ngân hàng) rồi lưu; lần sau tệp cùng ngân hàng được đọc tự động.</p>
      ${table(['Trường', 'Cột trong tệp'], Object.entries(s.format.columns).map(([k, v]) => `<tr><td>${esc(labels[k] || k)}</td><td class="mono">${esc(v)}</td></tr>`))}
      ${s.missing.length ? notice('warning', 'Chưa nhận ra cột', s.missing.map((k) => labels[k] || k).join(', ')) : ''}
      <h2 class="section">Xem trước</h2>${table(['Ngày', { label: 'Ghi nợ', num: true }, { label: 'Ghi có', num: true }, 'Nội dung'], s.preview.map((p) => (p.error
        ? `<tr><td colspan="4">${esc(p.error)}</td></tr>` : `<tr><td>${dmy(p.date)}</td><td class="num">${money(p.debit)}</td><td class="num">${money(p.credit)}</td><td>${esc(p.description)}</td></tr>`)))}
      <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="fmt-name">Tên mẫu</label><input class="cds--text-input" id="fmt-name" value="${esc(s.format.name)}"></div>
      ${button('Lưu mẫu sao kê', 'primary', 'id="save-fmt"')}<span id="fmt-msg"></span></div>`;
    $('#save-fmt').onclick = async () => {
      try { await post(`/api/workspaces/${state.ws}/bank/formats`, { ...s.format, name: $('#fmt-name').value || s.format.name }); $('#fmt-msg').innerHTML = notice('success', 'Đã lưu mẫu'); }
      catch (err) { $('#fmt-msg').innerHTML = notice('error', 'Không lưu được', err.message); }
    };
  } catch (err) { box.innerHTML = notice('error', 'Không nhận dạng được', err.message); }
}

export async function pageReview() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Việc cần xử lý</h1>${notice('info', 'Chưa phân tích', 'Chạy phân tích ở trang Tổng quan.')}`; return; }
  const filter = hashParams().get('loc') || 'all';
  const items = rep.items.filter((it) => filter === 'all' || it.status === filter);
  const count = (s) => rep.items.filter((i) => i.status === s).length;
  app().innerHTML = `<h1 class="page">Việc cần xử lý</h1><p class="lead">Xếp theo số tiền. Mở từng dòng để xem căn cứ và ghi quyết định; mọi quyết định cần chứng từ và tên người duyệt, và được ghi lại.</p>
    <div class="bar">${[['all', `Tất cả (${rep.items.length})`], ['AT_RISK', `Có nguy cơ (${count('AT_RISK')})`], ['REVIEW', `Cần xem xét (${count('REVIEW')})`], ['OPPORTUNITY', `Bỏ sót (${count('OPPORTUNITY')})`]]
      .map(([k, l]) => `<a class="cds--btn cds--btn--${k === filter ? 'secondary' : 'ghost'} cds--btn--sm" href="#/viec?loc=${k}">${esc(l)}</a>`).join('')}</div>
    ${table(['Trạng thái', 'Hóa đơn', 'Người bán', 'Lý do', { label: 'Số tiền', num: true }], items.map((it) => {
      const inv = invoiceOf(it.invoice_keys[0]);
      return `<tr class="clickable" data-item="${rep.items.indexOf(it)}"><td>${tag(it.status)}</td><td>${esc(invLabel(inv) || it.invoice_keys[0])}<div class="muted small">${dmy(inv?.issue_date)}</div></td>
        <td>${esc(inv?.seller_name || '')}</td><td><span class="cell-title">${esc(it.title)}</span><div class="muted small">${esc(it.detail)}</div></td><td class="num">${money(it.amount)}</td></tr>`;
    }))}`;
  app().querySelectorAll('[data-item]').forEach((tr) => { tr.onclick = () => openItem(rep.items[Number(tr.dataset.item)]); });
}

function openItem(it) {
  const inv = invoiceOf(it.invoice_keys[0]);
  const match = state.report.matches.find((m) => m.invoice_keys.includes(it.invoice_keys[0]));
  const canDecide = it.status === 'AT_RISK' || it.status === 'REVIEW';
  const payment = /^R0[123]_/.test(it.code);
  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-label="Chi tiết"><button class="cds--btn cds--btn--ghost cds--btn--sm close" id="close" type="button">Đóng</button>
    <h2>${esc(it.title)}</h2>${tag(it.status)}
    <h3 class="section" style="margin-top:1.5rem">Hóa đơn</h3>
    <dl class="kv"><dt>Số hóa đơn</dt><dd>${esc(invLabel(inv) || it.invoice_keys[0])}</dd><dt>Người bán</dt><dd>${esc(inv?.seller_name || '')} <span class="muted">MST ${esc(inv?.seller_tax_id || '')}</span></dd>
    <dt>Ngày lập</dt><dd>${dmy(inv?.issue_date)}</dd><dt>Tổng thanh toán</dt><dd>${money(inv?.gross)}</dd><dt>Thuế giá trị gia tăng</dt><dd>${money(inv?.vat)}</dd>
    <dt>Chứng từ ngân hàng</dt><dd>${match ? `${match.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}. ${esc(match.note)}` : 'Chưa ghép được'}</dd><dt>Tệp</dt><dd class="mono">${esc(inv?.file || '')}</dd></dl>
    <h3>Chi tiết</h3><p>${esc(it.detail)}</p><h3>Việc cần làm</h3><p>${esc(it.action)}</p>
    <h3>Căn cứ</h3><ul>${it.basis.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
    ${canDecide ? `<h3 class="section">Ghi quyết định</h3><form id="decide"><div class="form-grid">
      ${field({ key: 'action', label: 'Quyết định', type: 'choice', required: true, choices: payment ? [['PAYMENT_EVIDENCE_ATTACHED', 'Đã có chứng từ thanh toán không dùng tiền mặt'], ['NOT_CLAIMED', 'Không kê khai khấu trừ hóa đơn này']]
        : [['NOT_CLAIMED', 'Không kê khai khấu trừ hóa đơn này']], help: payment ? '' : 'Với loại rủi ro này, chứng từ thanh toán không khắc phục được; cần hóa đơn thay thế hoặc điều chỉnh từ người bán, hoặc không kê khai.' }, payment ? 'PAYMENT_EVIDENCE_ATTACHED' : 'NOT_CLAIMED')}
      ${field({ key: 'evidence', label: 'Chứng từ hoặc lý do', required: true, example: 'Ủy nhiệm chi số 5521 ngày 05/09/2026' })}
      ${field({ key: 'by', label: 'Người duyệt', required: true, example: 'Kế toán trưởng' })}</div>
      <div class="bar">${button('Lưu quyết định và chạy lại', 'primary', 'type="submit"')}<span id="dmsg"></span></div></form>` : ''}</aside>`;
  $('#close').onclick = () => { $('#modal-root').innerHTML = ''; };
  const form = $('#decide');
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      try { await post(`/api/workspaces/${state.ws}/decisions`, { ...d, invoice_key: it.invoice_keys[0] }); $('#modal-root').innerHTML = ''; rerender(); }
      catch (err) { $('#dmsg').innerHTML = notice('error', 'Không lưu được', err.message); }
    };
  }
}
