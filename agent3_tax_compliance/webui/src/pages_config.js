// The fixed framework and the enterprise's own configuration: welcome page, set-up wizard, configuration page.
import { $, api, app, button, dmy, esc, field, loadWorkspaces, loading, money, notice, post, put, state, store, table } from './core.js';
import { riskImport } from './pages_ai.js';
import { toast } from './ux.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));
const MONTHS = Array.from({ length: 12 }, (_, i) => [String(i + 1), `Tháng ${i + 1}`]);

// ---------------------------------------------------------------- welcome: the fixed framework before any enterprise
export async function pageWelcome() {
  const list = state.workspaces;
  app().innerHTML = `<h1 class="page">Agent 3 trợ lý thuế</h1>
    <p class="lead">Khung kiểm tra thuế dùng chung cho mọi doanh nghiệp. Doanh nghiệp tự thiết lập cấu hình của mình trong vài phút để biến khung này thành trợ lý thuế riêng. Mọi dữ liệu xử lý trên máy này.</p>
    <div class="welcome-grid">
      <div class="panel welcome-main"><h3>Bắt đầu với doanh nghiệp của bạn</h3>
        <ol class="welcome-steps"><li><strong>Thiết lập</strong>: hồ sơ, năm tài chính, quy định chi tiêu nội bộ, nhóm hàng đặc thù, ngày nghỉ (khoảng 3 phút)</li>
          <li><strong>Nạp dữ liệu</strong>: thả hóa đơn XML, sao kê ngân hàng, bảng kê cổng thuế vào một ô</li>
          <li><strong>Xử lý việc cần làm</strong>: mỗi việc có số tiền, căn cứ và cách xử lý ít thiệt hại nhất</li></ol>
        <div class="bar">${button('Thiết lập doanh nghiệp của tôi', 'primary', 'data-go="#/thiet-lap"')}</div></div>
      <div class="panel"><h3>Xem thử trước</h3><p class="muted">Một doanh nghiệp mô phỏng có sẵn hóa đơn, sao kê hai ngân hàng và các tình huống rủi ro, để thử toàn bộ luồng. Không phải doanh nghiệp thật.</p>
        ${button('Xem thử với dữ liệu mô phỏng', 'tertiary', 'id="demo"')}<div id="demo-msg"></div></div>
    </div>
    <h2 class="section">Khung cố định có sẵn cho mọi doanh nghiệp</h2>
    <div class="fixed-grid">
      ${[['Đọc và kiểm tra hóa đơn điện tử', 'Chữ ký số, tổng tiền, hóa đơn trùng, bị thay thế, sai mã số thuế người mua'],
        ['Ghép chứng từ thanh toán', 'Khoản chi trong sao kê với hóa đơn; AI đọc nội dung chuyển khoản viết tự do'],
        ['14 luật rủi ro theo ngày hiệu lực', 'Ngưỡng thanh toán không dùng tiền mặt, mua nhiều lần trong ngày, người bán rủi ro, tiền thu chưa có hóa đơn'],
        ['Lịch thuế và mức thiệt hại', 'Hạn tờ khai, tạm nộp, quyết toán; tự khai bổ sung so với để bị phát hiện'],
        ['Kho luật tự cập nhật', 'Văn bản từ cổng pháp luật quốc gia, tự biết văn bản nào đã bị thay thế'],
        ['Trợ lý AI chạy trên máy', 'Chỉ đề xuất, có kiểm tra tự động, người duyệt quyết định']].map(([t, d]) => `<div class="fixed-card"><strong>${esc(t)}</strong><span class="muted small">${esc(d)}</span></div>`).join('')}
    </div>
    ${list.length ? `<h2 class="section">Doanh nghiệp đã thiết lập trên máy này</h2>${table(['Doanh nghiệp', 'Mã số thuế', ''], list.map((w) => `<tr><td>${esc(w.name)}${w.simulated ? ' <span class="muted small">(mô phỏng)</span>' : ''}</td><td>${esc(w.tax_code)}</td>
      <td>${button('Mở', 'ghost', `data-open="${esc(w.id)}"`)}</td></tr>`))}` : ''}`;
  $('#demo').onclick = async () => {
    $('#demo-msg').innerHTML = loading('Đang tạo dữ liệu mô phỏng');
    const r = await post('/api/demo');
    await post(`/api/workspaces/${r.id}/run`);
    openWorkspace(r.id);
  };
  app().querySelectorAll('[data-open]').forEach((b) => { b.onclick = () => openWorkspace(b.dataset.open); });
}

