"""Tests for Contracts 14 and 15 of contracts.md:
- metric.selection.llm.v1
- metric.validation.v1
"""

from __future__ import annotations

import pytest

from tests.contract_harness import (
    ContractError,
    MetricCatalog,
    build_auth_context,
    validate_llm_selection_draft,
    validate_metrics,
)


class TestLLMMetricSelectionContract:
    """Contract 14: metric.selection.llm.v1."""

    def test_llm_selection_valid_statuses(self) -> None:
        resolved = validate_llm_selection_draft(
            {
                "status": "resolved",
                "metric_ids": ["net_profit_margin"],
                "clarification_question": None,
                "unsupported_reason": None,
            }
        )
        assert resolved["status"] == "resolved"
        assert resolved["metric_ids"] == ["net_profit_margin"]

        ambiguous = validate_llm_selection_draft(
            {
                "status": "ambiguous",
                "metric_ids": [],
                "clarification_question": "Bạn muốn xem lợi nhuận gộp hay lợi nhuận ròng?",
                "unsupported_reason": None,
            }
        )
        assert ambiguous["status"] == "ambiguous"

    def test_llm_selection_rejects_sql_or_table_names(self) -> None:
        with pytest.raises(ContractError) as exc_info:
            validate_llm_selection_draft(
                {
                    "status": "resolved",
                    "metric_ids": ["SELECT SUM(credit_amount) FROM v_mgmt"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                }
            )
        assert exc_info.value.code == "invalid_request"


class TestMetricsValidationContract:
    """Contract 15: metric.validation.v1 (Ultimate authority for metrics)."""

    def test_metrics_validation_happy_path(self, catalog: MetricCatalog, analyst_auth: dict) -> None:
        retrieval_result = {
            "status": "candidates_found",
            "candidates": [
                {"metric_id": "net_profit_margin", "rank": 1},
                {"metric_id": "gross_margin", "rank": 2},
            ],
        }
        llm_sel = {
            "status": "resolved",
            "metric_ids": ["net_profit_margin"],
            "clarification_question": None,
            "unsupported_reason": None,
        }
        validated = validate_metrics(llm_sel, retrieval_result, catalog, analyst_auth)
        assert validated["status"] == "validated"
        assert validated["metric_ids"] == ["net_profit_margin"]
        assert validated["catalog_hash"] == catalog.get_catalog_hash()
        assert "month" in validated["validated_capabilities"]["net_profit_margin"]["supported_dimensions"]

    def test_subset_invariant_rejects_metric_outside_candidates(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        # 'net_revenue' exists in catalog, but was NOT in retrieved candidate set
        retrieval_result = {
            "status": "candidates_found",
            "candidates": [{"metric_id": "net_profit_margin", "rank": 1}],
        }
        llm_sel = {
            "status": "resolved",
            "metric_ids": ["net_revenue"],
            "clarification_question": None,
            "unsupported_reason": None,
        }
        with pytest.raises(ContractError) as exc_info:
            validate_metrics(llm_sel, retrieval_result, catalog, analyst_auth)
        assert exc_info.value.code == "metric_outside_candidates"
        assert exc_info.value.final_status == "unsupported"

    def test_unknown_and_unapproved_and_unverified_metrics(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        # 1. Unknown metric invented by LLM
        with pytest.raises(ContractError) as e_unknown:
            validate_metrics(
                {
                    "status": "resolved",
                    "metric_ids": ["ebitda_custom_invented"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                },
                {"status": "candidates_found", "candidates": [{"metric_id": "ebitda_custom_invented", "rank": 1}]},
                catalog,
                analyst_auth,
            )
        assert e_unknown.value.code == "unknown_metric"

        # 2. Unapproved (draft) metric in catalog
        with pytest.raises(ContractError) as e_unapproved:
            validate_metrics(
                {
                    "status": "resolved",
                    "metric_ids": ["experimental_cash_burn"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                },
                {"status": "candidates_found", "candidates": [{"metric_id": "experimental_cash_burn", "rank": 1}]},
                catalog,
                analyst_auth,
            )
        assert e_unapproved.value.code == "unsupported_metric"

        # 3. Unverified custom handler metric
        with pytest.raises(ContractError) as e_unverified:
            validate_metrics(
                {
                    "status": "resolved",
                    "metric_ids": ["unverified_custom_kpi"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                },
                {"status": "candidates_found", "candidates": [{"metric_id": "unverified_custom_kpi", "rank": 1}]},
                catalog,
                analyst_auth,
            )
        assert e_unverified.value.code == "unsupported_data_source"

    def test_authorization_and_view_restrictions(
        self, catalog: MetricCatalog, analyst_auth: dict, cfo_auth: dict
    ) -> None:
        retrieval_result = {
            "status": "candidates_found",
            "candidates": [{"metric_id": "operating_expense", "rank": 1}, {"metric_id": "cash_balance", "rank": 2}],
        }
        llm_opex = {
            "status": "resolved",
            "metric_ids": ["operating_expense"],
            "clarification_question": None,
            "unsupported_reason": None,
        }
        # analyst_auth only has allowed_views=['mgmt']; requesting 'tax' must fail with forbidden_metric
        with pytest.raises(ContractError) as e_forbidden_view:
            validate_metrics(
                llm_opex,
                retrieval_result,
                catalog,
                analyst_auth,
                query_context={"requested_view": "tax"},
            )
        assert e_forbidden_view.value.code == "forbidden_metric"
        assert e_forbidden_view.value.final_status == "forbidden"

        # CFO has 'tax' view, but 'cash_balance' only supports ['mgmt', 'gl'] -> unsupported_view
        with pytest.raises(ContractError) as e_unsup_view:
            validate_metrics(
                {
                    "status": "resolved",
                    "metric_ids": ["cash_balance"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                },
                retrieval_result,
                catalog,
                cfo_auth,
                query_context={"requested_view": "tax"},
            )
        assert e_unsup_view.value.code == "unsupported_view"

        # Restricted allowed_metrics in AuthContext -> forbidden_metric
        restricted_auth = build_auth_context(
            idp_claims={"user_id": "u-limited", "tenant_id": "minh-phat", "roles": ["viewer"]},
            server_policy={
                "allowed_views": ["mgmt"],
                "allowed_metrics": ["net_revenue"],
                "policy_version": "v1",
            },
        )
        with pytest.raises(ContractError) as e_forb_metric:
            validate_metrics(llm_opex, retrieval_result, catalog, restricted_auth)
        assert e_forb_metric.value.code == "forbidden_metric"

    def test_incompatible_period_types_rejected(self, catalog: MetricCatalog, analyst_auth: dict) -> None:
        # Combining 'net_revenue' (flow) and 'cash_balance' (snapshot) must raise incompatible_metrics
        retrieval_result = {
            "status": "candidates_found",
            "candidates": [
                {"metric_id": "net_revenue", "rank": 1},
                {"metric_id": "cash_balance", "rank": 2},
            ],
        }
        with pytest.raises(ContractError) as exc_info:
            validate_metrics(
                {
                    "status": "resolved",
                    "metric_ids": ["net_revenue", "cash_balance"],
                    "clarification_question": None,
                    "unsupported_reason": None,
                },
                retrieval_result,
                catalog,
                analyst_auth,
            )
        assert exc_info.value.code == "incompatible_metrics"
