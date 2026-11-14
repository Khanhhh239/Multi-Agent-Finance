// Shared experience helpers: toast, stale-analysis banner, next-step checklist, deadline banner, visual analysis loading.
import { $, api, app, dmy, esc, loadWorkspaces, money, notice, post, state } from './core.js';

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

function ensureTopProgressBar() {
  let bar = document.querySelector('.kt-top-progress');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'kt-top-progress';
    bar.setAttribute('aria-hidden', 'true');
    document.body.appendChild(bar);
  }
  return bar;
}

export function renderAnalysisProgressCard(title = 'Đang phân tích dữ liệu hóa đơn và sao kê kỳ thuế') {
  return `<div class="a3-analysis-progress-card" role="status" aria-live="polite">
    <div class="a3-analysis-head">
      <div class="a3-analysis-title-wrap">
        <span class="kt-spinner" aria-hidden="true"></span>
        <div>
          <strong class="a3-analysis-title">${esc(title)}</strong>
          <div class="a3-analysis-sub">Hệ thống đang đối chiếu chứng từ gốc XML, bảng kê cổng thuế và sao kê ngân hàng</div>
        </div>
      </div>
      <span class="a3-analysis-timer" data-analysis-timer>0.0s</span>
    </div>
    <div class="a3-analysis-bar-track" aria-hidden="true">
      <div class="a3-analysis-bar-fill"></div>
    </div>
    <ol class="a3-analysis-steps">
      <li class="a3-step is-active" data-step-idx="0">
        <span class="a3-step-num">01</span>
        <span class="a3-step-text">Kiểm tra cấu trúc XML, chữ ký số và hóa đơn trùng lặp</span>
      </li>
      <li class="a3-step" data-step-idx="1">
        <span class="a3-step-num">02</span>
        <span class="a3-step-text">Đối chiếu bảng kê cổng thuế và danh sách mã số thuế rủi ro</span>
      </li>
      <li class="a3-step" data-step-idx="2">
        <span class="a3-step-num">03</span>
        <span class="a3-step-text">Khớp nối giao dịch sao kê ngân hàng và tổng hợp bảng tính thuế GTGT</span>
      </li>
    </ol>
  </div>`;
}

export async function runWithAnalysisEffect({ triggerBtn, stageEl, title, onSuccess, onError } = {}) {
  const topBar = ensureTopProgressBar();
  topBar.classList.add('active');

  const origHtml = triggerBtn ? triggerBtn.innerHTML : '';
  if (triggerBtn) {
    triggerBtn.disabled = true;
    triggerBtn.setAttribute('aria-busy', 'true');
    triggerBtn.classList.add('is-analyzing');
    triggerBtn.innerHTML = `<span class="kt-spinner" aria-hidden="true" style="width:14px;height:14px;border-width:2px;margin-right:8px"></span><span>Đang phân tích...</span>`;
  }

  let host = stageEl;
  if (!host) {
    host = $('#analysis-stage') || $('#run-msg') || $('#r2') || $('#autorun');
  }
  if (host) {
    host.innerHTML = renderAnalysisProgressCard(title);
  }

  const appRoot = app();
  if (appRoot) appRoot.classList.add('a3-is-analyzing');

  const startMs = performance.now();
  const timerId = setInterval(() => {
    if (!host || !host.isConnected) return;
    const elapsed = (performance.now() - startMs) / 1000;
    const timerNode = host.querySelector('[data-analysis-timer]');
    if (timerNode) timerNode.textContent = `${elapsed.toFixed(1)}s`;
    const steps = host.querySelectorAll('.a3-step');
    if (steps.length === 3) {
      if (elapsed >= 0.35) {
        steps[0].classList.remove('is-active');
        steps[0].classList.add('is-done');
        steps[1].classList.add('is-active');
      }
      if (elapsed >= 0.75) {
        steps[1].classList.remove('is-active');
        steps[1].classList.add('is-done');
        steps[2].classList.add('is-active');
      }
    }
  }, 100);

  try {
    const rep = await post(`/api/workspaces/${state.ws}/run`);
    await loadWorkspaces();
    if (host && host.isConnected) {
      host.querySelectorAll('.a3-step').forEach((s) => {
        s.classList.remove('is-active');
        s.classList.add('is-done');
      });
    }
    if (onSuccess) {
      await onSuccess(rep);
    } else {
      toast('Đã phân tích xong', `${rep.items.length} việc, thuế có nguy cơ ${Number(rep.totals.at_risk_vat).toLocaleString('vi-VN')} đ`);
      window.dispatchEvent(new Event('hashchange'));
    }
    return rep;
  } catch (err) {
    if (err.name !== 'AbortError') {
      if (onError) {
        onError(err, host);
      } else if (host && host.isConnected) {
        host.innerHTML = notice('error', 'Phân tích không chạy được', err.message);
      } else {
        toast('Không chạy được phân tích', err.message, 'error');
      }
    }
    return null;
  } finally {
    clearInterval(timerId);
    topBar.classList.remove('active');
    if (appRoot) appRoot.classList.remove('a3-is-analyzing');
    if (triggerBtn && triggerBtn.isConnected) {
      triggerBtn.disabled = false;
      triggerBtn.removeAttribute('aria-busy');
      triggerBtn.classList.remove('is-analyzing');
      triggerBtn.innerHTML = origHtml;
    }
  }
}

export async function runAnalysis(btnHost) {
  const triggerBtn = btnHost?.querySelector('#fresh-run') || btnHost?.querySelector('button') || null;
  let stageEl = $('#analysis-stage');
  if (!stageEl && btnHost) {
    stageEl = document.createElement('div');
    stageEl.style.marginTop = '10px';
    btnHost.after(stageEl);
  }
  return runWithAnalysisEffect({ triggerBtn, stageEl });
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
    ['Sao kê ngân hàng', files.bank > 0, '#/nap?b=nhanh', files.bank ? `${files.bank} tệp` : 'Nên có'],
    ['Bảng kê từ cổng thuế', files.portal_list > 0, '#/nap?b=nhanh', files.portal_list ? 'Đã có' : 'Nên có'],
    ['Chạy phân tích', !!rep, '#/nap?b=chay', rep ? `ngày ${dmy(rep.meta.as_of)}` : 'Chưa chạy'],
    ['AI phân loại dòng hàng', !!(ai && ai.labelled_invoices), '#/viec', ai && ai.labelled_invoices ? `${ai.labelled_invoices} hóa đơn` : 'Tùy chọn'],
    ['Xử lý việc cần làm', rep && open === 0, '#/viec', rep ? (open ? `còn ${open} việc` : 'Hoàn tất') : ''],
  ];
  const next = steps.find((s) => !s[1]);
  return `<details class="steps-card"><summary>Tiến độ kỳ này <span class="muted small">${next ? ` · Tiếp theo: ${esc(next[0])}` : ' · Hoàn tất các bước'}</span></summary><div class="steps-head">${next ? `<a class="cds--btn cds--btn--primary cds--btn--sm" href="${next[2]}">Làm tiếp: ${esc(next[0])}</a>` : '<span class="muted small">Hoàn tất các bước</span>'}</div>
    <ol class="checklist">${steps.map(([label, done, href, note], idx) => `<li class="${done ? 'done' : ''}"><a href="${href}"><span class="dot">${idx + 1}</span><span>${esc(label)}</span></a><span class="muted small">${esc(note)}</span></li>`).join('')}</ol></details>`;
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
