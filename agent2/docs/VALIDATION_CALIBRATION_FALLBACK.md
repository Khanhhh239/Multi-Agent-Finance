# Validation, Calibration, and Fallback Plan — Agent2

## 1. Architecture & Contracts
- **Schema & Lock:** `agent2/sme_fraud/evaluation_plan.schema.json` (`evaluation-plan/1.0.0`, validated via `StrictValidator` + SHA-256 checksum pinning).
- **Core Pipeline:** `agent2/sme_fraud/validation_study.py` (`agent2-validation-study/1.0.0`) enforcing 4 chronological splits (`history_train` -> `detector_validation` -> `calibration_policy_validation` -> `sealed_future_test`), structural test-label blinding (`pre_test_lock_sha256`), frozen historical reference percentiles (`historical-reference-dist/1.0.0`), verified-only calibration (`verified-calibrator/1.0.0`), and explicit degraded fallbacks (`explicit-fallback-plan/1.0.0`).
- **Enterprise CLI Runner:** `agent2/scripts/run_validation_study.py` executing strictly locally at enterprise node (no cloud plaintext upload, active model & operational queue untouched).
- **Verification Suite:** `agent2/tests_he/test_validation_study.py` covering test-label blinding, plan pin mismatch detection, missing source/model null/unavailable semantics, calibration blocking on insufficient/non-verified labels, `C001`/`C002` + episode isolation, and deterministic rerun reproducibility.

## 2. Governance & Scope Disclosures
- **Generated (UTC):** `2026-11-15T17:50:23.332024+00:00`
- **Real HE Models Used:** `True` (enterprise-decrypted signed `Concrete FHE` models from `C001` & `C002`, no cloud plaintext sent).
- **Promotion Status:** `candidate_shadow_only` (`production_approved = false`, `active_model_replaced = false`, `operational_queue_changed = false`).
- **Synthetic Limit:** Du lieu synthetic da ky dung de kiem chung quy trinh validation/calibration/fallback; khong thay the bang chung hieu qua tren du lieu doanh nghiep that.
- **Open Decision Gates (`Agent2_Spec_v2_1/99_decision_log.md`):** `D-03`, `D-04`, `D-06`, `D-07`, `D-09` remain explicitly `OPEN_BLOCKING` / `PROPOSED_DEFAULT_EXPERIMENTAL_ONLY` (`approved_for_production = false`).

## 3. Automated Acceptance Gates
- `deterministic_reproducible_c001_c002`: **True**
- `recall_pr_auc_gated_under_incomplete_gt`: **True**
- `governance_shadow_only_no_prod_approval`: **True**

## 4.1 Enterprise `C001` Results
- **Plan Lock:** `evp_6ce4ccf22c920a42a8759018` (`plan_sha256=6ce4ccf22c920a42...`, `pre_test_lock_sha256=99e34ff311a17fa3...`)
- **Selected Candidate (locked from `detector_validation`):** `rules_plus_ecod` (`selection_sha256=c1e88a14cf97feb2...`)
- **Episode Limitations:** calibration_policy_validation: synthetic payment batch without external ERP case-link table.; detector_validation: synthetic payment batch without external ERP case-link table.; sealed_future_test: synthetic payment batch without external ERP case-link table.
- **Calibrator (`calibration_policy_validation`):** status=`calibrated`, method=`platt_logistic`, verified pos/neg=`7/5`, excluded `confirmed_risk` reviews=`7`
- **Execution Costs:** val=`40.386ms` / `239.03KB`, cal=`94.867ms`, sealed_test=`28.874ms`, fallback=`35.415ms`
- **Sealed Test Calibration Metrics:** `brier=0.25357`, `log_loss=0.700296`, `ece=0.082427` (uncalibrated: brier=`0.210371`, log_loss=`0.612516`)

