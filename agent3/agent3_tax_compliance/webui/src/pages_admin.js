// Protected settings ("Quản trị"): not on the menu, opened at #/quan-tri. Needs the administrator password for every
// change: enterprise profile and policies, new enterprises, shared catalogs, legal corpus, risk lists.
import { $, api, app, button, esc, notice, post, put, state, store } from './core.js';
import { toast } from './ux.js';

export const ADMIN_TABS = [
  ['#/quan-tri', 'Tổng quan quản trị'], ['#/quan-tri/doanh-nghiep', 'Cấu hình doanh nghiệp'],
  ['#/quan-tri/danh-muc?ten=policy_presets', 'Quy định chi tiêu gợi ý'], ['#/quan-tri/danh-muc?ten=ai_categories', 'Nhóm hàng cho AI'],
  ['#/quan-tri/danh-muc?ten=holidays', 'Lịch nghỉ lễ'], ['#/quan-tri/danh-muc?ten=law_topics', 'Chủ đề tin luật'],
  ['#/quan-tri/danh-muc?ten=chat_domains', 'Câu hỏi của trợ lý'], ['#/quan-tri/kho-luat', 'Kho luật'], ['#/quan-tri/lich-su', 'Lịch sử thay đổi'],
];
const NAMES = Object.fromEntries(ADMIN_TABS.filter(([h]) => h.includes('ten=')).map(([h, l]) => [h.split('ten=')[1], l]));

async function status() { return api('/api/admin/status'); }

function subnav() {
  const cur = location.hash;
  const isMatch = (h) => cur === h || (h === '#/quan-tri/doanh-nghiep' && cur.startsWith('#/thiet-lap')) || (h !== '#/quan-tri' && cur.startsWith(h));
  return `<nav class="admin-nav" aria-label="Quản trị">${ADMIN_TABS.map(([h, l]) => `<a href="${h}" class="${isMatch(h) ? 'on' : ''}">${esc(l)}</a>`).join('')}
    <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="admin-logout">Đăng xuất quản trị</button></nav>`;
}

function bindLogout() {
  const b = $('#admin-logout');
  if (b) b.onclick = async () => { await post('/api/admin/logout'); toast('Đã đăng xuất quản trị'); location.hash = '#/'; };
}

function loginForm(st) {
  const setup = !st.configured;
  app().innerHTML = `<span class="eyebrow">Hệ thống bảo vệ</span>
    <h1 class="page">Quản trị hệ thống</h1>
    <p class="lead">${setup
    ? 'Lần đầu sử dụng: đặt mật khẩu quản trị. Mật khẩu này dùng để thay đổi cấu hình doanh nghiệp, danh mục dùng chung và kho luật; công việc hằng ngày (nạp dữ liệu, xử lý việc, hỏi đáp) không cần mật khẩu.'
    : 'Khu vực quản trị cấu hình và danh mục hệ thống. Vui lòng nhập mật khẩu quản trị để tiếp tục.'}</p>
    <div style="display:flex;justify-content:center;margin:32px 0">
      <form id="admin-form" class="panel narrow" style="width:100%;max-width:440px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--cds-border-subtle)">
          <div style="background:var(--a3-primary-soft);color:var(--a3-primary);width:40px;height:40px;border-radius:10px;display:grid;place-items:center;flex:none">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <div>
            <h3 style="margin:0;font-size:16px;font-weight:600">${setup ? 'Thiết lập mật khẩu quản trị' : 'Xác thực quản trị viên'}</h3>
            <span class="muted small">${st.ttl_minutes} phút không thao tác sẽ tự khóa</span>
          </div>
        </div>
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw">Mật khẩu${setup ? ' mới (ít nhất 8 ký tự)' : ''}</label>
        <input class="cds--text-input son-box" id="pw" type="password" autocomplete="${setup ? 'new-password' : 'current-password'}" required></div>
        ${setup ? '<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw2">Nhập lại mật khẩu</label><input class="cds--text-input son-box" id="pw2" type="password" autocomplete="new-password" required></div>' : ''}
        <div class="bar" style="margin-top:20px">${button(setup ? 'Đặt mật khẩu' : 'Đăng nhập', 'primary', 'type="submit"')}</div><div id="admin-msg"></div>
        <p class="muted small" style="margin-top:14px">Mật khẩu được mã hóa băm an toàn trên máy cục bộ.</p>
      </form>
    </div>`;
  $('#admin-form').onsubmit = async (e) => {
    e.preventDefault();
    const pw = $('#pw').value;
    if (setup && pw !== $('#pw2').value) { $('#admin-msg').innerHTML = notice('error', 'Hai lần nhập không khớp'); return; }
    try {
      await post(setup ? '/api/admin/setup' : '/api/admin/login', { password: pw });
      toast(setup ? 'Đã đặt mật khẩu quản trị' : 'Đã đăng nhập quản trị');
      window.dispatchEvent(new Event('hashchange'));
    } catch (err) { $('#admin-msg').innerHTML = notice('error', setup ? 'Không đặt được mật khẩu' : 'Không đăng nhập được', err.message); }
  };
}

