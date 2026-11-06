"""End-to-End benchmark evaluation tests running all 120 questions in
data/eval/contract_benchmark_questions.jsonl against data/cfo_warehouse.duckdb.
"""

from __future__ import annotations

import json
from decimal import Decimal
import pytest

from scripts.evaluate_contract_benchmark import (
    BENCHMARK_PATH,
    evaluate_benchmark_question,
)
from tests.contract_harness import EmbeddingProvider, MetricCatalog


def _load_benchmark_items() -> list[dict]:
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


BENCHMARK_ITEMS = _load_benchmark_items()


class TestBenchmarkSuiteIntegrity:
    """Verifies structure, distribution, and ground-truth coverage of the 120 benchmark questions."""

    def test_benchmark_has_120_questions_and_8_categories(self) -> None:
        assert len(BENCHMARK_ITEMS) == 120
        counts: dict[str, int] = {}
        locales: set[str] = set()
        for item in BENCHMARK_ITEMS:
            cat = item["category"]
            counts[cat] = counts.get(cat, 0) + 1
            locales.add(item["locale"])

        assert counts == {
            "1_single_multi_metric_aggregate": 20,
            "2_timeseries_and_comparison": 20,
            "3_dimensional_breakdown_filter_topk": 20,
            "4_business_views_and_ground_truth": 15,
            "5_ambiguous_needs_clarification": 15,
            "6_unsupported_out_of_catalog": 12,
            "7_no_data_and_edge_cases": 8,
            "8_authorization_and_security": 10,
        }
        assert locales == {"vi-VN", "en-US"}

    def test_ground_truth_scenarios_match_real_database_values(self) -> None:
        by_id = {item["benchmark_id"]: item for item in BENCHMARK_ITEMS}

        # A1_MARKETING_SPIKE (BM-023): Marketing expense jumps from 202,607,000 in 2026-08 to 1,391,237,000 in 2026-09
        bm023 = by_id["BM-023"]
        assert bm023["golden_rows"] == [
            {"month": "2026-08", "operating_expense": "202607000.00"},
            {"month": "2026-09", "operating_expense": "1391237000.00"},
        ]

        # A9_ELECTRICITY_HCM (BM-043): HCM electricity in Q2 2026 spikes in June 2026 to 76,445,000
        bm043 = by_id["BM-043"]
        assert bm043["golden_rows"][-1] == {"month": "2026-06", "operating_expense": "76445000.00"}

        # A7_IT_MARGIN_SQUEEZE (BM-022): IT gross margin drops from 2026-04 (15.60%) to 2026-08 (11.28%)
        bm022 = by_id["BM-022"]
        jan_margin = Decimal(bm022["golden_rows"][0]["gross_margin"])
        aug_margin = Decimal(bm022["golden_rows"][-1]["gross_margin"])
        assert jan_margin > aug_margin

        # Business views mgmt (BM-061) vs tax (BM-062) in 2026-08 differ by non-deductible expenses (incl. A6_WEEKEND_ENTRY)
        mgmt_opex = Decimal(by_id["BM-061"]["golden_rows"][0]["operating_expense"])
        tax_opex = Decimal(by_id["BM-062"]["golden_rows"][0]["operating_expense"])
        assert mgmt_opex == Decimal("3028615501.00")
        assert tax_opex == Decimal("2928697501.00")
        assert mgmt_opex > tax_opex


@pytest.mark.parametrize(
    "item",
    BENCHMARK_ITEMS,
    ids=[it["benchmark_id"] for it in BENCHMARK_ITEMS],
)
def test_all_120_benchmark_questions_end_to_end(
    item: dict,
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider,
) -> None:
    """Executes each of the 120 benchmark questions through the 25-contract pipeline and verifies output."""
    eval_out = evaluate_benchmark_question(item, catalog, embedding_provider)
    assert eval_out["passed"] is True, f"Benchmark {item['benchmark_id']} failed: {eval_out}"
    resp = eval_out["response"]
    assert resp["status"] == item["expected_final_status"]

    if resp["status"] == "ready":
        assert resp["provenance"] is not None
        assert resp["provenance"]["catalog_hash"] == catalog.get_catalog_hash()
        assert resp["provenance"]["data_watermark"] == "2026-10-14"
        assert resp["provenance"]["query_fingerprint"].startswith("sha256:")
        for expected_w in item.get("expected_warnings", []):
            assert expected_w in resp["warnings"]
