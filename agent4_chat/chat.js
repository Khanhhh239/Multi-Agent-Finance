"use strict";
// Agent 4 chat. Talks only to the portal (/api/agent4/...); the portal adds Agent 4's key, so the page never holds it.
(() => {
  const $ = (id) => document.getElementById(id);
  const SUGGESTIONS = [
    "Doanh thu thuần quý 3 năm 2026 là bao nhiêu?",
    "Lợi nhuận sau thuế tháng 8 năm 2026?",
    "Công nợ phải thu hiện tại?",
    "Tiền mặt cuối tháng 8 năm 2026?",
    "Doanh thu thuần theo tháng năm 2026",
  ];
  const STATUS = {
    ready: "Đã trả lời", needs_clarification: "Cần nói rõ hơn", unsupported: "Chưa hỗ trợ", forbidden: "Không có quyền",
    no_data: "Không có số liệu", temporarily_unavailable: "Tạm thời không trả lời được", error: "Lỗi",
  };

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children.flat(Infinity)) if (c !== null && c !== undefined && c !== false) node.append(c.nodeType ? c : String(c));
    return node;
  }

  const vnd = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });
  function cell(value, column) {
    if (value === null || value === undefined) return "";
    if (column.type === "decimal" || column.type === "integer") {
      const n = Number(value);
      return Number.isFinite(n) ? vnd.format(n) + (column.unit && column.unit !== "count" ? " " + column.unit : "") : value;
    }
    return value;
  }

  function table(data) {
    if (!data || !data.rows || !data.rows.length) return null;
    const cols = data.columns;
    return el("div", { class: "result" },
      el("table", {},
        el("thead", {}, el("tr", {}, cols.map((c) => el("th", {}, c.key)))),
        el("tbody", {}, data.rows.slice(0, 50).map((r) =>
          el("tr", {}, cols.map((c) => el("td", { class: c.type === "decimal" || c.type === "integer" ? "num" : "" }, cell(r[c.key], c))))))));
  }

  function source(res) {
    const p = res.provenance;
    const i = res.interpretation;
    if (!p && !i) return null;
    const rows = [];
    if (i) {
      rows.push(["Chỉ tiêu", i.metric_ids.join(", ")]);
      if (i.dimensions.length) rows.push(["Chiều", i.dimensions.join(", ")]);
      if (i.time) rows.push(["Thời gian", i.time.mode === "range" ? i.time.start + " đến " + i.time.end : i.time.as_of || "không giới hạn"]);
      if (i.view) rows.push(["Khung số liệu", i.view === "tax" ? "thuế" : "quản trị"]);
    }
    if (p) {
      rows.push(["Nguồn", p.source]);
      if (p.data_watermark) rows.push(["Dữ liệu đến", p.data_watermark]);
      rows.push(["Danh mục", p.catalog_hash.slice(0, 12)]);
    }
    return el("details", { class: "source" }, el("summary", {}, "Cách hiểu câu hỏi và nguồn"),
      el("dl", {}, rows.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])));
  }

  // Agent 4 writes raw amounts ("55792824000.00 VND", "khung mgmt"); show them the way an accountant reads them.
  function readable(text) {
    return String(text)
      .replace(/(\d+(?:\.\d+)?) VND/g, (_, n) => vnd.format(Math.round(Number(n))) + " đồng")
      .replace(/khung mgmt/g, "khung quản trị").replace(/khung tax/g, "khung thuế")
      .replace(/(\d{4})-(\d{2})-(\d{2})/g, "$3/$2/$1").replace(/–/g, " đến ");
  }

  function botMessage(res) {
    const warnings = (res.warnings || []).filter(Boolean);
    return [
      el("span", { class: "tag " + res.status }, STATUS[res.status] || res.status),
      el("div", { class: "answer" }, readable(res.answer || (res.error && res.error.message) || "Không có câu trả lời.")),
      table(res.data),
      res.data && res.data.truncated ? el("p", { class: "source" }, "Chỉ hiện 50 dòng đầu.") : null,
      source(res),
      warnings.length ? el("ul", { class: "warnings" }, warnings.map((w) => el("li", {}, w))) : null,
    ];
  }

  async function ask(question) {
    const thread = $("thread");
    thread.append(el("li", { class: "msg user" }, question));
    const bot = el("li", { class: "msg bot pending" }, el("div", { class: "answer" }, "Đang tra số liệu"));
    thread.append(bot);
    bot.scrollIntoView({ block: "end" });
    $("send").disabled = true;
    try {
      const r = await fetch("/api/agent4/query", {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Platform": "1" },
        body: JSON.stringify({ question }),
      });
      const res = await r.json();
      bot.replaceChildren(...botMessage(r.ok ? res : { status: "error", answer: res.error }).filter(Boolean));
    } catch (err) {
      bot.replaceChildren(...botMessage({ status: "error", answer: "Không kết nối được portal: " + err.message }).filter(Boolean));
    } finally {
      bot.classList.remove("pending");
      $("send").disabled = false;
      bot.scrollIntoView({ block: "end" });
    }
  }

  async function loadMetrics() {
    try {
      const res = await fetch("/api/agent4/metrics", { cache: "no-store" }).then((r) => r.json());
      const list = Array.isArray(res) ? res : res.items || res.metrics || [];
      if (!list.length) throw new Error(res.error || "Danh mục trống.");
      $("metric-count").textContent = list.length + " chỉ tiêu.";
      $("metrics").replaceChildren(...list.slice(0, 40).map((m) =>
        el("li", {}, m.label || m.name || m.metric_id || m.id, m.unit ? el("span", {}, " (" + m.unit + ")") : null)));
    } catch (err) {
      $("metric-count").textContent = "Chưa đọc được danh mục: " + err.message;
    }
  }

  $("suggest").replaceChildren(...SUGGESTIONS.map((q) => el("li", {}, el("button", { type: "button", onclick: () => ask(q) }, q))));
  const box = $("question");
  box.addEventListener("input", () => {
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, 160) + "px";
  });
  box.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("composer").requestSubmit();
    }
  });
  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = box.value.trim();
    if (!q || $("send").disabled) return;
    box.value = "";
    box.style.height = "auto";
    ask(q);
  });
  loadMetrics();
})();
