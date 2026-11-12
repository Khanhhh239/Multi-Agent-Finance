// Data intake: one drop zone for everything, file-by-file status, editable bank mapping, coverage check before analysis.
import { $, api, app, button, dmy, esc, field, hashParams, loadWorkspaces, loading, money, needWorkspace, notice, post, put, saveBankFormat, state, table, tag } from './core.js';

const KIND_LABEL = { purchase_xml: 'Hóa đơn mua vào', sales_xml: 'Hóa đơn bán ra', bank: 'Sao kê ngân hàng', portal_list: 'Bảng kê cổng thuế' };
const FIELD_LABEL = { date: 'Ngày giao dịch', debit: 'Ghi nợ (tiền ra)', credit: 'Ghi có (tiền vào)', description: 'Nội dung', counterparty_account: 'Tài khoản đối ứng', counterparty_name: 'Tên đối ứng' };

function dropZone(accept, hint) {
  return `<div class="drop" id="drop"><input type="file" id="file" multiple ${accept ? `accept="${esc(accept)}"` : ''} class="cds--visually-hidden">
    ${button('Chọn tệp', 'primary', 'id="pick"')}<span class="muted">${esc(hint)}</span></div><div id="up"></div>`;
}

function bindDrop(onFiles) {
  const input = $('#file');
  $('#pick').onclick = () => input.click();
  input.onchange = () => onFiles([...input.files]);
  const drop = $('#drop');
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); onFiles([...e.dataTransfer.files]); };
}

