'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  let token = '', actorID = '', contextID = '', company = '', epoch = 0, controller = null, busy = false, pollTimer = null;
  let state = null, snapshots = [], approvedModels = [], shadowRuns = [], currentShadowView = null, currentShadowMode = '', customJsonEdited = false;
  const idemKeys = new Map();

  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = String(text);
    if (cls) el.className = cls;
    return el;
  };

  function notice(text) {
    $('bt-notice').textContent = text || '';
    $('bt-notice').hidden = !text;
  }

  function base() {
    return '/api/v1/companies/' + encodeURIComponent(company) + '/batch-training';
  }

  async function api(path, body) {
    const headers = mount ? { 'X-Session': token, 'X-Platform': '1' } : { 'Authorization': 'Bearer ' + token };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      const sig = company + '|' + path + '|' + JSON.stringify(body);
      if (!idemKeys.has(sig)) idemKeys.set(sig, crypto.randomUUID());
      headers['Idempotency-Key'] = idemKeys.get(sig);
    }
    const res = await fetch(mount + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
      signal: controller?.signal,
    });
    const val = await res.json();
    if (!res.ok) {
      const msg = val.error?.message
        ? (val.error.message + (val.error.remediation ? ' ' + val.error.remediation : ''))
        : (val.errors?.map(e => e.message + ' ' + e.action).join('\n') || 'Chưa thực hiện được thao tác.');
      const err = new Error(msg);
      err.status = res.status;
      err.code = val.error?.code;
      throw err;
    }
    return val;
  }

  async function runTask(fn) {
    if (busy) return;
    busy = true;
    const e = epoch;
    updateControls();
    notice('');
    try {
      await fn(e);
    } catch (err) {
      if (e === epoch && err.name !== 'AbortError') {
        notice(err.message);
      }
    } finally {
      if (e === epoch) {
        busy = false;
        updateControls();
      }
    }
  }

  function currentSnapshotObj() {
    const sid = $('bt-snapshot').value;
    return snapshots.find(s => s.snapshot_id === sid) || null;
  }

  function populateDefaultBatchesFromSnapshot(snap) {
    if (!snap) return;
    const txs = snap.transactions || [];
    const tCount = Number($('bt-train-batch-count').value) || 2;
    const eCount = Number($('bt-eval-batch-count').value) || 1;
    if (!$('bt-train-start').value && txs.length > 0) {
      const firstTs = new Date(txs[0].occurred_at || '2026-01-02T00:00:00Z');
      const startIso = new Date(firstTs.getTime() - 24 * 3600 * 1000).toISOString().replace('.000Z', 'Z');
      const splitIdx = Math.min(txs.length - 1, tCount * 4);
      const splitTs = new Date(txs[splitIdx]?.occurred_at || '2026-01-20T00:00:00Z');
      const midIso = new Date(splitTs.getTime() - 1800 * 1000).toISOString().replace('.000Z', 'Z');
      const lastTs = new Date(txs[txs.length - 1]?.occurred_at || '2026-01-28T00:00:00Z');
      const endIso = new Date(lastTs.getTime() + 24 * 3600 * 1000).toISOString().replace('.000Z', 'Z');
      const asOfIso = new Date(lastTs.getTime() + 48 * 3600 * 1000).toISOString().replace('.000Z', 'Z');
      $('bt-train-start').value = startIso;
      $('bt-train-end').value = midIso;
      $('bt-eval-start').value = midIso;
      $('bt-eval-end').value = endIso;
      $('bt-as-of').value = asOfIso;
    }
    renderBatchSelectors(snap, null);
  }

  function renderBatchSelectors(snap, existingReq) {
    const wrap = $('bt-batch-selectors');
    wrap.replaceChildren();
    if (!snap) return;
    const txs = snap.transactions || [];
    const tCount = existingReq?.training_batches?.length || Number($('bt-train-batch-count').value) || 2;
    const eCount = existingReq?.evaluation_batches?.length || Number($('bt-eval-batch-count').value) || 1;
    $('bt-train-batch-count').value = String(tCount);
    $('bt-eval-batch-count').value = String(eCount);

    let cursor = 0;
    const buildGroup = (title, prefix, count, existingBatches) => {
      const sec = node('div');
      sec.append(node('h3', title));
      for (let b = 0; b < count; b++) {
        const card = node('div', null, 'panel compact');
        card.append(node('strong', `${prefix} #${b + 1} (4 giao dịch)`));
        const grid = node('div', null, 'grid');
        for (let r = 0; r < 4; r++) {
          const sel = document.createElement('select');
          sel.dataset.partition = prefix === 'Batch train' ? 'training' : 'evaluation';
          sel.dataset.batchIndex = String(b);
          sel.dataset.rowIndex = String(r);
          txs.forEach(tx => {
            const opt = node('option', `${tx.record_id} (v${tx.revision}) · ${tx.occurred_at || ''}`);
            opt.value = JSON.stringify({ record_id: tx.record_id, revision: tx.revision });
            sel.append(opt);
          });
          const wanted = existingBatches?.[b]?.[r] || txs[cursor];
          cursor++;
          if (wanted) {
            const val = JSON.stringify({ record_id: wanted.record_id, revision: wanted.revision });
            if ([...sel.options].some(o => o.value === val)) sel.value = val;
          }
          sel.addEventListener('change', () => {
            customJsonEdited = false;
            syncRequestJsonFromForm();
          });
          grid.append(sel);
        }
        card.append(grid);
        sec.append(card);
      }
      wrap.append(sec);
    };

    buildGroup('Danh sách batch train', 'Batch train', tCount, existingReq?.training_batches);
    buildGroup('Danh sách batch đánh giá giữ riêng', 'Batch đánh giá', eCount, existingReq?.evaluation_batches);
    customJsonEdited = false;
    syncRequestJsonFromForm();
  }

  function buildRequestFromForm() {
    if (customJsonEdited && $('bt-plan-request-json').value.trim()) {
      return JSON.parse($('bt-plan-request-json').value);
    }
    const tCount = Number($('bt-train-batch-count').value) || 2;
    const eCount = Number($('bt-eval-batch-count').value) || 1;
    const training_batches = [];
    for (let b = 0; b < tCount; b++) {
      const rows = [];
      for (let r = 0; r < 4; r++) {
        const sel = document.querySelector(`select[data-partition="training"][data-batch-index="${b}"][data-row-index="${r}"]`);
        if (sel && sel.value) rows.push(JSON.parse(sel.value));
      }
      training_batches.push(rows);
    }
    const evaluation_batches = [];
    for (let b = 0; b < eCount; b++) {
      const rows = [];
      for (let r = 0; r < 4; r++) {
        const sel = document.querySelector(`select[data-partition="evaluation"][data-batch-index="${b}"][data-row-index="${r}"]`);
        if (sel && sel.value) rows.push(JSON.parse(sel.value));
      }
      evaluation_batches.push(rows);
    }
    return {
      version: 'snapshot-he-batch-plan/0.1.0',
      snapshot_id: $('bt-snapshot').value,
      as_of: $('bt-as-of').value.trim(),
      training_start: $('bt-train-start').value.trim(),
      training_end: $('bt-train-end').value.trim(),
      evaluation_start: $('bt-eval-start').value.trim(),
      evaluation_end: $('bt-eval-end').value.trim(),
      training_batches,
      evaluation_batches,
    };
  }

  function syncRequestJsonFromForm() {
    try {
      const req = buildRequestFromForm();
      $('bt-plan-request-json').value = JSON.stringify(req, null, 2);
    } catch {
      /* ignore transient parse issues */
    }
  }

  function renderPlanSection(sess) {
    const ov = $('bt-plan-overview');
    const iss = $('bt-plan-issues');
    ov.replaceChildren();
    iss.replaceChildren();
    const ps = sess?.plan_summary;
    if (!ps) {
      ov.append(node('p', 'Chưa ghim kế hoạch cho doanh nghiệp này. Chọn dữ liệu và bấm "Kiểm tra và ghim kế hoạch".', 'hint'));
      $('bt-step1-tech').textContent = '';
      return;
    }
    const statusText = ps.status === 'ready'
      ? `Kế hoạch hợp lệ (ready) · ${ps.training_rows} giao dịch train (${ps.training_batch_count} batch) · ${ps.evaluation_rows} giao dịch đánh giá (${ps.evaluation_batch_count} batch)`
      : `Kế hoạch bị từ chối (rejected) · Phát hiện ${ps.issues.length} lỗi nguồn/feature`;
    ov.append(node('p', statusText, ps.status === 'ready' ? 'callout' : 'issue'));

    const tbl = document.createElement('table');
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    ['Phân vùng', 'Batch', 'Số giao dịch', 'Danh sách mã giao dịch', 'Trạng thái'].forEach(h => hr.append(node('th', h)));
    thead.append(hr);
    const tbody = document.createElement('tbody');
    ps.batches.forEach(b => {
      const tr = document.createElement('tr');
      tr.append(
        node('td', b.partition === 'training' ? 'Tập train' : 'Tập đánh giá giữ riêng'),
        node('td', `#${b.batch_index + 1}`),
        node('td', b.row_count),
        node('td', b.row_ids.join(', ')),
        node('td', b.status === 'ready' ? 'Đạt (ready)' : `Lỗi (${b.issues.length})`)
      );
      tbody.append(tr);
    });
    tbl.append(thead, tbody);
    ov.append(tbl);

    if (ps.issues && ps.issues.length) {
      const list = node('div', null, 'issue');
      list.append(node('strong', 'Lỗi nguồn/feature cần xử lý trước khi tiếp tục:'));
      ps.issues.forEach(item => {
        list.append(node('p', `[${item.partition} #${item.batch_index + 1} · ${item.record_id}] ${item.code}: ${item.message} (${item.remediation})`));
      });
      iss.append(list);
    }
    $('bt-step1-tech').textContent = JSON.stringify({
      plan_sha256: ps.plan_sha256,
      mapping_fingerprint: ps.mapping_fingerprint,
      simulated: ps.simulated,
      windows: ps.windows,
      batches: ps.batches,
    }, null, 2);
  }

  function renderLabelSection(sess) {
    const ov = $('bt-label-overview');
    const tblWrap = $('bt-label-packets-table');
    ov.replaceChildren();
    tblWrap.replaceChildren();
    const ls = sess?.label_status;
    if (!ls || !ls.created) {
      ov.append(node('p', 'Chưa tạo gói xác minh nhãn cho kế hoạch hiện tại.', 'hint'));
      $('bt-step2-tech').textContent = '';
      return;
    }
    const allPkts = [...(ls.training_packets || []), ...(ls.evaluation_packets || [])];
    const summaryText = ls.ready_to_confirm
      ? `Tất cả ${ls.training_packets.length} batch train đã khóa nhãn đầy đủ và có đủ 2 lớp {0, 1}.`
      : `Trạng thái nhãn: ${ls.blocking_reasons.join(' ')}`;
    ov.append(node('p', summaryText, ls.ready_to_confirm ? 'callout' : 'hint'));

    const tbl = document.createElement('table');
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    ['Phân vùng', 'Batch', 'Giao dịch', 'Đã gán nhãn', 'Gian lận / Không gian lận', 'Trạng thái khóa', 'Màn hình xác minh'].forEach(h => hr.append(node('th', h)));
    thead.append(hr);
    const tbody = document.createElement('tbody');
    allPkts.forEach(p => {
      const tr = document.createElement('tr');
      const linkTd = document.createElement('td');
      const a = node('a', 'Mở xác minh nhãn');
      a.href = `label-verification#company=${encodeURIComponent(company)}&packet=${encodeURIComponent(p.packet_id)}`;
      linkTd.append(a);
      tr.append(
        node('td', p.partition === 'training' ? 'Batch train' : 'Batch đánh giá'),
        node('td', `#${p.batch_index + 1}`),
        node('td', p.row_ids.join(', ')),
        node('td', `${p.labelled_count}/${p.row_count}` + (p.missing_count ? ` (trống ${p.missing_count})` : '')),
        node('td', `${p.fraud_count} / ${p.non_fraud_count}`),
        node('td', p.locked ? `Đã khóa (v${p.revision})` : `Đang rà (v${p.revision})`),
        linkTd
      );
      tbody.append(tr);
    });
    tbl.append(thead, tbody);
    tblWrap.append(tbl);
    $('bt-step2-tech').textContent = JSON.stringify(ls, null, 2);
  }

  function renderConfirmSection(sess) {
    const dl = $('bt-confirm-summary');
    const blk = $('bt-confirm-blockers');
    dl.replaceChildren();
    blk.replaceChildren();
    const ps = sess?.plan_summary;
    const ls = sess?.label_status;
    if (!ps) {
      $('bt-step3-tech').textContent = '';
      return;
    }
    const maxEpochs = Math.max(1, Math.floor(4 / Math.max(1, ps.training_batch_count)));
    [...$('bt-epochs').options].forEach(opt => {
      opt.disabled = Number(opt.value) > maxEpochs;
    });
    if (sess.job_id && sess.epochs && Number($('bt-epochs').value) !== sess.epochs && sess.epochs <= maxEpochs) {
      $('bt-epochs').value = String(sess.epochs);
    } else if (Number($('bt-epochs').value) > maxEpochs) {
      $('bt-epochs').value = '1';
    }
    const chosenEpochs = Number($('bt-epochs').value) || 1;
    const pairs = [
      ['Doanh nghiệp', company],
      ['Snapshot', ps.snapshot?.snapshot_id || '—'],
      ['Số dòng train / đánh giá', `${ps.training_rows} dòng train / ${ps.evaluation_rows} dòng đánh giá giữ riêng`],
      ['Số batch', `${ps.training_batch_count} batch train / ${ps.evaluation_batch_count} batch đánh giá`],
      ['Số epoch', `${chosenEpochs} epoch (tổng ${ps.training_batch_count * chosenEpochs}/4 bước cập nhật)`],
      ['Tình trạng nhãn', ls?.ready_to_confirm ? 'Đã khóa đủ các batch train, không còn nhãn trống, đủ 2 lớp {0, 1}' : 'Chưa đủ điều kiện xác nhận train'],
    ];
    pairs.forEach(([k, v]) => {
      dl.append(node('dt', k), node('dd', v));
    });
    if (ls?.blocking_reasons?.length) {
      ls.blocking_reasons.forEach(r => blk.append(node('p', r, 'issue')));
    }
    $('bt-step3-tech').textContent = JSON.stringify({
      expected_plan_sha256: sess.plan_sha256,
      recommended_locks: ls?.recommended_locks || [],
      pinned_locks: sess.locks,
      epochs: chosenEpochs,
      total_updates: ps.training_batch_count * chosenEpochs,
    }, null, 2);
  }

  function renderProgressSection(sess) {
    const st = $('bt-progress-status');
    const bar = $('bt-progress-bar');
    const cnt = $('bt-progress-counts');
    if (!sess || !sess.job_id) {
      st.textContent = 'Chưa bắt đầu phiên train trên worker.';
      bar.hidden = true;
      cnt.textContent = '';
      $('bt-step4-tech').textContent = '';
      return;
    }
    const wj = sess.worker_job || {};
    const done = Number(wj.completed_updates ?? 0);
    const total = Number(wj.total_updates ?? ((sess.plan_summary?.training_batch_count || 2) * (sess.epochs || 1)));
    st.textContent = `Trạng thái: ${sess.status_label} · Mã công việc: ${sess.job_id}`;
    bar.hidden = false;
    bar.max = Math.max(1, total);
    bar.value = Math.min(done, total);
    cnt.textContent = `Tiến độ cập nhật bản mã: ${done}/${total} bước cập nhật hoàn tất (Epoch hoàn tất: ${wj.completed_epochs ?? 0}/${wj.epochs ?? sess.epochs ?? 1})`
      + (wj.inflight_update !== null && wj.inflight_update !== undefined ? ` · Đang dở bước cập nhật #${wj.inflight_update}` : '');
    $('bt-step4-tech').textContent = JSON.stringify({
      phase: sess.phase,
      run_id: sess.run_id,
      dataset_id: sess.dataset_id,
      job_id: sess.job_id,
      consent_sha256: sess.consent_sha256,
      worker_reachable: sess.worker_reachable,
      worker_job: wj,
      last_error: sess.last_error,
    }, null, 2);
  }

  function renderReceiveSection(sess) {
    const st = $('bt-candidate-status');
    const cand = sess?.candidate;
    if (!cand) {
      st.textContent = 'Chưa nhận model ứng viên tại doanh nghiệp.';
      $('bt-step5-tech').textContent = '';
      return;
    }
    st.textContent = `${cand.status_label} · Đối chiếu oracle: ${cand.validation} · Chưa tự thay thế model đang chạy (operational_activation=false).`;
    $('bt-step5-tech').textContent = JSON.stringify(cand, null, 2);
  }

  function renderEvalSection(sess) {
    const sum = $('bt-eval-summary');
    const tblWrap = $('bt-eval-table');
    sum.replaceChildren();
    tblWrap.replaceChildren();
    const ev = sess?.evaluation;
    if (!ev) {
      sum.append(node('p', 'Chưa chạy đánh giá trên tập giữ riêng.', 'hint'));
      $('bt-step6-tech').textContent = '';
      return;
    }
    sum.append(node('p',
      `Nguồn đánh giá: Snapshot ${ev.snapshot_id || sess.plan_summary?.snapshot?.snapshot_id} · Số dòng giữ riêng: ${ev.evaluation_rows} giao dịch · `
      + `Tách biệt khỏi tập train: ${ev.held_out_from_training ? 'Có' : 'Không'} · Điểm chưa hiệu chỉnh (uncalibrated=true, accuracy=null).`
    ));
    const tbl = document.createElement('table');
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    ['Batch giữ riêng', 'Mã giao dịch', 'Điểm đối chiếu (chưa hiệu chỉnh)', 'Nhãn xác minh (chỉ đối chiếu, ngoài fit)'].forEach(h => hr.append(node('th', h)));
    thead.append(hr);
    const tbody = document.createElement('tbody');
    (ev.rows || []).forEach(r => {
      const tr = document.createElement('tr');
      tr.append(
        node('td', r.batch_index !== undefined ? `#${r.batch_index + 1}` : '—'),
        node('td', r.record_id),
        node('td', Number(r.score).toFixed(6)),
        node('td', r.verified_outcome || 'Không kèm nhãn / giữ riêng')
      );
      tbody.append(tr);
    });
    tbl.append(thead, tbody);
    tblWrap.append(tbl);
    $('bt-step6-tech').textContent = JSON.stringify({
      evaluation_sha256: sess.evaluation_sha256,
      evaluation: ev,
    }, null, 2);
  }

  function renderApprovalSection(sess) {
    const sum = $('bt-approval-summary');
    const shWrap = $('bt-shadow-results');
    sum.replaceChildren();
    shWrap.replaceChildren();
    const app = sess?.approval;
    if (!app) {
      sum.append(node('p', 'Model ứng viên chưa được phê duyệt dùng shadow. Mọi yêu cầu chấm shadow sẽ bị chặn cho tới khi phê duyệt.', 'hint'));
      $('bt-step7-btn').textContent = 'Phê duyệt dùng đối chiếu shadow';
    } else {
      sum.append(node('p',
        `Đã phê duyệt dùng đối chiếu shadow bởi ${app.actor_id} lúc ${new Date(app.at).toLocaleString('vi-VN')} · Lý do: "${app.reason}" · `
        + `Chỉ chạy đối chiếu shadow (shadow_only=true, active_model_replaced=false, operational_queue_changed=false).`,
        'callout'
      ));
      $('bt-approve-reason').value = app.reason;
      $('bt-step7-btn').textContent = 'Chạy đối chiếu shadow trên tập giữ riêng';
    }
    if (sess?.shadow) {
      const sh = sess.shadow;
      shWrap.append(node('h3', 'Kết quả chấm đối chiếu shadow trên tập giữ riêng'));
      shWrap.append(node('p', `Số giao dịch chấm shadow: ${sh.rows?.length || 0} · Model đang chạy và hàng đợi nghiệp vụ được giữ nguyên.`));
      const tbl = document.createElement('table');
      const thead = document.createElement('thead');
      const hr = document.createElement('tr');
      ['Mã giao dịch', 'Điểm shadow (chưa hiệu chỉnh)'].forEach(h => hr.append(node('th', h)));
      thead.append(hr);
      const tbody = document.createElement('tbody');
      (sh.rows || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.append(node('td', r.record_id), node('td', Number(r.score).toFixed(6)));
        tbody.append(tr);
      });
      tbl.append(thead, tbody);
      shWrap.append(tbl);
    }
    $('bt-step7-tech').textContent = JSON.stringify({
      approval: app || null,
      shadow: sess?.shadow || null,
    }, null, 2);
  }

  function shadowStorageKey(comp) {
    return 'agent2.shadow.selection.' + (actorID || '') + '.' + (comp || '');
  }

  function saveShadowSelectionState() {
    if (!company || !actorID) return;
    try {
      sessionStorage.setItem(shadowStorageKey(company), JSON.stringify({
        version: 1,
        actor: actorID,
        company,
        shadow_run_id: $('bt-shadow-history')?.value || '',
        model_run_id: $('bt-shadow-model')?.value || '',
        snapshot_id: $('bt-shadow-snapshot')?.value || '',
        as_of: $('bt-shadow-as-of')?.value || '',
        sort: $('bt-shadow-sort')?.value || 'score_desc',
      }));
    } catch {
      /* optional */
    }
  }

  function loadShadowSelectionState(comp) {
    if (!comp || !actorID) return null;
    try {
      const raw = sessionStorage.getItem(shadowStorageKey(comp));
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && parsed.actor === actorID && parsed.company === comp) return parsed;
    } catch {
      /* optional */
    }
    return null;
  }

  function selectedApprovedModelObj() {
    const mid = $('bt-shadow-model')?.value || '';
    return approvedModels.find(m => m.model_run_id === mid) || null;
  }

  function selectedShadowSnapshotObj() {
    const sid = $('bt-shadow-snapshot')?.value || '';
    return snapshots.find(s => s.snapshot_id === sid) || null;
  }

  function populateShadowSelectors(preserveSelection = true) {
    const modelSel = $('bt-shadow-model');
    const snapSel = $('bt-shadow-snapshot');
    const histSel = $('bt-shadow-history');
    if (!modelSel || !snapSel || !histSel) return;

    const saved = loadShadowSelectionState(company);
    const prevModel = preserveSelection ? (modelSel.value || saved?.model_run_id || '') : (saved?.model_run_id || '');
    const prevSnap = preserveSelection ? (snapSel.value || saved?.snapshot_id || '') : (saved?.snapshot_id || '');
    const prevHist = preserveSelection ? (histSel.value || saved?.shadow_run_id || '') : (saved?.shadow_run_id || '');
    const prevAsOf = preserveSelection ? ($('bt-shadow-as-of').value || saved?.as_of || '') : (saved?.as_of || '');
    const prevSort = preserveSelection ? ($('bt-shadow-sort').value || saved?.sort || 'score_desc') : (saved?.sort || 'score_desc');

    const defaultModelOpt = node('option', approvedModels.length
      ? '-- Chọn phiên bản model đã phê duyệt shadow --'
      : '-- Chưa có model nào được phê duyệt shadow --');
    defaultModelOpt.value = '';
    modelSel.replaceChildren(defaultModelOpt, ...approvedModels.map(m => {
      const label = `${m.model_run_id} · cipher=${(m.model_cipher_sha256 || '').slice(0, 12)}… · hợp đồng ${m.feature_contract?.version || '—'} · duyệt bởi ${m.approved_by || '—'}`;
      const o = node('option', label);
      o.value = m.model_run_id;
      return o;
    }));
    // Never auto-select the latest model unless explicitly chosen or restored from an explicit selection.
    if (prevModel && approvedModels.some(m => m.model_run_id === prevModel)) {
      modelSel.value = prevModel;
    } else {
      modelSel.value = '';
    }

    const defaultSnapOpt = node('option', snapshots.length
      ? '-- Chọn snapshot của doanh nghiệp --'
      : '-- Doanh nghiệp chưa có snapshot --');
    defaultSnapOpt.value = '';
    const selModel = selectedApprovedModelObj();
    snapSel.replaceChildren(defaultSnapOpt, ...snapshots.map(s => {
      const tag = selModel && selModel.training_snapshot_id === s.snapshot_id ? ' [Snapshot lúc train]' : '';
      const o = node('option', `${s.snapshot_id}${tag} (${s.transaction_count} giao dịch · ${s.contract_version} · as_of ${s.source_as_of || s.created_at})`);
      o.value = s.snapshot_id;
      return o;
    }));
    if (prevSnap && snapshots.some(s => s.snapshot_id === prevSnap)) {
      snapSel.value = prevSnap;
    } else if (snapshots.length) {
      snapSel.value = snapshots[0].snapshot_id;
    } else {
      snapSel.value = '';
    }

    const curSnap = selectedShadowSnapshotObj();
    if (prevAsOf) {
      $('bt-shadow-as-of').value = prevAsOf;
    } else if (curSnap) {
      $('bt-shadow-as-of').value = curSnap.source_as_of || curSnap.created_at || '';
    } else {
      $('bt-shadow-as-of').value = '';
    }

    $('bt-shadow-sort').value = prevSort === 'row_asc' ? 'row_asc' : 'score_desc';

    const defaultHistOpt = node('option', shadowRuns.length
      ? `-- Chọn lần chạy đã lưu để xem lại (${shadowRuns.length} lần chạy) --`
      : '-- Chưa có lần chạy shadow nào được lưu --');
    defaultHistOpt.value = '';
    histSel.replaceChildren(defaultHistOpt, ...shadowRuns.map(r => {
      const o = node('option',
        `${r.shadow_run_id} · Snapshot ${r.snapshot?.snapshot_id} · as_of ${r.snapshot?.as_of} · Model ${r.model?.model_run_id} (${r.summary?.scored_rows ?? 0}/${r.summary?.total_rows ?? 0} đã chấm)`
      );
      o.value = r.shadow_run_id;
      return o;
    }));
    if (prevHist && shadowRuns.some(r => r.shadow_run_id === prevHist)) {
      histSel.value = prevHist;
      const matched = shadowRuns.find(r => r.shadow_run_id === prevHist);
      if (matched) {
        currentShadowView = matched;
        currentShadowMode = 'saved';
        if (matched.model?.model_run_id && approvedModels.some(m => m.model_run_id === matched.model.model_run_id)) {
          modelSel.value = matched.model.model_run_id;
        }
        if (matched.snapshot?.snapshot_id && snapshots.some(s => s.snapshot_id === matched.snapshot.snapshot_id)) {
          snapSel.value = matched.snapshot.snapshot_id;
        }
        if (matched.snapshot?.as_of) {
          $('bt-shadow-as-of').value = matched.snapshot.as_of;
        }
      }
    } else {
      histSel.value = '';
    }
  }

  function renderShadowRunSection() {
    const runBanner = $('bt-shadow-run-banner');
    const compatBanner = $('bt-shadow-compat-banner');
    const sumCards = $('bt-shadow-summary-cards');
    const tblWrap = $('bt-shadow-run-table');
    if (!runBanner || !compatBanner || !sumCards || !tblWrap) return;

    runBanner.replaceChildren();
    compatBanner.replaceChildren();
    sumCards.replaceChildren();
    tblWrap.replaceChildren();

    const selModel = selectedApprovedModelObj();
    if (!currentShadowView) {
      if (!approvedModels.length) {
        runBanner.append(node('p', 'Doanh nghiệp chưa có model nào được phê duyệt dùng đối chiếu shadow. Hãy hoàn tất Bước 7 trước.', 'hint'));
      } else if (!selModel) {
        runBanner.append(node('p', 'Hãy chọn rõ một phiên bản model đã phê duyệt shadow và snapshot mục tiêu, sau đó bấm "Kiểm tra tương thích" hoặc "Chạy chấm shadow và lưu kết quả".', 'hint'));
      } else {
        runBanner.append(node('p',
          `Đang chọn Model ${selModel.model_run_id} (cipher=${(selModel.model_cipher_sha256 || '').slice(0, 16)}…, approval=${(selModel.approval_sha256 || '').slice(0, 16)}…, hợp đồng=${selModel.feature_contract?.version || '—'}). `
          + `Bấm "Kiểm tra tương thích" hoặc "Chạy chấm shadow và lưu kết quả".`,
          'hint'
        ));
      }
      $('bt-step8-tech').textContent = selModel ? JSON.stringify({ selected_model: selModel }, null, 2) : '';
      return;
    }

    const v = currentShadowView;
    const snap = v.snapshot || {};
    const mod = v.model || {};
    const compat = v.compatibility || {};
    const sum = v.summary || {};
    const bex = v.batch_execution || {};
    const disc = v.disclosures || {};

    const modeTitle = currentShadowMode === 'saved'
      ? `Đang xem lần chạy đã lưu: ${v.shadow_run_id} (tạo lúc ${v.created_at ? new Date(v.created_at).toLocaleString('vi-VN') : '—'} bởi ${v.actor_id || '—'})`
      : `Đang xem kết quả kiểm tra tương thích trước khi chạy (kiểm tra lúc ${v.checked_at ? new Date(v.checked_at).toLocaleString('vi-VN') : '—'})`;

    const bannerBox = node('div', '', 'callout');
    bannerBox.append(
      node('p', `${modeTitle} · Trạng thái: ${v.status_label || v.status}`),
      node('p',
        `Snapshot mục tiêu: ${snap.snapshot_id} (${snap.contract_version}) · data_checksum=${(snap.data_checksum || '').slice(0, 16)}… · `
        + `Thời điểm chốt as_of=${snap.as_of} · ${snap.same_as_training_snapshot ? 'Cùng snapshot lúc train (đã gắn nhãn phân biệt giao dịch train/holdout)' : 'Snapshot khác với snapshot lúc train'}`
      ),
      node('p',
        `Model đã ghim: ${mod.model_run_id} · model_cipher_sha256=${(mod.model_cipher_sha256 || '').slice(0, 16)}… · `
        + `approval_sha256=${(mod.approval_sha256 || '').slice(0, 16)}… · Snapshot lúc train: ${mod.training_snapshot_id || '—'} · `
        + `plan_sha256=${(mod.training_plan_sha256 || '').slice(0, 16)}…`
      ),
      node('p',
        `Thực thi: ${disc.execution_location || 'enterprise_node_decrypted_candidate'} · Nguồn tạo feature: ${bex.input_mode || 'backend_snapshot_feature_builder'} `
        + `(manual_features_accepted=${String(!!bex.manual_features_accepted)}) · Giới hạn mỗi lần gọi predict_batch_shadow: tối đa ${bex.max_rows_per_call || 64} dòng/lần `
        + `(số lần gọi=${bex.call_count ?? 0}, giới hạn 4 dòng của train áp dụng=${String(!!bex.training_four_row_limit_applied)}, cắt ngầm 64 dòng=${String(!!bex.truncated_to_64)}).`
      )
    );
    runBanner.append(bannerBox);

    const compatBox = node('div', '', 'callout');
    compatBox.append(
      node('p', `Kiểm tra hợp đồng feature & mapping (${compat.code || ''}): ${compat.message || ''}`),
      node('p',
        `Hợp đồng model: ${compat.expected_mapping?.source_contract_version || '—'} (fp=${(compat.expected_mapping?.source_contract_fingerprint || '').slice(0, 12)}…) · `
        + `Hợp đồng snapshot: ${compat.actual_mapping?.source_contract_version || '—'} (fp=${(compat.actual_mapping?.source_contract_fingerprint || '').slice(0, 12)}…) · `
        + `Mapping: ${(compat.actual_mapping?.columns || []).join(', ')} (fp=${(v.mapping_fingerprint || '').slice(0, 12)}…)`
      )
    );
    if (!compat.compatible && Array.isArray(compat.mismatches) && compat.mismatches.length) {
      const ul = document.createElement('ul');
      compat.mismatches.forEach(m => {
        ul.append(node('li', `[${m.field}] Mong đợi: ${JSON.stringify(m.expected)} vs Thực tế: ${JSON.stringify(m.actual)} — ${m.message}`));
      });
      compatBox.append(ul);
      if (compat.remediation) {
        compatBox.append(node('p', `Hướng xử lý: ${compat.remediation}`));
      }
    }
    compatBanner.append(compatBox);

    sumCards.append(node('p',
      `Tổng số giao dịch trong snapshot: ${sum.total_rows ?? 0} · `
      + `Đủ điều kiện: ${sum.eligible_rows ?? 0} · Đã chấm điểm: ${sum.scored_rows ?? 0} · `
      + `Unavailable: ${sum.unavailable_rows ?? 0} (sau mốc as_of: ${sum.post_cutoff_rows ?? 0}, thiếu nguồn feature: ${sum.missing_feature_rows ?? 0}) · `
      + `Không tương thích: ${sum.incompatible_rows ?? 0} · `
      + `Giao dịch mới: ${sum.new_transaction_rows ?? 0} · Đã xuất hiện trong tập train: ${sum.seen_in_training_rows ?? 0} · Đã xuất hiện trong tập holdout: ${sum.seen_in_evaluation_rows ?? 0}`
    ));

    const sortMode = $('bt-shadow-sort')?.value || 'score_desc';
    const rows = [...(v.rows || [])];
    if (sortMode === 'score_desc') {
      rows.sort((a, b) => {
        const aScored = a.score !== null && a.score !== undefined;
        const bScored = b.score !== null && b.score !== undefined;
        if (aScored && bScored) {
          if (b.score !== a.score) return b.score - a.score;
          return (a.snapshot_order || 0) - (b.snapshot_order || 0);
        }
        if (aScored !== bScored) return aScored ? -1 : 1;
        return (a.snapshot_order || 0) - (b.snapshot_order || 0);
      });
    } else {
      rows.sort((a, b) => (a.snapshot_order || 0) - (b.snapshot_order || 0));
    }

    const tbl = document.createElement('table');
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    [
      'Hạng / Thứ tự gốc',
      'Mã giao dịch',
      'Thời điểm giao dịch / Ghi nhận',
      'Số tiền (VND)',
      'Phân loại nguồn (Mới / Train / Holdout)',
      'Feature từ backend (round_million, creator_equals_approver)',
      'Trạng thái',
      'Điểm shadow (uncalibrated)',
      'Lý do thiếu nguồn / Hướng xử lý',
    ].forEach(h => hr.append(node('th', h)));
    thead.append(hr);

    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.dataset.recordId = r.record_id;
      tr.dataset.rowStatus = r.status;
      tr.dataset.historyStatus = r.history_status;
      const rankTxt = r.score_rank ? `#${r.score_rank} (gốc #${r.snapshot_order})` : `— (gốc #${r.snapshot_order})`;
      const amtTxt = (r.amount_vnd !== null && r.amount_vnd !== undefined ? Number(r.amount_vnd).toLocaleString('vi-VN') + ' ' + (r.currency || 'VND') : '—')
        + (r.transaction_type ? ` (${r.transaction_type})` : '');
      const featTxt = `round_million=${r.features?.round_million ?? 'null'}, creator_equals_approver=${r.features?.creator_equals_approver ?? 'null'}`;
      const scoreTxt = r.score !== null && r.score !== undefined ? Number(r.score).toFixed(6) : '—';
      const issueTxt = (r.issues && r.issues.length)
        ? r.issues.map(i => `[${i.code}] ${i.message}${i.remediation ? ' → ' + i.remediation : ''}`).join(' | ')
        : 'Đủ nguồn hợp lệ tại thời điểm chốt as_of.';
      tr.append(
        node('td', rankTxt),
        node('td', `${r.record_id} (rev ${r.revision})`),
        node('td', `${r.occurred_at || '—'} / obs: ${r.available_at || '—'}`),
        node('td', amtTxt),
        node('td', `${r.history_label} [${r.history_status}]`),
        node('td', featTxt),
        node('td', `${r.status_label} [${r.status}]`),
        node('td', scoreTxt),
        node('td', issueTxt)
      );
      tbody.append(tr);
    });
    tbl.append(thead, tbody);
    tblWrap.append(tbl);

    $('bt-step8-tech').textContent = JSON.stringify(v, null, 2);
  }

  function updateControls() {
    const perms = state?.permissions || {};
    const sess = state?.session;
    const ps = sess?.plan_summary;
    const ls = sess?.label_status;
    const wj = sess?.worker_job;
    const jobCompleted = wj && wj.status === 'completed' && wj.completed_updates === wj.total_updates;

    $('bt-company').disabled = busy || !$('bt-company').options.length;
    $('bt-step1-btn').disabled = busy || !perms.can_import || !$('bt-snapshot').value;
    $('bt-step2-btn').disabled = busy || !perms.can_verify || !ps || ps.status !== 'ready' || !!sess?.plan_stale;
    $('bt-step3-btn').disabled = busy || !perms.can_fit || !ps || ps.status !== 'ready' || !!sess?.plan_stale || !ls?.ready_to_confirm;
    $('bt-step4-btn').disabled = busy || !sess?.job_id;
    $('bt-step5-btn').disabled = busy || !sess?.job_id || !jobCompleted;
    $('bt-step6-btn').disabled = busy || !sess?.candidate;
    if (!sess?.approval) {
      $('bt-step7-btn').disabled = busy || !perms.can_fit || !sess?.candidate || !sess?.evaluation;
    } else {
      $('bt-step7-btn').disabled = busy || !perms.can_import;
    }

    const canShadowSnap = !busy && !!perms.can_import && !!$('bt-shadow-model')?.value && !!$('bt-shadow-snapshot')?.value && !!$('bt-shadow-as-of')?.value.trim();
    if ($('bt-shadow-check-btn')) $('bt-shadow-check-btn').disabled = !canShadowSnap;
    if ($('bt-shadow-run-btn')) $('bt-shadow-run-btn').disabled = !canShadowSnap;
  }

  function renderAll(val, rebuildForm = false) {
    state = val;
    if (val.snapshots) snapshots = val.snapshots;
    if (val.approved_models) approvedModels = val.approved_models;
    if (val.shadow_runs) shadowRuns = val.shadow_runs;
    const perms = val.permissions || {};
    $('bt-permission').textContent = `Tài khoản: ${val.actor_id} · Quyền: `
      + [
        perms.can_import ? 'nhập/xem (data.import)' : null,
        perms.can_verify ? 'xác minh nhãn (evidence.verify)' : null,
        perms.can_fit ? 'huấn luyện & phê duyệt shadow (model.fit)' : null,
      ].filter(Boolean).join(', ');
    const sess = val.session;
    $('bt-overall-status').textContent = sess
      ? `Phiên hiện tại: v${sess.revision} · ${sess.status_label}`
      : 'Chưa có phiên huấn luyện batch nào cho doanh nghiệp này.';

    if (rebuildForm) {
      $('bt-snapshot').replaceChildren(...snapshots.map(s => {
        const o = node('option', `${s.snapshot_id} (${s.transaction_count} giao dịch · ${new Date(s.created_at).toLocaleString('vi-VN')})`);
        o.value = s.snapshot_id;
        return o;
      }));
      if (sess?.request) {
        const req = sess.request;
        if ([...$('bt-snapshot').options].some(o => o.value === req.snapshot_id)) {
          $('bt-snapshot').value = req.snapshot_id;
        }
        $('bt-train-start').value = req.training_start || '';
        $('bt-train-end').value = req.training_end || '';
        $('bt-eval-start').value = req.evaluation_start || '';
        $('bt-eval-end').value = req.evaluation_end || '';
        $('bt-as-of').value = req.as_of || '';
        renderBatchSelectors(currentSnapshotObj(), req);
      } else if (snapshots.length) {
        $('bt-snapshot').value = snapshots[0].snapshot_id;
        populateDefaultBatchesFromSnapshot(snapshots[0]);
      } else {
        $('bt-batch-selectors').replaceChildren(node('p', 'Doanh nghiệp chưa có snapshot đã chốt. Hãy nhập và chốt snapshot trước.', 'hint'));
      }
      populateShadowSelectors(false);
    } else {
      populateShadowSelectors(true);
    }

    renderPlanSection(sess);
    renderLabelSection(sess);
    renderConfirmSection(sess);
    renderProgressSection(sess);
    renderReceiveSection(sess);
    renderEvalSection(sess);
    renderApprovalSection(sess);
    renderShadowRunSection();
    updateControls();
    schedulePoll();
  }

  function clearPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function schedulePoll() {
    clearPoll();
    if (!company || state?.session?.phase !== 'training') return;
    const pollEpoch = epoch;
    pollTimer = setTimeout(async () => {
      pollTimer = null;
      if (pollEpoch !== epoch || !company || state?.session?.phase !== 'training') return;
      if (busy) {
        schedulePoll();
        return;
      }
      try {
        const val = await api(base());
        if (pollEpoch === epoch) renderAll(val, false);
      } catch {
        if (pollEpoch === epoch) schedulePoll();
      }
    }, 1200);
  }

  function updateNavLinks() {
    const q = company ? '#company=' + encodeURIComponent(company) : '';
    if ($('bt-nav-workspace')) $('bt-nav-workspace').href = 'workspace' + q;
    if ($('bt-nav-bundle')) $('bt-nav-bundle').href = 'pipeline-workspace' + q;
    if ($('bt-nav-settings')) $('bt-nav-settings').href = 'analysis-settings' + q;
    if ($('bt-nav-labels')) $('bt-nav-labels').href = 'label-verification' + q;
    history.replaceState(null, '', location.pathname + q);
    try {
      if (company && actorID) {
        sessionStorage.setItem('agent2.company.selection', JSON.stringify({ version: 1, actor: actorID, context: contextID, company, page: 'batch-training' }));
      }
    } catch {
      /* optional */
    }
  }

  async function switchCompany() {
    epoch++;
    clearPoll();
    controller?.abort();
    controller = new AbortController();
    busy = false;
    idemKeys.clear();
    state = null;
    snapshots = [];
    approvedModels = [];
    shadowRuns = [];
    currentShadowView = null;
    currentShadowMode = '';
    customJsonEdited = false;
    $('bt-approve-reason').value = '';
    company = $('bt-company').value;
    updateNavLinks();
    if (!company) return;
    await runTask(async e => {
      const val = await api(base());
      if (e === epoch) {
        $('bt-workflow').hidden = false;
        renderAll(val, true);
      }
    });
  }

  $('bt-company').addEventListener('change', switchCompany);
  $('bt-snapshot').addEventListener('change', () => {
    $('bt-train-start').value = '';
    populateDefaultBatchesFromSnapshot(currentSnapshotObj());
  });
  $('bt-train-batch-count').addEventListener('change', () => renderBatchSelectors(currentSnapshotObj(), null));
  $('bt-eval-batch-count').addEventListener('change', () => renderBatchSelectors(currentSnapshotObj(), null));
  ['bt-train-start', 'bt-train-end', 'bt-eval-start', 'bt-eval-end', 'bt-as-of'].forEach(id => {
    $(id).addEventListener('input', () => {
      customJsonEdited = false;
      syncRequestJsonFromForm();
    });
  });
  $('bt-plan-request-json').addEventListener('input', () => {
    customJsonEdited = true;
  });
  $('bt-epochs').addEventListener('change', () => {
    if (state?.session) renderConfirmSection(state.session);
  });

  // Bước 1: Kiểm tra và ghim kế hoạch
  $('bt-step1-btn').addEventListener('click', () => runTask(async e => {
    let request;
    try {
      request = buildRequestFromForm();
    } catch {
      throw new Error('JSON request kế hoạch không hợp lệ.');
    }
    const val = await api(base() + '/preview', {
      expected_revision: state?.revision || 0,
      request,
    });
    if (e === epoch) {
      renderAll(val, false);
      notice(val.session?.plan_summary?.status === 'ready'
        ? 'Đã kiểm tra và ghim kế hoạch dữ liệu. Tiếp tục Bước 2 để tạo danh sách xác minh nhãn.'
        : 'Kế hoạch có lỗi nguồn/feature. Vui lòng xem chi tiết lỗi và điều chỉnh trước khi tiếp tục.');
    }
  }));

  // Bước 2: Tạo danh sách xác minh nhãn
  $('bt-step2-btn').addEventListener('click', () => runTask(async e => {
    const val = await api(base() + '/create-labels', {
      expected_revision: state.revision,
      expected_plan_sha256: state.session.plan_sha256,
      include_evaluation: true,
    });
    if (e === epoch) {
      renderAll(val, false);
      notice('Đã tạo/đồng bộ gói xác minh nhãn cho các batch trong kế hoạch. Mở liên kết từng batch để xác minh và khóa nhãn.');
    }
  }));

  // Bước 3: Xác nhận và bắt đầu train mã hóa
  $('bt-step3-btn').addEventListener('click', () => runTask(async e => {
    const epochs = Number($('bt-epochs').value) || 1;
    const locks = state.session.label_status?.recommended_locks || [];
    const val = await api(base() + '/confirm', {
      expected_revision: state.revision,
      expected_plan_sha256: state.session.plan_sha256,
      epochs,
      locks,
      run_mode: 'async',
    });
    if (e === epoch) {
      renderAll(val, false);
      notice(val.session?.phase === 'completed_waiting_receive'
        ? 'Đã hoàn tất huấn luyện trên bản mã. Chuyển sang Bước 5 để nhận và kiểm tra kỹ thuật model.'
        : 'Đã ghi nhận yêu cầu train. Xem tiến độ ở Bước 4.');
    }
  }));

  // Bước 4: Cập nhật / Tiếp tục yêu cầu đã lưu
  $('bt-step4-btn').addEventListener('click', () => runTask(async e => {
    const wj = state.session?.worker_job;
    const done = wj && wj.status === 'completed' && wj.completed_updates === wj.total_updates;
    const running = state.session?.phase === 'training';
    const val = (done || running)
      ? await api(base())
      : await api(base() + '/resume', { expected_revision: state.revision, run_mode: 'async' });
    if (e === epoch) {
      renderAll(val, false);
      notice('Đã cập nhật/tiếp tục đúng yêu cầu huấn luyện đã lưu.');
    }
  }));

  // Bước 5: Nhận và kiểm tra kỹ thuật model
  $('bt-step5-btn').addEventListener('click', () => runTask(async e => {
    const val = await api(base() + '/receive', {
      expected_revision: state.revision,
    });
    if (e === epoch) {
      renderAll(val, false);
      notice('Model ứng viên đã nhận và kiểm tra kỹ thuật tại doanh nghiệp.');
    }
  }));

  // Bước 6: Đánh giá trên tập giữ riêng
  $('bt-step6-btn').addEventListener('click', () => runTask(async e => {
    const val = await api(base() + '/evaluate', {
      expected_revision: state.revision,
      use_locked_evaluation_labels: true,
    });
    if (e === epoch) {
      renderAll(val, false);
      notice('Đã hoàn tất đánh giá model ứng viên trên tập giữ riêng.');
    }
  }));

  // Bước 7: Phê duyệt dùng đối chiếu shadow / Chạy đối chiếu shadow
  $('bt-step7-btn').addEventListener('click', () => runTask(async e => {
    if (!state.session?.approval) {
      const reason = $('bt-approve-reason').value.trim();
      const val = await api(base() + '/approve', {
        expected_revision: state.revision,
        reason,
        expected_model_cipher_sha256: state.session.candidate?.model_cipher_sha256,
        expected_plan_sha256: state.session.plan_sha256,
        expected_evaluation_sha256: state.session.evaluation_sha256,
      });
      if (e === epoch) {
        renderAll(val, false);
        notice('Đã phê duyệt model ứng viên cho chế độ đối chiếu shadow.');
      }
    } else {
      const val = await api(base() + '/shadow', {
        expected_revision: state.revision,
      });
      if (e === epoch) {
        renderAll(val, false);
        notice('Đã chạy đối chiếu shadow trên tập giữ riêng. Model đang chạy và hàng đợi nghiệp vụ không thay đổi.');
      }
    }
  }));

  // Bước 8: Chấm đối chiếu shadow trên snapshot giao dịch mới và lịch sử lần chạy
  $('bt-shadow-model')?.addEventListener('change', () => {
    $('bt-shadow-history').value = '';
    currentShadowView = null;
    currentShadowMode = '';
    populateShadowSelectors(true);
    saveShadowSelectionState();
    renderShadowRunSection();
    updateControls();
  });

  $('bt-shadow-snapshot')?.addEventListener('change', () => {
    $('bt-shadow-history').value = '';
    currentShadowView = null;
    currentShadowMode = '';
    const snap = selectedShadowSnapshotObj();
    if (snap) {
      $('bt-shadow-as-of').value = snap.source_as_of || snap.created_at || '';
    }
    saveShadowSelectionState();
    renderShadowRunSection();
    updateControls();
  });

  $('bt-shadow-as-of')?.addEventListener('input', () => {
    $('bt-shadow-history').value = '';
    currentShadowView = null;
    currentShadowMode = '';
    saveShadowSelectionState();
    renderShadowRunSection();
    updateControls();
  });

  $('bt-shadow-sort')?.addEventListener('change', () => {
    saveShadowSelectionState();
    renderShadowRunSection();
  });

  $('bt-shadow-history')?.addEventListener('change', () => {
    const rid = $('bt-shadow-history').value;
    if (!rid) {
      currentShadowView = null;
      currentShadowMode = '';
      saveShadowSelectionState();
      renderShadowRunSection();
      updateControls();
      return;
    }
    const found = shadowRuns.find(r => r.shadow_run_id === rid);
    if (found) {
      currentShadowView = found;
      currentShadowMode = 'saved';
      if (found.model?.model_run_id && approvedModels.some(m => m.model_run_id === found.model.model_run_id)) {
        $('bt-shadow-model').value = found.model.model_run_id;
      }
      if (found.snapshot?.snapshot_id && snapshots.some(s => s.snapshot_id === found.snapshot.snapshot_id)) {
        $('bt-shadow-snapshot').value = found.snapshot.snapshot_id;
      }
      if (found.snapshot?.as_of) {
        $('bt-shadow-as-of').value = found.snapshot.as_of;
      }
      saveShadowSelectionState();
      renderShadowRunSection();
      updateControls();
    }
  });

  $('bt-shadow-check-btn')?.addEventListener('click', () => runTask(async e => {
    const mod = selectedApprovedModelObj();
    const snapId = $('bt-shadow-snapshot').value;
    const asOf = $('bt-shadow-as-of').value.trim();
    const res = await api(base() + '/shadow-runs/check', {
      model_run_id: mod ? mod.model_run_id : $('bt-shadow-model').value,
      expected_model_cipher_sha256: mod?.model_cipher_sha256,
      expected_approval_sha256: mod?.approval_sha256,
      snapshot_id: snapId,
      as_of: asOf,
    });
    if (e === epoch) {
      $('bt-shadow-history').value = '';
      currentShadowView = res.check;
      currentShadowMode = 'check';
      saveShadowSelectionState();
      renderShadowRunSection();
      const c = res.check?.compatibility;
      const s = res.check?.summary || {};
      notice(c?.compatible
        ? `Kiểm tra tương thích đạt: ${s.eligible_rows}/${s.total_rows} giao dịch đủ điều kiện chấm shadow (${s.unavailable_rows} dòng unavailable).`
        : `Model không tương thích hợp đồng feature/mapping với snapshot đã chọn (${(c?.mismatches || []).map(m => m.field).join(', ')}).`);
    }
  }));

  $('bt-shadow-run-btn')?.addEventListener('click', () => runTask(async e => {
    const mod = selectedApprovedModelObj();
    const snapId = $('bt-shadow-snapshot').value;
    const asOf = $('bt-shadow-as-of').value.trim();
    const res = await api(base() + '/shadow-runs', {
      model_run_id: mod ? mod.model_run_id : $('bt-shadow-model').value,
      expected_model_cipher_sha256: mod?.model_cipher_sha256,
      expected_approval_sha256: mod?.approval_sha256,
      snapshot_id: snapId,
      as_of: asOf,
    });
    if (e === epoch) {
      if (res.shadow_runs) shadowRuns = res.shadow_runs;
      currentShadowView = res.shadow_run;
      currentShadowMode = 'saved';
      if ($('bt-shadow-history') && res.shadow_run?.shadow_run_id) {
        populateShadowSelectors(true);
        $('bt-shadow-history').value = res.shadow_run.shadow_run_id;
      }
      saveShadowSelectionState();
      renderShadowRunSection();
      const s = res.shadow_run?.summary || {};
      notice(res.reused_existing
        ? `Đã tải lại đúng lần chạy shadow đã lưu ${res.shadow_run.shadow_run_id} (không tạo bản ghi trùng).`
        : `Đã lưu lần chạy shadow ${res.shadow_run.shadow_run_id}: ${s.scored_rows}/${s.total_rows} giao dịch đã chấm (${s.unavailable_rows} unavailable).`);
    }
  }));

  async function init() {
    epoch++;
    controller?.abort();
    controller = new AbortController();
    busy = false;
    notice('');
    try {
      token = sessionStorage.getItem('kt-session') || '';
      if (!token) {
        $('bt-login').hidden = false;
        return;
      }
      const context = await api('/api/v1/ui/context');
      actorID = context.actor_id || '';
      contextID = context.context_id || '';
      $('bt-login').hidden = true;
      $('bt-company').replaceChildren(...(context.companies || []).map(c => {
        const o = node('option', c);
        o.value = c;
        return o;
      }));
      $('bt-company').disabled = !(context.companies || []).length;
      let shared;
      try { shared = JSON.parse(sessionStorage.getItem('agent2.company.selection')); } catch {}
      const remembered = shared?.version === 1 && shared.actor === actorID && shared.context === contextID && context.companies?.includes(shared.company) ? shared.company : '';
      const desired = new URLSearchParams(location.hash.slice(1)).get('company');
      if (context.companies?.includes(desired)) {
        $('bt-company').value = desired;
      } else if (remembered) {
        $('bt-company').value = remembered;
      }
      await switchCompany();
    } catch (err) {
      notice(err.message);
    }
  }

  window.addEventListener('storage', e => {
    if (e.key === 'kt-session') init();
  });
  window.addEventListener('focus', () => {
    const cur = sessionStorage.getItem('kt-session') || '';
    if (cur !== token) init();
    else if (company && !busy) {
      runTask(async e => {
        const val = await api(base());
        if (e === epoch) renderAll(val, false);
      });
    }
  });
  init();
})();