### Calibration Reliability Bins (Sealed Future Test)
| Bin | Range | Count | Mean Predicted Prob | Observed Fraud Rate | Abs Gap |
|---:|---|---:|---:|---:|---:|
| 0 | [0.00, 0.25] | 0 | n/a | n/a | n/a |
| 1 | [0.25, 0.50] | 0 | n/a | n/a | n/a |
| 2 | [0.50, 0.75] | 14 | 0.5824 | 0.5000 | 0.0824 |
| 3 | [0.75, 1.00] | 0 | n/a | n/a | n/a |

### Sealed Future Test Comparison (`rules_first_fill/1.0.0`, budget=5)
| Arm ID | Kind | Available | Selected | VF Added Over Rules | Resolved Denom | Unresolved (Rate) | Precision | Review Effort (s) | Recall / PR-AUC |
|---|---|---:|---:|---:|---:|---|---:|---|---|
| `rules_only` | `rules_only` | 16/16 | 3 | 0 cases | 3 | 0 (0.00) | 1.000 (3/3) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `ecod_standalone` | `individual_detector` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 1.000 (5/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `if_standalone` | `individual_detector` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 1.000 (5/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `supervised_shadow_standalone` | `individual_detector` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 0.800 (4/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_ecod` | `rules_plus_ml` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 1.000 (5/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_isolation_forest` | `rules_plus_ml` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 1.000 (5/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_supervised_shadow` | `rules_plus_ml` | 16/16 | 5 | 1 cases | 5 | 0 (0.00) | 0.800 (4/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_ens_ecod_sup` | `rules_plus_percentile_ensemble` | 16/16 | 5 | 1 cases | 5 | 0 (0.00) | 0.800 (4/5) | 0.016 | null (incomplete_or_selective_ground_truth_in_split) |

- **Common Coverage Subset:** `16/16` rows simultaneously available across all candidate arms.
- **Policy Variant `priority_top5_no_rules_priority` (isolated delta on `rules_plus_ecod`):** `vf_selected_delta=0`, `precision_delta=0.0`
- **Policy Variant `rules_first_thresh_0.55` (isolated delta on `rules_plus_ecod`):** `vf_selected_delta=0`, `precision_delta=0.0`

### Fallback Plan Validation Matrix
| Fallback ID | Trigger | Is Full Ensemble | Used Branches | Missing Branches | Avail Rate | Null On Unavail |
|---|---|---:|---|---|---:|---:|
| `fb_missing_sup_v1` | `missing_supervised_model` | False | `rules_35, ecod` | `supervised_shadow` | 1.00 | True |
| `fb_missing_unsup_v1` | `missing_unsupervised_model` | False | `rules_35, supervised_shadow` | `ecod, isolation_forest, robust_z` | 1.00 | True |
| `fb_incompatible_contract_v1` | `incompatible_contract` | False | `rules_35` | `ecod, isolation_forest, supervised_shadow` | 1.00 | True |
| `fb_missing_feature_v1` | `missing_feature_or_post_cutoff` | False | `rules_35, ecod` | `supervised_shadow` | 0.62 | True |
| `fb_missing_ref_v1` | `missing_reference_distribution` | False | `rules_35, supervised_shadow` | `ecod` | 1.00 | True |
| `fb_partial_rule_gap_v1` | `partial_rule_source_gap` | False | `rules_35, ecod` | `rule_E2_partial` | 1.00 | True |
| `fb_all_unavailable_v1` | `all_branches_unavailable` | False | `none` | `rules_35, ecod, isolation_forest, supervised_shadow` | 0.00 | True |

## 4.2 Enterprise `C002` Results
- **Plan Lock:** `evp_1649cc731a7e5aff1130e3fc` (`plan_sha256=1649cc731a7e5aff...`, `pre_test_lock_sha256=46a97c32c11f53ce...`)
- **Selected Candidate (locked from `detector_validation`):** `rules_plus_ecod` (`selection_sha256=39d6bd9a3e305435...`)
- **Episode Limitations:** calibration_policy_validation: synthetic payment batch without external ERP case-link table.; detector_validation: synthetic payment batch without external ERP case-link table.; sealed_future_test: synthetic payment batch without external ERP case-link table.
- **Calibrator (`calibration_policy_validation`):** status=`calibrated`, method=`platt_logistic`, verified pos/neg=`7/5`, excluded `confirmed_risk` reviews=`7`
- **Execution Costs:** val=`53.505ms` / `239.03KB`, cal=`95.318ms`, sealed_test=`25.752ms`, fallback=`36.779ms`
- **Sealed Test Calibration Metrics:** `brier=0.255544`, `log_loss=0.704353`, `ece=0.082909` (uncalibrated: brier=`0.297842`, log_loss=`0.791087`)

### Calibration Reliability Bins (Sealed Future Test)
| Bin | Range | Count | Mean Predicted Prob | Observed Fraud Rate | Abs Gap |
|---:|---|---:|---:|---:|---:|
| 0 | [0.00, 0.25] | 0 | n/a | n/a | n/a |
| 1 | [0.25, 0.50] | 0 | n/a | n/a | n/a |
| 2 | [0.50, 0.75] | 14 | 0.5829 | 0.5000 | 0.0829 |
| 3 | [0.75, 1.00] | 0 | n/a | n/a | n/a |

### Sealed Future Test Comparison (`rules_first_fill/1.0.0`, budget=5)
| Arm ID | Kind | Available | Selected | VF Added Over Rules | Resolved Denom | Unresolved (Rate) | Precision | Review Effort (s) | Recall / PR-AUC |
|---|---|---:|---:|---:|---:|---|---:|---|---|
| `rules_only` | `rules_only` | 16/16 | 2 | 0 cases | 2 | 0 (0.00) | 1.000 (2/2) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `ecod_standalone` | `individual_detector` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 1.000 (5/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `if_standalone` | `individual_detector` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 0.800 (4/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `supervised_shadow_standalone` | `individual_detector` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 0.600 (3/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_ecod` | `rules_plus_ml` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 1.000 (5/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_isolation_forest` | `rules_plus_ml` | 16/16 | 5 | 3 cases | 5 | 0 (0.00) | 1.000 (5/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_supervised_shadow` | `rules_plus_ml` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 0.800 (4/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |
| `rules_plus_ens_ecod_sup` | `rules_plus_percentile_ensemble` | 16/16 | 5 | 2 cases | 5 | 0 (0.00) | 0.800 (4/5) | null (unrecorded) | null (incomplete_or_selective_ground_truth_in_split) |

- **Common Coverage Subset:** `16/16` rows simultaneously available across all candidate arms.
- **Policy Variant `priority_top5_no_rules_priority` (isolated delta on `rules_plus_ecod`):** `vf_selected_delta=0`, `precision_delta=0.0`
- **Policy Variant `rules_first_thresh_0.55` (isolated delta on `rules_plus_ecod`):** `vf_selected_delta=0`, `precision_delta=0.0`

### Fallback Plan Validation Matrix
| Fallback ID | Trigger | Is Full Ensemble | Used Branches | Missing Branches | Avail Rate | Null On Unavail |
|---|---|---:|---|---|---:|---:|
| `fb_missing_sup_v1` | `missing_supervised_model` | False | `rules_35, ecod` | `supervised_shadow` | 1.00 | True |
| `fb_missing_unsup_v1` | `missing_unsupervised_model` | False | `rules_35, supervised_shadow` | `ecod, isolation_forest, robust_z` | 1.00 | True |
| `fb_incompatible_contract_v1` | `incompatible_contract` | False | `rules_35` | `ecod, isolation_forest, supervised_shadow` | 1.00 | True |
| `fb_missing_feature_v1` | `missing_feature_or_post_cutoff` | False | `rules_35, ecod` | `supervised_shadow` | 0.62 | True |
| `fb_missing_ref_v1` | `missing_reference_distribution` | False | `rules_35, supervised_shadow` | `ecod` | 1.00 | True |
| `fb_partial_rule_gap_v1` | `partial_rule_source_gap` | False | `rules_35, ecod` | `rule_E2_partial` | 1.00 | True |
| `fb_all_unavailable_v1` | `all_branches_unavailable` | False | `none` | `rules_35, ecod, isolation_forest, supervised_shadow` | 0.00 | True |
