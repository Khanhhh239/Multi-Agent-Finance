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

test("saved plan browsing and restore controls are removed from the workspace", () => {
  const html = fs.readFileSync(path.resolve(__dirname, "../../agent1_service/ui/workspace/index.html"), "utf8");
  assert.equal(html.includes('id="saved-plans"'),false);
  assert.equal(source.includes('$("saved-plans").onclick'),false);
  assert.equal(source.includes('function restoreForecastInputs('),false);
  assert.ok(html.includes('id="forecast-form"'),"New forecasts remain available");
});
