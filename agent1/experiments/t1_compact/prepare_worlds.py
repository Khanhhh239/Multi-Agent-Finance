"""Replay selected firms in retained configs without overwriting historical evidence."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.synth.world import World, WorldConfig


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def design():
    cohort = json.loads((ROOT / "data/synthetic/v4_shortpay_4shock_20261028_cohort.json").read_text())
    entries = []
    for i, item in enumerate(cohort["worlds"]):
        entries.append(dict(template=item["name"], role=item["role"],
                            firms=12 if item["role"] == "train" else 6,
                            kind="retained_config_replay", selection_seed=26111200+i))
    for i in range(2):
        entries.append(dict(template=f"practical_v6_20261105_aug_supported_{i:03}",
                            role="train", firms=8, kind="retained_stress_config_replay",
                            selection_seed=26111300+i))
    # Additional seeds/scenarios are declared before any labels or model scores.
    for i, role in enumerate(("train", "train", "validation", "test")):
        entries.append(dict(template=cohort["worlds"][i]["name"], role=role, firms=6,
                            kind="additional_stress", seed=261112101+i,
                            selection_seed=26111400+i,
                            late_scale=1.55 if i % 2 == 0 else 1.35,
                            dispute_scale=1.6, stress_family="credit" if i % 2 == 0 else "supply"))
    return entries


def prepare(output):
    import numpy as np
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries = design()
    protocol = dict(version="compact-world-replay-v1", entries=entries,
                    note="Selected-firm regenerated data, not recovery of deleted historical Parquet. World roles stay locked; no prior test/holdout World enters training.",
                    sources={str(p.relative_to(ROOT)): digest(p) if p.exists() else None for p in (
                        ROOT/"agent1/synth/world.py", ROOT/"agent1/synth/calibration_vn.json",
                        ROOT/"data/raw/wdi_vn/wdi_vietnam.csv",
                        ROOT/"data/raw/oxcgrt/OxCGRT_compact_national_v1.csv")},
                    missing_raw_policy="Explicit generator fallback assumptions for absent WDI/OxCGRT; this is a new synthetic cohort, not byte-identical historical data or a real-data replay.")
    protocol_path = output/"generation_protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise ValueError("Generation inputs changed; use a new output directory")
    protocol_path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    from experiments.t1_compact.audit_manifests import audit

    audit(output)
    inventory = []
    for index, entry in enumerate(entries):
        start = time.monotonic()
        source = ROOT/"data/synthetic"/entry["template"]/"config.json"
        config = json.loads(source.read_text())
        name = f"compact_{index:02}_{entry['role']}"
        config["name"] = name
        config["write_xml"] = 0
        if entry["kind"] == "additional_stress":
            config.update(seed=entry["seed"], late_scale=entry["late_scale"],
                          dispute_scale=entry["dispute_scale"])
            # Exogenous shocks in both historical fit and evaluation windows.
            config["shock_schedule"] = config.get("shock_schedule", []) + [
                dict(family=entry["stress_family"], start=d, severity=1.25,
                     rise_weeks=3, peak_weeks=6, recovery_weeks=12,
                     reference_event="compact_predeclared_synthetic_stress")
                for d in ("2020-06-01", "2023-02-06", "2024-08-05", "2025-02-03")]
        rng = np.random.default_rng(entry["selection_seed"])
        firms = sorted(map(int, rng.choice(config["n_firms"], entry["firms"], replace=False)))
        directory = output/"worlds"/name
        receipt = directory/"replay_manifest.json"
        expected = dict(entry=entry, template_config_sha256=digest(source),
                        selected_firm_indices=firms, generated_config=config,
                        source_hashes=protocol["sources"])
        if receipt.exists():
            saved = json.loads(receipt.read_text())
            if any(saved.get(k) != v for k, v in expected.items()):
                raise ValueError(f"Replay definition changed: {name}")
            for file, sha in saved["files"].items():
                if digest(directory/file) != sha:
                    raise ValueError(f"Replay payload changed: {name}/{file}")
        else:
            if directory.exists() and any(directory.iterdir()):
                raise ValueError(f"Incomplete replay; inspect before rerunning: {directory}")
            print(f"Generating {name} ({entry['kind']}), firms={firms}", flush=True)
            World(WorldConfig(**config)).run(directory, firm_indices=firms, verbose=True)
            saved = dict(expected, files={p.name: digest(p) for p in directory.glob("*.parquet")},
                         seconds=round(time.monotonic()-start, 2))
            receipt.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        inventory.append(dict(name=name, role=entry["role"], kind=entry["kind"],
                              template=entry["template"], firms=entry["firms"],
                              directory=str(directory.relative_to(output)),
                              replay_manifest_sha256=digest(receipt)))
        (output/"inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Prepared {len(inventory)} worlds, {sum(e['firms'] for e in inventory)} firms", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
