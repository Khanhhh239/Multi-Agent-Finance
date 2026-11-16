# R3 Evidence Report: Case Coalescing, Budget, Outbox Idempotency, and Backlog

- Run ID: `r3-case-queue-20261115T181143Z`
- Status: **PASS** (5/5 R3 criteria: `R3-01` .. `R3-05`, validated against `acceptance.schema.json`)
- Governance status: `approved_for_production=false` (`D-04`, `D-05`, `D-06`, `D-07` remain OPEN)
- Benchmark cap preserved: `selection_comparison.BUDGET = 5` (tx-level comparison untouched)

## Observed Results

| Criterion | Status | Observed Summary | Artifact |
|---|---|---|---|
| `R3-01` | `pass` | 3 tx on HD-COAL-99 coalesced to 1 case (score=8.4); 2 independent obligations with V_SHARED remained 2 cases. | `Agent2_Spec_v2_1/evidence/R3/case_policy_report.json` |
| `R3-02` | `pass` | Real SnapshotStore 35-rule run produced HD78 case with candidate_ids=['T105'], evidence_tx_ids=['T096'], evidence_bonus=0.0. | `Agent2_Spec_v2_1/evidence/R3/case_policy_report.json` |
| `R3-03` | `pass` | 5 qualifying -> queued=3, backlog=2; 0 qualifying -> queued=0; selection_comparison.BUDGET=5 untouched. | `Agent2_Spec_v2_1/evidence/R3/case_policy_report.json` |
| `R3-04` | `pass` | 12 concurrent calls -> queued=3, reserved=3/3; crash recovery across 3 fault boundaries -> queued=1, unacked=0. | `Agent2_Spec_v2_1/evidence/R3/case_policy_report.json` |
| `R3-05` | `pass` | Shadow queued=2, active queued=0, C002 queued=0, auto_expire=False. | `Agent2_Spec_v2_1/evidence/R3/case_policy_report.json` |
