"""WP-8.2: dự báo giữ lời trên sạch/nhiễu, cutoff hàng tuần, không chọn theo test."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT, ROOT
from agent1.eval.promise_reliability import predict_week
from agent1.eval.cluster import mean_ci
from agent1.eval.metrics import ece


def main():
    rows, losses = [], []
    for world in ['src', 'src_noisy_promises', 'tgt']:
        directory = SYNTH / world
        promises = pd.read_parquet(directory / 'promises.parquet')
        data_end = pd.read_parquet(directory / 'bank_txns.parquet', columns=['value_date']).value_date.max()
        parts = []
        for cutoff in pd.date_range('2024-07-01', periods=52, freq='7D'):
            query = promises[(promises.made_date > cutoff) &
                             (promises.made_date <= cutoff + pd.Timedelta(days=7)) &
                             (promises.promised_date + pd.Timedelta(days=3) <= data_end) & promises.kept.notna()]
            if 'resolved_date' in query:
                query = query[query.resolved_date.notna() & (query.resolved_date <= data_end)]
            if query.empty:
                continue
            predictions = predict_week(promises, query, cutoff)
            base = predictions['Customer historical rate']
            y = query.kept.to_numpy(float)
            for name, predicted in predictions.items():
                parts.append(pd.DataFrame(dict(firm_id=query.firm_id.to_numpy(), model=name,
                    y=y, probability=predicted, loss=(y-predicted)**2, baseline_loss=(y-base)**2)))
        frame = pd.concat(parts, ignore_index=True)
        for name, part in frame.groupby('model'):
            ci = mean_ci(part.loss, part.firm_id, baseline=part.baseline_loss)
            rows.append(dict(world=world, model=name, n=len(part), n_firms=ci['n_firms'],
                Brier=part.loss.mean(), Brier_ci_low=ci['ci_low'], Brier_ci_high=ci['ci_high'],
                improvement_pct=ci['improvement_pct'], improvement_ci_low=ci['improvement_ci_low'],
                improvement_ci_high=ci['improvement_ci_high'], ECE=ece(part.y, part.probability),
                base_rate=part.y.mean(), mean_p=part.probability.mean(), bootstrap_n=300,
                test_used_for_selection=False, measurement_version='T8-weekly-prequential-v1',
                limitation='synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation'))
            grouped = part.groupby('firm_id').agg(loss_sum=('loss','sum'), baseline_sum=('baseline_loss','sum'), n=('loss','size')).reset_index()
            grouped['world'], grouped['model'] = world, name
            losses.append(grouped)
        print(world, len(frame)//3, 'promises scored', flush=True)
    target = OUT / 't8'; target.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(target / 'reliability_metrics.csv', index=False)
    pd.concat(losses).to_csv(target / 'reliability_company_losses.csv', index=False)
    paths = ['agent1/models/t8_promise.py', 'agent1/eval/promise_reliability.py', 'scripts/run_t8_reliability.py']
    metadata = dict(complete=True, test_start='2024-07-01', n_weeks=52, history_rule='made<=T and promised+3<=T; resolved_date<=T when present',
        predictions='freeze at T for new promises in (T,T+7]; query supplies identifiers only',
        source_only_parameters=dict(strength=6, half_life_days=90), test_used_for_selection=False,
        code_sha256=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in paths)).hexdigest(),
        input_sha256={world:hashlib.sha256((SYNTH/world/'promises.parquet').read_bytes()).hexdigest()
                      for world in ['src','src_noisy_promises','tgt']})
    (target / 'reliability_protocol.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
