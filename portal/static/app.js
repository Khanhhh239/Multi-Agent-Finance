"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const AGENT_LABEL = { agent1: "Agent 1", agent2: "Agent 2", agent3: "Agent 3", agent4: "Agent 4" };
  const ALL_AGENT_IDS = Object.keys(AGENT_LABEL);
  const runtimeConfig = window.__MAF_RUNTIME_CONFIG__ || {};
  const enabledAgentIds = new Set(
    (Array.isArray(runtimeConfig.enabledAgents) ? runtimeConfig.enabledAgents : ALL_AGENT_IDS)
      .filter((id) => ALL_AGENT_IDS.includes(id))
  );
  const apiBaseUrl = String(runtimeConfig.apiBaseUrl || "").replace(/\/+$/, "");
  const WORKSPACE_LABEL = {
    agent1: "Trợ lý Dòng tiền",
    agent2: "Trợ lý Giám sát",
    agent3: "Trợ lý Thuế",
    agent4: "Trợ lý hỏi đáp"
  };
  const STATE_TEXT = { running: "Đang chạy", starting: "Đang khởi động", stopped: "Đang tắt", "busy-port": "Cổng bị chiếm" };
  const CHECK_TEXT = { checking: "Đang kiểm tra", ready: "Sẵn sàng ghi", error: "Có lỗi", offline: "Agent tắt", done: "Đã ghi", skipped: "Bỏ qua", stale: "Chờ kiểm tra lại" };
  let state = null;
  let profileSaving = false;
  let profileVersion = 0;
  let profileErrors = {};
  let currentAgent = null;
  const offlineFailures = { agent1: 0, agent2: 0, agent3: 0, agent4: 0 };
  let intakeStage = "choose";
  let intakeActivity = null;
  let intakeSelection = null;
  let intakeResult = null;
  let token = "";
  let authVersion = 0;
  let agent2RouteEpoch = 0;
  try { token = sessionStorage.getItem("kt-session") || ""; } catch (e) { token = ""; }

  const isAgentEnabled = (id) => enabledAgentIds.has(id);
  const apiUrl = (path) => {
    const value = String(path || "");
    if (/^https?:\/\//i.test(value)) return value;
    return apiBaseUrl + (value.startsWith("/") ? value : "/" + value);
  };
  const filterRuntimeState = (next) => {
    if (!next || !Array.isArray(next.agents)) return next;
    const keepAgent = (id) => isAgentEnabled(id);
    const filterChecks = (checks) => Object.fromEntries(
      Object.entries(checks || {}).filter(([id]) => keepAgent(id))
    );
    return {
      ...next,
      agents: next.agents.filter((agent) => keepAgent(agent.id)),
      slots: Array.isArray(next.slots) ? next.slots.filter((slot) => keepAgent(slot.agent)) : next.slots,
      pending: Array.isArray(next.pending)
        ? next.pending.map((record) => ({
            ...record,
            targets: Array.isArray(record.targets) ? record.targets.filter(keepAgent) : record.targets,
            checks: filterChecks(record.checks),
          }))
        : next.pending,
      batches: Array.isArray(next.batches)
        ? next.batches.map((batch) => ({
            ...batch,
            files: Array.isArray(batch.files)
              ? batch.files.map((file) => ({ ...file, results: filterChecks(file.results) }))
              : batch.files,
          }))
        : next.batches,
    };
  };

  function applyRuntimeUi() {
    const cloudSlice = enabledAgentIds.size < ALL_AGENT_IDS.length;
    const navTitle = $("nav-agent-title");
    if (navTitle) navTitle.textContent = cloudSlice ? "Nghiệp vụ · Agent 4 cloud" : "Nghiệp vụ · 4 agent";
    document.querySelectorAll("[data-requires-agents]").forEach((node) => {
      const required = String(node.dataset.requiresAgents || "").split(",").filter(Boolean);
      node.hidden = required.some((id) => !isAgentEnabled(id));
    });
  }

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
    const nextToken = value || "";
    if (token !== nextToken) {
      authVersion += 1;
      agent2RouteEpoch += 1;
      for (const id of ["agent1", "agent2"]) {
        const frame = $("agent-frame-" + id) || $("agent-frame");
        if (frame) { frame.removeAttribute("src"); delete frame.dataset.src; }
      }
    }
    token = nextToken;
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

  function toast(message, error = false, persistent = false) {
    const t = $("toast");
    t.textContent = message;
    t.className = "toast" + (error ? " error" : "");
    t.hidden = false;
    clearTimeout(toast.timer);
    if (!persistent) toast.timer = setTimeout(() => (t.hidden = true), error ? 7000 : 3500);
  }

  function pendingCheck() {
    return state?.pending?.find((r) => Object.values(r.checks || {}).some((c) => c.state === "checking"));
  }

  function renderIntakeProgress() {
    const panel = $("intake-progress");
    if (!panel) return;
    const pending = pendingCheck();
    const activity = intakeActivity || (pending && {
      title: "Đang kiểm tra tệp", file: pending.name,
      started: pending.check_started_at * 1000, kind: "check",
    });
    panel.hidden = !activity;
    if (!activity) return;
    $("intake-progress-title").textContent = activity.title;
    $("intake-progress-file").textContent = activity.file;
    $("intake-progress-detail").textContent = activity.kind === "commit"
      ? "Đang lưu dữ liệu và gửi tới các nghiệp vụ đã chọn. Giữ trang mở và chờ kết quả."
      : "Đang chờ kết quả kiểm tra dữ liệu và liên kết. Tệp lịch sử lớn có thể mất vài phút.";
    const seconds = Math.max(0, Math.floor((Date.now() - (activity.started || Date.now())) / 1000));
    $("intake-progress-time").textContent = "Đã chờ " + String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
  }

  function startIntakeActivity(title, file, kind = "check") {
    intakeActivity = { title, file, kind, started: Date.now() };
    renderData();
    renderIntakeProgress();
  }

  function endIntakeActivity() {
    intakeActivity = null;
    if (state) renderData();
    renderIntakeProgress();
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
    const reqToken = token;
    const reqAuthVersion = authVersion;
    try {
      const headers = { "X-Platform": "1", ...(options.headers || {}) };
      if (reqToken) headers["X-Session"] = reqToken;
      if (options.json !== undefined) {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.json);
      }
      const res = await fetch(apiUrl(path), { ...options, headers, cache: "no-store", signal: options.signal || AbortSignal.timeout(120000) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 401 && data.locked && reqAuthVersion === authVersion && reqToken === token) {
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
  const agentById = (id) => state?.agents?.find((a) => a.id === id);
  const dmy = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "");
  const stamp = (s) => (s ? dmy(s.slice(0, 10)) + " " + s.slice(11, 16) : "");
  const monogram = (company) => company.split(/\s+/).filter(Boolean).slice(-2).map((word) => [...word][0]).join("").toUpperCase() || "—";

  // ------------------------------------------------------------------ render
  function renderTop() {
    const c = state.company;
    $("sidebar-monogram").textContent = c.code ? c.code.slice(0, 2) : "SS";
    $("sidebar-company").textContent = c.legal_name || "Chưa cấu hình doanh nghiệp";
    $("lock-badge").hidden = state.intake.unlocked;
    $("pending-count").hidden = !state.pending.length;
    $("pending-count").textContent = state.pending.length;
  }

  let activeProfileTab = "all";

  function spotlightNode(node) {
    if (!node) return;
    node.classList.remove("is-spotlight");
    void node.offsetWidth;
    node.classList.add("is-spotlight");
    setTimeout(() => node.classList.remove("is-spotlight"), 1200);
  }

  function applyProfileTabFilter(tabName, shouldFocus = false) {
    activeProfileTab = tabName || "all";
    for (const btn of document.querySelectorAll("[data-profile-section]")) {
      if (btn.dataset.profileSection === activeProfileTab) btn.setAttribute("aria-current", "location");
      else btn.removeAttribute("aria-current");
    }
    const groups = document.querySelectorAll("#company-form [data-section-group]");
    for (const g of groups) {
      const groupName = g.dataset.sectionGroup;
      if (activeProfileTab === "all") {
        g.hidden = false;
      } else if (activeProfileTab === "profile-connections") {
        g.hidden = groupName !== "profile-connections" && groupName !== "profile-sync";
        if (g.id === "profile-extra-agent2") g.open = true;
      } else {
        g.hidden = groupName !== activeProfileTab;
      }
    }
    if (!shouldFocus) return;
    if (activeProfileTab === "profile-connections") {
      spotlightNode($("profile-connections"));
      spotlightNode($("profile-extra-agent2"));
      $("profile-agent2")?.focus({ preventScroll: true });
    } else if (activeProfileTab === "profile-sync") {
      spotlightNode($("profile-sync"));
      spotlightNode($("profile-saved"));
    } else if (activeProfileTab !== "all") {
      const sec = $(activeProfileTab);
      spotlightNode(sec);
      const firstInput = sec?.querySelector("input:not(:disabled), select:not(:disabled)");
      if (firstInput) firstInput.focus({ preventScroll: true });
    }
  }

  function renderDefaultSyncList() {
    const syncList = $("sync-result");
    if (!syncList || syncList.dataset.hasCustomSync === "1") return;
    const c = state.company;
    const savedLine = c.updated_at
      ? "Lần lưu gần nhất: " + c.updated_at + " · Mã đơn vị: " + (c.code || "—")
      : "Chưa có lịch sử lưu trên máy này.";
    syncList.replaceChildren(
      el("li", { class: c.updated_at ? "ok" : "" }, savedLine),
      ...state.agents.map((a) =>
        el("li", { class: a.state === "running" ? "ok" : "" },
          el("span", {}, AGENT_LABEL[a.id] + " (" + WORKSPACE_LABEL[a.id] + ")"),
          el("span", {}, a.id === "agent4" ? "Kho dữ liệu DuckDB sẵn sàng" : STATE_TEXT[a.state] + (c.code ? " · Mã " + c.code : ""))
        )
      )
    );
  }

  function isProfileProtected() {
    return !state?.intake?.unlocked;
  }

  function renderConfig() {
    const c = state.company;
    const gateHost = location.hash === "#config" && isProfileProtected() ? $("config-gate") : $("view-data");
    if ($("gate").parentElement !== gateHost) gateHost.prepend($("gate"));
    $("h-data").textContent = location.hash === "#config" ? "Mở khóa hồ sơ doanh nghiệp" : "Mở khóa dữ liệu";
    const form = $("company-form");
    form.hidden = isProfileProtected();
    if (isProfileProtected()) { delete form.dataset.dirty; for (const input of form.elements) if (input.name) input.value = ""; }
    if (!isProfileProtected() && !form.dataset.dirty) for (const [k, v] of Object.entries(c)) if (form.elements[k]) form.elements[k].value = v ?? "";
    profileText("saved-at", c.updated_at ? "Lưu lần cuối " + c.updated_at : "Chưa có lần lưu nào");
    const locked = isProfileProtected();
    $("config-lock").hidden = !locked;
    for (const input of form.elements) if (input.name) input.disabled = locked || profileSaving;
    form.querySelector("button[type=submit]").disabled = locked || profileSaving;
    $("profile-reset").disabled = !form.dataset.dirty || profileSaving;
    $("profile-lock").disabled = locked;
    if ($("profile-fill-demo")) $("profile-fill-demo").disabled = locked || profileSaving;
    if ($("profile-sync-now")) $("profile-sync-now").disabled = locked || profileSaving;
    if ($("profile-start-all-inline")) $("profile-start-all-inline").disabled = state.agents.every((a) => a.state !== "stopped");
    form.setAttribute("aria-busy", String(profileSaving));
    profileText("profile-submit", profileSaving ? "Đang lưu hồ sơ…" : "Lưu hồ sơ");
    const configured = Boolean(c.legal_name && c.code);
    const dirty = Boolean(form.dataset.dirty);
    const label = locked ? "Đang được bảo vệ" : profileSaving ? "Đang lưu hồ sơ" : dirty ? "Có thay đổi chưa lưu" : configured ? "Đã lưu" : "Chưa thiết lập";
    profileText("profile-status", label);

    profileText("profile-save-note", profileSaving ? "Đang lưu, vui lòng chờ" : locked ? "Mở khóa để lưu chỉnh sửa" : dirty ? "Có thay đổi chưa lưu" : "Thông tin được lưu trên máy này");
    updateProfileSummary();

    applyProfileTabFilter(activeProfileTab, false);
  }

  function profileText(id, text) { const node = $(id); if (node && node.textContent !== text) node.textContent = text; }

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
    profileText("profile-summary-format", (c.date_format === "iso" ? "yyyy-mm-dd" : "dd/mm/yyyy") + " · " + (c.number_format === "plain" ? "1250000.50" : "1.250.000,50"));
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
    if ($("sync-result")) delete $("sync-result").dataset.hasCustomSync;
    renderConfig();
  }

  const POPOUT_SVG = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h4M10 2h4v4M6.5 9.5L14 2"/></svg>`;

  function agentPageUrl(a) {
    const page = new URL(a.url, location.href);
    if (a.id !== "agent2") page.searchParams.set("portal", location.origin);
    if (a.id === "agent1") page.searchParams.set("company", state.company.code || "SME");
    return page.href;
  }

  function agentNeedsUnlock(a) {
    return (a.id === "agent2" || (a.id === "agent1" && (state.intake.configured || state.intake.has_biometric))) && (!token || !state.intake.unlocked);
  }

  function makePopoutIcon() {
    const span = el("span", { class: "popout-icon", "aria-hidden": "true" });
    span.innerHTML = POPOUT_SVG;
    return span;
  }

  function renderNav() {
    const signature = state.agents.map((a) => [a.id, a.name, a.state, a.url].join(":")).join("|") + "::" + (state.company.code || "");
    if ($("nav-agents").dataset.signature === signature) { markCurrent(); return; }
    $("nav-agents").dataset.signature = signature;
    $("nav-agents").replaceChildren(
      ...state.agents.map((a) => {
        const label = "Mở " + WORKSPACE_LABEL[a.id] + " ở tab riêng";
        return el("div", { class: "nav-agent-row", "data-agent-row": a.id },
          el("a", { class: "nav-link", href: "#" + a.id, "data-view": a.id },
            el("span", { class: "num", "aria-hidden": "true" }, "A" + a.number),
            el("span", { class: "nav-label" }, WORKSPACE_LABEL[a.id]),
            el("span", { class: "dot " + a.state, title: STATE_TEXT[a.state] })),
          el("a", {
            class: "nav-popout" + (a.state !== "running" ? " is-offline" : ""),
            href: agentPageUrl(a),
            target: "_blank",
            rel: "noopener",
            title: label,
            "aria-label": label,
            onclick: (event) => openAgentStandaloneTab(a.id, event)
          }, makePopoutIcon()));
      }));

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
      title: "Trợ lý Dòng tiền",
      desc: "Dự báo thanh khoản cho nhiều tuần tới, đối soát sao kê và công nợ phải thu",
      icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>`
    },
    agent2: {
      title: "Trợ lý Giám sát",
      desc: "Luật nội bộ, đồ thị và mã hóa đồng cấu học máy phát hiện gian lận",
      icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`
    },
    agent3: {
      title: "Trợ lý Thuế",
      desc: "Thẩm định hóa đơn điện tử, chữ ký số và hỏi đáp về luật thuế và giải thích",
      icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`
    },
    agent4: {
      title: "Trợ lý hỏi đáp",
      desc: "Truy xuất thông tin từ Sổ quản trị và Sổ thuế và giải đáp nhanh có dẫn chứng",
      icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="12" y1="7" x2="12" y2="13"/></svg>`
    }
  };

  function renderOverview() {
    const c = state.company;
    const agentCount = state.agents.length;
    $("profile-lead").textContent = "Thông tin pháp lý, thuế, kỳ kế toán và thiết lập định dạng dùng chung cho " + agentCount + " phân hệ.";
    $("h-overview").textContent = c.legal_name || "Sổ Son";
    $("overview-company-fullname").textContent = "Dòng tiền, giám sát, thuế và hỏi đáp trong cùng một không gian làm việc.";
    const running = state.agents.filter(a => a.state === "running").length;
    $("exec-agents-val").textContent = running + " / " + agentCount + " phân hệ sẵn sàng";
    $("exec-sec-val").textContent = state.intake.unlocked ? "Phiên đang mở khóa" : "Đã khóa bảo vệ";
    $("start-all").hidden = agentCount > 0 && running === agentCount;
    $("start-all").disabled = !state.agents.some(a => a.state === "stopped");
    $("start-all").textContent = agentCount === 1 ? "Bật " + (WORKSPACE_LABEL[state.agents[0].id] || state.agents[0].name) : "Bật tất cả";
    const signature = JSON.stringify([state.company.code || "", state.agents.map((a) => [a.id, a.state, a.url])]);
    if ($("agent-grid").dataset.signature === signature) return;
    $("agent-grid").dataset.signature = signature;
    $("agent-grid").replaceChildren(...state.agents.map((a) => {
      const info = WORKSTATION_INFO[a.id];
      const icon = el("span", { class: "ws-assistant-icon", "aria-hidden": "true" });
      icon.innerHTML = info.icon;
      const statusCls = "ws-status-pill" + (a.state === "starting" ? " is-starting" : a.state !== "running" ? " is-stopped" : "");
      const popoutLabel = "Mở " + info.title + " ở tab riêng";
      return el("article", { class: "workstation-card ws-theme-" + a.id },
        el("div", { class: "ws-card-top" }, icon, el("span", { class: statusCls }, a.state === "running" ? "Sẵn sàng" : STATE_TEXT[a.state])),
        el("h3", { class: "ws-title" }, info.title),
        el("p", { class: "ws-desc" }, info.desc),
        el("div", { class: "ws-card-actions" },
          el("a", { class: "ws-enter-link", href: "#" + a.id }, "Mở trợ lý", el("span", { "aria-hidden": "true" }, "→")),
          el("a", {
            class: "ws-popout-btn" + (a.state !== "running" ? " is-offline" : ""),
            href: agentPageUrl(a),
            target: "_blank",
            rel: "noopener",
            title: popoutLabel,
            "aria-label": popoutLabel,
            onclick: (event) => { event.stopPropagation(); openAgentStandaloneTab(a.id, event); }
          }, makePopoutIcon(), el("span", {}, "Tab riêng"))));
    }));
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



  }

  function renderQueue() {
    const lastResult = intakeResult?.code === state.company.code ? intakeResult.message : "";
    $("intake-result").textContent = lastResult;
    $("intake-result").hidden = !lastResult;
    const busy = Boolean(intakeActivity || pendingCheck());
    const waiting = new Set(state.pending.filter((record) => canRecheckInBatch(record, state.pending)).map((record) => record.id));
    const rows = state.pending.map((r) =>
      el("tr", { role: "row" },
        el("td", { role: "cell" }, el("div", { class: "file-name" }, r.name), el("div", { class: "sub" }, sizeText(r.size) + ", thêm lúc " + r.added_at.slice(11, 16))),
        el("td", { role: "cell" }, r.label, r.note ? el("div", { class: "sub" }, r.note) : null),
        el("td", { role: "cell", class: "sub", "data-label": "Kỳ dữ liệu" }, periodText(r.period)),
        el("td", { role: "cell" }, waiting.has(r.id)
          ? el("span", { class: "stale" }, "Kiểm tra lại sau khi nạp tệp nguồn trong bộ này")
          : checkLines(r)),
        el("td", { role: "cell", class: "right" }, el("div", { class: "queue-actions" },
          el("button", { type: "button", class: "link", disabled: Boolean(intakeActivity || pendingCheck()), onclick: () => recheck(r.id) }, "Kiểm tra lại"),
          el("button", { type: "button", class: "link", disabled: busy || Boolean(r.applied), onclick: () => dropFile(r.id) }, "Bỏ")))));
    $("queue").tBodies[0].replaceChildren(...rows);
    $("queue-empty").hidden = rows.length > 0;
    const tabPending = $("intake-tab-pending");
    if (tabPending) {
      tabPending.hidden = rows.length === 0;
      tabPending.textContent = String(rows.length);
    }
    const ready = state.pending.filter(canWrite);
    const extras = selectionNotes();
    const total = rows.length + extras.length;
    const cleared = $("clear-intake");
    cleared.hidden = !rows.length;
    cleared.disabled = busy || !state.pending.some((record) => !record.applied);
    const targets = new Set(ready.flatMap((record) => record.targets.filter((aid) => record.checks[aid]?.state === "ready")));
    $("intake-summary-count").textContent = "Tổng " + total + " tệp · " + ready.length + " sẵn sàng"
      + (waiting.size ? " · " + waiting.size + " chờ tệp nguồn" : "")
      + (extras.filter((item) => item.done).length ? " · " + extras.filter((item) => item.done).length + " đã có" : "");
    const notes = $("intake-selection-notes");
    notes.hidden = !extras.length;
    notes.replaceChildren(...extras.map((item) => el("li", {}, item.name + " — " + item.message)));
    // Every selected file is already in the sealed package: nothing to write, so the step is complete rather than stuck.
    const allRecorded = !ready.length && !rows.length && extras.length > 0 && extras.every((item) => item.done);
    $("intake-summary-agents").textContent = targets.size
      ? "Nghiệp vụ nhận tệp: " + [...targets].map((aid) => AGENT_LABEL[aid]).join(", ")
      : allRecorded
        ? "Cả " + extras.length + " tệp đã được ghi trước đó, không cần ghi lại. Xem ở Lịch sử dữ liệu."
        : "Chưa có tệp sẵn sàng để phân phối.";
    $("reason-field").hidden = !state.package;
    const button = $("commit");
    button.disabled = !ready.length || Boolean(intakeActivity || pendingCheck());
    button.textContent = intakeActivity?.kind === "commit" ? "Đang nạp dữ liệu…" : "Nạp cả bộ";

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
      history: ["Lịch sử dữ liệu", "Xem các phiên bản đã niêm phong và kết quả ghi vào từng agent."],
    }[stage];
    $("h-intake").textContent = title;
    $("intake-lead").textContent = description;
    $("intake-choose").hidden = stage !== "choose";
    $("intake-queue").hidden = stage !== "review";
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
      const profileGate = location.hash === "#config";
      $("gate-eyebrow").textContent = "Không gian bảo mật doanh nghiệp";
      $("gate-title").textContent = profileGate ? "Hồ sơ doanh nghiệp" : "Nạp dữ liệu chung";
      $("gate-description").textContent = profileGate
        ? "Xác thực để xem và cập nhật thông tin doanh nghiệp."
        : "Mở khóa để tiếp nhận và kiểm tra chứng từ doanh nghiệp.";
      $("gate-lead").textContent = first
        ? "Đặt mật khẩu để bảo vệ hồ sơ và dữ liệu doanh nghiệp."
        : profileGate ? "Nhập mật khẩu hoặc dùng FaceID để xem và chỉnh sửa hồ sơ. Phiên tự khóa sau 20 phút không dùng."
        : "Nhập mật khẩu để nạp hoặc xem gói dữ liệu của doanh nghiệp. Phiên tự khóa sau 20 phút không dùng.";
      $("gate-label").textContent = first ? "Mật khẩu mới (ít nhất 8 ký tự)" : "Mật khẩu";
      $("gate-confirm-field").hidden = !first;
      $("gate-password").autocomplete = first ? "new-password" : "current-password";
      $("gate-submit").textContent = first ? "Đặt mật khẩu và mở" : "Mở khóa";
      const bioSec = $("gate-biometric-section");
      if (bioSec) {
        bioSec.hidden = first;
        bioSec.dataset.enrolled = i.has_biometric ? "1" : "0";
        const bioLabel = $("gate-biometric-label");
        if (bioLabel) {
          bioLabel.textContent = i.has_biometric
            ? "Mở khóa bằng FaceID / Sinh trắc học"
            : "Thiết lập và Mở bằng FaceID (Tùy chọn)";
        }
        const bioPill = $("gate-bio-status-pill");
        if (bioPill) {
          bioPill.textContent = i.has_biometric ? "Đã kích hoạt AI" : "Chưa đăng ký";
          bioPill.className = "gate-bio-badge " + (i.has_biometric ? "is-enrolled" : "is-empty");
        }
        const bioDesc = $("gate-bio-desc");
        if (bioDesc) {
          bioDesc.textContent = i.has_biometric
            ? "Khuôn mặt quản trị đã được mã hóa thành vector 128 chiều. Nhấn nút bên dưới để mở máy quét và đăng nhập tức thì."
            : "Nhập mật khẩu quản trị ở cột bên trái, sau đó nhấn nút bên dưới để quét khuôn mặt 3 khung hình và kích hoạt FaceID.";
        }
        const bioCaption = $("gate-bio-caption");
        if (bioCaption) {
          bioCaption.textContent = i.has_biometric ? "SẴN SÀNG ĐỐI SOÁT · 128-D VECTOR" : "CHỜ ĐĂNG KÝ MẪU KHUÔN MẶT";
        }
      }
      return;
    }
    $("session-left").textContent = "Đã mở khóa · còn " + Math.max(1, Math.round(i.seconds_left / 60)) + " phút";
    const faceBadge = $("face-status-badge");
    if (faceBadge) {
      faceBadge.textContent = i.has_biometric ? "FaceID: Đã kích hoạt" : "FaceID: Chưa đăng ký";
      faceBadge.className = "session-bio-state " + (i.has_biometric ? "is-active" : "is-inactive");
    }
    const faceMng = $("face-manage-btn");
    if (faceMng) {
      faceMng.textContent = i.has_biometric ? "Cập nhật FaceID" : "+ Đăng ký FaceID";
      faceMng.title = i.has_biometric ? "Cập nhật lại khuôn mặt nhận diện FaceID" : "Đăng ký khuôn mặt nhận diện FaceID";
    }
    const faceRm = $("face-remove-btn");
    if (faceRm) {
      faceRm.hidden = !i.has_biometric;
    }
    const c = state.company;
    $("csv-format-help").textContent = "Điền ngày theo " + (c.date_format === "iso" ? "yyyy-mm-dd, ví dụ 2026-12-31" : "dd/mm/yyyy, ví dụ 31/12/2026") + ". Số tiền: " + (c.number_format === "plain" ? "1250000.50, dấu chấm thập phân, không có dấu phân nhóm" : "1.250.000,50, dấu chấm phân nhóm và dấu phẩy thập phân") + ". Giữ nguyên tên cột và lưu tệp CSV với mã hóa UTF-8.";

    $("file-input").disabled = !c.code || Boolean(intakeActivity || pendingCheck());
    $("drop").hidden = !c.code;
    renderSlots();
    renderQueue();
    showIntakeStage(intakeStage);
    renderIntakeProgress();
  }

  const AGENT_SUBTAGS = {
    agent1: "Trợ lý Dòng tiền 13 tuần & Đối soát công nợ",
    agent2: "Kiểm soát gian lận nội bộ, Đồ thị & FHE",
    agent3: "Rà soát thuế GTGT, Chữ ký số & HĐĐT",
    agent4: "Trợ lý hỏi đáp (v_mgmt & v_tax)"
  };
  function latestPortalAgent2Snapshot(companyCode) {
    if (!state?.batches || !companyCode) return "";
    const batches = state.batches.filter((b) => b.company === state.company?.code);
    for (let i = batches.length - 1; i >= 0; i--) {
      const files = batches[i].files || [];
      for (let j = files.length - 1; j >= 0; j--) {
        const r = files[j].results?.agent2;
        if (r?.state === "done" && r.snapshot_id && (!r.company_id || r.company_id === companyCode)) {
          return r.snapshot_id;
        }
      }
    }
    return "";
  }

  async function agent2ResumeUrl(fallback) {
    // Browser preferences never authorize a company. Recheck the current
    // Portal identity and grants before restoring a page in the iframe.
    const context = await api("/agent2/api/v1/ui/context");
    const portalCompany = String(state?.company?.agent2_company || state?.company?.code || "").trim();
    let saved, legacy;
    try { saved = JSON.parse(sessionStorage.getItem("agent2.company.selection")); } catch (e) { /* optional */ }
    try { legacy = JSON.parse(sessionStorage.getItem("agent2.workbench")); } catch (e) { /* optional */ }
    const portalSnap = portalCompany ? latestPortalAgent2Snapshot(portalCompany) : "";
    if (portalSnap && context.companies.includes(portalCompany) && (!legacy || legacy.company !== portalCompany || legacy.actor !== context.actor_id || legacy.context !== (context.context_id || ""))) {
      const defaultAsOf = new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 19);
      legacy = { actor: context.actor_id, context: context.context_id || "", company: portalCompany, snapshot: portalSnap, asOf: defaultAsOf };
      try { sessionStorage.setItem("agent2.workbench", JSON.stringify(legacy)); } catch (e) { /* optional */ }
    }
    if (!saved && legacy?.actor === context.actor_id && (legacy.context === undefined || legacy.context === (context.context_id || ""))) saved = { version: 1, actor: legacy.actor, context: legacy.context_id || context.context_id || "", company: legacy.company, page: "data-import" };
    const pages = ["workspace", "pipeline-workspace", "model-management", "data-import", "encrypted-analysis", "analysis-settings"];
    const validSaved = saved?.version === 1 && saved.actor === context.actor_id && saved.context === (context.context_id || "") && context.companies.includes(saved.company) && pages.includes(saved.page);
    if (!validSaved) {
      if (portalCompany && context.companies.includes(portalCompany)) {
        const target = new URL("/agent2/", location.origin);
        target.hash = new URLSearchParams({ company: portalCompany }).toString();
        return target.href;
      }
      return fallback;
    }
    // Old business workspace pins an HE/P1 run. The shared bundle workspace
    // must not reinterpret that run as a 35-rule bundle observation.
    const page = saved.page === "workspace" ? "pipeline-workspace" : saved.page;
    const chosenCompany = portalCompany && context.companies.includes(portalCompany) ? portalCompany : saved.company;
    const target = new URL("/agent2/" + page, location.origin);
    const fields = new URLSearchParams({ company: chosenCompany });
    if (chosenCompany === saved.company && page === "pipeline-workspace" && saved.page === page && /^[A-Za-z0-9_.:-]{8,128}$/.test(saved.run || "")) fields.set("run", saved.run);
    if (chosenCompany === saved.company && page === "pipeline-workspace" && saved.page === page &&
        /^[A-Za-z0-9_.:-]{1,128}$/.test(saved.transaction || "") && /^rvw_[a-f0-9]{64}$/.test(saved.review || "") && /^[A-Za-z0-9_.:-]{8,128}$/.test(saved.source_run || "")) {
      fields.set("transaction", saved.transaction); fields.set("review", saved.review); fields.set("source_run", saved.source_run);
    }
    target.hash = fields.toString();
    return target.href;
  }

  function renderAgentView() {
    if (!currentAgent) return;
    const a = agentById(currentAgent);
    if (!a) return;
    const noEl = $("agent-no");
    if (noEl) {
      noEl.textContent = "A" + a.number;
      noEl.setAttribute("data-agent", a.id);
    }
    const nameEl = $("agent-name");
    if (nameEl) nameEl.textContent = WORKSPACE_LABEL[a.id] || a.name;
    const subtagEl = $("agent-subtag");
    if (subtagEl) subtagEl.textContent = AGENT_SUBTAGS[a.id] || "Không gian làm việc chuyên biệt";

    const quickSwitch = $("agent-quick-switch");
    if (quickSwitch) {
      quickSwitch.replaceChildren(
        ...state.agents.map((item) =>
          el("a", {
            href: "#" + item.id,
            class: "agent-switch-pill",
            "aria-current": item.id === a.id ? "page" : false,
            title: AGENT_LABEL[item.id] + " · " + WORKSPACE_LABEL[item.id] + " (" + STATE_TEXT[item.state] + ")"
          },
            el("span", { class: "dot " + item.state, "aria-hidden": "true" }),
            el("strong", {}, "A" + item.number),
            el("span", { class: "switch-label-full" }, WORKSPACE_LABEL[item.id])
          )
        )
      );
    }

    const statusEl = $("agent-status");
    if (statusEl) {
      statusEl.className = "status status-pill " + a.state;
      statusEl.replaceChildren(el("span", { class: "dot " + a.state }), el("span", { class: "status-text" }, STATE_TEXT[a.state]));
    }

    const source = $("agent-source");
    if (source) {
      source.textContent = a.id === "agent2" ? "Chọn doanh nghiệp và bản dữ liệu trong Agent 2; quyền theo phiên Portal."
        : a.id === "agent4" ? "Kho mô phỏng độc lập của Agent 4"
        : state.company.code ? ["Hồ sơ " + state.company.code, state.package ? "Gói chung v" + state.package.version : "Chưa niêm phong"].join(" · ")
          : "Cấu hình doanh nghiệp để nạp dữ liệu";
      source.href = a.id !== "agent4" && !state.company.code ? "#config" : "#data";
    }

    const pageUrl = agentPageUrl(a);
    const popoutFab = $("agent-popout-fab");
    if (popoutFab) {
      const popoutLabel = "Mở " + WORKSPACE_LABEL[a.id] + " ở tab riêng";
      popoutFab.href = pageUrl;
      popoutFab.dataset.agent = a.id;
      popoutFab.title = popoutLabel;
      popoutFab.setAttribute("aria-label", popoutLabel);
    }


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
    const dependency = a.id === 'agent2' ? a.dependency : null;
    $("agent2-dependency").hidden = !dependency || dependency.status === 'ready' || a.state === 'stopped';
    $("agent2-dependency").textContent = dependency?.message || '';
    if ($("agent2-recover")) $("agent2-recover").hidden = !dependency || dependency.status === 'ready' || !a.owned || !dependency.can_recover;
    const frame = $("agent-frame-" + a.id) || $("agent-frame");
    if (a.state === "running") {
      offlineFailures[a.id] = 0;
    } else {
      offlineFailures[a.id] = (offlineFailures[a.id] || 0) + 1;
    }

    // Grace period: keep frame visible during temporary glitches (< 3 poll cycles = 12s)
    const needsUnlock = agentNeedsUnlock(a);
    const isOnline = (a.state === "running" || (frame.dataset.src && a.state === "starting" && offlineFailures[a.id] < 3)) && !needsUnlock;
    if (popoutFab) popoutFab.hidden = !isOnline;

    for (const id of ["agent1", "agent2", "agent3", "agent4"]) {
      const f = $("agent-frame-" + id);
      if (f && id !== a.id) f.hidden = true;
    }

    if (isOnline) {
      if (frame.dataset.src !== pageUrl) {
        startLoading();
        frame.classList.add("is-loading");
        frame.dataset.src = pageUrl;
        if (a.id !== "agent2") frame.src = pageUrl;
        else {
          const routeEpoch = ++agent2RouteEpoch, version = authVersion;
          agent2ResumeUrl(pageUrl).catch(() => pageUrl).then(target => {
            if (routeEpoch !== agent2RouteEpoch || version !== authVersion || currentAgent !== "agent2" || frame.dataset.src !== pageUrl || !token || !state.intake.unlocked) {
              frame.classList.remove("is-loading");
              stopLoading();
              return;
            }
            frame.src = target;
            if (popoutFab && currentAgent === "agent2") popoutFab.href = target;
          });
        }
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
      if (a.state === "stopped" || needsUnlock) {
        if (a.id === "agent2") agent2RouteEpoch += 1;
        frame.removeAttribute("src"); delete frame.dataset.src;
      }
      $("agent-off").hidden = false;
    }
    if (!isOnline) {
      if ($("agent-off-title")) {
        $("agent-off-title").textContent = needsUnlock && a.state === "running" ? "Cần mở khóa phiên làm việc" : a.state === "starting" ? "Agent đang khởi động" : "Agent đang tắt";
      }
      $("agent-off-text").textContent =
        needsUnlock && a.state === "running" ? `${WORKSPACE_LABEL[a.id]} yêu cầu mở khóa phiên bảo mật để truy cập dữ liệu doanh nghiệp.`
          : a.state === "starting" ? "Đang khởi động, trang sẽ tự mở khi agent sẵn sàng."
            : a.state === "busy-port" ? "Cổng " + a.port + " đang bị chương trình khác dùng. Tắt chương trình đó hoặc đổi cổng trong portal/config.local.json."
              : "Bật agent để mở giao diện. Portal chạy agent từ thư mục " + a.root + ".";
      $("agent-start").hidden = a.state !== "stopped";
      if ($("agent-unlock-link")) $("agent-unlock-link").hidden = !(needsUnlock && a.state === "running");
      if ($("agent-log-details")) $("agent-log-details").hidden = needsUnlock;
      if (!needsUnlock) api(a.log).then((d) => ($("agent-log").textContent = d.log || "Chưa có nhật ký.")).catch(() => {});
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

  let refreshInFlight = null;
  function refresh() {
    if (!refreshInFlight) refreshInFlight = fetchState().finally(() => { refreshInFlight = null; });
    return refreshInFlight;
  }

  async function fetchState() {
    const version = profileVersion;
    const reqAuthVersion = authVersion;
    const reqToken = token;
    try {
      const next = filterRuntimeState(await api("/api/state", { silent: Boolean(state) }));
      if (version !== profileVersion && state) next.company = state.company;
      if (reqAuthVersion !== authVersion || reqToken !== token) {
        if (state) {
          next.intake = state.intake;
          next.pending = state.pending;
          next.batches = state.batches;
          state = next;
          render();
        }
        return;
      }
      state = next;
      if (reqToken && reqToken === token && !state.intake.unlocked) {
        setToken("");
      }
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
    document.querySelectorAll(".nav-agent-row").forEach((row) =>
      row.classList.toggle("is-active", row.dataset.agentRow === view));
  }

  const TITLES = { overview: "Tổng quan", config: "Cấu hình", data: "Nạp dữ liệu" };

  function show() {
    let view = location.hash.slice(1) || "overview";
    if (/^agent[1-4]$/.test(view) && !isAgentEnabled(view)) {
      history.replaceState(null, "", "#overview");
      view = "overview";
    }
    const isAgent = /^agent[1-4]$/.test(view) && isAgentEnabled(view);
    for (const id of ["overview", "config", "data"]) $("view-" + id).hidden = id !== view;
    $("view-agent").hidden = !isAgent;
    if (view !== currentAgent) {
      agent2RouteEpoch += 1;
      if (currentAgent === "agent2") {
        const frame = $("agent-frame-agent2") || $("agent-frame");
        if (frame) { frame.removeAttribute("src"); delete frame.dataset.src; }
      }
    }
    if (!isAgent) {
      for (const id of ["agent1", "agent2", "agent3", "agent4"]) {
        const f = $("agent-frame-" + id);
        if (f) f.hidden = true;
      }
      const singleFrame = $("agent-frame");
      if (singleFrame) singleFrame.hidden = true;
      const popoutFab = $("agent-popout-fab");
      if (popoutFab) popoutFab.hidden = true;
    }
    currentAgent = isAgent ? view : null;
    if (sidebarMedia.matches) setSidebarOpen(false, $("sidebar").contains(document.activeElement));
    if (state) render();
    markCurrent();
    document.title = (isAgent && state ? AGENT_LABEL[view] + " · " + WORKSPACE_LABEL[view] : TITLES[view] || "") + " | Sổ Son — Phòng Kế Toán Số";
  }

  // ------------------------------------------------------------------ actions

  async function openAgentStandaloneTab(aid, event) {
    const a = state && agentById(aid);
    if (!a) {
      event?.preventDefault();
      return;
    }
    if (a.state !== "running") {
      event?.preventDefault();
      toast(
        a.state === "starting"
          ? AGENT_LABEL[aid] + " đang khởi động, vui lòng đợi thêm giây lát rồi mở tab riêng."
          : "Bật " + AGENT_LABEL[aid] + " rồi mở tab riêng.",
        true
      );
      return;
    }
    if (agentNeedsUnlock(a)) {
      event?.preventDefault();
      location.hash = "data";
      toast("Mở khóa phiên làm việc để mở " + WORKSPACE_LABEL[aid] + " ở tab riêng.", true);
      return;
    }
    if (aid === "agent2") {
      event?.preventDefault();
      const tab = window.open("about:blank", "_blank");
      if (!tab) { toast("Trình duyệt đã chặn tab mới. Cho phép mở tab rồi bấm lại.", true); return; }
      try {
        const version = authVersion;
        const target = await agent2ResumeUrl(new URL("/agent2/", location.href).href);
        if (version !== authVersion || !token || !state.intake.unlocked) { tab.close(); return; }
        tab.sessionStorage.setItem("kt-session", token);
        for (const key of ["agent2.company.selection", "agent2.workbench"]) {
          const value = sessionStorage.getItem(key);
          if (value) tab.sessionStorage.setItem(key, value);
        }
        tab.opener = null;
        if (!tab.closed) tab.location.replace(target);
      } catch (err) {
        if (!tab.closed) tab.close();
        toast("Không mở được Agent 2 ở tab riêng. Dùng Agent 2 ngay trong Portal.", true);
      }
      return;
    }
    if (aid === "agent1") {
      event?.preventDefault();
      const company = state.company.code || "SME";
      const agentOrigin = new URL(a.url, location.href).origin;
      // Open synchronously during the click, then sever the opener before any navigation.
      const tab = window.open("about:blank", "_blank");
      if (!tab) { toast("Trình duyệt đã chặn tab mới. Cho phép mở tab rồi bấm lại.", true); return; }
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
      return;
    }
    // Agent 3 and Agent 4 open directly via href with target="_blank" rel="noopener".
  }

  async function toggleAgent(a) {
    const action = a.state === "running" || a.state === "starting" ? "stop" : "start";
    $("agent-start").disabled=true;if ($("agent-toggle")) $("agent-toggle").disabled=true;
    try {
      await api("/api/agents/" + a.id + "/" + action, { method: "POST" });
      toast(action === "start" ? AGENT_LABEL[a.id] + " đang khởi động." : AGENT_LABEL[a.id] + " đã tắt.");
    } catch (err) { toast(err.message, true); }
    finally {$("agent-start").disabled=false;if ($("agent-toggle")) $("agent-toggle").disabled=false;}
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
      if (state && state.intake) {
        state.intake.configured = true;
        state.intake.unlocked = true;
        state.intake.seconds_left = 1200;
        render();
      }
      form.reset();
      await refresh();
    } catch (err) {
      $("gate-error").textContent = err.message;
    } finally { button.disabled = false; }
  }

  async function lockNow() {
    await api("/api/intake/lock", { method: "POST" }).catch(() => {});
    setToken("");
    if (state && state.intake) {
      state.intake.unlocked = false;
      state.pending = [];
      state.batches = [];
      render();
    }
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

  const FACE_FRAME_COUNT = 3;
  const FACE_FRAME_INTERVAL_MS = 120;

  let faceModelsLoaded = false;
  let faceStream = null;
  let faceAnimationId = null;
  let isFaceCompleted = false;

  function isValidFaceDescriptor(vec) {
    return Array.isArray(vec) && vec.length === 128 && vec.every((v) => typeof v === "number" && Number.isFinite(v));
  }

  function averageFaceDescriptors(descriptors) {
    if (!Array.isArray(descriptors) || !descriptors.length) return [];
    const dim = descriptors[0].length;
    if (dim !== 128) return [];
    const sums = new Array(dim).fill(0);
    for (const desc of descriptors) {
      if (!isValidFaceDescriptor(desc)) return [];
      for (let i = 0; i < dim; i++) {
        sums[i] += desc[i];
      }
    }
    return sums.map((s) => Number((s / descriptors.length).toFixed(8)));
  }

  function approxVndPortal(raw) {
    if (raw === null || raw === undefined || raw === "") return "";
    let str = typeof raw === "bigint"
      ? raw.toString()
      : typeof raw === "number"
        ? (Number.isFinite(raw) ? (Number.isInteger(raw) ? raw.toFixed(0) : raw.toFixed(4)) : "")
        : String(raw).trim();
    str = str.replace(/\u2212/g, "-").replace(/\s+/g, "");
    const m = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(str);
    if (!m) return "";
    let neg = m[1] === "-";
    let absVnd = BigInt(m[2]) + (Number((m[3] || "0")[0] || "0") >= 5 ? 1n : 0n);
    if (absVnd === 0n) neg = false;
    if (absVnd < 1000000n) return "";
    let tenths, unit;
    if (absVnd >= 1000000000000n) {
      tenths = (absVnd * 10n + 500000000000n) / 1000000000000n;
      unit = "nghìn tỷ đồng";
    } else if (absVnd >= 1000000000n) {
      tenths = (absVnd * 10n + 500000000n) / 1000000000n;
      unit = "tỷ đồng";
      if (tenths >= 10000n) { tenths = (tenths + 500n) / 1000n; unit = "nghìn tỷ đồng"; }
    } else {
      tenths = (absVnd * 10n + 500000n) / 1000000n;
      unit = "triệu đồng";
      if (tenths >= 10000n) { tenths = (tenths + 500n) / 1000n; unit = "tỷ đồng"; }
    }
    const w = (tenths / 10n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const r = tenths % 10n;
    return (neg ? "âm " : "") + (r === 0n ? w : w + "," + r.toString()) + " " + unit;
  }

  function updateFaceHud({ step = 1, pct = 15, status = "", framesText = "", scanState = "scanning" }) {
    const viewport = $("face-viewport");
    if (viewport) viewport.dataset.scanState = scanState;
    const bar = $("face-progress-bar");
    if (bar) {
      const clamped = Math.max(0, Math.min(100, pct));
      bar.dataset.pct = String(Math.round(clamped / 5) * 5);
    }
    const statusEl = $("face-hud-status");
    if (statusEl && status) statusEl.textContent = status;
    const framesEl = $("face-hud-frames");
    if (framesEl && framesText) framesEl.textContent = framesText;
    for (let i = 1; i <= 3; i++) {
      const sEl = $("face-step-" + i);
      if (!sEl) continue;
      sEl.classList.toggle("is-done", i < step);
      sEl.classList.toggle("is-active", i === step);
    }
  }

  function drawFaceOverlay(ctx, detection, canvas) {
    if (!ctx || !detection || !detection.landmarks) return;
    const dims = { width: canvas.width, height: canvas.height };
    const resized = faceapi.resizeResults(detection, dims);
    const pts = resized.landmarks.positions;
    if (!pts || !pts.length) return;

    ctx.save();
    // Draw subtle gold/emerald landmark points
    ctx.fillStyle = "rgba(16, 185, 129, 0.82)";
    ctx.strokeStyle = "rgba(212, 175, 55, 0.45)";
    ctx.lineWidth = 1.1;

    // Connect jaw, eyebrows, nose, eyes, mouth contours
    const groups = [
      resized.landmarks.getJawOutline(),
      resized.landmarks.getLeftEyeBrow(),
      resized.landmarks.getRightEyeBrow(),
      resized.landmarks.getNose(),
      resized.landmarks.getLeftEye(),
      resized.landmarks.getRightEye(),
      resized.landmarks.getMouth()
    ];
    for (const grp of groups) {
      if (!grp || grp.length < 2) continue;
      ctx.beginPath();
      ctx.moveTo(grp[0].x, grp[0].y);
      for (let i = 1; i < grp.length; i++) ctx.lineTo(grp[i].x, grp[i].y);
      ctx.stroke();
    }

    for (const pt of pts) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  async function loadFaceModels() {
    if (faceModelsLoaded) return true;
    if (typeof faceapi === "undefined") {
      throw new Error("Chưa tải được thư viện AI face-api.js.");
    }
    const MODEL_PATH = "/models";
    $("face-spinner").hidden = false;
    $("face-loading-text").textContent = "Đang nạp mạng nơ-ron nhận diện 128 chiều...";
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
    if (reticle) reticle.classList.remove("active", "verified", "err");
  }

  async function openFaceModal(mode, password = "") {
    const modal = $("face-modal");
    const video = $("face-video");
    const canvas = $("face-canvas");
    const titleEl = $("face-modal-title");
    const modeBadge = $("face-mode-badge");
    const feedback = $("face-feedback");
    const reticle = document.querySelector(".face-reticle");
    const targetFrames = FACE_FRAME_COUNT;

    modal.hidden = false;
    isFaceCompleted = false;
    if (modeBadge) {
      modeBadge.textContent = mode === "register" ? "ĐĂNG KÝ SINH TRẮC HỌC · 3 KHUNG LIÊN TIẾP" : "XÁC THỰC FACEID · 3 KHUNG LIÊN TIẾP";
    }
    titleEl.textContent = mode === "register" ? "Thiết lập Khuôn mặt Quản trị" : "Quét Khuôn mặt để Mở khóa";
    feedback.className = "face-feedback";
    feedback.textContent = "Đang khởi tạo ống kính và mạng nơ-ron nhận diện 128 chiều...";
    if (reticle) reticle.classList.remove("active", "verified", "err");
    updateFaceHud({
      step: 1,
      pct: 15,
      status: "KHỞI ĐỘNG ỐNG KÍNH",
      framesText: "0 / " + targetFrames + " KHUNG",
      scanState: "scanning"
    });

    try {
      await loadFaceModels();
      faceStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
      });
      video.srcObject = faceStream;
      await video.play();

      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;

      // Allow camera auto-exposure & white-balance to stabilize on first open
      await new Promise((resolve) => setTimeout(resolve, 240));
      if (!faceStream || modal.hidden || isFaceCompleted) return;

      updateFaceHud({
        step: 2,
        pct: 30,
        status: "ĐANG TÌM KHUÔN MẶT",
        framesText: "0 / " + targetFrames + " KHUNG",
        scanState: "scanning"
      });
      feedback.textContent = "Nhìn thẳng vào khung ngắm để thu 3 khung hình liên tiếp (~120ms/khung)...";

      let capturedDescriptors = [];
      let lastCaptureAt = 0;
      let verifyRetries = 0;
      const maxVerifyRetries = 3;
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
              drawFaceOverlay(ctx, detection, canvas);
              if (reticle) {
                reticle.classList.remove("err");
                reticle.classList.add("active");
              }

              const now = performance.now();
              if (capturedDescriptors.length === 0 || now - lastCaptureAt >= FACE_FRAME_INTERVAL_MS) {
                const frameDesc = Array.from(detection.descriptor, (x) => Number(x));
                if (!isValidFaceDescriptor(frameDesc)) {
                  capturedDescriptors = [];
                  lastCaptureAt = 0;
                  throw new Error("Vector đặc trưng khung hình không hợp lệ, đang thu lại...");
                }
                capturedDescriptors.push(frameDesc);
                lastCaptureAt = now;

                const capturedCount = capturedDescriptors.length;
                const stepPct = Math.min(90, 35 + Math.round((capturedCount / targetFrames) * 55));
                updateFaceHud({
                  step: capturedCount >= targetFrames ? 3 : 2,
                  pct: stepPct,
                  status: capturedCount >= targetFrames ? "TỔNG HỢP 3 KHUNG · 128-D" : "THU KHUNG " + capturedCount + "/" + targetFrames,
                  framesText: capturedCount + " / " + targetFrames + " KHUNG",
                  scanState: "locked"
                });
                feedback.className = "face-feedback ok";
                feedback.textContent = capturedCount < targetFrames
                  ? "Đã chụp khung hình " + capturedCount + "/" + targetFrames + " · Giữ ổn định khuôn mặt..."
                  : "Đã thu đủ 3/3 khung hình liên tiếp · Đang tổng hợp vector 128 chiều...";
              }

              if (capturedDescriptors.length >= targetFrames) {
                const descriptors = capturedDescriptors.slice(0, targetFrames);
                const averagedDescriptor = averageFaceDescriptors(descriptors);
                if (!isValidFaceDescriptor(averagedDescriptor)) {
                  capturedDescriptors = [];
                  lastCaptureAt = 0;
                  throw new Error("Không tổng hợp được vector 128 chiều hợp lệ.");
                }

                if (mode === "register") {
                  isFaceCompleted = true;
                  updateFaceHud({
                    step: 3,
                    pct: 95,
                    status: "MÃ HÓA & NIÊM PHONG",
                    framesText: targetFrames + " / " + targetFrames + " KHUNG",
                    scanState: "locked"
                  });
                  feedback.textContent = "Đang lưu 3 mẫu khung hình và trung bình hóa vector 128 chiều...";
                  const res = await api("/api/intake/face/register", {
                    method: "POST",
                    json: {
                      descriptor: averagedDescriptor,
                      descriptors,
                      password: password
                    }
                  });
                  updateFaceHud({
                    step: 4,
                    pct: 100,
                    status: "HOÀN TẤT ĐĂNG KÝ",
                    framesText: targetFrames + " / " + targetFrames + " KHUNG",
                    scanState: "verified"
                  });
                  if (reticle) reticle.classList.add("verified");
                  if (res && res.token) setToken(res.token);
                  if (state && state.intake) {
                    state.intake.unlocked = true;
                    state.intake.has_biometric = true;
                    state.intake.seconds_left = 1200;
                    render();
                  }
                  stopFaceCamera();
                  toast("Đã đăng ký FaceID (3 khung hình) và mở khóa thành công!");
                  await refresh();
                  return;
                } else {
                  feedback.textContent = "Đang đối soát 3 khung hình khuôn mặt 128 chiều...";
                  try {
                    const res = await api("/api/intake/face/verify", {
                      method: "POST",
                      json: {
                        descriptor: averagedDescriptor,
                        descriptors
                      }
                    });
                    isFaceCompleted = true;
                    updateFaceHud({
                      step: 4,
                      pct: 100,
                      status: "MỞ KHÓA THÀNH CÔNG",
                      framesText: targetFrames + " / " + targetFrames + " KHUNG",
                      scanState: "verified"
                    });
                    if (reticle) reticle.classList.add("verified");
                    setToken(res.token);
                    if (state && state.intake) {
                      state.intake.unlocked = true;
                      state.intake.seconds_left = 1200;
                      render();
                    }
                    stopFaceCamera();
                    toast("Đối soát FaceID 3 khung hình chính xác! Đã mở khóa.");
                    await refresh();
                    return;
                  } catch (verifyErr) {
                    verifyRetries++;
                    capturedDescriptors = [];
                    lastCaptureAt = 0;
                    if (verifyRetries < maxVerifyRetries) {
                      updateFaceHud({
                        step: 2,
                        pct: 40,
                        status: "QUÉT LẠI (" + verifyRetries + "/" + maxVerifyRetries + ")",
                        framesText: "0 / " + targetFrames + " KHUNG",
                        scanState: "scanning"
                      });
                      feedback.className = "face-feedback";
                      feedback.textContent = "Chưa khớp mẫu ổn định, đang thu lại 3 khung hình (" + verifyRetries + "/" + maxVerifyRetries + ")...";
                    } else {
                      isFaceCompleted = true;
                      if (reticle) {
                        reticle.classList.remove("active");
                        reticle.classList.add("err");
                      }
                      updateFaceHud({
                        step: 3,
                        pct: 100,
                        status: "KHÔNG KHỚP MẪU",
                        framesText: "THẤT BẠI",
                        scanState: "error"
                      });
                      feedback.className = "face-feedback err";
                      feedback.textContent = verifyErr.message || "Khuôn mặt không khớp sau 3 lần đối soát. Vui lòng thử lại hoặc dùng mật khẩu.";
                      return;
                    }
                  }
                }
              }
            } else {
              capturedDescriptors = [];
              lastCaptureAt = 0;
              if (reticle) reticle.classList.remove("active");
              updateFaceHud({
                step: 2,
                pct: 25,
                status: "ĐANG TÌM KHUÔN MẶT",
                framesText: "0 / " + targetFrames + " KHUNG",
                scanState: "scanning"
              });
              feedback.className = "face-feedback";
              feedback.textContent = "Vui lòng giữ khuôn mặt nằm gọn trong khung ngắm để chụp đủ 3 khung hình liên tiếp...";
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
        if (errEl) errEl.textContent = "Nhập mật khẩu quản trị ở cột bên trái trước, sau đó bấm lại nút Thiết lập FaceID.";
        pwInput?.focus();
        return;
      }
      openFaceModal("register", pw);
      return;
    }

    // Biometric already enrolled -> open direct camera scanner
    openFaceModal("verify");
  }

  async function removeFaceBiometric() {
    if (!state?.intake?.has_biometric) return;
    if (!confirm("Bạn có chắc chắn muốn xóa mẫu khuôn mặt FaceID hiện tại trên máy này?")) return;
    try {
      await api("/api/intake/face/remove", { method: "POST" });
      if (state && state.intake) state.intake.has_biometric = false;
      render();
      toast("Đã hủy đăng ký FaceID.");
      await refresh();
    } catch (err) {
      toast(err.message, true);
    }
  }

  let intakeUploadBusy = false;
  async function upload(files) {
    if (intakeUploadBusy || intakeActivity || pendingCheck()) { toast("Đang xử lý tệp đã chọn. Hãy chờ kết quả trước khi chọn thêm.", false, true); return; }
    const code = state?.company.code;
    if (!code) return;
    intakeUploadBusy = true;
    let uploaded = 0;
    const extras = [];
    const received = new Set();
    intakeSelection = { code, extras };
    intakeResult = null;
    try {
      for (const [index, file] of files.entries()) {
        startIntakeActivity("Đang kiểm tra tệp", file.name);
        toast("Đang kiểm tra " + file.name + ". Tệp lịch sử lớn có thể mất vài phút; hãy chờ kết quả.", false, true);
        try {
          const query = new URLSearchParams({ name: file.name, company: code });
          const result = await api("/api/inbox?" + query, { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" }, signal: AbortSignal.timeout(660000) });
          if (result.already_recorded) extras.push({ name: file.name, done: true, message: "Đã ghi trước đó" });
          else if (received.has(result.id)) extras.push({ name: file.name, done: true, message: "Tệp trùng trong lượt chọn; giữ một bản." });
          else { received.add(result.id); uploaded++; }
        } catch (err) {
          extras.push({ name: file.name, message: err.message });
          if (err.locked) {
            for (const item of files.slice(index + 1)) extras.push({ name: item.name, message: "Chưa gửi vì phiên đã khóa" });
            break;
          }
        }
      }
      await refresh();
      const already = extras.filter((item) => item.done).length;
      toast("Đã nhận " + uploaded + "/" + files.length + " tệp"
        + (already ? " · " + already + " đã có" : "")
        + (extras.length > already ? " · " + (extras.length - already) + " chưa vào hàng chờ" : "") + ".", extras.length > already);
      if ((uploaded || extras.length) && state.intake.unlocked && location.hash === "#data") showIntakeStage("review", true);
    } finally {
      intakeUploadBusy = false;
      endIntakeActivity();
    }
  }

  async function recheck(id) {
    if (intakeUploadBusy || intakeActivity || pendingCheck()) { toast("Đang xử lý tệp đã chọn. Hãy chờ kết quả.", false, true); return; }
    intakeUploadBusy = true;
    startIntakeActivity("Đang kiểm tra lại tệp", state.pending.find((r) => r.id === id)?.name || "Tệp đã chọn");
    toast("Đang kiểm tra lại tệp. Tệp lịch sử lớn có thể mất vài phút; hãy chờ kết quả.", false, true);
    try {
      await api("/api/inbox/" + id + "/check", { method: "POST" });
      await refresh();
      toast("Đã kiểm tra lại. Xem kết quả của tệp trước khi xác nhận nạp.");
    } catch (err) {
      toast(err.message, true);
    } finally {
      intakeUploadBusy = false;
      endIntakeActivity();
    }
  }

  async function dropFile(id) {
    await api("/api/inbox/" + id + "/delete", { method: "POST" }).catch((err) => toast(err.message, true));
    refresh();
  }

  function selectionNotes() {
    return intakeSelection?.code === state.company.code ? intakeSelection.extras : [];
  }

  async function clearIntake() {
    if (intakeUploadBusy || intakeActivity || pendingCheck()) return;
    if (!window.confirm("Xóa tất cả tệp chưa ghi trong hàng chờ của doanh nghiệp này?")) return;
    startIntakeActivity("Đang xóa tệp chờ", "");
    try {
      const res = await api("/api/inbox/clear", { method: "POST", json: { company: state.company.code } });
      intakeSelection = null;
      intakeResult = null;
      await refresh();
      toast("Đã xóa " + res.removed + " tệp chờ." + (res.retained ? " " + res.retained + " tệp đã ghi một phần vẫn cần hoàn tất." : ""));
      if (!res.retained) showIntakeStage("choose");
    } catch (err) { toast(err.message, true); }
    finally { endIntakeActivity(); }
  }

  function canWrite(record) {
    const checks = Object.values(record.checks || {});
    return checks.some((c) => c.state === "ready") &&
      (record.kind !== "shared_bank" || checks.every((c) => c.state === "ready" || c.state === "done"));
  }

  function canRecheckInBatch(record, records) {
    const parents = {
      "a1:statements": ["shared_bank", "a1:bank"],
      "a1:payments": ["a1:invoices", "shared_bank", "a1:bank"],
      "a1:actions": ["a1:invoices"],
      "a1:expense_payments": ["a1:outflows", "shared_bank", "a1:bank"]
    }[record.kind];
    return record.checks?.agent1?.state === "error" && parents
      && records.some((item) => parents.includes(item.kind) && canWrite(item));
  }

  async function commitAll() {
    if (intakeActivity || pendingCheck()) { toast("Chờ tác vụ đang xử lý hoàn tất trước khi ghi.", false, true); return; }
    if (!state.pending.some(canWrite)) return;
    const ids = state.pending.map((r) => r.id);
    const extras = selectionNotes();
    const button = $("commit");
    const reason = $("reason").value.trim();
    if (state.package && reason.length < 10) { $("reason").focus(); toast("Gói đã niêm phong: nhập lý do bổ sung hoặc thay thế, ít nhất 10 ký tự.", true); return; }
    startIntakeActivity("Đang ghi dữ liệu", ids.length + " tệp trong hàng chờ", "commit");
    button.disabled = true;
    button.textContent = "Đang ghi";
    try {
      const res = await api("/api/inbox/commit", { method: "POST", json: { ids, reason }, signal: AbortSignal.timeout(1800000) });
      if ((res.batch?.files || []).some((f) => f.results?.agent2?.snapshot_id)) {
        try {
          sessionStorage.removeItem("agent2.workbench");
          sessionStorage.removeItem("agent2.company.selection");
        } catch (e) { /* optional */ }
        const a2Frame = $("agent-frame-agent2");
        if (a2Frame) { a2Frame.removeAttribute("src"); delete a2Frame.dataset.src; }
      }
      $("reason").value = "";
      const written = res.batch.written_count ?? res.batch.files.length;
      const already = (res.batch.already_count || 0) + extras.filter((item) => item.done).length;
      const total = ids.length + extras.length;
      const remaining = total - written - already;
      intakeStage = remaining ? "review" : "history";
      const message = "Đã ghi " + written + "/" + total + " tệp"
        + (already ? " · " + already + " đã có" : "")
        + (remaining ? " · " + remaining + " chưa ghi. Xem chi tiết trong hàng chờ." : " · Phiên bản " + res.batch.version + ".");
      intakeResult = { code: res.batch.company, message };
      toast(message, Boolean(remaining));
      if (!remaining) intakeSelection = null;
    } catch (err) { toast(err.message, true); }
    finally { endIntakeActivity(); }
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
    if (profileSaving || isProfileProtected()) return;
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
      if ($("sync-result")) $("sync-result").dataset.hasCustomSync = "1";
      $("sync-result")?.replaceChildren(
        el("li", { class: "ok" }, "Đã lưu hồ sơ doanh nghiệp " + res.company.code + "."),
        ...Object.entries(res.sync || {}).map(([aid, s]) => syncItem(aid, s)));
      spotlightNode($("profile-sync"));
      toast("Đã lưu hồ sơ doanh nghiệp.");
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
    const version = authVersion;
    const source = a1Frame.contentWindow;
    try {
      const { key } = await api("/api/agents/agent1/key");
      if (key && version === authVersion && source === a1Frame.contentWindow) source.postMessage({ type: "platform-access-key", key }, origin);
    } catch (err) { toast(err.message, true); }
  });

  // ------------------------------------------------------------------ wire up
  window.addEventListener("hashchange", show);

  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    $("content").focus();
  });
  $("menu-toggle").addEventListener("click", () => {
    setSidebarOpen($("menu-toggle").getAttribute("aria-expanded") !== "true");
  });
  $("agent-popout-fab")?.addEventListener("click", (event) => {
    if (currentAgent) openAgentStandaloneTab(currentAgent, event);
    else event.preventDefault();
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
      applyProfileTabFilter(button.dataset.profileSection, true);
    });
  }
  $("profile-summary-aside")?.addEventListener("click", (event) => {
    const sectionTarget = event.target.closest("[data-focus-section]");
    if (sectionTarget) {
      applyProfileTabFilter(sectionTarget.dataset.focusSection, true);
      return;
    }
    const fieldTarget = event.target.closest("[data-focus-field]");
    if (!fieldTarget) return;
    const input = $(fieldTarget.dataset.focusField);
    if (!input) return;
    const group = input.closest("[data-section-group]");
    if (group && group.hidden) applyProfileTabFilter("all", false);
    const locked = isProfileProtected();
    if (locked) {
      spotlightNode($("config-lock"));
      $("config-lock")?.scrollIntoView({ behavior: "smooth", block: "center" });
      toast("Hồ sơ đang được bảo vệ. Nhấn 'Mở khóa để chỉnh sửa' phía trên.", true);
      return;
    }
    const fieldWrap = input.closest(".field") || group;
    spotlightNode(fieldWrap);
    input.scrollIntoView({ behavior: "smooth", block: "center" });
    input.focus({ preventScroll: true });
  });
  $("profile-fill-demo")?.addEventListener("click", () => {
    const locked = isProfileProtected();
    if (locked || profileSaving) return;
    const form = $("company-form");
    const defaults = {
      legal_name: "CÔNG TY TNHH DEMO KẾ TOÁN",
      tax_code: "0101243150",
      code: "KT",
      registered_address: "Số 12 Lê Duẩn, Quận Hải Châu, TP. Đà Nẵng",
      industry: "Dịch vụ kế toán và tư vấn thuế",
      vat_method: "DEDUCTION",
      filing_period: "QUARTER",
      fiscal_year_end_month: "12",
      date_format: "dmy",
      number_format: "vi-VN"
    };
    for (const [k, v] of Object.entries(defaults)) {
      if (form.elements[k] && !form.elements[k].value.trim()) form.elements[k].value = v;
    }
    if (!form.elements.registered_address.value.trim()) form.elements.registered_address.value = defaults.registered_address;
    if (!form.elements.industry.value.trim()) form.elements.industry.value = defaults.industry;
    form.dataset.dirty = "1";
    renderConfig();
    toast("Đã điền thông tin mẫu. Nhấn 'Lưu hồ sơ' để lưu lại.");
  });
  $("profile-sync-now")?.addEventListener("click", () => {
    $("company-form")?.requestSubmit();
  });
  $("profile-start-all-inline")?.addEventListener("click", () => {
    $("start-all")?.click();
  });
  $("profile-reset").addEventListener("click", () => {
    if (profileSaving) return;
    delete $("company-form").dataset.dirty;
    showProfileErrors({});
    if ($("sync-result")) delete $("sync-result").dataset.hasCustomSync;
    renderConfig();
    $("profile-status")?.setAttribute("tabindex", "-1");
    $("profile-status")?.focus({ preventScroll:true });
  });
  $("company-form").addEventListener("focusin", (event) => {
    if (!event.target.matches("input,select,a,button")) return;
    const target = event.target;
    requestAnimationFrame(() => {
      if (!target.isConnected || target.closest(".profile-actions")) return;
      const bounds = target.getBoundingClientRect();
      const actions = $("profile-submit").closest(".profile-actions").getBoundingClientRect();
      const header = { bottom: 0 };
      if (bounds.bottom > actions.top - 12 || bounds.top < header.bottom + 12) target.scrollIntoView({ block:"center", behavior:"instant" });
    });
  });
  $("gate-form").addEventListener("submit", unlockGate);
  $("gate-biometric-btn")?.addEventListener("click", unlockBiometric);
  $("face-manage-btn")?.addEventListener("click", () => openFaceModal("register"));
  $("face-remove-btn")?.addEventListener("click", removeFaceBiometric);
  $("face-modal-close")?.addEventListener("click", stopFaceCamera);
  $("face-cancel-btn")?.addEventListener("click", stopFaceCamera);
  $("lock-now").addEventListener("click", lockNow);
  $("profile-lock").addEventListener("click", lockNow);
  $("audit").addEventListener("toggle", (e) => e.target.open && loadAudit());
  $("start-all").addEventListener("click", async () => {
    for (const a of state.agents.filter((x) => x.state === "stopped")) {
      await api("/api/agents/" + a.id + "/start", { method: "POST" }).catch((err) => toast(err.message, true));
    }
    toast("Đang bật các agent. Agent 3 có thể mất nửa phút.");
    refresh();
  });
  $("step-agents-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    const stopped = (state?.agents || []).filter((x) => x.state === "stopped");
    if (stopped.length) {
      $("start-all")?.click();
    } else {
      $("agent-grid")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  $("agent-start").addEventListener("click", () => toggleAgent(agentById(currentAgent)));
  $("agent-toggle")?.addEventListener("click", () => toggleAgent(agentById(currentAgent)));
  $("agent2-recover")?.addEventListener("click", async()=>{
    $("agent2-recover").disabled=true;
    try{await api('/api/agents/agent2/recover',{method:'POST'});toast('Đã kết nối lại. Yêu cầu đã lưu có thể tiếp tục.');}
    catch(error){toast(error.message,true);}
    finally{$("agent2-recover").disabled=false;refresh();}
  });
  $("commit").addEventListener("click", commitAll);
  $("clear-intake").addEventListener("click", clearIntake);
  $("intake-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-intake-stage]");
    if (button && state?.intake.unlocked) showIntakeStage(button.dataset.intakeStage);
  });
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

  if (typeof window !== "undefined") {
    window.__SOSON_PORTAL_UTILS__ = Object.freeze({
      FACE_FRAME_COUNT,
      FACE_FRAME_INTERVAL_MS,
      isValidFaceDescriptor,
      averageFaceDescriptors,
      approxVndPortal,
    });
  }

  applyRuntimeUi();
  renderSidebar();
  for (const input of $("company-form").elements) if (input.name || input.tagName === "BUTTON") input.disabled = true;
  show();
  refresh().then(show);
  setInterval(() => document.visibilityState === "visible" && refresh(), 4000);
  setInterval(() => document.visibilityState === "visible" && renderIntakeProgress(), 1000);
})();
