"""Giao thức nguồn→fine-tune, XML/CSV thật sự, nhãn T9 và đủ đối chứng T6."""
import io
import json
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
from agent1.data.schema import quality_gate
from agent1.models.t9_recon import Reconciler
from agent1.models.reconciliation_pipeline import build_bank_labels


def observed_promises(promises,invoices,links):
    """Thất hứa chỉ được suy từ tiền đã khớp trước hạn; bỏ cột kept thật."""
    result=promises.copy().drop(columns=['kept'],errors='ignore')
    amounts=invoices.set_index('invoice_id').amount_gross
    by_invoice={iid:group.sort_values('est_pay_date') for iid,group in links.groupby('invoice_id')}
    kept=[]
    for promise in result.itertuples(index=False):
        group=by_invoice.get(promise.invoice_id)
        paid=0. if group is None else group.loc[group.est_pay_date<=promise.promised_date+pd.Timedelta(days=3),'amount'].sum()
        fraction=getattr(promise,'promised_fraction',1.)
        fraction=float(fraction) if pd.notna(fraction) else 1.
        required=amounts.get(promise.invoice_id,float('inf'))*fraction
        kept.append(bool(paid>=.995*required))
    result['kept']=kept
    return result


def source_reconciler(directory=None,require_training_firms=False):
    path=Path(directory) if directory is not None else OUT/'t9/source_reconciler'
    firms=[f'F{i:03d}' for i in range(12)]
    try:
        result=Reconciler.load(path)
        if result.provenance.get('target_used') is not False:raise ValueError('Nguồn huấn luyện không hợp lệ')
        if require_training_firms and (result.provenance.get('training_world')!='src' or
                result.provenance.get('training_firms')!=firms or
                result.provenance.get('training_period')!=['2023-01-01','2023-12-31'] or
                result.provenance.get('calibration_period')!=['2024-01-01','2024-06-30']):
            raise ValueError('Thiếu provenance xác minh DN nguồn giữ ngoài tập học')
        return result
    except (FileNotFoundError,ValueError,KeyError):
        from run_t9 import load
        bank,inv,customers,_=load('src',firms,'2023-01-01','2023-12-31')
        result=Reconciler().fit(Reconciler().candidates(bank,inv,customers))
        bank,inv,customers,_=load('src',firms,'2024-01-01','2024-06-30')
        result.calibrate(result.candidates(bank,inv,customers))
        result.provenance=dict(training_world='src',training_firms=firms,training_period=['2023-01-01','2023-12-31'],
            calibration_period=['2024-01-01','2024-06-30'],target_used=False)
        result.save(path,result.provenance)
        return result


def protocol_output(world,firms,weeks):
    full=(world=='tgt' and weeks==52 and (firms is None or len(set(firms))==14))
    return OUT/'e2e' if full else OUT/'e2e/diagnostics'/f'{world}_f{len(set(firms)) if firms else "all"}_w{weeks}'


