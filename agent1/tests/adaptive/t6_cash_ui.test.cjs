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
    statusLabels: {overdue: "Quá hạn, còn phải trả", partial: "Một phần", paid: "Đã tất toán", cancelled: "Đã hủy nghĩa vụ", replaced: "Đã thay thế"}};
  vm.createContext(scope);
  vm.runInContext(source.slice(source.indexOf("  function cashDetailTable("), source.indexOf("  function renderForecast(")), scope);
  return scope;
}
function plan() {
  const weeks = [{week: 1, date: "2026-02-17", opening_balance: 100, ar_in: 10, cash_sale_in: 0, new_credit_in: 0,
    cash_in: 10, scheduled_out: 200, variable_cost_topup: 0, cash_out: 200, net_change: -190, balance: -90}];
  return {cash_decomposition: {cutoff: "2026-02-10", model_version: "SAVED", scope: {description: "Toàn bộ công nợ mở"}, weeks,
    risk_focus: {week: 1, date: "2026-02-17", trigger: "expected_shortfall", expected_shortfall: 90, cash_floor: 0,
      opening_balance: 100, cumulative_cash_in: 10, cumulative_cash_out: 200, balance: -90, unreceived_ar: 990,
      largest_unreceived_customers: [{customer_id: "<script>unsafe</script>", unreceived: 990}], largest_scheduled_outflows: [], unknown_outflow_weeks: []},
    invoices: [{invoice_id: "<img onerror=unsafe>", customer_id: "CUSTOMER", outstanding: 1000, expected_in: 10, expected_by_week: [10]}],
    customers: [{customer_id: "CUSTOMER", invoice_count: 1, outstanding: 1000, expected_in: 10, expected_by_week: [10]}],
    outflows: [], assumptions: ["Không dùng SHAP cho phân vị."],
    }};

}

test("cash UI shows saved provenance, money bridge and T10 entry points safely as text", () => {
  const panel = ui().renderCashDecomposition(plan());
  const text = content(panel);
  for (const expected of ["SAVED", "2026-02-10", "thiếu 90 VND", "T1 + adapter partial", "Chạy lại T6", "<script>unsafe</script>", "<img onerror=unsafe>", "990 VND"]) assert.ok(text.includes(expected), expected);
  assert.equal(descendants(panel, node => node.tag === "script" || node.tag === "img").length, 0);
});

function t10Plan() {
  const data = plan(); data.id = "SAVED";
  data.t10 = {identity: {t1_version: "FROZEN-T1", adapter_version: "PARTIAL-V2", partial_version: "FROZEN-PARTIAL", t6: {version:"T6-V2"}},
    partial_profile: {fitted_through:"2026-01-31", probability:[.5], ratios:[[.5]], weights:[[1]], mean_ratios:[.5], evidence:{}},
    partial_support_status:"support_not_recorded", assumptions:["Không suy tác động của gọi điện."], replay:{status:"frozen"}};
  data.cash_decomposition.invoices[0].receipt_explanation = {formula:"ENGINE-FORMULA", weeks:[{week:1, expected_opening_debt:1000,
    expected_from_settlement:10, expected_from_partial:20, expected_receipt:30, expected_remaining_debt:970,
    settlement_probability:.1, settlement_hazard:.1, partial_states:[{cell:0, received_cash_state:false, expected_opening_debt:1000}]}]};
  return data;
}

test("adapter UI uses saved engine components and never fabricates missing partial support", () => {
  const panel = ui().renderT10Evidence(t10Plan()), text = content(panel);
  for (const value of ["FROZEN-T1", "FROZEN-PARTIAL", "ENGINE-FORMULA", "30 VND", "10 VND", "20 VND", "Chưa ghi", "chưa tính SHAP của tiền thu"]) assert.ok(text.includes(value), value);
  assert.ok(!text.includes("Có bằng chứng số tuần học"));
  assert.equal(descendants(panel, n => n.tag === "img" || n.tag === "script").length, 0);
});

test("risk comparison shows portfolio quantiles and probability changes as model sensitivity", () => {
  const baseline = {expected_balance:30, balance_quantiles:{"0.1":-10,"0.5":20,"0.9":60}, below_floor_probability:.2};
  const scenario = {expected_balance:10, balance_quantiles:{"0.1":-30,"0.5":0,"0.9":40}, below_floor_probability:.4};
  const panel = ui().renderT10ScenarioResult({baseline_any_shortfall_probability:.2, scenario_any_shortfall_probability:.4,
    delta_any_shortfall_probability:.2, delta_probability_mc_standard_error:.01, limitations:["Không cộng P10 hóa đơn."],
    weeks:[{week:1,baseline,scenario,delta:{expected_balance:-20,balance_quantiles:{"0.1":-20,"0.5":-20,"0.9":-20}, below_floor_probability:.2}}]});
  const text = content(panel);
  for (const value of ["Δ P10", "Δ P50", "Δ P90", "20.00 điểm %", "MC thô", "chưa chứng minh tác động", "Không cộng P10 hóa đơn"]) assert.ok(text.includes(value), value);
});

test("scenario form sends assumptions against the saved forecast without replacing its seed or bundle", async () => {
  const scope = ui(), calls = [];
  scope.action = async fn => fn();
  scope.api = async (url, options) => { calls.push([url, JSON.parse(options.body)]); throw new Error("recorded-request"); };
  const panel = scope.renderT10Scenarios(t10Plan());
  const get = label => descendants(panel, n => n.attributes["aria-label"] === label)[0];
  get("Khách trả chậm").value = "CUSTOMER";
  get("Khoản chi cần dời").value = "";
  get("Số tuần trả chậm thêm").value = "2";
  scope.action = async fn => { try { await fn(); } catch (e) { assert.equal(e.message, "recorded-request"); } };
  const form = descendants(panel, n => n.tag === "form")[0];
  form.onsubmit({preventDefault(){}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls[0][0], "/forecasts/SAVED/scenarios");
  assert.deepEqual(calls[0][1], {customer_id:"CUSTOMER",customer_delay_weeks:2,expense_id:null,expense_delay_weeks:0});
  assert.equal("simulation_seed" in calls[0][1], false);
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

test("T5 ledger separates cancelled and replaced amounts from what remains payable", () => {
  const data = plan();
  data.t5 = {obligations: [
    {expense_id: "CANCELLED", status: "cancelled", obligation_amount: 100, settled_amount: 40, cancelled_amount: 60, replaced_amount: 0, remaining_amount: 0},
    {expense_id: "OLD", status: "replaced", obligation_amount: 100, settled_amount: 0, cancelled_amount: 0, replaced_amount: 100, remaining_amount: 0},
  ]};
  const panel = ui().renderCashDecomposition(data);
  const ledger = descendants(panel, node => node.tag === "table" && content(node).includes("Còn phải trả/nhận"))[0];
  const headers = descendants(ledger, node => node.tag === "th").map(content);
  const rows = descendants(ledger, node => node.tag === "tbody")[0].children.map(row =>
    Object.fromEntries(row.children.map((cell, i) => [headers[i], content(cell)])));
  assert.equal(rows[0]["Đã thanh toán"], "40 VND");
  assert.equal(rows[0]["Đã hủy"], "60 VND");
  assert.equal(rows[0]["Đã thay thế"], "0 VND");
  assert.equal(rows[1]["Đã thay thế"], "100 VND");
  assert.ok(rows.every(row => row["Còn phải trả/nhận"] === "0 VND"));
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
