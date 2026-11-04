from __future__ import annotations

import json
from pathlib import Path

from agent4.text2sql.models import QueryRequest, QueryResponse, SemanticPlanDraft


def main() -> None:
    destination = Path("schemas")
    destination.mkdir(exist_ok=True)
    models = {
        "query_request.schema.json": QueryRequest,
        "query_response.schema.json": QueryResponse,
        "semantic_plan.schema.json": SemanticPlanDraft,
    }
    for filename, model in models.items():
        payload = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
        (destination / filename).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
