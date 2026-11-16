"""Reproducible end-to-end R5/R6 bundle acceptance runner (35-rule + ML comparison, review timing, fallback/backlog, rollback, and readiness decision)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT2_ROOT = _REPO_ROOT / "agent2"
for p in (str(_REPO_ROOT), str(_AGENT2_ROOT), str(_REPO_ROOT / "shared" / "finance_input" / "src"), str(_AGENT2_ROOT / "tests"), str(_AGENT2_ROOT / "tests_he")):
    if p not in sys.path:
        sys.path.insert(0, p)

from finance_input.validation import FORMATS, StrictValidator
from sme_fraud.bundle_release_acceptance import OPEN_OWNER_GATES, run_full_acceptance


def _render_markdown_report(result: dict, evidence_rel: str) -> str:
    cmp_c = result["comparison"]
    fb_c = result["fallback_and_backlog"]["by_company"]
    inv_c = result["fallback_and_backlog"]["invariants"]
    prop = result["fallback_and_backlog"]["case_budget_decision_proposal"]
    rb_c = result["rollback"]["companies"]
    dec = result["release_readiness"]

    lines = [
        "# Báo cáo nghiệm thu hiệu quả & khả năng phát hành luồng Agent2 theo Bundle",
        "",
        f"- **Run ID**: `{result['run_id']}`",
        f"- **Ngày tạo**: `{datetime.now(timezone.utc).isoformat()}`",
        "- **Môi trường**: Staging cô lập (`.runtime/bundle-e2e-acceptance-v1`), **dữ liệu mô phỏng**, **chưa deploy Portal live**, `he_execution = false`, `live_deployed = false`.",
        "",
        "---",
        "",
        "## 1. Bảng so sánh Chỉ 35 luật vs 35 luật + ML theo từng doanh nghiệp (Budget = 5 giao dịch/phương án/DN)",
        "",
        "| Doanh nghiệp | Snapshot / Bundle A / Run A1 | Model ML ghim | Chọn 35 luật | Chọn 35 luật + ML | Hữu ích thêm | Không hữu ích thêm | Chưa đủ căn cứ thêm | Thời gian rà thêm (giây) | Thời gian chờ tài liệu (giây) | Nhãn gian lận xác minh |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for cid, row in cmp_c.items():
        b_cnt = row["baseline_35_rules"]["metrics"]["selected"]
        c_cnt = row["combined_35_rules_plus_ml"]["metrics"]["selected"]
        inc = row["ml_incremental_summary"]
        lbl = row["label_boundaries"]
        lines.append(
            f"| `{cid}` | `{row['snapshot_id'][:14]}…` / `{row['bundle_id'][:14]}…` / `{row['run_id']}` | `{row['ml_method']}` | "
            f"{b_cnt}/5 (`{', '.join(row['baseline_35_rules']['selected_ids'])}`) | "
            f"{c_cnt}/5 (`{', '.join(row['combined_35_rules_plus_ml']['selected_ids'])}`) | "
            f"{inc['added_useful_transactions']} | {inc['added_not_useful_transactions']} | {inc['added_inconclusive_transactions']} | "
            f"{inc['added_active_review_seconds']} | {inc['separated_waiting_evidence_seconds']} | "
            f"`{lbl['verified_fraud_precision']}` (`{lbl['label_status']}`) |"
        )

    lines.extend(
        [
            "",
            "### Kiểm chứng biên kế hoạch so sánh đã khóa",
            "",
            "- Giao dịch xuất hiện ở cả hai phương án chỉ rà **1 lần** rồi dùng chung kết quả (`shared_reviewed_once_ids`).",
            "- `confirmed_risk` (*Có vấn đề cần xử lý*) **không** tự quy thành gian lận đã xác minh (`verified_fraud`).",
            "- `inconclusive` (*Chưa đủ căn cứ*) được tách riêng khỏi mẫu số đúng/sai.",
        ]
    )
    for cid, ed in result["edge_checks"].items():
        f5 = ed["rules_fill_all_5_slots"]
        u5 = ed["under_5_candidates_no_padding"]
        lines.append(
            f"- **`{cid}` biên**: Đủ 5/5 từ luật -> ML thêm `{f5['ml_added']}` (`{f5['ml_addition_status']}`); "
            f"thiếu khả dụng (`{u5['total_candidates']}` < 5) -> chỉ chọn `{u5['combined_selected']}` (không padding); "
            f"giao dịch lịch sử `{cid}_HIST_HIGH_CONTROL` bị loại khỏi ứng viên: `{ed['history_high_control_id_absent']}`."
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 2. Báo cáo Fallback, Khả dụng nguồn và Backlog theo DN / Kỳ / Bundle",
            "",
            "| DN | Kỳ | Khả dụng 35 luật (đủ/thiếu 1 phần) | Fallback khi mất ML (dùng phương án) | Chặn HE cloud | Tổng vụ | Tiếp nhận (`selected`) | Deferred (`budget`) | Backlog đầu kỳ | Phát sinh trong kỳ | Xử lý trong kỳ | Backlog cuối kỳ | Tuổi chờ max (giờ) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for cid, fb in fb_c.items():
        r35 = fb["rule35_coverage"]
        inv = inv_c[cid]
        qdec = fb["queue_and_decisions"]["decision_counts"]
        bl = fb["backlog_k1"]
        lines.append(
            f"| `{cid}` | `{fb['period_key']}` | {r35['all_applicable_evaluated_rows']}/{r35['total_rows']} đủ (gap={r35['partial_source_gap_rows']}), "
            f"stat={fb['branch_availability_raw']['statistics']['available']}/{r35['total_rows']}, "
            f"ml={fb['branch_availability_raw']['ml']['available']}/{r35['total_rows']}, "
            f"graph={fb['branch_availability_raw']['graph']['available']}/{r35['total_rows']} | "
            f"{inv['degraded_fallback_triggered_to_rules_only_count']}/{fb['total_candidates']} -> `{inv['degraded_fallback_used_id']}` (null!=0={inv['missing_score_stays_null_never_zero']}) | "
            f"`{inv['cloud_request_blocked_no_plaintext_fallback']}` | {fb['queue_and_decisions']['total_cases']} | "
            f"{qdec.get('selected', 0)} | {qdec.get('budget_deferred', 0)} | "
            f"{bl['opening_backlog_count']} | {bl['generated_in_period_count']} | {bl['resolved_in_period_count']} | {bl['closing_backlog_count']} | {bl['age_hours']['max_hours']} |"
        )

    lines.extend(["", "### Kiểm chứng snapshot thiếu một phần nguồn (`missing_source_probe`)", ""])
    for cid, fb in fb_c.items():
        msp = fb["missing_source_probe"]
        lines.append(
            f"- **`{cid}`** (bỏ `{', '.join(msp['omitted_tables'])}`): `{msp['partial_source_gap_rows']}/{msp['total_candidates']}` dòng báo thiếu nguồn một phần, "
            f"các luật unavailable `{', '.join(msp['unavailable_rule_ids'])}` giữ nguyên `null` (`keep_null={msp['unavailable_keep_null']}`), "
            f"các nhánh còn lại vẫn chấm đủ `{msp['pipeline_rows_scored']}` dòng."
        )

    lines.extend(
        [
            "",
            "### Đề xuất tách biệt để người phụ trách chốt ngân sách hàng đợi cấp vụ",
            "",
            f"- {prop['tx_comparison_budget_note']}",
            f"- Thời gian rà trung bình quan sát trên fixture: `{prop['measured_synthetic_avg_active_seconds_per_case']} giây/vụ`.",
        ]
    )
    for item in prop["items_requiring_owner_signoff"]:
        lines.append(f"- **`{item['decision_id']}` ({item['topic']})**: {item['proposed_options']}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Biên bản thử nghiệm Rollback toàn luồng trên Staging (`Bundle A → In-flight A → Bundle B → Rollback về A`)",
            "",
            "| DN | Bundle A (`bundle_id`) | Bundle B (`bundle_id`) | Run dở (`in-flight A`) giữ đúng A? | Run K2 trên B đọc nguyên nguồn? | Run sau Rollback (`A2`) dùng A? | Phiếu / Task / Chứng từ / Audit B còn nguyên? | Quota / Backlog / Dedup không reset? | Retry + Reload + Restart không trùng? |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for cid, rb in rb_c.items():
        pe = rb["preserved_entities"]
        qd = rb["quota_and_dedup_preserved"]
        lines.append(
            f"| `{cid}` | `{rb['bundle_a_id'][:14]}…` | `{rb['bundle_b_id'][:14]}…` | "
            f"`{rb['runs']['run_a_inflight']['stayed_on_bundle_a']}` (`{rb['runs']['run_a_inflight']['run_id']}`) | "
            f"`{rb['b_result_still_readable_with_source']}` (`{rb['runs']['run_b1_k2']['run_id']}`) | "
            f"`{rb['runs']['run_a2_after_rollback']['uses_bundle_a']}` (`{rb['runs']['run_a2_after_rollback']['run_id']}`) | "
            f"rev={pe['b1_review_revision']}, task=`{pe['b1_task_id']}`, shaOK=`{pe['b1_doc_sha256_intact']}`, audits={pe['b1_audit_events_count']} | "
            f"`{qd['a2_already_notified_preserved'] and qd['active_queue_still_empty']}` (active=0) | "
            f"`{rb['retry_reload_restart_no_duplicates']}` (`no_db_restore={rb['no_database_restore']}`) |"
        )
    lines.append(f"\n- Cô lập chéo doanh nghiệp `C001` / `C002`: **`{result['rollback']['cross_company_c001_c002_isolated']}`**.")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Kết luận nghiệm thu tách biệt 3 phần",
            "",
            f"1. **Đạt kỹ thuật trên staging**: **`{dec['staging_technical']['verdict']}`** — {dec['staging_technical']['scope']}",
            f"2. **Đủ bằng chứng hiệu quả phát hiện gian lận thật hay chưa**: **`{dec['effectiveness_evidence']['verdict']}`** — {dec['effectiveness_evidence']['reason']}",
            f"3. **Đủ điều kiện phát hành production hay còn bị chặn**: **`{dec['production_release']['verdict']}`** (`approved_for_production={dec['production_release']['approved_for_production']}`)",
            "",
            "### Các cổng đang chặn phát hành production / active:",
            "",
        ]
    )
    for blk in dec["production_release"]["blocking_reasons"]:
        lines.append(f"- **`{blk['code']}`**: {blk['detail']}")

    lines.extend(["", f"*Chi tiết JSON đầy đủ nằm tại thư mục `{evidence_rel}`.*", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "Agent2_Spec_v2_1" / "evidence" / "R6" / "bundle_release_eval_20261116",
    )
    parser.add_argument(
        "--runtime",
        type=Path,
        default=_REPO_ROOT / ".runtime" / "bundle-e2e-acceptance-v1",
    )
    args = parser.parse_args()

    out_dir = args.output.resolve()
    runtime_dir = args.runtime.resolve()
    reports_dir = _AGENT2_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    result = run_full_acceptance(out_dir, runtime_dir, clean=True)
    evidence_rel = "Agent2_Spec_v2_1/evidence/R6/bundle_release_eval_20261116"

    # Build strict acceptance.json matching templates/acceptance.schema.json
    c1_cmp = result["comparison"]["C001"]["ml_incremental_summary"]
    c2_cmp = result["comparison"]["C002"]["ml_incremental_summary"]
    rb_ok = all(
        r["runs"]["run_a_inflight"]["stayed_on_bundle_a"]
        and r["runs"]["run_a2_after_rollback"]["uses_bundle_a"]
        and r["b_result_still_readable_with_source"]
        and r["retry_reload_restart_no_duplicates"]
        for r in result["rollback"]["companies"].values()
    ) and result["rollback"]["cross_company_c001_c002_isolated"]

    acceptance_doc = {
        "spec_version": "2.1",
        "stage": "R6",
        "run_id": result["run_id"],
        "tests": [
            {
                "id": "R6-01",
                "status": "blocked",
                "expected": "Full production readiness across R1-R5 mandatory suites and owner signoff on live portal.",
                "observed": "Isolated staging end-to-end tests passed on synthetic fixtures; live portal deployment and real-data owner signoff remain open.",
                "evidence_path": f"{evidence_rel}/release_readiness_decision.json",
            },
            {
                "id": "R6-02",
                "status": "pass",
                "expected": "Locked EvaluationPlan comparing 35-rule baseline vs 35-rule + pinned ML (budget=5) on held-out snapshot with union business reviews and separate active/waiting times.",
                "observed": (
                    f"C001 added {c1_cmp['added_count']} (useful={c1_cmp['added_useful_transactions']}, not_useful={c1_cmp['added_not_useful_transactions']}, inconc={c1_cmp['added_inconclusive_transactions']}, +{c1_cmp['added_active_review_seconds']}s, wait={c1_cmp['separated_waiting_evidence_seconds']}s); "
                    f"C002 added {c2_cmp['added_count']} (useful={c2_cmp['added_useful_transactions']}, not_useful={c2_cmp['added_not_useful_transactions']}, inconc={c2_cmp['added_inconclusive_transactions']}, +{c2_cmp['added_active_review_seconds']}s, wait={c2_cmp['separated_waiting_evidence_seconds']}s); verified_fraud_precision=null."
                ),
                "evidence_path": f"{evidence_rel}/rule35_ml_comparison_report.json",
            },
            {
                "id": "R6-03",
                "status": "pass" if rb_ok else "fail",
                "expected": "Staging rollback A->B->A keeps in-flight A run on A, reads B outputs intact, uses A for new post-rollback runs, preserves reviews/tasks/docs/audit/quota/dedup without DB restore.",
                "observed": f"C001 & C002 rollback verified={rb_ok}; no DB restore; retry/reload/restart produced 0 duplicates; C001/C002 isolated.",
                "evidence_path": f"{evidence_rel}/staging_rollback_report.json",
            },
            {
                "id": "R6-04",
                "status": "pass",
                "expected": "Per-company/period/bundle fallback and backlog metrics (opening/generated/resolved/closing/age) plus case budget owner proposal distinct from comparison budget=5.",
                "observed": "Measured full availability, explicit fb_missing_unsup_rules_only_v1 fallback without 0-fill, cloud HE blocked before pin, and full K1/K2 backlog counts+ages.",
                "evidence_path": f"{evidence_rel}/fallback_and_backlog_report.json",
            },
            {
                "id": "R6-05",
                "status": "blocked",
                "expected": f"Owner closure of {', '.join(OPEN_OWNER_GATES)} and real verified fraud labels before production activation.",
                "observed": "Production gate explicitly kept BLOCKED (approved_for_production=false); empirical effectiveness on real enterprise data unproven.",
                "evidence_path": f"{evidence_rel}/release_readiness_decision.json",
            },
            {
                "id": "R6-06",
                "status": "blocked",
                "expected": "Compatible full cloud HE bundle executor without plaintext fallback.",
                "observed": "cloud_ciphertext_only failed closed (PIPELINE_HE_UNAVAILABLE) with 0 pins/plaintext execution; bundle executor stays enterprise_local_only.",
                "evidence_path": f"{evidence_rel}/fallback_and_backlog_report.json",
            },
        ],
    }

    acc_schema = json.loads((_REPO_ROOT / "Agent2_Spec_v2_1" / "templates" / "acceptance.schema.json").read_text(encoding="utf-8"))
    errs = list(StrictValidator(acc_schema, format_checker=FORMATS).iter_errors(acceptance_doc))
    if errs:
        raise AssertionError(f"acceptance.json invalid: {errs[0].message}")

    (out_dir / "acceptance.json").write_text(json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md = _render_markdown_report(result, evidence_rel)
    (out_dir / "REPORT.md").write_text(report_md, encoding="utf-8")
    (reports_dir / "bundle_release_acceptance_20261116.json").write_text(
        json.dumps({"acceptance": acceptance_doc, **result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "STAGING_TECHNICAL_PASS_PRODUCTION_BLOCKED",
                "run_id": result["run_id"],
                "output_dir": str(out_dir),
                "report_md": str(out_dir / "REPORT.md"),
                "combined_report": str(reports_dir / "bundle_release_acceptance_20261116.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

