const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../..");
const portalSource = fs.readFileSync(path.join(root, "portal/static/app.js"), "utf8");
const agentSource = fs.readFileSync(path.join(root, "agent1/agent1_service/ui/workspace/app.js"), "utf8");

function section(source, start, end) {
  const begin = source.indexOf(start);
  const finish = source.indexOf(end, begin);
  assert.ok(begin >= 0 && finish > begin, "Expected application function was not found");
  return source.slice(begin, finish);
}

test("all assistants stay embedded without a popup action or a separate-tab handler", () => {
  const html = fs.readFileSync(path.join(root, "portal/static/index.html"), "utf8");
  assert.equal(html.includes('id="agent-newtab"'), false);
  assert.equal(html.includes("Mở tab riêng"), false);
  assert.equal(portalSource.includes("window.open("), false);
  assert.equal(portalSource.includes("async function openAgent1Tab("), false);
  for (const id of ["agent1", "agent2", "agent3", "agent4"]) {
    assert.ok(html.includes(`id="agent-frame-${id}"`), "Assistant still has its embedded workspace");
  }
});

function embeddedHandoff() {
  const calls = [], sent = [];
  let listener;
  const frame = {contentWindow:{postMessage:(data, origin)=>sent.push([data,origin])}};
  const scope = {
    window:{addEventListener:(name, handler)=>{ assert.equal(name,"message"); listener=handler; }},
    state:{}, authVersion:0, agentById:()=>({url:"http://127.0.0.1:8011/workspace"}),
    $: id => id === "agent-frame-agent1" ? frame : null, URL,
    api:async url=>{calls.push(url);return {key:"synthetic-key"};}, toast() {}
  };
  vm.createContext(scope);
  vm.runInContext(section(portalSource, '  window.addEventListener("message",', '  // ------------------------------------------------------------------ wire up'),scope);
  return {calls,sent,frame,listener};
}

test("embedded Agent 1 receives its key only from its own frame and origin", async () => {
  const ui=embeddedHandoff();
  await ui.listener({data:{type:"platform-ready"},source:ui.frame.contentWindow,origin:"https://unexpected.example"});
  await ui.listener({data:{type:"platform-ready"},source:{},origin:"http://127.0.0.1:8011"});
  assert.equal(ui.calls.length,0);
  await ui.listener({data:{type:"platform-ready"},source:ui.frame.contentWindow,origin:"http://127.0.0.1:8011"});
  assert.deepEqual(ui.calls,["/api/agents/agent1/key"]);
  assert.equal(ui.sent[0][0].type,"platform-access-key");
  assert.equal(ui.sent[0][0].key,"synthetic-key");
  assert.equal(ui.sent[0][1],"http://127.0.0.1:8011");
});

test("changing the Portal session clears both assistant frames for a fresh handoff", () => {
  const frames = Object.fromEntries(["agent1", "agent2"].map(id => [id, {
    dataset: {src: id}, removeAttribute(name) { assert.equal(name, "src"); this.removed = true; }
  }]));
  const scope = { token: "old", authVersion: 0, agent2RouteEpoch: 0,
    $: id => frames[id.replace("agent-frame-", "")],
    sessionStorage: {setItem(){}, removeItem(){}} };
  vm.createContext(scope);
  vm.runInContext(section(portalSource, "  function setToken(", "  function el("), scope);
  scope.setToken("new");
  for (const frame of Object.values(frames)) { assert.equal(frame.removed, true); assert.equal(frame.dataset.src, undefined); }
  assert.equal(scope.authVersion, 1);
});

test("ticket is removed from the address before authentication while portal context is retained", () => {
  let cleanUrl;
  const scope = { URL, URLSearchParams, location: { href: "http://127.0.0.1:8011/workspace?portal=http%3A%2F%2Flocalhost%3A9912#portal-connect=synthetic-ticket", hash: "#portal-connect=synthetic-ticket" }, history: { replaceState(a, b, url) { cleanUrl = url; } } };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  const connectHash =", "  const fmt =") + "\nthis.savedTicket = portalTicket;", scope);
  assert.equal(scope.savedTicket, "synthetic-ticket");
  assert.equal(new URL(cleanUrl).hash, "#overview");
  assert.equal(new URL(cleanUrl).searchParams.get("portal"), "http://localhost:9912");
  assert.equal(cleanUrl.includes("synthetic-ticket"), false);
});

