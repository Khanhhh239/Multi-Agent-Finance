// Shared helpers and state for the Agent 3 interface. Markup uses Carbon Design System classes.
export const $ = (s, el = document) => el.querySelector(s);
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const money = (v) => {
  if (v === null || v === undefined || v === '') return '—';
  const raw = String(v); if (!/^-?\d+(\.\d+)?$/.test(raw)) return 'Không xác định';
  const [whole, fraction = ''] = raw.split('.');
  const tail = fraction.replace(/0+$/, '');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (tail ? ',' + tail : '') + ' đ';
};

export function formatSpecialMoney(v) {
  if (v === null || v === undefined || v === '') return '<span class="kpi-amount-empty">—</span>';
  const raw = String(v);
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return '<span class="kpi-amount-empty">Không xác định</span>';
  const [whole, fraction = ''] = raw.split('.');
  const tail = fraction.replace(/0+$/, '');
  const isNegative = whole.startsWith('-');
  const absWhole = whole.replace(/^-/, '');
  const formattedWhole = absWhole.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  return `<span class="kpi-money-wrap">
    ${isNegative ? '<span class="kpi-sign">-</span>' : ''}
    <span class="kpi-digits">${formattedWhole}</span>
    ${tail ? `<span class="kpi-tail">,${tail}</span>` : ''}
    <span class="kpi-currency-symbol">₫</span>
  </span>`;
}
export function compareDecimal(a, b) {
  const parts = value => String(value ?? '0').split('.');
  const [aw, af = ''] = parts(a), [bw, bf = ''] = parts(b);
  const scale = Math.max(af.length, bf.length);
  const integer = (whole, fraction) => BigInt((whole.startsWith('-') ? '-' : '') + whole.replace(/^-/, '') + fraction.padEnd(scale, '0'));
  const x = integer(aw, af), y = integer(bw, bf);
  return x > y ? 1 : x < y ? -1 : 0;
}
export const dmy = (s) => (s ? s.slice(0, 10).split('-').reverse().join('/') : '');
export const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const packEtags = new Map();
let pageController = new AbortController();
let cleanups = [];
export function onPageLeave(fn) { cleanups.push(fn); }
export function beginPage() {
  pageController.abort();
  cleanups.splice(0).forEach((fn) => fn());
  pageController = new AbortController();
  return pageController.signal;
}
export const pageSignal = () => pageController.signal;
export async function api(path, opts = {}) {
  const signal = opts.signal || pageController.signal;
  const headers = new Headers(opts.headers);
  const key = path.split('?')[0];
  if (path.startsWith('/api/workspaces/')) {
    headers.set('X-Agent3-Profile-Revision', state.platform?.profile_revision || '');
    if (opts.method === 'PUT' && key.endsWith('/pack') && packEtags.has(key)) headers.set('If-Match', packEtags.get(key));
  }
  const revision = state.platform?.profile_revision;
  const res = await fetch(path, { ...opts, headers, signal });
  const type = res.headers.get('content-type') || '';
  const body = type.includes('json') ? await res.json() : await res.text();
  signal.throwIfAborted();
  if (path.startsWith('/api/workspaces/') && revision !== state.platform?.profile_revision) throw new DOMException('Context changed', 'AbortError');
  if (res.headers.get('etag')) packEtags.set(key, res.headers.get('etag'));
  if (!res.ok && body?.detail?.context_stale) window.dispatchEvent(new Event('agent3-context-stale'));
  if (!res.ok) { const error = new Error(typeof body === 'object' ? body.detail?.message || body.detail || JSON.stringify(body) : body); error.status = res.status; throw error; }
  return body;
}
export const post = (path, data, opts = {}) => api(path, { ...opts, method: 'POST', headers: { 'Content-Type': 'application/json', ...opts.headers }, body: JSON.stringify(data ?? {}) });
export const put = (path, data) => api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

export async function decisionContext() {
  const path = `/api/workspaces/${state.ws}/decisions`;
  const journal = await api(path);
  return { etag: packEtags.get(path), events: journal.events || [], report_revision: state.report?.meta.report_revision, workspace: state.ws, revision: state.platform?.profile_revision };
}

