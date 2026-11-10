// Question assistant: guide generated from the domain catalog, suggestions from this enterprise's data, answers with
// "how the question was understood" and other domains to pick when it was misunderstood.
import { $, api, app, button, esc, loading, needWorkspace, notice, onPageLeave, pageSignal, post, state, tag } from './core.js';

let guideCache = null;

function guideHtml(g) {
  return `<details class="guide" id="guide" style="border-radius:8px;overflow:hidden">
    <summary style="font-size:13.5px;font-weight:600">Danh mục câu hỏi trợ lý hỗ trợ (${g.groups.reduce((n, x) => n + x.domains.length, 0)} nhóm)</summary>
    <p class="muted small" style="margin:4px 0 12px 1rem">Bấm vào bất kỳ câu hỏi ví dụ nào để gửi ngay vào hội thoại.</p>
    ${g.groups.map((grp) => `<details class="guide-group" style="margin:6px 0 6px 1rem">
      <summary style="font-size:13px;font-weight:600">${esc(grp.title)} <span class="muted small">(${grp.domains.length} câu)</span></summary>
      ${grp.domains.map((d) => `<div class="guide-domain" style="border-bottom:1px solid var(--cds-border-subtle);padding:10px 0">
        <strong style="font-size:13px;color:var(--a3-primary)">${esc(d.title)}</strong>
        <div class="small" style="margin:2px 0 6px">${esc(d.what)}</div>
        ${d.limits ? `<div class="muted small" style="margin-bottom:6px"><em>Giới hạn:</em> ${esc(d.limits)}</div>` : ''}
        <div class="chips">${d.examples.map((q) => (q.includes('<')
          ? `<span class="chip-tpl small">${esc(q)}</span>`
          : `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${esc(q)}" style="border-radius:9999px;font-size:12px">${esc(q)}</button>`)).join('')}</div>
      </div>`).join('')}
    </details>`).join('')}
  </details>`;
}

function understood(a) {
  const u = a.understood || {};
  if (!u.title) return '';
  const bits = [u.period && `kỳ ${u.period}`, u.invoice_numbers && `hóa đơn ${u.invoice_numbers.join(', ')}`, u.seller && `người bán ${u.seller}`,
    u.issue && `loại vấn đề: ${u.issue}`, u.top_n && `${u.top_n} dòng`].filter(Boolean);
  return `<div class="understood small" style="background:var(--cds-layer-hover);padding:6px 12px;border-radius:6px;margin:8px 0;display:inline-block">
    Phân tích câu hỏi: <strong>${esc(u.title)}</strong>${bits.length ? ` (${esc(bits.join('; '))})` : ''}
  </div>`;
}

function answerHtml(q, a, secs) {
  const rag = (a.facts || []).find((f) => f && f.passages);
  const cites = rag
    ? rag.sentences.flatMap((s) => s.citations).filter((c, i, arr) => arr.findIndex((x) => x.path === c.path) === i)
      .map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener" style="color:var(--a3-primary);font-weight:600">${esc(c.doc_num)}</a>: ${esc(c.path.split(' > ').slice(1).join(' > '))}`)
    : (a.citations || []).map(esc);
  const rows = a.rows || [];
  const cols = a.columns || [];
  const shown = rows.slice(0, 50);
  const tableHtml = rows.length && cols.length ? `<div class="table-wrap" style="margin:12px 0"><table class="cds--data-table cds--data-table--sm"><thead><tr>${cols.map(([, h]) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${shown.map((r) => `<tr>${cols.map(([k]) => `<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${rows.length > shown.length ? `<div class="muted small">Hiện 50 trên ${rows.length} dòng; xem đủ ở trang liên quan.</div>` : ''}` : '';
  const alts = a.alternatives?.length ? `<div class="alts small" style="margin-top:12px;border-top:1px solid var(--cds-border-subtle);padding-top:8px">${a.domain ? 'Không đúng ý? Thử hỏi theo loại khác:' : 'Có phải bạn muốn hỏi:'} ${a.alternatives
    .map((x) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm alt-q" data-q="${esc(q)}" data-domain="${esc(x.domain)}" style="border-radius:9999px;margin:2px">${esc(x.title)}</button>`).join('')}</div>` : '';
  const how = { SEMANTIC: 'nhận dạng ngữ nghĩa', STRUCTURE: 'nhận dạng theo số hóa đơn/MST đối tác', MODEL: 'mô hình AI phân loại',
    CHOSEN_BY_USER: 'loại do bạn chọn', REFUSED: 'ngoài phạm vi', KEYWORD_FALLBACK: 'nhận dạng từ khóa' }[a.route?.method] || '';

  return `<div class="answer msg-bot">
    <div class="ans-head">
      ${tag(a.branch === 'REFUSED' ? 'ABSTAIN' : a.branch, a.branch === 'REFUSED' ? 'Không trả lời' : a.branch === 'HELP' ? 'Hướng dẫn' : undefined)}
      ${rag ? tag(rag.mode) : ''}
      <span class="muted small" style="margin-left:auto">${secs}s${how ? ` · ${esc(how)}` : ''}</span>
    </div>
    ${understood(a)}
    <p class="ans-text">${esc(a.text)}</p>
    ${tableHtml}
    ${cites.length ? `<div class="cite" style="background:var(--cds-layer);padding:8px 12px;border-radius:6px;margin-top:10px"><strong>Căn cứ pháp lý:</strong> ${cites.join('; ')}</div>` : ''}
    ${rag?.dropped?.length ? `<div class="cite" style="color:var(--a3-warning)">⚠️ ${rag.dropped.length} câu của mô hình đã bị loại bỏ do không có trích dẫn điều luật bảo đảm.</div>` : ''}
    ${(a.links || []).length ? `<div class="chips" style="margin-top:10px">${a.links.map(([l, h]) => `<a class="cds--btn cds--btn--ghost cds--btn--sm" href="${esc(h)}" style="border-radius:6px">${esc(l)} →</a>`).join('')}</div>` : ''}
    ${alts}
  </div>`;
}

export async function pageAsk() {
  if (needWorkspace()) return;
  const signal = pageSignal();
  const workspace = state.ws;
  let timer;
  onPageLeave(() => clearInterval(timer));
  const key = `agent3.chat2.${state.ws}`;
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(key) || '[]'); } catch { history = []; }
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(history.slice(-30))); } catch { /* private mode */ } };

  app().innerHTML = `<div class="ask-wrap">
    <h1 class="page">Trợ lý hỏi đáp thuế & Dữ liệu</h1>
    <p class="lead">Hỏi bằng ngôn ngữ tự nhiên về dữ liệu thuế của doanh nghiệp hoặc các quy định pháp luật. Trợ lý chỉ trả lời khi có căn cứ đối chiếu cụ thể từ hóa đơn hoặc điều luật.</p>
    
    <div id="sugg" class="sugg" style="margin-bottom:12px"></div>
    <div id="chat" class="chat" role="log" aria-label="Hội thoại" aria-live="polite"></div>
    <div id="pending" role="status"></div>

    <form id="ask" class="ask-bar">
      <div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
        <label class="cds--label" for="q">Nhập câu hỏi (Enter để gửi)</label>
        <input class="cds--text-input" id="q" name="q" autocomplete="off" maxlength="500" placeholder="Ví dụ: quý 3 có bao nhiêu tiền thuế có nguy cơ bị loại?">
      </div>
      ${button('Hỏi trợ lý', 'primary', 'type="submit"')}
      ${history.length ? button('Xóa lịch sử', 'ghost', 'id="clear"') : ''}
    </form>

    <div id="guide-box" style="margin-top:24px">${loading('Đang tải danh mục câu hỏi trợ lý')}</div>
  </div>`;

  const chat = $('#chat');
  const pending = $('#pending');
  const form = $('#ask');
  const submit = form.querySelector('[type="submit"]');
  const input = $('#q');
  const draw = () => { chat.innerHTML = history.join(''); };
  draw();

  let busy = false;
  const ask = async (q, domain) => {
    if (busy || !q || signal.aborted) return;
    busy = true;
    submit.disabled = true; input.disabled = true; form.setAttribute('aria-busy', 'true');
    history.push(`<div class="msg-user"><div>${esc(q)}${domain ? ' <span class="small">(đã chọn lại loại câu hỏi)</span>' : ''}</div></div>`);
    draw();
    const t0 = Date.now();
    const tick = () => {
      const s = Math.round((Date.now() - t0) / 1000);
      if (!signal.aborted) pending.innerHTML = loading(s > 3 ? `Đang tìm điều khoản và trích xuất căn cứ (${s}s)` : 'Đang xử lý câu hỏi');
    };
    tick();
    timer = setInterval(tick, 1000);
    try {
      const a = await post(`/api/workspaces/${workspace}/ask`, domain ? { question: q, domain } : { question: q }, { signal });
      if (signal.aborted) return;
      history.push(answerHtml(q, a, Math.round((Date.now() - t0) / 1000)));
    } catch (err) {
      if (signal.aborted) return;
      history.push(notice('error', 'Không trả lời được', err.message));
      input.value = q;
    }
    clearInterval(timer);
    pending.innerHTML = '';
    busy = false;
    submit.disabled = false; input.disabled = false; form.removeAttribute('aria-busy'); input.focus();
    save();
    draw();
    chat.lastElementChild?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
  };

  $('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); $('#q').value = ''; ask(q); };

  app().addEventListener('click', (e) => {
    const c = e.target.closest('.chip-q');
    if (c) { ask(c.dataset.q); return; }
    const alt = e.target.closest('.alt-q');
    if (alt) ask(alt.dataset.q, alt.dataset.domain);
  }, { signal });

  if ($('#clear')) $('#clear').onclick = () => { history = []; save(); draw(); $('#clear').remove(); };

  try {
    guideCache ||= await api('/api/chat/guide');
    if (signal.aborted) return;
    $('#guide-box').innerHTML = guideHtml(guideCache);
  } catch (err) {
    if (signal.aborted) return;
    $('#guide-box').innerHTML = notice('error', 'Không tải được hướng dẫn', err.message);
  }

  try {
    const s = await api(`/api/workspaces/${state.ws}/chat/suggestions`);
    if (signal.aborted) return;
    $('#sugg').innerHTML = `<div class="muted small" style="margin-bottom:6px">Gợi ý câu hỏi phổ biến:</div>
      <div class="chips">${s.slice(0, 5).map((q) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${esc(q)}" style="border-radius:9999px">${esc(q)}</button>`).join('')}</div>`;
  } catch {
    if (!signal.aborted) $('#sugg').innerHTML = '';
  }
}
