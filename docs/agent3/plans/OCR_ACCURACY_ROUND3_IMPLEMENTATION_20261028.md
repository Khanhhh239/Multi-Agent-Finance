# OCR accuracy round 3 - implementation and evidence

Date: 2026-10-28. Plan: `PLAN_OCR_ACCURACY_ROUND3_20261028.md`.
All invoice content, references, crops, downloads and SQLite files stay in
ignored local data directories. No automatic confirmation or default-model
promotion is enabled.

## Implemented changes

- Extraction separates native text spans containing both tax-rate and tax-amount
  headings, preserving original value evidence. Mixed 8%/10% rows on pages 12-13
  are read from the actual row column, never copied from invoice totals.
- Buyer section labels are matched exactly, including `Co. name` and `Company
  name` glosses. A company starting with "DON VI" is not itself a new label.
  Footer labels and numeric-only company names do not create name values.
- Party names can continue over adjacent lines and stop before the next tax
  label. Unlabelled administrative address prose is not appended to issuer names.
  Address continuation supports word-level native PDF spans and both label/value
  indentation, with complete-value span checks to prevent truncating good fields.
- Recovery groups adjacent server-owned word spans into observed line crops,
  retaining all original evidence separately from the crop union rectangle.
  Limits remain two fields/four crops per run, four complete lines per field,
  bounded pixels and time. More lines are deferred, never silently truncated.
- Recovery policy v4 flags numeric-only names in existing PRESENT fields, long
  OCR lines and exact-arithmetic total mismatches. Flags only request review;
  they do not fabricate corrections. HUMAN_CONFIRMED values remain protected.

## Audit and controlled crop experiments

`scripts/invoice_accuracy.py` provides audit preparation, scope scoring, reviewed
label revision export, rescoring both candidates with the same revised labels,
bounded crop benchmarks, benchmark summarization, holdout admission and holdout
evaluation. The wrapper is `RUN_OCR_ACCURACY.cmd`.

The initial inventory binds 706 annotations and 171 errors to document hashes,
field paths, original block evidence and crop availability. Scope checks remain
separate from reference transcription and independent review. Unreviewed entries
are excluded from scoped metrics, not counted as successful OCR.

The visually checked VAT scope includes 64 paired outputs for 32 rows: 20 outputs
are row-printed and 44 refer to invoice-level VAT without a printed row column.
Those 44 missing row outputs are not automatically inferred or misrepresented as
independent recognizer failures. Existing 706-field reports are preserved.

A proposed address-reference revision was withdrawn after full-page QA found
repeated administrative address text beyond the crop. Its old exports remain
for audit, with a `retraction.json`; they are not authoritative scores. Original
labels are unchanged. Target 017 is excluded from the final crop oracle pending
independent review. Company-name references were unchanged: their observed
error was an English gloss retained in extraction.

150 real crop recognition requests were run: 20 fields/30 observed regions across
baseline 512 greedy, width 1024 greedy, width 1024 beam, original-PDF 300 DPI, and
the existing production region reader. References never enter model requests.
Each arm pins crop/model/config/runtime hashes and preserves raw responses.

A separate visually checked, complete-crop subset has 12 fields. Exact matches:
baseline 4/12, width 2/12, beam 2/12, PDF300 4/12, production 3/12. Incomplete
crop targets are excluded transparently from this subset. The sample does not
justify a new default recognizer. Timings are diagnostic batch timings under
uncontrolled workload, not end-to-end latency or an SLA measurement.

Local evidence:

- `agent3_tax_compliance/data/ocr_quality/invoice_accuracy_crops_20261028/`
- `agent3_tax_compliance/data/ocr_quality/invoice_accuracy_benchmark_final_20261028/`
- `agent3_tax_compliance/data/ocr_quality/invoice_accuracy_label_revision_20261028/retraction.json`

## Development comparison

Frozen source observations and the unchanged original DRAFT references:

| Metric | Previous round | Round 3 |
|---|---:|---:|
| Cases / labeled outputs | 28 / 706 | 28 / 706 |
| Correct | 535 | 565 |
| Wrong present | 43 | 32 |
| Missing/ambiguous | 128 | 109 |
| Discovered rows | 57 | 57 |

Field exact match is 80.03%. Errors decline 171 to 141 (17.54%). No previously
correct field changes to wrong/missing, and no new critical wrong-present field
is allowed. This is DEV, already used for tuning, with incomplete DRAFT labels;
it is not production accuracy or independent holdout accuracy.

The previous public pilot (15 variants/9 source invoices) retains its header
counts, including 44/44 total fields. Synthetic tests and browser results are
reported separately from invoice accuracy.

Recovery calibration on PRESENT fields is weak: the policy flags 1 of 32 known
wrong-present values and 8 of 511 correct-present values. Unflagged fields must
not be treated as correct. The final scope audit includes only 32 reviewed
outputs; 630 remain unreviewed and 44 are document-level VAT excluded from row
scoring. This subset is an error investigation, not an accuracy estimate.

## New public document evaluation

