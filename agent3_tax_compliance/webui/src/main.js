import '@carbon/styles/css/styles.min.css';
import '@fontsource/be-vietnam-pro/400.css';
import '@fontsource/be-vietnam-pro/500.css';
import '@fontsource/be-vietnam-pro/600.css';
import './app.css';
import { $, app, esc, loadWorkspaces, notice, state, store } from './core.js';
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
  ['#/quan-tri/lich-su', 'Lịch sử thay đổi', adminOnly(pageAdminHistory)], ['#/thiet-lap', 'Thiết lập doanh nghiệp', adminOnly(pageSetup)],
  ['#/cai-dat', 'Cấu hình doanh nghiệp', adminOnly(pageConfig)],
];

function renderNav(cur) {
  $('#nav').innerHTML = NAV.map(([href, label]) => `<li class="cds--side-nav__item"><a class="cds--side-nav__link" href="${href}" ${href === cur ? 'aria-current="page"' : ''}>
    <span class="cds--side-nav__link-text">${esc(label)}</span></a></li>`).join('');
}

async function route() {
  const cur = location.hash.split('?')[0] || '#/';
  const dn = new URLSearchParams(location.hash.split('?')[1] || '').get('dn');   // link that opens one enterprise
  if (dn && dn !== state.ws && state.workspaces.some((w) => w.id === dn)) { state.ws = dn; store.set('agent3.ws', dn); await loadWorkspaces(); }
  renderNav(cur);
  document.body.classList.remove('nav-open');
  $('#modal-root').innerHTML = '';
  const entry = NAV.find(([h]) => h === cur) || HIDDEN.find(([h]) => h === cur) || NAV[0];
  const page = entry[2];
  document.title = `${entry[1]} · Agent 3 Trợ lý thuế`;
  try { await page(); } catch (err) { app().innerHTML = notice('error', 'Có lỗi khi tải trang', err.message); }
  app().focus({ preventScroll: true });
}

document.addEventListener('click', (e) => {
  const go = e.target.closest('[data-go]');
  if (go) location.hash = go.dataset.go;
});
$('#ws-select').onchange = (e) => {
  if (e.target.value === '__new') { e.target.value = state.ws || ''; location.hash = '#/thiet-lap'; return; }
  state.ws = e.target.value || null; store.set('agent3.ws', state.ws || ''); location.hash = '#/'; route();
};
$('.menu-toggle').onclick = () => document.body.classList.toggle('nav-open');
const initial = store.get('agent3.theme') || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'g100' : 'g10');
document.body.className = `cds--${initial}`;
$('.theme-toggle').onclick = () => {
  const next = document.body.classList.contains('cds--g100') ? 'g10' : 'g100';
  document.body.className = `cds--${next}`;
  store.set('agent3.theme', next);
};
window.addEventListener('hashchange', route);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('#modal-root').innerHTML) $('#modal-root').innerHTML = ''; });
loadWorkspaces().then(route).catch((err) => { app().innerHTML = notice('error', 'Không kết nối được máy chủ Agent 3', err.message); });
