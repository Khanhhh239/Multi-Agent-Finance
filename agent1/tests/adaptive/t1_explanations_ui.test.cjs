const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../../agent1_service/ui/workspace/app.js"), "utf8");
function section(start, end) {
  return source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
}
class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text; this.children = []; this.attributes = {}; }
  append(...nodes) { nodes.forEach(n => { n.parent = this; this.children.push(n); }); }
  setAttribute(key, value) { this.attributes[key] = value; }
  after(node) { node.parent = this.parent; this.parent.children.splice(this.parent.children.indexOf(this) + 1, 0, node); }
  querySelector(selector) {
    if (selector === "thead tr") return this.children.find(n => n.tag === "thead").children[0];
    return this.children.find(n => n.tag === selector);
  }
  closest() { return {scrollTo() {}}; }
  showModal() { this.open = true; }
  close() { this.open = false; this.onclose(); }
  remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); }
}
function text(node) { return [node.textContent || "", ...node.children.map(text)].join(" "); }
function ui() {
  const scope = { node: (tag, text) => new Element(tag, text), fmt: new Intl.NumberFormat("vi-VN"),
    displayDate: value => value, labels: {}, dateColumns: new Set(), document: {body: new Element("body")} };
  vm.createContext(scope);
  vm.runInContext(section("  function table(", "  const recordFields ="), scope);
  vm.runInContext(section("  function renderPaymentExplanation(", "  function renderForecast("), scope);
  return scope;
}
function explanation() {
  return {status: "available", cutoff: "2026-11-11", model_version: "SAVED-MODEL", probability: 0.3725,
    baseline_probability: 0.3, reconstructed_probability: 0.3725, scenario_shift_weeks: 2,
    members: [{method: "lightgbm", label: "LightGBM", weight: 0.5}, {method: "customer", label: "Lịch sử khách", weight: 0.5}],
    reference: {count: 8, population: 20, max_weighted_cdf_distance: 0}, limitations: ["Không chứng minh nguyên nhân."],
    stability: {checked: true, sample_count: 3}, plausibility: {status: "no_warning", unsupported_fraction: 0},
    factors: [{feature: "amount", label: "<script>unsafe</script>", value: 100000, value_unit: "VND",
      business_review: {protocol: "t1-business-evidence-v1", status: "eligible", feature: "amount", value: 100000, value_unit: "VND"},
      contribution_pp: 7.25, direction: "increase", stability: {status: "stable", reasons: [], min_contribution_pp: 7, max_contribution_pp: 7.5}}]};
}

test("compact grouped attribution remains distinct from reviewed causal business reasons", () => {
  const scope = ui(), e = explanation();
  e.protocol = "compact-t1-grouped-exact-v1";
  e.method = "exact_grouped_interventional_shapley";
  e.model_version = "t1-compact-landmark-v1";
  e.factors = [{feature: "receipt_state", label: "Khoản đã thu và lần thu gần nhất", contribution_pp: 7.25}];
  e.stability = {checked: false, sample_count: 0};
  const content = text(scope.renderPaymentExplanation(e, {}, 0.3725));
  assert.ok(content.includes("Khoản đã thu và lần thu gần nhất"));
  assert.ok(content.includes("chưa được kiểm tra độ ổn định"));
  assert.ok(content.includes("điểm phần trăm"));
  e.factors[0].contribution_pp = 50;
  assert.ok(text(scope.renderPaymentExplanation(e, {})).includes("không khớp"));
});

test("landmark18 grouped explanations retain their schema across saved model identifiers", () => {
  const scope = ui(), e = explanation();
  Object.assign(e, {protocol: "landmark-grouped-exact-reference-v2", feature_schema: "t1-landmark-18-v2",
    model_version: "landmark:artifact-id", method: "exact_grouped_interventional_shapley"});
  e.factors = [{feature: "receipt_state", label: "Trạng thái thu tiền", contribution_pp: 7.25}];
  assert.ok(text(scope.renderPaymentExplanation(e, {}, .3725)).includes("Trạng thái thu tiền"));
  e.factors[0].contribution_pp = 9;
  assert.ok(text(scope.renderPaymentExplanation(e, {}, .3725)).includes("không khớp"));
  assert.ok(text(scope.renderPaymentExplanation({status:"deferred",reason:"Giới hạn 10 hóa đơn"}, {})).includes("Giới hạn 10 hóa đơn"));
});

