"use strict";
// Sổ Son — Agent 4 CFO Two-Book Chat.
// Talks only to the portal (/api/agent4/...); exact BigInt/Decimal VND formatting; zero inline styles.
(() => {
  const $ = (id) => document.getElementById(id);
  const runtimeConfig = window.__MAF_RUNTIME_CONFIG__ || {};
  const apiBaseUrl = String(runtimeConfig.apiBaseUrl || "").replace(/\/+$/, "");
  const apiUrl = (path) => {
    const value = String(path || "");
    if (/^https?:\/\//i.test(value)) return value;
    return apiBaseUrl + (value.startsWith("/") ? value : "/" + value);
  };
  const SESSION_STORAGE_KEY = "soson.agent4.session_id";

  const SUGGESTIONS = [
    "Doanh thu thuần quý 3 năm 2026 là bao nhiêu?",
    "Lợi nhuận sau thuế quý 3 năm 2026 theo sổ quản trị?",
    "Tiền mặt cuối tháng 8 năm 2026?",
    "Công nợ phải thu hiện tại?",
    "Doanh thu thuần theo tháng năm 2026",
    "Doanh thu thuần là bao nhiêu?",
  ];

  const FOLLOWUP_SUGGESTIONS = [
    "Còn theo sổ thuế thì sao?",
    "So sánh hai sổ quản trị và thuế trong cùng kỳ?",
    "Chi tiết theo từng chi nhánh?",
  ];

  const STATUS = {
    ready: "Đã trả lời",
    needs_clarification: "Cần làm rõ thêm",
    clarification_needed: "Cần làm rõ thêm",
    unsupported: "Chưa hỗ trợ",
    forbidden: "Ngoài phạm vi quyền",
    no_data: "Không có số liệu",
    temporarily_unavailable: "Tạm thời gián đoạn",
    error: "Lỗi truy vấn",
  };

  const LABELS = {
    net_revenue: "Doanh thu thuần",
    gross_revenue: "Doanh thu gộp",
    revenue: "Doanh thu",
    net_profit: "Lợi nhuận sau thuế",
    profit_before_tax: "Lợi nhuận trước thuế",
    gross_profit: "Lợi nhuận gộp",
    gross_margin: "Biên lợi nhuận gộp",
    gross_margin_pct: "Biên lợi nhuận gộp (%)",
    net_margin_pct: "Biên lợi nhuận ròng (%)",
    ebitda: "EBITDA",
    cash: "Tiền và tương đương tiền",
    cash_end: "Tiền mặt cuối kỳ",
    cash_balance: "Số dư tiền",
    accounts_receivable: "Công nợ phải thu",
    ar_balance: "Phải thu khách hàng",
    accounts_payable: "Công nợ phải trả",
    ap_balance: "Phải trả nhà cung cấp",
    selling_expenses: "Chi phí bán hàng",
    admin_expenses: "Chi phí quản lý doanh nghiệp",
    operating_expenses: "Chi phí hoạt động",
    expense: "Chi phí",
    cogs: "Giá vốn hàng bán",
    vat_position: "Vị thế thuế GTGT",
    cit_expense: "Chi phí thuế TNDN",
    branch_code: "Chi nhánh",
    branch: "Chi nhánh",
    department_code: "Phòng ban",
    department: "Phòng ban",
    partner_code: "Đối tác",
    customer: "Khách hàng",
    vendor: "Nhà cung cấp",
    product_line: "Dòng sản phẩm",
    cost_category: "Khoản mục chi phí",
    month: "Tháng",
    period: "Kỳ",
    quarter: "Quý",
    year: "Năm",
    value: "Giá trị",
    amount: "Số tiền",
    mgmt_value: "Sổ quản trị",
    tax_value: "Sổ thuế",
    delta: "Chênh lệch",
    diff: "Chênh lệch",
    variance: "Chênh lệch",
    as_of: "Tại ngày",
    date: "Ngày",
  };

  const metricNames = {};
  const label = (key) => LABELS[key] || metricNames[key] || String(key).replace(/_/g, " ");

  const WARNINGS = [
    [/DEMO DATA\s*[—-]\s*NOT REAL FINANCIAL RESULTS/i, "Dữ liệu kho doanh nghiệp mô phỏng để kiểm thử nghiệp vụ."],
  ];

  const ERROR_TEXT = {
    unsupported_metric: "Chưa có chỉ tiêu nào khớp với câu hỏi này. Hãy hỏi về doanh thu, lợi nhuận, công nợ, tiền mặt, thuế hoặc chi phí.",
    unsupported_comparison: "Hiện chưa hỗ trợ gộp hai kỳ khác nhau trong một câu đơn. Bạn có thể hỏi từng kỳ hoặc hỏi nối tiếp ở lượt sau.",
    forbidden: "Tài khoản hiện tại không có quyền truy cập chỉ tiêu hoặc phạm vi này.",
    forbidden_metric: "Tài khoản hiện tại không có quyền xem chỉ tiêu này.",
    retrieval_unavailable: "Dịch vụ truy hồi chỉ tiêu tạm thời bận. Hãy thử lại sau ít giây.",
    invalid_request: "Câu hỏi cần diễn đạt rõ hơn về chỉ tiêu và kỳ báo cáo (ví dụ: Quý 3/2026 hoặc Tháng 08/2026).",
  };

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children.flat(Infinity)) {
      if (c !== null && c !== undefined && c !== false) {
        node.append(c.nodeType ? c : String(c));
      }
    }
    return node;
  }

  // ------------------------------------------------------------------ Exact Decimal VND Arithmetic
  function groupDigitsVi(bigIntVal) {
    const s = (bigIntVal < 0n ? -bigIntVal : bigIntVal).toString();
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function parseExactDecimal(raw) {
    if (raw === null || raw === undefined || raw === "") return null;
    let str;
    if (typeof raw === "bigint") {
      str = raw.toString();
    } else if (typeof raw === "number") {
      if (!Number.isFinite(raw)) return null;
      // Avoid scientific notation for large VND numbers within safe integer range
      str = Number.isInteger(raw) ? raw.toFixed(0) : raw.toFixed(4);
    } else {
      str = String(raw).trim();
    }
    if (!str) return null;
    str = str.replace(/\u2212/g, "-").replace(/\s+/g, "");
    const match = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(str);
    if (!match) return null;

    let negative = match[1] === "-";
    let whole = BigInt(match[2]);
    const fracRaw = (match[3] || "").padEnd(3, "0");
    let cents = Number(fracRaw.slice(0, 2));
    const thirdDigit = Number(fracRaw[2] || "0");
    if (thirdDigit >= 5) {
      cents += 1;
      if (cents >= 100) {
        whole += 1n;
        cents = 0;
      }
    }
    if (whole === 0n && cents === 0) negative = false;
    return { negative, whole, cents };
  }

  function formatVnd(raw, options = {}) {
    const parsed = parseExactDecimal(raw);
    if (!parsed) return String(raw ?? "");
    let { negative, whole, cents } = parsed;
    if (options.roundToInt) {
      if (cents >= 50) whole += 1n;
      cents = 0;
      if (whole === 0n) negative = false;
    }
    const sign = negative ? "-" : "";
    const intPart = groupDigitsVi(whole);
    const fracPart = !options.roundToInt && cents > 0
      ? "," + String(cents).padStart(2, "0").replace(/0+$/, "")
      : "";
    const unitSuffix = options.withUnit ? " đồng" : "";
    return sign + intPart + fracPart + unitSuffix;
  }

  // Short spoken Vietnamese summary: preserves negative sign explicitly ("âm 666,4 triệu đồng").
  function approxVnd(raw) {
    const parsed = parseExactDecimal(raw);
    if (!parsed) return "";
    const absVnd = parsed.whole + (parsed.cents >= 50 ? 1n : 0n);
    if (absVnd < 1000000n) return "";

    let tenths;
    let unit;
    if (absVnd >= 1000000000000n) {
      tenths = (absVnd * 10n + 500000000000n) / 1000000000000n;
      unit = "nghìn tỷ đồng";
    } else if (absVnd >= 1000000000n) {
      tenths = (absVnd * 10n + 500000000n) / 1000000000n;
      unit = "tỷ đồng";
      if (tenths >= 10000n) {
        tenths = (tenths + 500n) / 1000n;
        unit = "nghìn tỷ đồng";
      }
    } else {
      tenths = (absVnd * 10n + 500000n) / 1000000n;
      unit = "triệu đồng";
      if (tenths >= 10000n) {
        tenths = (tenths + 500n) / 1000n;
        unit = "tỷ đồng";
      }
    }

    const wholePart = groupDigitsVi(tenths / 10n);
    const rem = tenths % 10n;
    const numStr = rem === 0n ? wholePart : wholePart + "," + rem.toString();
    const prefix = parsed.negative ? "âm " : "";
    return prefix + numStr + " " + unit;
  }
  const shortVnd = approxVnd;

  const nonVndDec = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

  function readable(text) {
    return String(text ?? "")
      .replace(/([+-−]?\d+(?:\.\d+)?)\s*(?:VND|VNĐ)\b/g, (_, rawNum) =>
        formatVnd(rawNum, { withUnit: true, roundToInt: true })
      )
      .replace(
        /(?:(\bâm\s+)|([−-]))?(\d{1,3}(?:\.\d{3}){2,}(?:,\d+)?)\s*đồng(?!\s*\(khoảng\b)/gi,
        (match, amWord, minusSign, groupedDigits) => {
          const isNeg = Boolean(amWord || minusSign);
          const normalized = (isNeg ? "-" : "") + groupedDigits.replace(/\./g, "").replace(",", ".");
          const shortText = approxVnd(normalized);
          return shortText ? match + " (khoảng " + shortText + ")" : match;
        }
      )
      .replace(/\bkhung mgmt\b/gi, "Sổ quản trị")
      .replace(/\bkhung tax\b/gi, "Sổ thuế")
      .replace(/(\d{4})-(\d{2})-(\d{2})/g, "$3/$2/$1")
      .replace(/(\d{2}\/\d{2}\/\d{4})\s*–\s*(\d{2}\/\d{2}\/\d{4})/g, "$1 đến $2");
  }

  // ------------------------------------------------------------------ Session Management
  function generateSessionId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID().replace(/-/g, "").toLowerCase();
    }
    const bytes = new Uint8Array(16);
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
      crypto.getRandomValues(bytes);
    } else {
      for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function loadOrCreateSessionId() {
    try {
      const existing = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (existing && /^[0-9a-z_-]{8,64}$/i.test(existing)) return existing;
    } catch (e) { /* private mode */ }
    const created = generateSessionId();
    saveSessionId(created);
    return created;
  }

  function saveSessionId(id) {
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, id);
    } catch (e) { /* private mode */ }
  }

  let sessionId = loadOrCreateSessionId();
  let conversationVersion = 0;
  let activeClarification = null;
  const conversations = new Map();
  let currentConversation = generateSessionId();

  function renderSessionHeader() {
    const badge = $("session-badge");
    if (badge) {
      const shortId = String(sessionId).replace(/[^0-9a-z]/gi, "").slice(0, 6);
      badge.textContent = "Phiên #" + (shortId || "mới");
      badge.dataset.sessionId = sessionId;
    }
    const bar = $("clarification-bar");
    if (bar) {
      bar.hidden = !activeClarification;
    }
  }

  function clearActiveClarification() {
    activeClarification = null;
    renderSessionHeader();
  }

  function buildIntroElement() {
    return el("li", { class: "intro", id: "chat-intro" },
      el("div", { class: "intro-badges" },
        el("span", { class: "data-badge" }, "Một sổ cái · Hai góc nhìn"),
        el("span", { class: "data-badge gov" }, "Số liệu có dẫn chứng")
      ),
      el("h1", {}, "Trợ lý hỏi đáp"),
      el("p", {},
        "Đặt câu hỏi bằng tiếng Việt về doanh thu, lợi nhuận, công nợ, dòng tiền hay chi phí theo ",
        el("strong", {}, "Sổ quản trị"),
        " hoặc ",
        el("strong", {}, "Sổ thuế"),
        ". Hỗ trợ hỏi nối tiếp trong cùng phiên (ví dụ: ",
        el("em", {}, "“Còn theo sổ thuế thì sao?”"),
        ", ",
        el("em", {}, "“Chi tiết theo từng chi nhánh?”"),
        ") kèm bằng chứng đối chiếu minh bạch."
      )
    );
  }

  // ------------------------------------------------------------------ Follow-up context
  // The governed pipeline answers each question on its own: a session only carries a pending clarification.
  // A short follow-up ("Còn theo sổ thuế thì sao?", "Chi tiết theo từng chi nhánh?") is therefore rewritten here
  // into a complete question from the last answered one before it is sent.
  let lastAnswered = null;

  function saveConversation() {
    const current = conversations.get(currentConversation);
    if (!current) return;
    current.sessionId = sessionId;
    current.clarification = activeClarification;
    current.lastAnswered = lastAnswered;
    current.nodes = Array.from($("thread").children);
  }

  function updateConversationList() {
    const list = $("session-list");
    if (!list) return;
    list.replaceChildren(...Array.from(conversations, ([id, item]) => {
      const option = el("option", { value: id }, item.title);
      option.selected = id === currentConversation;
      return option;
    }));
  }

  function openConversation(id) {
    if (!conversations.has(id) || id === currentConversation) return;
    conversationVersion += 1;
    const pending = $("thread").querySelector(".msg.pending");
    if (pending) pending.replaceChildren(el("div", { class: "answer" }, "Yêu cầu đã dừng khi chuyển hội thoại. Hãy gửi lại câu hỏi."));
    pending?.classList.remove("pending");
    saveConversation();
    currentConversation = id;
    const item = conversations.get(id);
    sessionId = item.sessionId;
    activeClarification = item.clarification;
    lastAnswered = item.lastAnswered;
    saveSessionId(sessionId);
    $("thread").replaceChildren(...item.nodes);
    $("send").disabled = false;
    $("question").value = "";
    syncComposerRows($("question"));
    renderSessionHeader();
    updateConversationList();
    $("thread").scrollTop = $("thread").scrollHeight;
  }

  function newConversation() {
    const id = generateSessionId();
    conversations.set(id, { title: "Hội thoại " + (conversations.size + 1), sessionId: generateSessionId(),
      clarification: null, lastAnswered: null, nodes: [buildIntroElement()] });
    openConversation(id);
  }
  const FOLLOW_RE = /^(?:vậy |thế )?(?:còn|nếu)\s+(.+?)(?:\s+thì sao)?\s*\??$/i;
  const DETAIL_RE = /^(?:chi tiết|tách|phân)\s+(?:theo\s+)?(.+?)\s*\??$/i;
  const COMPARE_RE = /^so sánh hai sổ/i;
  const MODIFIER_RE = /(sổ|chi nhánh|tháng|quý|năm|khu vực|sản phẩm|đối tác|phân khúc|kênh)/i;

  function baseQuestion(q) {
    return String(q || "")
      .replace(/\s*\((?:theo\s+)?sổ\s+(?:thuế|quản trị)\)/gi, "")
      .replace(/\s+theo\s+(?:sổ\s+)?(?:thuế|quản trị)(?:\s*\(v_\w+\))?/gi, "")
      .replace(/\s+theo\s+(?:từng\s+)?(?:chi nhánh|tháng|quý|khu vực|dòng sản phẩm|sản phẩm|đối tác|phân khúc)/gi, "")
      .replace(/\s*(?:là\s+)?bao nhiêu\s*\??\s*$/i, "")
      .replace(/\s*\?+\s*$/, "")
      .trim();
  }

  function composeFollowUp(q) {
    if (!lastAnswered) return null;
    const base = baseQuestion(lastAnswered.question);
    if (!base) return null;
    if (COMPARE_RE.test(q)) {
      return { pair: [base + " theo sổ quản trị là bao nhiêu?", base + " theo sổ thuế là bao nhiêu?"] };
    }
    let m = q.match(FOLLOW_RE);
    if (m && MODIFIER_RE.test(m[1])) {
      const mod = /^theo\b/i.test(m[1].trim()) ? m[1].trim() : "theo " + m[1].trim();
      return { text: base + " " + mod + " là bao nhiêu?" };
    }
    m = q.match(DETAIL_RE);
    if (m && MODIFIER_RE.test(m[1])) {
      const view = (String(lastAnswered.question).match(/theo\s+sổ\s+(?:thuế|quản trị)/i) || [""])[0];
      return { text: (base + " theo " + m[1].trim().replace(/^theo\s+/i, "") + (view ? " " + view : "")).trim() };
    }
    return null;
  }

  function resetConversation() {
    conversationVersion += 1;
    if ($("send")) $("send").disabled = false;
    sessionId = generateSessionId();
    saveSessionId(sessionId);
    activeClarification = null;
    lastAnswered = null;
    renderSessionHeader();
    const thread = $("thread");
    if (thread) {
      thread.replaceChildren(buildIntroElement());
    }
    saveConversation();
    const box = $("question");
    if (box) {
      box.value = "";
      syncComposerRows(box);
      box.focus();
    }
  }

  // ------------------------------------------------------------------ Governance & Provenance Detection
  function detectAccountingView(res) {
    const interp = res?.interpretation || {};
    const prov = res?.provenance || {};
    const cols = (res?.data?.columns || []).map((c) => String(c.key || "").toLowerCase());
    const rawViews = Array.isArray(interp.views)
      ? interp.views
      : Array.isArray(prov.views)
        ? prov.views
        : [];
    const viewStr = String(interp.view || res?.view || res?.accounting_view || prov.view || prov.source || "").toLowerCase();

    const hasDualCols = cols.some((k) => k.includes("mgmt")) && cols.some((k) => k.includes("tax"));
    const hasBothViews = (rawViews.includes("mgmt") && rawViews.includes("tax"))
      || /\b(both|dual|compare|mgmt_vs_tax|two_book|hai_so)\b/.test(viewStr)
      || (viewStr.includes("mgmt") && viewStr.includes("tax"))
      || hasDualCols;

    if (hasBothViews) {
      return { key: "dual", label: "So sánh hai sổ", css: "view-dual" };
    }
    if (viewStr === "tax" || viewStr === "v_tax" || rawViews[0] === "tax") {
      return { key: "tax", label: "Sổ thuế", css: "view-tax" };
    }
    if (viewStr === "mgmt" || viewStr === "v_mgmt" || rawViews[0] === "mgmt") {
      return { key: "mgmt", label: "Sổ quản trị", css: "view-mgmt" };
    }
    return null;
  }

  function detectProvenanceMode(res) {
    const prov = res?.provenance || {};
    const warnings = (res?.warnings || []).map((w) => String(w));
    const modeStr = String(
      prov.mode || prov.execution_mode || prov.retrieval_mode || res?.execution_mode || ""
    ).toLowerCase();
    const sourceStr = String(prov.source || "").toLowerCase();

    const isLexicalDegraded = Boolean(prov.degraded || res?.degraded)
      || /lexical|degraded|fallback|offline|regex/.test(modeStr)
      || (sourceStr === "synthetic_duckdb" && !prov.query_fingerprint)
      || warnings.some((w) => /lexical|degraded|fallback|offline/i.test(w))
      || Boolean(res?.demo_evidence?.recovery_reason);

    if (isLexicalDegraded) {
      return {
        key: "lexical",
        label: "Tra cứu danh mục",
        css: "prov-lexical",
        detail: "Đối chiếu danh mục chỉ tiêu",
      };
    }
    if (prov.query_fingerprint || res?.demo_evidence?.sql || res?.evidence || (res?.status === "ready" && (prov.catalog_hash || prov.source))) {
      const fp = prov.query_fingerprint ? " · #" + String(prov.query_fingerprint).slice(0, 8) : "";
      return {
        key: "sql",
        label: "Số liệu đã đối chiếu",
        css: "prov-sql",
        detail: "Đã đối chiếu với nguồn dữ liệu",
      };
    }
    return null;
  }

  // ------------------------------------------------------------------ KPI Cards & Table Rendering
  function isDeltaKey(key) {
    return /(delta|diff|variance|chenh_lech|tang_giam|change|gap)/i.test(String(key || ""));
  }

  function isProfitOrCashKey(key) {
    return /(profit|loss|margin|ebit|cash|income|loi_nhuan|dong_tien|tien_mat|vat_position)/i.test(String(key || ""));
  }

  function formatColumnValue(value, column) {
    if (value === null || value === undefined) return { text: "—", short: "", negative: false };
    const unit = column.unit || "";
    const parsed = parseExactDecimal(value);
    if (parsed) {
      const isVnd = unit === "VND" || unit === "VNĐ";
      const numText = isVnd
        ? formatVnd(value, { roundToInt: parsed.cents === 0 })
        : nonVndDec.format(Number(value));
      const unitSuffix = unit && unit !== "count" ? " " + (unit === "VND" ? "VNĐ" : unit) : "";
      return {
        text: numText + unitSuffix,
        short: isVnd ? approxVnd(value) : "",
        negative: parsed.negative,
      };
    }
    const n = Number(value);
    if (Number.isFinite(n)) {
      const unitSuffix = unit && unit !== "count" ? " " + unit : "";
      return {
        text: nonVndDec.format(n) + unitSuffix,
        short: unit === "VND" ? approxVnd(n) : "",
        negative: n < 0,
      };
    }
    return { text: String(value), short: "", negative: false };
  }

  function renderMetricCards(data) {
    if (!data || !Array.isArray(data.rows) || data.rows.length !== 1) return null;
    const cols = (data.columns || []).filter((c) => c.type === "decimal" || c.type === "integer");
    if (!cols.length) return null;
    const row = data.rows[0];
    const cards = cols.map((col) => {
      const raw = row[col.key];
      if (raw === null || raw === undefined) return null;
      const formatted = formatColumnValue(raw, col);
      const showDelta = isDeltaKey(col.key);
      const showProfitCash = isProfitOrCashKey(col.key);
      let badge = null;
      if (formatted.negative && (showDelta || showProfitCash || col.unit === "VND")) {
        const badgeText = showDelta ? "▼ Chênh lệch âm" : "▼ Số âm / Lỗ kỳ";
        badge = el("span", { class: "delta-badge is-negative" }, badgeText);
      } else if (!formatted.negative && showDelta && parseExactDecimal(raw)?.whole > 0n) {
        badge = el("span", { class: "delta-badge is-positive" }, "▲ Chênh lệch dương");
      }

      const cardClass = "kpi-card" + (formatted.negative ? " is-negative" : showDelta ? " is-positive" : "");
      return el("div", { class: cardClass },
        el("span", { class: "kpi-label" }, label(col.key)),
        el("strong", { class: "kpi-value" + (formatted.negative ? " is-negative" : "") }, formatted.text),
        (formatted.short || badge)
          ? el("div", { class: "kpi-sub-row" },
              badge,
              formatted.short
                ? el("span", { class: "kpi-approx" + (formatted.negative ? " is-negative" : "") }, formatted.short)
                : null
            )
          : null
      );
    }).filter(Boolean);

    return cards.length ? el("div", { class: "kpi-strip" }, cards) : null;
  }

  function cell(value, column) {
    if (value === null || value === undefined) return { content: "", negative: false };
    if (column.type === "decimal" || column.type === "integer") {
      const formatted = formatColumnValue(value, column);
      const mainSpan = el("span", { class: "cell-num" + (formatted.negative ? " is-negative" : "") }, formatted.text);
      const deltaBadge = isDeltaKey(column.key) && formatted.text !== "—"
        ? el("span", { class: "delta-badge " + (formatted.negative ? "is-negative" : "is-positive") }, formatted.negative ? "▼" : "▲")
        : null;
      const shortNode = formatted.short
        ? el("small", { class: "short" + (formatted.negative ? " is-negative" : "") }, formatted.short)
        : null;
      return {
        content: [deltaBadge ? [deltaBadge, " "] : null, mainSpan, shortNode],
        negative: formatted.negative,
      };
    }
    return { content: String(value), negative: false };
  }

  function table(data) {
    if (!data || !data.rows || !data.rows.length) return null;
    const cols = data.columns || [];
    return el("div", { class: "result" },
      el("table", {},
        el("thead", {}, el("tr", {}, cols.map((c) =>
          el("th", { class: c.type === "decimal" || c.type === "integer" ? "num" : "" }, label(c.key))
        ))),
        el("tbody", {}, data.rows.slice(0, 50).map((r) =>
          el("tr", {}, cols.map((c) => {
            const isNum = c.type === "decimal" || c.type === "integer";
            const rendered = cell(r[c.key], c);
            const cls = (isNum ? "num" : "") + (rendered.negative ? " is-negative" : "");
            return el("td", { class: cls.trim() }, rendered.content);
          }))
        ))
      )
    );
  }

  function source(res) {
    const p = res.provenance;
    const i = res.interpretation;
    const sqlText = res.demo_evidence?.sql || p?.sql || null;
    if (!p && !i && !sqlText) return null;

    const viewBadge = detectAccountingView(res);
    const provBadge = detectProvenanceMode(res);
    const rows = [];

    if (i) {
      if (Array.isArray(i.metric_ids) && i.metric_ids.length) {
        rows.push(["Chỉ tiêu", i.metric_ids.map(label).join(", ")]);
      }
      if (Array.isArray(i.dimensions) && i.dimensions.length) {
        rows.push(["Chiều phân tích", i.dimensions.map(label).join(", ")]);
      }
      if (i.time) {
        const timeStr = i.time.mode === "range"
          ? readable(i.time.start + "–" + i.time.end)
          : readable(i.time.as_of || "Không giới hạn");
        rows.push(["Kỳ số liệu", timeStr]);
      }
    }
    if (viewBadge) {
      rows.push(["Khung sổ kế toán", viewBadge.label]);
    }

    if (p) {
      const srcMap = {
        mgmt: "Sổ quản trị",
        v_mgmt: "Sổ quản trị",
        tax: "Sổ thuế",
        v_tax: "Sổ thuế",
        synthetic_duckdb: "Kho dữ liệu doanh nghiệp",
      };
      if (p.source) {
        rows.push(["Nguồn truy vấn", srcMap[p.source] || String(p.source).replace(/_/g, " ")]);
      }
      if (p.data_watermark) rows.push(["Dữ liệu cập nhật đến", readable(p.data_watermark)]);
    }

    return el("details", { class: "source" },
      el("summary", {}, "Kiểm tra nguồn số liệu"),
      el("dl", {}, rows.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
      null
    );
  }

  // ------------------------------------------------------------------ Interactive Clarification & Follow-up Chips
  function normalizeChipItem(item, isGuidedSlot = false) {
    if (!item) return null;
    if (typeof item === "string") {
      const trimmed = item.trim();
      return trimmed ? { label: trimmed, sendValue: trimmed, displayText: trimmed, isGuidedSlot } : null;
    }
    if (typeof item === "object") {
      const choiceId = item.choice_id ?? item.id ?? item.value ?? null;
      const sendValue = String(item.value ?? item.query ?? item.question ?? item.id ?? item.label ?? "").trim();
      const chipLabel = String(item.label ?? item.title ?? item.text ?? sendValue).trim();
      if (!sendValue || !chipLabel) return null;
      return {
        label: chipLabel,
        sendValue,
        displayText: chipLabel,
        choiceId: choiceId !== null ? String(choiceId) : null,
        isGuidedSlot,
      };
    }
    return null;
  }

  function extractClarificationSpec(res, lastQuestion) {
    const isClarifyStatus = res?.status === "needs_clarification" || res?.status === "clarification_needed";
    const clar = res?.clarification;
    const guidedSessionId = typeof clar?.session_id === "string" && clar.session_id ? clar.session_id : null;
    const items = [];
    let promptTitle = "Chọn nhanh thông tin cần làm rõ:";

    if (Array.isArray(clar?.slot_prompts) && clar.slot_prompts.length) {
      const firstSlot = clar.slot_prompts[0];
      if (firstSlot.prompt) promptTitle = firstSlot.prompt;
      for (const c of firstSlot.choices || []) {
        const norm = normalizeChipItem(c, Boolean(guidedSessionId));
        if (norm) items.push(norm);
      }
    }

    const directChoices = clar?.choices || clar?.options || res?.choices || res?.clarification_options || res?.options;
    if (!items.length && Array.isArray(directChoices)) {
      for (const c of directChoices) {
        const norm = normalizeChipItem(c, Boolean(guidedSessionId));
        if (norm) items.push(norm);
      }
    }

    // Smart fallback chips when backend asks for clarification in prose without a choices array
    if (isClarifyStatus && !items.length) {
      const text = String(res?.answer || clar?.question_for_user || "").toLowerCase();
      const slots = Array.isArray(clar?.unresolved_slots) ? clar.unresolved_slots : [];
      const baseQ = String(lastQuestion || "").replace(/[?.!]+$/, "").trim();

      if (slots.includes("view") || /quản trị|sổ thuế|góc nhìn|khung/.test(text)) {
        items.push(
          { label: "Sổ quản trị", sendValue: guidedSessionId ? "mgmt" : (baseQ ? baseQ + " theo sổ quản trị" : "Theo sổ quản trị"), displayText: "Theo Sổ quản trị", isGuidedSlot: Boolean(guidedSessionId) },
          { label: "Sổ thuế", sendValue: guidedSessionId ? "tax" : (baseQ ? baseQ + " theo sổ thuế" : "Theo sổ thuế"), displayText: "Theo Sổ thuế", isGuidedSlot: Boolean(guidedSessionId) }
        );
      } else if (slots.includes("metric") && /lợi nhuận|profit/.test(text + " " + baseQ.toLowerCase())) {
        items.push(
          { label: "Lợi nhuận sau thuế", sendValue: guidedSessionId ? "net_profit" : "Lợi nhuận sau thuế quý 3 năm 2026?", displayText: "Lợi nhuận sau thuế", isGuidedSlot: Boolean(guidedSessionId) },
          { label: "Lợi nhuận gộp", sendValue: guidedSessionId ? "gross_profit" : "Lợi nhuận gộp quý 3 năm 2026?", displayText: "Lợi nhuận gộp", isGuidedSlot: Boolean(guidedSessionId) }
        );
      } else if (slots.includes("time") || /kỳ|thời gian|tháng|quý|năm|ngày/.test(text)) {
        const periods = [
          ["Tháng 08/2026", "2026-08", "tháng 08/2026"],
          ["Quý 3/2026", "Q3 2026", "quý 3 năm 2026"],
          ["Năm 2026", "2026", "năm 2026"],
          ["Năm 2025", "2025", "năm 2025"],
        ];
        for (const [lbl, slotVal, suffix] of periods) {
          items.push({
            label: lbl,
            sendValue: guidedSessionId ? slotVal : (baseQ ? baseQ + " " + suffix + "?" : lbl),
            displayText: guidedSessionId ? lbl : (baseQ ? baseQ + " " + suffix + "?" : lbl),
            isGuidedSlot: Boolean(guidedSessionId),
          });
        }
      }
    }

    if (!isClarifyStatus && !items.length) return null;
    return { guidedSessionId, promptTitle, items };
  }

  function extractFollowUpItems(res) {
    const rawList = res?.follow_up_suggestions || res?.follow_ups || res?.suggested_questions;
    if (Array.isArray(rawList) && rawList.length) {
      return rawList.map((item) => normalizeChipItem(item, false)).filter(Boolean);
    }
    if (res?.status !== "ready") return [];
    const viewInfo = detectAccountingView(res);
    const dims = res?.interpretation?.dimensions || [];
    const contextual = [];
    if (viewInfo?.key === "mgmt") {
      contextual.push("Còn theo sổ thuế thì sao?");
    } else if (viewInfo?.key === "tax") {
      contextual.push("Còn theo sổ quản trị thì sao?");
    }
    if (!dims.includes("branch_code") && !dims.includes("branch")) {
      contextual.push("Chi tiết theo từng chi nhánh?");
    }
    return contextual.slice(0, 3).map((q) => normalizeChipItem(q, false)).filter(Boolean);
  }

  function renderChipsPanel(res, lastQuestion) {
    const clarSpec = extractClarificationSpec(res, lastQuestion);
    if (clarSpec && clarSpec.items.length) {
      return el("div", { class: "chip-panel is-clarification", role: "group", "aria-label": "Tùy chọn làm rõ câu hỏi" },
        el("p", { class: "chip-panel-title" }, clarSpec.promptTitle),
        el("div", { class: "chip-row" },
          clarSpec.items.map((item) =>
            el("button", {
              type: "button",
              class: "quick-chip is-clarify",
              onclick: () => {
                ask(item.sendValue, {
                  displayQuestion: item.displayText,
                  clarificationSessionId: clarSpec.guidedSessionId,
                  selectedChoiceId: item.choiceId || null,
                });
              },
            }, item.label)
          )
        )
      );
    }

    const followUps = extractFollowUpItems(res);
    if (followUps.length) {
      return el("div", { class: "chip-panel", role: "group", "aria-label": "Gợi ý hỏi tiếp" },
        el("p", { class: "chip-panel-title" }, "Hỏi tiếp nhanh trong cùng phiên:"),
        el("div", { class: "chip-row" },
          followUps.map((item) =>
            el("button", {
              type: "button",
              class: "quick-chip",
              onclick: () => ask(item.sendValue, { displayQuestion: item.displayText }),
            }, item.label)
          )
        )
      );
    }
    return null;
  }

  function errorText(error) {
    if (!error) return "";
    if (typeof error === "string") return error;
    if (ERROR_TEXT[error.code]) return ERROR_TEXT[error.code];
    if (error.stage === "llm_metric_selection") {
      return "Mô hình chưa chọn được chỉ tiêu phù hợp. Hãy nêu rõ tên chỉ tiêu và kỳ báo cáo.";
    }
    return error.message || "Không trả lời được câu hỏi này.";
  }

  function botMessage(res, lastQuestion) {
    const warnings = (res.warnings || []).filter(Boolean);
    const statusKey = res.status || "error";
    const viewBadge = detectAccountingView(res);
    const provBadge = detectProvenanceMode(res);

    const metaBar = el("div", { class: "msg-meta-bar" },
      el("span", { class: "tag " + statusKey }, STATUS[statusKey] || statusKey),
      viewBadge ? el("span", { class: "gov-badge " + viewBadge.css }, viewBadge.label) : null,
      provBadge ? el("span", { class: "gov-badge " + provBadge.css, title: provBadge.detail }, provBadge.label) : null
    );

    const answerStr = res.answer || res.clarification?.question_for_user || errorText(res.error) || "Không có câu trả lời.";

    return [
      metaBar,
      el("div", { class: "answer" }, readable(answerStr)),
      renderMetricCards(res.data),
      table(res.data),
      res.data && res.data.truncated ? el("p", { class: "source" }, "Chỉ hiển thị 50 dòng đầu tiên.") : null,
      renderChipsPanel(res, lastQuestion),
      source(res),
      warnings.length
        ? el("ul", { class: "warnings" }, warnings.map((w) =>
            el("li", {},
              ({
                partial_data_watermark: "Kỳ báo cáo chưa khóa sổ hoàn tất; số liệu có thể cập nhật thêm.",
                ratio_undefined: "Không tính được tỷ lệ do mẫu số bằng 0 hoặc chưa phát sinh dữ liệu.",
              })[w] || WARNINGS.reduce((t, [re, vi]) => t.replace(re, vi), String(w))
            )
          ))
        : null,
    ].filter(Boolean);
  }

  // ------------------------------------------------------------------ Query Execution
  async function postAgent4Query(question, targetSessionId, isClarificationTurn, selectedChoiceId = null) {
    const body = {
      question,
      ...(targetSessionId ? { session_id: targetSessionId } : {}),
      ...(selectedChoiceId ? { selected_choice_id: selectedChoiceId } : {}),
      options: {
        include_table: true,
        explain_metrics: true,
        ...(isClarificationTurn ? {} : { clarification_mode: "guided" }),
      },
    };
    const r = await fetch(apiUrl("/api/agent4/query"), {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Platform": "1" },
      body: JSON.stringify(body),
    });
    const res = await r.json().catch(() => ({ status: "error", error: "Phản hồi JSON không hợp lệ." }));
    return { ok: r.ok, statusHttp: r.status, res };
  }

  async function ask(question, opts = {}) {
    const trimmed = String(question || "").trim();
    if (!trimmed) return;
    const sendBtn = $("send");
    if (sendBtn && sendBtn.disabled) return;

    const requestVersion = conversationVersion;
    const displayQuestion = opts.displayQuestion || trimmed;
    const conversation = conversations.get(currentConversation);
    if (conversation && !conversation.named) {
      conversation.title = displayQuestion.slice(0, 55);
      conversation.named = true;
      updateConversationList();
    }
    const isClarificationTurn = Boolean(opts.clarificationSessionId || activeClarification);
    const effectiveSessionId = opts.clarificationSessionId || activeClarification?.sessionId || sessionId;

    const followUp = isClarificationTurn || opts.composed ? null : composeFollowUp(trimmed);
    if (followUp?.pair) {
      await ask(followUp.pair[0], { displayQuestion: displayQuestion + " (Sổ quản trị)", composed: true });
      if (requestVersion !== conversationVersion) return;
      await ask(followUp.pair[1], { displayQuestion: displayQuestion + " (Sổ thuế)", composed: true });
      return;
    }
    const sendText = followUp?.text || trimmed;
    const originalQuestion = activeClarification?.originalQuestion || null;

    const thread = $("thread");
    if (thread) {
      thread.append(el("li", { class: "msg user" }, displayQuestion));
    }
    const bot = el("li", { class: "msg bot pending" }, el("div", { class: "answer" }, "Đang tra cứu và đối chiếu số liệu…"));
    if (thread) {
      thread.append(bot);
      bot.scrollIntoView({ block: "end" });
    }
    if (sendBtn) sendBtn.disabled = true;

    try {
      let { ok, res } = await postAgent4Query(sendText, effectiveSessionId, isClarificationTurn, opts.selectedChoiceId || null);

      if (requestVersion !== conversationVersion) return;

      // Resilient fallback if an un-upgraded backend treats session_id strictly as single-use clarification token
      if (
        !isClarificationTurn &&
        effectiveSessionId &&
        res?.error?.stage === "clarification" &&
        res?.error?.code === "invalid_request"
      ) {
        const retry = await postAgent4Query(sendText, null, false, null);
        if (requestVersion !== conversationVersion) return;
        ok = retry.ok;
        res = retry.res;
      }

      if (typeof res?.session_id === "string" && res.session_id) {
        sessionId = res.session_id;
        saveSessionId(sessionId);
      }

      const isClarifyNeeded = res?.status === "needs_clarification" || res?.status === "clarification_needed";
      if (isClarifyNeeded && res?.clarification?.session_id) {
        activeClarification = {
          sessionId: res.clarification.session_id,
          originalQuestion: activeClarification?.originalQuestion || displayQuestion,
        };
      } else {
        activeClarification = null;
      }
      renderSessionHeader();

      const payloadToRender = ok || res?.api_version === "v1"
        ? res
        : { status: "error", answer: errorText(res?.error) || "Yêu cầu không thành công." };
      bot.replaceChildren(...botMessage(payloadToRender, displayQuestion));
      if (followUp?.text) {
        bot.prepend(el("div", { class: "followup-note" }, "Hiểu theo ngữ cảnh: “" + sendText + "”"));
      }
      if (res?.status === "ready") {
        const answered = isClarificationTurn ? originalQuestion : sendText;
        if (answered) lastAnswered = { question: answered };
      }
    } catch (err) {
      if (requestVersion !== conversationVersion) return;
      bot.replaceChildren(...botMessage({ status: "error", answer: "Không kết nối được máy chủ Portal: " + err.message }, displayQuestion));
    } finally {
      if (requestVersion !== conversationVersion) return;
      bot.classList.remove("pending");
      if (sendBtn) sendBtn.disabled = false;
      bot.scrollIntoView({ block: "end" });
    }
  }

  async function loadMetrics() {
    const countEl = $("metric-count");
    const listEl = $("metrics");
    if (!countEl || !listEl) return;
    try {
      const res = await fetch(apiUrl("/api/agent4/metrics"), { cache: "no-store" }).then((r) => r.json());
      const list = Array.isArray(res) ? res : res.items || res.metrics || [];
      if (!list.length) throw new Error(res.error || "Danh mục trống.");
      for (const m of list) {
        const id = m.metric_id || m.id;
        const name = m.name_vi || m.label || m.name;
        if (id && name && name !== id) metricNames[id] = name;
      }
      countEl.textContent = list.length + " chỉ tiêu được cấp quyền.";
      listEl.replaceChildren(...list.slice(0, 50).map((m) => {
        const name = m.name_vi || m.label || m.name || m.metric_id || m.id;
        const snapshot = m.period_type === "snapshot";
        const sampleQ = snapshot
          ? name + " tính đến 30/09/2026 là bao nhiêu?"
          : name + " quý 3 năm 2026 là bao nhiêu?";
        return el("li", {},
          el("button", {
            type: "button",
            class: "metric-pick",
            title: "Nhấn để điền câu hỏi mẫu cho chỉ tiêu này",
            onclick: () => {
              const box = $("question");
              if (!box) return;
              clearActiveClarification();
              box.value = sampleQ;
              syncComposerRows(box);
              box.focus();
            },
          },
            name,
            m.unit ? el("span", {}, " (" + (m.unit === "VND" ? "VNĐ" : m.unit) + ")") : null
          )
        );
      }));
    } catch (err) {
      countEl.textContent = "Chưa đọc được danh mục: " + err.message;
    }
  }

  // Zero-inline-style textarea auto-sizing (strict CSP safe)
  function syncComposerRows(box) {
    if (!box) return;
    const text = box.value || "";
    const lineBreaks = text.split("\n").length;
    const wrappedLines = Math.ceil(text.length / 72);
    const rows = Math.min(5, Math.max(1, Math.max(lineBreaks, wrappedLines)));
    box.rows = rows;
  }

  // Expose pure utilities for automated regression verification
  if (typeof window !== "undefined") {
    window.__SOSON_CHAT_UTILS__ = Object.freeze({
      parseExactDecimal,
      formatVnd,
      approxVnd,
      shortVnd,
      readable,
      detectAccountingView,
      detectProvenanceMode,
      extractClarificationSpec,
      generateSessionId,
    });
  }

  // Wire up DOM
  if ($("suggest")) {
    $("suggest").replaceChildren(
      ...SUGGESTIONS.map((q) =>
        el("li", {}, el("button", { type: "button", onclick: () => { clearActiveClarification(); ask(q); } }, q))
      )
    );
  }
  if ($("suggest-followup")) {
    $("suggest-followup").replaceChildren(
      ...FOLLOWUP_SUGGESTIONS.map((q) =>
        el("li", {}, el("button", { type: "button", onclick: () => ask(q) }, q))
      )
    );
  }
  $("reset-session")?.addEventListener("click", resetConversation);
  $("new-session")?.addEventListener("click", newConversation);
  $("session-list")?.addEventListener("change", (event) => openConversation(event.target.value));
  $("cancel-clarification")?.addEventListener("click", () => {
    clearActiveClarification();
    $("question")?.focus();
  });

  const box = $("question");
  if (box) {
    box.addEventListener("input", () => syncComposerRows(box));
    box.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        $("composer")?.requestSubmit();
      }
    });
  }
  $("composer")?.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!box) return;
    const q = box.value.trim();
    if (!q || $("send")?.disabled) return;
    box.value = "";
    syncComposerRows(box);
    ask(q);
  });

  conversations.set(currentConversation, { title: "Hội thoại 1", sessionId, clarification: null,
    lastAnswered: null, nodes: Array.from($("thread").children) });
  updateConversationList();
  renderSessionHeader();
  loadMetrics();
})();