export async function openWorkspace(id, hash = '#/') {
  state.ws = id; store.set('agent3.ws', id);
  await loadWorkspaces();
  if (location.hash === hash) rerender(); else location.hash = hash;
}

// ---------------------------------------------------------------- set-up wizard
export async function pageSetup() {
  state.schema ||= await api('/api/schema');
  const presets = await api('/api/presets');
  const others = state.workspaces;
  const d = { profile: {}, policies: [], thresholds: {}, ai_categories: [], days_off: [], copy_from: '' };
  let step = Math.max(0, Math.min(5, Number(new URLSearchParams(location.hash.split('?')[1] || '').get('buoc') || 1) - 1));
  const steps = ['Hồ sơ', 'Quy định chi tiêu', 'Ngưỡng nội bộ', 'Nhóm hàng đặc thù', 'Ngày nghỉ', 'Xác nhận'];
  const draw = () => {
    const nav = `<nav class="steps">${steps.map((s, i) => `<a class="${i === step ? 'on' : ''}" ${i < step ? `data-step="${i}" href="javascript:void 0"` : ''}><span class="n">${i + 1}</span>${esc(s)}</a>`).join('')}</nav>`;
    let body = '';
    if (step === 0) {
      body = `<p class="muted">Thông tin trên giấy chứng nhận đăng ký thuế. Kỳ khai và năm tài chính quyết định lịch hạn nộp.</p>
        <div class="form-grid">${state.schema.profile.map((f) => field(f, d.profile[f.key] ?? (f.type === 'choice' ? f.choices[0][0] : ''))).join('')}
        ${field({ key: 'fiscal_year_end_month', label: 'Năm tài chính kết thúc vào tháng', type: 'choice', required: true, choices: MONTHS, help: 'Đa số doanh nghiệp là tháng 12 (năm dương lịch). Hạn quyết toán là ngày cuối tháng thứ 3 sau tháng này.' }, String(d.profile.fiscal_year_end_month || 12))}
        ${others.length ? field({ key: 'copy_from', label: 'Sao chép cấu hình từ doanh nghiệp khác', type: 'choice', choices: [['', 'Không sao chép'], ...others.map((w) => [w.id, w.name])], help: 'Lấy mẫu sao kê, quy định chi tiêu, ngưỡng, nhóm hàng đặc thù, ngày nghỉ; hồ sơ và dữ liệu vẫn riêng.' }, d.copy_from) : ''}</div>`;
    } else if (step === 1) {
      body = `<p class="muted">Chọn các quy định chi tiêu nội bộ doanh nghiệp đang áp dụng. Mỗi quy định chỉ thêm nhắc nhở cho kế toán, không làm thay đổi kết quả theo luật.</p>
        <div class="preset-list">${presets.policies.map((p, i) => `<label class="preset"><input type="checkbox" data-preset="${i}" ${d.policies.some((x) => x.id === p.id) ? 'checked' : ''}>
          <span><strong>${esc(p.flag)}</strong><span class="muted small">${p.min_gross ? `từ ${money(p.min_gross)}` : ''}${p.description_contains ? ` khi tên hàng có: ${p.description_contains.map(esc).join(', ')}` : ''}</span></span></label>`).join('')}</div>`;
    } else if (step === 2) {
      body = `<p class="muted">Ngưỡng của doanh nghiệp chỉ được chặt hơn luật. Để trống để dùng mức theo luật.</p><div class="form-grid">
        ${field({ key: 'match_days_after_invoice', label: 'Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán', example: '90 (không quá 90)', help: 'Khoản chi trả quá số ngày này sau hóa đơn sẽ không được tự ghép.' }, d.thresholds.match_days_after_invoice ?? '')}
        ${field({ key: 'non_cash_threshold_override', label: 'Ngưỡng nội bộ yêu cầu chuyển khoản (đồng)', example: 'ví dụ 2000000; để trống dùng 5.000.000 theo luật', help: 'Nếu công ty quy định mọi khoản từ 2 triệu phải chuyển khoản, nhập 2000000.' }, d.thresholds.non_cash_threshold_override ?? '')}</div>`;
    } else if (step === 3) {
      body = `<p class="muted">Nhóm hàng đặc thù của ngành mà AI có thể hiểu nhầm là chi tiêu cá nhân. Ví dụ nhà hàng mua thực phẩm, spa mua mỹ phẩm, công ty du lịch mua vé máy bay. AI sẽ coi các nhóm này là phục vụ kinh doanh.</p>
        <div id="cats">${(d.ai_categories.length ? d.ai_categories : [{ name: '', description: '' }]).map((c, i) => `<div class="form-grid cat-row">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${i}" data-k="name" value="${esc(c.name)}" placeholder="Nguyên liệu thực phẩm"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${i}" data-k="description" value="${esc(c.description)}" placeholder="thịt, cá, rau, gia vị dùng chế biến món ăn bán cho khách"></div></div>`).join('')}</div>
        <div class="bar">${button('Thêm nhóm', 'ghost', 'id="add-cat"')}<span class="muted small">Không bắt buộc. Tối đa 10 nhóm.</span></div>`;
    } else if (step === 4) {
      body = `<p class="muted">Ngày nghỉ Tết và nghỉ bù do Chính phủ công bố hằng năm. Hạn nộp trùng ngày nghỉ sẽ được dời sang ngày làm việc kế tiếp (khoản 7 Điều 3 Nghị định 252/2026). Thứ Bảy, Chủ nhật và lễ cố định (1/1, 30/4, 1/5, 2/9) đã có sẵn.</p>
        <div class="cds--form-item"><label class="cds--label" for="days">Mỗi dòng một ngày, dạng năm-tháng-ngày</label><textarea class="cds--text-area" id="days" rows="6" placeholder="2027-02-05&#10;2027-02-08">${esc(d.days_off.join('\n'))}</textarea></div>`;
    } else {
      body = `<p class="muted">Kiểm tra lại rồi tạo doanh nghiệp. Mọi mục đều sửa được sau trong trang Cấu hình doanh nghiệp.</p>
        <dl class="kv"><dt>Doanh nghiệp</dt><dd>${esc(d.profile.legal_name || '')} (MST ${esc(d.profile.tax_code || '')})</dd>
        <dt>Phương pháp, kỳ khai</dt><dd>${d.profile.vat_method === 'DIRECT' ? 'Trực tiếp' : 'Khấu trừ'}, ${d.profile.filing_period === 'QUARTER' ? 'theo quý' : 'theo tháng'}</dd>
        <dt>Năm tài chính kết thúc</dt><dd>tháng ${esc(d.profile.fiscal_year_end_month || 12)}</dd>
        <dt>Quy định chi tiêu</dt><dd>${d.policies.length ? d.policies.map((p) => esc(p.flag)).join('<br>') : 'không có'}</dd>
        <dt>Ngưỡng nội bộ</dt><dd>${Object.keys(d.thresholds).length ? Object.entries(d.thresholds).map(([k, v]) => `${k === 'match_days_after_invoice' ? 'Số ngày tối đa' : 'Ngưỡng chuyển khoản'}: ${esc(v)}`).join('<br>') : 'theo luật'}</dd>
        <dt>Nhóm hàng đặc thù</dt><dd>${d.ai_categories.length ? d.ai_categories.map((c) => esc(c.name)).join(', ') : 'không có'}</dd>
        <dt>Ngày nghỉ thêm</dt><dd>${d.days_off.length ? d.days_off.map(dmy).join(', ') : 'không có'}</dd>
        ${d.copy_from ? `<dt>Sao chép từ</dt><dd>${esc(others.find((w) => w.id === d.copy_from)?.name || '')}</dd>` : ''}</dl><div id="setup-msg"></div>`;
    }
    app().innerHTML = `<h1 class="page">Thiết lập doanh nghiệp</h1><p class="lead">Biến khung cố định thành trợ lý thuế của doanh nghiệp bạn. Bước ${step + 1}/${steps.length}: ${esc(steps[step])}.</p>${nav}<form id="setup">${body}
      <div class="bar">${step > 0 ? button('Quay lại', 'ghost', 'id="back"') : button('Hủy', 'ghost', 'data-go="#/"')}${button(step === steps.length - 1 ? 'Tạo doanh nghiệp' : 'Tiếp tục', 'primary', 'type="submit"')}</div></form>`;
    app().querySelectorAll('[data-step]').forEach((a) => { a.onclick = () => { collect(); step = Number(a.dataset.step); draw(); }; });
    if ($('#back')) $('#back').onclick = () => { collect(); step -= 1; draw(); };
    if ($('#add-cat')) $('#add-cat').onclick = () => { collect(); if (d.ai_categories.length < 10) d.ai_categories.push({ name: '', description: '' }); draw(); };
    $('#setup').onsubmit = async (e) => {
      e.preventDefault();
      if (!collect()) return;
      if (step < steps.length - 1) { step += 1; draw(); return; }
      $('#setup-msg').innerHTML = loading('Đang tạo doanh nghiệp');
      try {
        const r = await post('/api/workspaces', { ...d, by: store.get('agent3.reviewer') || '' });
        toast('Đã tạo doanh nghiệp', 'Tiếp theo: nạp hóa đơn và sao kê');
        openWorkspace(r.id, '#/nap?b=nhanh');
      } catch (err) { $('#setup-msg').innerHTML = notice('error', 'Chưa tạo được', err.message); }
    };
    if (step === 0) app().querySelector('input')?.focus();
  };
  const collect = () => {
    const f = $('#setup');
    if (!f) return true;
    if (step === 0) {
      const v = Object.fromEntries(new FormData(f).entries());
      d.copy_from = v.copy_from || '';
      delete v.copy_from;
      v.industry = (v.industry || '').split(';').map((s) => s.trim()).filter(Boolean);
      v.fiscal_year_end_month = Number(v.fiscal_year_end_month || 12);
      d.profile = v;
      if (!/^\d{10}(-\d{3})?$/.test(v.tax_code || '') || !(v.legal_name || '').trim()) { toast('Cần mã số thuế 10 hoặc 13 số và tên doanh nghiệp', '', 'error'); return false; }
    } else if (step === 1) {
      d.policies = [...f.querySelectorAll('[data-preset]')].filter((c) => c.checked).map((c) => presets.policies[Number(c.dataset.preset)]);
    } else if (step === 2) {
      const v = Object.fromEntries(new FormData(f).entries());
      d.thresholds = {};
      if (v.match_days_after_invoice) d.thresholds.match_days_after_invoice = Number(v.match_days_after_invoice);
      if (v.non_cash_threshold_override) d.thresholds.non_cash_threshold_override = Number(String(v.non_cash_threshold_override).replace(/\D/g, ''));
      if ((d.thresholds.match_days_after_invoice || 0) > 90) { toast('Số ngày không được quá 90 (chỉ được chặt hơn luật)', '', 'error'); return false; }
      if ((d.thresholds.non_cash_threshold_override || 0) > 5000000) { toast('Ngưỡng nội bộ không được cao hơn 5.000.000 đồng theo luật', '', 'error'); return false; }
    } else if (step === 3) {
      const cats = {};
      f.querySelectorAll('[data-cat]').forEach((i) => { cats[i.dataset.cat] ||= {}; cats[i.dataset.cat][i.dataset.k] = i.value.trim(); });
      d.ai_categories = Object.values(cats).filter((c) => c.name || c.description);
      if (d.ai_categories.some((c) => !c.name || !c.description)) { toast('Mỗi nhóm cần cả tên và mô tả', '', 'error'); return false; }
    } else if (step === 4) {
      d.days_off = $('#days').value.split(/\s+/).map((s) => s.trim()).filter(Boolean);
      if (d.days_off.some((s) => !/^\d{4}-\d{2}-\d{2}$/.test(s))) { toast('Ngày phải có dạng năm-tháng-ngày, ví dụ 2027-02-05', '', 'error'); return false; }
    }
    return true;
  };
  draw();
}

