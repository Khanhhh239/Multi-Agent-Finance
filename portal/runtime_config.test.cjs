const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "static/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "static/index.html"), "utf8");

function section(start, end) {
  const begin = source.indexOf(start);
  const finish = source.indexOf(end, begin);
  assert.ok(begin >= 0 && finish > begin, "Expected Portal function was not found");
  return source.slice(begin, finish);
}

function runtime(config = {}) {
  const scope = { window: { __MAF_RUNTIME_CONFIG__: config }, AGENT_LABEL: {
    agent1: "Agent 1", agent2: "Agent 2", agent3: "Agent 3", agent4: "Agent 4",
  } };
  vm.createContext(scope);
  vm.runInContext(section("  const ALL_AGENT_IDS =", "  const WORKSPACE_LABEL ="), scope);
  vm.runInContext(section("  const isAgentEnabled =", "  function applyRuntimeUi("), scope);
  return scope;
}

test("Portal sends cloud requests to the configured gateway and retains request timeouts", async () => {
  const scope = runtime({ apiBaseUrl: "https://gateway.example.test/", enabledAgents: ["agent4"] });
  const calls = [];
  Object.assign(scope, { token: "synthetic-session", authVersion: 0, AbortSignal,
    startLoading() {}, stopLoading() {},
    fetch: async (url, options) => { calls.push([url, options]); return { ok: true, json: async () => ({ ok: true }) }; },
  });
  vm.runInContext(section("  async function api(", "  const sizeText ="), scope);
  await scope.api("/api/state");
  const customSignal = new AbortController().signal;
  await scope.api("/api/inbox/commit", { method: "POST", json: { ids: ["file-1"] }, signal: customSignal });
  assert.equal(calls[0][0], "https://gateway.example.test/api/state");
  assert.ok(calls[0][1].signal instanceof AbortSignal);
  assert.equal(calls[1][1].signal, customSignal);
  assert.equal(calls[1][1].headers["X-Session"], "synthetic-session");
  assert.deepEqual(JSON.parse(calls[1][1].body), { ids: ["file-1"] });
});

test("local requests keep their same-origin URL when no gateway is configured", () => {
  const scope = runtime();
  assert.equal(vm.runInContext('apiUrl("/api/state")', scope), "/api/state");
});

test("cloud capability filtering removes unavailable agents from state and intake results", () => {
  const scope = runtime({ enabledAgents: ["agent4"] });
  scope.next = { agents: [{ id: "agent1" }, { id: "agent4" }],
    slots: [{ agent: "agent1" }, { agent: "agent4" }],
    pending: [{ targets: ["agent1", "agent4"], checks: { agent1: { state: "ready" }, agent4: { state: "ready" } } }],
    batches: [{ files: [{ results: { agent1: { state: "done" }, agent4: { state: "done" } } }] }],
  };
  const filtered = JSON.parse(vm.runInContext("JSON.stringify(filterRuntimeState(next))", scope));
  assert.deepEqual(filtered.agents, [{ id: "agent4" }]);
  assert.deepEqual(filtered.slots, [{ agent: "agent4" }]);
  assert.deepEqual(filtered.pending[0].targets, ["agent4"]);
  assert.deepEqual(Object.keys(filtered.pending[0].checks), ["agent4"]);
  assert.deepEqual(Object.keys(filtered.batches[0].files[0].results), ["agent4"]);
  assert.equal(scope.next.agents.length, 2);
});

for (const count of [1, 4]) {
  test(`overview reflects ${count} available assistants and their launch state`, () => {
    const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => [match[1], {
      dataset: {}, textContent: "", hidden: false, disabled: false,
      replaceChildren(...children) { this.children = children; },
    }]));
    const ids = count === 1 ? ["agent4"] : ["agent1", "agent2", "agent3", "agent4"];
    const scope = { $: id => nodes.get(id), state: { company: { legal_name: "Test Company" },
      agents: ids.map(id => ({ id, name: id, state: "running" })), intake: { unlocked: true } },
      WORKSPACE_LABEL: { agent4: "Trợ lý hỏi đáp" }, STATE_TEXT: { stopped: "Đang tắt" },
      WORKSTATION_INFO: Object.fromEntries(ids.map(id => [id, { icon: "", title: id, desc: id }])),
      el: (tag, attrs, ...children) => ({ tag, attrs, children }),
      agentPageUrl: (a) => "/" + a.id, makePopoutIcon: () => ({}), openAgentStandaloneTab() {},
    };
    vm.createContext(scope);
    vm.runInContext(section("  function renderOverview()", "  function checkLines("), scope);
    scope.renderOverview();
    assert.equal(nodes.get("exec-agents-val").textContent, `${count} / ${count} phân hệ sẵn sàng`);
    assert.equal(nodes.get("start-all").hidden, true);
    assert.equal(nodes.get("agent-grid").children.length, count);
    scope.state.agents[0].state = "stopped";
    scope.renderOverview();
    assert.equal(nodes.get("start-all").hidden, false);
    assert.equal(nodes.get("start-all").disabled, false);
    assert.equal(nodes.get("agent-grid").children.length, count);
  });
}

test("public runtime configuration loads before the Portal application", () => {
  assert.ok(html.indexOf('src="/runtime-config.js"') > 0);
  assert.ok(html.indexOf('src="/runtime-config.js"') < html.indexOf('src="/app.js"'));
});
