"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const AGENT_LABEL = { agent1: "Agent 1", agent2: "Agent 2", agent3: "Agent 3", agent4: "Agent 4" };
  const STATE_TEXT = { running: "Đang chạy", starting: "Đang khởi động", stopped: "Đang tắt", "busy-port": "Cổng bị chiếm" };
  const CHECK_TEXT = { ready: "Sẵn sàng ghi", error: "Có lỗi", offline: "Agent tắt", done: "Đã ghi", skipped: "Bỏ qua" };
  let state = null;
  let currentAgent = null;
  let poll = null;

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
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.json);
    }
    const res = await fetch(path, { ...options, headers, cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Yêu cầu không thành công (" + res.status + ").");
    return data;
  }

  const sizeText = (n) => (n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB");
  const agentById = (id) => state.agents.find((a) => a.id === id);

  // ------------------------------------------------------------------ render
  function renderCompany() {
    const c = state.company;
    const configured = Boolean(c.legal_name && c.code);
    $("company-name").textContent = configured ? c.legal_name : "Chưa cấu hình doanh nghiệp";
    $("company-meta").textContent = configured ? [c.tax_code && "MST " + c.tax_code, "Mã " + c.code].filter(Boolean).join(", ") : "Bấm để nhập thông tin";
    const form = $("company-form");
    if (!form.dataset.dirty) {
      for (const [k, v] of Object.entries(c)) if (form.elements[k]) form.elements[k].value = v ?? "";
    }
    $("saved-at").textContent = c.updated_at ? "Lưu lần cuối " + c.updated_at : "";
  }

  function renderNav() {
    const nav = $("nav-agents");
    nav.replaceChildren(
      ...state.agents.map((a) =>
        el("a", { class: "nav-link", href: "#" + a.id, "data-view": a.id },
          el("span", { class: "num" }, a.number), a.name, el("span", { class: "dot " + a.state, title: STATE_TEXT[a.state] }))),
    );
    const n = state.pending.length;
    $("pending-count").hidden = !n;
    $("pending-count").textContent = n;
    markCurrent();
  }

  function receivedCount(aid) {
    return state.history.filter((h) => h.results[aid] && h.results[aid].state === "done").length;
  }

  function renderOverview() {
    const c = state.company;
    const steps = $("steps").children;
    steps[0].classList.toggle("done", Boolean(c.legal_name && c.code));
    steps[1].classList.toggle("done", state.agents.every((a) => a.state === "running"));
    steps[2].classList.toggle("done", state.history.length > 0);
    $("agent-grid").replaceChildren(
      ...state.agents.map((a) => {
        const running = a.state === "running";
        const files = receivedCount(a.id);
        return el("article", { class: "agent" },
          el("span", { class: "big", "aria-hidden": "true" }, a.number),
          el("h3", {}, a.name, el("span", { class: "status" }, el("span", { class: "dot " + a.state }), STATE_TEXT[a.state])),
          el("p", {}, a.summary),
          el("div", { class: "actions" },
            el("a", { class: "btn primary", href: "#" + a.id }, "Mở " + AGENT_LABEL[a.id]),
            a.owned || a.state === "stopped"
              ? el("button", { type: "button", onclick: () => toggleAgent(a) }, running || a.state === "starting" ? "Tắt" : "Bật")
              : null,
            el("span", { class: "sub" }, a.id === "agent4" ? "Kho dữ liệu demo" : files ? files + " tệp đã ghi qua portal" : "Chưa nhận tệp qua portal")));
      }),
    );
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

  function renderQueue() {
    const rows = state.pending.map((r) =>
      el("tr", {},
        el("td", {}, el("div", { class: "file-name" }, r.name), el("div", { class: "sub" }, sizeText(r.size) + ", thêm lúc " + r.added_at.slice(11, 16))),
        el("td", {}, r.label, r.note && r.targets.length ? el("div", { class: "sub" }, r.note) : null),
        el("td", {}, checkLines(r)),
        el("td", { class: "right" },
          el("button", { type: "button", class: "link", onclick: () => recheck(r.id) }, "Kiểm tra lại"), " ",
          el("button", { type: "button", class: "link", onclick: () => dropFile(r.id) }, "Bỏ"))));
    $("queue").tBodies[0].replaceChildren(...rows);
    $("queue-empty").hidden = rows.length > 0;
    const ready = state.pending.filter((r) => Object.values(r.checks || {}).some((c) => c.state === "ready"));
    $("commit").disabled = !ready.length;
    if ($("commit").dataset.confirm !== "1")
      $("commit").textContent = ready.length ? "Ghi " + ready.length + " tệp vào agent" : "Ghi vào agent";

    const hist = state.history.map((h) =>
      el("tr", {},
        el("td", { class: "sub" }, h.at),
        el("td", {}, el("div", { class: "file-name" }, h.name), el("div", { class: "sub" }, h.label)),
        el("td", {}, el("ul", { class: "checks" }, Object.entries(h.results).map(([aid, r]) =>
          el("li", {}, el("span", { class: "who" }, AGENT_LABEL[aid]), el("span", { class: r.state }, r.message)))))));
    $("history").tBodies[0].replaceChildren(...hist);
    $("history-empty").hidden = hist.length > 0;
  }

  function renderAgentView() {
    if (!currentAgent) return;
    const a = agentById(currentAgent);
    $("agent-no").textContent = a.number;
    $("agent-name").textContent = a.name;
    $("agent-status").replaceChildren(el("span", { class: "dot " + a.state }), STATE_TEXT[a.state]);
    $("agent-newtab").href = a.url;
    $("agent-toggle").textContent = a.state === "running" || a.state === "starting" ? "Tắt agent" : "Bật agent";
    $("agent-toggle").hidden = !(a.owned || a.state === "stopped");
    const frame = $("agent-frame");
    const up = a.state === "running";
    if (up && frame.dataset.src !== a.url) {
      frame.dataset.src = a.url;
      frame.src = a.url;
    }
    if (!up) {
      frame.removeAttribute("src");
      delete frame.dataset.src;
    }
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
    renderCompany();
    renderNav();
    renderOverview();
    renderQueue();
    renderAgentView();
  }

  async function refresh() {
    try {
      state = await api("/api/state");
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

  function show() {
    const view = location.hash.slice(1) || "overview";
    const isAgent = /^agent[1-4]$/.test(view);
    for (const id of ["overview", "config", "data"]) $("view-" + id).hidden = id !== view;
    $("view-agent").hidden = !isAgent;
    if (!isAgent && currentAgent) {
      $("agent-frame").removeAttribute("src");
      delete $("agent-frame").dataset.src;
    }
    currentAgent = isAgent ? view : null;
    $("sidebar").classList.remove("open");
    $("menu-toggle").setAttribute("aria-expanded", "false");
    if (state) render();
    markCurrent();
    document.title = (isAgent && state ? AGENT_LABEL[view] + " " + agentById(view).name : { overview: "Tổng quan", config: "Cấu hình", data: "Nạp dữ liệu" }[view] || "") + " | Văn phòng kế toán số";
  }

  // ------------------------------------------------------------------ actions
  async function toggleAgent(a) {
    const action = a.state === "running" || a.state === "starting" ? "stop" : "start";
    try {
      await api("/api/agents/" + a.id + "/" + action, { method: "POST" });
      toast(action === "start" ? AGENT_LABEL[a.id] + " đang khởi động." : AGENT_LABEL[a.id] + " đã tắt.");
    } catch (err) {
      toast(err.message, true);
    }
    refresh();
  }

  async function upload(files) {
    for (const file of files) {
      toast("Đang nhận dạng và kiểm tra " + file.name);
      try {
        await api("/api/inbox?name=" + encodeURIComponent(file.name), { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
      } catch (err) {
        toast(file.name + ": " + err.message, true);
      }
      await refresh();
    }
    toast("Đã kiểm tra " + files.length + " tệp. Xem kết quả rồi bấm Ghi vào agent.");
  }

  async function recheck(id) {
    try {
      await api("/api/inbox/" + id + "/check", { method: "POST" });
    } catch (err) {
      toast(err.message, true);
    }
    refresh();
  }

  async function dropFile(id) {
    await api("/api/inbox/" + id + "/delete", { method: "POST" }).catch((err) => toast(err.message, true));
    refresh();
  }

  async function commitAll() {
    const ids = state.pending.filter((r) => Object.values(r.checks || {}).some((c) => c.state === "ready")).map((r) => r.id);
    const replaces = state.pending.some((r) => ids.includes(r.id) && r.checks.agent2 && r.checks.agent2.state === "ready");
    const button = $("commit");
    if (replaces && button.dataset.confirm !== "1") {
      button.dataset.confirm = "1";
      button.textContent = "Bấm lần nữa: Agent 2 thay toàn bộ giao dịch";
      setTimeout(() => { delete button.dataset.confirm; renderQueue(); }, 6000);
      return;
    }
    delete button.dataset.confirm;
    $("commit").disabled = true;
    $("commit").textContent = "Đang ghi";
    try {
      const res = await api("/api/inbox/commit", { method: "POST", json: { ids } });
      const errors = res.results.flatMap((r) => Object.values(r.results)).filter((r) => r.state === "error").length;
      toast(errors ? "Ghi xong, " + errors + " lượt có lỗi. Xem Lịch sử ghi." : "Đã ghi " + res.results.length + " tệp vào agent.", errors > 0);
    } catch (err) {
      toast(err.message, true);
    }
    refresh();
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
      } catch (err) {
        toast(err.message, true);
        button.disabled = false;
      }
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
      $("sync-result").replaceChildren(
        el("li", { class: "ok" }, "Đã lưu hồ sơ. Agent 1 và Agent 2 dùng mã " + res.company.code + " cho lần nạp tiếp theo."),
        ...Object.entries(res.sync).map(([aid, s]) => syncItem(aid, s)));
      toast("Đã lưu cấu hình doanh nghiệp.");
    } catch (err) {
      $("sync-result").replaceChildren(el("li", { class: "error" }, err.message));
      toast(err.message, true);
    } finally {
      button.disabled = false;
    }
    refresh();
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
    } catch (err) {
      toast(err.message, true);
    }
  });

  // ------------------------------------------------------------------ wire up
  window.addEventListener("hashchange", show);
  $("menu-toggle").addEventListener("click", () => {
    const open = $("sidebar").classList.toggle("open");
    $("menu-toggle").setAttribute("aria-expanded", String(open));
  });
  $("company-form").addEventListener("submit", saveCompany);
  $("company-form").addEventListener("input", (e) => (e.currentTarget.dataset.dirty = "1"));
  $("company-form").addEventListener("change", (e) => (e.currentTarget.dataset.dirty = "1"));
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
  poll = setInterval(() => document.visibilityState === "visible" && refresh(), 4000);
})();
