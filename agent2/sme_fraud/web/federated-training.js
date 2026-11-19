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
  let token = '', company = '', status = null, pollTimer = null, activeRun = null, busy = false;

  const pct = v => v == null ? '—' : (Number(v) * 100).toFixed(1).replace('.', ',') + '%';
  const num = v => v == null ? '—' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 3 });
  const notice = msg => { $('notice').textContent = msg || ''; $('notice').hidden = !msg; };
  const success = msg => { $('success-banner').textContent = msg || ''; $('success-banner').hidden = !msg; };
  const base = () => '/api/v1/companies/' + encodeURIComponent(company) + '/model-lifecycle/federated';

  async function api(path, body) {
    const headers = { 'X-Platform': '1', 'X-Session': token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetch(mount + path, { method: body === undefined ? 'GET' : 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.errors?.map(e => [e.message, e.action].filter(Boolean).join(' ')).join('\n') || data.error || 'Chưa thực hiện được thao tác.');
    }
    return data;
  }

  function parseCsv(text) {
    const lines = text.replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) throw new Error('Tệp CSV trống.');
    const head = lines[0].split(',').map(s => s.trim().toLowerCase());
    const col = name => head.indexOf(name);
    const iId = col('record_id'), i1 = col('round_million'), i2 = col('creator_equals_approver');
    let iY = col('label'); if (iY < 0) iY = col('y');
    if ([iId, i1, i2, iY].some(i => i < 0)) throw new Error('Thiếu cột. Cần record_id, round_million, creator_equals_approver, label.');
    return lines.slice(1).map((line, n) => {
      const c = line.split(',').map(s => s.trim());
      const v = i => /^[01]$/.test(c[i] ?? '') ? Number(c[i]) : NaN;
      const row = { record_id: c[iId], x: [v(i1), v(i2)], y: v(iY) };
      if (!row.record_id || row.x.some(Number.isNaN) || Number.isNaN(row.y)) throw new Error('Dòng ' + (n + 2) + ' có giá trị không phải 0/1 hoặc thiếu mã.');
      return row;
    });
  }

  function sampleCsv() {
    const rows = ['record_id,round_million,creator_equals_approver,label'];
    for (let i = 0; i < 24; i++) { const risk = i % 4 === 0 ? 1 : 0; rows.push(`DN-${String(i).padStart(3, '0')},${risk ? (i % 8 ? 1 : 0) : (i % 7 ? 0 : 1)},${risk ? 1 : (i % 9 ? 0 : 1)},${risk}`); }
    return rows.join('\n');
  }

  async function contribute(cid, payload) {
    const prev = company; company = cid;
    try { await api(base() + '/contribute', payload); } finally { company = prev; }
  }

  function renderCompanies() {
    const body = $('fed-companies');
    body.replaceChildren(...status.companies.map(c => {
      const tr = el('tr');
      tr.append(el('td', c.company_id, 'fed-strong'));
      tr.append(el('td', c.enrolled ? '✓ Đã sinh khóa riêng' : '✗ Chưa đăng ký', c.enrolled ? 'fed-ok' : 'fed-bad'));
      tr.append(el('td', c.rows || 'Chưa nạp'));
      tr.append(el('td', c.rows ? `${c.label_1} / ${c.label_0}` : '—'));
      tr.append(el('td', c.rows ? `${c.train_rows} / ${c.holdout_rows}` : '—'));
      tr.append(el('td', c.source === 'simulated' ? 'Mô phỏng' : c.source ? 'Tệp CSV' : '—'));
      const act = el('td', null, 'fed-row-actions');
      const sim = el('button', 'Dùng mô phỏng', 'btn-outline btn-sm');
      sim.type = 'button';
      sim.onclick = () => guarded(async () => { await contribute(c.company_id, { simulate: true, count: 48 }); await load(); success(`Đã tạo dữ liệu mô phỏng cho ${c.company_id}.`); });
      const file = el('input'); file.type = 'file'; file.accept = '.csv,text/csv'; file.hidden = true;
      file.onchange = () => file.files[0] && guarded(async () => {
        const rows = parseCsv(await file.files[0].text());
        await contribute(c.company_id, { rows, source: 'upload' });
        await load(); success(`Đã nạp ${rows.length} dòng cho ${c.company_id}.`);
      });
      const up = el('button', 'Nạp CSV', 'btn-outline btn-sm'); up.type = 'button'; up.onclick = () => file.click();
      act.append(sim, up, file);
      tr.append(act);
      return tr;
    }));
    const sims = status.companies.some(c => c.source === 'simulated');
    $('sim-badge').hidden = !sims;
  }

  function renderFeatures() {
    $('fed-feature-list').replaceChildren(...status.features.map((f, i) => {
      const card = el('div', null, 'fed-feature');
      card.append(el('b', `X${i + 1} · ${f.name}`), el('span', f.label_vi), el('em', 'Nhị phân 0/1 · khóa theo mạch'));
      return card;
    }));
    $('fed-feature-note').textContent = `Mạch mã hóa hiện biên dịch cố định ${status.limits.circuit_features} đặc trưng nhị phân, ${status.limits.batch_size} dòng mỗi bước, tối đa ${status.limits.circuit_updates_per_round} bước mỗi vòng. ` +
      'Bộ 33 đặc trưng đầy đủ dùng cho Isolation Forest và Autoencoder ở tab "Huấn luyện & mô hình". Muốn thêm đặc trưng cho LR mã hóa cần biên dịch lại mạch (đổi số cột).';
  }

  function renderWorker() {
    const w = status.worker || {};
    const ok = w.status === 'ok' || w.ok === true || w.reachable === true || w.healthy === true;
    const pill = $('worker-pill');
    pill.className = 'status-pill ' + (ok ? 'status-active' : 'status-review');
    pill.textContent = ok ? 'Máy chủ cloud đang sẵn sàng' : 'Máy chủ cloud chưa chạy (sẽ tự bật khi cần)';
  }

  function renderRun(doc) {
    const stateMap = { running: ['Đang chạy', 'status-pending'], completed: ['Hoàn tất', 'status-active'], failed: ['Lỗi', 'status-review'] };
    const [label, cls] = stateMap[doc.state] || ['Chưa chạy', 'status-idle'];
    $('fed-state').className = 'status-pill ' + cls; $('fed-state').textContent = label;
    const evs = doc.events || [];
    $('fed-events').replaceChildren(...evs.map(e => {
      const li = el('li', null, 'fed-ev fed-ev-' + e.stage);
      li.append(el('time', new Date(e.at).toLocaleTimeString('vi-VN')), el('span', e.message));
      return li;
    }));
    const total = doc.rounds * doc.companies.length;
    const done = evs.filter(e => e.stage === 'fhe').length;
    $('fed-progress-fill').style.width = (doc.state === 'completed' ? 100 : Math.min(96, Math.round(done / Math.max(1, total) * 90))) + '%';
    if (doc.state === 'completed' && doc.result) renderResult(doc);
  }

  function row(scope, name, m) {
    const tr = el('tr');
    tr.append(el('td', scope), el('td', name), el('td', pct(m.recall)), el('td', pct(m.precision)), el('td', pct(m.f1)), el('td', num(m.bce_loss)), el('td', m.sample_count));
    return tr;
  }

  function renderResult(doc) {
    const r = doc.result, s = r.summary;
    $('fed-result').hidden = false; $('fed-approve').hidden = false;
    const kpi = (label, value, sub) => { const b = el('div', null, 'kpi-box'); b.append(el('small', label), el('strong', value), el('span', sub || '')); return b; };
    $('fed-kpis').replaceChildren(
      kpi('Recall sau huấn luyện', pct(s.recall), 'chưa huấn luyện: ' + pct(s.untrained_recall)),
      kpi('Precision', pct(s.precision), 'chưa huấn luyện: ' + pct(s.untrained_precision)),
      kpi('F1', pct(s.f1)),
      kpi('Sai số BCE', num(s.bce), 'chưa huấn luyện: ' + num(s.untrained_bce)),
      kpi('Ngưỡng chọn trên kiểm định', num(s.threshold)),
      kpi('Dữ liệu', `${s.train_rows} train · ${s.holdout_rows} kiểm định`, `${s.seconds} giây`));
    $('fed-target').className = 'fed-target ' + (s.recall_target_met ? 'fed-ok' : 'fed-bad');
    $('fed-target').textContent = `Mục tiêu recall ≥ ${pct(s.target_recall)}: ${s.recall_target_met ? 'đạt' : 'chưa đạt'} (${pct(s.recall)}).` + (doc.simulated ? ' Dữ liệu mô phỏng, chưa chứng minh hiệu quả thực tế.' : '');
    const body = $('fed-compare');
    body.replaceChildren(row('Gộp các doanh nghiệp', 'Chưa huấn luyện', r.untrained), row('Gộp các doanh nghiệp', 'Đã huấn luyện chung', r.trained),
      ...Object.entries(r.per_company).flatMap(([cid, v]) => [row(cid, 'Chưa huấn luyện', v.untrained), row(cid, 'Đã huấn luyện chung', v.trained)]));
    $('fed-weights').textContent = `w = [${r.weights.w.map(num).join(' ; ')}], b = ${num(r.weights.b)}  ·  đặc trưng: ${r.weights.features.join(', ')}  ·  mã nguyên hóa: [${r.weights.codes.join(', ')}]`;
    const p = r.privacy, pr = $('fed-privacy');
    pr.replaceChildren(...[
      `Thực thi: ${p.execution} trên máy chủ cloud (${p.worker_url}).`,
      'Cloud không giữ khóa bí mật nào và không thấy dữ liệu, nhãn hay trọng số dạng rõ.',
      `Bản cập nhật của từng doanh nghiệp được che bằng ${p.secure_aggregation}; cloud không thấy từng bản riêng lẻ.`,
      p.cross_company_decrypt ? `Thử giải mã chéo (${p.cross_company_decrypt.company_reads_other}): ${p.cross_company_decrypt.rejected ? 'bị từ chối, đúng thiết kế' : 'KHÔNG bị từ chối, cần kiểm tra'}.` : null,
    ].filter(Boolean).map(t => el('li', t)));
    const ap = r.approval;
    $('fed-approval-box').replaceChildren(ap ? el('p', `Đã phê duyệt bởi ${ap.by} lúc ${new Date(ap.at).toLocaleString('vi-VN')}: ${ap.reason}`, 'fed-ok') : el('p', 'Chưa phê duyệt.', 'mm-sub'));
    $('fed-approve-btn').disabled = !!ap;
  }

  async function poll() {
    if (!activeRun) return;
    try {
      const doc = await api(base() + '/job', { run_id: activeRun });
      renderRun(doc);
      if (doc.state === 'running') { pollTimer = setTimeout(poll, 2000); return; }
      activeRun = null; busy = false; $('fed-start').disabled = false;
      if (doc.state === 'failed') notice(doc.error || 'Huấn luyện thất bại.');
    } catch (err) { notice(err.message); activeRun = null; busy = false; $('fed-start').disabled = false; }
  }

  async function guarded(fn) {
    if (busy) return;
    notice(''); success('');
    try { await fn(); } catch (err) { notice(err.message); }
  }

  async function load() {
    status = await api(base() + '/status');
    renderWorker(); renderFeatures(); renderCompanies();
    const latest = status.latest;
    if (latest) {
      renderRun(latest);
      if (latest.state === 'running') { activeRun = latest.run_id; busy = true; $('fed-start').disabled = true; clearTimeout(pollTimer); poll(); }
    }
    $('fed-start').disabled = busy || status.companies.some(c => !c.rows || !c.enrolled);
  }

  $('fed-sim-all').onclick = () => guarded(async () => {
    for (const c of status.companies) await contribute(c.company_id, { simulate: true, count: 48 });
    await load(); success('Đã tạo dữ liệu mô phỏng cho các doanh nghiệp đóng góp.');
  });
  $('fed-start').onclick = () => guarded(async () => {
    busy = true; $('fed-start').disabled = true; $('fed-result').hidden = true; $('fed-approve').hidden = true;
    try {
      const doc = await api(base() + '/run', { rounds: Number($('fed-rounds').value) });
      activeRun = doc.run_id; renderRun(doc); poll();
    } catch (err) { busy = false; $('fed-start').disabled = false; throw err; }
  });
  $('fed-approve-btn').onclick = () => guarded(async () => {
    const doc = await api(base() + '/approve', { run_id: status.latest?.run_id || activeRun, reason: $('fed-reason').value });
    renderRun(doc); success('Đã ghi nhận phê duyệt chạy song song.');
  });
  $('refresh').onclick = () => guarded(load);
  $('company').onchange = () => { company = $('company').value; guarded(load); remember(); };
  $('fed-sample').onclick = e => { e.currentTarget.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(sampleCsv()); };

  function remember() {
    history.replaceState(null, '', location.pathname + '#company=' + encodeURIComponent(company));
    for (const id of ['nav-queue', 'nav-models', 'nav-fed']) {
      const a = $(id); a.href = mount + '/' + a.getAttribute('href').replace(/#.*/, '') + '#company=' + encodeURIComponent(company);
    }
  }

  async function init() {
    token = sessionStorage.getItem('kt-session') || '';
    if (!mount || !token) { notice('Mở Agent2 từ Portal và đăng nhập bằng tài khoản quản lý để dùng Huấn luyện chung.'); return; }
    try {
      const ctx = await api('/api/v1/ui/context');
      const hash = new URLSearchParams(location.hash.slice(1));
      company = ctx.companies.includes(hash.get('company')) ? hash.get('company') : (ctx.companies[0] || '');
      $('company').replaceChildren(...ctx.companies.map(id => { const o = el('option', id); o.value = id; return o; }));
      $('company').value = company; $('company').disabled = !company;
      if (!company) { notice('Chưa được cấp quyền doanh nghiệp.'); return; }
      remember();
      await load();
    } catch (err) { notice(err.message); }
  }
  init();
})();
