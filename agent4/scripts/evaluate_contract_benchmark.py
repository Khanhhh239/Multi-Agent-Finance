"""CLI for new evaluation; compatibility fixtures for the existing contract tests.

``evaluate_benchmark_question`` supplies fixed selection/plan inputs to the test
harness. It checks contract wiring, NOT retrieval/LLM/planner accuracy. Its frozen
v1 fixture is kept separate from the v2 questions used by vals/run_eval.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BENCHMARK_PATH = REPO_ROOT / "data/eval/contract_benchmark_questions.v1.jsonl"


def evaluate_benchmark_question(
    item: dict[str, Any],
    catalog: Any,
    embedding_provider: Any,
) -> dict[str, Any]:
    """Preserve the input-fixture API used by user-authored contract tests.

    Ground truth is intentionally an INPUT to this integration fixture. Do not
    report its pass rate as natural-language or independent model evaluation.
    The new runner never imports this function or the test harness.
    """
    from tests.contract_harness import (
        DB_PATH,
        ContractError,
        build_auth_context,
        build_final_response,
        compile_sql,
        execute_safe_sql,
        generate_grounded_answer,
        orchestrate_retrieval,
        query_intake,
        retrieve_dynamic_fewshot,
        validate_answer,
        validate_metrics,
        validate_result,
        validate_semantic_plan_draft,
        validate_sql_safety,
    )

    bm_id = item["benchmark_id"]
    raw_auth = item["auth_context"]
    auth = build_auth_context(
        idp_claims={key: raw_auth[key] for key in ("user_id", "tenant_id", "roles")},
        server_policy={
            "allowed_views": raw_auth["allowed_views"],
            "allowed_metrics": raw_auth.get("allowed_metrics"),
            "policy_version": "2026.11",
        },
    )
    context = {
        "request_id": f"req-{bm_id}",
        "trace_id": f"trace-{bm_id}",
        "tenant_id": auth["tenant_id"],
        "user_id": auth["user_id"],
        "roles": auth["roles"],
        "allowed_views": auth["allowed_views"],
        "locale": item["locale"],
        "timezone": "Asia/Ho_Chi_Minh",
        "catalog_hash": catalog.get_catalog_hash(),
        "policy_hash": auth["policy_hash"],
    }
    fewshot = None
    try:
        query = query_intake(
            {"api_version": "v1", "question": item["question"], "locale": item["locale"]}
        )
        retrieval = orchestrate_retrieval(query, catalog, embedding_provider, top_k=15)
        candidate_ids = [candidate["metric_id"] for candidate in retrieval["candidates"]]
        selection = item["expected_selection"]
        # Fixed-input integration fixture: downstream validators must receive the
        # supplied metric inputs. This is explicitly excluded from new evals.
        for metric_id in selection.get("metric_ids", []):
            if (
                metric_id not in candidate_ids
                and catalog.contains(metric_id)
                and catalog.get(metric_id)["status"] == "approved"
            ):
                retrieval["candidates"].append(
                    {
                        "metric_id": metric_id,
                        "rank": len(candidate_ids) + 1,
                        "retrieval_sources": ["dense"],
                        "dense_score": 0.5,
                        "lexical_score": None,
                        "fusion_score": 0.01,
                        "rerank_score": 0.5,
                    }
                )
                candidate_ids.append(metric_id)
        plan_draft = item.get("expected_plan")
        fewshot = retrieve_dynamic_fewshot(
            {
                "question": query["question"],
                "locale": query["locale"],
                "candidate_metric_ids": candidate_ids,
                "context": {"view": (plan_draft or {}).get("view", "mgmt")},
                "max_examples": 3,
                "token_budget": 2500,
                "selection_strategy": "hybrid",
                "example_bank_version": "fewshot-v4",
                "compatible_only": True,
            }
        )
        draft = {
            "status": selection["status"],
            "metric_ids": list(selection.get("metric_ids", [])),
            "clarification_question": selection.get("clarification_question"),
            "unsupported_reason": selection.get("unsupported_reason"),
        }
        validated_metrics = validate_metrics(
            draft,
            retrieval,
            catalog,
            auth,
            query_context={
                "requested_view": plan_draft["view"] if plan_draft else "mgmt",
                "requested_dimensions": plan_draft["dimensions"] if plan_draft else [],
                "requested_operation": (plan_draft or {}).get("operation") or "aggregate",
            },
        )
        if validated_metrics["status"] == "needs_clarification":
            response = build_final_response(
                request_id=context["request_id"],
                status="needs_clarification",
                answer=validated_metrics["clarification_question"],
            )
            return {
                "benchmark_id": bm_id,
                "response": response,
                "fewshot": fewshot,
                "passed": response["status"] == item["expected_final_status"],
            }
        if plan_draft is None:
            raise ValueError("Executable integration fixture requires expected_plan")
        plan = validate_semantic_plan_draft(plan_draft, validated_metrics, catalog, auth)
        if plan["status"] == "needs_clarification":
            response = build_final_response(
                request_id=context["request_id"],
                status="needs_clarification",
                answer=plan["question_for_user"],
            )
            return {
                "benchmark_id": bm_id,
                "response": response,
                "fewshot": fewshot,
                "passed": response["status"] == item["expected_final_status"],
            }
        bound = compile_sql(plan, catalog)
        safe = validate_sql_safety(bound, catalog, context)
        result = execute_safe_sql(safe, db_path=DB_PATH)
        validated_result = validate_result(result, plan, catalog)
        answer = generate_grounded_answer(plan, validated_result, catalog, locale=item["locale"])
        validated_answer = validate_answer(
            answer, validated_result, plan, catalog, locale=item["locale"]
        )
        status = "no_data" if validated_result["status"] == "no_data" else "ready"
        response = build_final_response(
            request_id=context["request_id"],
            status=status,
            answer=validated_answer["answer"],
            execution_result=result,
            validated_plan=plan,
            bound_query=bound,
            warnings=validated_answer["warnings"],
        )
        rows_match = result["rows"] == item["golden_rows"] if item.get("golden_sql") else True
        return {
            "benchmark_id": bm_id,
            "response": response,
            "fewshot": fewshot,
            "rows_match": rows_match,
            "passed": response["status"] == item["expected_final_status"] and rows_match,
        }
    except ContractError as exc:
        response = build_final_response(
            request_id=context["request_id"], status=exc.final_status, error=exc.to_dict()
        )
        return {
            "benchmark_id": bm_id,
            "response": response,
            "fewshot": None,
            "rows_match": True,
            "passed": response["status"] == item["expected_final_status"],
        }


if __name__ == "__main__":
    from vals.run_eval import main

    raise SystemExit(main())
