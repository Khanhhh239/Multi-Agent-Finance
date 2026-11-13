# T1 compact: World training and observed landmark features

## Global to local family comparison, 13 November 2026

`global_local_families.py` compares continued Neural, LightGBM and XGBoost
on the same A1 sample (all eligible snapshots at the existing clocks, up to
12,000 weekly risk rows). Frozen family globals shared the original 100,000-row
pretraining table. Each family uses its own dated validation to select from
four algorithm-specific learning configurations and five pooling weights;
past audit accepts that locked choice or falls back to its own global.

The primary comparison pools each adapted model with its own standalone
family global. The retained Neural/customer global and previous A1 pipeline
remain explicit additional controls. Tree continuation appends trees and
verifies that the old trees and global artifacts remain unchanged.

Artifacts and the locked protocol are retained alongside the
[development report](../../outputs/t1/global_local_families_20261113/REPORT.md).
This reuses the preceding 75
inspected synthetic contexts; it does not open a new final test, select a
future per-enterprise winner, or activate a service model.

## Neural data-cap ablation, 13 November 2026

`neural_data_ablation.py` runs A0 (50 snapshots/day, 12,000 weekly risk rows),
A1 (all snapshots, 12,000 risk rows), and A2 (all snapshots/risk rows) from the
same frozen Neural. Validation, audit and development evaluation use the same
eligible census; training caps remain separate, including final local refits.
Sources, input hashes, Adam steps, invoice counts, predictions and final models
are retained in `outputs/t1/neural_data_ablation_20261113`.

The [development report](../../outputs/t1/neural_data_ablation_20261113/REPORT.md)
covers 75 already inspected synthetic contexts and explicitly separates the
primary study from subsequent Dai Phat update-budget diagnostics. It does not
open a new final test, train trees, or activate a tenant model.

## Corrected refit/adaptation study, 13 November 2026

Run `run_corrected_study.py` for the versioned cash-calendar study in
`outputs/t1/aligned_cashcalendar_20261113`. It retains the initial
`aligned_refit_20261112` evidence, corrects Paid event times when receipt posting
order differs from cash order, retrains global candidates/refit and tenant
adaptations, and verifies/reuses unchanged dated Workspace bundles. All feature
values, invoice keys, World seeds, splits and tuning budgets remain fixed.

The [measured report](../../docs/03_Evaluation/T1_REFIT_LOCAL_ADAPTATION_2026-11-13.md)
separates global, reweighted global, continued Neural, audited adaptation,
same-architecture local Neural and the existing Workspace pipeline. New-seed
Worlds are reused after the model-independent target repair; they are not
additional untouched Worlds after that repair. The refit failed its declared
audit. `release.json` selects the retained global artifact for explicit research
integration, subject to technical/SHAP checks, without activating any tenant.

T6 now exposes `simulation_paths=1000`, `shap_limit=30`, and
`simulation_seed=7`. All valid open invoices enter cash forecasting; SHAP limits
only explanations in the unchanged top-30 collection queue. Read the service
README for the research run/firm allowlist. The earlier AST budget experiment
is historical; current benchmarks call the public forecast parameters directly.

[Decision for general T1 → T6/SHAP, 12 November 2026](../../docs/03_Evaluation/T1_T6_SHAP_SELECTION_2026-11-12.md)
selects the frozen 18-feature Neural/customer ensemble as the general research
candidate, retaining company-specific challengers subject to dated local cash
validation. `selection_decision.json` records the artifact and scope. It does
not activate a synthetic model for every service tenant.

## Workspace comparison across the test Worlds, 12 November 2026

`compare_workspace_worlds.py` compares the unchanged Workspace model selection
procedure with the frozen 18-feature ensemble, previous 10-feature ensemble,
and empirical Survival reference on the same 5,486 eligible test landmarks:
three Worlds, eighteen firms, six origins, and 108 tenant/origin contexts.
Every local fit uses only that tenant's history available at its origin.
Insufficient local validation/audit windows retain the actual Workspace
customer-history fallback. Test firms are never pooled into global fitting.
This evaluates dated tenant adaptation on a reused test cohort; it is not a
fresh independent test or a new hyperparameter/ensemble search.

