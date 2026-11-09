"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  // Retain the originating portal across Agent 1 pages and standalone-tab reloads.
  let portalOrigin = new URLSearchParams(location.search).get("portal");
  try {
    if (!portalOrigin) portalOrigin = sessionStorage.getItem("agent1-portal-origin");
    const portal = new URL(portalOrigin);
    if (portal.protocol === "http:" && ["127.0.0.1", "localhost"].includes(portal.hostname) &&
        !portal.username && !portal.password && portal.origin !== location.origin) {
      $("portal-return").href = portal.origin + "/#overview";
      $("portal-return").hidden = false;
      try { sessionStorage.setItem("agent1-portal-origin", portal.origin); } catch (e) { /* private mode */ }
    }
  } catch (e) { /* No portal context when Agent 1 is opened independently. */ }
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
    training: "Thiết lập & kiểm định",
    forecast: "Dự báo & kịch bản",
    guide: "Hướng dẫn dữ liệu",
  };
  const labels = {
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
    currency: "Đồng tiền",
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
  };
  let token = "",
    state = null,
    preview = null,
    lastForecast = null,
    baselineForecast = null,
    currentView = "overview",
    manualMapping = {},
    poll = null;
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
    "promised_date", "promise_date", "start_date", "end_date", "cutoff"]);
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
    if (!token) {
      connect();
      throw new Error("Kết nối doanh nghiệp để tiếp tục.");
    }
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", "Bearer " + token);
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const response = await fetch("/v1" + path, {
      ...options,
      headers,
      cache: "no-store",
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
  $("connect-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.submitter || $("connect-form").querySelector("button[type=submit]");
    button.disabled = true;
    token = $("token-input").value.trim();
    try {
      const access = await api("/access");
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
      $("connect-error").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
  // Inside the platform shell: the shell sends the access key once, it is kept in memory only like a typed key.
  if (window.parent !== window) {
    window.addEventListener("message", (event) => {
      const data = event.data || {};
      if (event.source !== window.parent || data.type !== "platform-access-key" || token) return;
      if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(event.origin)) return;
      $("token-input").value = String(data.key || "");
      $("connect-form").requestSubmit();
    });
    window.parent.postMessage({ type: "platform-ready", agent: "agent1" }, "*");
  }
  $("logout").onclick = () => {
    token = "";
    state = null;
    clearTimeout(poll);
    location.reload();
  };
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
  async function refresh() {
    const next = await api("/workspace");
    if (state && state.dataset_hash !== next.dataset_hash) {
      $("train-complete").checked = false;
      $("forecast-complete").checked = false;
    }
    if (
      state &&
      (state.dataset_hash !== next.dataset_hash ||
        state.active_version !== next.active_version) &&
      lastForecast
    )
      clearForecast();
    state = next;
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
                    outflows: "khoản chi",
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
  $("load-pending").onclick = () =>
    action(async () => {
      const r = await api("/reconciliation");
      $("manual-allocation").hidden = !r.pending_count;
      $("manual-allocation").open = false;
      if (!r.pending_count) {
        $("pending-rows").replaceChildren(node("p", "Các khoản thu trong phạm vi đã được ghép. Bạn không cần phân bổ thêm."));
        return;
      }
      const grid = table(r.pending, ["bank_id", "account", "date", "amount", "unallocated"]);
      const header = grid.querySelector("thead tr");
      if (header) header.append(node("th", "Xử lý ngoại lệ"));
      grid.querySelectorAll("tbody tr").forEach((tr, i) => {
        const item = r.pending[i];
        const cell = node("td"), choose = node("button", "Ghép khoản này", "link-button");
        choose.type = "button";
        choose.onclick = () => {
          $("allocate-bank").value = item.bank_id;
          $("allocate-amount").value = item.unallocated;
          $("allocate-id").value = "P-" + crypto.randomUUID();
          $("allocate-invoice").value = "";
          $("manual-allocation").open = true;
          $("allocate-invoice").focus();
        };
        cell.append(choose); tr.append(cell);
      });
      $("pending-rows").replaceChildren(
        node("p", fmt.format(r.unallocated) + " VND · " + r.pending_count + " khoản chưa ghép. Có thể bổ sung bằng CSV hoặc để chờ xác minh."), grid);
    }, $("load-pending"));
  $("allocate-form").onsubmit = (e) => {
    e.preventDefault();
    action(async () => {
      await api("/allocations", {
        method: "POST",
        body: JSON.stringify({
          payment_id: $("allocate-id").value,
          bank_id: $("allocate-bank").value,
          invoice_id: $("allocate-invoice").value,
          amount: Number($("allocate-amount").value),
        }),
      });
      await refresh();
      $("load-pending").click();
      notice("Đã ghi phân bổ và cập nhật số còn phải thu.");
    }, e.submitter);
  };
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
          select.onchange = () => {
            manualMapping[field] = select.value;
            preview = null;
            $("commit-import").disabled = true;
          };
          label.append(select);
          return label;
        }),
      );
      $("mapping-panel").hidden = false;
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
          " dòng. Dữ liệu cũ có cùng mã đã được cập nhật.",
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
    const blob = await api("/templates/" + kind);
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
    if (r.unknown_outflow_weeks?.length) assumptions.push("Lịch chi chưa biết ở tuần " + r.unknown_outflow_weeks.join(", ") + ".");
    $("forecast-assumptions").replaceChildren(...assumptions.map(a => node("p", a)));
    $("forecast-customers").replaceChildren(...[...new Set(r.collections.map(x => x.customer_id))].map(id => {
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
              scheduled: "Có lịch",
            })[v] || "Chưa biết",
          below_floor_probability: (v) =>
            v == null ? "—" : Math.round(v * 100) + "%",
        },
      ),
    );
    $("collections-table").replaceChildren(
      r.collections.length
        ? table(
            r.collections,
            [
              "invoice_id",
              "customer_id",
              "outstanding",
              "overdue_days",
              "due_date",
              "promised_date",
              "promise_reliability",
              "disputed",
              "reason",
              "payment_probability_4w",
            ],
            {
              promise_reliability: (v) =>
                v == null ? "Chưa đủ lịch sử" : Math.round(v * 100) + "%",
              disputed: (v) => (v ? "Có" : "Không"),
              payment_probability_4w: (v) => (v * 100).toFixed(0) + "%",
            },
          )
        : node("p", "Không có công nợ còn mở tại ngày dự báo.", "muted"),
    );
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
            stroke: "#1b6148",
            width: 2.5,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
          {
            label: "P10",
            stroke: "#a6b990",
            width: 1,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
          {
            label: "P90",
            stroke: "#a6b990",
            width: 1,
            value: (_u, v) => (v == null ? "—" : short(v)),
          },
        ],
        bands: [{ series: [3, 2], fill: "#d6e2c24d" }],
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
            stroke: "#7f8b78",
            grid: { show: false },
            ticks: { show: false },
            font: "10px Segoe UI",
            space: 70,
            values: (_u, ticks) =>
              ticks.map((t) => displayDate(new Date(t * 1000).toISOString())),
          },
          {
            stroke: "#7f8b78",
            grid: { stroke: "#e6eadf", width: 1 },
            ticks: { show: false },
            font: "10px Segoe UI",
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
})();
