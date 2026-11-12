// Shared experience helpers: toast, stale-analysis banner, next-step checklist, deadline banner.
import { $, api, dmy, esc, loadWorkspaces, post, state } from './core.js';

export function toast(title, sub = '', kind = 'success') {
  let box = $('#toasts');
  if (!box) { box = document.createElement('div'); box.id = 'toasts'; document.body.appendChild(box); }
  const el = document.createElement('div');
  el.className = `toast toast-${kind}`;
  el.setAttribute('role', 'status');
  el.innerHTML = `<strong>${esc(title)}</strong>${sub ? `<div>${esc(sub)}</div>` : ''}`;
  box.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 4200);
}

export async function runAnalysis(btnHost) {
  const buttons = [...(btnHost?.querySelectorAll('button') || [])];
  buttons.forEach((b) => { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
  try {
    const rep = await post(`/api/workspaces/${state.ws}/run`);
    await loadWorkspaces();
    toast('Đã phân tích xong', `${rep.items.length} việc, thuế có nguy cơ ${Number(rep.totals.at_risk_vat).toLocaleString('vi-VN')} đ`);
    window.dispatchEvent(new Event('hashchange'));
    return rep;
  } catch (err) { if (err.name !== 'AbortError') toast('Không chạy được phân tích', err.message, 'error'); return null; }
  finally { buttons.forEach((b) => { b.disabled = false; b.removeAttribute('aria-busy'); }); }
}

// A banner when files or decisions changed after the last analysis.
export async function freshBanner(el) {
  if (!el || !state.ws) return;
  try {
    const f = await api(`/api/workspaces/${state.ws}/freshness`);
    if (!f.stale) { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="banner banner-warn"><div><strong>${f.analysed ? 'Dữ liệu đã thay đổi sau lần phân tích gần nhất' : 'Chưa có kết quả phân tích'}</strong>
      <div class="small">${f.analysed ? 'Số liệu đang hiển thị có thể đã cũ.' : 'Nạp dữ liệu rồi chạy phân tích để xem kết quả.'}${f.reason ? ' ' + esc(f.reason) : ''}</div></div>
      <button type="button" class="cds--btn cds--btn--primary cds--btn--sm" id="fresh-run">Chạy phân tích ngay</button></div>`;
    $('#fresh-run').onclick = () => runAnalysis($('#fresh-run').parentElement);
  } catch { el.innerHTML = ''; }
}

// Deadlines within the next 7 days, or passed in the last 3 days.
export function deadlineBanner(rep, today = new Date()) {
  const soon = (rep?.calendar || []).filter((c) => { const d = (new Date(c.due) - today) / 864e5; return d >= -3 && d <= 7; });
  if (!soon.length) return '';
  return `<div class="banner banner-danger"><div><strong>Hạn sắp tới</strong><div class="small">${soon.map((c) => `${esc(c.period)}: ${dmy(c.due)} (${esc(c.status)})`).join('; ')}</div></div>
    <a class="cds--btn cds--btn--ghost cds--btn--sm" href="#/lich">Xem lịch thuế</a></div>`;
}

// The next thing to do, from what is already loaded and decided.
export async function nextSteps(ws, rep) {
  const files = ws.files || {};
  let ai = null;
  try { ai = await api(`/api/workspaces/${state.ws}/ai`); } catch { /* model status is optional */ }
  const open = (rep?.items || []).filter((i) => i.status === 'AT_RISK' || i.status === 'REVIEW').length;
  const steps = [
    ['Hồ sơ doanh nghiệp', true, '#/quan-tri/doanh-nghiep', 'Đã có'],
    ['Hóa đơn mua vào (XML)', files.purchase_xml > 0, '#/nap?b=nhanh', files.purchase_xml ? `${files.purchase_xml} tệp` : 'Bắt buộc'],
    ['Sao kê ngân hàng', files.bank > 0, '#/nap?b=nhanh', files.bank ? `${files.bank} tệp` : 'Nên có: thiếu thì mọi hóa đơn từ ngưỡng bị báo chưa có chứng từ'],
    ['Bảng kê từ cổng thuế', files.portal_list > 0, '#/nap?b=nhanh', files.portal_list ? 'Đã có' : 'Nên có: để phát hiện hóa đơn bỏ sót'],
    ['Chạy phân tích', !!rep, '#/nap?b=chay', rep ? `ngày ${dmy(rep.meta.as_of)}` : 'Chưa chạy'],
    ['AI phân loại dòng hàng', !!(ai && ai.labelled_invoices), '#/viec', ai && ai.labelled_invoices ? `${ai.labelled_invoices} hóa đơn` : 'Tùy chọn, chạy trên máy'],
    ['Xử lý việc cần làm', rep && open === 0, '#/viec', rep ? (open ? `còn ${open} việc` : 'Đã xử lý hết') : ''],
  ];
  const next = steps.find((s) => !s[1]);
  return `<details class="steps-card"><summary>Tiến độ kỳ này <span class="muted small">${next ? ` · Tiếp theo: ${esc(next[0])}` : ' · Đã xong các bước'}</span></summary><div class="steps-head">${next ? `<a class="cds--btn cds--btn--primary cds--btn--sm" href="${next[2]}">Làm tiếp: ${esc(next[0])}</a>` : '<span class="muted small">Đã xong các bước</span>'}</div>
    <ol class="checklist">${steps.map(([label, done, href, note]) => `<li class="${done ? 'done' : ''}"><a href="${href}"><span class="dot">${done ? '✓' : ''}</span><span>${esc(label)}</span></a><span class="muted small">${esc(note)}</span></li>`).join('')}</ol></details>`;
}

// A5: sellers that appear on a risk list since this browser last looked.
export function sellerWatch(el, rep) {
  if (!el || !rep) return;
  const key = `agent3.seenRisky.${state.ws}`;
  const now = [...new Set(rep.items.filter((i) => i.code === 'R08_RISKY_SELLER').map((i) => i.invoice_keys[0].split('|')[0]))];
  let seen = null;
  try { seen = JSON.parse(localStorage.getItem(key) || 'null'); } catch { seen = null; }
  const fresh = seen ? now.filter((t) => !seen.includes(t)) : now;
  if (fresh.length) {
    const names = fresh.map((t) => rep.invoices.find((i) => i.seller_tax_id === t)?.seller_name || t);
    const n = rep.items.filter((i) => i.code === 'R08_RISKY_SELLER' && fresh.includes(i.invoice_keys[0].split('|')[0])).length;
    el.innerHTML = `<div class="banner banner-danger"><div><strong>${seen ? 'Người bán mới xuất hiện trong danh sách rủi ro' : 'Người bán đang nằm trong danh sách rủi ro'}</strong>
      <div class="small">${names.map(esc).join(', ')}: ${n} hóa đơn cần kiểm tra hợp đồng, giao nhận và thanh toán trước khi kê khai.</div></div>
      <div class="chips"><a class="cds--btn cds--btn--primary cds--btn--sm" href="#/viec?loc=REVIEW">Xem các hóa đơn</a><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="seen-ok">Đã biết</button></div></div>`;
    $('#seen-ok').onclick = () => { try { localStorage.setItem(key, JSON.stringify(now)); } catch { /* private mode */ } el.innerHTML = ''; };
  } else { el.innerHTML = ''; }
}
