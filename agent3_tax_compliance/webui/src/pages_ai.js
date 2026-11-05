// The controlled AI layer in the interface: plain explanations, line classification, bank-text proposals,
// explanation letter and dossier, law alerts, VAT figures. AI output is always labelled and verified; people decide.
import { $, api, app, button, dmy, esc, invLabel, invoiceOf, loadReport, loading, money, needWorkspace, notice, post, state, store, table, tag } from './core.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));
const aiTag = (mode) => (mode === 'AI_VERIFIED' ? tag('LLM_VERIFIED', 'AI, đã kiểm tra') : tag('INFO', 'Câu mẫu'));

// ---------------------------------------------------------------- A4 in the review drawer
export async function explainBox(el, index) {
  el.innerHTML = `<div class="plain">${loading('Mô hình trên máy đang viết lời giải thích dễ hiểu')}</div>`;
  try {
    const e = await post(`/api/workspaces/${state.ws}/ai/explain`, { index });
    el.innerHTML = `<div class="plain"><div class="bar" style="margin:0 0 .5rem">${aiTag(e.mode)}<span class="muted small">Nói đơn giản${e.note ? ` (${esc(e.note)})` : ''}</span></div>${esc(e.text)}</div>`;
  } catch (err) { el.innerHTML = ''; }
}

// ---------------------------------------------------------------- AI jobs toolbar (review page)
export async function aiToolbar(el) {
  const s = await api(`/api/workspaces/${state.ws}/ai`);
  const job = s.job;
  const running = job && job.running;
  el.innerHTML = `<div class="panel ai-panel"><h3>Trợ lý AI chạy trên máy (${esc(s.model)})</h3>
    <p class="muted small">AI chỉ đề xuất; mọi đề xuất đã qua kiểm tra tự động và chỉ thành "cần xem xét", người duyệt quyết định. Dữ liệu không rời khỏi máy này.</p>
    <div class="bar">${button(running && job.task === 'phân loại dòng hàng' ? `Đang phân loại ${job.done}/${job.total}` : `Phân loại dòng hàng (${s.labelled_invoices} hóa đơn đã phân loại, ${s.flagged_invoices} cần xem)`, 'tertiary', `id="ai-cls" ${running ? 'disabled' : ''}`)}
    ${button(running && job.task === 'đọc nội dung chuyển khoản' ? 'Đang đọc nội dung chuyển khoản' : `Đọc nội dung chuyển khoản (${s.proposals.length} đề xuất chờ xác nhận)`, 'tertiary', `id="ai-bank" ${running ? 'disabled' : ''}`)}
    ${s.proposals.length ? button('Xem đề xuất ghép', 'ghost', 'data-go="#/ngan-hang"') : ''}</div>
    ${job && job.error ? notice('error', 'Việc AI bị lỗi', job.error) : ''}${job && !job.running && job.result ? notice('success', `Xong: ${job.task}`, JSON.stringify(job.result).replace(/[{}"]/g, '').replace('flagged:', 'hóa đơn cần xem: ').replace('proposals:', 'đề xuất: ')) : ''}</div>`;
  const start = async (path) => { try { await post(`/api/workspaces/${state.ws}/ai/${path}`); aiToolbar(el); } catch (err) { el.insertAdjacentHTML('beforeend', notice('error', 'Không chạy được', err.message)); } };
  $('#ai-cls').onclick = () => start('classify');
  $('#ai-bank').onclick = () => start('bank');
  const finished = el.dataset.wasRunning === '1' && !running;     // a job just ended: show the new findings
  el.dataset.wasRunning = running ? '1' : '0';
  if (finished && !document.querySelector('.drawer')) rerender();
  else if (running) setTimeout(() => { if (document.body.contains(el)) aiToolbar(el); }, 3000);
}

