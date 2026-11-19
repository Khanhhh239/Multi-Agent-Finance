"""Automated UI/UX, CSP, Multi-Turn CFO Chat & Multi-Frame FaceID Regression Suite.

Covers:
1. Strict CSP compliance: zero inline style/on* attributes or <style>/<script> inline blocks
   across portal/static/* and agent4_chat/*, plus zero runtime .style.* DOM mutations.
2. Shared design token sync check (design/sync.py --check).
3. Exact BigInt/Decimal VND formatting & negative sign preservation in agent4_chat/chat.js
   and portal/static/app.js (preventing the -666.4M loss -> +666.4M gain sign-flip bug).
4. Multi-turn session_id persistence, reset button, 1-click clarification chips, and
   accounting view / execution provenance governance badges in agent4_chat/chat.js.
5. 3-frame (~120ms) FaceID enrollment & verification sending both descriptors: [d1, d2, d3]
   and descriptor: averagedDescriptor in portal/static/app.js.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL_STATIC = ROOT / "portal" / "static"
AGENT4_CHAT = ROOT / "agent4_chat"
DESIGN = ROOT / "design"


class _StrictCSPHTMLInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inline_styles: list[tuple[int, str]] = []
        self.inline_events: list[tuple[int, str, str]] = []
        self.style_tags: list[int] = []
        self.inline_scripts: list[int] = []
        self._in_script_without_src = False
        self._script_line = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, _ = self.getpos()
        lower_tag = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if lower_tag == "style":
            self.style_tags.append(line)
        if lower_tag == "script" and "src" not in attr_map:
            self._in_script_without_src = True
            self._script_line = line
        for name, _ in attrs:
            lname = name.lower()
            if lname == "style":
                self.inline_styles.append((line, lower_tag))
            elif lname.startswith("on"):
                self.inline_events.append((line, lower_tag, lname))

    def handle_data(self, data: str) -> None:
        if self._in_script_without_src and data.strip():
            self.inline_scripts.append(self._script_line)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_script_without_src = False


class SoSonUiUxRegressionTest(unittest.TestCase):
    def test_strict_csp_html_and_js(self) -> None:
        html_files = sorted(list(PORTAL_STATIC.rglob("*.html")) + list(AGENT4_CHAT.rglob("*.html")))
        self.assertGreaterEqual(len(html_files), 3)
        for html_file in html_files:
            inspector = _StrictCSPHTMLInspector()
            inspector.feed(html_file.read_text(encoding="utf-8"))
            rel = html_file.relative_to(ROOT)
            self.assertEqual(inspector.inline_styles, [], f"Inline style=... found in {rel}")
            self.assertEqual(inspector.inline_events, [], f"Inline on*=... found in {rel}")
            self.assertEqual(inspector.style_tags, [], f"Inline <style> tag found in {rel}")
            self.assertEqual(inspector.inline_scripts, [], f"Inline <script> found in {rel}")

        js_targets = [
            PORTAL_STATIC / "app.js",
            AGENT4_CHAT / "chat.js",
            DESIGN / "platform-theme.js",
        ]
        for js_file in js_targets:
            src = js_file.read_text(encoding="utf-8")
            rel = js_file.relative_to(ROOT)
            self.assertIsNone(
                re.search(r"\.style\.(?!fillStyle|strokeStyle)[A-Za-z]+", src),
                f"Direct .style.<prop> mutation found in {rel}",
            )
            self.assertIsNone(
                re.search(r'setAttribute\(\s*["\']style["\']', src),
                f"setAttribute('style', ...) found in {rel}",
            )

    def test_design_sync_is_up_to_date(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(DESIGN / "sync.py"), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"design/sync.py --check failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("Up to date.", proc.stdout)

    def test_node_syntax_check(self) -> None:
        for js_file in (PORTAL_STATIC / "app.js", AGENT4_CHAT / "chat.js", DESIGN / "platform-theme.js"):
            proc = subprocess.run(
                ["node", "--check", str(js_file)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"node --check failed on {js_file}:\n{proc.stderr}")

    def test_agent4_chat_runtime_vnd_session_clarification_and_governance(self) -> None:
        node_harness = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const chatJs = fs.readFileSync(process.argv[1], "utf8");

class MockElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.nodeType = 1;
    this.className = "";
    this.id = "";
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.rows = 1;
    this.attributes = {};
    this.dataset = {};
    this.children = [];
    this.listeners = {};
    this._text = "";
    this.classList = {
      add: (...cls) => {
        const set = new Set(this.className.split(/\s+/).filter(Boolean));
        for (const c of cls) if (c) set.add(c);
        this.className = [...set].join(" ");
      },
      remove: (...cls) => {
        const rem = new Set(cls);
        this.className = this.className.split(/\s+/).filter((c) => c && !rem.has(c)).join(" ");
      },
      toggle: (c, force) => {
        const has = this.className.split(/\s+/).includes(c);
        const next = force === undefined ? !has : Boolean(force);
        if (next) this.classList.add(c);
        else this.classList.remove(c);
        return next;
      },
      contains: (c) => this.className.split(/\s+/).includes(c),
    };
  }
  get textContent() {
    if (this.children.length === 0) return this._text;
    return this.children.map((c) => (typeof c === "string" ? c : c.textContent)).join("");
  }
  set textContent(v) {
    this.children = [];
    this._text = String(v ?? "");
  }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
    if (k === "id") this.id = String(v);
    if (k.startsWith("data-")) {
      const camel = k.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
      this.dataset[camel] = String(v);
    }
  }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(ev, fn) { (this.listeners[ev] ||= []).push(fn); }
  dispatchEvent(ev, payload = {}) {
    for (const fn of this.listeners[ev] || []) fn({ preventDefault() {}, target: this, ...payload });
  }
  click() { this.dispatchEvent("click"); }
  focus() {}
  scrollIntoView() {}
  requestSubmit() { this.dispatchEvent("submit"); }
  append(...nodes) {
    for (const n of nodes) {
      if (n !== null && n !== undefined) this.children.push(typeof n === "object" ? n : String(n));
    }
  }
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }
  findAll(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const c of this.children) {
      if (c && typeof c === "object" && typeof c.findAll === "function") c.findAll(pred, out);
    }
    return out;
  }
}

const byId = {};
for (const [id, tag] of [
  ["suggest", "ul"], ["suggest-followup", "ul"], ["metric-count", "p"], ["metrics", "ul"],
  ["thread", "ol"], ["question", "textarea"], ["send", "button"], ["composer", "form"],
  ["session-badge", "span"], ["reset-session", "button"], ["clarification-bar", "div"],
  ["cancel-clarification", "button"]
]) {
  const node = new MockElement(tag);
  node.id = id;
  byId[id] = node;
}

const storage = new Map();
const postedBodies = [];
let nextResponses = [];

async function mockFetch(url, opts = {}) {
  if (url === "/api/agent4/metrics") {
    return {
      ok: true,
      status: 200,
      async json() {
        return [{ metric_id: "net_profit", name_vi: "Lợi nhuận sau thuế", unit: "VND", period_type: "flow" }];
      },
    };
  }
  if (url === "/api/agent4/query") {
    const body = JSON.parse(opts.body);
    postedBodies.push(body);
    const handler = nextResponses.shift();
    const reply = typeof handler === "function" ? handler(body) : handler;
    return {
      ok: reply.httpOk !== false,
      status: reply.httpStatus || 200,
      async json() { return reply.json; },
    };
  }
  throw new Error("Unexpected URL: " + url);
}

const windowObj = {
  crypto: globalThis.crypto,
  sessionStorage: {
    getItem: (k) => storage.get(k) || null,
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  },
};
const context = vm.createContext({
  window: windowObj,
  crypto: globalThis.crypto,
  sessionStorage: windowObj.sessionStorage,
  Intl,
  BigInt,
  Number,
  Math,
  String,
  Boolean,
  Array,
  Object,
  RegExp,
  Error,
  Promise,
  JSON,
  fetch: mockFetch,
  document: {
    getElementById: (id) => byId[id] || null,
    createElement: (tag) => new MockElement(tag),
  },
});

vm.runInContext(chatJs, context);
const u = windowObj.__SOSON_CHAT_UTILS__;
assert.ok(u, "Expected __SOSON_CHAT_UTILS__");

// 1. Critical Negative VND Sign-Flip Regression Checks
assert.equal(u.approxVnd("-666387909.00"), "âm 666,4 triệu đồng");
assert.equal(u.approxVnd(-666387909), "âm 666,4 triệu đồng");
assert.equal(u.approxVnd("666387909.00"), "666,4 triệu đồng");
assert.equal(u.approxVnd("-12500000000.00"), "âm 12,5 tỷ đồng");
assert.equal(u.approxVnd("-1500000000000"), "âm 1,5 nghìn tỷ đồng");
assert.equal(u.approxVnd("-0.00"), "");
assert.equal(u.formatVnd("-0.00", { withUnit: true, roundToInt: true }), "0 đồng");
assert.equal(u.approxVnd("999960000"), "1 tỷ đồng");
assert.equal(u.formatVnd("-98765432109876.00", { withUnit: true, roundToInt: true }), "-98.765.432.109.876 đồng");

const lossAnswer = u.readable("Lợi nhuận sau thuế: -666387909.00 VND (khung mgmt, 2026-07-01–2026-09-30).");
assert.match(lossAnswer, /-666\.387\.909 đồng \(khoảng âm 666,4 triệu đồng\)/);
assert.doesNotMatch(lossAnswer, /khoảng 666,4 triệu đồng/);
assert.match(lossAnswer, /Sổ quản trị \(v_mgmt\)/);
assert.match(lossAnswer, /01\/07\/2026 đến 30\/09\/2026/);

const unicodeMinus = u.readable("Dòng tiền thuần: −666387909 VND");
assert.match(unicodeMinus, /-666\.387\.909 đồng \(khoảng âm 666,4 triệu đồng\)/);

// 2. Governance View & Provenance Detection
assert.equal(u.detectAccountingView({ interpretation: { view: "mgmt" } }).label, "Sổ quản trị (v_mgmt)");
assert.equal(u.detectAccountingView({ interpretation: { view: "tax" } }).label, "Sổ thuế (v_tax)");
assert.equal(u.detectAccountingView({ interpretation: { views: ["mgmt", "tax"] } }).label, "So sánh hai sổ (v_mgmt & v_tax)");
assert.equal(u.detectProvenanceMode({ provenance: { query_fingerprint: "abcdef1234567890", source: "mgmt" } }).key, "sql");
assert.equal(u.detectProvenanceMode({ provenance: { source: "synthetic_duckdb", query_fingerprint: null } }).key, "lexical");

// 3. Multi-Turn session_id, Clarification Chips & Reset Flow
(async () => {
  await new Promise((r) => setTimeout(r, 10));
  const initialSid = byId["session-badge"].dataset.sessionId;
  assert.match(initialSid, /^[0-9a-f]{32}$/);

  // Turn 1: Ambiguous question -> clarification_needed with choices
  nextResponses.push({
    json: {
      api_version: "v1",
      status: "clarification_needed",
      answer: "Vui lòng chọn kỳ báo cáo cho Lợi nhuận sau thuế.",
      clarification: {
        session_id: "11112222333344445555666677778888",
        slot_prompts: [{
          slot: "time",
          prompt: "Chọn kỳ báo cáo:",
          choices: [
            { value: "Q3 2026", label: "Quý 3/2026" },
            { value: "2026", label: "Năm 2026" },
          ],
        }],
      },
    },
  });

  byId["question"].value = "Lợi nhuận sau thuế là bao nhiêu?";
  byId["composer"].requestSubmit();
  await new Promise((r) => setTimeout(r, 20));

  assert.equal(postedBodies.length, 1);
  assert.equal(postedBodies[0].session_id, initialSid);
  assert.equal(byId["clarification-bar"].hidden, false);

  const clarifyChips = byId["thread"].findAll((n) => n.classList && n.classList.contains("is-clarify"));
  assert.equal(clarifyChips.length, 2);
  assert.equal(clarifyChips[0].textContent, "Quý 3/2026");

  // Turn 2: Click 1st clarification chip -> sends guided session_id and renders negative KPI + governance badges
  nextResponses.push({
    json: {
      api_version: "v1",
      status: "ready",
      answer: "Lợi nhuận sau thuế: -666387909.00 VND (khung mgmt, 2026-07-01–2026-09-30).",
      data: {
        columns: [{ key: "net_profit", type: "decimal", unit: "VND" }],
        rows: [{ net_profit: "-666387909.00" }],
        row_count: 1,
        truncated: false,
      },
      interpretation: { metric_ids: ["net_profit"], dimensions: [], view: "mgmt", time: { mode: "range", start: "2026-07-01", end: "2026-09-30" } },
      provenance: { source: "mgmt", query_fingerprint: "9988776655443322", catalog_hash: "aabbccddeeff", data_watermark: "2026-09-30" },
      warnings: [],
    },
  });

  clarifyChips[0].click();
  await new Promise((r) => setTimeout(r, 20));

  assert.equal(postedBodies.length, 2);
  assert.equal(postedBodies[1].question, "Q3 2026");
  assert.equal(postedBodies[1].session_id, "11112222333344445555666677778888");
  assert.equal(byId["clarification-bar"].hidden, true);

  const negCards = byId["thread"].findAll((n) => n.classList && n.classList.contains("kpi-card") && n.classList.contains("is-negative"));
  assert.equal(negCards.length, 1);
  assert.match(negCards[0].textContent, /âm 666,4 triệu đồng/);

  const govBadges = byId["thread"].findAll((n) => n.classList && n.classList.contains("gov-badge"));
  const badgeTexts = govBadges.map((b) => b.textContent);
  assert.ok(badgeTexts.includes("Sổ quản trị (v_mgmt)"));
  assert.ok(badgeTexts.includes("SQL tất định đóng dấu"));

  // Turn 3: Follow-up question retains client session_id; then reset creates a brand-new session_id
  nextResponses.push({
    json: {
      api_version: "v1",
      status: "ready",
      answer: "Lợi nhuận sau thuế: -410000000.00 VND (khung tax, 2026-07-01–2026-09-30).",
      interpretation: { metric_ids: ["net_profit"], dimensions: [], view: "tax" },
      provenance: { source: "tax", query_fingerprint: "1234567890abcdef", catalog_hash: "aabbccddeeff" },
      warnings: [],
    },
  });
  byId["question"].value = "Còn theo sổ thuế thì sao?";
  byId["composer"].requestSubmit();
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(postedBodies[2].session_id, initialSid);

  byId["reset-session"].click();
  const nextSid = byId["session-badge"].dataset.sessionId;
  assert.notEqual(nextSid, initialSid);
  assert.match(nextSid, /^[0-9a-f]{32}$/);

  // Turn 4: Dual-book comparison with negative delta + follow_up_suggestions + fallback retry check
  nextResponses.push(
    {
      httpOk: false,
      httpStatus: 400,
      json: {
        api_version: "v1",
        status: "error",
        error: { stage: "clarification", code: "invalid_request", message: "Invalid clarification turn." },
      },
    },
    {
      json: {
        api_version: "v1",
        status: "ready",
        answer: "So sánh lợi nhuận: Sổ quản trị 400000000.00 VND, Sổ thuế 650000000.00 VND, chênh lệch -250000000.00 VND.",
        data: {
          columns: [
            { key: "mgmt_value", type: "decimal", unit: "VND" },
            { key: "tax_value", type: "decimal", unit: "VND" },
            { key: "delta", type: "decimal", unit: "VND" },
          ],
          rows: [{ mgmt_value: "400000000.00", tax_value: "650000000.00", delta: "-250000000.00" }],
          row_count: 1,
          truncated: false,
        },
        follow_up_suggestions: ["Chi tiết khoản loại trừ thuế TNDN?"],
        provenance: { source: "synthetic_duckdb", query_fingerprint: null, catalog_hash: "123456123456" },
        warnings: ["DEMO DATA — NOT REAL FINANCIAL RESULTS"],
      },
    }
  );
  byId["question"].value = "So sánh hai sổ năm 2026?";
  byId["composer"].requestSubmit();
  await new Promise((r) => setTimeout(r, 25));

  // Verify automatic retry happened (first with nextSid, second without session_id)
  assert.equal(postedBodies.length, 5);
  assert.equal(postedBodies[3].session_id, nextSid);
  assert.equal("session_id" in postedBodies[4], false);

  const allBadges = byId["thread"].findAll((n) => n.classList && n.classList.contains("gov-badge")).map((b) => b.textContent);
  assert.ok(allBadges.includes("So sánh hai sổ (v_mgmt & v_tax)"));
  assert.ok(allBadges.includes("Chế độ từ vựng dự phòng (Lexical)"));

  const deltaNegBadges = byId["thread"].findAll((n) => n.classList && n.classList.contains("delta-badge") && n.classList.contains("is-negative"));
  assert.ok(deltaNegBadges.some((b) => b.textContent.includes("Chênh lệch âm")));

  const followChips = byId["thread"].findAll((n) => n.classList && n.classList.contains("quick-chip") && !n.classList.contains("is-clarify"));
  assert.ok(followChips.some((c) => c.textContent === "Chi tiết khoản loại trừ thuế TNDN?"));

  // Zero style attributes anywhere in rendered thread
  const styledNodes = byId["thread"].findAll((n) => n.attributes && "style" in n.attributes);
  assert.equal(styledNodes.length, 0);

  console.log("AGENT4_CHAT_OK");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""
        proc = subprocess.run(
            ["node", "-e", node_harness, str(AGENT4_CHAT / "chat.js")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Agent 4 chat runtime test failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("AGENT4_CHAT_OK", proc.stdout)

    def test_portal_multiframe_faceid_and_navigation(self) -> None:
        node_harness = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const appJs = fs.readFileSync(process.argv[1], "utf8");

class MockNode {
  constructor(tag = "div") {
    this.tagName = String(tag).toUpperCase();
    this.nodeType = 1;
    this.className = "";
    this.id = "";
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.name = "";
    this.innerHTML = "";
    this.attributes = {};
    this.dataset = {};
    this.children = [];
    this.listeners = {};
    this.elements = [];
    this.tBodies = [{ replaceChildren: (...n) => {} }];
    this._text = "";
    this.readyState = 4;
    this.videoWidth = 640;
    this.videoHeight = 480;
    this.classList = {
      add: (...cls) => {
        const s = new Set(this.className.split(/\s+/).filter(Boolean));
        for (const c of cls) if (c) s.add(c);
        this.className = [...s].join(" ");
      },
      remove: (...cls) => {
        const r = new Set(cls);
        this.className = this.className.split(/\s+/).filter((c) => c && !r.has(c)).join(" ");
      },
      toggle: (c, force) => {
        const has = this.className.split(/\s+/).includes(c);
        const next = force === undefined ? !has : Boolean(force);
        if (next) this.classList.add(c);
        else this.classList.remove(c);
        return next;
      },
      contains: (c) => this.className.split(/\s+/).includes(c),
    };
  }
  get textContent() {
    if (!this.children.length) return this._text;
    return this.children.map((c) => (typeof c === "string" ? c : c.textContent)).join("");
  }
  set textContent(v) { this.children = []; this._text = String(v ?? ""); }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
    if (k.startsWith("data-")) {
      const camel = k.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
      this.dataset[camel] = String(v);
    }
  }
  getAttribute(k) { return this.attributes[k] || null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(ev, fn) { (this.listeners[ev] ||= []).push(fn); }
  removeEventListener() {}
  dispatchEvent(ev, extra = {}) {
    for (const fn of this.listeners[ev] || []) fn({ preventDefault() {}, stopPropagation() {}, target: this, ...extra });
  }
  click() { this.dispatchEvent("click"); }
  focus() {}
  play() { return Promise.resolve(); }
  getContext() {
    return {
      clearRect() {}, save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, arc() {}, fill() {},
    };
  }
  append(...nodes) {
    for (const n of nodes) if (n !== null && n !== undefined) this.children.push(typeof n === "object" ? n : String(n));
  }
  prepend(...nodes) {
    this.children.unshift(...nodes);
    for (const node of nodes) if (node && typeof node === "object") node.parentElement = this;
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  querySelector() { return new MockNode("button"); }
  querySelectorAll() { return []; }
  contains() { return false; }
  closest() { return null; }
}

const nodes = new Map();
function getNode(id) {
  if (!nodes.has(id)) {
    const n = new MockNode(id === "company-form" || id === "gate-form" ? "form" : "div");
    n.id = id;
    if (id === "company-form") {
      const fieldNames = [
        "legal_name", "code", "tax_code", "registered_address", "industry",
        "fiscal_year_end_month", "vat_method", "filing_period", "date_format", "number_format", "agent2_company"
      ];
      for (const fname of fieldNames) {
        const inp = new MockNode("input");
        inp.name = fname;
        inp.value = "";
        n.elements.push(inp);
        n.elements[fname] = inp;
      }
    }
    nodes.set(id, n);
  }
  return nodes.get(id);
}

const shellNode = new MockNode("div");
const reticleNode = new MockNode("div");
const skipLinkNode = new MockNode("a");

let clockMs = 1000;
const rafQueue = [];
const faceApiCalls = [];
let frameSeq = 0;

const d1 = Array.from({ length: 128 }, (_, i) => Number((0.1 + i * 0.001).toFixed(6)));
const d2 = Array.from({ length: 128 }, (_, i) => Number((0.2 + i * 0.001).toFixed(6)));
const d3 = Array.from({ length: 128 }, (_, i) => Number((0.3 + i * 0.001).toFixed(6)));
const sampleFrames = [d1, d1, d2, d2, d3]; // includes <120ms intermediate polls to test spacing!

const mockState = {
  company: { legal_name: "Công ty TNHH Minh Phát", code: "MP", tax_code: "0101243150", vat_method: "DEDUCTION", filing_period: "QUARTER", fiscal_year_end_month: "12" },
  agents: [
    { id: "agent1", number: 1, name: "Agent 1", state: "running", url: "http://127.0.0.1:8011/workspace", port: 8011, log: "/api/agents/agent1/log" },
    { id: "agent2", number: 2, name: "Agent 2", state: "running", url: "http://127.0.0.1:8766/", port: 8766, log: "/api/agents/agent2/log" },
    { id: "agent3", number: 3, name: "Agent 3", state: "running", url: "http://127.0.0.1:8640/", port: 8640, log: "/api/agents/agent3/log" },
    { id: "agent4", number: 4, name: "Agent 4", state: "running", url: "http://127.0.0.1:8800/agent4/", port: 8040, log: "/api/agents/agent4/log" },
  ],
  intake: { configured: true, unlocked: false, seconds_left: 0, has_biometric: false },
  package: { version: 2, sealed_at: "2026-10-14 09:30:00", files: 5, manifest: "abcdef0123456789" },
  slots: [{ agent: "agent1", key: "invoices", label: "Hóa đơn", state: "sealed" }],
  pending: [],
  batches: [],
};

async function mockFetch(path, opts = {}) {
  if (path === "/api/state") {
    return { ok: true, status: 200, async json() { return structuredClone(mockState); } };
  }
  if (path === "/api/intake/face/register" || path === "/api/intake/face/verify") {
    faceApiCalls.push({ path, body: JSON.parse(opts.body) });
    mockState.intake.has_biometric = true;
    mockState.intake.unlocked = true;
    mockState.intake.seconds_left = 1200;
    return { ok: true, status: 200, async json() { return { ok: true, token: "tok_test_123" }; } };
  }
  return { ok: true, status: 200, async json() { return {}; } };
}

const faceapiMock = {
  nets: {
    tinyFaceDetector: { loadFromUri: async () => {} },
    faceLandmark68Net: { loadFromUri: async () => {} },
    faceRecognitionNet: { loadFromUri: async () => {} },
  },
  TinyFaceDetectorOptions: function () {},
  resizeResults: () => ({
    landmarks: {
      positions: [{ x: 10, y: 10 }],
      getJawOutline: () => [],
      getLeftEyeBrow: () => [],
      getRightEyeBrow: () => [],
      getNose: () => [],
      getLeftEye: () => [],
      getRightEye: () => [],
      getMouth: () => [],
    },
  }),
  detectSingleFace: () => ({
    withFaceLandmarks: () => ({
      withFaceDescriptor: async () => {
        const desc = sampleFrames[Math.min(frameSeq, sampleFrames.length - 1)];
        frameSeq += 1;
        return { descriptor: Float32Array.from(desc), landmarks: { positions: [] } };
      },
    }),
  }),
};

const win = {
  location: { hash: "#agent4", href: "http://localhost:8800/#agent4", origin: "http://localhost:8800", hostname: "localhost" },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener() {},
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  localStorage: { getItem: () => null, setItem() {} },
};

const context = vm.createContext({
  window: win,
  location: win.location,
  sessionStorage: win.sessionStorage,
  localStorage: win.localStorage,
  navigator: {
    mediaDevices: {
      getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
    },
  },
  performance: { now: () => clockMs },
  requestAnimationFrame: (cb) => { rafQueue.push(cb); return rafQueue.length; },
  cancelAnimationFrame: () => {},
  setTimeout: (fn) => { fn(); return 1; },
  clearTimeout: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  fetch: mockFetch,
  faceapi: faceapiMock,
  URL,
  URLSearchParams,
  AbortSignal,
  FormData: function () { return { entries: () => [] }; },
  Intl,
  Date,
  Math,
  Number,
  BigInt,
  String,
  Boolean,
  Array,
  Object,
  Set,
  Map,
  RegExp,
  Error,
  Promise,
  JSON,
  structuredClone,
  document: {
    title: "",
    visibilityState: "visible",
    activeElement: null,
    body: new MockNode("body"),
    getElementById: (id) => getNode(id),
    createElement: (tag) => new MockNode(tag),
    addEventListener() {},
    querySelector: (sel) => (sel === ".shell" ? shellNode : sel === ".face-reticle" ? reticleNode : sel === ".skip-link" ? skipLinkNode : new MockNode()),
    querySelectorAll: () => [],
  },
});

vm.runInContext(appJs, context);
const utils = win.__SOSON_PORTAL_UTILS__;
assert.ok(utils, "Expected __SOSON_PORTAL_UTILS__");
assert.equal(utils.FACE_FRAME_COUNT, 3);
assert.equal(utils.FACE_FRAME_INTERVAL_MS, 120);
assert.equal(utils.approxVndPortal("-666387909"), "âm 666,4 triệu đồng");
assert.equal(utils.isValidFaceDescriptor(new Array(128).fill(NaN)), false);

const avg = utils.averageFaceDescriptors([d1, d2, d3]);
assert.equal(avg.length, 128);
assert.ok(Math.abs(avg[0] - 0.2) < 1e-6);
assert.ok(Math.abs(avg[127] - (0.2 + 127 * 0.001)) < 1e-6);

(async () => {
  await new Promise((r) => setTimeout(r, 15));

  // Check cohesive Vietnamese SME navigation & quick switcher rendered
  const navText = getNode("nav-agents").textContent;
  assert.match(navText, /Trợ lý Dòng tiền/);
  assert.match(navText, /Trợ lý Giám sát/);
  assert.match(navText, /Trợ lý Thuế/);
  assert.match(navText, /Trợ lý hỏi đáp/);
  assert.equal(getNode("agent-grid").children.length, 4);
  assert.equal(getNode("exec-agents-val").textContent, "4 / 4 phân hệ sẵn sàng");
  assert.ok(!("style" in getNode("agent-grid").attributes));

  const switchText = getNode("agent-quick-switch").textContent;
  assert.match(switchText, /A1/);
  assert.match(switchText, /A4/);

  // Test 3-frame FaceID Enrollment (~120ms spacing: 60ms ticks -> captures at t=1000, t=1120, t=1240)
  frameSeq = 0;
  getNode("gate-password").value = "AdminSecret123";
  getNode("gate-biometric-btn").click();
  await new Promise((r) => setTimeout(r, 10));

  while (rafQueue.length && faceApiCalls.length === 0) {
    const fn = rafQueue.shift();
    await fn();
    clockMs += 60; // 60ms step proves intermediate frame <120ms is skipped!
  }
  await new Promise((r) => setTimeout(r, 10));

  assert.equal(faceApiCalls.length, 1);
  assert.equal(faceApiCalls[0].path, "/api/intake/face/register");
  assert.equal(faceApiCalls[0].body.descriptors.length, 3);
  assert.equal(faceApiCalls[0].body.descriptor.length, 128);
  // Frame 1 at t=1000 (idx 0 = d1), t=1060 skipped (idx 1), Frame 2 at t=1120 (idx 2 = d2), t=1180 skipped (idx 3), Frame 3 at t=1240 (idx 4 = d3)!
  assert.ok(Math.abs(faceApiCalls[0].body.descriptors[0][0] - 0.1) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[0].body.descriptors[1][0] - 0.2) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[0].body.descriptors[2][0] - 0.3) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[0].body.descriptor[0] - 0.2) < 1e-5);

  // Test 3-frame FaceID Verification (including a dropped frame resetting consecutive count!)
  const verifySequence = [d1, null, d1, d2, d3];
  let verifyIdx = 0;
  faceapiMock.detectSingleFace = () => ({
    withFaceLandmarks: () => ({
      withFaceDescriptor: async () => {
        const desc = verifySequence[Math.min(verifyIdx, verifySequence.length - 1)];
        verifyIdx += 1;
        return desc ? { descriptor: Float32Array.from(desc), landmarks: { positions: [] } } : null;
      },
    }),
  });
  rafQueue.length = 0;
  mockState.intake.unlocked = false;
  mockState.intake.has_biometric = true;
  getNode("gate-biometric-btn").click();
  await new Promise((r) => setTimeout(r, 10));

  while (rafQueue.length && faceApiCalls.length === 1) {
    const fn = rafQueue.shift();
    await fn();
    clockMs += 130;
  }
  await new Promise((r) => setTimeout(r, 10));

  assert.equal(faceApiCalls.length, 2);
  assert.equal(faceApiCalls[1].path, "/api/intake/face/verify");
  assert.equal(faceApiCalls[1].body.descriptors.length, 3);
  assert.equal(faceApiCalls[1].body.descriptor.length, 128);
  assert.ok(Math.abs(faceApiCalls[1].body.descriptors[0][0] - 0.1) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[1].body.descriptors[1][0] - 0.2) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[1].body.descriptors[2][0] - 0.3) < 1e-5);
  assert.ok(Math.abs(faceApiCalls[1].body.descriptor[0] - 0.2) < 1e-5);
  assert.ok(!("style" in getNode("face-progress-bar").attributes));

  console.log("PORTAL_UI_FACEID_OK");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""
        proc = subprocess.run(
            ["node", "-e", node_harness, str(PORTAL_STATIC / "app.js")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Portal UI / FaceID runtime test failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("PORTAL_UI_FACEID_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
