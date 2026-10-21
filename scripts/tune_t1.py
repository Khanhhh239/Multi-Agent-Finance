"""Optuna chỉ chọn trên nguồn, cửa sổ trước test ít nhất 120 ngày; không đọc tgt."""
import argparse
import json
from pathlib import Path
import sys
import time
import hashlib
import gc
import subprocess
import threading
import queue
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
    parser.add_argument('--max-train', type=int, default=120000)
    parser.add_argument('--max-valid', type=int, default=40000)
    args = parser.parse_args()
    O = pd.Timestamp(args.origin)
    cal_hi, cal_lo = O - pd.Timedelta(days=120), O - pd.Timedelta(days=183)
    S = snapshots('src', pd.date_range('2019-07-01', cal_hi, freq='14D'), tag='tune_source')
    train = censor(S[S.cutoff < cal_lo], cal_lo)
    valid = censor(S[S.cutoff.between(cal_lo, cal_hi)], O)
    train = train.sample(min(len(train), args.max_train), random_state=args.seed)
    valid = valid.sample(min(len(valid), args.max_valid), random_state=args.seed)
    del S
    directory = OUT / 't1'; directory.mkdir(exist_ok=True)
    fingerprint = hashlib.sha256(b''.join((Path(t1.__file__).parent / name).read_bytes()
        for name in ['t1.py', 'features.py'])).hexdigest()[:12]
    n_train,n_valid=len(train),len(valid)
    cache=directory/'tuning_cache';cache.mkdir(exist_ok=True)
    train_path,valid_path=cache/'train.parquet',cache/'valid.parquet'
    train.to_parquet(train_path,index=False);valid.to_parquet(valid_path,index=False)
    del train,valid;gc.collect()
    study = optuna.create_study(direction='minimize', sampler=optuna.samplers.TPESampler(seed=args.seed),
                                pruner=optuna.pruners.MedianPruner(), study_name=f'source_{args.origin}_{args.seed}_{fingerprint}_{args.max_train}_{args.max_valid}',
                                storage=f"sqlite:///{(directory / 'tune_source.sqlite3').as_posix()}", load_if_exists=True)

    def objective(trial):
        params = dict(num_leaves=trial.suggest_int('num_leaves', 15, 127),
                      min_data_in_leaf=trial.suggest_int('min_data_in_leaf', 50, 800, log=True),
                      lambda_l2=trial.suggest_float('lambda_l2', .1, 50, log=True),
                      feature_fraction=trial.suggest_float('feature_fraction', .5, 1),
                      learning_rate=trial.suggest_float('learning_rate', .02, .1),
                      bagging_fraction=trial.suggest_float('bagging_fraction', .5, 1), seed=args.seed)
        start = time.monotonic()
        params_path=cache/f'trial_{trial.number}.json'
        params_path.write_text(json.dumps(params),encoding='utf-8')
        process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('tune_worker.py')),
            '--train',str(train_path),'--valid',str(valid_path),'--params',str(params_path)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
        messages=queue.Queue()
        def read_output():
            for line in process.stdout:messages.put(line)
            messages.put(None)
        reader=threading.Thread(target=read_output,daemon=True);reader.start()
        loss=None;last_output=[]
        try:
            while True:
                remaining=720-(time.monotonic()-start)
                if remaining<=0:raise optuna.TrialPruned('Giới hạn 12 phút/trial')
                try:line=messages.get(timeout=remaining)
                except queue.Empty:raise optuna.TrialPruned('Giới hạn 12 phút/trial')
                if line is None:break
                try:progress=json.loads(line)
                except json.JSONDecodeError:
                    last_output.append(line);continue
                loss=float(progress['loss']);trial.report(loss,int(progress['step']))
                if trial.should_prune():raise optuna.TrialPruned()
            code=process.wait()
            if code or loss is None:raise RuntimeError('Trial worker thất bại: '+''.join(last_output)[-1000:])
        finally:
            if process.poll() is None:process.kill()
            process.wait();reader.join(timeout=1)
            process.stdout.close()
        trial.set_user_attr('train_seconds', time.monotonic() - start)
        return loss

    def checkpoint(study, trial):
        study.trials_dataframe().to_csv(directory / 'tuning_trials.csv', index=False)
        complete=sum(t.state==optuna.trial.TrialState.COMPLETE for t in study.trials)
        pruned=sum(t.state==optuna.trial.TrialState.PRUNED for t in study.trials)
        if complete:
            data=dict(params=study.best_params,seed=args.seed,validation_pinball=study.best_value,origin=args.origin,
                training_label_end=str(cal_lo.date()),calibration_last_cutoff=str(cal_hi.date()),test_used=False,
                source_fingerprint=fingerprint,n_train=n_train,n_validation=n_valid,max_train=args.max_train,
                max_validation=args.max_valid,study_name=study.study_name,n_complete=complete,n_pruned=pruned,
                n_failed=sum(t.state==optuna.trial.TrialState.FAIL for t in study.trials),
                search_complete=(complete+pruned>=args.trials),worker_isolation=True)
            temporary=directory/'best_params.tmp';temporary.write_text(json.dumps(data,indent=2),encoding='utf-8')
            temporary.replace(directory/'best_params.json')
    finished = sum(t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED) for t in study.trials)
    checkpoint(study,None)
    study.optimize(objective,n_trials=max(0,args.trials-finished),callbacks=[checkpoint],gc_after_trial=True,catch=(RuntimeError,))
    checkpoint(study,None)
    if not json.loads((directory/'best_params.json').read_text())['search_complete']:
        raise RuntimeError('Chưa đủ số trial thành công/pruned; xem nhật ký lỗi và resume')


if __name__ == '__main__':
    main()
