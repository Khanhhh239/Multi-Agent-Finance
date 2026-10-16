"""Verify the documented A1 environment and world fingerprints without scoring.

This gate must pass before the development study or one-shot evaluation.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
from pathlib import Path


EXPECTED = {
    "w4_s411": (800, 194, 30), "w4_s412": (801, 196, 30), "w4_s413": (806, 190, 30),
    "s4_s931": (800, 154, 37), "s4_s932": (801, 174, 37), "s4_s933": (807, 150, 37),
}


def check_fingerprints(data: Path, names=None):
    checks = {}
    for name in names or EXPECTED:
        expected = dict(zip(("fraud_rows", "cases", "schemes"), EXPECTED[name]))
        path = data / name / "validation_v4.json"
        if not path.exists():
            checks[name] = {"status": "missing", "expected": expected}
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        actual = {k: report.get(k) for k in expected}
        ok = actual == expected and report.get("status") == "passed"
        checks[name] = {"status": "passed" if ok else "mismatch", "expected": expected, "actual": actual}
    return {"status": "passed" if all(v["status"] == "passed" for v in checks.values()) else "blocked", "worlds": checks}


def environment():
    packages = ("numpy", "pandas", "scikit-learn", "lightgbm", "scipy", "joblib", "pyarrow", "pytest", "PyYAML", "defusedxml", "Flask")
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": {p: importlib.metadata.version(p) for p in packages}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("work/data"))
    p.add_argument("--out", type=Path, default=Path("work/results/a1_repro.json"))
    p.add_argument("--worlds", nargs="+", choices=list(EXPECTED))
    a = p.parse_args()
    result = {"environment": environment(), **check_fingerprints(a.data, a.worlds)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
