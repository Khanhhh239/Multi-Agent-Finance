"""WP-2.4: ablation T3→T1, ngân sách nguồn giống nhau, lịch sử cố định tại ngày lập."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT, ROOT
from agent1.models.features import FEATURES
from agent1.models.dispute_features import at_issue_dispute_rates, add_dispute_rates
from agent1.models import t1
from agent1.eval.cluster import mean_ci
from run_t1 import snapshots, censor, score


def pinball(y, quantiles):
    error = np.minimum(y, t1.CAP)[:, None] - quantiles
    return np.maximum(np.asarray(t1.QS)*error, (np.asarray(t1.QS)-1)*error).mean(1)


def main():
    origin = pd.Timestamp('2024-07-01'); label_end = origin-pd.Timedelta(days=183)
    train = censor(snapshots('src', pd.date_range('2019-07-01', label_end-pd.Timedelta(days=7), freq='14D'),
                             tag='variants_training'), label_end)
    train = train.sample(min(len(train), 40000), random_state=7)
    source = pd.read_parquet(SYNTH/'src/invoices.parquet')
    train = add_dispute_rates(train, at_issue_dispute_rates(source)); del source; gc.collect()
    models, times = {}, {}
    for name, feats in [('DH-GBM default', FEATURES), ('DH-GBM + dispute EB at issue', [*FEATURES,'c_disp_eb'])]:
        began = time.monotonic(); models[name] = t1.HazardGBM(rounds=300, feats=feats).fit(train)
        times[name] = time.monotonic()-began
        print(name, 'fit', flush=True)
    n_train = len(train); del train; gc.collect()
    rows, company = [], []
    for world in ['src','tgt']:
        invoices = pd.read_parquet(SYNTH/world/'invoices.parquet')
        rates = at_issue_dispute_rates(invoices); labels = invoices.set_index('invoice_id').dispute
        test = add_dispute_rates(censor(snapshots(world, pd.date_range(origin, periods=52, freq='7D'),
                                 tag='variants_test'), '2025-12-31'), rates)
        del invoices, rates; gc.collect()
        predictions = {'B1d-cust-quantiles': dict(Q=t1.b1_dist(test))}
        for name, model in models.items():
            hazard = model.hazards(test); pmf, survival = t1.pmf_from_hazard(hazard)
            predictions[name] = dict(Q=t1.quantiles_from_hazard(hazard), P=pmf, cdf=1-survival)
        default_loss = pinball(test.remaining.to_numpy(), predictions['DH-GBM default']['Q'])
        flags = test.invoice_id.map(labels).to_numpy(bool)
        for stratum, mask in [('all', np.ones(len(test), bool)), ('disputed', flags), ('not_disputed', ~flags)]:
            cohort = test.loc[mask].copy()
            subpred = {name:{key:value[mask] for key,value in prediction.items()} for name,prediction in predictions.items()}
            result = score(subpred, cohort, world)
            for name, prediction in subpred.items():
                loss = pinball(cohort.remaining.to_numpy(), prediction['Q'])
                ci = mean_ci(loss, cohort.firm_id, baseline=default_loss[mask])
                for key in ['improvement_pct','improvement_ci_low','improvement_ci_high']:
                    result.loc[result.model==name,'vs_default_'+key] = ci[key]
                grouped = pd.DataFrame(dict(firm_id=cohort.firm_id.to_numpy(), loss=loss,
                    baseline=default_loss[mask])).groupby('firm_id').agg(loss_sum=('loss','sum'), baseline_sum=('baseline','sum'), n=('loss','size')).reset_index()
                grouped['world'], grouped['stratum'], grouped['model'] = world, stratum, name
                company.append(grouped)
            result['stratum'] = stratum; result['n_train'] = n_train
            result['fit_seconds'] = result.model.map(times).fillna(0)
            result['rounds'] = 300; result['test_used_for_selection'] = False
            result['measurement_version'] = 'T3-T1-at-issue-locked-ablation-v1-fullweek'
            result['limitation'] = 'synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption'
            rows.append(result)
        print(world, 'scored', flush=True); del test, predictions; gc.collect()
    pd.concat(rows).to_csv(OUT/'t1/T3_T1_ablation.csv', index=False)
    pd.concat(company).to_csv(OUT/'t1/T3_T1_company_losses.csv', index=False)
    files = ['scripts/run_t3_t1.py','agent1/models/dispute_features.py','agent1/models/t3_features.py',
             'agent1/models/t1.py','agent1/models/features.py','scripts/run_t1.py']
    (OUT/'t1/T3_T1_protocol.json').write_text(json.dumps(dict(complete=True, origin=str(origin.date()),
        training_label_end=str(label_end.date()), n_train=n_train, rounds=300, feature='c_disp_eb frozen at invoice issue; closed customer history only',
        test_used_for_selection=False, adopted=False, code_sha256=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in files)).hexdigest(),
        input_sha256={world:hashlib.sha256((SYNTH/world/'invoices.parquet').read_bytes()).hexdigest() for world in ['src','tgt']}), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
