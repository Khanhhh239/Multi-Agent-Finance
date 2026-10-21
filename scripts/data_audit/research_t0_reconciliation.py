"""Capture cited primary sources and read local papers; never execute external code."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0.data import read_json, write_json

PLAN = ROOT / "research/references/data-checks/t0/reconciliation-benchmark-plan-v1.json"


def capture(source, directory):
    path = directory / (source["id"] + ".raw")
    metadata = path.with_suffix(".json")
    if path.exists() or metadata.exists():
        if not path.is_file() or not metadata.is_file():
            raise ValueError("Incomplete source cache; preserve it and use a new snapshot")
        result = read_json(metadata)
        payload = path.read_bytes()
        if (hashlib.sha256(payload).hexdigest() != result["sha256"] or len(payload) != result["bytes"]
                or any(result.get(key) != source[key] for key in ("id", "url", "kind", "supports"))):
            raise ValueError("Cached source hash changed")
        return result
    result = {**source, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(source["url"], headers={"User-Agent": "T0-Research/1.0"}), timeout=30) as response:
            payload = response.read(12_000_001)
            if len(payload) > 12_000_000:
                raise ValueError("Source exceeds 12 MB capture limit")
            result.update(status=response.status, final_url=response.url,
                          bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                          content_type=response.headers.get("Content-Type"))
        path.write_bytes(payload)
        write_json(metadata, result)
    except Exception as exc:
        result.update(status="unavailable", error=type(exc).__name__ + ": " + str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/reconciliation_research/2026-10-19")
    parser.add_argument("--output", type=Path, default=ROOT / "data/T0/processed/source-audits/reconciliation-research.json")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Research report exists; choose a new --output to preserve history")
    plan = read_json(PLAN)
    raw = args.input
    raw.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(lambda source: capture(source, raw), plan["sources"]))
    # PDF parsing is an optional research dependency, never needed by the matcher.
    from pypdf import PdfReader
    local = []
    for path in sorted((ROOT / "research/references/papers/t0").glob("*.pdf")):
        pages = PdfReader(path).pages
        text = "\n".join(page.extract_text() or "" for page in pages)
        (raw / (path.stem + ".txt")).write_text(text, encoding="utf-8")
        local.append({"path": path.relative_to(ROOT).as_posix(), "pages": len(pages),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "extracted_characters": len(text)})
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
              "sources": sources, "local_papers_read": local,
              "scope": "Source access and local PDF text extraction; synthesis is maintained in t0-method-review.md. Not a business-data audit or a replication of published models."}
    write_json(args.output, report)
    print(json.dumps({"sources": len(sources), "available": sum(s["status"] == 200 for s in sources), "local_papers": len(local)}))


if __name__ == "__main__":
    main()