export async function decide(path, body, context) {
  if (!context?.etag || !context.report_revision) throw new Error('Cần chạy phân tích và tải lại quyết định trước khi lưu.');
  if (context.workspace !== state.ws || context.revision !== state.platform?.profile_revision) throw new Error('Hồ sơ đã thay đổi; không gửi quyết định cũ.');
  const hash = JSON.stringify(body);
  if (hash !== context.body) { context.request_id = crypto.randomUUID(); context.body = hash; }
  return post(path, { ...body, request_id: context.request_id, report_revision: context.report_revision }, { headers: { 'If-Match': context.etag } });
}

export async function saveBankFormat(format) {
  const path = `/api/workspaces/${state.ws}/pack`;
  const target = `/api/workspaces/${state.ws}/bank/formats`;
  const result = await post(target, format, { headers: { 'If-Match': packEtags.get(path) || '' } });
  if (packEtags.has(target)) packEtags.set(path, packEtags.get(target));
  return result;
}

export const balance = (value) => value === null || value === undefined ? 'Chưa đủ dữ liệu / không áp dụng'
  : `${String(value).startsWith('-') ? 'Đầu vào vượt đầu ra' : 'Đầu ra vượt đầu vào'}: ${money(String(value).replace(/^-/, ''))}`;

export const moneyShort = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n) || Math.abs(n) < 1e6) return '';
  const f = (x) => x.toLocaleString('vi-VN', { maximumFractionDigits: 1 });
  return Math.abs(n) >= 1e12 ? `${f(n / 1e12)} nghìn tỷ đồng` : Math.abs(n) >= 1e9 ? `${f(n / 1e9)} tỷ đồng` : `${f(n / 1e6)} triệu đồng`;
};

const STATUS = {
  AT_RISK: ['Có nguy cơ bị loại', 'red'], REVIEW: ['Cần xem xét', 'magenta'], OPPORTUNITY: ['Có thể đang bỏ sót', 'blue'], INFO: ['Thông tin', 'gray'],
  LLM_VERIFIED: ['Đã kiểm tra căn cứ', 'green'], EXTRACTIVE: ['Trích nguyên văn', 'teal'], ABSTAIN: ['Không đủ căn cứ', 'gray'],
  DATA: ['Dữ liệu doanh nghiệp', 'cool-gray'], POLICY: ['Quy định', 'purple'], JUDGMENT: ['Cần chuyên gia', 'warm-gray'],
};
export const tag = (key, text) => {
  const [label, color] = STATUS[key] || [text || key, 'gray'];
  return `<div class="cds--tag cds--tag--${color}"><span class="cds--tag__label">${esc(text || label)}</span></div>`;
};
export const notice = (kind, title, sub = '') => `<div class="cds--inline-notification cds--inline-notification--${kind} cds--inline-notification--low-contrast notice" role="${kind === 'error' ? 'alert' : 'status'}">
  <div class="cds--inline-notification__details"><div class="cds--inline-notification__text-wrapper">
  <div class="cds--inline-notification__title">${esc(title)}</div><div class="cds--inline-notification__subtitle">${esc(sub)}</div></div></div></div>`;
