"""Regression & 7,700-row benchmark tests for fast import, EntityGraph, Vietnamese normalization, and 26 canonical fraud rules."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest

from difflib import SequenceMatcher
import jsonschema

from finance_input import AccessScope
from sme_fraud.auth import FileAuthorizer
from sme_fraud.benford import monthly_diagnostics, vn_posting_context, vn_timestamp
from sme_fraud.entity_graph import EntityGraph
from sme_fraud.identity import normalize, normalize_mst, normalize_vn_phone_digits
from sme_fraud.identity_graph import KnownGraph
from sme_fraud.import_files import canonical, parse_file
from sme_fraud.method_adapters import METHODS, score_snapshot
from sme_fraud.noise_policy import name_key, outside_schedule
from sme_fraud.p1_inputs import export_manifest
from sme_fraud.review_server import make_server
from sme_fraud.rule_evaluation import (
    EXTENDED_SCHEMA_RULES,
    SUPPORTED,
    _evaluate,
    canonical_rule_summary,
)
from sme_fraud.rule_sources import _resolve
from sme_fraud.rules import RULE_NAMES
from sme_fraud.snapshot_analysis import (
    MAX_SOURCE_RECORDS,
    MAX_TRANSACTIONS,
    _fast_score_snapshot,
    analyze_snapshot,
)
from sme_fraud.snapshot_features import build_feature_rows
from sme_fraud.snapshots import SnapshotStore

# Preload scientific stack once so benchmark measures steady-state server execution
import sme_fraud.method_adapters as _preload_adapters  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
RULE_RESULTS_SCHEMA = json.loads((ROOT / "sme_fraud/rule_results.schema.json").read_text("utf-8"))
ANALYSIS_SCHEMA = json.loads((ROOT / "sme_fraud/snapshot_analysis.schema.json").read_text("utf-8"))


def _rec_base(tid, cid, rid, ts, rev=1, obs=None):
    return dict(
        tenant_id=tid,
        company_id=cid,
        record_id=rid,
        revision=rev,
        effective_at=ts,
        observed_at=obs or ts,
        source=dict(system="misa_sme", record_id=rid, is_simulated=False),
    )


def _commit_request(preview_report):
    req = {k: preview_report[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
    req.update(expected_revision=preview_report["revision"], acknowledge=True)
    return req


def build_benchmark_bundle(n_tx=7700, tenant_id="T_BENCH", company_id="C_BENCH"):
    vendors = [
        dict(
            **_rec_base(tenant_id, company_id, f"V{i:03d}", "2026-01-01T08:00:00+07:00"),
            name=f"Công ty TNHH Cơ Khí Minh Phát {i}",
            tax_id=f"0101234{i:03d}",
            bank_account=f"1900100{i:04d}",
            bank_code="VCB",
            phone=f"0243825{i:04d}",
            address=f"{i} Nguyễn Trãi, Thanh Xuân, Hà Nội",
            related_party_disclosed_at="2026-01-01T08:00:00+07:00",
        )
        for i in range(1, 26)
    ]
    employees = [
        dict(
            **_rec_base(tenant_id, company_id, f"E{i:03d}", "2026-01-01T08:00:00+07:00"),
            name=f"Nguyễn Văn Nhân Viên {i}",
            role="accountant" if i <= 3 else "approver",
            bank_account=f"8800200{i:04d}",
            bank_code="TCB",
        )
        for i in range(1, 7)
    ]
    transactions, invoices, allocations, approvals = [], [], [], []
    for idx in range(1, n_tx + 1):
        vid = f"V{(idx % 25) + 1:03d}"
        v_bank = f"1900100{(idx % 25) + 1:04d}"
        day = ((idx - 1) // 50) + 1
        month = ((day - 1) // 28) + 1
        dom = ((day - 1) % 28) + 1
        slot = (idx - 1) % 50
        hr = 8 + (slot // 6)
        mn = (slot % 6) * 10 + (idx % 7)
        ts = f"2026-{month:02d}-{dom:02d}T{hr:02d}:{mn:02d}:00+07:00"
        amt = 1_250_000 + ((idx * 137) % 18_000) * 1_000
        tid, iid, aid, apid = f"TX{idx:05d}", f"INV{idx:05d}", f"AL{idx:05d}", f"AP{idx:05d}"
        invoices.append(
            dict(
                **_rec_base(tenant_id, company_id, iid, ts),
                kind="invoice",
                number=f"HD26-{idx:05d}",
                vendor_ref=dict(record_id=vid, revision=1),
                amount_vnd=amt,
                currency="VND",
            )
        )
        transactions.append(
            dict(
                **_rec_base(tenant_id, company_id, tid, ts),
                kind="payment",
                amount_vnd=amt,
                currency="VND",
                payment_channel="bank",
                vendor_ref=dict(record_id=vid, revision=1),
                created_by_ref=dict(record_id="E001", revision=1),
                bank_account=v_bank,
                bank_code="VCB",
                description=f"Thanh toán hóa đơn mua vật tư {iid}",
                accounting_lines=[
                    dict(account="331", debit_vnd=amt, credit_vnd=0),
                    dict(account="1121", debit_vnd=0, credit_vnd=amt),
                ],
            )
        )
        allocations.append(
            dict(
                **_rec_base(tenant_id, company_id, aid, ts),
                kind="allocation",
                transaction_ref=dict(record_id=tid, revision=1),
                invoice_ref=dict(record_id=iid, revision=1),
                amount_vnd=amt,
                currency="VND",
            )
        )
        approvals.append(
            dict(
                **_rec_base(tenant_id, company_id, apid, ts),
                transaction_ref=dict(record_id=tid, revision=1),
                employee_ref=dict(record_id="E004", revision=1),
                decision="approved",
                limit_vnd=50_000_000,
            )
        )

    bundle = dict(
        contract_version="1.2.0",
        tenant_id=tenant_id,
        companies=[
            dict(
                **_rec_base(tenant_id, company_id, company_id, "2026-01-01T08:00:00+07:00"),
                name="Công ty TNHH Sản Xuất Cơ Khí Bench",
                tax_id="0109998887",
            )
        ],
        vendors=vendors,
        employees=employees,
        invoices=invoices,
        transactions=transactions,
        payment_allocations=allocations,
        approvals=approvals,
        supporting_documents=[],
        vendor_bank_history=[],
        payment_history_coverage=[],
    )
    claim = dict(
        **_rec_base(tenant_id, company_id, "COV_ALL", "2026-06-30T23:59:59+07:00"),
        export_id="EXPORT_BENCH_7700",
        coverage_status="complete",
        history_basis="since_inception",
        covered_from="2026-01-01T00:00:00+07:00",
        covered_through="2026-06-30T23:59:59+07:00",
        invoice_refs=[dict(record_id=r["record_id"], revision=1) for r in invoices],
        manifest=dict(invoice_refs=[], transaction_refs=[], allocation_refs=[], record_counts={}, records_sha256=""),
    )
    claim["manifest"] = export_manifest(bundle, claim)
    bundle["payment_history_coverage"] = [claim]
    return bundle


class FastImportAndBenchmarkTests(unittest.TestCase):
    def test_snapshot_analysis_limits_raised_for_full_sme_ledgers(self):
        self.assertGreaterEqual(MAX_TRANSACTIONS, 25_000)
        self.assertGreaterEqual(MAX_SOURCE_RECORDS, 100_000)

    def test_7700_transactions_end_to_end_upload_preview_commit_analyze_under_10s(self):
        bundle = build_benchmark_bundle(7700)
        raw_bytes = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
        scope = AccessScope(
            "T_BENCH",
            frozenset({"C_BENCH"}),
            "bench-reviewer",
            frozenset({"data.import", "evidence.verify", "analysis.read", "analysis.technical"}),
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "snapshots.sqlite3")
            t0 = time.perf_counter()
            draft = store.upload(scope, raw_bytes, "ledger_7700.json", "upload-bench-7700")
            prev = store.preview(scope, draft["import_id"], draft["revision"])
            self.assertEqual(prev["status"], "accepted_with_warnings")
            self.assertEqual(prev["errors"], [])

            committed = store.commit(scope, draft["import_id"], _commit_request(prev), "commit-bench-7700")
            snap_id = committed["snapshot"]["snapshot_id"]
            analysis = analyze_snapshot(store, scope, snap_id, "2026-07-01T00:00:00+07:00", technical=False)
            elapsed = time.perf_counter() - t0

            self.assertEqual(analysis["row_count"], 7700)
            self.assertEqual(len(analysis["rows"]), 7700)
            self.assertLess(elapsed, 10.0, f"Expected 7,700-row end-to-end < 10.0s, got {elapsed:.3f}s")

    def test_7700_row_csv_tabular_import_fast(self):
        lines = [
            "table,contract_version,tenant_id,company_id,record_id,revision,effective_at,observed_at,source.system,source.record_id,source.is_simulated,name,amount_vnd,currency,kind,description",
            "metadata,1.0.0,T_CSV,,,,,,,,,,,,,",
            "companies,,T_CSV,C_CSV,C_CSV,1,2026-01-01 08:00:00,2026-01-01 08:00:00,csv_sys,C_CSV,false,Công ty CSV,,,,",
        ]
        for i in range(1, 7701):
            day = ((i - 1) // 60) + 1
            m = ((day - 1) // 28) + 1
            d = ((day - 1) % 28) + 1
            lines.append(
                f"transactions,,T_CSV,C_CSV,TX{i:05d},1,2026-{m:02d}-{d:02d} 09:15:00,2026-{m:02d}-{d:02d} 09:15:00,csv_sys,TX{i:05d},false,,{1500000 + i * 1000},VND,payment,Chi phí {i}"
            )
        raw_csv = ("\n".join(lines) + "\n").encode("utf-8")
        scope = AccessScope("T_CSV", frozenset({"C_CSV"}), "csv-actor", frozenset({"data.import"}))
        t0 = time.perf_counter()
        parsed, report = parse_file(raw_csv, {}, scope, "ledger_7700.csv")
        elapsed = time.perf_counter() - t0
        self.assertIsNotNone(parsed)
        self.assertNotEqual(report["status"], "rejected")
        self.assertEqual(report["counts"]["transactions"], 7700)
        self.assertLess(elapsed, 5.0, f"Expected 7,700-row CSV parse+validate < 5.0s, got {elapsed:.3f}s")

    def test_fast_scorer_matches_standard_scorer_parity(self):
        bundle = build_benchmark_bundle(70, tenant_id="T_PAR", company_id="C_PAR")
        raw_bytes = canonical(bundle)
        scope = AccessScope("T_PAR", frozenset({"C_PAR"}), "par-actor", frozenset({"data.import"}))
        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "par.sqlite3")
            draft = store.upload(scope, raw_bytes, "par.json", "upload-par-0001")
            prev = store.preview(scope, draft["import_id"], draft["revision"])
            com = store.commit(scope, draft["import_id"], _commit_request(prev), "commit-par-0001")
            snap_id = com["snapshot"]["snapshot_id"]
            manifest = store.get_snapshot(scope, snap_id)
            as_of = "2026-07-01T00:00:00+07:00"

            std = score_snapshot(store, scope, snap_id, as_of, methods=METHODS, artifacts={})
            fast = _fast_score_snapshot(bundle, manifest, scope, as_of, methods=METHODS, artifacts={})
            self.assertEqual(fast["feature_contract_fingerprint"], std["feature_contract_fingerprint"])
            self.assertEqual(fast["row_count"], std["row_count"])
            for f_row, s_row in zip(fast["rows"], std["rows"]):
                self.assertEqual(f_row["record_id"], s_row["record_id"])
                f_rules = {r["rule_id"]: (r["status"], r["matched"], r["score"]) for r in f_row["methods"]["rules"]["details"]["rule_results"]["rules"]}
                s_rules = {r["rule_id"]: (r["status"], r["matched"], r["score"]) for r in s_row["methods"]["rules"]["details"]["rule_results"]["rules"]}
                self.assertEqual(f_rules, s_rules)


class CanonicalRuleEvaluatorsTests(unittest.TestCase):
    def setUp(self):
        self.tid = "T_RULE"
        self.cid = "C_RULE"
        self.scope = AccessScope(self.tid, frozenset({self.cid}), "auditor", frozenset({"data.import", "evidence.verify"}))

    def _eval_tx(self, bundle, tx_id, as_of="2026-12-31T23:59:59+07:00"):
        frame = build_feature_rows(bundle, self.scope, as_of)
        private, public = _resolve(bundle, frame, self.scope)
        meta = next(r for r in frame["rows"] if r["record_id"] == tx_id)
        key = (tx_id, meta["revision"])
        res = _evaluate(private[key], public[key], self.scope, meta)
        jsonschema.validate(res, RULE_RESULTS_SCHEMA)
        self.assertEqual({r["rule_id"] for r in res["rules"]}, set(RULE_NAMES))
        return {r["rule_id"]: r for r in res["rules"]}

    def _minimal_bundle(self):
        return dict(
            contract_version="1.2.0",
            tenant_id=self.tid,
            companies=[dict(**_rec_base(self.tid, self.cid, self.cid, "2025-01-01T08:00:00+07:00"), name="Công ty Kiểm Toán", tax_id="0101234567")],
            vendors=[
                dict(
                    **_rec_base(self.tid, self.cid, "V001", "2025-01-01T08:00:00+07:00"),
                    name="Công ty TNHH Thiết Bị Công Nghiệp An Bình",
                    tax_id="0102345678",
                    bank_account="1900888801",
                    bank_code="VCB",
                    phone="0901234567",
                    address="12 Lê Lợi, Quận 1, TP.HCM",
                    related_party_disclosed_at=None,
                )
            ],
            employees=[
                dict(**_rec_base(self.tid, self.cid, "E001", "2025-01-01T08:00:00+07:00"), name="Lê Kế Toán", bank_account="7700111101", bank_code="TCB"),
                dict(**_rec_base(self.tid, self.cid, "E002", "2025-01-01T08:00:00+07:00"), name="Trần Giám Đốc", bank_account="7700111102", bank_code="TCB"),
            ],
            invoices=[],
            transactions=[],
            payment_allocations=[],
            approvals=[],
            supporting_documents=[],
            vendor_bank_history=[],
            payment_history_coverage=[],
        )

    def test_active_canonical_rule_catalog_count_is_26_of_35(self):
        summary = canonical_rule_summary()
        self.assertEqual(summary["total_rules"], 35)
        self.assertEqual(summary["active_canonical_count"], 26)
        self.assertEqual(summary["requires_extended_schema_count"], 9)
        self.assertEqual(len(SUPPORTED), 26)
        self.assertEqual(set(SUPPORTED) | set(EXTENDED_SCHEMA_RULES), set(RULE_NAMES))

    def test_extended_schema_rules_transparently_marked(self):
        b = self._minimal_bundle()
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T1", "2026-03-10T10:00:00+07:00"),
                kind="payment", amount_vnd=5_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), created_by_ref=dict(record_id="E001", revision=1),
                description="Mua vật tư",
            )
        )
        rules = self._eval_tx(b, "T1")
        for code in ("D2", "D3", "D6", "F2", "F4", "T1", "T2"):
            self.assertEqual(rules[code]["status"], "unavailable")
            self.assertEqual(rules[code]["reason"]["code"], "requires_extended_schema")
            self.assertTrue(rules[code]["details"]["requires_extended_schema"])

    def test_a1_a2_split_threshold_vs_legitimate_30_70_milestone_exemption(self):
        # 1) Fraudulent threshold-splitting across two separate unlinked payments near 20M VND
        b_split = self._minimal_bundle()
        for rid, ts, amt in (("T1", "2026-03-10T09:00:00+07:00", 9_800_000), ("T2", "2026-03-11T09:00:00+07:00", 9_800_000), ("T3", "2026-03-15T09:00:00+07:00", 8_000_000)):
            b_split["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, rid, ts),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), created_by_ref=dict(record_id="E001", revision=1),
                    bank_account="1900888801", bank_code="VCB", description="Thanh toán tách nhỏ",
                )
            )
        r_t2 = self._eval_tx(b_split, "T2")
        self.assertEqual(r_t2["A1"]["status"], "evaluated_hit")
        r_t3 = self._eval_tx(b_split, "T3")
        self.assertEqual(r_t3["A2"]["status"], "evaluated_hit")

        # 2) Legitimate 30% deposit + 70% settlement referencing the SAME valid 18M VND invoice -> EXEMPT!
        b_legit = self._minimal_bundle()
        b_legit["invoices"].append(
            dict(
                **_rec_base(self.tid, self.cid, "INV_M1", "2026-03-01T08:00:00+07:00"),
                kind="invoice", number="HD-MILESTONE-01", vendor_ref=dict(record_id="V001", revision=1),
                amount_vnd=18_000_000, currency="VND",
            )
        )
        for idx, (rid, ts, amt) in enumerate((("TM1", "2026-03-10T09:00:00+07:00", 5_400_000), ("TM2", "2026-03-11T14:00:00+07:00", 12_600_000)), 1):
            b_legit["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, rid, ts),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), created_by_ref=dict(record_id="E001", revision=1),
                    bank_account="1900888801", bank_code="VCB", description=f"Đợt {idx} hợp đồng INV_M1",
                )
            )
            b_legit["payment_allocations"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"ALM{idx}", ts),
                    kind="allocation", transaction_ref=dict(record_id=rid, revision=1),
                    invoice_ref=dict(record_id="INV_M1", revision=1), amount_vnd=amt, currency="VND",
                )
            )
        r_legit = self._eval_tx(b_legit, "TM2")
        self.assertEqual(r_legit["A1"]["status"], "evaluated_no_hit")
        self.assertTrue(r_legit["A1"]["details"]["exempt_documented_installment"])

    def test_a3_linked_vendor_cluster_and_a4_near_limit_chain(self):
        b = self._minimal_bundle()
        # V002 shares phone with V001 -> linked cluster!
        v2 = copy.deepcopy(b["vendors"][0])
        v2.update(record_id="V002", name="Công ty TNHH Thương Mại Phú Quý", tax_id="0108765432", bank_account="1900999902")
        v2["source"]["record_id"] = "V002"
        b["vendors"].append(v2)
        for rid, vid, ts, amt in (
            ("TA1", "V001", "2026-04-02T09:00:00+07:00", 17_000_000),
            ("TA2", "V002", "2026-04-04T09:00:00+07:00", 18_000_000),
            ("TA3", "V001", "2026-04-15T09:00:00+07:00", 19_000_000),
        ):
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, rid, ts),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id=vid, revision=1), created_by_ref=dict(record_id="E001", revision=1),
                    description="Chi mua hàng",
                )
            )
        r_ta2 = self._eval_tx(b, "TA2")
        self.assertEqual(r_ta2["A3"]["status"], "evaluated_hit")
        r_ta3 = self._eval_tx(b, "TA3")
        self.assertEqual(r_ta3["A4"]["status"], "evaluated_hit")

    def test_a5_million_round_vs_normal_thousand_vnd_and_retainer_exemption_and_a6(self):
        b = self._minimal_bundle()
        base_amts = [1_235_000, 1_480_000, 1_615_000, 1_390_000, 1_520_000, 1_745_000]
        for idx, amt in enumerate(base_amts, 1):
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"TH{idx}", f"2026-02-{idx:02d}T10:00:00+07:00"),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), description="Mua văn phòng phẩm",
                )
            )
        # Normal 1,000 VND multiple (99%+ of legitimate VND invoices!) -> NO HIT
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T_NORM_K", "2026-02-15T10:00:00+07:00"),
                kind="payment", amount_vnd=9_875_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), description="Mua phụ tùng lẻ",
            )
        )
        # Exact 20,000,000 VND round spike on non-retainer -> HIT
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T_ROUND_M", "2026-02-16T10:00:00+07:00"),
                kind="payment", amount_vnd=20_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), description="Chi phí tiếp khách đột xuất",
            )
        )
        # Exact 20,000,000 VND monthly office rent retainer -> EXEMPT NO HIT + A6 over-invoice test
        b["invoices"].append(
            dict(
                **_rec_base(self.tid, self.cid, "INV_A6", "2026-02-17T09:00:00+07:00"),
                kind="invoice", number="HD-A6-01", vendor_ref=dict(record_id="V001", revision=1),
                amount_vnd=18_450_000, currency="VND",
            )
        )
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T_RENT", "2026-02-17T10:00:00+07:00"),
                kind="payment", amount_vnd=20_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), description="Thanh toán tiền thuê văn phòng tháng 02",
            )
        )
        b["payment_allocations"].append(
            dict(
                **_rec_base(self.tid, self.cid, "AL_A6", "2026-02-17T10:00:00+07:00"),
                kind="allocation", transaction_ref=dict(record_id="T_RENT", revision=1),
                invoice_ref=dict(record_id="INV_A6", revision=1), amount_vnd=18_450_000, currency="VND",
            )
        )
        self.assertEqual(self._eval_tx(b, "T_NORM_K")["A5"]["status"], "evaluated_no_hit")
        self.assertEqual(self._eval_tx(b, "T_ROUND_M")["A5"]["status"], "evaluated_hit")
        r_rent = self._eval_tx(b, "T_RENT")
        self.assertEqual(r_rent["A5"]["status"], "evaluated_no_hit")
        self.assertEqual(r_rent["A6"]["status"], "evaluated_hit")

    def test_b1_employee_bank_match_vs_tk141_advance_reimbursement_exemption_and_b2_double_pay(self):
        b = self._minimal_bundle()
        # Vendor shares bank account with E001
        b["vendors"][0]["bank_account"] = "7700111101"
        b["vendors"][0]["bank_code"] = "TCB"
        # 1) Normal vendor payment to employee's bank -> B1 HIT
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TB1_HIT", "2026-03-05T10:00:00+07:00"),
                kind="payment", amount_vnd=6_500_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), bank_account="7700111101", bank_code="TCB",
                description="Thanh toán dịch vụ tư vấn",
            )
        )
        # 2) Employee advance settlement on TK 141 -> B1 EXEMPT (evaluated_no_hit)!
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TB1_141", "2026-03-06T10:00:00+07:00"),
                kind="payment", amount_vnd=3_200_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), bank_account="7700111101", bank_code="TCB",
                description="Hoàn tạm ứng công tác phí",
                accounting_lines=[
                    dict(account="642", debit_vnd=3_200_000, credit_vnd=0),
                    dict(account="141", debit_vnd=0, credit_vnd=3_200_000),
                ],
            )
        )
        # 3) Identical (vendor, amount, VN-date) across two distinct payment IDs -> B2 HIT!
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TB2_DUP", "2026-03-05T15:30:00+07:00"),
                kind="payment", amount_vnd=6_500_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), bank_account="7700111101", bank_code="TCB",
                description="Thanh toán trùng lần 2",
            )
        )
        self.assertEqual(self._eval_tx(b, "TB1_HIT")["B1"]["status"], "evaluated_hit")
        r_141 = self._eval_tx(b, "TB1_141")
        self.assertEqual(r_141["B1"]["status"], "evaluated_no_hit")
        self.assertTrue(r_141["B1"]["details"]["exempt_advance_reimbursement_141"])
        self.assertEqual(self._eval_tx(b, "TB2_DUP")["B2"]["status"], "evaluated_hit")

    def test_b3_new_vendor_b4_missing_kyc_b6_spike_b7_unverified_bank_change(self):
        b = self._minimal_bundle()
        # V_SHELL: newly onboarded, missing both tax_id & bank_account
        b["vendors"].append(
            dict(
                **_rec_base(self.tid, self.cid, "V_SHELL", "2026-05-01T08:00:00+07:00"),
                name="Hộ Kinh Doanh Vật Liệu Tạm",
                tax_id=None,
                bank_account=None,
            )
        )
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T_SHELL", "2026-05-05T10:00:00+07:00"),
                kind="payment", amount_vnd=25_000_000, currency="VND", payment_channel="cash",
                vendor_ref=dict(record_id="V_SHELL", revision=1), description="Chi mua vật liệu không MST",
            )
        )
        r_shell = self._eval_tx(b, "T_SHELL")
        self.assertEqual(r_shell["B3"]["status"], "evaluated_hit")
        self.assertEqual(r_shell["B4"]["status"], "evaluated_hit")
        self.assertEqual(r_shell["P2"]["status"], "evaluated_hit")

        # B6 velocity spike + B7 recent unverified bank change on V001
        for i in range(1, 4):
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"TV{i}", f"2026-01-0{i}T10:00:00+07:00"),
                    kind="payment", amount_vnd=2_000_000, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), description="Mua định kỳ",
                )
            )
        b["vendor_bank_history"].append(
            dict(
                **_rec_base(self.tid, self.cid, "BH1", "2026-05-10T09:00:00+07:00"),
                vendor_ref=dict(record_id="V001", revision=1),
                bank_account="9999888877", bank_code="ACB", verification_status="unverified",
            )
        )
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TV_SPIKE", "2026-05-12T10:00:00+07:00"),
                kind="payment", amount_vnd=30_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), bank_account="9999888877", bank_code="ACB",
                description="Thanh toán đột biến sau đổi TK",
            )
        )
        r_spike = self._eval_tx(b, "TV_SPIKE")
        self.assertEqual(r_spike["B6"]["status"], "evaluated_hit")
        self.assertEqual(r_spike["B7"]["status"], "evaluated_hit")

    def test_c1_off_hours_vn_tz_c2_sod_c3_rubber_stamp_vs_midnight_date_only_guard(self):
        b = self._minimal_bundle()
        # 1) UTC 16:30Z == 23:30+07:00 VN late-night + self-approval above limit + 20s rubber-stamp >=50M!
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TC_HIT", "2026-04-08T16:30:00Z"),
                kind="payment", amount_vnd=60_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), created_by_ref=dict(record_id="E001", revision=1),
                description="Chi khẩn ban đêm tự duyệt",
            )
        )
        b["approvals"].append(
            dict(
                **_rec_base(self.tid, self.cid, "AP_HIT", "2026-04-08T16:29:40Z"),
                transaction_ref=dict(record_id="TC_HIT", revision=1),
                employee_ref=dict(record_id="E001", revision=1),
                decision="approved", limit_vnd=20_000_000,
            )
        )
        r_hit = self._eval_tx(b, "TC_HIT")
        self.assertEqual(r_hit["C1"]["status"], "evaluated_hit")
        self.assertEqual(r_hit["C2"]["status"], "evaluated_hit")
        self.assertEqual(r_hit["C3"]["status"], "evaluated_hit")

        # 2) Date-only CSV midnight 00:00:00+07:00 on both created & approved + distinct approver E002 -> NO FALSE POSITIVES!
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "TC_MID", "2026-04-09T00:00:00+07:00"),
                kind="payment", amount_vnd=65_000_000, currency="VND", payment_channel="bank",
                vendor_ref=dict(record_id="V001", revision=1), created_by_ref=dict(record_id="E001", revision=1),
                description="Nhập từ CSV chỉ có cột ngày",
            )
        )
        b["approvals"].append(
            dict(
                **_rec_base(self.tid, self.cid, "AP_MID", "2026-04-09T00:00:00+07:00"),
                transaction_ref=dict(record_id="TC_MID", revision=1),
                employee_ref=dict(record_id="E002", revision=1),
                decision="approved", limit_vnd=100_000_000,
            )
        )
        r_mid = self._eval_tx(b, "TC_MID")
        self.assertEqual(r_mid["C1"]["status"], "evaluated_no_hit")
        self.assertEqual(r_mid["C2"]["status"], "evaluated_no_hit")
        self.assertEqual(r_mid["C3"]["status"], "evaluated_no_hit")
        self.assertTrue(r_mid["C3"]["details"]["midnight_date_only_skipped"])

    def test_e2_terminated_payroll_f1_imbalance_f3_duplicate_inv_p2_decree_181_5m_cutoff(self):
        b = self._minimal_bundle()
        b["employees"][0]["terminated_at"] = "2026-03-31T17:00:00+07:00"
        b["transactions"].append(
            dict(
                **_rec_base(self.tid, self.cid, "T_PAY_GHOST", "2026-04-25T10:00:00+07:00"),
                kind="payroll", amount_vnd=15_000_000, currency="VND",
                employee_ref=dict(record_id="E001", revision=1), description="Chi lương tháng 4",
                accounting_lines=[
                    dict(account="334", debit_vnd=15_000_000, credit_vnd=0),
                    dict(account="1121", debit_vnd=0, credit_vnd=14_500_000),  # 500k imbalance!
                ],
            )
        )
        r_pay = self._eval_tx(b, "T_PAY_GHOST")
        self.assertEqual(r_pay["E2"]["status"], "evaluated_hit")
        self.assertEqual(r_pay["F1"]["status"], "evaluated_hit")

        # F3 duplicate invoice number across distinct invoice IDs + P2 6M cash pre- vs post-2025-07-01
        b["invoices"].extend([
            dict(**_rec_base(self.tid, self.cid, "I_DUP1", "2025-06-10T09:00:00+07:00"), kind="invoice", number="000999", vendor_ref=dict(record_id="V001", revision=1), amount_vnd=6_000_000, currency="VND"),
            dict(**_rec_base(self.tid, self.cid, "I_DUP2", "2025-08-10T09:00:00+07:00"), kind="invoice", number="000999", vendor_ref=dict(record_id="V001", revision=1), amount_vnd=6_000_000, currency="VND"),
        ])
        b["transactions"].extend([
            dict(**_rec_base(self.tid, self.cid, "TP_PRE", "2025-06-10T10:00:00+07:00"), kind="payment", amount_vnd=6_000_000, currency="VND", payment_channel="cash", vendor_ref=dict(record_id="V001", revision=1), description="Chi tiền mặt trước 01/07/2025"),
            dict(**_rec_base(self.tid, self.cid, "TP_POST", "2025-08-10T10:00:00+07:00"), kind="payment", amount_vnd=6_000_000, currency="VND", payment_channel="cash", vendor_ref=dict(record_id="V001", revision=1), description="Chi tiền mặt sau 01/07/2025"),
        ])
        b["payment_allocations"].extend([
            dict(**_rec_base(self.tid, self.cid, "AL_P1", "2025-06-10T10:00:00+07:00"), kind="allocation", transaction_ref=dict(record_id="TP_PRE", revision=1), invoice_ref=dict(record_id="I_DUP1", revision=1), amount_vnd=6_000_000, currency="VND"),
            dict(**_rec_base(self.tid, self.cid, "AL_P2", "2025-08-10T10:00:00+07:00"), kind="allocation", transaction_ref=dict(record_id="TP_POST", revision=1), invoice_ref=dict(record_id="I_DUP2", revision=1), amount_vnd=6_000_000, currency="VND"),
        ])
        claim = dict(
            **_rec_base(self.tid, self.cid, "COV_F3", "2025-08-15T00:00:00+07:00"),
            export_id="EXP_F3", coverage_status="complete", history_basis="since_inception",
            covered_from="2025-01-01T00:00:00+07:00", covered_through="2025-08-15T00:00:00+07:00",
            invoice_refs=[dict(record_id="I_DUP1", revision=1), dict(record_id="I_DUP2", revision=1)],
            manifest=dict(invoice_refs=[], transaction_refs=[], allocation_refs=[], record_counts={}, records_sha256=""),
        )
        claim["manifest"] = export_manifest(b, claim)
        b["payment_history_coverage"] = [claim]

        r_pre = self._eval_tx(b, "TP_PRE")
        self.assertEqual(r_pre["P2"]["status"], "evaluated_no_hit")  # 6M < 20M pre-2025-07-01
        r_post = self._eval_tx(b, "TP_POST")
        self.assertEqual(r_post["P2"]["status"], "evaluated_hit")   # 6M >= 5M post-2025-07-01 (ND 181/2025)
        self.assertEqual(r_post["F3"]["status"], "evaluated_hit")   # I_DUP1 & I_DUP2 share (V001, 000999)

    def test_d1_d4_d5_benford_and_million_suffix_surge(self):
        b = self._minimal_bundle()
        # Add low positive disbursements (~500k..950k) so max/min > 200 for Benford D1 dispersion gate
        for i in range(1, 15):
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"TD_SMALL_{i}", f"2026-02-{i:02d}T09:00:00+07:00"),
                    kind="payment", amount_vnd=450_000 + i * 37_000, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), description="Chi phí nhỏ",
                )
            )
        # Older window (60..95 days before 2026-06-15): 54 diverse natural amounts >= 1M
        for i in range(1, 55):
            amt = (1_000 + i * 613) * 1_000
            if (amt // 1000) % 1000 in (0, 500, 990, 999):
                amt += 123_000
            day = ((i - 1) % 28) + 1
            m = 3 if i <= 28 else 4
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"TD_OLD_{i}", f"2026-{m:02d}-{day:02d}T10:00:00+07:00"),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), description="Chi phí tự nhiên",
                )
            )
        # Include 2 990k-suffix rows in baseline so baseline_rate > 0 (~0.037)
        b["transactions"][15]["amount_vnd"] = 2_990_000
        b["transactions"][16]["amount_vnd"] = 3_990_000
        # Recent 30-day window: 60 distinct leading-9 + 990k-suffix amounts!
        for i in range(1, 61):
            day = ((i - 1) % 15) + 1
            amt = 90_990_000 + i * 1_000_000  # distinct, leading digit 9, (amt//1000)%1000 == 990!
            b["transactions"].append(
                dict(
                    **_rec_base(self.tid, self.cid, f"TD_REC_{i}", f"2026-06-{day:02d}T11:{i%60:02d}:00+07:00"),
                    kind="payment", amount_vnd=amt, currency="VND", payment_channel="bank",
                    vendor_ref=dict(record_id="V001", revision=1), description="Chi phí nhân tạo đầu 9",
                )
            )
        r_d = self._eval_tx(b, "TD_REC_60")
        self.assertEqual(r_d["D1"]["status"], "evaluated_hit")
        self.assertEqual(r_d["D4"]["status"], "evaluated_hit")
        self.assertEqual(r_d["D5"]["status"], "evaluated_hit")


class GraphIdentityNoiseTimezoneWorkspaceTests(unittest.TestCase):
    def test_missing_contacts_filtered_and_shared_vendor_phone_detected_in_entity_graph(self):
        tables = {
            "vendors": [
                dict(company_id="C1", vendor_id="V1", name="NCC 1", recorded_at="2026-01-01T00:00:00+07:00",
                     address="N/A", phone="Chưa có", tax_code="Không có", bank_account="NULL", bank_code="VCB"),
                dict(company_id="C1", vendor_id="V2", name="NCC 2", recorded_at="2026-01-01T00:00:00+07:00",
                     address="N/A", phone="Chưa có", tax_code="UNKNOWN", bank_account="N/A", bank_code="VCB"),
                dict(company_id="C1", vendor_id="V3", name="NCC 3", recorded_at="2026-01-01T00:00:00+07:00",
                     address="10 Trần Hưng Đạo", phone="024 3825 9999", tax_code="0101112223", bank_account="111", bank_code="VCB"),
                dict(company_id="C1", vendor_id="V4", name="NCC 4", recorded_at="2026-01-01T00:00:00+07:00",
                     address="99 Lê Duẩn", phone="+84 24 3825 9999", tax_code="079095001234", bank_account="222", bank_code="VCB"),
            ],
            "employees": [],
        }
        eg = EntityGraph(tables, "C1", "2026-02-01T00:00:00+07:00")
        findings = eg.findings()
        # V1 & V2 have only placeholder contacts -> MUST NOT collide; V3 & V4 share 11-digit Hanoi landline -> vendors_shared_phone!
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "vendors_shared_phone")
        self.assertEqual(set(findings[0]["entity_nodes"]), {eg.actor("vendor", "V3"), eg.actor("vendor", "V4")})
        # V4's 12-digit CCCD MST (079095001234) is accepted without a tax_code gap!
        v4_gaps = [g for g in eg.gaps if g["entity_id"] == "V4"]
        self.assertEqual(v4_gaps, [])

        kg = KnownGraph()
        kg.apply_master(dict(company_id="C1", recorded_at="2026-01-01T00:00:00+07:00", bank_account="Chưa có", bank_code="VCB", phone="N/A"), "vend:V1", role="vendor")
        kg.apply_master(dict(company_id="C1", recorded_at="2026-01-01T00:00:00+07:00", bank_account="NULL", bank_code="VCB", phone="N/A"), "vend:V2", role="vendor")
        kg.apply_master(dict(company_id="C1", recorded_at="2026-01-01T00:00:00+07:00", bank_account="N/A", bank_code="VCB", phone="Không có"), "emp:E1", role="employee")
        # vend:V1 component contains ONLY itself (0 employees, 1 vendor), NOT merged with V2 or E1!
        self.assertEqual(kg.counts("C1", "vend:V1"), (0, 1))

    def test_11_digit_vn_landline_and_12_digit_cccd_mst_normalization(self):
        # 11-digit Hanoi (024) and HCMC (028) landlines across domestic & international prefixes
        self.assertEqual(normalize("024 3825 1234", "phone"), "02438251234")
        self.assertEqual(normalize("+84 24 3825 1234", "phone"), "02438251234")
        self.assertEqual(normalize("0084-24-3825-1234", "phone"), "02438251234")
        self.assertEqual(normalize("+84 (0)28 3910 5678", "phone"), "02839105678")
        self.assertEqual(normalize_vn_phone_digits("84901234567"), "0901234567")

        # 10-digit enterprise, 12-digit CCCD personal tax ID (TT 86/2024), 13-digit branch MST
        self.assertEqual(normalize("0101234567", "tax_id"), "0101234567")
        self.assertEqual(normalize("079095001234", "tax_id"), "079095001234")
        self.assertEqual(normalize("0101234567-001", "tax_id"), "0101234567001")
        self.assertEqual(normalize("N/A", "tax_id"), "")
        self.assertEqual(normalize_mst("12345"), "")

    def test_vietnamese_co_khi_preserved_and_corporate_boilerplate_normalized(self):
        # "CƠ KHÍ", "CƠ ĐIỆN", "CƠ SỞ" must NOT have "CƠ" deleted by \bCO\b!
        self.assertIn("COKHI", name_key("Công ty TNHH Cơ Khí Chính Xác Bình Dương")[0])
        self.assertIn("CODIEN", name_key("CTY CP Cơ Điện Lạnh Việt Nam")[0])
        self.assertIn("COSO", name_key("Cơ Sở Sản Xuất Thành Đạt")[0])
        # Trailing English Co., Ltd is still stripped cleanly
        self.assertEqual(name_key("Mekong Precision Co., Ltd.")[0], "MEKONGPRECISION")

        # Distinct companies sharing long Vietnamese boilerplate must NOT exceed 0.85 similarity
        k_phat = name_key("Công ty TNHH Thương mại Dịch vụ Xây dựng Minh Phát")[0]
        k_tam = name_key("Công ty TNHH Thương mại Dịch vụ Xây dựng Minh Tâm")[0]
        sim_distinct = SequenceMatcher(None, k_phat, k_tam).ratio()
        self.assertLessEqual(sim_distinct, 0.85, f"Distinct vendors collided: {k_phat} vs {k_tam} ({sim_distinct})")

        # Abbreviated vs full boilerplate of the SAME company matches cleanly
        k_abbrev = name_key("CTY TNHH TM DV XD Minh Phát")[0]
        self.assertEqual(k_abbrev, k_phat)

    def test_benford_and_schedule_convert_utc_to_vietnam_utc_plus_7(self):
        # 2026-07-31T19:30:00Z is 2026-08-01T02:30:00+07:00 in Vietnam!
        vn_dt = vn_timestamp("2026-07-31T19:30:00Z")
        self.assertEqual((vn_dt.year, vn_dt.month, vn_dt.day, vn_dt.hour), (2026, 8, 1, 2))
        ctx = vn_posting_context("2026-07-31T19:30:00Z")
        self.assertTrue(ctx["is_off_hours"])
        comp = dict(company_id="C1", saturday_operations=0)
        emp = dict(employee_id="E1")
        staff = {"E1": dict(company_id="C1", employee_id="E1", role="accountant", recorded_at="2026-01-01T00:00:00Z")}
        self.assertTrue(outside_schedule("2026-07-31T19:30:00Z", "create", comp, emp, [], staff, set())[0])
        # 2026-07-31T03:00:00Z is 10:00+07:00 Friday in Vietnam -> normal business hours!
        self.assertFalse(outside_schedule("2026-07-31T03:00:00Z", "create", comp, emp, [], staff, set())[0])

        # Monthly diagnostics must bucket 2026-07-31T19:30:00Z into August VN (cutoff 2026-09-01+07:00), NOT July UTC!
        tables = {
            "transactions": [
                dict(
                    company_id="C1", transaction_id="TX_AUG_VN", txn_type="vendor_payment",
                    is_financial_entry=1, payment_channel="bank", creator_id="E1",
                    amount_vnd=5_000_000, posted_at="2026-07-31T19:30:00Z",
                    observed_at="2026-07-31T19:30:00Z", created_at="2026-07-31T19:30:00Z",
                )
            ]
        }
        diag = monthly_diagnostics(tables)
        self.assertEqual({d["cutoff_at"] for d in diag}, {"2026-09-01T00:00:00+07:00"})

    def test_review_server_auto_initializes_default_workspace_without_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            token = secrets.token_urlsafe(32)
            policy = dict(
                policy_version="1.0.0",
                principals=[
                    dict(
                        actor_id="fresh-reviewer",
                        tenant_id="demo",
                        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                        status="active",
                        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        memberships=[
                            dict(
                                company_id="C001",
                                role="accountant",
                                status="active",
                                permissions=["data.import", "evidence.verify"],
                            )
                        ],
                    )
                ],
            )
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            # Pass neither snapshots nor he_backend -> must auto-initialize instead of 503 WORKSPACE_NOT_CONFIGURED!
            server = make_server(0, FileAuthorizer(policy_path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
                try:
                    conn.request(
                        "GET",
                        "/api/v1/companies/C001/workspace",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    resp = conn.getresponse()
                    body = json.loads(resp.read())
                finally:
                    conn.close()
                self.assertEqual(resp.status, 200, f"Unexpected non-200 workspace response: {body}")
                self.assertEqual(body["version"], "agent2-workspace/1.0.0")
                self.assertEqual(body["company_id"], "C001")
                self.assertIn("datasets", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)


if __name__ == "__main__":
    unittest.main()
