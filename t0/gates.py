"""Separate execution, technical checks, measured quality and external evidence."""


DEFAULT_POLICY = {"ar_min_precision": 0.998, "ar_min_recall": 0.8,
                  "settlement_min_precision": 0.998, "settlement_min_recall": 0.95,
                  "journal_min_precision": 0.998, "journal_min_recall": 0.8}


def assess(results, checks, policy=None):
    policy = dict(DEFAULT_POLICY if policy is None else policy)
    if set(policy) != set(DEFAULT_POLICY) or any(type(v) not in (float, int) or not 0 <= v <= 1 for v in policy.values()):
        raise ValueError("explicit finite quality thresholds in [0,1] required")
    unavailable = [k for k in ("finrca", "recbench", "finbalance", "fiscus")
                   if results[k].get("status") == "unavailable"]
    ar = [r for r in results["ar"]["summary"] if r["split"] == "test" and r["method"] == "v2_full"]
    ar_pass = bool(ar) and all(r["metrics"]["precision"]["mean"] is not None
                             and r["metrics"]["precision"]["mean"] >= policy["ar_min_precision"]
                             and r["metrics"]["recall"]["mean"] is not None
                             and r["metrics"]["recall"]["mean"] >= policy["ar_min_recall"] for r in ar)
    new_ar = [r for r in results.get("robustness", {}).get("summary", [])
              if r["split"] == "test" and r["method"] == "constrained_flow"]
    new_ar_pass = bool(new_ar) and all(r["metrics"]["precision"]["mean"] is not None
                                     and r["metrics"]["precision"]["mean"] >= policy["ar_min_precision"]
                                     and r["metrics"]["recall"]["mean"] is not None
                                     and r["metrics"]["recall"]["mean"] >= policy["ar_min_recall"] for r in new_ar)
    settlement = results["recbench"].get("metrics", {})
    journal = results["finbalance"].get("metrics", {}).get("summary", {})

    def quality(metrics, p, r, prefix):
        if metrics.get(p) is None or metrics.get(r) is None:
            return None
        return metrics[p] >= policy[prefix + "_min_precision"] and metrics[r] >= policy[prefix + "_min_recall"]

    task_quality = {"ar_v2_regression": ar_pass, "constrained_flow": new_ar_pass, "finrca": None,
                    "recbench": quality(settlement, "exact_link_precision", "exact_link_recall", "settlement"),
                    "finbalance": quality(journal, "entry_precision", "entry_recall_full_coverage_pool", "journal")}
    technical = bool(checks) and all(value is True for value in checks.values())
    return {"policy": policy, "policy_scope": "Explicit development gates, not a production SLA or statistical certificate",
            "unavailable_tasks": unavailable, "execution_complete": not unavailable,
            "technical_pass": technical, "task_quality_pass": task_quality,
            "quality_complete": all(v is True for v in task_quality.values()),
            "status": "technical_failure" if not technical and not unavailable else
                      "incomplete" if unavailable else "quality_or_evidence_incomplete",
            "production_ready": False,
            "missing_external_evidence": ["Independent SME invoice-bank labels and historical availability",
                                          "Verified FinRCA repair/bank oracle", "Live ERP/bank and domain holdout",
                                          "RecBench missing endpoints and full settlement", "Broad journal policies/main eval"]}


def exit_code(assessment, gate="execution"):
    if gate not in ("execution", "technical", "quality"):
        raise ValueError("unknown gate")
    if not assessment["execution_complete"]:
        return 3
    if not assessment["technical_pass"]:
        return 1
    if gate == "quality" and not assessment["quality_complete"]:
        return 4
    return 0