function guideBox(spec, open) {
  return `<details class="guide" ${open ? 'open' : ''}><summary>Lấy tệp này ở đâu và cần lưu ý gì</summary><div class="guide-body"><ol>${spec.how.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
    ${spec.pitfalls.length ? `<p class="cell-title">Lưu ý</p><ul>${spec.pitfalls.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}</div></details>`;
}

function uploadResult(records) {
  const used = records.filter((r) => r.kind);
  const counts = Object.entries(used.reduce((a, r) => ({ ...a, [r.label]: (a[r.label] || 0) + 1 }), {})).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(', ');
  const rejected = records.filter((r) => !r.kind);
  const warned = used.filter((r) => /vẫn nạp để kiểm tra/.test(r.reason));
  const auto = used.filter((r) => r.auto_format);
  return `${used.length ? notice('success', `Đã nhận ${used.length} tệp`, counts) : ''}
    ${auto.map((r) => notice('info', `Sao kê ${r.file}: đã tự nhận dạng cột`, `Ngày: ${r.auto_format.columns.date}; ghi nợ: ${r.auto_format.columns.debit}; ghi có: ${r.auto_format.columns.credit}; nội dung: ${r.auto_format.columns.description}`
      + `${r.auto_format.columns.counterparty_name ? `; tên đối ứng: ${r.auto_format.columns.counterparty_name}` : '; chưa thấy cột tên đối ứng'}. Kiểm tra lại ở bước Sao kê ngân hàng nếu cần.`)).join('')}
    ${warned.length ? notice('warning', `${warned.length} hóa đơn ghi sai mã số thuế doanh nghiệp`, warned.map((r) => `${r.file}: ${r.reason}`).join('; ')) : ''}
    ${rejected.length ? `<div class="panel"><h3>${rejected.length} tệp không dùng</h3>${table(['Tệp', 'Lý do'], rejected.map((r) => `<tr><td class="mono">${esc(r.file)}</td><td>${esc(r.reason)}</td></tr>`))}</div>` : ''}`;
}

async function sendAll(files, url) {
  const records = [];
  for (const [i, f] of files.entries()) {
    $('#up').innerHTML = loading(`Đang nạp ${i + 1}/${files.length}: ${f.name}`);
    try {
      const r = await api(`${url}?name=${encodeURIComponent(f.name)}`, { method: 'PUT', body: f });
      records.push(...(r.files || r.saved.map((n) => ({ file: n, kind: 'ok', label: 'Tệp', reason: '' }))));
    } catch (err) { records.push({ file: f.name, kind: null, label: 'Không dùng', reason: err.message }); }
  }
  await loadWorkspaces();
  return records;
}

function detailsTable(kind, rows) {
  if (!rows.length) return '<div class="empty">Chưa có tệp.</div>';
  const bad = rows.filter((r) => !r.ok).length;
  const head = bad ? notice('warning', `${bad} trên ${rows.length} tệp có lỗi`, 'Xem cột Tình trạng; tệp lỗi vẫn được giữ, hệ thống báo trong Việc cần xử lý.') : notice('success', `${rows.length} tệp đọc tốt`);
  if (kind === 'purchase_xml' || kind === 'sales_xml') {
    return head + table(['Tệp', 'Hóa đơn', 'Ngày', kind === 'purchase_xml' ? 'Người bán' : 'Người mua', { label: 'Tổng thanh toán', num: true }, 'Tình trạng'],
      rows.map((r) => `<tr><td class="mono small">${esc(r.file)}</td><td>${esc(r.number || '')}</td><td>${dmy(r.date)}</td><td>${esc(r.party || '')}</td>
        <td class="num">${money(r.gross)}</td><td>${r.ok ? tag('LLM_VERIFIED', 'Đọc tốt') : tag('AT_RISK', 'Có lỗi')}<div class="muted small">${esc((r.errors || []).join(', '))}</div></td></tr>`));
  }
  if (kind === 'bank') {
    return head + table(['Tệp', { label: 'Giao dịch', num: true }, 'Từ ngày', 'Đến ngày', 'Tình trạng', ''], rows.map((r) => `<tr><td class="mono small">${esc(r.file)}</td>
      <td class="num">${r.rows ?? ''}</td><td>${dmy(r.first)}</td><td>${dmy(r.last)}</td><td>${r.ok ? tag('LLM_VERIFIED', 'Đọc tốt') : tag('AT_RISK', 'Chưa đọc được')}<div class="muted small">${esc((r.errors || []).join(', '))}</div></td>
      <td>${/\.(csv|xlsx)$/i.test(r.file) ? button(r.ok ? 'Xem cột' : 'Nhận dạng cột', r.ok ? 'ghost' : 'primary', `data-suggest="${esc(r.file)}"`) : ''}</td></tr>`));
  }
  return head + table(['Tệp', { label: 'Số dòng', num: true }, 'Tình trạng'], rows.map((r) => `<tr><td class="mono small">${esc(r.file)}</td><td class="num">${r.rows ?? ''}</td>
    <td>${r.ok ? tag('LLM_VERIFIED', 'Đọc tốt') : tag('AT_RISK', 'Chưa đọc được')}<div class="muted small">${esc((r.errors || []).join(', '))}</div></td></tr>`));
}

async function mappingEditor(name) {
  const box = $('#suggest');
  box.innerHTML = loading('Đang nhận dạng cột');
  let s;
  try { s = await post(`/api/workspaces/${state.ws}/bank/suggest?name=${encodeURIComponent(name)}`); } catch (err) { box.innerHTML = notice('error', 'Không nhận dạng được', err.message); return; }
  const fmt = structuredClone(s.format);
  const opts = (cur) => `<option value="">(không có)</option>${s.headers.map((h) => `<option ${h === cur ? 'selected' : ''}>${esc(h)}</option>`).join('')}`;
  box.innerHTML = `<div class="panel"><h3>Cột của ${esc(name)}</h3><p class="muted">Hệ thống đã đoán cột ở dòng tiêu đề số ${s.header_row}. Nếu đoán sai, chọn lại; bản xem trước cập nhật ngay. Lưu mẫu một lần, lần sau tệp cùng ngân hàng được đọc tự động.</p>
    <div class="form-grid">${Object.keys(FIELD_LABEL).map((k) => `<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-${k}">${FIELD_LABEL[k]}${k === 'date' || k === 'debit' ? '' : ' (không bắt buộc)'}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-${k}" data-col="${k}">${opts(fmt.columns[k])}</select></div></div></div>`).join('')}
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-num">Cách viết số tiền</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-num">
        <option value=".," ${fmt.thousands === '.' ? 'selected' : ''}>1.234.567,00 (dấu chấm ngăn nghìn)</option><option value=",." ${fmt.thousands === ',' ? 'selected' : ''}>1,234,567.00 (dấu phẩy ngăn nghìn)</option></select></div></div></div>
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-date">Cách viết ngày</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-date">
        ${[['%d/%m/%Y', '31/12/2026'], ['%Y-%m-%d', '2026-12-31'], ['%d-%m-%Y', '31-12-2026'], ['%d.%m.%Y', '31.12.2026']].map(([v, l]) => `<option value="${v}" ${fmt.date_format === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div></div></div></div>
    <div id="pv"></div>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="fmt-name">Tên mẫu (thường là tên ngân hàng)</label><input class="cds--text-input" id="fmt-name" value="${esc(fmt.name)}"></div>
      ${button('Lưu mẫu sao kê', 'primary', 'id="save-fmt"')}<span id="fmt-msg"></span></div></div>`;
  const read = () => {
    box.querySelectorAll('[data-col]').forEach((sel) => { if (sel.value) fmt.columns[sel.dataset.col] = sel.value; else delete fmt.columns[sel.dataset.col]; });
    [fmt.thousands, fmt.decimal] = $('#m-num').value.split('');
    fmt.date_format = $('#m-date').value;
    fmt.name = $('#fmt-name').value || fmt.name;
    return fmt;
  };
  const refresh = async () => {
    $('#pv').innerHTML = loading('Đang đọc thử');
    try {
      const p = await post(`/api/workspaces/${state.ws}/bank/preview?name=${encodeURIComponent(name)}`, read());
      $('#pv').innerHTML = `<h3 style="margin-top:1rem">Đọc thử ${p.preview.length} dòng đầu</h3>${p.errors ? notice('warning', `${p.errors} dòng không đọc được`, 'Kiểm tra cách viết ngày và số tiền.') : ''}
        ${table(['Ngày', { label: 'Tiền ra', num: true }, { label: 'Tiền vào', num: true }, 'Đối ứng', 'Nội dung'], p.preview.map((r) => (r.error
          ? `<tr><td colspan="5">${esc(r.error)}</td></tr>` : `<tr><td>${dmy(r.date)}</td><td class="num">${money(r.debit)}</td><td class="num">${money(r.credit)}</td><td>${esc(r.counterparty)}</td><td>${esc(r.description)}</td></tr>`)))}`;
    } catch (err) { $('#pv').innerHTML = notice('error', 'Chưa đọc được với cách chọn này', err.message); }
  };
  box.querySelectorAll('select').forEach((sel) => { sel.onchange = refresh; });
  refresh();
  $('#save-fmt').onclick = async () => {
    const submit = $('#save-fmt'); submit.disabled = true;
    try { await saveBankFormat(read()); $('#fmt-msg').innerHTML = notice('success', 'Đã lưu mẫu; chạy lại phân tích để kiểm tra toàn bộ tệp'); }
    catch (err) { $('#fmt-msg').innerHTML = notice('error', 'Không lưu được', err.message); }
    finally { if (submit.isConnected) submit.disabled = false; }
  };
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export async function pageBankFormats() {
  await api(`/api/workspaces/${state.ws}/pack`);
  const rows = await api(`/api/workspaces/${state.ws}/details/bank`);
  app().innerHTML = `<h1 class="page">Nhận dạng cột sao kê</h1><p class="lead">Chỉnh cách đọc các tệp đã nạp. Lưu mẫu cần quyền quản trị; thao tác này không nạp thêm tệp.</p>${detailsTable('bank', rows)}<div id="suggest"></div>`;
  app().querySelectorAll('[data-suggest]').forEach(b => { b.onclick = () => mappingEditor(b.dataset.suggest); });
}

export async function pageDataWorkspace() {
  const versions = await api(`/api/workspaces/${state.ws}/portal/lists`);
  app().innerHTML = `<h1 class="page">Bảng kê cổng thuế đang sử dụng</h1>
    <p class="lead">Các bản nguồn được giữ riêng. Chỉ bản được chọn mới được phân tích; chọn lại không xóa bản cũ.</p>
    ${versions.error ? notice('warning', 'Cần chọn bản bảng kê', versions.error) : ''}
    <form id="active-list"><label for="list-version">Bản nguồn</label><select id="list-version" class="cds--select-input" required><option value="">Chọn bảng kê</option>${versions.files.map(name => `<option value="${esc(name)}" ${name === versions.active ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select>
    <div class="bar">${button('Sử dụng bản này', 'primary', 'type="submit"')}<span id="list-result"></span></div></form>
    <a class="cds--btn cds--btn--ghost" href="#/quan-tri/mau-sao-ke">Nhận dạng cột sao kê (quản trị)</a>`;
  $('#active-list').onsubmit = async e => {
    e.preventDefault(); const submit = e.target.querySelector('button'); submit.disabled = true;
    try { await put(`/api/workspaces/${state.ws}/portal/active-list`, {name: $('#list-version').value}); $('#list-result').innerHTML = notice('success', 'Đã chọn bảng kê; chạy lại phân tích để áp dụng.'); }
    catch (err) { $('#list-result').innerHTML = notice('error', 'Không đổi được bảng kê', err.message); }
    finally { if (submit.isConnected) submit.disabled = false; }
  };
}

export async function pageIntake() {
  if (needWorkspace()) return;
  state.schema ||= await api('/api/schema');
  const pack = await api(`/api/workspaces/${state.ws}/pack`);
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const kinds = state.schema.files.filter((f) => f.folder);
  const total = Object.values(ws?.files || {}).reduce((a, n) => a + (Number(n) || 0), 0);
  const asked = hashParams().get('b');
  const step = asked === 'chay' ? 'chay' : asked === 'nhanh' ? 'nhanh' : asked ? 'da-nap' : (total ? 'chay' : 'nhanh');
  const steps = [['nhanh', 'Nạp tệp'], ['da-nap', `Tệp đã nạp (${total})`], ['chay', 'Kiểm tra và chạy']];
  const header = `<h1 class="page">Nạp dữ liệu</h1><p class="lead">Doanh nghiệp tự xuất tệp từ cổng hóa đơn điện tử, ngân hàng điện tử và phần mềm đang dùng. Hệ thống không đăng nhập thay doanh nghiệp và không gửi dữ liệu ra ngoài máy này.</p>
    <nav class="steps">${steps.map(([k, l], i) => `<a href="#/nap?b=${k}" class="${k === step ? 'on' : ''}"><span class="n">${i + 1}</span>${esc(l)}</a>`).join('')}</nav>`;

  if (step === 'nhanh') {
    app().innerHTML = `${header}<p>Thả cùng lúc mọi thứ đang có: tệp XML hóa đơn (mua vào và bán ra), tệp nén .zip, sao kê Excel, CSV hoặc MT940, bảng kê từ cổng thuế. Hệ thống tự nhận ra từng loại theo nội dung tệp, không cần đặt tên hay chia thư mục.</p>
      ${dropZone('.xml,.zip,.csv,.xlsx,.sta,.mt940,.txt', 'hoặc kéo thả tất cả vào đây')}
      <details class="guide"><summary>Lấy các tệp này ở đâu</summary><div class="guide-body">${kinds.map((k) => `<p class="cell-title">${esc(k.label)}</p><ol>${k.how.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`).join('')}</div></details>`;
    bindDrop(async (files) => {
      const recs = await sendAll(files, `/api/workspaces/${state.ws}/inbox`);
      const now = Object.values(state.workspaces.find((w) => w.id === state.ws)?.files || {}).reduce((a, n) => a + (Number(n) || 0), 0);
      const tab = app().querySelector('.steps a[href="#/nap?b=da-nap"]');
      if (tab) tab.lastChild.textContent = `Tệp đã nạp (${now})`;
      $('#up').innerHTML = `${uploadResult(recs)}<div id="autorun">${loading('Đang tự chạy phân tích với dữ liệu mới')}</div>`;
      if (recs.some((r) => r.kind)) {
        try {
          const rep = await post(`/api/workspaces/${state.ws}/run`);
          const cov = await api(`/api/workspaces/${state.ws}/coverage`);
          $('#autorun').innerHTML = notice('success', 'Đã phân tích xong', `${rep.items.length} việc; thuế có nguy cơ ${money(rep.totals.at_risk_vat)}`)
            + cov.filter((w) => w.level === 'warning').map((w) => notice('warning', w.title, w.detail)).join('')
            + `<div class="bar">${button('Xem việc cần xử lý', 'primary', 'data-go="#/viec"')}${button('Về tổng quan', 'ghost', 'data-go="#/"')}</div>`;
        } catch (err) { $('#autorun').innerHTML = notice('error', 'Phân tích chưa chạy được', err.message); }
      } else { $('#autorun').innerHTML = ''; }
    });
    return;
  }
  if (step === 'chay') {
    app().innerHTML = `${header}<h2 class="section" style="margin-top:0">Kiểm tra trước khi phân tích</h2><div id="cov">${loading('Đang kiểm tra dữ liệu đã nạp')}</div>
      <div class="bar">${button('Chạy phân tích', 'primary', 'id="run2"')}<span id="r2"></span></div>`;
    $('#run2').onclick = async () => {
      $('#r2').innerHTML = loading('Đang phân tích');
      try { await post(`/api/workspaces/${state.ws}/run`); location.hash = '#/'; } catch (err) { $('#r2').innerHTML = notice('error', 'Phân tích không chạy được', err.message); }
    };
    try {
      const cov = await api(`/api/workspaces/${state.ws}/coverage`);
      $('#cov').innerHTML = cov.length ? cov.map((w) => notice(w.level === 'warning' ? 'warning' : 'info', w.title, w.detail)).join('')
        : notice('success', 'Dữ liệu đủ để phân tích', 'Có hóa đơn, sao kê phủ các tháng có hóa đơn và bảng kê cổng thuế.');
    } catch (err) { $('#cov').innerHTML = notice('error', 'Không kiểm tra được', err.message); }
    return;
  }
  // "Tệp đã nạp": every kind in one page, each with its file-by-file reading status
  app().innerHTML = `${header}${kinds.map((k) => `<h2 class="section">${esc(k.label)} (${ws?.files?.[k.key] ?? 0})</h2><div id="det-${k.key}">${loading('Đang đọc từng tệp')}</div>`).join('')}<div id="suggest"></div>`;
  await Promise.all(kinds.map(async (k) => {
    try {
      const rows = await api(`/api/workspaces/${state.ws}/details/${k.key}`);
      $(`#det-${k.key}`).innerHTML = detailsTable(k.key, rows);
    } catch (err) { $(`#det-${k.key}`).innerHTML = notice('error', 'Không đọc được danh sách tệp', err.message); }
  }));
  app().querySelectorAll('[data-suggest]').forEach((b) => { b.onclick = () => mappingEditor(b.dataset.suggest); });
}

export const KIND_LABELS = KIND_LABEL;