test("business view contains only the final probability and reviewed drivers, with no technical section", () => {
  const scope = ui(), panel = scope.renderPaymentExplanation(explanation(), {model_version: "NEW-MODEL"}), content = text(panel);
  for (const expected of ["37,25%", "2026-11-11", "100.000 VND", "2 tuần", "Giá trị thực", "Góp phần tăng khả năng tất toán trong 4 tuần"]) {
    assert.ok(content.includes(expected), expected);
  }
  for (const hidden of ["Mức tham chiếu", "LightGBM", "SAVED-MODEL", "NEW-MODEL", "điểm %", "SHAP", "Chi tiết kỹ thuật", "kiểm tra độ ổn định"]) assert.ok(!content.includes(hidden), hidden);
  assert.ok(!panel.children.some(n => n.tag === "details"));
  assert.ok(content.includes("<script>unsafe</script>"));
  const allTags = node => [node.tag, ...node.children.flatMap(allTags)];
  assert.ok(!allTags(panel).includes("script"));
});

function comparisonExample() {
  const e = explanation(), f = e.factors[0];
  e.baseline_probability = e.probability + 0.0725;
  e.reference.hash = "REF-1";
  Object.assign(f, {feature: "term_days", label: "Kỳ hạn thanh toán", value: 45, value_unit: "ngày",
    contribution_pp: -7.25, direction: "decrease",
    stability: {status: "stable", reasons: [], min_contribution_pp: -7.5, max_contribution_pp: -7}});
  f.comparison = {protocol: "t1-fixed-input-comparison-v1", feature: "term_days", value_unit: "ngày",
    actual_value: 45, alternative_value: 30, actual_probability: e.probability, alternative_probability: 0.55,
    horizon_weeks: 4, scenario_shift_weeks: 2, other_prepared_inputs_fixed: true, source_reference_hash: "REF-1"};
  return e;
}

test("saved hypothetical contrasts are never used as business reasons; contract terms are context only", () => {
  const content = text(ui().renderPaymentExplanation(comparisonExample(), {}));
  for (const expected of ["Thông tin đầu vào", "Kỳ hạn thanh toán: 45 ngày", "Chưa đủ cơ sở"]) assert.ok(content.includes(expected), expected);
  for (const hidden of ["Đối chiếu giả định", "55%", "Góp phần giảm", "kéo giảm"]) assert.ok(!content.includes(hidden), hidden);
});

test("all old comparison variants remain hidden", () => {
  for (const change of [c => c.actual_probability = 0.1, c => c.alternative_probability = 0.2,
    c => c.alternative_probability = NaN, c => c.alternative_probability = 1.5,
    c => c.source_reference_hash = "OTHER", c => c.horizon_weeks = 1, c => c.scenario_shift_weeks = 0,
    c => c.other_prepared_inputs_fixed = false, c => c.actual_value = 60, c => c.alternative_value = 45]) {
    const e = comparisonExample(); change(e.factors[0].comparison);
    const content = text(ui().renderPaymentExplanation(e, {}));
    assert.ok(content.includes("Kỳ hạn thanh toán: 45 ngày"));
    assert.ok(!content.includes("Đối chiếu giả định"));
  }
});

test("negative historical delay is described as early payment rather than negative lateness", () => {
  const e = explanation();
  Object.assign(e.factors[0], {feature: "customer_delay_days", value: -5, value_unit: "ngày"});
  Object.assign(e.factors[0].business_review, {feature: "customer_delay_days", value: -5, value_unit: "ngày"});
  const content = text(ui().renderPaymentExplanation(e, {}));
  assert.ok(content.includes("sớm hơn hạn 5 ngày"));
  assert.ok(!content.includes("-5 ngày"));
});

test("unstable effects are removed before selecting the three main reasons", () => {
  const e = explanation();
  e.factors.push({...e.factors[0], feature: "age_days", label: "Stable factor", contribution_pp: 2,
    business_review: {...e.factors[0].business_review, feature: "age_days"},
    stability: {status: "stable", reasons: [], min_contribution_pp: 1.5, max_contribution_pp: 2.5}});
  e.baseline_probability -= 0.02;
  e.factors[0].stability = {status: "unstable", meaningful: true, min_contribution_pp: -1, max_contribution_pp: 9};
  const panel = ui().renderPaymentExplanation(e, {});
  const content = text(panel);
  assert.ok(content.includes("Stable factor"));
  assert.ok(!content.includes("unsafe") && !content.includes("Ảnh hưởng chưa ổn định"));
});

