"""World creation and protection of preceding model artifacts."""
import json
from agent1.paths import ROOT,SYNTH
from agent1.data.world_manifest import code_provenance,create_world_manifest,sha256_file,verify_world_manifest
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import World,WorldConfig
from experiments.t1_competing_v6.run import write_json


def protected_files():
    directories = [ROOT/f"experiments/t1_competing_{v}" for v in ("v5", "v6")]
    directories += [ROOT/"outputs/data"/v for v in ("v4_shortpay_4shock_20261028", "v5_competing_risks_53w_20261028", "t1_competing_v6_20261101")]
    directories += list(SYNTH.glob("v4_shortpay_4shock_20261028*"))+list(SYNTH.glob("v6_holdout_20261101*"))
    files = []
    for d in directories:
        files += [d] if d.is_file() else [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in sorted(set(files))}


def fresh_worlds(out, cohort, p):
    registry = out/"fresh_holdout_registry.json"
    if registry.exists():
        return json.loads(registry.read_text(encoding="utf-8"))
    entries = []
    for entry in p["fresh_holdouts"]:
        directory = SYNTH/entry["name"]
        config = json.loads((SYNTH/entry["template"]/"config.json").read_text(encoding="utf-8"))
        config.update(name=entry["name"], seed=entry["seed"], n_firms=entry["n_firms"], write_xml=0)
        if (directory/"manifest.json").exists():
            manifest = verify_world_manifest(directory)
            if manifest["config"] != config:
                raise ValueError("Fresh configuration differs from locked protocol")
        elif directory.exists():
            raise ValueError("Incomplete fresh directory: refusing overwrite")
        else:
            print(f"Generating locked fresh World {entry['name']}", flush=True)
            parsed = {**config, "shock_schedule": [ShockEpisode(**s) for s in config["shock_schedule"]]}
            World(WorldConfig(**parsed)).run(directory)
            manifest = create_world_manifest(directory, {**code_provenance(), "source_data_sha256": cohort["source_data_sha256"]})
        entries.append({"name": entry["name"], "role": "fresh_test", "seed": manifest["seed"], "manifest_sha256": sha256_file(directory/"manifest.json")})
    write_json(registry, entries)
    return entries
