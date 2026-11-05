// Invoices, bank, calendar, questions, legal corpus and enterprise settings.
import { $, api, app, button, dmy, esc, field, hashParams, invLabel, invoiceOf, loadReport, loading, money, needWorkspace, notice, post, put,
  state, table, tag } from './core.js';
import { bankProposals, lawAlerts, riskImport } from './pages_ai.js';

const rerender = () => window.dispatchEvent(new Event('hashchange'));

export async function pageInvoices() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Hóa đơn</h1>${notice('info', 'Chưa phân tích')}`; return; }
  const matched = new Map(rep.matches.flatMap((m) => m.invoice_keys.map((k) => [k, m])));
  const risk = new Map();
  rep.items.forEach((it) => it.invoice_keys.forEach((k) => risk.set(k, [...(risk.get(k) || []), it])));
  app().innerHTML = `<h1 class="page">Hóa đơn</h1><p class="lead">${rep.invoices.length} hóa đơn đọc từ tệp XML. Cột Toàn vẹn cho biết chữ ký số và các kiểm tra số liệu của khung cố định.</p>
    ${table(['Hóa đơn', 'Ngày', 'Người bán', { label: 'Tổng thanh toán', num: true }, { label: 'Thuế', num: true }, 'Toàn vẹn', 'Thanh toán', 'Cảnh báo'], rep.invoices.map((i) => {
      const m = matched.get(i.key);
      const its = risk.get(i.key) || [];
      const integrity = i.guard_errors.length ? tag('AT_RISK', `Lỗi ${i.guard_errors.length}`) : i.signed ? tag('LLM_VERIFIED', 'Chữ ký hợp lệ') : tag('INFO', 'Không ký');
      return `<tr><td>${esc(invLabel(i))}${i.duplicate_of ? ' <span class="muted small">(bản trùng)</span>' : ''}</td><td>${dmy(i.issue_date)}</td><td>${esc(i.seller_name)}</td>
        <td class="num">${money(i.gross)}</td><td class="num">${money(i.vat)}</td><td>${integrity}</td>
        <td>${m ? (m.status === 'MATCHED' ? 'Đã ghép' : 'Mơ hồ') : '<span class="muted">Chưa ghép</span>'}</td><td><div class="chips">${its.map((x) => tag(x.status, x.code.split('_')[0])).join('')}</div></td></tr>`;
    }))}`;
}

export async function pageBank() {
  if (needWorkspace()) return;
  const rep = await loadReport();
  if (!rep) { app().innerHTML = `<h1 class="page">Ngân hàng</h1>${notice('info', 'Chưa phân tích')}`; return; }
  const usedBy = new Map(rep.matches.flatMap((m) => m.txn_ids.map((t) => [t, m])));
  app().innerHTML = `<h1 class="page">Ngân hàng</h1><p class="lead">${rep.transactions.length} giao dịch từ các tệp sao kê. Một khoản chi chỉ được ghép khi đúng số tiền và có dấu hiệu nhận ra người bán (tài khoản, tên hoặc mã số thuế, số hóa đơn).</p><div id="props"></div>
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
  app().innerHTML = `<h1 class="page">Lịch thuế</h1><p class="lead">Hạn nộp tờ khai thuế giá trị gia tăng theo kỳ khai trong hồ sơ; căn cứ đọc từ kho luật. Hạn chưa dời khi trùng ngày nghỉ.</p>
    ${table(['Kỳ', 'Hạn nộp', 'Tình trạng', 'Căn cứ'], (rep?.calendar || []).map((c) => `<tr><td>${esc(c.period)}</td><td>${dmy(c.due)}</td><td>${esc(c.status)}</td><td class="muted small">${esc(c.basis)}</td></tr>`), 'Chưa có dữ liệu.')}`;
}

