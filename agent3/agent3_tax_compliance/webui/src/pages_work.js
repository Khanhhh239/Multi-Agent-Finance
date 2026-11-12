const ICONS = {
  risk: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  penalty: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1zM2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>',
  review: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M11 8v6M8 11h6"/></svg>',
  opportunity: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  chart: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
  calendar: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
  bank: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="21" x2="21" y2="21"/><line x1="3" y1="10" x2="21" y2="10"/><polyline points="5 6 12 3 19 6"/><line x1="4" y1="10" x2="4" y2="21"/><line x1="20" y1="10" x2="20" y2="21"/><line x1="8" y1="14" x2="8" y2="17"/><line x1="12" y1="14" x2="12" y2="17"/><line x1="16" y1="14" x2="16" y2="17"/></svg>',
  dossier: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
  law: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'
};

// Overview, data intake and the review queue.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loadWorkspaces, loading, money, moneyShort, needWorkspace, notice, post, put,
  state, store, table, tag, decide, decisionContext, onPageLeave } from './core.js';
import { aiToolbar, explainBox } from './pages_ai.js';
import { pageWelcome } from './pages_config.js';
import { deadlineBanner, freshBanner, nextSteps, sellerWatch, toast } from './ux.js';
import { bindDialog, closeDialog } from './interactions.js';

