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
function ui() {
  const elements = new Map();
  const scope = {
    $: id => {
      if (!elements.has(id)) elements.set(id, {value:"", checked:false, dataset:{}, onchange(){}});
      return elements.get(id);
    },
    document: {addEventListener(){}}, labels: {},
  };
  vm.createContext(scope);
  vm.runInContext(section("  function fieldValidationError(", "  function connect("), scope);
  scope.clearFormErrors = () => {};
  scope.setDate = (id, iso) => { scope.$(id).value = iso; scope.$(id).dataset.iso = iso; };
  scope.presets = {base:[0,0,false], delay14:[14,0,false], delay28:[28,0,false], cost25:[0,25,false], stress:[0,0,true]};
  vm.runInContext(section("  function restoreForecastInputs(", '  $("forecast-form").onsubmit ='), scope);
  return scope;
}

test("business validation errors cannot be labelled as valid rows", () => {
  const scope = ui();
  const result = {rows:1,valid_rows:1,error_count:1,can_commit:false,updates:0};
  const title = scope.importPreviewTitle(result);
  assert.ok(title.includes("Chưa thể lưu"));
  assert.ok(title.includes("1 lỗi cần sửa"));
  assert.ok(!title.includes("dòng hợp lệ"));
  assert.ok(scope.importPreviewTitle({...result,error_count:0}).includes("Chưa thể lưu"));
  assert.equal(scope.importPreviewTitle({...result,error_count:0,can_commit:true,
    counts:{new:0,changed:0,unchanged:1}}), "1/1 dòng hợp lệ · 0 thêm mới · 0 sửa · 1 trùng giữ nguyên");
});

test("week lists reject malformed or out of horizon input with Vietnamese field guidance", () => {
  const scope = ui();
  assert.deepEqual(Array.from(scope.parseConfirmedWeeks(" 1, 2,4 ",4)),[1,2,4]);
  assert.deepEqual(Array.from(scope.parseConfirmedWeeks(" ",4)),[]);
  for (const value of ["abc","0","5","1.5","1e0","1,,2","1,"])
    assert.throws(() => scope.parseConfirmedWeeks(value,4), e =>
      e.fieldErrors[0].id === "confirmed-weeks" && /từ 1 đến 4/.test(e.message) && /1,2,3/.test(e.message));
  assert.throws(() => scope.parseConfirmedWeeks("2",1), e => e.message.endsWith("ví dụ 1."));
});

test("API field locations become actionable Vietnamese errors", () => {
  const scope = ui(); scope.$("horizon-weeks").value = "4";
  const error = scope.apiValidationError([{loc:["body","confirmed_weeks",0],type:"int_type",msg:"Input should be a valid integer"}],"/predict");
  assert.equal(error.fieldErrors[0].id,"confirmed-weeks");
  assert.ok(error.message.includes("Các tuần đã rà soát"));
  assert.ok(!error.message.includes("Input should"));
  const money = scope.apiValidationError([{loc:["body","cash_floor"],type:"float_type"}],"/predict");
  assert.equal(money.fieldErrors[0].id,"cash-floor");
  assert.ok(money.message.includes("Ngưỡng cảnh báo (VND)"));
  const expense = scope.apiValidationError([{loc:["body","expense_multiplier"],type:"less_than_equal",ctx:{le:3}}],"/predict");
  assert.ok(expense.message.includes("Thay đổi chi (%)"));
  assert.ok(expense.message.includes("không vượt quá 200"));
});

test("opening a saved plan restores all exposed assumptions without pre-confirming coverage", () => {
  const scope = ui();
  scope.$("forecast-complete").checked = true;
  scope.restoreForecastInputs({cutoff:"2026-11-11",opening_balance:250000000,cash_floor:100000000,horizon_weeks:4,
    confirmed_weeks:[1,3],operating_included:true,
    scenario:{delay_days:8,expense_multiplier:1.125,delay_customer:"C1",shared_customer_risk:true}});
  for (const [id,value] of Object.entries({"forecast-cutoff":"2026-11-11","opening-balance":250000000,
    "cash-floor":100000000,"horizon-weeks":4,"confirmed-weeks":"1,3","delay-days":8,
    "expense-change":12.5,"delay-customer":"C1","scenario-preset":"custom"}))
    assert.equal(scope.$(id).value,value,id);
  assert.equal(scope.$("include-operating").checked,true);
  assert.equal(scope.$("common-risk").checked,true);
  assert.equal(scope.$("forecast-complete").checked,false);
  assert.equal(scope.$("forecast-input-context").hidden,false);
  const multiplier = 1.0000000000001;
  scope.restoreForecastInputs({scenario:{expense_multiplier:multiplier}});
  assert.equal(scope.$("scenario-preset").value,"custom");
  assert.equal(1+scope.$("expense-change").value/100,multiplier);
});

test("saved preset scenarios and missing legacy parameters do not keep stale form values", () => {
  const scope = ui();
  for (const [preset,[delay,expense,shared]] of Object.entries(scope.presets)) {
    scope.restoreForecastInputs({cutoff:"2026-11-11",opening_balance:0,cash_floor:0,weeks:[{}],confirmed_weeks:[],
      scenario:{delay_days:delay,expense_multiplier:1+expense/100,shared_customer_risk:shared}});
    assert.equal(scope.$("scenario-preset").value,preset);
    assert.equal(scope.$("cash-floor").value,0);
  }
  scope.restoreForecastInputs({weeks:[{},{}]});
  assert.equal(scope.$("opening-balance").value,"");
  assert.equal(scope.$("cash-floor").value,"");
  assert.equal(scope.$("horizon-weeks").value,2);
  assert.equal(scope.$("forecast-cutoff").value,"");
  assert.equal(scope.$("forecast-cutoff").dataset.iso,undefined);
  assert.ok(scope.$("forecast-input-context").textContent.includes("chưa có đủ tham số"));
});
