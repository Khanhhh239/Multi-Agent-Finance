"""R3/R4 driver (only after the pre-seal gate passes). Synthetic data only.

  python scripts/run_sealed_v5.py generate      # dry-run seed 5199 then 5101-5104: generate, validate V1-V12, hash
  python scripts/run_sealed_v5.py prepare       # base + change matrices into work/v5_sealed_matrices
  python scripts/run_sealed_v5.py dryrun        # V13 field-presence audit on 5199, then full evaluation path on 5199
                                                #   -> results/v6/sealed_v6_dryrun.json
  python scripts/run_sealed_v5.py evaluate      # ONE run on 5101-5104 -> results/v6/sealed_v6.json
Sealed world folders are named v5dev_s<seed> only because the preparation code expects that prefix.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "work" / "data_sealed_v5"
GEN = ROOT / "results" / "v6" / "sealed_generation"
MAT = ROOT / "work" / "v5_sealed_matrices"
SEEDS = [5199, 5101, 5102, 5103, 5104]


def one_world(seed):
    from agent2.runtime_v5 import limit_memory, sha256, write_json
    from agent2.validate_v4 import validate_v4
    from agent2.world_v5_sealed import generate_sealed
    limit_memory(6)
    checkpoint = GEN / f"world_{seed}.json"
    if checkpoint.exists():
        return
    directory = DATA / f"v5dev_s{seed}"
    began = time.monotonic()
    generate_sealed(seed, directory)
    report = validate_v4(directory, run_shortcut=True)
    checks = {f"V{i}": "passed" for i in range(1, 13)}
    write_json(checkpoint, {"status": "validated", "seed": seed, "checks": checks, "validation": report,
                            "seconds": time.monotonic() - began, "data_origin": "dữ liệu tổng hợp",
                            "file_hashes": {p.name: sha256(p) for p in sorted(directory.glob("*.csv"))}})


def prepare_one(seed):
    from agent2.base_v5 import prepare_change_world, prepare_world
    from agent2.runtime_v5 import limit_memory
    limit_memory(6)
    if not (MAT / f"s{seed}" / "manifest.json").exists():
        prepare_world(seed, DATA, MAT, GEN)
    if not (MAT / f"s{seed}" / "manifest_cd.json").exists():
        prepare_change_world(seed, DATA, MAT)


def sub(args):
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    code = subprocess.run([sys.executable, *args], cwd=ROOT, env=env).returncode
    if code:
        raise SystemExit(code)


def new_separations(findings, baselines):
    """V13 findings on the dry-run world that no development world showed (encoding artefacts to review)."""
    known = {(f["txn_type"], f["column"]) for base in baselines for f in base["findings"]}
    return [f for f in findings if (f["txn_type"], f["column"]) not in known]


def audit_dry_run():
    """V13 on the dry-run world only (never on 5101-5104): stop if the encoding added a field-presence shortcut."""
    import importlib.util
    from agent2.runtime_v5 import write_json
    spec = importlib.util.spec_from_file_location("audit_field_presence", ROOT / "scripts" / "audit_field_presence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baselines = [json.loads((ROOT / "results" / "v5" / f"field_presence_{s}.json").read_text(encoding="utf-8"))
                 for s in (1001, 1010, 1020)]
    findings = module.audit(DATA / "v5dev_s5199")
    new = new_separations(findings, baselines)
    write_json(GEN / "field_presence_5199.json", {"data_origin": "dữ liệu tổng hợp", "findings": findings, "new": new,
                                                  "baseline_worlds": [1001, 1010, 1020]})
    if new:
        raise SystemExit(f"V13: {len(new)} new field-presence separations on 5199; review before any evaluation: {new}")


def main():
    stage = sys.argv[1]
    if stage == "world":
        one_world(int(sys.argv[2]))
    elif stage == "prepare_one":
        prepare_one(int(sys.argv[2]))
    elif stage == "generate":
        if not (ROOT / "results" / "v6" / "v6_frozen.json").exists():
            raise SystemExit("freeze first: sealed worlds are generated only after the pre-seal gate passed")
        for seed in SEEDS:                         # each world in its own bounded process
            sub([__file__, "world", str(seed)])
    elif stage == "prepare":
        for seed in SEEDS:
            sub([__file__, "prepare_one", str(seed)])
    elif stage == "dryrun":
        audit_dry_run()
        sub(["-m", "agent2.sealed_v5", "evaluate", "--seeds", "5199", "--out", "results/v6/sealed_v6_dryrun.json",
             "--sealed-matrices", str(MAT)])
    elif stage == "evaluate":
        if not (ROOT / "results" / "v6" / "sealed_v6_dryrun.json").exists():
            raise SystemExit("run the dry run first")
        sub(["-m", "agent2.sealed_v5", "evaluate", "--sealed-matrices", str(MAT)])
    print(json.dumps({"stage": stage, "status": "done"}))


if __name__ == "__main__":
    main()