```powershell
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace_worlds.py --output agent1/outputs/t1/workspace_worlds_20261112 --init
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace_worlds.py --output agent1/outputs/t1/workspace_worlds_20261112 --world compact_06_test
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace_worlds.py --output agent1/outputs/t1/workspace_worlds_20261112 --world compact_07_test
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace_worlds.py --output agent1/outputs/t1/workspace_worlds_20261112 --world compact_13_test
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace_worlds.py --output agent1/outputs/t1/workspace_worlds_20261112 --summarize
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/review_world_comparison.py --output agent1/outputs/t1/workspace_worlds_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_serving_contexts.py --output agent1/outputs/t1/workspace_worlds_20261112 --prepare --summarize
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/review_serving_comparison.py --output agent1/outputs/t1/workspace_worlds_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/benchmark_serving_shap.py --output agent1/outputs/t1/workspace_worlds_20261112
```

The first three World commands may run independently. Firm checkpoints support
resumption; `precompute_workspace_world_firms.py` can precompute disjoint firms
without publishing partial World results. Completed checkpoints must remain
consistent with the protocol, source, model, and input hashes.

The first run exposed float32 XGBoost hazards losing probability mass. Runtime
hazards now use float64 before survival updates. `precision_amendment.json`
preserves the prior protocol and records retained checkpoints that had already
passed the unit-mass check. It does not retune candidates or thresholds. Use a
new output directory to start another run with different sources or settings.

`results.json`, `by_world.csv`, `by_firm.csv`, `by_origin.csv`, and `slices.csv`
use the original common World feature/partial-cash reference. The verifier
reproduces the three frozen global scores and all local checkpoint predictions.
Its paired bootstrap resamples firms within the three fixed Worlds, retaining
all origins of each firm. It does not quantify uncertainty over real SMEs.

`compare_serving_contexts.py` separately checks the actual Workspace bridge.
Dated claim revisions and receipt availability can change history features
and empirical partial-payment profiles relative to the World ledger builder.
`serving_results.json` and `serving_by_firm_origin.csv` score both models with
the actual serving features/profiles; they never overwrite the frozen World
results. `runtime_verification.json` records three full `forecast()` replays,
cash/probability agreement, and invariance to future records. Their zero opening
balances are smoke fixtures, not a bank-balance accuracy experiment.

`benchmark_world_shap.py` measures the frozen ledger reference;
`benchmark_serving_shap.py` uses the actual Workspace context. Both measure
separate invoice requests across all eighteen firms. Model loading and ledger
construction are outside the timed call, and feature preparation is included.

## Eighteen-feature comparison with Survival

The user's latest six-group feature table contains eighteen state features.
`landmark_features.py` implements all eighteen at the forecast origin. Counts
use `log1p`, delay histories use a 180-day window, trends express delay-days per
30 calendar days, and customer delay estimates shrink toward the firm history.
Open-balance shares use the current tenant's observed ledger.

| Group | State features |
|---|---|
| Invoice value and terms | Relative amount, payment term |
| Invoice age | Age at the forecast origin |
| Receipt state | Fraction received, receipt recency, receipt count, fraction received in the last 28 days |
| Customer history | Settlement count, typical delay, delay dispersion, delay trend |
| Company history | Typical delay, delay trend |
| Current debt | Customer and company overdue-balance shares at 30/90 days, customer's share of company outstanding |

```powershell
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/train_landmark.py --output agent1/outputs/t1/landmark18_survival_cash_20261112 --latency-inputs agent1/outputs/t6/baseline_workspace_trained_t1_20261112/inputs
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/verify_landmark.py --output agent1/outputs/t1/landmark18_survival_cash_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace.py --output agent1/outputs/t1/landmark18_survival_cash_20261112 --baseline agent1/outputs/t6/baseline_workspace_trained_t1_20261112
```

The prepared inputs preserve the exact eligible World/firm/origin/invoice keys
from the source experiment. Train and validation are prepared before selection.
Test preparation begins after `frozen.json` locks the selected artifact and
references. Each model receives the same observed landmarks and full-cash-paid
target over thirteen weeks. The empirical `survival` baseline uses age-stratified
hazards estimated from the same sampled weekly risk rows and sample weights.
Unpaid landmarks stay exposed through their mature horizon. A noncash writeoff
does not create a cash-paid event. Survival is evaluated as a reference and may
join the ensemble when its cached validation predictions improve the pool.

Selection uses weekly and cumulative cash errors, each normalized by the
outstanding claim of a World/firm/origin. The weekly component sums thirteen
absolute weekly errors. The cumulative component averages thirteen absolute
cumulative errors. Their declared weights are 0.5 each. Candidate cash predictions
include the same empirical partial-payment override as T6. Integrated Brier
across all thirteen weeks, weighted by outstanding amounts, constrains additions.
Brier at weeks four and thirteen remains available in the reports.

