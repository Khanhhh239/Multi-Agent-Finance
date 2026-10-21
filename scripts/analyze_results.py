"""Kết luận DA và các kết quả chưa đạt, số đọc trực tiếp từ CSV hiện hành."""
from pathlib import Path
import json
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,ROOT


def main():
    rows=[]
    b=OUT/'t1/B_domain_adaptation_tgt.csv'
    if b.exists():
        frame=pd.read_csv(b)
        def row(months,model):
            result=frame[(frame.months_history==months)&(frame.model==model)]
            return result.iloc[0] if len(result) else None
        zero=row(0,'SRC-only DH-GBM (zero-shot)');base=row(0,'B1-cust-median')
        gain=1-zero.WAPE_collect_w1_4/base.WAPE_collect_w1_4
        rows.append(dict(hypothesis='DA1',status='supported_point_estimate' if gain>=.2 else 'rejected_point_estimate',
            measured_value=gain,target='WAPE giảm >=20% so B1 ở M0',
            limitation='Chưa có CI cặp cho WAPE; chưa nghiệm thu đầy đủ'))
        ft=row(3,'FINE-TUNE src->tgt');zero3=row(3,'SRC-only DH-GBM (zero-shot)')
        gain=1-ft.pinball_avg/zero3.pinball_avg
        rows.append(dict(hypothesis='DA2',status='supported_point_estimate' if gain>=.1 else 'rejected_point_estimate',
            measured_value=gain,target='Pinball fine-tune M3 giảm >=10% so zero-shot',
            model_ci_low=ft.pinball_ci_low,model_ci_high=ft.pinball_ci_high,
            baseline_ci_low=zero3.pinball_ci_low,baseline_ci_high=zero3.pinball_ci_high,
            limitation='CI từng mô hình; chưa có CI cặp cho hiệu số'))
        early=all(row(m,'FINE-TUNE src->tgt').pinball_avg<=row(m,'TGT-only DH-GBM').pinball_avg for m in [3,6])
        catchup=row(24,'TGT-only DH-GBM').pinball_avg<=row(24,'FINE-TUNE src->tgt').pinball_avg
        rows.append(dict(hypothesis='DA3',status='supported_point_estimate' if early and catchup else 'rejected_point_estimate',
            measured_value=row(24,'TGT-only DH-GBM').pinball_avg/row(24,'FINE-TUNE src->tgt').pinball_avg,
            target='Fine-tune thắng ở M3/M6 và TGT-only bắt kịp tại M24',limitation='Bắt kịp được hiểu là pinball <= fine-tune'))
        rows.append(dict(hypothesis='DA4',status='not_measured',target='IW thắng pooled khi khoảng cách miền lớn',
            limitation='B hiện chỉ đo tgt; thiếu so sens_* và CI cặp'))
        cqr=row(3,'FINE-TUNE src->tgt+CQR')
        rows.append(dict(hypothesis='DA5',status='not_measured' if cqr is None else ('supported' if .75<=cqr.cov80<=.85 else 'rejected'),
            measured_value=cqr.cov80 if cqr is not None else float('nan'),target='CQR M3 có cov80 75–85%',
            limitation='M3 không đủ cửa sổ hiệu chỉnh tách 120 ngày; không dùng test để lấp'))
    for name,reason in [('DA6','Chưa có đường scaling và M* từ nguồn lớn'),('DA7','Chưa có ablation sốc chung ở các cửa sổ khủng hoảng')]:
        if name=='DA7' and (OUT/'t1/crisis_ablation.csv').exists():
            crisis=pd.read_csv(OUT/'t1/crisis_ablation.csv')
            primary=crisis[(crisis.world=='tgt')&(crisis.model=='shock_28d')]
            if set(primary.regime_start)=={'2021-07-01','2022-10-01'}:
                supported=(primary.improvement_ci_low>0).all()
                rows.append(dict(hypothesis='DA7',status='supported' if supported else 'not_demonstrated',
                    measured_value=primary.improvement_pct.min(),target='Đặc trưng sốc chung giảm pinball ở cả hai giai đoạn khủng hoảng; CI cặp >0',
                    limitation='Nguồn trước mỗi origin 120 ngày; cùng ngân sách; tổng hợp; fast_30d_7d là đối chứng phụ, không chọn cấu hình theo tgt'))
                continue
        if name=='DA6' and (OUT/'t1/scaling_M_star.csv').exists():
            scaling=pd.read_csv(OUT/'t1/scaling_M_star.csv').sort_values('expanded_rows')
            if set([1000000,3000000,10000000])<=set(scaling.expanded_rows) and 'bootstrap_n' in scaling:
                small,large=scaling.iloc[0],scaling.iloc[-1]
                probability=large.paired_prob_largest_needs_less_history_than_smallest
                supported=large.M_star<small.M_star and probability>=.95
                rows.append(dict(hypothesis='DA6',status='supported' if supported else 'not_demonstrated',
                    measured_value=probability,target='Nguồn lớn >=5x giảm M*; bootstrap cặp theo công ty',
                    limitation='M*: zero-shot tại M0, fine-tune khi M>0; ngưỡng pinball <=0.9 B1d; kiểm trên tổng hợp'+
                        ('; cả ba đã ở sàn M*=0, chưa thể chứng minh giảm thêm lịch sử' if scaling.M_star.eq(0).all() else '')))
                continue
        rows.append(dict(hypothesis=name,status='not_measured',limitation=reason))
    protocol_path=OUT/'t1/DA_paired_protocol.json'
    paired_path=OUT/'t1/DA_paired_comparisons.csv'
    if protocol_path.exists() and paired_path.exists() and json.loads(protocol_path.read_text(encoding='utf-8')).get('complete'):
        comparisons=pd.read_csv(paired_path)
        for name in ['DA1','DA2','DA3','DA4']:
            selected=comparisons[comparisons.hypothesis==name]
            if name=='DA4':selected=selected[selected.world.isin(['sens_uk','sens_coface'])]
            expected=3 if name=='DA3' else 2 if name=='DA4' else 1
            if len(selected)!=expected:continue
            supported=(selected.improvement_ci_low>=selected.threshold_pct).all()
            if name=='DA4':supported=(selected.improvement_ci_low>0).all()
            rejected=(selected.improvement_ci_high<selected.threshold_pct).any()
            old=next(row for row in rows if row['hypothesis']==name)
            replacement=dict(hypothesis=name,status='supported' if supported else 'rejected' if rejected else 'not_demonstrated',
                measured_value=selected.improvement_pct.min(),paired_ci_low=selected.improvement_ci_low.min(),
                paired_ci_high=selected.improvement_ci_high.max(),target=old['target'],
                evidence='outputs/t1/DA_paired_comparisons.csv',
                limitation='Xác nhận riêng: tối đa 40k snapshot nguồn/đích, 300 vòng, FT 150; không thay bảng B cũ. '+
                    ('DA3 là giao của M3/M6/M24.' if name=='DA3' else 'DA4 yêu cầu cả sens_uk và sens_coface có CI >0; tgt là đối chứng.' if name=='DA4' else 'CI phải đạt ngưỡng giả thuyết, không chỉ ước lượng điểm.'))
            rows[rows.index(old)]=replacement
    hypotheses=pd.DataFrame(rows)
    current=True
    for source in ['t1/B_domain_adaptation_tgt.csv','t1/DA_paired_comparisons.csv','t1/crisis_ablation.csv','t1/scaling_M_star.csv']:
        candidate_path=OUT/source
        if not candidate_path.exists():current=False;break
        versions=pd.read_csv(candidate_path)
        if 'measurement_version' not in versions or not versions.measurement_version.fillna('').str.contains('fullweek').all():
            current=False;break
    hypotheses['measurement_version']='da-asof-evidence-v2-fullweek' if current else 'da-asof-evidence-v2-legacy-expand-pending'
    hypotheses.to_csv(OUT/'t1/DA_hypotheses.csv',index=False)
    text='# Kết quả chưa đạt và giới hạn bằng chứng\n\n'
    text+='Sinh bởi `scripts/analyze_results.py`; không dùng chỉ số đích để chọn tham số.\n\n'
    v2=OUT/'t1/real_v2/C_real_v2.csv'
    if v2.exists():
        selected=pd.read_csv(v2)
        selected=selected[selected.model.str.startswith('BLEND(DH-GBM,B1d) w=')]
        text+='## Dữ liệu thật v2 sau sửa lỗi expand, cập nhật 21/10/2026\n\n'
        for row in selected.itertuples():
            text+=f'- {row.setting}, {row.model}: pinball {row.pinball_avg:.4f}, cải thiện vs B1d {row.improvement_vs_B1d_pct:.3f}%, CI [{row.improvement_ci_low:.3f}, {row.improvement_ci_high:.3f}]%. w chọn trên calibration rồi refit; bootstrap theo khách, chưa đại diện SME VN.\n'
        text+='\nCác kết luận v1 bên dưới chỉ để kiểm toán. Lỗi tuần bị cắt, LR ngoại suy và chia dữ liệu bỏ đói đã được xác định trong nhật ký Sprint 1; không dùng v1 để kết luận BLEND v2 thua mốc.\n\n'
    p=OUT/'t1/C_real_domains.legacy_expand.csv'
    if not p.exists():p=OUT/'t1/C_real_domains.csv'
    if p.exists():
        for name,g in pd.read_csv(p).groupby('setting'):
            ens=g[g.model=='ENS DH-GBM+QLGBM'].iloc[0];base=g[g.model=='B1d-cust-quantiles'].iloc[0]
            text+=f'- **LEGACY v1** {name}: pinball ensemble {ens.pinball_avg:.4f}, B1d {base.pinball_avg:.4f}; '
            text+='giả thuyết ensemble không thua mốc bị bác bỏ.\n' if ens.pinball_avg>base.pinball_avg else 'ensemble đạt so sánh điểm.\n'
    p=OUT/'t6/t6_interval_metrics.csv'
    if p.exists():
        for r in pd.read_csv(p).query("model == 'MC-copula-t + ACI'").itertuples():
            text+=f'- T6 {r.horizon}: cov80={r.cov80:.4f}, CI [{r.cov80_ci_low:.4f}, {r.cov80_ci_high:.4f}]. Nhãn ở thí nghiệm này là nhãn thật tổng hợp, chưa phải E2E từ nhãn T9 ước lượng.\n'
    p=OUT/'data/c2st.csv'
    if p.exists():
        for r in pd.read_csv(p).itertuples():
            text+=f'- C2ST {r.world}: AUC={r.AUC:.4f}, CI [{r.ci_low:.4f}, {r.ci_high:.4f}]; '+('không đạt mục tiêu <0.75.\n' if r.AUC>=.75 else 'đạt mục tiêu điểm <0.75.\n')
    p=OUT/'data/generator_benchmark.csv'
    if p.exists():
        for r in pd.read_csv(p).itertuples():
            text+=f'- Máy phát: tăng tốc {r.speedup:.3f}× trên {r.n_invoices} HĐ; chưa chứng minh >=5× tại 1M HĐ.\n'
    text+='\nNgoài lỗi expand/ngoại suy/chia dữ liệu v1 đã xác định ở Sprint 1, không suy nguyên nhân của các kết quả còn lại chỉ từ bảng điểm hoặc tự quy cho domain shift. CSV hazard chưa có fullweek chỉ dùng kiểm toán trong lúc chờ chuỗi chạy lại.\n'
    p=OUT/'t1/A_tuned_equal_budget.csv'
    if p.exists():
        tuned=pd.read_csv(p);base=tuned[tuned.model=='DH-GBM default (equal budget)'].iloc[0]
        candidate=tuned[tuned.model=='DH-GBM tuned'].iloc[0]
        gain=1-candidate.pinball_avg/base.pinball_avg
        comparison=dict(pinball_gain_pct=100*gain,target_pct=3.,candidate_cov80=candidate.cov80,baseline_cov80=base.cov80,
            candidate_ECE=candidate.ECE_4w,baseline_ECE=base.ECE_4w,
            improvement_ci_low=candidate.vs_default_improvement_ci_low,improvement_ci_high=candidate.vs_default_improvement_ci_high,
            meets_target=bool(gain>=.03 and candidate.ECE_4w<=base.ECE_4w and abs(candidate.cov80-.8)<=abs(base.cov80-.8)),
            candidate_adopted=False,test_used_for_selection=False,measurement_version='tuning-source-equal-budget-v1')
        pd.DataFrame([comparison]).to_csv(OUT/'t1/tuning_comparison.csv',index=False)
        text+=f'\n- Tuning cùng ngân sách: thay đổi pinball {100*gain:.3f}%; CI cải thiện [{comparison["improvement_ci_low"]:.3f}, {comparison["improvement_ci_high"]:.3f}]%. Tham số mới chưa được đưa vào mô hình mặc định.\n'
    text+='\nHome Credit/SEC tạm bỏ theo Q1/Q2; không có dữ liệu người thật, xác minh chuyên môn, UAT ba người hoặc pilot.\n'
    p=OUT/'t1/BPI_no_due_ablation.csv'
    if p.exists():
        candidate=pd.read_csv(p).query("model == 'DH-GBM virtual30 age/no_due'").iloc[0]
        text+=f'\n- BPI không hạn: thêm hạn ảo/tuổi thay đổi pinball {candidate.vs_current_improvement_pct:.3f}% (dương là cải thiện), CI [{candidate.vs_current_improvement_ci_low:.3f}, {candidate.vs_current_improvement_ci_high:.3f}]%; không tự áp dụng. Chỉ có {candidate.n_firms} cụm DN; BPI là phải trả, không phải AR Việt Nam.\n'
    p=OUT/'t1/T3_T1_ablation.csv'
    if p.exists():
        frame=pd.read_csv(p)
        for candidate in frame[(frame.model=='DH-GBM + dispute EB at issue')&(frame.stratum=='disputed')].itertuples():
            text+=f'\n- T3→T1 nhóm tranh chấp {candidate.setting}: cải thiện pinball {candidate.vs_default_improvement_pct:.3f}%, CI [{candidate.vs_default_improvement_ci_low:.3f}, {candidate.vs_default_improvement_ci_high:.3f}]%; chưa đưa đặc trưng vào mặc định. Nhãn tranh chấp chỉ dùng phân nhóm chấm điểm, đầu vào là lịch sử đã đóng tại ngày lập.\n'
    p=OUT/'t6/additional_baseline_comparisons.csv'
    if p.exists():
        frame=pd.read_csv(p)
        for candidate in frame[(frame.metric=='IS80')&(frame.challenger=='Chronos-Bolt Tiny zero-shot')].itertuples():
            text+=f'\n- E2E ACI so Chronos-Bolt Tiny ({candidate.horizon}): cải thiện IS80 {candidate.main_improvement_pct:.3f}%, CI [{candidate.main_improvement_ci_low:.3f}, {candidate.main_improvement_ci_high:.3f}]%. G12 chỉ kiểm bốn đối chứng gốc; không suy từ G12 rằng đã thắng mọi đối chứng bổ sung. Không chọn lại mô hình theo test.\n'
    p=OUT/'t9/hard_case_recall.csv'
    if p.exists():
        frame=pd.read_csv(p);hybrid=frame[frame.method.str.startswith('Hybrid')]
        text+=f'\nT9 đã có {hybrid["case"].nunique()}/12 thế giới ở kỳ giữ lại 2024-07→2025-06. Kỳ này không bao phủ đợt supply_shock năm 2022; xem ngày sao kê thực tế ở CSV, đặc biệt DN mới chỉ xuất hiện từ 2025.\n'
        for candidate in hybrid[(hybrid.link_precision<.95)|(hybrid.link_f1<.8)].itertuples():
            text+=f'- T9 {candidate.case}: precision {candidate.link_precision:.4f}, recall {candidate.link_recall:.4f}, F1 {candidate.link_f1:.4f}, tự động {candidate.auto_txn_coverage:.4f}; chưa đạt đồng thời precision >=.95 và F1 >=.80.\n'
    p=OUT/'t2_t3/sba_macro_comparisons.csv'
    if p.exists():
        for candidate in pd.read_csv(p).itertuples():
            text+=f'\n- SBA cohort trước ({candidate.exempt_policy}): cải thiện Brier {candidate.improvement_pct:.3f}%, CI [{candidate.improvement_ci_low:.3f}, {candidate.improvement_ci_high:.3f}]%; {candidate.decision}. Trễ công bố 90 ngày là giả định, không có vintage lịch sử; chưa áp dụng đặc trưng này.\n'
    p=OUT/'t7/regime_cash/metrics.csv'
    regime_protocol=OUT/'t7/regime_cash/protocol.json'
    if p.exists() and regime_protocol.exists() and json.loads(regime_protocol.read_text(encoding='utf-8')).get('complete'):
        for candidate in pd.read_csv(p).query("model == 'with_controller' and horizon == 'all'").itertuples():
            text+=f'\n- T7→T6 {candidate.window}: cov80 {candidate.cov80:.4f}, CI [{candidate.cov80_ci_low:.4f}, {candidate.cov80_ci_high:.4f}]; thay đổi độ phủ {candidate.coverage_change:.4f}, CI [{candidate.coverage_change_ci_low:.4f}, {candidate.coverage_change_ci_high:.4f}]. '+('Chưa đạt 70%.' if not candidate.point_coverage_target_met else 'Đạt ngưỡng điểm 70%.')+' Ngưỡng chọn trên nguồn; lịch thu lý tưởng, khác E2E T9.\n'
    p=OUT/'t6/collection_policy/P2_vs_P1.csv'
    policy_protocol=OUT/'t6/collection_policy/protocol.json'
    if p.exists() and policy_protocol.exists() and json.loads(policy_protocol.read_text(encoding='utf-8')).get('complete'):
        for candidate in pd.read_csv(p).query("metric == 'DSO'").itertuples():
            text+=f'\n- Thu nợ q={candidate.q}: P2 so P1 giảm DSO {candidate.reduction_P2_vs_P1:.3f} ngày, CI [{candidate.reduction_ci_low:.3f}, {candidate.reduction_ci_high:.3f}]; {candidate.decision}. Mô phỏng phản hồi giả định, chưa phải tác động nhân quả hoặc ROI.\n'
    p=OUT/'t6/copula_hierarchy/metrics.csv'
    copula_protocol=OUT/'t6/copula_hierarchy/protocol.json'
    if p.exists() and copula_protocol.exists() and json.loads(copula_protocol.read_text(encoding='utf-8')).get('complete'):
        candidate=pd.read_csv(p).query("horizon == 'all' and model == 'source_selected_hierarchical'").iloc[0]
        text+=f'\n- Copula phân tầng: IS80 cải thiện {candidate.vs_one_factor_improvement_pct:.3f}%, CI [{candidate.vs_one_factor_improvement_ci_low:.3f}, {candidate.vs_one_factor_improvement_ci_high:.3f}]% so một nhân tố chọn trên nguồn. Cov80 khoảng thô {candidate.cov80:.4f}; chưa thay E2E hoặc tự đưa vào dịch vụ.\n'
    p=OUT/'t1/IW_oof/comparisons.csv';iw_protocol=OUT/'t1/IW_oof/protocol.json'
    if p.exists() and iw_protocol.exists() and json.loads(iw_protocol.read_text(encoding='utf-8')).get('complete'):
        for candidate in pd.read_csv(p).query("baseline == 'pooled'").itertuples():
            text+=f'\n- IW ngoài công ty {candidate.world}, M6: pinball cải thiện {candidate.improvement_pct:.3f}%, CI [{candidate.improvement_ci_low:.3f}, {candidate.improvement_ci_high:.3f}]%; {candidate.status}. Ablation thăm dò, không thay DA4 gốc hoặc tự áp dụng. AUC/ESS trong bảng chẩn đoán không xác nhận hai miền chồng lấn.\n'
    p=OUT/'t1/DR/decisions.csv';dr_protocol=OUT/'t1/DR/protocol.json'
    if p.exists() and dr_protocol.exists() and json.loads(dr_protocol.read_text(encoding='utf-8')).get('complete'):
        for candidate in pd.read_csv(p).itertuples():
            text+=f'\n- DR 20×20 so 1×400 trên {candidate.target}: cải thiện pinball {candidate.improvement_pct:.3f}%, CI [{candidate.improvement_ci_low:.3f}, {candidate.improvement_ci_high:.3f}]%; ngưỡng định trước 5%, {candidate.status}. Cùng số HĐ theo cặp DN; seed nguồn đơn, chưa có bất định qua nhiều lần sinh nguồn.\n'
    p=OUT/'t9/supply_shock_2022/metrics.csv';shock_protocol=OUT/'t9/supply_shock_2022/protocol.json'
    if p.exists() and shock_protocol.exists() and json.loads(shock_protocol.read_text(encoding='utf-8')).get('complete'):
        for candidate in pd.read_csv(p).query("stratum == 'steel_shock'").itertuples():
            if candidate.method.startswith('Hybrid'):
                text+=f'\n- T9 sốc cung ứng 2022, nhóm thép, {candidate.window}: precision {candidate.link_precision:.4f}, recall {candidate.link_recall:.4f}, F1 {candidate.link_f1:.4f}, CI F1 [{candidate.link_f1_ci_low:.4f}, {candidate.link_f1_ci_high:.4f}], tự động {candidate.auto_txn_coverage:.4f}. Mô hình nguồn 2020/calibration 2021; tau=.9 khoá trước; không tự chọn lại hoặc thay G15.\n'
    (ROOT/'docs/03_Evaluation/KET_QUA_CHUA_DAT.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
