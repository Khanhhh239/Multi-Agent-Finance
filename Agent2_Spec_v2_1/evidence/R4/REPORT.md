# R4 Evidence Report: Document Checklists, Evidence Versioning, Reconciliation, and ActionTasks

- Run ID: `r4-acc-20261115T183253Z`
- Status: **PASS** (`R4-01` .. `R4-06`, validated against `acceptance.schema.json`)
- Governance gates: `approved_for_production=false` (`D-08`, `D-14` remain OPEN; no hardcoded 7-day default SLA)

## Observed Results

| Criterion | Status | Observed Summary | Artifact |
|---|---|---|---|
| `R4-01` | `pass` | 50+70->matched; HD78 T096+T105->overpaid excess=120000000 loss=None. | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
| `R4-02` | `pass` | HD-MN-A settled net=70000000 status=matched with refund=70000000. | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
| `R4-03` | `pass` | Policy families=9, doc v2 preserved history, late arrival preserved snapshot sha256 ea973fd1d40d. | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
| `R4-04` | `pass` | Task tsk_7fe851e7f193a33c5e6817f3 blocked before verify (blocked=True), completed after verify, reopened cleanly (history=4 events). | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
| `R4-05` | `pass` | Closed Case case_0040797479ee16a9e14bf1ded4682597 kept task open; completed task generated 0 labels in LabelStore; snapshot unchanged. | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
| `R4-06` | `pass` | acc_c001_2 deduplicated=True; model.fit denied=True; C002 cases=0; report C001 related=240000000. | `Agent2_Spec_v2_1/evidence/R4/business_acceptance.json` |
