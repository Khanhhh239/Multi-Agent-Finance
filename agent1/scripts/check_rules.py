"""Liệt kê quy tắc chưa xác minh hoặc quá 12 tháng, xuất CSV để rà soát."""
import argparse
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.rules import all_rules
from agent1.paths import OUT


def main():
    p = argparse.ArgumentParser(); p.add_argument('--asof', default='2026-10-16'); args = p.parse_args()
    df = pd.DataFrame(all_rules())
    reviewed = pd.to_datetime(df.reviewed_on)
    df['needs_review'] = ~df.verified | reviewed.isna() | (reviewed < pd.Timestamp(args.asof)-pd.DateOffset(months=12))
    directory = OUT / 'rules'; directory.mkdir(exist_ok=True)
    df.to_csv(directory / 'rules_review.csv', index=False)
    print(f'{df.needs_review.sum()}/{len(df)} rules require review')


if __name__ == '__main__':
    main()
