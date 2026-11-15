"""Single-page client and example questions for the governed demo."""

from secrets import token_urlsafe

from fastapi.responses import HTMLResponse

_DEMO_EXAMPLES = (
    ("Chỉ tiêu", "Doanh thu thuần", "Doanh thu thuần tháng 08/2026 là bao nhiêu?", "vi-VN"),
    ("Chỉ tiêu", "Biên lợi nhuận gộp", "What was the gross margin in August 2026?", "en-US"),
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
        "Chi phí nhà cung cấp lũy kế",
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
.result-body { padding: 19px; }
.answer { white-space: pre-wrap; overflow-wrap: anywhere; }
.placeholder { color: var(--muted); }
.meta { display: flex; flex-wrap: wrap; gap: 7px; margin: 13px 0 0; padding: 0; list-style: none; }
.meta li { padding: 5px 8px; border-radius: 5px; background: #edf4f2; font-size: .79rem; overflow-wrap: anywhere; }
.quick-prompt { color: var(--ink); font-size: .96rem; font-weight: 650; }
.quick-title { color: var(--muted); font-size: .8rem; }
.reply { border: 0; border-radius: 6px; color: #075447; background: #e6f3ee; padding: 8px 11px; font-size: .87rem; min-height: 38px; }
.reply.cancel { color: #465d62; background: #edf1f0; }
.quick {
  display: grid; gap: 10px; margin-top: 14px; padding: 14px;
  background: #f6f9f8; border: 1px solid var(--line); border-radius: 9px;
}
.choices { display: flex; flex-wrap: wrap; gap: 8px; max-height: 190px; overflow: auto; }
.clarification-form { flex-basis: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 7px; }
.clarification-form label { grid-column: 1 / -1; color: var(--muted); font-size: .82rem; }
.clarification-form textarea { min-height: 68px; font-size: .86rem; }
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
    <label class="persona-wrap">Vai trò
      <select id="persona">
        <option value="cfo_full">Giám đốc tài chính · Toàn quyền</option>
        <option value="branch_viewer">Người xem chi nhánh HCM · Giới hạn</option>
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
            <select id="locale"><option value="vi-VN">Tiếng Việt</option><option value="en-US">Tiếng Anh</option></select>
          </label>
          <div class="run-state" id="progress" hidden aria-live="polite">
            <span class="spinner" aria-hidden="true"></span><span>Đang truy vấn</span>
            <span id="elapsed" aria-hidden="true">0,0 giây</span>
          </div>
          <button class="run" type="submit" id="run"><span id="run-label">Truy vấn</span></button>
        </div>
      </form>
    </section>
    <section class="panel result-panel" aria-labelledby="answer-title">
      <div class="result-head">
        <h2 id="answer-title">Kết quả</h2><span class="status" id="status" hidden></span>
      </div>
      <div class="result-body" aria-live="polite">
        <p id="answer" class="answer placeholder">Nhập câu hỏi hoặc chọn một câu mẫu.</p>
        <ul class="meta" id="meta" hidden></ul>
        <div class="quick" id="quick" hidden aria-label="Làm rõ câu hỏi"></div>
      </div>
    </section>
    <section class="panel table-panel" id="data-panel" aria-labelledby="data-title" hidden>
      <div class="table-head"><h2 id="data-title">Bảng dữ liệu</h2><span class="table-count" id="table-count"></span></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Cuộn bảng dữ liệu">
        <table><thead id="table-head"></thead><tbody id="table-body"></tbody></table>
      </div>
    </section>
    <details class="panel drawer" id="drawer" hidden>
      <summary>Kiểm soát truy vấn và bằng chứng SQL</summary>
      <p>Mã theo dõi <span class="trace-value" id="trace-id"></span></p>
      <div class="drawer-grid" id="sql-plan" hidden>
        <div><h3>Câu lệnh chỉ đọc</h3><pre id="sql"></pre></div>
        <div><h3>Kế hoạch truy vấn</h3><pre id="plan"></pre></div>
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
  ready: ["Hoàn tất", "success"],
  needs_clarification: ["Cần bổ sung thông tin", "notice"],
  no_data: ["Không có dữ liệu", "info"],
  forbidden: ["Ngoài phạm vi quyền", "danger"],
  unsupported: ["Chưa hỗ trợ", "notice"],
  temporarily_unavailable: ["Tạm thời gián đoạn", "danger"],
  error: ["Chưa xử lý được", "danger"],
};
const metricLabels = new Map();
const dimensionLabels = {
  branch_code: "Chi nhánh",
  product_line: "Dòng sản phẩm",
  department_code: "Phòng ban",
  cost_category: "Khoản mục chi phí",
  partner_code: "Đối tác",
  segment: "Phân khúc",
  month: "Tháng",
  quarter: "Quý",
  year: "Năm",
  salesperson_code: "Nhân viên phụ trách",
  aging_bucket: "Nhóm tuổi nợ",
  transaction_id: "Mã giao dịch",
  component: "Thành phần",
  branch: "Chi nhánh",
  department: "Phòng ban",
  customer: "Khách hàng",
  vendor: "Nhà cung cấp",
  item: "Mặt hàng",
  account: "Tài khoản",
};
const friendlyErrors = {
  forbidden_metric: "Tài khoản hiện tại chưa được cấp quyền xem chỉ tiêu này.",
  forbidden: "Tài khoản hiện tại chưa được cấp quyền xem dữ liệu này.",
  unsupported_comparison: "Chưa thể so sánh hai kỳ trong một câu hỏi. Bạn có thể hỏi từng kỳ riêng.",
  incompatible_metrics: "Các chỉ tiêu này không thể tổng hợp cùng nhau. Hãy hỏi riêng từng chỉ tiêu.",
  unsupported_metric: "Chỉ tiêu này chưa được hỗ trợ. Hãy chọn một chỉ tiêu trong danh mục.",
  unsupported_data_source: "Chưa có dữ liệu để trả lời yêu cầu này.",
  unsupported_view: "Góc nhìn được yêu cầu chưa hỗ trợ cho chỉ tiêu này.",
  unsupported_request: "Câu hỏi này chưa thuộc phạm vi truy vấn tài chính được hỗ trợ.",
  invalid_request: "Mình chưa hiểu câu hỏi. Hãy viết lại và nêu rõ chỉ tiêu hoặc kỳ báo cáo.",
  retrieval_unavailable: "Hệ thống truy vấn đang tạm gián đoạn. Vui lòng thử lại sau.",
  clarification_unavailable: "Chưa thể tiếp tục phần làm rõ. Vui lòng gửi lại câu hỏi.",
  connection_error: "Chưa kết nối được với hệ thống. Vui lòng thử lại sau.",
  invalid_response: "Hệ thống chưa trả được kết quả. Vui lòng thử lại sau.",
};
const warningLabels = {
  partial_data_watermark: "Kỳ báo cáo chưa hoàn tất",
  ratio_undefined: "Không tính được tỷ lệ do thiếu dữ liệu hoặc mẫu số bằng 0",
  no_data_for_period: "Không có dữ liệu trong kỳ này",
  no_data_found: "Không tìm thấy dữ liệu phù hợp",
};
let active = null;
let clock = null;
let activeClarification = null;
const defaultQuestionPlaceholder = question.placeholder;

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
function setRunLabel(pendingClarification) {
  byId("run-label").textContent = pendingClarification ? "Hỏi câu mới" : "Truy vấn";
}
function resetResult(message) {
  byId("answer").textContent = message;
  byId("answer").classList.add("placeholder");
  for (const id of ["status", "meta", "quick", "data-panel", "drawer"]) byId(id).hidden = true;
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
  activeClarification = null;
  setRunLabel(false);
  question.placeholder = defaultQuestionPlaceholder;
  stopProgress();
  updateScope();
  resetResult("Chạy truy vấn để xem kết quả trong phạm vi persona hiện tại.");
});
function setExample(example, card) {
  activeClarification = null;
  setRunLabel(false);
  question.placeholder = defaultQuestionPlaceholder;
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
function displayUnit(unit) {
  return ({VND: "VNĐ", ratio: "lần", days: "ngày", count: "số lượng", mixed: "tùy thành phần"})[unit]
    ?? unit;
}
function renderTable(body) {
  const preview = body.evidence?.preview_table;
  const data = body.data;
  const columns = preview?.columns ?? data?.columns ?? [];
  const rows = preview?.sample_rows ?? data?.rows ?? [];
  if (!columns.length || !rows.length) return;
  const headers = node("tr");
  for (const col of columns) {
    const label = metricLabels.get(col.key) ?? dimensionLabels[col.key] ?? col.key.replaceAll("_", " ");
    const unit = displayUnit(col.unit);
    const th = node("th", unit ? `${label} (${unit})` : label);
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
    ["Chỉ tiêu", interpretation?.metric_ids?.map(id => metricLabels.get(id)).filter(Boolean).join(", ")],
    ["Kỳ", time?.as_of ?? (time?.start && `${time.start} → ${time.end}`)],
    ["Góc nhìn", ({mgmt: "Quản trị", tax: "Thuế"})[interpretation?.view]],
    ["Dữ liệu đến", body.provenance?.data_watermark],
    ["Lưu ý", (body.warnings ?? []).map(code => warningLabels[code]).filter(Boolean).join(" · ")],
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
function renderClarification(clarification, sent, sentLocale, continuation) {
  const slot = clarification?.slot_prompts?.[0];
  if (!clarification?.session_id || !slot) {
    activeClarification = null;
    setRunLabel(false);
    question.placeholder = defaultQuestionPlaceholder;
    return;
  }
  setRunLabel(true);
  activeClarification = {
    sessionId: clarification.session_id,
    originalQuestion: continuation?.originalQuestion ?? sent,
    locale: continuation?.locale ?? sentLocale,
    persona: persona.value,
    clarification,
  };

  const quick = byId("quick");
  quick.setAttribute("aria-label", "Câu hỏi cần làm rõ");
  quick.replaceChildren(
    node("p", "Cần làm rõ một thông tin", "quick-title"),
    node("p", slot.prompt, "quick-prompt"),
  );
  const choices = node("div", null, "choices");
  for (const choice of slot.choices ?? []) {
    const reply = node("button", choice.label, "reply");
    reply.type = "button";
    reply.addEventListener("click", () => { void submitClarification(choice.value); });
    choices.append(reply);
  }
  if (choices.childElementCount) quick.append(choices);
  if (slot.slot === "filters" && !(slot.choices ?? []).length) {
    quick.append(node(
      "p",
      "Mục lọc này chưa hỗ trợ diễn giải câu trả lời tự do. Hãy đặt câu hỏi mới và nêu rõ giá trị lọc.",
      "quick-prompt",
    ));
  } else {
    const replyForm = node("form", null, "clarification-form");
    const replyLabel = node("label", "Câu trả lời cho mục đang làm rõ");
    const replyInput = node("textarea");
    replyInput.id = "clarification-answer";
    replyLabel.htmlFor = replyInput.id;
    replyInput.required = true;
    replyInput.maxLength = 500;
    replyInput.setAttribute("aria-label", "Câu trả lời cho mục đang làm rõ");
    replyInput.placeholder = slot.prompt || "Nhập câu trả lời…";
    const sendReply = node("button", "Gửi câu trả lời", "reply");
    sendReply.type = "submit";
    replyForm.append(replyLabel, replyInput, sendReply);
    replyForm.addEventListener("submit", event => {
      event.preventDefault();
      void submitClarification(replyInput.value);
    });
    quick.append(replyForm);
  }
  const cancel = node("button", "Hủy và nhập câu hỏi khác", "reply cancel");
  cancel.type = "button";
  cancel.addEventListener("click", beginNewQuestion);
  quick.append(cancel);
  quick.hidden = false;
}
function beginNewQuestion() {
  activeClarification = null;
  setRunLabel(false);
  question.value = "";
  question.placeholder = defaultQuestionPlaceholder;
  resetResult("Nhập câu hỏi mới hoặc chọn một câu mẫu.");
  question.focus();
}
function friendlyErrorMessage(body) {
  const code = body.error?.code ?? body.reason_code;
  if (code && friendlyErrors[code]) return friendlyErrors[code];
  if (body.status === "forbidden") return friendlyErrors.forbidden;
  if (body.status === "unsupported") return friendlyErrors.unsupported_request;
  if (body.status === "temporarily_unavailable") return friendlyErrors.retrieval_unavailable;
  return "Chưa thể xử lý yêu cầu này. Vui lòng thử lại sau.";
}
function renderResult(body, sent, sentLocale, continuation) {
  const [label, tone] = statusText[body.status] ?? statusText.error;
  const badge = byId("status");
  badge.textContent = label;
  badge.dataset.tone = tone;
  badge.hidden = false;
  const answer = byId("answer");
  answer.classList.remove("placeholder");
  const clarificationError = continuation
    && body.error?.stage === "clarification"
    && body.error?.code === "invalid_request";
  const guidedSlot = body.clarification?.slot_prompts?.[0];
  const hasError = ["forbidden", "unsupported", "temporarily_unavailable", "error"].includes(body.status);
  answer.textContent = clarificationError
    ? "Mình chưa ghép được câu trả lời với mục đang làm rõ. Hãy chọn một phương án hoặc nhập lại câu trả lời."
    : hasError
      ? friendlyErrorMessage(body)
      : body.status === "needs_clarification" && guidedSlot
        ? "Chọn một phương án hoặc nhập câu trả lời bên dưới để tiếp tục."
        : body.answer || "Không có nội dung để hiển thị.";
  renderMeta(body);
  renderTable(body);
  const evidence = body.demo_evidence;
  byId("drawer").hidden = !evidence?.trace_id;
  byId("trace-id").textContent = evidence?.trace_id ?? "";
  byId("sql-plan").hidden = !evidence?.sql;
  byId("sql").textContent = evidence?.sql ?? "";
  byId("plan").textContent = evidence?.semantic_plan ? JSON.stringify(evidence.semantic_plan, null, 2) : "";
  if (body.status === "needs_clarification") {
    renderClarification(body.clarification, sent, sentLocale, continuation);
  } else if (continuation) {
    if (body.status === "error" || body.status === "temporarily_unavailable") {
      renderClarification(continuation.clarification, continuation.originalQuestion, continuation.locale, continuation);
    } else {
      activeClarification = null;
      setRunLabel(false);
    }
  }
}
async function sendQuery(sent, sentLocale, continuation) {
  if (continuation && continuation.persona !== persona.value) {
    activeClarification = null;
    return;
  }
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
        ...(continuation ? {session_id: continuation.sessionId} : {}),
        options: {
          include_table: true, include_evidence_preview: true,
          ...(!continuation ? {clarification_mode: "guided"} : {}),
        },
      }),
    });
    let body;
    try { body = await response.json(); }
    catch { body = {status: "error", error: {code: "invalid_response", message: "API không trả dữ liệu JSON."}}; }
    if (active === controller) renderResult(body, sent, sentLocale, continuation);
  } catch {
    if (active === controller) renderResult(
      {status: "error", error: {code: "connection_error", message: "Không kết nối được API."}},
      sent, sentLocale, continuation,
    );
  } finally {
    if (active === controller) {
      active = null;
      stopProgress();
    }
  }
}
async function submitClarification(reply = null) {
  const continuation = activeClarification;
  if (!continuation) return;
  const sent = typeof reply === "string" ? reply.trim() : byId("clarification-answer").value.trim();
  const sentLocale = continuation.locale;
  if (!sent) {
    byId("clarification-answer")?.reportValidity();
    return;
  }
  await sendQuery(sent, sentLocale, continuation);
}
async function submit() {
  const sent = question.value.trim();
  if (!sent || !byId("query-form").reportValidity()) {
    question.reportValidity();
    return;
  }
  activeClarification = null;
  setRunLabel(false);
  question.placeholder = defaultQuestionPlaceholder;
  await sendQuery(sent, locale.value, null);
}
byId("query-form").addEventListener("submit", event => { event.preventDefault(); void submit(); });
updateScope();

