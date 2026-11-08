# Selective visible native text and invoice-number review

Date: 2026-10-30. Follow-up to `OCR_RUNTIME_DIAGNOSTICS_20261029.md`.

## Changes

The PDF reader retains complete native text spans outside bounded Highlight and
Square annotation rectangles, with a one-point safety margin. A span intersecting
a mask or later filled path/image is withheld in full: masked numbers cannot
survive as prefixes or suffixes. Invisible text and spans extending outside the
visible crop are excluded. Native glyph/coverage trust policy must still pass.
Covered whitespace does not by itself force OCR.

Pages with selectively retained text use HYBRID processing against the original
visible page render. Unknown annotation types, widgets or unbounded paint geometry
retain the previous whole-page OCR fallback. Full-page and regional renders keep
annotation appearances. Original PDFs are never edited or exported as sanitized
redactions. This is conservative native admission, not proof that every possible
PDF clipping/appearance mechanism is understood.

The default route policy is `route-v1.3`. Upload idempotency fingerprints include
the policy and page-cache keys include the native blocks and page artifact, so
new filtered text does not reuse an old fused page. Historical artifacts and
confirmed values are not rewritten; restart the app/worker and ingest originals
in a fresh run to apply the new policy.

Visible native invoice numbers participate alongside OCR observations. If the
same header has different leading-zero readings, the number stays AMBIGUOUS with
both exact candidates and original evidence. No zero is trimmed, padded or
selected using evaluation labels. This prevents Micro Precision's OCR-only wrong
number from being promoted to PRESENT while retaining the source candidate for
human confirmation.

Extraction also recognizes exact short party labels `Đơn vị bán` and `Đơn vị mua`.
These labels do not match arbitrary whitespace prefixes of company names such
as `ĐƠN VỊ BÁN LẺ ABC`. Existing Decimal arithmetic, legal rules, model settings,
resource limits and manual-confirmation requirements remain unchanged.

## Verification protocol

Synthetic tests cover standard annotations, later vector/image overlays, all four
page rotations, cropped-page evidence transforms, unknown annotations, widgets,
partial masking of a numeric span, whitespace-only overlap, native trust-policy
failure and annotation budgets. An ingestion-to-extraction regression preserves
the visible native number and a conflicting OCR number as AMBIGUOUS candidates.

The existing 28-case / 706-output DEV extraction replay increases correct outputs
from 565 to 571, retains 32 wrong-present outputs, and leaves 103 missing/ambiguous.
No previously correct field regresses. Labels remain the unchanged DRAFT labels
used for development. This frozen-OCR extraction comparison does not measure the
new reader or independent accuracy.

`scripts/replay_invoice_reader.py` re-reads original PDFs and reuses raw OCR only
when source identity, rendered bytes, transforms, runtime and model configuration
match. It refuses missing responses rather than synthesizing successful OCR.
The full DEV reader replay is explicitly INCOMPLETE: 24 of 28 old cases require
fresh recognition that was not stored in their original native-only run. Only
four cases were replayable. Their partial results are not an aggregate acceptance
score. Fresh end-to-end validation is reported separately on the three previously
opened public documents; these remain DEV cases with self-reviewed references.

Local evidence:

- `agent3_tax_compliance/data/ocr_quality/visible_native_extraction_regression_20261030/`
- `agent3_tax_compliance/data/ocr_quality/visible_native_dev_replay_20261030/` (INCOMPLETE).
- `agent3_tax_compliance/data/ocr_quality/visible_native_public_replay_20261030_final/` (frozen OCR, fresh reader).
- `agent3_tax_compliance/data/ocr_quality/invoice_visible_native_20261030/` (fresh pipeline).

Example commands on the prepared local workspace; use a fresh output run ID:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\replay_invoice_reader.py --source-run invoice_visibility_serial_20261029 --run-id my_visible_native_replay
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\ocr_quality.py run --manifest agent3_tax_compliance/data/ocr_quality/invoice_visibility_boundary_dev_20261029/manifest.json --run-id my_visible_native_pipeline --split dev
```

The replay makes zero model calls and supplies no latency evidence. The fresh
pipeline uses isolated databases and sequential OCR; regression/model tests are
run afterward to avoid competing workloads. Sources, labels, images and databases
stay outside Git. New corpus collection and independent label review remain
outstanding before production acceptance or automatic confirmation.

## Fresh pipeline results

All five pages completed with fresh OCR, no cached responses and the existing
600-second page budget. Page OCR times were 85.5, 79.9, 74.2, 110.0 and 92.4
seconds. Model asset hashes match the preceding run. Timing differences across
these uncontrolled runs are not attributed to this code change or an SLA.

| Case | Previous correct | New correct / labelled | Correct printed / printed | Wrong present | Masked numeric slots unexpectedly filled |
|---|---:|---:|---:|---:|---:|
| Imall | 10 | 12 / 19 | 11 / 18 | 0 | No masked slots |
| Khang Vu | 35 | 36 / 49 | 9 / 22 | 0 | 0 / 15 |
| Micro Precision | 28 | 29 / 43 | 5 / 19 | 0 | 0 / 13 |

All three records remain reviewable `SINGLE_CANDIDATE` documents. Imall and Micro
Precision retain AMBIGUOUS invoice numbers with the printed reference available
as a candidate; Khang Vu's observed number is PRESENT. The Micro Precision
critical wrong-present number has become a required review, not an automatically
corrected value. Correct absence outputs are not recognized printed text. Many
visible fields remain missing or ambiguous, so there is no production approval.

An independent rectangle-intersection check on the freshly persisted ingestion
artifacts finds 364 retained native blocks on the three annotated pages, with
zero intersections with annotation bounds plus the safety margin. Whole-span
withholding is also checked by synthetic numeric-prefix tests. No masked numeric
reference slot is unexpectedly PRESENT in these two negative documents.

The local read-only report at
`invoice_test/results/invoice_visible_native_20261030/review.html` displays the
fresh database images, field outcomes and exact invoice-number candidates without
removing leading zeros. Its Chrome check loads all five images, verifies the two
Micro Precision candidates and checks desktop/mobile layout without page errors.
Images and candidate values remain local, outside Git.

[Published summary](evidence/visible_native_20261030/summary.json).

## Final software validation

`validation_visible_native_20261030/validation.json` records 603 passing Python
tests, nine JavaScript syntax checks, two Node checks and four Chrome regression
runners, all passing. Validation ran after fresh OCR completed. All app-source
hashes match the candidate used by the inference run, and the replay helper passes
AST parsing. These software tests are separate from the invoice scores above.

No main-branch merge or automatic invoice confirmation is part of this change.
