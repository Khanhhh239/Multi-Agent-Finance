'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  };
  const statuses = { new: 'Chưa kiểm tra', in_review: 'Đang kiểm tra', waiting_evidence: 'Cần bổ sung bằng chứng', concluded: 'Đã kết luận' };
  const kinds = { vendor_payment: 'Thanh toán NCC', payment: 'Thanh toán NCC', customer_receipt: 'Thu tiền khách hàng', receipt: 'Thu tiền khách hàng', salary: 'Lương', payroll: 'Chi lương', adjustment: 'Điều chỉnh', advance: 'Tạm ứng' };
  const outcomes = { confirmed_risk: 'Vi phạm (Có vấn đề cần xử lý)', legitimate: 'Hợp lệ (Không phát hiện vấn đề)', inconclusive: 'Chưa đủ bằng chứng' };
  const methodStatusVi = { available: 'Khả dụng', partial: 'Có giới hạn', unavailable: 'Chưa khả dụng', not_applicable: 'Không áp dụng' };
  const branchNamesVi = { rules: 'Luật nghiệp vụ', ml: 'ML không giám sát', unsupervised_ml: 'ML không giám sát', statistics: 'Thống kê lịch sử', graph: 'Đồ thị quan hệ', supervised_lr: 'Logistic Regression có giám sát' };
  const cleanMethodLabel = m => branchNamesVi[m?.method_id] || m?.method_label_vi || m?.method_id || '';
  const nodeIcons = { transactions: '⇄', vendors: '🏪', employees: '👤', customers: '🏢', invoices: '📄', transaction_documents: '📎', bank: '🏦', phone: '☎', address: '📍' };
  const fieldLabels = {
    transaction_id: 'Mã giao dịch', record_id: 'Mã bản ghi', revision: 'Phiên bản',
    posted_at: 'Thời điểm ghi sổ', effective_at: 'Thời điểm hiệu lực', observed_at: 'Thời điểm ghi nhận nguồn',
    recorded_at: 'Thời điểm lập hồ sơ', occurred_at: 'Thời điểm phát sinh',
    txn_type: 'Loại giao dịch', kind: 'Loại nghiệp vụ', amount_vnd: 'Số tiền (VND)', currency: 'Đơn vị tiền tệ',
    vendor_id: 'Mã nhà cung cấp', customer_id: 'Mã khách hàng', employee_id: 'Mã nhân viên',
    creator_id: 'Người lập', approver_id: 'Người phê duyệt',
    name: 'Tên đối tượng', full_name: 'Họ và tên', legal_name: 'Tên pháp lý',
    invoice_id: 'Mã hóa đơn', invoice_number: 'Số hóa đơn', invoice_gross_vnd: 'Tổng hóa đơn (VND)',
    invoice_issued_at: 'Ngày hóa đơn', business_purpose: 'Nội dung nghiệp vụ', description: 'Diễn giải',
    bank_code: 'Mã ngân hàng', status: 'Trạng thái', decision: 'Quyết định', gross_vnd: 'Giá trị gốc (VND)',
    number: 'Số chứng từ', transaction_ref: 'Tham chiếu giao dịch', employee_ref: 'Tham chiếu nhân viên'
  };

  let token = '', actor = '', context = '', company = '', run = '', listing = null, selection = null, detail = null, epoch = 0, controller = null, lease = null, beat = null, dirty = false, busy = false, pendingSave = null;
  let shown = new Set(), chosenNode = '', chosenEdge = '', zoom = 1;

  const notice = text => { $('notice').textContent = text; $('notice').hidden = !text; };
  const money = v => v == null ? 'Chưa có số tiền' : /^-?\d+$/.test(String(v)) ? BigInt(v).toLocaleString('vi-VN') + ' đ' : 'Chưa có số tiền';
  const date = v => v ? new Date(v).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) : 'Chưa có thời gian';
  const score = r => r.score == null ? 'Chưa khả dụng' : r.score.toLocaleString('vi-VN', { maximumFractionDigits: 6 });
  const fmtPct = p => p == null ? 'Chưa khả dụng' : (Number(p) * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%';
  const fmtNum = v => v == null ? 'Chưa khả dụng' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 4 });
  const base = () => '/api/v1/companies/' + encodeURIComponent(company) + '/pipeline-workspace';
  const queuePath = () => base() + (run ? '/runs/' + encodeURIComponent(run) : '') + '/investigation';
  const detailPath = r => base() + '/runs/' + encodeURIComponent(r.run_id) + '/investigation/' + encodeURIComponent(r.transaction_id) + '/reviews/' + r.review_id;

  function renderRecordTable(record) {
    const entries = Object.entries(record || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');
    if (!entries.length) return el('p', 'Không có trường chi tiết bổ sung trong bản ghi nguồn.', 'muted');
    const tbl = el('table', undefined, 'kv-table');
    const tb = el('tbody');
    for (const [k, v] of entries) {
      const tr = el('tr');
      let display = v;
      if (k.endsWith('_vnd')) display = money(v);
      else if (k.endsWith('_at') && typeof v === 'string') display = date(v);
      else if (k === 'txn_type' || k === 'kind') display = kinds[v] || String(v);
      else if (typeof v === 'object') display = JSON.stringify(v);
      tr.append(el('th', fieldLabels[k] || k), el('td', String(display)));
      tb.append(tr);
    }
    tbl.append(tb);
    return tbl;
  }

  async function api(path, body) {
    const headers = { 'X-Platform': '1', 'X-Session': token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetch(mount + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
      signal: controller?.signal
    });
    const v = await res.json();
    if (!res.ok) {
      const err = Error(v.errors?.map(e => [e.message, e.action].filter(Boolean).join(' ')).join('\n') || v.error || 'Chưa thực hiện được thao tác.');
      err.status = res.status;
      throw err;
    }
    return v;
  }

  function stop() { clearInterval(beat); beat = null; lease = null; }
  const leaseKey = d => 'agent2.investigation.lease.' + [actor, context, company, d.run_id, d.review_id].join('.');
  function forgetLease(d) { try { sessionStorage.removeItem(leaseKey(d)); } catch {} }
  function startBeat(d, e) {
    clearInterval(beat);
    beat = setInterval(async () => {
      if (document.hidden || !lease) return;
      try {
        const value = await api(detailPath(d) + '/heartbeat', { lease });
        if (e === epoch) $('timer').textContent = Math.round(d.review.active_seconds + value.active_seconds) + ' giây kết nối';
      } catch (err) {
        if (e === epoch) {
          stop(); forgetLease(d); $('start').disabled = false; $('save').disabled = true;
          notice('Kết nối rà bị gián đoạn. Bấm Bắt đầu rà để tiếp tục.');
        }
      }
    }, 5000);
  }
  async function restoreLease(d, e) {
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(leaseKey(d))); } catch {}
    if (!saved || saved.revision !== d.review.revision) return;
    try {
      await api(detailPath(d) + '/heartbeat', { lease: saved.lease });
      if (e !== epoch) return;
      lease = saved.lease; $('start').disabled = true; $('save').disabled = false; startBeat(d, e);
    } catch (err) {
      if (e === epoch && err.name !== 'AbortError') { forgetLease(d); $('start').disabled = false; }
    }
  }
  function guard() { return !busy && (!dirty || confirm('Bạn có nội dung chưa lưu. Bỏ nội dung này để tiếp tục?')); }
  function remember(r) {
    const params = new URLSearchParams({ company, ...(run ? { run } : {}) });
    if (r) { params.set('transaction', r.transaction_id); params.set('review', r.review_id); params.set('source_run', r.run_id); }
    history.replaceState(null, '', location.pathname + '#' + params);
    try {
      sessionStorage.setItem('agent2.company.selection', JSON.stringify({
        version: 1, actor, context, company, page: 'pipeline-workspace',
        ...(run ? { run } : {}),
        ...(r ? { transaction: r.transaction_id, review: r.review_id, source_run: r.run_id } : {})
      }));
    } catch {}
    $('nav-queue').href = mount + '/pipeline-workspace#company=' + encodeURIComponent(company);
    $('nav-models').href = mount + '/model-management#company=' + encodeURIComponent(company);
    $('nav-fed').href = mount + '/federated-training#company=' + encodeURIComponent(company);
    $('operations').href = mount + '/pipeline-operations#company=' + encodeURIComponent(company);
  }
  function reset() {
    epoch++; controller?.abort(); controller = new AbortController(); stop();
    detail = null; dirty = false; pendingSave = null;
    $('investigation').hidden = true; $('queue').hidden = false; notice('');
  }
  function bindings(r) {
    const d = el('dl');
    for (const [name, value] of [
      ['Bản dữ liệu (Snapshot)', r.snapshot_id],
      ['Lần phân tích (Run)', r.run_id],
      ['Phiên bản phân tích (Bundle)', r.bundle_id],
      ['Thời điểm chốt nguồn', date(r.as_of)]
    ]) d.append(el('dt', name), el('dd', value));
    return d;
  }

  function renderRows() {
    const term = $('search').value.trim().toLocaleLowerCase('vi'), status = $('status').value, priority = $('priority').value;
    const rows = (listing?.rows || []).filter(r =>
      (!status || r.status === status) &&
      (!priority || (priority === 'mandatory' ? r.mandatory : priority === 'scored' ? r.score !== null : r.score === null)) &&
      (!term || [r.transaction_id, r.description, ...r.signals.map(s => s.name)].join(' ').toLocaleLowerCase('vi').includes(term))
    );
    $('rows').replaceChildren(...rows.map(r => {
      const tr = el('tr', undefined, 'tx-row');
      tr.tabIndex = 0; tr.setAttribute('role', 'button'); tr.setAttribute('aria-label', 'Xem ' + r.transaction_id);
      tr.dataset.transaction = r.transaction_id; tr.dataset.review = r.review_id;
      if (selection?.review_id === r.review_id && selection.transaction_id === r.transaction_id) tr.classList.add('selected');
      const first = el('td'); first.append(el('strong', r.transaction_id), el('small', date(r.event_at)));
      const amount = el('td'); amount.append(el('span', kinds[r.kind] || r.kind || 'Chưa rõ loại'), el('strong', money(r.amount_vnd)), el('small', r.signals.slice(0, 2).map(x => x.name).join(' · ') || r.explanation.why));
      tr.append(first, amount, el('td', score(r)), el('td', r.priority), el('td'));
      tr.lastChild.append(el('span', statuses[r.status], 'pill ' + r.status));
      const choose = () => { selection = r; renderRows(); preview(r); };
      tr.onclick = choose; tr.ondblclick = () => open(r);
      tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); } };
      return tr;
    }));
    $('empty').hidden = !!rows.length;
    $('empty').textContent = listing?.rows.length ? 'Không có giao dịch khớp bộ lọc.' : 'Chưa có giao dịch thuộc vụ đã được tiếp nhận. Dữ liệu chưa phân tích hoặc vụ đang chờ không được tự coi là hợp lệ.';
    $('counts').replaceChildren(...Object.entries(statuses).map(([key, label]) => {
      const n = el('div', undefined, 'metric');
      n.append(el('span', label), el('strong', listing?.counts[key] || 0));
      return n;
    }));
  }

  function preview(r) {
    const box = $('preview');
    box.replaceChildren(el('h2', 'Vì sao cần kiểm tra?'), el('p', r.explanation.why));
    const signals = el('ul');
    for (const s of r.signals) signals.append(el('li', s.name + (s.context_only ? ' · Chỉ là bối cảnh' : '')));
    box.append(signals, el('h3', 'Nguồn điểm'));
    const fm = r.explanation.five_methods;
    if (Array.isArray(fm) && fm.length) {
      for (const m of fm) {
        const label = cleanMethodLabel(m);
        const stTxt = methodStatusVi[m.status] || m.status;
        if (m.status === 'unavailable' || m.score == null) {
          box.append(el('p', `${label} · Chưa khả dụng (không quy về 0)`));
          continue;
        }
        if (m.method_id === 'supervised_lr' && m.probability != null) {
          const pts = m.contribution != null ? m.contribution : m.score;
          box.append(el('p', `${label} · ${stTxt} · Xác suất ${fmtPct(m.probability)} · Dự đoán ${m.prediction} · +${fmtNum(pts)} điểm`));
        } else if (m.included_in_total === false) {
          if (m.method_id === 'graph') {
            box.append(el('p', `${label} · ${stTxt} · Chỉ dùng đối chiếu bối cảnh (không cộng điểm)`));
          } else {
            box.append(el('p', `${label} · ${stTxt} · Mức bất thường ${fmtNum(m.score)} (tham khảo, không cộng vào tổng)`));
          }
        } else {
          const pts = m.contribution != null ? m.contribution : m.score;
          const weightDetail = (m.contribution != null && m.weight != null && Math.abs(m.weight - 1) > 1e-6 && Number(m.score) > 0)
            ? ` (${fmtNum(m.score)} × ${fmtNum(m.weight)})`
            : '';
          box.append(el('p', `${label} · ${stTxt} · Điểm: ${fmtNum(pts)}${weightDetail}`));
        }
      }
    } else {
      for (const b of r.explanation.branches) {
        box.append(el('p', (branchNamesVi[b.name] || b.name) + ' · ' + (methodStatusVi[b.status] || b.status)));
      }
    }
    const activeContribs = (r.explanation.contributions || []).filter(p => p.contribution != null && p.weight > 0);
    const sumFormula = activeContribs.length
      ? ' (= ' + activeContribs.map(p => `${p.name} ${fmtNum(p.contribution)}`).join(' + ') + ')'
      : '';
    box.append(el('p', 'Tổng điểm ưu tiên: ' + score(r) + sumFormula + '. Điểm ưu tiên không phải xác suất gian lận.', 'footnote'));
    const b = el('button', 'Mở điều tra'); b.id = 'open-investigation'; b.onclick = () => open(r);
    box.append(b);
    const source = el('details'); source.append(el('summary', 'Xem nguồn của giao dịch'), bindings(r));
    box.append(source);
  }

  async function load(wanted) {
    reset(); $('rows').replaceChildren(); $('counts').replaceChildren(); $('preview').replaceChildren(); $('source').textContent = '';
    const e = epoch; $('refresh').disabled = true;
    try {
      const [next, rights] = await Promise.all([api(queuePath()), api(base())]);
      if (e !== epoch) return;
      listing = next; run = listing.run_id || '';
      if (!wanted) remember();
      $('operations').hidden = !rights.can_manage;
      $('nav-models').hidden = !rights.can_manage;
      $('nav-fed').hidden = !rights.can_manage;
      $('analyze-box').hidden = !rights.can_manage;
      const isSim = listing.rows.some(r => r.source_kind === 'simulated');
      $('env-badge').textContent = isSim ? 'BẢN ĐỀ XUẤT · DỮ LIỆU MÔ PHỎNG' : 'DỮ LIỆU DOANH NGHIỆP';
      $('env-badge').hidden = !listing.rows.length;

      const selectedRun = $('run').value;
      const opt = el('option', 'Lần phân tích mới nhất của từng vụ'); opt.value = '';
      $('run').replaceChildren(opt, ...listing.runs.map(r => {
        const o = el('option', date(r.created_at) + ' · ' + r.run_id.slice(-12));
        o.value = r.run_id;
        return o;
      }));
      $('run').value = run || selectedRun;
      $('source').textContent = 'Nguồn kết quả đã lưu · ' + listing.rows.length + ' giao dịch/vụ · ' + (isSim ? 'Có dữ liệu mô phỏng · ' : '') + (listing.truncated ? 'Đang xem tối đa 50 lượt mới nhất.' : '');
      selection = listing.rows.find(r => r.review_id === selection?.review_id && r.transaction_id === selection?.transaction_id) || listing.rows[0] || null;
      renderRows();
      if (selection) preview(selection);
      else $('preview').replaceChildren(el('h2', 'Chưa có giao dịch để mở'), el('p', 'Dữ liệu được nhập tại sảnh chung. Người quản lý cần chạy và xét tiếp nhận bằng phiên bản đã phê duyệt.'));
      if (wanted) {
        const row = listing.rows.find(r => r.transaction_id === wanted.transaction && r.review_id === wanted.review && r.run_id === wanted.source_run);
        if (row) await open(row);
        else notice('Giao dịch trong liên kết không thuộc hàng đợi hiện tại. Chọn đúng doanh nghiệp và lần phân tích.');
      }
    } catch (err) {
      if (e === epoch && err.name !== 'AbortError') notice(err.message);
    } finally {
      if (e === epoch) $('refresh').disabled = false;
    }
  }

  async function open(row) {
    if (!guard()) return;
    reset(); const e = epoch; selection = row; remember(row);
    try {
      const value = await api(detailPath(row));
      if (e !== epoch) return;
      detail = value; $('refresh').disabled = false; $('queue').hidden = true; $('investigation').hidden = false;
      $('breadcrumb').textContent = 'Hàng đợi / ' + value.transaction_id;
      $('detail-title').textContent = 'Điều tra giao dịch ' + value.transaction_id;

      const cAmt = el('span', undefined, 'summary-chip'); cAmt.append(el('strong', money(value.amount_vnd)));
      const cKind = el('span', kinds[value.kind] || value.kind || 'Chưa rõ loại', 'summary-chip');
      const cDate = el('span', date(value.event_at), 'summary-chip');
      const prioLabel = value.mandatory ? 'Bắt buộc rà' : (row.priority || (value.score != null && value.score >= 15 ? 'Ưu tiên cao' : 'Cần đối chiếu'));
      const cScore = el('span', 'Tổng điểm rủi ro ' + score(value) + ' · ' + prioLabel, 'pill priority-high');
      const lrInfo = value.explanation?.supervised_lr;
      const cLr = lrInfo && lrInfo.status === 'available' && lrInfo.probability != null
        ? el('span', `Xác suất LR: ${fmtPct(lrInfo.probability)} · Dự đoán ${lrInfo.prediction} (ngưỡng ${fmtPct(lrInfo.threshold)})`, 'summary-chip lr-chip')
        : el('span', 'Xác suất LR: Chưa khả dụng', 'summary-chip lr-chip unavail');
      const cStatus = el('span', statuses[value.status], 'pill ' + value.status);
      $('tx-summary').replaceChildren(cAmt, cKind, cDate, cScore, cLr, cStatus);

      shown = new Set(value.graph.root ? [value.graph.root] : []);
      chosenNode = value.graph.root; chosenEdge = ''; zoom = 1;
      if (chosenNode) neighbors(chosenNode);
      renderGraph(); showNode(chosenNode); renderEvidence(); renderExplanation(); renderHistory(); renderRelated(); renderReview();
      restoreLease(value, e); tab('relations'); window.scrollTo(0, 0);
    } catch (err) {
      if (e === epoch && err.name !== 'AbortError') notice(err.message);
    }
  }

  function tab(id) {
    for (const n of document.querySelectorAll('.tab')) n.hidden = n.id !== id;
    for (const b of document.querySelectorAll('[data-tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === id));
  }
  for (const b of document.querySelectorAll('[data-tab]')) b.onclick = () => tab(b.dataset.tab);

  function neighbors(id) {
    for (const edge of detail.graph.edges) {
      if (edge.source === id || edge.target === id) {
        if (shown.size >= 80) break;
        shown.add(edge.source); shown.add(edge.target);
      }
    }
  }
  function svg(tag, attrs, text) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function renderGraph() {
    const graph = $('graph'); graph.replaceChildren();
    const nodes = detail.graph.nodes.filter(n => shown.has(n.id));
    if (!nodes.length) {
      $('graph-status').textContent = detail.graph.limits.join(' ') || 'Chưa có nguồn quan hệ khả dụng.';
      return;
    }
    const edges = detail.graph.edges.filter(e => shown.has(e.source) && shown.has(e.target));
    const depth = new Map([[detail.graph.root, 0]]), front = [detail.graph.root];
    for (let i = 0; i < front.length; i++) {
      const id = front[i];
      for (const e of edges) {
        const next = e.source === id ? e.target : e.target === id ? e.source : null;
        if (next && !depth.has(next)) { depth.set(next, depth.get(id) + 1); front.push(next); }
      }
    }
    const columns = new Map();
    for (const n of nodes) {
      const col = Math.min(depth.get(n.id) ?? 3, 5);
      if (!columns.has(col)) columns.set(col, []);
      columns.get(col).push(n);
    }
    const height = 580, positions = new Map();
    let nextColumn = 1;
    for (const [col, list] of [...columns].sort((a, b) => a[0] - b[0])) {
      if (col === 0) { for (const n of list) positions.set(n.id, { x: 28, y: 240 }); continue; }
      list.forEach((n, i) => positions.set(n.id, { x: 28 + (nextColumn + Math.floor(i / 4)) * 310, y: 26 + (i % 4) * 136 }));
      nextColumn += Math.ceil(list.length / 4);
    }
    const width = Math.max(980, nextColumn * 310 + 40);
    graph.setAttribute('viewBox', `0 0 ${width} ${height}`);
    graph.style.width = (width * zoom) + 'px';
    graph.style.height = (height * zoom) + 'px';

    edges.forEach((edge, idx) => {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      const isBank = edge.label.toLowerCase().includes('tài khoản');
      const cls = 'edge' + (edge.context_only ? ' context' : '') + (isBank ? ' bank-match' : '') + (edge.id === chosenEdge ? ' selected' : '');
      const g = svg('g', { class: cls, tabindex: 0, role: 'button', 'aria-label': edge.label });
      const x1 = a.x + 184, y1 = a.y + 39, x2 = b.x, y2 = b.y + 39;
      const sx1 = a.x < b.x ? x1 : a.x, sx2 = a.x < b.x ? x2 : b.x + 184;
      for (const c of ['line', 'hit']) g.append(svg('line', { x1: sx1, y1, x2: sx2, y2, class: c }));
      const mx = (sx1 + sx2) / 2, my = (y1 + y2) / 2 + ((idx % 2 === 0 ? -1 : 1) * 4);
      const lbl = edge.label.length > 24 ? edge.label.slice(0, 23) + '…' : edge.label;
      const pw = Math.max(82, lbl.length * 6.3 + 16);
      g.append(svg('rect', { x: mx - pw / 2, y: my - 11, width: pw, height: 22, rx: 11, class: 'edge-pill' }));
      g.append(svg('text', { x: mx, y: my + 4, 'text-anchor': 'middle' }, lbl));
      g.onclick = () => showEdge(edge);
      g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showEdge(edge); } };
      graph.append(g);
    });

    for (const n of nodes) {
      const p = positions.get(n.id);
      const isRoot = n.id === detail.graph.root;
      const g = svg('g', {
        class: 'node' + (isRoot ? ' root' : '') + (n.id === chosenNode ? ' selected' : ''),
        tabindex: 0, role: 'button', 'aria-label': n.kind + ' ' + n.label,
        transform: `translate(${p.x},${p.y})`, 'data-node': n.id
      });
      const icon = nodeIcons[n.table] || '●';
      const title = n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label;
      g.append(
        svg('rect', { width: 184, height: 78, rx: 11, class: 'card' }),
        svg('text', { x: 12, y: 20, class: 'node-kind' }, icon + ' ' + n.kind),
        svg('text', { x: 12, y: 40, class: 'node-title' }, title),
        svg('rect', { x: 12, y: 50, width: 76, height: 20, rx: 10, class: 'expand-chip' }),
        svg('text', { x: 50, y: 63, 'text-anchor': 'middle', class: 'node-expand' }, '+ Mở rộng')
      );
      g.onclick = () => { chosenNode = n.id; chosenEdge = ''; neighbors(n.id); renderGraph(); showNode(n.id); };
      g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); g.onclick(); } };
      graph.append(g);
    }
    $('graph-status').textContent = `Đang xem ${nodes.length}/${detail.graph.nodes.length} đối tượng. ` + (shown.size >= 80 ? 'Giới hạn 80 nút mỗi lượt xem; dùng tìm kiếm hoặc thu gọn. ' : '') + detail.graph.limits.join(' ');
  }

  function showNode(id) {
    const n = detail?.graph.nodes.find(x => x.id === id), box = $('relation-evidence');
    box.replaceChildren(el('h2', 'Căn cứ của liên kết'));
    if (!n) { box.append(el('p', 'Chưa có nguồn đối tượng khả dụng.', 'muted')); return; }
    const card = el('div', undefined, 'ev-highlight-card');
    card.append(el('h3', (nodeIcons[n.table] || '') + ' ' + n.label), el('span', n.kind + ' · Dữ kiện trong bản dữ liệu', 'pill'));
    box.append(card, el('div', '⚠ Chưa xác minh chứng từ gốc', 'warn-banner'));
    const record = el('details');
    record.append(el('summary', 'Xem bản ghi nguồn'), renderRecordTable(n.record));
    box.append(record);
    const expand = el('button', 'Mở rộng quan hệ của đối tượng'); expand.id = 'expand-node';
    expand.onclick = () => { neighbors(id); chosenNode = id; renderGraph(); };
    box.append(expand);
    const related = detail.graph.edges.filter(e => e.source === id || e.target === id);
    const links = el('details');
    links.append(el('summary', 'Các liên kết của đối tượng (' + related.length + ')'));
    links.open = related.length <= 6;
    for (const e of related) {
      const b = el('button', e.label, 'secondary'); b.onclick = () => showEdge(e);
      const wrap = el('p'); wrap.append(b); links.append(wrap);
    }
    box.append(links);
    if (detail.explanation?.question) {
      const q = el('div', undefined, 'question-card');
      q.append(el('strong', 'Câu hỏi cần làm rõ'), el('span', detail.explanation.question));
      box.append(q);
    }
  }

  function showEdge(edge) {
    chosenEdge = edge.id; chosenNode = ''; renderGraph();
    const box = $('relation-evidence');
    const source = detail.graph.nodes.find(n => n.id === edge.source), target = detail.graph.nodes.find(n => n.id === edge.target);
    const card = el('div', undefined, 'ev-highlight-card');
    card.append(
      el('h3', edge.label),
      el('span', edge.context_only ? 'Liên kết bối cảnh · cần đối chiếu' : 'Dữ kiện trong bản dữ liệu', 'pill')
    );
    box.replaceChildren(el('h2', 'Căn cứ của liên kết'), card);
    const d = el('dl');
    d.append(el('dt', 'Đối tượng liên quan'), el('dd', (source?.label || '') + ' ↔ ' + (target?.label || '')));
    for (const [k, v] of Object.entries(edge.evidence)) {
      const lbl = ({ table: 'Bảng nguồn', record_id: 'Mã bản ghi', revision: 'Phiên bản', known_at: 'Nguồn được biết tại', sha256: 'Checksum', snapshot_id: 'Bản dữ liệu', source_kind: 'Loại nguồn', original_verified: 'Chứng từ gốc đã xác minh' }[k] || k);
      const val = v === false ? 'Chưa' : k === 'known_at' ? date(v) : k === 'source_kind' ? (v === 'simulated' ? 'Dữ liệu mô phỏng' : 'Nguồn xuất dữ liệu') : String(v);
      d.append(el('dt', lbl), el('dd', val));
    }
    box.append(d, el('div', '⚠ Chưa xác minh chứng từ gốc', 'warn-banner'));
    const q = el('div', undefined, 'question-card');
    q.append(el('strong', 'Câu hỏi cần làm rõ'), el('span', detail.explanation?.question || 'Liên kết này chưa chứng minh sai phạm. Cần đối chiếu hồ sơ, ủy quyền và chứng từ gốc.'));
    box.append(q);
  }

  function renderRelated() {
    const box = $('related'), inline = $('inline-related');
    box.replaceChildren(el('h2', 'Giao dịch liên quan trong nguồn đã chốt'));
    const makeTable = () => {
      const tbl = el('table');
      tbl.innerHTML = '<thead><tr><th>Mã giao dịch</th><th>Vai trò</th><th>Số tiền</th><th>Loại</th><th>Thời điểm</th></tr></thead>';
      const tb = el('tbody');
      // Current investigated row first
      const trSelf = el('tr', undefined, 'selected');
      trSelf.append(
        el('td', detail.transaction_id),
        (() => { const td = el('td'); td.append(el('span', 'Ứng viên (đang điều tra)', 'pill')); return td; })(),
        el('td', money(detail.amount_vnd)),
        el('td', kinds[detail.kind] || detail.kind || '—'),
        el('td', date(detail.event_at))
      );
      tb.append(trSelf);
      for (const tx of detail.related_transactions.slice(0, 5)) {
        const id = tx.transaction_id || tx.record_id;
        const tr = el('tr', undefined, 'tx-row');
        tr.append(
          el('td', id),
          (() => { const td = el('td'); td.append(el('span', 'Lịch sử (tham chiếu)', 'pill')); return td; })(),
          el('td', money(tx.amount_vnd)),
          el('td', kinds[tx.txn_type || tx.kind] || tx.txn_type || tx.kind || '—'),
          el('td', date(tx.posted_at || tx.effective_at))
        );
        tr.onclick = () => {
          shown.add(tx.graph_node); chosenNode = tx.graph_node; neighbors(chosenNode);
          renderGraph(); showNode(chosenNode); tab('relations');
        };
        tb.append(tr);
      }
      tbl.append(tb);
      return tbl;
    };

    inline.replaceChildren(el('h3', `Giao dịch liên quan (${1 + detail.related_transactions.length})`), makeTable());
    if (detail.related_transactions.length > 5) {
      const more = el('button', `Xem tất cả ${detail.related_transactions.length} giao dịch liên quan →`, 'secondary');
      more.style.marginTop = '10px';
      more.onclick = () => tab('related');
      inline.append(more);
    }

    for (const tx of detail.related_transactions) {
      const id = tx.transaction_id || tx.record_id;
      const b = el('button', id + ' · ' + money(tx.amount_vnd) + ' · ' + date(tx.posted_at || tx.effective_at), 'secondary related-button');
      b.onclick = () => { shown.add(tx.graph_node); chosenNode = tx.graph_node; neighbors(chosenNode); renderGraph(); showNode(chosenNode); tab('relations'); };
      const wrap = el('p'); wrap.append(b); box.append(wrap);
    }
    if (!detail.related_transactions.length) box.append(el('p', 'Chưa có giao dịch liên quan trong phạm vi nguồn và thời điểm này.', 'muted'));
    box.append(el('p', 'Các giao dịch liên quan không tự trở thành ứng viên hoặc được cộng vào điểm.', 'footnote'));
  }

  function renderEvidence() {
    const box = $('evidence');
    box.replaceChildren(el('h2', 'Bằng chứng của phiếu đã khóa'));
    const tx = el('details');
    tx.open = true;
    tx.append(el('summary', 'Thông tin giao dịch trong nguồn tại thời điểm điều tra'), renderRecordTable(detail.transaction));
    box.append(tx);
    for (const e of detail.evidence) {
      const d = el('details');
      d.append(
        el('summary', e.table + ' · ' + (e.record.transaction_id || e.record.record_id || e.record.invoice_id || e.evidence_id)),
        el('p', e.source_kind === 'simulated' ? 'Dữ liệu mô phỏng · chưa xác minh chứng từ gốc' : 'Bản ghi nguồn · chưa xác minh chứng từ gốc', 'source-badge'),
        renderRecordTable(e.record)
      );
      box.append(d);
    }
  }

  function renderExplanation() {
    const box = $('explanation');
    box.replaceChildren(
      el('h2', 'Giải thích tổng điểm rủi ro ' + score(detail)),
      el('p', detail.explanation.basis, 'source-badge'),
      el('p', detail.explanation.why)
    );

    // 1. Unified 5-Method Score Table (Rules, Statistics, Graph, Unsupervised ML, Supervised LR)
    const fiveMethods = detail.explanation.five_methods || [];
    if (fiveMethods.length) {
      const fmCard = el('div', undefined, 'contrib-card');
      fmCard.id = 'five-methods-card';
      fmCard.append(el('h3', 'Điểm từng phương pháp phát hiện'));
      const scroll = el('div', undefined, 'table-scroll');
      const tbl = el('table', undefined, 'five-method-table');
      tbl.innerHTML = '<thead><tr><th>Phương pháp</th><th>Trạng thái</th><th>Điểm cộng vào tổng</th><th>Xác suất / Ghi chú</th><th>Phiên bản mô hình / mạch</th></tr></thead>';
      const tb = el('tbody');
      for (const m of fiveMethods) {
        const tr = el('tr');
        const stCls = m.status === 'available' ? 'available' : m.status === 'partial' ? 'partial' : 'unavailable';
        const tdSt = el('td');
        tdSt.append(el('span', methodStatusVi[m.status] || m.status, 'method-pill ' + stCls));

        let scoreTxt;
        if (m.status === 'unavailable' || m.score == null) {
          scoreTxt = 'Chưa khả dụng (không quy về 0)';
        } else if (m.included_in_total === false) {
          scoreTxt = m.method_id === 'graph'
            ? 'Không cộng điểm (bối cảnh)'
            : `Không cộng tổng (mức ${fmtNum(m.score)})`;
        } else {
          const pts = m.contribution != null ? m.contribution : m.score;
          scoreTxt = (m.contribution != null && m.weight != null && Math.abs(m.weight - 1) > 1e-6 && Number(m.score) > 0)
            ? `${fmtNum(pts)} (${fmtNum(m.score)} × ${fmtNum(m.weight)})`
            : fmtNum(pts);
        }

        let noteTxt = '—';
        if (m.method_id === 'supervised_lr') {
          if (m.status === 'available' && m.probability != null) {
            noteTxt = `Xác suất ${fmtPct(m.probability)} · Ngưỡng ${fmtPct(m.threshold)} · Dự đoán ${m.prediction}`;
          } else {
            noteTxt = m.message || 'Chưa có mô hình Logistic Regression được kích hoạt.';
          }
        } else if (m.method_id === 'rules') {
          const hits = m.confidence_metadata?.hit_count ?? 0;
          const sigCount = (detail.signals || []).filter(s => !s.context_only).length;
          const totalHits = Math.max(hits, sigCount);
          noteTxt = totalHits ? `Kích hoạt ${totalHits} dấu hiệu luật` : 'Không có luật kích hoạt';
        } else if (m.method_id === 'statistics') {
          noteTxt = m.status === 'available'
            ? `Mức bất thường so với lịch sử (${fmtPct(m.score)}), dùng để tham khảo`
            : 'Chưa đủ dữ liệu lịch sử để so sánh';
        } else if (m.method_id === 'graph') {
          const links = m.confidence_metadata?.link_count ?? 0;
          noteTxt = m.status === 'unavailable' ? 'Chưa đủ nguồn đối chiếu quan hệ' : `Đối chiếu quan hệ (${links} liên kết; không tự cộng điểm)`;
        } else if (m.method_id === 'unsupervised_ml') {
          noteTxt = m.status === 'available'
            ? `Hạng bất thường không giám sát (không phải xác suất)`
            : 'Chưa có mô hình không giám sát phù hợp';
        }

        const verParts = [m.model_version, m.circuit_version ? `Mạch ${m.circuit_version}` : null].filter(Boolean);
        tr.append(
          el('td', cleanMethodLabel(m)),
          tdSt,
          el('td', scoreTxt),
          el('td', noteTxt),
          el('td', verParts.join(' · ') || '—', 'mono-tag')
        );
        tb.append(tr);
      }
      tbl.append(tb);
      scroll.append(tbl);
      fmCard.append(scroll);
      box.append(fmCard);
    }

    // 2. Supervised Logistic Regression (5th Method) Detail Card
    const lr = detail.explanation.supervised_lr;
    if (lr) {
      const lrCard = el('div', undefined, 'contrib-card');
      lrCard.id = 'lr-explanation-card';
      lrCard.append(el('h3', 'Logistic Regression có giám sát (Phương pháp thứ 5)'));
      if (lr.status === 'available') {
        const kpis = el('div', undefined, 'lr-kpi-strip');
        for (const [label, val] of [
          ['Xác suất P(lớp 1)', fmtPct(lr.probability)],
          ['Ngưỡng validation', fmtPct(lr.threshold)],
          ['Dự đoán nhị phân', lr.prediction === 1 ? '1 (Cần rà soát)' : '0 (Dưới ngưỡng)'],
          ['Điểm quy đổi hiệu lực', `${fmtNum(lr.score)} điểm`],
        ]) {
          const item = el('div', undefined, 'lr-kpi-item');
          item.append(el('span', label), el('strong', val));
          kpis.append(item);
        }
        lrCard.append(kpis);

        if (lr.deduplication) {
          const dd = lr.deduplication;
          const ddNote = dd.overlap_applied
            ? `Chống cộng trùng dấu hiệu (${(dd.overlapping_rules || []).join(', ')}): điểm LR gốc ${fmtNum(dd.raw_lr_points)} giảm ${fmtNum(dd.overlap_discount_points)} → còn ${fmtNum(dd.effective_lr_points)} điểm. ${dd.note || ''}`
            : `Không có luật trùng lặp (A6/C2) kích hoạt cùng đặc trưng LR; giữ nguyên điểm quy đổi ${fmtNum(dd.effective_lr_points)} điểm.`;
          lrCard.append(el('div', ddNote, 'lr-dedup-note'));
        }

        const cm = lr.confidence_metadata || {};
        const valMeta = cm.validation_precision != null
          ? `Hiệu chuẩn theo validation: Precision=${fmtPct(cm.validation_precision)}, Recall=${fmtPct(cm.validation_recall)}, F1=${fmtPct(cm.validation_f1)} · Hệ số tin cậy=${fmtNum(cm.quality_factor)}. `
          : '';
        const backendLabel = cm.inference_backend === 'local_approved_model'
          ? 'Suy luận local trên mô hình đã phê duyệt'
          : (cm.inference_backend || 'local');
        lrCard.append(el('p', `${valMeta}${cm.quality_note || ''} · Môi trường: ${backendLabel} · Phiên bản: ${lr.model_version || '—'}${lr.circuit_version ? ` (${lr.circuit_version})` : ''}`, 'muted'));

        if (Array.isArray(lr.explanation_evidence) && lr.explanation_evidence.length) {
          const evScroll = el('div', undefined, 'table-scroll');
          const evTbl = el('table', undefined, 'five-method-table');
          evTbl.innerHTML = '<thead><tr><th>Đặc trưng đầu vào LR</th><th>Giá trị</th><th>Trọng số</th><th>Đóng góp logit</th></tr></thead>';
          const evTb = el('tbody');
          for (const ev of lr.explanation_evidence) {
            const tr = el('tr');
            tr.append(
              el('td', ev.label_vi || ev.feature),
              el('td', String(ev.value)),
              el('td', String(ev.weight)),
              el('td', String(ev.logit_contribution))
            );
            evTb.append(tr);
          }
          evTbl.append(evTb);
          evScroll.append(evTbl);
          lrCard.append(evScroll);
        }
      } else {
        lrCard.append(
          el('p', `Trạng thái: Chưa khả dụng (${lr.error_code || 'LR_UNAVAILABLE'}) — ${lr.message || 'Mô hình LR chưa sẵn sàng cho giao dịch này.'}`),
          el('p', 'Hệ thống giữ nguyên trạng thái chưa khả dụng và tuyệt đối không quy về 0 điểm.', 'muted')
        );
      }
      box.append(lrCard);
    }

    if (detail.signals?.length) {
      const sigCard = el('div', undefined, 'contrib-card');
      sigCard.append(el('h3', 'Các dấu hiệu đáng nghi (Luật nghiệp vụ)'));
      for (const s of detail.signals) {
        sigCard.append(el('p', `${s.rule_id} · ${s.name}` + (s.context_only ? ' · Bối cảnh, không tự cộng điểm' : (s.points != null ? ` (+${s.points} điểm)` : ''))));
      }
      box.append(sigCard);
    }

    const d = el('dl');
    const rawLabels = {
      rule_score: 'Điểm luật trước phối hợp',
      ml_score: 'Điểm ML trước phối hợp',
      lr_score: 'Điểm LR sau giảm trùng lắp',
    };
    for (const [k, v] of Object.entries(detail.explanation.raw_components)) {
      d.append(el('dt', rawLabels[k] || k), el('dd', v == null ? 'Chưa có' : String(v)));
    }
    box.append(d);

    // Visual contribution bars
    const cCard = el('div', undefined, 'contrib-card');
    cCard.append(el('h3', 'Đóng góp vào tổng điểm rủi ro đã lưu'));
    const totalVal = Math.max(detail.score || 0, 1e-6);
    for (const p of detail.explanation.contributions || []) {
      const pct = p.contribution != null ? Math.min(100, Math.max(4, Math.round((p.contribution / totalVal) * 100))) : 0;
      const row = el('div', undefined, 'contrib-row');
      row.append(
        el('strong', p.name),
        el('span', p.contribution == null ? 'Chưa đủ dữ liệu phân rã' : `${p.raw_score} × ${p.weight} = ${p.contribution} điểm`)
      );
      const track = el('div', undefined, 'bar-track');
      const barCls = p.name.includes('Logistic Regression') ? ' lr' : p.name.includes('ML') ? ' ml' : '';
      const fill = el('div', undefined, 'bar-fill' + barCls);
      fill.style.width = pct + '%';
      track.append(fill);
      cCard.append(row, track);
    }
    if (!detail.explanation.components_reconcile) {
      cCard.append(el('p', 'Bảng phân rã chưa đủ để đối chiếu tổng. Điểm hiển thị vẫn là điểm giao dịch đã được khóa; không tự suy phần còn thiếu.', 'muted'));
    }
    box.append(cCard);

    if (detail.explanation.ml_attributions?.length) {
      const aCard = el('div', undefined, 'contrib-card');
      aCard.append(el('h3', 'Đặc trưng đóng góp chính vào điểm bất thường ML không giám sát'));
      for (const f of detail.explanation.ml_attributions) {
        const pct = Math.round((f.share || 0) * 100);
        const row = el('div', undefined, 'contrib-row');
        row.append(el('span', `${f.label_vi} (${f.group})`), el('strong', pct + '%'));
        const track = el('div', undefined, 'bar-track');
        const fill = el('div', undefined, 'bar-fill ml'); fill.style.width = Math.max(5, pct) + '%';
        track.append(fill);
        aCard.append(row, track);
      }
      box.append(aCard);
    }

    // 3. Explicit Unavailable / Unsupported Methods Disclosure (NEVER merged into score 0)
    const unavailList = detail.explanation.unavailable_methods || [];
    const unavailCard = el('div', undefined, 'unavailable-card');
    unavailCard.id = 'unavailable-methods-card';
    unavailCard.append(el('h3', 'Trạng thái các phương pháp chưa hỗ trợ / chưa khả dụng'));
    if (unavailList.length) {
      for (const u of unavailList) {
        unavailCard.append(el('p', `• ${u.method_label_vi || u.method_id} [${u.error_code || 'UNAVAILABLE'}]: ${u.message || 'Chưa khả dụng cho giao dịch này.'}`));
      }
      unavailCard.append(el('p', 'Nguyên tắc an toàn: phương pháp chưa khả dụng luôn hiển thị trạng thái unavailable và tuyệt đối không bị gộp thành 0 điểm.', 'muted'));
    } else {
      unavailCard.append(el('p', 'Tất cả 5 phương pháp phát hiện (Luật, Thống kê, Đồ thị, ML không giám sát, LR có giám sát) đều đang khả dụng cho giao dịch này.', 'muted'));
    }
    for (const gap of detail.explanation.limitations) unavailCard.append(el('p', '• ' + gap, 'muted'));
    box.append(unavailCard);

    const trace = el('details');
    trace.open = Boolean(detail.explanation.lr_model_version || detail.explanation.model_version_tag);
    trace.append(el('summary', 'Truy vết phiên bản mô hình, mạch FHE, cấu hình và dữ liệu đã dùng'), bindings(detail));
    if (detail.model_trace?.length) {
      const mtScroll = el('div', undefined, 'table-scroll');
      const mtbl = el('table', undefined, 'five-method-table');
      mtbl.innerHTML = '<thead><tr><th>Phương pháp / Mô hình</th><th>Phiên bản &amp; Mạch / Artifact</th><th>Trạng thái</th></tr></thead>';
      const mtb = el('tbody');
      for (const m of detail.model_trace) {
        const tr = el('tr');
        const tag = [
          m.version_tag || m.model_version,
          m.circuit_version ? `mạch ${m.circuit_version}` : null,
          m.artifact_id ? m.artifact_id.slice(0, 18) + '…' : null,
          m.error_code ? `[${m.error_code}]` : null,
        ].filter(Boolean).join(' · ') || '—';
        tr.append(el('td', m.method_id), el('td', tag, 'mono-tag'), el('td', methodStatusVi[m.status] || m.status));
        mtb.append(tr);
      }
      mtbl.append(mtb);
      mtScroll.append(mtbl);
      trace.append(mtScroll);
    }
    box.append(trace);
  }

  function renderHistory() {
    const box = $('history');
    box.replaceChildren(el('h2', 'Lịch sử thao tác và kết quả đã lưu'));
    for (const event of detail.workflow_history) {
      box.append(el('p', date(event.at) + ' · ' + event.actor + ' · ' + ({ started: 'Bắt đầu rà', saved: 'Lưu kết quả', attached: 'Đính kèm bằng chứng' }[event.action] || event.action), 'event'));
    }
    for (const event of detail.review.history) {
      const d = el('details');
      d.append(
        el('summary', 'Kết quả phiên bản ' + event.revision + ' · ' + date(new Date(event.at * 1000).toISOString()) + ' · ' + event.actor_id),
        el('p', outcomes[event.feedback.outcome]),
        el('p', event.feedback.explanation),
        el('p', 'Hành động: ' + event.feedback.action)
      );
      box.append(d);
    }
    if (!detail.workflow_history.length && !detail.review.history.length) box.append(el('p', 'Chưa có thao tác đã lưu cho phiếu này.', 'muted'));
  }

  function renderReview() {
    const old = detail.review.feedback;
    $('outcome').value = old?.outcome || '';
    $('notes').value = old?.explanation || '';
    $('action').value = old?.action || '';
    $('missing').value = old?.missing_materials || '';
    $('checks').checked = !!old?.checks_completed;
    $('save').disabled = true; $('start').disabled = false; $('review-fields').disabled = false;
    $('save-status').textContent = '';
    $('timer').textContent = Math.round(detail.review.active_seconds) + ' giây đã lưu';
    $('review-status').textContent = statuses[detail.status];
    $('review-status').className = 'pill ' + detail.status;
    $('review-context').textContent = 'Phiếu xử lý dùng chung cho các giao dịch cùng vụ · ' + detail.case_id;
    $('evidence-selection').replaceChildren(el('h3', 'Chọn những căn cứ bạn đã đối chiếu'));
    for (const e of [...detail.evidence, ...detail.review.attachments.map(a => ({ evidence_id: a.id, table: a.name, record: {} }))]) {
      const l = el('label', undefined, 'check'), c = el('input');
      c.type = 'checkbox'; c.value = e.evidence_id; c.checked = !!old?.evidence_ids.includes(e.evidence_id);
      l.append(c, el('span', e.table + ' · ' + (e.record.transaction_id || e.record.record_id || e.evidence_id)));
      $('evidence-selection').append(l);
    }
    attachments();
  }

  function attachments() {
    const box = $('attachment-list'); box.replaceChildren();
    for (const a of detail.review.attachments) {
      const b = el('button', a.name + ' · chưa xác minh', 'secondary');
      b.onclick = async () => {
        try {
          const f = await api(detail.review_path + '/attachments/' + a.id);
          const bytes = Uint8Array.from(atob(f.content), c => c.charCodeAt(0));
          const u = URL.createObjectURL(new Blob([bytes])), link = el('a');
          link.href = u; link.download = f.name; link.click();
          setTimeout(() => URL.revokeObjectURL(u), 1000);
        } catch (e) { notice(e.message); }
      };
      const wrap = el('p'); wrap.append(b); box.append(wrap);
    }
  }

  $('review-form').oninput = () => { dirty = true; };
  $('review-form').onsubmit = async event => {
    event.preventDefault();
    if (busy || !detail || (!lease && !pendingSave)) return;
    const d = detail, e = epoch;
    if (!pendingSave) {
      pendingSave = {
        expected_revision: d.review.revision, lease, request_id: crypto.randomUUID(),
        feedback: {
          outcome: $('outcome').value, usefulness: 'not_assessed',
          explanation: $('notes').value, action: $('action').value, missing_materials: $('missing').value,
          evidence_ids: [...document.querySelectorAll('#evidence-selection input:checked')].map(n => n.value),
          checks_completed: $('checks').checked
        }
      };
    }
    busy = true; $('save').disabled = true; $('review-fields').disabled = true;
    try {
      const saved = await api(detailPath(d) + '/save', pendingSave);
      if (e !== epoch) return;
      d.review = saved; pendingSave = null; dirty = false; forgetLease(d); stop(); notice('');
      $('save-status').textContent = 'Đã lưu kết quả trên server · phiên bản ' + saved.revision;
      const latest = await api(detailPath(d));
      if (e === epoch) {
        detail = latest; renderHistory();
        $('review-status').textContent = statuses[detail.status];
        $('review-status').className = 'pill ' + detail.status;
        $('start').disabled = false;
      }
    } catch (err) {
      if (e === epoch) {
        notice(err.message);
        if (err.status) { pendingSave = null; $('review-fields').disabled = false; }
        if (err.status === 409) { stop(); $('start').disabled = false; } else $('save').disabled = false;
        $('save-status').textContent = err.status ? 'Kiểm tra nội dung hoặc tải lại phiếu trước khi lưu.' : 'Mất phản hồi. Bấm lưu lại để gửi đúng yêu cầu cũ.';
      }
    } finally { busy = false; }
  };

  $('start').onclick = async () => {
    if (busy || !detail) return;
    const d = detail, e = epoch; $('start').disabled = true;
    try {
      const value = await api(detailPath(d) + '/start', { request_id: crypto.randomUUID() });
      if (e !== epoch) return;
      stop(); notice(''); lease = value.lease;
      try { sessionStorage.setItem(leaseKey(d), JSON.stringify({ lease, revision: d.review.revision })); } catch {}
      $('save').disabled = false; $('review-fields').disabled = false;
      $('review-status').textContent = 'Đang kiểm tra'; $('review-status').className = 'pill in_review';
      $('save-status').textContent = 'Đối chiếu căn cứ rồi ghi kết quả.';
      startBeat(d, e);
    } catch (err) {
      if (e === epoch) { notice(err.message); $('start').disabled = false; }
    }
  };

  $('attach').onclick = async () => {
    const file = $('file').files[0];
    if (!file || !detail || busy) { $('attachment-status').textContent = 'Chọn một tệp trước khi lưu.'; return; }
    if (file.size > 2 * 1024 * 1024) { $('attachment-status').textContent = 'Tệp tối đa 2 MB. Chọn tệp nhỏ hơn.'; return; }
    const d = detail, e = epoch; busy = true; $('attach').disabled = true;
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      await api(detailPath(d) + '/attachments', { name: file.name, content: btoa(binary) });
      if (e !== epoch) return;
      const latest = await api(detailPath(d));
      if (e !== epoch) return;
      d.review.attachments = latest.review.attachments; detail.review.attachments = latest.review.attachments;
      detail.workflow_history = latest.workflow_history;
      attachments(); renderHistory();
      const existing = new Set([...document.querySelectorAll('#evidence-selection input')].map(n => n.value));
      for (const a of latest.review.attachments) {
        if (!existing.has(a.id)) {
          const l = el('label', undefined, 'check'), c = el('input');
          c.type = 'checkbox'; c.value = a.id;
          l.append(c, el('span', a.name + ' · chưa xác minh'));
          $('evidence-selection').append(l);
        }
      }
      $('attachment-status').textContent = 'Đã lưu tệp trên server; tệp chưa được xác minh.';
      $('file').value = '';
    } catch (err) {
      if (e === epoch) $('attachment-status').textContent = err.message + ' Có thể gửi lại cùng tệp; server chống tạo trùng.';
    } finally { busy = false; $('attach').disabled = false; }
  };

  $('zoom-in').onclick = () => { zoom = Math.min(3, zoom + .2); renderGraph(); };
  $('zoom-out').onclick = () => { zoom = Math.max(.5, zoom - .2); renderGraph(); };
  $('fit').onclick = () => { zoom = 1; shown = new Set(detail.graph.root ? [detail.graph.root] : []); if (detail.graph.root) neighbors(detail.graph.root); renderGraph(); };
  $('find-node').onclick = () => {
    const q = $('graph-search').value.trim().toLocaleLowerCase('vi');
    if (!q) return;
    const n = detail.graph.nodes.find(x => [x.label, x.record_id].join(' ').toLocaleLowerCase('vi').includes(q));
    if (!n) { $('graph-status').textContent = 'Không tìm thấy đối tượng trong nguồn quan hệ đã khóa.'; return; }
    shown = new Set([detail.graph.root, n.id]); neighbors(n.id); chosenNode = n.id; renderGraph(); showNode(n.id);
  };
  $('back').onclick = () => { if (guard()) { remember(); load(); } };
  $('refresh').onclick = () => { if (guard()) load(); };
  $('company').onchange = () => { if (!guard()) { $('company').value = company; return; } company = $('company').value; run = ''; selection = null; remember(); load(); };
  $('analyze').onclick = async () => {
    if (!guard()) return;
    const btn = $('analyze'), st = $('analyze-status');
    btn.disabled = true; st.textContent = 'Đang phân tích dữ liệu mới nhất…';
    try {
      const out = await api('/api/v1/companies/' + encodeURIComponent(company) + '/model-lifecycle/analyze', { request_id: 'ui-analyze-' + crypto.randomUUID() });
      st.textContent = `Hoàn tất: ${out.admitted_cases} giao dịch cần kiểm tra trên ${out.total_cases} trường hợp.`;
      run = ''; await init();
    } catch (err) { st.textContent = ''; $('notice').textContent = err.message; $('notice').hidden = false; }
    finally { btn.disabled = false; }
  };
  $('run').onchange = () => { if (!guard()) { $('run').value = run; return; } run = $('run').value; remember(); load(); };
  for (const id of ['search', 'status', 'priority']) $(id).oninput = renderRows;

  async function init() {
    reset(); token = sessionStorage.getItem('kt-session') || '';
    if (!mount || !token) { notice('Mở Agent2 từ Portal và đăng nhập để tiếp tục.'); return; }
    try {
      const ctx = await api('/api/v1/ui/context');
      actor = ctx.actor_id; context = ctx.context_id || '';
      const hash = new URLSearchParams(location.hash.slice(1));
      company = ctx.companies.includes(hash.get('company')) ? hash.get('company') : ctx.companies[0] || '';
      $('company').replaceChildren(...ctx.companies.map(id => { const o = el('option', id); o.value = id; return o; }));
      $('company').value = company; $('company').disabled = !company;
      run = '';  // một lần đăng nhập = một doanh nghiệp; luôn mở lần phân tích mới nhất
      if (!company) { notice('Chưa được cấp quyền doanh nghiệp.'); return; }
      const old = await api(base());
      $('operations').hidden = !old.can_manage;
      $('nav-models').hidden = !old.can_manage;
      $('nav-fed').hidden = !old.can_manage;
      $('analyze-box').hidden = !old.can_manage;
      const wanted = hash.get('transaction') ? { transaction: hash.get('transaction'), review: hash.get('review'), source_run: hash.get('source_run') } : null;
      remember(wanted ? { transaction_id: wanted.transaction, review_id: wanted.review, run_id: wanted.source_run } : null);
      await load(wanted);
    } catch (err) { notice(err.message); }
  }

  window.addEventListener('beforeunload', e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('pagehide', stop);
  window.addEventListener('focus', () => { if ((sessionStorage.getItem('kt-session') || '') !== token) { if (guard()) init(); } });
  init();
})();