The whole-ensemble SHAP default uses a census for up to 512 open invoices.
Larger populations use 128 weighted stratified reference invoices. Three
additional samples measure sensitivity of contribution signs, magnitudes and
the strongest group. All samples share one union of evaluated background rows.
Duplicate hybrid inputs are evaluated once. Saved reference definitions contain
the selected invoices, prepared values and weights. `background_policy="legacy24"`
reproduces the earlier ten-feature explanation for retrospective comparisons.

The current reference population is the company's open invoices at that origin.
Company-wide inputs shared by those invoices enter the common prediction
baseline. Background sensitivity and predictive generalization across companies
or time are recorded as separate evaluation questions. The fixed-model audit
in `background_audit/` measures the earlier 24-row policy against a census.

The schema loader retains support for the earlier ten-feature artifacts.
Company-specific adaptation remains a separate validation question. Compare a
global model, a local model and their pooling weights on dated local validation
windows, then evaluate their frozen choice on later local observations.

## Cached validation ensemble

`train_ensemble.py` trains all eligible individual entries in the Workspace T1
catalog against the same prepared landmark tables. Each learned entry has two
predeclared tuning configurations, two CPU threads, and the same seeded sample
of at most 100,000 weekly risk rows with World/firm/origin weights. Rule and
empirical baselines use one fit. Ten shared state features are fixed before fit.

```powershell
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/train_ensemble.py --source agent1/outputs/t1/compact_world_20261112 --output agent1/outputs/t1/compact_ensemble_20261112_v3 --latency-inputs agent1/outputs/t6/baseline_workspace_trained_t1_20261112/inputs
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/verify_ensemble.py --output agent1/outputs/t1/compact_ensemble_20261112_v3
```

Full 14-bucket validation distributions are retained for every trial in
`trials/`, with the selected trial per model also in `validation_predictions/`.
`validation_rows.parquet` preserves their exact row alignment. Interrupted runs
resume completed fits after checking code, protocol, data, sample and artifact
hashes. `--selection-only` stops after freezing the configuration. Running the
same command subsequently evaluates that frozen artifact on test.

Selection starts with the best validation single model meeting the SHAP budget.
Greedy additions search positive weights on a 0.05 grid and retain at most three
members. An addition must lower mean Brier by at least 0.0001, improve at least
three of four validation windows by 0.00001, and limit any window regression to
0.001. These thresholds are declared in `protocol.json` before fitting.
`validation_residual_correlations.csv` records complementary error diagnostics.
Every individual candidate has an opportunity to contribute through this search.

Whole-ensemble grouped SHAP runs through the served distribution, including its
pooling weights. Probability calibration is identity in this experiment. The
gate requires a single-invoice p95 of at most one second in every measured
context, using twenty repetitions per context with model and ledger context
ready. Feature preparation is included. Contexts cover the largest open firm in
each validation World and, when supplied, the retained large Workspace inputs.

`frozen.json` locks features, members, weights, selection and artifact hashes
before test tables are loaded. `test_results.json` contains final evaluation of
the frozen pool and the validation-best single reference. The source experiment
already evaluated these synthetic test Worlds, so this run's final scores have
the scope of a reused reference holdout. `REPORT.md` and `verification.json`
record the measured outcome and independent recomputation.

Load the ensemble through the existing `load_workspace_bundle` API, passing its
`artifact/` directory. Member payloads and nested metadata are hash checked. The
loader also checks the serving-date boundary. Fitted sklearn objects use local
joblib payloads, and LightGBM text artifacts from the earlier experiment remain
supported.

## Earlier single-LightGBM experiment

Candidate experiment, 12 November 2026. No service model or database is activated
by these commands. The artifact can be passed explicitly into the existing
Workspace `forecast` function; company training remains available.

Run from the repository root using the root virtual environment:

```powershell
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/prepare_worlds.py --output agent1/outputs/t1/compact_world_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/audit_manifests.py --output agent1/outputs/t1/compact_world_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/train.py --output agent1/outputs/t1/compact_world_20261112
.\.venv\Scripts\python.exe agent1/experiments/t1_compact/compare_workspace.py --output agent1/outputs/t1/compact_world_20261112
```

The measured run is locked after test evaluation. Use a new directory and a new
declared experiment for any change to features, parameters, splits or sources.
`runtime_source/` and `source_snapshot.json` preserve the exact code used for
fitting; subsequent additions to preflight checks do not rewrite that evidence.

## Data contract

- Retained manifest hashes, embedded configs, config file hashes and v4 World
  roles are checked. Missing historical Parquet is not silently accepted as an
  existing World. Generation writes only new versioned directories.
