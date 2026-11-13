// Invoices, bank, calendar, questions, legal corpus and enterprise settings.
import { $, api, app, button, compareDecimal, dmy, esc, field, formatSpecialMoney, hashParams, invLabel, invoiceOf, loadReport, loading, money, needWorkspace, notice, post, put, sonHeader,
  onPageLeave, state, table, tag } from './core.js';

const ICONS_INV = {
  inbox: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>',
  send: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
  alert: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  shieldCheck: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>',
  checkCircle: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  check: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  search: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  download: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  list: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
  clock: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  minus: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
};
import { bankProposals, lawAlerts, riskImport } from './pages_ai.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageInvoices() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Hóa đơn</h1>${notice('info', 'Chưa phân tích')}`; return; }
  const matched = new Map(rep.matches.flatMap((m) => m.invoice_keys.map((k) => [k, m])));
  const risk = new Map();
  rep.items.forEach((it) => it.invoice_keys.forEach((k) => risk.set(k, [...(risk.get(k) || []), it])));
  const months = [...new Set(rep.invoices.filter((i) => i.issue_date).map((i) => i.issue_date.slice(0, 7)))].sort();
  const worst = (i) => { const its = (risk.get(i.key) || []).filter((x) => x.status !== 'INFO'); return its.some((x) => x.status === 'AT_RISK') ? 'AT_RISK' : its.some((x) => x.status === 'REVIEW') ? 'REVIEW' : its.length ? 'OTHER' : 'OK'; };
  const PAGE = 50;
  const viewKey = `agent3.invoices.${state.ws}.${state.platform?.profile_revision}`;
  let savedView = {}; try { savedView = JSON.parse(sessionStorage.getItem(viewKey) || '{}'); } catch {}
  let page = savedView.page || 0;
  let tabFilter = savedView.tabFilter || 'all';

  const purchaseInvs = rep.invoices.filter((i) => i.role === 'PURCHASE');
  const saleInvs = rep.invoices.filter((i) => i.role === 'SALE');
  const purchaseGross = purchaseInvs.reduce((s, i) => s + Number(i.gross || 0), 0);
  const purchaseVat = purchaseInvs.reduce((s, i) => s + Number(i.vat || 0), 0);
  const saleGross = saleInvs.reduce((s, i) => s + Number(i.gross || 0), 0);
  const saleVat = saleInvs.reduce((s, i) => s + Number(i.vat || 0), 0);
  const totalGross = purchaseGross + saleGross;
  const purchasePct = totalGross > 0 ? Math.round((purchaseGross / totalGross) * 100) : 50;
  const salePct = 100 - purchasePct;
  const vatDiff = purchaseVat - saleVat; // > 0: khấu trừ chuyển sau; < 0: phải nộp
  const atRiskCount = rep.invoices.filter((i) => worst(i) === 'AT_RISK').length;
  const reviewCount = rep.invoices.filter((i) => worst(i) === 'REVIEW').length;
  const unpaidCount = purchaseInvs.filter((i) => !matched.get(i.key)).length;
  const signedCount = rep.invoices.filter((i) => i.signed).length;
  const signedPct = rep.invoices.length > 0 ? Math.round((signedCount / rep.invoices.length) * 100) : 100;

  app().innerHTML = `
    ${sonHeader('Hóa đơn', 'Hóa đơn GTGT', 'QUẢN LÝ CHỨNG TỪ', `<span class="ctx-chip chip-count">${rep.invoices.length.toLocaleString('vi-VN')} hóa đơn</span>`)}
    
    <!-- EXECUTIVE INVOICE & VAT BALANCE HUB -->
    <div class="inv-balance-hub">
      <div class="hub-main-grid">
        <!-- CỘT 1: HÓA ĐƠN MUA VÀO (ĐẦU VÀO) -->
        <div class="hub-card hub-card-purchase">
          <div class="hub-card-header">
            <span class="hub-icon-badge badge-purchase">${ICONS_INV.inbox}</span>
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN ĐẦU VÀO</span>
              <span class="hub-action-sub">Mua vào để khấu trừ thuế</span>
            </div>
            <span class="hub-count-tag count-purchase">${purchaseInvs.length.toLocaleString('vi-VN')} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng TT:</span>
              <span class="hub-amount font-num">${money(purchaseGross)}</span>
            </div>
            <div class="hub-vat-pill vat-purchase">
              <span class="vat-pill-label">Thuế GTGT đầu vào:</span>
              <span class="vat-pill-val font-num"><strong>${money(purchaseVat)}</strong></span>
            </div>
          </div>
        </div>

        <!-- CỘT 2: CÁN CÂN GTGT & ĐỐI CHIẾU TRUNG TÂM -->
        <div class="hub-card hub-card-center">
          <div class="center-balance-head">
            <span class="balance-title">CÂN ĐỐI NGHĨA VỤ THUẾ GTGT</span>
            <span class="balance-sub">Đối chiếu Mua vào ⟷ Bán ra</span>
          </div>

          <div class="balance-ratio-bar-wrap">
            <div class="ratio-labels">
              <span class="ratio-label-p">Mua: <strong>${purchasePct}%</strong></span>
              <span class="ratio-label-s">Bán: <strong>${salePct}%</strong></span>
            </div>
            <div class="ratio-bar-track">
              <div class="ratio-bar-fill-p" style="width:${purchasePct}%" title="Tỷ trọng mua vào: ${purchasePct}%"></div>
              <div class="ratio-bar-fill-s" style="width:${salePct}%" title="Tỷ trọng bán ra: ${salePct}%"></div>
            </div>
          </div>

          <div class="balance-result-box ${vatDiff >= 0 ? 'result-credit' : 'result-payable'}">
            <span class="result-status-icon">${vatDiff >= 0 ? ICONS_INV.shieldCheck : ICONS_INV.alert}</span>
            <div class="result-info">
              <div class="result-name">${vatDiff >= 0 ? 'Thuế GTGT còn được khấu trừ:' : 'Thuế GTGT phải nộp dự kiến:'}</div>
              <div class="result-value font-num">${vatDiff >= 0 ? '+' : ''}${money(Math.abs(vatDiff))}</div>
            </div>
          </div>
        </div>

        <!-- CỘT 3: HÓA ĐƠN BÁN RA (ĐẦU RA) -->
        <div class="hub-card hub-card-sale">
          <div class="hub-card-header">
            <span class="hub-icon-badge badge-sale">${ICONS_INV.send}</span>
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN ĐẦU RA</span>
              <span class="hub-action-sub">Bán ra phát sinh thuế nộp</span>
            </div>
            <span class="hub-count-tag count-sale">${saleInvs.length.toLocaleString('vi-VN')} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng TT:</span>
              <span class="hub-amount font-num">${money(saleGross)}</span>
            </div>
            <div class="hub-vat-pill vat-sale">
              <span class="vat-pill-label">Thuế GTGT đầu ra:</span>
              <span class="vat-pill-val font-num"><strong>${money(saleVat)}</strong></span>
            </div>
          </div>
        </div>
      </div>

      <!-- DẢI FOOTNOTE GIÁM SÁT RỦI RO & CHỨNG TỪ DƯỚI ĐÁY -->
      <div class="hub-footer-strip">
        <div class="strip-left">
          <span class="strip-label">Giám sát rủi ro:</span>
          <span class="audit-badge audit-risk ${atRiskCount > 0 ? 'has-issue' : ''}">
            ${ICONS_INV.alert} <strong>${atRiskCount.toLocaleString('vi-VN')}</strong> có nguy cơ
          </span>
          <span class="audit-badge audit-review">
            <strong>${reviewCount.toLocaleString('vi-VN')}</strong> cần xem xét
          </span>
          <span class="audit-badge audit-bank">
            ${ICONS_INV.clock} <strong>${unpaidCount.toLocaleString('vi-VN')}</strong> chưa ghép ngân hàng
          </span>
        </div>
        <div class="strip-right">
          <span class="audit-badge audit-signed">
            ${ICONS_INV.checkCircle} Chữ ký số: <strong>${signedPct}% hợp lệ</strong> (${signedCount.toLocaleString('vi-VN')}/${rep.invoices.length.toLocaleString('vi-VN')})
          </span>
        </div>
      </div>
    </div>

    <!-- SEGMENTED TABS -->
    <div class="inv-segmented-pills">
      ${[
        ['all', 'Tất cả', rep.invoices.length, ICONS_INV.list, 'pill-tab-all'],
        ['PURCHASE', 'Mua vào', purchaseInvs.length, ICONS_INV.inbox, 'pill-tab-purchase'],
        ['SALE', 'Bán ra', saleInvs.length, ICONS_INV.send, 'pill-tab-sale'],
        ['RISK', 'Có cảnh báo', atRiskCount + reviewCount, ICONS_INV.alert, 'pill-tab-risk'],
        ['UNPAID', 'Chưa ghép ngân hàng', unpaidCount, ICONS_INV.clock, 'pill-tab-bank'],
      ].map(([k, l, n, icon, cls]) => `<button type="button" class="inv-filter-pill ${cls} ${k === tabFilter ? 'active' : ''}" data-tab="${k}">
        <span class="pill-icon">${icon}</span>
        <span class="pill-name">${esc(l)}</span>
        <span class="pill-count">${n.toLocaleString('vi-VN')}</span>
      </button>`).join('')}
    </div>

    <!-- UNIFIED SINGLE-LINE TOOLBAR -->
    <div class="inv-toolbar">
      <div class="inv-search-wrap">
        <span class="inv-search-icon" aria-hidden="true">${ICONS_INV.search}</span>
        <input class="cds--text-input inv-search-input" id="iq" placeholder="Tìm theo số hóa đơn, đối tác, MST hoặc nội dung hàng hóa..." aria-label="Tìm hóa đơn">
        <button type="button" class="inv-search-clear" id="iq-clear" title="Xóa tìm kiếm" hidden aria-label="Xóa tìm kiếm">✕</button>
      </div>

      <select class="cds--select-input inv-filter-select" id="st" aria-label="Tình trạng">
        <option value="">Mọi tình trạng</option>
        <option value="AT_RISK">Có nguy cơ</option>
        <option value="REVIEW">Cần xem xét</option>
        <option value="OK">Không cảnh báo</option>
        <option value="UNPAID">Chưa ghép thanh toán</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="mon" aria-label="Tháng">
        <option value="">Mọi kỳ tháng</option>
        ${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}
      </select>

      ${button('✕ Đặt lại', 'ghost', 'id="reset-invoices" class="cds--btn--sm btn-inv-reset"')}
      <a class="cds--btn cds--btn--ghost cds--btn--sm btn-inv-export" href="/api/workspaces/${esc(state.ws)}/export/hoa-don.xlsx">
        <span class="btn-icon">${ICONS_INV.download}</span> <span>Xuất Excel</span>
      </a>
      <span class="muted small inv-counter" id="icount" role="status"></span>
    </div>

    <div id="ilist"></div>`;

  let sort = savedView.sort || ['issue_date', -1];
  const keyOf = { issue_date: (i) => i.issue_date || '', gross: (i) => i.gross || '0', vat: (i) => i.vat || '0', seller: (i) => (i.role === 'SALE' ? i.buyer_name : i.seller_name) || '' };

  const paint = () => {
    const st = $('#st').value; const mon = $('#mon').value; const q = $('#iq').value.trim().toLowerCase();
    const view = rep.invoices.filter((i) => {
      if (tabFilter === 'PURCHASE' && i.role !== 'PURCHASE') return false;
      if (tabFilter === 'SALE' && i.role !== 'SALE') return false;
      if (tabFilter === 'RISK' && !['AT_RISK', 'REVIEW'].includes(worst(i))) return false;
      if (tabFilter === 'UNPAID' && (i.role !== 'PURCHASE' || matched.get(i.key))) return false;

      if (mon && !(i.issue_date || '').startsWith(mon)) return false;
      if (st) {
        if (st === 'UNPAID' && (i.role !== 'PURCHASE' || matched.get(i.key))) return false;
        if (st !== 'UNPAID' && worst(i) !== st) return false;
      }
      if (q && !`${invLabel(i)} ${i.number} ${i.seller_name} ${i.seller_tax_id} ${i.buyer_name || ''} ${(i.descriptions || []).join(' ')}`.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    }).sort((x, y) => {
      const a = keyOf[sort[0]](x); const b = keyOf[sort[0]](y);
      return (['gross', 'vat'].includes(sort[0]) ? compareDecimal(a, b) : a > b ? 1 : a < b ? -1 : 0) * sort[1];
    });

    const pages = Math.max(1, Math.ceil(view.length / PAGE));
    page = Math.min(page, pages - 1);
    const th = (k, l, num, extraCls = '') => `<th class="${num ? 'num ' : ''}${extraCls} sortable" aria-sort="${sort[0] === k ? (sort[1] > 0 ? 'ascending' : 'descending') : 'none'}"><button type="button" class="sort-button" data-sort="${k}">${esc(l)}${sort[0] === k ? (sort[1] > 0 ? ' ↑' : ' ↓') : ''}</button></th>`;
    $('#icount').textContent = `${view.length.toLocaleString('vi-VN')} hóa đơn`;

    $('#ilist').innerHTML = view.length ? `<div class="table-wrap inv-table-wrap"><table class="cds--data-table cds--data-table--md inv-data-table">
      <thead>
        <tr>
          <th style="min-width:160px">Hóa đơn & Ký hiệu</th>
          ${th('issue_date', 'Ngày lập', false, 'th-date')}
          ${th('seller', 'Người bán / Người mua', false, 'th-partner')}
          ${th('gross', 'Tổng thanh toán', true, 'th-gross')}
          ${th('vat', 'Thuế GTGT', true, 'th-vat')}
          <th style="min-width:110px">Toàn vẹn</th>
          <th style="min-width:115px">Thanh toán</th>
          <th style="min-width:150px">Cảnh báo rủi ro</th>
        </tr>
      </thead>
      <tbody>
        ${view.slice(page * PAGE, page * PAGE + PAGE).map((i) => {
          const m = matched.get(i.key);
          const its = (risk.get(i.key) || []).filter((x) => x.status !== 'INFO');
          const integrity = i.guard_errors.length
            ? `<span class="integrity-badge badge-err">${ICONS_INV.alert} Lỗi XML (${i.guard_errors.length})</span>`
            : (i.signed ? `<span class="integrity-badge badge-ok">${ICONS_INV.shieldCheck} Ký hợp lệ</span>` : `<span class="integrity-badge badge-none">Không ký</span>`);
          
          const payStatus = i.role === 'SALE'
            ? '<span class="muted small">—</span>'
            : (m ? (m.status === 'MATCHED'
                ? `<span class="pay-badge pay-ok">${ICONS_INV.checkCircle} Đã ghép</span>`
                : `<span class="pay-badge pay-ambig">${ICONS_INV.clock} Mơ hồ</span>`)
              : `<span class="pay-badge pay-none">${ICONS_INV.minus} Chưa ghép</span>`);
              
          const partnerName = i.role === 'SALE' ? (i.buyer_name || 'Khách hàng') : (i.seller_name || 'Nhà cung cấp');
          const partnerTax = i.role === 'SALE' ? (i.buyer_tax_id || '') : (i.seller_tax_id || '');

          return `<tr class="${its.length ? 'clickable row-has-risk' : ''}" ${its.length ? `data-go="#/viec?open=${encodeURIComponent(i.key)}" title="Bấm để mở việc cần xử lý"` : ''}>
            <td>
              <div class="inv-code-pill ${i.role === 'SALE' ? 'pill-sale' : 'pill-purchase'}" title="${esc(invLabel(i))}">
                <span class="inv-type-icon">${i.role === 'SALE' ? ICONS_INV.send : ICONS_INV.inbox}</span>
                <span class="inv-code-text">${esc(invLabel(i))}</span>
                ${i.duplicate_of ? '<span class="dup-pill">Trùng</span>' : ''}
              </div>
              <div class="inv-role-sub">${i.role === 'SALE' ? '<span class="role-badge sale">Bán ra</span>' : '<span class="role-badge purchase">Mua vào</span>'}</div>
            </td>
            <td class="font-date">${dmy(i.issue_date)}</td>
            <td>
              <div class="partner-name" title="${esc(partnerName)}">${esc(partnerName)}</div>
              ${partnerTax ? `<div class="partner-tax mono"><span class="mst-tag">MST</span> <code>${esc(partnerTax)}</code></div>` : ''}
            </td>
            <td class="num font-num"><strong>${money(i.gross)}</strong></td>
            <td class="num font-num vat-cell"><span class="vat-amount">${money(i.vat)}</span></td>
            <td>${integrity}</td>
            <td>${payStatus}</td>
            <td>
              <div class="chips">
                ${its.length ? its.map((x) => tag(x.status, x.title.length > 36 ? `${x.title.slice(0, 34)}…` : x.title)).join('') : `<span class="tag-ok-check">${ICONS_INV.check} Hợp lệ</span>`}
              </div>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>
    <div class="bar pager">
      ${button('Trang trước', 'ghost', `id="prev" ${page === 0 ? 'disabled' : ''}`)}
      <span class="small">Trang <strong>${page + 1}</strong> / ${pages} (${view.length.toLocaleString('vi-VN')} hóa đơn)</span>
      ${button('Trang sau', 'ghost', `id="next" ${page >= pages - 1 ? 'disabled' : ''}`)}
    </div>`
    : `<div class="empty invoice-empty">
        <div class="empty-icon-wrap" style="color:var(--cds-text-secondary);margin-bottom:8px">${ICONS_INV.alert}</div>
        <div style="font-weight:600;font-size:15px;margin-bottom:4px">Không có hóa đơn nào khớp bộ lọc</div>
        <div class="muted small">Thử xóa bộ lọc hoặc điều chỉnh từ khóa tìm kiếm.</div>
      </div>`;

    if ($('#prev')) $('#prev').onclick = () => { page -= 1; paint(); };
    if ($('#next')) $('#next').onclick = () => { page += 1; paint(); };
    app().querySelectorAll('[data-sort]').forEach((h) => {
      h.onclick = () => {
        const key = h.dataset.sort;
        sort = [key, sort[0] === key ? -sort[1] : -1];
        paint();
        app().querySelector(`[data-sort="${key}"]`)?.focus({ preventScroll: true });
      };
    });
  };

  app().querySelectorAll('.inv-filter-pill').forEach((btn) => {
    btn.onclick = () => {
      app().querySelectorAll('.inv-filter-pill').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      tabFilter = btn.dataset.tab;
      page = 0;
      paint();
    };
  });

  ['st', 'mon'].forEach((id) => { $(`#${id}`).onchange = () => { page = 0; paint(); }; });
  
  const iq = $('#iq');
  const iqClear = $('#iq-clear');
  iq.oninput = () => {
    iqClear.hidden = !iq.value;
    page = 0;
    paint();
  };
  iqClear.onclick = () => {
    iq.value = '';
    iqClear.hidden = true;
    page = 0;
    paint();
  };

  $('#reset-invoices').onclick = () => {
    tabFilter = 'all';
    app().querySelectorAll('.inv-filter-pill').forEach((b) => b.classList.toggle('active', b.dataset.tab === 'all'));
    ['st', 'mon', 'iq'].forEach((id) => { $(`#${id}`).value = ''; });
    iqClear.hidden = true;
    page = 0;
    paint();
  };

  ['st', 'mon', 'iq'].forEach(id => { $(`#${id}`).value = savedView[id] || ''; });
  if (savedView.iq) iqClear.hidden = false;
  paint();

  onPageLeave(() => {
    if (!app().querySelector('#ilist')) return;
    try {
      sessionStorage.setItem(viewKey, JSON.stringify({
        sort, page, tabFilter, scroll: window.scrollY,
        ...Object.fromEntries(['st', 'mon', 'iq'].map(id => [id, $(`#${id}`).value]))
      }));
    } catch {}
  });

  requestAnimationFrame(() => {
    if (app().querySelector('#ilist')) window.scrollTo(0, savedView.scroll || 0);
  });
}

export async function pageBank() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Ngân hàng</h1>${notice('info', 'Chưa phân tích')}`; return; }
  const usedBy = new Map(rep.matches.flatMap((m) => m.txn_ids.map((t) => [t, m])));
  app().innerHTML = `
    ${sonHeader('Ngân hàng', 'Giao dịch ngân hàng', 'ĐỐI SOÁT THANH TOÁN', `<span class="ctx-chip chip-count">${rep.transactions.length} giao dịch</span>`)}
    <p class="lead" style="margin-top:10px">${rep.transactions.length} giao dịch từ các tệp sao kê. Một khoản chi chỉ được ghép khi đúng số tiền và có dấu hiệu nhận ra người bán. <a href="#/du-lieu">Chọn bảng kê cổng thuế đang dùng ↗</a></p><div id="props"></div>
    ${table(['Ngày', 'Chiều', { label: 'Số tiền', num: true }, 'Đối ứng', 'Nội dung', 'Ghép với hóa đơn', 'Nguồn'], rep.transactions.map((t) => {
      const m = usedBy.get(t.txn_id);
      return `<tr><td>${dmy(t.booked)}</td><td>${t.direction === 'OUT' ? 'Chi' : 'Thu'}</td><td class="num">${money(t.amount)}</td>
        <td>${esc(t.counterparty_name || '')}<div class="muted small mono">${esc(t.counterparty_account || '')}</div></td><td>${esc(t.description)}</td>
        <td>${m ? `${m.invoice_keys.map((k) => esc(invLabel(invoiceOf(k)))).join(', ')}<div class="muted small">${m.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}</div>` : ''}</td><td class="muted small">${esc(t.source)}</td></tr>`;
    }))}`;
  bankProposals($('#props'));
}

export async function pageCalendar() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  app().innerHTML = `
    ${sonHeader('Lịch thuế', 'Lịch thuế', 'THEO DÕI NGHĨA VỤ')}
    <p class="lead" style="margin-top:10px">Hạn lịch theo bộ quy tắc nháp, đã tính dời ngày nghỉ theo cấu hình. Tình trạng được tính tại ngày phân tích ${dmy(rep?.meta.as_of)}; chưa xác nhận đã kê khai hoặc nộp tiền.</p>
    ${table(['Kỳ', 'Hạn nộp', 'Tình trạng', 'Căn cứ'], (rep?.calendar || []).map((c) => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}${c.moved_from ? `<div class="muted small">Dời từ ${dmy(c.moved_from)} do ngày nghỉ</div>` : ''}</td><td>${esc(c.status)}${c.open_items ? `<div><a href="#/viec" class="risk-text">còn ${c.open_items} việc chưa xử lý của kỳ này</a></div>` : ''}${c.extension ? `<div class="muted small">${esc(c.extension)}</div>` : ''}</td><td class="muted small">${esc(c.basis)}</td></tr>`), 'Chưa có dữ liệu.')}`;
}

export async function pageAsk() {
  if (needWorkspace()) return;
  const key = `agent3.chat.${state.ws}`;
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(key) || '[]'); } catch { history = []; }
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(history.slice(-30))); } catch { /* private mode */ } };
  const groups = [['Về dữ liệu của doanh nghiệp (trả lời ngay)', ['Tháng 8 có bao nhiêu thuế có nguy cơ bị loại?', 'Hóa đơn số 340 có vấn đề gì, vì sao?', 'Hạn nộp tờ khai khi nào?']],
    ['Về quy định (mô hình trên máy đọc luật, 30 đến 60 giây)', ['Mức tính tiền chậm nộp là bao nhiêu mỗi ngày?', 'Lập hóa đơn không đúng thời điểm bị phạt thế nào?', 'Điều kiện khấu trừ thuế giá trị gia tăng đầu vào gồm những gì?']]];
  app().innerHTML = `<h1 class="page">Hỏi đáp</h1><p class="lead">Câu hỏi về dữ liệu được trả lời từ kết quả phân tích. Câu hỏi về quy định được trả lời từ kho luật: mỗi câu phải trích nguyên văn điều khoản và qua kiểm tra căn cứ; không qua thì hệ thống trích nguyên văn hoặc từ chối. Câu cần phán đoán được chuyển chuyên gia.</p>
    ${groups.map(([g, qs]) => `<p class="muted small" style="margin:.75rem 0 .25rem">${esc(g)}</p><div class="chips">${qs.map((q) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>`).join('')}
    <div id="chat"></div><div id="pending"></div>
    <form id="ask" class="bar ask-bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="q">Câu hỏi (Enter để gửi)</label><input class="cds--text-input" id="q" name="q" autocomplete="off" placeholder="Ví dụ: hóa đơn số 340 có vấn đề gì?"></div>${button('Hỏi', 'primary', 'type="submit"')}
    ${history.length ? button('Xóa lịch sử', 'ghost', 'id="clear"') : ''}</form>`;
  const chat = $('#chat');
  const draw = () => { chat.innerHTML = history.join(''); };
  draw();
  let busy = false;
  const ask = async (q) => {
    if (busy) return;
    busy = true;
    history.push(`<div class="answer user"><strong>${esc(q)}</strong></div>`); draw();
    const t0 = Date.now();
    const policy = !/hóa đơn số|\d{3,}|tháng \d|hạn nộp|người bán|bao nhiêu thuế/i.test(q);
    const tick = () => {
      const s = Math.round((Date.now() - t0) / 1000);
      $('#pending').innerHTML = loading(policy && s > 2 ? `Đang tìm điều khoản và để mô hình trên máy đọc (${s} giây); câu trả lời được kiểm tra căn cứ trước khi hiện` : `Đang trả lời (${s} giây)`);
    };
    tick();
    const timer = setInterval(tick, 1000);
    try {
      const a = await post(`/api/workspaces/${state.ws}/ask`, { question: q });
      const rag = a.facts?.find((f) => f && f.passages);
      const cites = rag
        ? rag.sentences.flatMap((s) => s.citations).filter((c, i, arr) => arr.findIndex((x) => x.path === c.path) === i)
          .map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.doc_num)}</a>: ${esc(c.path.split(' > ').slice(1).join(' > '))}`)
        : a.citations.map(esc);
      history.push(`<div class="answer"><div class="chips">${tag(a.branch)}${rag ? tag(rag.mode) : ''}<span class="muted small">${Math.round((Date.now() - t0) / 1000)} giây</span></div><p style="margin:.5rem 0 0">${esc(a.text)}</p>
        ${cites.length ? `<div class="cite">Căn cứ: ${cites.join('; ')}</div>` : ''}
        ${rag?.dropped?.length ? `<div class="cite">${rag.dropped.length} câu của mô hình bị loại vì không có căn cứ.</div>` : ''}</div>`);
    } catch (err) { history.push(notice('error', 'Không trả lời được', err.message)); }
    clearInterval(timer);
    $('#pending').innerHTML = '';
    busy = false;
    save();
    draw();
    $('#q').focus();
  };
  $('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); if (q) { $('#q').value = ''; ask(q); } };
  app().querySelectorAll('[data-q]').forEach((b) => { b.onclick = () => ask(b.dataset.q); });
  if ($('#clear')) $('#clear').onclick = () => { history = []; save(); rerender(); };
  $('#q').focus();
}

export async function pageLaw() {
  const st = await api('/api/law/status');
  const s = st.stats;
  const params = hashParams();
  const doc = params.get('doc');
  if (doc) {
    const d = await api(`/api/law/docs/${encodeURIComponent(doc)}`);
    app().innerHTML = `<div class="bar">${button('Quay lại kho luật', 'ghost', 'data-go="#/luat"')}</div><h1 class="page">${esc(d.doc.doc_type)} ${esc(d.doc.doc_num)}</h1>
      <p class="lead">${esc(d.doc.title)}</p><dl class="kv"><dt>Ban hành</dt><dd>${dmy(d.doc.issue_date)}</dd><dt>Hiệu lực</dt><dd>${dmy(d.doc.eff_from) || 'không ghi'}${d.doc.eff_to ? ' đến ' + dmy(d.doc.eff_to) : ''}</dd>
      <dt>Tình trạng</dt><dd>${esc(d.doc.status_name || 'không ghi')}</dd><dt>Nguồn</dt><dd><a href="${esc(d.doc.url)}" target="_blank" rel="noopener">Cơ sở dữ liệu quốc gia về pháp luật</a></dd>
      <dt>Chuyên gia duyệt</dt><dd>${esc(d.doc.review_status)}</dd><dt>Dùng để trả lời</dt><dd>${d.doc.indexed ? 'Có' : 'Không (chỉ lưu để đối chiếu)'}</dd></dl>
      ${d.ended ? notice('warning', `Hết hiệu lực từ ${dmy(d.ended.eff_to)} theo ${d.ended.by_path || d.ended.by_doc_num}`,
        `${d.ended.path ? d.ended.path + '. ' : ''}Căn cứ nguyên văn: "${d.ended.quote}"${d.ended.exception ? ` Ngoại lệ: ${d.ended.exception}` : ''}`) : ''}
      ${d.validity_notes.length ? `<div class="panel"><h3>Ghi chú hiệu lực cần chuyên gia xem</h3><ul>${d.validity_notes.map((n) => `<li>${esc(n.kind === 'PARTIAL' ? 'Hết hiệu lực một phần' : 'Được nhắc là văn bản sửa đổi, vẫn giữ hiệu lực')} theo ${esc(n.by_doc_num)}: <span class="muted">${esc(n.quote.slice(0, 300))}</span></li>`).join('')}</ul></div>` : ''}
      ${d.provisions.length ? d.provisions.map((p) => `<div class="law-prov l${p.level}">${esc(p.text)}</div>`).join('') : notice('warning', 'Văn bản chưa có toàn văn trong kho', 'Trang nguồn chỉ có tệp đính kèm.')}`;
    return;
  }
  app().innerHTML = `
    ${sonHeader('Kho luật', 'Kho luật thuế', 'CĂN CỨ PHÁP LÝ')}
    <p class="lead" style="margin-top:10px">Văn bản thuế lấy tự động từ Cơ sở dữ liệu quốc gia về pháp luật (vbpl.vn) của Bộ Tư pháp, theo từng điều, khoản, điểm, có ngày hiệu lực. Chỉ đọc trang được phép theo robots.txt, tối đa 1 yêu cầu mỗi 2 giây.</p>
    <div class="kpis"><div class="kpi"><span class="label">Văn bản</span><span class="value">${s ? s.documents : 0}</span><span class="sub">${s ? `${s.in_force} còn hiệu lực` : ''}</span></div>
    <div class="kpi"><span class="label">Điều khoản</span><span class="value">${s ? s.provisions.toLocaleString('vi-VN') : 0}</span><span class="sub">${s ? `${s.chunks.toLocaleString('vi-VN')} đoạn tìm kiếm` : ''}</span></div>
    <div class="kpi"><span class="label">Lần đồng bộ gần nhất</span><span class="value" style="font-size:1.25rem">${s?.last_snapshot?.created_at ? dmy(s.last_snapshot.created_at) : 'chưa có'}</span>
    <span class="sub">${st.job.running ? `đang chạy${st.job.external ? ' từ dòng lệnh' : ''}: ${st.job.done} văn bản, ${esc(st.job.last)}` : ''}</span></div>
    <div class="kpi"><span class="label">Hết hiệu lực theo văn bản thay thế</span><span class="value">${s ? s.ended_by_later_act ?? 0 : 0}</span><span class="sub">đọc từ điều khoản hiệu lực thi hành của văn bản mới</span></div></div>
    <h2 class="section">Tìm trong kho</h2><form id="lsearch" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="lq">Nội dung</label><input class="cds--text-input" id="lq" placeholder="Ví dụ: thời hạn nộp hồ sơ khai thuế theo quý"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="lasof">Ngày áp dụng</label><input class="cds--text-input" id="lasof" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
    ${button('Tìm', 'primary', 'type="submit"')}</form><div id="lres"></div>
    <h2 class="section">Văn bản</h2><div id="ldocs">${loading('Đang tải danh sách')}</div><details class="law-management"><summary>Đồng bộ và lịch sử kho luật</summary>    <div class="bar">${button(st.job.running ? 'Đang đồng bộ' : 'Đồng bộ kho luật', 'primary', `id="sync" ${st.job.running ? 'disabled' : ''}`)}${button('Chỉ văn bản lõi', 'tertiary', `id="sync-core" ${st.job.running ? 'disabled' : ''}`)}
    <span>${st.job.error ? notice('error', 'Lỗi đồng bộ', st.job.error) : ''}</span></div>
    <div id="alerts"></div>
    <h2 class="section">Thay đổi gần đây</h2>${table(['Lần', 'Loại', 'Văn bản', 'Chi tiết'], (st.changes || []).slice(0, 15).map((c) => `<tr><td>${c.snapshot_id}</td><td>${esc(c.kind)}</td><td>${esc(c.doc_num || '')}</td><td>${esc(c.detail)}</td></tr>`), 'Chưa có thay đổi.')}
</details>`;
  const startSync = async (q) => {
    try { await post(`/api/law/sync${q}`); rerender(); } catch (err) { $('#lres').innerHTML = notice('error', 'Chưa đồng bộ được', err.message); }
  };
  $('#sync').onclick = () => startSync('');
  $('#sync-core').onclick = () => startSync('?core_only=true');
  lawAlerts($('#alerts')).catch(() => {});
  if (st.job.running) { const timer = setTimeout(() => { if (!hashParams().get('doc')) rerender(); }, 5000); onPageLeave(() => clearTimeout(timer)); }
  $('#lsearch').onsubmit = async (e) => {
    e.preventDefault();
    const q = $('#lq').value.trim();
    if (!q) return;
    $('#lres').innerHTML = loading('Đang tìm');
    try {
      const rows = await api(`/api/law/search?q=${encodeURIComponent(q)}&as_of=${$('#lasof').value}`);
      $('#lres').innerHTML = rows.length ? rows.map((r) => `<div class="panel"><h3><a href="#/luat?doc=${esc(r.doc_id)}">${esc(r.path)}</a></h3>
        <div class="muted small">${esc(r.status || 'không ghi tình trạng')}, hiệu lực từ ${dmy(r.eff_from) || 'không ghi'}</div><p>${esc(r.text.slice(0, 900))}${r.text.length > 900 ? '...' : ''}</p></div>`).join('')
        : '<div class="empty">Không tìm thấy điều khoản phù hợp tại ngày này.</div>';
    } catch (err) { $('#lres').innerHTML = notice('error', 'Không tìm được', err.message); }
  };
  try {
    const docs = await api('/api/law/docs');
    $('#ldocs').innerHTML = table(['Văn bản', 'Ban hành', 'Hiệu lực', 'Tình trạng', { label: 'Điều khoản', num: true }], docs.map((d) => `<tr class="clickable" data-go="#/luat?doc=${esc(d.doc_id)}">
      <td><span class="cell-title">${esc(d.doc_type)} ${esc(d.doc_num)}</span><div class="muted small">${esc((d.title || '').slice(0, 140))}</div></td><td>${dmy(d.issue_date)}</td><td>${dmy(d.eff_from)}</td>
      <td>${d.ended_on ? `Hết hiệu lực từ ${dmy(d.ended_on)} theo ${esc(d.ended_by)}` : esc(d.status_name || '')}${d.structure === 'none' ? '<div class="muted small">chưa có toàn văn</div>' : ''}${d.indexed ? '' : '<div class="muted small">không dùng để trả lời</div>'}</td><td class="num">${d.n_provisions}</td></tr>`), 'Kho trống. Bấm Đồng bộ kho luật.');
  } catch { $('#ldocs').innerHTML = '<div class="empty">Kho trống. Bấm Đồng bộ kho luật.</div>'; }
}

export async function pageSettings() {
  if (needWorkspace()) return;
  const pack = await api(`/api/workspaces/${state.ws}/pack`);
  const save = async (next, msgEl) => {
    try { await put(`/api/workspaces/${state.ws}/pack`, next); msgEl.innerHTML = notice('success', 'Đã lưu'); setTimeout(rerender, 600); }
    catch (err) { msgEl.innerHTML = notice('error', 'Không lưu được', err.message); }
  };
  app().innerHTML = `<h1 class="page">Cài đặt của doanh nghiệp</h1><p class="lead">Phần thích ứng do doanh nghiệp giữ. Ngưỡng chỉ được chặt hơn mặc định; chính sách nội bộ chỉ thêm cờ, không làm nhẹ kết quả luật; danh sách tham chiếu phải ghi ngày.</p>
    <h2 class="section">Mẫu sao kê ngân hàng</h2>${table(['Tên mẫu', 'Cột ngày', 'Cột ghi nợ', 'Cột ghi có', 'Phân cách số'], (pack.bank_formats || []).map((f) => `<tr><td>${esc(f.name)}</td>
      <td class="mono">${esc(f.columns.date)}</td><td class="mono">${esc(f.columns.debit)}</td><td class="mono">${esc(f.columns.credit || '')}</td><td class="mono">nghìn "${esc(f.thousands)}", thập phân "${esc(f.decimal)}"</td></tr>`), 'Chưa có mẫu. Nạp sao kê rồi dùng Nhận dạng cột.')}
    <h2 class="section">Ngưỡng</h2><form id="th"><div class="form-grid">
      ${field({ key: 'match_days_after_invoice', label: 'Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán (không quá 90)', example: '90' }, pack.thresholds?.match_days_after_invoice ?? '')}
      ${field({ key: 'non_cash_threshold_override', label: 'Ngưỡng nội bộ thấp hơn ngưỡng luật (đồng)', example: 'để trống để dùng ngưỡng luật' }, pack.thresholds?.non_cash_threshold_override ?? '')}</div>
      <div class="bar">${button('Lưu ngưỡng', 'primary', 'type="submit"')}<span id="thmsg"></span></div></form>
    <h2 class="section">Chính sách nội bộ</h2>${table(['Mã', 'Cờ', 'Điều kiện'], (pack.policies || []).map((p) => `<tr><td>${esc(p.id)}</td><td>${esc(p.flag)}</td>
      <td>${p.min_gross ? 'từ ' + money(p.min_gross) : ''} ${(p.description_contains || []).map(esc).join(', ')}</td></tr>`), 'Chưa có.')}
    <form id="pol" style="margin-top:1rem"><div class="form-grid">${field({ key: 'id', label: 'Mã chính sách', required: true, example: 'TIEP_KHACH' })}${field({ key: 'flag', label: 'Nội dung cờ', required: true, example: 'Cần giấy đề nghị thanh toán' })}
      ${field({ key: 'min_gross', label: 'Áp dụng từ số tiền (đồng)', example: '2000000' })}${field({ key: 'description_contains', label: 'Tên hàng có chứa', example: 'tiếp khách' })}</div>
      <div class="bar">${button('Thêm chính sách', 'secondary', 'type="submit"')}<span id="polmsg"></span></div></form>
    <h2 class="section">Danh sách doanh nghiệp rủi ro</h2>${table(['Tên danh sách', 'Ngày', { label: 'Số mã số thuế', num: true }, 'Nguồn'], (pack.reference_lists || []).map((r) => `<tr><td>${esc(r.name)}</td><td>${dmy(r.as_of)}</td>
      <td class="num">${r.tax_ids.length}</td><td>${esc(r.source || '')}</td></tr>`), 'Chưa có.')}
    <form id="ref" style="margin-top:1rem"><div class="form-grid">${field({ key: 'name', label: 'Tên danh sách', required: true, example: 'Danh sách theo công văn số ...' })}
      <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="ref-date">Ngày của danh sách</label><input class="cds--text-input" id="ref-date" name="as_of" type="date" required></div>
      ${field({ key: 'source', label: 'Nguồn', example: 'Công văn số ... của Cục Thuế' })}
      <div class="cds--form-item"><label class="cds--label" for="ref-ids">Mã số thuế, mỗi dòng một mã</label><textarea class="cds--text-area" id="ref-ids" name="tax_ids" rows="4"></textarea></div></div>
      <div class="bar">${button('Thêm danh sách', 'secondary', 'type="submit"')}<span id="refmsg"></span></div></form><div id="riskimp"></div>`;
  riskImport($('#riskimp'));
  $('#th').onsubmit = (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const th = { ...pack.thresholds };
    if (f.match_days_after_invoice) th.match_days_after_invoice = Number(f.match_days_after_invoice); else delete th.match_days_after_invoice;
    if (f.non_cash_threshold_override) th.non_cash_threshold_override = Number(f.non_cash_threshold_override); else delete th.non_cash_threshold_override;
    save({ ...pack, thresholds: th }, $('#thmsg'));
  };
  $('#pol').onsubmit = (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const p = { id: f.id, flag: f.flag };
    if (f.min_gross) p.min_gross = Number(f.min_gross);
    if (f.description_contains) p.description_contains = f.description_contains.split(';').map((x) => x.trim()).filter(Boolean);
    save({ ...pack, policies: [...(pack.policies || []).filter((x) => x.id !== p.id), p] }, $('#polmsg'));
  };
  $('#ref').onsubmit = (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const ids = f.tax_ids.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
    save({ ...pack, reference_lists: [...(pack.reference_lists || []), { name: f.name, as_of: f.as_of, source: f.source, tax_ids: ids }] }, $('#refmsg'));
  };
}
