"""Thế giới đối nghịch: mỗi lớp bật một thay đổi; RNG tình huống tách khỏi RNG nền."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from .world import World, WorldConfig
from ..data.contracts import validate_world

CASES=['lumpy_customer','group_payer','heterogeneity','cod_realistic','discount_early','retention',
       'fx','credit_note','verbal','supply_shock','seasonal_extreme','new_company']


class HardCaseWorld(World):
    def __init__(self,cfg,case):
        if case not in CASES:raise ValueError('Hard case không hợp lệ')
        self.case=case
        cfg.hard_case=case
        self.annotations=[]
        super().__init__(cfg)

    def noise(self,firm,phase):
        return np.random.default_rng(np.random.SeedSequence([self.cfg.seed,int(firm['firm_id'][1:]),700+phase]))

    def make_customers(self,firm):
        c=super().make_customers(firm);r=self.noise(firm,1)
        if self.case=='lumpy_customer':
            anchor=float(r.uniform(.4,.6));rest=c.weight.to_numpy(copy=True);rest[0]=0
            c['weight']=rest/rest.sum()*(1-anchor);c.loc[0,'weight']=anchor;c['is_anchor']=c.index==0
            c.loc[0,['start_day','end_day']]=[0,(self.end-self.start).days+1]
        elif self.case=='heterogeneity':
            base=np.clip(r.beta(.8,.8,len(c)),.005,.995)
            c['ontime_logit']=np.log(base/(1-base));c['late_med']*=r.lognormal(0,.95,len(c))
        elif self.case=='cod_realistic':
            order=r.permutation(len(c));expected=c.weight.to_numpy()/c.ticket.to_numpy()
            mass=expected[order].cumsum()/expected.sum();selected=order[mass<=.25]
            c.loc[c.term_days==0,'term_days']=30;c.loc[selected,'term_days']=0
        elif self.case=='verbal':
            c['verbal_extension_days']=np.where(r.random(len(c))<.15,r.integers(15,61,len(c)),0)
        elif self.case=='discount_early':
            c['discount_eligible']=r.random(len(c))<.25
            c.loc[c.discount_eligible,'term_days']=30
        return c

    def make_invoices(self,firm,cust):
        inv=super().make_invoices(firm,cust)
        if self.case=='lumpy_customer':
            # Điều kiện hard case là tỷ trọng doanh thu thực hiện, không phải trọng số
            # bị chuẩn hoá lại khi khách khác vào/ra thị trường.
            anchor=inv.ci.eq(0);share=float(cust.loc[0,'weight'])
            target=inv.loc[~anchor,'net'].sum()*share/(1-share)
            inv.loc[anchor,'net']=np.maximum(1000.,np.round(inv.loc[anchor,'net']*target/inv.loc[anchor,'net'].sum(),-3))
        return inv

    def customer_paths(self,firm,cust):
        L,default,stress=super().customer_paths(firm,cust)
        if self.case=='supply_shock' and firm['industry']=='steel_metals':
            mask=(self.weeks>=pd.Timestamp('2022-10-03'))&(self.weeks<pd.Timestamp('2022-11-28'))
            L[:,mask]-=1.5;stress=stress.copy();stress[mask]+=1
        return L,default,stress

    def settle(self,firm,cust,inv,L,default,stress):
        inv,pay=super().settle(firm,cust,inv,L,default,stress);r=self.noise(firm,2)
        if self.case=='discount_early':
            eligible=cust.discount_eligible.to_numpy()
            mask=eligible[inv.ci.to_numpy()]&~inv.is_bad_debt.to_numpy()&~inv.dispute.to_numpy()
            selected=np.flatnonzero(mask);discounted=np.round(inv.loc[mask,'amount_gross'].to_numpy()*.98,-3)
            pay=pay[~pay.k.isin(selected)].copy()
            early=pd.DataFrame(dict(k=selected,day_i=self.cal.snap_bd(inv.loc[mask,'issue_i'].to_numpy()+10),amount=discounted,kind='full'))
            pay=pd.concat([pay,early],ignore_index=True)
            inv['discount_taken']=mask
            inv.loc[mask,'credit_note']=inv.loc[mask,'amount_gross']-discounted
            inv.loc[mask,'partial']=False
        elif self.case=='retention':
            inv['retention_amount']=0.;inv['retention_due_i']=-1
            extra=[]
            for k,g in pay[pay.kind.isin(['full','final'])].groupby('k'):
                if r.random()>=.2:continue
                ix=g.day_i.idxmax();held=float(min(inv.loc[k,'amount_gross']*.05,pay.loc[ix,'amount']*.5))
                when=int(self.cal.snap_bd(int(pay.loc[ix,'day_i'])+730))
                pay.loc[ix,'amount']-=held;pay.loc[ix,'kind']='partial'
                extra.append(dict(k=k,day_i=when,amount=held,kind='final'))
                inv.loc[k,['retention_amount','retention_due_i']]=[held,when]
            if extra:pay=pd.concat([pay,pd.DataFrame(extra)],ignore_index=True)
        elif self.case=='verbal':
            extension=cust.verbal_extension_days.to_numpy()[inv.ci.to_numpy()]
            inv['verbal_extension_days']=extension
            pay['day_i']=self.cal.snap_bd(pay.day_i.to_numpy()+extension[pay.k.to_numpy()])
        annotation_columns=[c for c in ('discount_taken','retention_amount','retention_due_i','verbal_extension_days') if c in inv]
        if annotation_columns:
            a=inv[annotation_columns].copy()
            a['invoice_id']=firm['firm_id']+'-'+inv.symbol+'-'+inv.invoice_no
            if 'retention_due_i' in a:
                values=a.pop('retention_due_i').astype(int)
                a['retention_due']=pd.to_datetime(self.cal.date(values.clip(lower=0))).where(values.to_numpy()>=0)
            self.annotations.append(a)
        return inv,pay.sort_values(['day_i','k']).reset_index(drop=True)

    def promises(self,firm,cust,inv,pays):
        p=super().promises(firm,cust,inv,pays)
        if self.case=='verbal' and len(p):
            p=p[inv.verbal_extension_days.to_numpy()[p.invoice_k.to_numpy()]==0]
        return p

    def bank_ledger(self,firm,cust,inv,pays):
        bank,pay=super().bank_ledger(firm,cust,inv,pays)
        if self.case=='group_payer':
            ids=cust.customer_id.tolist();mapping={cid:ids[(i//3)*3] for i,cid in enumerate(ids)}
            bank['payer_group_id']=bank.true_customer_id.map(mapping)
            names=cust.set_index('customer_id')['name']
            mask=bank.payer_group_id.notna()
            bank.loc[mask,'counterparty']=bank.loc[mask,'payer_group_id'].map(names)
        return bank,pay

    def run(self,out_dir=None,verbose=True):
        directory=super().run(out_dir,verbose)
        inv=pd.read_parquet(directory/'invoices.parquet')
        pay=pd.read_parquet(directory/'payments.parquet')
        bank=pd.read_parquet(directory/'bank_txns.parquet')
        if self.annotations:
            inv=inv.merge(pd.concat(self.annotations,ignore_index=True),on='invoice_id',how='left')
        if self.case=='fx':
            r=np.random.default_rng(np.random.SeedSequence([self.cfg.seed,799]))
            # Tỷ giá là kịch bản tổng hợp, không phải số liệu thị trường thật.
            days=pd.date_range(self.start,self.end+pd.Timedelta(days=1100))
            rates=pd.Series(25000*np.exp(np.cumsum(r.normal(0,.001,len(days)))),index=days)
            selected=r.random(len(inv))<.15
            inv['original_currency']=np.where(selected,'USD','VND')
            inv['fx_rate_at_issue']=inv.issue_date.map(rates).where(selected,1.)
            inv['amount_foreign']=inv.amount_gross/inv.fx_rate_at_issue
            fx=inv.set_index('invoice_id')
            foreign=pay.invoice_id.map(fx.original_currency).eq('USD')
            issue_rate=pay.invoice_id.map(fx.fx_rate_at_issue)
            pay['fx_adjustment']=0.
            ratio=pay.pay_date_true.map(rates).fillna(rates.iloc[-1])/issue_rate
            pay.loc[foreign,'fx_adjustment']=pay.loc[foreign,'amount']*(ratio[foreign]-1)
            pay['amount']+=pay.fx_adjustment
            sums=pay.groupby('txn_id').amount.sum()
            mask=bank.txn_id.isin(sums.index)
            bank.loc[mask,'amount']=bank.loc[mask,'txn_id'].map(sums)-bank.loc[mask,'fee_deducted']
            inv['paid_amount']=inv.invoice_id.map(pay.groupby('invoice_id').amount.sum()).fillna(0.)
            rates.rename_axis('date').rename('fx_rate').to_frame().to_parquet(directory/'fx_rates.parquet')
        elif self.case=='credit_note':
            r=np.random.default_rng(np.random.SeedSequence([self.cfg.seed,798]))
            selected=r.random(len(inv))<.03
            mapping={iid:iid+'-REPLACED' for iid in inv.loc[selected,'invoice_id']}
            inv['adjusts_invoice_id']=inv.invoice_id.where(selected)
            inv['adjustment_type']=np.where(selected,'replacement','original')
            for table,columns in [(inv,['invoice_id']),(pay,['invoice_id','ledger_invoice_id'])]:
                for c in columns:table[c]=table[c].map(mapping).fillna(table[c])
            inv.loc[selected,'invoice_no']=(inv.loc[selected,'invoice_no'].astype(int)+50000000).astype(str)
            promises_path=directory/'promises.parquet';prom=pd.read_parquet(promises_path)
            prom['invoice_id']=prom.invoice_id.map(mapping).fillna(prom.invoice_id);prom.to_parquet(promises_path,index=False)
        elif self.case=='supply_shock':
            firms=pd.read_parquet(directory/'firms.parquet')
            affected=firms[firms.industry=='steel_metals']
            extra=pd.DataFrame([dict(firm_id=f.firm_id,customer_id=None,type='sector_supply_disruption',
                date=pd.Timestamp('2022-10-03'),end_date=pd.Timestamp('2022-11-28'),magnitude=-1.5) for f in affected.itertuples()])
            events=pd.read_parquet(directory/'events.parquet')
            if len(extra):pd.concat([events,extra],ignore_index=True).to_parquet(directory/'events.parquet',index=False)
        inv.to_parquet(directory/'invoices.parquet',index=False)
        pay.to_parquet(directory/'payments.parquet',index=False)
        bank.to_parquet(directory/'bank_txns.parquet',index=False)
        if self.case=='fx':
            firms=pd.read_parquet(directory/'firms.parquet');out=pd.read_parquet(directory/'outflows.parquet')
            self.cash_paths(firms,bank,out).to_parquet(directory/'daily_cash.parquet',index=False)
        validate_world(directory)
        (directory/'hard_case_complete.txt').write_text(self.case,encoding='utf-8')
        return directory