export const loading = (text = 'Đang xử lý') => `<div class="bar kt-loading-wrap" style="display:inline-flex;align-items:center;gap:10px;padding:6px 0" aria-live="polite"><span class="kt-spinner teal" aria-hidden="true"></span><span class="muted" style="font-size:13px;font-weight:500">${esc(text)}...</span></div>`;
export const button = (label, cls = 'primary', attrs = '') => `<button ${/\btype=/.test(attrs) ? '' : 'type="button" '}class="cds--btn cds--btn--${cls} cds--btn--md" ${attrs}>${esc(label)}</button>`;
export const field = (f, value = '') => {
  const id = `f-${f.key}`;
  const help = f.help ? `<div class="cds--form__helper-text">${esc(f.help)}</div>` : '';
  const opt = f.required ? '' : ' (không bắt buộc)';
  if (f.type === 'choice') {
    return `<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="${id}">${esc(f.label)}${opt}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="${id}" name="${f.key}" ${f.required ? 'required' : ''}>
      ${f.choices.map(([v, l]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>${help}</div></div>`;
  }
  const v = Array.isArray(value) ? value.join('; ') : value;
  return `<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="${id}">${esc(f.label)}${opt}</label>
    <div class="cds--text-input__field-wrapper"><input class="cds--text-input" id="${id}" name="${f.key}" value="${esc(v)}" placeholder="${esc(f.example || '')}" ${f.required ? 'required' : ''}></div>${help}</div>`;
};
export const table = (head, rows, empty = 'Không có dữ liệu.') => (rows.length ? `<div class="table-wrap"><table class="cds--data-table cds--data-table--md">
  <thead><tr>${head.map((h) => `<th${h.num ? ' class="num"' : ''}><div class="cds--table-header-label">${esc(h.label || h)}</div></th>`).join('')}</tr></thead>
  <tbody>${rows.join('')}</tbody></table></div>` : `<div class="empty">${esc(empty)}</div>`);

const SUBNAV_GROUPS = {
  'chung-tu': [
    ['#/hoa-don', 'Hóa đơn GTGT'],
    ['#/ngan-hang', 'Sao kê ngân hàng'],
    ['#/du-lieu', 'Bảng kê cổng thuế'],
  ],
  'bao-cao': [
    ['#/so-lieu', 'Số liệu thuế GTGT'],
    ['#/giai-trinh', 'Hồ sơ giải trình'],
    ['#/lich', 'Lịch thuế'],
  ],
  'tu-van': [
    ['#/hoi', 'Hỏi đáp thuế & dữ liệu'],
    ['#/luat', 'Kho văn bản luật'],
  ],
};

export function subNav(group, currentHash) {
  const tabs = SUBNAV_GROUPS[group];
  if (!tabs) return '';
  const cur = (currentHash || location.hash.split('?')[0] || '#/').replace('#/tin-luat', '#/luat');
  return `<nav class="a3-subnav" aria-label="Điều hướng nhóm trang">
    ${tabs.map(([href, label]) => `<a href="${href}" class="a3-subnav-link ${cur === href ? 'active' : ''}" ${cur === href ? 'aria-current="page"' : ''}>${esc(label)}</a>`).join('')}
  </nav>`;
}

export const DEFAULT_SUBTITLES = {
  'Tổng quan': 'Tổng hợp rủi ro khấu trừ, đối chiếu số liệu tờ khai và tiến độ xử lý thuế GTGT trong kỳ.',
  'Việc cần xử lý': 'Rà soát từng cảnh báo hóa đơn, đối chiếu chứng từ thanh toán và ghi nhận quyết định phê duyệt.',
  'Hóa đơn': 'Tra cứu, kiểm tra tính toàn vẹn chữ ký số XML và trạng thái ghép sao kê của từng hóa đơn.',
  'Ngân hàng': 'Đối chiếu các khoản thu chi ngân hàng và xác nhận ghép ủy nhiệm chi với hóa đơn mua vào.',
  'Bảng kê': 'Quản lý và chọn bản bảng kê hóa đơn điện tử từ cổng thuế để đối chiếu chéo với tệp XML.',
  'Số liệu thuế GTGT': 'Tổng hợp thuế GTGT đầu ra, đầu vào theo kịch bản rà soát và đối chiếu số liệu tờ khai đã nộp.',
  'Giải trình': 'Tập hợp chứng từ, trích dẫn căn cứ pháp lý và soạn thảo công văn giải trình cơ quan thuế.',
  'Lịch thuế': 'Theo dõi thời hạn nộp hồ sơ khai thuế và quy tắc dời hạn khi trùng ngày nghỉ lễ, cuối tuần.',
  'Hỏi đáp': 'Hỏi đáp trực tiếp trên số liệu hóa đơn kỳ này hoặc tra cứu điều khoản luật thuế GTGT.',
  'Kho luật': 'Tra cứu văn bản quy phạm pháp luật thuế còn hiệu lực từ Cơ sở dữ liệu quốc gia.',
  'Nạp dữ liệu': 'Tải lên hóa đơn điện tử XML, sao kê ngân hàng và bảng kê cổng thuế để chạy phân tích.',
  'Mẫu sao kê': 'Chỉnh sửa ánh xạ cột ngày, số tiền và nội dung chuyển khoản cho từng định dạng sao kê ngân hàng.',
  'Quản trị hệ thống': 'Khu vực bảo vệ dùng để thiết lập cấu hình doanh nghiệp, danh mục dùng chung và kho văn bản luật.',
  'Tổng quan quản trị': 'Quản lý danh mục dùng chung toàn hệ thống, phiên bản quy tắc và cấu hình riêng của từng doanh nghiệp.',
  'Cấu hình doanh nghiệp': 'Thiết lập các tham số, quy định chi tiêu, ngưỡng kiểm soát và danh mục đặc thù khớp với doanh nghiệp.',
  'Thiết lập nghiệp vụ': 'Trình hướng dẫn tuần tự 5 bước giúp cá nhân hóa quy chế kiểm tra thuế cho doanh nghiệp.',
  'Danh mục dùng chung': 'Chỉnh sửa danh mục hệ thống áp dụng chung cho mọi doanh nghiệp với nhật ký phiên bản đầy đủ.',
  'Lịch sử thay đổi': 'Theo dõi toàn bộ nhật ký cập nhật danh mục hệ thống và cấu hình nghiệp vụ của doanh nghiệp.',
};

