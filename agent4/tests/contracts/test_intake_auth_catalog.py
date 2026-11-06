"""Tests for Section 1 (General Conventions) and Contracts 2, 3, 4 of contracts.md:
- query.intake.v1
- auth.policy-context.v1
- metric.catalog.v1
"""

from __future__ import annotations

import copy
import pytest

from tests.contract_harness import (
     DEFAULT_METRICS_DEFINITIONS,
    ContractError,
    MetricCatalog,
    build_auth_context,
    query_intake,
)


class TestGeneralConventions:
    """Section 1.1 - 1.4 of contracts.md."""

    def test_reject_unknown_fields_at_boundary(self) -> None:
        payload = {
            "api_version": "v1",
            "question": "Doanh thu tháng 8/2026 là bao nhiêu?",
            "locale": "vi-VN",
            "admin_override": True,
        }
        with pytest.raises(ContractError) as exc_info:
            query_intake(payload)
        err = exc_info.value.to_dict()
        assert err["code"] == "invalid_request"
        assert err["stage"] == "query_intake"
        assert "admin_override" in err["details"]["unknown_fields"]

    def test_input_immutability(self) -> None:
        payload = {
            "api_version": "v1",
            "question": "  Biên lợi nhuận ròng tháng này là bao nhiêu?  ",
            "locale": "vi-VN",
            "session_id": None,
            "options": {"include_table": True, "explain_metrics": False},
        }
        snapshot = copy.deepcopy(payload)
        out = query_intake(payload)
        assert payload == snapshot
        assert out["options"] is not payload["options"]

    def test_common_error_sanitization(self) -> None:
        err = ContractError(
            code="execution_failed",
            stage="sql_execution",
            message="Failed on SELECT * FROM gl_wide WHERE amount > 1000; password=supersecret",
            retryable=False,
            details={
                "raw_sql": "SELECT * FROM gl_wide",
                "stack_trace": "Traceback (most recent call last): File 'db.py'",
                "rows": [{"net_revenue": "19339316000.00"}],
                "safe_hint": "check connection",
            },
        )
        public_dict = err.to_dict()
        serialized = str(public_dict)
        assert "SELECT * FROM" not in serialized
        assert "supersecret" not in serialized
        assert "Traceback" not in serialized
        assert "19339316000" not in serialized
        assert public_dict["details"] == {"safe_hint": "check connection"}


class TestQueryIntakeContract:
    """Contract 2: query.intake.v1."""

    def test_intake_happy_path_vi_and_en(self) -> None:
        res_vi = query_intake(
            {
                "api_version": "v1",
                "question": "  Biên lợi nhuận ròng   tháng này là bao nhiêu? ",
                "locale": "vi-VN",
                "session_id": None,
                "options": {"include_table": True, "explain_metrics": True},
            }
        )
        assert res_vi["contract_version"] == "normalized-query.v1"
        assert res_vi["question"] == "  Biên lợi nhuận ròng   tháng này là bao nhiêu? "
        assert res_vi["normalized_question"] == "biên lợi nhuận ròng tháng này là bao nhiêu"
        assert res_vi["locale"] == "vi-VN"

        res_en = query_intake(
            {
                "api_version": "v1",
                "question": "What was the Net Revenue in August 2026?!",
                "locale": "en-US",
            }
        )
        assert res_en["normalized_question"] == "what was the net revenue in august 2026"
        assert res_en["locale"] == "en-US"

    def test_intake_errors(self) -> None:
        # Empty question -> invalid_request
        with pytest.raises(ContractError) as e1:
            query_intake({"api_version": "v1", "question": "   ", "locale": "vi-VN"})
        assert e1.value.code == "invalid_request"

        # Unsupported locale -> unsupported_locale
        with pytest.raises(ContractError) as e2:
            query_intake({"api_version": "v1", "question": "Chiffre d'affaires?", "locale": "fr-FR"})
        assert e2.value.code == "unsupported_locale"
        assert e2.value.final_status == "unsupported"

        # Question too long -> question_too_long
        with pytest.raises(ContractError) as e3:
            query_intake({"api_version": "v1", "question": "a" * 505, "locale": "vi-VN"})
        assert e3.value.code == "question_too_long"

    def test_intake_rejects_embedded_auth_claims(self) -> None:
        with pytest.raises(ContractError) as exc_info:
            query_intake(
                {
                    "api_version": "v1",
                    "question": "Doanh thu tháng 8/2026?",
                    "locale": "vi-VN",
                    "tenant_id": "other-tenant",
                    "roles": ["cfo"],
                }
            )
        assert exc_info.value.code == "invalid_request"


