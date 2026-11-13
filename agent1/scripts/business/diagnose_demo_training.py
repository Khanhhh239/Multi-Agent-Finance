"""Reproduce company training on the fictional input files, with stage timings."""

import os

os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path
import psutil

if __name__ == "__main__" and psutil.virtual_memory().available < 3 * 1024**3:
    raise SystemExit("Requires 3 GiB free RAM before starting job")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from threadpoolctl import threadpool_limits
from agent1.adaptive.data import parse_rows, suggested_mapping
from experiments.t1_compact.historical_workspace import train, Method
from agent1.adaptive.operating import select_operating

if __name__ == "__main__":
    data = {}
    for path in sorted((ROOT / "pilot/demo_dai_phat").glob("*.csv")):
        kind = path.stem.split("_", 1)[1]
        raw = pd.read_csv(path, dtype=str)
        rows, errors, _ = parse_rows(
            raw,
            kind,
            suggested_mapping(raw.columns, kind),
            date_format="%Y-%m-%d",
            number_format="plain",
        )
        assert not errors
        data[kind] = rows
    original = Method.fit

    def timed_fit(self, frame, clock):
        started = time.monotonic()
        print("FIT", self.variant, len(frame), flush=True)
        result = original(self, frame, clock)
        print(
            "FIT_DONE", self.variant, round(time.monotonic() - started, 2), flush=True
        )
        return result

    Method.fit = timed_fit
    with threadpool_limits(limits=2):
        start = time.monotonic()
        bundle = train(data, "2026-10-31", lambda s: print(s, flush=True))
        print("T1_T2_DONE", round(time.monotonic() - start, 2), flush=True)
        bundle["operating"] = select_operating(data, "2026-10-31", True)
        print("ALL_DONE", round(time.monotonic() - start, 2), flush=True)
