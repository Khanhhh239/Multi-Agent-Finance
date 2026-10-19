# P2 experimental protocol

**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở). G0.7 OPEN / CHƯA ĐẠT. 22 Must cần duyệt trước pilot.

Authorized scope: Step 0 fixes; T2.1–T2.5 datasets/harness; T2.6 ordered ablations; at most three read-only metric calls; explanatory questions; stable 8B measurement. Stop at M2. No G1 claim unless every documented threshold passes on val AND final test; E-gold/accountant approval cannot be synthesized.

Splits: TRAIN=dev warehouse seed20251, val=71, test=9001. E1/E2 each 600/200/400; E3/E4 each150/50/100; E5 100/40/100; E6 400/100/300; E7 80/30/80; E8 60/20/60. Additional multi-metric/why cases are separately labeled. Each originating template belongs to exactly one split; normalized questions are globally disjoint. At least25% noise; each metric at least3 E1/E2 cases with two forms per split.

All labels and values derive from authored slots and the independent base-table oracle, never from LLM output. Engine results may be used for E6 verifier fixtures, but not gold finance values for E1/E2. The existing M1, retriever/preprocess smoke, 60-example bank and any other tuning question are excluded from reported metrics. Few-shot selection reads TRAIN only. No test previews, failure examples or row-level statistics before the final run. Warehouse reconciliation aggregates are allowed in Step0c.

Development fixes happen on TRAIN only. Val chooses configurations, without revising generated labels or training on val. All ablations use the same frozen val rows and seed; temperature0 uses one deterministic run. Target metric changes must be at least +1 percentage point and none of numeric faithfulness, unauthorized actions, injection blocking may regress. Report n/denominators, paired bootstrap95%CI (2000 resamples), latency/tokens, examples and limitations. Degenerate bootstrap intervals at 0/100% do not establish zero risk.

Order: B0 4B/8B (66 metric-specific native tools, no hints) → H2 → H1 k66/20/12/8/5 → H3 native/schema → H4 model×think → H7 counts/H8 VI/EN → H5 answer modes/H6 verifier → H13 quantization. Retain a change only by the preregistered rule; report rejected or unmeasured hypotheses explicitly. Safety is enforced for real execution in every configuration; a verifier-off experimental score never grants SQL/write capabilities.

Seal B* config/model/data/template hashes before opening test. The final runner creates an exclusive start marker, never repeats a completed test case, and permits no alternative config on test. Final report compares B0 vs B* on val and reports the single B* held-out run separately. No post-test tuning.

## Pre-validation audit and experiment sample plan (19/10/2026)

Before any val model measurement, the initial E1/E2 sampling loop was found to under-exercise synonyms and noise kinds. Language corpus v1 is retired; v2 cycles genuine normalized synonyms and all five noise kinds, then recomputes independent golds and E6 fixtures. Warehouse version stays v2.1. Preserve old manifest hashes; no labels are revised from model results. Behavior-template review remains valid because E3/E4/E5 did not change.

B0: full frozen val suites for both models. H2/H1/H3: full E1/E2/E5/E6/E8 val. H4/H7/H8/H5/H6/H13: fixed seed0 screening subset of100 E1 and100 E2, plus complete E5/E6/E8; every arm in a comparison uses exactly the same IDs. Report actual n, bootstrap CI and subset limitations. Reuse an already measured identical arm as reference; postprocessing-only replays must be labeled, with no claim of fresh routing latency. Reconfirm the chosen B* on the complete val suite before the sole held-out run.

Promotion requires >=1 percentage point target improvement and no Must regression. Thinking is also subject to the documented operational latency targets (p50<=6s,p95<=15s); a quality gain rejected for latency is not called a refuted accuracy hypothesis. Configurations without enough measured Must evidence cannot be promoted.

Exclude all prior tuning hashes, including any matching E7 turn. One unit test accidentally copied a held-out followup from generator source; no generated test record or model result was opened. The unit now uses TRAIN wording. The permanent exclusion hash prevents evaluating matching scenarios. Disclose exclusions and a conservative planned-denominator bound, rather than presenting the remaining sample as the full planned test. Never regenerate cleaner test questions from this failure.
