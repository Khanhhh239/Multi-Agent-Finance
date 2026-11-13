"""Single-page client and example questions for the governed demo."""

from secrets import token_urlsafe

from fastapi.responses import HTMLResponse

_DEMO_EXAMPLES = (
    ("Chỉ tiêu", "Doanh thu thuần", "Doanh thu thuần tháng 08/2026 là bao nhiêu?", "vi-VN"),
    ("Chỉ tiêu", "Gross margin", "What was the gross margin in August 2026?", "en-US"),
    (
        "Chỉ tiêu",
        "Số dư tiền",
        "Số dư tiền và tương đương tiền tính đến cuối năm 2025 (31/12/2025) là bao nhiêu?",
        "vi-VN",
    ),
    (
        "Chỉ tiêu",
        "Nhiều chỉ tiêu",
        "Cho biết doanh thu thuần, giá vốn hàng bán và lợi nhuận gộp trong tháng 08/2026.",
        "vi-VN",
    ),
    (
        "Phân tích",
        "Chi phí theo bộ phận",
        "Cơ cấu chi phí hoạt động theo bộ phận trong Quý 2/2026 như thế nào?",
        "vi-VN",
    ),
    (
        "Phân tích",
        "Xu hướng doanh thu",
        "Xu hướng doanh thu thuần theo tháng từ tháng 01/2026 đến tháng 08/2026 như thế nào?",
        "vi-VN",
    ),
    (
        "Góc nhìn và bộ lọc",
        "Góc nhìn thuế",
        "Lợi nhuận ròng tháng 08/2026 theo khung thuế (tax) là bao nhiêu?",
        "vi-VN",
    ),
    (
        "Góc nhìn và bộ lọc",
        "Chi phí nhà cung cấp",
        "Tổng chi phí hoạt động phát sinh với nhà cung cấp NCC-MK-DG trong tháng 09/2026 là bao nhiêu?",
        "vi-VN",
    ),
    (
        "Góc nhìn và bộ lọc",
        "Vendor expense YTD",
        "What was the total operating expense for vendor NCC-MK-DG in FY 2026 (up to September 2026)?",
        "en-US",
    ),
    ("Làm rõ và phân quyền", "Thiếu kỳ báo cáo", "Doanh thu thuần là bao nhiêu?", "vi-VN"),
    (
        "Làm rõ và phân quyền",
        "Chỉ tiêu ngoài quyền HCM",
        "Chi phí nhân sự (labor cost) tháng 08/2026 là bao nhiêu?",
        "vi-VN",
    ),
    (
        "Làm rõ và phân quyền",
        "Chỉ tiêu thử nghiệm",
        "Chỉ số experimental_cash_burn trong tháng 08/2026 là bao nhiêu?",
        "vi-VN",
    ),
)
DEMO_QUESTIONS = [
    {
        "id": f"D-{index:02d}",
        "category": category,
        "title": title,
        "question": question,
        "locale": locale,
        **({"persona": "branch_viewer"} if index == 11 else {}),
    }
    for index, (category, title, question, locale) in enumerate(_DEMO_EXAMPLES, 1)
]