test("only the three largest eligible drivers are shown; neutral effects invent no reason", () => {
  const e = explanation();
  e.factors = [1, 5, 2, 4, 3, 0].map((effect, i) => ({...e.factors[0], label: "Feature " + i, contribution_pp: effect,
    stability: {status: "stable", reasons: [], min_contribution_pp: effect, max_contribution_pp: effect}}));
  e.baseline_probability = e.probability - 0.15;
  const panel = ui().renderPaymentExplanation(e, {}), main = panel.children.find(n => n.tag === "table");
  assert.equal(main.querySelector("tbody").children.length, 3);
  assert.ok(!text(main).includes("Feature 0"));
  e.factors.forEach(f => f.contribution_pp = 0);
  e.baseline_probability = e.probability;
  assert.ok(text(ui().renderPaymentExplanation(e, {})).includes("Chưa đủ cơ sở"));
});

test("missing checks, poor support and an unrepresentative reference suppress explanations", () => {
  for (const change of [e => delete e.stability, e => e.stability.sample_count = 1,
    e => e.plausibility.status = "caution", e => e.plausibility.unsupported_fraction = 0.2,
    e => delete e.reference.max_weighted_cdf_distance, e => e.reference.max_weighted_cdf_distance = 0.2,
    e => e.factors[0].stability.status = "insufficient"]) {
    const e = explanation(); change(e);
    const panel = ui().renderPaymentExplanation(e, {}), content = text(panel);
    assert.ok(content.includes("37,25%") && content.includes("Chưa đủ cơ sở"));
    assert.ok(!content.includes("unsafe") && !panel.children.some(n => n.tag === "table"));
  }
});

test("a stable label alone cannot justify a direction that crosses zero or an ambiguous value", () => {
  for (const change of [e => e.factors[0].stability.min_contribution_pp = -0.01,
    e => e.factors[0].stability.min_contribution_pp = 0.05,
    e => e.factors[0].direction = "decrease", e => e.factors[0].value = null,
    e => e.factors[0].stability.reasons = ["direction_changed"]]) {
    const e = explanation(); change(e);
    assert.ok(text(ui().renderPaymentExplanation(e, {})).includes("Chưa đủ cơ sở"));
  }
});

test("an explanation must reconstruct and match the probability shown on the invoice", () => {
  const e = explanation(), scope = ui();
  const panel = scope.renderPaymentExplanation(e, {}, 0.8);
  assert.ok(text(panel).includes("80%") && text(panel).includes("Chưa đủ cơ sở"));
  e.baseline_probability = 0;
  assert.ok(text(scope.renderPaymentExplanation(e, {})).includes("Chưa đủ cơ sở"));
});

test("business sentences use stored historical facts, never infer payment quality from invoice count", () => {
  const e = explanation(), f = e.factors[0];
  Object.assign(f, {feature: "customer_delay_days", label: "Lịch sử thanh toán", value: 24, value_unit: "ngày"});
  Object.assign(f.business_review, {feature: f.feature, value: 24, value_unit: "ngày", evidence: {
    protocol: "t1-business-evidence-v1", scope: "settlements_available_before_invoice_issue", asof: "2026-01-01",
    source_hash: "VERIFIED", count: 24, late_count: 20, on_time_count: 4, early_count: 0}});
  let content = text(ui().renderPaymentExplanation(e, {}));
  assert.ok(content.includes("chậm hơn hạn 24 ngày"));
  assert.ok(content.includes("Trong 24 hóa đơn của khách này"));
  assert.ok(content.includes("20 hóa đơn được trả sau hạn"));
  // A late history must not overwrite an actual positive model contribution.
  assert.ok(content.includes("Góp phần tăng") && !content.includes("Góp phần giảm"));
  f.business_review.evidence.late_count = 25;
  content = text(ui().renderPaymentExplanation(e, {}));
  assert.ok(!content.includes("được trả sau hạn"));
});

test("small effects and missing business review never become reasons, even if SHAP is stable", () => {
  for (const change of [f => delete f.business_review, f => f.business_review.value = 2,
    f => { f.contribution_pp = .8; f.stability.min_contribution_pp = .7; f.stability.max_contribution_pp = .9; }]) {
    const e = explanation(); change(e.factors[0]);
    e.baseline_probability = e.probability - e.factors[0].contribution_pp / 100;
    const panel = ui().renderPaymentExplanation(e, {});
    assert.ok(text(panel).includes("Chưa đủ cơ sở"));
    assert.ok(!panel.children.some(n => n.tag === "table"));
  }
});

test("a withheld larger driver is acknowledged instead of presenting a partial explanation as complete", () => {
  const e = explanation();
  e.factors.push({...e.factors[0], feature: "term_days", value: 45, value_unit: "ngày", contribution_pp: -20});
  e.baseline_probability += .2;
  const content = text(ui().renderPaymentExplanation(e, {}));
  assert.ok(content.includes("chỉ giải thích một phần"));
  assert.ok(content.includes("Chưa đủ cơ sở để diễn giải yếu tố có ảnh hưởng lớn nhất"));
  assert.ok(content.includes("Kỳ hạn thanh toán: 45 ngày"));
});