// ---------------------------------------------------------------- A2 proposals (bank page)
export async function bankProposals(el) {
  const s = await api(`/api/workspaces/${state.ws}/ai`);
  if (!s.proposals.length) { el.innerHTML = ''; return; }
  const by = store.get('agent3.reviewer') || '';
  el.innerHTML = `<h2 class="section">Đề xuất ghép từ nội dung chuyển khoản (${s.proposals.length})</h2>
    <p class="muted">Số tiền khớp chính xác; AI đọc nội dung chuyển khoản và tìm thấy cụm chữ nhắc tới người bán. Xác nhận thì hệ thống ghi quyết định có tên người duyệt và chạy lại.</p>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="reviewer">Người duyệt</label><input class="cds--text-input" id="reviewer" value="${esc(by)}" placeholder="Kế toán trưởng"></div></div>
    ${table(['Giao dịch', { label: 'Số tiền', num: true }, 'Nội dung chuyển khoản', 'Hóa đơn đề xuất', 'Căn cứ của AI', ''], s.proposals.map((p, n) => `<tr>
      <td>${dmy(p.booked)}<div class="muted small">${esc(p.source || '')}</div></td><td class="num">${money(p.amount)}</td><td>${esc(p.description || '')}<div class="muted small">${esc(p.counterparty_name || '')}</div></td>
      <td>${esc(p.seller_name)}<div class="muted small">số ${esc(p.invoice_number || '')}</div></td><td>cụm "<strong>${esc(p.name_in_text)}</strong>", độ giống ${p.similarity}<div class="muted small">${esc(p.reason)}</div></td>
      <td><div class="chips">${button('Xác nhận', 'primary', `data-acc="${n}"`)}${button('Bác bỏ', 'ghost', `data-rej="${n}"`)}</div></td></tr>`))}<div id="pmsg"></div>`;
  const decide = async (n, accept) => {
    const who = $('#reviewer').value.trim();
    if (accept && !who) { $('#pmsg').innerHTML = notice('warning', 'Cần tên người duyệt'); return; }
    store.set('agent3.reviewer', who);
    try { await post(`/api/workspaces/${state.ws}/ai/bank/decide`, { txn_id: s.proposals[n].txn_id, invoice_key: s.proposals[n].invoice_key, accept, by: who }); rerender(); }
    catch (err) { $('#pmsg').innerHTML = notice('error', 'Không ghi được', err.message); }
  };
  el.querySelectorAll('[data-acc]').forEach((b) => { b.onclick = () => decide(Number(b.dataset.acc), true); });
  el.querySelectorAll('[data-rej]').forEach((b) => { b.onclick = () => decide(Number(b.dataset.rej), false); });
}

