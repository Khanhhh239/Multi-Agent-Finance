"""DSO/DPO mô tả từ BCTC chính chủ; so DSO máy phát mà không chỉnh tham số."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import ROOT,RAW,SYNTH,OUT
from agent1.eval.accounting import accounting_days


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def observed_ar(inv,pay,date):
    received=pay[pay.pay_date_true<=date].groupby('invoice_id').amount.sum()
    remaining=(inv.amount_gross-inv.invoice_id.map(received).fillna(0)).clip(lower=0.)
    open_mask=(inv.issue_date<=date)&(inv.paid_date_true.isna()|(inv.paid_date_true>date))&\
        (inv.writeoff_date.isna()|(inv.writeoff_date>date))
    return remaining.where(open_mask,0).groupby(inv.firm_id).sum()


def main():
    directory=OUT/'data';directory.mkdir(exist_ok=True)
    source=ROOT/'docs/02_Data/vn_listed_inputs.json';records=json.loads(source.read_text(encoding='utf-8'))
    manifest=json.loads((RAW/'MANIFEST.json').read_text(encoding='utf-8'))
    expected={f['path']:f['sha256'] for spec in manifest.values() for f in spec.get('files',[])}
    rows=[];comparisons=[];firm_rows=[]
    for record in records:
        path=RAW/record['report'];digest=sha(path)
        if expected.get(record['report'])!=digest:raise ValueError('BCTC không khớp manifest: '+str(path))
        dso=accounting_days(record['opening_short_trade_receivables'],record['closing_short_trade_receivables'],record['net_revenue'])
        dpo=accounting_days(record['opening_short_trade_payables'],record['closing_short_trade_payables'],record['cost_of_sales'])
        rows.append(dict(record,DSO_proxy=dso,DPO_COGS_proxy=dpo,days_basis=365,pdf_sha256=digest,
            n_issuers_in_sector=1,used_for_generator_calibration=False))
        year=record['year'];start=pd.Timestamp(year,1,1);end=pd.Timestamp(year,12,31)
        for world in ['src','tgt']:
            firms=pd.read_parquet(SYNTH/world/'firms.parquet',columns=['firm_id','industry'])
            firms=firms[firms.industry==record['industry']]
            filters=[('firm_id','in',firms.firm_id.tolist())]
            inv=pd.read_parquet(SYNTH/world/'invoices.parquet',filters=filters,
                columns=['invoice_id','firm_id','issue_date','paid_date_true','writeoff_date','amount_gross','amount_net'])
            pay=pd.read_parquet(SYNTH/world/'payments.parquet',filters=filters,columns=['invoice_id','pay_date_true','amount'])
            opening=observed_ar(inv,pay,start-pd.Timedelta(days=1));closing=observed_ar(inv,pay,end)
            sales=inv[inv.issue_date.between(start,end)].groupby('firm_id').amount_net.sum()
            for firm in firms.firm_id:
                if sales.get(firm,0)<=0:continue
                value=accounting_days(opening.get(firm,0.),closing.get(firm,0.),sales[firm])
                firm_rows.append(dict(world=world,firm_id=firm,industry=record['industry'],year=year,DSO_proxy=value))
            sample=[r['DSO_proxy'] for r in firm_rows if r['world']==world and r['industry']==record['industry'] and r['year']==year]
            comparisons.append(dict(issuer=record['issuer'],year=year,industry=record['industry'],world=world,n_synthetic_firms=len(sample),
                issuer_DSO_proxy=dso,synthetic_DSO_median=float(np.median(sample)),synthetic_DSO_p10=float(np.quantile(sample,.1)),
                synthetic_DSO_p90=float(np.quantile(sample,.9)),calibration_used=False,decision='descriptive_only_no_sector_CI'))
    pd.DataFrame(rows).to_csv(directory/'vn_listed_accounting.csv',index=False)
    pd.DataFrame(comparisons).to_csv(directory/'vn_listed_DSO_comparison.csv',index=False)
    pd.DataFrame(firm_rows).to_csv(directory/'vn_listed_synthetic_DSO.csv',index=False)
    protocol=dict(complete=True,n_issuer_years=len(records),n_industries=len({r['industry'] for r in records}),
        scope='three issuer-years in three industries, not a complete VN sector validation',
        missing='BMP2024 downloads HTTP403, plastics illustrated with NTP2024 instead; TCM2024 annual report lacks full statements, used separately disclosed audited2022 instead',
        formula='365*(opening+closing short-term gross trade balance)/2 / net revenue (DSO), COGS (DPO proxy, not purchases)',
        limitations='listed consolidated entities not SMEs; n=1 per sector; different years; no sector CI; VAT/net-sales mismatch; SMC emphasis of matter; synthetic realized AR treats known terminal settlement/write-off as zero; no synthetic AP comparable',
        used_for_generator_calibration=False,expert_verified=False,input_sha256=sha(source),
        synthetic_sha256={f'{world}/{table}.parquet':sha(SYNTH/world/f'{table}.parquet')
            for world in ['src','tgt'] for table in ['invoices','payments','firms']},
        code_sha256=sha(Path(__file__).resolve()))
    (directory/'vn_listed_protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print(pd.DataFrame(comparisons).to_string(index=False))


if __name__=='__main__':main()
