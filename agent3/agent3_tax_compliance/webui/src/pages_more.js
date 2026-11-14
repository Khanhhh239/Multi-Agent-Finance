// Invoices, bank, calendar, legal corpus and enterprise settings.
import { $, api, app, balance, button, compareDecimal, computeReportStats, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loading, money, needWorkspace, notice, post, put, sonHeader,
  onPageLeave, state, table, tag } from './core.js';
import { bindDialog } from './interactions.js';
import { bankProposals, lawAlerts, riskImport } from './pages_ai.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));

function openInvoiceDrawer(inv, stats, rep) {
  const m = stats.matchedMap.get(inv.key);
  const txn = m ? rep.transactions.find((t) => m.txn_ids.includes(t.txn_id)) : null;
  const its = (stats.riskByInvoice.get(inv.key) || []).filter((x) => x.status !== 'INFO');
  const partnerName = inv.role === 'SALE' ? (inv.buyer_name || 'Khách hàng') : (inv.seller_name || 'Nhà cung cấp');
  const partnerTax = inv.role === 'SALE' ? (inv.buyer_tax_id || '—') : (inv.seller_tax_id || '—');

  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-labelledby="inv-drawer-title">
    <div class="drawer-top-bar">
      <div class="drawer-header-content">
        <div class="drawer-subhead">
          <span class="role-badge ${inv.role === 'SALE' ? 'sale' : 'purchase'}">${inv.role === 'SALE' ? 'Hóa đơn bán ra' : 'Hóa đơn mua vào'}</span>
          ${inv.duplicate_of ? '<span class="dup-pill">Bản trùng XML</span>' : ''}
          <span class="amount-badge">Tổng TT: <strong>${money(inv.gross)}</strong></span>
        </div>
        <h2 id="inv-drawer-title">Hóa đơn ${esc(invLabel(inv))}</h2>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close drawer-close-btn" id="close" type="button" aria-label="Đóng ngăn chi tiết">Đóng</button>
    </div>

    <div class="dossier-grid" style="margin-top:16px">
      <div class="dossier-card">
        <h3 class="dossier-card-title">Thông tin chứng từ XML</h3>
        <dl class="kv">
          <dt>Ký hiệu / Số</dt><dd><strong>${esc(invLabel(inv))}</strong></dd>
          <dt>Ngày lập</dt><dd>${dmy(inv.issue_date) || '—'}</dd>
          <dt>${inv.role === 'SALE' ? 'Người mua' : 'Người bán'}</dt><dd><strong>${esc(partnerName)}</strong><div class="muted small">MST: ${esc(partnerTax)}</div></dd>
          <dt>Tổng thanh toán</dt><dd><strong>${money(inv.gross)}</strong></dd>
          <dt>Thuế GTGT</dt><dd><strong style="color:var(--a3-primary)">${money(inv.vat)}</strong></dd>
          <dt>Chữ ký số & XML</dt><dd>${inv.guard_errors?.length ? `Lỗi XML (${inv.guard_errors.join(', ')})` : (inv.signed ? 'Chữ ký số hợp lệ' : 'Chưa ký số')}</dd>
          <dt>Tệp gốc</dt><dd class="mono small" style="word-break:break-all">${esc(inv.file || '—')}</dd>
        </dl>
      </div>

      <div class="dossier-card">
        <h3 class="dossier-card-title">Đối chiếu thanh toán ngân hàng</h3>
        ${inv.role === 'SALE' ? '<p class="muted small">Hóa đơn bán ra không bắt buộc ghép ủy nhiệm chi khấu trừ đầu vào.</p>' : (m ? `
          <div class="match-badge ${m.status === 'MATCHED' ? 'match-ok' : 'match-warn'}">
            ${m.status === 'MATCHED' ? 'Đã ghép giao dịch ngân hàng' : 'Khớp mơ hồ / Cần kiểm tra'}
          </div>
          <p class="small" style="margin:8px 0 12px">${esc(m.note || '')}</p>
          ${txn ? `<dl class="kv"><dt>Ngày hạch toán</dt><dd>${dmy(txn.booked)}</dd><dt>Số tiền</dt><dd><strong>${money(txn.amount)}</strong></dd><dt>Nội dung</dt><dd>${esc(txn.description || '')}</dd></dl>` : ''}
        ` : `
          <div class="match-badge match-empty">Chưa ghép giao dịch ngân hàng</div>
          <p class="muted small" style="margin-top:8px">Chưa tìm thấy giao dịch chi tiền khớp số tiền và tên nhà cung cấp trong sao kê đã nạp.</p>
        `)}
      </div>
    </div>

    ${(inv.descriptions || []).length ? `
      <h3 class="section">Nội dung hàng hóa / dịch vụ</h3>
      <ul style="font-size:13px;line-height:1.6;margin:0 0 16px 20px;padding:0">
        ${inv.descriptions.slice(0, 15).map((d) => `<li>${esc(d)}</li>`).join('')}
      </ul>
    ` : ''}

    <h3 class="section">Kết quả rà soát rủi ro (${its.length} vấn đề)</h3>
    ${its.length ? `
      <div style="display:grid;gap:10px;margin-bottom:16px">
        ${its.map((x) => `<div class="panel" style="margin:0">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px">
            ${tag(x.status)}
            <span class="mono small muted">${esc(x.code)}</span>
          </div>
          <div style="font-weight:600;margin-bottom:4px">${esc(x.title)}</div>
          <div class="muted small">${esc(x.detail)}</div>
        </div>`).join('')}
      </div>
      <div class="bar">
        <a class="cds--btn cds--btn--primary cds--btn--md" href="#/viec?open=${encodeURIComponent(inv.key)}">Mở tại Việc cần xử lý để phê duyệt →</a>
      </div>
    ` : `<p class="muted small">Hóa đơn này hiện không có cảnh báo rủi ro.</p>`}
  </aside>`;

  bindDialog();
}

export async function pageInvoices() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Hóa đơn</h1>${notice('info', 'Chưa phân tích')}`; return; }

  const stats = computeReportStats(rep);
  const matched = stats.matchedMap;
  const risk = stats.riskByInvoice;
  const months = [...new Set(rep.invoices.filter((i) => i.issue_date).map((i) => i.issue_date.slice(0, 7)))].sort();
  const worst = (i) => stats.invoiceBucket(i);

  const PAGE = 50;
  const viewKey = `agent3.invoices.${state.ws}.${state.platform?.profile_revision}`;
  let savedView = {}; try { savedView = JSON.parse(sessionStorage.getItem(viewKey) || '{}'); } catch {}
  let page = savedView.page || 0;
  let tabFilter = savedView.tabFilter || 'all';

  const purchaseInvs = stats.purchaseInvs;
  const saleInvs = stats.saleInvs;
  const purchaseGross = stats.purchaseGross;
  const purchaseVat = stats.purchaseVat;
  const saleGross = stats.saleGross;
  const saleVat = stats.saleVat;
  const atRiskCount = stats.atRiskInvoices;
  const reviewCount = stats.reviewInvoices;
  const unpaidCount = stats.unpaidCount;
  const dupCount = stats.duplicateInvs.length;

  const nonDupInvoices = rep.invoices.filter((i) => !i.duplicate_of);
  const signedCount = nonDupInvoices.filter((i) => i.signed).length;
  const signedPct = nonDupInvoices.length > 0 ? Math.round((signedCount / nonDupInvoices.length) * 100) : 100;

  // Scenario with review matches #/so-lieu (output_vat - no_alert_vat - review_vat)
  const netVat = stats.scenarioWithReview;

  app().innerHTML = `
    ${sonHeader('Hóa đơn', 'Hóa đơn', 'QUẢN LÝ CHỨNG TỪ', `<span class="ctx-chip chip-count">${nonDupInvoices.length.toLocaleString('vi-VN')} hóa đơn hợp lệ${dupCount ? ` · ${dupCount} bản trùng` : ''}</span>`, 'chung-tu')}

    <div class="inv-balance-hub">
      <div class="hub-main-grid">
        <div class="hub-card hub-card-purchase">
          <div class="hub-card-header">
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN MUA VÀO</span>
              <span class="hub-action-sub">Đã loại trừ ${dupCount} bản trùng XML</span>
            </div>
            <span class="hub-count-tag count-purchase">${purchaseInvs.length.toLocaleString('vi-VN')} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng thanh toán:</span>
              <span class="hub-amount font-num">${money(purchaseGross)}</span>
            </div>
            <div class="hub-vat-pill vat-purchase">
              <span class="vat-pill-label">Tổng thuế GTGT mua vào:</span>
              <span class="vat-pill-val font-num"><strong>${money(purchaseVat)}</strong></span>
            </div>
          </div>
        </div>

        <div class="hub-card hub-card-center">
          <div class="center-balance-head">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span class="balance-title">PHÂN TÁCH THUẾ GTGT ĐẦU VÀO & CÂN ĐỐI</span>
              <a href="#/so-lieu" class="small" style="font-weight:600;text-decoration:none">Bảng tính thuế →</a>
            </div>
            <span class="balance-sub">Khớp 100% với trang Số liệu thuế GTGT</span>
          </div>

          <div class="a3-vat-breakdown">
            <div class="a3-vat-row"><span>Đầu vào chưa có cảnh báo:</span><strong class="font-num">${money(stats.noAlertVat)}</strong></div>
            <div class="a3-vat-row"><span>Đầu vào chờ xem xét (${reviewCount} HĐ):</span><strong class="font-num">${money(stats.reviewVat)}</strong></div>
            <div class="a3-vat-row"><span>Có nguy cơ / Không khai (${atRiskCount} HĐ):</span><strong class="font-num" style="color:var(--a3-danger)">${money(Number(stats.atRiskVat) + stats.notClaimedVat)}</strong></div>
          </div>

          <div class="balance-result-box ${netVat <= 0 ? 'result-credit' : 'result-payable'}">
            <div class="result-info">
              <div class="result-name">${netVat <= 0 ? 'Đầu vào vượt đầu ra (kể cả chờ duyệt):' : 'Đầu ra vượt đầu vào (kể cả chờ duyệt):'}</div>
              <div class="result-value font-num">${money(Math.abs(netVat))}</div>
            </div>
          </div>
        </div>

        <div class="hub-card hub-card-sale">
          <div class="hub-card-header">
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN BÁN RA</span>
              <span class="hub-action-sub">Phát sinh nghĩa vụ thuế đầu ra</span>
            </div>
            <span class="hub-count-tag count-sale">${saleInvs.length.toLocaleString('vi-VN')} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng thanh toán:</span>
              <span class="hub-amount font-num">${money(saleGross)}</span>
            </div>
            <div class="hub-vat-pill vat-sale">
              <span class="vat-pill-label">Tổng thuế GTGT bán ra:</span>
              <span class="vat-pill-val font-num"><strong>${money(saleVat)}</strong></span>
            </div>
          </div>
        </div>
      </div>

      <div class="hub-footer-strip">
        <div class="strip-left">
          <span class="strip-label">Lọc nhanh rủi ro:</span>
          <button type="button" class="audit-badge audit-risk clickable-badge" data-quick-st="AT_RISK">
            <strong>${atRiskCount.toLocaleString('vi-VN')}</strong> HĐ có nguy cơ (${money(stats.atRiskVat)})
          </button>
          <button type="button" class="audit-badge audit-review clickable-badge" data-quick-st="REVIEW">
            <strong>${reviewCount.toLocaleString('vi-VN')}</strong> HĐ cần xem xét (${money(stats.reviewVat)})
          </button>
          <button type="button" class="audit-badge audit-bank clickable-badge" data-quick-tab="UNPAID">
            <strong>${unpaidCount.toLocaleString('vi-VN')}</strong> HĐ mua vào chưa ghép sao kê
          </button>
        </div>
        <div class="strip-right">
          <span class="audit-badge audit-signed">
            Chữ ký số hợp lệ: <strong>${signedPct}%</strong> (${signedCount.toLocaleString('vi-VN')}/${nonDupInvoices.length.toLocaleString('vi-VN')})
          </span>
        </div>
      </div>
    </div>

    <div class="inv-segmented-pills">
      ${[
        ['all', 'Tất cả', rep.invoices.length, 'pill-tab-all'],
        ['PURCHASE', 'Mua vào', purchaseInvs.length, 'pill-tab-purchase'],
        ['SALE', 'Bán ra', saleInvs.length, 'pill-tab-sale'],
        ['RISK', 'Có cảnh báo', atRiskCount + reviewCount, 'pill-tab-risk'],
        ['UNPAID', 'Chưa ghép sao kê', unpaidCount, 'pill-tab-bank'],
      ].map(([k, l, n, cls]) => `<button type="button" class="inv-filter-pill ${cls} ${k === tabFilter ? 'active' : ''}" data-tab="${k}">
        <span class="pill-name">${esc(l)}</span>
        <span class="pill-count">${n.toLocaleString('vi-VN')}</span>
      </button>`).join('')}
    </div>

    <div class="inv-toolbar">
      <div class="inv-search-wrap">
        <input class="cds--text-input inv-search-input" id="iq" style="padding-left:12px !important" placeholder="Tìm theo số hóa đơn, đối tác, MST hoặc nội dung hàng hóa..." aria-label="Tìm hóa đơn">
        <button type="button" class="inv-search-clear" id="iq-clear" title="Xóa tìm kiếm" hidden aria-label="Xóa tìm kiếm">✕</button>
      </div>

      <select class="cds--select-input inv-filter-select" id="st" aria-label="Tình trạng">
        <option value="">Mọi tình trạng</option>
        <option value="AT_RISK">Có nguy cơ (${atRiskCount})</option>
        <option value="REVIEW">Cần xem xét (${reviewCount})</option>
        <option value="OK">Không cảnh báo</option>
        <option value="UNPAID">Chưa ghép sao kê (${unpaidCount})</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="mon" aria-label="Tháng">
        <option value="">Mọi kỳ tháng</option>
        ${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}
      </select>

      ${button('Đặt lại', 'ghost', 'id="reset-invoices" class="cds--btn--sm btn-inv-reset"')}
      <a class="cds--btn cds--btn--ghost cds--btn--sm btn-inv-export" href="/api/workspaces/${esc(state.ws)}/export/hoa-don.xlsx">
        <span>Xuất Excel</span>
      </a>
      <span class="muted small inv-counter" id="icount" role="status"></span>
    </div>

    <div id="ilist"></div>`;

  let sort = savedView.sort || ['issue_date', -1];
  const keyOf = { issue_date: (i) => i.issue_date || '', gross: (i) => i.gross || '0', vat: (i) => i.vat || '0', seller: (i) => (i.role === 'SALE' ? i.buyer_name : i.seller_name) || '' };

  const isUnpaid = (i) => {
    if (i.role !== 'PURCHASE' || i.duplicate_of) return false;
    const m = matched.get(i.key);
    return !m || m.status !== 'MATCHED';
  };

  const paint = () => {
    const st = $('#st').value; const mon = $('#mon').value; const q = $('#iq').value.trim().toLowerCase();
    const view = rep.invoices.filter((i) => {
      if (tabFilter === 'PURCHASE' && (i.role !== 'PURCHASE' || i.duplicate_of)) return false;
      if (tabFilter === 'SALE' && (i.role !== 'SALE' || i.duplicate_of)) return false;
      if (tabFilter === 'RISK' && !['AT_RISK', 'REVIEW'].includes(worst(i))) return false;
      if (tabFilter === 'UNPAID' && !isUnpaid(i)) return false;

      if (mon && !(i.issue_date || '').startsWith(mon)) return false;
      if (st) {
        if (st === 'UNPAID' && !isUnpaid(i)) return false;
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

    const pageSlice = view.slice(page * PAGE, page * PAGE + PAGE);

    $('#ilist').innerHTML = view.length ? `<div class="table-wrap inv-table-wrap"><table class="cds--data-table cds--data-table--md inv-data-table">
      <thead>
        <tr>
          <th style="min-width:155px">Hóa đơn & Ký hiệu</th>
          ${th('issue_date', 'Ngày lập', false, 'th-date')}
          ${th('seller', 'Đối tác / MST', false, 'th-partner')}
          ${th('gross', 'Tổng thanh toán', true, 'th-gross')}
          ${th('vat', 'Thuế GTGT', true, 'th-vat')}
          <th style="min-width:105px">Toàn vẹn XML</th>
          <th style="min-width:110px">Sao kê NH</th>
          <th style="min-width:140px">Trạng thái rà soát</th>
        </tr>
      </thead>
      <tbody>
        ${pageSlice.map((i, rowIdx) => {
          const m = matched.get(i.key);
          const its = (risk.get(i.key) || []).filter((x) => x.status !== 'INFO');
          const bStatus = worst(i);
          const integrity = i.guard_errors.length
            ? `<span class="integrity-badge badge-err">Lỗi XML (${i.guard_errors.length})</span>`
            : (i.signed ? `<span class="integrity-badge badge-ok">Hợp lệ</span>` : `<span class="integrity-badge badge-none">Không ký</span>`);

          const payStatus = i.role === 'SALE'
            ? '<span class="muted small">—</span>'
            : (m ? (m.status === 'MATCHED'
                ? `<span class="pay-badge pay-ok">Đã ghép</span>`
                : `<span class="pay-badge pay-ambig">Mơ hồ</span>`)
              : `<span class="pay-badge pay-none">Chưa ghép</span>`);

          const partnerName = i.role === 'SALE' ? (i.buyer_name || 'Khách hàng') : (i.seller_name || 'Nhà cung cấp');
          const partnerTax = i.role === 'SALE' ? (i.buyer_tax_id || '') : (i.seller_tax_id || '');

          return `<tr class="clickable ${its.length ? 'row-has-risk' : ''}" tabindex="0" data-inv-idx="${rowIdx}" title="Bấm để xem chi tiết hóa đơn">
            <td>
              <div class="inv-code-pill ${i.role === 'SALE' ? 'pill-sale' : 'pill-purchase'}" title="${esc(invLabel(i))}">
                <span class="inv-code-text">${esc(invLabel(i))}</span>
                ${i.duplicate_of ? '<span class="dup-pill">Trùng</span>' : ''}
              </div>
              <div class="inv-role-sub">${i.role === 'SALE' ? '<span class="role-badge sale">Bán ra</span>' : '<span class="role-badge purchase">Mua vào</span>'}</div>
            </td>
            <td class="font-date">${dmy(i.issue_date)}</td>
            <td>
              <div class="partner-name" title="${esc(partnerName)}">${esc(partnerName)}</div>
              ${partnerTax ? `<div class="partner-tax mono">MST <code>${esc(partnerTax)}</code></div>` : ''}
            </td>
            <td class="num font-num"><strong>${money(i.gross)}</strong></td>
            <td class="num font-num vat-cell"><span class="vat-amount">${money(i.vat)}</span></td>
            <td>${integrity}</td>
            <td>${payStatus}</td>
            <td>
              <div class="chips">
                ${bStatus === 'NOT_CLAIMED' ? tag('INFO', 'Không kê khai') : (its.length ? its.map((x) => tag(x.status, x.title.length > 34 ? `${x.title.slice(0, 32)}…` : x.title)).join('') : `<span class="tag-ok-check">Không cảnh báo</span>`)}
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
        <div style="font-weight:600;font-size:15px;margin-bottom:4px">Không có hóa đơn nào khớp bộ lọc</div>
        <div class="muted small">Thử đặt lại bộ lọc hoặc điều chỉnh từ khóa tìm kiếm.</div>
      </div>`;

    if ($('#prev')) $('#prev').onclick = () => { page -= 1; paint(); };
    if ($('#next')) $('#next').onclick = () => { page += 1; paint(); };
    app().querySelectorAll('[data-inv-idx]').forEach((tr) => {
      const inv = pageSlice[Number(tr.dataset.invIdx)];
      tr.onclick = () => openInvoiceDrawer(inv, stats, rep);
      tr.onkeydown = (e) => { if (e.target === tr && ['Enter', ' '].includes(e.key)) { e.preventDefault(); tr.click(); } };
    });
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

  app().querySelectorAll('[data-quick-st]').forEach((btn) => {
    btn.onclick = () => {
      tabFilter = 'all';
      app().querySelectorAll('.inv-filter-pill').forEach((b) => b.classList.toggle('active', b.dataset.tab === 'all'));
      $('#st').value = btn.dataset.quickSt;
      page = 0;
      paint();
    };
  });

  app().querySelectorAll('[data-quick-tab]').forEach((btn) => {
    btn.onclick = () => {
      tabFilter = btn.dataset.quickTab;
      app().querySelectorAll('.inv-filter-pill').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabFilter));
      $('#st').value = '';
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
  const months = [...new Set(rep.transactions.filter((t) => t.booked).map((t) => t.booked.slice(0, 7)))].sort();
  const PAGE = 50;
  let page = 0;

  app().innerHTML = `
    ${sonHeader('Ngân hàng', 'Giao dịch ngân hàng', 'QUẢN LÝ CHỨNG TỪ', '', 'chung-tu')}
    <div id="props"></div>

    <div class="toolbar inv-toolbar">
      <div class="inv-search-wrap">
        <input class="cds--text-input inv-search-input" id="bq" style="padding-left:14px !important" placeholder="Tìm theo đối ứng, số tài khoản, nội dung chuyển khoản, số hóa đơn..." aria-label="Tìm giao dịch ngân hàng">
        <button type="button" class="inv-search-clear" id="bq-clear" hidden title="Xóa tìm kiếm">✕</button>
      </div>

      <select class="cds--select-input inv-filter-select" id="bdir" aria-label="Chiều giao dịch">
        <option value="">Mọi chiều (Thu & Chi)</option>
        <option value="OUT">Chi ra (Thanh toán)</option>
        <option value="IN">Thu vào</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="bmatch" aria-label="Trạng thái ghép hóa đơn">
        <option value="">Mọi trạng thái ghép</option>
        <option value="MATCHED">Đã ghép hóa đơn</option>
        <option value="AMBIGUOUS">Khớp mơ hồ</option>
        <option value="UNMATCHED">Chưa ghép</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="bmon" aria-label="Tháng giao dịch">
        <option value="">Mọi tháng</option>
        ${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}
      </select>

      ${button('Đặt lại', 'ghost', 'id="breset" class="cds--btn--sm btn-inv-reset"')}
      <span class="inv-counter" id="bcount" role="status"></span>
    </div>

    <div id="blist"></div>`;

  const paint = () => {
    const q = $('#bq').value.trim().toLowerCase();
    const dir = $('#bdir').value;
    const matchSt = $('#bmatch').value;
    const mon = $('#bmon').value;

    const view = rep.transactions.filter((t) => {
      if (dir && t.direction !== dir) return false;
      if (mon && !(t.booked || '').startsWith(mon)) return false;
      const m = usedBy.get(t.txn_id);
      if (matchSt === 'MATCHED' && (!m || m.status !== 'MATCHED')) return false;
      if (matchSt === 'AMBIGUOUS' && (!m || m.status === 'MATCHED')) return false;
      if (matchSt === 'UNMATCHED' && m) return false;
      if (q) {
        const invText = m ? m.invoice_keys.map((k) => invLabel(invoiceOf(k))).join(' ') : '';
        const haystack = `${t.counterparty_name || ''} ${t.counterparty_account || ''} ${t.description || ''} ${t.amount || ''} ${t.source || ''} ${invText}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    const pages = Math.max(1, Math.ceil(view.length / PAGE));
    page = Math.min(page, pages - 1);
    $('#bcount').textContent = `${view.length.toLocaleString('vi-VN')} / ${rep.transactions.length.toLocaleString('vi-VN')} giao dịch`;

    const slice = view.slice(page * PAGE, page * PAGE + PAGE);
    $('#blist').innerHTML = table(
      ['Ngày', 'Chiều', { label: 'Số tiền', num: true }, 'Đối ứng', 'Nội dung', 'Ghép với hóa đơn', 'Nguồn'],
      slice.map((t) => {
        const m = usedBy.get(t.txn_id);
        return `<tr><td>${dmy(t.booked)}</td><td>${t.direction === 'OUT' ? 'Chi' : 'Thu'}</td><td class="num"><strong>${money(t.amount)}</strong></td>
          <td>${esc(t.counterparty_name || '')}<div class="muted small mono">${esc(t.counterparty_account || '')}</div></td><td>${esc(t.description)}</td>
          <td>${m ? `${m.invoice_keys.map((k) => esc(invLabel(invoiceOf(k)))).join(', ')}<div class="muted small">${m.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}</div>` : '<span class="muted small">Chưa ghép</span>'}</td><td class="muted small">${esc(t.source)}</td></tr>`;
      }),
      'Không có giao dịch ngân hàng nào khớp bộ lọc.'
    ) + (view.length > PAGE ? `<div class="bar pager">
      ${button('Trang trước', 'ghost', `id="bprev" ${page === 0 ? 'disabled' : ''}`)}
      <span class="small">Trang <strong>${page + 1}</strong> / ${pages} (${view.length.toLocaleString('vi-VN')} giao dịch)</span>
      ${button('Trang sau', 'ghost', `id="bnext" ${page >= pages - 1 ? 'disabled' : ''}`)}
    </div>` : '');

    if ($('#bprev')) $('#bprev').onclick = () => { page -= 1; paint(); };
    if ($('#bnext')) $('#bnext').onclick = () => { page += 1; paint(); };
  };

  const bq = $('#bq');
  const bqClear = $('#bq-clear');
  bq.oninput = () => { bqClear.hidden = !bq.value; page = 0; paint(); };
  bqClear.onclick = () => { bq.value = ''; bqClear.hidden = true; page = 0; paint(); };
  ['bdir', 'bmatch', 'bmon'].forEach((id) => { $(`#${id}`).onchange = () => { page = 0; paint(); }; });
  $('#breset').onclick = () => {
    ['bq', 'bdir', 'bmatch', 'bmon'].forEach((id) => { $(`#${id}`).value = ''; });
    bqClear.hidden = true;
    page = 0;
    paint();
  };

  paint();
  bankProposals($('#props'));
}

export async function pageCalendar() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  app().innerHTML = `
    ${sonHeader('Lịch thuế', 'Lịch thuế', 'TỔNG HỢP & HỒ SƠ THUẾ', rep ? `<span class="ctx-chip chip-date">Tính tại ngày ${dmy(rep.meta.as_of)}</span>` : '', 'bao-cao')}
    ${table(['Kỳ thuế', 'Hạn nộp', 'Tình trạng', 'Căn cứ pháp lý'], (rep?.calendar || []).map((c) => `<tr><td><strong>${esc(c.period)}</strong></td><td>${dmy(c.due)}${c.moved_from ? `<div class="muted small">Dời từ ${dmy(c.moved_from)} do ngày nghỉ</div>` : ''}</td><td>${esc(c.status)}${c.open_items ? `<div><a href="#/viec" class="risk-text">còn ${c.open_items} việc chưa xử lý của kỳ này</a></div>` : ''}${c.extension ? `<div class="muted small">${esc(c.extension)}</div>` : ''}</td><td class="muted small">${esc(c.basis)}</td></tr>`), 'Chưa có dữ liệu.')}`;
}

export async function pageLaw() {
  const st = await api('/api/law/status');
  const s = st.stats;
  const params = hashParams();
  const doc = params.get('doc');
  if (doc) {
    const d = await api(`/api/law/docs/${encodeURIComponent(doc)}`);
    app().innerHTML = `<div class="bar">${button('← Quay lại kho luật', 'ghost', 'data-go="#/luat"')}</div><h1 class="page">${esc(d.doc.doc_type)} ${esc(d.doc.doc_num)}</h1>
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
    ${sonHeader('Kho luật', 'Kho luật thuế', 'TƯ VẤN & TRA CỨU LUẬT', `<span class="ctx-chip chip-count">${s ? s.documents : 0} văn bản</span>`, 'tu-van')}
    <div class="kpis" style="margin-top:14px"><div class="kpi"><span class="label">Văn bản pháp luật</span><span class="value">${s ? s.documents : 0}</span><span class="sub">${s ? `${s.in_force} còn hiệu lực` : ''}</span></div>
    <div class="kpi"><span class="label">Điều khoản chi tiết</span><span class="value">${s ? s.provisions.toLocaleString('vi-VN') : 0}</span><span class="sub">${s ? `${s.chunks.toLocaleString('vi-VN')} đoạn chỉ mục` : ''}</span></div>
    <div class="kpi"><span class="label">Đồng bộ gần nhất</span><span class="value" style="font-size:1.25rem">${s?.last_snapshot?.created_at ? dmy(s.last_snapshot.created_at) : 'chưa có'}</span>
    <span class="sub">${st.job.running ? `đang chạy: ${st.job.done} văn bản` : 'Nguồn: vbpl.vn'}</span></div>
    <div class="kpi"><span class="label">Văn bản hết hiệu lực</span><span class="value">${s ? s.ended_by_later_act ?? 0 : 0}</span><span class="sub">theo điều khoản thay thế</span></div></div>
    <h2 class="section">Tra cứu điều khoản</h2><form id="lsearch" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="lq">Từ khóa hoặc nội dung</label><input class="cds--text-input" id="lq" placeholder="Ví dụ: thời hạn nộp hồ sơ khai thuế theo quý"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="lasof">Ngày áp dụng</label><input class="cds--text-input" id="lasof" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
    ${button('Tìm kiếm', 'primary', 'type="submit"')}</form><div id="lres"></div>
    <h2 class="section">Danh mục văn bản</h2><div id="ldocs">${loading('Đang tải danh sách')}</div><details class="law-management"><summary>Đồng bộ và lịch sử kho luật</summary><div class="bar">${button(st.job.running ? 'Đang đồng bộ' : 'Đồng bộ kho luật', 'primary', `id="sync" ${st.job.running ? 'disabled' : ''}`)}${button('Chỉ văn bản lõi', 'tertiary', `id="sync-core" ${st.job.running ? 'disabled' : ''}`)}
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