// Wraps a page so it opens only for a logged-in administrator and carries the admin sub-menu.
export function adminOnly(page) {
  return async () => {
    const st = await status();
    if (!st.logged_in) { loginForm(st); return; }
    await page();
    app().insertAdjacentHTML('afterbegin', subnav());
    bindLogout();
  };
}

export async function pageAdminHome() {
  const cats = await api('/api/admin/catalog');
  app().innerHTML = `<span class="eyebrow">Bảng điều khiển quản trị</span>
    <h1 class="page">Quản trị và Danh mục dùng chung</h1>
    <p class="lead">Mọi thay đổi ở đây được kiểm tra hợp lệ, ghi phiên bản và lưu vào nhật ký lịch sử. Danh mục dùng chung áp dụng cho mọi doanh nghiệp; cấu hình doanh nghiệp áp dụng riêng cho từng không gian.</p>
    <div class="grid2">
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>🏢</span> Doanh nghiệp từ portal
        </h3>
        <p class="muted" style="font-size:13.5px;line-height:1.65">Doanh nghiệp từ hồ sơ chung tại portal: <strong>${esc(state.workspaces.find((w) => w.id === state.ws)?.name || 'chưa chọn')}</strong>.</p>
        <div class="bar" style="margin-top:20px">
          ${button('Cấu hình doanh nghiệp này', 'primary', 'data-go="#/quan-tri/doanh-nghiep"')}
          ${button('Chạy wizard thiết lập (5 bước)', 'ghost', 'data-go="#/thiet-lap"')}
        </div>
      </div>
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>📚</span> Danh mục dùng chung toàn hệ thống
        </h3>
        <ul class="list-plain" style="margin-top:14px">
          ${cats.map((c) => `<li style="padding:10px 0;border-bottom:1px solid var(--cds-border-subtle);display:flex;justify-content:space-between;align-items:center">
            <a href="#/quan-tri/danh-muc?ten=${c.name}" style="font-weight:500;text-decoration:none">${esc(NAMES[c.name] || c.name)}</a>
            <span class="cds--tag cds--tag--teal" style="font-size:11.5px">v${esc(c.version)}</span>
          </li>`).join('')}
        </ul>
      </div>
    </div>
    <div class="panel narrow" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-top:24px;max-width:560px">
      <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
        <span>🔑</span> Đổi mật khẩu quản trị
      </h3>
      <form id="pwchg" style="margin-top:16px">
        <div class="form-grid">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="old">Mật khẩu hiện tại</label><input class="cds--text-input" id="old" type="password" autocomplete="current-password"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="new">Mật khẩu mới</label><input class="cds--text-input" id="new" type="password" autocomplete="new-password"></div>
        </div>
        <div class="bar" style="margin-top:18px">${button('Đổi mật khẩu', 'secondary', 'type="submit"')}</div>
      </form>
    </div>`;
  $('#pwchg').onsubmit = async (e) => {
    e.preventDefault();
    try { const r = await post('/api/admin/password', { old: $('#old').value, new: $('#new').value }); toast('Đã đổi mật khẩu', r.note); window.dispatchEvent(new Event('hashchange')); }
    catch (err) { toast('Không đổi được mật khẩu', err.message, 'error'); }
  };
}

// ---------------------------------------------------------------- catalog editors
const lines = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean);
const csv = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
const inp = (cls, v, attrs = '') => `<input class="cds--text-input ${cls}" value="${esc(v ?? '')}" ${attrs}>`;