def demo_page() -> HTMLResponse:
    nonce = token_urlsafe(18)
    return HTMLResponse(
        _PAGE.replace("__NONCE__", nonce),
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


_PAGE = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Truy vấn dữ liệu tài chính tổng hợp theo quyền và kiểm tra bằng chứng.">
<title>Agent 4 · Truy vấn tài chính</title>
<style nonce="__NONCE__">
:root {
  color-scheme: light;
  --ink: #182b32; --muted: #556c74; --line: #d9e3e3;
  --accent: #086857; --accent-dark: #074a3f; --surface: #fff; --canvas: #f1f5f4;
  font: 15px/1.5 "Inter", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; color: var(--ink); background: var(--canvas); }
[hidden] { display: none !important; }
button, select, textarea { font: inherit; }
button, summary, select { cursor: pointer; }
:focus-visible { outline: 3px solid #159d86; outline-offset: 3px; }
.topbar { color: #f6fffc; background: #102d31; }
.top-inner {
  max-width: 1420px; margin: auto; min-height: 88px; padding: 15px 28px;
  display: flex; align-items: center; gap: 26px; justify-content: space-between;
}
.brand { display: flex; gap: 12px; align-items: center; flex-shrink: 0; }
.mark {
  display: grid; place-items: center; width: 40px; height: 40px; border-radius: 11px;
  background: #a9ebd6; color: #102d31; font-weight: 820; letter-spacing: -.08em;
}
.brand strong { display: block; font-size: 1.17rem; letter-spacing: -.035em; }
.brand span:last-child { display: block; color: #b7d4d0; font-size: .81rem; }
.health { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; }
.health span {
  font-size: .78rem; color: #d4eeea; background: #ffffff0d; border: 1px solid #ffffff2b;
  border-radius: 6px; padding: 5px 9px; overflow-wrap: anywhere;
}
.persona-wrap { display: grid; gap: 4px; font-size: .78rem; color: #b7d4d0; }
.persona-wrap select {
  max-width: 100%; color: #fff; background: #1c3e43; border: 1px solid #456368;
  border-radius: 7px; padding: 8px; font-size: .83rem;
}
.layout {
  max-width: 1420px; margin: auto; padding: 28px;
  display: grid; grid-template-columns: minmax(235px, 306px) minmax(0, 1fr); gap: 24px;
}
.sidebar, .workspace { min-width: 0; }
.sidebar { display: grid; gap: 16px; align-content: start; }
.workspace { display: grid; gap: 16px; align-content: start; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 13px; }
.sidebar .panel { padding: 17px; }
h1, h2, h3, p { margin: 0; }
h1 { font-size: clamp(1.42rem, 3vw, 1.85rem); letter-spacing: -.048em; line-height: 1.2; }
h2 { font-size: 1.09rem; letter-spacing: -.025em; }
h3 { font-size: .82rem; color: var(--muted); }
.examples { display: grid; gap: 14px; margin-top: 14px; }
.example-group { display: grid; gap: 5px; }
.example {
  border: 0; background: transparent; text-align: left; border-radius: 6px;
  color: var(--ink); width: 100%; padding: 5px 7px; display: flex; gap: 9px;
  font-size: .89rem; align-items: baseline;
}
.example:hover, .example[aria-current="true"] { background: #e6f3ee; color: var(--accent-dark); }
.example-code, .trace-value {
  font: .75rem/1.5 "IBM Plex Mono", ui-monospace, monospace;
  color: var(--muted);
}
summary { font-weight: 700; color: var(--ink); }
.metrics-list { padding: 0; list-style: none; margin: 12px 0 0; max-height: 340px; overflow: auto; }
.metrics-list li { padding: 8px 0; border-top: 1px solid var(--line); font-size: .86rem; }
.metrics-list small { display: block; overflow-wrap: anywhere; color: var(--muted); }
.query-panel { padding: 24px; border-top: 3px solid var(--accent); }
.scope { color: var(--muted); margin: 6px 0 18px; font-size: .87rem; }
textarea {
  display: block; resize: vertical; width: 100%; min-height: 101px; padding: 12px 14px;
  border: 1px solid #c2d3d2; border-radius: 8px; background: #fafcfc; color: var(--ink);
}
textarea::placeholder { color: #607579; }
.form-actions { display: flex; gap: 10px; justify-content: space-between; align-items: center; margin-top: 12px; }
.locale-control { font-size: .82rem; color: var(--muted); }
.locale-control select { margin-left: 5px; background: #fff; border: 1px solid var(--line); border-radius: 5px; padding: 6px; color: var(--ink); }
.run {
  color: #fff; background: var(--accent); border: 0; border-radius: 7px;
  padding: 9px 17px; font-weight: 700; min-height: 40px;
}
.run:hover { background: var(--accent-dark); }
.run:disabled { opacity: .65; cursor: progress; }
.run-state { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: .83rem; }
.spinner {
  height: 15px; width: 15px; border: 2px solid #c2dbd4; border-top-color: var(--accent);
  border-radius: 50%; animation: spin .75s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
.result-panel { overflow: hidden; }
.result-head {
  padding: 13px 19px; border-bottom: 1px solid var(--line); background: #f8fbfa;
  display: flex; flex-wrap: wrap; gap: 9px; align-items: center; justify-content: space-between;
}
.result-head h2 { margin-right: auto; }
.status {
  display: inline-block; padding: 4px 8px; border-radius: 5px;
  font-size: .74rem; font-weight: 750; background: #e8efef; color: #3b575a;
}
.status[data-tone="success"] { background: #dff3e8; color: #145740; }
.status[data-tone="notice"] { background: #fff0d6; color: #754700; }
.status[data-tone="danger"] { background: #fce8e5; color: #8a2f27; }
.status[data-tone="info"] { background: #e3edf9; color: #304e79; }
.reason { color: var(--muted); font: .75rem/1.5 "IBM Plex Mono", monospace; overflow-wrap: anywhere; }
.result-body { padding: 19px; }
.answer { white-space: pre-wrap; overflow-wrap: anywhere; }
.placeholder { color: var(--muted); }
.meta { display: flex; flex-wrap: wrap; gap: 7px; margin: 13px 0 0; padding: 0; list-style: none; }
.meta li { padding: 5px 8px; border-radius: 5px; background: #edf4f2; font-size: .79rem; overflow-wrap: anywhere; }
.reply { border: 0; border-radius: 6px; color: #075447; background: #e6f3ee; padding: 6px 9px; font-size: .83rem; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 13px; }
.table-panel { padding: 17px 19px; }
.table-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-bottom: 10px; }
.table-count { color: var(--muted); font-size: .81rem; }
.table-scroll { overflow: auto; border: 1px solid var(--line); border-radius: 7px; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 11px; text-align: left; }
th { background: #edf4f2; white-space: nowrap; }
td.amount { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: 0; }
.drawer { padding: 15px 19px; }
.drawer p { margin: 11px 0; color: var(--muted); font-size: .83rem; overflow-wrap: anywhere; }
.drawer-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
pre {
  background: #122c32; color: #e5f5ef; padding: 12px; border-radius: 7px; margin: 5px 0 0;
  max-height: 360px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere;
  font: .78rem/1.55 "IBM Plex Mono", ui-monospace, monospace;
}
@media (max-width: 920px) {
  .top-inner { flex-wrap: wrap; gap: 12px 18px; }
  .health { order: 3; flex-basis: 100%; }
}
@media (max-width: 680px) {
  .top-inner, .layout { padding: 15px; }
  .layout { grid-template-columns: minmax(0, 1fr); gap: 15px; }
  .workspace { grid-row: 1; }
  .query-panel { padding: 16px; }
  .drawer-grid { grid-template-columns: minmax(0, 1fr); }
  .top-inner { justify-content: flex-start; }
  .form-actions { flex-wrap: wrap; }
}
</style>
</head>
<body>
<header class="topbar">
  <div class="top-inner">
    <div class="brand">
      <span class="mark" aria-hidden="true">A4</span>
      <div><strong>Agent 4</strong><span>Truy vấn tài chính · Dữ liệu tổng hợp</span></div>
    </div>
    <div class="health" id="health" aria-live="polite"><span>Đang kết nối API</span></div>
    <label class="persona-wrap">Persona
      <select id="persona">
        <option value="cfo_full">CFO / Finance Lead (Full Access)</option>
        <option value="branch_viewer">HCM Branch Viewer (Restricted RBAC)</option>
      </select>
    </label>
  </div>
</header>
<main class="layout">
  <aside class="sidebar" aria-label="Tham chiếu demo">
    <section class="panel">
      <h2>Câu hỏi mẫu</h2>
      <div class="examples" id="examples"></div>
    </section>
    <details class="panel" id="catalog">
      <summary id="catalog-title">Danh mục chỉ tiêu</summary>
      <ul class="metrics-list" id="metrics"></ul>
    </details>
  </aside>
  <div class="workspace">
    <section class="panel query-panel" aria-labelledby="query-title">
      <h1 id="query-title">Truy vấn tài chính</h1>
      <p class="scope" id="scope"></p>
      <form id="query-form">
        <textarea id="question" aria-label="Câu hỏi tài chính" maxlength="500" required
          placeholder="Ví dụ: Doanh thu thuần tháng 08/2026 là bao nhiêu?"></textarea>
        <div class="form-actions">
          <label class="locale-control">Ngôn ngữ
            <select id="locale"><option value="vi-VN">Tiếng Việt</option><option value="en-US">English</option></select>
          </label>
          <div class="run-state" id="progress" hidden aria-live="polite">
            <span class="spinner" aria-hidden="true"></span><span>Đang truy vấn</span>
            <span id="elapsed" aria-hidden="true">0,0 giây</span>
          </div>
          <button class="run" type="submit" id="run">Truy vấn <span lang="en">(Run Query)</span></button>
        </div>
      </form>
    </section>
    <section class="panel result-panel" aria-labelledby="answer-title">
      <div class="result-head">
        <h2 id="answer-title">Kết quả</h2><span class="status" id="status" hidden></span>
        <span class="reason" id="reason" hidden></span>
      </div>
      <div class="result-body" aria-live="polite">
        <p id="answer" class="answer placeholder">Nhập câu hỏi hoặc chọn một câu mẫu.</p>
        <ul class="meta" id="meta" hidden></ul>
        <div class="quick" id="quick" hidden aria-label="Bổ sung kỳ báo cáo"></div>
      </div>
    </section>
    <section class="panel table-panel" id="data-panel" aria-labelledby="data-title" hidden>
      <div class="table-head"><h2 id="data-title">Bảng dữ liệu</h2><span class="table-count" id="table-count"></span></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Cuộn bảng dữ liệu">
        <table><thead id="table-head"></thead><tbody id="table-body"></tbody></table>
      </div>
    </section>
    <details class="panel drawer" id="drawer" hidden>
      <summary>Governance &amp; bằng chứng SQL</summary>
      <p>Trace ID <span class="trace-value" id="trace-id"></span></p>
      <div class="drawer-grid" id="sql-plan" hidden>
        <div><h3>SQL chỉ đọc</h3><pre id="sql"></pre></div>
        <div><h3>Semantic plan</h3><pre id="plan"></pre></div>
      </div>
    </details>
  </div>
</main>
<script nonce="__NONCE__">
"use strict";
const byId = id => document.getElementById(id);
const persona = byId("persona");
const question = byId("question");
const locale = byId("locale");
const run = byId("run");
const statusText = {
  ready: ["OK", "success"],
  needs_clarification: ["NEEDS CLARIFICATION", "notice"],
  no_data: ["NO DATA", "info"],
  forbidden: ["UNAUTHORIZED", "danger"],
  unsupported: ["UNSUPPORTED", "notice"],
  temporarily_unavailable: ["ERROR", "danger"],
  error: ["ERROR", "danger"],
};
const quickReplies = [
  ["trong tháng 08/2026", "in August 2026"],
  ["trong Quý 2/2026", "in Q2 2026"],
  ["tính đến 31/12/2025", "as of December 31, 2025"],
];
const metricLabels = new Map();
let active = null;
let clock = null;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
async function fetchJson(url) {
  const response = await fetch(url, {cache: "no-store"});
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}
function updateScope() {
  byId("scope").textContent = persona.value === "branch_viewer"
    ? "Phạm vi HCM · chỉ góc nhìn quản trị · 4 ID chỉ tiêu được cấp quyền"
    : "Toàn doanh nghiệp demo · góc nhìn quản trị và thuế";
}
function resetResult(message) {
  byId("answer").textContent = message;
  byId("answer").classList.add("placeholder");
  for (const id of ["status", "reason", "meta", "quick", "data-panel", "drawer"]) byId(id).hidden = true;
  byId("drawer").open = false;
  for (const id of ["sql", "plan", "trace-id", "table-head", "table-body", "meta", "quick"]) {
    byId(id).replaceChildren();
  }
}
function stopProgress() {
  clearInterval(clock);
  run.disabled = false;
  byId("progress").hidden = true;
  byId("query-form").removeAttribute("aria-busy");
}
persona.addEventListener("change", () => {
  active?.abort();
  active = null;
  stopProgress();
  updateScope();
  resetResult("Chạy truy vấn để xem kết quả trong phạm vi persona hiện tại.");
});
function setExample(example, card) {
  for (const selected of document.querySelectorAll('.example[aria-current="true"]')) {
    selected.removeAttribute("aria-current");
  }
  card.setAttribute("aria-current", "true");
  if (example.persona) {
    persona.value = example.persona;
    updateScope();
  }
  question.value = example.question;
  locale.value = example.locale;
  void submit();
}
function renderExamples(examples) {
  const groups = new Map();
  for (const example of examples) {
    if (!groups.has(example.category)) {
      const group = node("div", null, "example-group");
      group.append(node("h3", example.category));
      byId("examples").append(group);
      groups.set(example.category, group);
    }
    const card = node("button", null, "example");
    card.type = "button";
    card.title = example.question;
    card.append(node("span", example.id, "example-code"), node("span", example.title));
    card.addEventListener("click", () => setExample(example, card));
    groups.get(example.category).append(card);
  }
}
function formatCell(value, column) {
  if (value == null) return "—";
  const text = String(value);
  if (column.type !== "decimal" || !/^-?\d+(\.\d+)?$/.test(text)) return text;
  const [whole, fraction] = text.split(".");
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (fraction ? "," + fraction : "");
}
function renderTable(body) {
  const preview = body.evidence?.preview_table;
  const data = body.data;
  const columns = preview?.columns ?? data?.columns ?? [];
  const rows = preview?.sample_rows ?? data?.rows ?? [];
  if (!columns.length || !rows.length) return;
  const headers = node("tr");
  for (const col of columns) {
    const label = metricLabels.get(col.key) ?? col.key;
    const th = node("th", col.unit ? `${label} (${col.unit})` : label);
    th.scope = "col";
    headers.append(th);
  }
  byId("table-head").replaceChildren(headers);
  const fragment = document.createDocumentFragment();
  for (const row of rows) {
    const line = node("tr");
    for (const col of columns) {
      line.append(node("td", formatCell(row[col.key], col), col.type === "decimal" ? "amount" : ""));
    }
    fragment.append(line);
  }
  byId("table-body").replaceChildren(fragment);
  const total = preview?.total_row_count ?? data?.row_count ?? rows.length;
  byId("table-count").textContent = rows.length === total ? `${total} dòng` : `${rows.length} / ${total} dòng`;
  byId("data-panel").hidden = false;
}
function renderMeta(body) {
  const interpretation = body.interpretation;
  const time = interpretation?.time;
  const entries = [
    ["Chỉ tiêu", interpretation?.metric_ids?.join(", ")],
    ["Kỳ", time?.as_of ?? (time?.start && `${time.start} → ${time.end}`)],
    ["View", interpretation?.view],
    ["Dữ liệu đến", body.provenance?.data_watermark],
    ["Cảnh báo", body.warnings?.join(", ")],
  ];
  const meta = byId("meta");
  meta.replaceChildren();
  for (const [label, value] of entries) {
    if (!value) continue;
    const item = node("li");
    item.append(node("strong", label + " · "), document.createTextNode(value));
    meta.append(item);
  }
  meta.hidden = !meta.children.length;
}
function renderResult(body, httpStatus, sent, sentLocale) {
  const [label, tone] = statusText[body.status] ?? statusText.error;
  const badge = byId("status");
  badge.textContent = `${label} (${httpStatus})`;
  badge.dataset.tone = tone;
  badge.hidden = false;
  const code = body.error?.code ?? body.reason_code;
  byId("reason").textContent = code ?? "";
  byId("reason").hidden = !code;
  const answer = byId("answer");
  answer.classList.remove("placeholder");
  answer.textContent = body.answer || body.error?.message || "Không có kết quả để hiển thị.";
  renderMeta(body);
  renderTable(body);
  const evidence = body.demo_evidence;
  byId("drawer").hidden = !evidence?.trace_id;
  byId("trace-id").textContent = evidence?.trace_id ?? "";
  byId("sql-plan").hidden = !evidence?.sql;
  byId("sql").textContent = evidence?.sql ?? "";
  byId("plan").textContent = evidence?.semantic_plan ? JSON.stringify(evidence.semantic_plan, null, 2) : "";
  if (body.status === "needs_clarification") {
    const quick = byId("quick");
    quick.replaceChildren();
    for (const [vi, en] of quickReplies) {
      const reply = node("button", vi, "reply");
      reply.type = "button";
      reply.addEventListener("click", () => {
        question.value = sent.replace(/[.?!]+$/, "") + " " + (sentLocale === "en-US" ? en : vi);
        locale.value = sentLocale;
        void submit();
      });
      quick.append(reply);
    }
    quick.hidden = false;
  }
}
async function submit() {
  const sent = question.value.trim();
  const sentLocale = locale.value;
  if (!sent || !byId("query-form").reportValidity()) return;
  active?.abort();
  clearInterval(clock);
  const controller = new AbortController();
  active = controller;
  resetResult("Đang kiểm tra phạm vi và xử lý câu hỏi…");
  run.disabled = true;
  byId("query-form").setAttribute("aria-busy", "true");
  byId("progress").hidden = false;
  const started = performance.now();
  function tick() {
    byId("elapsed").textContent = ((performance.now() - started) / 1000).toFixed(1).replace(".", ",") + " giây";
  }
  tick();
  clock = setInterval(tick, 100);
  try {
    const response = await fetch("/v1/query", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Demo-Persona": persona.value},
      signal: controller.signal,
      body: JSON.stringify({
        api_version: "v1", question: sent, locale: sentLocale,
        options: {include_table: true, include_evidence_preview: true},
      }),
    });
    let body;
    try { body = await response.json(); }
    catch { body = {status: "error", error: {code: "invalid_response", message: "API không trả dữ liệu JSON."}}; }
    if (active === controller) renderResult(body, response.status, sent, sentLocale);
  } catch {
    if (active === controller) renderResult(
      {status: "error", error: {code: "connection_error", message: "Không kết nối được API."}},
      503, sent, sentLocale,
    );
  } finally {
    if (active === controller) {
      active = null;
      stopProgress();
    }
  }
}
byId("query-form").addEventListener("submit", event => { event.preventDefault(); void submit(); });
updateScope();

fetchJson("/health").then(health => {
  const model = node("span", "LLM · " + health.llm_model);
  const db = node("span", "DB · " + health.db_path.split(/[\\/]/).pop());
  db.title = health.db_path;
  byId("health").replaceChildren(model, db);
}).catch(() => { byId("health").textContent = "API chưa sẵn sàng"; });
fetchJson("/v1/demo-questions").then(renderExamples).catch(() => {
  byId("examples").textContent = "Không tải được câu hỏi mẫu.";
});
fetchJson("/v1/metrics").then(metrics => {
  byId("catalog-title").textContent = `Danh mục · ${metrics.length} chỉ tiêu đã xác minh`;
  for (const metric of metrics) {
    metricLabels.set(metric.metric_id, metric.name_vi);
    const item = node("li");
    item.append(node("strong", metric.name_vi));
    item.append(node("small", `${metric.metric_id} · ${metric.unit} · ${metric.allowed_views.join(", ")}`));
    byId("metrics").append(item);
  }
}).catch(() => { byId("metrics").append(node("li", "Không tải được danh mục.")); });
</script>
</body>
</html>"""