test("the row button opens only its saved explanation in a native dialog and cleans up after closing", () => {
  const scope = ui(), plan = {collections: [{invoice_id: "I1", payment_probability_4w: 0.3725, payment_explanation: explanation()}]};
  const table = scope.renderCollections(plan), body = table.querySelector("tbody");
  assert.equal(body.children.length, 1);
  const invoice = body.children[0], button = invoice.children.at(-1).children[0];
  assert.equal(button.tag, "button");
  assert.equal(button.attributes["aria-expanded"], "false");
  assert.equal(scope.document.body.children.length, 0);
  button.onclick();
  const detail = scope.document.body.children[0];
  assert.equal(detail.tag, "dialog");
  assert.equal(detail.open, true);
  assert.equal(button.attributes["aria-expanded"], "true");
  assert.ok(text(detail).includes("37,25%"));
  detail.children[0].onclick();
  assert.equal(detail.open, false);
  assert.equal(scope.document.body.children.length, 0);
  assert.equal(button.attributes["aria-expanded"], "false");
  button.onclick();
  assert.equal(scope.document.body.children.length, 1);
  assert.equal(detail.children.length, 3);
});

test("old plans and unsupported models do not fabricate an attribution", () => {
  const scope = ui();
  assert.ok(text(scope.renderPaymentExplanation(null, {})).includes("Tạo kế hoạch mới"));
  assert.ok(text(scope.renderPaymentExplanation({status: "unavailable", message: "Chưa hỗ trợ"}, {})).includes("Tạo kế hoạch mới"));
});

test("floating-point noise at zero is never displayed as a negative probability", () => {
  const e = explanation();
  e.probability = 0; e.reconstructed_probability = -1e-17;
  assert.ok(!text(ui().renderPaymentExplanation(e, {})).includes("-0%"));
});

function rankingExplanation() {
  const shap = explanation();
  shap.target = "triage_probability_4w"; shap.model_version = null;
  shap.probability = 0.3; shap.baseline_probability = 0.2275;
  return {protocol: "collection-ranking-v1", policy: "amount_at_risk", label: "Dư nợ × nguy cơ chưa tất toán",
    rank: 1, eligible_count: 3, score: 70000, score_unit: "VND", uses_probability: true,
    formula: "Dư nợ × (1 − xác suất tất toán 4 tuần theo lịch sử khách)",
    selection: {message: "Dùng chính sách lưu trong phiên bản."}, cutoff: "2026-11-11", displayed_model_version: "SAVED-RANK-MODEL",
    next: {invoice_id: "<script>peer</script>", score: 50000, tied: false}, tie_break: {group_size: 1, position: 1},
    probability_source: {label: "Lịch sử khách hàng tại ngày dự báo", asof: "2026-11-11", differs_from_displayed: true,
      detail: "Ước lượng riêng; không áp dụng kịch bản thu chậm."},
    triage_probability_4w: 0.3, displayed_probability_4w: 0.8, probability_explanation: shap,
    factors: [{label: "Dư nợ", value: 100000, unit: "VND", message: "Tham gia điểm."},
      {label: "Tranh chấp", value: true, unit: "boolean", message: "Không đổi điểm."},
      {label: "Lời hứa", value: "2026-11-10", unit: "date", reliability: 0.2, message: "Đã đến hạn; không đổi điểm."}],
    business_rules: ["Loại xóa nợ; tạm bỏ qua liên hệ chưa đủ 7 ngày."], limitation: "Không phải tiền tăng thêm do liên hệ."};
}

test("ranking explanation shows its score, peer comparison and distinct probability source", () => {
  const scope = ui(), panel = scope.renderRankingExplanation({ranking_explanation: rankingExplanation()}, {model_version: "NEW"});
  const content = text(panel);
  for (const expected of ["1/3", "70.000 VND", "50.000 VND", "100.000 VND", "SAVED-RANK-MODEL", "30%", "80%",
    "khác nguồn", "không áp dụng kịch bản", "Tranh chấp: Có", "Không đổi điểm", "20%", "7 ngày"]) {
    assert.ok(content.includes(expected), expected);
  }
  const details = panel.children.find(n => n.tag === "details");
  assert.ok(text(details).includes("chưa giải thích toàn bộ thứ tự ưu tiên"));
  assert.ok(text(details).includes("30%"));
  assert.ok(!text(details).includes("SHAP"));
  assert.ok(!text(details).includes("NEW") && !text(details).includes("SAVED-RANK-MODEL"));
  assert.ok(!panel.children.some(n => n.tag === "script"));
});