const EDITORS = {
  policy_presets: {
    help: 'Mỗi dòng là một quy định gợi ý khi thiết lập doanh nghiệp. "Ngành" là hai chữ số đầu mã VSIC (cách nhau dấu phẩy) để gợi ý theo ngành; để trống là gợi ý cho mọi doanh nghiệp. Quy định chỉ thêm nhắc nhở, không đổi kết quả theo luật.',
    render: (d) => `<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã</th><th>Nội dung nhắc</th><th>Nhóm</th><th>Ngành</th><th>Từ số tiền</th><th>Khi tên hàng có</th><th>Đánh dấu sẵn</th><th></th></tr></thead>
      <tbody id="rows">${d.presets.map((p) => EDITORS.policy_presets.row(p)).join('')}</tbody></table></div>${button('Thêm quy định', 'ghost', 'id="add-row"')}`,
    row: (p = {}) => `<tr><td>${inp('f-id', p.id, 'placeholder="VD: VAN_PHONG_PHAM"')}</td><td>${inp('f-flag', p.flag)}</td><td>${inp('f-group', p.group || 'Chung')}</td>
      <td>${inp('f-for', (p.for || []).join(', '), 'placeholder="62, 63"')}</td><td>${inp('f-min', p.min_gross ?? '', 'inputmode="numeric"')}</td>
      <td>${inp('f-words', (p.description_contains || []).join(', '))}</td><td><input type="checkbox" class="f-rec" ${p.recommended ? 'checked' : ''}></td>
      <td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,
    read: (d) => ({ ...d, presets: [...app().querySelectorAll('#rows tr')].map((tr) => {
      const g = (c) => tr.querySelector(c).value.trim();
      const p = { id: g('.f-id').toUpperCase(), flag: g('.f-flag'), group: g('.f-group'), for: csv(g('.f-for')), recommended: tr.querySelector('.f-rec').checked };
      if (g('.f-min')) p.min_gross = Number(g('.f-min').replace(/\D/g, ''));
      if (g('.f-words')) p.description_contains = csv(g('.f-words'));
      return p;
    }).filter((p) => p.id || p.flag) }),
  },
  ai_categories: {
    help: 'Nhóm hàng mà AI chọn khi phân loại từng dòng hàng trên hóa đơn mua vào. Mô tả càng cụ thể AI càng chọn đúng. Nhóm CA_NHAN (đồ cá nhân) và KHONG_RO (không rõ) là nhóm hệ thống, không xóa được. Đổi danh mục thì nên chạy lại "Phân loại dòng hàng".',
    render: (d) => `<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã nhóm</th><th>Mô tả cho AI</th><th></th></tr></thead>
      <tbody id="rows">${d.categories.map((c) => EDITORS.ai_categories.row(c, d.system)).join('')}</tbody></table></div>${button('Thêm nhóm', 'ghost', 'id="add-row"')}`,
    row: (c = {}, system = []) => `<tr><td>${inp('f-id', c.id, system.includes(c.id) ? 'readonly' : 'placeholder="VD: THIET_BI_Y_TE"')}</td><td>${inp('f-desc', c.description)}</td>
      <td>${system.includes(c.id) ? '<span class="muted small">hệ thống</span>' : '<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button>'}</td></tr>`,
    read: (d) => ({ ...d, categories: [...app().querySelectorAll('#rows tr')].map((tr) => ({ id: tr.querySelector('.f-id').value.trim().toUpperCase(), description: tr.querySelector('.f-desc').value.trim() })).filter((c) => c.id) }),
  },
  holidays: {
    help: 'Ngày nghỉ dùng để dời hạn nộp hồ sơ thuế khi hạn trùng ngày nghỉ (thứ Bảy, Chủ nhật luôn được tính). Ngày lễ cố định lặp lại mỗi năm; nghỉ Tết, nghỉ bù thay đổi theo năm, nhập theo thông báo của Bộ Nội vụ. Bỏ đánh dấu "Đã đối chiếu" với ngày chỉ là phương án dự kiến.',
    render: (d) => {
      const years = Object.keys(d.years || {}).sort();
      return `<h3>Ngày lễ cố định hằng năm</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tháng</th><th>Tên</th><th></th></tr></thead>
        <tbody id="fixed">${d.fixed.map((f) => `<tr><td>${inp('f-day', f.day, 'inputmode="numeric"')}</td><td>${inp('f-month', f.month, 'inputmode="numeric"')}</td><td>${inp('f-name', f.name)}</td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`).join('')}</tbody></table></div>
        ${years.map((y) => `<h3>Năm ${y}</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tên</th><th>Đã đối chiếu</th><th></th></tr></thead>
          <tbody class="year" data-year="${y}">${d.years[y].map((r) => EDITORS.holidays.row(r)).join('')}</tbody></table></div>
          <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm add-day" data-year="${y}">Thêm ngày nghỉ năm ${y}</button>`).join('')}
        <div class="bar"><input class="cds--text-input filter-input" id="new-year" placeholder="Năm mới, VD 2028" inputmode="numeric">${button('Thêm năm', 'ghost', 'id="add-year"')}</div>
        ${(d.sources || []).length ? `<p class="muted small">Nguồn đã dùng: ${d.sources.map((s) => `<a href="${esc(s)}" target="_blank" rel="noopener">${esc(new URL(s).hostname)}</a>`).join(', ')}</p>` : ''}`;
    },
    row: (r = {}) => `<tr><td>${inp('f-date', r.date, 'type="date"')}</td><td>${inp('f-name', r.name)}</td><td><input type="checkbox" class="f-ver" ${r.verified !== false ? 'checked' : ''}></td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,
    read: (d) => ({ ...d,
      fixed: [...app().querySelectorAll('#fixed tr')].map((tr) => ({ day: Number(tr.querySelector('.f-day').value), month: Number(tr.querySelector('.f-month').value), name: tr.querySelector('.f-name').value.trim() })),
      years: Object.fromEntries([...app().querySelectorAll('tbody.year')].map((tb) => [tb.dataset.year, [...tb.querySelectorAll('tr')]
        .map((tr) => ({ date: tr.querySelector('.f-date').value, name: tr.querySelector('.f-name').value.trim(), verified: tr.querySelector('.f-ver').checked })).filter((r) => r.date)])) }),
  },
  law_topics: {
    help: 'Tin luật mới được lọc theo độ gần nghĩa giữa trích yếu văn bản và các chủ đề dưới đây (mô hình bge-m3 chạy trên máy). Viết mỗi chủ đề một dòng, càng cụ thể càng tốt. "Chủ đề loại trừ" là từ khóa của văn bản khu vực công cần bỏ qua.',
    render: (d) => `<div class="cds--form-item"><label class="cds--label" for="topics">Chủ đề liên quan (mỗi dòng một chủ đề)</label><textarea class="cds--text-area" id="topics" rows="12">${esc(d.topics.join('\n'))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label" for="noise">Chủ đề loại trừ (mỗi dòng một cụm từ, viết không dấu)</label><textarea class="cds--text-area" id="noise" rows="6">${esc((d.noise || []).join('\n'))}</textarea></div>`,
    read: (d) => ({ ...d, topics: lines($('#topics').value), noise: lines($('#noise').value) }),
  },
  chat_domains: {
    help: 'Mỗi loại câu hỏi có mô tả (hiện ở trang Hỏi đáp), câu ví dụ để trợ lý học cách nhận ra loại câu đó, và câu gợi ý hiện cho người dùng. Thêm câu ví dụ đúng cách người dùng hay hỏi giúp trợ lý nhận dạng tốt hơn. Thêm loại câu hỏi mới cần lập trình hàm trả lời nên không làm được ở đây.',
    render: (d) => d.domains.map((x) => `<details class="guide-group domain-edit" data-id="${esc(x.id)}"><summary>${esc(x.title)} <span class="muted small">${esc(x.id)}, ${x.examples.length} câu ví dụ${x.examples_generated?.length ? `, ${x.examples_generated.length} câu do mô hình viết đã lọc` : ''}</span></summary>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Tên loại câu hỏi</label>${inp('f-title', x.title)}</div>
      <div class="cds--form-item"><label class="cds--label">Giới hạn</label>${inp('f-limits', x.limits)}</div></div>
      <div class="cds--form-item"><label class="cds--label">Trả lời được</label><textarea class="cds--text-area f-what" rows="2">${esc(x.what)}</textarea></div>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Câu ví dụ để nhận dạng (mỗi dòng một câu, ít nhất 3)</label><textarea class="cds--text-area f-ex" rows="8">${esc(x.examples.join('\n'))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label">Câu gợi ý hiện cho người dùng (dùng &lt;...&gt; cho chỗ cần điền)</label><textarea class="cds--text-area f-guide" rows="8">${esc((x.guide || []).join('\n'))}</textarea></div></div></details>`).join(''),
    read: (d) => ({ ...d, domains: d.domains.map((x) => {
      const el = app().querySelector(`.domain-edit[data-id="${x.id}"]`);
      return { ...x, title: el.querySelector('.f-title').value.trim(), limits: el.querySelector('.f-limits').value.trim(), what: el.querySelector('.f-what').value.trim(),
        examples: lines(el.querySelector('.f-ex').value), guide: lines(el.querySelector('.f-guide').value) };
    }) }),
  },
};