const itemId = (it) => it.finding_id || `${it.code}|${it.invoice_keys.join(',')}`;
let reviewItems = [];
let reviewSnapshot = null;
let lastOpened = null;

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageOverview() {
  if (!state.ws) { await pageWelcome(); return; }
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const rep = await loadReport();
  const t = rep?.totals;
  const files = ws.files;
  const period = rep?.meta.period ? ` Dữ liệu từ ${dmy(rep.meta.period[0])} đến ${dmy(rep.meta.period[1])}.` : '';


  // Monetary aggregation lives in the backend; Number conversion is for SVG coordinates only.
  const byWeek = false;
  const bucketLabel = (key) => key === 'undated' ? 'Chưa rõ ngày' : `Tháng ${key.slice(5)}/${key.slice(0, 4)}`;
  const monthly = rep?.totals.series || [];
  const spark = (status) => {
    if (t?.missing_vat_invoices) return '';
    const v = monthly.map((e) => Math.abs(Number(e[status] || 0)));
    if (v.length < 2 || !v.some(Boolean)) return '';
    const W = 96; const H = 30; const max = Math.max(...v);
    const pts = v.map((x, i) => [2 + (i / (v.length - 1)) * (W - 8), H - 4 - (x / max) * (H - 10)]);
    const last = pts[pts.length - 1];
    const polyPts = pts.map((q) => q.map((n) => n.toFixed(1)).join(',')).join(' ');
    const areaPts = `2,${H} ${polyPts} ${last[0].toFixed(1)},${H}`;
    const gradId = `spark-g-${status.toLowerCase()}`;
    const colorMap = {
      at_risk: ['#ff8389', 'rgba(255, 131, 137, 0.28)', 'rgba(255, 131, 137, 0)'],
      review: ['#fcd34d', 'rgba(252, 211, 77, 0.28)', 'rgba(252, 211, 77, 0)'],
      opportunity: ['#2dd4bf', 'rgba(45, 212, 191, 0.28)', 'rgba(45, 212, 191, 0)']
    };
    const c = colorMap[status.toLowerCase()] || ['#60a5fa', 'rgba(96, 165, 250, 0.28)', 'rgba(96, 165, 250, 0)'];
    return `<svg class="spark spark-${status.toLowerCase()}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Diễn biến theo tháng, ${v.length} tháng">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${c[1]}"/>
          <stop offset="100%" stop-color="${c[2]}"/>
        </linearGradient>
      </defs>
      <polygon points="${areaPts}" fill="url(#${gradId})"/>
      <polyline points="${polyPts}" stroke="${c[0]}"/>
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.8" fill="${c[0]}"/>
    </svg>`;
  };
  const monthChart = () => {
    if (t?.missing_vat_invoices) return notice('info', 'Chưa đủ số thuế để vẽ biểu đồ', 'Một số hóa đơn thiếu số thuế; không thay giá trị thiếu bằng 0.');
    if (monthly.length < 2) return '';
    const total = (e) => Number(e.total || 0);
    const max = Math.max(...monthly.map(total), 1);
    const X = 118; const BW = 300; const ROW = 34;
    const rows = monthly.map((e, i) => {
      const y = 10 + i * ROW;
      const wr = (Math.abs(Number(e.AT_RISK)) / max) * BW; const wv = (Math.abs(Number(e.REVIEW)) / max) * BW;
      const parts = [Number(e.AT_RISK) ? `${moneyShort(e.AT_RISK) || money(e.AT_RISK)} có nguy cơ` : '', Number(e.REVIEW) ? `${moneyShort(e.REVIEW) || money(e.REVIEW)} cần xem xét` : ''].filter(Boolean);
      return `<text class="t-month" x="0" y="${y + 15}">${esc(bucketLabel(e.k))}</text>
        ${wr ? `<rect class="bar-risk" x="${X}" y="${y}" width="${wr.toFixed(1)}" height="20"/>` : ''}${wv ? `<rect class="bar-review" x="${(X + wr).toFixed(1)}" y="${y}" width="${wv.toFixed(1)}" height="20"/>` : ''}
        <text class="t-val" x="${(X + wr + wv + 10).toFixed(1)}" y="${y + 15}">${esc(parts.join(' · ') || 'không có việc')}</text>`;
    }).join('');
    return `<section class="tufte" aria-labelledby="tufte-h"><h2 class="section" id="tufte-h">${byWeek ? 'Thuế cần chú ý theo tuần lập hóa đơn' : 'Thuế cần chú ý theo tháng lập hóa đơn'}</h2>
      <svg class="tufte-svg" viewBox="0 0 700 ${monthly.length * ROW + 14}" role="img" aria-label="Thuế có nguy cơ và cần xem xét theo tháng">${rows}</svg></section>`;
  };

  app().innerHTML = `<span class="eyebrow">Trợ lý giám sát thuế GTGT</span>
    <h1 class="page">${esc(ws.name)}</h1>
    <div class="context-line">
      <span><strong>MST:</strong> ${esc(ws.tax_code)}</span>
      <span>${rep ? `Phân tích ngày ${dmy(rep.meta.as_of)}` : 'Chưa có kết quả phân tích'}</span>
      ${period ? `<span>${period.trim()}</span>` : ''}
    </div>
    ${ws.simulated ? '<p class="lead">Dữ liệu mô phỏng đối soát nội bộ, không phải doanh nghiệp thật.</p>' : ''}
    ${notice('warning', 'Kết quả rà soát theo quy tắc nháp', 'Chưa có chuyên gia thuế duyệt. Cảnh báo và ước tính không phải kết luận vi phạm hoặc số thuế phải nộp.')}
    ${(rep?.meta.data_warnings || []).map(w => notice('warning', w)).join('')}
    <div id="fresh"></div>
    <div id="watch"></div>
    ${deadlineBanner(rep)}

    <div class="kpis">
      <div class="kpi kpi-risk">
        <div class="kpi-head">
          <div class="kpi-title-wrap">
            <span class="kpi-badge badge-risk">${ICONS.risk}</span>
            <span class="label">Thuế đầu vào có nguy cơ bị loại</span>
          </div>
          ${spark('AT_RISK')}
        </div>
        <div class="value risk">${t ? money(t.at_risk_vat) : '—'}</div>
        ${t && moneyShort(t.at_risk_vat) ? `<span class="short-read">khoảng ${moneyShort(t.at_risk_vat)}</span>` : ''}
        <div class="sub">${t ? `${t.at_risk_invoices} hóa đơn có cảnh báo cần kiểm tra` : 'Chưa phân tích'}</div>
      </div>
      <div class="kpi kpi-penalty">
        <div class="kpi-head">
          <div class="kpi-title-wrap">
            <span class="kpi-badge badge-penalty">${ICONS.penalty}</span>
            <span class="label">Kịch bản phạt nếu xác định khai sai</span>
          </div>
          ${spark('AT_RISK')}
        </div>
        <div class="value">${t ? money(t.penalty_estimate) : '—'}</div>
        ${t && moneyShort(t.penalty_estimate) ? `<span class="short-read">khoảng ${moneyShort(t.penalty_estimate)}</span>` : ''}
        <div class="sub">${t ? `Giả định có thiếu thuế; chưa xác nhận đã kê khai` : 'Chưa có số liệu'}</div>
      </div>
      <div class="kpi kpi-warn">
        <div class="kpi-head">
          <div class="kpi-title-wrap">
            <span class="kpi-badge badge-warn">${ICONS.review}</span>
            <span class="label">Hóa đơn cần người xem xét</span>
          </div>
          ${spark('REVIEW')}
        </div>
        <div class="value warn">${t ? money(t.review_vat) : '—'}</div>
        ${t && moneyShort(t.review_vat) ? `<span class="short-read">khoảng ${moneyShort(t.review_vat)}</span>` : ''}
        <div class="sub">${t ? `${t.review_invoices} hóa đơn cần đối chiếu chứng từ` : 'Không có hóa đơn chờ'}</div>
      </div>
      <div class="kpi kpi-opportunity">
        <div class="kpi-head">
          <div class="kpi-title-wrap">
            <span class="kpi-badge badge-opportunity">${ICONS.opportunity}</span>
            <span class="label">Có thể đang bỏ sót khấu trừ</span>
          </div>
          ${spark('OPPORTUNITY')}
        </div>
        <div class="value">${t ? money(t.opportunity_vat) : '—'}</div>
        ${t && moneyShort(t.opportunity_vat) ? `<span class="short-read">khoảng ${moneyShort(t.opportunity_vat)}</span>` : ''}
        <div class="sub">Hóa đơn trên cổng thuế chưa có tệp lưu trữ</div>
      </div>
    </div>

    <div class="bar">
      ${button('Chạy phân tích ngay', 'primary', 'id="run"')}
      ${rep ? `<details class="quick-export"><summary>Xuất và in báo cáo</summary>
        <a class="cds--btn cds--btn--tertiary cds--btn--md" href="/api/workspaces/${esc(state.ws)}/report.html" target="_blank" rel="noopener">Mở báo cáo để in</a>
        <a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/hoa-don.xlsx">Xuất danh sách hóa đơn (Excel)</a>
        <a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${esc(state.ws)}/export/quyet-dinh.xlsx">Xuất nhật ký quyết định (Excel)</a>
      </details>` : ''}
      <span id="run-msg"></span>
    </div>

    ${monthChart()}

    <div class="quick-links">
      <a href="#/so-lieu"><span class="icon-wrap">${ICONS.chart}</span> <span>Số liệu thuế GTGT theo kỳ</span></a>
      <a href="#/lich"><span class="icon-wrap">${ICONS.calendar}</span> <span>Lịch thuế và Hạn nộp</span></a>
      <a href="#/ngan-hang"><span class="icon-wrap">${ICONS.bank}</span> <span>Giao dịch ngân hàng</span></a>
      <a href="#/giai-trinh"><span class="icon-wrap">${ICONS.dossier}</span> <span>Soạn hồ sơ giải trình</span></a>
      <a href="#/luat"><span class="icon-wrap">${ICONS.law}</span> <span>Kho luật và Điểm mới</span></a>
    </div>

    <div class="grid2">
      <div>
        <h2 class="section">Việc lớn nhất cần xử lý</h2>
        ${table(['Trạng thái', 'Hóa đơn', 'Lý do', { label: 'Số tiền', num: true }], (rep?.items || []).slice(0, 6).map((it) => {
          const inv = invoiceOf(it.invoice_keys[0]);
          return `<tr class="clickable" data-go="#/viec">
            <td>${tag(it.status)}</td>
            <td><strong>${esc(invLabel(inv) || it.invoice_keys[0])}</strong><div class="muted small">${esc(inv?.seller_name || '')}</div></td>
            <td>${esc(it.title)}</td>
            <td class="num"><strong>${money(it.amount)}</strong></td>
          </tr>`;
        }), rep ? 'Không có khoản nào có rủi ro.' : 'Chưa phân tích.')}
      </div>

      <div>
        <h2 class="section">Dữ liệu đã nạp</h2>
        <div class="panel">
          <div class="coverage-grid">
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn mua vào</span>
              <span class="cov-status ${files.purchase_xml ? 'ok' : 'empty'}">${files.purchase_xml ? `✓ ${files.purchase_xml} tệp` : 'Chưa có'}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn bán ra</span>
              <span class="cov-status ${files.sales_xml ? 'ok' : 'empty'}">${files.sales_xml ? `✓ ${files.sales_xml} tệp` : '0 tệp'}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Sao kê ngân hàng</span>
              <span class="cov-status ${files.bank ? 'ok' : 'empty'}">${files.bank ? `✓ ${files.bank} tệp` : 'Chưa có'}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Bảng kê cổng thuế</span>
              <span class="cov-status ${files.portal_list ? 'ok' : 'empty'}">${files.portal_list ? '✓ Đã có' : 'Chưa có'}</span>
            </div>
          </div>
          ${button('Nạp thêm dữ liệu', 'ghost', 'data-go="#/nap"')}
        </div>

        <h2 class="section">Hạn nộp gần nhất</h2>
        ${table(['Kỳ', 'Hạn', 'Tình trạng'], (rep?.calendar || []).filter(c => c.due >= new Date().toLocaleDateString('sv-SE')).slice(0, 3).map((c) => `<tr>
          <td><strong>${esc(c.period)}</strong></td>
          <td>${dmy(c.due)}</td>
          <td>${esc(c.status)}</td>
        </tr>`), 'Chưa có hạn sắp tới trong dữ liệu đã nạp.')}
        <details><summary>Hạn đã qua — cần kiểm tra tình trạng kê khai</summary>
        ${table(['Kỳ', 'Hạn'], (rep?.calendar || []).filter(c => c.due < new Date().toLocaleDateString('sv-SE')).map(c => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}</td></tr>`), 'Không có hạn đã qua.')}</details>
      </div>
    </div>
    <div id="next"></div>`;

  freshBanner($('#fresh'));
  sellerWatch($('#watch'), rep);
  nextSteps(ws, rep).then((h) => { const el = $('#next'); if (el) el.innerHTML = h; });

  $('#run').onclick = async () => {
    const run = $('#run'); const message = $('#run-msg'); run.disabled = true;
    message.innerHTML = loading('Đang phân tích dữ liệu hóa đơn và sao kê');
    try { await post(`/api/workspaces/${state.ws}/run`); await loadWorkspaces(); rerender(); }
    catch (err) { if (message.isConnected && err.name !== 'AbortError') message.innerHTML = notice('error', 'Phân tích không chạy được', err.message); }
    finally { if (run.isConnected) run.disabled = false; }
  };
}

export async function pageReview() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Việc cần xử lý</h1>${notice('info', 'Chưa phân tích', 'Chạy phân tích ở trang Tổng quan để kiểm tra rủi ro.')}`; return; }
  if (rep.meta.schema_version !== 2) { app().innerHTML = `<h1 class="page">Việc cần xử lý</h1>${notice('warning', 'Báo cáo phiên bản cũ', 'Về Tổng quan và chạy lại phân tích trước khi lưu quyết định.')}<a href="#/">Về Tổng quan</a>`; return; }
  const filter = hashParams().get('loc') || 'all';
  const viewKey = `agent3.review.${state.ws}.${state.platform?.profile_revision}`;
  let savedView = {}; try { savedView = JSON.parse(sessionStorage.getItem(viewKey) || '{}'); } catch {}
  const context = await decisionContext();
  const months = [...new Set(rep.invoices.filter((i) => i.issue_date).map((i) => i.issue_date.slice(0, 7)))].sort();
  const items = rep.items.filter((it) => filter === 'all' || it.status === filter);
  const count = (s) => rep.items.filter((i) => i.status === s).length;

  app().innerHTML = `<h1 class="page">Việc cần xử lý</h1>
    <p class="lead">Danh sách các vấn đề thuế được sắp xếp theo mức độ ảnh hưởng số tiền. Bấm vào từng dòng để mở ngăn chi tiết đối chiếu chứng từ, căn cứ điều luật và lưu quyết định phê duyệt.</p>
    <div id="fresh"></div>
    <div id="ai-tools"></div>

    <div class="toolbar">
      <div class="status-filter-pills">
        ${[
          ['all', 'Tất cả', rep.items.length, ''],
          ['AT_RISK', 'Có nguy cơ', count('AT_RISK'), 'risk'],
          ['REVIEW', 'Cần xem xét', count('REVIEW'), 'warn'],
          ['OPPORTUNITY', 'Bỏ sót', count('OPPORTUNITY'), '']
        ].map(([k, l, n]) => `<a class="${k === filter ? 'active' : ''}" href="#/viec?loc=${k}">${esc(l)} <span class="pill-count">${n}</span></a>`).join('')}
      </div>

      <div class="filter-field" style="flex: 2 1 240px">
        <span>Tìm kiếm</span>
        <input class="cds--text-input filter-input" id="q" placeholder="Số hóa đơn, người bán, lý do..." aria-label="Tìm việc">
      </div>

      <div class="filter-field">
        <span>Vấn đề</span>
        <select class="cds--select-input filter-select" id="group" aria-label="Lọc theo vấn đề"></select>
      </div>

      <div class="filter-field">
        <span>Kỳ phát sinh</span>
        <select class="cds--select-input filter-select" id="month" aria-label="Lọc theo tháng">
          <option value="">Mọi tháng</option>
          ${months.map((m) => `<option value="${m}">Tháng ${m.slice(5)}/${m.slice(0, 4)}</option>`).join('')}
        </select>
      </div>

      <div style="display:flex;align-items:center;gap:8px;margin-top:auto">
        <span class="muted small" id="shown" role="status"></span>
        ${button('Xóa bộ lọc', 'ghost', 'id="reset-filters"')}
        <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${esc(state.ws)}/export/viec-can-xu-ly.xlsx">Xuất Excel</a>
      </div>
    </div>

    <div class="bulk" id="bulk" hidden>
      <span id="bulk-n"></span>
      <select class="cds--select-input filter-select" id="bulk-action" aria-label="Quyết định hàng loạt"></select>
      <input class="cds--text-input filter-input" id="bulk-ev" aria-label="Chứng từ hoặc lý do chung" placeholder="Chứng từ hoặc lý do chung">
      <input class="cds--text-input filter-input" id="bulk-by" aria-label="Người duyệt" placeholder="Người duyệt" value="${esc(store.get('agent3.reviewer') || '')}">
      ${button('Ghi cho các việc đã chọn', 'primary', 'id="bulk-go"')}
    </div>

    <div id="list"></div>`;

  const PAGE = 50;
  let shown = savedView.shown || PAGE;
  let code = hashParams().get('nhom') || savedView.code || '';
  const idxOf = new Map(rep.items.map((it, i) => [it, i]));
  const txnOf = it => rep.transactions.find(t => it.txn_ids?.includes(t.txn_id));
  const textOf = (it) => { const inv = invoiceOf(it.invoice_keys[0]); const txn = txnOf(it); return `${invLabel(inv)} ${inv?.seller_name || txn?.counterparty_name || ''} ${it.title} ${it.detail}`.toLowerCase(); };
  const monthOf = (it) => (invoiceOf(it.invoice_keys[0])?.issue_date || txnOf(it)?.booked || '').slice(0, 7);
  const groups = {};
  items.forEach((it) => { const g = groups[it.code] ||= { title: it.title, status: it.status, n: 0, amount: 0 }; g.n += 1; g.amount += Number(it.amount || 0); });

  const paintGroups = () => {
    const opts = Object.entries(groups).sort((x, y) => y[1].amount - x[1].amount || y[1].n - x[1].n);
    $('#group').innerHTML = `<option value="">Mọi vấn đề</option>${opts.map(([c, g]) => `<option value="${esc(c)}" ${c === code ? 'selected' : ''}>${esc(g.title)} (${g.n})</option>`).join('')}`;
  };

  const selectedPicks = new Set();
  const rowTpl = (it) => {
    const inv = invoiceOf(it.invoice_keys[0]);
    const txn = txnOf(it);
    const i = idxOf.get(it);
    return `<tr class="clickable" tabindex="0" data-item="${i}">
      <td class="pickcell">${(it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length ? `<input type="checkbox" class="bulk-pick" data-idx="${i}" aria-label="Chọn" ${selectedPicks.has(it.finding_id) ? 'checked' : ''}>` : ''}</td>
      <td>${tag(it.status)}</td>
      <td><strong>${esc(invLabel(inv) || it.invoice_keys[0] || (txn ? 'Khoản thu' : ''))}</strong><div class="muted small">${dmy(inv?.issue_date || txn?.booked)}</div></td>
      <td><strong>${esc(inv?.seller_name || txn?.counterparty_name || '')}</strong><div class="muted small mono">${inv ? 'MST ' + esc(inv.seller_tax_id || '') : esc(txn?.source || '')}</div></td>
      <td><span class="cell-title">${esc(it.title)}</span><div class="muted small">${esc(it.detail)}</div></td>
      <td class="num"><strong>${money(it.amount)}</strong></td>
    </tr>`;
  };

  let picks = [];
  const syncBulk = () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    $('#bulk').hidden = !chosen.length;
    if (!chosen.length) return;
    $('#bulk-n').textContent = `Đã chọn ${chosen.length} việc`;
    const common = chosen.map(decisionChoices).reduce((acc, ch) => acc.filter(([v]) => ch.some(([w]) => w === v)));
    $('#bulk-action').innerHTML = common.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
  };

  const paint = () => {
    const q = $('#q').value.trim().toLowerCase(); const m = $('#month').value;
    const view = items.filter((it) => (!code || it.code === code) && (!q || textOf(it).includes(q)) && (!m || monthOf(it) === m));
    reviewItems = view;
    reviewSnapshot = () => { try { sessionStorage.setItem(viewKey, JSON.stringify({q: $('#q').value, month: $('#month').value, code, shown, scroll: window.scrollY, focus: lastOpened})); } catch {} };
    $('#shown').textContent = q || m || code ? `${view.length} việc khớp` : `${view.length} việc`;
    $('#list').innerHTML = table(['', 'Trạng thái', 'Hóa đơn', 'Người bán', 'Lý do', { label: 'Số tiền', num: true }], view.slice(0, shown).map(rowTpl), 'Không có việc nào khớp bộ lọc.')
      + (view.length > shown ? `<div class="bar" style="margin-top:16px"><span class="muted small">Đang hiện ${shown} trên ${view.length} việc</span>${button(`Hiện thêm ${Math.min(PAGE, view.length - shown)} việc`, 'ghost', 'id="more"')}${button('Hiện tất cả', 'ghost', 'id="all"')}</div>` : '');
    picks = [...app().querySelectorAll('.bulk-pick')];
    picks.forEach((c) => { c.onclick = (e) => e.stopPropagation(); c.onchange = () => { const key = rep.items[Number(c.dataset.idx)].finding_id; c.checked ? selectedPicks.add(key) : selectedPicks.delete(key); syncBulk(); }; });
    app().querySelectorAll('[data-item]').forEach((tr) => {
      tr.onclick = () => openItem(rep.items[Number(tr.dataset.item)], Number(tr.dataset.item));
      tr.onkeydown = (e) => { if (e.target === tr && ['Enter', ' '].includes(e.key)) { e.preventDefault(); tr.click(); } };
    });
    if ($('#more')) $('#more').onclick = () => { shown += PAGE; paint(); };
    if ($('#all')) $('#all').onclick = () => { shown = view.length; paint(); };
    syncBulk();
  };

  $('#group').onchange = () => { code = $('#group').value; shown = PAGE; paint(); };
  $('#bulk-go').onclick = async () => {
    const chosen = picks.filter((c) => c.checked).map((c) => rep.items[Number(c.dataset.idx)]);
    const body = { invoice_keys: [...new Set(chosen.map((x) => x.invoice_keys[0]))], finding_ids: chosen.map(x => x.finding_id), action: $('#bulk-action').value, evidence: $('#bulk-ev').value.trim(), by: $('#bulk-by').value.trim() };
    if (!body.action || !body.evidence || !body.by) { toast('Cần quyết định, chứng từ hoặc lý do và người duyệt', '', 'error'); return; }
    store.set('agent3.reviewer', body.by);
    const submit = $('#bulk-go'); submit.disabled = true;
    try { reviewSnapshot?.(); const r = await decide(`/api/workspaces/${state.ws}/decisions/bulk`, body, context); if (r.report_pending) { toast('Quyết định đã lưu; cần chạy lại báo cáo', r.message, 'warning'); submit.disabled = false; return; } toast(`Đã ghi ${r.decisions} quyết định`, `Thuế có nguy cơ còn ${money(r.totals.at_risk_vat)}`); window.sonStamp?.(body.by); rerender(); }
    catch (err) { if (submit.isConnected) { toast('Không ghi được', err.message, 'error'); submit.disabled = false; } }
  };
  $('#q').oninput = () => { shown = PAGE; paint(); }; $('#month').onchange = () => { shown = PAGE; paint(); };
  $('#reset-filters').onclick = () => {
    if (filter !== 'all') { location.hash = '#/viec'; return; }
    $('#q').value = ''; $('#month').value = ''; code = ''; $('#group').value = ''; shown = PAGE; paint();
  };

  $('#q').value = savedView.q || ''; $('#month').value = savedView.month || '';
  paintGroups(); paint();
  onPageLeave(() => { if (app().querySelector('#shown')) reviewSnapshot?.(); });
  requestAnimationFrame(() => { if (app().querySelector('#shown') && !document.querySelector('.drawer')) { window.scrollTo(0, savedView.scroll || 0); const idx = rep.items.findIndex(it => itemId(it) === savedView.focus); app().querySelector(`[data-item="${idx}"]`)?.focus({preventScroll: true}); } });
  aiToolbar($('#ai-tools')).catch((err) => { const el = $('#ai-tools'); if (el && err.name !== 'AbortError') el.innerHTML = notice('info', 'Trợ lý AI chưa sẵn sàng', 'Bạn vẫn có thể xem chứng từ và xử lý công việc bình thường.'); });
  freshBanner($('#fresh'));

  let want = null;
  try { want = sessionStorage.getItem('agent3.openNext'); sessionStorage.removeItem('agent3.openNext'); } catch { /* private mode */ }
  if (want) {
    const idx = rep.items.findIndex((it) => itemId(it) === want);
    if (idx >= 0) openItem(rep.items[idx], idx);
  }
  const deep = hashParams().get('open');
  if (deep && !want) {
    const idx = rep.items.findIndex((it) => it.code === deep || itemId(it) === deep || it.invoice_keys.includes(deep));
    if (idx >= 0) openItem(rep.items[idx], idx);
  }
}

