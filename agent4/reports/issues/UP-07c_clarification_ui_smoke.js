/* Runtime smoke for separate new-query and clarification forms. */
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
byId("run-label").textContent = "Truy vấn";
byId("question").value = "Lợi nhuận tại HCM?";
byId("query-form").reportValidity = () => Boolean(byId("question").value.trim());

const requests = [];
const firstSession = "a".repeat(32);
const secondSession = "b".repeat(32);
const thirdSession = "c".repeat(32);
const response = (body, status = 200) => ({ok: status < 400, status, json: async () => body});
const clarification = (sessionId, slot, prompt, choices) => ({
  status: "needs_clarification",
  answer: prompt,
  clarification: {session_id: sessionId, slot_prompts: [{slot, prompt, choices}]},
});
const fetch = async (url, options = {}) => {
  if (url === "/health") return response({llm_model: "mock", db_path: "/tmp/demo.db"});
  if (url === "/v1/demo-questions" || url === "/v1/metrics") return response([]);
  if (url !== "/v1/query") throw new Error(`Unexpected fetch: ${url}`);
  requests.push(JSON.parse(options.body));
  switch (requests.length) {
    case 1:
      return response(clarification(firstSession, "metric", "Chọn chỉ tiêu", [
        {value: "gross_profit", label: "Lợi nhuận gộp"},
      ]));
    case 2:
      return response(clarification(firstSession, "time", "Chọn kỳ", [
        {value: "2026-08", label: "Tháng 2026-08"},
      ]));
    case 3:
      return response(clarification(secondSession, "time", "Chọn kỳ", [
        {value: "2026-08", label: "Tháng 2026-08"},
      ]));
    case 4:
      return response({
        status: "error",
        error: {code: "invalid_request", stage: "clarification", message: "Invalid clarification turn."},
        data: null,
      }, 400);
    case 6:
      return response(clarification(thirdSession, "filters", "Chọn giá trị lọc", []));
    default:
      return response({
        status: "ready",
        answer: "Đã xong",
        data: {columns: [], rows: [], row_count: 0},
      });
  }
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
const sendClarificationForm = async value => {
  const form = byId("quick").children.find(item => item.tagName === "form");
  const input = form.children.find(item => item.tagName === "textarea");
  input.value = value;
  form.listeners.submit({preventDefault() {}});
  await tick();
  await tick();
};

(async () => {
  await tick();
  await vm.runInContext("submit()", context);
  assert.equal(requests[0].options.clarification_mode, "guided");
  assert.equal(byId("question").value, "Lợi nhuận tại HCM?");
  assert.equal(byId("run-label").textContent, "Hỏi câu mới");

  const metricButton = byId("quick").children.find(item => item.textContent === "Lợi nhuận gộp");
  metricButton.listeners.click();
  await tick();
  await tick();
  assert.equal(requests[1].session_id, firstSession);
  assert.equal(requests[1].question, "gross_profit");

  byId("question").value = "Câu hỏi mới, không tiếp tục phiên cũ";
  await vm.runInContext("submit()", context);
  assert.equal(requests[2].question, "Câu hỏi mới, không tiếp tục phiên cũ");
  assert.equal(Object.hasOwn(requests[2], "session_id"), false);
  assert.equal(requests[2].options.clarification_mode, "guided");

  await sendClarificationForm("câu trả lời không hợp lệ");
  assert.equal(requests[3].session_id, secondSession);
  assert.equal(byId("status").textContent, "ERROR (400)");
  assert.match(byId("answer").textContent, /chưa ghép được câu trả lời/);
  assert.ok(byId("quick").children.some(item => item.tagName === "form"));

  const periodButton = byId("quick").children.find(item => item.textContent === "Tháng 2026-08");
  periodButton.listeners.click();
  await tick();
  await tick();
  assert.equal(requests[4].session_id, secondSession);
  assert.equal(requests[4].question, "2026-08");
  assert.equal(byId("status").textContent, "OK (200)");
  assert.equal(byId("run-label").textContent, "Truy vấn");

  byId("question").value = "Câu hỏi mới có bộ lọc chưa hỗ trợ";
  await vm.runInContext("submit()", context);
  assert.equal(requests[5].question, "Câu hỏi mới có bộ lọc chưa hỗ trợ");
  assert.equal(Object.hasOwn(requests[5], "session_id"), false);
  assert.ok(byId("quick").children.some(item => item.textContent.includes("chưa hỗ trợ diễn giải")));
  assert.ok(!byId("quick").children.some(item => item.tagName === "form"));
  console.log("UI smoke passed: separate sessions, fresh-query isolation, and retry after a 400.");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
