"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const AGENT_LABEL = { agent1: "Agent 1", agent2: "Agent 2", agent3: "Agent 3", agent4: "Agent 4" };
  const STATE_TEXT = { running: "Đang chạy", starting: "Đang khởi động", stopped: "Đang tắt", "busy-port": "Cổng bị chiếm" };
  const CHECK_TEXT = { ready: "Sẵn sàng ghi", error: "Có lỗi", offline: "Agent tắt", done: "Đã ghi", skipped: "Bỏ qua", stale: "Chờ kiểm tra lại" };
  let state = null;
  let currentAgent = null;
  let token = "";
  try { token = sessionStorage.getItem("kt-session") || ""; } catch (e) { token = ""; }

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

  async function api(path, options = {}) {
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
  }

  const sizeText = (n) => (n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB");
  const agentById = (id) => state.agents.find((a) => a.id === id);
  const dmy = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "");
  const stamp = (s) => (s ? dmy(s.slice(0, 10)) + " " + s.slice(11, 16) : "");

  // ------------------------------------------------------------------ render
  function renderTop() {
    const c = state.company;
    const configured = Boolean(c.legal_name && c.code);
    $("company-name").textContent = configured ? c.legal_name : "Chưa cấu hình doanh nghiệp";
    $("company-meta").textContent = configured ? [c.tax_code && "MST " + c.tax_code, "Mã " + c.code].filter(Boolean).join(", ") : "Bấm để nhập thông tin";
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
    $("saved-at").textContent = c.updated_at ? "Lưu lần cuối " + c.updated_at : "";
    const locked = Boolean(state.package) && !state.intake.unlocked;
    $("config-lock").hidden = !locked;
    for (const input of form.elements) if (input.name) input.disabled = locked;
    form.querySelector("button[type=submit]").disabled = locked;
  }

  function renderNav() {
    $("nav-agents").replaceChildren(
      ...state.agents.map((a) =>
        el("a", { class: "nav-link", href: "#" + a.id, "data-view": a.id },
          el("span", { class: "num" }, a.number), a.name, el("span", { class: "dot " + a.state, title: STATE_TEXT[a.state] }))));
    markCurrent();
  }

  function receivedCount(aid) {
    return state.batches.filter((b) => b.company === state.company.code).flatMap((b) => b.files).filter((f) => f.results[aid] && f.results[aid].state === "done").length;
  }

  function renderOverview() {
    const c = state.company;
    const steps = $("steps").children;
    steps[0].classList.toggle("done", Boolean(c.legal_name && c.code));
    steps[1].classList.toggle("done", state.agents.every((a) => a.state === "running"));
    steps[2].classList.toggle("done", Boolean(state.package));
    $("agent-grid").replaceChildren(
      ...state.agents.map((a) => {
        const running = a.state === "running";
        const files = state.intake.unlocked ? receivedCount(a.id) : null;
        return el("article", { class: "agent" },
          el("span", { class: "big", "aria-hidden": "true" }, a.number),
          el("h3", {}, a.name, el("span", { class: "status" }, el("span", { class: "dot " + a.state }), STATE_TEXT[a.state])),
          el("p", {}, a.summary),
          el("div", { class: "actions" },
            el("a", { class: "btn primary", href: "#" + a.id }, "Mở " + AGENT_LABEL[a.id]),
            a.owned || a.state === "stopped"
              ? el("button", { type: "button", onclick: () => toggleAgent(a) }, running || a.state === "starting" ? "Tắt" : "Bật") : null,
            el("span", { class: "sub" }, a.id === "agent4" ? "Kho dữ liệu demo" : files === null ? "Mở khóa để xem" : files ? files + " tệp đã ghi qua gói" : "Chưa nhận tệp")));
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
          el("li", {}, el("span", { class: "mark " + s.state }), s.label,
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
        el("td", { role: "cell" }, r.label, r.note && r.targets.length ? el("div", { class: "sub" }, r.note) : null),
        el("td", { role: "cell", class: "sub", "data-label": "Kỳ dữ liệu" }, periodText(r.period)),
        el("td", { role: "cell" }, checkLines(r)),
        el("td", { role: "cell", class: "right" }, el("div", { class: "queue-actions" },
          el("button", { type: "button", class: "link", onclick: () => recheck(r.id) }, "Kiểm tra lại"),
          el("button", { type: "button", class: "link", onclick: () => dropFile(r.id) }, "Bỏ")))));
    $("queue").tBodies[0].replaceChildren(...rows);
    $("queue-empty").hidden = rows.length > 0;
    const ready = state.pending.filter((r) => Object.values(r.checks || {}).some((c) => c.state === "ready"));
    $("reason-field").hidden = !state.package;
    const button = $("commit");
    button.disabled = !ready.length;
    if (button.dataset.confirm !== "1") button.textContent = ready.length ? "Niêm phong và ghi " + ready.length + " tệp" : "Niêm phong và ghi vào agent";

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

  function renderData() {
    const i = state.intake;
    $("view-data").setAttribute("aria-labelledby", i.unlocked ? "h-intake" : "h-data");
    $("gate").hidden = i.unlocked;
    $("intake").hidden = !i.unlocked;
    if (!i.unlocked) {
      const first = !i.configured;
      $("gate-lead").textContent = first
        ? "Đặt mật khẩu một lần. Từ đó mọi lần nạp, bổ sung hay sửa cấu hình sau khi niêm phong đều phải mở khóa."
        : "Nhập mật khẩu để nạp hoặc xem gói dữ liệu của doanh nghiệp. Phiên tự khóa sau 20 phút không dùng.";
      $("gate-label").textContent = first ? "Mật khẩu mới (ít nhất 8 ký tự)" : "Mật khẩu";
      $("gate-confirm-field").hidden = !first;
      $("gate-password").autocomplete = first ? "new-password" : "current-password";
      $("gate-submit").textContent = first ? "Đặt mật khẩu và mở" : "Mở khóa";
      return;
    }
    $("session-left").textContent = "Đã mở khóa, còn " + Math.max(1, Math.round(i.seconds_left / 60)) + " phút";
    const c = state.company;
    $("intake-company").replaceChildren(c.code
      ? el("strong", {}, c.legal_name + " · " + c.code)
      : el("a", { href: "#config" }, "Lưu hồ sơ doanh nghiệp để nạp tệp"));
    $("file-input").disabled = !c.code;
    $("drop").hidden = !c.code;
    renderSlots();
    renderQueue();
  }

  function renderAgentView() {
    if (!currentAgent) return;
    const a = agentById(currentAgent);
    $("agent-no").textContent = a.number;
    $("agent-name").textContent = a.name;
    $("agent-status").replaceChildren(el("span", { class: "dot " + a.state }), STATE_TEXT[a.state]);
    const source = $("agent-source");
    source.textContent = a.id === "agent4" ? "Nguồn số liệu: kho mô phỏng của Agent 4"
      : state.company.code ? ["Hồ sơ " + state.company.code, state.package ? "Gói chung v" + state.package.version : "Chưa niêm phong"].join(" · ")
        : "Cấu hình doanh nghiệp để nạp dữ liệu";
    source.href = a.id !== "agent4" && !state.company.code ? "#config" : "#data";
    $("agent-newtab").href = a.url;
    $("agent-toggle").textContent = a.state === "running" || a.state === "starting" ? "Tắt agent" : "Bật agent";
    $("agent-toggle").hidden = !(a.owned || a.state === "stopped");
    const frame = $("agent-frame");
    const up = a.state === "running";
    if (up && frame.dataset.src !== a.url) { frame.dataset.src = a.url; frame.src = a.url; }
    if (!up) { frame.removeAttribute("src"); delete frame.dataset.src; }
    frame.hidden = !up;
    $("agent-off").hidden = up;
    if (!up) {
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
    try {
      state = await api("/api/state");
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
    if (!isAgent && currentAgent) { $("agent-frame").removeAttribute("src"); delete $("agent-frame").dataset.src; }
    currentAgent = isAgent ? view : null;
    $("sidebar").classList.remove("open");
    $("menu-toggle").setAttribute("aria-expanded", "false");
    if (state) render();
    markCurrent();
    document.title = (isAgent && state ? AGENT_LABEL[view] + " " + agentById(view).name : TITLES[view] || "") + " | Văn phòng kế toán số";
  }

  // ------------------------------------------------------------------ actions
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
  }

  async function recheck(id) {
    try { await api("/api/inbox/" + id + "/check", { method: "POST" }); } catch (err) { toast(err.message, true); }
    refresh();
  }

  async function dropFile(id) {
    await api("/api/inbox/" + id + "/delete", { method: "POST" }).catch((err) => toast(err.message, true));
    refresh();
  }

  async function commitAll() {
    const ready = state.pending.filter((r) => Object.values(r.checks || {}).some((c) => c.state === "ready"));
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
    const body = Object.fromEntries(new FormData(form).entries());
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const res = await api("/api/company", { method: "PUT", json: body });
      delete form.dataset.dirty;
      await refresh();
      $("sync-result").replaceChildren(
        el("li", { class: "ok" }, "Đã lưu hồ sơ. Agent 1 và Agent 2 dùng mã " + res.company.code + " cho lần nạp tiếp theo."),
        ...Object.entries(res.sync).map(([aid, s]) => syncItem(aid, s)));
      toast("Đã lưu cấu hình doanh nghiệp.");
    } catch (err) {
      $("sync-result").replaceChildren(el("li", { class: "error" }, err.message));
      toast(err.message, true);
    } finally { button.disabled = false; }
  }

  // Agent 1 asks for its access key once it has loaded inside the frame.
  window.addEventListener("message", async (event) => {
    const a1 = state && agentById("agent1");
    if (!a1 || event.data?.type !== "platform-ready" || event.source !== $("agent-frame").contentWindow) return;
    const origin = new URL(a1.url).origin;
    if (event.origin !== origin) return;
    try {
      const { key } = await api("/api/agents/agent1/key");
      if (key) $("agent-frame").contentWindow.postMessage({ type: "platform-access-key", key }, origin);
    } catch (err) { toast(err.message, true); }
  });

  // ------------------------------------------------------------------ wire up
  window.addEventListener("hashchange", show);
  $("menu-toggle").addEventListener("click", () => {
    const open = $("sidebar").classList.toggle("open");
    $("menu-toggle").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("sidebar").classList.contains("open")) {
      $("menu-toggle").click();
      $("menu-toggle").focus();
    }
  });
  $("company-form").addEventListener("submit", saveCompany);
  $("company-form").addEventListener("input", (e) => (e.currentTarget.dataset.dirty = "1"));
  $("company-form").addEventListener("change", (e) => (e.currentTarget.dataset.dirty = "1"));
  $("gate-form").addEventListener("submit", unlockGate);
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

  show();
  refresh().then(show);
  setInterval(() => document.visibilityState === "visible" && refresh(), 4000);
})();
