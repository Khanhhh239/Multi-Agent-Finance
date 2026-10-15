"""Optuna chỉ chọn trên nguồn, cửa sổ trước test ít nhất 120 ngày; không đọc tgt."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
import optuna

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models import t1
from agent1.paths import OUT
from run_t1 import snapshots, censor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=50)
    parser.add_argument('--origin', default='2024-07-01')
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()
    O = pd.Timestamp(args.origin)
    cal_hi, cal_lo = O - pd.Timedelta(days=120), O - pd.Timedelta(days=183)
    S = snapshots('src', pd.date_range('2019-07-01', cal_hi, freq='14D'), tag='tune_source')
    train = censor(S[S.cutoff < cal_lo], cal_lo)
    valid = censor(S[S.cutoff.between(cal_lo, cal_hi)], O)
    directory = OUT / 't1'; directory.mkdir(exist_ok=True)
    study = optuna.create_study(direction='minimize', sampler=optuna.samplers.TPESampler(seed=args.seed),
                                pruner=optuna.pruners.MedianPruner(), study_name=f'source_{args.origin}',
                                storage=f"sqlite:///{(directory / 'tune_source.sqlite3').as_posix()}", load_if_exists=True)

    def objective(trial):
        params = dict(num_leaves=trial.suggest_int('num_leaves', 15, 127),
                      min_data_in_leaf=trial.suggest_int('min_data_in_leaf', 50, 800, log=True),
                      lambda_l2=trial.suggest_float('lambda_l2', .1, 50, log=True),
                      feature_fraction=trial.suggest_float('feature_fraction', .5, 1),
                      learning_rate=trial.suggest_float('learning_rate', .02, .1),
                      bagging_fraction=trial.suggest_float('bagging_fraction', .5, 1), seed=args.seed)
        start = time.monotonic()
        # Từng chặng cho phép pruner và giới hạn thời gian; mục tiêu là pinball.
        model = None
        for step in range(6):
            model = t1.HazardGBM(params, rounds=100).fit(train, init_model=model.booster if model else None)
            loss = t1.evaluate_quantiles(valid.remaining, t1.quantiles_from_hazard(model.hazards(valid)))['pinball_avg']
            trial.report(loss, step)
            if trial.should_prune() or time.monotonic() - start >= 720:
                raise optuna.TrialPruned()
        trial.set_user_attr('train_seconds', time.monotonic() - start)
        return loss

    study.optimize(objective, n_trials=args.trials)
    study.trials_dataframe().to_csv(directory / 'tuning_trials.csv', index=False)
    (directory / 'best_params.json').write_text(json.dumps(dict(params=study.best_params, seed=args.seed,
        validation_pinball=study.best_value, origin=args.origin, training_label_end=str(cal_lo.date()),
        calibration_last_cutoff=str(cal_hi.date()), test_used=False), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
