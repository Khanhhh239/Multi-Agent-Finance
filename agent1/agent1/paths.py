from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
SYNTH = DATA / "synthetic"
OUT = ROOT / "outputs"
CALIBRATION = ROOT / "agent1" / "synth" / "calibration_vn.json"

for _p in (RAW, INTERIM, PROCESSED, SYNTH, OUT):
    _p.mkdir(parents=True, exist_ok=True)
