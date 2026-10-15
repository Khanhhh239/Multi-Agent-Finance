import sys, time, json
sys.path.insert(0, ".")
from agent2.world_v4_sealed import generate_v4_sealed
from agent2.validate_v4 import validate_v4
for seed in (931, 932, 933):
    t = time.time()
    out = f"work/data/s4_s{seed}"
    generate_v4_sealed(out, n=200_000, rate=.004, seed=seed, companies=40)
    r = validate_v4(out)
    print(seed, "s", round(time.time() - t), "fraud", r["fraud_rows"], "cases", r["cases"], "schemes", r["schemes"],
          "shortcut", {k: round(v, 3) for k, v in r["shortcut_audit"].items()}, "conceal", r["concealment"], flush=True)
