const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../../agent1_service/ui/workspace/app.js"), "utf8");
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
}
class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text || ""; this.children = []; this.value = ""; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}
function descendants(element, predicate) {
  return [...(predicate(element) ? [element] : []), ...element.children.flatMap(child => descendants(child, predicate))];
}
function content(element) { return [element.textContent, ...element.children.map(content)].join(" "); }
function ui() {
  const elements = new Map(), calls = [], notices = [];
  let nextKey = 0;
  const scope = {
    $: id => {
      if (!elements.has(id)) elements.set(id, new Element("div"));
      return elements.get(id);
    },
    node: (tag, text) => new Element(tag, text),
    exactMoney: String, displayDate: value => value,
    crypto: {randomUUID: () => "key-" + (++nextKey)},
    reconciliationReviewer: () => "Reviewer",
    notice: (text, error) => notices.push({text, error}),
    refresh: async () => {}, loadReconciliation: async () => {},
    reconciliationState: {pending_count: 3, unallocated: "19000000", pending: []},
    api: async (url, options) => { calls.push({url, body:JSON.parse(options.body)}); },
    chooseAllocation: () => assert.fail("No manual allocation was requested"),
  };
  scope.action = (fn) => { scope.pendingAction = fn(); return scope.pendingAction; };
  vm.createContext(scope);
  vm.runInContext(section("  let reconciliationProposalRefresh =", "  async function loadReconciliation()"), scope);
  vm.runInContext(section("  function renderReconciliationCases(", "  function renderReconciliationHistory("), scope);
  return {scope, calls, notices, target:scope.$("reconciliation-cases")};
}
function proposal(id, bank = "DP-B-GOP") {
  return {id, cutoff:"2026-11-18", stale:false, cases:[{
    bank_id:bank, status:"auto", reason:"unique_transport", date:"2026-11-18", account:"DP-VND01",
    available_minor:"10000000", reason_text:"Check documents", candidates:[],
    allocations:[{invoice_id:bank + "-1",amount_minor:"3000000"}, {invoice_id:bank + "-2",amount_minor:"7000000"}],
  }]};
}

test("stale proposals show a local reload action instead of old actionable-looking bank cards", async () => {
  const {scope, calls, target} = ui();
  scope.renderReconciliationCases({...proposal("OLD"), stale:true});
  assert.ok(content(target).includes("3 khoản chờ"));
  assert.ok(content(target).includes("Cần cập nhật đề xuất"));
  assert.ok(!content(target).includes("DP-B-GOP"));
  const buttons = descendants(target, element => element.tag === "button");
  assert.equal(buttons.length, 1);
  assert.ok(buttons[0].textContent.includes("Tải lại đề xuất"));
  await buttons[0].onclick();
  assert.deepEqual(calls.map(call => call.url), ["/reconciliation/run"]);
});

test("approving GOP sends only its bank ID and refreshes remaining proposals without accepting them", async () => {
  const {scope, calls, notices, target} = ui();
  const current = proposal("CURRENT");
  scope.reconciliationState.proposal = current;
  scope.loadReconciliation = async () => {
    const fresh = calls.some(call => call.url === "/reconciliation/run");
    const next = {...proposal(fresh ? "NEW" : "CURRENT", "DP-B-MOTPHAN"), stale:!fresh};
    scope.reconciliationState.proposal = next;
    scope.renderReconciliationCases(next);
  };
  scope.renderReconciliationCases(current);
  const form = descendants(target, element => element.tag === "form")[0];
  form.onsubmit({preventDefault(){}, submitter:{value:"accept"}});
  await scope.pendingAction;
  assert.deepEqual(calls.map(call => call.url), ["/reconciliation/accept", "/reconciliation/run"]);
  assert.equal(calls[0].body.bank_id, "DP-B-GOP");
  assert.equal(calls[0].body.proposal_id, "CURRENT");
  assert.ok(notices[0].text.includes("Đã duyệt riêng DP-B-GOP"));
  assert.ok(!content(target).includes("DP-B-GOP"));
  assert.ok(content(target).includes("DP-B-MOTPHAN"));
  assert.ok(descendants(target, element => element.tag === "button").some(button => button.value === "accept"));
});

test("a refresh failure reports the saved decision and never resubmits acceptance", async () => {
  const {scope, calls, notices} = ui();
  scope.reconciliationState.proposal = {...proposal("OLD"), stale:true};
  scope.api = async (url, options) => {
    calls.push({url, body:JSON.parse(options.body)});
    throw new Error("offline");
  };
  await scope.refreshReconciliationAfterChange("Đã duyệt riêng DP-B-GOP.");
  assert.deepEqual(calls.map(call => call.url), ["/reconciliation/run"]);
  assert.ok(notices.at(-1).text.startsWith("Đã duyệt riêng DP-B-GOP."));
  assert.ok(notices.at(-1).text.includes("không cần gửi lại thao tác vừa lưu"));
  assert.equal(notices.at(-1).error, true);
});

