"""Produce bounded, sanitized evidence for the verified answer."""

from agent4.core.catalog import MetricCatalog
from agent4.planning.validator import ValidatedPlan
from agent4.sql.compiler import BoundQuery

from .generator import metric_label
from .result_validator import safe_display_text

_VIEW_EXPLANATION = {
    "mgmt": ("Số liệu theo góc nhìn quản trị.", "Figures follow management reporting."),
    "tax": ("Số liệu theo góc nhìn thuế.", "Figures follow tax reporting."),
}


def build_evidence_preview(
    validated_answer: dict,
    validated_result: dict,
    plan: ValidatedPlan,
    catalog: MetricCatalog,
    bound: BoundQuery,
    *,
    locale: str = "vi-VN",
    preview_limit: int = 5,
    explain_metrics: bool = True,
) -> dict:
    result = validated_result["result"]
    rows = result["rows"]
    cited = []
    indexes: dict[int, None] = {}
    definitions = {mid: catalog.get(mid) for mid in plan.metric_ids}

    def preview(index: int) -> dict:
        return {
            key: safe_display_text(value) if isinstance(value, str) else value
            for key, value in rows[index].items()
        }

    for claim in validated_answer["validated_claims"]:
        for index in claim["source_rows"]:
            indexes[index] = None
            row = preview(index)
            for mid in claim["source_columns"]:
                definition = definitions[mid]
                cited.append(
                    {
                        "metric_id": mid,
                        "metric_label": metric_label(definition, locale),
                        "value": row[mid],
                        "unit": definition["unit"],
                        "source_columns": [mid],
                        "source_rows": [index],
                        "cited_row_preview": row,
                    }
                )
    indexes.update(dict.fromkeys(range(len(rows))))
    sample = [preview(index) for index in list(indexes)[: max(0, min(5, preview_limit))]]
    return {
        "contract_version": "evidence.preview.v1",
        "claim_citations": cited,
        "preview_table": {
            "columns": result["columns"],
            "sample_rows": sample,
            "sample_row_count": len(sample),
            "total_row_count": len(rows),
            "is_sample_truncated": len(sample) < len(rows),
        },
        "metric_explanations": [
            {
                "metric_id": mid,
                "label": metric_label(definition, locale),
                "description": safe_display_text(definition["description"]),
                "unit": definition["unit"],
                "kind": definition["kind"],
                "period_type": definition["period_type"],
                "active_view": plan.view,
                "view_explanation": _VIEW_EXPLANATION[plan.view][int(locale == "en-US")],
            }
            for mid, definition in definitions.items()
        ]
        if explain_metrics
        else [],
        "verification_badge": {
            "numbers_verified": any(item["value"] is not None for item in cited),
            "source_relation": plan.view,
            "data_watermark": result["data_watermark"],
            "period_close_status": (
                "open_partial" if validated_result["status"] == "partial" else "closed"
            ),
            "applied_defaults": list(plan.applied_defaults),
            "query_fingerprint": bound.fingerprint,
        },
    }
