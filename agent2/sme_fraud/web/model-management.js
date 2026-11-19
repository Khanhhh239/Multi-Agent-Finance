'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  };

  const STATUS_VI = {
    active: ['Đang dùng', 'status-active'],
    shadow: ['Chạy thử', 'status-shadow'],
    pending_approval: ['Chờ phê duyệt', 'status-pending'],
    evaluated: ['Cần đối chiếu', 'status-review'],
    trained: ['Chờ đánh giá', 'status-pending'],
    superseded: ['Đã thay thế', 'status-superseded'],
    rolled_back: ['Đã hoàn nguyên', 'status-rolled_back'],
  };

  let token = '', actor = '', context = '', company = '';
  let overviewData = null, profileData = null;
  let selectedVersionId = null, selectedAlgo = 'isolation_forest', approvalMode = 'shadow', currentStep = 4;
  let lrStatusData = null, lrPreviewData = null, lrMode = 'fhe_cloud_ciphertext', selectedLrJobId = null;
  let lrRegistryData = null, selectedLrRegId = null;
  let busy = false;

  const setNotice = msg => { $('notice').textContent = msg || ''; $('notice').hidden = !msg; };
  const setSuccess = msg => { $('success-banner').textContent = msg || ''; $('success-banner').hidden = !msg; };

  function fmtDateTime(iso) {
    if (!iso) return 'Chưa rõ';
    try {
      const d = new Date(iso);
      return d.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return String(iso); }
  }
  function fmtDate(iso) {
    if (!iso) return 'Chưa rõ';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch { return String(iso).slice(0, 10); }
  }
  function fmtSec(sec) {
    if (sec === null || sec === undefined) return '—';
    return Number(sec).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 2 }) + ' giây';
  }
  function statusPill(status) {
    const [label, cls] = STATUS_VI[status] || [status || 'Chưa rõ', 'status-idle'];
    return el('span', label, 'status-pill ' + cls);
  }

  function remember() {
    const params = new URLSearchParams({ company });
    history.replaceState(null, '', location.pathname + '#' + params);
    try {
      sessionStorage.setItem('agent2.company.selection', JSON.stringify({
        version: 1, actor, context, company, page: 'model-management'
      }));
    } catch {}
    $('nav-queue').href = mount + '/pipeline-workspace#company=' + encodeURIComponent(company);
    $('nav-models').href = mount + '/model-management#company=' + encodeURIComponent(company);
    $('nav-fed').href = mount + '/federated-training#company=' + encodeURIComponent(company);
  }

  async function api(path, body, idempotencyKey) {
    const headers = { 'X-Platform': '1', 'X-Session': token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    const res = await fetch(mount + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await res.json();
    if (!res.ok) {
      const msg = data.errors?.map(e => [e.message, e.action].filter(Boolean).join(' ')).join('\n') || data.error || 'Chưa thực hiện được thao tác.';
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  const basePath = () => '/api/v1/companies/' + encodeURIComponent(company) + '/model-lifecycle';

  function setStep(step) {
    currentStep = Number(step);
    for (const btn of document.querySelectorAll('.step-pill')) {
      const active = Number(btn.dataset.step) === currentStep;
      btn.classList.toggle('active', active);
      if (active) btn.setAttribute('aria-current', 'step');
      else btn.removeAttribute('aria-current');
    }
    $('step-panel-2').hidden = currentStep !== 2;
    $('step-panel-3').hidden = currentStep !== 3;
    $('step-panel-45').hidden = !(currentStep === 4 || currentStep === 5);
    if ((currentStep === 2 || currentStep === 3) && !profileData && overviewData?.shared_data?.primary_snapshot) {
      loadProfile(overviewData.shared_data.primary_snapshot.snapshot_id);
    }
    if (currentStep === 5) {
      $('approval-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function populateSnapshotSelect(selectEl, snapshots, preferredId) {
    selectEl.replaceChildren(...snapshots.map(s => {
      const tag = s.native_35_rules ? '35 luật' : 'Chuẩn sảnh';
      const sim = s.is_simulated ? ' · mô phỏng' : '';
      const o = el('option', `${s.snapshot_id.slice(0, 14)}… · ${s.transaction_count} GD (${s.period_label} · ${tag}${sim})`);
      o.value = s.snapshot_id;
      return o;
    }));
    if (preferredId && snapshots.some(s => s.snapshot_id === preferredId)) {
      selectEl.value = preferredId;
    }
  }

  function renderHero() {
    const ov = overviewData;
    const act = ov.active_version;
    const badge = $('source-env-badge');
    const isSim = ov.shared_data.primary_snapshot?.is_simulated !== false;
    badge.textContent = isSim ? 'BẢN ĐỀ XUẤT · DỮ LIỆU MÔ PHỎNG' : 'DỮ LIỆU DOANH NGHIỆP';
    badge.hidden = false;

    $('role-badge').textContent = ov.can_fit ? '🛡 Quyền quản trị mô hình' : '👁 Chỉ xem (cần quyền model.fit để duyệt)';

    if (act) {
      const [lbl, cls] = STATUS_VI[act.status] || ['Đang sử dụng', 'status-active'];
      $('active-status-pill').textContent = (act.status === 'active' ? '✓ Đang sử dụng' : lbl);
      $('active-status-pill').className = 'status-pill ' + cls;
      $('active-model-title').textContent = `${act.method_label} · ${act.version_tag}`;
      const apAt = act.approval?.approved_at || act.updated_at;
      $('active-model-meta').textContent = `Được duyệt ${fmtDate(apAt)} · ${act.artifact_id.slice(0, 16)}…`;
      $('btn-view-active').disabled = false;
    } else {
      $('active-status-pill').textContent = 'Chưa kích hoạt';
      $('active-status-pill').className = 'status-pill status-idle';
      $('active-model-title').textContent = 'Chưa có mô hình đang dùng';
      $('active-model-meta').textContent = 'Chọn dữ liệu và huấn luyện phiên bản đầu tiên ở bước 3.';
      $('btn-view-active').disabled = true;
    }

    const sd = ov.shared_data;
    const ps = sd.primary_snapshot;
    if (ps) {
      $('shared-data-count').textContent = `${Number(ps.transaction_count).toLocaleString('vi-VN')} giao dịch`;
      $('shared-data-meta').textContent = `${ps.period_label} · ${sd.snapshot_count} bản dữ liệu đã khóa`;
    } else {
      $('shared-data-count').textContent = '0 bản dữ liệu';
      $('shared-data-meta').textContent = 'Hãy nạp dữ liệu tại mục Dữ liệu chung ở sảnh Portal.';
    }
  }

  function renderCandidatesAndHistory() {
    const ov = overviewData;
    const cands = ov.candidates || [];
    const body = $('candidates-body');
    const anySim = cands.some(v => v.evaluation?.is_simulated !== false);
    $('compare-sim-badge').hidden = !anySim;

    if (!selectedVersionId || !ov.versions.some(v => v.version_id === selectedVersionId)) {
      const preferred = cands.find(v => v.status === 'pending_approval') || cands[0] || ov.versions[0] || null;
      selectedVersionId = preferred ? preferred.version_id : null;
    }

    body.replaceChildren(...cands.map(v => {
      const tr = el('tr', undefined, 'clickable' + (v.version_id === selectedVersionId ? ' selected' : ''));
      const ev = v.evaluation || {};
      const tdName = el('td');
      tdName.append(el('strong', `${v.method_label} · v${v.version_number}`));
      const tdPeriod = el('td', ev.eval_period_label || v.data_profile?.period_label || '—');
      const tdUseful = el('td', ev.useful_display || 'Chưa đánh giá');
      const tdTime = el('td', fmtSec(ev.inference_seconds));
      const tdStatus = el('td');
      tdStatus.append(statusPill(v.status));
      tr.append(tdName, tdPeriod, tdUseful, tdTime, tdStatus);
      tr.onclick = () => { selectedVersionId = v.version_id; renderCandidatesAndHistory(); renderSelectedApproval(); };
      return tr;
    }));
    $('candidates-empty').hidden = cands.length > 0;

    // History table
    const hBody = $('history-body');
    hBody.replaceChildren(...(ov.versions || []).map(v => {
      const tr = el('tr', undefined, 'clickable' + (v.version_id === selectedVersionId ? ' selected' : ''));
      tr.append(
        el('td', 'v' + v.version_number),
        el('td', v.method_label),
        el('td', fmtDateTime(v.created_at)),
        (() => { const td = el('td'); td.append(statusPill(v.status)); return td; })()
      );
      tr.onclick = () => { selectedVersionId = v.version_id; renderCandidatesAndHistory(); renderSelectedApproval(); };
      return tr;
    }));

    // Rollback button & targets
    const rTargets = ov.rollback_targets || [];
    const rbBtn = $('btn-rollback');
    if (rTargets.length > 0 && ov.can_fit) {
      rbBtn.disabled = false;
      rbBtn.textContent = `↺ Hoàn nguyên phiên bản (v${rTargets[0].version_number})`;
      $('rollback-target').replaceChildren(...rTargets.map(t => {
        const o = el('option', `${t.version_tag} · ${t.method_label} (${fmtDate(t.approval?.approved_at || t.created_at)})`);
        o.value = t.version_id;
        return o;
      }));
    } else {
      rbBtn.disabled = true;
      rbBtn.textContent = '↺ Hoàn nguyên phiên bản';
      $('rollback-box').hidden = true;
    }
  }

  function renderSelectedApproval() {
    const ov = overviewData;
    const v = (ov.versions || []).find(x => x.version_id === selectedVersionId) || null;
    const chkGrid = $('checklist-grid');
    const detailBox = $('eval-metrics-detail');

    if (!v) {
      $('ap-model').textContent = '—';
      $('ap-snapshot').textContent = '—';
      $('ap-features').textContent = '—';
      $('btn-approve').disabled = true;
      $('btn-score-queue').disabled = true;
      chkGrid.replaceChildren();
      detailBox.replaceChildren(el('p', 'Chọn một phiên bản để xem chi tiết.', 'muted'));
      return;
    }

    const ev = v.evaluation || {};
    $('ap-model').textContent = `${v.method_label} · ${v.version_tag}`;
    $('ap-snapshot').textContent = v.snapshot_id.slice(0, 16) + '…';
    $('ap-features').textContent = `${v.data_profile?.kept_features ?? 33}/${ov.feature_contract.total_features} đặc trưng · ${v.feature_contract_version.split('/').pop()}`;

    // Checklist 4 items
    const items = ev.checklist || [];
    chkGrid.replaceChildren(...items.map(c => {
      const cls = c.status === 'pass' ? 'pass' : c.status === 'fail' ? 'fail' : 'waiting';
      const icon = c.status === 'pass' ? '✓' : c.status === 'fail' ? '✕' : '◷';
      const box = el('div', undefined, 'chk-item ' + cls);
      const wrap = el('div');
      wrap.append(el('strong', c.label + (c.status === 'waiting' ? ' · Đang chờ' : '')), el('small', c.detail || ''));
      box.append(el('span', icon, 'chk-icon'), wrap);
      return box;
    }));

    // Deep unsupervised metrics & feature attributions
    detailBox.replaceChildren();
    const u = ev.unsupervised || {};
    const statsGrid = el('div', undefined, 'kpi-strip');
    for (const [k, val] of [
      ['Dòng đánh giá', `${ev.scored_rows ?? 0}/${ev.eval_rows ?? 0}`],
      ['Tỷ lệ tách đuôi (max/p50)', u.separation_ratio != null ? String(u.separation_ratio) : '—'],
      ['Vượt p95 tham chiếu', u.tail_above_ref_p95_pct != null ? `${u.tail_above_ref_p95_pct}%` : '—'],
      ['Bền vững khi khuyết 5 trường', ev.missing_robustness_pass ? `Đạt (Δ=${ev.missing_probe_delta ?? 0})` : 'Cảnh báo'],
    ]) {
      const b = el('div', undefined, 'kpi-box');
      b.append(el('span', k), el('strong', val));
      statsGrid.append(b);
    }
    detailBox.append(statsGrid);

    if (ev.top_attributions?.length) {
      detailBox.append(el('h3', 'Giao dịch có mức bất thường cao nhất & đặc trưng đóng góp (không phải xác suất gian lận)'));
      const tbl = el('table', undefined, 'mm-table');
      tbl.innerHTML = '<thead><tr><th>Mã giao dịch</th><th>Hạng tương đối</th><th>Đặc trưng đóng góp chính</th></tr></thead>';
      const tb = el('tbody');
      for (const tc of ev.top_attributions) {
        const tr = el('tr');
        const featText = (tc.top_features || []).slice(0, 3).map(f => `${f.label_vi} (${Math.round(f.share * 100)}%)`).join(' · ') || 'Đánh giá đa biến';
        tr.append(el('td', tc.record_id), el('td', `Top ${tc.relative_rank_pct}% (điểm thô ${tc.raw_score})`), el('td', featText));
        tb.append(tr);
      }
      tbl.append(tb);
      detailBox.append(tbl);
    }
    detailBox.append(el('p', ev.limitation || '', 'muted-note'));

    // Approval form readiness
    const canApprove = Boolean(ov.can_fit && ev.technical_ready);
    updateApproveButtonState(v, canApprove);

    // Queue scoring button enabled only for approved (shadow/active) versions
    const isApproved = (v.status === 'active' || v.status === 'shadow') && Boolean(v.approval);
    $('btn-score-queue').disabled = !(ov.can_fit && isApproved && ov.shared_data.snapshots.some(s => s.native_35_rules));
    $('btn-score-queue').textContent = isApproved
      ? `Chấm vào hàng đợi bằng ${v.version_tag}`
      : 'Phê duyệt phiên bản trước khi chấm hàng đợi';
  }

  function updateApproveButtonState(v, canApprove) {
    const label = approvalMode === 'active' ? 'Xác nhận đưa vào sử dụng' : 'Phê duyệt chạy thử';
    $('btn-approve').textContent = label;
    const reasonOk = $('approve-reason').value.trim().length >= 10;
    const checked = $('approve-checked').checked;
    $('btn-approve').disabled = busy || !v || !canApprove || !reasonOk || !checked;
  }

  function renderProfileAndFeatures() {
    const p = profileData;
    if (!p) return;
    const s = p.snapshot;
    const fc = p.feature_contract;
    const split = p.recommended_split;

    // Step 1 KPIs
    $('profile-kpis').replaceChildren(...[
      ['Tổng giao dịch', Number(s.transaction_count).toLocaleString('vi-VN')],
      ['Kỳ dữ liệu', s.period_label],
      ['Độ đầy đủ đặc trưng', p.completeness_pct + '%'],
      ['Điểm chất lượng dữ liệu', p.data_quality_score + '/100'],
    ].map(([k, v]) => {
      const b = el('div', undefined, 'kpi-box');
      b.append(el('span', k), el('strong', v));
      return b;
    }));

    $('profile-warnings').replaceChildren(...(p.warnings || []).map(w => el('div', '⚠ ' + w, 'warn-item')));

    // Tables coverage
    const tbl = el('table', undefined, 'mm-table');
    tbl.innerHTML = '<thead><tr><th>Bảng nguồn</th><th>Số dòng</th><th>Độ phủ</th></tr></thead>';
    const tb = el('tbody');
    for (const row of p.tables_summary || []) {
      const tr = el('tr');
      const covVi = row.coverage_status === 'complete' ? 'Đầy đủ' : row.coverage_status === 'partial' ? 'Một phần' : row.coverage_status;
      tr.append(el('td', row.table), el('td', row.record_count), el('td', covVi));
      tb.append(tr);
    }
    tbl.append(tb);
    $('profile-tables').replaceChildren(tbl);

    // Split info
    const typeText = Object.entries(p.transaction_type_counts || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'Không có';
    const splitBox = $('profile-split-box');
    splitBox.replaceChildren(
      el('p', `Loại giao dịch: ${typeText}`),
      el('p', `Tách kỳ huấn luyện đề xuất: ${split.history_rows} dòng huấn luyện · ${split.reference_rows} dòng tham chiếu · ${split.eval_rows} dòng đánh giá độc lập.`),
      el('p', `Khả dụng để huấn luyện: ${split.split_feasible ? 'Đạt yêu cầu tách kỳ thời gian' : 'Cần bản dữ liệu dài kỳ hơn'}.`, 'muted-note')
    );

    // Step 2 Features
    $('feature-contract-badge').textContent = `${fc.version} · ${fc.fingerprint.slice(0, 12)}…`;
    $('feature-summary-strip').replaceChildren(...[
      ['Tổng đặc trưng chuẩn', fc.total_features],
      ['Đặc trưng có biến thiên', fc.active_variance_features],
      ['Có quan sát nhưng hằng số', Math.max(0, fc.observed_features - fc.active_variance_features)],
      ['Toàn null (tự loại bỏ)', fc.all_missing_features],
    ].map(([k, v]) => {
      const b = el('div', undefined, 'kpi-box');
      b.append(el('span', k), el('strong', v));
      return b;
    }));

    const ftbl = el('table', undefined, 'mm-table');
    ftbl.innerHTML = '<thead><tr><th>Nhóm</th><th>Đặc trưng</th><th>Tỷ lệ thiếu</th><th>Trạng thái</th></tr></thead>';
    const ftb = el('tbody');
    for (const f of fc.features || []) {
      const tr = el('tr');
      const stLabel = f.status === 'active' ? ['Đưa vào huấn luyện', 'status-active']
        : f.status === 'constant' ? ['Hằng số (giữ 0 lệch)', 'status-superseded']
        : ['Loại do không có nguồn', 'status-shadow'];
      const nameTd = el('td');
      nameTd.append(el('strong', f.label_vi), el('div', f.name, 'muted small-note'));
      const stTd = el('td');
      stTd.append(el('span', stLabel[0], 'status-pill ' + stLabel[1]));
      tr.append(el('td', f.group), nameTd, el('td', f.missing_pct + '%'), stTd);
      ftb.append(tr);
    }
    ftbl.append(ftb);
    $('feature-table-wrap').replaceChildren(ftbl);
    $('feature-exclusions').textContent = 'Trường tuyệt đối loại khỏi ma trận đặc trưng ML (chống rò rỉ): ' + (fc.excluded_predictors || []).join(', ');

    // Step 3 Algorithm selector & prefilled split (4 unsupervised + R2 Logistic Regression FHE)
    const lrCardSpec = {
      id: 'logistic_regression_fhe',
      label: 'Logistic Regression (FHE · Worker 8870)',
      badge: 'FHE · 2 đặc trưng',
      recommended: false,
      eligible: true,
      summary_vi: 'Huấn luyện có nhãn bằng Logistic Regression lượng tử hóa: hỗ trợ chạy tham chiếu local hoặc FHE thật trên ciphertext qua Worker 8870.',
      fit_note_vi: 'Cố định 2 đặc trưng mạch FHE (round_million, creator_equals_approver); không cho chọn 33 đặc trưng; có checkpoint & resume idempotent.',
    };
    const allMethods = [...(p.recommended_methods || []), lrCardSpec];
    $('algo-grid').replaceChildren(...allMethods.map(m => {
      const card = el('button', undefined, 'algo-card' + (m.id === selectedAlgo ? ' selected' : ''));
      card.type = 'button';
      card.setAttribute('role', 'radio');
      card.setAttribute('aria-checked', String(m.id === selectedAlgo));
      const head = el('div', undefined, 'algo-card-head');
      head.append(el('strong', m.label));
      if (m.badge) head.append(el('span', m.badge, 'pill-rose'));
      else if (m.recommended) head.append(el('span', 'Ưu tiên khuyến nghị', 'pill-rose'));
      else head.append(el('span', m.eligible ? 'Sẵn sàng' : 'Thiếu mẫu', 'pill-soft'));
      card.append(head, el('p', m.summary_vi), el('div', m.fit_note_vi, 'algo-note'));
      card.onclick = () => {
        selectedAlgo = m.id;
        renderProfileAndFeatures();
        if (selectedAlgo === 'logistic_regression_fhe') loadLrFheStatus();
      };
      return card;
    }));

    const isLr = selectedAlgo === 'logistic_regression_fhe';
    $('train-form').hidden = isLr;
    $('lr-fhe-panel').hidden = !isLr;
    if (isLr && !lrStatusData) loadLrFheStatus();

    $('train-snapshot').value = s.snapshot_id;
    $('train-h-start').value = split.history_start || '';
    $('train-h-end').value = split.history_end || '';
    $('train-r-start').value = split.reference_start || '';
    $('train-r-end').value = split.reference_end || '';
    $('train-e-start').value = split.evaluation_start || '';
  }

  async function loadProfile(snapshotId) {
    if (!snapshotId) return;
    setNotice('');
    try {
      profileData = await api(basePath() + '/profile', { snapshot_id: snapshotId });
      renderProfileAndFeatures();
    } catch (err) {
      setNotice(err.message);
    }
  }

  async function loadOverview() {
    setNotice('');
    $('refresh').disabled = true;
    try {
      overviewData = await api(basePath());
      const snaps = overviewData.shared_data.snapshots || [];
      const primaryId = overviewData.shared_data.primary_snapshot?.snapshot_id;
      const evalId = overviewData.shared_data.recommended_eval_snapshot?.snapshot_id || primaryId;
      populateSnapshotSelect($('profile-snapshot'), snaps, primaryId);
      populateSnapshotSelect($('train-snapshot'), snaps, primaryId);
      populateSnapshotSelect($('train-eval-snapshot'), snaps, evalId);
      populateSnapshotSelect($('reeval-snapshot'), snaps, evalId);
      const nativeSnaps = snaps.filter(s => s.native_35_rules);
      populateSnapshotSelect($('score-snapshot'), nativeSnaps, evalId);
      if ($('lr-score-snapshot')) populateSnapshotSelect($('lr-score-snapshot'), nativeSnaps, evalId);
      renderHero();
      renderCandidatesAndHistory();
      renderSelectedApproval();
      profileData = null;
      if (currentStep <= 3 && primaryId) await loadProfile(primaryId);
    } catch (err) {
      setNotice(err.message);
    } finally {
      $('refresh').disabled = false;
    }
  }

  function openDrawer(title, contentNodes) {
    $('drawer-title').textContent = title;
    $('drawer-content').replaceChildren(...contentNodes);
    $('detail-drawer').hidden = false;
    $('detail-drawer').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // Event bindings
  for (const btn of document.querySelectorAll('.step-pill')) {
    btn.onclick = () => setStep(btn.dataset.step);
  }
  $('btn-inspect-data').onclick = () => setStep(2);
  $('btn-to-step-3').onclick = () => setStep(3);
  $('btn-back-step-2').onclick = () => setStep(2);
  $('btn-new-train').onclick = () => setStep(3);
  $('btn-run-profile').onclick = () => loadProfile($('profile-snapshot').value);
  $('profile-snapshot').onchange = () => loadProfile($('profile-snapshot').value);
  $('train-snapshot').onchange = () => loadProfile($('train-snapshot').value);
  $('btn-close-drawer').onclick = () => { $('detail-drawer').hidden = true; };

  $('btn-view-active').onclick = () => {
    const v = overviewData?.active_version;
    if (!v) return;
    const dl = el('dl', undefined, 'kv-list');
    for (const [k, val] of [
      ['Phiên bản', v.version_tag],
      ['Thuật toán', v.method_label],
      ['Artifact ID', v.artifact_id],
      ['Bản dữ liệu train', v.snapshot_id],
      ['Hợp đồng đặc trưng', `${v.feature_contract_version} (${v.feature_contract_fingerprint.slice(0, 16)}…)`],
      ['Tiền xử lý', v.preprocess_version],
      ['Chế độ hiện tại', v.mode === 'active' ? 'Đang dùng' : 'Chạy thử'],
      ['Người phê duyệt', v.approval?.approved_by || '—'],
      ['Thời điểm duyệt', fmtDateTime(v.approval?.approved_at)],
      ['Ý kiến phê duyệt', v.approval?.reason || '—'],
    ]) dl.append(el('dt', k), el('dd', val));
    openDrawer(`Chi tiết phiên bản ${v.version_tag}`, [dl]);
  };

  $('btn-limits').onclick = () => {
    const list = el('ul');
    for (const g of overviewData?.guardrails || []) list.append(el('li', g));
    const formula = el('p', 'Điểm ưu tiên điều tra trong Hàng đợi kết hợp tín hiệu từ 35 luật nghiệp vụ, liên kết đồ thị quan hệ (bối cảnh đối chiếu) và thứ hạng bất thường tương đối của mô hình ML đã phê duyệt. Điểm ML chưa hiệu chuẩn tuyệt đối không được diễn giải thành tỷ lệ phần trăm xác suất gian lận.');
    openDrawer('Giải thích cơ chế tính điểm & giới hạn mô hình', [formula, list]);
  };

  for (const btn of [$('mode-shadow'), $('mode-active')]) {
    btn.onclick = () => {
      approvalMode = btn.dataset.mode;
      $('mode-shadow').classList.toggle('active', approvalMode === 'shadow');
      $('mode-active').classList.toggle('active', approvalMode === 'active');
      const v = overviewData?.versions?.find(x => x.version_id === selectedVersionId);
      updateApproveButtonState(v, Boolean(overviewData?.can_fit && v?.evaluation?.technical_ready));
    };
  }
  const syncApproveEnable = () => {
    const v = overviewData?.versions?.find(x => x.version_id === selectedVersionId);
    updateApproveButtonState(v, Boolean(overviewData?.can_fit && v?.evaluation?.technical_ready));
  };
  $('approve-reason').oninput = syncApproveEnable;
  $('approve-checked').onchange = syncApproveEnable;

  $('train-form').onsubmit = async e => {
    e.preventDefault();
    if (busy) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-train').disabled = true;
    $('train-status').textContent = 'Đang huấn luyện ngoại tuyến & đánh giá trên kỳ độc lập…';
    try {
      const payload = {
        snapshot_id: $('train-snapshot').value,
        eval_snapshot_id: $('train-eval-snapshot').value,
        method_id: selectedAlgo,
        missing_policy: $('train-missing-policy').value,
        history_start: $('train-h-start').value.trim() || undefined,
        history_end: $('train-h-end').value.trim() || undefined,
        reference_start: $('train-r-start').value.trim() || undefined,
        reference_end: $('train-r-end').value.trim() || undefined,
        evaluation_start: $('train-e-start').value.trim() || undefined,
      };
      const res = await api(basePath() + '/train', payload, 'ui-train-' + crypto.randomUUID());
      selectedVersionId = res.version.version_id;
      setSuccess(`Đã huấn luyện và đánh giá thành công ${res.version.version_tag} (${res.version.method_label}). Kiểm tra chất lượng trước khi phê duyệt.`);
      await loadOverview();
      setStep(4);
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('btn-train').disabled = false;
      $('train-status').textContent = '';
    }
  };

  $('btn-reeval').onclick = async () => {
    if (busy || !selectedVersionId) return;
    busy = true;
    setNotice('');
    $('btn-reeval').disabled = true;
    try {
      await api(basePath() + '/evaluate', {
        version_id: selectedVersionId,
        eval_snapshot_id: $('reeval-snapshot').value,
      });
      setSuccess('Đã chạy đánh giá lại trên bản dữ liệu mới (không huấn luyện lại mô hình).');
      await loadOverview();
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('btn-reeval').disabled = false;
    }
  };

  $('approve-form').onsubmit = async e => {
    e.preventDefault();
    if (busy || !selectedVersionId) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-approve').disabled = true;
    try {
      const res = await api(basePath() + '/approve', {
        version_id: selectedVersionId,
        mode: approvalMode,
        reason: $('approve-reason').value.trim(),
        reviewed_evaluation: $('approve-checked').checked,
      }, 'ui-approve-' + crypto.randomUUID());
      $('approve-reason').value = '';
      $('approve-checked').checked = false;
      setSuccess(`Đã phê duyệt ${res.version.version_tag} vào chế độ ${approvalMode === 'active' ? 'Đang dùng' : 'Chạy thử'} và cập nhật cấu hình ghim doanh nghiệp.`);
      await loadOverview();
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      syncApproveEnable();
    }
  };

  $('btn-rollback').onclick = () => { $('rollback-box').hidden = !$('rollback-box').hidden; };
  $('btn-cancel-rollback').onclick = () => { $('rollback-box').hidden = true; };
  $('btn-confirm-rollback').onclick = async () => {
    if (busy) return;
    const targetId = $('rollback-target').value;
    const reason = $('rollback-reason').value.trim();
    if (reason.length < 10) { setNotice('Nhập lý do hoàn nguyên tối thiểu 10 ký tự.'); return; }
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-confirm-rollback').disabled = true;
    try {
      const res = await api(basePath() + '/rollback', { target_version_id: targetId, reason }, 'ui-rb-' + crypto.randomUUID());
      selectedVersionId = res.version.version_id;
      $('rollback-reason').value = '';
      $('rollback-box').hidden = true;
      setSuccess(`Đã hoàn nguyên thành công về phiên bản ${res.version.version_tag} (${res.version.method_label}).`);
      await loadOverview();
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('btn-confirm-rollback').disabled = false;
    }
  };

  $('btn-score-queue').onclick = async () => {
    if (busy || !selectedVersionId) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-score-queue').disabled = true;
    const resBox = $('score-queue-result');
    resBox.hidden = true;
    try {
      const res = await api(basePath() + '/score-queue', {
        version_id: selectedVersionId,
        snapshot_id: $('score-snapshot').value,
      }, 'ui-score-' + crypto.randomUUID());
      const lrSuffix = res.lr_included
        ? ` · Phương pháp thứ 5 (LR): ${res.lr_model_version}`
        : ` · Phương pháp thứ 5 (LR): chưa khả dụng (${res.lr_error_code || 'LR_UNAVAILABLE'})`;
      resBox.replaceChildren(
        el('div', `Đã chấm xong bằng ${res.version_tag}${lrSuffix}: tiếp nhận ${res.admitted_cases}/${res.total_cases} vụ vào hàng đợi (${res.elapsed_seconds} giây).`),
        (() => {
          const a = el('a', 'Mở ngay trong Hàng đợi & điều tra →');
          a.href = mount + '/' + res.queue_url;
          return a;
        })()
      );
      resBox.hidden = false;
      setSuccess(`Đã kết nối kết quả ML (${res.version_tag}) vào hàng đợi điều tra.`);
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      renderSelectedApproval();
    }
  };

  $('refresh').onclick = () => {
    loadOverview();
    if (selectedAlgo === 'logistic_regression_fhe') loadLrFheStatus();
  };
  $('company').onchange = () => {
    company = $('company').value;
    selectedVersionId = null;
    profileData = null;
    lrStatusData = null;
    lrPreviewData = null;
    selectedLrJobId = null;
    lrRegistryData = null;
    selectedLrRegId = null;
    remember();
    loadOverview();
  };

  // ==================== R2: LOGISTIC REGRESSION (FHE · WORKER 8870) ====================
  function syncLrEpochBounds() {
    const bc = Number($('lr-batch-count').value || 2);
    const epSel = $('lr-epochs');
    const maxEp = Math.max(1, Math.floor(4 / bc));
    for (const opt of epSel.options) {
      opt.disabled = Number(opt.value) > maxEp;
    }
    if (Number(epSel.value) > maxEp) epSel.value = String(maxEp);
  }

  function syncLrModeUI() {
    for (const btn of document.querySelectorAll('.lr-mode-btn')) {
      const active = btn.dataset.lrMode === lrMode;
      btn.classList.toggle('selected', active);
      btn.setAttribute('aria-checked', String(active));
    }
    const fhe = lrMode === 'fhe_cloud_ciphertext';
    $('btn-lr-train').textContent = fhe
      ? 'Bắt đầu huấn luyện LR (FHE Worker 8870)'
      : 'Chạy huấn luyện tham chiếu local';
  }

  function renderLrWorkerAndCircuit() {
    if (!lrStatusData) return;
    const wh = lrStatusData.worker_health || {};
    const cr = lrStatusData.crypto || {};
    const cir = cr.circuit || {};
    const keys = cr.keys || {};

    const wPill = $('lr-worker-pill');
    wPill.className = 'status-pill ' + (wh.reachable ? 'status-active' : 'status-rolled_back');
    wPill.textContent = wh.reachable ? `Sẵn sàng · ${wh.latency_ms ?? 0} ms` : 'Mất kết nối';
    $('lr-worker-meta').textContent = (wh.message || '') + (wh.portal_managed ? ` · Portal quản lý (restart: ${wh.restart_count ?? 0})` : '');
    $('btn-lr-restart').disabled = busy || !wh.can_restart;

    const cPill = $('lr-crypto-pill');
    cPill.className = 'status-pill ' + (cr.ready_for_fhe ? 'status-active' : 'status-review');
    cPill.textContent = cr.ready_for_fhe ? 'Mạch & khóa hợp lệ' : 'Cần kiểm tra khóa';

    const dl = $('lr-circuit-meta');
    dl.replaceChildren();
    for (const [k, v] of [
      ['Phiên bản mạch', `${cir.profile_version || '—'} (Concrete ${cir.concrete_version || '—'})`],
      ['Build SHA-256', cir.build_sha256 ? cir.build_sha256.slice(0, 20) + '…' : '—'],
      ['Key Epoch', keys.key_epoch || 'Chưa cấp'],
      ['Evaluation Key', keys.evaluation_keys_sha256 ? `${keys.evaluation_keys_sha256.slice(0, 16)}… (${keys.evaluation_key_verified ? 'đã khớp grant' : 'chưa khớp'})` : 'Thiếu'],
      ['Thang lượng tử hóa', cir.weight_scale ? `weight_scale=${cir.weight_scale}, prob_scale=${cir.probability_scale}, max_steps=${cir.max_steps}` : '—'],
    ]) {
      dl.append(el('dt', k), el('dd', v));
    }

    // Locked 2-feature contract box (explicitly prevents selecting 33 features)
    const feats = (lrPreviewData?.supported_features || lrStatusData.supported_features || []);
    $('lr-feature-ratio').textContent = `${feats.length} / ${lrStatusData.total_system_features || 33}`;
    const chipBox = $('lr-locked-feature-list');
    chipBox.replaceChildren(
      ...feats.map(f => el('span', `✓ ${f.name} — ${f.label_vi}`, 'lr-feature-chip')),
      el('span', `✕ ${(lrStatusData.total_system_features || 33) - feats.length} đặc trưng khác bị khóa theo mạch FHE`, 'lr-feature-chip disabled-31')
    );
  }

  function renderLrDatasetPreview() {
    const p = lrPreviewData || lrStatusData?.default_dataset_preview;
    if (!p) return;
    $('lr-dataset-kpis').replaceChildren(...[
      ['Số mẫu hợp lệ', `${p.valid_samples} train · ${p.validation_samples} val`],
      ['Số nhãn 0 (Hợp lệ)', `${p.label_0_count} train · ${p.validation_label_0_count ?? 0} val`],
      ['Số nhãn 1 (Bất thường)', `${p.label_1_count} train · ${p.validation_label_1_count ?? 0} val`],
      ['Features mạch hỗ trợ', `${p.supported_feature_count} / ${p.total_system_features}`],
      ['Số batch', `${p.batch_count} batch (${p.batch_size} mẫu/batch)`],
      ['Số epoch / bước', `${p.epochs} epoch (${p.total_updates}/${p.max_circuit_updates} bước)`],
    ].map(([k, v]) => {
      const b = el('div', undefined, 'kpi-box');
      b.append(el('span', k), el('strong', v));
      return b;
    }));
    const vrl = lrStatusData?.verified_review_labels;
    const vNote = $('lr-verified-reviews-note');
    if (vNote) {
      if (vrl) {
        vNote.textContent = `Kho nhãn rà soát cho chu kỳ supervised tiếp theo: ${vrl.eligible_count} giao dịch đã xác minh (${vrl.fraud_count} Vi phạm · ${vrl.legitimate_count} Hợp lệ); đã loại trừ ${vrl.excluded_inconclusive_count} Chưa đủ bằng chứng và ${vrl.excluded_unverified_count} giao dịch chưa rà/chưa đủ đối chiếu.`;
        vNote.hidden = false;
      } else {
        vNote.hidden = true;
      }
    }
  }

  function syncLrPromoteButton(job) {
    const reasonOk = $('lr-promote-reason').value.trim().length >= 10;
    const checked = $('lr-promote-checked').checked;
    const canPromote = Boolean(
      job &&
      job.artifact_stage === 'validated_checkpoint' &&
      job.validation?.implementation_error?.pass === true
    );
    $('btn-lr-promote').disabled = busy || !canPromote || !reasonOk || !checked;
  }

  function renderLrJobDetails() {
    const jobs = lrStatusData?.jobs || [];
    if (!selectedLrJobId && jobs.length) selectedLrJobId = jobs[0].job_id;
    const job = jobs.find(j => j.job_id === selectedLrJobId) || jobs[0] || null;
    if (job) selectedLrJobId = job.job_id;

    // Jobs history table
    const histWrap = $('lr-history-wrap');
    histWrap.hidden = !jobs.length;
    if (jobs.length) {
      const tbody = $('lr-jobs-body');
      tbody.replaceChildren(...jobs.map(j => {
        const tr = el('tr', undefined, j.job_id === selectedLrJobId ? 'selected-row' : '');
        const stageText = j.is_releasable_model
          ? 'Model có thể phát hành'
          : j.artifact_stage === 'validated_checkpoint'
            ? 'Checkpoint đã đối chiếu'
            : 'Train checkpoint';
        const stageCls = j.is_releasable_model ? 'status-active' : j.artifact_stage === 'validated_checkpoint' ? 'status-pending' : 'status-shadow';
        const lossVal = j.validation?.actual?.metrics?.bce_loss;
        tr.append(
          el('td', j.job_id, 'mono-cell'),
          el('td', j.mode === 'fhe_cloud_ciphertext' ? 'FHE Worker 8870' : 'Tham chiếu local'),
          el('td', `${j.completed_updates}/${j.total_updates} bước`),
          (() => { const td = el('td'); td.append(el('span', stageText, 'status-pill ' + stageCls)); return td; })(),
          el('td', lossVal != null ? String(lossVal) : 'Chưa đối chiếu')
        );
        tr.onclick = () => { selectedLrJobId = j.job_id; renderLrJobDetails(); };
        return tr;
      }));
    }

    const box = $('lr-job-progress-box');
    if (!job) {
      box.hidden = true;
      $('btn-lr-resume').disabled = true;
      $('btn-lr-decrypt').disabled = true;
      syncLrRegButtons();
      return;
    }
    box.hidden = false;

    const pct = job.total_updates ? Math.round((job.completed_updates / job.total_updates) * 100) : 0;
    $('lr-job-title').textContent = `Job ${job.job_id}` + (job.worker_job_id ? ` · Worker Job ${job.worker_job_id}` : '');
    $('lr-job-sub').textContent = `${job.mode_label_vi || job.mode} · ${job.native_fhe_executed ? 'FHE Concrete thực thi trên bản mã (không fallback plaintext)' : 'Tham chiếu local lượng tử hóa'} · ${fmtSec(job.elapsed_seconds)}`;

    const stageBadge = $('lr-stage-badge');
    if (job.is_releasable_model) {
      stageBadge.className = 'status-pill status-active';
      stageBadge.textContent = `Model có thể phát hành · ${job.promoted_version?.version_tag || ''}`;
    } else if (job.artifact_stage === 'validated_checkpoint') {
      stageBadge.className = 'status-pill status-pending';
      stageBadge.textContent = 'Train checkpoint đã giải mã — chưa phát hành';
    } else {
      stageBadge.className = 'status-pill status-shadow';
      stageBadge.textContent = 'Train checkpoint (bản mã) — chưa thể phát hành';
    }

    $('lr-progress-fill').style.width = `${pct}%`;
    const ds = job.dataset_summary || {};
    const pf = job.preflight || {};
    $('lr-progress-meta').replaceChildren(
      el('span', `Tiến trình: ${job.completed_updates}/${job.total_updates} bước cập nhật (${pct}%)`),
      el('span', `Dữ liệu: ${ds.valid_samples ?? 0} train (nhãn 0: ${ds.label_0_count ?? 0}, nhãn 1: ${ds.label_1_count ?? 0})`),
      el('span', `Mạch: ${job.circuit_and_keys?.profile_version || '—'} · ${ds.supported_feature_count ?? 2}/${ds.total_system_features ?? 33} đặc trưng`),
      el('span', pf.ciphertext_verified ? `Preflight: ${pf.ciphertext_checked_count} bản mã & evaluation key đã xác minh` : (pf.note || ''))
    );

    const errBox = $('lr-job-error');
    if (job.error) {
      errBox.textContent = `⚠ [${job.error.code}] ${job.error.message}`;
      errBox.hidden = false;
    } else {
      errBox.hidden = true;
    }

    // Resume & Decrypt button states
    $('btn-lr-resume').disabled = busy || job.mode !== 'fhe_cloud_ciphertext';
    $('btn-lr-decrypt').disabled = busy || job.mode !== 'fhe_cloud_ciphertext' || job.completed_updates < job.total_updates;

    // Checkpoints table
    const ckBody = $('lr-checkpoints-body');
    ckBody.replaceChildren(...(job.checkpoints || []).map(c => {
      const tr = el('tr');
      const isInit = Number(c.step_cursor) === 0;
      tr.append(
        el('td', isInit ? 'Cursor 0 (khởi tạo W=0)' : `Cursor ${c.step_cursor}/${job.total_updates}`),
        el('td', isInit ? 'Khởi tạo' : `Epoch ${c.epoch} · Batch ${c.batch_index}`),
        (() => {
          const td = el('td');
          td.append(el('span', 'Train checkpoint', 'status-pill status-shadow'));
          return td;
        })(),
        el('td', (c.weights_hash || '').slice(0, 24) + '…', 'mono-cell'),
        el('td', fmtDateTime(c.committed_at))
      );
      return tr;
    }));

    // Validation results & Implementation Error vs Quantization Error separation
    const valBox = $('lr-validation-box');
    const val = job.validation;
    valBox.hidden = !val;
    if (val) {
      const impl = val.implementation_error || {};
      const quant = val.quantization_error || {};
      const splitGrid = $('lr-error-split-grid');
      const implCard = el('div', undefined, 'chk-item ' + (impl.pass ? 'pass' : 'fail'));
      const implWrap = el('div');
      implWrap.append(
        el('strong', `Sai số triển khai (FHE vs lượng tử hóa): ${impl.pass ? 'Đạt · 0 lỗi' : 'LỖI TRIỂN KHAI'}`),
        el('small', `ΔW max = ${impl.weight_max_abs_diff} · ΔLoss = ${impl.loss_abs_diff} · ΔProb max = ${impl.pred_prob_max_abs_diff}. ${impl.explanation_vi || ''}`)
      );
      implCard.append(el('span', impl.pass ? '✓' : '✕', 'chk-icon'), implWrap);

      const qCard = el('div', undefined, 'chk-item ' + (quant.within_standard ? 'pass' : 'waiting'));
      const qWrap = el('div');
      qWrap.append(
        el('strong', `Sai số lượng tử hóa (so với LR số thực): ${quant.within_standard ? 'Trong chuẩn cho phép' : 'Cần lưu ý'}`),
        el('small', `ΔW max = ${quant.weight_max_abs_diff} (ngưỡng ≤ ${quant.standard_bounds?.max_weight_diff}) · ΔLoss = ${quant.loss_abs_diff} · Khớp nhãn = ${Math.round((quant.class_agreement_rate || 0) * 100)}%. ${quant.explanation_vi || ''}`)
      );
      qCard.append(el('span', quant.within_standard ? '✓' : '◷', 'chk-icon'), qWrap);
      splitGrid.replaceChildren(implCard, qCard);

      const cmpRows = [
        { item: val.actual, note: job.native_fhe_executed ? `Giải mã local bởi ${job.decrypted_model?.decrypted_by || actor} · weights_code=${JSON.stringify(val.actual.weights_code)}` : `weights_code=${JSON.stringify(val.actual.weights_code)}` },
        { item: val.quantized_reference, note: `Chuẩn số học lượng tử hóa · weights_code=${JSON.stringify(val.quantized_reference.weights_code)}` },
        { item: val.float_reference, note: 'Tham chiếu số thực SGD (không lượng tử hóa)' },
      ];
      $('lr-compare-body').replaceChildren(...cmpRows.map(({ item, note }) => {
        const tr = el('tr');
        const w = `w0=${item.coefficients[0]}, w1=${item.coefficients[1]}, b=${item.intercept}`;
        tr.append(
          el('td', item.label),
          el('td', w, 'mono-cell'),
          el('td', String(item.metrics?.bce_loss ?? '—')),
          el('td', item.metrics?.accuracy != null ? `${Math.round(item.metrics.accuracy * 100)}%` : '—'),
          el('td', note)
        );
        return tr;
      }));

      // Per-sample predictions table
      const preds = val.actual?.metrics?.predictions || [];
      const fPreds = val.float_reference?.metrics?.predictions || [];
      const ptbl = el('table', undefined, 'mm-table');
      ptbl.innerHTML = '<thead><tr><th>Mẫu validation</th><th>2 đặc trưng [x0, x1]</th><th>Nhãn thật</th><th>Điểm FHE/Lượng tử</th><th>Điểm LR số thực</th><th>Dự đoán</th></tr></thead>';
      const ptb = el('tbody');
      preds.forEach((pr, idx) => {
        const fpr = fPreds[idx] || {};
        const tr = el('tr');
        tr.append(
          el('td', pr.record_id, 'mono-cell'),
          el('td', `[${pr.x.join(', ')}]`, 'mono-cell'),
          el('td', String(pr.y_true)),
          el('td', String(pr.score)),
          el('td', fpr.score != null ? String(fpr.score) : '—'),
          el('td', `${pr.predicted_class} (${pr.correct ? 'Khớp' : 'Lệch'})`)
        );
        ptb.append(tr);
      });
      ptbl.append(ptb);
      $('lr-pred-table-wrap').replaceChildren(ptbl);
    }

    // Promotion box (strict separation between Train Checkpoint vs Releasable Model)
    const promBox = $('lr-promote-box');
    promBox.hidden = !val;
    const promSum = $('lr-promoted-summary');
    const lrScoreBox = $('lr-score-queue-box');
    const lrScoreRes = $('lr-score-queue-result');
    if (job.is_releasable_model && job.promoted_version) {
      const pv = job.promoted_version;
      const vm = pv.validation_metrics || {};
      const tauTxt = pv.threshold != null ? `${(Number(pv.threshold) * 100).toFixed(1)}%` : '50.0%';
      const sigAlgo = pv.signature_envelope?.algorithm || pv.signature?.algorithm;
      const sigTxt = sigAlgo ? `Đã ký ${sigAlgo.toUpperCase()}` : 'Chưa ký';
      const prTxt = vm.precision != null ? ` · Precision=${Math.round(vm.precision * 100)}%, Recall=${Math.round((vm.recall || 0) * 100)}%, F1=${Math.round((vm.f1 || 0) * 100)}%` : '';
      promSum.textContent = `Đã phê duyệt thành Model có thể phát hành: ${pv.version_tag} (${pv.model_id}) · ${sigTxt} · Ngưỡng validation: ${tauTxt}${prTxt} · Duyệt bởi ${pv.approved_by} lúc ${fmtDateTime(pv.approved_at)}.`;
      promSum.hidden = false;
      if (lrScoreBox) {
        lrScoreBox.hidden = false;
        $('btn-lr-score-queue').disabled = busy || !$('lr-score-snapshot')?.value;
      }
    } else {
      promSum.hidden = true;
      if (lrScoreBox) lrScoreBox.hidden = true;
      if (lrScoreRes) lrScoreRes.hidden = true;
    }
    syncLrPromoteButton(job);
    syncLrRegButtons();
  }

  async function refreshLrPreview() {
    syncLrEpochBounds();
    try {
      lrPreviewData = await api(basePath() + '/lr-fhe/prepare', {
        source_mode: $('lr-source-mode').value,
        snapshot_id: $('train-snapshot').value || undefined,
        batch_count: Number($('lr-batch-count').value || 2),
        epochs: Number($('lr-epochs').value || 1),
        selected_features: ['round_million', 'creator_equals_approver'],
      });
      setNotice('');
      renderLrWorkerAndCircuit();
      renderLrDatasetPreview();
    } catch (err) {
      setNotice(err.message);
    }
  }

  async function loadLrFheStatus() {
    if (!company) return;
    try {
      lrStatusData = await api(basePath() + '/lr-fhe/status');
      renderLrWorkerAndCircuit();
      renderLrDatasetPreview();
      renderLrJobDetails();
      await loadLrRegistry();
    } catch (err) {
      setNotice(err.message);
    }
  }

  for (const btn of document.querySelectorAll('.lr-mode-btn')) {
    btn.onclick = () => {
      lrMode = btn.dataset.lrMode;
      syncLrModeUI();
    };
  }
  $('lr-source-mode').onchange = () => refreshLrPreview();
  $('lr-batch-count').onchange = () => refreshLrPreview();
  $('lr-epochs').onchange = () => refreshLrPreview();
  $('btn-lr-back-step-2').onclick = () => setStep(2);

  $('btn-lr-health').onclick = async () => {
    if (busy) return;
    $('lr-action-status').textContent = 'Đang kiểm tra Worker 8870…';
    try {
      await loadLrFheStatus();
      $('lr-action-status').textContent = 'Đã cập nhật trạng thái Worker 8870.';
    } catch (err) {
      setNotice(err.message);
      $('lr-action-status').textContent = '';
    }
  };

  $('btn-lr-restart').onclick = async () => {
    if (busy) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-lr-restart').disabled = true;
    $('lr-action-status').textContent = 'Đang khởi động lại có kiểm soát Worker 8870…';
    try {
      await api(basePath() + '/lr-fhe/worker-restart', {});
      await loadLrFheStatus();
      setSuccess('Đã khởi động lại thành công Worker huấn luyện FHE (cổng 8870).');
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('lr-action-status').textContent = '';
      renderLrWorkerAndCircuit();
    }
  };

  $('btn-lr-train').onclick = async () => {
    if (busy) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-lr-train').disabled = true;
    $('lr-action-status').textContent = lrMode === 'fhe_cloud_ciphertext'
      ? 'Đang xác minh khóa/bản mã, mã hóa Concrete FHE tại local và huấn luyện trên Worker 8870 (nạp khóa FHE thật có thể mất 2–4 phút)…'
      : 'Đang chạy huấn luyện tham chiếu lượng tử hóa tại local…';
    try {
      const res = await api(basePath() + '/lr-fhe/train', {
        mode: lrMode,
        source_mode: $('lr-source-mode').value,
        snapshot_id: $('train-snapshot').value || undefined,
        batch_count: Number($('lr-batch-count').value || 2),
        epochs: Number($('lr-epochs').value || 1),
        selected_features: ['round_million', 'creator_equals_approver'],
        auto_decrypt: true,
      }, 'ui-lrfhe-train-' + crypto.randomUUID());
      selectedLrJobId = res.job.job_id;
      await loadLrFheStatus();
      setSuccess(
        lrMode === 'fhe_cloud_ciphertext'
          ? `Hoàn tất huấn luyện FHE trên Worker 8870 (${res.job.job_id}) và giải mã đối chiếu tại local (0 lỗi triển khai).`
          : `Hoàn tất huấn luyện tham chiếu local lượng tử hóa (${res.job.job_id}).`
      );
    } catch (err) {
      setNotice(err.message);
      await loadLrFheStatus();
    } finally {
      busy = false;
      $('btn-lr-train').disabled = false;
      $('lr-action-status').textContent = '';
      renderLrWorkerAndCircuit();
      renderLrJobDetails();
    }
  };

  $('btn-lr-resume').onclick = async () => {
    if (busy || !selectedLrJobId) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-lr-resume').disabled = true;
    $('lr-action-status').textContent = 'Đang tiếp tục (Resume idempotent) từ checkpoint cuối…';
    try {
      const curJob = (lrStatusData?.jobs || []).find(j => j.job_id === selectedLrJobId);
      const res = await api(basePath() + '/lr-fhe/resume', {
        job_id: selectedLrJobId,
        expected_cursor: curJob ? curJob.completed_updates : undefined,
        auto_decrypt: true,
      }, 'ui-lrfhe-resume-' + crypto.randomUUID());
      await loadLrFheStatus();
      setSuccess(
        res.already_completed
          ? `Job ${selectedLrJobId} đã hoàn tất đủ checkpoint (idempotent — không chạy trùng batch).`
          : `Đã resume thành công từ bước ${res.resumed_from_cursor}, cập nhật thêm ${res.new_updates_applied} bước.`
      );
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('lr-action-status').textContent = '';
      renderLrJobDetails();
    }
  };

  $('btn-lr-decrypt').onclick = async () => {
    if (busy || !selectedLrJobId) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-lr-decrypt').disabled = true;
    $('lr-action-status').textContent = 'Đang giải mã checkpoint tại local theo quyền doanh nghiệp…';
    try {
      await api(basePath() + '/lr-fhe/decrypt', { job_id: selectedLrJobId }, 'ui-lrfhe-dec-' + crypto.randomUUID());
      await loadLrFheStatus();
      setSuccess(`Đã giải mã và hoàn tất kiểm tra đối chiếu validation tại local cho ${selectedLrJobId}.`);
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      $('lr-action-status').textContent = '';
      renderLrJobDetails();
    }
  };

  const syncLrPromoteOnInput = () => {
    const job = (lrStatusData?.jobs || []).find(j => j.job_id === selectedLrJobId);
    syncLrPromoteButton(job);
    syncLrRegButtons();
  };
  $('lr-promote-reason').oninput = syncLrPromoteOnInput;
  $('lr-promote-checked').onchange = syncLrPromoteOnInput;

  $('btn-lr-promote').onclick = async () => {
    if (busy || !selectedLrJobId) return;
    busy = true;
    setNotice('');
    setSuccess('');
    $('btn-lr-promote').disabled = true;
    try {
      const res = await api(basePath() + '/lr-fhe/promote', {
        job_id: selectedLrJobId,
        reason: $('lr-promote-reason').value.trim(),
        reviewed_checked: $('lr-promote-checked').checked,
      }, 'ui-lrfhe-prom-' + crypto.randomUUID());
      $('lr-promote-reason').value = '';
      $('lr-promote-checked').checked = false;
      await loadLrFheStatus();
      setSuccess(`Đã phê duyệt thành Model có thể phát hành: ${res.releasable_model.version_tag}.`);
    } catch (err) {
      setNotice(err.message);
    } finally {
      busy = false;
      renderLrJobDetails();
    }
  };

  if ($('btn-lr-score-queue')) {
    $('btn-lr-score-queue').onclick = async () => {
      const job = (lrStatusData?.jobs || []).find(j => j.job_id === selectedLrJobId);
      const pv = job?.promoted_version;
      const snapId = $('lr-score-snapshot')?.value;
      if (busy || !pv || !snapId) return;
      busy = true;
      setNotice('');
      setSuccess('');
      $('btn-lr-score-queue').disabled = true;
      const resBox = $('lr-score-queue-result');
      resBox.hidden = true;
      try {
        const res = await api(basePath() + '/score-queue', {
          snapshot_id: snapId,
          lr_model_id: pv.model_id,
          lr_execution_preference: 'local_preferred',
        }, 'ui-lr-score-' + crypto.randomUUID());
        resBox.replaceChildren(
          el('div', `Đã chấm 5 phương pháp (có LR ${res.lr_model_version || pv.version_tag}): tiếp nhận ${res.admitted_cases}/${res.total_cases} vụ vào hàng đợi (${res.elapsed_seconds} giây).`),
          (() => {
            const a = el('a', 'Mở kết quả 5 phương pháp trong Hàng đợi & điều tra →');
            a.href = mount + '/' + res.queue_url;
            return a;
          })()
        );
        resBox.hidden = false;
        setSuccess(`Đã tích hợp Logistic Regression (${res.lr_model_version || pv.version_tag}) thành phương pháp phát hiện thứ 5 vào hàng đợi điều tra.`);
      } catch (err) {
        setNotice(err.message);
      } finally {
        busy = false;
        renderLrJobDetails();
      }
    };
  }

  // ==================== R5: VALIDATION, 4-WAY COMPARISON & 9-STATE LR MODEL REGISTRY ====================
  const REG_STATE_CLS = {
    TRAINING: 'status-idle',
    VALIDATING: 'status-pending',
    CANDIDATE: 'status-pending',
    SHADOW: 'status-shadow',
    APPROVED: 'status-active',
    ACTIVE: 'status-active',
    REJECTED: 'status-review',
    ROLLED_BACK: 'status-rolled_back',
    BLOCKED: 'status-review',
  };
  const REG_ALLOWED = {
    TRAINING: ['VALIDATING', 'BLOCKED', 'REJECTED'],
    VALIDATING: ['CANDIDATE', 'BLOCKED', 'REJECTED'],
    CANDIDATE: ['SHADOW', 'BLOCKED', 'REJECTED'],
    SHADOW: ['APPROVED', 'BLOCKED', 'REJECTED'],
    APPROVED: ['ACTIVE', 'BLOCKED', 'REJECTED'],
    ACTIVE: ['ROLLED_BACK', 'BLOCKED'],
    BLOCKED: ['VALIDATING', 'REJECTED'],
    ROLLED_BACK: ['VALIDATING', 'ACTIVE', 'REJECTED'],
    REJECTED: [],
  };
  const fmtPct1 = v => v == null ? '—' : (Number(v) * 100).toFixed(1) + '%';

  function syncLrRegButtons() {
    if (!$('lr-registry-section')) return;
    const job = (lrStatusData?.jobs || []).find(j => j.job_id === selectedLrJobId);
    $('btn-lr-reg-register').disabled = busy || !job || !job.decrypted_model;

    const models = lrRegistryData?.models || [];
    const cur = models.find(m => m.registry_id === selectedLrRegId) || models[0] || null;
    const st = cur?.lifecycle_state || '';
    $('btn-lr-reg-validate').disabled = busy || !cur || !['VALIDATING', 'BLOCKED', 'ROLLED_BACK'].includes(st);

    const allowed = REG_ALLOWED[st] || [];
    const reasonOk = ($('lr-reg-reason')?.value || '').trim().length >= 10;
    const revOk = Boolean($('lr-reg-reviewed')?.checked);
    const qaOk = Boolean(cur?.quality_approved);

    $('btn-lr-tr-shadow').disabled = busy || !cur || !allowed.includes('SHADOW') || !reasonOk;
    $('btn-lr-tr-approve').disabled = busy || !cur || !allowed.includes('APPROVED') || !qaOk || !revOk || !reasonOk;
    $('btn-lr-tr-activate').disabled = busy || !cur || !allowed.includes('ACTIVE') || !qaOk || !cur?.approval_record || !reasonOk;
    $('btn-lr-tr-rollback').disabled = busy || !cur || !allowed.includes('ROLLED_BACK') || !cur?.rollback_target || !reasonOk;
    $('btn-lr-tr-block').disabled = busy || !cur || !allowed.includes('BLOCKED') || !reasonOk;
    $('btn-lr-tr-reject').disabled = busy || !cur || !allowed.includes('REJECTED') || !reasonOk;
  }

  function renderLrRegistry() {
    if (!$('lr-registry-section') || !lrRegistryData) return;
    const models = lrRegistryData.models || [];
    const active = lrRegistryData.active_model;
    const actBadge = $('lr-reg-active-badge');
    if (active) {
      actBadge.className = 'status-pill status-active';
      actBadge.textContent = `ACTIVE · ${active.model_version}`;
    } else {
      actBadge.className = 'status-pill status-idle';
      actBadge.textContent = 'Chưa có LR ACTIVE';
    }

    if (!selectedLrRegId || !models.some(m => m.registry_id === selectedLrRegId)) {
      selectedLrRegId = models[0]?.registry_id || null;
    }
    const cur = models.find(m => m.registry_id === selectedLrRegId) || null;

    // Registry list table
    const listWrap = $('lr-reg-list-wrap');
    listWrap.hidden = !models.length;
    if (models.length) {
      $('lr-reg-body').replaceChildren(...models.map(m => {
        const tr = el('tr', undefined, m.registry_id === selectedLrRegId ? 'selected-row' : '');
        const tdSt = el('td'); tdSt.append(el('span', m.lifecycle_state, 'status-pill ' + (REG_STATE_CLS[m.lifecycle_state] || 'status-idle')));
        const tdQa = el('td'); tdQa.append(el('span', m.quality_approved ? 'quality_approved = true' : 'quality_approved = false', 'status-pill ' + (m.quality_approved ? 'status-active' : 'status-review')));
        const recTxt = m.metrics?.recall_class_1 != null ? fmtPct1(m.metrics.recall_class_1) : 'Chưa đo';
        const fpTxt = m.metrics?.false_positives_per_1000 != null ? String(m.metrics.false_positives_per_1000) : '—';
        const actRb = [m.activation_timestamp ? fmtDateTime(m.activation_timestamp) : null, m.rollback_target ? `RB→${m.rollback_target.slice(0, 12)}…` : null].filter(Boolean).join(' · ') || '—';
        tr.append(el('td', m.model_version, 'mono-cell'), tdSt, tdQa, el('td', recTxt), el('td', fpTxt), el('td', actRb));
        tr.onclick = () => { selectedLrRegId = m.registry_id; renderLrRegistry(); };
        return tr;
      }));
    }

    const box = $('lr-reg-detail-box');
    if (!cur) {
      box.hidden = true;
      syncLrRegButtons();
      return;
    }
    box.hidden = false;

    $('lr-reg-title').textContent = `${cur.model_version} (${cur.registry_id})`;
    $('lr-reg-sub').textContent = `Job nguồn: ${cur.source_job_id || '—'} · Mạch: ${cur.circuit_version || '—'} · Schema: ${(cur.feature_schema_hash || '').slice(0, 16)}…`;

    const stPill = $('lr-reg-state-pill');
    stPill.className = 'status-pill ' + (REG_STATE_CLS[cur.lifecycle_state] || 'status-idle');
    stPill.textContent = cur.lifecycle_state;

    const qaPill = $('lr-reg-qa-pill');
    qaPill.className = 'status-pill ' + (cur.quality_approved ? 'status-active' : 'status-review');
    qaPill.textContent = cur.quality_approved ? 'quality_approved = true' : 'quality_approved = false';

    // Lifecycle stepper
    const mainStages = ['TRAINING', 'VALIDATING', 'CANDIDATE', 'SHADOW', 'APPROVED', 'ACTIVE'];
    const curIdx = mainStages.indexOf(cur.lifecycle_state);
    const stepBox = $('lr-reg-stepper');
    stepBox.replaceChildren();
    mainStages.forEach((stName, idx) => {
      const cls = curIdx === idx ? 'lr-stage-node current' : (curIdx > idx ? 'lr-stage-node done' : 'lr-stage-node');
      stepBox.append(el('span', stName, cls));
      if (idx < mainStages.length - 1) stepBox.append(el('span', '→', 'lr-stage-arrow'));
    });
    if (curIdx === -1) {
      stepBox.append(el('span', '|', 'lr-stage-arrow'), el('span', cur.lifecycle_state, 'lr-stage-node blocked-state'));
    }

    // 9 Mandatory Metrics + Quality Gate + 4-Way Comparison
    const mWrap = $('lr-reg-metrics-wrap');
    const met = cur.metrics;
    mWrap.hidden = !met;
    if (met) {
      const cm = met.confusion_matrix || {};
      const fheErr = met.fhe_error_vs_reference || {};
      const implPass = fheErr.implementation_error?.pass;
      const qDiff = fheErr.quantization_error?.weight_max_abs_diff;
      $('lr-reg-metrics-grid').replaceChildren(...[
        ['1. Recall lớp 1 (95% CI)', `${fmtPct1(met.recall_class_1)} (${fmtPct1(met.recall_wilson_95ci?.[0])}–${fmtPct1(met.recall_wilson_95ci?.[1])})`],
        ['2. Precision lớp 1', fmtPct1(met.precision_class_1)],
        ['3. F1-score', met.f1_score != null ? Number(met.f1_score).toFixed(4) : '—'],
        ['4. PR-AUC', met.pr_auc != null ? Number(met.pr_auc).toFixed(4) : '—'],
        ['5. FP / 1.000 giao dịch', `${met.false_positives_per_1000 ?? '—'} FP/1.000`],
        ['6. Confusion Matrix', `TP=${cm.tp ?? 0} · FP=${cm.fp ?? 0} · TN=${cm.tn ?? 0} · FN=${cm.fn ?? 0}`],
        ['7. Thời gian train', fmtSec(met.train_time_seconds)],
        ['8. Thời gian inference', `${met.inference_time_ms ?? '—'} ms (${met.inference_ms_per_1000_tx ?? '—'} ms/1k GD)`],
        ['9. Sai số FHE vs tham chiếu', `${implPass ? 'Triển khai = 0 lỗi' : 'Chưa đạt parity'}${qDiff != null ? ` · ΔW_quant=${qDiff}` : ''}`],
      ].map(([k, v]) => {
        const b = el('div', undefined, 'kpi-box');
        b.append(el('span', k), el('strong', v));
        return b;
      }));

      // Quality Gate checks
      const gChecks = cur.quality_gate?.checks || [];
      $('lr-reg-gate-grid').replaceChildren(...gChecks.map(c => {
        const item = el('div', undefined, 'chk-item ' + (c.passed ? 'pass' : 'fail'));
        const w = el('div');
        w.append(el('strong', c.label), el('small', c.detail));
        item.append(el('span', c.passed ? '✓' : '✕', 'chk-icon'), w);
        return item;
      }));

      // Incremental value summary
      const inc = cur.incremental_value || {};
      const incBox = $('lr-reg-incremental-box');
      incBox.className = 'lr-incremental-box ' + (inc.verdict === 'negative_excess_false_positives' ? 'warn' : inc.verdict === 'neutral_no_gain' ? 'neutral' : '');
      incBox.textContent = inc.summary_vi || 'Chưa có dữ liệu giá trị bổ sung.';

      // 4-Way Comparison table
      const cmp = cur.comparisons || {};
      const rowsCmp = [
        { name: `LR mới (${cur.model_version})`, m: met },
        { name: '1. Logistic Regression baseline (float)', m: cmp.lr_baseline },
        {
          name: cmp.previous_lr_version?.available
            ? `2. LR phiên bản trước (${cmp.previous_lr_version.model_version})`
            : '2. LR phiên bản trước (Chưa có phiên bản trước)',
          m: cmp.previous_lr_version?.available ? cmp.previous_lr_version.metrics : null,
        },
        { name: '3. Pipeline 4 phương pháp (chưa có LR)', m: cmp.pipeline_4_methods },
        { name: '4. Pipeline 5 phương pháp (có LR mới)', m: cmp.pipeline_5_methods },
      ];
      $('lr-reg-compare-body').replaceChildren(...rowsCmp.map(({ name, m }) => {
        const tr = el('tr');
        if (!m) {
          tr.append(el('td', name), el('td', '—'), el('td', '—'), el('td', '—'), el('td', '—'), el('td', '—'), el('td', 'Chưa khả dụng'));
        } else {
          const c = m.confusion_matrix || {};
          tr.append(
            el('td', name),
            el('td', fmtPct1(m.recall_class_1)),
            el('td', fmtPct1(m.precision_class_1)),
            el('td', m.f1_score != null ? Number(m.f1_score).toFixed(4) : '—'),
            el('td', m.pr_auc != null ? Number(m.pr_auc).toFixed(4) : '—'),
            el('td', String(m.false_positives_per_1000 ?? '—')),
            el('td', `${c.tp ?? 0}/${c.fp ?? 0}/${c.tn ?? 0}/${c.fn ?? 0}`, 'mono-cell')
          );
        }
        return tr;
      }));
    }

    // Metadata & disclosable provenance
    const prov = cur.training_data_provenance || {};
    const tc = cur.training_configuration || {};
    const appRec = cur.approval_record;
    const dl = $('lr-reg-meta-dl');
    dl.replaceChildren();
    for (const [k, v] of [
      ['Model version', cur.model_version],
      ['Feature schema hash', cur.feature_schema_hash || '—'],
      ['Circuit version', `${cur.circuit_version || '—'} · build ${(tc.build_sha256 || '').slice(0, 16) || '—'}`],
      ['Training config', `mode=${tc.mode || '—'}, w=${JSON.stringify(tc.coefficients)}, b=${tc.intercept}, tau=${tc.threshold ?? '—'}`],
      ['Data provenance (công bố)', `train=${prov.train_sample_count ?? 0} (+${prov.train_positive_count ?? 0}/-${prov.train_negative_count ?? 0}), eval=${prov.eval_sample_count ?? 0} (+${prov.eval_positive_count ?? 0}/-${prov.eval_negative_count ?? 0}), simulated=${prov.simulated ? 'có' : 'không'}, privacy_redacted=true`],
      ['Approval record', appRec ? `${appRec.approved_by} lúc ${fmtDateTime(appRec.approved_at)} · Ed25519 ${(appRec.signature_envelope?.payload_sha256 || '').slice(0, 14)}…` : 'Chưa phê duyệt'],
      ['Activation timestamp', cur.activation_timestamp ? fmtDateTime(cur.activation_timestamp) : 'Chưa kích hoạt'],
      ['Rollback target', cur.rollback_target || 'Chưa có (phiên bản đầu tiên)'],
    ]) {
      dl.append(el('dt', k), el('dd', v));
    }

    syncLrRegButtons();
  }

  async function loadLrRegistry() {
    if (!company || !$('lr-registry-section')) return;
    try {
      lrRegistryData = await api(basePath() + '/lr-registry');
      renderLrRegistry();
    } catch (err) {
      // Non-blocking if backend not configured
    }
  }

  if ($('btn-lr-reg-register')) {
    $('btn-lr-reg-register').onclick = async () => {
      if (busy || !selectedLrJobId) return;
      busy = true; setNotice(''); setSuccess('');
      $('lr-reg-status').textContent = 'Đang đăng ký phiên bản LR vào Registry…';
      syncLrRegButtons();
      try {
        const res = await api(basePath() + '/lr-registry/register', { job_id: selectedLrJobId });
        selectedLrRegId = res.model.registry_id;
        await loadLrRegistry();
        setSuccess(`Đã đăng ký ${res.model.model_version} vào LR Model Registry ở trạng thái VALIDATING (quality_approved = false).`);
      } catch (err) {
        setNotice(err.message);
      } finally {
        busy = false; $('lr-reg-status').textContent = ''; syncLrRegButtons();
      }
    };
  }

  if ($('btn-lr-reg-validate')) {
    $('btn-lr-reg-validate').onclick = async () => {
      if (busy || !selectedLrRegId) return;
      busy = true; setNotice(''); setSuccess('');
      $('lr-reg-status').textContent = 'Đang chạy đánh giá R5 (9 metrics & so sánh 4 mốc)…';
      syncLrRegButtons();
      try {
        const res = await api(basePath() + '/lr-registry/validate', {
          registry_id: selectedLrRegId,
          eval_mode: $('lr-reg-eval-mode').value,
        });
        await loadLrRegistry();
        if (res.model.quality_approved) {
          setSuccess(`Validation R5 ĐẠT cổng chất lượng cho ${res.model.model_version} -> CANDIDATE (quality_approved = true).`);
        } else {
          setNotice(`Validation R5 CHẶN ${res.model.model_version} -> BLOCKED (quality_approved = false): ${(res.model.quality_gate?.blocking_reasons || []).map(r => r.code).join(', ')}.`);
        }
      } catch (err) {
        setNotice(err.message);
      } finally {
        busy = false; $('lr-reg-status').textContent = ''; syncLrRegButtons();
      }
    };
  }

  for (const btnId of ['btn-lr-tr-shadow', 'btn-lr-tr-approve', 'btn-lr-tr-activate', 'btn-lr-tr-rollback', 'btn-lr-tr-block', 'btn-lr-tr-reject']) {
    const b = $(btnId);
    if (!b) continue;
    b.onclick = async () => {
      if (busy || !selectedLrRegId) return;
      const targetState = b.dataset.targetState;
      busy = true; setNotice(''); setSuccess('');
      $('lr-reg-status').textContent = `Đang chuyển sang ${targetState}…`;
      syncLrRegButtons();
      try {
        const res = await api(basePath() + '/lr-registry/transition', {
          registry_id: selectedLrRegId,
          target_state: targetState,
          reason: $('lr-reg-reason').value.trim(),
          reviewed_evidence: $('lr-reg-reviewed').checked,
        });
        $('lr-reg-reason').value = '';
        $('lr-reg-reviewed').checked = false;
        await loadLrRegistry();
        setSuccess(`Đã chuyển ${res.model.model_version} sang trạng thái ${res.model.lifecycle_state}.`);
      } catch (err) {
        setNotice(err.message);
      } finally {
        busy = false; $('lr-reg-status').textContent = ''; syncLrRegButtons();
      }
    };
  }

  if ($('lr-reg-reason')) $('lr-reg-reason').oninput = syncLrRegButtons;
  if ($('lr-reg-reviewed')) $('lr-reg-reviewed').onchange = syncLrRegButtons;

  syncLrEpochBounds();
  syncLrModeUI();

  async function init() {
    token = sessionStorage.getItem('kt-session') || '';
    if (!mount || !token) {
      setNotice('Mở Agent2 từ Portal và đăng nhập bằng tài khoản quản lý để truy cập Huấn luyện & quản lý mô hình.');
      return;
    }
    try {
      const ctx = await api('/api/v1/ui/context');
      actor = ctx.actor_id;
      context = ctx.context_id || '';
      const hash = new URLSearchParams(location.hash.slice(1));
      company = ctx.companies.includes(hash.get('company')) ? hash.get('company') : (ctx.companies[0] || '');
      $('company').replaceChildren(...ctx.companies.map(id => { const o = el('option', id); o.value = id; return o; }));
      $('company').value = company;
      $('company').disabled = !company;
      if (!company) { setNotice('Chưa được cấp quyền doanh nghiệp.'); return; }
      remember();
      setStep(4);
      await loadOverview();
    } catch (err) {
      setNotice(err.message);
    }
  }

  init();
})();
