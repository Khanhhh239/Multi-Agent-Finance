// The fixed framework and the enterprise's own configuration: welcome page, set-up wizard, configuration page.
import { $, api, app, button, dmy, esc, field, loadWorkspaces, loading, money, notice, post, put, state, store, table } from './core.js';
import { riskImport } from './pages_ai.js';
import { toast } from './ux.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));
const POLICY_FIELDS = ['id', 'flag', 'min_gross', 'description_contains'];
const cleanPolicy = (p) => Object.fromEntries(POLICY_FIELDS.filter((k) => p[k] !== undefined && p[k] !== '' && !(Array.isArray(p[k]) && !p[k].length)).map((k) => [k, p[k]]));

// One editable policy card: tick to apply, and change the reminder text, the amount and the item words.
function policyCard(p, i, checked, prefix = 'pol') {
  return `<div class="preset ${checked ? 'on' : ''}" data-card="${i}"><input type="checkbox" data-${prefix}="${i}" ${checked ? 'checked' : ''} aria-label="Áp dụng">
    <div class="preset-body"><div class="preset-head"><strong>${esc(p.flag)}</strong>${p.industry_fit ? '<span class="badge-fit">Gợi ý cho ngành của bạn</span>' : p.recommended ? '<span class="badge-rec">Nên dùng</span>' : ''}${p.group ? `<span class="muted small">${esc(p.group)}</span>` : ''}</div>
    <div class="preset-edit">
      <label>Nội dung nhắc<input class="cds--text-input" data-f="flag" value="${esc(p.flag)}"></label>
      <label>Áp dụng từ số tiền (đồng)<input class="cds--text-input" data-f="min_gross" inputmode="numeric" value="${p.min_gross ?? ''}" placeholder="mọi số tiền"></label>
      <label>Khi tên hàng có (cách nhau dấu phẩy)<input class="cds--text-input" data-f="description_contains" value="${esc((p.description_contains || []).join(', '))}" placeholder="mọi hàng hóa"></label></div></div></div>`;
}

function readCard(card) {
  const g = (f) => card.querySelector(`[data-f="${f}"]`).value.trim();
  const amount = Number(g('min_gross').replace(/\D/g, '')) || undefined;
  return { flag: g('flag'), min_gross: amount, description_contains: g('description_contains').split(',').map((x) => x.trim()).filter(Boolean) };
}

// Live offline check of a tax code (format and check digit) under the input.
export function bindTaxCheck(input, box, onResult) {
  if (!input) return;
  let t = null;
  const run = async () => {
    const v = input.value.trim();
    if (!v) { box.innerHTML = ''; onResult?.(null); return; }
    try {
      const r = await api(`/api/check-tax-id?mst=${encodeURIComponent(v)}`);
      box.innerHTML = `<div class="taxcheck ${r.ok ? 'ok' : 'bad'}">${r.ok ? '✓' : '✗'} ${esc(r.reason)}</div>`;
      onResult?.(r);
    } catch { box.innerHTML = ''; }
  };
  input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 300); });
  run();
}
const MONTHS = Array.from({ length: 12 }, (_, i) => [String(i + 1), `Tháng ${i + 1}`]);

