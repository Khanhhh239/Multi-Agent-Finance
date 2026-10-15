import sys, time
sys.path.insert(0, ".")
from agent2.world_v3 import generate_v3
from agent2.validate_v3 import validate_v3
for seed in (201, 202, 203, 204, 205):
    t = time.time()
    out = f"work/data/w3_s{seed}"
    m = generate_v3(out, n=100_000, rate=.003, seed=seed, companies=8)
    r = validate_v3(out)
    print(seed, round(time.time() - t), "fraud", m["actual_fraud_rows"], "tenureAUC", round(r["vendor_tenure_auc_among_vendor_rows"], 3), flush=True)
