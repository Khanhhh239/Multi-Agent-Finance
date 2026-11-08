# Performance report

Run `python scripts/benchmark_text2sql.py`. It executes 70 local synthetic
queries (seven shapes × ten repetitions) and writes measured p50/p95/max to
`reports/performance/latency_summary.json`.

This is a single-process local DuckDB measurement, not a concurrency/load test
or production SLO certification. Provider latency is absent because offline
selection is used. A production performance claim requires named hardware,
DB/provider, concurrency and data volume.

Observed local result on 2026-11-04: 70/70 requests returned `ready`; p50
19.123 ms, p95 150.231 ms, max 160.483 ms. Raw JSON:
`reports/performance/latency_summary.json`.
