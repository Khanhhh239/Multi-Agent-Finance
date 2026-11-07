"""Tests for Section 1 (General Conventions) and Contracts 2, 3, 4 of contracts.md:
- query.intake.v1
- auth.policy-context.v1
- metric.catalog.v1
"""

from __future__ import annotations

import copy

import pytest

from agent4.core.catalog import DEFAULT_METRICS_DEFINITIONS, MetricCatalog
from agent4.core.config import AppConfig
from agent4.core.context import build_auth_context, build_runtime_context, query_intake
from agent4.core.errors import ContractError


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
        assert "SELECT * FROM" not in str(err)
        assert "supersecret" not in str(err)
        assert public_dict["details"] == {"safe_hint": "check connection"}

    def test_app_config_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "AGENT4_DB",
            "AGENT4_GROUND_TRUTH",
            "AGENT4_LLM_BASE_URL",
            "AGENT4_LLM_MODEL",
            "AGENT4_MAX_QUESTION_LENGTH",
            "AGENT4_DEFAULT_ROW_CAP",
            "AGENT4_QUERY_TIMEOUT_MS",
        ):
            monkeypatch.delenv(name, raising=False)

        config = AppConfig()
        assert str(config.db_path) == "data/cfo_warehouse.duckdb"
        assert str(config.ground_truth_path) == "data/cfo_warehouse_ground_truth.json"
        assert config.qwen_base_url == "http://localhost:11434/api/chat"
        assert config.qwen_model == "qwen3:4b"
        assert config.max_question_length == 500
        assert config.default_row_cap == 1000
        assert config.query_timeout_ms == 5000


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
            query_intake(
                {"api_version": "v1", "question": "Chiffre d'affaires?", "locale": "fr-FR"}
            )
        assert e2.value.code == "unsupported_locale"
        assert e2.value.final_status == "unsupported"

        # Question too long -> question_too_long
        with pytest.raises(ContractError) as e3:
            query_intake({"api_version": "v1", "question": "a" * 505, "locale": "vi-VN"})
        assert e3.value.code == "question_too_long"

        with pytest.raises(ContractError) as e4:
            query_intake({"api_version": "v1", "question": "Revenue?", "locale": []})
        assert e4.value.code == "unsupported_locale"

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
            build_auth_context(
                idp_claims=None, server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"}
            )
        assert e1.value.code == "forbidden"
        assert e1.value.final_status == "forbidden"

        with pytest.raises(ContractError) as e2:
            build_auth_context(
                idp_claims={"user_id": "u-1", "tenant_id": "", "roles": []},
                server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"},
            )
        assert e2.value.code == "forbidden"

        with pytest.raises(ContractError) as e3:
            build_auth_context(
                idp_claims={"user_id": "u-1", "tenant_id": "tenant-a"},
                server_policy={"allowed_views": ["mgmt"], "policy_version": "v1"},
            )
        assert e3.value.code == "forbidden"

    def test_policy_hash_and_runtime_context_are_server_sourced(self) -> None:
        claims = {"user_id": "u-10", "tenant_id": "tenant-a", "roles": ["analyst", "reviewer"]}
        policy = {
            "allowed_views": ["tax", "mgmt"],
            "allowed_metrics": ["net_revenue"],
            "policy_version": "v1",
        }
        claims_snapshot = copy.deepcopy(claims)
        policy_snapshot = copy.deepcopy(policy)
        auth1 = build_auth_context(claims, policy)
        auth2 = build_auth_context(
            {"user_id": "u-10", "tenant_id": "tenant-a", "roles": ["reviewer", "analyst"]},
            {
                "allowed_views": ["mgmt", "tax"],
                "allowed_metrics": ["net_revenue"],
                "policy_version": "v1",
            },
        )
        assert auth1["policy_hash"] == auth2["policy_hash"]
        unrestricted = build_auth_context(
            claims,
            {"allowed_views": ["mgmt"], "allowed_metrics": None, "policy_version": "v1"},
        )
        deny_all = build_auth_context(
            claims,
            {"allowed_views": ["mgmt"], "allowed_metrics": [], "policy_version": "v1"},
        )
        assert unrestricted["policy_hash"] != deny_all["policy_hash"]
        assert claims == claims_snapshot
        assert policy == policy_snapshot
        assert auth1["roles"] is not claims["roles"]

        runtime = build_runtime_context(
            request_id="req-1",
            trace_id="trace-1",
            auth_context=auth1,
            locale="vi-VN",
            timezone="Asia/Ho_Chi_Minh",
            catalog_hash="catalog-abc",
            request_body={
                "tenant_id": "hacked-tenant",
                "roles": ["cfo"],
                "allowed_views": ["gl"],
                "policy_hash": "policy-hacked",
            },
        )
        assert runtime["tenant_id"] == "tenant-a"
        assert runtime["roles"] == ["analyst", "reviewer"]
        assert runtime["allowed_views"] == ["tax", "mgmt"]
        assert runtime["policy_hash"] == auth1["policy_hash"]