export function cleanCompanyName(raw) {
  return String(raw || '').replace(/^["'“”‘’\s]+|["'“”‘’\s]+$/g, '').trim();
}

export function sonHeader(breadcrumb, title, eyebrow = 'KHÔNG GIAN DOANH NGHIỆP', subtitle = '', navGroup = '') {
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const isOverview = breadcrumb === 'Tổng quan';
  const rawCompany = ws?.name || state.platform?.profile?.legal_name || '';
  const cleanName = cleanCompanyName(rawCompany);
  const taxCode = state.platform?.profile?.tax_code || ws?.tax_code || '';

  const stripHtml = (s) => String(s || '').replace(/<[^>]*>/g, '').trim();
  const cleanSub = stripHtml(subtitle) || DEFAULT_SUBTITLES[breadcrumb] || '';

  let metaParts = [];
  if (!isOverview && cleanName) metaParts.push(cleanName);
  if (taxCode) metaParts.push(`MST ${taxCode}`);
  if (state.report?.meta?.as_of) metaParts.push(`Kỳ phân tích: ${dmy(state.report.meta.as_of)}`);

  const h1Inner = isOverview && cleanName
    ? `<span class="a3-h1-main">${esc(title)}</span><span class="a3-h1-sep"> · </span><span class="a3-h1-company">${esc(cleanName)}</span>`
    : `<span class="a3-h1-main">${esc(title)}</span>`;

  return `
    <div class="page-heading a3-compact-header son-illustrated">
      <div class="a3-header-main">
        <div class="eyebrow"><span class="a3-eyebrow-pill">${esc(eyebrow)}</span><span class="a3-eyebrow-dot">·</span><span id="breadcrumb">${esc(breadcrumb)}</span></div>
        <h1 class="page">${h1Inner}</h1>
        ${(cleanSub || metaParts.length) ? `<p class="a3-header-sub">${cleanSub ? `<span class="a3-sub-desc">${esc(cleanSub)}</span>` : ''}${metaParts.length ? `<span class="a3-sub-meta">${cleanSub ? ' · ' : ''}${esc(metaParts.join(' · '))}</span>` : ''}</p>` : ''}
      </div>
    </div>
    ${navGroup ? subNav(navGroup) : ''}
  `;
}

// Unified mathematical & bucket calculator mirroring backend accounting.py 100%
export function computeReportStats(rep) {
  if (!rep) return null;
  const t = rep.totals || {};
  const invoices = rep.invoices || [];
  const items = rep.items || [];
  const matches = rep.matches || [];
  const notClaimedKeys = new Set(rep.decisions?.not_claimed_keys || []);

  const matchedMap = new Map(matches.flatMap((m) => (m.invoice_keys || []).map((k) => [k, m])));
  const riskByInvoice = new Map();
  items.forEach((it) => {
    (it.invoice_keys || []).forEach((k) => {
      if (!riskByInvoice.has(k)) riskByInvoice.set(k, []);
      riskByInvoice.get(k).push(it);
    });
  });

  // Exact invoice status matching accounting.py:buckets(rep)
  const invoiceBucket = (inv) => {
    if (!inv || inv.duplicate_of) return 'DUPLICATE';
    if (inv.role === 'PURCHASE' && notClaimedKeys.has(inv.key)) return 'NOT_CLAIMED';
    const its = (riskByInvoice.get(inv.key) || []).filter((x) => x.status !== 'INFO');
    if (its.some((x) => x.status === 'AT_RISK')) return 'AT_RISK';
    if (its.some((x) => x.status === 'REVIEW')) return 'REVIEW';
    if (its.length) return 'OTHER';
    return 'OK';
  };

  // Unique (non-duplicate) purchase and sales invoices
  const purchaseInvs = invoices.filter((i) => i.role === 'PURCHASE' && !i.duplicate_of);
  const saleInvs = invoices.filter((i) => i.role === 'SALE' && !i.duplicate_of);
  const duplicateInvs = invoices.filter((i) => Boolean(i.duplicate_of));

  const purchaseGross = purchaseInvs.reduce((s, i) => s + Number(i.gross || 0), 0);
  const purchaseVat = purchaseInvs.reduce((s, i) => s + Number(i.vat || 0), 0);
  const saleGross = saleInvs.reduce((s, i) => s + Number(i.gross || 0), 0);
  const saleVat = saleInvs.reduce((s, i) => s + Number(i.vat || 0), 0);

  const atRiskPurchaseInvs = purchaseInvs.filter((i) => invoiceBucket(i) === 'AT_RISK');
  const reviewPurchaseInvs = purchaseInvs.filter((i) => invoiceBucket(i) === 'REVIEW');
  const notClaimedInvs = purchaseInvs.filter((i) => invoiceBucket(i) === 'NOT_CLAIMED');
  const noAlertPurchaseInvs = purchaseInvs.filter((i) => invoiceBucket(i) === 'OK');

  const atRiskVat = t.at_risk_vat !== undefined ? t.at_risk_vat : String(atRiskPurchaseInvs.reduce((s, i) => s + Number(i.vat || 0), 0));
  const reviewVat = t.review_vat !== undefined ? t.review_vat : String(reviewPurchaseInvs.reduce((s, i) => s + Number(i.vat || 0), 0));
  const opportunityVat = t.opportunity_vat !== undefined ? t.opportunity_vat : String(items.filter((i) => i.status === 'OPPORTUNITY').reduce((s, i) => s + Number(i.amount || 0), 0));
  const penaltyEstimate = t.penalty_estimate !== undefined ? t.penalty_estimate : '0';

  const notClaimedVat = notClaimedInvs.reduce((s, i) => s + Number(i.vat || 0), 0);
  const noAlertVat = noAlertPurchaseInvs.reduce((s, i) => s + Number(i.vat || 0), 0);

  // Matches accounting.py: scenario_without_review = output_vat - no_alert_vat; scenario_with_review = output_vat - no_alert_vat - review_vat
  const scenarioWithoutReview = saleVat - noAlertVat;
  const scenarioWithReview = saleVat - noAlertVat - Number(reviewVat || 0);

  // Unpaid purchase invoices (consistent with table row payStatus)
  const unpaidInvs = purchaseInvs.filter((i) => {
    const m = matchedMap.get(i.key);
    return !m || m.status !== 'MATCHED';
  });

  const atRiskItems = items.filter((i) => i.status === 'AT_RISK').length;
  const reviewItems = items.filter((i) => i.status === 'REVIEW').length;
  const opportunityItems = items.filter((i) => i.status === 'OPPORTUNITY').length;

  const atRiskInvoices = t.at_risk_invoices ?? atRiskPurchaseInvs.length;
  const reviewInvoices = t.review_invoices ?? reviewPurchaseInvs.length;

  return {
    matchedMap,
    riskByInvoice,
    invoiceBucket,
    purchaseInvs,
    saleInvs,
    duplicateInvs,
    purchaseGross,
    purchaseVat,
    saleGross,
    saleVat,
    noAlertVat,
    notClaimedVat,
    atRiskVat,
    reviewVat,
    opportunityVat,
    penaltyEstimate,
    scenarioWithoutReview,
    scenarioWithReview,
    unpaidInvs,
    unpaidCount: unpaidInvs.length,
    atRiskItems,
    reviewItems,
    opportunityItems,
    atRiskInvoices,
    reviewInvoices,
  };
}

export const state = { platform: null, ws: null, workspaces: [], report: null, schema: null };
export const app = () => $('#app');
export const hashParams = () => new URLSearchParams(location.hash.split('?')[1] || '');

export async function loadWorkspaces() {
  state.platform = await api('/api/platform/context');
  state.ws = state.platform.state === 'ready' ? state.platform.workspace_id : null;
  state.workspaces = state.ws ? await api('/api/workspaces') : [];
  const company = $('#active-company');
  if (company) {
    const profile = state.platform.profile;
    const name = profile?.legal_name || 'Chưa kết nối doanh nghiệp';
    const taxCode = profile?.tax_code ? ` · MST ${profile.tax_code}` : '';
    company.querySelector('.company-legal-name').textContent = name;
    company.querySelector('.company-tax-code').textContent = taxCode;
    company.title = name + taxCode;
  }
  const profileLink = $('#company-profile-link a');
  if (profileLink) {
    const href = portalHref('config');
    if (href) profileLink.href = href;
    else profileLink.removeAttribute('href');
    profileLink.parentElement.hidden = !href;
  }
}

function portalHref(section) {
  try {
    const u = new URL(state.platform?.portal_url);
    const securePortal = u.protocol === 'https:';
    const localPortal = u.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname);
    if ((securePortal || localPortal) && !u.username && !u.password)
      return `${u.origin}/#${section}`;
  } catch { /* No trusted portal connection. */ }
}

export function portalLink(section = 'config', label = 'Mở hồ sơ chung tại portal') {
  const href = portalHref(section);
  if (href) return `<a class="cds--btn cds--btn--tertiary" href="${esc(href)}" target="_top">${esc(label)}</a>`;
  return '<p class="muted">Khởi động Agent 3 từ portal để kết nối hồ sơ doanh nghiệp chung.</p>';
}

export async function loadReport() {
  if (!state.ws) { state.report = null; return null; }
  try {
    state.report = await api(`/api/workspaces/${state.ws}/report`);
  } catch (err) {
    if (err.status !== 404) throw err;
    state.report = null;
  }
  return state.report;
}

export const invoiceOf = (key) => state.report?.invoices.find((i) => i.key === key) || null;
export const invLabel = (i) => (i ? `${i.template || ''}${i.symbol || ''}/${i.number || ''}` : '');

export function needWorkspace() {
  if (state.ws) return false;
  const messages = { sync_required: 'Hồ sơ đang chờ đồng bộ. Lưu lại hồ sơ tại portal hoặc khởi động lại Agent 3 từ portal.', conflict: 'Có nhiều dữ liệu trùng MST hoặc trùng dữ liệu mô phỏng. Cần kiểm tra trước khi liên kết.', invalid_profile: 'Hồ sơ chung chưa hợp lệ. Kiểm tra lại thông tin tại portal.', missing_profile: 'Chưa có hồ sơ doanh nghiệp chung. Hoàn tất hồ sơ tại portal.' };
  app().innerHTML = `<h1 class="page">Kết nối hồ sơ doanh nghiệp</h1><p class="lead">${esc(messages[state.platform?.state] || 'Agent 3 sử dụng doanh nghiệp do portal quản lý.')}</p>${portalLink()}`;
  return true;
}
