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

function popup() {
  const trace = [], messages = [];
  const agent = { state: "running", url: "http://127.0.0.1:8011/workspace" };
  const result = { company: "TEST_A", url: "http://127.0.0.1:8011/workspace?portal=http%3A%2F%2Flocalhost%3A9912#portal-connect=synthetic-ticket" };
  const tab = { opener: {}, closed: false, document: { body: {} }, location: { replace(url) { trace.push(["navigate", url]); } }, close() { this.closed = true; } };
  const scope = {
    currentAgent: "agent1", state: { company: { code: "TEST_A" } }, agentById: () => agent,
    location: { href: "http://localhost:9912/#agent1", origin: "http://localhost:9912" }, URL,
    window: { open() { trace.push(["open"]); return tab; } },
    toast: text => messages.push(text),
    api: async (url, options) => { assert.equal(tab.opener, null); trace.push(["request", url, options]); return result; },
  };
  vm.createContext(scope);
  vm.runInContext(section(portalSource, "  async function openAgent1Tab(", "  async function toggleAgent("), scope);
  let prevented = false;
  return { scope, agent, result, tab, trace, messages, event: { preventDefault() { prevented = true; } }, prevented: () => prevented };
}

test("portal opens immediately, disconnects opener and navigates after issuing the ticket", async () => {
  const p = popup();
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.prevented(), true);
  assert.deepEqual(p.trace.map(x => x[0]), ["open", "request", "navigate"]);
  assert.equal(p.trace[1][1], "/api/agents/agent1/connect-link");
  assert.equal(p.trace[1][2].json.company, "TEST_A");
  assert.equal(p.tab.opener, null);
  assert.equal(p.tab.closed, false);
});

test("blocked popup does not issue a ticket", async () => {
  const p = popup();
  p.scope.window.open = () => null;
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.trace.length, 0);
  assert.equal(p.messages.length, 1);
});

test("other agents retain their ordinary new-tab links", async () => {
  const p = popup();
  p.scope.currentAgent = "agent2";
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.prevented(), false);
  assert.equal(p.trace.length, 0);
});

test("stopped Agent 1 does not open a blank tab", async () => {
  const p = popup();
  p.agent.state = "stopped";
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.trace.length, 0);
  assert.equal(p.messages.length, 1);
});

test("company change during the request closes the new tab", async () => {
  const p = popup();
  p.scope.api = async () => { p.scope.state.company.code = "TEST_B"; return p.result; };
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.tab.closed, true);
  assert.equal(p.trace.some(x => x[0] === "navigate"), false);
});

test("unexpected redirect target is rejected", async () => {
  const p = popup();
  p.result.url = "https://example.com/workspace";
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.tab.closed, true);
  assert.equal(p.trace.some(x => x[0] === "navigate"), false);
});

test("failed ticket issuance closes only the newly opened tab", async () => {
  const p = popup();
  p.scope.api = async () => { throw Error("Agent unavailable"); };
  await p.scope.openAgent1Tab(p.event);
  assert.equal(p.tab.closed, true);
  assert.deepEqual(p.messages, ["Agent unavailable"]);
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

function redeem(ok) {
  const nodes = new Map(), calls = [], notices = [];
  const submit = { disabled: false };
  const $ = id => { if (!nodes.has(id)) nodes.set(id, { disabled: false, querySelector: () => submit }); return nodes.get(id); };
  let openedDialog = false;
  const scope = {
    $, notice: (text, error) => notices.push([text, error]), connect: () => { openedDialog = true; },
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

test("expired ticket preserves the manual connection fallback", async () => {
  const r = redeem(false);
  await r.scope.redeemPortalTicket("expired-ticket");
  assert.equal(r.openedDialog(), true);
  assert.equal(r.$("connect-error").textContent, "Ticket expired");
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
  const scope = {window, $, token:"", connected:false, notice() {},
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
  vm.runInContext(section(agentSource, '  $("allocate-form").onsubmit =', '  $("saved-plans").onclick ='), scope);
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
  function node(tag, text) {
    return { tag, textContent: text, value: "", children: [], append(...items) { this.children.push(...items); }, focus() { this.focused = true; } };
  }
  const proposal = { id: "proposal-1", stale, cases: [{ bank_id: "B1", status: "auto", date: "2026-03-01", account: "A",
    available_minor: 100, reason: "unique_transport", reason_text: "Cần đối chiếu chứng từ", memo: "<script>unsafe</script>",
    allocations: [{ invoice_id: "I1", amount_minor: 100 }], candidates: [] }] };
  let pending;
  const scope = { node, $: () => target, crypto: { randomUUID: () => "test-key" },
    reconciliationState: { proposal }, exactMoney: String, displayDate: String, reconciliationReviewer: () => "Accountant",
    action: work => { pending = work(); }, api: async (url, options) => { calls.push([url, JSON.parse(options.body)]); },
    refresh: async () => {}, loadReconciliation: async () => {}, notice() {} };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, "  function renderReconciliationCases(", "  function renderReconciliationHistory("), scope);
  scope.renderReconciliationCases(proposal);
  const all = object => [object, ...(object.children || []).flatMap(all)];
  return { calls, proposal, scope, elements: all(target), readElements: () => all(target), run: async (form, kind) => {
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
  vm.runInContext(section(agentSource, '  $("source-correction-form").onsubmit =', '  $("saved-plans").onclick ='), scope);
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
