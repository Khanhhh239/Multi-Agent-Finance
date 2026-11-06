"""Finish corrected bank diagnostics on source if the predeclared test gate stops.

This does not relax the gate, select another collection model, or create fresh
Worlds. The shared T4 settings and source cutoffs remain those locked in v2.
"""
from agent1.paths import ROOT
from agent1.data.world_manifest import load_cohort,sha256_file
from experiments.unified_collection_v2.data import PROTOCOL,read_json,write_json,verify_preserved
from experiments.unified_collection_v2.run import train_t4
from experiments.unified_collection_v2.evaluate import evaluate_bank


def main():
    p = read_json(PROTOCOL)
    out = ROOT/p["output_directory"]
    decision = read_json(out/"decision.json")
    if decision["decision"]!="stop_before_fresh_test":
        raise ValueError("This helper is only for a stopped confirmatory run")
    selection = read_json(out/"selection.json")
    cohort = load_cohort(ROOT/p["source_cohort"])
    t4 = train_t4(out,cohort,p)
    evaluate_bank(out,[e for e in cohort["worlds"] if e["role"]=="train"],p,selection,t4,"source_bank")
    integrity = verify_preserved(out)
    write_json(out/"source_diagnostic_completion.json",{**integrity,
        "source_sha256":sha256_file(__file__),"confirmatory_decision_unchanged":True,
        "fresh_worlds_created":False,"scope":"source bank diagnostics only; no collection refit or parameter selection"})


if __name__=="__main__":
    main()