// ---------------------------------------------------------------- welcome: the fixed framework before any enterprise
export async function pageWelcome() {
  const list = state.workspaces;
  const ICONS = [
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><polyline points="9 15 11 17 15 13"/></svg>`,
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`,
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--a3-primary);margin-bottom:8px" aria-hidden="true"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="4" y="8" width="16" height="12" rx="2"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/><path d="M9 17h6"/></svg>`
  ];
  const fixedItems = [
    ['Đọc và kiểm tra hóa đơn điện tử', 'Chữ ký số, tổng tiền, hóa đơn trùng, bị thay thế, sai mã số thuế người mua'],
    ['Ghép chứng từ thanh toán', 'Khoản chi trong sao kê với hóa đơn; AI đọc nội dung chuyển khoản viết tự do'],
    ['14 luật rủi ro theo ngày hiệu lực', 'Ngưỡng thanh toán không dùng tiền mặt, mua nhiều lần trong ngày, người bán rủi ro, tiền thu chưa có hóa đơn'],
    ['Lịch thuế và mức thiệt hại', 'Hạn tờ khai, tạm nộp, quyết toán; tự khai bổ sung so với để bị phát hiện'],
    ['Kho luật tự cập nhật', 'Văn bản từ cổng pháp luật quốc gia, tự biết văn bản nào đã bị thay thế'],
    ['Trợ lý AI chạy trên máy', 'Chỉ đề xuất, có kiểm tra tự động, người duyệt quyết định']
  ];

  app().innerHTML = `<span class="eyebrow">Hệ thống Trợ lý Thuế GTGT Doanh nghiệp</span>
    <h1 class="page">Agent 3 trợ lý thuế</h1>
    <p class="lead">Khung kiểm tra thuế dùng chung cho mọi doanh nghiệp. Doanh nghiệp tự thiết lập cấu hình của mình trong vài phút để biến khung này thành trợ lý thuế riêng. Mọi dữ liệu xử lý an toàn nội bộ trên máy này.</p>
    <div class="welcome-grid">
      <div class="panel welcome-main">
        <h3 style="margin-top:0;font-size:18px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>🚀</span> Bắt đầu với doanh nghiệp của bạn
        </h3>
        <ol class="welcome-steps">
          <li><strong>Thiết lập</strong>: hồ sơ, năm tài chính, quy định chi tiêu nội bộ, nhóm hàng đặc thù, ngày nghỉ (khoảng 3 phút)</li>
          <li><strong>Nạp dữ liệu</strong>: thả hóa đơn XML, sao kê ngân hàng, bảng kê cổng thuế vào một ô</li>
          <li><strong>Xử lý việc cần làm</strong>: mỗi việc có số tiền, căn cứ và cách xử lý ít thiệt hại nhất</li>
        </ol>
        <div class="bar">${button('Thiết lập doanh nghiệp của tôi', 'primary', 'data-go="#/thiet-lap"')}</div>
      </div>
      <div class="panel">
        <h3 style="margin-top:0;font-size:18px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>🧪</span> Xem thử trước
        </h3>
        <p class="muted" style="line-height:1.65;font-size:13.5px">Một doanh nghiệp mô phỏng có sẵn hóa đơn, sao kê hai ngân hàng và các tình huống rủi ro, để thử toàn bộ luồng. Không phải doanh nghiệp thật.</p>
        <div class="bar" style="margin-top:20px">${button('Xem thử với dữ liệu mô phỏng', 'tertiary', 'id="demo"')}</div>
        <div id="demo-msg"></div>
      </div>
    </div>

    <h2 class="section">Khung cố định có sẵn cho mọi doanh nghiệp</h2>
    <div class="fixed-grid">
      ${fixedItems.map(([t, d], idx) => `<div class="fixed-card">
        ${ICONS[idx]}
        <strong>${esc(t)}</strong>
        <span class="muted small">${esc(d)}</span>
      </div>`).join('')}
    </div>

    ${list.length ? `<h2 class="section">Doanh nghiệp đã thiết lập trên máy này</h2>${table(['Doanh nghiệp', 'Mã số thuế', ''], list.map((w) => `<tr><td><strong>${esc(w.name)}</strong>${w.simulated ? ' <span class="cds--tag cds--tag--magenta" style="margin-left:6px">mô phỏng</span>' : ''}</td><td><code>${esc(w.tax_code)}</code></td>
      <td>${button('Mở không gian làm việc', 'ghost', `data-open="${esc(w.id)}"`)}</td></tr>`))}` : ''}`;
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
  let presets = null;
  let presetsKey = null;
  const others = state.workspaces;
  const d = { profile: {}, policies: [], custom: [], picked: null, edits: {}, thresholds: {}, ai_categories: [], days_off: [], copy_from: '' };
  let taxCheck = null;
  let step = Math.max(0, Math.min(5, Number(new URLSearchParams(location.hash.split('?')[1] || '').get('buoc') || 1) - 1));
  const steps = ['Hồ sơ', 'Quy định chi tiêu', 'Ngưỡng nội bộ', 'Nhóm hàng đặc thù', 'Ngày nghỉ', 'Xác nhận'];
  const draw = () => {
    const nav = `<nav class="steps">${steps.map((s, i) => `<a class="${i === step ? 'on' : i < step ? 'done' : ''}" ${i < step ? `data-step="${i}" href="javascript:void 0"` : ''}><span class="n">${i < step ? '✓' : i + 1}</span>${esc(s)}</a>`).join('')}</nav>`;
    let body = '';
    if (step === 1) {
      const key = (d.profile.industry || []).join(';');
      if (!presets || presetsKey !== key) {
        api(`/api/presets?industry=${encodeURIComponent(key)}`).then((r) => {
          presets = r.policies; presetsKey = key;
          if (d.picked === null) d.picked = new Set(presets.filter((x) => x.recommended).map((x) => x.id));
          draw();
        });
        app().innerHTML = `<h1 class="page">Thiết lập doanh nghiệp</h1>${loading('Đang chọn gợi ý theo ngành nghề')}`;
        return;
      }
    }
    if (step === 0) {
      body = `<p class="muted">Thông tin trên giấy chứng nhận đăng ký thuế. Kỳ khai và năm tài chính quyết định lịch hạn nộp. Ngành nghề (mã VSIC) dùng để gợi ý quy định chi tiêu ở bước sau.</p>
        <div class="form-grid">${state.schema.profile.map((f) => field(f, d.profile[f.key] ?? (f.type === 'choice' ? f.choices[0][0] : ''))).join('')}
        ${field({ key: 'fiscal_year_end_month', label: 'Năm tài chính kết thúc vào tháng', type: 'choice', required: true, choices: MONTHS, help: 'Đa số doanh nghiệp là tháng 12 (năm dương lịch). Hạn quyết toán là ngày cuối tháng thứ 3 sau tháng này.' }, String(d.profile.fiscal_year_end_month || 12))}
        ${others.length ? field({ key: 'copy_from', label: 'Sao chép cấu hình từ doanh nghiệp khác', type: 'choice', choices: [['', 'Không sao chép'], ...others.map((w) => [w.id, w.name])], help: 'Lấy mẫu sao kê, quy định chi tiêu, ngưỡng, nhóm hàng đặc thù, ngày nghỉ; hồ sơ và dữ liệu vẫn riêng.' }, d.copy_from) : ''}</div>`;
    } else if (step === 1) {
      const codes = (d.profile.industry || []).map((x) => (String(x).match(/^\s*(\d{2,5})/) || [])[1]).filter(Boolean);
      body = `<p class="muted">Quy định chi tiêu nội bộ: mỗi quy định chỉ thêm nhắc nhở cho kế toán khi gặp hóa đơn phù hợp, không làm thay đổi kết quả theo luật.
        ${codes.length ? `Đã đánh dấu sẵn các mục gợi ý cho ngành ${codes.map(esc).join(', ')}.` : 'Chưa có ngành nghề ở bước 1 nên chỉ gợi ý các mục chung.'} Sửa nội dung, số tiền, từ khóa theo quy chế của doanh nghiệp.</p>
        <div class="preset-list">${presets.map((p, i) => policyCard({ ...p, ...(d.edits[p.id] || {}) }, i, d.picked.has(p.id))).join('')}</div>
        <h3 class="sub-h">Quy định riêng của doanh nghiệp</h3>
        <div id="custom-list">${d.custom.map((c, i) => policyCard({ ...c, recommended: false }, i, true, 'cus')).join('') || '<p class="muted small">Chưa có. Ví dụ: "Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất" khi tên hàng có "giấy, bút, mực in".</p>'}</div>
        <div class="bar">${button('Thêm quy định riêng', 'ghost', 'id="add-pol"')}</div>`;
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
    app().innerHTML = `<span class="eyebrow">Cấu hình khởi tạo doanh nghiệp</span>
      <h1 class="page">Thiết lập doanh nghiệp</h1>
      <p class="lead">Biến khung kiểm tra thuế dùng chung thành trợ lý thuế riêng của doanh nghiệp. Bước ${step + 1}/${steps.length}: <strong>${esc(steps[step])}</strong>.</p>
      ${nav}
      <form id="setup">
        <div class="panel" style="padding:26px 28px;border-radius:12px;box-shadow:var(--a3-shadow-sm);margin-bottom:20px;border:1px solid var(--cds-border-subtle)">${body}</div>
        <div class="bar">${step > 0 ? button('Quay lại', 'ghost', 'id="back"') : button('Hủy', 'ghost', 'data-go="#/"')}${button(step === steps.length - 1 ? 'Tạo doanh nghiệp' : 'Tiếp tục', 'primary', 'type="submit"')}</div>
      </form>`;
    app().querySelectorAll('[data-step]').forEach((a) => { a.onclick = () => { collect(); step = Number(a.dataset.step); draw(); }; });
    if ($('#back')) $('#back').onclick = () => { collect(); step -= 1; draw(); };
    app().querySelectorAll('[data-pol],[data-cus]').forEach((c) => { c.onchange = () => c.closest('[data-card]').classList.toggle('on', c.checked); });
    if ($('#add-pol')) $('#add-pol').onclick = () => { collect(); d.custom.push({ flag: 'Quy định mới: sửa nội dung nhắc', description_contains: [] }); draw(); };
    if (step === 0) {
      const tax = $('#f-tax_code');
      if (tax && !$('#mst-msg')) tax.closest('.cds--form-item').insertAdjacentHTML('beforeend', '<div id="mst-msg"></div>');
      bindTaxCheck(tax, $('#mst-msg'), (r) => { taxCheck = r; });
    }
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
      if (taxCheck && !taxCheck.ok) { toast('Mã số thuế chưa hợp lệ', taxCheck.reason, 'error'); return false; }
      if (!(v.legal_name || '').trim()) { toast('Cần tên doanh nghiệp đúng như trên giấy đăng ký thuế', '', 'error'); return false; }
    } else if (step === 1) {
      d.picked = new Set();
      f.querySelectorAll('[data-pol]').forEach((c) => {
        const p = presets[Number(c.dataset.pol)];
        d.edits[p.id] = readCard(c.closest('[data-card]'));
        if (c.checked) d.picked.add(p.id);
      });
      d.custom = [...f.querySelectorAll('[data-cus]')].filter((c) => c.checked).map((c) => readCard(c.closest('[data-card]'))).filter((c) => c.flag);
      d.policies = [...presets.filter((p) => d.picked.has(p.id)).map((p) => cleanPolicy({ id: p.id, ...d.edits[p.id] })),
        ...d.custom.map((c, i) => cleanPolicy({ id: `RIENG_${i + 1}`, ...c }))];
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
  const [pack, history] = await Promise.all([api(`/api/workspaces/${state.ws}/pack`), api(`/api/workspaces/${state.ws}/pack/history`)]);
  const presets = { policies: (await api(`/api/presets?industry=${encodeURIComponent((pack.profile.industry || []).join(';'))}`)).policies };
  const save = async (next, msg) => {
    try { await put(`/api/workspaces/${state.ws}/pack?by=${encodeURIComponent(store.get('agent3.reviewer') || '')}`, next); toast(msg || 'Đã lưu cấu hình', 'Chạy lại phân tích để áp dụng'); await loadWorkspaces(); rerender(); }
    catch (err) { toast('Không lưu được', err.message, 'error'); }
  };
  const SEC_ICONS = {
    'ho-so': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
    'ngan-hang': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`,
    'bang-ke': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>`,
    'quy-dinh': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    'nguong': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20v-6M6 20V10M18 20V4"/></svg>`,
    'nhom-hang': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>`,
    'ngay-nghi': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    'rui-ro': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    'lich-su': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`
  };
  const sec = (id, title, sub, inner) => `<section class="cfg" id="cfg-${id}"><h2 class="section">${SEC_ICONS[id] || ''} <span>${esc(title)}</span></h2><p class="section-desc">${esc(sub)}</p>${inner}</section>`;
  const cats = pack.ai_categories || [];
  app().innerHTML = `<span class="eyebrow">Cấu hình riêng của doanh nghiệp</span>
    <h1 class="page">${esc(pack.profile.legal_name)}</h1>
    <p class="lead">Thiết lập các tham số, quy định chi tiêu, ngưỡng kiểm soát và danh mục đặc thù khớp với doanh nghiệp của bạn. Khung kiểm tra luật thuế dùng chung luôn được bảo toàn.</p>
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
      <span><strong>${esc(p.flag)}</strong>${p.industry_fit ? '<span class="badge-fit">Gợi ý cho ngành của bạn</span>' : ''}<span class="muted small">${p.min_gross ? `từ ${money(p.min_gross)}` : ''}${p.description_contains ? ` khi tên hàng có: ${p.description_contains.map(esc).join(', ')}` : ''}</span></span></label>`).join('')}
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
  const tax = $('#f-tax_code');
  if (tax) { tax.closest('.cds--form-item').insertAdjacentHTML('beforeend', '<div id="mst-msg2"></div>'); bindTaxCheck(tax, $('#mst-msg2')); }
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
    ...presets.policies.filter((p, i) => app().querySelector(`[data-preset="${i}"]`).checked).map((p) => cleanPolicy({ ...p, ...((pack.policies || []).find((x) => x.id === p.id) || {}) })),
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