function redeem(ok, fromPortal = false) {
  const nodes = new Map(), calls = [], notices = [];
  const submit = { disabled: false };
  const $ = id => { if (!nodes.has(id)) nodes.set(id, { disabled: false, querySelector: () => submit }); return nodes.get(id); };
  let openedDialog = false;
  const scope = {
    $, notice: (text, error) => notices.push([text, error]), connect: () => { openedDialog = true; },
    showCompanySyncError: message => { if (fromPortal) notices.push([message, true]); return fromPortal; },
    connectWithKey: async (key, company) => calls.push(["authenticate", key, company]),
    fetch: async (url, options) => { calls.push(["redeem", url, options]); assert.equal(submit.disabled, true); return { ok, json: async () => ok ? { key: "synthetic-key", company: "TEST_A" } : { detail: "Ticket expired" } }; },
  };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  async function redeemPortalTicket(", "  // Inside the platform shell:"), scope);
  return { scope, $, submit, calls, notices, openedDialog: () => openedDialog };
}

test("Agent 1 redeems with a POST and authenticates the expected company", async () => {
  const r = redeem(true);
  await r.scope.redeemPortalTicket("synthetic-ticket");
  assert.equal(r.calls[0][1], "/v1/portal-connect/redeem");
  assert.equal(r.calls[0][2].method, "POST");
  assert.equal(r.calls[0][2].cache, "no-store");
  assert.deepEqual(JSON.parse(r.calls[0][2].body), { ticket: "synthetic-ticket" });
  assert.deepEqual(r.calls[1], ["authenticate", "synthetic-key", "TEST_A"]);
  assert.equal(r.submit.disabled, false);
  assert.equal(r.openedDialog(), false);
});

test("an expired Portal ticket shows recovery guidance without opening the key form", async () => {
  const r = redeem(false, true);
  await r.scope.redeemPortalTicket("expired-ticket");
  assert.equal(r.openedDialog(), false);
  assert.deepEqual(r.notices.at(-1), ["Ticket expired", true]);
  assert.equal(r.submit.disabled, false);
  assert.equal(r.calls.length, 1);
});

test("company mismatch is rejected before workspace data is loaded", async () => {
  let refreshed = false;
  const input = {};
  const scope = { token: "", $: () => input, api: async () => ({ company: "TEST_B", role: "accountant" }), refresh: async () => { refreshed = true; } };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  async function connectWithKey(", '  $("connect-form").onsubmit ='), scope);
  await assert.rejects(scope.connectWithKey("synthetic-key", "TEST_A"));
  assert.equal(scope.token, "");
  assert.equal(refreshed, false);
  assert.equal(input.value, "");
});

function sessionUI(embedded = false) {
  const calls = [], elements = new Map();
  const $ = id => { if (!elements.has(id)) elements.set(id, {value:"", close() { this.closed = true; }}); return elements.get(id); };
  const window = {}; window.parent = embedded ? {} : window;
  const scope = {window, $, token:"", connected:false, expectedPortalCompany:null, notice() {}, showCompanySyncError:() => false,
    api:async (path, options) => { calls.push([path, options]); return {company:"TEST_A", role:"accountant"}; },
    refresh:async () => calls.push(["refresh"])};
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  async function connectWithKey(", '  $("connect-form").onsubmit ='), scope);
  vm.runInContext(section(agentSource, "  async function restoreSession(", "  // Inside the platform shell:"), scope);
  return {scope, calls, $};
}

test("standalone connection exchanges its key for a session before loading company data", async () => {
  const ui = sessionUI();
  await ui.scope.connectWithKey("synthetic-key", "TEST_A");
  assert.deepEqual(ui.calls.map(call => call[0]), ["/access", "/session", "refresh"]);
  assert.equal(ui.calls[1][1].method, "POST");
  assert.equal(ui.scope.connected, true);
  assert.equal(ui.scope.token, "");
  assert.equal(ui.$("token-input").value, "");
});

test("reload restores a cookie session without requiring the access key again", async () => {
  const ui = sessionUI();
  ui.scope.fetch = async (url, options) => {
    assert.equal(url, "/v1/access"); assert.equal(options.credentials, "same-origin");
    return {ok:true};
  };
  await ui.scope.restoreSession();
  assert.equal(ui.scope.connected, true);
  assert.equal(ui.scope.token, "");
  assert.deepEqual(ui.calls.map(call => call[0]), ["/access", "refresh"]);
});

test("embedded portal retains its in-memory fallback when third-party cookies are blocked", async () => {
  const ui = sessionUI(true);
  await ui.scope.connectWithKey("synthetic-key", "TEST_A");
  assert.equal(ui.scope.connected, true);
  assert.equal(ui.scope.token, "synthetic-key");
});

test("an expired browser session does not fabricate a connected workspace", async () => {
  const ui = sessionUI();
  ui.scope.fetch = async () => ({ok:false});
  await ui.scope.restoreSession();
  assert.equal(ui.scope.connected, false);
  assert.equal(ui.calls.length, 0);
});

test("moving from Agent 1 to shared intake leaves its current view intact", () => {
  const link = "http://127.0.0.1:8800/#data";
  const calls = [];
  const scope = {portalPage: () => link, window: {top: {location: {}}}, switchView: view => calls.push(view)};
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function openIntake(", '  document.querySelectorAll("[data-view]").forEach'), scope);
  assert.equal(scope.openIntake(), true);
  assert.equal(scope.window.top.location.href, link);
  assert.deepEqual(calls, []);
  scope.portalPage = () => null;
  assert.equal(scope.openIntake(), false);
  assert.deepEqual(calls, ["data"]);
});

test("a record shortcut selects its own menu item and URL", () => {
  function button(view, table) {
    return {dataset:{view, table}, classList:{toggle() {}},
      setAttribute(name, value) { this[name] = value; }, removeAttribute(name) { delete this[name]; }};
  }
  const buttons = [button("records"), button("records", "bank"), button("records", "outflows")];
  const kind = {value:"invoices", options:[{value:"bank"}, {value:"outflows"}]};
  const location = {hash:"#overview"};
  let resets = 0;
  const scope = {Object, location, currentView:"overview", titles:{records:"Sổ dữ liệu"}, token:"", connected:false,
    document:{querySelectorAll: selector => selector === ".view" ? [] : buttons},
    $: id => id === "records-kind" ? kind : {}, history:{pushState(_state, _title, url) { location.hash = url; }},
    drawVisibleChart() {}, updateRecordLinks() {}, resetRecordFilters() { resets++; }, window:{scrollTo() {}}};
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function switchView(", "  function openIntake("), scope);
  for (const [index, table] of [[1, "bank"], [2, "outflows"]]) {
    scope.switchView("records/" + table);
    assert.equal(location.hash, "#records/" + table);
    assert.equal(kind.value, table);
    assert.deepEqual(buttons.map(item => item["aria-current"]), buttons.map((_, i) => i === index ? "page" : undefined));
  }
  assert.equal(resets, 2);
});

test("manual allocation sends VND text without rounding through a JavaScript number", async () => {
  const nodes = new Map(), calls = [];
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, { value: "100000000000000001", click() {} });
    return nodes.get(id);
  };
  let pending;
  const scope = { $, action: work => { pending = work(); }, refresh: async () => {}, loadReconciliation: async () => {},
    reconciliationReviewer: () => "Kế toán thử", notice() {},
    api: async (url, options) => calls.push([url, JSON.parse(options.body)]) };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  let reconciliationProposalRefresh =", "  async function loadReconciliation("), scope);
  vm.runInContext(section(agentSource, '  $("allocate-form").onsubmit =', '  function invalidateSourceCorrection('), scope);
  $("allocate-form").onsubmit({ preventDefault() {} });
  await pending;
  assert.equal(calls[0][0], "/allocations");
  assert.equal(calls[0][1].amount, "100000000000000001");
  assert.equal(calls[0][1].reviewed_by, "Kế toán thử");
});

test("T9 money display preserves exact VND above Number.MAX_SAFE_INTEGER", () => {
  const scope = { fmt: new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }) };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function exactMoney(", "  function reconciliationReviewer("), scope);
  assert.equal(scope.exactMoney("100000000000000001"), "100.000.000.000.000.001");
});

test("T9 review requires an identified accountant", () => {
  let focused = false;
  const input = { value: "  ", focus() { focused = true; } };
  const scope = { $: () => input };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function reconciliationReviewer(", "  function chooseAllocation("), scope);
  assert.throws(() => scope.reconciliationReviewer(), /Nhập tên người xử lý/);
  assert.equal(focused, true);
  input.value = "  Kế toán A  ";
  assert.equal(scope.reconciliationReviewer(), "Kế toán A");
});

function reviewUI(stale = false) {
  const calls = [], target = { children: [], replaceChildren() { this.children = []; }, append(...items) { this.children.push(...items); } };
  const drawer = { open:false, replaceChildren:target.replaceChildren, append:target.append,
    showModal() { this.open = true; }, close() { this.open = false; } };
  function node(tag, text) {
    return { tag, textContent: text, value: "", children: [], setAttribute() {},
      append(...items) { this.children.push(...items); }, focus() { this.focused = true; } };
  }
  const proposal = { id: "proposal-1", stale, cases: [{ bank_id: "B1", status: "auto", date: "2026-03-01", account: "A",
    available_minor: 100, reason: "unique_transport", reason_text: "Cần đối chiếu chứng từ", memo: "<script>unsafe</script>",
    allocations: [{ invoice_id: "I1", amount_minor: 100 }], candidates: [] }] };
  let pending;
  const scope = { node, $: id => id === "reconciliation-drawer" ? drawer : target, crypto: { randomUUID: () => "test-key" },
    currentView:"reconciliation",
    reconciliationState: { proposal }, exactMoney: String, displayDate: String, reconciliationReviewer: () => "Accountant",
    action: work => { pending = work(); }, api: async (url, options) => { calls.push([url, JSON.parse(options.body)]); },
    refresh: async () => {}, loadReconciliation: async () => {}, notice() {} };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  let reconciliationProposalRefresh =", "  async function loadReconciliation("), scope);
  vm.runInContext(section(agentSource, "  function renderReconciliationCases(", "  function renderReconciliationHistory("), scope);
  scope.renderReconciliationCases(proposal);
  const all = object => [object, ...(object.children || []).flatMap(all)];
  const openReview = () => all(target).find(x => x.tag === "button" && x.textContent === "Mở đối soát")?.onclick();
  openReview();
  return { calls, proposal, scope, openReview, elements: all(drawer), readElements: () => all(drawer), run: async (form, kind) => {
    form.onsubmit({ preventDefault() {}, submitter: { value: kind } });
    await pending;
  } };
}

test("T9 reject requires a reason and approval sends only the selected bank case", async () => {
  const ui = reviewUI();
  const form = ui.elements.find(x => x.tag === "form");
  const note = ui.elements.find(x => x.tag === "textarea");
  await assert.rejects(ui.run(form, "reject"), /Nhập lý do từ chối/);
  assert.equal(ui.calls.length, 0);
  assert.equal(note.focused, true);
  note.value = "Đã đối chiếu";
  await ui.run(form, "accept");
  assert.equal(ui.calls[0][0], "/reconciliation/accept");
  assert.equal(ui.calls[0][1].bank_id, "B1");
  assert.equal(ui.calls[0][1].proposal_id, "proposal-1");
  assert.equal(ui.calls[0][1].reviewed_by, "Accountant");
  assert.equal(ui.elements.some(x => x.textContent === "<script>unsafe</script>"), true);
});

test("T9 stale proposals have no approval form and replaced proposals cannot be submitted", async () => {
  assert.equal(reviewUI(true).elements.some(x => x.tag === "form"), false);
  const ui = reviewUI();
  ui.scope.reconciliationState = { proposal: { id: "new-proposal" } };
  await assert.rejects(ui.run(ui.elements.find(x => x.tag === "form"), "accept"), /Đề xuất đã đổi/);
  assert.equal(ui.calls.length, 0);
});

test("T9 candidate selection works outside the first page of pending bank rows", () => {
  const ui = reviewUI();
  let selected;
  ui.scope.reconciliationState.pending = [];
  ui.scope.chooseAllocation = (...args) => { selected = args; };
  ui.proposal.cases[0].available_minor = "100000000000000001";
  ui.proposal.cases[0].candidates = [{ invoice_id: "I1", customer_id: "C1", score: 1,
    amount_open_minor: "100000000000000000", evidence: ["Khớp số hóa đơn"] }];
  ui.scope.renderReconciliationCases(ui.proposal);
  ui.openReview();
  ui.readElements().find(x => x.tag === "button" && x.textContent === "Chọn để ghép thủ công").onclick();
  assert.equal(selected[0].bank_id, "B1");
  assert.equal(selected[1], "I1");
  assert.equal(selected[2], "100000000000000000");
});

function sourceCorrectionUI() {
  const nodes = new Map(), calls = [], trace = [];
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, { id, value: "", disabled: false, hidden: false, open: false,
      children: [], replaceChildren(...items) { this.children = items; }, append(...items) { this.children.push(...items); } });
    return nodes.get(id);
  };
  let pending;
  const scope = { $, sourceCorrection: {base_hash:"dataset-1", records:[], preview:null, key:null},
    crypto:{randomUUID:()=>"correction-key"},
    action:work=>{pending=work();}, api:async (url, options)=>{
      calls.push([url, JSON.parse(options.body)]);
      return url.endsWith("/preview") ? {id:"C-1", changes:[], affected_decisions:[], affected_payments:[], affected_actions:[]}
        : {reversed_count:2};
    }, renderSourceCorrectionPreview:()=>trace.push("preview"),
    refresh:async()=>trace.push("refresh"), loadReconciliation:async()=>trace.push("reload"), notice() {} };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function invalidateSourceCorrection(", "  function renderSourceCorrectionPreview("), scope);
  vm.runInContext(section(agentSource, '  $("source-correction-form").onsubmit =', '  $("date-format").onchange ='), scope);
  return { scope, $, calls, trace, wait:()=>pending };
}

test("source correction preview preserves exact VND and sends only edited fields", async () => {
  const ui = sourceCorrectionUI();
  ui.scope.sourceCorrection.records = [{kind:"bank", identifier:"B1", values:{amount:"100", account:"A"},
    inputs:{amount:{value:"100000000000000001"}, account:{value:"A"}}}];
  ui.$("source-correction-reviewer").value = "  Accountant  ";
  ui.$("source-correction-note").value = "Bank statement proof";
  ui.$("source-correction-form").onsubmit({preventDefault(){}});
  await ui.wait();
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.calls[0][0], "/corrections/preview");
  assert.deepEqual(ui.calls[0][1], {base_hash:"dataset-1", reviewed_by:"Accountant", note:"Bank statement proof",
    changes:[{kind:"bank", identifier:"B1", values:{amount:"100000000000000001"}}]});
  assert.equal(ui.scope.sourceCorrection.preview.id, "C-1");
  assert.deepEqual(ui.trace, ["preview"]);
});

test("source correction commit requires a preview and uses its immutable server ID", async () => {
  const ui = sourceCorrectionUI();
  ui.$("commit-source-correction").onclick();
  await assert.rejects(ui.wait(), /Xem trước bản sửa/);
  assert.equal(ui.calls.length, 0);
  ui.scope.sourceCorrection.preview = {id:"C-1"}; ui.scope.sourceCorrection.key = "stable-key";
  ui.$("commit-source-correction").onclick(); await ui.wait();
  assert.equal(ui.calls[0][0], "/corrections/C-1/commit");
  assert.deepEqual(ui.calls[0][1], {idempotency_key:"stable-key"});
  assert.equal(ui.scope.sourceCorrection.preview, null);
  assert.equal(ui.$("commit-source-correction").disabled, true);
  assert.deepEqual(ui.trace, ["refresh", "reload"]);
});

test("source correction editing invalidates approval and a failed commit retains the retry key", async () => {
  const ui = sourceCorrectionUI();
  ui.scope.sourceCorrection.preview = {id:"C-1"}; ui.scope.sourceCorrection.key = "stable-key";
  ui.scope.api = async()=>{throw Error("Connection interrupted");};
  ui.$("commit-source-correction").onclick();
  await assert.rejects(ui.wait(), /Connection interrupted/);
  assert.equal(ui.scope.sourceCorrection.preview.id, "C-1");
  assert.equal(ui.scope.sourceCorrection.key, "stable-key");
  ui.scope.invalidateSourceCorrection();
  assert.equal(ui.scope.sourceCorrection.preview, null);
  assert.equal(ui.$("source-correction-preview").hidden, true);
  assert.equal(ui.$("commit-source-correction").disabled, true);
});

test("source correction requires changed values, a reviewer and correction evidence", async () => {
  const ui = sourceCorrectionUI();
  ui.$("source-correction-form").onsubmit({preventDefault(){}});
  await assert.rejects(ui.wait(), /ít nhất một thay đổi/);
  ui.scope.sourceCorrection.records = [{kind:"bank", identifier:"B1", values:{amount:"100"}, inputs:{amount:{value:"200"}}}];
  ui.$("source-correction-form").onsubmit({preventDefault(){}});
  await assert.rejects(ui.wait(), /tên người xử lý và lý do/);
  assert.equal(ui.calls.length, 0);
});

test("source correction rejects a late preview response after the user edits values", async () => {
  const ui = sourceCorrectionUI();
  let resolve;
  ui.scope.api = () => new Promise(done => { resolve = done; });
  ui.scope.sourceCorrection.records = [{kind:"bank", identifier:"B1", values:{amount:"100"}, inputs:{amount:{value:"200"}}}];
  ui.$("source-correction-reviewer").value = "Accountant";
  ui.$("source-correction-note").value = "Proof";
  ui.$("source-correction-form").onsubmit({preventDefault(){}});
  ui.scope.invalidateSourceCorrection();
  resolve({id:"old-preview"});
  await assert.rejects(ui.wait(), /Giá trị đã thay đổi/);
  assert.equal(ui.scope.sourceCorrection.preview, null);
  assert.equal(ui.$("commit-source-correction").disabled, true);
});
