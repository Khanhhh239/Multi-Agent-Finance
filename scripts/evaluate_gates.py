"""Cổng từ CSV hiện hành; thiếu giao thức hoặc thiếu bằng chứng không được coi là đạt."""
from pathlib import Path
import sys
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,ROOT


def main():
    rows={f'G{i}':dict(gate=f'G{i}',status='pending',reason='Chưa đủ bằng chứng theo giao thức mới',evidence='') for i in range(1,19)}
    def set_gate(g,passed,reason,evidence):
        rows[g]=dict(gate=g,status='passed' if passed else 'failed',reason=reason,evidence=evidence)
    def load(path,allow_legacy=False):
        p=OUT/path
        if not p.exists():return None
        df=pd.read_csv(p)
        if 'measurement_version' not in df:return None
        hazard=path.startswith(('t1/A_','t1/B_','t1/EF_','t1/T9_T1_'))
        if hazard and not allow_legacy and not df.measurement_version.fillna('').str.contains('fullweek').all():return None
        return df
    a=load('t1/A_rolling_origin_src.csv')
    if a is not None:
        m=a[a.model=='DH-GBM'].set_index('setting');b=a[a.model=='B1-cust-median'].set_index('setting')
        set_gate('G1',len(m)>=2 and (m.WAPE_collect_w1_4<=.7*b.WAPE_collect_w1_4).all(),'Giảm WAPE >=30% ở hai origin','outputs/t1/A_rolling_origin_src.csv')
        set_gate('G2',len(m)>=2 and (m.IBS_13w<=.8*b.IBS_13w).all(),'IBS so với B1 trên hai origin','outputs/t1/A_rolling_origin_src.csv')
        cal=a[a.model=='DH-GBM+CQR']
        set_gate('G3',len(cal)>=2 and cal.cov80.between(.75,.85).all(),'Độ phủ DH-GBM+CQR ở đủ hai origin theo ngưỡng cổng 75–85%','outputs/t1/A_rolling_origin_src.csv')
        set_gate('G4',(m.ECE_4w<=.05).all(),'ECE4 <=0.05 trên cả hai origin','outputs/t1/A_rolling_origin_src.csv')
    c_path='t1/C_real_domains.legacy_expand.csv' if (OUT/'t1/C_real_domains.legacy_expand.csv').exists() else 't1/C_real_domains.csv'
    c=load(c_path,allow_legacy=True)
    if c is not None:
        hr=c[c.setting.str.contains('customer_invoices')]
        if len(hr):
            base=hr[hr.model=='B1-cust-median'].MAE_p50.iloc[0]
            set_gate('G5',hr[hr.model=='ENS DH-GBM+QLGBM'].MAE_p50.iloc[0]<=.9*base,'Ensemble vs B1 trên AR thật, cohort đã chín','outputs/'+c_path)
        wins=[]
        for name,g in c.groupby('setting'):
            base=g[g.model=='B1d-cust-quantiles'].pinball_avg.iloc[0]
            wins.append(g[g.model=='ENS DH-GBM+QLGBM'].pinball_avg.iloc[0]<=base)
        set_gate('G6',len(wins)>=2 and all(wins),'Ensemble không thua B1d trên hai bộ thật','outputs/'+c_path)
    for old in ['G5','G6']:
        rows[old+'_v1']=dict(rows[old],gate=old+'_v1',reason='LEGACY v1: '+rows[old]['reason'])
        rows[old]=dict(gate=old,status='pending',reason='Chờ BLEND giao thức v2',evidence='outputs/t1/real_v2/C_real_v2.csv')
    v2=load('t1/real_v2/C_real_v2.csv')
    if v2 is not None:
        from agent1.eval.real_v2_gates import real_v2_decisions
        reference=load('t1/real_v2/B1_reference.csv')
        decisions=real_v2_decisions(v2,reference)
        for gate in ['G5','G6']:set_gate(gate,decisions[gate],decisions['reason'],'outputs/t1/real_v2/C_real_v2.csv')
    g3_protocol=OUT/'t1/G3/protocol.json'
    g3=load('t1/G3/metrics.csv')
    if g3 is not None and g3_protocol.exists():
        import json
        protocol=json.loads(g3_protocol.read_text(encoding='utf-8'))
        if protocol.get('complete'):
            candidate=g3[g3.model=='mondrian_two_sided'].sort_values('origin')
            reference=g3[g3.model=='global_two_sided'].sort_values('origin')
            passed=(len(candidate)==2 and len(reference)==2 and candidate.cov80.between(.75,.85).all()
                and (candidate.IS80.to_numpy()<=reference.IS80.to_numpy()).all()
                and candidate.measurement_version.str.endswith('-fullweek').all())
            set_gate('G3',passed,'Mondrian CQR nguồn: cov80 75–85% ở hai gốc và IS80 không xấu hơn CQR hai phía toàn cục','outputs/t1/G3/metrics.csv')
    b=load('t1/B_domain_adaptation_tgt.csv')
    if b is not None:
        g=b[b.months_history==12]
        if len(g):set_gate('G7',g[g.model=='FINE-TUNE src->tgt'].pinball_avg.iloc[0]<=.9*g[g.model=='SRC-only DH-GBM (zero-shot)'].pinball_avg.iloc[0],'Fine-tune M12 cải thiện pinball >=10%','outputs/t1/B_domain_adaptation_tgt.csv')
    s=load('t2_t3/t2_sba_variants.csv')
    if s is not None:
        g=s[(s.exempt_policy=='drop')&(s.stratum=='term<=120')&s.model.str.contains('isotonic')]
        if len(g):
            r=g.iloc[0];set_gate('G8',r.PR_AUC>=2*r.base_rate and r.ECE<=.02 and .8<=r.expected_vs_actual_default_amount<=1.25,'SBA drop EXEMPT, kỳ hạn <=120 tháng, nhãn chín trước test','outputs/t2_t3/t2_sba_variants.csv')
    t4=load('t4/t4_revenue_forecast.csv')
    if t4 is not None:
        flags=[]
        for setting,g in t4[t4.setting.str.startswith('synthetic')].groupby('setting'):
            flags.append(g[g.model=='Global-LGBM-Q+CQR'].SPL.min()<=g[g.model.isin(['Seasonal-naive','Mean-13w'])].SPL.min())
        set_gate('G9',len(flags)>=2 and all(flags),'So mốc doanh thu trên nguồn và đích','outputs/t4/t4_revenue_forecast.csv')
        g=t4[t4.setting.str.contains('real Online Retail II')]
        if len(g):set_gate('G10',g[~g.model.isin(['Seasonal-naive','Mean-13w'])].SPL.min()<=g[g.model.isin(['Seasonal-naive','Mean-13w'])].SPL.min(),'Đối chứng thật, có phân biệt cụm series','outputs/t4/t4_revenue_forecast.csv')
    rules=OUT/'rules/rules_review.csv'
    if rules.exists():set_gate('G11',not pd.read_csv(rules).needs_review.any(),'Quy tắc cần cả hồi quy và xác minh chuyên môn; hiện chưa xác minh','outputs/rules/rules_review.csv')
    e=OUT/'e2e/e2e_metrics.csv'
    if e.exists():
        g=pd.read_csv(e)
        if 'measurement_version' not in g or not g.measurement_version.fillna('').str.contains('fullweek').all():
            rows['G12']=dict(gate='G12',status='pending',reason='Chờ chạy lại E2E với expand fullweek; CSV cũ chỉ kiểm toán',evidence='outputs/e2e/e2e_metrics.csv')
        elif not g.full_protocol.all():
            set_gate('G12',False,'E2E hiện chưa đủ mô hình fine-tune và bốn đối chứng; không được dùng smoke để nghiệm thu','outputs/e2e/e2e_metrics.csv')
        elif 'oracle_ablation_completed' in g and not g.oracle_ablation_completed.all():
            set_gate('G12',False,'Đang chạy ablation cùng đầu vào/ngân sách; chưa đủ bằng chứng E2E','outputs/e2e/e2e_metrics.csv')
        elif 'label_mode' in g and 'model' in g:
            estimated=g[g.label_mode=='estimated_T9']
            main=estimated[estimated.model=='MC-copula-t + ACI']
            baselines=['Direct LGBM-Q (src)','Naive (known out + avg in)','MC-independent (rho=0)','MC with B1 point dates']
            intervals=estimated.pivot(index='horizon',columns='model',values='IS80')
            complete=set(baselines+['MC-copula-t + ACI'])<=set(intervals.columns) and len(main)==2
            better=complete and (intervals[baselines].sub(intervals['MC-copula-t + ACI'],axis=0)>0).all().all()
            sf=OUT/'e2e/protocol/t6_shortfall_metrics.csv';brier_ok=False
            if sf.exists():
                values=pd.read_csv(sf).set_index('model')
                brier_ok=all(values.loc['MC-copula-t (T1+T4+T5)',f'Brier_{h}w']<values.loc['Naive (known out + avg in)',f'Brier_{h}w'] for h in [4,13])
            set_gate('G12',complete and main.cov80.between(.75,.85).all() and better and brier_ok,
                'Nhãn T9 ước lượng: cov80 75–85%, IS80 thắng đủ bốn đối chứng, Brier thắng naive','outputs/e2e/e2e_metrics.csv')
    alerts=OUT/'e2e/protocol/alert_policy.csv' if e.exists() and pd.read_csv(e).full_protocol.all() else OUT/'t6/alert_policy.csv'
    if alerts.exists():
        g=pd.read_csv(alerts);g=g[(g.model=='MC-copula-t (T1+T4+T5)')&(g.cost_ratio==5)&(g.horizon==13)]
        if len(g):
            r=g.iloc[0];set_gate('G13_v1',r.n_events>0 and r.detected_at_least_4w>=.7 and r.median_lead_weeks>=4 and r.false_alarms_per_firm_year<=1,'v1 (kiểm toán): ngưỡng theo chi phí từng tuần trên 144 điểm nguồn',str(alerts.relative_to(OUT.parent)))
    # G13 v2 (đăng ký trước: docs/03_Evaluation/G13_ALERT_POLICY.md): isotonic + xác nhận k tuần, chọn trên backtest src.
    v2=OUT/'e2e/protocol/alert_policy_v2.csv'
    if v2.exists():
        g=pd.read_csv(v2);g=g[(g.model=='MC-copula-t (T1+T4+T5)')&(g.calibration=='isotonic')&(g.horizon==13)]
        if len(g):
            r=g.iloc[0];set_gate('G13',r.n_events>0 and r.detected_at_least_4w>=.7 and r.median_lead_weeks>=4 and r.false_alarms_per_firm_year<=1,
                f'Isotonic + xác nhận {int(r.k)} tuần, τ={r.tau:g}, chọn trên backtest src; phát hiện {r.detected_at_least_4w:.2f} [{r.detected_ci_low:.2f}; {r.detected_ci_high:.2f}], báo giả {r.false_alarms_per_firm_year:.2f}/công ty-năm',
                'outputs/e2e/protocol/alert_policy_v2.csv')
    # Tham khảo (không thay G13): cùng chính sách đóng băng trên bộ niêm phong tgt2, nhãn oracle (cận trên).
    t2=OUT/'tgt2/alert_policy_tgt2.csv'
    if t2.exists():
        g=pd.read_csv(t2);g=g[(g.model=='MC-copula-t (T1+T4+T5)')&(g.calibration=='isotonic')]
        if len(g):
            r=g.iloc[0];set_gate('G13_tgt2',r.n_events>0 and r.detected_at_least_4w>=.7 and r.median_lead_weeks>=4 and r.false_alarms_per_firm_year<=1,
                f'THAM KHẢO, nhãn oracle (cận trên): {int(r.n_events)} sự kiện, phát hiện {r.detected_at_least_4w:.2f} [{r.detected_ci_low:.2f}; {r.detected_ci_high:.2f}], báo giả {r.false_alarms_per_firm_year:.2f} [{r.fa_ci_low:.2f}; {r.fa_ci_high:.2f}]',
                'outputs/tgt2/alert_policy_tgt2.csv')
    t7=load('t7/t7_changepoint.csv')
    if t7 is not None:
        g=t7[t7.world.str.startswith('held-out')]
        passed=((g.detection_rate_180d>=.5)&(g.false_alarms_per_cust_year<=.5)).any()
        set_gate('G14',passed,'Bộ phát hiện chọn ngưỡng trên nguồn; kết quả giữ lại','outputs/t7/t7_changepoint.csv')
    t9=load('t9/t9_reconciliation_tgt.csv')
    if t9 is not None:
        g=t9[t9.method.str.startswith('Hybrid')]
        if len(g):
            r=g.iloc[0];rules_f1=t9[t9.method.str.startswith(('R1','R2'))].link_f1.max()
            set_gate('G15',r.link_f1>=.8 and r.link_f1>rules_f1 and r.pay_date_MAE_est_days<=3 and r.link_precision>=.95 and r.auto_txn_coverage>=.6,'WP4: F1 >=.80 và thắng quy tắc, precision >=.95, tự động >=.6, MAE ngày <=3','outputs/t9/t9_reconciliation_tgt.csv')
    t0=OUT/'wp0/T0_quality_metrics.csv'
    p5_policy=OUT/'t9/sprint3/source_policy.json'
    p5_metrics=OUT/'t9/sprint3/target_metrics.csv'
    if p5_policy.exists() and p5_metrics.exists():
        import json
        protocol=json.loads(p5_policy.read_text(encoding='utf-8'))
        if protocol.get('complete') and protocol.get('target_complete') and protocol.get('target_used') is False:
            candidates=pd.read_csv(p5_metrics);part=candidates[candidates.world=='tgt']
            deployed=part[part.method=='Deployment source-selected']
            if len(deployed)==1:
                r=deployed.iloc[0];baseline=part[part.method.isin(['R1','R2'])].link_f1.max()
                rows['G15_v1']=dict(rows['G15'],gate='G15_v1',reason='LEGACY allocation: '+rows['G15']['reason'])
                set_gate('G15',r.link_f1>=.8 and r.link_f1>baseline and r.link_precision>=.95 and
                    r.auto_txn_coverage>=.6 and r.pay_date_MAE_est_days<=3,
                    'T9 P5: tau/ứng viên chọn trên DN nguồn; F1 >=.8, precision >=.95, coverage >=.6, MAE ngày <=3; chưa đổi pipeline E2E',
                    'outputs/t9/sprint3/target_metrics.csv')
    if t0.exists():
        r=pd.read_csv(t0).iloc[0];set_gate('G16',r.precision>=.95 and r.recall>=.95,'Chèn lỗi có nhãn, precision/recall >=.95','outputs/wp0/T0_quality_metrics.csv')
    ef=load('t1/EF_t8_t9.csv');noisy=load('t1/EF_t8_t9_src_noisy_promises.csv')
    promise_models={'DH-GBM with promises (T8)','DH-GBM without promises'}
    if ef is not None and noisy is not None and all(promise_models<=set(f.model) for f in [ef,noisy]):
        flags=[]
        for frame in [ef,noisy]:
            on=frame[frame.model=='DH-GBM with promises (T8)'].MAE_p50_promised_only.iloc[0]
            off=frame[frame.model=='DH-GBM without promises'].MAE_p50_promised_only.iloc[0]
            flags.append(on<=.9*off)
        set_gate('G17',all(flags),'Giảm MAE >=10% trên lời hứa sạch và nhiễu','outputs/t1/EF_t8_t9*.csv')
    if ef is not None:
        bank=ef[ef.model=='DH-GBM trained on BANK dates (T9)'].WAPE_collect_w1_4.iloc[0]
        ledger=ef[ef.model=='DH-GBM trained on LEDGER dates'].WAPE_collect_w1_4.iloc[0]
        rows['G18']=dict(gate='G18',status='partial',reason=f'Oracle bank/ledger WAPE={bank:.6g}/{ledger:.6g}; cần nhãn T9 ước lượng để nghiệm thu',evidence='outputs/t1/EF_t8_t9.csv')
    propagation=load('t1/T9_T1_gap_reduction.csv')
    if propagation is not None and set(propagation.horizon)=={'w1-4','w5-13'}:
        set_gate('G18',propagation.target_met.all(),'Điểm ước lượng: T9 thu hẹp >=50% khoảng cách WAPE với oracle ở cả hai chân trời; CI xa còn rộng, không bảo đảm cho mọi DN',
                 'outputs/t1/T9_T1_gap_reduction.csv')
    df=pd.DataFrame(rows.values());df.to_csv(OUT/'implementation/gates.csv',index=False)
    required=['G1','G2','G5','G9','G11','G12','G13','G15','G16']
    ready=df.set_index('gate').loc[required,'status'].eq('passed').all()
    text='# Cổng hiện hành (sinh tự động)\n\nTrạng thái pilot: **'+('GO' if ready else 'NO-GO')+'**.\n\n'
    text+='| Cổng | Trạng thái | Bằng chứng / lý do |\n|---|---|---|\n'
    for r in df.itertuples():text+=f'| {r.gate} | {r.status} | {r.reason} (`{r.evidence}`) |\n'
    (ROOT/'docs/03_Evaluation/GATES_CURRENT.md').write_text(text,encoding='utf-8')
    print('pilot:', 'GO' if ready else 'NO-GO')


if __name__=='__main__':main()
