# OCR stage diagnostics and sequential development regression

Date: 2026-10-29. Follow-up to `OCR_PDF_VISIBILITY_AND_BOUNDARIES_20261029.md`.

## Instrumentation

The bounded worker now records a small, best-effort progress snapshot in its
private temporary workspace. Stages distinguish worker imports, Torch/Paddle
imports, detector/recognizer loading, detection and each recognition crop.
Snapshots contain timings, region counts and crop dimensions, never recognized
text or reference labels. Failed attempts retain the last snapshot in worker
metrics before temporary cleanup. Retry attempts clear the previous snapshot.
Malformed or unavailable diagnostic files do not replace the worker error.

Successful VietOCR responses include separate detection and recognition stage
timings. The quality runner saves these alongside model-load time, whole-page
time, peak job memory and cache/lifecycle information. Stage times are diagnostic
wall times, including their stage overhead; they are not calibrated throughput
or production latency guarantees.

Model weights, decoding settings, numeric extraction and the 600-second default
page timeout are unchanged. Diagnostic files do not relax the response byte,
process, memory, source-hash or request-correlation checks. The changed runtime
source participates in runtime fingerprints; restart existing app/worker clients
before using this build.

## Investigation protocol

A separate 120-second, one-attempt diagnostic probe stopped in recognition after
detection found 74 regions. Its timeout was intentional and is not an accuracy
result. Model initialization and detection had completed; it was not evidence
that those imports were permanently stuck.

The three previously opened public sources are rerun in fresh databases, with
original labels and visual PDF masking preserved. They remain DEV samples.
The OCR run is sequential and does not overlap regression/model tests launched
by this agent. Other machine activity is not controlled, so the runner retains
`workload_controlled=false`.

Local evidence:

- Diagnostic probe: `agent3_tax_compliance/data/ocr_quality/ocr_timeout_profile_probe_20261029/`.
- Sequential pipeline: `agent3_tax_compliance/data/ocr_quality/invoice_visibility_serial_20261029/`.
- Sources and labels: `agent3_tax_compliance/data/ocr_quality/invoice_visibility_boundary_dev_20261029/manifest.json`.

On a workspace containing that sealed local manifest, use a fresh run ID:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\ocr_quality.py run --manifest agent3_tax_compliance/data/ocr_quality/invoice_visibility_boundary_dev_20261029/manifest.json --run-id my_serial_regression --split dev
```

Run OCR before starting the regression validator or another model benchmark.
Keep defaults while diagnosing; increasing timeouts or accepting partial OCR
text would not establish correctness. Downloaded sources, labels, databases and
temporary progress files remain excluded from Git.

## Interpretation

Imall completed a fresh, uncached OCR page in about 220 seconds: model load 38.4
seconds, detection 45.8 seconds and recognition 130.2 seconds. Recognition is the
largest measured component on that page. Extraction produced a reviewable record
with 10/19 labelled outputs correct; this is not a production accuracy estimate.

The earlier 600-second failure occurred while replay and validation workloads
were also running. Successful serial execution is consistent with resource
contention contributing to that failure, but does not prove it was the only
cause. No general timeout-resolution or latency-SLA claim follows from one page.
Masked references and absent fields must be reported separately from printed
fields, and invoice-number ambiguity still requires human confirmation.

## Completed fresh pipeline

All three cases / five pages completed in fresh databases, with no OCR timeouts,
no cached page responses and the original 600-second default unchanged. Per-page
OCR wall times were 220.2, 200.1, 174.2, 211.4 and 93.0 seconds. The runtime
inventory confirms that model assets match the earlier public-source run.
These few, uncontrolled samples do not establish an SLA or prove that every
future timeout has been resolved.

| DEV case | Correct / labelled | Correct printed / printed | Wrong present | Unexpected present in masked numeric slots |
|---|---:|---:|---:|---:|
| Imall | 10 / 19 | 9 / 18 | 0 | No masked numeric slots |
| Khang Vu | 35 / 49 | 8 / 22 | 0 | 0 / 15 |
| Micro Precision | 28 / 43 | 4 / 19 | 1 | 0 / 13 |

All three segmentation results are `SINGLE_CANDIDATE`. The remaining wrong-present
output is Micro Precision's invoice number, a critical field that still needs
source review. Correct absence outputs are not recognized printed values and
must not inflate the apparent recognition accuracy. Conservative OCR-only routing
protects masked content but loses some otherwise useful native text; visible
field completeness remains poor. This is verification of bounded execution and
mask handling on known DEV cases, not production acceptance.

The new local review uses page images read from each fresh ingestion database,
checks image/source hashes, and displays field outcomes without exposing hidden
numeric values:
`invoice_test/results/invoice_visibility_serial_20261029/review.html`.
Its browser check loads all five images and verifies desktop/mobile layout with
no page errors. The older review HTML is a historical result and is not replaced.

After inference completed, the affected OCR, quality and recovery suites passed
152 Python tests, including three new checks for timeout progress retention,
stale retry snapshots and malformed diagnostics. Changed runtime files pass AST
parsing. The runner and all app-source hashes still match those captured at the
start of the fresh run. Source-image hashes match the independent rendering audit
from the previous visibility fix, and all annotated pages retain zero native
blocks. Functional regression evidence remains separate from real-invoice scores.
Local test evidence: `agent3_tax_compliance/data/ocr_quality/validation_ocr_runtime_20261029/validation.json`.

[Machine-readable evidence](evidence/ocr_runtime_serial_20261029/summary.json)
records page timings, printed-field counts, masked-slot checks and provenance.
No automatic acceptance is enabled. Restart app/worker clients to load the
instrumented runtime; use fresh runs when evaluating existing sources.
