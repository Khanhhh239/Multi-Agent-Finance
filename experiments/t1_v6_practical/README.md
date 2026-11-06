# V6 practical feature study (P0-P4)

This isolated experiment compares original v6, v6 + 14 dated industry features,
v6 + 15 ledger behavior features, and v6 + both. The five hypothetical
`macro_credit_*` features are excluded. Nothing activates a service model.

`ledger.PracticalFeatureBuilder` is the real-input boundary. It requires an
explicit set of authorized seller tenants and accepts only registered invoice,
append-only ledger entry, export-coverage, and dated industry columns. Receipt
and credit amounts may be signed to represent append-only reversals. A missing
or stale ledger is missing, not an observed zero. No opening balances are inferred
for invoices predating declared complete history; those invoices remain missing.
Customers with any such uncovered older invoice also keep missing behavior
features for newer invoices. Unknown due dates make overdue shares missing,
not an observed absence of arrears.

The input schemas and units are defined in `ledger.py`. `known_at` controls
visibility; `event_date` controls the accounting effective date. Delay is the
positive number of days from due date to **observed settlement recognition**,
clipped at 240, rather than an inaccessible true bank settlement. Partial and
overdue shares are weighted by remaining ledger balance. Collection ratio is
net receipts newly known during the last 28 days divided by previous open
balance plus invoices newly learned during that window. Ratios with no valid
denominator remain missing. Changes require the corresponding historical
as-of snapshots, not a backdated reconstruction using today's knowledge.
The current experiment is VND-only. Real callers must validate a single common
currency before projecting input columns; this module does not convert FX.

All model weeks use the same feature values frozen at forecast cutoff.
The risk set and terminal labels match v6. The legacy 64-feature baseline still
has its original synthetic observation assumptions; adding realistic features
does not make every baseline input production-ready.

There are no real SME records connected for this study. `sidecars.py` creates a
**new synthetic ERP observation process** with assumptions fixed in
`design.py`: one-day invoice/ledger ingestion, seven-day write-off ingestion,
quarterly industry exports with 14-day lag and 75% buyer coverage. It uses ledger
posting dates and ledger invoice allocations, which can be imperfect. Industry
records are explicitly simulated, not asserted to have existed in old Worlds.
Real callers must provide actual sourced records and knowledge timestamps.

`run.py` locks protocol, code, environment, source provenance and input hashes
before fitting. It reproduces the original baseline, fits the four arms on
identical 200,000 source rows, and selects on 2024 invoice anchors from eight
reserved companies per source World. These companies never enter fit. They are
source selection data, not a new independent test or a leave-World-out study.

P3 checks source support. If more than 10% of finite source-selection values
of tenure/customer history/firm history fall outside fit min/max, a separate
augmentation study adds two source Worlds with different shock regimes. The
original 2016 warm-up plan failed before writing data because economic rules
only cover 2019 onward; the amendment is recorded before any augmented fit or
fresh generation. This branch does not resolve tenure support. It fits both an augmented baseline and the
primary-selected feature set on identical augmented data. Added Worlds do not
change the original four-arm ablation population.

P4 generates four new Worlds with predeclared seeds, episode timing, durations,
and intensities only after `final_selection.lock.json` exists. All arms are
reported; fresh results and industry-missing sensitivity never select again.
Old `test_000` observations are not loaded for modeling. Preservation may hash
historical files. Results remain synthetic, conditional on one generator family.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m experiments.t1_v6_practical.run --stage all
```

Stages `prepare`, `primary`, `select`, and `fresh` support inspected/resumable
execution. Existing artifacts must have exactly matching hashes and protocol.
Use a new output directory for different experiments; do not overwrite outputs.
