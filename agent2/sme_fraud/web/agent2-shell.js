'use strict';
/* Khung chung của Agent 2: thanh tab và banner theo mẫu Agent Thuế. Mỗi trang chỉ khai báo <div id="a2-shell" data-page data-title data-desc>. */
(() => {
  const host = document.getElementById('a2-shell');
  if (!host) return;
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  const page = host.dataset.page;
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  const tabs = [
    ['nav-queue', 'pipeline-workspace', 'Tổng quan', 'overview'],
    ['nav-models', 'model-management', 'Huấn luyện & mô hình', 'models'],
    ['nav-fed', 'federated-training', 'Đóng góp huấn luyện', 'contribute'],
  ];
  const bar = el('header', 'a2-tabbar');
  const nav = el('nav', 'a2-tabs');
  nav.setAttribute('aria-label', 'Chức năng Agent 2');
  for (const [id, href, label, key] of tabs) {
    const a = el('a', 'a2-tab', label);
    a.id = id; a.href = href;
    if (key !== 'overview' && page === 'overview') a.hidden = true;
    if (key === page) a.setAttribute('aria-current', 'page');
    nav.append(a);
  }
  bar.append(nav, el('span', 'a2-env', 'DỮ LIỆU MÔ PHỎNG'));
  bar.lastChild.id = host.dataset.envId || 'env-badge';
  bar.lastChild.hidden = true;

  const banner = el('div', 'page-heading a3-compact-header son-illustrated a2-banner');
  banner.dataset.sonSheet = '0';
  banner.dataset.sonRow = { overview: '0', models: '1', contribute: '2' }[page] || '0';
  const main = el('div', 'a3-header-main');
  const eyebrow = el('div', 'eyebrow');
  eyebrow.append(el('span', 'a3-eyebrow-pill', 'KHÔNG GIAN DOANH NGHIỆP'), el('span', 'a3-eyebrow-dot', '·'), el('span', null, host.dataset.crumb || host.dataset.title));
  const h1 = el('h1', 'page'); h1.append(el('span', 'a3-h1-main', host.dataset.title));
  const company = el('p', 'a3-company-line');
  const sub = el('p', 'a3-header-sub');
  sub.append(el('span', 'a3-sub-desc', host.dataset.desc || ''), el('span', 'a3-sub-meta'));
  main.append(eyebrow, h1, company, sub);
  banner.append(main);
  host.replaceWith(bar, banner);

  // Tên công ty và MST lấy từ Portal (cùng nguồn với các agent khác); một lần đăng nhập chỉ có một doanh nghiệp.
  const token = sessionStorage.getItem('kt-session') || '';
  if (mount && token) {
    fetch('/api/state', { headers: { 'X-Platform': '1', 'X-Session': token }, cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(s => {
        const c = (s && s.company) || {};
        const name = String(c.name || c.legal_name || '').replace(/^["'“”‘’\s]+|["'“”‘’\s]+$/g, '');
        if (name) company.textContent = name;
        const mst = c.tax_code || (s && s.profile && s.profile.tax_code);
        if (mst) sub.lastChild.textContent = ' · MST ' + mst;
      })
      .catch(() => {});
  }
})();
