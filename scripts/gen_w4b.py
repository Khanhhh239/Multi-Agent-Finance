import sys, time, json
sys.path.insert(0, ".")
from agent2.world_v4 import generate_v4
from agent2.validate_v4 import validate_v4
for seed in (411, 412, 413):
    t = time.time()
    out = f"work/data/w4_s{seed}"
    m = generate_v4(out, n=200_000, rate=.004, seed=seed, companies=48)
    g = time.time() - t
    r = validate_v4(out)
    print(seed, "gen s", round(g), "total s", round(time.time() - t), "fraud", r["fraud_rows"], "cases", r["cases"], "schemes", r["schemes"],
          "gaps", r["scheme_split_gaps"], "shortcut", {k: round(v, 3) for k, v in r["shortcut_audit"].items()},
          "levels", r["perpetrator_level"], "collusion", r["collusion"], flush=True)

