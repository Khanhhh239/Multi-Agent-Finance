const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.resolve(__dirname, "../../agent1_service/ui/workspace/app.js"), "utf8");
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first);
  assert(first >= 0 && last > first);
  return source.slice(first, last);
}
class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text || ""; this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
}
function content(node) { return [node.textContent, ...node.children.map(content)].join(" "); }
function descendants(node, tag) { return [...(node.tag === tag ? [node] : []), ...node.children.flatMap(n => descendants(n, tag))]; }
function ui() {
  const elements = Object.fromEntries(["t1-updates", "train-button", "train-schedule-hint", "versions-list"].map(id => [id, new Element("div")]));
  const context = { $: id => elements[id], elements, node: (tag, text) => new Element(tag, text),
    fmt: new Intl.NumberFormat("vi-VN"), displayDate: v => v || "—", selectedDate: "2026-11-14",
    state: { jobs: [], t1_updates: { due: true, state: { next_due: "2026-11-01" }, challengers: [] } } };
  context.inputDate = () => context.selectedDate;
  vm.createContext(context);
  vm.runInContext(section("  function servingModeLabel(", "  function renderForecast("), context);
  vm.runInContext(section("  function updateDecisionMessage(", "  function renderJobs("), context);
  vm.runInContext(section("  function renderT1Updates(", "  function renderVersions("), context);
  vm.runInContext(section("  function renderVersions(", '  $("export-report").onclick'), context);
  return context;
}

test("frozen global provenance corrects old company_trained labels", () => {
  const c = ui();
  assert.equal(c.servingModeLabel({mode: "company_trained", model_version: "global:OLD"}), "MÔ HÌNH NỀN DỰ PHÒNG");
  assert.equal(c.servingModeLabel({mode: "company_trained", t1_provenance: {source: "global_catalog"}}), "MÔ HÌNH NỀN DỰ PHÒNG");
});

test("explicit serving states distinguish selected globals and adapted bundles", () => {
  const c = ui();
  assert.equal(c.servingModeLabel({serving_mode: "global_selected"}), "MÔ HÌNH NỀN ĐƯỢC CHỌN");
  assert.equal(c.servingModeLabel({serving_mode: "company_adapted"}), "ĐÃ THÍCH NGHI CHO DOANH NGHIỆP");
});

test("an old registry or adaptation flag alone does not claim private training", () => {
  const c = ui();
  assert.equal(c.servingModeLabel({mode: "company_trained", company_bundle_version: "OLD"}), "PHIÊN BẢN ĐÃ LƯU");
  assert.equal(c.servingModeLabel({mode: "company_trained", t1_provenance: {local_adaptation: true}}), "PHIÊN BẢN ĐÃ LƯU");
  assert.equal(c.servingModeLabel({mode: "company_trained", t10: {partial_profile: {evidence: {
    prior_sha256: "GLOBAL", cells: [{weeks: 10}]
  }}}}), "ĐÃ THÍCH NGHI CHO DOANH NGHIỆP");
});

test("server schedule and selected cutoff both gate training", () => {
  const c = ui();
  c.state.t1_updates.due = false;
  c.renderTrainingAvailability();
  assert.equal(c.elements["train-button"].disabled, true);
  c.state.t1_updates.due = true;
  c.selectedDate = "2026-10-31";
  c.renderTrainingAvailability();
  assert.equal(c.elements["train-button"].disabled, true);
  assert.match(content(c.elements["train-schedule-hint"]), /2026-11-01/);
  c.selectedDate = "2026-11-01";
  c.renderTrainingAvailability();
  assert.equal(c.elements["train-button"].disabled, false);
  c.state.jobs = [{status: "running"}];
  c.renderTrainingAvailability();
  assert.equal(c.elements["train-button"].disabled, true);
});

test("challenger history remains accessible beyond the first twenty records", () => {
  const c = ui();
  c.state.t1_updates.challengers = Array.from({length: 25}, (_, i) => ({
    id: String(i), origin: "2026-01-01", status: "rejected", display_status: "rejected", matures_on: "2026-04-02"
  }));
  c.renderT1Updates();
  const panel = c.elements["t1-updates"];
  assert.equal(descendants(panel, "li").length, 20);
  assert.match(content(panel), /20\/25/);
  descendants(panel, "button")[0].onclick();
  assert.equal(descendants(panel, "li").length, 25);
  assert.equal(descendants(panel, "button").length, 0);
});

