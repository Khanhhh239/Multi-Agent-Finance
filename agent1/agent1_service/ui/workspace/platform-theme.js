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
      if (input.hidden || cs.display === 'none' || /visually-hidden|sr-only|hidden/.test(input.className) || (box.width < 4 && box.height < 4)) { if (document.documentElement.dataset.agent === '2') delete input.dataset.sonFile; return; }
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
    if (document.documentElement.dataset.agent === '2') {
      document.querySelectorAll('input[type=file][data-son-file]').forEach(input => {
        const button = input.previousElementSibling?.querySelector('.son-file-btn');
        if (button && button.disabled !== input.disabled) button.disabled = input.disabled;
      });
      const messages = [
        ['Chưa cấu hình luồng bundle.', 'Doanh nghiệp chưa có bộ thiết lập phân tích.'],
        ['Liên hệ người vận hành.', 'Nhờ người quản lý thiết lập trước khi chạy.'],
        ['Chưa có bundle', 'Chưa có bộ thiết lập phân tích'],
        ['Snapshot không', 'Bản dữ liệu không'],
      ];
      document.querySelectorAll('#notice, #bw-notice, #ws-notice, #bt-notice').forEach(box => {
        if (box.children.length) return;
        const old = box.textContent;
        const next = messages.reduce((v, [a,b]) => v.split(a).join(b), old);
        if (next !== old) box.textContent = next;
      });
    }
    toolTabs();
    const root = document.documentElement;
    const agent = root.dataset.agent;
    const headings = agent ? document.querySelectorAll('main h1, #main h1, .intro h1, #app h1, .a2-hero h1') : document.querySelectorAll('#view-config .profile-heading, #intake .page-head');
    for (const heading of headings) {
      if (heading.id === 'h-data' || heading.closest('[role="dialog"], dialog, .drawer, .empty')) continue;
      let banner = heading.closest('.page-heading, .intro, .a2-hero, .son-page-header');
      if (!banner && ['1', '2', '3'].includes(agent)) {
        banner = document.createElement('div');
        banner.className = 'son-page-header';
        const description = heading.nextElementSibling;
        heading.before(banner);
        banner.append(heading);
        if (description?.matches('p:not(.notice):not([role])')) banner.append(description);
      }
      banner ||= heading;
      if (banner !== heading) heading.classList.remove('son-illustrated');
      banner.classList.add('son-illustrated');
      if (!['1', '2', '3'].includes(agent)) continue;
      banner.classList.add('son-page-header');
      let copy = banner.querySelector(':scope > .son-heading-copy, :scope > .a3-header-main');
      if (!copy) {
        const parent = heading.parentElement;
        if (parent !== banner && parent.parentElement === banner) {
          copy = parent;
          copy.classList.add('son-heading-copy');
        } else {
          copy = document.createElement('div');
          copy.className = 'son-heading-copy';
          const content = [...banner.children].filter(el => el === heading || el.matches('.eyebrow, p, .lead'));
          banner.prepend(copy);
          for (const el of content) copy.append(el);
        }
      }
      if (!copy.querySelector('.eyebrow')) {
        const eyebrow = document.createElement('div');
        eyebrow.className = 'eyebrow son-heading-eyebrow';
        eyebrow.textContent = agent === '1' ? 'TRỢ LÝ DÒNG TIỀN' : agent === '2' ? 'TRỢ LÝ GIÁM SÁT' : 'TRỢ LÝ THUẾ';
        copy.prepend(eyebrow);
      }
      if (agent !== '3') {
        const selected = document.querySelector('#ws-company, #company, #bw-company');
        const company = agent === '1' ? document.getElementById('company-name')?.textContent?.trim()
          : selected?.selectedOptions?.[0]?.value ? selected.selectedOptions[0].textContent.trim() : '';
        let line = copy.querySelector('.son-heading-company');
        if (company && !/^(Doanh nghiệp của bạn|Chọn doanh nghiệp)/i.test(company)) {
          if (!line) { line = document.createElement('p'); line.className = 'son-heading-company'; heading.after(line); }
          if (line.textContent !== company) line.textContent = company;
        } else if (line) line.remove();
      }
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

  // Agent 2 presentation shell. Existing controls, IDs, permissions and routes stay intact.
  function setupAgent2Shell() {
    if (document.documentElement.dataset.agent !== '2' || document.body.classList.contains('a2-product')) return;
    const header = document.querySelector('body > header');
    const main = document.querySelector('body > main');
    if (!header || !main) return;
    document.body.classList.add('a2-product');
    header.classList.add('a2-header');
    main.classList.add('a2-main');
    if (!main.id) main.id = 'a2-main';
    const skip = document.createElement('a');
    skip.className = 'a2-skip'; skip.href = '#' + main.id; skip.textContent = 'Đến nội dung chính';
    document.body.prepend(skip);
    const brand = header.querySelector('.brand');
    if (brand) { brand.textContent = 'Trợ lý Giám sát'; brand.classList.add('a2-brand'); }
    let nav = header.querySelector('nav');
    if (!nav) { nav = document.createElement('nav'); header.append(nav); }
    nav.classList.add('a2-nav'); nav.id = 'a2-navigation'; nav.setAttribute('aria-label', 'Chức năng Agent 2');
    for (const link of [...header.querySelectorAll(':scope > a:not(.brand)')]) nav.append(link);
    const page = a => new URL(a.href, location.href).pathname.replace(/\/+$/, '').split('/').pop();
    const here = location.pathname.replace(/\/+$/, '').split('/').pop() ||
      (document.getElementById('bw-company') ? 'pipeline-workspace' : 'data-import');
    const primary = [['data-import', 'Nhập dữ liệu'], ['workspace', 'Kết quả và công việc']];
    const extras = { 'status': 'T\u00ecnh tr\u1ea1ng h\u1ec7 th\u1ed1ng', 'encrypted-analysis': 'Phân tích bảo mật', 'label-verification': 'Xác nhận kết quả giao dịch',
      'batch-training': 'Hướng dẫn hệ thống học', 'pipeline-releases': 'Quản lý phiên bản phân tích', 'analysis-settings': 'Thiết lập phân tích' };
    if (extras[here] && ![...nav.querySelectorAll('a[href]')].some(a => page(a) === here)) { const self = document.createElement('a'); self.href = here + location.hash; self.textContent = extras[here]; nav.append(self); }
    for (const link of nav.querySelectorAll('a[href]')) if (page(link) === 'pipeline-workspace') link.remove();
    let previous = null;
    for (const [route, label] of primary) {
      let link = [...nav.querySelectorAll('a[href]')].find(a => page(a) === route);
      if (!link) { link = document.createElement('a'); link.href = route + location.hash; }
      link.textContent = label;
      if (previous) previous.after(link); else nav.prepend(link);
      previous = link;
    }
    for (const link of nav.querySelectorAll('a[href]')) {
      if (extras[page(link)]) link.textContent = extras[page(link)];
      if (page(link) === here) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    const menu = document.createElement('button'); menu.type = 'button'; menu.className = 'a2-menu';
    menu.textContent = '☰'; menu.setAttribute('aria-controls', nav.id); menu.setAttribute('aria-label', 'Mở danh sách chức năng');
    header.prepend(menu);
    const shade = document.createElement('button'); shade.type = 'button'; shade.className = 'a2-nav-shade';
    shade.setAttribute('aria-label', 'Đóng danh sách chức năng'); document.body.append(shade);
    function setMenu(open) {
      document.body.classList.toggle('a2-nav-open', open);
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? 'Đóng danh sách chức năng' : 'Mở danh sách chức năng');
      nav.inert = !document.documentElement.classList.contains('in-platform') && innerWidth < 900 && !open;
    }
    menu.addEventListener('click', () => setMenu(!document.body.classList.contains('a2-nav-open')));
    shade.addEventListener('click', () => { setMenu(false); menu.focus(); });
    nav.addEventListener('click', e => { if (e.target.closest('a')) setMenu(false); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.body.classList.contains('a2-nav-open')) { setMenu(false); menu.focus(); } });
    window.addEventListener('resize', () => setMenu(false)); setMenu(false);
    const theme = document.createElement('button'); theme.type = 'button'; theme.className = 'a2-theme';
    theme.setAttribute('aria-label', 'Đổi giao diện sáng hoặc tối'); theme.title = 'Đổi giao diện sáng hoặc tối';
    function appearance(dark) { document.body.classList.toggle('a2-dark', dark); theme.textContent = dark ? '☀' : '☾'; theme.setAttribute('aria-pressed', String(dark)); }
    try { appearance(localStorage.getItem('agent2.appearance') === 'dark'); } catch (_) { appearance(false); }
    theme.addEventListener('click', () => { const dark = !document.body.classList.contains('a2-dark'); appearance(dark); try { localStorage.setItem('agent2.appearance', dark ? 'dark' : 'light'); } catch (_) { /* preference only */ } });
    header.append(theme);
  }

  function start() {
    setupAgent2Shell();
    setupPortalReturn();
    decorate();
    let pending = false;
    const observer = new MutationObserver(() => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; decorate(); });
    });
    const watch = { childList: true, subtree: true };
    if (document.documentElement.dataset.agent === '2') Object.assign(watch, { attributes: true, attributeFilter: ['hidden', 'disabled'] });
    observer.observe(document.body, watch);
    document.addEventListener('click', () => requestAnimationFrame(decorate));
    window.addEventListener('hashchange', decorate);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
