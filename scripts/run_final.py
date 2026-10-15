import sys, subprocess
py = sys.executable
dev = [f"work/data/w3_s{s}" for s in (201, 202, 203, 204, 205)]
sealed = [f"work/data/sealed_s{s}" for s in (901, 902, 903)]
subprocess.run([py, "-W", "ignore", "-m", "agent2.final_eval", "dev", "--dev", *dev, "--out", "work/results/final_dev_ext.json"], check=True)
subprocess.run([py, "-W", "ignore", "-m", "agent2.final_eval", "sealed", "--dev", *dev, "--sealed", *sealed, "--out", "work/results/final_sealed.json"], check=True)
