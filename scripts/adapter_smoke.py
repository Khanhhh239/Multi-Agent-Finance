"""Round-trip a renamed synthetic ledger through the generic CSV adapter."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import yaml

from agent2.adapters.csv_generic import CSVAdapter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--world", type=Path, default=Path("work/data/w4_s411"))
    p.add_argument("--out", type=Path, default=Path("work/adapter_smoke"))
    a = p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        raise SystemExit("refusing to overwrite adapter smoke output")
    source, normalized = a.out / "source", a.out / "normalized"
    source.mkdir(parents=True)
    normalized.mkdir()
    mapping = {"timezone": "Asia/Ho_Chi_Minh", "tables": {}}
    originals = {}
    for name in ("transactions", "employees", "vendors", "customers", "companies", "bank_account_changes"):
        frame = pd.read_csv(a.world / f"{name}.csv", dtype=str, keep_default_na=False,
                            nrows=1000 if name == "transactions" else None)
        originals[name] = frame
        columns = {f"source_{c}": c for c in frame}
        frame.rename(columns={v: k for k, v in columns.items()}).to_csv(source / f"{name}.csv", index=False, encoding="utf-8-sig")
        spec = {"file": f"{name}.csv", "columns": columns}
        if name == "transactions":
            spec["types"] = {"amount_vnd": "integer", **{c: "datetime" for c in ("posted_at", "created_at", "approved_at")}}
        mapping["tables"][name] = spec
    config = a.out / "mapping.yaml"
    config.write_text(yaml.safe_dump(mapping, allow_unicode=True), encoding="utf-8")
    adapter = CSVAdapter(config)
    tables = adapter.load(source)
    assert tables["transactions"].transaction_id.tolist() == originals["transactions"].transaction_id.tolist()
    assert tables["transactions"].amount_vnd.tolist() == originals["transactions"].amount_vnd.astype(int).tolist()
    for name, frame in tables.items():
        frame.to_csv(normalized / f"{name}.csv", index=False, encoding="utf-8-sig")
    report = {"data_kind": "synthetic", "source_world": a.world.name, "id_and_amount_roundtrip": "passed", **adapter.last_report}
    (a.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
