from datetime import date

import pytest

from agent4.text2sql.compiler import SQLCompiler, assert_safe_select
from agent4.text2sql.errors import UnsafeQuery
from agent4.text2sql.models import FilterDraft, SemanticPlanDraft, TimeDraft
from agent4.text2sql.validation import SemanticValidator


def plan(catalog, auth, *, metric_ids=None, dimensions=None, filters=None, view="mgmt", time=None):
    draft = SemanticPlanDraft(
        plan_version="1.0", status="ready",
        metric_ids=metric_ids or ["net_revenue"],
        time=time or TimeDraft.range(date(2026, 10, 1), date(2026, 10, 31)),
        dimensions=dimensions or [], filters=filters or [], view=view,
        operation="timeseries" if dimensions else "aggregate", sort=None, top_k=None,
        comparison=None, question_for_user=None, unresolved_slots=[], reason_code=None,
    )
    return SemanticValidator(catalog).validate(draft, auth)


def test_c01_dates_and_prefixes_are_bound(catalog, auth):
    query = SQLCompiler(catalog).compile(plan(catalog, auth))
    assert query.sql.count("?") == len(query.params)
    assert "2026-10-01" not in query.sql
    assert "511%" not in query.sql
    assert query.sql.startswith("WITH aggregated AS")


def test_c02_injection_filter_is_bound_not_interpolated(catalog, auth):
    attack = "HN' OR 1=1 --"
    query = SQLCompiler(catalog).compile(plan(
        catalog, auth, filters=[FilterDraft(field="branch", operator="eq", values=[attack])]
    ))
    assert attack not in query.sql
    assert attack in query.params
    assert "branch_code = ?" in query.sql


def test_c03_dimensions_are_allowlisted(catalog, auth):
    query = SQLCompiler(catalog).compile(plan(catalog, auth, dimensions=["month"]))
    assert "strftime(posting_date" in query.sql


@pytest.mark.parametrize("sql", [
    "DROP TABLE ledger", "SELECT 1; DELETE FROM ledger", "UPDATE ledger SET x=1",
    "COPY ledger TO '/tmp/leak'", "SELECT * FROM information_schema.tables",
    "SELECT * FROM read_csv_auto('/tmp/private.csv')",
])
def test_c04_c06_unsafe_sql_is_rejected(sql):
    with pytest.raises(UnsafeQuery):
        assert_safe_select(sql)


def test_c14_ratio_uses_aggregated_num_den(catalog, auth):
    query = SQLCompiler(catalog).compile(plan(catalog, auth, metric_ids=["gross_margin_pct"]))
    assert "gross_margin_pct__num" in query.sql
    assert "gross_margin_pct__den" in query.sql
    assert "CASE WHEN gross_margin_pct__den = 0 THEN NULL" in query.sql
    assert "AS DECIMAL(38, 10)" in query.sql


def test_c20_lineage_contains_only_selected_metrics(catalog, auth):
    query = SQLCompiler(catalog).compile(plan(catalog, auth, metric_ids=["net_revenue", "gross_profit"]))
    assert query.metric_ids == ("net_revenue", "gross_profit")
    assert set(query.units) == {"net_revenue", "gross_profit"}
    assert len(query.fingerprint) == 24


def test_catalog_version_mismatch_is_fail_closed(catalog, auth):
    validated = plan(catalog, auth)
    stale = validated.model_copy(update={"catalog_hash": "stale-catalog"})
    with pytest.raises(UnsafeQuery, match="catalog changed"):
        SQLCompiler(catalog).compile(stale)


def test_resource_abuse_filter_cardinality_rejected_by_schema():
    with pytest.raises(ValueError):
        FilterDraft(field="branch", operator="in", values=[str(i) for i in range(101)])
