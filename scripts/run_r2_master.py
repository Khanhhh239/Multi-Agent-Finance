"""Resumable R2 master: generation check -> matrices -> subsampling check -> PU -> screening -> selection -> Cold.

Every step is a fresh bounded subprocess whose outputs are checkpointed, so rerunning this script continues
where it stopped. Progress: work/r2_master.log and results/v5/R2/master_state.json. Synthetic data only.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOG = ROOT / "work" / "r2_master.log"
STATE = ROOT / "results" / "v5" / "R2" / "master_state.json"
WORLDS = range(1001, 1021)


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def state(**kw):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    s = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    s.update(kw, updated=time.strftime("%Y-%m-%d %H:%M:%S"), data_origin="dữ liệu tổng hợp")
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def run(args, step):
    log(f"START {step}: {' '.join(args)}")
    state(step=step, status="running")
    with LOG.open("a", encoding="utf-8") as f:
        code = subprocess.run([PY, *args], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                              env={**__import__("os").environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}).returncode
    if code:
        state(step=step, status="failed", exit_code=code)
        log(f"FAILED {step} exit={code}")
        raise SystemExit(code)
    log(f"DONE {step}")


def main():
    gen = ROOT / "results" / "v5" / "development"
    for s in WORLDS:
        if json.loads((gen / f"world_{s}.json").read_text(encoding="utf-8"))["status"] != "validated":
            raise SystemExit(f"world {s} not validated")
    mat = ROOT / "work" / "v5_matrices"
    for s in WORLDS:
        if not (mat / f"s{s}" / "manifest.json").exists():
            run(["-m", "agent2.base_v5", "--prepare-world", str(s)], f"prepare_base_{s}")
        if not (mat / f"s{s}" / "manifest_cd.json").exists():
            run(["-m", "agent2.base_v5", "--prepare-change-world", str(s)], f"prepare_change_{s}")
    r2 = ROOT / "results" / "v5" / "R2"
    fraction = None
    for f in (.1, .2):
        out = r2 / f"subsample_equivalence_{f}.json"
        if not out.exists():
            run(["scripts/check_subsample_equivalence.py", "--target", "1001", "--kind", "L4-PU", "--fraction", str(f),
                 "--out", str(out)], f"subsample_check_{f}")
        if json.loads(out.read_text(encoding="utf-8"))["passed"]:
            fraction = f
            break
    fraction = fraction or 1.0
    state(fraction=fraction)
    log(f"registered subsampling fraction = {fraction}")
    if not (r2 / "PU_locked.json").exists():
        run(["-m", "agent2.screen_v5", "pu", "--fraction", str(fraction)], "PU_screen")
    if not (r2 / "screening_summary.json").exists():
        run(["-m", "agent2.screen_v5", "screen", "--fraction", str(fraction)], "candidate_screen")
    if not (r2 / "cold_selection.json").exists():
        run(["-m", "agent2.screen_v5", "cold", "--fraction", str(fraction)], "cold_selection")
    if not (r2 / "selection_summary.json").exists():
        run(["-m", "agent2.screen_v5", "select", "--fraction", str(fraction)], "supervised_selection")
    state(step="R2_complete", status="done")
    log("R2 COMPLETE")


if __name__ == "__main__":
    main()
