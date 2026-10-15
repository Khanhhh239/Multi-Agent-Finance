import sys, json, warnings
warnings.filterwarnings("ignore")
from agent2.bench import run_leave_family_out
from agent2.data import load
name = sys.argv[1]
df = load("work/data/" + name)
res = run_leave_family_out(df)
json.dump(res, open(f"work/results/lfo_{name}.json", "w"), indent=1)
print("done", name)
