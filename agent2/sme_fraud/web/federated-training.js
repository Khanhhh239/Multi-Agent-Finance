'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); if (cls) n.className = cls; return n; };
  const pct = v => v == null ? '—' : (Number(v) * 100).toFixed(1).replace('.', ',') + '%';
  const when = s => s ? new Date(s).toLocaleString('vi-VN') : '';
  let token = '', company = '';
  const notice = m => { $('notice').textContent = m || ''; $('notice').hidden = !m; };
  const success = m => { $('success-banner').textContent = m || ''; $('success-banner').hidden = !m; };
  const base = () => '/api/v1/companies/' + encodeURIComponent(company) + '/model-lifecycle/federated';

  async function api(path, body) {
    const headers = { 'X-Platform': '1', 'X-Session': token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const r = await fetch(mount + path, { method: body === undefined ? 'GET' : 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.errors?.map(e => [e.message, e.action].filter(Boolean).join(' ')).join('\n') || d.error || 'Chưa thực hiện được thao tác.');
    return d;
  }

  function parseCsv(text) {
    const lines = text.replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) throw new Error('Tệp CSV trống.');
    const head = lines[0].split(',').map(s => s.trim().toLowerCase());
    const at = n => head.indexOf(n);
    const iId = at('record_id'), i1 = at('round_million'), i2 = at('creator_equals_approver');
    const iY = at('label') >= 0 ? at('label') : at('y');
    if ([iId, i1, i2, iY].some(i => i < 0)) throw new Error('Thiếu cột. Cần record_id, round_million, creator_equals_approver, label (theo tệp mẫu).');
    return lines.slice(1).map((line, n) => {
      const c = line.split(',').map(s => s.trim());
      const v = i => /^[01]$/.test(c[i] ?? '') ? Number(c[i]) : NaN;
      const row = { record_id: c[iId], x: [v(i1), v(i2)], y: v(iY) };
      if (!row.record_id || row.x.some(Number.isNaN) || Number.isNaN(row.y)) throw new Error('Dòng ' + (n + 2) + ' có giá trị không phải 0/1 hoặc thiếu mã.');
      return row;
    });
  }

  function sampleCsv() {
    const out = ['record_id,round_million,creator_equals_approver,label'];
    for (let i = 0; i < 24; i++) { const r = i % 4 === 0 ? 1 : 0; out.push(`GD-${String(i + 1).padStart(3, '0')},${r ? 1 : (i % 7 ? 0 : 1)},${r ? (i % 8 ? 1 : 0) : 0},${r}`); }
    return out.join('\n');
  }

  function render(s) {
    const kpi = (label, value) => { const b = el('div', null, 'kpi-box'); b.append(el('small', label), el('strong', value)); return b; };
    $('fed-data').replaceChildren(...(s.rows ? [kpi('Số dòng', s.rows), kpi('Nhãn 1 (có vấn đề)', s.label_1), kpi('Nhãn 0 (hợp lệ)', s.label_0), kpi('Nạp lúc', when(s.updated_at))] : [el('p', 'Chưa nạp dữ liệu.', 'mm-sub')]));
    $('sim-badge').hidden = s.source !== 'simulated';
    $('fed-submit').disabled = !s.rows || !s.enrolled;
    $('fed-submit-state').textContent = s.submitted_at ? 'Đã gửi ' + when(s.submitted_at) : (s.enrolled ? 'Chưa gửi' : 'Chưa có khóa mã hóa riêng');
    $('fed-submit-state').className = 'status-pill ' + (s.submitted_at ? 'status-active' : 'status-idle');
    const m = s.station_model;
    $('fed-model').textContent = m ? `Phiên bản v${m.version} (cập nhật ${when(m.accepted_at)}) · học từ ${m.companies.join(', ')} · recall ${pct(m.summary.recall)} · precision ${pct(m.summary.precision)}.` : 'Trạm chưa có mô hình nào.';
    $('fed-sync').disabled = !m || s.synced_version === m.version;
    $('fed-sync-state').textContent = s.synced_version ? `Đang dùng v${s.synced_version} (${when(s.synced_at)})` : 'Chưa đồng bộ';
    $('fed-sync-state').className = 'status-pill ' + (m && s.synced_version === m.version ? 'status-active' : 'status-idle');
  }

  async function load() { render(await api(base() + '/status')); }
  async function guarded(fn) { notice(''); success(''); try { await fn(); } catch (e) { notice(e.message); } }

  $('fed-file').onchange = () => $('fed-file').files[0] && guarded(async () => {
    const rows = parseCsv(await $('fed-file').files[0].text());
    render(await api(base() + '/contribute', { rows, source: 'upload' }));
    success(`Đã nạp ${rows.length} dòng có nhãn.`);
  });
  $('fed-submit').onclick = () => guarded(async () => { render(await api(base() + '/submit', {})); success('Đã gửi lên trạm huấn luyện.'); });
  $('fed-sync').onclick = () => guarded(async () => { const s = await api(base() + '/sync', {}); render(s); success(`Đã đồng bộ mô hình ${s.installed_model.version_tag}.`); });
  $('fed-sample').onclick = e => { e.currentTarget.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(sampleCsv()); };

  async function init() {
    token = sessionStorage.getItem('kt-session') || '';
    if (!mount || !token) { notice('Mở Agent 2 từ Portal và đăng nhập bằng tài khoản quản lý.'); return; }
    try {
      const ctx = await api('/api/v1/ui/context');
      const hash = new URLSearchParams(location.hash.slice(1));
      company = ctx.companies.includes(hash.get('company')) ? hash.get('company') : (ctx.companies[0] || '');
      for (const id of ['nav-queue', 'nav-models', 'nav-fed']) { const a = $(id); a.href = mount + '/' + a.getAttribute('href').replace(/#.*/, '') + '#company=' + encodeURIComponent(company); }
      await load();
    } catch (e) { notice(e.message); }
  }
  init();
})();
