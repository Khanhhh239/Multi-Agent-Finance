import '@carbon/styles/css/styles.min.css';
import '@fontsource/be-vietnam-pro/400.css';
import '@fontsource/be-vietnam-pro/500.css';
import '@fontsource/be-vietnam-pro/600.css';
import './app.css';
import { $, app, beginPage, esc, loadWorkspaces, notice, needWorkspace, state, store } from './core.js';
import { decoratePage, installValidation, portalOrigin } from './interactions.js';
import { pageIntake } from './pages_intake.js';
import { pageOverview, pageReview } from './pages_work.js';
import { pageBank, pageCalendar, pageInvoices, pageLaw } from './pages_more.js';
import { pageAsk } from './pages_ask.js';
import { adminOnly, pageAdminHistory, pageAdminHome, pageCatalog } from './pages_admin.js';
import { pageDossier, pageVat } from './pages_ai.js';
import { pageConfig, pageSetup } from './pages_config.js';

// Five places for daily work. Everything that changes configuration lives under #/quan-tri behind the administrator
// password (gear icon in the header); detail pages open from links inside these five.
const NAV = [
  ['#/', 'Tổng quan', pageOverview], ['#/nap', 'Nạp dữ liệu', pageIntake], ['#/viec', 'Việc cần xử lý', pageReview], ['#/hoa-don', 'Hóa đơn', pageInvoices],
  ['#/hoi', 'Hỏi đáp', pageAsk],
];
const HIDDEN = [
  ['#/ngan-hang', 'Ngân hàng', pageBank], ['#/so-lieu', 'Số liệu thuế GTGT', pageVat], ['#/giai-trinh', 'Giải trình', pageDossier],
  ['#/lich', 'Lịch thuế', pageCalendar], ['#/luat', 'Kho luật', pageLaw], ['#/tin-luat', 'Kho luật', pageLaw],
  ['#/quan-tri', 'Quản trị', adminOnly(pageAdminHome)], ['#/quan-tri/doanh-nghiep', 'Cấu hình doanh nghiệp', adminOnly(pageConfig)],
  ['#/quan-tri/danh-muc', 'Danh mục dùng chung', adminOnly(pageCatalog)], ['#/quan-tri/kho-luat', 'Kho luật', adminOnly(pageLaw)],
  ['#/quan-tri/lich-su', 'Lịch sử thay đổi', adminOnly(pageAdminHistory)], ['#/thiet-lap', 'Thiết lập nghiệp vụ thuế', adminOnly(pageSetup)],
  ['#/cai-dat', 'Cấu hình doanh nghiệp', adminOnly(pageConfig)],
];

const DETAIL = ['#/ngan-hang', '#/so-lieu', '#/giai-trinh', '#/lich', '#/luat', '#/tin-luat'];

function renderNav(cur) {
  const active = cur.startsWith('#/quan-tri') || ['#/thiet-lap', '#/cai-dat'].includes(cur) ? '#/quan-tri'
    : cur;
  $('#nav').innerHTML = NAV.map(([href, label]) => `<li class="cds--side-nav__item"><a class="cds--side-nav__link" href="${href}" ${href === active ? 'aria-current="page"' : ''}>
    <span class="cds--side-nav__link-text">${esc(label)}</span></a></li>`).join('');
  $('.admin-link').setAttribute('aria-current', active === '#/quan-tri' ? 'page' : 'false');
  decoratePage($('#nav'));
}

async function route() {
  const signal = beginPage();
  const cur = location.hash.split('?')[0] || '#/';
  if (signal.aborted) return;
  if (cur === '#/nap' && state.ws && portalOrigin()) { window.top.location.href = portalOrigin() + '/#data'; return; }
  renderNav(cur);
  const company = $('#active-company'); if (company) company.title = company.textContent;
  document.body.classList.remove('nav-open');
  $('.menu-toggle').setAttribute('aria-expanded', 'false');
  $('#modal-root').innerHTML = '';
  const entry = NAV.find(([h]) => h === cur) || HIDDEN.find(([h]) => h === cur) || NAV[0];
  const page = entry[2];
  document.title = `${entry[1]} · Agent 3 Trợ lý thuế`;
  try { if (needWorkspace()) return; await page(); } catch (err) { if (signal.aborted) return; app().innerHTML = `<h1 class="page">${esc(entry[1])}</h1>` + notice('error', 'Có lỗi khi tải trang', err.message); }
  if (!signal.aborted && DETAIL.includes(cur) && !app().querySelector('.back-crumb')) app().insertAdjacentHTML('afterbegin', '<a class="back-crumb" href="#/">← Quay về Tổng quan</a>');
  if (!signal.aborted) { decoratePage(app()); if (!document.querySelector('.drawer')) app().focus({ preventScroll: true }); }
}

document.addEventListener('click', (e) => {
  const go = e.target.closest('[data-go]');
  if (go) location.hash = go.dataset.go;
});
$('.menu-toggle').setAttribute('aria-expanded', 'false');
$('.menu-toggle').onclick = () => { const open = document.body.classList.toggle('nav-open'); $('.menu-toggle').setAttribute('aria-expanded', String(open)); };
const initial = store.get('agent3.theme') || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'g100' : 'g10');
document.body.className = `cds--${initial}`;
$('.theme-toggle').onclick = () => {
  const next = document.body.classList.contains('cds--g100') ? 'g10' : 'g100';
  document.body.className = `cds--${next}`;
  store.set('agent3.theme', next);
};
window.addEventListener('hashchange', route);
installValidation();
$('.skip-link').onclick = (e) => { e.preventDefault(); app().focus(); };
const observer = new MutationObserver(() => decoratePage(app()));
observer.observe(app(), { childList: true, subtree: true });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if ($('#modal-root').innerHTML) $('#modal-root').innerHTML = '';
  else if (document.body.classList.contains('nav-open')) { document.body.classList.remove('nav-open'); $('.menu-toggle').setAttribute('aria-expanded', 'false'); $('.menu-toggle').focus(); }
});
loadWorkspaces().then(route).catch((err) => { app().innerHTML = notice('error', 'Không kết nối được máy chủ Agent 3', err.message); });

let checkingContext = false;
async function refreshContext() {
  if (checkingContext || document.hidden) return;
  checkingContext = true;
  try {
    const res = await fetch('/api/platform/context', { cache: 'no-store' });
    if (!res.ok) return;
    const next = await res.json();
    if (JSON.stringify(next) !== JSON.stringify(state.platform)) {
      const draft = [...app().querySelectorAll('input,select,textarea')].filter(e => !['password', 'file', 'hidden'].includes(e.type)).map(e => ({ name: e.name || e.id || e.dataset.f, value: e.value, checked: e.checked }));
      if (draft.length) try { sessionStorage.setItem('agent3.previous-context-draft', JSON.stringify({ revision: state.platform?.profile_revision, path: location.hash, fields: draft })); } catch { /* storage unavailable */ }
      beginPage();
      state.report = null;
      $('#modal-root').replaceChildren();
      await loadWorkspaces();
      await route();
      if (draft.length) app().insertAdjacentHTML('afterbegin', notice('warning', 'Hồ sơ portal đã thay đổi', 'Bản nháp cũ được giữ riêng trong phiên trình duyệt; không áp dụng sang doanh nghiệp mới.'));
    }
  } catch { /* Preserve the current page during a temporary disconnect. */ }
  finally { checkingContext = false; }
}
setInterval(refreshContext, 4000);
document.addEventListener('visibilitychange', refreshContext);
window.addEventListener('agent3-context-stale', refreshContext);