// ---------------------------------------------------------------- A3 + F5 explanation letter and dossier
export async function pageDossier() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Giải trình</h1>${notice('info', 'Chưa phân tích')}`; return; }
  const keys = [...new Set(rep.items.filter((i) => i.status !== 'INFO').flatMap((i) => i.invoice_keys))].filter((k) => invoiceOf(k));
  app().innerHTML = `<h1 class="page">Giải trình với cơ quan thuế</h1>
    <p class="lead">Khi nhận công văn yêu cầu giải trình hoặc bổ sung hồ sơ: chọn hóa đơn liên quan, dán nội dung công văn. Hệ thống gom hóa đơn XML, chứng từ thanh toán đã ghép, quyết định của người duyệt và điều khoản luật thành một tệp nén, kèm bản nháp thư. Mỗi đoạn thư ghi rõ dựa vào dữ kiện nào; đoạn có số liệu không khớp dữ kiện bị loại.</p>
    <div class="cds--form-item"><label class="cds--label" for="req">Nội dung công văn của cơ quan thuế (không bắt buộc)</label>
    <textarea class="cds--text-area" id="req" rows="4" placeholder="Ví dụ: Đề nghị doanh nghiệp giải trình việc kê khai khấu trừ thuế GTGT đầu vào của các hóa đơn mua hàng của Công ty TNHH Điện máy Thành Công trong quý 3/2026..."></textarea></div>
    <h2 class="section">Hóa đơn đưa vào hồ sơ</h2>
    ${table(['', 'Hóa đơn', 'Người bán', 'Vấn đề', { label: 'Tổng thanh toán', num: true }], keys.map((k) => { const i = invoiceOf(k); const its = rep.items.filter((x) => x.invoice_keys.includes(k));
      return `<tr><td><input type="checkbox" class="pick" value="${esc(k)}"></td><td>${esc(invLabel(i))}<div class="muted small">${dmy(i.issue_date)}</div></td><td>${esc(i.seller_name)}</td><td><div class="chips">${its.map((x) => tag(x.status, x.title.slice(0, 48))).join('')}</div></td><td class="num">${money(i.gross)}</td></tr>`; }), 'Không có hóa đơn nào có vấn đề.')}
    <div class="bar">${button('Soạn thư và lập hồ sơ', 'primary', 'id="make"')}<span id="mk"></span></div><div id="letter"></div>`;
  $('#make').onclick = async () => {
    const invoice_keys = [...app().querySelectorAll('.pick:checked')].map((c) => c.value);
    if (!invoice_keys.length) { $('#mk').innerHTML = notice('warning', 'Chọn ít nhất một hóa đơn'); return; }
    $('#mk').innerHTML = loading('Đang gom chứng từ và soạn thư bằng mô hình trên máy (khoảng 1 đến 2 phút)');
    try {
      const r = await post(`/api/workspaces/${state.ws}/dossier`, { invoice_keys, request_text: $('#req').value });
      $('#mk').innerHTML = '';
      const L = r.letter;
      $('#letter').innerHTML = `<div class="panel"><div class="bar" style="margin-top:0">${aiTag(L.mode)}<span class="muted small">${esc(L.note || '')}</span>
        <a class="cds--btn cds--btn--primary cds--btn--sm" href="/api/workspaces/${esc(state.ws)}/dossier/${esc(r.file)}">Tải hồ sơ (.zip)</a></div>
        <h3>Bản nháp thư</h3>${L.paragraphs.map((p) => `<p>${esc(p.text)} <span class="muted small">${[...p.fact_ids, ...p.passage_ids].map(esc).join(', ')}</span></p>`).join('')}
        ${L.dropped && L.dropped.length ? notice('info', `${L.dropped.length} đoạn của mô hình bị loại vì không qua kiểm tra`, L.dropped.map((d) => d.reason).join('; ')) : ''}
        <h3>Dữ kiện</h3><ul>${r.facts.map((f) => `<li><strong>${esc(f.id)}</strong> ${esc(f.text)}</li>`).join('')}</ul>
        ${r.passages.length ? `<h3>Điều khoản</h3><ul>${r.passages.map((p) => `<li><strong>${esc(p.pid)}</strong> <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.path)}</a></li>`).join('')}</ul>` : ''}
        <p class="muted small">Bản nháp; người có thẩm quyền phải đọc, sửa và ký trước khi gửi.</p></div>`;
    } catch (err) { $('#mk').innerHTML = notice('error', 'Không lập được hồ sơ', err.message); }
  };
}

// ---------------------------------------------------------------- F3 VAT figures
export async function pageVat() {
  if (needWorkspace()) return;
  let v;
  try { v = await api(`/api/workspaces/${state.ws}/vat-summary`); } catch (err) { app().innerHTML = `<h1 class="page">Số liệu thuế GTGT</h1>${notice('info', 'Chưa phân tích', err.message)}`; return; }
  app().innerHTML = `<h1 class="page">Số liệu thuế giá trị gia tăng theo kỳ</h1><p class="lead">${esc(v.note)}</p>
    ${table(['Kỳ', { label: 'Thuế đầu ra', num: true }, { label: 'Thuế đầu vào', num: true }, { label: 'Có nguy cơ bị loại', num: true }, { label: 'Đầu vào an toàn', num: true }, { label: 'Phải nộp (ước tính)', num: true }, 'Hóa đơn'],
      v.rows.map((r) => `<tr><td>${esc(r.period)}</td><td class="num">${money(r.output_vat)}</td><td class="num">${money(r.input_vat)}</td><td class="num">${Number(r.at_risk) ? `<strong>${money(r.at_risk)}</strong>` : money(0)}</td>
        <td class="num">${money(r.input_safe)}</td><td class="num">${money(r.net)}</td><td class="muted small">${r.purchases} mua vào, ${r.sales} bán ra${r.review ? `, ${r.review} cần xem` : ''}</td></tr>`))}
    ${v.rows.some((r) => !r.sales) ? notice('info', 'Chưa có hóa đơn bán ra ở một số kỳ', 'Số phải nộp ước tính sẽ âm nếu thiếu thuế đầu ra; nạp hóa đơn bán ra để số liệu đầy đủ.') : ''}`;
}

// ---------------------------------------------------------------- A5 law alerts (law page)
export async function lawAlerts(el) {
  const rows = await api('/api/law/alerts');
  if (!rows.length) { el.innerHTML = ''; return; }
  el.innerHTML = `<h2 class="section">Thay đổi luật cần chú ý (150 ngày qua và 180 ngày tới)</h2>
    ${table(['Ngày', 'Loại', 'Văn bản', ''], rows.slice(0, 40).map((r, n) => `<tr><td>${dmy(r.day)}</td><td>${r.kind === 'ENDED' ? tag('AT_RISK', 'Hết hiệu lực') : tag('OPPORTUNITY', 'Có hiệu lực')}</td>
      <td><a href="#/luat?doc=${esc(r.doc_id)}">${esc(r.doc_type)} ${esc(r.doc_num)}</a><div class="muted small">${esc((r.title || '').slice(0, 150))}${r.by_doc_num ? `; thay bằng ${esc(r.by_doc_num)}` : ''}</div><div id="sum-${n}"></div></td>
      <td>${r.kind === 'EFFECTIVE' ? button('Tóm tắt điểm chính', 'ghost', `data-sum="${n}"`) : ''}</td></tr>`))}`;
  el.querySelectorAll('[data-sum]').forEach((b) => { b.onclick = async () => {
    const n = Number(b.dataset.sum); const box = $(`#sum-${n}`);
    box.innerHTML = loading('Mô hình trên máy đang đọc văn bản (30 đến 90 giây)');
    try {
      const a = await post(`/api/law/alerts/${encodeURIComponent(rows[n].doc_id)}/summary`);
      box.innerHTML = `<div class="answer"><div class="chips">${tag(a.mode)}</div>${a.sentences.map((s) => `<p style="margin:.4rem 0">${esc(s.text)} <span class="muted small">[${s.citations.map((c) => esc(c.path.split(' > ').slice(1).join(' > '))).join('; ')}]</span></p>`).join('')}
        ${a.dropped?.length ? `<div class="cite">${a.dropped.length} câu bị loại vì không có căn cứ.</div>` : ''}${a.note ? `<div class="cite">${esc(a.note)}</div>` : ''}</div>`;
    } catch (err) { box.innerHTML = notice('error', 'Không tóm tắt được', err.message); }
  }; });
}