fetchJson("/health").then(health => {
  const model = node("span", "Mô hình · " + health.llm_model);
  const db = node("span", "Kho dữ liệu · Demo");
  byId("health").replaceChildren(model, db);
}).catch(() => { byId("health").textContent = "API chưa sẵn sàng"; });
fetchJson("/v1/demo-questions").then(renderExamples).catch(() => {
  byId("examples").textContent = "Không tải được câu hỏi mẫu.";
});
fetchJson("/v1/metrics").then(metrics => {
  byId("catalog-title").textContent = `Danh mục · ${metrics.length} chỉ tiêu có truy vấn`;
  for (const metric of metrics) {
    metricLabels.set(metric.metric_id, metric.name_vi);
    const item = node("li");
    const choose = node("button", metric.name_vi);
    choose.type = "button";
    choose.addEventListener("click", () => {
      const snapshot = metric.period_type === "snapshot";
      const tax = !metric.allowed_views.includes("mgmt");
      const when = locale.value === "en-US"
        ? snapshot ? "as of August 31, 2026" : "for August 2026"
        : snapshot ? "tính đến 31/08/2026" : "tháng 08/2026";
      const view = tax ? (locale.value === "en-US" ? " in the tax view" : " theo góc nhìn thuế") : "";
      const label = locale.value === "en-US" ? metric.name_en : metric.name_vi;
      question.value = locale.value === "en-US"
        ? `${label} ${when}${view}?`
        : `${label} ${when}${view} là bao nhiêu?`;
      question.focus();
    });
    item.append(choose);
    const unit = displayUnit(metric.unit);
    const views = metric.allowed_views.map(view => ({mgmt: "Quản trị", tax: "Thuế"})[view] ?? view);
    item.append(node("small", `${unit} · ${views.join(", ")}`));
    byId("metrics").append(item);
  }
}).catch(() => { byId("metrics").append(node("li", "Không tải được danh mục.")); });
</script>
</body>
</html>"""
