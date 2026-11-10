// Shared helpers and state for the Agent 3 interface. Markup uses Carbon Design System classes.
export const $ = (s, el = document) => el.querySelector(s);
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const money = (v) => (v === null || v === undefined || v === '' ? '' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 0 }) + ' đ');
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
export const post = (path, data, opts = {}) => api(path, { ...opts, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data ?? {}) });
export const put = (path, data) => api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

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
export const loading = (text = 'Đang xử lý') => `<div class="bar"><div class="cds--loading cds--loading--small" aria-live="polite"><svg class="cds--loading__svg" viewBox="0 0 100 100"><title>${esc(text)}</title><circle class="cds--loading__stroke" cx="50%" cy="50%" r="44"></circle></svg></div><span class="muted">${esc(text)}...</span></div>`;
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

export const state = { platform: null, ws: null, workspaces: [], report: null, schema: null };
export const app = () => $('#app');
export const hashParams = () => new URLSearchParams(location.hash.split('?')[1] || '');

export async function loadWorkspaces() {
  state.platform = await api('/api/platform/context');
  state.ws = state.platform.state === 'ready' ? state.platform.workspace_id : null;
  state.workspaces = state.ws ? await api('/api/workspaces') : [];
  const company = $('#active-company');
  if (company) {
    company.textContent = state.platform.profile ? `${state.platform.profile.legal_name} · MST ${state.platform.profile.tax_code}` : 'Chưa kết nối doanh nghiệp';
    company.title = company.textContent;
  }
  const link = $('#company-profile-link');
  if (link) { link.innerHTML = portalLink('config', 'Hồ sơ chung'); }
}

export function portalLink(section = 'config', label = 'Mở hồ sơ chung tại portal') {
  try {
    const u = new URL(state.platform?.portal_url);
    if (u.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname) && !u.username && !u.password)
      return `<a class="cds--btn cds--btn--tertiary" href="${esc(u.origin)}/#${esc(section)}" target="_top">${esc(label)}</a>`;
  } catch { /* No trusted portal connection. */ }
  return '<p class="muted">Khởi động Agent 3 từ portal để kết nối hồ sơ doanh nghiệp chung.</p>';
}

export async function loadReport() {
  state.report = null;
  if (!state.ws) return null;
  try { state.report = await api(`/api/workspaces/${state.ws}/report`); } catch (err) { if (err.status !== 404) throw err; state.report = null; }
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
