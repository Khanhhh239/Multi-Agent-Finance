// Overview, data intake and the review queue.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loadWorkspaces, loading, money, moneyShort, needWorkspace, notice, post, put,
  state, store, table, tag } from './core.js';
import { aiToolbar, explainBox } from './pages_ai.js';
import { pageWelcome } from './pages_config.js';
import { deadlineBanner, freshBanner, nextSteps, sellerWatch, toast } from './ux.js';
import { bindDialog, closeDialog } from './interactions.js';

const itemId = (it) => `${it.code}|${it.invoice_keys.join(',')}`;

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageOverview() {
  if (!state.ws) { await pageWelcome(); return; }
  const ws = state.workspaces.find((w) => w.id === state.ws);
  const rep = await loadReport();
  const t = rep?.totals;
  const files = ws.files;
  const period = rep?.meta.period ? ` Dữ liệu từ ${dmy(rep.meta.period[0])} đến ${dmy(rep.meta.period[1])}.` : '';


  // Series for the sparklines and the small table, from the report only (nothing estimated).
  // By month when the data spans several months; otherwise by week, so a single month still shows a shape.
  const dated = (rep?.items || []).filter((it) => ['AT_RISK', 'REVIEW', 'OPPORTUNITY'].includes(it.status))
    .map((it) => ({ it, d: (invoiceOf(it.invoice_keys[0])?.issue_date || '').slice(0, 10) })).filter((x) => x.d);
  const byWeek = new Set(dated.map((x) => x.d.slice(0, 7))).size < 2;
  const bucketOf = (d) => {
    if (!byWeek) return d.slice(0, 7);
    const day = Number(d.slice(8, 10));
    return `${d.slice(0, 7)}-${String(Math.min(4, Math.floor((day - 1) / 7)) + 1)}`;   // four buckets per month: 1-7, 8-14, 15-21, 22-end
  };
  const bucketLabel = (k) => {
    if (!byWeek) return `Tháng ${Number(k.slice(5, 7))}/${k.slice(0, 4)}`;
    const w = Number(k.slice(8)); const mo = Number(k.slice(5, 7));
    const last = new Date(Number(k.slice(0, 4)), mo, 0).getDate();
    return `${(w - 1) * 7 + 1}–${w === 4 ? last : w * 7}/${mo}/${k.slice(0, 4)}`;
  };
  const monthly = (() => {
    const m = {};
    dated.forEach(({ it, d }) => { const e = m[bucketOf(d)] ||= { AT_RISK: 0, REVIEW: 0, OPPORTUNITY: 0 }; e[it.status] += Number(it.amount || 0); });
    return Object.keys(m).sort().map((k) => ({ k, ...m[k] }));
  })();
  const spark = (status) => {
    const v = monthly.map((e) => e[status]);
    if (v.length < 2 || !v.some(Boolean)) return '';
    const W = 92; const H = 28; const max = Math.max(...v);
    const pts = v.map((x, i) => [2 + (i / (v.length - 1)) * (W - 8), H - 4 - (x / max) * (H - 10)]);
    const last = pts[pts.length - 1];
    return `<svg class="spark spark-${status.toLowerCase()}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Diễn biến theo tháng, ${v.length} tháng"><polyline points="${pts.map((q) => q.map((n) => n.toFixed(1)).join(',')).join(' ')}"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6"/></svg>`;
  };
  const monthChart = () => {
    if (monthly.length < 2) return '';
    const total = (e) => e.AT_RISK + e.REVIEW;
    const max = Math.max(...monthly.map(total), 1);
    const X = 118; const BW = 300; const ROW = 34;
    const rows = monthly.map((e, i) => {
      const y = 10 + i * ROW;
      const wr = (e.AT_RISK / max) * BW; const wv = (e.REVIEW / max) * BW;
      const parts = [e.AT_RISK ? `${moneyShort(e.AT_RISK) || money(e.AT_RISK)} có nguy cơ` : '', e.REVIEW ? `${moneyShort(e.REVIEW) || money(e.REVIEW)} cần xem xét` : ''].filter(Boolean);
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
    <div id="fresh"></div>
    <div id="watch"></div>
    ${deadlineBanner(rep, rep ? new Date(rep.meta.as_of) : new Date())}

    <div class="kpis">
      <div class="kpi kpi-risk">
        <div class="kpi-head">
          <span class="label">Thuế đầu vào có nguy cơ bị loại</span>
          ${spark('AT_RISK')}
        </div>
        <div class="value risk">${t ? money(t.at_risk_vat) : '—'}</div>
        ${t && moneyShort(t.at_risk_vat) ? `<span class="short-read">khoảng ${moneyShort(t.at_risk_vat)}</span>` : ''}
        <div class="sub">${t ? `${t.at_risk_invoices} hóa đơn vi phạm điều kiện khấu trừ` : 'Chưa phân tích'}</div>
      </div>
      <div class="kpi">
        <div class="kpi-head">
          <span class="label">Ước tính phạt tối đa</span>
          ${spark('AT_RISK')}
        </div>
        <div class="value">${t ? money(t.penalty_estimate) : '—'}</div>
        ${t && moneyShort(t.penalty_estimate) ? `<span class="short-read">khoảng ${moneyShort(t.penalty_estimate)}</span>` : ''}
        <div class="sub">${t ? `${Math.round(t.penalty_rate * 100)}% số thuế khai thiếu theo luật thuế` : 'Chưa có số liệu'}</div>
      </div>
      <div class="kpi kpi-warn">
        <div class="kpi-head">
          <span class="label">Hóa đơn cần người xem xét</span>
          ${spark('REVIEW')}
        </div>
        <div class="value warn">${t ? money(t.review_vat) : '—'}</div>
        ${t && moneyShort(t.review_vat) ? `<span class="short-read">khoảng ${moneyShort(t.review_vat)}</span>` : ''}
        <div class="sub">${t ? `${t.review_invoices} hóa đơn cần đối chiếu chứng từ` : 'Không có hóa đơn chờ'}</div>
      </div>
      <div class="kpi kpi-opportunity">
        <div class="kpi-head">
          <span class="label">Có thể đang bỏ sót khấu trừ</span>
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
      <a href="#/so-lieu"><span>📊</span> Số liệu thuế GTGT theo kỳ</a>
      <a href="#/lich"><span>📅</span> Lịch thuế và Hạn nộp</a>
      <a href="#/ngan-hang"><span>🏦</span> Giao dịch ngân hàng</a>
      <a href="#/giai-trinh"><span>📑</span> Soạn hồ sơ giải trình</a>
      <a href="#/luat"><span>⚖️</span> Kho luật và Điểm mới</a>
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
        ${table(['Kỳ', 'Hạn', 'Tình trạng'], (rep?.calendar || []).slice(-3).reverse().map((c) => `<tr>
          <td><strong>${esc(c.period)}</strong></td>
          <td>${dmy(c.due)}</td>
          <td>${esc(c.status)}</td>
        </tr>`), 'Chưa có dữ liệu lịch.')}
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
  const filter = hashParams().get('loc') || 'all';
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
  let shown = PAGE;
  let code = hashParams().get('nhom') || '';
  const idxOf = new Map(rep.items.map((it, i) => [it, i]));
  const textOf = (it) => { const inv = invoiceOf(it.invoice_keys[0]); return `${invLabel(inv)} ${inv?.seller_name || ''} ${it.title} ${it.detail}`.toLowerCase(); };
  const monthOf = (it) => (invoiceOf(it.invoice_keys[0])?.issue_date || '').slice(0, 7);
  const groups = {};
  items.forEach((it) => { const g = groups[it.code] ||= { title: it.title, status: it.status, n: 0, amount: 0 }; g.n += 1; g.amount += Number(it.amount || 0); });

  const paintGroups = () => {
    const opts = Object.entries(groups).sort((x, y) => y[1].amount - x[1].amount || y[1].n - x[1].n);
    $('#group').innerHTML = `<option value="">Mọi vấn đề</option>${opts.map(([c, g]) => `<option value="${esc(c)}" ${c === code ? 'selected' : ''}>${esc(g.title)} (${g.n})</option>`).join('')}`;
  };

  const rowTpl = (it) => {
    const inv = invoiceOf(it.invoice_keys[0]);
    const i = idxOf.get(it);
    return `<tr class="clickable" tabindex="0" data-item="${i}">
      <td class="pickcell">${(it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length ? `<input type="checkbox" class="bulk-pick" data-idx="${i}" aria-label="Chọn">` : ''}</td>
      <td>${tag(it.status)}</td>
      <td><strong>${esc(invLabel(inv) || it.invoice_keys[0] || '')}</strong><div class="muted small">${dmy(inv?.issue_date)}</div></td>
      <td><strong>${esc(inv?.seller_name || '')}</strong><div class="muted small mono">MST ${esc(inv?.seller_tax_id || '')}</div></td>
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
    $('#shown').textContent = q || m || code ? `${view.length} việc khớp` : `${view.length} việc`;
    $('#list').innerHTML = table(['', 'Trạng thái', 'Hóa đơn', 'Người bán', 'Lý do', { label: 'Số tiền', num: true }], view.slice(0, shown).map(rowTpl), 'Không có việc nào khớp bộ lọc.')
      + (view.length > shown ? `<div class="bar" style="margin-top:16px"><span class="muted small">Đang hiện ${shown} trên ${view.length} việc</span>${button(`Hiện thêm ${Math.min(PAGE, view.length - shown)} việc`, 'ghost', 'id="more"')}${button('Hiện tất cả', 'ghost', 'id="all"')}</div>` : '');
    picks = [...app().querySelectorAll('.bulk-pick')];
    picks.forEach((c) => { c.onclick = (e) => e.stopPropagation(); c.onchange = syncBulk; });
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
    const body = { invoice_keys: [...new Set(chosen.map((x) => x.invoice_keys[0]))], action: $('#bulk-action').value, evidence: $('#bulk-ev').value.trim(), by: $('#bulk-by').value.trim() };
    if (!body.action || !body.evidence || !body.by) { toast('Cần quyết định, chứng từ hoặc lý do và người duyệt', '', 'error'); return; }
    store.set('agent3.reviewer', body.by);
    const submit = $('#bulk-go'); submit.disabled = true;
    try { const r = await post(`/api/workspaces/${state.ws}/decisions/bulk`, body); toast(`Đã ghi ${r.decisions} quyết định`, `Thuế có nguy cơ còn ${Number(r.totals.at_risk_vat).toLocaleString('vi-VN')} đ`); window.sonStamp?.(body.by); rerender(); }
    catch (err) { if (submit.isConnected) { toast('Không ghi được', err.message, 'error'); submit.disabled = false; } }
  };
  $('#q').oninput = () => { shown = PAGE; paint(); }; $('#month').onchange = () => { shown = PAGE; paint(); };
  $('#reset-filters').onclick = () => {
    if (filter !== 'all') { location.hash = '#/viec'; return; }
    $('#q').value = ''; $('#month').value = ''; code = ''; $('#group').value = ''; shown = PAGE; paint();
  };

  paintGroups(); paint();
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
      ${e.declared
        ? `<table class="mini" style="width:100%;font-size:13px">
            <tr><td>Tự khai bổ sung và nộp ngay</td><td class="num"><strong>${money(Number(e.amount) + Number(e.interest))}</strong></td><td class="muted small">thuế ${money(e.amount)} + tiền chậm nộp ${money(e.interest)} (${e.days_late} ngày); không bị phạt khai sai</td></tr>
            <tr><td>Để cơ quan thuế phát hiện</td><td class="num risk-text"><strong>${money(Number(e.amount) + Number(e.interest) + Number(e.penalty))}</strong></td><td class="muted small">thêm phạt 20% (${money(e.penalty)}), tiền chậm nộp tiếp tục tăng</td></tr>
          </table>`
        : `<p style="font-size:13.5px">Kỳ của hóa đơn này chưa đến hạn khai (${dmy(e.due)}): xử lý xong trước khi nộp tờ khai thì <strong>không phát sinh phạt hay tiền chậm nộp</strong>.</p>`}
      <div class="cite" style="margin-top:8px">${e.basis.filter(Boolean).map(esc).join('<br>')}</div>
    </div>`;
  } catch { el.innerHTML = ''; }
}

function openItem(it, index) {
  const inv = invoiceOf(it.invoice_keys[0]);
  const match = state.report.matches.find((m) => m.invoice_keys.includes(it.invoice_keys[0]));
  const canDecide = (it.status === 'AT_RISK' || it.status === 'REVIEW') && it.invoice_keys.length > 0;

  $('#modal-root').innerHTML = `<aside class="drawer" role="dialog" aria-labelledby="drawer-title">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
      <div>
        <h2 id="drawer-title">${esc(it.title)}</h2>
        <div style="display:flex;gap:8px;align-items:center;margin-top:4px">${tag(it.status)} <span class="muted small">${esc(it.code)}</span></div>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close" id="close" type="button" aria-label="Đóng ngăn chi tiết">✕ Đóng</button>
    </div>

    <div id="plain" style="margin-top:1rem"></div>

    <h3 class="section">Thông tin hóa đơn</h3>
    <dl class="kv">
      <dt>Số hóa đơn</dt><dd><strong>${esc(invLabel(inv) || it.invoice_keys[0])}</strong></dd>
      <dt>Người bán</dt><dd><strong>${esc(inv?.seller_name || '')}</strong> <span class="muted">(MST: ${esc(inv?.seller_tax_id || '')})</span></dd>
      <dt>Ngày lập</dt><dd>${dmy(inv?.issue_date)}</dd>
      <dt>Tổng thanh toán</dt><dd><strong>${money(inv?.gross)}</strong></dd>
      <dt>Tiền thuế GTGT</dt><dd><strong style="color:var(--a3-primary)">${money(inv?.vat)}</strong></dd>
      <dt>Chứng từ ngân hàng</dt><dd>${match ? `✓ ${match.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ'}. ${esc(match.note)}` : '<span style="color:var(--a3-warning)">Chưa ghép được chứng từ thanh toán</span>'}</dd>
      <dt>Tệp XML gốc</dt><dd class="mono small">${esc(inv?.file || '')}</dd>
    </dl>

    <div id="exposure"></div>

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
        </div>
        <div class="bar" style="margin-top:16px">
          ${button('Lưu và mở việc tiếp theo', 'primary', 'type="submit" data-next="1"')}
          ${button('Lưu quyết định này', 'secondary', 'type="submit"')}
          <span id="dmsg"></span>
        </div>
      </form>` : ''}
  </aside>`;

  bindDialog();
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
      const open = state.report.items.filter((x) => (x.status === 'AT_RISK' || x.status === 'REVIEW') && itemId(x) !== itemId(it) && !x.invoice_keys.includes(it.invoice_keys[0]));
      const after = open[open.indexOf(open.find((x) => state.report.items.indexOf(x) > index))] || open[0];
      $('#dmsg').innerHTML = '<span class="muted">Đang lưu quyết định...</span>';
      const message = $('#dmsg');
      const buttons = [...form.querySelectorAll('button[type="submit"]')];
      buttons.forEach((b) => { b.disabled = true; });
      try {
        const r = await post(`/api/workspaces/${state.ws}/decisions`, { ...d, invoice_key: it.invoice_keys[0] });
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
