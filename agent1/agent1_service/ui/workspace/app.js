"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const connectHash = new URLSearchParams(location.hash.slice(1));
  const hasPortalTicket = connectHash.has("portal-connect");
  const portalTicket = connectHash.get("portal-connect");
  if (hasPortalTicket) {
    const cleanUrl = new URL(location.href);
    cleanUrl.hash = "overview";
    history.replaceState(null, "", cleanUrl.href);
  }
  const fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
  const short = (n) =>
    Math.abs(n) >= 1e9
      ? (n / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 1 }) + " tỷ"
      : Math.abs(n) >= 1e6
        ? (n / 1e6).toLocaleString("vi-VN", { maximumFractionDigits: 1 }) +
          " tr"
        : fmt.format(n);
  const titles = {
    overview: "Tổng quan",
    data: "Dữ liệu doanh nghiệp",
    records: "Sổ dữ liệu và lịch sử nạp",
    training: "Thiết lập và kiểm định",
    forecast: "Dự báo và kịch bản",
    guide: "Hướng dẫn dữ liệu",
  };
  const labels = {
    field: "Trường", before: "Trước khi sửa", after: "Sau khi sửa",
    invoices: "Hóa đơn", bank: "Dòng sao kê", payments: "Thanh toán", statements: "Kỳ sao kê", actions: "Nhật ký", outflows: "Lịch cố định · T5",
    expense_payments: "Thanh toán nghĩa vụ T5", settlement_id: "Mã thanh toán nghĩa vụ",
    forecast_date: "Ngày dự kiến trả/nhận còn lại", source: "Nguồn hồ sơ/hợp đồng",
    verified: "Đã xác nhận hồ sơ (true/false)", refund_approved_at: "Ngày quyết định hoàn",
    business_day: "Dời ngày (none/following/preceding)", replaces_expense_id: "Mã lịch được thay thế",
    identifier: "Mã bản ghi", status: "Trạng thái", remaining_amount: "Còn lại", allocated_amount: "Đã phân bổ",
    value: "Giá trị", source_file: "Tên tệp", imported_by: "Người nạp", created_at: "Thời gian",
    new: "Mới", changed: "Sửa", unchanged: "Trùng giữ nguyên", error_count: "Lỗi", rows: "Số dòng", valid_rows: "Dòng hợp lệ",
    legacy: "Nhật ký cũ", note: "Ghi chú",
    outstanding_before: "Công nợ trước", outstanding_after: "Công nợ sau",
    promise_reliability: "Tỷ lệ giữ hứa ước tính",
    promised_date: "Ngày khách hứa",
    disputed: "Tranh chấp",
    reason: "Lý do",
    kind: "Loại sự kiện",
    event_id: "Mã sự kiện",
    promise_date: "Ngày hứa trả",
    actual_balance: "Số dư thực tế",
    in_error: "Chênh thu (VND)",
    out_error: "Chênh chi (VND)",
    bank_id: "Mã dòng sao kê",
    direction: "Thu/chi",
    account: "Tài khoản",
    statement_id: "Mã kỳ",
    opening_balance: "Số dư đầu",
    closing_balance: "Số dư cuối",
    start_date: "Từ ngày",
    end_date: "Đến ngày",
    unallocated: "Chưa phân bổ",
    outflow_status: "Phạm vi lịch chi",
    below_floor_probability: "Xác suất dưới mức tối thiểu",
    cutoff: "Ngày chốt",
    model_version: "Phiên bản",
    dataset_hash: "Mã dữ liệu",
    component: "Nhóm dự báo",
    invoice_id: "Mã hóa đơn",
    customer_id: "Mã khách hàng",
    issue_date: "Ngày lập",
    due_date: "Hạn thanh toán",
    amount: "Số tiền",
    known_at: "Ngày ghi nhận",
    memo: "Nội dung chuyển khoản",
    counterparty: "Tên người chuyển / đối tác",
    customer_name: "Tên khách hàng",
    cash_flow_class: "Loại dòng tiền (ar / financing / internal / non_ar…)",
    currency: "Đồng tiền",
    seller_mst: "MST người bán",
    buyer_mst: "MST người mua",
    symbol: "Ký hiệu hóa đơn",
    invoice_no: "Số chứng từ",
    amount_net: "Tiền trước thuế",
    vat: "Tiền thuế VAT",
    record_version: "Phiên bản chứng từ",
    adjustment_type: "Loại: replacement / adjustment",
    adjusts_invoice_id: "Mã hóa đơn gốc",
    adjusts_symbol: "Ký hiệu hóa đơn gốc",
    adjusts_invoice_no: "Số hóa đơn gốc",
    adjusts_issue_date: "Ngày lập hóa đơn gốc",
    event_type: "Loại: cancel",
    event_date: "Ngày hủy",
    payment_id: "Mã thanh toán",
    payment_date: "Ngày tiền về",
    expense_id: "Mã khoản chi",
    date: "Ngày",
    category: "Loại chi",
    week: "Tuần",
    cash_in: "Dự kiến thu",
    cash_out: "Dự kiến chi",
    balance: "Số dư dự kiến",
    low: "Mô phỏng P10",
    high: "Mô phỏng P90",
    outstanding: "Còn phải thu",
    overdue_days: "Ngày quá hạn",
    payment_probability_4w: "Xác suất tất toán 4 tuần",
    collection_rank: "Ưu tiên",
    priority_score: "Điểm ưu tiên",
  };
  let token = "",
    connected = false,
    state = null,
    preview = null,
    reconciliationState = null,
    sourceCorrection = {base_hash:null, records:[], preview:null, key:null, edit_revision:0},
    lastForecast = null,
    baselineForecast = null,
    currentView = "overview",
    appliedCompanyProfile = "",
    manualMapping = {},
    poll = null;
  let recordsOffset = 0, importsOffset = 0, recordsRequest = 0, importsRequest = 0;
  const statusLabels = {recorded:"Đã ghi nhận", open:"Chưa thanh toán", partial:"Một phần", paid:"Đã tất toán",
    cancelled:"Đã hủy nghĩa vụ", replaced:"Đã thay thế", overdue:"Quá hạn, còn phải trả",
    awaiting_approval:"Chờ quyết định hoàn", awaiting_refund_date:"Cần ngày dự kiến nhận hoàn mới",
    inactive:"Chưa có hiệu lực / chứng từ liên quan", written_off:"Đã xóa nợ", outgoing:"Tiền chi", non_ar:"Ngoài công nợ",
    allocated:"Đã phân bổ hết", pending:"Chưa phân bổ", linked:"Có liên kết sao kê", unlinked:"Chưa liên kết sao kê",
    future:"Chưa đến ngày ghi nhận", committed:"Đã lưu", preview:"Đã kiểm tra, chưa lưu", invalid:"Có lỗi, chưa lưu",
    legacy_preview:"Đã kiểm tra · chưa rõ xác nhận",
    accepted:"Đã duyệt", reversed:"Đã đảo", rejected:"Đã từ chối", corrected:"Đã sửa nguồn", active:"Đang hiệu lực"};
  const charts = new Map();
  const node = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };
  const today = new Date();
  const localDate = new Date(
    today.getTime() - today.getTimezoneOffset() * 60000,
  )
    .toISOString()
    .slice(0, 10);
  function displayDate(value) {
    const iso = String(value || "").slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(iso)
      ? `${iso.slice(8, 10)}-${iso.slice(5, 7)}-${iso.slice(2, 4)}` : (value || "—");
  }
  function setDate(id, iso) {
    $(id).value = displayDate(iso);
    $(id).dataset.iso = iso;
  }
  function inputDate(id) {
    const field = $(id), value = field.value.trim();
    if (field.dataset.iso && value === displayDate(field.dataset.iso)) return field.dataset.iso;
    const match = /^(\d{2})-(\d{2})-(\d{2})$/.exec(value);
    const iso = match ? `${Number(match[3]) >= 69 ? "19" : "20"}${match[3]}-${match[2]}-${match[1]}` : value;
    const parsed = new Date(iso + "T00:00:00Z");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso) || Number.isNaN(parsed.getTime()) ||
        parsed.toISOString().slice(0, 10) !== iso)
      throw new Error("Nhập ngày hợp lệ theo dd-mm-yy, ví dụ 31-10-26.");
    setDate(id, iso);
    return iso;
  }
  const dateColumns = new Set(["date", "issue_date", "due_date", "payment_date", "known_at",
    "forecast_date", "refund_approved_at",
    "promised_date", "promise_date", "start_date", "end_date", "cutoff", "event_date", "adjusts_issue_date"]);
  $("today").textContent = displayDate(localDate);
  for (const id of ["train-asof", "forecast-cutoff", "actuals-date"]) {
    setDate(id, localDate);
    $(id).addEventListener("blur", () => {
      try { inputDate(id); } catch { /* Keep the text for correction. */ }
    });
  }
  function notice(message, error = false) {
    $("notice").textContent = message;
    $("notice").className = error ? "error" : "";
    $("notice").hidden = false;
  }
  function connect() {
    $("connect-error").textContent = "";
    if (!$("connect-dialog").open) $("connect-dialog").showModal();
  }
  async function api(path, options = {}) {
    if (!token && !connected) {
      connect();
      throw new Error("Kết nối doanh nghiệp để tiếp tục.");
    }
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", "Bearer " + token);
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const response = await fetch("/v1" + path, {
      ...options,
      headers,
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) {
      let detail;
      try {
        detail = (await response.json()).detail;
      } catch {
        detail = "Không thể hoàn tất yêu cầu (" + response.status + ").";
      }
      if (response.status === 401) {
        token = "";
        connected = false;
        connect();
      }
      throw new Error(
        Array.isArray(detail)
          ? detail.map((x) => x.msg).join("; ")
          : String(detail),
      );
    }
    return response.headers.get("Content-Type")?.includes("application/json")
      ? response.json()
      : response.blob();
  }
  async function action(fn, button) {
    const disabled = button?.disabled;
    if (button) button.disabled = true;
    try {
      await fn();
    } catch (err) {
      notice(err.message || "Không kết nối được máy chủ.", true);
    } finally {
      if (button)
        button.disabled =
          button.id === "train-button"
            ? Boolean(
                state?.jobs.some((j) =>
                  ["queued", "running"].includes(j.status),
                ),
              )
            : button.id === "commit-import"
              ? !preview?.can_commit
              : button.id === "commit-source-correction"
                ? !sourceCorrection.preview
                : disabled;
    }
  }
  function switchView(view) {
    if (!titles[view]) return;
    currentView = view;
    document
      .querySelectorAll(".view")
      .forEach((e) => (e.hidden = e.id !== "view-" + view));
    document.querySelectorAll("nav button").forEach((e) => {
      e.classList.toggle("active", e.dataset.view === view);
      e.setAttribute(
        "aria-current",
        e.dataset.view === view ? "page" : "false",
      );
    });
    $("breadcrumb").textContent = titles[view];
    document.querySelector(".nav-more").open = ["overview", "training", "guide"].includes(view);
    location.hash = view;
    drawVisibleChart();
    window.scrollTo({ top: 0, behavior: "instant" });
    if (view === "records" && (token || connected)) action(async () => {
      await Promise.all([loadRecords(), loadImportHistory()]);
    });
  }
  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.addEventListener("click", () => switchView(button.dataset.view)),
    );
  window.addEventListener("hashchange", () => {
    const name = location.hash.slice(1);
    if (name !== currentView) switchView(name);
  });
  $("connect-top").onclick = $("connect-open").onclick = connect;
  $("connect-cancel").onclick = () => $("connect-dialog").close();
  async function connectWithKey(key, expectedCompany = null) {
    token = key;
    try {
      const access = await api("/access");
      if (expectedCompany && access.company !== expectedCompany) {
        throw new Error("Kết nối không khớp doanh nghiệp. Mở lại tab từ trang chung.");
      }
      if (key) await api("/session", { method: "POST" });
      connected = true;
      // A localhost portal may embed 127.0.0.1, where third-party cookies are blocked.
      token = window.parent !== window ? key : "";
      if (access.role === "reader") {
        document.body.classList.add("reader-mode");
        $("company-name").textContent = access.company;
        $("mode-badge").textContent = access.company;
        $("connection-state").textContent = "Chỉ xem kế hoạch đã lưu";
        $("connect-top").hidden = true;
        $("logout").hidden = false;
        switchView("forecast");
        $("saved-plans").click();
      } else await refresh();
      $("token-input").value = "";
      $("connect-dialog").close();
      notice(
        "Đã kết nối. Dữ liệu chỉ hiển thị trong không gian doanh nghiệp này.",
      );
    } catch (err) {
      token = "";
      connected = false;
      throw err;
    } finally {
      $("token-input").value = "";
    }
  }
  $("connect-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.submitter || $("connect-form").querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await connectWithKey($("token-input").value.trim());
    } catch (err) {
      $("connect-error").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
  async function redeemPortalTicket(ticket) {
    const submit = $("connect-form").querySelector("button[type=submit]");
    for (const button of [$("connect-top"), $("connect-open"), submit]) button.disabled = true;
    notice("Đang kết nối với doanh nghiệp từ trang chung…");
    try {
      const response = await fetch("/v1/portal-connect/redeem", {
        method: "POST", cache: "no-store", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket: ticket || "" }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Không đổi được mã kết nối. Mở lại tab từ trang chung.");
      if (!result.key || !result.company) throw new Error("Kết nối thiếu thông tin doanh nghiệp. Mở lại tab từ trang chung.");
      await connectWithKey(result.key, result.company);
    } catch (err) {
      connect();
      $("connect-error").textContent = err.message;
      notice(err.message, true);
    } finally {
      for (const button of [$("connect-top"), $("connect-open"), submit]) button.disabled = false;
    }
  }
  async function restoreSession() {
    try {
      const response = await fetch("/v1/access", { cache: "no-store", credentials: "same-origin" });
      if (!response.ok || connected || token) return;
      connected = true;
      await connectWithKey("");
    } catch (err) {
      connected = false;
      notice(err.message || "Không khôi phục được phiên kết nối.", true);
    }
  }
  // Inside the platform shell: exchange its access key for a browser session.
  if (window.parent !== window) {
    window.addEventListener("message", (event) => {
      const data = event.data || {};
      if (event.source !== window.parent || data.type !== "platform-access-key" || token || connected) return;
      if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(event.origin)) return;
      $("token-input").value = String(data.key || "");
      $("connect-form").requestSubmit();
    });
    window.parent.postMessage({ type: "platform-ready", agent: "agent1" }, "*");
  }
  $("logout").onclick = () => action(async () => {
    const response = await fetch("/v1/session", { method: "DELETE", credentials: "same-origin" });
    if (!response.ok) throw new Error("Chưa ngắt được phiên. Thử lại.");
    token = "";
    connected = false;
    state = null;
    clearTimeout(poll);
    location.reload();
  }, $("logout"));
  $("refresh").onclick = () => action(refresh, $("refresh"));
  function clearForecast() {
    lastForecast = null;
    baselineForecast = null;
    charts.forEach((chart) => chart.destroy());
    charts.clear();
    $("forecast-output").hidden = true;
    $("forecast-empty").hidden = false;
    $("export-forecast").disabled = true;
    $("kpi-outstanding").textContent = $("kpi-balance").textContent = "—";
    $("kpi-invoices").textContent = "Chưa lập dự báo";
    const empty = node("div", undefined, "empty-chart");
    const copy = node("div", undefined, "empty-copy");
    copy.append(
      node("span", "↗", "round-icon"),
      node("h3", "Dữ liệu đã đổi, hãy lập dự báo mới."),
      node("p", "Mỗi lần cập nhật là một kế hoạch chính xác hơn."),
    );
    empty.append(copy);
    $("overview-chart").replaceChildren(empty);
  }
  function applyCompanyProfile(profile) {
    const managed = Boolean(profile?.managed);
    $("company-profile").hidden = !managed;
    $("import-format-hint").hidden = !managed;
    $("date-format").disabled = managed;
    $("number-format").disabled = managed;
    if (!managed) return;
    const signature = JSON.stringify([profile.code, profile.date_format, profile.number_format]);
    if (appliedCompanyProfile && appliedCompanyProfile !== signature) resetPreview();
    appliedCompanyProfile = signature;
    $("date-format").value = profile.date_format === "iso" ? "%Y-%m-%d" : "%d/%m/%Y";
    $("number-format").value = profile.number_format;
    $("profile-code").textContent = profile.code;
    $("profile-date").textContent = profile.date_format === "iso" ? "2026-12-31 (năm-tháng-ngày)" : "31/12/2026 (ngày/tháng/năm)";
    $("profile-number").textContent = profile.number_format === "plain" ? "1250000.50" : "1.250.000,50";
    const home = $("portal-return").getAttribute("href");
    $("profile-settings").hidden = !home;
    if (home) {
      const settings = new URL(home);
      settings.hash = "config";
      $("profile-settings").href = settings.href;
    }
  }
  async function refresh() {
    const next = await api("/workspace");
    if (state && state.dataset_hash !== next.dataset_hash) {
      $("train-complete").checked = false;
      $("forecast-complete").checked = false;
      reconciliationState = null;
      $("reconciliation-status").textContent = "Dữ liệu đã đổi. Tải lại khoản chờ hoặc tìm đề xuất mới trước khi duyệt.";
      $("reconciliation-cases").replaceChildren();
      invalidateSourceCorrection();
    }
    if (
      state &&
      (state.dataset_hash !== next.dataset_hash ||
        state.active_version !== next.active_version) &&
      lastForecast
    )
      clearForecast();
    state = next;
    applyCompanyProfile(state.company_profile);
    $("company-name").textContent = state.company;
    $("mode-badge").textContent = state.synthetic_sandbox ? "MÔI TRƯỜNG DEMO · ĐƯỢC PHÉP TRAIN" : state.company;
    $("connection-state").textContent = "Đã kết nối · dữ liệu riêng";
    $("connect-top").hidden = true;
    $("logout").hidden = false;
    $("kpi-records").textContent = fmt.format(state.counts.invoices);
    $("kpi-payments").textContent =
      fmt.format(state.counts.payments) + " khoản thanh toán đã nạp";
    $("data-counts").replaceChildren(
      ...Object.entries(state.counts).map(([key, value]) => {
        const el = node("div");
        el.append(
          node("b", fmt.format(value)),
          node(
            "span",
            key === "invoices"
              ? "hóa đơn"
              : key === "payments"
                ? "thanh toán"
                : {
                    actions: "sự kiện thu nợ",
                    bank: "dòng sao kê",
                    statements: "kỳ đã đối chiếu",
                    outflows: "lần đến hạn T5",
                    expense_payments: "thanh toán nghĩa vụ T5",
                    invoice_events: "sự kiện hủy hóa đơn",
                  }[key] || key,
          ),
        );
        return el;
      }),
    );
    if (state.needs_retraining) {
      $("next-title").textContent = "Dữ liệu mới đã sẵn sàng.";
      $("next-copy").textContent =
        "Phiên bản đang dùng được học trên dữ liệu trước. Hãy kiểm định lại để cập nhật.";
    } else if (state.counts.invoices) {
      $("next-title").textContent =
        "Sổ của bạn đã có " + fmt.format(state.counts.invoices) + " hóa đơn.";
      $("next-copy").textContent = state.active_version
        ? "Phiên bản đã chọn sẵn sàng. Nhập số dư thực tế để lập kế hoạch."
        : "Tiếp tục nạp thanh toán, kiểm định hoặc lập dự báo theo lịch sử hiện có.";
    }
    renderVersions();
    renderJobs();
    if (currentView === "records") await Promise.all([loadRecords(), loadImportHistory()]);
    clearTimeout(poll);
    if (state.jobs.some((j) => ["queued", "running"].includes(j.status)))
      poll = setTimeout(() => action(refresh), 3000);
  }
  function table(records, fields, formatting = {}) {
    const t = node("table"),
      head = node("thead"),
      header = node("tr");
    fields.forEach((field) =>
      header.append(node("th", labels[field] || field)),
    );
    head.append(header);
    t.append(head);
    const body = node("tbody");
    records.forEach((record) => {
      const tr = node("tr");
      fields.forEach((field) =>
        tr.append(
          node(
            "td",
            formatting[field]
              ? formatting[field](record[field])
              : typeof record[field] === "number"
                ? fmt.format(record[field])
                : dateColumns.has(field)
                  ? displayDate(record[field])
                  : String(record[field] ?? "—"),
          ),
        ),
      );
      body.append(tr);
    });
    t.append(body);
    return t;
  }
  const recordFields = {
    invoices:["identifier", "customer_id", "issue_date", "due_date", "amount", "remaining_amount", "status"],
    bank:["identifier", "account", "date", "direction", "amount", "allocated_amount", "remaining_amount", "status"],
    payments:["identifier", "invoice_id", "bank_id", "payment_date", "amount", "status"],
    statements:["identifier", "account", "start_date", "end_date", "opening_balance", "closing_balance"],
    outflows:["identifier", "date", "amount", "allocated_amount", "remaining_amount", "category", "status", "known_at"],
    expense_payments:["identifier", "expense_id", "bank_id", "payment_date", "amount", "known_at"],
    actions:["identifier", "invoice_id", "date", "kind", "promise_date"],
    invoice_events:["identifier", "invoice_id", "event_type", "event_date", "known_at"],
  };
  function recordLink(kind, identifier) {
    const button = node("button", identifier, "link-button");
    button.type = "button";
    button.onclick = () => action(() => showRecord(kind, identifier), button);
    return button;
  }
  async function loadRecords() {
    const requestId = ++recordsRequest;
    const kind = $("records-kind").value, selectedStatus = $("records-status").value;
    const query = new URLSearchParams({kind, q:$("records-query").value.trim(), status:selectedStatus,
      date_from:$("records-from").value, date_to:$("records-to").value, offset:String(recordsOffset), limit:"25"});
    $("records-status-text").textContent = "Đang tải bản ghi…";
    const result = await api("/records?" + query);
    if (requestId !== recordsRequest) return;
    $("records-status").replaceChildren(new Option("Tất cả", ""),
      ...result.statuses.map(value => new Option(statusLabels[value] || value, value)));
    $("records-status").value = selectedStatus;
    const fields = recordFields[kind], grid = table(result.rows, fields, {
      status:value => statusLabels[value] || value, direction:value => value === "in" ? "Thu" : "Chi",
    });
    Array.from(grid.querySelectorAll("tbody tr")).forEach((row, index) => {
      row.cells[0].replaceChildren(recordLink(kind, result.rows[index].identifier));
    });
    $("records-table").replaceChildren(grid);
    $("records-status-text").textContent = result.total ? fmt.format(result.total) + " bản ghi phù hợp. Bấm mã để xem chi tiết và liên kết." : "Không có bản ghi phù hợp.";
    $("records-page").textContent = result.total ? `${recordsOffset + 1}–${Math.min(recordsOffset + 25, result.total)} / ${fmt.format(result.total)}` : "0 bản ghi";
    $("records-prev").disabled = recordsOffset === 0;
    $("records-next").disabled = recordsOffset + 25 >= result.total;
  }
  function valueTable(record) {
    return table(Object.entries(record).map(([field, value]) => ({field:labels[field] || field,
      value:value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : value})), ["field", "value"]);
  }
  async function showRecord(kind, identifier) {
    const result = await api("/records/" + encodeURIComponent(kind) + "/" + encodeURIComponent(identifier));
    const content = $("record-detail-content");
    content.replaceChildren();
    $("record-detail-title").textContent = (labels[kind] || kind) + " · " + identifier + (result.deleted ? " · Đã xóa/đảo" : "");
    const values = node("div", undefined, "table-scroll"); values.append(valueTable(result.record)); content.append(values);
    content.append(node("h3", "Hóa đơn, thanh toán và sao kê liên quan"));
    if (!result.related.length) content.append(node("p", "Chưa có bản ghi liên kết."));
    const links = node("div", undefined, "record-links");
    result.related.forEach(row => { const item = node("div"); item.append(node("span", (labels[row.kind] || row.kind) + ": "), recordLink(row.kind, row.identifier)); links.append(item); });
    content.append(links, node("h3", "Quyết định phân bổ và lịch sử xử lý"));
    if (!result.decisions.length) content.append(node("p", "Chưa có quyết định T9 liên quan."));
    result.decisions.forEach(decision => {
      const card = node("div", undefined, "record-decision");
      card.append(node("strong", decision.decision_id), node("p", (statusLabels[decision.status] || decision.status || "Đã xử lý") +
        " · " + (decision.reviewed_by || "—") + " · " + displayDate(decision.known_at)), node("p", decision.note || ""));
      (decision.allocations || []).forEach(allocation => {
        const line = node("p"); line.append(recordLink("bank", allocation.payment_id), node("span", " → "),
          recordLink("invoices", allocation.invoice_id), node("span", " · " + exactMoney(allocation.amount_minor) + " VND")); card.append(line);
      });
      if (decision.reversal) card.append(node("p", "Đảo bởi " + decision.reversal.reviewed_by + ": " + decision.reversal.note));
      content.append(card);
    });
    content.append(node("h3", "Các lần nạp chứa bản ghi này"));
    if (!result.imports.length) content.append(node("p", "Chưa có nhật ký tệp; bản ghi có thể được tạo trước khi bật nhật ký hoặc do T9 tạo."));
    result.imports.forEach(batch => { const button = node("button", (batch.source_file || "Tệp dữ liệu") + " · " + displayTime(batch.created_at), "link-button");
      button.type = "button"; button.onclick = () => action(() => showImport(batch.id), button); content.append(button); });
    content.append(node("h3", "Phiên bản bản ghi"));
    const versions = node("div", undefined, "table-scroll");
    versions.append(table(result.versions.length ? result.versions : [result.record],
      [...new Set([...(recordFields[kind] || []).filter(field => field !== "identifier" && field !== "status"), "known_at", "known_at_time", "_deleted"])]));
    content.append(versions);
    $("record-detail-panel").hidden = false;
    $("record-detail-panel").scrollIntoView({behavior:"smooth", block:"start"});
  }
  function displayTime(value) {
    const stamp = new Date(value);
    return Number.isNaN(stamp.getTime()) ? String(value || "—") : stamp.toLocaleString("vi-VN");
  }
  async function loadImportHistory() {
    const requestId = ++importsRequest;
    const result = await api("/imports?offset=" + importsOffset + "&limit=20&kind=" + encodeURIComponent($("records-kind").value));
    if (requestId !== importsRequest) return;
    const fields = ["source_file", "created_at", "imported_by", "status", "rows", "valid_rows", "new", "changed", "unchanged", "error_count", "outstanding_before", "outstanding_after"];
    const grid = table(result.rows, fields, {created_at:displayTime, status:value => statusLabels[value] || value,
      imported_by:value => value || "Chưa ghi tên"});
    Array.from(grid.querySelectorAll("tbody tr")).forEach((row, index) => {
      const button = node("button", result.rows[index].source_file || "Chưa ghi tên tệp · nhật ký cũ", "link-button"); button.type = "button";
      button.onclick = () => action(() => showImport(result.rows[index].id), button); row.cells[0].replaceChildren(button);
    });
    $("import-history-table").replaceChildren(grid);
    $("import-history-status").textContent = result.total ? "Lịch sử của bảng " + labels[$("records-kind").value] + ". Bấm tên tệp để xem bản ghi và lỗi." : "Chưa có lần nạp được ghi nhật ký cho bảng này.";
    if (result.legacy_count) $("import-history-status").textContent += " Có " + result.legacy_count +
      " lần kiểm tra từ phiên bản cũ: chưa ghi tên tệp, người nạp hoặc kết quả xác nhận. Dấu — là thông tin chưa được ghi lại.";
    $("imports-page").textContent = result.total ? `${importsOffset + 1}–${Math.min(importsOffset + 20, result.total)} / ${result.total}` : "0 lần nạp";
    $("imports-prev").disabled = importsOffset === 0;
    $("imports-next").disabled = importsOffset + 20 >= result.total;
  }
  async function showImport(identifier) {
    const result = await api("/imports/" + encodeURIComponent(identifier)), target = $("import-history-detail");
    target.replaceChildren(node("h3", "Chi tiết lần nạp"));
    const batch = {...result.batch, status:statusLabels[result.batch.status] || result.batch.status};
    batch.kind = labels[batch.kind] || batch.kind;
    batch.created_at = displayTime(batch.created_at);
    batch.source_file ||= "Chưa ghi tên tệp";
    batch.imported_by ||= "Chưa ghi tên";
    delete batch.legacy; delete batch.note;
    const values = node("div", undefined, "table-scroll"); values.append(valueTable(batch)); target.append(values);
    if (result.batch.note) target.prepend(node("p", result.batch.note, "warning-box"));
    result.errors.forEach(error => target.append(node("p", (error.row ? "Dòng " + error.row + ": " : "") + error.message, "error-text")));
    const links = node("div", undefined, "record-links");
    result.records.forEach(row => links.append(recordLink(row.kind, row.identifier))); target.append(links);
    if (result.record_count > result.records.length) target.append(node("p", "Hiển thị " + result.records.length + " mã đầu. Dùng danh sách bản ghi để tìm các mã còn lại."));
    target.scrollIntoView({behavior:"smooth", block:"start"});
  }
  $("records-filter").onsubmit = event => { event.preventDefault(); recordsOffset = 0; action(loadRecords, event.submitter); };
  $("records-kind").onchange = () => {
    recordsOffset = importsOffset = 0; $("records-status").replaceChildren(new Option("Tất cả", ""));
    $("record-detail-panel").hidden = true; $("import-history-detail").replaceChildren();
    action(async () => { await Promise.all([loadRecords(), loadImportHistory()]); });
  };
  $("records-prev").onclick = () => { recordsOffset = Math.max(0, recordsOffset - 25); action(loadRecords); };
  $("records-next").onclick = () => { recordsOffset += 25; action(loadRecords); };
  $("imports-prev").onclick = () => { importsOffset = Math.max(0, importsOffset - 20); action(loadImportHistory); };
  $("imports-next").onclick = () => { importsOffset += 20; action(loadImportHistory); };
  $("reload-import-history").onclick = () => action(loadImportHistory, $("reload-import-history"));
  $("record-detail-close").onclick = () => { $("record-detail-panel").hidden = true; };
  function resetPreview() {
    preview = null;
    manualMapping = {};
    $("mapping-panel").hidden = $("preview-panel").hidden = true;
    $("commit-import").disabled = true;
  }
  $("table-kind").onchange = resetPreview;
  $("sheet-name").onchange = () => {
    resetPreview();
    notice("Kiểm tra lại sheet đã chọn.");
  };
  $("all-errors").onclick = () =>
    action(async () => {
      if (preview) {
        const result = await api("/imports/" + preview.id + "/errors");
        const cell = (v) =>
          '"' +
          String(v ?? "")
            .replace(/^[=+@\-\t\r]/, (m) => "'" + m)
            .replace(/"/g, '""') +
          '"';
        const lines = [
          ["Dòng", "Cột", "Giá trị gốc", "Lỗi", "Cách sửa"],
          ...result.errors.map((e) => [
            e.row,
            e.column,
            e.original,
            e.message,
            e.suggestion,
          ]),
        ];
        download(
          new Blob(
            ["\ufeff", lines.map((r) => r.map(cell).join(",")).join("\r\n")],
            { type: "text/csv;charset=utf-8" },
          ),
          "loi-nhap-so.csv",
        );
      }
    });
  $("import-allocations").onclick = () => {
    $("table-kind").value = "payments";
    $("import-file").value = "";
    resetPreview();
    $("import-form").scrollIntoView({ behavior: "smooth", block: "start" });
    notice("Chọn CSV thanh toán bổ sung. Giữ mã thanh toán cũ để cập nhật; kiểm tra rồi xác nhận lưu.");
  };
  function exactMoney(value) {
    try { return fmt.format(BigInt(String(value))); }
    catch { return String(value ?? "—"); }
  }
  function reconciliationReviewer() {
    const input = $("reconciliation-reviewer");
    if (!input.value.trim()) {
      input.focus();
      throw new Error("Nhập tên người xử lý trước khi xác nhận.");
    }
    return input.value.trim();
  }
  function chooseAllocation(item, invoiceId = "", amount = item.unallocated) {
    $("allocate-bank").value = item.bank_id;
    $("allocate-amount").value = String(amount);
    $("allocate-id").value = "P-" + crypto.randomUUID();
    $("allocate-invoice").value = invoiceId;
    $("allocate-note").value = "";
    $("manual-allocation").hidden = false;
    $("manual-allocation").open = true;
    $(invoiceId ? "allocate-note" : "allocate-invoice").focus();
  }
  async function loadReconciliation() {
      const r = await api("/reconciliation");
      reconciliationState = r;
      $("manual-allocation").hidden = !r.pending_count;
      $("manual-allocation").open = false;
      $("allocation-invoices").replaceChildren(...r.invoices.map(item => {
        const option = node("option"); option.value = item.invoice_id;
        option.label = item.customer_id + " · còn " + exactMoney(item.amount_open_minor) + " VND";
        return option;
      }));
      if (!r.pending_count)
        $("pending-rows").replaceChildren(node("p", "Các khoản thu trong phạm vi đã được ghép. Bạn không cần phân bổ thêm."));
      else {
      const grid = table(r.pending, ["bank_id", "account", "date", "amount", "unallocated"], {amount:exactMoney, unallocated:exactMoney});
      const header = grid.querySelector("thead tr");
      if (header) header.append(node("th", "Xử lý ngoại lệ"));
      grid.querySelectorAll("tbody tr").forEach((tr, i) => {
        const item = r.pending[i];
        const cell = node("td"), choose = node("button", "Ghép khoản này", "link-button");
        choose.type = "button";
        choose.onclick = () => chooseAllocation(item);
        const edit = node("button", "Sửa dòng sao kê", "link-button"); edit.type = "button";
        edit.onclick = () => {
          $("source-correction-kind").value = "bank"; $("source-correction-id").value = item.bank_id;
          $("source-correction-load").closest("details").open = true;
          $("source-correction-load").requestSubmit();
        };
        const actions = node("div", undefined, "pending-actions");
        actions.append(choose, edit); cell.append(actions); tr.append(cell);
      });
      $("pending-rows").replaceChildren(
        node("p", exactMoney(r.unallocated) + " VND · " + r.pending_count + " khoản chưa ghép" + (r.pending_count > r.pending.length ? " · đang hiện " + r.pending.length + " khoản đầu" : "") + "."), grid);
      }
      renderReconciliationCases(r.proposal);
      renderReconciliationHistory(r.history, r.history_count);
      $("reconciliation-status").textContent = r.proposal?.stale
        ? "Đề xuất đã cũ vì dữ liệu hoặc quyết định thay đổi. Bấm Tìm đề xuất đối soát để cập nhật."
        : r.proposal ? "Đề xuất ngày " + displayDate(r.proposal.cutoff) + ". Kiểm tra chứng từ trước khi duyệt."
        : "Đã tải khoản chờ. Bấm Tìm đề xuất đối soát để tạo gợi ý.";
  }
  function renderReconciliationCases(proposal) {
    const target = $("reconciliation-cases"); target.replaceChildren();
    if (!proposal?.cases.length) {
      target.append(node("p", proposal ? "Không có khoản thu cần đối soát thêm." : "Chưa có đề xuất. Bấm Tìm đề xuất đối soát.", "muted"));
      return;
    }
    if (proposal.cases.length > 100) target.append(node("p", "Đang hiện 100 / " + proposal.cases.length + " giao dịch. Sau khi xử lý, chạy lại để xem các khoản tiếp theo."));
    for (const item of proposal.cases.slice(0, 100)) {
      const card = node("article", undefined, "reconciliation-case");
      const nonAr = item.reason === "non_ar_bank_movement";
      const status = nonAr ? "Ngoài công nợ" : {auto:"Có đề xuất", review:"Cần kiểm tra", unmatched:"Chưa ghép", rejected:"Đã từ chối"}[item.status] || item.status;
      card.append(node("h4", item.bank_id + " · " + status),
        node("p", displayDate(item.date) + " · " + item.account + " · " + (nonAr ? "giao dịch ngân hàng " : "chưa phân bổ ") + exactMoney(item.available_minor) + " VND"),
        node("p", item.reason_text), node("p", item.memo || "Sao kê chưa có nội dung chuyển khoản", "muted"));
      if (nonAr) card.append(node("p", "Không thuộc hàng chờ ghép công nợ. Nếu phân loại sai, sửa dữ liệu nguồn của dòng sao kê này.", "helper"));
      else if (item.status === "review" && item.reason === "ambiguous_subset")
        card.append(node("p", "Có nhiều phương án: mở danh sách ứng viên, đối chiếu chứng từ rồi ghép thủ công. Có thể để khoản này chờ nếu chưa đủ bằng chứng.", "helper"));
      else if (item.status === "review" && item.reason === "unknown_party")
        card.append(node("p", "Chưa rõ người chuyển: chỉ ghép thủ công khi đã xác nhận khách hàng và có bằng chứng; nếu chưa rõ, để khoản này chờ.", "helper"));
      if (item.allocations.length) {
        const allocations = node("ul");
        for (const a of item.allocations) allocations.append(node("li", a.invoice_id + " · " + exactMoney(a.amount_minor) + " VND"));
        card.append(allocations);
      }
      if (!nonAr && item.candidates.length) {
        const details = node("details"), list = node("div", undefined, "reconciliation-candidates");
        details.append(node("summary", "Ứng viên và điểm gợi ý · tối đa 10"));
        for (const candidate of item.candidates) {
          const row = node("div");
          row.append(node("span", candidate.invoice_id + " · " + candidate.customer_id + " · điểm " + candidate.score.toFixed(2) + " · còn " + exactMoney(candidate.amount_open_minor) + " VND"),
            node("small", candidate.evidence.join(" · ")));
          const button = node("button", "Chọn để ghép thủ công", "link-button"); button.type = "button";
          button.disabled = Boolean(proposal.stale);
          button.onclick = () => {
            const pending = reconciliationState?.pending.find(r => r.bank_id === item.bank_id)
              || {bank_id:item.bank_id, unallocated:item.available_minor};
            const amount = BigInt(String(pending.unallocated)) < BigInt(String(candidate.amount_open_minor)) ? pending.unallocated : candidate.amount_open_minor;
            chooseAllocation(pending, candidate.invoice_id, amount);
          };
          row.append(button); list.append(row);
        }
        details.append(list, node("p", "Có thể nhập mã hóa đơn khác ở phần phân bổ thủ công nếu danh sách gợi ý chưa có hóa đơn cần tìm.", "helper")); card.append(details);
      }
      if (item.status === "rejected") {
        card.append(node("p", "Người xử lý: " + item.reviewed_by + " · Lý do: " + item.note));
      } else if (!proposal.stale && item.reason !== "non_ar_bank_movement") {
        const form = node("form", undefined, "reconciliation-review"), label = node("label", "Ghi chú / lý do từ chối"), note = node("textarea");
        note.maxLength = 2000; label.append(note); form.append(label);
        const controls = node("div", undefined, "reconciliation-actions");
        if (item.allocations.length) {
          const accept = node("button", "Duyệt phân bổ", "button primary"); accept.type = "submit"; accept.value = "accept"; controls.append(accept);
        }
        if (item.status === "review" && ["ambiguous_subset", "unknown_party"].includes(item.reason)) {
          const manual = node("button", "Ghép thủ công khi có bằng chứng", "button"); manual.type = "button";
          manual.onclick = () => {
            const pending = reconciliationState?.pending.find(r => r.bank_id === item.bank_id);
            if (pending) chooseAllocation(pending);
          };
          controls.append(manual);
        }
        const reject = node("button", "Từ chối và lưu lý do", "button"); reject.type = "submit"; reject.value = "reject"; controls.append(reject);
        form.append(controls);
        const keys = {accept:crypto.randomUUID(), reject:crypto.randomUUID()};
        form.onsubmit = event => {
          event.preventDefault(); const kind = event.submitter.value;
          action(async () => {
            const actor = reconciliationReviewer();
            if (kind === "reject" && !note.value.trim()) { note.focus(); throw new Error("Nhập lý do từ chối để lưu lịch sử."); }
            if (reconciliationState?.proposal?.id !== proposal.id) throw new Error("Đề xuất đã đổi. Tải lại trước khi duyệt.");
            await api("/reconciliation/" + kind, {method:"POST", body:JSON.stringify({
              idempotency_key:keys[kind], proposal_id:proposal.id, bank_id:item.bank_id, reviewed_by:actor, note:note.value.trim(),
            })});
            await refresh(); await loadReconciliation();
            notice(kind === "accept" ? "Đã duyệt và cập nhật công nợ. Tìm đề xuất mới để xử lý khoản tiếp theo." : "Đã lưu lý do từ chối. Khoản thu vẫn chưa phân bổ.");
          }, event.submitter);
        };
        card.append(form);
      }
      target.append(card);
    }
  }
  function renderReconciliationHistory(history, count) {
    const target = $("reconciliation-history"); target.replaceChildren();
    if (!history.length) { target.append(node("p", "Chưa có quyết định xử lý trong Workspace.", "muted")); return; }
    if (count > history.length) target.append(node("p", "Đang hiện " + history.length + " / " + count + " quyết định gần nhất."));
    for (const item of history) {
      const row = node("article", undefined, "reconciliation-case");
      const status = {committed:"Đã xác nhận", reversed:"Đã đảo phân bổ", rejected:"Đã từ chối", corrected:"Đã sửa nguồn"}[item.status] || item.status;
      const when = displayDate(item.known_at) + (item.created_at ? " · " + new Date(item.created_at).toLocaleTimeString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", hour:"2-digit", minute:"2-digit", second:"2-digit"}) : "");
      row.append(node("h4", status + " · " + when), node("small", item.decision_id),
        node("p", "Người xử lý: " + item.reviewed_by), node("p", item.note || "Không có ghi chú bổ sung."));
      if (item.bank_id) row.append(node("p", "Giao dịch: " + item.bank_id));
      for (const edit of item.changes || []) {
        row.append(node("p", (labels[edit.kind] || edit.kind) + " · " + edit.identifier));
        for (const field of edit.changed_fields) row.append(node("p", (labels[field] || field) + ": " + String(edit.before[field] ?? "—") + " → " + String(edit.after[field] ?? "—")));
      }
      for (const a of item.allocations) row.append(node("p", a.payment_id + " → " + a.invoice_id + " · " + exactMoney(a.amount_minor) + " VND"));
      if (item.reversal) row.append(node("p", "Đảo bởi " + item.reversal.reviewed_by + " · " + displayDate(item.reversal.known_at) + " · " + item.reversal.note));
      if (item.status === "committed") {
        const form = node("form", undefined, "reconciliation-review"), label = node("label", "Lý do đảo phân bổ"), note = node("textarea"), button = node("button", "Đảo quyết định", "button danger");
        note.required = true; note.maxLength = 2000; label.append(note); form.append(label, button);
        const key = crypto.randomUUID();
        form.onsubmit = event => {
          event.preventDefault();
          action(async () => {
            if (!note.value.trim()) { note.focus(); throw new Error("Nhập lý do đảo phân bổ."); }
            await api("/reconciliation/reverse", {method:"POST", body:JSON.stringify({idempotency_key:key,
              decision_id:item.decision_id, reviewed_by:reconciliationReviewer(), note:note.value.trim()})});
            await refresh(); await loadReconciliation();
            notice("Đã đảo phân bổ. Công nợ và số tiền chưa phân bổ đã cập nhật.");
          }, event.submitter);
        };
        row.append(form);
      }
      target.append(row);
    }
  }
  $("load-pending").onclick = () => action(loadReconciliation, $("load-pending"));
  $("run-reconciliation").onclick = () => action(async () => {
    await api("/reconciliation/run", {method:"POST", body:"{}"});
    await loadReconciliation();
  }, $("run-reconciliation"));
  $("allocate-form").onsubmit = (e) => {
    e.preventDefault();
    action(async () => {
      if (!$("allocate-note").value.trim()) {
        $("allocate-note").focus();
        throw new Error("Nhập nguồn bằng chứng trước khi phân bổ thủ công.");
      }
      await api("/allocations", {
        method: "POST",
        body: JSON.stringify({
          payment_id: $("allocate-id").value,
          bank_id: $("allocate-bank").value,
          invoice_id: $("allocate-invoice").value,
          amount: $("allocate-amount").value,
          reviewed_by: reconciliationReviewer(),
          note: $("allocate-note").value.trim(),
        }),
      });
      await refresh();
      await loadReconciliation();
      notice("Đã ghi phân bổ và cập nhật số còn phải thu.");
    }, e.submitter);
  };
  function invalidateSourceCorrection() {
    sourceCorrection.edit_revision = (sourceCorrection.edit_revision || 0) + 1;
    sourceCorrection.preview = null;
    sourceCorrection.key = null;
    $("source-correction-preview").hidden = true;
    $("commit-source-correction").disabled = true;
  }
  function clearSourceCorrection() {
    invalidateSourceCorrection();
    sourceCorrection.base_hash = null;
    sourceCorrection.records = [];
    $("source-correction-editors").replaceChildren();
  }
  function correctionChanges() {
    return sourceCorrection.records.map(record => {
      const values = {};
      for (const [field, input] of Object.entries(record.inputs))
        if (input.value !== String(record.values[field] ?? "")) values[field] = input.value;
      return {kind:record.kind, identifier:record.identifier, values};
    }).filter(record => Object.keys(record.values).length);
  }
  function renderSourceCorrectionPreview(result) {
    $("source-correction-diff").replaceChildren(...result.changes.map(edit => {
      const part = node("div"); part.append(node("h4", edit.identifier));
      part.append(table(edit.changed_fields.map(field => ({field:labels[field] || field,
        before:String(edit.before[field] ?? "—"), after:String(edit.after[field] ?? "—")})), ["field", "before", "after"]));
      return part;
    }));
    const impact = $("source-correction-impact");
    impact.replaceChildren(node("p", "Sẽ đảo " + result.affected_decisions.length + " quyết định phân bổ. " +
      result.affected_payments.length + " bản ghi thanh toán cũ và " + result.affected_actions.length + " nhật ký / lời hứa bị ảnh hưởng."));
    for (const [title, rows, describe] of [
      ["Quyết định sẽ đảo", result.affected_decisions, r => r.decision_id + " · " + r.allocations.map(a => a.payment_id + " → " + a.invoice_id + ": " + exactMoney(a.amount_minor) + " VND").join("; ")],
      ["Thanh toán cũ sẽ ngừng sử dụng", result.affected_payments, r => r.payment_id + " · " + r.invoice_id + " · " + exactMoney(r.amount) + " VND"],
      ["Nhật ký / lời hứa cũ sẽ ngừng sử dụng", result.affected_actions, r => r.event_id + " · " + r.invoice_id + " · " + r.kind],
    ]) {
      if (!rows.length) continue;
      const details = node("details"), list = node("ul"); details.append(node("summary", title + " (" + rows.length + ")"));
      for (const row of rows.slice(0, 100)) list.append(node("li", describe(row)));
      if (rows.length > 100) list.append(node("li", "Hiển thị 100 / " + rows.length + " bản ghi. Xác nhận sẽ áp dụng toàn bộ phạm vi trên."));
      details.append(list); impact.append(details);
    }
    impact.append(node("p", "Bản cũ vẫn được giữ để kiểm tra lịch sử. Bản sửa chưa được phân bổ lại tự động; tìm đề xuất và duyệt lại sau khi lưu.", "helper"));
    $("source-correction-preview").hidden = false;
    $("commit-source-correction").disabled = false;
  }
  $("source-correction-load").onsubmit = event => {
    event.preventDefault();
    action(async () => {
      const kind = $("source-correction-kind").value, identifier = $("source-correction-id").value.trim();
      if (sourceCorrection.records.length >= 20) throw new Error("Mỗi lần sửa tối đa 20 bản ghi.");
      if (sourceCorrection.records.some(r => r.kind === kind && r.identifier === identifier)) throw new Error("Bản ghi này đã có trong form sửa.");
      const record = await api("/corrections/record?kind=" + encodeURIComponent(kind) + "&identifier=" + encodeURIComponent(identifier));
      if (sourceCorrection.base_hash && sourceCorrection.base_hash !== record.base_hash)
        throw new Error("Dữ liệu đã đổi. Làm trống form sửa rồi tải lại các bản ghi.");
      invalidateSourceCorrection(); sourceCorrection.base_hash = record.base_hash; record.inputs = {};
      const fieldset = node("fieldset", undefined, "source-correction-record"), grid = node("div", undefined, "two-fields");
      fieldset.append(node("legend", identifier + " · " + kind));
      for (const field of record.fields) {
        const label = node("label", labels[field] || field), input = node("input");
        input.value = String(record.values[field] ?? "");
        if (field.endsWith("date") || field === "date") input.type = "date";
        else { input.type = "text"; if (["amount", "amount_net", "vat", "opening_balance", "closing_balance"].includes(field)) input.inputMode = "numeric"; }
        input.maxLength = 2000; input.oninput = invalidateSourceCorrection; label.append(input); grid.append(label); record.inputs[field] = input;
      }
      const remove = node("button", "Bỏ khỏi form sửa", "link-button"); remove.type = "button";
      remove.onclick = () => { sourceCorrection.records = sourceCorrection.records.filter(r => r !== record); fieldset.remove(); invalidateSourceCorrection(); if (!sourceCorrection.records.length) sourceCorrection.base_hash = null; };
      fieldset.append(grid, remove); $("source-correction-editors").append(fieldset); sourceCorrection.records.push(record);
      if (!$("source-correction-reviewer").value) $("source-correction-reviewer").value = $("reconciliation-reviewer").value;
      $("source-correction-status").textContent = "Đã tải " + sourceCorrection.records.length + " bản ghi. Nhập giá trị đúng rồi xem trước ảnh hưởng.";
    }, event.submitter);
  };
  $("source-correction-reviewer").oninput = $("source-correction-note").oninput = invalidateSourceCorrection;
  $("source-correction-clear").onclick = () => { clearSourceCorrection(); $("source-correction-status").textContent = "Đã làm trống form. Chưa thay đổi dữ liệu nguồn."; };
  $("source-correction-form").onsubmit = event => {
    event.preventDefault();
    action(async () => {
      invalidateSourceCorrection();
      const changes = correctionChanges(), actor = $("source-correction-reviewer").value.trim(), note = $("source-correction-note").value.trim();
      const revision = sourceCorrection.edit_revision;
      if (!changes.length) throw new Error("Tải bản ghi và nhập ít nhất một thay đổi trước khi xem trước.");
      if (!actor || !note) throw new Error("Nhập tên người xử lý và lý do / bằng chứng sửa nguồn.");
      const result = await api("/corrections/preview", {method:"POST", body:JSON.stringify({base_hash:sourceCorrection.base_hash,
        changes, reviewed_by:actor, note})});
      if (sourceCorrection.edit_revision !== revision) throw new Error("Giá trị đã thay đổi trong lúc tải bản xem trước. Bấm Xem trước ảnh hưởng lại.");
      sourceCorrection.preview = result; sourceCorrection.key = crypto.randomUUID();
      renderSourceCorrectionPreview(result);
      $("source-correction-status").textContent = "Đang xem trước. Chưa lưu bản sửa; kiểm tra các giá trị và phân bổ bị ảnh hưởng bên dưới.";
    }, event.submitter);
  };
  $("commit-source-correction").onclick = () => action(async () => {
    const preview = sourceCorrection.preview, key = sourceCorrection.key;
    if (!preview || !key) throw new Error("Xem trước bản sửa trước khi xác nhận.");
    $("source-correction-status").textContent = "Đang gửi xác nhận sửa nguồn. Nếu chưa nhận được kết quả, tải lịch sử hoặc thử lại cùng bản xem trước này.";
    const result = await api("/corrections/" + encodeURIComponent(preview.id) + "/commit", {method:"POST", body:JSON.stringify({idempotency_key:key})});
    $("source-correction-status").textContent = "Đã lưu bản sửa và đảo " + result.reversed_count + " quyết định. Đang tải lại dữ liệu; có thể bấm Tải khoản chờ và lịch sử nếu kết nối bị gián đoạn.";
    clearSourceCorrection(); await refresh(); await loadReconciliation();
    $("reconciliation-ledger").open = true;
    $("source-correction-status").textContent = "Đã sửa nguồn và đảo " + result.reversed_count + " quyết định. Tìm đề xuất đối soát để duyệt lại các khoản cần phân bổ.";
    notice("Đã lưu phiên bản sửa; lịch sử và các kế hoạch đã lưu được giữ.");
  }, $("commit-source-correction"));
  $("saved-plans").onclick = () =>
    action(async () => {
      const plans = await api("/forecasts");
      $("plans-list").replaceChildren(
        ...plans.map((x) => {
          const btn = node(
            "button",
            displayDate(x.cutoff) +
              " · " +
              (x.created_at
                ? displayDate(x.created_at) + " " + new Date(x.created_at).toLocaleTimeString("vi-VN", {hour:"2-digit", minute:"2-digit"})
                : "Bản lưu cũ") +
              " · số dư thấp nhất " +
              short(x.minimum_balance),
            "button",
          );
          btn.onclick = () =>
            action(async () => {
              lastForecast = await api("/forecasts/" + x.id);
              $("saved-plans").closest("details").open = false;
              renderForecast();
            });
          return btn;
        }),
      );
      if (!plans.length) notice("Chưa có kế hoạch đã lưu.");
    });

  $("date-format").onchange = $("number-format").onchange = () => {
    preview = null;
    $("commit-import").disabled = true;
  };
  $("xml-known-at").value = localDate;
  $("xml-known-at").onchange = resetPreview;
  $("import-file").onchange = () => {
    resetPreview();
    $("sheet-name").replaceChildren();
    $("sheet-label").hidden = true;
    $("file-label").textContent =
      $("import-file").files[0]?.name || "Kéo file vào đây, hoặc bấm để chọn";
  };
  const drop = $("drop-zone");
  drop.ondragover = (event) => {
    event.preventDefault();
    drop.classList.add("drag");
  };
  drop.ondragleave = () => drop.classList.remove("drag");
  drop.ondrop = (event) => {
    event.preventDefault();
    drop.classList.remove("drag");
    if (event.dataTransfer.files.length) {
      $("import-file").files = event.dataTransfer.files;
      $("import-file").dispatchEvent(new Event("change"));
    }
  };
  $("import-form").onsubmit = (event) => {
    event.preventDefault();
    action(async () => {
      const file = $("import-file").files[0];
      if (!file) throw new Error("Chọn file trước.");
      const form = new FormData();
      form.append("file", file);
      form.append("kind", $("table-kind").value);
      form.append("sheet", $("sheet-name").value);
      form.append("mapping", JSON.stringify(manualMapping));
      form.append("date_format", $("date-format").value);
      form.append("number_format", $("number-format").value);
      form.append("imported_by", $("imported-by").value.trim());
      if (file.name.toLowerCase().endsWith(".xml")) {
        if (!$("xml-known-at").value) throw new Error("Chọn ngày biết dữ liệu XML.");
        form.append("known_at", $("xml-known-at").value);
      }
      preview = await api("/imports/preview", { method: "POST", body: form });
      const previousSheet = $("sheet-name").value;
      $("sheet-name").replaceChildren(
        ...preview.sheets.map((x) => new Option(x, x)),
      );
      if (preview.sheets.includes(previousSheet))
        $("sheet-name").value = previousSheet;
      $("sheet-label").hidden = !preview.sheets.length;
      $("all-errors").hidden = !preview.error_count;
      manualMapping = { ...preview.mapping };
      $("mapping-fields").replaceChildren(
        ...preview.fields.map((field) => {
          const label = node("label", labels[field] || field),
            select = node("select");
          select.setAttribute("aria-label", "Cột " + (labels[field] || field));
          const skip = node("option", "— Không ghép —");
          skip.value = "";
          select.append(skip);
          preview.columns.forEach((column) => {
            const option = node("option", column);
            option.value = column;
            select.append(option);
          });
          select.value = manualMapping[field] || "";
          select.disabled = preview.mapping_locked;
          select.onchange = () => {
            manualMapping[field] = select.value;
            preview = null;
            $("commit-import").disabled = true;
          };
          label.append(select);
          return label;
        }),
      );
      $("mapping-panel").hidden = preview.mapping_locked;
      $("preview-panel").hidden = false;
      $("preview-title").textContent =
        preview.valid_rows +
        "/" +
        preview.rows +
        " dòng hợp lệ · " +
        preview.updates +
        " dòng sẽ cập nhật";
      $("import-warnings").replaceChildren(
        ...preview.warnings.map((w) => node("p", w, "warning-box")),
      );
      $("import-errors").replaceChildren();
      if (preview.error_count) {
        const box = node("div", undefined, "error-list");
        box.append(
          node("b", preview.error_count + " lỗi cần sửa trước khi lưu"),
        );
        const list = node("ul");
        preview.errors.forEach((error) =>
          list.append(
            node(
              "li",
              (error.row ? "Dòng " + error.row + " · " : "") +
                (labels[error.column] || error.column) +
                ": " +
                error.message,
            ),
          ),
        );
        box.append(list);
        if (preview.error_count > 100)
          box.append(
            node("p", "Hiển thị 100 lỗi đầu. Sửa file rồi kiểm tra lại."),
          );
        $("import-errors").append(box);
      }
      $("preview-table").replaceChildren(table(preview.sample, preview.fields));
      $("changed-rows").replaceChildren(
        ...(preview.changes || []).flatMap((x) => [
          node("strong", "Trước / sau thay đổi"),
          table([x.before, x.after], preview.fields),
        ]),
      );
      $("commit-import").disabled = !preview.can_commit;
      $("preview-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    }, event.submitter);
  };
  $("commit-import").onclick = () =>
    action(async () => {
      if (!preview) return;
      const result = await api("/imports/" + preview.id + "/commit", {
        method: "POST",
      });
      resetPreview();
      await refresh();
      notice(
        "Đã lưu " +
          fmt.format(result.accepted) +
        " dòng: " + result.new + " mới, " + result.changed + " sửa, " + result.unchanged + " trùng giữ nguyên. Xem Sổ dữ liệu để tra cứu.",
      );
    }, $("commit-import"));
  function download(blob, name) {
    const url = URL.createObjectURL(blob),
      a = node("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function template(kind) {
    const formats = new URLSearchParams({ date_format: $("date-format").value, number_format: $("number-format").value });
    const blob = await api("/templates/" + kind + "?" + formats);
    download(blob, "agent1-" + kind + ".csv");
    notice(
      "Đã tải mẫu. Thay toàn bộ dòng DEMO bằng dữ liệu thật trước khi nạp.",
    );
  }
  $("download-template").onclick = () =>
    action(() => template($("table-kind").value));
  document
    .querySelectorAll(".template-link")
    .forEach(
      (button) =>
        (button.onclick = () =>
          action(() => template(button.dataset.kind), button)),
    );
  $("delete-record").onsubmit = (event) => {
    event.preventDefault();
    const kind = $("delete-kind").value,
      id = $("delete-id").value.trim();
    if (!confirm("Xóa bản ghi " + id + " khỏi dữ liệu hiện tại?")) return;
    action(async () => {
      await api("/records/" + kind + "/" + encodeURIComponent(id), {
        method: "DELETE",
      });
      await refresh();
      notice("Đã xóa bản ghi " + id + ".");
      $("delete-id").value = "";
    }, event.submitter);
  };
  $("train-form").onsubmit = (event) => {
    event.preventDefault();
    action(async () => {
      await api("/training", {
        method: "POST",
        body: JSON.stringify({
          asof: inputDate("train-asof"),
          payments_complete: $("train-complete").checked,
          try_deep_cash: $("try-deep").checked,
        }),
      });
      await refresh();
      notice(
        "Đã bắt đầu kiểm định. Bạn có thể chuyển màn hình; tiến độ được cập nhật tự động.",
      );
    }, event.submitter);
  };
  function renderJobs() {
    const status = {
      queued: "Đang xếp hàng",
      running: "Đang kiểm định",
      completed: "Đã hoàn tất",
      failed: "Cần xử lý",
    };
    $("jobs").replaceChildren(
      ...state.jobs.slice(0, 3).map((job, index) => {
        const el = node("div", undefined, "job " + job.status);
        el.append(
          node("b", (index ? "Lượt trước · " : "") + (status[job.status] || job.status)),
          node("small", job.message),
        );
        return el;
      }),
    );
    const latest = state.jobs[0];
    if (latest && latest.status === "failed") notice(latest.message, true);
    else if (latest && latest.status === "completed") notice("Kiểm định hoàn tất. Xem kết quả phiên bản trước khi sử dụng.");
    $("train-button").disabled = state.jobs.some((j) =>
      ["queued", "running"].includes(j.status),
    );
  }
  function renderVersions() {
    const list = $("versions-list");
    list.replaceChildren();
    if (!state.versions.length) {
      list.append(
        node(
          "p",
          state.jobs[0]?.status === "failed"
            ? "Lượt kiểm định chưa hoàn tất nên chưa có phiên bản. Xem lỗi bên trái."
            : state.jobs.some(j => ["queued", "running"].includes(j.status))
              ? "Đang học và kiểm định. Phiên bản sẽ xuất hiện khi hoàn tất."
              : "Chưa có phiên bản. Bắt đầu kiểm định sau khi nạp đủ lịch sử.",
          "muted",
        ),
      );
      return;
    }
    state.versions.forEach((version, index) => {
      const row = node("div", undefined, "version"),
        info = node("div"),
        audit = version.audit;
      info.append(
        node(
          "h3",
          "Phiên bản " +
            (state.versions.length - index) +
            " · dữ liệu đến " +
            displayDate(version.asof),
        ),
      );
      const measures = node("div", undefined, "audit-metrics");
      [
        ["ỨNG VIÊN", audit.candidate_brier4.toFixed(4)],
        ["MỐC LỊCH SỬ", audit.baseline_brier4.toFixed(4)],
        ["HÓA ĐƠN KIỂM TRA", fmt.format(audit.n)],
      ].forEach(([label, value]) => {
        const item = node("div", label);
        item.append(node("b", value));
        measures.append(item);
      });
      info.append(
        measures,
        node(
          "p",
          audit.accepted
            ? "Ứng viên không kém mốc trên bài kiểm tra. Sẵn sàng để bạn xem xét sử dụng."
            : "Ứng viên chưa vượt mốc lịch sử. Phiên bản này dùng phương án mốc để dự báo.",
        ),
      );
      info.append(
        node(
          "small",
          "Cải thiện Brier, khoảng 95%: [" +
            audit.improvement_ci_low.toFixed(4) +
            "; " +
            audit.improvement_ci_high.toFixed(4) +
            "]. " +
            (audit.ci_reliable
              ? ""
              : "Ít nhóm khách hàng; khoảng ước lượng cần thận trọng. ") +
            version.train_n +
            " hóa đơn học, " +
            version.validation_n +
            " hóa đơn hiệu chỉnh.",
        ),
      );
      if (version.risk_status) info.append(node("p", version.risk_status === "evaluated"
        ? "Rủi ro xóa nợ: đã kiểm tra trên lịch sử đủ thời gian quan sát."
        : "Rủi ro xóa nợ: chưa đủ lịch sử có nhãn; chưa đưa ra xác suất."));
      const cq = version.collection_quality;
      if (cq && cq.audit) info.append(node("p", "Kiểm tra danh sách 10 khoản ưu tiên: bao phủ " +
        (100*cq.audit.amount_capture).toFixed(1) + "% dư nợ còn lại sau 28 ngày. Đây là độ bao phủ, không phải tiền tăng thu nhờ liên hệ."));
      const active = state.active_version === version.id;
      const control = node(
        active ? "span" : "button",
        active ? "● Đang sử dụng" : "Sử dụng phiên bản này",
        active ? "active-label" : "button",
      );
      if (!active)
        control.onclick = () =>
          action(async () => {
            await api("/models/" + version.id + "/activate", {
              method: "POST",
            });
            await refresh();
            notice(
              "Đã chọn phiên bản. Lập lại dự báo để sử dụng phiên bản này.",
            );
          }, control);
      row.append(info, control);
      if (!active) {
        const discard = node(
          "button",
          "Xóa phiên bản chưa dùng",
          "link-button",
        );
        discard.onclick = () =>
          action(async () => {
            if (
              !confirm(
                "Xóa phiên bản " +
                  version.id +
                  "? Không thể hoàn tác. Phiên bản của kế hoạch đã lưu sẽ được giữ.",
              )
            )
              return;
            await api(
              "/models/" +
                version.id +
                "?confirm=" +
                encodeURIComponent(version.id),
              { method: "DELETE" },
            );
            await refresh();
          }, discard);
        row.append(discard);
      }
      list.append(row);
    });
  }
  $("export-report").onclick = () => {
    if (!state) {
      connect();
      return;
    }
    download(
      new Blob(
        [
          JSON.stringify(
            {
              company: state.company,
              active_version: state.active_version,
              versions: state.versions,
            },
            null,
            2,
          ),
        ],
        { type: "application/json" },
      ),
      "agent1-kiem-dinh.json",
    );
  };
  const presets = {
    base: [0, 0, false], delay14: [14, 0, false], delay28: [28, 0, false],
    cost25: [0, 25, false], stress: [0, 0, true],
  };
  $("scenario-preset").onchange = () => {
    const custom = $("scenario-preset").value === "custom";
    $("scenario-custom").hidden = !custom;
    $("scenario-custom").disabled = !custom;
  };
  $("scenario-preset").onchange();
  $("forecast-form").onsubmit = (event) => {
    event.preventDefault();
    action(async () => {
      const chosen = $("scenario-preset").value;
      const custom = chosen === "custom";
      const [delay, expense, shared] = custom ? [
        Number($("delay-days").value), Number($("expense-change").value), $("common-risk").checked,
      ] : presets[chosen];
      lastForecast = await api("/predict", {
        method: "POST",
        body: JSON.stringify({
          cutoff: inputDate("forecast-cutoff"),
          opening_balance: Number($("opening-balance").value),
          horizon_weeks: Number($("horizon-weeks").value),
          payments_complete: $("forecast-complete").checked,
          delay_days: delay,
          include_operating: $("include-operating").checked,
          confirmed_weeks: $("confirmed-weeks").value.split(",").map(x => x.trim()).filter(Boolean).map(Number),
          cash_floor: Number($("cash-floor").value),
          delay_customer: custom && delay ? $("delay-customer").value.trim() || null : null,
          shared_customer_risk: shared,
          expense_multiplier: 1 + expense / 100,
        }),
      });
      renderForecast();
      if (window.innerWidth < 1120) $("forecast-output").scrollIntoView({block:"start", behavior:"smooth"});
    }, event.submitter);
  };
  $("compare-actuals").onclick = () =>
    action(async () => {
      if (!lastForecast) return;
      const when = inputDate("actuals-date");
      if (!when) {
        notice("Chọn ngày chốt sao kê.");
        return;
      }
      const r = await api(
        "/forecasts/" +
          lastForecast.id +
          "/actuals?asof=" +
          encodeURIComponent(when),
      );
      $("actuals-result").replaceChildren(
        node(
          "p",
          r.covered_weeks +
            "/" + lastForecast.weeks.length + " tuần có số dư đối soát · Sai số tuyệt đối trung bình: " +
            (r.mae == null ? "chưa đủ sao kê" : fmt.format(r.mae) + " VND") +
            " · Báo giả: " +
            r.false_alerts +
            " · Bỏ sót: " +
            r.misses,
        ),
        table(r.weeks, ["week", "actual_balance", "in_error", "out_error"]),
      );
    });
  function renderPaymentExplanation(explanation, plan, expectedProbability) {
    const panel = node("section", undefined, "t1-explanation");
    const available = explanation?.status === "available";
    const probability = expectedProbability ?? explanation?.probability;
    const validProbability = Number.isFinite(probability) && probability >= 0 && probability <= 1;
    panel.append(node("h3", "Vì sao có khả năng tất toán này?"));
    if (validProbability) panel.append(node("p", "Tất toán trong 4 tuần: " +
      (probability * 100).toLocaleString("vi-VN", {maximumFractionDigits: 2}) + "%", "t1-probability"));
    if (explanation?.cutoff) panel.append(node("p", "Ngày dự báo " + displayDate(explanation.cutoff), "muted"));
    if (!available) {
      panel.append(node("p", "Kế hoạch này chưa có lời giải thích đã được kiểm tra. Tạo kế hoạch mới để xem."));
      return panel;
    }
    if (explanation.scenario_shift_weeks) panel.append(node("p",
      "Kịch bản thu chậm thêm " + explanation.scenario_shift_weeks + " tuần."));

    // Fail closed, including for saved plans without diagnostics. Users only
    // receive reviewed drivers; raw SHAP and diagnostics stay in the saved plan.
    const checks = explanation.stability, support = explanation.plausibility, reference = explanation.reference;
    const factors = explanation.factors || [];
    const reconstructs = Number.isFinite(explanation.baseline_probability) && factors.every(f => Number.isFinite(f.contribution_pp)) &&
      Math.abs(explanation.baseline_probability + factors.reduce((total, f) => total + f.contribution_pp / 100, 0) - probability) <= 1e-10;
    const checked = validProbability && Number.isFinite(explanation.probability) &&
      Math.abs(probability - explanation.probability) <= 1e-10 && reconstructs &&
      checks?.checked === true && checks.sample_count >= 3 &&
      support?.status === "no_warning" && Number.isFinite(support.unsupported_fraction) &&
      support.unsupported_fraction >= 0 && support.unsupported_fraction <= 0.1 &&
      Number.isFinite(reference?.max_weighted_cdf_distance) && reference.max_weighted_cdf_distance >= 0 && reference.max_weighted_cdf_distance <= 0.1;
    const drivers = checked ? factors.filter(factor => {
      const stability = factor.stability, effect = factor.contribution_pp;
      const review = factor.business_review;
      if (review?.protocol !== "t1-business-evidence-v1" || review.status !== "eligible" ||
          review.feature !== factor.feature || review.value_unit !== factor.value_unit ||
          String(review.value) !== String(factor.value) ||
          !["amount", "age_days", "customer_delay_days", "company_delay_days"].includes(factor.feature)) return false;
      const actualValue = typeof factor.value === "number" ? Number.isFinite(factor.value)
        : factor.value_unit === "VND" && typeof factor.value === "string" && /^-?\d+(\.\d+)?$/.test(factor.value);
      if (!actualValue || !Number.isFinite(effect) || stability?.status !== "stable" ||
          (stability.reasons || []).length || !Number.isFinite(stability.min_contribution_pp) ||
          !Number.isFinite(stability.max_contribution_pp) || stability.min_contribution_pp > stability.max_contribution_pp ||
          effect < stability.min_contribution_pp - 1e-8 || effect > stability.max_contribution_pp + 1e-8) return false;
      return factor.direction === "increase" && effect >= 1 && stability.min_contribution_pp >= 1 ||
        factor.direction === "decrease" && effect <= -1 && stability.max_contribution_pp <= -1;
    }).sort((a, b) => Math.abs(b.contribution_pp) - Math.abs(a.contribution_pp)).slice(0, 3) : [];
    if (drivers.length) {
      const table = node("table", undefined, "t1-drivers"), head = node("thead"), header = node("tr"), body = node("tbody");
      ["Yếu tố ảnh hưởng", "Giá trị thực", "Chiều ảnh hưởng trong dự báo"].forEach(label => header.append(node("th", label)));
      head.append(header); table.append(head);
      const names = {
        customer_delay_days: "Mức chậm thanh toán ước tính của khách trước ngày lập",
        company_delay_days: "Mức chậm thanh toán chung của khách hàng trước ngày lập",
      };
      drivers.forEach(factor => {
        const row = node("tr"), reason = node("td");
        const value = paymentFactorValue(factor.value, factor);
        reason.append(node("p", factor.direction === "increase"
          ? "Góp phần tăng khả năng tất toán trong 4 tuần."
          : "Góp phần giảm khả năng tất toán trong 4 tuần.",
          factor.direction === "increase" ? "effect-increase" : "effect-decrease"));
        const evidence = paymentFactorEvidence(factor, explanation);
        if (evidence) reason.append(node("p", evidence, "t1-business-evidence"));
        row.append(node("td", names[factor.feature] || factor.label), node("td", value),
          reason);
        body.append(row);
      });
      table.append(body); panel.append(table);
      panel.append(node("p", "Các yếu tố này chỉ giải thích một phần dự báo, chưa chứng minh nguyên nhân khách hàng sẽ trả hoặc chưa trả.", "muted"));
      const largest = Math.max(...drivers.map(f => Math.abs(f.contribution_pp)));
      if (factors.some(f => Math.abs(f.contribution_pp) > largest && !drivers.includes(f))) {
        panel.append(node("p", "Chưa đủ cơ sở để diễn giải yếu tố có ảnh hưởng lớn nhất thành lý do nghiệp vụ.", "muted"));
      }
    } else panel.append(node("p", "Chưa đủ cơ sở để đưa ra lý do nghiệp vụ đáng tin cho dự báo này.", "muted"));
    const context = factors.filter(f => ["term_days", "customer_history_count", "amount"].includes(f.feature) &&
      f.value != null && !drivers.includes(f) && (Number.isFinite(f.value) ||
        f.value_unit === "VND" && typeof f.value === "string" && /^\d+$/.test(f.value)));
    if (context.length) {
      const information = node("div", undefined, "t1-input-context");
      information.append(node("h4", "Thông tin đầu vào"), node("p",
        "Các thông tin dưới đây được sử dụng trong dự báo; chưa đủ căn cứ coi chúng là lý do xác suất cao hay thấp.", "muted"));
      const names = {term_days: "Kỳ hạn thanh toán", customer_history_count: "Số hóa đơn khách đã tất toán trước ngày lập", amount: "Giá trị hóa đơn"};
      context.forEach(f => information.append(node("p", names[f.feature] + ": " + paymentFactorValue(f.value, f))));
      panel.append(information);
    }
    return panel;
  }
  function paymentFactorValue(value, factor) {
    if (factor.value_unit === "VND") return rankingNumber(value, "VND");
    if (["customer_delay_days", "company_delay_days"].includes(factor.feature)) {
      if (value === 0) return "đúng hạn";
      return (value < 0 ? "sớm hơn hạn " : "chậm hơn hạn ") + fmt.format(Math.abs(value)) + " ngày";
    }
    return value.toLocaleString("vi-VN", {maximumFractionDigits: 2}) + " " + factor.value_unit;
  }
  function paymentFactorEvidence(factor, explanation) {
    const e = factor.business_review?.evidence;
    if (e?.protocol !== "t1-business-evidence-v1") return null;
    if (["customer_delay_days", "company_delay_days"].includes(factor.feature)) {
      if (e.scope !== "settlements_available_before_invoice_issue" || !e.asof || !e.source_hash ||
          ![e.count, e.late_count, e.on_time_count, e.early_count].every(n => Number.isInteger(n) && n >= 0) ||
          e.count < 10 || e.late_count + e.on_time_count + e.early_count !== e.count) return null;
      return "Trong " + fmt.format(e.count) + " hóa đơn " +
        (factor.feature === "customer_delay_days" ? "của khách này " : "trong lịch sử doanh nghiệp ") +
        "đã được ghi nhận tất toán trước ngày lập hóa đơn này, " + fmt.format(e.late_count) + " hóa đơn được trả sau hạn.";
    }
    if (factor.feature === "age_days" && e.cutoff === explanation.cutoff && e.due_date &&
        Number.isInteger(e.overdue_days) && e.overdue_days >= 0) {
      return "Hóa đơn đến hạn ngày " + displayDate(e.due_date) + (e.overdue_days
        ? "; tại ngày dự báo đã quá hạn " + fmt.format(e.overdue_days) + " ngày." : ".");
    }
    return null;
  }
  function rankingNumber(value, unit) {
    if (value == null) return "—";
    if (unit === "VND" && typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
      const negative = value.startsWith("-"), [whole, fraction = ""] = value.replace(/^-/, "").split(".");
      // Round decimal text without first passing exact VND through Number.
      let cents = BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2));
      if ((fraction[2] || "0") >= "5") cents += 1n;
      const digits = (cents % 100n).toString().padStart(2, "0").replace(/0+$/, "");
      return (negative && cents ? "-" : "") + fmt.format(cents / 100n) + (digits ? "," + digits : "") + " VND";
    }
    return unit === "probability" ? (value * 100).toLocaleString("vi-VN", {maximumFractionDigits: 2}) + "%"
      : value.toLocaleString("vi-VN", {maximumFractionDigits: 2}) + (unit === "VND" ? " VND" : " " + unit);
  }
  function renderCollectionPolicy(policy) {
    const panel = node("div", undefined, "collection-policy");
    if (!policy) {
      panel.append(node("p", "Kế hoạch cũ chưa lưu chính sách xếp hạng. Tạo kế hoạch mới để xem lý do ưu tiên.", "muted"));
      return panel;
    }
    const excluded = policy.eligibility || {};
    panel.append(node("p", "Chính sách: " + policy.label + " · Hiển thị " + policy.displayed_count +
      "/" + policy.eligible_count + " khoản đủ điều kiện."),
      node("p", "Điểm = " + policy.formula + ". " + policy.selection.message, "muted"),
      node("p", "Loại khỏi danh sách: " + (excluded.writeoff_excluded || 0) + " khoản đã xóa nợ; " +
        (excluded.recent_contact_or_skip_excluded || 0) + " khoản vừa liên hệ hoặc tạm bỏ qua chưa đủ 7 ngày.", "muted"));
    return panel;
  }
  function renderRankingExplanation(invoice, plan) {
    const e = invoice.ranking_explanation, panel = node("section", undefined, "t1-explanation ranking-explanation");
    if (!e) {
      panel.append(node("p", "Kế hoạch này chưa lưu lý do xếp hạng. Tạo kế hoạch mới để xem."));
      return panel;
    }
    panel.append(node("h3", "Vì sao khoản này được ưu tiên trước?"),
      node("p", "Ưu tiên " + e.rank + "/" + e.eligible_count + " · Chính sách: " + e.label),
      node("p", "Điểm ưu tiên: " + rankingNumber(e.score, e.score_unit)),
      node("p", "Công thức: " + e.formula + ". " + e.selection.message),
      node("p", "Ngày dự báo " + displayDate(e.cutoff) + " · Phiên bản dự báo: " +
        (e.displayed_model_version || plan.model_version || "Theo lịch sử"), "muted"));
    const next = e.next;
    if (next) {
      panel.append(node("p", next.tied
        ? "Cùng điểm với hóa đơn " + next.invoice_id + "; đứng trước theo thứ tự bản ghi trong snapshot dữ liệu."
        : "Đứng trước hóa đơn " + next.invoice_id + " vì điểm cao hơn: " + rankingNumber(e.score, e.score_unit) +
          " so với " + rankingNumber(next.score, e.score_unit) + "."));
    } else panel.append(node("p", "Đây là khoản cuối trong danh sách đủ điều kiện."));
    if (e.tie_break.group_size > 1) panel.append(node("p", "Vị trí " + e.tie_break.position +
      "/" + e.tie_break.group_size + " trong nhóm cùng điểm; không ưu tiên thêm theo ngày quá hạn hoặc mã hóa đơn.", "muted"));
    panel.append(node("h4", "Nguồn xác suất"),
      node("p", (e.uses_probability ? "Dùng trong điểm: " : "Ước lượng tham khảo: ") + rankingNumber(e.triage_probability_4w, "probability") + " tất toán trong 4 tuần · " +
        e.probability_source.label + " (" + displayDate(e.probability_source.asof) + ")."),
      node("p", "Trên bảng dự báo: " + rankingNumber(e.displayed_probability_4w, "probability") + " tất toán trong 4 tuần."));
    if (!e.uses_probability) panel.append(node("p", "Chính sách này chỉ dùng dư nợ; các xác suất không tham gia điểm ưu tiên."));
    else if (e.probability_source.differs_from_displayed) panel.append(node("p",
      "Điểm dùng một ước lượng riêng từ lịch sử khách, khác nguồn với xác suất dự báo đang hiển thị. " + e.probability_source.detail,
      "ranking-source-note"));
    else panel.append(node("p", "Hai xác suất cùng nguồn lịch sử khách và cùng giả định tại ngày chốt.", "muted"));
    const list = node("ul");
    e.factors.forEach(f => {
      const value = f.unit === "boolean" ? (f.value ? "Có" : "Chưa ghi nhận")
        : f.unit === "date" ? (f.value ? displayDate(f.value) : "Chưa có") : rankingNumber(f.value, f.unit);
      let line = f.label + ": " + value + ". " + f.message;
      if (f.reliability != null) line += " Tỷ lệ giữ hứa ước tính: " + rankingNumber(f.reliability, "probability") + ".";
      list.append(node("li", line));
    });
    panel.append(node("h4", "Yếu tố tính điểm và thông tin xử lý"), list);
    const rules = node("ul"); e.business_rules.forEach(rule => rules.append(node("li", rule)));
    panel.append(node("h4", "Quy tắc lập danh sách"), rules, node("p", e.limitation, "muted"));
    if (e.probability_explanation) {
      const details = node("details");
      details.append(node("summary", "Vì sao có khả năng tất toán này?"),
        node("p", "Các yếu tố dưới đây giải thích khả năng tất toán, chưa giải thích toàn bộ thứ tự ưu tiên.", "muted"),
        renderPaymentExplanation(e.probability_explanation, plan, e.triage_probability_4w));
      panel.append(details);
    }
    return panel;
  }
  function collectionExplanationCell(invoice, plan, index, kind) {
    const ranking = kind === "ranking", cell = node("td"),
      button = node("button", ranking ? "Vì sao ưu tiên?" : "Giải thích"),
      detail = node("dialog", undefined, "t1-explanation-dialog"), close = node("button", "Đóng giải thích", "button"),
      label = ranking ? "Giải thích thứ tự ưu tiên hóa đơn " : "Giải thích xác suất tất toán hóa đơn ";
    detail.id = (ranking ? "ranking-explanation-" : "payment-explanation-") + index;
    detail.setAttribute("aria-label", label + invoice.invoice_id);
    close.type = "button"; close.onclick = () => detail.close();
    detail.onclose = () => { button.setAttribute("aria-expanded", "false"); detail.remove(); };
    button.type = "button"; button.setAttribute("aria-label", label + invoice.invoice_id);
    button.setAttribute("aria-expanded", "false"); button.setAttribute("aria-controls", detail.id);
    button.onclick = () => {
      if (detail.open) return;
      if (!detail.children.length) detail.append(close, node("h2", "Hóa đơn " + invoice.invoice_id),
        ranking ? renderRankingExplanation(invoice, plan) : renderPaymentExplanation(invoice.payment_explanation, plan, invoice.payment_probability_4w));
      document.body.append(detail); detail.showModal(); button.setAttribute("aria-expanded", "true");
    };
    cell.append(button); return cell;
  }
  function renderCollections(plan) {
    if (!plan.collections.length) {
      const eligibility = plan.collection_ranking?.eligibility;
      const open = plan.open_invoices ?? (eligibility ? eligibility.open_before_rules - (eligibility.writeoff_excluded || 0) : null);
      return node("p", open === 0 ? "Không có công nợ còn mở tại ngày dự báo."
        : open > 0 ? `Còn ${fmt.format(open)} hóa đơn đang mở; chưa có khoản đủ điều kiện trong hàng đợi thu nợ.` +
          (eligibility?.recent_contact_or_skip_excluded ? ` ${fmt.format(eligibility.recent_contact_or_skip_excluded)} khoản đang tạm hoãn do vừa liên hệ hoặc bỏ qua chưa đủ 7 ngày.` : "")
        : "Chưa có khoản nào trong hàng đợi thu nợ của kế hoạch này.", "muted");
    }
    const fields = ["collection_rank", "priority_score", "invoice_id", "customer_id", "outstanding", "overdue_days", "due_date",
      "promised_date", "promise_reliability", "disputed", "reason", "payment_probability_4w"];
    const result = table(plan.collections, fields, {
      promise_reliability: v => v == null ? "Chưa đủ lịch sử" : Math.round(v * 100) + "%",
      disputed: v => v ? "Có" : "Không",
      payment_probability_4w: v => (v * 100).toLocaleString("vi-VN", {maximumFractionDigits: 2}) + "%",
      outstanding: v => rankingNumber(v, "VND"),
      priority_score: v => rankingNumber(v, plan.collection_ranking?.score_unit || ""),
    });
    result.querySelector("thead tr").append(node("th", "Lý do ưu tiên"));
    result.querySelector("thead tr").append(node("th", "Giải thích xác suất"));
    const body = result.querySelector("tbody"), invoiceRows = [...body.children];
    invoiceRows.forEach((row, i) => {
      const invoice = plan.collections[i];
      row.append(collectionExplanationCell(invoice, plan, i, "ranking"), collectionExplanationCell(invoice, plan, i, "payment"));
    });
    return result;
  }
  function cashDetailTable(headers, rows) {
    const result = node("table"), head = node("thead"), heading = node("tr"), body = node("tbody");
    headers.forEach(label => heading.append(node("th", label)));
    head.append(heading);
    rows.forEach(values => {
      const row = node("tr");
      values.forEach(value => row.append(node("td", value)));
      body.append(row);
    });
    result.append(head, body);
    return result;
  }
  function cashPagedTable(host, headers, rows) {
    let offset = 0;
    const render = () => {
      const scroll = node("div", undefined, "table-scroll"), controls = node("div", undefined, "cash-pagination");
      scroll.append(cashDetailTable(headers, rows.slice(offset, offset + 20)));
      const previous = node("button", "← Trước", "button"), next = node("button", "Sau →", "button");
      previous.type = next.type = "button";
      previous.disabled = offset === 0; next.disabled = offset + 20 >= rows.length;
      previous.onclick = () => { offset -= 20; render(); };
      next.onclick = () => { offset += 20; render(); };
      const status = node("span", rows.length ? `${offset + 1}–${Math.min(offset + 20, rows.length)} / ${rows.length} dòng` : "Không có khoản phù hợp.");
      status.setAttribute("role", "status");
      controls.append(previous, status, next);
      host.replaceChildren(scroll, controls);
    };
    render();
  }
  function renderCashDecomposition(plan) {
    const panel = node("div", undefined, "cash-decomposition"), d = plan.cash_decomposition;
    if (!d) {
      panel.append(node("p", "Kế hoạch cũ chưa lưu phân rã dòng tiền. Tạo kế hoạch mới để xem theo hóa đơn, lịch chi và so sánh thu sớm/chậm."));
      return panel;
    }
    const money = value => fmt.format(Math.abs(value) < 0.000001 ? 0 : value) + " VND";
    let t5Ledger = null;
    if (plan.t5) {
      const ledger = node("details", undefined, "cash-details"), content = node("div");
      ledger.append(node("summary", "Nghĩa vụ T5: đã thanh toán, còn lại và khoản quá hạn"), content);
      cashPagedTable(content, ["Mã", "Đến hạn", "Loại", "Trạng thái", "Nghĩa vụ", "Đã thanh toán", "Còn lại", "Dự kiến còn lại"],
        plan.t5.obligations.map(r => [r.expense_id, displayDate(r.due_date), r.category, statusLabels[r.status] || r.status,
          money(r.obligation_amount), money(r.settled_amount), money(r.remaining_amount), r.forecast_date ? displayDate(r.forecast_date) : "—"]));
      t5Ledger = ledger;
      if (plan.t5.obligations.some(r => r.status === "overdue")) panel.append(node("p", "Khoản chi đến/quá hạn chưa thanh toán được đưa sang ngày làm việc kế tiếp. Có thể sửa ngày dự kiến hoặc nạp thanh toán thực tế để cập nhật phần còn lại.", "warning-box"));
      if (plan.t5.obligations.some(r => r.status === "awaiting_refund_date")) panel.append(node("p", "Có khoản hoàn quá ngày dự kiến nhận. Khoản này chưa được cộng vào dự thu; cần xác nhận ngày nhận mới.", "warning-box"));
    }
    panel.append(node("p", "Ngày " + displayDate(d.cutoff) + " · Phiên bản " + (d.model_version || "Theo lịch sử") + " · Phân rã số dư kỳ vọng.", "muted"));
    const f = d.risk_focus, risk = node("div", undefined, "cash-risk-focus");
    let message;
    if (f.trigger === "expected_shortfall") {
      message = `Tuần ${f.week} (${displayDate(f.date)}): số dư kỳ vọng thiếu ${money(f.expected_shortfall)} so với ngưỡng ${money(f.cash_floor)}.`;
    } else if (f.trigger === "simulation_only") {
      message = `Tuần ${f.week}: số dư kỳ vọng vẫn đạt ngưỡng, nhưng ít nhất 25% đường mô phỏng xuống dưới ngưỡng. Phân rã dưới đây giải thích số dư kỳ vọng; chưa phân rã xác suất cảnh báo.`;
    } else {
      message = `Chưa có cảnh báo dưới ngưỡng trong kỳ. Số dư kỳ vọng thấp nhất ở tuần ${f.week} (${displayDate(f.date)}).`;
    }
    risk.append(node("h3", "Vì sao cần chú ý tuần " + f.week + "?"), node("p", message));
    const bridge = node("div", undefined, "cash-bridge");
    [["Số dư đầu", f.opening_balance], ["+ Thu đến tuần " + f.week, f.cumulative_cash_in],
      ["− Chi đến tuần " + f.week, f.cumulative_cash_out], ["= Số dư tuần " + f.week, f.balance]].forEach(([label, value]) => {
      const item = node("div"); item.append(node("span", label), node("strong", money(value))); bridge.append(item);
    });
    risk.append(bridge);
    const customers = f.largest_unreceived_customers.filter(row => row.unreceived > 0.000001);
    if (customers.length) risk.append(node("p", "Dư nợ chưa dự thu đến hết tuần này: " + money(f.unreceived_ar) + ". Các khách có phần chưa thu lớn nhất: " +
      customers.map(row => row.customer_id + " · " + money(row.unreceived)).join("; ") + ". Kế hoạch còn phụ thuộc vào việc thu các khoản này."));
    if (f.largest_scheduled_outflows.length) risk.append(node("p", "Các khoản chi đã biết lớn nhất đến tuần này: " +
      f.largest_scheduled_outflows.map(row => row.expense_id + " · " + displayDate(row.date) + " · " + money(row.amount)).join("; ") + "."));
    if (f.unknown_outflow_weeks.length) risk.append(node("p", "Chưa xác nhận đủ lịch chi ở tuần " + f.unknown_outflow_weeks.join(", ") + "; số dư có thể thiếu các khoản chi chưa nạp.", "warning-box"));
    panel.append(risk, node("h3", "Tiền dự thu đến từ khoản nào?"), node("p", d.scope.description));
    const filters = node("div", undefined, "cash-filters");
    const weekLabel = node("label", "Kỳ cần xem"), weekSelect = node("select");
    const all = node("option", "Toàn kỳ " + d.weeks.length + " tuần"); all.value = "all"; weekSelect.append(all);
    d.weeks.forEach(week => { const option = node("option", `Tuần ${week.week} · ${displayDate(week.date)}`); option.value = String(week.week); weekSelect.append(option); });
    weekSelect.setAttribute("aria-label", "Kỳ phân rã dòng tiền"); weekLabel.append(weekSelect);
    const groupLabel = node("label", "Nhóm dự thu"), group = node("select");
    [["invoices", "Theo hóa đơn"], ["customers", "Theo khách hàng"]].forEach(([value, label]) => { const option = node("option", label); option.value = value; group.append(option); });
    group.setAttribute("aria-label", "Nhóm đóng góp dự thu"); groupLabel.append(group);
    const searchLabel = node("label", "Tìm mã hóa đơn/khách"), search = node("input");
    search.type = "search"; search.setAttribute("aria-label", "Tìm khoản dự thu"); searchLabel.append(search);
    filters.append(weekLabel, groupLabel, searchLabel);
    const summary = node("p"), receipts = node("div"), expenses = node("div");
    const expenseDetails = node("details", undefined, "cash-details");
    expenseDetails.append(node("summary", "Lịch chi đã biết và số tiền sau kịch bản"), expenses);
    const renderRows = () => {
      const week = weekSelect.value === "all" ? null : Number(weekSelect.value);
      const selected = week ? [d.weeks[week - 1]] : d.weeks;
      const sum = field => selected.reduce((total, row) => total + (row[field] || 0), 0);
      summary.textContent = "Dự thu " + money(sum("cash_in")) + " = công nợ mở " + money(sum("ar_in")) + " + bán thu ngay " + money(sum("cash_sale_in")) + " + bán chịu mới " + money(sum("new_credit_in")) + " + hoàn theo hồ sơ T5 " + money(sum("obligation_in")) + ". Dự chi " + money(sum("cash_out")) + " = lịch đã biết " + money(sum("scheduled_out")) + " + chi biến đổi bổ sung " + money(sum("variable_cost_topup")) + ".";
      const byCustomer = group.value === "customers", query = search.value.trim().toLocaleLowerCase("vi");
      const source = (byCustomer ? d.customers : d.invoices).filter(row =>
        ((row.invoice_id || "") + " " + row.customer_id).toLocaleLowerCase("vi").includes(query));
      const amountFor = row => week ? row.expected_by_week[week - 1] : row.expected_in;
      const sorted = [...source].sort((a, b) => amountFor(b) - amountFor(a));
      const rows = sorted.map(row => {
        const pending = Math.max(0, row.outstanding - (week ? row.expected_by_week.slice(0, week).reduce((sum, value) => sum + value, 0) : row.expected_in));
        return [byCustomer ? row.customer_id : row.invoice_id, byCustomer ? row.invoice_count : row.customer_id,
          money(row.outstanding), money(amountFor(row)), money(pending)];
      });
      cashPagedTable(receipts, [byCustomer ? "Khách hàng" : "Hóa đơn", byCustomer ? "Số hóa đơn" : "Khách hàng", "Dư nợ tại ngày chốt", week ? "Dự thu tuần " + week : "Dự thu trong kỳ", week ? "Chưa dự thu đến tuần " + week : "Chưa dự thu trong kỳ"], rows);
      cashPagedTable(expenses, ["Mã khoản chi", "Ngày", "Loại chi", "Còn phải chi", "Sau kịch bản"],
        d.outflows.filter(row => !week || row.week === week).map(row => [row.expense_id, displayDate(row.date), row.category, money(row.original_amount), money(row.amount)]));
    };
    weekSelect.value = "all"; group.value = "invoices"; search.value = "";
    weekSelect.onchange = group.onchange = search.oninput = renderRows;
    panel.append(filters, summary, receipts, node("p", "Số tiền là kỳ vọng phân bổ theo tuần, không phải cam kết thu hoặc xác suất tất toán 4 tuần. Thu hoạt động và hóa đơn chưa phát hành nằm ở nhóm riêng.", "muted"), expenseDetails);
    renderRows();
    if (d.inflows?.length) {
      const refunds = node("details", undefined, "cash-details"), content = node("div");
      refunds.append(node("summary", "Tiền hoàn theo hồ sơ đã duyệt"), content);
      cashPagedTable(content, ["Mã", "Ngày dự kiến nhận", "Số còn nhận", "Nguồn hồ sơ"],
        d.inflows.map(r => [r.expense_id, displayDate(r.date), money(r.amount), r.source]));
      panel.append(refunds);
    }
    const weekly = node("details", undefined, "cash-details"), weeklyScroll = node("div", undefined, "table-scroll");
    weekly.append(node("summary", "Đối chiếu thu, chi và thay đổi số dư từng tuần"), weeklyScroll);
    weeklyScroll.append(cashDetailTable(["Tuần", "Số dư đầu tuần", "+ Công nợ mở", "+ Bán thu ngay", "+ Bán chịu mới", "+ Hoàn theo hồ sơ T5", "− Lịch chi", "− Chi biến đổi bổ sung", "Thay đổi số dư", "Số dư cuối tuần"],
      d.weeks.map(w => [w.week, ...[w.opening_balance, w.ar_in, w.cash_sale_in, w.new_credit_in, w.obligation_in || 0, w.scheduled_out, w.variable_cost_topup, w.net_change, w.balance].map(money)])));
    panel.append(weekly, node("h3", "Nếu tiền thu sớm hoặc chậm 2 tuần?"));
    const comparison = d.timing_comparison, comparisonScroll = node("div", undefined, "table-scroll");
    comparisonScroll.append(cashDetailTable(["Kịch bản", "Dự thu công nợ", "Số dư thấp nhất", "Chênh mức thấp nhất", "Số dư cuối kỳ", "Tuần đầu dưới ngưỡng", "Thu bị đẩy ra ngoài kỳ"],
      comparison.scenarios.map(s => [s.label, money(s.ar_in), money(s.minimum_balance), money(s.minimum_balance_change), money(s.closing_balance), s.first_below_floor_week || "Không có", money(s.receipts_pushed_beyond_horizon)])));
    panel.append(comparisonScroll);
    const timingDetails = node("details", undefined, "cash-details"), timingScroll = node("div", undefined, "table-scroll");
    const [current, early, late] = comparison.scenarios;
    timingScroll.append(cashDetailTable(["Tuần", "Ngày", "Số dư đang xem", "Thu sớm", "Chênh thu sớm", "Thu chậm", "Chênh thu chậm"],
      current.weeks.map((w, i) => [w.week, displayDate(w.date), ...[w.balance, early.weeks[i].balance, early.weeks[i].balance_change, late.weeks[i].balance, late.weeks[i].balance_change].map(money)])));
    timingDetails.append(node("summary", "So sánh số dư từng tuần"), timingScroll);
    panel.append(timingDetails);
    comparison.assumptions.forEach(note => panel.append(node("p", note, "muted")));
    const assumptions = node("details", undefined, "cash-details");
    assumptions.append(node("summary", "Cách phân bổ tiền và giới hạn mô phỏng"));
    d.assumptions.forEach(note => assumptions.append(node("p", note)));
    panel.append(assumptions);
    if (t5Ledger) panel.append(t5Ledger);
    return panel;
  }
  function renderForecast() {
    const r = lastForecast;
    $("actuals-result").replaceChildren();
    setDate("actuals-date", localDate);
    $("forecast-output").hidden = false;
    $("forecast-empty").hidden = true;
    $("export-forecast").disabled = false;
    $("forecast-mode").textContent =
      r.mode === "company_trained" ? "PHIÊN BẢN RIÊNG" : "THEO LỊCH SỬ";
    $("kpi-outstanding").textContent = short(r.outstanding);
    $("kpi-balance").textContent = short(r.minimum_balance);
    $("kpi-invoices").textContent =
      fmt.format(r.open_invoices) + " hóa đơn · ngày " + displayDate(r.cutoff);
    const scenario = r.scenario || {};
    const isBase = !scenario.delay_days && (scenario.expense_multiplier ?? 1) === 1 && !scenario.shared_customer_risk;
    const period = r.weeks.length;
    $("forecast-period").textContent = period + " tuần · " + displayDate(r.cutoff);
    $("kpi-horizon").textContent = "Trong " + period + " tuần · VND";
    const total = (plan, field) => plan.weeks.reduce((sum, week) => sum + week[field], 0);
    $("forecast-totals").replaceChildren(...[
      ["Dự thu", total(r, "cash_in")], ["Dự chi", total(r, "cash_out")],
      ["Số dư thấp nhất", r.minimum_balance],
    ].map(([label, value]) => {
      const item = node("div"); item.append(node("span", label), node("strong", short(value))); return item;
    }));
    $("forecast-comparison").replaceChildren();
    if (isBase) baselineForecast = r;
    else {
      const summary = [scenario.delay_days ? `Thu chậm ${scenario.delay_days} ngày${scenario.delay_customer ? " · " + scenario.delay_customer : ""}` : null,
        (scenario.expense_multiplier ?? 1) !== 1 ? `Chi ${Math.round(scenario.expense_multiplier * 100)}% kế hoạch` : null,
        scenario.shared_customer_risk ? "Rủi ro chung theo khách" : null].filter(Boolean).join(" · ");
      $("forecast-comparison").append(node("p", summary, "scenario-line"));
      const base = baselineForecast;
      if (base && base.weeks.length === period && ["cutoff", "dataset_hash", "opening_balance", "cash_floor", "model_version", "operating_included"].every(k => base[k] === r[k]) &&
          JSON.stringify(base.confirmed_weeks) === JSON.stringify(r.confirmed_weeks)) {
        $("forecast-comparison").append(node("p", "So với kế hoạch gốc · Chênh thu " + short(total(r,"cash_in")-total(base,"cash_in")) +
          " · Chênh chi " + short(total(r,"cash_out")-total(base,"cash_out")) +
          " · Chênh số dư thấp nhất " + short(r.minimum_balance-base.minimum_balance), "scenario-line"));
      }
    }
    const assumptions = [...(r.assumptions || [])];
    if (r.inference_ms != null) assumptions.push(`Thời gian tính dự báo ${(r.inference_ms / 1000).toFixed(2)} giây. Phiên bản đã học chỉ tính xác suất và mô phỏng cho công nợ đang mở.`);
    assumptions.push(r.operating_included ? "Chi gồm lịch cố định T5 đã nạp và chi hoạt động ước lượng từ lịch sử sao kê."
      : "Chi chỉ gồm lịch cố định T5 đã nạp; chưa bao gồm chi hoạt động phát sinh khác.");
    if (r.unknown_outflow_weeks?.length) assumptions.push("Chưa xác nhận lịch cố định T5 ở tuần " + r.unknown_outflow_weeks.join(", ") + ".");
    $("forecast-assumptions").replaceChildren(...assumptions.map(a => node("p", a)));
    $("forecast-customers").replaceChildren(...[...new Set((r.cash_decomposition?.customers || r.collections).map(x => x.customer_id))].map(id => {
      const option = node("option"); option.value = id; return option;
    }));
    $("forecast-alerts").replaceChildren();
    if (r.alerts.length)
      $("forecast-alerts").append(
        node(
          "p",
          r.alerts.length +
            " tuần có nguy cơ dưới mức tối thiểu. Kiểm tra kế hoạch từ tuần " +
            r.alerts[0].week +
            ".",
          "warning-box",
        ),
      );
    if (
      r.payment_delay_shift_days != null &&
      Math.abs(r.payment_delay_shift_days) >= 7
    )
      $("forecast-alerts").append(
        node(
          "p",
          "So với 12 tuần trước, trung vị số ngày trả trễ trong 4 tuần gần nhất thay đổi " +
            r.payment_delay_shift_days +
            " ngày. Hãy kiểm tra lại lịch thu.",
          "warning-box",
        ),
      );
    if (r.stale_model)
      $("forecast-alerts").append(
        node(
          "p",
          "Dữ liệu đã thay đổi so với phiên bản học. Xem xét kiểm định lại.",
          "warning-box",
        ),
      );
    $("forecast-table").replaceChildren(
      table(
        r.weeks,
        [
          "week",
          "date",
          "cash_in",
          "cash_out",
          "balance",
          "low",
          "high",
          "outflow_status",
          "below_floor_probability",
        ],
        {
          outflow_status: (v) =>
            ({
              unknown: "Chưa biết",
              confirmed_zero: "Đã xác nhận 0",
              scheduled: "Đã xác nhận đủ lịch",
              scheduled_unconfirmed: "Có khoản chi, chưa xác nhận đủ",
            })[v] || "Chưa biết",
          below_floor_probability: (v) =>
            v == null ? "—" : Math.round(v * 100) + "%",
        },
      ),
    );
    $("collection-policy").replaceChildren(renderCollectionPolicy(r.collection_ranking));
    $("collections-table").replaceChildren(renderCollections(r));
    $("cash-decomposition").replaceChildren(renderCashDecomposition(r));
    drawVisibleChart();
    notice("Đã mở kế hoạch " + period + " tuần · " + displayDate(r.cutoff) + ".");
  }
  function drawVisibleChart() {
    if (!lastForecast || !["overview", "forecast"].includes(currentView))
      return;
    const target = $(currentView + "-chart");
    if (!target || target.clientWidth < 1 || typeof uPlot === "undefined")
      return;
    charts.get(target.id)?.destroy();
    target.replaceChildren();
    const weeks = lastForecast.weeks;
    const theme = getComputedStyle(target);
    const color = (token, fallback) => theme.getPropertyValue(token).trim() || fallback;
    const axisFont = "11px " + theme.fontFamily;
    // The probability band must remain translucent so it cannot cover the
    // expected balance line drawn underneath it. Theme tokens use six-digit hex.
    const bandFill = color("--kt-accent-soft", "#d6e2c2").replace(/^#[0-9a-f]{6}$/i, hex => hex + "80");
    const plot = new uPlot(
      {
        width: target.clientWidth,
        height: Math.min(330, Math.max(265, window.innerHeight * 0.36)),
        padding: [15, 15, 0, 5],
        series: [
          {
            label: "Ngày",
            value: (_u, v) =>
              v ? displayDate(new Date(v * 1000).toISOString()) : "—",
          },
          {
            label: "Số dư",
            stroke: color("--kt-accent", "#1b6148"),
            width: 2.5,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
          {
            label: "P10",
            stroke: color("--kt-field-line", "#a6b990"),
            width: 1,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
          {
            label: "P90",
            stroke: color("--kt-field-line", "#a6b990"),
            width: 1,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
        ],
        bands: [{ series: [3, 2], fill: bandFill }],
        scales: {
          x: { time: true },
          y: {
            range: (_u, min, max) => [
              Math.min(0, min) - Math.max(1, (max - min) * 0.1),
              Math.max(1, max + Math.max(1, (max - min) * 0.1)),
            ],
          },
        },
        axes: [
          {
            stroke: color("--muted", "#7f8b78"),
            grid: { show: false },
            ticks: { show: false },
            font: axisFont,
            space: 70,
            values: (_u, ticks) =>
              ticks.map((t) => displayDate(new Date(t * 1000).toISOString())),
          },
          {
            stroke: color("--muted", "#7f8b78"),
            grid: { stroke: color("--line", "#e6eadf"), width: 1 },
            ticks: { show: false },
            font: axisFont,
            size: 60,
            values: (_u, ticks) => ticks.map(short),
          },
        ],
        legend: { show: true },
        cursor: { drag: { x: false, y: false } },
      },
      [
        weeks.map((w) => Date.parse(w.date + "T00:00:00Z") / 1000),
        weeks.map((w) => w.balance),
        weeks.map((w) => w.low),
        weeks.map((w) => w.high),
      ],
      target,
    );
    charts.set(target.id, plot);
  }
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawVisibleChart, 150);
  });
  $("export-forecast").onclick = () => action(async () => {
    if (!lastForecast) return;
    const blob = await api("/forecasts/" + encodeURIComponent(lastForecast.id) + "/xlsx");
    download(blob, "agent1-ke-hoach-" + displayDate(lastForecast.cutoff) + "-" + lastForecast.weeks.length + "t.xlsx");
  }, $("export-forecast"));
  switchView(
    titles[location.hash.slice(1)] ? location.hash.slice(1) : "overview",
  );
  if (hasPortalTicket) redeemPortalTicket(portalTicket);
  else restoreSession();
})();
