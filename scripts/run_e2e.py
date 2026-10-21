"""XML + sao kê CSV -> T9 -> nhãn -> T1/T4 -> T6+ACI -> T10; chấm ngoài pipeline.

Mặc định chạy nguồn→fine-tune và đủ đối chứng. Chế độ tenant là phép chẩn đoán
riêng, lưu ngoài bảng nghiệm thu để không ghi đè kết quả đầy đủ.
"""
import argparse
import io
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT
from agent1.synth.einvoice import invoice_to_xml
from agent1_service.ingest.einvoice_xml import read_invoice_xml
from agent1_service.ingest.bank_statement import normalize_statement
from agent1_service.jobs.nightly import run
from agent1.models.t6_cash import simulate,ACI
from agent1.eval.metrics import coverage,interval_score
from agent1.eval.cluster import mean_ci
from agent1.models.t9_recon import Reconciler
from agent1.data.schema import quality_gate


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--world',default='tgt')
    parser.add_argument('--firms',default='all');parser.add_argument('--weeks',type=int,default=52)
    parser.add_argument('--modes',default='reconciled,truth,ledger')
    parser.add_argument('--protocol',choices=['source-finetune','tenant'],default='source-finetune')
    parser.add_argument('--source-budget',type=int,default=40000)
    args=parser.parse_args()
    if args.protocol=='source-finetune':
        from run_e2e_protocol import run_protocol
        firms=None if args.firms=='all' else args.firms.split(',')
        print(run_protocol(args.world,firms,args.weeks,args.source_budget).to_string(),flush=True)
        return
    start=time.monotonic();directory=SYNTH/args.world;output=OUT/'e2e/tenant';output.mkdir(parents=True,exist_ok=True)
    tables={name:pd.read_parquet(directory/f'{name}.parquet') for name in ['invoices','bank_txns','customers','firms','outflows','daily_cash','promises']}
    firms=tables['firms'].firm_id.tolist() if args.firms=='all' else args.firms.split(',')
    rows=[]
    for firm in firms:
        original=tables['invoices'][tables['invoices'].firm_id==firm]
        seller=tables['firms'].set_index('firm_id').loc[firm]
        customers=tables['customers'][tables['customers'].firm_id==firm]
        by_customer=customers.set_index('customer_id')
        normalized=[]
        for _,invoice in original.iterrows():
            normalized.append(read_invoice_xml(invoice_to_xml(invoice,seller,by_customer.loc[invoice.customer_id]),firm,validate=False))
        inv=pd.DataFrame(normalized).merge(original[['invoice_id','paid_date_true','ledger_clear_date']],on='invoice_id')
        if quality_gate(inv).any_error.any():raise ValueError('XML không đạt cổng chất lượng')
        print(firm,'XML validated',len(inv),flush=True)
        inv['customer_id']=inv.customer_id.map(dict(zip(customers.mst.astype(str),customers.customer_id)))
        b=tables['bank_txns'][tables['bank_txns'].firm_id==firm]
        # CSV thực sự được ghi/đọc qua cùng parser dùng cho định dạng chuẩn.
        buffer=io.StringIO();b[['txn_id','value_date','amount','memo','counterparty']].to_csv(buffer,index=False);buffer.seek(0)
        bank=normalize_statement(pd.read_csv(buffer),firm,mapping={},dayfirst=False)
        out=tables['outflows'][tables['outflows'].firm_id==firm]
        daily=tables['daily_cash'][tables['daily_cash'].firm_id==firm].set_index('date')
        promises=tables['promises'][tables['promises'].firm_id==firm]
        # T9 tuần tự có tính bất biến theo prefix; chỉ đưa links đã lộ tại T vào engine.
        offline_links,offline_queue=Reconciler().reconcile(bank,inv,customers)
        for mode in args.modes.split(','):
            cache={'offline_links':offline_links,'offline_queue':offline_queue};aci=ACI();pending=[]
            for T in pd.date_range('2024-07-01',periods=args.weeks,freq='7D'):
                for reveal,k,lo,hi,y in [p for p in pending if p[0]<=T]:aci.update(k,not lo<=y<=hi)
                pending=[p for p in pending if p[0]>T]
                current=float(daily.loc[T,'balance'])
                result,simargs=run(inv,bank,customers,promises,out,T,current,model_cache=cache,evaluation_label_mode=mode)
                samples,_=simulate(**simargs)
                scale=max(float(np.mean(simargs['known_out'])),1.)
                for k in range(13):
                    when=T+pd.Timedelta(days=7*(k+1))
                    if when not in daily.index:continue
                    truth=float(daily.loc[when,'balance'])
                    lo,hi=aci.interval(samples[:,k],k)
                    med=float(np.median(samples[:,k]))
                    pending.append((when,k,lo,hi,truth))
                    rows.append(dict(firm_id=firm,label_mode=mode,cutoff=T,k=k+1,y=truth/scale,
                        lo=lo/scale,med=med/scale,hi=hi/scale,auto_txn_coverage=result['auto_txn_coverage'],
                        measurement_version='e2e-xml-csv-tenant-v1',seed=7,full_52w=(args.weeks==52)))
            print(firm,mode,'done',flush=True)
        pd.DataFrame(rows).to_parquet(output/'predictions.parquet',index=False)
    df=pd.DataFrame(rows);summary=[]
    for mode,g in df.groupby('label_mode'):
        ci=mean_ci(((g.y>=g.lo)&(g.y<=g.hi)).astype(float),g.firm_id)
        summary.append(dict(label_mode=mode,cov80=coverage(g.y,g.lo,g.hi),IS80=interval_score(g.y,g.lo,g.hi),
            MAE_p50=float(np.abs(g.y-g.med).mean()),cov80_ci_low=ci['ci_low'],cov80_ci_high=ci['ci_high'],
            bootstrap_n=300,n_firms=g.firm_id.nunique(),weeks=args.weeks,full_protocol=False,
            limitation='tenant_models_not_source_finetune;four_baselines_pending',seconds=time.monotonic()-start))
    pd.DataFrame(summary).to_csv(output/'e2e_metrics.csv',index=False)
    df.assign(absolute_error=np.abs(df.y-df.med)).nlargest(20,'absolute_error').to_csv(output/'worst_cases.csv',index=False)


if __name__=='__main__':main()
