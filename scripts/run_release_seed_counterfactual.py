"""Research-only same-code control seeds and a paired macro counterfactual.

The counterfactual shifts only the 2025 common factor to a zero annual mean.
It is a sensitivity experiment, not a calibrated real-world scenario.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import create_world_manifest, source_provenance, verify_world_manifest
from agent1.paths import RAW, SYNTH
from agent1.synth.world import World, WorldConfig
from scripts.audit_existing_world_metrics import one_world


class Neutral2025MacroWorld(World):
    def macro(self):
        frame = super().macro()
        mask = frame.week.dt.year.eq(2025).to_numpy()
        shift = -float(np.mean(self.F[mask]))
        self.F[mask] += shift
        frame["common_factor"] = self.F
        self.macro_shift_2025 = shift
        return frame


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, nargs="+", default=list(range(94317, 94322)))
    p.add_argument("--output", type=Path,
                   default=Path("outputs/data/release_gate_audit_20261026"))
    args = p.parse_args()
    template = json.loads((SYNTH / "v5_lifecycle_control_94319/config.json").read_text(encoding="utf-8"))
    evidence = source_provenance(sources={
        "calibration": SYNTH / "calibration_fit.json",
        "oxcgrt": RAW / "oxcgrt/OxCGRT_compact_national_v1.csv",
        "wdi": RAW / "wdi_vn/wdi_vietnam.csv",
    })
    names = []
    for seed in args.seeds:
        for intervention in (["base", "neutral2025"] if seed == 94319 else ["base"]):
            name = f"v3_releasecheck_{seed}_{intervention}"
            cfg = WorldConfig(**{**template, "name": name, "seed": seed})
            dest = SYNTH / name
            if dest.exists():
                manifest = verify_world_manifest(dest, validate=True)
                if manifest["source_code_sha256"] != evidence["source_code_sha256"]:
                    raise ValueError(f"{name}: code changed; use a new research prefix")
                if manifest["config"] != json.loads(json.dumps(asdict(cfg))):
                    raise ValueError(f"{name}: config changed; use a new research prefix")
            else:
                world = Neutral2025MacroWorld(cfg) if intervention == "neutral2025" else World(cfg)
                world.run(dest, verbose=False)
                (dest / "intervention.json").write_text(json.dumps({
                    "kind": intervention,
                    "definition": ("2025 common_factor shifted by a constant to zero mean; "
                                   "2019-2024 path preserved") if intervention == "neutral2025"
                                  else "unchanged generator macro path",
                    "common_factor_shift_2025": getattr(world, "macro_shift_2025", 0.0),
                }, indent=2), encoding="utf-8")
                create_world_manifest(dest, evidence)
            names.append(name)
            print(name, flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row for name in names for row in one_world(SYNTH / name)]).to_csv(
        args.output / "same_code_seed_metrics.csv", index=False)
    (args.output / "seed_counterfactual_provenance.json").write_text(json.dumps({
        "worlds": names, "source_code_sha256": evidence["source_code_sha256"],
        "source_data_sha256": evidence["source_data_sha256"],
        "commit": evidence["commit"],
    }, indent=2), encoding="utf-8")
    print(f"{len(names)} worlds -> {args.output}", flush=True)


if __name__ == "__main__":
    main()
