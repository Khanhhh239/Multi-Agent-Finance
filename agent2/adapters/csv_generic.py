"""CSV ingestion with explicit source-to-canonical mapping and timezone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .base import Adapter
from ..schema import validate_input


class CSVAdapter(Adapter):
    def __init__(self, mapping):
        self.mapping = yaml.safe_load(Path(mapping).read_text(encoding="utf-8-sig")) if isinstance(mapping, (str, Path)) else mapping
        if not isinstance(self.mapping, dict) or not isinstance(self.mapping.get("tables"), dict):
            raise ValueError("mapping requires a tables dictionary")
        try:
            ZoneInfo(self.mapping.get("timezone", "Asia/Ho_Chi_Minh"))
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("mapping timezone must be a recognized IANA timezone") from exc
        for name, spec in self.mapping["tables"].items():
            if not isinstance(name, str) or not name.isidentifier() or not isinstance(spec, dict):
                raise ValueError("mapping requires valid table names and table dictionaries")
            columns = spec.get("columns")
            if not isinstance(spec.get("file"), str) or not isinstance(columns, dict) or not columns:
                raise ValueError("each table requires a file and a non-empty column mapping")
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in columns.items()):
                raise ValueError("column mapping names must be strings")
            if not isinstance(spec.get("types", {}), dict):
                raise ValueError("types must be a dictionary")
        self.last_report = None

    def load(self, path):
        root = Path(path).resolve()
        timezone = self.mapping.get("timezone", "Asia/Ho_Chi_Minh")
        tables = {}
        for name, spec in self.mapping["tables"].items():
            source = (root / spec["file"]).resolve()
            if not source.is_relative_to(root):
                raise ValueError("source file must stay inside the input directory")
            columns = spec["columns"]
            if len(set(columns.values())) != len(columns):
                raise ValueError(f"duplicate canonical column in {name}")
            frame = pd.read_csv(source, dtype=str, keep_default_na=False, encoding=spec.get("encoding", "utf-8-sig"),
                                sep=spec.get("separator", ","))
            missing = set(columns) - set(frame)
            if missing:
                raise ValueError(f"missing source columns in {name}: {sorted(missing)}")
            frame = frame[list(columns)].rename(columns=columns)
            for col, kind in spec.get("types", {}).items():
                if col not in frame:
                    raise ValueError(f"type specified for unmapped column: {name}.{col}")
                if kind == "string":
                    frame[col] = frame[col].astype(str)
                elif kind in ("integer", "number"):
                    values = frame[col].replace("", pd.NA)
                    if spec.get("thousands_separator"):
                        values = values.str.replace(spec["thousands_separator"], "", regex=False)
                    if spec.get("decimal_separator", ".") != ".":
                        values = values.str.replace(spec["decimal_separator"], ".", regex=False)
                    values = pd.to_numeric(values, errors="raise")
                    frame[col] = values.astype("Int64") if kind == "integer" else values
                elif kind == "datetime":
                    def timestamp(value):
                        if not value:
                            return ""
                        dt = pd.Timestamp(value)
                        if dt.tzinfo is None:
                            dt = dt.tz_localize(timezone, ambiguous="raise", nonexistent="raise")
                        return dt.tz_convert("Asia/Ho_Chi_Minh").isoformat()
                    frame[col] = frame[col].map(timestamp)
                else:
                    raise ValueError(f"unsupported type: {kind}")
            tables[name] = frame
        self.last_report = validate_input(tables)
        if self.last_report["errors"]:
            raise ValueError(f"input validation failed: {json.dumps(self.last_report['errors'], ensure_ascii=False)}")
        return tables


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        raise SystemExit("refusing to overwrite a non-empty output directory")
    adapter = CSVAdapter(a.mapping)
    tables = adapter.load(a.input)
    a.out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        if not name.isidentifier():
            raise ValueError("table names must be identifiers")
        frame.to_csv(a.out / f"{name}.csv", index=False, encoding="utf-8-sig")
    (a.out / "input_report.json").write_text(json.dumps(adapter.last_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(adapter.last_report, ensure_ascii=False))


if __name__ == "__main__":
    main()