export function decisionChoices(it) {
  if (it.code.startsWith('R14')) return [['CONFIRMED_NON_REVENUE', 'Đã kiểm tra: không phải khoản thu bán hàng'], ['SALES_EVIDENCE_ATTACHED', 'Đã bổ sung hóa đơn bán ra liên quan']];
  const payment = /^R0[123]_/.test(it.code);
  const out = [];
  if (payment) out.push(['PAYMENT_EVIDENCE_ATTACHED', 'Đã có chứng từ thanh toán không dùng tiền mặt']);
  if (it.status === 'REVIEW') out.push(['CONFIRMED_OK', 'Đã kiểm tra, không có vấn đề (ghi rõ căn cứ kiểm tra)']);
  out.push(['NOT_CLAIMED', 'Không kê khai khấu trừ hóa đơn này']);
  return out;
}

const decisionHelp = (it) => (/^R0[123]_/.test(it.code) || it.status === 'REVIEW' ? ''
  : 'Với loại rủi ro này, chứng từ thanh toán không khắc phục được; cần hóa đơn thay thế hoặc điều chỉnh từ người bán, hoặc không kê khai.');

async function exposureBox(el, index) {
  try {
    const ex = await api(`/api/workspaces/${state.ws}/exposure`);
    const e = ex[index];
    if (!e) return;
    el.innerHTML = `<div class="panel exposure" style="border-left:3px solid var(--a3-danger);background:var(--cds-layer)">
      <h3 style="margin-top:0">Đánh giá thiệt hại và Phương án xử lý tối ưu</h3>
      <p>${esc(e.note)}</p>
      ${e.overdue === true
        ? `<table class="mini" style="width:100%;font-size:13px">
            <tr><td>Thuế theo giả định</td><td class="num"><strong>${money(e.amount)}</strong></td><td class="muted small">Chưa xác nhận đã khấu trừ hoặc thực tế thiếu thuế</td></tr>
            <tr><td>Chậm nộp theo giả định</td><td class="num">${money(e.interest) || 'Chưa đủ dữ liệu'}</td><td class="muted small">${e.days_late} ngày sau hạn lịch</td></tr>
            <tr><td>Phạt theo giả định</td><td class="num">${money(e.penalty) || 'Chưa đủ dữ liệu'}</td><td class="muted small">Không phải kết luận xử phạt</td></tr>
          </table>`
        : `<p>${e.due ? `Hạn theo lịch: ${dmy(e.due)}; chưa quá hạn lịch.` : 'Chưa xác định được hạn; không tính số ngày chậm.'} Chưa có bằng chứng xác nhận tình trạng kê khai hoặc nộp.</p>`}
      <div class="cite" style="margin-top:8px">${e.basis.filter(Boolean).map(esc).join('<br>')}</div>
    </div>`;
  } catch { el.innerHTML = ''; }
}