test("missing schedule and empty challenger states are explicit", () => {
  const c = ui();
  c.renderT1Updates();
  assert.match(content(c.elements["t1-updates"]), /Không có phương án mới/);
  c.state.t1_updates = null;
  c.renderT1Updates();
  assert.match(content(c.elements["t1-updates"]), /Chưa có thông tin lịch cập nhật/);
});

test("version UI separates data cutoff, parameter fit, partial fit and readiness", () => {
  const c = ui();
  c.state.versions = [{id: "V", asof: "2025-03-01", update_asof: "2025-04-02",
    t1_parameter_asof: "2024-11-10", partial_fitted_through: "2025-02-01"}];
  c.renderVersions();
  const panel = c.elements["versions-list"];
  assert.match(content(descendants(panel, "h3")[0]), /cập nhật dữ liệu đến 2025-04-02/);
  assert.match(content(panel), /Ước tính thanh toán cập nhật: 2024-11-10 · Ước tính trả từng phần: 2025-02-01 · Phiên bản sẵn sàng: 2025-03-01/);
});

test("legacy missing data cutoff remains unknown instead of borrowing ready date", () => {
  const c = ui();
  c.state.versions = [{id: "OLD", asof: "2025-03-01"}];
  c.renderVersions();
  const panel = c.elements["versions-list"];
  assert.match(content(descendants(panel, "h3")[0]), /cập nhật dữ liệu đến —/);
  assert.doesNotMatch(content(descendants(panel, "h3")[0]), /2025-03-01/);
  assert.match(content(panel), /Phiên bản sẵn sàng: 2025-03-01/);
});

test("completion messages distinguish missing history, pending outcomes and a chosen version", () => {
  const c = ui();
  const kept = c.updateDecisionMessage({status:"kept_incumbent",candidate_update_audit:{status:"insufficient_local_windows"}});
  assert.match(kept,/Cần thêm lịch sử thanh toán/);
  assert.doesNotMatch(kept,/đang chờ|Đã chọn/);
  assert.match(c.updateDecisionMessage({status:"pending_prospective_audit"}),/Đang đối chiếu với các khoản thu thực tế/);
  assert.match(c.updateDecisionMessage({status:"accepted_prospective_audit"}),/Đã chọn phiên bản mới/);
  assert.match(c.jobMessage({status:"completed",message:"Ứng viên đang chờ",decision:{status:"kept_incumbent",audit:{status:"insufficient_local_windows"}}}),/Cần thêm lịch sử thanh toán/);
});

test("versions show update dates and outcomes without raw validation metrics", () => {
  const c = ui();
  c.state.versions = [{id:"V", update_asof:"2026-11-19", asof:"2026-11-19",
    promotion_status:"accepted_historical_audit", train_n:6977, validation_n:536,
    audit:{candidate:{score:0.0907}, baseline:{score:0.1029}, n:285}}];
  c.state.active_version = "V";
  c.renderVersions();
  const text = content(c.elements["versions-list"]);
  assert.ok(text.includes("2026-11-19") && text.includes("Đã chọn phiên bản mới") && text.includes("Đang sử dụng"));
  for (const hidden of ["SAI SỐ", "SỐ MẪU", "0.0907", "0.1029", "6977", "536", "chưa kết luận"])
    assert.ok(!text.includes(hidden), hidden);
});

test("update reasons distinguish improvement, insufficient history and waiting for actual payments", () => {
  const c = ui();
  assert.match(c.updateDecisionMessage({status:"accepted_historical_audit"}), /sát thực tế hơn khi kiểm tra lịch sử/);
  assert.match(c.updateDecisionMessage({status:"accepted_prospective_audit", candidate_update_audit:{status:"insufficient_local_windows"}}), /sát các khoản thu thực tế hơn/);
  assert.match(c.updateDecisionMessage({status:"kept_incumbent", audit:{status:"scored", accepted:false}}), /Bản mới chưa cải thiện/);
  assert.match(c.updateDecisionMessage({status:"kept_incumbent", audit:{status:"insufficient_audit_outcomes"}}), /Cần thêm lịch sử thanh toán/);
  assert.match(c.updateDecisionMessage({status:"pending_prospective_audit"}), /Đang đối chiếu với các khoản thu thực tế/);
  assert.doesNotMatch(c.updateDecisionMessage({status:"kept_incumbent"}), /chưa cải thiện|sát thực tế hơn/);
});
