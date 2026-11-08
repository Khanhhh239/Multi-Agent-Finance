# Synthetic demo runbook

Prerequisites: Python 3.11+, project dependencies and repo root as working
directory.

```bash
pip install -r requirements.txt
pip install -e . --no-deps
make demo
```

If `data/cfo_warehouse.duckdb` is absent, the demo deterministically rebuilds
it with seed 20251. Every output line is JSON and explicitly labeled fake.

API mode:

```bash
export AGENT4_DEMO_TOKEN='choose-a-local-token'
uvicorn agent4.text2sql.api:create_app --factory
curl -s http://127.0.0.1:8000/health/ready
curl -s http://127.0.0.1:8000/v1/query \
  -H "Authorization: Bearer $AGENT4_DEMO_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"api_version":"v1","question":"Biên lợi nhuận gộp quý 3/2026 là bao nhiêu phần trăm?","locale":"vi-VN","session_id":null,"options":{"include_table":true,"explain_metrics":true}}'
```

Expected demo paths: ready scalar, multi-metric month table, snapshot vs flow,
ratio, unsupported grouping, clarification and prompt-injection rejection.
Never describe these values as a real company result.