function openItem(it, index) {
  lastOpened = itemId(it);
  const inv = invoiceOf(it.invoice_keys[0]);
  const match = state.report.matches.find((m) => m.invoice_keys.includes(it.invoice_keys[0]));
  const canDecide = (it.status === 'AT_RISK' || it.status === 'REVIEW') && (it.invoice_keys.length > 0 || it.txn_ids?.length > 0);
  const receipt = it.code.startsWith('R14');
  const selectedSales = new Set();
  const txn = state.report.transactions.find(t => it.txn_ids?.includes(t.txn_id));
  const contextReady = decisionContext();
  contextReady.catch(() => {});

  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-labelledby="drawer-title">
    <div class="drawer-top-bar">
      <div>
        <div class="drawer-subhead">
          ${tag(it.status)}
          <span class="rule-code-badge">${esc(it.code)}</span>
          ${it.amount ? `<span class="amount-badge">Thuế: ${money(it.amount)}</span>` : ''}
        </div>
        <h2 id="drawer-title">${esc(it.title)}</h2>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close" id="close" type="button" aria-label="Đóng ngăn chi tiết">✕ Đóng</button>
    </div>

    <div id="plain" style="margin-top:1rem"></div>

    <div class="dossier-grid">
      <div class="dossier-card">
        <h3 class="dossier-card-title"><span class="dossier-icon">${ICONS.dossier}</span> ${receipt ? 'Thông tin giao dịch' : 'Hóa đơn đầu vào XML'}</h3>
        ${receipt && txn ? `<dl class="kv"><dt>Ngày</dt><dd>${dmy(txn.booked)}</dd><dt>Số tiền</dt><dd><strong>${money(txn.amount)}</strong></dd><dt>Đối tác</dt><dd>${esc(txn.counterparty_name)}</dd><dt>Nội dung</dt><dd>${esc(txn.description)}</dd><dt>Nguồn</dt><dd class="mono small">${esc(txn.source)}</dd></dl>` : ''}
        <dl class="kv" ${receipt ? 'hidden' : ''}>
          <dt>Số hóa đơn</dt><dd><strong>${esc(invLabel(inv) || it.invoice_keys[0])}</strong></dd>
          <dt>Người bán</dt><dd><strong>${esc(inv?.seller_name || '')}</strong> <div class="muted small">MST: ${esc(inv?.seller_tax_id || '')}</div></dd>
          <dt>Ngày lập</dt><dd>${dmy(inv?.issue_date)}</dd>
          <dt>Tổng thanh toán</dt><dd><strong>${money(inv?.gross)}</strong></dd>
          <dt>Tiền thuế GTGT</dt><dd><strong style="color:var(--a3-primary);font-size:15px">${money(inv?.vat)}</strong></dd>
          <dt>Tệp XML gốc</dt><dd class="mono small" style="word-break:break-all">${esc(inv?.file || '')}</dd>
        </dl>
      </div>

      <div class="dossier-card">
        <h3 class="dossier-card-title"><span class="dossier-icon">${ICONS.bank}</span> Chứng từ Ngân hàng đối chiếu</h3>
        ${match ? `
          <div class="match-badge ${match.status === 'MATCHED' ? 'match-ok' : 'match-warn'}">
            ${match.status === 'MATCHED' ? '✓ Đã ghép chứng từ thanh toán' : '⚠ Khớp mơ hồ / Cần xem lại'}
          </div>
          <p class="small" style="margin:8px 0 12px">${esc(match.note)}</p>
          ${txn ? `<dl class="kv"><dt>Ngày hạch toán</dt><dd>${dmy(txn.booked)}</dd><dt>Số tiền TT</dt><dd><strong>${money(txn.amount)}</strong></dd><dt>Nội dung CK</dt><dd>${esc(txn.description)}</dd></dl>` : ''}
        ` : `
          <div class="match-badge match-empty">⚠ Chưa ghép được chứng từ thanh toán không dùng tiền mặt</div>
          <p class="muted small" style="margin-top:8px">Hóa đơn có giá trị từ 20 triệu đồng trở lên cần chứng từ thanh toán không dùng tiền mặt để đủ điều kiện khấu trừ thuế GTGT.</p>
        `}
      </div>
    </div>

    <div id="exposure"></div>
    <details><summary>Lịch sử quyết định và bằng chứng</summary><div id="decision-history"></div></details>

    <h3 class="section">Chi tiết vấn đề và Khuyến nghị</h3>
    <div style="background:var(--cds-layer);padding:14px 16px;border-radius:8px;border:1px solid var(--cds-border-subtle);margin-bottom:14px">
      <p style="margin:0 0 8px;font-size:13.5px"><strong>Hiện tượng:</strong> ${esc(it.detail)}</p>
      <p style="margin:0;font-size:13.5px;color:var(--a3-primary)"><strong>Hành động cần làm:</strong> ${esc(it.action)}</p>
    </div>

    <h3 class="section">Căn cứ pháp lý</h3>
    <ul style="font-size:13px;line-height:1.6;margin:0 0 16px 20px;padding:0">
      ${it.basis.map((b) => `<li>${esc(b)}</li>`).join('')}
    </ul>

    ${canDecide ? `<h3 class="section">Phê duyệt và Quyết định xử lý</h3>
      <div id="suggest"></div>
      <form id="decide">
        <div class="form-grid">
          ${field({ key: 'action', label: 'Quyết định xử lý', type: 'choice', required: true, choices: decisionChoices(it), help: decisionHelp(it) }, decisionChoices(it)[0][0])}
          ${field({ key: 'evidence', label: 'Chứng từ hoặc lý do giải trình', required: true, example: 'Ủy nhiệm chi số 5521 ngày 05/09/2026' })}
          ${field({ key: 'by', label: 'Người duyệt', required: true, example: 'Kế toán trưởng' }, store.get('agent3.reviewer') || '')}
          ${receipt ? field({ key: 'category', label: 'Loại khoản thu nếu không phải bán hàng', type: 'choice', choices: [['LOAN', 'Khoản vay'], ['INTERNAL_TRANSFER', 'Chuyển nội bộ'], ['CAPITAL', 'Góp vốn'], ['REFUND', 'Hoàn tiền'], ['OTHER', 'Khác, ghi rõ bằng chứng']] }) : ''}
        </div>
        ${receipt ? `<details><summary>Hóa đơn bán ra liên quan (khi xác nhận đã bổ sung hóa đơn)</summary><label for="sales-query">Tìm số hóa đơn hoặc người mua</label><input id="sales-query" class="cds--text-input"><div id="sales-picks" class="sales-evidence-list"></div><div id="sales-selected" role="status"></div></details>` : ''}
        <div class="bar" style="margin-top:16px">
          ${button('Lưu và mở việc tiếp theo', 'primary', 'type="submit" data-next="1"')}
          ${button('Lưu quyết định này', 'secondary', 'type="submit"')}
          <span id="dmsg"></span>
        </div>
      </form>` : ''}
  </aside>`;

  bindDialog();
  const historyBox = $('#decision-history');
  contextReady.then(ctx => {
    if (!historyBox.isConnected) return;
    const rows = ctx.events.filter(e => e.finding_id === it.finding_id || it.invoice_keys.includes(e.invoice_key) || e.txn_ids?.some(t => it.txn_ids?.includes(t)));
    historyBox.innerHTML = table(['Thời điểm', 'Người duyệt', 'Quyết định', 'Bằng chứng'], rows.map(e => `<tr><td>${esc(e.at)}${e.legacy ? ' (dữ liệu cũ)' : ''}</td><td>${esc(e.by)}</td><td>${esc(e.action)}${e.supersedes ? '<div class="muted small">Thay thế một quyết định trước; bản trước vẫn được giữ</div>' : ''}</td><td>${esc(e.evidence)}</td></tr>`), 'Chưa có quyết định cho đối tượng này.');
  }).catch(err => { if (historyBox.isConnected) historyBox.innerHTML = notice('error', 'Không tải được lịch sử', err.message); });
  if (receipt) {
    const sales = state.report.invoices.filter(i => i.role === 'SALE' && !i.duplicate_of);
    const paintSales = () => {
      const q = $('#sales-query').value.trim().toLowerCase();
      const filtered = sales.filter(i => `${invLabel(i)} ${i.buyer_name}`.toLowerCase().includes(q));
      $('#sales-picks').innerHTML = filtered.slice(0, 50).map(i => `<label><input type="checkbox" value="${esc(i.key)}" ${selectedSales.has(i.key) ? 'checked' : ''}> ${esc(invLabel(i))} — ${esc(i.buyer_name)} — ${money(i.gross)}</label>`).join('');
      $('#sales-selected').textContent = `Hiện tối đa 50/${filtered.length} hóa đơn; đã chọn ${selectedSales.size}. Tìm để thu hẹp kết quả.`;
      $('#sales-picks').onchange = e => { if (e.target.matches('input')) { e.target.checked ? selectedSales.add(e.target.value) : selectedSales.delete(e.target.value); paintSales(); } };
    };
    $('#sales-query').oninput = paintSales; paintSales();
  }
  if (Number.isInteger(index)) explainBox($('#plain'), index);
  if (it.status === 'AT_RISK' && Number.isInteger(index)) exposureBox($('#exposure'), index);

  const form = $('#decide');
  if (form) {
    const drawer = $('.drawer');
    api(`/api/workspaces/${state.ws}/decisions/suggest?key=${encodeURIComponent(it.invoice_keys[0])}&code=${encodeURIComponent(it.code)}`).then((r) => {
      const s = r.suggestion;
      if (!s || !drawer.isConnected) return;
      const ok = decisionChoices(it).some(([v]) => v === s.action);
      if (!ok) return;
      $('#suggest').innerHTML = `<div class="banner banner-info">
        <div><strong>Gợi ý từ quyết định trước</strong><div class="small">${esc(s.because)}</div></div>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="use-sugg">Điền theo gợi ý</button>
      </div>`;
      $('#use-sugg').onclick = () => {
        form.querySelector('[name=action]').value = s.action;
        form.querySelector('[name=evidence]').value = '';
        form.querySelector('[name=evidence]').placeholder = `Lần trước: ${s.evidence}`;
        if (!form.querySelector('[name=by]').value) form.querySelector('[name=by]').value = s.by;
        form.querySelector('[name=evidence]').focus();
      };
    }).catch(() => {});

    form.onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      store.set('agent3.reviewer', d.by);
      const goNext = e.submitter && e.submitter.dataset.next;
      const open = reviewItems.filter((x) => (x.status === 'AT_RISK' || x.status === 'REVIEW') && itemId(x) !== itemId(it) && !x.invoice_keys.includes(it.invoice_keys[0]));
      const after = open[open.indexOf(open.find((x) => state.report.items.indexOf(x) > index))] || open[0];
      $('#dmsg').innerHTML = '<span class="muted">Đang lưu quyết định...</span>';
      const message = $('#dmsg');
      const buttons = [...form.querySelectorAll('button[type="submit"]')];
      buttons.forEach((b) => { b.disabled = true; });
      try {
        reviewSnapshot?.();
        const r = await decide(`/api/workspaces/${state.ws}/decisions`, { ...d, invoice_key: it.invoice_keys[0], finding_id: it.finding_id, invoice_keys: receipt ? [...selectedSales] : undefined }, await contextReady);
        if (r.report_pending) { message.innerHTML = notice('warning', 'Quyết định đã lưu; cần chạy lại báo cáo', r.message); buttons.forEach(b => { b.disabled = false; }); return; }
        toast('Đã lưu quyết định', `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`);
        window.sonStamp?.(d.by);
        if (goNext && after) { try { sessionStorage.setItem('agent3.openNext', itemId(after)); } catch { /* private mode */ } }
        closeDialog(); rerender();
      }
      catch (err) {
        if (form.isConnected) {
          message.innerHTML = notice('error', 'Không lưu được', err.message);
          buttons.forEach((b) => { b.disabled = false; });
        }
      }
    };
  }
}
