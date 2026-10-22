"""Prove that the hire_guard revision leaves already-validated development worlds byte-identical.

Regenerates the given seeds with the current code into work/parity/, compares the SHA-256 of every CSV with
the validated checkpoint, and records the proof. Only if every seed matches is the old generation plan
archived (never deleted) so the queue can continue with 1017-1020. All data are dữ liệu tổng hợp.
  python scripts/v5_hire_guard_parity.py --seeds 1001 1016
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, ".")
from agent2.runtime_v5 import limit_memory, sha256, write_json  # noqa: E402
from agent2.world_v5_dev import development_config, generate, generation_plan  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, nargs="+", default=[1001, 1016])
    p.add_argument("--generation", type=Path, default=Path("results/v5/development"))
    a = p.parse_args()
    limit_memory(6)
    proof = {"data_origin": "dữ liệu tổng hợp", "revision": "hire_guard (agent2/world_v5_dev.py)", "seeds": {}}
    for seed in a.seeds:
        recorded = json.loads((a.generation / f"world_{seed}.json").read_text(encoding="utf-8"))["file_hashes"]
        out = Path("work/parity") / f"v5dev_s{seed}"
        if out.exists():
            shutil.rmtree(out)
        generate(development_config(seed), out)
        actual = {path.name: sha256(path) for path in sorted(out.glob("*.csv"))}
        mismatches = sorted(n for n in set(recorded) | set(actual) if recorded.get(n) != actual.get(n))
        proof["seeds"][str(seed)] = {"csv_files": len(recorded), "mismatches": mismatches}
        print(seed, "mismatches:", mismatches, flush=True)
        shutil.rmtree(out)
    proof["status"] = "passed" if all(not v["mismatches"] for v in proof["seeds"].values()) else "failed"
    if proof["status"] == "passed":
        old = a.generation / "generation_plan.json"
        archive = a.generation / "hire_guard_revision"
        archive.mkdir(exist_ok=True)
        if old.exists():
            shutil.copy2(old, archive / "generation_plan_before_hire_guard.json")
        new = generation_plan(list(range(1001, 1021)))
        proof["new_source_hashes"] = new["source_hashes"]
        write_json(old, new)
    write_json(a.generation / "hire_guard_parity.json", proof)
    print(proof["status"])
    if proof["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
