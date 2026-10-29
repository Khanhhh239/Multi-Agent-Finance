# Invoice boundaries and visible PDF content

Date: 2026-10-29. Follow-up to `OCR_ACCURACY_ROUND3_IMPLEMENTATION_20261028.md`.

## Behavior changes

Native PDF text and OCR can disagree about leading zeros in the same invoice
number box. Previously, any two distinct readings prevented the whole record
from being extracted with `REVIEW_SPLIT`. Segmentation now groups observations
only when their original evidence overlaps on the same page. Different readings
in that one location remain separate candidates in an AMBIGUOUS invoice-number
field, while other fields can be reviewed. No candidate is selected or rewritten.

Spatial grouping requires mutual overlap and comparable box dimensions. Every
member must agree with every other member, so one oversized OCR box cannot join
independent headers. Separate header locations or pages with different reading
sets still require boundary confirmation. Missing geometry cannot bypass this
check. This change does not automatically split a PDF into accepted invoices.

Full-page and original-PDF regional rendering now include annotation appearances.
The reader withholds all native text on pages containing annotations or widgets,
and on pages where a later filled path/image overlaps earlier visible text. Such
pages use full-page OCR of the rendered appearance, without native-text fusion.
The source PDF is preserved. Annotation, widget, paint-operation, pixel and byte
budgets remain bounded; region rendering retains its source-hash checks.

The default route policy is `route-v1.2`. Its configuration participates in upload
idempotency fingerprints. The changed region renderer participates in recovery
implementation hashes, so old region results are not reused under the new reader.
No model, legal rule, confirmed value or automatic-acceptance policy is changed.

## Verification protocol

- Synthetic extraction cases cover one disputed header, repeated disputed headers
  across pages, distinct headers with different leading zeros, actual different
  invoice numbers, unavailable geometry, and oversized bridge boxes.
- Synthetic PDFs cover black Highlight and rectangle annotations, vector/image
  overlays, rotation, backgrounds painted before text, annotation budgets, and
  exact full-page/crop pixel comparison with visible annotation appearances.
- Retry accounting uses a definite timeout error; a separate real sleeping worker
  checks OS-enforced timeout behavior. The prior 1 ms parser-startup assumption
  was intermittent under load; the original failed validation log is preserved.
- The existing 28-invoice frozen-OCR replay isolates segmentation from recognition.
  It does not evaluate the changed PDF reader or end-to-end latency.
- The four previously opened public invoices are now development regression
  sources. Their original reports and labels remain unchanged. Read-only source
  audits check visible renders and native-text withholding; fresh pipeline runs
  are reported separately, including OCR failures.

Local evidence directories:

- `agent3_tax_compliance/data/ocr_quality/invoice_segmentation_replay_20261029_v2/`
- `agent3_tax_compliance/data/ocr_quality/pdf_visibility_source_audit_20261029_v3/`
- `agent3_tax_compliance/data/ocr_quality/validation_pdf_visibility_boundary_20261029/`
- `agent3_tax_compliance/data/ocr_quality/invoice_visibility_boundary_fix_20261029/`

## Limits and migration

Final verification passes **593 Python tests**, nine JavaScript syntax checks,
two Node checks and four Chrome regressions. The final aggregate uses the
explicitly successful 30-test ingestion rerun; the original failed log and
validation report are retained. See local `verification_final.json` in the
validation directory and the [published summary](evidence/pdf_visibility_boundary_20261029/summary.json).

The source audit passes for all six pages of the four public PDFs. Full-page
render bytes match visible annotation rendering. All three annotated pages
have zero native blocks and route through OCR. Both annotated PDF crop checks
match the visible source pixels at 300 DPI. Frozen observations for Imall and
Micro Precision now produce `SINGLE_CANDIDATE` with an `AMBIGUOUS` invoice
number, preserving respectively two and four candidates. Those checks do not
select a number or claim fresh recognition success.

The 28-invoice frozen extraction replay retains 565/706 correct fields, 32
wrong-present and 109 missing/ambiguous outputs under the original DRAFT labels.
It makes no recognition or fresh-reader accuracy claim. The fresh pipeline run
was aborted after Imall's OCR exceeded the existing 600-second limit; the two
remaining cases were interrupted. The partial report is explicitly ABORTED,
not a completed accuracy evaluation. No timeout, absent output or unprocessed
case is counted as successful recognition. End-to-end evaluation must be rerun
on an available runtime before claiming those accuracy gates.

Historical ingestion artifacts, crops, exports and human-confirmed records are
not rewritten. To check an old masked document with the new reader, ingest the
original into a fresh run with a new idempotency key; an extraction-only replay
of old native observations cannot repair historical visual masking.

This is conservative visibility routing, not a general PDF redaction sanitizer
or proof of production accuracy. Benign annotations can also force OCR and add
latency. Transparent, malformed or unusual PDF appearances may need further
review. The original document can still contain hidden text; it is never edited
or exported as a safely redacted replacement. OCR can still misread visible text,
and a disputed invoice number still needs human confirmation.

Boundary detection still depends on observed invoice-number headers. Unlabelled
headers or different invoices sharing the same observed number are not proven
to be a single invoice by this check; manual boundary review remains necessary.

An independent larger acceptance corpus and controlled latency measurements
remain outstanding. These development fixes do not enable automatic acceptance.