class TestAuthAndPolicyContextContract:
    """Contract 3: auth.policy-context.v1."""

    def test_auth_context_server_sourced_only(self) -> None:
        malicious_request_body = {
            "tenant_id": "hacked-tenant",
            "roles": ["cfo"],
            "allowed_views": ["mgmt", "tax", "gl"],
        }
        ctx = build_auth_context(
            idp_claims={"user_id": "u-10", "tenant_id": "tenant-a", "roles": ["finance_analyst"]},
            server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"},
            request_body=malicious_request_body,
        )
        assert ctx["tenant_id"] == "tenant-a"
        assert ctx["roles"] == ["finance_analyst"]
        assert ctx["allowed_views"] == ["mgmt"]
        assert ctx["policy_hash"].startswith("policy-")

    def test_auth_context_fail_closed(self) -> None:
        with pytest.raises(ContractError) as e1:
            build_auth_context(idp_claims=None, server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"})
        assert e1.value.code == "forbidden"
        assert e1.value.final_status == "forbidden"

        with pytest.raises(ContractError) as e2:
            build_auth_context(
                idp_claims={"user_id": "u-1", "tenant_id": "", "roles": []},
                server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"},
            )
        assert e2.value.code == "forbidden"


class TestMetricCatalogContract:
    """Contract 4: metric.catalog.v1."""

    def test_catalog_operations(self, catalog: MetricCatalog, analyst_auth: dict) -> None:
        assert catalog.contains("net_profit_margin") is True
        assert catalog.contains("non_existent_metric") is False

        m = catalog.get("net_profit_margin")
        assert m is not None
        assert m["unit"] == "%"
        assert m["period_type"] == "flow"
        assert m["status"] == "approved"

        cap = catalog.get_capability("net_profit_margin")
        assert "month" in cap["supported_dimensions"]
        assert "aggregate" in cap["supported_operations"]

        visible_ids = {item["metric_id"] for item in catalog.list_visible_metrics(analyst_auth)}
        assert "net_revenue" in visible_ids
        assert "net_profit_margin" in visible_ids

    def test_unapproved_and_unverified_metrics_hidden(self, catalog: MetricCatalog, cfo_auth: dict) -> None:
        # Draft metric and unverified custom KPI exist in raw definitions but must not be visible
        assert catalog.contains("experimental_cash_burn") is True
        assert catalog.contains("unverified_custom_kpi") is True
        visible_ids = {item["metric_id"] for item in catalog.list_visible_metrics(cfo_auth)}
        assert "experimental_cash_burn" not in visible_ids
        assert "unverified_custom_kpi" not in visible_ids

    def test_catalog_hash_reproducibility(self) -> None:
        c1 = MetricCatalog(DEFAULT_METRICS_DEFINITIONS)
        c2 = MetricCatalog(DEFAULT_METRICS_DEFINITIONS)
        assert c1.get_catalog_hash() == c2.get_catalog_hash()

        modified = copy.deepcopy(DEFAULT_METRICS_DEFINITIONS)
        modified[0]["sql_expr"] = "SUM(credit_amount)"
        c3 = MetricCatalog(modified)
        assert c3.get_catalog_hash() != c1.get_catalog_hash()