- The original WDI/OxCGRT files are absent. New Worlds explicitly use the
  generator's documented fallback assumptions. The user accepted skipping
  byte-identical recovery. These data cannot reproduce historical scores.
- Four retained train configs contribute 12 selected firms each; two retained
  practical augmentation configs contribute 8 each. Two additional stress train
  seeds contribute 6 each. Total fit: 8 Worlds, 76 tenant histories.
- Two retained validation configs plus one new stress validation seed contribute
  18 separate firms. Test has two retained test configs plus one new stress seed,
  another 18 firms. Existing v6/practical/unified holdouts never enter fit.
- Additional stress assumptions increase delay/dispute and add credit or supply
  episodes. Seeds, dates and severity are fixed before scores. The two added
  stress train Worlds have 25% of initial World weighting; all eight fit Worlds
  have equal weight. Calm periods and recovery remain in their histories.
- Each tenant is processed separately. IDs key joins, sampling and group audits;
  they never become estimator features. Only ledger allocations available at
  origin contribute receipts. Private invoice/customer/shock truth is excluded.
- Fit landmarks: January 2020–September 2023, 28-day cadence, labels through
  December 2023. Validation: January–March 2024, labels through June 2024.
  Test origins: July 2024–September 2025, labels through December 2025.
- Every included landmark has 91 days of follow-up. Future claim changes,
  credit-note closures and late-known pre-origin cash are excluded from the
  fixed-claim full-cash target and counted. Results are conditional on this
  eligible population, not all ledger cases.
- There is no random invoice-week train/test split. Sample open invoices by a
  stable hash, cap each firm's contribution, and weight equally by World, firm
  and origin. Unpaid outcomes remain in the risk sets; no class oversampling.
- Feature and parameter choices use validation only. Test is read after saving
  the frozen candidate. Replayed historical test scenarios are reference tests;
  the extra stress seed is new, but all still share a simulator family.

## Bounded features and explanation

Ten candidate state scalars: relative amount, terms, age, fraction received,
receipt recency, recent customer/company delay, recent settlement count, customer
and company overdue-balance share. Fit the feature values at each historical
origin. Serving uses the same builder with current observed ledger context.
Freeze current state across the future distribution; only the forecast-week
coordinate advances. The final measured candidate retained **eight** scalars;
customer/company median delays were removed by validation ablation. One derived
future-week coordinate makes nine estimator inputs, not nine independent SHAP
players.

Origins/reference ideas: `agent1/models/features.py` (Khánh: relative amount,
age/term, customer history), `experiments/t1_competing_v6/features.py` (as-of
receipts/overdue shares), and `experiments/unified_collection_v2/core.py` (receipt
state and recency). No research model object replaces the Workspace estimator.

Exact interventional SHAP explains the **served four-week cumulative
probability**, grouped into at most six declared business groups (64 coalitions),
with at most 24 deterministic reference invoices. The selected model has five
active groups, hence 32 coalitions. Exactness concerns this finite grouped game;
it does not assert causal meaning, individual feature effects within groups,
representativeness or background stability. These limitations remain in saved
plans and in the UI. The old explanation protocol remains available to old T1.

The model is fit for 13 forecast weeks. For a longer Workspace horizon, its
remaining mass stays in the unresolved tail; it does not extrapolate untrained
weekly hazards. T6 partial-payment empirical overrides remain separate.

## Explicit Workspace usage

```python
from agent1.adaptive.compact_t1 import load_workspace_bundle
from agent1.adaptive.methods import forecast

bundle = load_workspace_bundle(
    "outputs/t1/compact_world_20261112/artifact", "2026-10-31"
)
plan = forecast(data, "2026-10-31", opening_balance, bundle)
```

The text LightGBM model is checked against its metadata hash and feature schema.
The loader refuses dates earlier than the fit/selection label boundary. This is
a retrospective synthetic experiment, not a claim that the artifact actually
existed in July 2024. No cross-tenant raw histories are embedded in the artifact.

The native artifact does not carry the local T2/collection/operating learners;
passing it alone uses existing fallbacks for those components. The comparison
therefore measures a frozen global T1 with unchanged T6 assumptions, and must
not be described as a fully accepted replacement for the company bundle.

Inspect `selection.json`, `data_audit.json`, `test_by_world.csv`, `test_results.json`,
`latency.json`, and the separate Workspace diagnostic. Lower Brier alone does not
establish calibrated probabilities or useful bank-balance intervals.
