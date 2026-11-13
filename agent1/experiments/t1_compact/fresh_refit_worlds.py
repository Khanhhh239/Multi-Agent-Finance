"""Predeclared new weight-validation, audit and test Worlds; no score-based seeds."""
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from agent1.adaptive.compact_t1 import sha256
from agent1.synth.world import World, WorldConfig
from experiments.t1_compact.aligned_data import write, landmarks
from experiments.t1_compact.train import world_ledgers
from agent1.adaptive.ledger_bridge import workspace_data


DESIGN = [
    dict(role=role, seed=261112901+i, scenario=scenario, firms=6)
    for i, (role, scenario) in enumerate([
        ("weight_validation", "baseline"), ("weight_validation", "credit"),
        ("audit", "baseline"), ("audit", "supply"),
        ("fresh_test", "baseline"), ("fresh_test", "credit"), ("fresh_test", "supply"),
    ])
]
ORIGINS = {
    "weight_validation": ["2024-07-01", "2024-09-30", "2024-12-30"],
    "audit": ["2025-04-07", "2025-06-30"],
    "fresh_test": ["2025-04-07", "2025-06-30", "2025-09-29"],
}
ONBOARDING = dict(role="fresh_test", seed=261113999, scenario="short_history", firms=6, start="2025-01-01")


def generate_onboarding(source, output):
    """Declared before candidate scoring; a company with only 3/6/9 months of data."""
    template = json.loads((source / "worlds/compact_00_train/config.json").read_text(encoding="utf-8"))
    name = "refit_07_fresh_test_onboarding"
    config = dict(template, name=name, seed=ONBOARDING["seed"], start=ONBOARDING["start"], write_xml=0)
    config["shock_schedule"] = [r for r in config["shock_schedule"] if r["start"] >= config["start"]]
    firms = sorted(map(int, np.random.default_rng(ONBOARDING["seed"]+100).choice(config["n_firms"], 6, replace=False)))
    design = dict(**ONBOARDING, config=config, selected_firm_indices=firms, origins=ORIGINS["fresh_test"])
    path = output / "onboarding_design.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != design:
        raise ValueError("Onboarding design changed")
    write(path, design)
    directory = output / "worlds" / name
    receipt = directory / "manifest.json"
    if not receipt.exists():
        World(WorldConfig(**config)).run(directory, firm_indices=firms, verbose=False)
        write(receipt, dict(config=config, firm_indices=firms, files={p.name:sha256(p) for p in directory.glob("*.parquet")}))
    inventory = json.loads((output / "fresh_inventory.json").read_text(encoding="utf-8"))
    if not any(e["name"] == name for e in inventory):
        inventory.append(dict(**ONBOARDING, name=name, directory=str(directory.relative_to(output)), manifest_sha256=sha256(receipt)))
        write(output / "fresh_inventory.json", inventory)


def generate(source, output):
    template = json.loads((source / "worlds/compact_00_train/config.json").read_text(encoding="utf-8"))
    definition = dict(design=DESIGN, origins=ORIGINS, template=template,
                      generator_sha256=sha256(Path(__file__).resolve().parents[2] / "agent1/synth/world.py"),
                      raw_policy="Generator fallback assumptions; simulator-family synthetic, not real SME validation.")
    protocol = output / "fresh_world_design.json"
    if protocol.exists() and json.loads(protocol.read_text(encoding="utf-8")) != definition:
        raise ValueError("Fresh World design changed")
    write(protocol, definition)
    inventory = []
    for i, entry in enumerate(DESIGN):
        name = f"refit_{i:02}_{entry['role']}"
        directory = output / "worlds" / name
        receipt = directory / "manifest.json"
        config = dict(template, name=name, seed=entry["seed"], write_xml=0)
        if entry["scenario"] != "baseline":
            config.update(late_scale=1.55, dispute_scale=1.6)
            config["shock_schedule"] = config["shock_schedule"] + [
                dict(family=entry["scenario"], start=d, severity=1.25,
                     rise_weeks=3, peak_weeks=6, recovery_weeks=12,
                     reference_event="aligned_refit_predeclared_synthetic_stress")
                for d in ("2023-02-06", "2024-08-05", "2025-02-03", "2025-07-07")]
        firms = sorted(map(int, np.random.default_rng(entry["seed"]+100).choice(config["n_firms"], entry["firms"], replace=False)))
        if not receipt.exists():
            if directory.exists() and any(directory.iterdir()):
                raise ValueError(f"Incomplete World: {directory}")
            print(f"Generating {name}: {entry['scenario']}, firms={firms}", flush=True)
            World(WorldConfig(**config)).run(directory, firm_indices=firms, verbose=False)
            write(receipt, dict(config=config, firm_indices=firms,
                                files={p.name: sha256(p) for p in directory.glob("*.parquet")}))
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved["config"] != config or saved["firm_indices"] != firms:
            raise ValueError("World input changed")
        for name_, digest in saved["files"].items():
            if sha256(directory / name_) != digest:
                raise ValueError("World payload changed")
        inventory.append(dict(**entry, name=name, directory=str(directory.relative_to(output)),
                              manifest_sha256=sha256(receipt)))
        write(output / "fresh_inventory.json", inventory)
    return inventory


def prepare(output, role):
    import pandas as pd
    paths = []
    for entry in json.loads((output / "fresh_inventory.json").read_text(encoding="utf-8")):
        if entry["role"] != role:
            continue
        path = output / "prepared" / f"{entry['name']}.parquet"
        if not path.exists():
            parts = []
            label_end = "2025-03-31" if role == "weight_validation" else "2025-12-31"
            for firm, ledger in world_ledgers(output / entry["directory"]):
                data = workspace_data(ledger)
                for origin in ORIGINS[role]:
                    frame = landmarks(ledger, data, origin, label_end, entry["name"], firm, role)
                    if len(frame):
                        parts.append(frame)
                print(f"Prepared {entry['name']}/{firm}", flush=True)
            frame = pd.concat(parts, ignore_index=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
            write(path.with_suffix(".json"), dict(sha256=sha256(path), world=entry["name"], role=role,
                                                 manifest_sha256=entry["manifest_sha256"], rows=len(frame)))
        receipt = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if sha256(path) != receipt["sha256"]:
            raise ValueError("Prepared new World changed")
        paths.append(path)
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
