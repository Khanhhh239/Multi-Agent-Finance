import { $, esc, onPageLeave } from './core.js';

export function portalOrigin() {
  try {
    const value = new URLSearchParams(location.search).get('portal') || sessionStorage.getItem('kt-portal-origin');
    const u = new URL(value);
    if (u.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(u.hostname) && !u.username && !u.password && u.origin !== location.origin) return u.origin;
  } catch { /* standalone */ }
  return null;
}

export function intakeLinks(root) {
  const origin = portalOrigin();
  if (!document.documentElement.classList.contains('in-platform') || !origin) return;
  root.querySelectorAll('a[href^="#/nap"], [data-go^="#/nap"]').forEach((el) => {
    const action = el.getAttribute('href') || el.dataset.go;
    if (action.includes('b=chay')) {
      el.setAttribute('href', '#/'); el.dataset.go = '#/';
      el.textContent = 'Chạy phân tích ở Tổng quan';
      return;
    }
    const a = document.createElement('a');
    a.className = el.className;
    a.href = origin + '/#data'; a.target = '_top';
    a.textContent = 'Nạp dữ liệu tại workspace tổng';
    el.replaceWith(a);
  });
}

export function closeDialog() { $('#modal-root').replaceChildren(); }
export function bindDialog() {
  const dialog = $('.drawer');
  if (!dialog) return;
  const previous = document.activeElement;
  dialog.setAttribute('aria-modal', 'true'); dialog.tabIndex = -1;
  const backdrop = document.createElement('div'); backdrop.className = 'drawer-backdrop';
  dialog.before(backdrop);
  const inert = [$('#app'), $('.side'), $('header')].filter(Boolean);
  inert.forEach((el) => { el.inert = true; });
  const controller = new AbortController();
  const observer = new MutationObserver(() => { if (!dialog.isConnected) release(); });
  const release = () => {
    observer.disconnect(); controller.abort(); backdrop.remove();
    inert.forEach((el) => { el.inert = false; });
    if (previous?.isConnected) previous.focus({ preventScroll: true });
  };
  observer.observe($('#modal-root'), { childList: true });
  const close = () => closeDialog();
  $('#close', dialog)?.addEventListener('click', close, { signal: controller.signal });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    if (e.key !== 'Tab') return;
    const els = [...dialog.querySelectorAll('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter((el) => el.getClientRects().length);
    if (!els.length) { e.preventDefault(); dialog.focus(); return; }
    if (e.shiftKey && (document.activeElement === els[0] || document.activeElement === dialog)) { e.preventDefault(); els.at(-1).focus(); }
    else if (!e.shiftKey && (document.activeElement === els.at(-1) || document.activeElement === dialog)) { e.preventDefault(); els[0].focus(); }
  }, { signal: controller.signal });
  dialog.focus({ preventScroll: true });
  onPageLeave(() => { close(); release(); });
}

export function decoratePage(root) {
  intakeLinks(root);
  root.querySelectorAll('.table-wrap').forEach((el) => { el.tabIndex = 0; el.setAttribute('role', 'region'); el.setAttribute('aria-label', 'Bảng dữ liệu, cuộn ngang để xem thêm cột'); });
  root.querySelectorAll('[data-go]').forEach((el) => {
    if (el.tagName !== 'TR') return;
    el.tabIndex = 0;
    el.onkeydown = (e) => { if (e.target === el && ['Enter', ' '].includes(e.key)) { e.preventDefault(); el.click(); } };
  });
  root.querySelectorAll('.bar:has(.filter-input)').forEach((bar) => {
    bar.classList.add('toolbar');
    bar.querySelectorAll('input[aria-label],select[aria-label]').forEach((input) => {
      if (input.closest('label')) return;
      const label = document.createElement('label'); label.className = 'filter-field';
      const text = document.createElement('span'); text.textContent = input.getAttribute('aria-label');
      input.before(label); label.append(text, input);
    });
  });
}

// Native constraints plus inline errors and a linked summary, without changing API validation.
export function installValidation() {
  document.addEventListener('invalid', (e) => {
    e.preventDefault();
    const input = e.target; const form = input.form;
    if (!form) return;
    queueMicrotask(() => {
      const fields = [...form.elements].filter((el) => el.validity && !el.validity.valid);
      form.querySelectorAll('.form-error,.error-summary').forEach((el) => el.remove());
      fields.forEach((el, i) => {
        el.id ||= 'invalid-' + i;
        el.setAttribute('aria-invalid', 'true');
        const error = document.createElement('div'); error.className = 'form-error'; error.id = el.id + '-error'; error.textContent = el.validationMessage;
        el.setAttribute('aria-errormessage', error.id); el.after(error);
      });
      if (!fields.length) return;
      const summary = document.createElement('div'); summary.className = 'error-summary'; summary.tabIndex = -1; summary.setAttribute('role', 'alert');
      summary.innerHTML = '<strong>Kiểm tra lại thông tin</strong>' + fields.map((el) => `<a href="#${esc(el.id)}" data-error-field="${esc(el.id)}">${esc(el.labels?.[0]?.textContent || el.name || 'Trường bắt buộc')}: ${esc(el.validationMessage)}</a>`).join('');
      summary.onclick = (ev) => { const link = ev.target.closest('[data-error-field]'); if (link) { ev.preventDefault(); document.getElementById(link.dataset.errorField)?.focus(); } };
      form.prepend(summary); summary.focus();
    });
  }, true);
  document.addEventListener('input', (e) => {
    if (!e.target.validity?.valid) return;
    e.target.removeAttribute('aria-invalid');
    document.getElementById(e.target.id + '-error')?.remove();
    e.target.removeAttribute('aria-errormessage');
  });
}
