"""Check retained recipe/split identity without pretending deleted data exist."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import sha256


def audit(output):
    cohort_path = ROOT/"data/synthetic/v4_shortpay_4shock_20261028_cohort.json"
    cohort = json.loads(cohort_path.read_text())
    generation = json.loads((output/"generation_protocol.json").read_text())
    locked = {e["name"]: e for e in cohort["worlds"]}
    result = []
    for entry in generation["entries"]:
        directory = ROOT/"data/synthetic"/entry["template"]
        manifest = json.loads((directory/"manifest.json").read_text())
        config = json.loads((directory/"config.json").read_text())
        manifest_sha = sha256(directory/"manifest.json")
        config_ok = config == manifest["config"] and sha256(directory/"config.json") == manifest["config_sha256"]
        split_ok = entry["kind"] == "additional_stress" or entry["template"] not in locked or entry["role"] == locked[entry["template"]]["role"]
        lock_ok = entry["template"] not in locked or manifest_sha == locked[entry["template"]]["manifest_sha256"]
        if not (config_ok and split_ok and lock_ok):
            raise ValueError(f"Retained manifest/config/split mismatch: {entry['template']}")
        sources = {}
        for name, relative in (("calibration", "data/synthetic/calibration_fit.json"),
                               ("wdi", "data/raw/wdi_vn/wdi_vietnam.csv"),
                               ("oxcgrt", "data/raw/oxcgrt/OxCGRT_compact_national_v1.csv"),
                               ("shock_design", "data/synthetic/v4_shortpay_4shock_20261028_design.json")):
            if name not in manifest["source_data_sha256"]:
                continue
            path = ROOT/relative
            actual = sha256(path) if path.exists() else None
            sources[name] = dict(expected=manifest["source_data_sha256"][name], actual=actual,
                                 status="missing_explicit_synthetic_fallback" if actual is None else "matched" if actual == manifest["source_data_sha256"][name] else "changed")
        result.append(dict(template=entry["template"], new_role=entry["role"], kind=entry["kind"],
                           retained_manifest_sha256=manifest_sha, config_matches_retained_manifest=config_ok,
                           retained_cohort_manifest_hash_matches=lock_ok, retained_role_preserved=split_ok,
                           sources=sources, original_table_payloads_available=all((directory/f).exists() for f in manifest["tables_sha256"])))
    report = dict(status="recipe_and_roles_verified_new_synthetic_cohort", original_cohort_sha256=sha256(cohort_path),
                  original_payload_recovery_required=False,
                  policy="User permitted skipping byte-identical historical recovery. New data must keep its own manifests, hashes and evaluation; no fallback is passed off as the original dataset.",
                  entries=result)
    (output/"retained_manifest_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(status=report["status"], checked=len(result), all_configs_match=True, all_roles_preserved=True)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    audit(parser.parse_args().output.resolve())
