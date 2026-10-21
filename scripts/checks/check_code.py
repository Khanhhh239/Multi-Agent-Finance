"""Compile repository Python and validate JSON/JSONL without executing code.

Raw/interim/processed data, environments and external reference code are out of
scope. Historical evidence is parsed read-only, never rewritten or remeasured.
"""

from collections import Counter
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0.data import read_json, read_jsonl

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}


def iter_sources(root):
    root = Path(root).resolve()
    for current, dirs, files in os.walk(root):
        directory = Path(current)
        relative = directory.relative_to(root).parts
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not (relative[:1] == ("data",) and d in {"raw", "interim", "processed"})
                         and not (relative == ("research", "references") and d == "code")
                         and not (directory / d).is_symlink())
        for name in sorted(files):
            path = directory / name
            if path.suffix.lower() in {".py", ".json", ".jsonl"}:
                yield path


def check_repository(root=ROOT):
    root = Path(root).resolve()
    errors, counts = [], Counter()
    for path in iter_sources(root):
        name = path.relative_to(root).as_posix()
        counts[path.suffix.lower()] += 1
        try:
            if not path.resolve().is_relative_to(root):
                raise ValueError("file points outside repository")
            if path.suffix.lower() == ".py":
                compile(path.read_text(encoding="utf-8-sig"), name, "exec", dont_inherit=True)
            elif path.suffix.lower() == ".jsonl":
                read_jsonl(path)
            else:
                read_json(path)
        except (OSError, ValueError, TypeError, SyntaxError) as exc:
            errors.append(f"{name}: {exc}")
    return errors, dict(sorted(counts.items()))


def main():
    errors, counts = check_repository()
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Python/JSON checks: {counts}; errors={len(errors)}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