test("score ties and amount-only policies do not invent probability-based ordering", () => {
  const e = rankingExplanation();
  e.next.tied = true; e.next.score = e.score; e.tie_break = {group_size: 2, position: 1};
  e.policy = "amount"; e.uses_probability = false; delete e.probability_explanation;
  const content = text(ui().renderRankingExplanation({ranking_explanation: e}, {}));
  assert.ok(content.includes("Cùng điểm"));
  assert.ok(content.includes("thứ tự bản ghi"));
  assert.ok(content.includes("các xác suất không tham gia điểm"));
  assert.ok(!content.includes("vì điểm cao hơn"));
});

test("ranking has its own dialog and old forecasts remain readable", () => {
  const scope = ui(), e = rankingExplanation();
  const table = scope.renderCollections({collections: [{invoice_id: "I1", priority_score: 70000,
    collection_rank: 1, payment_probability_4w: 0.8, ranking_explanation: e}], collection_ranking: {score_unit: "VND"}});
  table.querySelector("tbody").children[0].children.at(-2).children[0].onclick();
  const dialog = scope.document.body.children[0];
  assert.equal(dialog.id, "ranking-explanation-0");
  assert.ok(text(dialog).includes("Vì sao khoản này được ưu tiên trước"));
  assert.ok(text(scope.renderRankingExplanation({}, {})).includes("Tạo kế hoạch mới"));
  assert.ok(text(scope.renderCollectionPolicy(null)).includes("chưa lưu chính sách"));
});

test("policy summary shows eligibility counts and audit status without claiming causal benefit", () => {
  const p = {label: "Dư nợ lớn trước", displayed_count: 30, eligible_count: 40, formula: "Dư nợ",
    selection: {message: "Chưa đủ lịch sử kiểm định."}, eligibility: {writeoff_excluded: 2, recent_contact_or_skip_excluded: 3}};
  const content = text(ui().renderCollectionPolicy(p));
  for (const expected of ["30/40", "Chưa đủ lịch sử", "2 khoản đã xóa nợ", "3 khoản vừa liên hệ"]) assert.ok(content.includes(expected));
});

test("large VND and fractional priority scores retain their digits in the table and explanation", () => {
  const scope = ui(), e = rankingExplanation();
  e.score = "9007199254741009"; e.next.score = "9007199254741008";
  e.factors[0].value = "9007199254741009";
  const content = text(scope.renderRankingExplanation({ranking_explanation: e}, {}));
  assert.ok(content.includes("9.007.199.254.741.009 VND"));
  assert.ok(content.includes("9.007.199.254.741.008 VND"));
  assert.ok(!content.includes("Cùng điểm"));
  assert.equal(scope.rankingNumber("4503599627370504.5", "VND"), "4.503.599.627.370.504,5 VND");
  assert.equal(scope.rankingNumber("9999999999999999.999", "VND"), "10.000.000.000.000.000 VND");
  const table = scope.renderCollections({collections: [{invoice_id: "LARGE", outstanding: "9007199254741009",
    priority_score: "9007199254741009", payment_probability_4w: 1}], collection_ranking: {score_unit: "VND"}});
  assert.ok(text(table).includes("9.007.199.254.741.009 VND"));
  const shap = explanation(); shap.factors[0].value = "9007199254741009";
  assert.ok(text(scope.renderPaymentExplanation(shap, {})).includes("9.007.199.254.741.009 VND"));
});

test("an empty contact queue distinguishes deferred debt, no debt and legacy unknown scope", () => {
  const scope = ui(), deferred = {collections: [], open_invoices: 3, outstanding: 300,
    collection_ranking: {eligibility: {recent_contact_or_skip_excluded: 3}}};
  const content = text(scope.renderCollections(deferred));
  assert.ok(content.includes("Còn 3 hóa đơn đang mở"));
  assert.ok(content.includes("3 khoản đang tạm hoãn"));
  assert.ok(!content.includes("Không có công nợ còn mở"));
  assert.ok(text(scope.renderCollections({collections: [], open_invoices: 0})).includes("Không có công nợ còn mở"));
  assert.ok(!text(scope.renderCollections({collections: []})).includes("Không có công nợ còn mở"));
  delete deferred.open_invoices;
  deferred.collection_ranking.eligibility.open_before_rules = 4;
  deferred.collection_ranking.eligibility.writeoff_excluded = 1;
  assert.ok(text(scope.renderCollections(deferred)).includes("Còn 3 hóa đơn đang mở"));
});