// ---------------------------------------------------------------- configuration page
export async function pageConfig() {
  if (!state.ws) { location.hash = '#/'; return; }
  state.schema ||= await api('/api/schema');
  const [pack, presets, history] = await Promise.all([api(`/api/workspaces/${state.ws}/pack`), api('/api/presets'), api(`/api/workspaces/${state.ws}/pack/history`)]);
  const save = async (next, msg) => {
    try { await put(`/api/workspaces/${state.ws}/pack?by=${encodeURIComponent(store.get('agent3.reviewer') || '')}`, next); toast(msg || 'Đã lưu cấu hình', 'Chạy lại phân tích để áp dụng'); await loadWorkspaces(); rerender(); }
    catch (err) { toast('Không lưu được', err.message, 'error'); }
  };
  const sec = (id, title, sub, inner) => `<section class="cfg" id="cfg-${id}"><h2 class="section">${esc(title)}</h2><p class="muted small">${esc(sub)}</p>${inner}</section>`;
  const cats = pack.ai_categories || [];
  app().innerHTML = `<h1 class="page">Cấu hình doanh nghiệp</h1>
    <p class="lead">Phần riêng của ${esc(pack.profile.legal_name)}. Khung cố định (luật rủi ro, kho luật, cách kiểm tra) dùng chung và không sửa ở đây; các mục dưới đây làm khung đó khớp với doanh nghiệp. Ngưỡng chỉ được chặt hơn luật, quy định nội bộ chỉ thêm nhắc nhở.</p>
    <nav class="cfg-nav">${[['ho-so', 'Hồ sơ'], ['ngan-hang', 'Mẫu sao kê'], ['bang-ke', 'Cột bảng kê'], ['quy-dinh', 'Quy định chi tiêu'], ['nguong', 'Ngưỡng'], ['nhom-hang', 'Nhóm hàng đặc thù'], ['ngay-nghi', 'Ngày nghỉ'], ['rui-ro', 'Danh sách rủi ro'], ['lich-su', 'Lịch sử thay đổi']]
      .map(([id, l]) => `<a href="javascript:void 0" data-jump="cfg-${id}">${esc(l)}</a>`).join('')}</nav>
    ${sec('ho-so', 'Hồ sơ', 'Thông tin trên giấy chứng nhận đăng ký thuế; kỳ khai và năm tài chính quyết định lịch hạn nộp.', `<form id="f-profile"><div class="form-grid">
      ${state.schema.profile.map((f) => field(f, pack.profile[f.key] ?? '')).join('')}
      ${field({ key: 'fiscal_year_end_month', label: 'Năm tài chính kết thúc vào tháng', type: 'choice', required: true, choices: MONTHS }, String(pack.profile.fiscal_year_end_month || 12))}</div>
      <div class="bar">${button('Lưu hồ sơ', 'primary', 'type="submit"')}</div></form>`)}
    ${sec('ngan-hang', 'Mẫu sao kê ngân hàng', 'Mỗi ngân hàng một mẫu; tạo bằng nút Nhận dạng cột ở Nạp dữ liệu, Sao kê ngân hàng.', table(['Tên mẫu', 'Cột ngày', 'Cột tiền ra', 'Cột tiền vào', 'Cách viết số', ''], (pack.bank_formats || []).map((f, i) => `<tr><td>${esc(f.name)}</td><td class="mono">${esc(f.columns.date)}</td>
      <td class="mono">${esc(f.columns.debit)}</td><td class="mono">${esc(f.columns.credit || '')}</td><td>${f.thousands === '.' ? '1.234.567' : '1,234,567'}</td><td>${button('Xóa', 'ghost', `data-delfmt="${i}"`)}</td></tr>`), 'Chưa có mẫu. Nạp sao kê rồi bấm Nhận dạng cột.') + `<div class="bar">${button('Thêm mẫu từ tệp sao kê', 'ghost', 'data-go="#/nap?b=bank"')}</div>`)}
    ${sec('bang-ke', 'Cột của bảng kê cổng thuế', 'Khi cổng hóa đơn điện tử đổi mẫu tệp xuất, chọn lại cột ở đây; không cần sửa tệp.', '<div id="portal-map"><div class="bar">' + button('Đọc tiêu đề bảng kê đã nạp', 'ghost', 'id="portal-load"') + '</div></div>')}
    ${sec('quy-dinh', 'Quy định chi tiêu nội bộ', 'Chỉ thêm nhắc nhở cho kế toán, không thay đổi kết quả theo luật.', `<div class="preset-list">${presets.policies.map((p, i) => `<label class="preset"><input type="checkbox" data-preset="${i}" ${(pack.policies || []).some((x) => x.id === p.id) ? 'checked' : ''}>
      <span><strong>${esc(p.flag)}</strong><span class="muted small">${p.min_gross ? `từ ${money(p.min_gross)}` : ''}${p.description_contains ? ` khi tên hàng có: ${p.description_contains.map(esc).join(', ')}` : ''}</span></span></label>`).join('')}
      ${(pack.policies || []).filter((x) => !presets.policies.some((p) => p.id === x.id)).map((x) => `<label class="preset"><input type="checkbox" checked data-custom="${esc(x.id)}"><span><strong>${esc(x.flag)}</strong><span class="muted small">quy định riêng</span></span></label>`).join('')}</div>
      <form id="f-pol" style="margin-top:.75rem"><div class="form-grid">${field({ key: 'flag', label: 'Thêm quy định riêng: nội dung nhắc', example: 'Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất' })}${field({ key: 'min_gross', label: 'Áp dụng từ số tiền (đồng)', example: '1000000' })}${field({ key: 'description_contains', label: 'Tên hàng có chứa (cách nhau dấu chấm phẩy)', example: 'giấy; bút; mực in' })}</div>
      <div class="bar">${button('Lưu quy định', 'primary', 'type="submit"')}</div></form>`)}
    ${sec('nguong', 'Ngưỡng nội bộ', 'Chỉ được chặt hơn luật; để trống để dùng mức theo luật.', `<form id="f-th"><div class="form-grid">
      ${field({ key: 'match_days_after_invoice', label: 'Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán', example: '90 (không quá 90)' }, pack.thresholds?.match_days_after_invoice ?? '')}
      ${field({ key: 'non_cash_threshold_override', label: 'Ngưỡng nội bộ yêu cầu chuyển khoản (đồng)', example: 'để trống dùng 5.000.000 theo luật' }, pack.thresholds?.non_cash_threshold_override ?? '')}</div>
      <div class="bar">${button('Lưu ngưỡng', 'primary', 'type="submit"')}</div></form>`)}
    ${sec('nhom-hang', 'Nhóm hàng đặc thù cho AI', 'AI coi các nhóm này là phục vụ kinh doanh khi phân loại dòng hàng (ví dụ nhà hàng mua thực phẩm). Chạy lại Phân loại dòng hàng sau khi đổi.', `<form id="f-cat">${(cats.length ? cats : [{ name: '', description: '' }]).concat([{ name: '', description: '' }]).map((c, i) => `<div class="form-grid cat-row">
      <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${i}" data-k="name" value="${esc(c.name)}" placeholder="Nguyên liệu thực phẩm"></div>
      <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${i}" data-k="description" value="${esc(c.description)}" placeholder="thịt, cá, rau dùng chế biến món ăn"></div></div>`).join('')}
      <div class="bar">${button('Lưu nhóm hàng', 'primary', 'type="submit"')}</div></form>`)}
    ${sec('ngay-nghi', 'Ngày nghỉ trong năm', 'Tết và nghỉ bù do Chính phủ công bố hằng năm; thứ Bảy, Chủ nhật và lễ cố định đã có sẵn.', `<form id="f-days"><div class="cds--form-item"><textarea class="cds--text-area" id="days" rows="4" placeholder="2027-02-05">${esc((pack.days_off || []).join('\n'))}</textarea></div>
      <div class="bar">${button('Lưu ngày nghỉ', 'primary', 'type="submit"')}</div></form>`)}
    ${sec('rui-ro', 'Danh sách doanh nghiệp rủi ro', 'Người bán trong danh sách sẽ được gắn cờ cần xem; luôn ghi ngày và nguồn.', table(['Tên danh sách', 'Ngày', { label: 'Số mã số thuế', num: true }, 'Nguồn'], (pack.reference_lists || []).map((r) => `<tr><td>${esc(r.name)}</td><td>${dmy(r.as_of)}</td><td class="num">${r.tax_ids.length}</td><td>${esc(r.source || '')}</td></tr>`), 'Chưa có.') + '<div id="riskimp"></div>')}
    ${sec('lich-su', 'Lịch sử thay đổi cấu hình', 'Ai đổi phần nào, lúc nào.', table(['Thời điểm', 'Người', 'Phần thay đổi'], history.slice(0, 30).map((h) => `<tr><td>${esc(h.at.replace('T', ' '))}</td><td>${esc(h.by)}</td><td>${h.created ? 'Tạo doanh nghiệp' : esc(h.changed.join(', '))}</td></tr>`), 'Chưa có thay đổi nào được ghi.'))}`;
  app().querySelectorAll('[data-jump]').forEach((a) => { a.onclick = () => document.getElementById(a.dataset.jump).scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  $('#f-profile').onsubmit = (e) => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.target).entries());
    v.industry = (v.industry || '').split(';').map((s) => s.trim()).filter(Boolean);
    v.fiscal_year_end_month = Number(v.fiscal_year_end_month || 12);
    save({ ...pack, profile: { ...pack.profile, ...v } }, 'Đã lưu hồ sơ');
  };
  app().querySelectorAll('[data-delfmt]').forEach((b) => { b.onclick = () => save({ ...pack, bank_formats: pack.bank_formats.filter((_, i) => i !== Number(b.dataset.delfmt)) }, 'Đã xóa mẫu sao kê'); });
  const policiesFromChecks = () => [
    ...presets.policies.filter((p, i) => app().querySelector(`[data-preset="${i}"]`).checked),
    ...(pack.policies || []).filter((x) => !presets.policies.some((p) => p.id === x.id) && app().querySelector(`[data-custom="${x.id}"]`)?.checked)];
  $('#f-pol').onsubmit = (e) => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.target).entries());
    const list = policiesFromChecks();
    if (v.flag) {
      const p = { id: `RIENG_${Date.now().toString(36).toUpperCase()}`, flag: v.flag };
      if (v.min_gross) p.min_gross = Number(String(v.min_gross).replace(/\D/g, ''));
      if (v.description_contains) p.description_contains = v.description_contains.split(';').map((s) => s.trim()).filter(Boolean);
      list.push(p);
    }
    save({ ...pack, policies: list }, 'Đã lưu quy định chi tiêu');
  };
  $('#f-th').onsubmit = (e) => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.target).entries());
    const th = {};
    if (v.match_days_after_invoice) th.match_days_after_invoice = Number(v.match_days_after_invoice);
    if (v.non_cash_threshold_override) th.non_cash_threshold_override = Number(String(v.non_cash_threshold_override).replace(/\D/g, ''));
    save({ ...pack, thresholds: th }, 'Đã lưu ngưỡng');
  };
  $('#f-cat').onsubmit = (e) => {
    e.preventDefault();
    const m = {};
    e.target.querySelectorAll('[data-cat]').forEach((i) => { m[i.dataset.cat] ||= {}; m[i.dataset.cat][i.dataset.k] = i.value.trim(); });
    save({ ...pack, ai_categories: Object.values(m).filter((c) => c.name && c.description) }, 'Đã lưu nhóm hàng đặc thù');
  };
  $('#f-days').onsubmit = (e) => {
    e.preventDefault();
    save({ ...pack, days_off: $('#days').value.split(/\s+/).map((s) => s.trim()).filter(Boolean) }, 'Đã lưu ngày nghỉ');
  };
  $('#portal-load').onclick = async () => {
    try {
      const s = await post(`/api/workspaces/${state.ws}/portal/suggest`);
      $('#portal-map').innerHTML = `<form id="f-portal"><div class="form-grid">${Object.entries(s.fields).map(([k, l]) => `<div class="cds--form-item"><div class="cds--select"><label class="cds--label">${esc(l)}</label>
        <div class="cds--select-input__wrapper"><select class="cds--select-input" name="${k}"><option value="">(không có)</option>${s.headers.map((h) => `<option ${h === s.current[k] ? 'selected' : ''}>${esc(h)}</option>`).join('')}</select></div></div></div>`).join('')}</div>
        <div class="bar">${button('Lưu cột bảng kê', 'primary', 'type="submit"')}</div></form>`;
      $('#f-portal').onsubmit = (e) => {
        e.preventDefault();
        const cols = Object.fromEntries([...new FormData(e.target).entries()].filter(([, v]) => v));
        save({ ...pack, portal_columns: cols }, 'Đã lưu cột bảng kê');
      };
    } catch (err) { $('#portal-map').insertAdjacentHTML('beforeend', notice('warning', 'Chưa đọc được bảng kê', err.message)); }
  };
  riskImport($('#riskimp'));
}
