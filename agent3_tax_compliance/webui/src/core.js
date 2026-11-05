// Shared helpers and state for the Agent 3 interface. Markup uses Carbon Design System classes.
export const $ = (s, el = document) => el.querySelector(s);
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const money = (v) => (v === null || v === undefined || v === '' ? '' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 0 }) + ' đ');
export const dmy = (s) => (s ? s.slice(0, 10).split('-').reverse().join('/') : '');
export const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const type = res.headers.get('content-type') || '';
  const body = type.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error(typeof body === 'object' ? body.detail || JSON.stringify(body) : body);
  return body;
}
export const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data ?? {}) });
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
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="${id}" name="${f.key}">
      ${f.choices.map(([v, l]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>${help}</div></div>`;
  }
  const v = Array.isArray(value) ? value.join('; ') : value;
  return `<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="${id}">${esc(f.label)}${opt}</label>
    <div class="cds--text-input__field-wrapper"><input class="cds--text-input" id="${id}" name="${f.key}" value="${esc(v)}" placeholder="${esc(f.example || '')}" ${f.required ? 'required' : ''}></div>${help}</div>`;
};
export const table = (head, rows, empty = 'Không có dữ liệu.') => (rows.length ? `<div class="table-wrap"><table class="cds--data-table cds--data-table--md">
  <thead><tr>${head.map((h) => `<th${h.num ? ' class="num"' : ''}><div class="cds--table-header-label">${esc(h.label || h)}</div></th>`).join('')}</tr></thead>
  <tbody>${rows.join('')}</tbody></table></div>` : `<div class="empty">${esc(empty)}</div>`);

export const state = { ws: store.get('agent3.ws'), workspaces: [], report: null, schema: null };
export const app = () => $('#app');
export const hashParams = () => new URLSearchParams(location.hash.split('?')[1] || '');

export async function loadWorkspaces() {
  state.workspaces = await api('/api/workspaces');
  if (!state.workspaces.find((w) => w.id === state.ws)) state.ws = state.workspaces[0]?.id || null;
  $('#ws-select').innerHTML = state.workspaces.length
    ? state.workspaces.map((w) => `<option value="${esc(w.id)}" ${w.id === state.ws ? 'selected' : ''}>${esc(w.name)}${w.simulated ? ' (mô phỏng)' : ''}</option>`).join('')
    : '<option value="">Chưa có doanh nghiệp</option>';
}

export async function loadReport() {
  state.report = null;
  if (!state.ws) return null;
  try { state.report = await api(`/api/workspaces/${state.ws}/report`); } catch { state.report = null; }
  return state.report;
}

export const invoiceOf = (key) => state.report?.invoices.find((i) => i.key === key) || null;
export const invLabel = (i) => (i ? `${i.template || ''}${i.symbol || ''}/${i.number || ''}` : '');

export function needWorkspace() {
  if (state.ws) return false;
  app().innerHTML = `<h1 class="page">Chưa có doanh nghiệp</h1><p class="lead">Tạo hồ sơ doanh nghiệp ở trang Tổng quan trước.</p>${button('Về Tổng quan', 'primary', 'data-go="#/"')}`;
  return true;
}
