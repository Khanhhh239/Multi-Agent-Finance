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

test("manual allocation sends VND text without rounding through a JavaScript number", async () => {
  const nodes = new Map(), calls = [];
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, { value: "100000000000000001", click() {} });
    return nodes.get(id);
  };
  let pending;
  const scope = { $, action: work => { pending = work(); }, refresh: async () => {}, notice() {},
    api: async (url, options) => calls.push([url, JSON.parse(options.body)]) };
  vm.createContext(scope);
  vm.runInContext(section(agentSource, '  $("allocate-form").onsubmit =', '  $("saved-plans").onclick ='), scope);
  $("allocate-form").onsubmit({ preventDefault() {} });
  await pending;
  assert.equal(calls[0][0], "/allocations");
  assert.equal(calls[0][1].amount, "100000000000000001");
});