def prepare(world='tgt',firms=None,output=None):
    output=output or OUT/'e2e'
    suffix='' if output==OUT/'e2e' else '_diagnostic_'+output.name
    original=SYNTH/world;name='e2e_observed_'+world+suffix;target=SYNTH/name;target.mkdir(exist_ok=True)
    invoices=pd.read_parquet(original/'invoices.parquet')
    customers=pd.read_parquet(original/'customers.parquet')
    sellers=pd.read_parquet(original/'firms.parquet')
    if firms is not None:
        invoices=invoices[invoices.firm_id.isin(firms)];customers=customers[customers.firm_id.isin(firms)]
        sellers=sellers[sellers.firm_id.isin(firms)]
    # Cùng cửa sổ onboarding 12 tháng với đối chứng T6, không đưa HĐ cũ ngoài cửa sổ vào mô hình.
    visible=pd.Timestamp('2023-07-01');invoices=invoices[invoices.issue_date>=visible]
    seller_by_id=sellers.set_index('firm_id');buyer_by_id=customers.set_index('customer_id')
    observed_customer_ids={(row.firm_id,str(row.mst)):row.customer_id for row in customers.itertuples(index=False)}
    rows=[]
    for invoice in invoices.itertuples(index=False):
        row=read_invoice_xml(invoice_to_xml(pd.Series(invoice._asdict()),seller_by_id.loc[invoice.firm_id],
            buyer_by_id.loc[invoice.customer_id]),invoice.firm_id,validate=False)
        row['customer_id']=observed_customer_ids[(row['firm_id'],str(row['buyer_mst']))]
        rows.append(row)
    normalized=pd.DataFrame(rows)
    if quality_gate(normalized).any_error.any():raise ValueError('XML không đạt cổng chất lượng')
    bank=pd.read_parquet(original/'bank_txns.parquet')
    bank=bank[(bank.value_date>=visible)&bank.firm_id.isin(sellers.firm_id)]
    statements=[]
    for firm,group in bank.groupby('firm_id'):
        buffer=io.StringIO();group[['txn_id','value_date','amount','memo','counterparty']].to_csv(buffer,index=False);buffer.seek(0)
        statements.append(normalize_statement(pd.read_csv(buffer),firm,mapping={},dayfirst=False))
    bank=pd.concat(statements,ignore_index=True)
    rec=source_reconciler()
    links,review=rec.reconcile(bank,normalized,customers[['customer_id','firm_id','short']],tau_auto=.9)
    labelled=build_bank_labels(normalized,links)
    # Tên cột nội bộ của T1 được giữ; giá trị là nhãn ƯỚC LƯỢNG, không lấy lại nhãn thật.
    labelled['paid_date_true']=labelled.pop('paid_date_est')
    labelled['writeoff_date']=pd.NaT;labelled['ledger_clear_date']=pd.NaT
    labelled['is_bad_debt']=False;labelled['credit_note']=0.
    labelled['dispute']=False;labelled['partial']=False
    labelled.to_parquet(target/'invoices.parquet',index=False)
    payments=links.rename(columns={'est_pay_date':'pay_date_true'}).copy()
    payments['firm_id']=payments.txn_id.map(bank.set_index('txn_id').firm_id)
    payments['ledger_post_date']=payments.pay_date_true
    payments['ledger_invoice_id']=payments.invoice_id
    payments['payment_id']=[f'EST{i:08d}' for i in range(len(payments))]
    payments.to_parquet(target/'payments.parquet',index=False)
    promises=pd.read_parquet(original/'promises.parquet')
    promises=promises[promises.invoice_id.isin(labelled.invoice_id)]
    observed_promises(promises,labelled,links).to_parquet(target/'promises.parquet',index=False)
    bank.to_parquet(target/'bank_txns.parquet',index=False)
    for table in ['outflows','daily_cash']:
        data=pd.read_parquet(original/f'{table}.parquet');data[data.firm_id.isin(sellers.firm_id)].to_parquet(target/f'{table}.parquet',index=False)
    customers[['customer_id','firm_id','name','short','mst']].to_parquet(target/'customers.parquet',index=False)
    sellers[['firm_id','name','mst']].to_parquet(target/'firms.parquet',index=False)
    report=output/'protocol';report.mkdir(parents=True,exist_ok=True)
    links.to_parquet(report/'observed_links.parquet',index=False);review.to_parquet(report/'review_queue.parquet',index=False)
    (report/'input_protocol.json').write_text(json.dumps(dict(world=world,observed_world=name,visible_from=str(visible.date()),
        n_firms=len(sellers),n_invoices=len(normalized),n_bank=len(bank),n_links=len(links),n_review=len(review),
        tau_auto=.9,customer_model='source_2023_cal2024H1',true_invoice_labels_used=False,
        additional_inputs=['declared_obligation_schedule','observed_balances','recorded_promises'],
        promise_outcomes='derived_from_estimated_links_not_oracle',opening_ar='invoices_issued_before_visible_from_excluded_in_all_compared_models'),indent=2),encoding='utf-8')
    return name,len(sellers)


def oracle_ablation(observed,world):
    source=SYNTH/observed;name='e2e_oracle_'+observed.removeprefix('e2e_observed_');target=SYNTH/name;target.mkdir(exist_ok=True)
    invoices=pd.read_parquet(source/'invoices.parquet')
    truth=pd.read_parquet(SYNTH/world/'invoices.parquet').set_index('invoice_id')
    invoices['paid_date_true']=invoices.invoice_id.map(truth.paid_date_true)
    invoices.to_parquet(target/'invoices.parquet',index=False)
    payments=pd.read_parquet(SYNTH/world/'payments.parquet')
    payments=payments[payments.invoice_id.isin(invoices.invoice_id)]
    payments.to_parquet(target/'payments.parquet',index=False)
    promises=pd.read_parquet(source/'promises.parquet')
    links=payments.rename(columns={'pay_date_true':'est_pay_date'})
    observed_promises(promises,invoices,links).to_parquet(target/'promises.parquet',index=False)
    for table in ['bank_txns','outflows','daily_cash','customers','firms']:
        # Bảng của cùng XML/CSV và lịch chi; chỉ thay nhãn/tiền đã phân bổ trong ablation.
        (target/f'{table}.parquet').write_bytes((source/f'{table}.parquet').read_bytes())
    return name