class TestMetricCatalogContract:
    """Contract 4: metric.catalog.v1."""

    def test_catalog_operations(self, analyst_auth: dict) -> None:
        catalog = MetricCatalog()
        assert len(DEFAULT_METRICS_DEFINITIONS) == 15
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

        with pytest.raises(ContractError) as exc_info:
            catalog.get_capability("non_existent_metric")
        assert exc_info.value.code == "unknown_metric"
        assert exc_info.value.stage == "metric_catalog"

    def test_unapproved_and_unverified_metrics_hidden(self, cfo_auth: dict) -> None:
        catalog = MetricCatalog()
        # Draft metric and unverified custom KPI exist in raw definitions but must not be visible
        assert catalog.contains("experimental_cash_burn") is True
        assert catalog.contains("unverified_custom_kpi") is True
        visible_ids = {item["metric_id"] for item in catalog.list_visible_metrics(cfo_auth)}
        assert len(visible_ids) == 13
        assert "experimental_cash_burn" not in visible_ids
        assert "unverified_custom_kpi" not in visible_ids

        restricted = copy.deepcopy(cfo_auth)
        restricted["allowed_metrics"] = ["net_revenue"]
        assert [item["metric_id"] for item in catalog.list_visible_metrics(restricted)] == [
            "net_revenue"
        ]

        gl_only = copy.deepcopy(cfo_auth)
        gl_only["allowed_views"] = ["gl"]
        gl_visible = {item["metric_id"] for item in catalog.list_visible_metrics(gl_only)}
        assert "net_revenue" in gl_visible
        assert "net_profit_margin" not in gl_visible

    def test_catalog_hash_reproducibility(self) -> None:
        c1 = MetricCatalog(DEFAULT_METRICS_DEFINITIONS)
        c2 = MetricCatalog(DEFAULT_METRICS_DEFINITIONS)
        assert c1.get_catalog_hash() == c2.get_catalog_hash()

        modified = copy.deepcopy(DEFAULT_METRICS_DEFINITIONS)
        modified[0]["sql_expr"] = "SUM(credit_amount)"
        c3 = MetricCatalog(modified)
        assert c3.get_catalog_hash() != c1.get_catalog_hash()

        relabeled = copy.deepcopy(DEFAULT_METRICS_DEFINITIONS)
        relabeled[0]["label"] = "Doanh thu thuần (đã đổi)"
        c4 = MetricCatalog(relabeled)
        assert c4.get_catalog_hash() != c1.get_catalog_hash()

    def test_catalog_does_not_expose_mutable_internal_state(self) -> None:
        source = copy.deepcopy(DEFAULT_METRICS_DEFINITIONS)
        catalog = MetricCatalog(source)
        original_hash = catalog.get_catalog_hash()

        source[0]["label"] = "tampered source"
        fetched = catalog.get("net_revenue")
        assert fetched is not None
        fetched["label"] = "tampered getter"
        fetched["supported_views"].clear()

        capability = catalog.get_capability("net_revenue")
        capability["supported_views"].clear()
        visible = catalog.list_visible_metrics({"allowed_views": ["mgmt"], "allowed_metrics": None})
        visible[0]["label"] = "tampered visibility result"

        unchanged = catalog.get("net_revenue")
        assert unchanged is not None
        assert unchanged["label"] == "Doanh thu thuần"
        assert unchanged["supported_views"] == ["mgmt", "tax", "gl"]
        assert catalog.get_catalog_hash() == original_hash