The extraction/recovery/config candidate was frozen before searching new public
documents. Four original PDF invoices (six pages) were fetched from the public
Ministry of Health document portal with verified HTTPS, maximum sizes and URL/
hash provenance. Two are unredacted positive examples; two contain redacted
numeric cells and are a separate negative group. Hidden PDF text under black
rectangles is not used to populate references.

One 150-DPI PNG derived from Unity is an additional OCR variant of the same
invoice, not a fifth independent invoice. The corpus is source-held-out, small,
self-labelled and may share invoice-provider layouts with DEV. It must not be
described as layout-independent or representative of production traffic.

Holdout admission rejects reused development files, source bundles or groups,
and records the extractor/recovery/config hashes. Evaluation rejects a changed
candidate, empty inputs or incomplete references, and records that test has been
opened. These documents cannot be used for further tuning while retaining their
holdout designation.

References and source provenance:
`invoice_test/public_unseen_20261028/verified_downloads/`.
Sealed inputs: `agent3_tax_compliance/data/ocr_quality/invoice_public_holdout_20261028/`.
Fresh evaluation: `agent3_tax_compliance/data/ocr_quality/invoice_public_holdout_eval_20261028/`.

The frozen evaluation completed all five cases and revalidated source hashes.
Extractor, recovery and OCR configurations still match the pre-search freeze.

| Case | Correct / labeled | Correct printed / printed | Correct absence / absence | Segmentation |
|---|---:|---:|---:|---|
| Unity PDF | 15 / 19 | 12 / 16 | 3 / 3 | SINGLE_CANDIDATE |
| Imall PDF | 1 / 19 | 0 / 18 | 1 / 1 | REVIEW_SPLIT |
| Khang Vu masked PDF | 32 / 49 | 20 / 22 | 12 / 27 | SINGLE_CANDIDATE |
| Micro Precision masked PDF | 24 / 43 | 0 / 19 | 24 / 24 | REVIEW_SPLIT |
| Unity derived PNG | 11 / 19 | 8 / 16 | 3 / 3 | SINGLE_CANDIDATE |

Neither positive PDF is wholly correct. The two REVIEW_SPLIT cases produce no
record, so their correct absence outputs must not be presented as extraction
success. Khang Vu has 15 unexpected PRESENT outputs against absence references;
numeric values underneath masking are not disclosed in these reports. Aggregate
percentages across positive, masked and derived cases would obscure these facts.

Read-only source review: `invoice_test/results/invoice_public_holdout_eval_20261028/review.html`.
Its browser check loads all seven images across five cases, checks desktop and
mobile overflow, and records no page errors. The local review includes visible
source pages and field outcomes, without hidden numeric values. The sanitized
aggregate is `docs/agent3/plans/evidence/ocr_accuracy_round3_20261028/summary.json`.

This evaluation is not sufficient to claim the planned >=90% DEV target or a
production acceptance gate. Default OCR, confirmed financial values, legal rules
and automatic acceptance policies remain unchanged.

Two downloaded PDFs use black Highlight annotations to obscure numeric values.
The current ingestion and regional PDF renderers use `annots=False`. These are
negative robustness cases; their native text and render path cannot establish
safe handling of visual masking. Reports show field outcomes without publishing
hidden numeric values. Any fix informed by these cases must treat them as DEV
and obtain new untouched documents for the next acceptance evaluation.

## Validation and remaining gates

The final aggregate records 582 passing Python tests, nine JavaScript syntax
checks, two Node checks and four Chrome regressions. Focused extraction, quality
and recovery suites were rerun after the last core change. The latest DEV review
HTML passes six browser checks with an image loaded, no page errors and 285 DOM
nodes. These are software regressions, separate from real-document accuracy.

The crop experiment does not support changing the default model. The 90% DEV
target remains unmet, labels remain incomplete, end-to-end latency was not
measured on a controlled workload, and a 100-200 invoice representative corpus
has not been collected. Priorities after this frozen evaluation are boundary
confirmation on ordinary single invoices, visible PDF annotation handling,
missing item quantity/unit price, and an independently reviewed larger corpus.

Latest DEV review: `invoice_test/results/invoice_accuracy_round3_release/review.html`.
Final verification: `agent3_tax_compliance/data/ocr_quality/validation_accuracy_round3_final_20261028/verification_final.json`.

## Commands

Choose a new output run ID for each invocation; existing runs are immutable.

```powershell
.\RUN_OCR_ACCURACY.cmd prepare --source-run invoice_accuracy_round3_release --run-id my_crop_run --category all --limit 20
.\RUN_OCR_ACCURACY.cmd benchmark --run-id my_crop_run --arm baseline
.\RUN_OCR_ACCURACY.cmd benchmark --run-id my_crop_run --arm width
.\RUN_OCR_ACCURACY.cmd benchmark --run-id my_crop_run --arm beam
.\RUN_OCR_ACCURACY.cmd benchmark --run-id my_crop_run --arm pdf300
.\RUN_OCR_ACCURACY.cmd benchmark --run-id my_crop_run --arm production
```

Review the source scope and complete-crop oracle before interpreting scores.
Use `score-audit`, `export-labels`, `compare-labels` and `summarize-benchmark`
for versioned comparisons. `holdout` seals new manifests with a current candidate
hash; `evaluate-holdout` runs that frozen candidate with reviewed references.