def run_protocol(world='tgt',firms=None,weeks=52,source_budget=40000,with_oracle=True):
    if not 1<=weeks<=52 or source_budget<=0:raise ValueError('Cần 1–52 tuần và ngân sách huấn luyện dương')
    output=protocol_output(world,firms,weeks);output.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();observed,n_firms=prepare(world,firms,output)
    import run_t6
    directory=output/'protocol'
    run_t6.main(target_world=observed,evaluation_world=world,result_dir=directory,source_budget=source_budget,n_weeks=weeks,label_mode='estimated_T9')
    metrics=pd.read_csv(directory/'t6_interval_metrics.csv')
    metrics['full_protocol']=(weeks==52 and n_firms==14)
    metrics['label_mode']='estimated_T9';metrics['n_firms']=n_firms;metrics['weeks']=weeks
    metrics['seconds']=time.monotonic()-start;metrics['source_training_budget']=source_budget
    metrics['limitation']='synthetic;declared_schedule_and_observed_balances_required;source_budget_limited'
    metrics['oracle_ablation_completed']=False
    # Bộ chờ nhận biết chữ fullweek ở file cuối: chỉ phát marker sau cả oracle.
    metrics.to_csv(output/'e2e_metrics.in_progress.csv',index=False)
    predictions=pd.read_parquet(directory/'t6_predictions.parquet')
    predictions['absolute_error']=(predictions.y-predictions.med).abs()
    predictions.nlargest(20,'absolute_error').to_csv(output/'worst_cases.csv',index=False)
    predictions.assign(covered=predictions.y.between(predictions.lo,predictions.hi)).groupby('firm_id').agg(
        MAE_p50=('absolute_error','mean'),cov80=('covered','mean')).sort_values('MAE_p50',ascending=False).to_csv(output/'company_errors.csv')
    sf=pd.read_csv(directory/'t6_shortfall_predictions.csv')
    policy=pd.read_csv(directory/'alert_policy.csv')
    for model,g in sf.groupby('model'):
        selected=policy[(policy.model==model)&(policy.cost_ratio==5)&(policy.horizon==13)]
        if len(selected):
            g=g.assign(threshold=selected.threshold.iloc[0])
            g[(g.y13==1)&(g.p13<g.threshold)].to_csv(directory/('missed_'+''.join(c if c.isalnum() else '_' for c in model)+'.csv'),index=False)
    if with_oracle:
        oracle=oracle_ablation(observed,world);oracle_directory=directory/'oracle_equal_budget'
        run_t6.main(target_world=oracle,evaluation_world=world,result_dir=oracle_directory,source_budget=source_budget,n_weeks=weeks,label_mode='oracle_bank_same_inputs')
        comparison=pd.read_csv(oracle_directory/'t6_interval_metrics.csv')
        comparison['label_mode']='oracle_bank_same_inputs';comparison['full_protocol']=metrics.full_protocol.iloc[0]
        comparison['n_firms']=n_firms;comparison['weeks']=weeks;comparison['source_training_budget']=source_budget
        comparison['limitation']=metrics.limitation.iloc[0]
        metrics=pd.concat([metrics,comparison],ignore_index=True)
        metrics['oracle_ablation_completed']=True
        metrics['seconds']=time.monotonic()-start
        publish_metrics(metrics,output,require_full=output==OUT/'e2e')
    elif output!=OUT/'e2e':
        metrics.to_csv(output/'e2e_metrics.csv',index=False)
    return metrics


def publish_metrics(metrics,output,require_full=True):
    """Không ghi đè kết quả đã công bố bằng lượt chưa đủ cả hai nhánh."""
    if (require_full and not metrics.full_protocol.all()) or not metrics.oracle_ablation_completed.all():
        raise ValueError('Chưa đủ full protocol và oracle; chưa phát marker fullweek')
    output=Path(output);temporary=output/'e2e_metrics.ready.csv'
    metrics.to_csv(temporary,index=False)
    temporary.replace(output/'e2e_metrics.csv')
    pending=output/'e2e_metrics.in_progress.csv'
    if pending.exists():pending.unlink()
