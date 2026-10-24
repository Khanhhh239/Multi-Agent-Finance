"""Export reviewer-confirmed legitimate cases, anonymised, for the shared feedback corpus (read-only on the store).

  python scripts/export_feedback_labels.py --db work/service/review.sqlite --approval-ref "LS-2026-001" \
      --salt-file secret.txt --out feedback_corpus.json
Refuses without an approval reference and a salt. Do not commit the output or the salt file.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from agent2.feedback_export import export_confirmed_legitimate  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--approval-ref", required=True, help="reference to the written legal approval")
    p.add_argument("--salt-file", type=Path, required=True, help="file holding the secret salt (kept outside Git)")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = export_confirmed_legitimate(a.db, a.salt_file.read_text(encoding="utf-8").strip(), a.approval_ref)
    a.out.write_bytes(json.dumps(result, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({"records": result["count"], "out": str(a.out)}))


if __name__ == "__main__":
    main()