export async function pageCatalog() {
  const name = new URLSearchParams(location.hash.split('?')[1] || '').get('ten') || 'policy_presets';
  const ed = EDITORS[name];
  if (!ed) { app().innerHTML = notice('error', 'Không có danh mục này'); return; }
  const { data, history } = await api(`/api/admin/catalog/${name}`);
  app().innerHTML = `<span class="eyebrow">Danh mục dùng chung hệ thống</span>
    <h1 class="page">${esc(NAMES[name])}</h1>
    <p class="lead">${esc(ed.help)}</p>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
      <span class="cds--tag cds--tag--teal">Phiên bản ${esc(data.version)}</span>
      <span class="muted small">Áp dụng chung cho mọi doanh nghiệp trên máy này</span>
    </div>
    <form id="cat-form"><div id="cat-body" class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-bottom:24px">${ed.render(data)}</div>
    <div class="bar sticky-save"><input class="cds--text-input filter-input" id="by" placeholder="Người sửa" value="${esc(store.get('agent3.reviewer') || '')}" required>
    ${button('Lưu danh mục', 'primary', 'type="submit"')}<span id="cat-msg"></span></div></form>
    ${history.length ? `<h2 class="section">Nhật ký phiên bản danh mục</h2><ul class="list-plain small" style="background:var(--a3-surface);border:1px solid var(--cds-border-subtle);border-radius:10px;padding:16px 20px">${history.map((h) => `<li style="padding:6px 0;border-bottom:1px solid var(--cds-border-subtle)">${esc(h.at.replace('T', ' '))}: <strong>${esc(h.by)}</strong> ${esc(JSON.stringify(h.summary))}</li>`).join('')}</ul>` : ''}`;
  const body = $('#cat-body');
  body.addEventListener('click', (e) => {
    if (e.target.closest('.del-row')) e.target.closest('tr').remove();
    const addDay = e.target.closest('.add-day');
    if (addDay) app().querySelector(`tbody.year[data-year="${addDay.dataset.year}"]`).insertAdjacentHTML('beforeend', EDITORS.holidays.row({ date: `${addDay.dataset.year}-01-01`, name: '' }));
  });
  if ($('#add-row')) $('#add-row').onclick = () => $('#rows').insertAdjacentHTML('beforeend', ed.row({}, data.system || []));
  if ($('#add-year')) $('#add-year').onclick = () => {
    const y = $('#new-year').value.trim();
    if (!/^20\d{2}$/.test(y)) { toast('Năm không hợp lệ', '', 'error'); return; }
    data.years = { ...ed.read(data).years, [y]: [] };
    body.innerHTML = ed.render({ ...ed.read(data), years: data.years });
  };
  $('#cat-form').onsubmit = async (e) => {
    e.preventDefault();
    const by = $('#by').value.trim();
    if (!by) { toast('Cần ghi tên người sửa', '', 'error'); return; }
    store.set('agent3.reviewer', by);
    try {
      const saved = await put(`/api/admin/catalog/${name}?by=${encodeURIComponent(by)}`, ed.read(data));
      toast('Đã lưu danh mục', `phiên bản ${saved.version}`);
      window.dispatchEvent(new Event('hashchange'));
    } catch (err) { $('#cat-msg').innerHTML = notice('error', 'Chưa lưu được', err.message); }
  };
}

