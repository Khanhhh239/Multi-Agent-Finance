"""Resumable v6 master (docs/05_ke_hoach_giao_viec/11_dang_ky_truoc_v6.md): h lock -> screening -> selection.

w is inherited from v5 (0.1, clarification of 2026-10-22). Matrices are the v5 matrices (not modified). Every step is a
bounded subprocess with checkpoints, so rerunning continues where it stopped. Progress: work/r6_master.log and
results/v6/R6/master_state.json. Synthetic data only.
"""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOG = ROOT / "work" / "r6_master.log"
OUT = ROOT / "results" / "v6" / "R6"
STATE = OUT / "master_state.json"
ENV = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
COMMON = ["--output", str(OUT), "--fraction", "0.1", "--threads", "6"]
HN = ("0.5", "1.0", "2.0")


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def state(**kw):
    OUT.mkdir(parents=True, exist_ok=True)
    s = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    s.update(kw, updated=time.strftime("%Y-%m-%d %H:%M:%S"), data_origin="dữ liệu tổng hợp")
    STATE.write_bytes(json.dumps(s, ensure_ascii=False, indent=1).encode("utf-8"))


def run(args, step):
    log(f"START {step}")
    state(step=step, status="running")
    with LOG.open("a", encoding="utf-8") as f:
        code = subprocess.run([PY, *args], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=ENV).returncode
    if code:
        state(step=step, status="failed", exit_code=code)
        log(f"FAILED {step} exit={code}")
        raise SystemExit(code)
    log(f"DONE {step}")


MAX_PARALLEL = 2     # 3 concurrent fits exceeded 16 GB RAM (commit 34 of 38 GB, paging 5000+/s): scheduling only


def parallel(jobs, step, limit=MAX_PARALLEL):
    """Run at most `limit` workers at a time; a finished worker is replaced by the next job."""
    log(f"START {step}: {len(jobs)} workers, at most {limit} at once")
    state(step=step, status="running")
    pending, running, codes = list(enumerate(jobs)), [], []
    while pending or running:
        while pending and len(running) < limit:
            k, args = pending.pop(0)
            out = (ROOT / "work" / f"r6_{step}_{k}.log").open("a", encoding="utf-8")
            running.append((subprocess.Popen([PY, *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=ENV), out))
            time.sleep(20)                  # stagger dataset construction peaks
        for item in list(running):
            code = item[0].poll()
            if code is not None:
                item[1].close()
                codes.append(code)
                running.remove(item)
        time.sleep(5)
    if any(codes):
        state(step=step, status="failed", exit_codes=codes)
        log(f"FAILED {step} exit={codes}")
        raise SystemExit(1)
    log(f"DONE {step}")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def stop(reason):
    state(step="R6_stopped", status="stopped", reason=reason)
    log(f"R6 STOPPED: {reason}")
    raise SystemExit(0)


DROP = ("L3-PU",)      # registration v6.1: removed from the selection tier by the owner (compute time)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "PU_locked.json").exists():              # inherited from v5, registered before any v6 result
        (OUT / "PU_locked.json").write_bytes(json.dumps(
            {"status": "inherited_from_v5", "w": 0.1, "data_origin": "dữ liệu tổng hợp"}, ensure_ascii=False).encode("utf-8"))
    if not (OUT / "HN_locked.json").exists():
        parallel([["-m", "agent2.screen_v5", "hn", *COMMON, "--hns", h] for h in HN], "HN_workers")
        run(["-m", "agent2.screen_v5", "hn", *COMMON], "HN_summary")
    if load("HN_locked.json")["h"] is None:
        stop("no eligible hard-negative weight (registration section 3)")
    log(f"registered hard-negative weight h = {load('HN_locked.json')['h']}")
    if not (OUT / "screening_summary.json").exists():
        parallel([["-m", "agent2.screen_v5", "screen", *COMMON, "--kinds", k] for k in ("L3-PU", "L4-PU-E2-AR")],
                 "screen_workers")
        run(["-m", "agent2.screen_v5", "screen", *COMMON], "screen_summary")
    roster = [k for k in load("screening_summary.json")["roster"]["supervised"] if k not in DROP]
    if not roster:
        stop("no eligible supervised candidate after screening")
    if not (OUT / "selection_summary.json").exists():
        parallel([["-m", "agent2.screen_v5", "select", *COMMON, "--kinds", k, "--drop", *DROP] for k in roster], "select_workers")
        run(["-m", "agent2.screen_v5", "select", *COMMON, "--drop", *DROP], "select_summary")
    state(step="R6_complete", status="done")
    log("R6 COMPLETE")


if __name__ == "__main__":
    main()
