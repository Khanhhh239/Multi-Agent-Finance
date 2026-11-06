// Question assistant: guide generated from the domain catalog, suggestions from this enterprise's data, answers with
// "how the question was understood" and other domains to pick when it was misunderstood.
import { $, api, app, button, esc, loading, needWorkspace, notice, post, state, tag } from './core.js';

let guideCache = null;

function guideHtml(g) {
  return `<details class="guide" id="guide"><summary>Trợ lý trả lời được gì (${g.groups.reduce((n, x) => n + x.domains.length, 0)} loại câu hỏi)</summary>
    <p class="muted small">Danh sách này sinh ra từ đúng danh mục mà trợ lý dùng để hiểu câu hỏi, nên chỉ có những loại câu trợ lý thật sự trả lời được. Bấm một câu ví dụ để hỏi.</p>
    ${g.groups.map((grp) => `<details class="guide-group"><summary>${esc(grp.title)} <span class="muted small">(${grp.domains.length})</span></summary>
      ${grp.domains.map((d) => `<div class="guide-domain"><strong>${esc(d.title)}</strong><div class="small">${esc(d.what)}</div>
        ${d.limits ? `<div class="muted small">Giới hạn: ${esc(d.limits)}</div>` : ''}
        <div class="chips">${d.examples.map((q) => (q.includes('<')
          ? `<span class="chip-tpl small">${esc(q)}</span>`
          : `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${esc(q)}">${esc(q)}</button>`)).join('')}</div></div>`).join('')}
    </details>`).join('')}</details>`;
}

function understood(a) {
  const u = a.understood || {};
  if (!u.title) return '';
  const bits = [u.period && `kỳ ${u.period}`, u.invoice_numbers && `hóa đơn ${u.invoice_numbers.join(', ')}`, u.seller && `người bán ${u.seller}`,
    u.issue && `loại vấn đề: ${u.issue}`, u.top_n && `${u.top_n} dòng`].filter(Boolean);
  return `<div class="understood small">Trợ lý hiểu câu hỏi là: <strong>${esc(u.title)}</strong>${bits.length ? ` (${esc(bits.join('; '))})` : ''}</div>`;
}

function answerHtml(q, a, secs) {
  const rag = (a.facts || []).find((f) => f && f.passages);
  const cites = rag
    ? rag.sentences.flatMap((s) => s.citations).filter((c, i, arr) => arr.findIndex((x) => x.path === c.path) === i)
      .map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.doc_num)}</a>: ${esc(c.path.split(' > ').slice(1).join(' > '))}`)
    : (a.citations || []).map(esc);
  const rows = a.rows || [];
  const cols = a.columns || [];
  const shown = rows.slice(0, 50);
  const tableHtml = rows.length && cols.length ? `<div class="table-wrap"><table class="cds--data-table cds--data-table--sm"><thead><tr>${cols.map(([, h]) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${shown.map((r) => `<tr>${cols.map(([k]) => `<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${rows.length > shown.length ? `<div class="muted small">Hiện 50 trên ${rows.length} dòng; xem đủ ở trang liên quan.</div>` : ''}` : '';
  const alts = a.alternatives?.length ? `<div class="alts small">${a.domain ? 'Không đúng ý? Hỏi theo loại khác:' : 'Có phải bạn muốn hỏi:'} ${a.alternatives
    .map((x) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm alt-q" data-q="${esc(q)}" data-domain="${esc(x.domain)}">${esc(x.title)}</button>`).join('')}</div>` : '';
  const how = { SEMANTIC: 'nhận dạng theo nghĩa', STRUCTURE: 'nhận dạng theo số hóa đơn, tên người bán trong câu', MODEL: 'mô hình trên máy chọn loại câu hỏi',
    CHOSEN_BY_USER: 'loại do bạn chọn', REFUSED: 'không nhận dạng được', KEYWORD_FALLBACK: 'nhận dạng theo từ (máy chủ mô hình chưa chạy)' }[a.route?.method] || '';
  return `<div class="answer"><div class="chips">${tag(a.branch === 'REFUSED' ? 'ABSTAIN' : a.branch, a.branch === 'REFUSED' ? 'Không trả lời' : a.branch === 'HELP' ? 'Hướng dẫn' : undefined)}${rag ? tag(rag.mode) : ''}
    <span class="muted small">${secs} giây${how ? `; ${esc(how)}` : ''}</span></div>${understood(a)}
    <p style="margin:.5rem 0 0">${esc(a.text)}</p>${tableHtml}
    ${cites.length ? `<div class="cite">Căn cứ: ${cites.join('; ')}</div>` : ''}
    ${rag?.dropped?.length ? `<div class="cite">${rag.dropped.length} câu của mô hình bị loại vì không có căn cứ.</div>` : ''}
    ${(a.links || []).length ? `<div class="chips">${a.links.map(([l, h]) => `<a class="cds--btn cds--btn--ghost cds--btn--sm" href="${esc(h)}">${esc(l)}</a>`).join('')}</div>` : ''}
    ${alts}</div>`;
}

export async function pageAsk() {
  if (needWorkspace()) return;
  const key = `agent3.chat2.${state.ws}`;
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(key) || '[]'); } catch { history = []; }
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(history.slice(-30))); } catch { /* private mode */ } };
  app().innerHTML = `<h1 class="page">Hỏi đáp</h1><p class="lead">Hỏi bằng lời thường về số liệu của doanh nghiệp hoặc về quy định. Số liệu lấy từ kết quả phân tích; câu về quy định phải trích nguyên văn điều khoản còn hiệu lực. Câu ngoài phạm vi hoặc chưa rõ thì trợ lý từ chối, không đoán.</p>
    <div id="guide-box">${loading('Đang tải hướng dẫn')}</div>
    <div class="chips" id="sugg"></div>
    <div id="chat"></div><div id="pending"></div>
    <form id="ask" class="bar ask-bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="q">Câu hỏi (Enter để gửi)</label><input class="cds--text-input" id="q" name="q" autocomplete="off" maxlength="500" placeholder="Ví dụ: quý này có bao nhiêu thuế có nguy cơ?"></div>${button('Hỏi', 'primary', 'type="submit"')}
    ${history.length ? button('Xóa lịch sử', 'ghost', 'id="clear"') : ''}</form>`;
  const chat = $('#chat');
  const draw = () => { chat.innerHTML = history.join(''); };
  draw();
  let busy = false;
  const ask = async (q, domain) => {
    if (busy || !q) return;
    busy = true;
    history.push(`<div class="answer user"><strong>${esc(q)}</strong>${domain ? ' <span class="muted small">(chọn lại loại câu hỏi)</span>' : ''}</div>`); draw();
    const t0 = Date.now();
    const tick = () => {
      const s = Math.round((Date.now() - t0) / 1000);
      $('#pending').innerHTML = loading(s > 3 ? `Đang trả lời (${s} giây). Câu về quy định cần tìm điều khoản và kiểm tra căn cứ, có thể mất 30 đến 60 giây` : 'Đang trả lời');
    };
    tick();
    const timer = setInterval(tick, 1000);
    try {
      const a = await post(`/api/workspaces/${state.ws}/ask`, domain ? { question: q, domain } : { question: q });
      history.push(answerHtml(q, a, Math.round((Date.now() - t0) / 1000)));
    } catch (err) { history.push(notice('error', 'Không trả lời được', err.message)); }
    clearInterval(timer);
    $('#pending').innerHTML = '';
    busy = false;
    save();
    draw();
    chat.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  $('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); $('#q').value = ''; ask(q); };
  app().addEventListener('click', (e) => {
    const c = e.target.closest('.chip-q');
    if (c) { ask(c.dataset.q); return; }
    const alt = e.target.closest('.alt-q');
    if (alt) ask(alt.dataset.q, alt.dataset.domain);
  });
  if ($('#clear')) $('#clear').onclick = () => { history = []; save(); draw(); $('#clear').remove(); };
  try {
    guideCache ||= await api('/api/chat/guide');
    $('#guide-box').innerHTML = guideHtml(guideCache);
  } catch (err) { $('#guide-box').innerHTML = notice('error', 'Không tải được hướng dẫn', err.message); }
  try {
    const s = await api(`/api/workspaces/${state.ws}/chat/suggestions`);
    $('#sugg').innerHTML = `<span class="muted small">Gợi ý từ dữ liệu của doanh nghiệp:</span>${s.map((q) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${esc(q)}">${esc(q)}</button>`).join('')}`;
  } catch { $('#sugg').innerHTML = ''; }
}