export async function pageAsk() {
  if (needWorkspace()) return;
  const history = [];
  const samples = ['Tháng 8 có bao nhiêu thuế có nguy cơ bị loại?', 'Hạn nộp tờ khai khi nào?', 'Mức tính tiền chậm nộp là bao nhiêu mỗi ngày?', 'Lập hóa đơn không đúng thời điểm bị phạt thế nào?'];
  app().innerHTML = `<h1 class="page">Hỏi đáp</h1><p class="lead">Câu hỏi về dữ liệu doanh nghiệp được trả lời từ kết quả phân tích. Câu hỏi về quy định được trả lời từ kho luật: mỗi câu phải trích nguyên văn điều khoản và qua kiểm tra căn cứ; không qua thì hệ thống trích nguyên văn hoặc từ chối. Câu cần phán đoán được chuyển chuyên gia.</p>
    <div class="bar">${samples.map((q) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <div id="chat"></div><form id="ask" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="q">Câu hỏi</label><input class="cds--text-input" id="q" name="q" autocomplete="off" placeholder="Ví dụ: hóa đơn số 340 có vấn đề gì?"></div>${button('Hỏi', 'primary', 'type="submit"')}</form>`;
  const chat = $('#chat');
  const ask = async (q) => {
    history.push(`<div class="answer user"><strong>${esc(q)}</strong></div>`);
    chat.innerHTML = history.join('') + loading('Đang trả lời; câu hỏi về quy định có thể mất 20 đến 60 giây với mô hình chạy trên máy');
    try {
      const a = await post(`/api/workspaces/${state.ws}/ask`, { question: q });
      const rag = a.facts?.find((f) => f && f.passages);
      const cites = rag
        ? rag.sentences.flatMap((s) => s.citations).filter((c, i, arr) => arr.findIndex((x) => x.path === c.path) === i)
          .map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.doc_num)}</a>: ${esc(c.path.split(' > ').slice(1).join(' > '))}`)
        : a.citations.map(esc);
      history.push(`<div class="answer"><div class="chips">${tag(a.branch)}${rag ? tag(rag.mode) : ''}</div><p style="margin:.5rem 0 0">${esc(a.text)}</p>
        ${cites.length ? `<div class="cite">Căn cứ: ${cites.join('; ')}</div>` : ''}
        ${rag?.dropped?.length ? `<div class="cite">${rag.dropped.length} câu của mô hình bị loại vì không có căn cứ.</div>` : ''}
        ${rag?.stats?.seconds ? `<div class="cite">${esc(rag.stats.model)}, ${rag.stats.prompt_tokens} token ngữ cảnh, ${rag.stats.seconds} giây.</div>` : ''}</div>`);
    } catch (err) { history.push(notice('error', 'Không trả lời được', err.message)); }
    chat.innerHTML = history.join('');
  };
  $('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); if (q) { $('#q').value = ''; ask(q); } };
  app().querySelectorAll('[data-q]').forEach((b) => { b.onclick = () => ask(b.dataset.q); });
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
  app().innerHTML = `<h1 class="page">Kho luật</h1><p class="lead">Văn bản thuế lấy tự động từ Cơ sở dữ liệu quốc gia về pháp luật (vbpl.vn) của Bộ Tư pháp, theo từng điều, khoản, điểm, có ngày hiệu lực. Chỉ đọc trang được phép theo robots.txt, tối đa 1 yêu cầu mỗi 2 giây.</p>
    <div class="kpis"><div class="kpi"><span class="label">Văn bản</span><span class="value">${s ? s.documents : 0}</span><span class="sub">${s ? `${s.in_force} còn hiệu lực` : ''}</span></div>
    <div class="kpi"><span class="label">Điều khoản</span><span class="value">${s ? s.provisions.toLocaleString('vi-VN') : 0}</span><span class="sub">${s ? `${s.chunks.toLocaleString('vi-VN')} đoạn tìm kiếm` : ''}</span></div>
    <div class="kpi"><span class="label">Lần đồng bộ gần nhất</span><span class="value" style="font-size:1.25rem">${s?.last_snapshot?.created_at ? dmy(s.last_snapshot.created_at) : 'chưa có'}</span>
    <span class="sub">${st.job.running ? `đang chạy${st.job.external ? ' từ dòng lệnh' : ''}: ${st.job.done} văn bản, ${esc(st.job.last)}` : ''}</span></div>
    <div class="kpi"><span class="label">Hết hiệu lực theo văn bản thay thế</span><span class="value">${s ? s.ended_by_later_act ?? 0 : 0}</span><span class="sub">đọc từ điều khoản hiệu lực thi hành của văn bản mới</span></div></div>
    <div class="bar">${button(st.job.running ? 'Đang đồng bộ' : 'Đồng bộ kho luật', 'primary', `id="sync" ${st.job.running ? 'disabled' : ''}`)}${button('Chỉ văn bản lõi', 'tertiary', `id="sync-core" ${st.job.running ? 'disabled' : ''}`)}
    <span>${st.job.error ? notice('error', 'Lỗi đồng bộ', st.job.error) : ''}</span></div>
    <div id="alerts"></div>
    <h2 class="section">Tìm trong kho</h2><form id="lsearch" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="lq">Nội dung</label><input class="cds--text-input" id="lq" placeholder="Ví dụ: thời hạn nộp hồ sơ khai thuế theo quý"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="lasof">Ngày áp dụng</label><input class="cds--text-input" id="lasof" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
    ${button('Tìm', 'primary', 'type="submit"')}</form><div id="lres"></div>
    <h2 class="section">Thay đổi gần đây</h2>${table(['Lần', 'Loại', 'Văn bản', 'Chi tiết'], (st.changes || []).slice(0, 15).map((c) => `<tr><td>${c.snapshot_id}</td><td>${esc(c.kind)}</td><td>${esc(c.doc_num || '')}</td><td>${esc(c.detail)}</td></tr>`), 'Chưa có thay đổi.')}
    <h2 class="section">Văn bản</h2><div id="ldocs">${loading('Đang tải danh sách')}</div>`;
  const startSync = async (q) => {
    try { await post(`/api/law/sync${q}`); rerender(); } catch (err) { $('#lres').innerHTML = notice('error', 'Chưa đồng bộ được', err.message); }
  };
  $('#sync').onclick = () => startSync('');
  $('#sync-core').onclick = () => startSync('?core_only=true');
  lawAlerts($('#alerts')).catch(() => {});
  if (st.job.running) setTimeout(() => { if (location.hash.startsWith('#/luat') && !hashParams().get('doc')) rerender(); }, 5000);
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