test("concurrent reload clicks share one proposal refresh, and failures remain retryable", async () => {
  const {scope, calls} = ui();
  let release;
  scope.api = async (url) => { calls.push({url}); await new Promise(resolve => { release = resolve; }); };
  const first = scope.findReconciliationProposals(), second = scope.findReconciliationProposals();
  assert.equal(first, second);
  assert.equal(calls.length, 1);
  release();
  await first;
  scope.api = async () => { throw new Error("offline"); };
  await assert.rejects(scope.findReconciliationProposals(), /offline/);
  scope.api = async () => {};
  await scope.findReconciliationProposals();
});

test("editing a pending bank opens and scrolls to its correction form before loading", () => {
  const {scope} = ui();
  vm.runInContext(section("  function focusCorrectionRecord(", "  let reconciliationProposalRefresh ="), scope);
  const panel = {open:false, scrollIntoView(options){ this.scroll = options; }};
  let submits = 0;
  const form = scope.$("source-correction-load");
  form.closest = () => panel;
  form.requestSubmit = () => { submits++; };
  scope.sourceCorrection = {records:[]};
  scope.openBankCorrection("DP-B-CHUARO");
  assert.equal(panel.open, true);
  assert.equal(panel.scroll.block, "start");
  assert.equal(scope.$("source-correction-kind").value, "bank");
  assert.equal(scope.$("source-correction-id").value, "DP-B-CHUARO");
  assert.equal(submits, 1);
});

test("clicking an already loaded bank focuses its cash flow field instead of loading a duplicate", () => {
  const {scope} = ui();
  vm.runInContext(section("  function focusCorrectionRecord(", "  let reconciliationProposalRefresh ="), scope);
  const field = {scrollIntoView(options){ this.scroll = options; }, focus(options){ this.focused = options; }};
  const form = scope.$("source-correction-load");
  form.closest = () => ({scrollIntoView(){}});
  form.requestSubmit = () => assert.fail("Existing edits must not be reloaded");
  scope.sourceCorrection = {records:[{kind:"bank", identifier:"DP-B-CHUARO", inputs:{cash_flow_class:field}}]};
  scope.openBankCorrection("DP-B-CHUARO");
  assert.equal(field.scroll.block, "center");
  assert.equal(field.focused.preventScroll, true);
});

test("outside-AR history cannot crowd actionable proposals out of the first 100 cases", () => {
  const {scope, target} = ui(), current = proposal("CURRENT");
  const outside = Array.from({length:625}, (_, i) => ({...current.cases[0],
    bank_id:"OUT-" + i, reason:"non_ar_bank_movement", allocations:[]}));
  current.cases = [...outside, ...current.cases];
  scope.renderReconciliationCases(current);
  assert.ok(content(target).includes("DP-B-GOP"));
  assert.equal(descendants(target, element => element.tag === "form").length, 1);
  const group = descendants(target, element => element.id === "reconciliation-outside-ar")[0];
  assert.ok(!group.open);
  assert.ok(content(group).includes("625 giao dịch"));
  assert.equal(descendants(group, element => element.tag === "tbody").length, 0);
});

test("outside-AR lookup pages every record without approval controls and edits only the selected bank", () => {
  const {scope, target, calls} = ui(), current = proposal("CURRENT");
  current.cases = Array.from({length:26}, (_, i) => ({...current.cases[0],
    bank_id:"OUT-" + String(i).padStart(2, "0"), reason:"non_ar_bank_movement", allocations:[]}));
  let selected;
  scope.openBankCorrection = bank => { selected = bank; };
  scope.renderReconciliationCases(current);
  assert.ok(content(target).includes("Không còn đề xuất ghép công nợ cần xử lý"));
  const group = descendants(target, element => element.id === "reconciliation-outside-ar")[0];
  group.open = true; group.ontoggle();
  const buttons = () => descendants(group, element => element.tag === "button");
  assert.equal(buttons().filter(button => button.textContent === "Sửa dòng sao kê").length, 25);
  assert.equal(buttons().find(button => button.textContent === "Trang trước").disabled, true);
  buttons().find(button => button.textContent === "Trang sau").onclick();
  assert.ok(content(group).includes("Dòng 26–26 / 26"));
  assert.equal(buttons().find(button => button.textContent === "Trang sau").disabled, true);
  buttons().find(button => button.textContent === "Sửa dòng sao kê").onclick();
  assert.equal(selected, "OUT-25");
  assert.equal(descendants(group, element => element.tag === "form").length, 0);
  assert.deepEqual(calls, []);
  buttons().find(button => button.textContent === "Trang trước").onclick();
  assert.ok(content(group).includes("Dòng 1–25 / 26"));
});
