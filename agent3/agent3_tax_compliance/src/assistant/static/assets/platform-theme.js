// Shared portal context for embedded agents and their standalone pages.
(function () {
  try {
    if (window.self !== window.top) document.documentElement.classList.add("in-platform");
  } catch (e) {
    document.documentElement.classList.add("in-platform");
  }

  function setupPortalReturn() {
    const links = document.querySelectorAll("[data-portal-return]");
    if (!links.length) return;
    let origin = new URLSearchParams(location.search).get("portal");
    if (!origin && document.documentElement.dataset.agent === "4") origin = location.origin;
    try {
      if (!origin) origin = sessionStorage.getItem("kt-portal-origin") || sessionStorage.getItem("agent1-portal-origin");
      const portal = new URL(origin);
      if (portal.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(portal.hostname) ||
          portal.username || portal.password || (portal.origin === location.origin && document.documentElement.dataset.agent !== "4")) return;
      for (const link of links) {
        link.href = portal.origin + "/#overview";
        link.hidden = false;
      }
      try { sessionStorage.setItem("kt-portal-origin", portal.origin); } catch (e) { /* private mode */ }
    } catch (e) { /* Independently opened agents may have no portal context. */ }
  }

  // The browser's own file control is written in the browser's language. Swap it for a Vietnamese button and file name.
  function enhanceFiles() {
    document.querySelectorAll('input[type=file]:not([data-son-file])').forEach((input) => {
      input.dataset.sonFile = '1';
      const cs = getComputedStyle(input);
      const box = input.getBoundingClientRect();
      if (input.hidden || cs.display === 'none' || /visually-hidden|sr-only|hidden/.test(input.className) || (box.width < 4 && box.height < 4)) return;
      const wrap = document.createElement('span');
      const btn = document.createElement('button');
      const name = document.createElement('span');
      wrap.className = 'son-file';
      btn.type = 'button'; btn.className = 'son-file-btn secondary'; btn.textContent = 'Chọn tệp';
      name.className = 'son-file-name'; name.textContent = 'Chưa chọn tệp';
      input.classList.add('son-file-input');
      input.before(wrap);
      wrap.append(btn, name);
      btn.addEventListener('click', () => input.click());
      input.addEventListener('change', () => {
        const f = input.files;
        name.textContent = !f || !f.length ? 'Chưa chọn tệp' : f.length === 1 ? f[0].name : f.length + ' tệp đã chọn';
      });
    });
  }

  // Agent 2 tool pages have no shell of their own: give them the same tab strip as the review page.
  function toolTabs() {
    if (document.documentElement.dataset.agent !== '2' || !document.body.classList.contains('tool-page') || document.querySelector('.son-tabs')) return;
    const here = location.pathname.replace(/\/+$/, '') || '/';
    const tabs = [['/', 'Hồ sơ rà soát'], ['/data-import', 'Nhập CSV / Excel'], ['/company-ml', 'Dữ liệu và ML'], ['/ml-reviews', 'Phiếu rà ML']];
    if (here === '/p2-controls') tabs.push(['/p2-controls', 'Đối chứng P2']);
    const nav = document.createElement('nav');
    nav.className = 'son-tabs'; nav.setAttribute('aria-label', 'Nghiệp vụ soát giao dịch');
    for (const [href, label] of tabs) {
      const a = document.createElement('a');
      a.href = href + location.search; a.textContent = label;
      if (href === here) a.setAttribute('aria-current', 'page');
      nav.append(a);
    }
    document.body.prepend(nav);
  }

  function decorate() {
    enhanceFiles();
    toolTabs();
    const root = document.documentElement;
    const agent = root.dataset.agent;
    const headings = agent ? document.querySelectorAll('main h1, #main h1, .intro h1, #app h1') : document.querySelectorAll('#view-config .profile-heading, #intake .page-head');
    for (const heading of headings) {
      if (heading.id === 'h-data' || heading.closest('[role="dialog"], dialog')) continue;
      const banner = heading.closest('.page-heading') || heading;
      if (banner !== heading) heading.classList.remove('son-illustrated');
      banner.classList.add('son-illustrated');
    }
    if (root.classList.contains('in-platform')) {
      const navigation = document.querySelector('[data-agent="1"] .nav-more');
      if (navigation) {
        for (const button of navigation.querySelectorAll('button[data-view]')) {
          navigation.parentElement.insertBefore(button, navigation);
        }
      }
    }
    const routes = ['#/', '#/viec', '#/hoa-don', '#/ngan-hang', '#/so-lieu', '#/giai-trinh', '#/hoi', '#/lich', '#/luat', '#/quan-tri', '#/quan-tri/doanh-nghiep', '#/quan-tri/danh-muc', '#/quan-tri/lich-su'];
    const a1 = document.querySelector('.rail [data-view].active');
    let scene = location.hash === '#data' ? 1 : 0;
    if (agent === '1') {
      scene = a1?.dataset.view === 'records' ? 32 : 6 + Math.max(0, ['overview', 'forecast', 'data', 'training', 'guide'].indexOf(a1?.dataset.view));
    } else if (agent === '2') {
      const paths = ['company-ml', 'ml-reviews', 'p2-controls', 'data-import'];
      const tool = paths.indexOf(location.pathname.split('/').filter(Boolean).pop());
      scene = tool >= 0 ? 15 + tool : 11;
      const modalTitle = document.querySelector('#modal-title');
      if (modalTitle) {
        const modal = ['Phạm vi các quy tắc', 'Thông báo Zalo / Email', 'Cách rà soát một hồ sơ'].indexOf(modalTitle.textContent);
        if (modal >= 0) {
          const art = modal + 12;
          modalTitle.dataset.sonSheet = String(art % 6);
          modalTitle.dataset.sonRow = String(Math.floor(art / 6));
        } else {
          delete modalTitle.dataset.sonSheet;
          delete modalTitle.dataset.sonRow;
        }
      }
    } else if (agent === '3') {
      scene = 19 + Math.max(0, routes.indexOf(location.hash.split('?')[0] || '#/'));
    } else if (agent === '4') {
      scene = 35;
    }
    root.dataset.sonSheet = String(scene % 6);
    // Attribute selectors keep this compatible with the agents' strict style CSP.
    root.dataset.sonRow = String(Math.floor(scene / 6));
  }
  // Approval seal. Built from classes only, so it works under the agents' strict style CSP.
  window.sonStamp = function (by, caption) {
    try {
      document.querySelectorAll('.son-stamp').forEach((n) => n.remove());
      const wrap = document.createElement('div');
      const box = document.createElement('div');
      const title = document.createElement('b');
      const who = document.createElement('span');
      const when = document.createElement('small');
      title.textContent = 'ĐÃ DUYỆT';
      who.textContent = by ? String(by).slice(0, 40) : (caption || '');
      const d = new Date();
      when.textContent = [d.getDate(), d.getMonth() + 1, d.getFullYear()].map((x, i) => (i < 2 ? String(x).padStart(2, '0') : x)).join('/');
      box.append(title, who, when);
      wrap.className = 'son-stamp';
      wrap.setAttribute('aria-hidden', 'true');
      wrap.append(box);
      document.body.append(wrap);
      setTimeout(() => wrap.remove(), 2400);
    } catch (e) { /* decoration only */ }
  };

  function start() {
    setupPortalReturn();
    decorate();
    let pending = false;
    const observer = new MutationObserver(() => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; decorate(); });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('click', () => requestAnimationFrame(decorate));
    window.addEventListener('hashchange', decorate);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
