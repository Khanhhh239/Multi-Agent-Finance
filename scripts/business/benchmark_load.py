"""Synthetic mechanical load test. Size is the number OPEN; no predictive-quality claims."""

import argparse
from datetime import date, timedelta
import platform
from pathlib import Path
import sys
import time
import threading
import psutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.methods import forecast


def run(n):
    proc = psutil.Process()
    result = dict(
        open_invoices=n,
        platform=platform.platform(),
        processor=platform.machine(),
        ram_gib=round(psutil.virtual_memory().total / 2**30, 2),
        available_gib=round(psutil.virtual_memory().available / 2**30, 2),
    )
    if n >= 10000 and psutil.virtual_memory().available < 3 * 2**30:
        return dict(**result, status="deferred_ram_below_3_gib")
    clock = date(2026, 1, 1)
    data = dict(invoices=[], payments=[], outflows=[])
    for i in range(n):
        day = clock - timedelta(days=i % 120)
        data["invoices"].append(
            dict(
                invoice_id=str(i),
                customer_id=str(i % 150),
                amount=100000.0 + i,
                issue_date=str(day),
                known_at=str(day),
                due_date=str(day + timedelta(days=30)),
            )
        )
    done = threading.Event()
    samples = [proc.memory_info().rss]

    def monitor():
        while not done.wait(0.05):
            samples.append(proc.memory_info().rss)

    worker = threading.Thread(target=monitor)
    worker.start()
    try:
        start = time.perf_counter()
        first = forecast(data, str(clock), 1000000.0)
        batch = time.perf_counter() - start
        start = time.perf_counter()
        forecast(data, str(clock), 1000000.0, delay_days=14, shared_customer_risk=True)
        scenario = time.perf_counter() - start
    finally:
        done.set()
        worker.join()
    assert first["open_invoices"] == n
    return dict(
        **result,
        status="measured_baseline",
        batch_seconds=batch,
        scenario_seconds=scenario,
        peak_rss_mib=max(samples) / 2**20,
        within_batch_budget=batch <= 300,
        within_scenario_budget=scenario <= 3,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[2000, 10000, 50000])
    args = parser.parse_args()
    out = ROOT / "outputs/business"
    out.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame([run(n) for n in args.sizes])
    table.to_csv(out / "load.csv", index=False)
    print(table.to_string(index=False))