export async function pageAdminHistory() {
  const lists = await Promise.all(Object.keys(NAMES).map((n) => api(`/api/admin/catalog/${n}`).then((r) => r.history.map((h) => ({ ...h, label: NAMES[n] })))));
  const all = lists.flat().sort((a, b) => (a.at < b.at ? 1 : -1));
  let packHist = [];
  if (state.ws) { try { packHist = await api(`/api/workspaces/${state.ws}/pack/history`); } catch { packHist = []; } }
  app().innerHTML = `<h1 class="page">Lịch sử thay đổi</h1><h2 class="section">Danh mục dùng chung</h2>
    ${all.length ? `<ul class="list-plain small">${all.map((h) => `<li>${esc(h.at.replace('T', ' '))}: <strong>${esc(h.label)}</strong>, ${esc(h.by)}, ${esc(JSON.stringify(h.summary))}</li>`).join('')}</ul>` : '<p class="muted">Chưa có thay đổi.</p>'}
    <h2 class="section">Cấu hình doanh nghiệp đang chọn</h2>
    ${packHist.length ? `<ul class="list-plain small">${packHist.slice().reverse().map((h) => `<li>${esc((h.at || '').replace('T', ' '))}: ${esc(h.by || '')} ${esc(JSON.stringify(h.changes || h.diff || h))}</li>`).join('')}</ul>` : '<p class="muted">Chưa có thay đổi.</p>'}`;
}
