"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const AGENT_LABEL = { agent1: "Agent 1", agent2: "Agent 2", agent3: "Agent 3", agent4: "Agent 4" };
  const WORKSPACE_LABEL = { agent1: "Dòng tiền", agent2: "Kiểm soát", agent3: "Thuế", agent4: "Hỏi đáp" };
  const STATE_TEXT = { running: "Đang chạy", starting: "Đang khởi động", stopped: "Đang tắt", "busy-port": "Cổng bị chiếm" };
  const CHECK_TEXT = { ready: "Sẵn sàng ghi", error: "Có lỗi", offline: "Agent tắt", done: "Đã ghi", skipped: "Bỏ qua", stale: "Chờ kiểm tra lại" };
  let state = null;
  let profileSaving = false;
  let profileVersion = 0;
  let profileErrors = {};
  let currentAgent = null;
  const offlineFailures = { agent1: 0, agent2: 0, agent3: 0, agent4: 0 };
  let intakeStage = "choose";
  let token = "";
  try { token = sessionStorage.getItem("kt-session") || ""; } catch (e) { token = ""; }

  const sidebarMedia = window.matchMedia("(max-width: 900px)");
  let desktopSidebarOpen = true;
  let mobileSidebarOpen = false;
  try { desktopSidebarOpen = localStorage.getItem("kt-sidebar-collapsed") !== "1"; } catch (e) { /* private mode */ }

  function renderSidebar() {
    const mobile = sidebarMedia.matches;
    const open = mobile ? mobileSidebarOpen : desktopSidebarOpen;
    const sidebar = $("sidebar");
    const toggle = $("menu-toggle");
    document.querySelector(".shell").classList.toggle("sidebar-collapsed", !mobile && !open);
    document.body.classList.toggle("sidebar-open", mobile && open);
    document.body.classList.toggle("desktop-sidebar-open", !mobile && open);
    sidebar.classList.toggle("open", mobile && open);
    sidebar.inert = !open;
    sidebar.setAttribute("aria-hidden", String(!open));
    $("nav-backdrop").hidden = !mobile || !open;
    toggle.setAttribute("aria-expanded", String(open));
    const label = open ? (mobile ? "Đóng menu điều hướng" : "Thu gọn menu điều hướng") : "Mở menu điều hướng";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
  }

  function setSidebarOpen(open, returnFocus = false) {
    if (sidebarMedia.matches) mobileSidebarOpen = open;
    else {
      desktopSidebarOpen = open;
      try { localStorage.setItem("kt-sidebar-collapsed", open ? "0" : "1"); } catch (e) { /* private mode */ }
    }
    renderSidebar();
    if (returnFocus) $("menu-toggle").focus();
  }

  function setToken(value) {
    token = value || "";
    try { token ? sessionStorage.setItem("kt-session", token) : sessionStorage.removeItem("kt-session"); } catch (e) { /* private mode */ }
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat(Infinity)) if (c !== null && c !== undefined && c !== false) node.append(c.nodeType ? c : String(c));
    return node;
  }

  function toast(message, error = false) {
    const t = $("toast");
    t.textContent = message;
    t.className = "toast" + (error ? " error" : "");
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.hidden = true), error ? 7000 : 3500);
  }

  let activeLoadingCount = 0;
  function startLoading() {
    activeLoadingCount++;
    const bar = $("top-progress");
    if (bar) bar.classList.add("active");
  }
  function stopLoading() {
    activeLoadingCount = Math.max(0, activeLoadingCount - 1);
    if (activeLoadingCount === 0) {
      const bar = $("top-progress");
      if (bar) bar.classList.remove("active");
    }
  }

  async function api(path, options = {}) {
    const isSilent = options.silent || path.includes('/health');
    if (!isSilent) startLoading();
    try {
      const headers = { "X-Platform": "1", ...(options.headers || {}) };
      if (token) headers["X-Session"] = token;
      if (options.json !== undefined) {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.json);
      }
      const res = await fetch(path, { ...options, headers, cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 401 && data.locked) {
          setToken("");
          if (state) { state.intake.unlocked = false; state.pending = []; state.batches = []; render(); }
        }
        const err = new Error(data.error || "Yêu cầu không thành công (" + res.status + ").");
        err.locked = Boolean(data.locked);
        throw err;
      }
      return data;
    } finally {
      if (!isSilent) stopLoading();
    }
  }

  const sizeText = (n) => (n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB");
  const agentById = (id) => state.agents.find((a) => a.id === id);
  const dmy = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "");
  const stamp = (s) => (s ? dmy(s.slice(0, 10)) + " " + s.slice(11, 16) : "");
  const monogram = (company) => company.split(/\s+/).filter(Boolean).slice(-2).map((word) => [...word][0]).join("").toUpperCase() || "—";

  // ------------------------------------------------------------------ render
  function renderTop() {
    const c = state.company;
    const configured = Boolean(c.legal_name && c.code);
    $("company-name").textContent = configured ? c.legal_name : "Chưa cấu hình doanh nghiệp";
    $("company-meta").textContent = configured ? [c.tax_code && "MST " + c.tax_code, "Mã " + c.code].filter(Boolean).join(", ") : "Bấm để nhập thông tin";
    $("masthead-period").textContent = new Intl.DateTimeFormat("vi-VN", { month: "long", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
    $("sidebar-monogram").textContent = c.code ? c.code.slice(0, 2) : monogram(c.legal_name || "");
    $("sidebar-company").textContent = c.legal_name || "Chưa cấu hình doanh nghiệp";
    $("company-chip").title = c.legal_name || "Hồ sơ doanh nghiệp";
    const p = state.package;
    $("package-chip").hidden = !p;
    if (p) $("package-chip").textContent = "Gói v" + p.version + ", niêm phong " + stamp(p.sealed_at).slice(0, 10);
    $("lock-badge").hidden = state.intake.unlocked;
    const n = state.pending.length;
    $("pending-count").hidden = !n;
    $("pending-count").textContent = n;
  }

  function renderConfig() {
    const c = state.company;
    const form = $("company-form");
    if (!form.dataset.dirty) for (const [k, v] of Object.entries(c)) if (form.elements[k]) form.elements[k].value = v ?? "";
    profileText("saved-at", c.updated_at ? "Lưu lần cuối " + c.updated_at : "Chưa có lần lưu nào");
    const locked = Boolean(state.package) && !state.intake.unlocked;
    $("config-lock").hidden = !locked;
    for (const input of form.elements) if (input.name) input.disabled = locked || profileSaving;
    form.querySelector("button[type=submit]").disabled = locked || profileSaving;
    $("profile-reset").disabled = !form.dataset.dirty || profileSaving;
    form.setAttribute("aria-busy", String(profileSaving));
    profileText("profile-submit", profileSaving ? "Đang lưu hồ sơ…" : "Lưu hồ sơ");
    const configured = Boolean(c.legal_name && c.code);
    const dirty = Boolean(form.dataset.dirty);
    const label = locked ? "Đang được bảo vệ" : profileSaving ? "Đang lưu hồ sơ" : dirty ? "Có thay đổi chưa lưu" : configured ? "Đã lưu" : "Chưa thiết lập";
    profileText("profile-status", label);
    $("profile-status").dataset.state = locked ? "locked" : dirty ? "draft" : configured ? "saved" : "empty";
    profileText("profile-save-note", profileSaving ? "Đang lưu, vui lòng chờ" : locked ? "Mở khóa để lưu chỉnh sửa" : dirty ? "Có thay đổi chưa lưu" : "Thông tin được lưu trên máy này");
    updateProfileSummary();
  }

  function profileText(id, text) { if ($(id).textContent !== text) $(id).textContent = text; }

  function profileValues() {
    const form = $("company-form");
    return Object.fromEntries([...form.elements].filter((input) => input.name).map((input) => [input.name, input.value]));
  }

  function updateProfileSummary() {
    const c = profileValues();
    profileText("profile-summary-title", c.legal_name.trim() || "Chưa có doanh nghiệp");
    profileText("profile-summary-state", $("company-form").dataset.dirty ? "Bản nháp chưa lưu" : state.company.code ? "Thông tin đã lưu" : "Chưa thiết lập");
    profileText("profile-summary-code", c.code.trim() || "Chưa nhập");
    profileText("profile-summary-tax", c.tax_code.trim() || "Chưa nhập");
    profileText("profile-monogram", c.code.trim().slice(0, 2).toUpperCase() || monogram(c.legal_name));
    profileText("profile-summary-address", c.registered_address.trim() || "Chưa nhập");
    profileText("profile-summary-industry", c.industry.trim() || "Chưa nhập");
    profileText("profile-summary-year", c.fiscal_year_end_month ? "Tháng " + c.fiscal_year_end_month : "Chưa chọn");
    profileText("profile-summary-vat", { DEDUCTION: "Khấu trừ", DIRECT: "Trực tiếp" }[c.vat_method] || "Chưa chọn");
    profileText("profile-summary-filing", { MONTH: "Theo tháng", QUARTER: "Theo quý" }[c.filing_period] || "Chưa chọn");
    profileText("profile-date-preview", c.date_format === "iso" ? "2026-12-31" : "31/12/2026");
    profileText("profile-number-preview", c.number_format === "plain" ? "1250000.50" : "1.250.000,50");
  }

  function validateProfile(body) {
    const errors = {};
    if (!body.legal_name.trim()) errors.legal_name = "Nhập tên doanh nghiệp.";
    if (!/^[A-Z0-9][A-Z0-9_-]{0,63}$/.test(body.code.trim().toUpperCase())) errors.code = "Nhập mã gồm chữ không dấu, số, gạch ngang hoặc gạch dưới, tối đa 64 ký tự.";
    if (body.tax_code) {
      const digits = body.tax_code.replace(/[^0-9]/g, "");
      const weights = [31,29,23,19,17,13,7,5,3];
      if (![10,13].includes(digits.length) || 10 - weights.reduce((sum,w,i) => sum + Number(digits[i]) * w, 0) % 11 !== Number(digits[9])) errors.tax_code = "Mã số thuế cần 10 hoặc 13 chữ số và đúng chữ số kiểm tra.";
    }
    for (const [key, choices] of Object.entries({ vat_method:["DEDUCTION","DIRECT"], filing_period:["MONTH","QUARTER"], date_format:["dmy","iso"], number_format:["vi-VN","plain"] })) {
      if (!choices.includes(body[key])) errors[key] = "Chọn một giá trị hợp lệ.";
    }
    if (!/^(?:[1-9]|1[0-2])$/.test(body.fiscal_year_end_month)) errors.fiscal_year_end_month = "Chọn tháng kết thúc năm tài chính từ 1 đến 12.";
    return errors;
  }

  function showProfileErrors(errors, general = "", focus = false) {
    profileErrors = errors;
    const form = $("company-form");
    form.querySelectorAll(".profile-field-error").forEach((node) => node.remove());
    for (const input of form.elements) if (input.name) { input.removeAttribute("aria-invalid"); input.removeAttribute("aria-errormessage"); }
    const summary = $("profile-errors");
    summary.replaceChildren();
    summary.hidden = !general && !Object.keys(errors).length;
    if (summary.hidden) return;
    summary.append(el("h2", {}, general ? "Chưa lưu được hồ sơ" : "Kiểm tra lại thông tin"));
    if (general) summary.append(el("p", {}, general));
    for (const [key, message] of Object.entries(errors)) {
      const input = form.elements[key];
      input.setAttribute("aria-invalid", "true");
      const id = input.id + "-error";
      input.setAttribute("aria-errormessage", id);
      input.after(el("span", { id, class:"profile-field-error" }, message));
      summary.append(el("a", { href:"#" + input.id, onclick:(event) => { event.preventDefault(); input.focus(); } }, message));
    }
    if (focus) summary.focus();
  }

  function editProfile(event) {
    if (!event.target.name) return;
    const values = profileValues();
    const dirty = Object.entries(values).some(([key,value]) => value !== String(state.company[key] ?? ""));
    if (dirty) $("company-form").dataset.dirty = "1";
    else delete $("company-form").dataset.dirty;
    if (profileErrors[event.target.name]) { const remaining = { ...profileErrors }; delete remaining[event.target.name]; showProfileErrors(remaining); }
    $("profile-sync").hidden = true;
    renderConfig();
  }

  function renderNav() {
    const signature = state.agents.map((a) => [a.id, a.name, a.state].join(":" )).join("|");
    if ($("nav-agents").dataset.signature === signature) { markCurrent(); return; }
    $("nav-agents").dataset.signature = signature;
    $("nav-agents").replaceChildren(
      ...state.agents.map((a) =>
        el("a", { class: "nav-link", href: "#" + a.id, "data-view": a.id },
          el("span", { class: "num", "aria-hidden": "true" }, "A" + a.number), WORKSPACE_LABEL[a.id], el("span", { class: "dot " + a.state, title: STATE_TEXT[a.state] }))));
    $("profile-agent-list").replaceChildren(...state.agents.map((a) =>
      el("li", {}, el("a", { href: "#" + a.id }, WORKSPACE_LABEL[a.id] + " · A" + a.number),
        el("span", {}, a.id === "agent4" ? "Kho mô phỏng riêng" : STATE_TEXT[a.state]))));
    markCurrent();
  }

  function receivedCount(aid) {
    return state.batches.filter((b) => b.company === state.company.code).flatMap((b) => b.files).filter((f) => f.results[aid] && f.results[aid].state === "done").length;
  }

  const AGENT_SVGS = {
    agent1: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>`,
    agent2: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`,
    agent3: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
    agent4: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="12" y1="7" x2="12" y2="13"/></svg>`
  };

  const WORKSTATION_INFO = {
    agent1: {
      title: "Quản trị Dòng tiền",
      desc: "Dự báo thu chi theo tuần, kiểm soát thanh khoản và phân tích kịch bản công nợ khách hàng.",
      icon: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>`
    },
    agent2: {
      title: "Soát xét Giao dịch",
      desc: "Rà soát giao dịch bất thường, xung đột lợi ích và phòng ngừa gian lận chứng từ bằng ML.",
      icon: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`
    },
    agent3: {
      title: "Tuân thủ Thuế GTGT",
      desc: "Đối chiếu tự động 3 bên giữa hóa đơn XML, sao kê ngân hàng và bảng kê cổng Cục Thuế.",
      icon: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`
    },
    agent4: {
      title: "Trợ lý CFO & Sổ cái",
      desc: "Hỏi đáp chỉ tiêu tài chính bằng tiếng Việt và trích xuất dữ liệu sổ cái DuckDB có kiểm chứng.",
      icon: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="12" y1="7" x2="12" y2="13"/></svg>`
    }
  };

  function renderOverview() {
    const c = state.company;
    if ($("today")) {
      $("today").textContent = new Intl.DateTimeFormat("vi-VN", { day: "numeric", month: "long", year: "numeric" }).format(new Date());
    }

    // 1. Sleek Minimalist Header
    const monogram = (c.code || "SS").slice(0, 2).toUpperCase();
    if ($("overview-monogram")) $("overview-monogram").textContent = monogram;
    if ($("overview-company-fullname")) {
      $("overview-company-fullname").textContent = c.legal_name || "Văn phòng kế toán số";
    }
    if ($("overview-tax-badge")) {
      $("overview-tax-badge").textContent = c.tax_code ? "MST: " + c.tax_code : "MST: —";
    }

    const runningCount = state.agents.filter((a) => a.state === "running").length;
    const pill = $("overview-status-pill");
    const statusText = $("overview-system-status");
    if (statusText) {
      if (runningCount === state.agents.length) {
        statusText.textContent = "4/4 Agent sẵn sàng";
        if (pill) pill.classList.remove("is-partial");
      } else if (runningCount > 0) {
        statusText.textContent = runningCount + "/4 Agent trực tuyến";
        if (pill) pill.classList.add("is-partial");
      } else {
        statusText.textContent = "Các agent đang tạm dừng";
        if (pill) pill.classList.add("is-partial");
      }
    }

    if ($("start-all")) {
      $("start-all").disabled = state.agents.every((a) => a.state !== "stopped");
      $("start-all").innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${runningCount === state.agents.length ? "Tất cả đang chạy" : "Bật các agent"}</span>`;
    }

    // 2. The 4 Specialized Workstations (NO FAKE NUMBERS, 100% Interactive Tiles)
    const signature = JSON.stringify([state.agents.map((a) => [a.id, a.state, a.name]), c.code]);
    if ($("agent-grid").dataset.signature !== signature) {
      $("agent-grid").dataset.signature = signature;

      $("agent-grid").replaceChildren(
        ...state.agents.map((a) => {
          const info = WORKSTATION_INFO[a.id] || {
            title: a.name,
            desc: a.summary,
            icon: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/></svg>`
          };

          const iconBox = el("div", { class: "ws-icon-box" });
          iconBox.innerHTML = info.icon;

          const isRunning = a.state === "running";
          const statusDot = el("span", {
            class: "ws-status-dot " + (isRunning ? "" : "is-stopped"),
            title: isRunning ? "Đang hoạt động" : "Đang tạm dừng"
          });

          return el("a", { class: "workstation-card", href: "#" + a.id, "data-id": a.id },
            el("div", { class: "ws-card-top" },
              el("div", { class: "ws-card-meta" },
                el("span", { class: "ws-num-pill" }, "A" + a.number),
                iconBox
              ),
              statusDot
            ),
            el("h3", { class: "ws-title" }, info.title),
            el("p", { class: "ws-desc" }, info.desc),
            el("div", { class: "ws-card-foot" },
              el("span", {}, "Mở không gian tác nghiệp"),
              el("span", { class: "ws-arrow" }, "↗")
            )
          );
        })
      );
    }

    // 3. Executive Setup Progress
    const step1Done = Boolean(c.legal_name && c.code);
    const step2Done = state.agents.every((a) => a.state === "running");
    const step3Done = Boolean(state.package);
    const doneCount = (step1Done ? 1 : 0) + (step2Done ? 1 : 0) + (step3Done ? 1 : 0);
    const pct = Math.round((doneCount / 3) * 100);

    if ($("meter-bar")) $("meter-bar").style.width = pct + "%";
    if ($("setup-progress-text")) {
      $("setup-progress-text").textContent = doneCount === 3
        ? "Sẵn sàng vận hành (3/3 hoàn tất) ✓"
        : "Tiến độ: " + doneCount + "/3 bước (" + pct + "%)";
    }

    const steps = $("steps") ? $("steps").children : [];
    if (steps.length >= 3) {
      steps[0].classList.toggle("done", step1Done);
      steps[1].classList.toggle("done", step2Done);
      steps[2].classList.toggle("done", step3Done);
    }

    if ($("step-config-desc")) {
      $("step-config-desc").textContent = step1Done
        ? (c.code ? "Mã: " + c.code : "") + (c.tax_code ? " · MST: " + c.tax_code : "")
        : "Chưa cấu hình thông tin doanh nghiệp";
    }
    if ($("step-agents-status")) {
      $("step-agents-status").textContent = runningCount === state.agents.length
        ? "4/4 Agent đang trực tuyến"
        : runningCount + "/4 Agent trực tuyến";
    }
    if ($("step-data-desc")) {
      $("step-data-desc").textContent = state.package
        ? "Gói v" + state.package.version + " (" + state.package.files + " tệp) · Đã niêm phong"
        : "Chưa niêm phong gói dữ liệu";
    }
  }

  function checkLines(record) {
    return el("ul", { class: "checks" },
      record.targets.length
        ? record.targets.map((aid) => {
          const c = (record.checks || {})[aid] || { state: "offline", message: "" };
          return [
            el("li", {}, el("span", { class: "who" }, AGENT_LABEL[aid]), el("span", { class: c.state }, CHECK_TEXT[c.state] + (c.message ? ": " + c.message : ""))),
            c.warning && c.state === "ready" ? el("li", {}, el("span"), el("span", { class: "warn" }, c.warning)) : null,
            ...(c.detail || []).map((d) => el("li", {}, el("span"), el("span", { class: "detail" }, d))),
          ];
        })
        : el("li", {}, el("span", { class: "who" }, "Không"), el("span", { class: "skipped" }, record.note || "Không agent nào đọc được tệp này.")));
  }

  const periodText = (p) => (p ? (p[0] === p[1] ? dmy(p[0]) : dmy(p[0]) + " đến " + dmy(p[1])) : "Không rõ");

  function periodWarning() {
    const ranges = {};
    const add = (aid, p) => {
      if (!p) return;
      const r = ranges[aid] || (ranges[aid] = [p[0], p[1]]);
      if (p[0] < r[0]) r[0] = p[0];
      if (p[1] > r[1]) r[1] = p[1];
    };
    for (const r of state.pending) for (const aid of r.targets) add(aid, r.period);
    for (const b of state.batches) for (const f of b.files) {
      for (const [aid, result] of Object.entries(f.results)) if (result.state === "done") add(aid, f.period);
    }
    const list = Object.entries(ranges);
    if (list.length < 2) return "";
    const lo = list.map(([, r]) => r[0]).sort().pop();
    const hi = list.map(([, r]) => r[1]).sort()[0];
    if (lo <= hi) return "";
    return "Kỳ dữ liệu của các agent không giao nhau: " + list.map(([aid, r]) => AGENT_LABEL[aid] + " " + periodText(r)).join("; ") + ". Kiểm tra đã chọn đúng doanh nghiệp và kỳ chưa.";
  }

  function renderSlots() {
    const groups = state.agents.map(({ id: aid, name }) =>
      el("div", { class: "slot-group" },
        el("h3", {}, AGENT_LABEL[aid] + " · " + name),
        aid === "agent4" ? el("p", { class: "hint" }, "Kho mô phỏng riêng. Tệp trong gói được chuyển đến Agent 1–3.") :
          el("ul", {}, state.slots.filter((s) => s.agent === aid).map((s) =>
          el("li", {}, el("span", { class: "mark " + s.state }), s.agent === "agent1" && s.key === "outflows" ? "Lịch cố định T5 (tùy chọn)" : s.label,
            el("span", { class: "slot-note" }, s.state === "sealed" ? "đã niêm phong" : s.state === "pending" ? "chờ ghi" : ""))))));
    $("slots").replaceChildren(...groups);
    const p = state.package;
    $("package-line").textContent = p
      ? "Phiên bản " + p.version + ", niêm phong " + stamp(p.sealed_at) + ", " + p.files + " tệp, mã " + p.manifest + (p.amendments ? ", đã sửa đổi " + p.amendments + " lần" : "")
      : "Chưa có phiên bản niêm phong.";
    const w = periodWarning();
    $("period-warning").hidden = !w;
    $("period-warning").textContent = w;
  }

  function renderQueue() {
    const rows = state.pending.map((r) =>
      el("tr", { role: "row" },
        el("td", { role: "cell" }, el("div", { class: "file-name" }, r.name), el("div", { class: "sub" }, sizeText(r.size) + ", thêm lúc " + r.added_at.slice(11, 16))),
        el("td", { role: "cell" }, r.label, r.note ? el("div", { class: "sub" }, r.note) : null),
        el("td", { role: "cell", class: "sub", "data-label": "Kỳ dữ liệu" }, periodText(r.period)),
        el("td", { role: "cell" }, checkLines(r)),
        el("td", { role: "cell", class: "right" }, el("div", { class: "queue-actions" },
          el("button", { type: "button", class: "link", onclick: () => recheck(r.id) }, "Kiểm tra lại"),
          el("button", { type: "button", class: "link", onclick: () => dropFile(r.id) }, "Bỏ")))));
    $("queue").tBodies[0].replaceChildren(...rows);
    $("queue-empty").hidden = rows.length > 0;
    const ready = state.pending.filter(canWrite);
    const targets = new Set(ready.flatMap((record) => record.targets.filter((aid) => record.checks[aid]?.state === "ready")));
    $("intake-summary-count").textContent = ready.length + " / " + rows.length + " tệp sẵn sàng ghi";
    $("intake-summary-agents").textContent = targets.size
      ? "Nghiệp vụ nhận tệp: " + [...targets].map((aid) => AGENT_LABEL[aid]).join(", ")
      : "Chưa có tệp sẵn sàng để phân phối.";
    $("intake-next").disabled = !ready.length;
    $("reason-field").hidden = !state.package;
    const button = $("commit");
    button.disabled = !ready.length;
    if (button.dataset.confirm !== "1") button.textContent = ready.length && ready.length < rows.length ? "Ghi " + ready.length + " tệp sẵn sàng" : "Ghi toàn bộ dữ liệu";

    const mine = state.batches.filter((b) => b.company === state.company.code);
    const hist = mine.map((b) =>
      el("tr", {},
        el("td", {}, el("span", { class: "ver" }, "v" + b.version), el("span", { class: "tag" + (b.kind === "gốc" ? "" : " amend") }, b.kind), el("div", { class: "sub" }, "mã " + b.manifest.slice(0, 12))),
        el("td", { class: "sub" }, stamp(b.sealed_at)),
        el("td", {}, b.reason || el("span", { class: "sub" }, "Gói gốc")),
        el("td", {}, el("ul", { class: "checks" }, b.files.map((f) =>
          el("li", {}, el("span", { class: "who" }, f.name.length > 14 ? f.name.slice(0, 12) + "…" : f.name),
            el("span", { class: "done" }, Object.entries(f.results).map(([aid, r]) => AGENT_LABEL[aid] + ": " + r.message).join("; "))))))));
    $("history").tBodies[0].replaceChildren(...hist);
    $("history-empty").hidden = hist.length > 0;
  }

  function showIntakeStage(stage, focus = false) {
    intakeStage = stage;
    $("intake").dataset.stage = stage;
    const [title, description] = {
      choose: ["Nạp dữ liệu chung", "Tiếp nhận tệp một lần cho các nghiệp vụ sử dụng dữ liệu chung."],
      review: ["Kiểm tra tệp", "Xem loại tệp, kỳ dữ liệu và kết quả kiểm tra theo từng agent."],
      confirm: ["Xác nhận và nạp toàn bộ dữ liệu", "Kiểm tra danh sách tệp và nghiệp vụ nhận dữ liệu trước khi ghi."],
      history: ["Lịch sử dữ liệu", "Xem các phiên bản đã niêm phong và kết quả ghi vào từng agent."],
    }[stage];
    $("h-intake").textContent = title;
    $("intake-lead").textContent = description;
    $("intake-choose").hidden = stage !== "choose";
    $("intake-queue").hidden = stage !== "review" && stage !== "confirm";
    $("intake-next").hidden = stage !== "review";
    $("commit-bar").hidden = stage !== "confirm";
    $("intake-history").hidden = stage !== "history";
    $("intake-versions").hidden = stage !== "history";
    for (const button of $("intake-tabs").querySelectorAll("button")) {
      if (button.dataset.intakeStage === stage) {
        button.setAttribute("aria-current", "step");
        if (focus) button.focus();
      } else button.removeAttribute("aria-current");
    }
  }

  function renderData() {
    const i = state.intake;
    $("view-data").setAttribute("aria-labelledby", i.unlocked ? "h-intake" : "h-data");
    $("gate").hidden = i.unlocked;
    $("intake").hidden = !i.unlocked;
    if (!i.unlocked) {
      intakeStage = "choose";
      const first = !i.configured;
      $("gate-lead").textContent = first
        ? "Đặt mật khẩu một lần. Từ đó mọi lần nạp, bổ sung hay sửa cấu hình sau khi niêm phong đều phải mở khóa."
        : "Nhập mật khẩu để nạp hoặc xem gói dữ liệu của doanh nghiệp. Phiên tự khóa sau 20 phút không dùng.";
      $("gate-label").textContent = first ? "Mật khẩu mới (ít nhất 8 ký tự)" : "Mật khẩu";
      $("gate-confirm-field").hidden = !first;
      $("gate-password").autocomplete = first ? "new-password" : "current-password";
      $("gate-submit").textContent = first ? "Đặt mật khẩu và mở" : "Mở khóa";
      const bioSec = $("gate-biometric-section");
      if (bioSec) {
        bioSec.hidden = first;
        const bioLabel = $("gate-biometric-label");
        if (bioLabel) {
          bioLabel.textContent = i.has_biometric
            ? "Mở khóa bằng FaceID / Sinh trắc học"
            : "Thiết lập và Mở bằng FaceID (Tùy chọn)";
        }
      }
      return;
    }
    $("session-left").textContent = "Đã mở khóa, còn " + Math.max(1, Math.round(i.seconds_left / 60)) + " phút";
    const faceMng = $("face-manage-btn");
    if (faceMng) {
      faceMng.textContent = i.has_biometric ? "🛡️ Quét lại FaceID" : "+ Đăng ký FaceID";
      faceMng.title = i.has_biometric ? "Cập nhật lại khuôn mặt nhận diện FaceID" : "Đăng ký khuôn mặt nhận diện FaceID";
    }
    const c = state.company;
    $("intake-company").replaceChildren(c.code
      ? el("strong", {}, c.legal_name + " · " + c.code)
      : el("a", { href: "#config" }, "Lưu hồ sơ doanh nghiệp để nạp tệp"));
    $("file-input").disabled = !c.code;
    $("drop").hidden = !c.code;
    renderSlots();
    renderQueue();
    showIntakeStage(intakeStage);
  }

  const AGENT_SUBTAGS = {
    agent1: "Quản lý Bán hàng & Hóa đơn",
    agent2: "Ngân hàng & Sổ cái",
    agent3: "Tuân thủ thuế GTGT & Hóa đơn",
    agent4: "Mô phỏng & Hỏi đáp thông minh"
  };

  function renderAgentView() {
    if (!currentAgent) return;
    const a = agentById(currentAgent);
    const noEl = $("agent-no");
    if (noEl) {
      noEl.textContent = "A" + a.number;
      noEl.setAttribute("data-agent", a.id);
    }
    const nameEl = $("agent-name");
    if (nameEl) nameEl.textContent = a.id === "agent4" ? "Agent 4 · Hỏi đáp" : a.name;
    const subtagEl = $("agent-subtag");
    if (subtagEl) subtagEl.textContent = AGENT_SUBTAGS[a.id] || "Không gian làm việc chuyên biệt";

    const statusEl = $("agent-status");
    if (statusEl) {
      statusEl.className = "status status-pill " + a.state;
      statusEl.replaceChildren(el("span", { class: "dot " + a.state }), el("span", { class: "status-text" }, STATE_TEXT[a.state]));
    }

    const source = $("agent-source");
    if (source) {
      source.textContent = a.id === "agent4" ? "Kho mô phỏng độc lập của Agent 4"
        : state.company.code ? ["Hồ sơ " + state.company.code, state.package ? "Gói chung v" + state.package.version : "Chưa niêm phong"].join(" · ")
          : "Cấu hình doanh nghiệp để nạp dữ liệu";
      source.href = a.id !== "agent4" && !state.company.code ? "#config" : "#data";
    }

    const page = new URL(a.url, location.href);
    page.searchParams.set("portal", location.origin);
    const pageUrl = page.href;
    const newtab = $("agent-newtab");
    if (newtab) newtab.href = pageUrl;

    const toggleBtn = $("agent-toggle");
    if (toggleBtn) {
      const isRunning = a.state === "running" || a.state === "starting";
      toggleBtn.classList.toggle("is-running", isRunning);
      toggleBtn.classList.toggle("is-stopped", !isRunning);
      const btnText = toggleBtn.querySelector(".btn-text");
      if (btnText) btnText.textContent = isRunning ? "Tắt agent" : "Bật agent";
      else toggleBtn.textContent = isRunning ? "Tắt agent" : "Bật agent";
      toggleBtn.hidden = !(a.owned || a.state === "stopped");
    }
    const frame = $("agent-frame-" + a.id) || $("agent-frame");
    if (a.state === "running") {
      offlineFailures[a.id] = 0;
    } else {
      offlineFailures[a.id] = (offlineFailures[a.id] || 0) + 1;
    }

    // Grace period: keep frame visible during temporary glitches (< 3 poll cycles = 12s)
    const isOnline = a.state === "running" || (frame.dataset.src && a.state === "starting" && offlineFailures[a.id] < 3);

    for (const id of ["agent1", "agent2", "agent3", "agent4"]) {
      const f = $("agent-frame-" + id);
      if (f && id !== a.id) f.hidden = true;
    }

    if (isOnline) {
      if (frame.dataset.src !== pageUrl) {
        startLoading();
        frame.classList.add("is-loading");
        frame.dataset.src = pageUrl;
        frame.src = pageUrl;
        const onLoad = () => {
          frame.removeEventListener("load", onLoad);
          frame.classList.remove("is-loading");
          stopLoading();
        };
        frame.addEventListener("load", onLoad);
      }
      frame.hidden = false;
      $("agent-off").hidden = true;
    } else {
      frame.hidden = true;
      if (a.state === "stopped") { frame.removeAttribute("src"); delete frame.dataset.src; }
      $("agent-off").hidden = false;
    }
    if (!isOnline) {
      $("agent-off-text").textContent =
        a.state === "starting" ? "Đang khởi động, trang sẽ tự mở khi agent sẵn sàng."
          : a.state === "busy-port" ? "Cổng " + a.port + " đang bị chương trình khác dùng. Tắt chương trình đó hoặc đổi cổng trong portal/config.local.json."
            : "Bật agent để mở giao diện. Portal chạy agent từ thư mục " + a.root + ".";
      $("agent-start").hidden = a.state !== "stopped";
      api(a.log).then((d) => ($("agent-log").textContent = d.log || "Chưa có nhật ký.")).catch(() => {});
    }
  }

  function render() {
    renderTop();
    renderConfig();
    renderNav();
    renderOverview();
    renderData();
    renderAgentView();
  }

  async function refresh() {
    const version = profileVersion;
    try {
      const next = await api("/api/state");
      if (version !== profileVersion && state) next.company = state.company;
      state = next;
      if (token && !state.intake.unlocked) setToken("");
      render();
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------------ routing
  function markCurrent() {
    const view = location.hash.slice(1) || "overview";
    document.querySelectorAll(".nav-link").forEach((a) =>
      a.dataset.view === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  }

  const TITLES = { overview: "Tổng quan", config: "Cấu hình", data: "Nạp dữ liệu" };

  function show() {
    const view = location.hash.slice(1) || "overview";
    const isAgent = /^agent[1-4]$/.test(view);
    for (const id of ["overview", "config", "data"]) $("view-" + id).hidden = id !== view;
    $("view-agent").hidden = !isAgent;
    if (!isAgent) {
      for (const id of ["agent1", "agent2", "agent3", "agent4"]) {
        const f = $("agent-frame-" + id);
        if (f) f.hidden = true;
      }
      const singleFrame = $("agent-frame");
      if (singleFrame) singleFrame.hidden = true;
    }
    currentAgent = isAgent ? view : null;
    if (sidebarMedia.matches) setSidebarOpen(false, $("sidebar").contains(document.activeElement));
    if (state) render();
    markCurrent();
    document.title = (isAgent && state ? AGENT_LABEL[view] + " " + agentById(view).name : TITLES[view] || "") + " | Văn phòng kế toán số";
  }

  // ------------------------------------------------------------------ actions
  async function openAgent1Tab(event) {
    if (currentAgent !== "agent1") return;
    event.preventDefault();
    const agent = agentById("agent1");
    if (agent.state !== "running") {
      toast("Bật Agent 1 rồi mở tab riêng.", true);
      return;
    }
    const company = state.company.code || "SME";
    const agentOrigin = new URL(agent.url, location.href).origin;
    // Open during the click, then sever the opener before any navigation.
    const tab = window.open("about:blank", "_blank");
    if (!tab) {
      toast("Trình duyệt đã chặn tab mới. Cho phép mở tab rồi bấm lại.", true);
      return;
    }
    try {
      tab.opener = null;
      tab.document.title = "Đang kết nối Agent 1";
      if (tab.document.body) tab.document.body.textContent = "Đang kết nối Agent 1 với doanh nghiệp của bạn…";
      const result = await api("/api/agents/agent1/connect-link", { method: "POST", json: { company } });
      if ((state.company.code || "SME") !== company || result.company !== company) {
        throw new Error("Doanh nghiệp đã đổi. Mở lại tab từ trang chung.");
      }
      const target = new URL(result.url);
      if (target.origin !== agentOrigin || target.pathname !== "/workspace" || target.searchParams.get("portal") !== location.origin) {
        throw new Error("Địa chỉ kết nối không khớp Agent 1 đang mở.");
      }
      if (!tab.closed) tab.location.replace(target.href);
    } catch (err) {
      if (!tab.closed) tab.close();
      toast(err.message, true);
    }
  }

  async function toggleAgent(a) {
    const action = a.state === "running" || a.state === "starting" ? "stop" : "start";
    try {
      await api("/api/agents/" + a.id + "/" + action, { method: "POST" });
      toast(action === "start" ? AGENT_LABEL[a.id] + " đang khởi động." : AGENT_LABEL[a.id] + " đã tắt.");
    } catch (err) { toast(err.message, true); }
    refresh();
  }

  async function unlockGate(event) {
    event.preventDefault();
    const form = event.target;
    const first = !state.intake.configured;
    $("gate-error").textContent = "";
    const button = $("gate-submit");
    button.disabled = true;
    try {
      const body = { password: form.password.value, confirm: form.confirm.value };
      const res = await api(first ? "/api/intake/setup" : "/api/intake/unlock", { method: "POST", json: body });
      setToken(res.token);
      form.reset();
      await refresh();
    } catch (err) {
      $("gate-error").textContent = err.message;
    } finally { button.disabled = false; }
  }

  async function lockNow() {
    await api("/api/intake/lock", { method: "POST" }).catch(() => {});
    setToken("");
    await refresh();
  }

  function bufToB64Url(buf) {
    const bytes = new Uint8Array(buf);
    let str = "";
    for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function b64UrlToBuf(b64url) {
    let str = (b64url || "").replace(/-/g, "+").replace(/_/g, "/");
    while (str.length % 4) str += "=";
    const raw = atob(str);
    const buf = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
    return buf.buffer;
  }

  function checkLocalhostForBiometrics() {
    if (window.location.hostname === "127.0.0.1") {
      const target = window.location.href.replace("127.0.0.1", "localhost");
      if (confirm("Chuẩn bảo mật WebAuthn / FaceID yêu cầu truy cập qua tên miền 'localhost' thay vì địa chỉ IP '127.0.0.1'.\n\nBấm OK để chuyển sang " + target + " và kích hoạt FaceID.")) {
        window.location.href = target;
      }
      return false;
    }
    return true;
  }

  let faceModelsLoaded = false;
  let faceStream = null;
  let faceAnimationId = null;
  let isFaceCompleted = false;

  async function loadFaceModels() {
    if (faceModelsLoaded) return true;
    if (typeof faceapi === "undefined") {
      throw new Error("Chưa tải được thư viện AI face-api.js.");
    }
    const MODEL_PATH = "/models";
    $("face-spinner").hidden = false;
    $("face-loading-text").textContent = "Đang tải mô hình AI khuôn mặt...";
    try {
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_PATH),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_PATH),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_PATH)
      ]);
      faceModelsLoaded = true;
      $("face-spinner").hidden = true;
      return true;
    } catch (err) {
      $("face-loading-text").textContent = "Lỗi tải mô hình AI: " + err.message;
      throw err;
    }
  }

  function stopFaceCamera() {
    isFaceCompleted = true;
    if (faceAnimationId) {
      cancelAnimationFrame(faceAnimationId);
      faceAnimationId = null;
    }
    if (faceStream) {
      faceStream.getTracks().forEach((track) => track.stop());
      faceStream = null;
    }
    const video = $("face-video");
    if (video) video.srcObject = null;
    const modal = $("face-modal");
    if (modal) modal.hidden = true;
    const reticle = document.querySelector(".face-reticle");
    if (reticle) reticle.classList.remove("active");
  }

  async function openFaceModal(mode, password = "") {
    const modal = $("face-modal");
    const video = $("face-video");
    const canvas = $("face-canvas");
    const titleEl = $("face-modal-title");
    const feedback = $("face-feedback");
    const reticle = document.querySelector(".face-reticle");

    modal.hidden = false;
    isFaceCompleted = false;
    titleEl.textContent = mode === "register" ? "Đăng ký khuôn mặt FaceID mới" : "Quét khuôn mặt để mở khóa";
    feedback.className = "face-feedback";
    feedback.textContent = "Đang khởi động camera...";
    if (reticle) reticle.classList.remove("active");

    try {
      await loadFaceModels();
      faceStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
      });
      video.srcObject = faceStream;
      await video.play();

      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;

      let consecutiveMatches = 0;
      let isProcessing = false;

      const detectFrame = async () => {
        if (!faceStream || modal.hidden || isFaceCompleted) return;

        if (!isProcessing && video.readyState === 4 && !isFaceCompleted) {
          isProcessing = true;
          try {
            const detection = await faceapi.detectSingleFace(
              video,
              new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.5 })
            ).withFaceLandmarks().withFaceDescriptor();

            if (isFaceCompleted) return;

            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (detection) {
              if (reticle) reticle.classList.add("active");
              feedback.className = "face-feedback ok";

              if (mode === "register") {
                consecutiveMatches++;
                feedback.textContent = "Đã nhận diện khuôn mặt! Giữ nguyên... (" + consecutiveMatches + "/3)";
                if (consecutiveMatches >= 3) {
                  isFaceCompleted = true;
                  feedback.textContent = "Đang lưu trữ vector sinh trắc học...";
                  const descArray = Array.from(detection.descriptor);
                  const res = await api("/api/intake/face/register", {
                    method: "POST",
                    json: { descriptor: descArray, password: password }
                  });
                  stopFaceCamera();
                  if (res && res.token) setToken(res.token);
                  toast("Đã đăng ký FaceID và mở khóa thành công!");
                  await refresh();
                  return;
                }
              } else {
                isFaceCompleted = true;
                feedback.textContent = "Đang đối soát nhận diện khuôn mặt...";
                const descArray = Array.from(detection.descriptor);
                const res = await api("/api/intake/face/verify", {
                  method: "POST",
                  json: { descriptor: descArray }
                });
                stopFaceCamera();
                setToken(res.token);
                toast("Nhận diện FaceID chính xác! Đã mở khóa.");
                await refresh();
                return;
              }
            } else {
              consecutiveMatches = 0;
              if (reticle) reticle.classList.remove("active");
              feedback.className = "face-feedback";
              feedback.textContent = "Vui lòng nhìn thẳng vào vòng quét...";
            }
          } catch (err) {
            if (!isFaceCompleted) {
              feedback.className = "face-feedback err";
              feedback.textContent = err.message || "Lỗi đối soát khuôn mặt.";
            }
          } finally {
            isProcessing = false;
          }
        }
        if (!isFaceCompleted) {
          faceAnimationId = requestAnimationFrame(detectFrame);
        }
      };

      faceAnimationId = requestAnimationFrame(detectFrame);
    } catch (err) {
      feedback.className = "face-feedback err";
      feedback.textContent = "Không thể mở camera: " + (err.message || err);
      toast(err.message || "Không thể truy cập camera.", true);
    }
  }

  async function unlockBiometric() {
    const errEl = $("gate-error");
    if (errEl) errEl.textContent = "";

    // If biometric is not yet enrolled, prompt for password first to link FaceID
    if (!state?.intake?.has_biometric) {
      const pwInput = $("gate-password");
      let pw = (pwInput?.value || "").trim();
      if (!pw) {
        // No native prompt(): it would show the password in clear text and cannot be styled or automated.
        if (errEl) errEl.textContent = "Nhập mật khẩu vào ô phía trên, rồi bấm lại nút FaceID để đăng ký lần đầu.";
        pwInput?.focus();
        return;
      }
      openFaceModal("register", pw);
      return;
    }

    // Biometric already enrolled -> open direct camera scanner
    openFaceModal("verify");
  }

  async function toggleBiometric() {
    if (!state?.intake) return;
    if (state.intake.has_biometric) {
      if (!confirm("Bạn có chắc chắn muốn hủy FaceID trên máy này?")) return;
      try {
        await api("/api/intake/biometric/remove", { method: "POST" });
        toast("Đã hủy FaceID.");
        await refresh();
      } catch (err) {
        toast(err.message, true);
      }
    } else {
      await registerBiometric();
    }
  }

  async function upload(files) {
    const code = state?.company.code;
    if (!code) return;
    let uploaded = 0;
    const failures = [];
    for (const file of files) {
      toast("Đang nhận dạng và kiểm tra " + file.name);
      try {
        const query = new URLSearchParams({ name: file.name, company: code });
        await api("/api/inbox?" + query, { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
        uploaded++;
      } catch (err) {
        failures.push(file.name + " — " + err.message);
        if (err.locked) break;
      }
    }
    await refresh();
    toast(failures.length ? "Đã nhận " + uploaded + " tệp. " + failures.join(". ")
      : "Đã kiểm tra " + uploaded + " tệp. Xem kết quả trước khi niêm phong.", failures.length > 0);
    if (uploaded && state.intake.unlocked && location.hash === "#data") showIntakeStage("review", true);
  }

  async function recheck(id) {
    try { await api("/api/inbox/" + id + "/check", { method: "POST" }); } catch (err) { toast(err.message, true); }
    refresh();
  }

  async function dropFile(id) {
    await api("/api/inbox/" + id + "/delete", { method: "POST" }).catch((err) => toast(err.message, true));
    refresh();
  }

  function canWrite(record) {
    const checks = Object.values(record.checks || {});
    return checks.some((c) => c.state === "ready") &&
      (record.kind !== "shared_bank" || checks.every((c) => c.state === "ready" || c.state === "done"));
  }

  async function commitAll() {
    const ready = state.pending.filter(canWrite);
    const ids = ready.map((r) => r.id);
    const replaces = ready.some((r) => r.checks.agent2 && r.checks.agent2.state === "ready");
    const button = $("commit");
    const reason = $("reason").value.trim();
    if (state.package && reason.length < 10) { $("reason").focus(); toast("Gói đã niêm phong: nhập lý do bổ sung hoặc thay thế, ít nhất 10 ký tự.", true); return; }
    if (replaces && button.dataset.confirm !== "1") {
      button.dataset.confirm = "1";
      button.textContent = "Bấm lần nữa: Agent 2 thay toàn bộ giao dịch";
      setTimeout(() => { delete button.dataset.confirm; renderQueue(); }, 6000);
      return;
    }
    delete button.dataset.confirm;
    button.disabled = true;
    button.textContent = "Đang ghi";
    try {
      const res = await api("/api/inbox/commit", { method: "POST", json: { ids, reason } });
      $("reason").value = "";
      intakeStage = "history";
      toast("Đã niêm phong gói phiên bản " + res.batch.version + " với " + res.batch.files.length + " tệp.");
    } catch (err) { toast(err.message, true); }
    refresh();
  }

  async function loadAudit() {
    try {
      const a = await api("/api/intake/audit");
      $("audit-status").textContent = a.valid ? "Chuỗi nhật ký hợp lệ, " + a.count + " dòng, dấu cuối " + a.head + "." : "Nhật ký bị sửa tại dòng " + a.broken_at + ".";
      $("audit").querySelector("tbody").replaceChildren(...a.entries.map((e) =>
        el("tr", {}, el("td", {}, e.seq), el("td", { class: "sub" }, stamp(e.at)), el("td", {}, e.event),
          el("td", { class: "sub" }, Object.entries(e.detail).map(([k, v]) => k + ": " + v).join(", ")))));
    } catch (err) { toast(err.message, true); }
  }

  function syncItem(aid, s) {
    const item = el("li", { class: s.state === "error" ? "error" : s.state === "ok" ? "ok" : "" }, AGENT_LABEL[aid] + ": " + s.message);
    if (aid !== "agent3" || s.state !== "needs_admin") return item;
    const input = el("input", { type: "password", autocomplete: "current-password", "aria-label": "Mật khẩu quản trị Agent 3", placeholder: "Mật khẩu quản trị Agent 3" });
    const button = el("button", { type: "button", class: "primary" }, "Tạo ở Agent 3");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const res = await api("/api/agent3/workspace", { method: "POST", json: { password: input.value } });
        item.replaceWith(syncItem("agent3", res));
      } catch (err) { toast(err.message, true); button.disabled = false; }
      input.value = "";
    });
    item.append(el("div", { class: "inline-form" }, input, button));
    return item;
  }

  async function saveCompany(event) {
    event.preventDefault();
    const form = event.target;
    if (profileSaving || (state.package && !state.intake.unlocked)) return;
    const body = Object.fromEntries(new FormData(form).entries());
    const errors = validateProfile(body);
    showProfileErrors(errors, "", Boolean(Object.keys(errors).length));
    if (Object.keys(errors).length) return;
    profileSaving = true;
    renderConfig();
    try {
      const res = await api("/api/company", { method: "PUT", json: body });
      profileVersion += 1;
      state.company = res.company;
      delete form.dataset.dirty;
      $("profile-sync").hidden = false;
      $("sync-result").replaceChildren(
        el("li", { class: "ok" }, "Đã lưu hồ sơ doanh nghiệp " + res.company.code + "."),
        ...Object.entries(res.sync || {}).map(([aid, s]) => syncItem(aid, s)));
      toast("Đã lưu hồ sơ. Xem kết quả kết nối từng agent bên dưới.");
      render();
      await refresh();
    } catch (err) {
      showProfileErrors({}, err.message, !$("view-config").hidden);
    } finally { profileSaving = false; renderConfig(); }
  }

  // Agent 1 asks for its access key once it has loaded inside the frame.
  window.addEventListener("message", async (event) => {
    const a1 = state && agentById("agent1");
    const a1Frame = $("agent-frame-agent1") || $("agent-frame");
    if (!a1 || event.data?.type !== "platform-ready" || (a1Frame && event.source !== a1Frame.contentWindow)) return;
    const origin = new URL(a1.url).origin;
    if (event.origin !== origin) return;
    try {
      const { key } = await api("/api/agents/agent1/key");
      if (key && a1Frame) a1Frame.contentWindow.postMessage({ type: "platform-access-key", key }, origin);
    } catch (err) { toast(err.message, true); }
  });

  // ------------------------------------------------------------------ wire up
  window.addEventListener("hashchange", show);
  $("agent-newtab").addEventListener("click", openAgent1Tab);
  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    $("content").focus();
  });
  $("menu-toggle").addEventListener("click", () => {
    setSidebarOpen($("menu-toggle").getAttribute("aria-expanded") !== "true");
  });
  $("nav-backdrop").addEventListener("click", () => setSidebarOpen(false, true));
  $("sidebar").addEventListener("click", (event) => {
    if (sidebarMedia.matches && event.target.closest("a[href]")) setSidebarOpen(false, true);
  });
  sidebarMedia.addEventListener("change", () => {
    const hadSidebarFocus = $("sidebar").contains(document.activeElement);
    mobileSidebarOpen = false;
    renderSidebar();
    if ($("sidebar").inert && hadSidebarFocus) $("menu-toggle").focus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("menu-toggle").getAttribute("aria-expanded") === "true") {
      setSidebarOpen(false, true);
    }
  });
  $("company-form").addEventListener("submit", saveCompany);
  $("company-form").addEventListener("input", editProfile);
  $("company-form").addEventListener("change", editProfile);
  for (const button of document.querySelectorAll("[data-profile-section]")) {
    button.addEventListener("click", () => {
      for (const other of document.querySelectorAll("[data-profile-section]")) other.removeAttribute("aria-current");
      button.setAttribute("aria-current", "location");
      $(button.dataset.profileSection).scrollIntoView({ block: "nearest" });
    });
  }
  $("profile-reset").addEventListener("click", () => {
    if (profileSaving) return;
    delete $("company-form").dataset.dirty;
    showProfileErrors({});
    $("profile-sync").hidden = true;
    renderConfig();
    $("profile-status").setAttribute("tabindex", "-1");
    $("profile-status").focus({ preventScroll:true });
  });
  $("company-form").addEventListener("focusin", (event) => {
    if (!event.target.matches("input,select,a,button")) return;
    const target = event.target;
    requestAnimationFrame(() => {
      if (!target.isConnected || target.closest(".profile-actions")) return;
      const bounds = target.getBoundingClientRect();
      const actions = $("profile-submit").closest(".profile-actions").getBoundingClientRect();
      const header = document.querySelector(".topbar").getBoundingClientRect();
      if (bounds.bottom > actions.top - 12 || bounds.top < header.bottom + 12) target.scrollIntoView({ block:"center", behavior:"instant" });
    });
  });
  $("gate-form").addEventListener("submit", unlockGate);
  $("gate-biometric-btn")?.addEventListener("click", unlockBiometric);
  $("face-manage-btn")?.addEventListener("click", () => openFaceModal("register"));
  $("face-modal-close")?.addEventListener("click", stopFaceCamera);
  $("face-cancel-btn")?.addEventListener("click", stopFaceCamera);
  $("lock-now").addEventListener("click", lockNow);
  $("audit").addEventListener("toggle", (e) => e.target.open && loadAudit());
  $("start-all").addEventListener("click", async () => {
    for (const a of state.agents.filter((x) => x.state === "stopped")) {
      await api("/api/agents/" + a.id + "/start", { method: "POST" }).catch((err) => toast(err.message, true));
    }
    toast("Đang bật các agent. Agent 3 có thể mất nửa phút.");
    refresh();
  });
  $("agent-start").addEventListener("click", () => toggleAgent(agentById(currentAgent)));
  $("agent-toggle").addEventListener("click", () => toggleAgent(agentById(currentAgent)));
  $("commit").addEventListener("click", commitAll);
  $("intake-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-intake-stage]");
    if (button && state?.intake.unlocked) showIntakeStage(button.dataset.intakeStage);
  });
  $("intake-next").addEventListener("click", () => showIntakeStage("confirm", true));
  $("file-input").addEventListener("change", (e) => {
    if (e.target.files.length) upload([...e.target.files]);
    e.target.value = "";
  });
  const drop = $("drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) upload([...e.dataTransfer.files]);
  });

  renderSidebar();
  for (const input of $("company-form").elements) if (input.name || input.tagName === "BUTTON") input.disabled = true;
  show();
  refresh().then(show);
  setInterval(() => document.visibilityState === "visible" && refresh(), 4000);
})();
