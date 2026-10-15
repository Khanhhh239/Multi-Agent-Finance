import sys, time, os
sys.path.insert(0, ".")
from agent2.world_sealed import generate_sealed, ALL_SEALED, DECOYS_SEALED
from agent2.validate_v3 import validate_v3
for seed in (901, 902, 903):
    out = f"work/data/sealed_s{seed}"
    if not (os.path.exists(out) and os.listdir(out)):
        generate_sealed(out, seed=seed)
    r = validate_v3(out, expected_families=ALL_SEALED, extra_decoys=DECOYS_SEALED)
    print(seed, "valid; fraud", r["fraud_rows"], r["families"], flush=True)