// ---------------------------------------------------------------- F6 risk list import (settings page)
export function riskImport(el) {
  el.innerHTML = `<h3 style="margin-top:1.5rem">Nhập danh sách từ tệp</h3><p class="muted small">Tệp CSV hoặc văn bản bất kỳ có mã số thuế (ví dụ danh sách doanh nghiệp bỏ địa chỉ kinh doanh do cơ quan thuế công bố). Hệ thống lấy mọi mã số thuế hợp lệ trong tệp.</p>
    <div class="form-grid"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-name">Tên danh sách</label><input class="cds--text-input" id="rl-name" placeholder="Danh sách bỏ địa chỉ kinh doanh tháng 10/2026"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-date">Ngày của danh sách</label><input class="cds--text-input" id="rl-date" type="date"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-src">Nguồn</label><input class="cds--text-input" id="rl-src" placeholder="Thông báo của Thuế tỉnh ..."></div></div>
    <div class="bar"><input type="file" id="rl-file" accept=".csv,.txt" class="cds--visually-hidden">${button('Chọn tệp và nhập', 'secondary', 'id="rl-pick"')}<span id="rl-msg"></span></div>`;
  $('#rl-pick').onclick = () => {
    if (!$('#rl-name').value || !$('#rl-date').value) { $('#rl-msg').innerHTML = notice('warning', 'Cần tên và ngày của danh sách'); return; }
    $('#rl-file').click();
  };
  $('#rl-file').onchange = async () => {
    const f = $('#rl-file').files[0];
    try {
      const r = await api(`/api/workspaces/${state.ws}/risk-list?name=${encodeURIComponent($('#rl-name').value)}&as_of=${$('#rl-date').value}&source=${encodeURIComponent($('#rl-src').value)}`, { method: 'PUT', body: f });
      $('#rl-msg').innerHTML = notice('success', `Đã nhập ${r.tax_ids} mã số thuế`, r.rejected.length ? `Bỏ qua mã sai: ${r.rejected.join(', ')}` : 'Chạy lại phân tích để áp dụng.');
    } catch (err) { $('#rl-msg').innerHTML = notice('error', 'Không nhập được', err.message); }
  };
}
