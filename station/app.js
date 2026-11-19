'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const el = (t, txt, cls) => { const n = document.createElement(t); if (txt != null) n.textContent = txt; if (cls) n.className = cls; return n; };
  const pct = v => v == null ? '—' : (v * 100).toFixed(1).replace('.', ',') + '%';
  const time = s => s ? new Date(s).toLocaleString('vi-VN') : '—';
  let active = null;
  const notice = m => { $('notice').textContent = m || ''; $('notice').hidden = !m; };

  async function api(path, body) {
    const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    const d = await r.json();
    if (!r.ok) throw new Error(d.errors?.map(e => e.message).join(' ') || d.error || 'Lỗi');
    return d;
  }

  function renderRun(doc) {
    const map = { running: 'Đang huấn luyện', completed: 'Hoàn tất', failed: 'Lỗi' };
    $('state').textContent = map[doc.state] || 'Chưa chạy';
    $('state').className = 'pill ' + (doc.state || '');
    $('events').replaceChildren(...(doc.events || []).map(e => { const li = el('li'); li.append(el('time', new Date(e.at).toLocaleTimeString('vi-VN')), el('span', e.message)); return li; }));
    const total = (doc.rounds || 1) * (doc.companies || []).length;
    const done = (doc.events || []).filter(e => e.stage === 'fhe').length;
    $('fill').style.width = (doc.state === 'completed' ? 100 : Math.min(95, Math.round(done / Math.max(1, total) * 90))) + '%';
  }

  async function load() {
    const s = await api('/api/status');
    const ok = s.worker && (s.worker.status === 'ok' || s.worker.ok || s.worker.healthy || s.worker.reachable);
    $('worker').textContent = ok ? 'Máy tính toán mã hóa sẵn sàng' : 'Máy tính toán mã hóa đang tắt (tự bật khi huấn luyện)';
    $('contrib').replaceChildren(...s.contributions.map(c => { const tr = el('tr'); tr.append(el('td', c.company_id), el('td', c.submitted ? 'Đã gửi' : 'Chưa gửi', c.submitted ? 'ok' : 'muted'), el('td', c.rows || '—'), el('td', c.submitted ? c.label_1 : '—'), el('td', time(c.submitted_at))); return tr; }));
    const m = s.current_model;
    $('model').textContent = m ? `Phiên bản v${m.version} · recall ${pct(m.summary.recall)} · precision ${pct(m.summary.precision)} · F1 ${pct(m.summary.f1)} · từ ${m.companies.join(', ')} · cập nhật ${time(m.accepted_at)}` : 'Chưa có mô hình nào.';
    $('models').replaceChildren(...s.models.map(v => { const tr = el('tr'); tr.append(el('td', 'v' + v.version), el('td', pct(v.summary.recall)), el('td', pct(v.summary.precision)), el('td', pct(v.summary.f1)), el('td', time(v.accepted_at))); return tr; }));
    $('run').disabled = s.contributions.filter(c => c.submitted).length < 2 || !!active;
    if (s.latest) { renderRun(s.latest); if (s.latest.state === 'running' && !active) { active = s.latest.run_id; poll(); } }
  }

  async function poll() {
    if (!active) return;
    try {
      const doc = await api('/api/job', { run_id: active });
      renderRun(doc);
      if (doc.state === 'running') { setTimeout(poll, 2000); return; }
      active = null; if (doc.state === 'failed') notice(doc.error); await load();
    } catch (e) { notice(e.message); active = null; }
  }

  $('run').onclick = async () => {
    notice(''); $('run').disabled = true;
    try { const doc = await api('/api/run', { rounds: Number($('rounds').value) }); active = doc.run_id; renderRun(doc); poll(); }
    catch (e) { notice(e.message); $('run').disabled = false; }
  };
  load().catch(e => notice(e.message));
  setInterval(() => { if (!active) load().catch(() => {}); }, 10000);
})();
