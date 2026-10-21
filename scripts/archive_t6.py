from pathlib import Path
import sys
import shutil
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT


def main():
    directory=OUT/'t6';metrics=directory/'t6_interval_metrics.csv'
    if not metrics.exists():return
    df=pd.read_csv(metrics)
    if 'measurement_version' not in df or not df.measurement_version.str.contains('-v4-').all():return
    archive=directory/'v4_without_owner_policy';archive.mkdir(exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and not (archive/path.name).exists():shutil.copy2(path,archive/path.name)


if __name__=='__main__':main()
