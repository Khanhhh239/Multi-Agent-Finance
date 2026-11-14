/* Runtime smoke for the embedded demo client, using only Node built-ins. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(process.argv[2] || "/tmp/agent4-demo-ui-check.js", "utf8");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.classList = {add() {}, remove() {}};
    this.value = "";
    this.textContent = "";
    this.hidden = false;
    this.open = false;
    this.disabled = false;
    this.placeholder = "";
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  reportValidity() { return Boolean(this.value.trim()); }
  focus() {}
}

const elements = new Map();
const byId = id => {
  if (!elements.has(id)) elements.set(id, new Element(id));
  return elements.get(id);
};
byId("persona").value = "cfo_full";
byId("locale").value = "vi-VN";
byId("question").value = "Lợi nhuận tại HCM?";
byId("query-form").reportValidity = () => Boolean(byId("question").value.trim());

const requests = [];
const sessionId = "a".repeat(32);
const response = body => ({ok: true, status: 200, json: async () => body});
const fetch = async (url, options = {}) => {
  if (url === "/health") return response({llm_model: "mock", db_path: "/tmp/demo.db"});
  if (url === "/v1/demo-questions" || url === "/v1/metrics") return response([]);
  if (url !== "/v1/query") throw new Error(`Unexpected fetch: ${url}`);
  requests.push(JSON.parse(options.body));
  if (requests.length === 1) {
    return response({
      status: "needs_clarification",
      answer: "Chọn chỉ tiêu",
      clarification: {
        session_id: sessionId,
        slot_prompts: [{
          slot: "metric",
          prompt: "Chọn chỉ tiêu",
          choices: [{value: "gross_profit", label: "Lợi nhuận gộp"}],
        }],
      },
    });
  }
  if (requests.length === 2) {
    return response({
      status: "needs_clarification",
      answer: "Chọn kỳ",
      clarification: {
        session_id: sessionId,
        slot_prompts: [{
          slot: "time",
          prompt: "Chọn kỳ",
          choices: [{value: "2026-08", label: "Tháng 2026-08"}],
        }],
      },
    });
  }
  return response({
    status: "ready",
    answer: "Đã xong",
    data: {columns: [], rows: [], row_count: 0},
    interpretation: {metric_ids: ["gross_profit"], time: {start: "2026-08-01", end: "2026-08-31"}},
  });
};
const document = {
  getElementById: byId,
  createElement: tag => new Element(tag),
  createDocumentFragment: () => new Element("fragment"),
  createTextNode: text => ({textContent: text}),
  querySelectorAll: () => [],
};
const context = vm.createContext({
  document,
  fetch,
  performance: {now: () => 0},
  setInterval: () => 1,
  clearInterval() {},
  AbortController,
});
vm.runInContext(source, context);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

(async () => {
  await tick();
  await vm.runInContext("submit()", context);
  const metricButton = byId("quick").children.find(item => item.textContent === "Lợi nhuận gộp");
  assert.ok(metricButton, "renders the server metric choice");
  metricButton.listeners.click();
  await tick();
  await tick();

  assert.equal(requests[0].options.clarification_mode, "guided");
  assert.equal(requests[1].session_id, sessionId);
  assert.equal(requests[1].question, "gross_profit");
  assert.equal(byId("quick").children[0].textContent, "Chọn kỳ");
  assert.equal(byId("quick").children[1].textContent, "Tháng 2026-08");
  assert.ok(!byId("quick").children.some(item => item.textContent === "Lợi nhuận gộp"));

  byId("quick").children[1].listeners.click();
  await tick();
  await tick();
  assert.equal(requests[2].session_id, sessionId);
  assert.equal(requests[2].question, "2026-08");
  assert.equal(byId("status").textContent, "OK (200)");
  console.log("UI continuation smoke passed: guided start, two canonical choices, one session.");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
