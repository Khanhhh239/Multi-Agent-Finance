"""Đo wall time cùng seed trước/sau vòng groupby; baseline chỉ dùng trong benchmark."""
import argparse
import cProfile
import inspect
from pathlib import Path
import pstats
import sys
import textwrap
import time
import types
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.synth import world as module
from agent1.paths import SYNTH,OUT

LEGACY_LOOP='''    for g, sub in p.groupby("grp", sort=False):
        c = cust.iloc[int(sub["ci"].iloc[0])]
        fee = float(r.choice([11000, 22000])) if r.random() < 0.05 else 0.0
        dt = pd.Timestamp(C.date(int(sub["day_i"].iloc[0])))
        tid = f"{firm['firm_id']}-T{len(txns):06d}"
        txns.append(dict(txn_id=tid, firm_id=firm["firm_id"], value_date=dt, amount=float(sub["amount"].sum()) - fee,
                         direction="in", counterparty=nm.counterparty_variant(r, c["name"], c["short"]),
                         memo=nm.transfer_memo(r, c["short"], firm["core"], sub["invoice_no"].tolist(), dt.month,
                                               c["memo_no_p"]),
                         txn_type="customer_payment", true_customer_id=c["customer_id"], fee_deducted=fee))
        tx_of[sub.index.values] = tid
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--firms',type=int,default=6);args=parser.parse_args()
    source=textwrap.dedent(inspect.getsource(module.World.bank_ledger))
    start=source.index('    customer_records =');end=source.index('    p["txn_id"]',start)
    legacy=source[:start]+LEGACY_LOOP+source[end:]
    namespace=dict(vars(module));exec(compile(legacy,'bank_ledger_v1_benchmark','exec'),namespace)
    times={};paths={}
    for kind in ('legacy','vectorized'):
        cfg=module.WorldConfig(name=f'benchmark_{kind}',seed=314,n_firms=args.firms,write_xml=0)
        generator=module.World(cfg)
        if kind=='legacy':generator.bank_ledger=types.MethodType(namespace['bank_ledger'],generator)
        t=time.monotonic();paths[kind]=generator.run(verbose=False);times[kind]=time.monotonic()-t
    same=True
    for path in paths['legacy'].glob('*.parquet'):
        try:pd.testing.assert_frame_equal(pd.read_parquet(path),pd.read_parquet(paths['vectorized']/path.name))
        except AssertionError:same=False
    count=len(pd.read_parquet(paths['vectorized']/'invoices.parquet'))
    directory=OUT/'data';directory.mkdir(exist_ok=True)
    speedup=times['legacy']/times['vectorized']
    pd.DataFrame([dict(n_firms=args.firms,n_invoices=count,legacy_seconds=times['legacy'],
        vectorized_seconds=times['vectorized'],speedup=speedup,meets_5x=speedup>=5,
        value_tables_equal=same,seed=314,scope='full_world_small_not_1M')]).to_csv(directory/'generator_benchmark.csv',index=False)
    profile=cProfile.Profile();profile.enable()
    module.World(module.WorldConfig(name='benchmark_profile',seed=314,n_firms=args.firms,write_xml=0)).run(verbose=False)
    profile.disable();stats=pstats.Stats(profile)
    rows=[dict(file=k[0],line=k[1],function=k[2],primitive_calls=v[0],calls=v[1],self_seconds=v[2],cumulative_seconds=v[3]) for k,v in stats.stats.items()]
    pd.DataFrame(rows).sort_values('cumulative_seconds',ascending=False).to_csv(directory/'generator_profile.csv',index=False)
    if not same:raise ValueError('Vector hoá làm đổi bảng giá trị')


if __name__=='__main__':main()
