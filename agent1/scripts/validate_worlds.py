"""Đo bất biến dữ liệu; không huấn luyện/chọn mô hình trên miền niêm phong."""
import argparse
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.contracts import validate_world
from agent1.paths import SYNTH, OUT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worlds', default='src,tgt,sens_uk,sens_coface')
    args = parser.parse_args()
    results = []
    for world in args.worlds.split(','):
        result = validate_world(SYNTH / world, raise_on_error=False)
        result.insert(0, 'world', world)
        results.append(result)
        print(world, f"{result['passed'].sum()}/{len(result)} passed", flush=True)
    result = pd.concat(results, ignore_index=True)
    (OUT / 'wp0').mkdir(exist_ok=True)
    result.to_csv(OUT / 'wp0' / 'world_contracts.csv', index=False)
    return 0 if result['passed'].all() else 1


if __name__ == '__main__':
    raise SystemExit(main())
