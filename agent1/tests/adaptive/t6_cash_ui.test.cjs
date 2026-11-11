const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../../agent1_service/ui/workspace/app.js"), "utf8");
class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text; this.children = []; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
function content(node) { return [node.textContent || "", ...node.children.map(content)].join(" "); }
function descendants(node, predicate) { return [...(predicate(node) ? [node] : []), ...node.children.flatMap(child => descendants(child, predicate))]; }
function ui() {
  const scope = {node: (tag, text) => new Element(tag, text), fmt: new Intl.NumberFormat("vi-VN"), displayDate: value => value,
    statusLabels: {overdue: "Quá hạn, còn phải trả", partial: "Một phần", paid: "Đã tất toán"}};
  vm.createContext(scope);
  vm.runInContext(source.slice(source.indexOf("  function cashDetailTable("), source.indexOf("  function renderForecast(")), scope);
  return scope;
}
function plan() {
  const weeks = [{week: 1, date: "2026-02-17", opening_balance: 100, ar_in: 10, cash_sale_in: 0, new_credit_in: 0,
    cash_in: 10, scheduled_out: 200, variable_cost_topup: 0, cash_out: 200, net_change: -190, balance: -90}];
  const scenario = {ar_in: 10, minimum_balance: -90, minimum_balance_change: 0, closing_balance: -90,
    first_below_floor_week: 1, receipts_pushed_beyond_horizon: 0, weeks: [{week: 1, date: "2026-02-17", balance: -90, balance_change: 0}]};
  return {cash_decomposition: {cutoff: "2026-02-10", model_version: "SAVED", scope: {description: "Toàn bộ công nợ mở"}, weeks,
    risk_focus: {week: 1, date: "2026-02-17", trigger: "expected_shortfall", expected_shortfall: 90, cash_floor: 0,
      opening_balance: 100, cumulative_cash_in: 10, cumulative_cash_out: 200, balance: -90, unreceived_ar: 990,
      largest_unreceived_customers: [{customer_id: "<script>unsafe</script>", unreceived: 990}], largest_scheduled_outflows: [], unknown_outflow_weeks: []},
    invoices: [{invoice_id: "<img onerror=unsafe>", customer_id: "CUSTOMER", outstanding: 1000, expected_in: 10, expected_by_week: [10]}],
    customers: [{customer_id: "CUSTOMER", invoice_count: 1, outstanding: 1000, expected_in: 10, expected_by_week: [10]}],
    outflows: [], assumptions: ["Không dùng SHAP cho phân vị."],
    timing_comparison: {scenarios: ["Kế hoạch đang xem", "Thu sớm 2 tuần", "Thu chậm 2 tuần"].map(label => ({...scenario, label})), assumptions: ["Chỉ dịch phần dự thu trong kỳ."]}}};
}

test("cash UI shows saved provenance, money bridge and both timing scenarios safely as text", () => {
  const panel = ui().renderCashDecomposition(plan());
  const text = content(panel);
  for (const expected of ["SAVED", "2026-02-10", "thiếu 90 VND", "Thu sớm 2 tuần", "Thu chậm 2 tuần", "<script>unsafe</script>", "<img onerror=unsafe>", "990 VND"]) assert.ok(text.includes(expected), expected);
  assert.equal(descendants(panel, node => node.tag === "script" || node.tag === "img").length, 0);
});

test("T5 UI keeps paid remainder, overdue warning and refunds visible without HTML injection", () => {
  const data = plan();
  data.t5 = {obligations: [{expense_id: "<script>rent</script>", due_date: "2026-02-09", category: "rent",
    status: "overdue", obligation_amount: 100, settled_amount: 40, remaining_amount: 60, forecast_date: "2026-02-11"}]};
  data.cash_decomposition.inflows = [{expense_id: "R", date: "2026-02-12", amount: 300, source: "Quyết định đã duyệt"}];
  data.cash_decomposition.weeks[0].obligation_in = 300;
  const panel = ui().renderCashDecomposition(data), text = content(panel);
  for (const expected of ["<script>rent</script>", "Quá hạn", "40 VND", "60 VND", "ngày làm việc kế tiếp", "Quyết định đã duyệt", "300 VND"])
    assert.ok(text.includes(expected), expected);
  assert.equal(descendants(panel, node => node.tag === "script").length, 0);
});

test("grouping and search use the full saved contributions, with pagination instead of truncation", () => {
  const scope = ui(), data = plan();
  data.cash_decomposition.invoices = Array.from({length: 45}, (_, i) => ({...data.cash_decomposition.invoices[0], invoice_id: "I" + i}));
  const panel = scope.renderCashDecomposition(data);
  const firstBody = () => descendants(panel, node => node.tag === "tbody")[0];
  assert.equal(firstBody().children.length, 20);
  const next = descendants(panel, node => node.tag === "button" && node.textContent === "Sau →")[0];
  next.onclick();
  assert.ok(content(firstBody()).includes("I20"));
  const search = descendants(panel, node => node.attributes["aria-label"] === "Tìm khoản dự thu")[0];
  search.value = "I44"; search.oninput();
  assert.equal(firstBody().children.length, 1);
  assert.ok(content(firstBody()).includes("I44"));
  search.value = "";
  const group = descendants(panel, node => node.attributes["aria-label"] === "Nhóm đóng góp dự thu")[0];
  group.value = "customers"; group.onchange();
  assert.equal(firstBody().children.length, 1);
  assert.ok(content(firstBody()).includes("CUSTOMER"));
});

test("simulation-only risk and old plans never fabricate a cash shortfall decomposition", () => {
  const scope = ui(), data = plan();
  data.cash_decomposition.risk_focus.trigger = "simulation_only";
  const text = content(scope.renderCashDecomposition(data));
  assert.ok(text.includes("ít nhất 25% đường mô phỏng"));
  assert.ok(text.includes("chưa phân rã xác suất"));
  assert.ok(!text.includes("thiếu 90 VND"));
  assert.ok(content(scope.renderCashDecomposition({})).includes("Tạo kế hoạch mới"));
});
