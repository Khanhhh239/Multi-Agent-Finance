// Question assistant: guide generated from the domain catalog, suggestions from this enterprise's data, answers with
// "how the question was understood" and other domains to pick when it was misunderstood.
import { $, api, app, button, esc, loading, needWorkspace, notice, onPageLeave, pageSignal, post, sonHeader, state, tag } from './core.js';

const ICONS_CHAT = {
  sparkles: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>',
  bolt: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  calendar: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
  law: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="3" x2="12" y2="21"/><path d="M4 7h16"/><path d="M5 7l-3 7h6l-3-7z"/><path d="M19 7l-3 7h6l-3-7z"/><circle cx="12" cy="3" r="1"/></svg>',
  book: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
  alertTriangle: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  shieldLock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><rect x="9.5" y="10" width="5" height="4" rx="1"/><path d="M10.5 10V8.5a1.5 1.5 0 0 1 3 0V10"/></svg>',
  trash: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
};

let guideCache = null;

function guideHtml(g) {
  return `<details class="guide" id="guide" style="border-radius:12px;overflow:hidden;margin-top:20px;border:1px solid var(--cds-border-subtle);background:var(--cds-layer)">
    <summary style="font-size:13.5px;font-weight:600;padding:12px 16px;cursor:pointer">Danh mục câu hỏi trợ lý hỗ trợ (${g.groups.reduce((n, x) => n + x.domains.length, 0)} nhóm)</summary>
    <p class="muted small" style="margin:4px 16px 12px">Bấm vào bất kỳ câu hỏi mẫu nào để gửi ngay vào cuộc hội thoại.</p>
    ${g.groups.map((grp) => `<details class="guide-group" style="margin:6px 16px 10px">
      <summary style="font-size:13px;font-weight:600;cursor:pointer">${esc(grp.title)} <span class="muted small">(${grp.domains.length} câu)</span></summary>
      ${grp.domains.map((d) => `<div class="guide-domain" style="border-bottom:1px solid var(--cds-border-subtle);padding:10px 0">
        <strong style="font-size:13px;color:var(--a3-primary, #0f766e)">${esc(d.title)}</strong>
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
  return `<div class="understood small" style="background:var(--cds-layer-hover, #f4f4f4);padding:5px 12px;border-radius:6px;margin:6px 0 10px;display:inline-block">
    Phân tích câu hỏi: <strong>${esc(u.title)}</strong>${bits.length ? ` (${esc(bits.join('; '))})` : ''}
  </div>`;
}

function answerHtml(q, a, secs) {
  const rag = (a.facts || []).find((f) => f && f.passages);
  const cites = rag
    ? rag.sentences.flatMap((s) => s.citations).filter((c, i, arr) => arr.findIndex((x) => x.path === c.path) === i)
      .map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener" style="color:#0f766e;font-weight:600">${esc(c.doc_num)}</a>: ${esc(c.path.split(' > ').slice(1).join(' > '))}`)
    : (a.citations || []).map(esc);
  const rows = a.rows || [];
  const cols = a.columns || [];
  const shown = rows.slice(0, 50);
  const tableHtml = rows.length && cols.length ? `<div class="table-wrap" style="margin:12px 0"><table class="cds--data-table cds--data-table--sm"><thead><tr>${cols.map(([, h]) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${shown.map((r) => `<tr>${cols.map(([k]) => `<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${rows.length > shown.length ? `<div class="muted small">Hiện 50 trên ${rows.length} dòng; xem đủ ở trang liên quan.</div>` : ''}` : '';
  const alts = a.alternatives?.length ? `<div class="alts small" style="margin-top:12px;border-top:1px dashed var(--cds-border-subtle);padding-top:8px">${a.domain ? 'Không đúng ý? Thử hỏi theo loại khác:' : 'Có phải bạn muốn hỏi:'} ${a.alternatives
    .map((x) => `<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm alt-q" data-q="${esc(q)}" data-domain="${esc(x.domain)}" style="border-radius:9999px;margin:2px">${esc(x.title)}</button>`).join('')}</div>` : '';
  const how = { SEMANTIC: 'nhận dạng ngữ nghĩa', STRUCTURE: 'nhận dạng theo số hóa đơn/MST đối tác', MODEL: 'mô hình AI phân loại',
    CHOSEN_BY_USER: 'loại do bạn chọn', REFUSED: 'ngoài phạm vi', KEYWORD_FALLBACK: 'nhận dạng từ khóa' }[a.route?.method] || '';

  return `<div class="msg-bot-row">
    <div class="bot-avatar-box" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="3" y="8" width="18" height="12" rx="4"/><circle cx="9" cy="13" r="1.5" fill="currentColor"/><circle cx="15" cy="13" r="1.5" fill="currentColor"/><path d="M9 17h6"/></svg>
    </div>
    <div class="bot-bubble">
      <div class="bot-bubble-head">
        <span class="bot-author">Trợ lý Thuế GTGT</span>
        ${tag(a.branch === 'REFUSED' ? 'ABSTAIN' : a.branch, a.branch === 'REFUSED' ? 'Không trả lời' : a.branch === 'HELP' ? 'Hướng dẫn' : undefined)}
        ${rag ? tag(rag.mode) : ''}
        <span class="bot-time">${secs}s${how ? ` · ${esc(how)}` : ''}</span>
      </div>
      ${understood(a)}
      <div class="bot-text">${esc(a.text)}</div>
      ${tableHtml}
      ${cites.length ? `<div class="cite-box">
        <div class="cite-head"><span class="cite-icon" aria-hidden="true">${ICONS_CHAT.book}</span> Căn cứ pháp lý trích dẫn:</div>
        <div class="cite-links">${cites.join('; ')}</div>
      </div>` : ''}
      ${rag?.dropped?.length ? `<div class="cite-warning"><span class="warn-icon" aria-hidden="true">${ICONS_CHAT.alertTriangle}</span> ${rag.dropped.length} câu của mô hình đã bị loại bỏ do không có trích dẫn điều luật bảo đảm.</div>` : ''}
      ${(a.links || []).length ? `<div class="chips" style="margin-top:10px">${a.links.map(([l, h]) => `<a class="cds--btn cds--btn--ghost cds--btn--sm" href="${esc(h)}" style="border-radius:6px">${esc(l)} →</a>`).join('')}</div>` : ''}
      ${alts}
      <div class="bot-actions-row">
        <button type="button" class="copy-msg-btn" title="Sao chép nội dung">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>Sao chép</span>
        </button>
      </div>
    </div>
  </div>`;
}

function userMsgHtml(q, domain) {
  const d = new Date();
  const timeStr = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  return `<div class="msg-user-row">
    <div class="user-bubble-box">
      <div class="user-bubble">${esc(q)}${domain ? ' <span class="small">(đã chọn lại loại câu hỏi)</span>' : ''}</div>
      <div class="user-meta"><span>Bạn</span> · <span class="msg-time">${timeStr}</span></div>
    </div>
    <div class="user-avatar-circle" aria-hidden="true">B</div>
  </div>`;
}

function renderHero() {
  return `<div class="chat-hero" id="chat-hero">
    <div class="hero-badge">
      <span class="sparkle-icon" aria-hidden="true">${ICONS_CHAT.sparkles}</span>
      <span>TRỢ LÝ AI ĐỐI SOÁT THUẾ GTGT</span>
    </div>
    <h2 class="hero-title">Xin chào! Trợ lý có thể hỗ trợ gì cho doanh nghiệp hôm nay?</h2>
    <p class="hero-desc">Hỏi bằng ngôn ngữ tự nhiên về số liệu thuế, rà soát hóa đơn rủi ro hoặc tra cứu căn cứ pháp lý từ Cơ sở dữ liệu Quốc gia. Dữ liệu xử lý an toàn 100% nội bộ trên máy này.</p>
    <div class="prompt-cards-grid">
      <div class="prompt-card chip-q" data-q="Quý này có bao nhiêu tiền thuế có nguy cơ bị loại?">
        <div class="card-icon">${ICONS_CHAT.bolt}</div>
        <div class="card-title">Rủi ro thuế kỳ hiện tại</div>
        <div class="card-sub">Tổng số thuế GTGT có nguy cơ và cần xem xét</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hóa đơn số 340 có vấn đề gì và căn cứ xử lý?">
        <div class="card-icon">${ICONS_CHAT.search}</div>
        <div class="card-title">Đối chiếu hóa đơn</div>
        <div class="card-sub">Kiểm tra tính hợp lệ và cảnh báo nhà cung cấp</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hạn nộp tờ khai thuế giá trị gia tăng quý 1 năm 2026 khi nào?">
        <div class="card-icon">${ICONS_CHAT.calendar}</div>
        <div class="card-title">Lịch nộp tờ khai</div>
        <div class="card-sub">Theo dõi hạn nộp tờ khai và dời ngày nghỉ</div>
      </div>
      <div class="prompt-card chip-q" data-q="Điều kiện khấu trừ thuế giá trị gia tăng đầu vào gồm những gì?">
        <div class="card-icon">${ICONS_CHAT.law}</div>
        <div class="card-title">Điều kiện khấu trừ</div>
        <div class="card-sub">Trích dẫn luật thuế GTGT và chứng từ thanh toán</div>
      </div>
    </div>
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
    ${sonHeader('Hỏi đáp', 'Hỏi đáp thuế & dữ liệu', 'TRỢ LÝ AI ĐỐI CHIẾU')}
    
    <div id="hero-container">${history.length ? '' : renderHero()}</div>
    <div id="chat" class="chat" role="log" aria-label="Hội thoại" aria-live="polite"></div>
    <div id="pending" role="status"></div>

    <form id="ask" class="ask-bar-floating">
      <div class="ask-input-pill">
        <input class="ask-text-input" id="q" name="q" autocomplete="off" maxlength="500" placeholder="Nhập câu hỏi về hóa đơn, kỳ thuế hoặc quy định pháp luật... (Enter để gửi)">
        <button type="submit" class="send-btn" id="send-btn" title="Gửi câu hỏi" aria-label="Gửi câu hỏi">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div class="ask-bar-footer">
        <span class="privacy-badge"><span class="privacy-icon" aria-hidden="true">${ICONS_CHAT.shieldLock}</span> <span>Dữ liệu được xử lý an toàn nội bộ trên máy này</span></span>
        <div style="display:flex;align-items:center;gap:12px">
          ${history.length ? `<button type="button" class="btn-clear-chat" id="clear"><span class="clear-icon" aria-hidden="true">${ICONS_CHAT.trash}</span> <span>Xóa hội thoại</span></button>` : ''}
        </div>
      </div>
    </form>

    <div id="guide-box">${loading('Đang tải danh mục câu hỏi trợ lý')}</div>
  </div>`;

  const chat = $('#chat');
  const pending = $('#pending');
  const form = $('#ask');
  const submit = form.querySelector('[type="submit"]');
  const input = $('#q');
  const heroContainer = $('#hero-container');

  const draw = () => {
    chat.innerHTML = history.join('');
    if (heroContainer) {
      heroContainer.innerHTML = history.length ? '' : renderHero();
    }
  };
  draw();

  let busy = false;
  const ask = async (q, domain) => {
    if (busy || !q || signal.aborted) return;
    busy = true;
    submit.disabled = true; input.disabled = true; form.setAttribute('aria-busy', 'true');
    history.push(userMsgHtml(q, domain));
    draw();
    chat.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const t0 = Date.now();
    const tick = () => {
      const s = Math.round((Date.now() - t0) / 1000);
      if (!signal.aborted) {
        pending.innerHTML = `
          <div class="typing-row">
            <div class="bot-avatar-box" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="3" y="8" width="18" height="12" rx="4"/><circle cx="9" cy="13" r="1.5" fill="currentColor"/><circle cx="15" cy="13" r="1.5" fill="currentColor"/><path d="M9 17h6"/></svg>
            </div>
            <div class="typing-bubble">
              <span class="kt-typing-dots"><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span></span>
              <span class="typing-text">${s > 3 ? `Đang tìm điều khoản và trích xuất căn cứ (${s}s)...` : 'Trợ lý đang phân tích câu hỏi...'}</span>
            </div>
          </div>
        `;
      }
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
    chat.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  $('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); $('#q').value = ''; ask(q); };

  app().addEventListener('click', (e) => {
    const c = e.target.closest('.chip-q');
    if (c) { ask(c.dataset.q); return; }
    const alt = e.target.closest('.alt-q');
    if (alt) { ask(alt.dataset.q, alt.dataset.domain); return; }
    
    // Copy button
    const copyBtn = e.target.closest('.copy-msg-btn');
    if (copyBtn) {
      const bubble = copyBtn.closest('.bot-bubble');
      const text = bubble ? bubble.querySelector('.bot-text')?.innerText || '' : '';
      if (text) {
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.classList.add('copied');
          const span = copyBtn.querySelector('span');
          if (span) span.textContent = 'Đã chép!';
          setTimeout(() => {
            copyBtn.classList.remove('copied');
            if (span) span.textContent = 'Sao chép';
          }, 2000);
        }).catch(() => {});
      }
      return;
    }

    if (e.target.closest('#clear')) {
      history = [];
      save();
      draw();
    }
  }, { signal });

  try {
    guideCache ||= await api('/api/chat/guide');
    if (signal.aborted) return;
    $('#guide-box').innerHTML = guideHtml(guideCache);
  } catch (err) {
    if (signal.aborted) return;
    $('#guide-box').innerHTML = notice('error', 'Không tải được hướng dẫn', err.message);
  }
}
