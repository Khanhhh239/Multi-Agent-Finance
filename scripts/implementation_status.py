"""Sổ tiến độ từ bằng chứng trên đĩa; tồn tại mã không đồng nghĩa nghiệm thu."""
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,ROOT


PACKAGES=[
    ('WP-0','Nền, hợp đồng, chống rò rỉ','implementation/test_summary.csv','Môi trường khoá phiên bản; contract và kiểm thử. Xem số ca/exit code bên dưới.'),
    ('WP-1','T1','t1/A_rolling_origin_src.csv','Đã đo A/CQR/seed/tuning; tuning không đạt mục tiêu. Còn PDP/monotone, daily hazard, mixture, EB ML-II, ablation không hạn và nhãn khoảng từ quan sát hợp lệ.'),
    ('WP-2','T2/T3','t2_t3/t2_sba_variants.csv','Đã đo SBA EXEMPT và T3 as-of; còn hiệu chỉnh vĩ mô FY và tranh chấp→T1. Home Credit bỏ theo Q1.'),
    ('WP-3','Thích nghi miền','t1/B_domain_adaptation_tgt.csv','Đã đo B, onboarding nguồn, phân loại miền, DA7; scaling theo CSV bên dưới. Còn DR 1×400 so 20×20 cùng số HĐ, IW trên sens_* và CI cặp cho DA1–DA4.'),
    ('WP-4','T9','t9/t9_reconciliation_tgt.csv','Đã đo lai R2/R1/ML, as-of ledger, khách được biết, ngưỡng .9 khoá trước. Precision/F1 chưa đạt; chưa đủ thí nghiệm lan truyền T9→T1 so sổ và hard-case recall.'),
    ('WP-5','T5 và quy tắc','rules/rules_review.csv','27 quy tắc có phiên bản, hồi quy và dự phòng. Còn nghĩa vụ mở rộng, >=40 ca nghiệp vụ và xác minh chuyên gia.'),
    ('WP-6','T6/T10/E2E','e2e/e2e_metrics.csv','Đã có đầy đủ luồng XML/CSV→nguồn→fine-tune và bốn đối chứng. Kết luận cổng đọc từ CSV sau khi oracle xong. Còn chính sách P0/P1/P2, ETS/ARIMA/Chronos và phép đo copula phân tầng.'),
    ('WP-7','T7','t7/t7_changepoint.csv','Đã đo điểm gãy và Berka bán tổng hợp. Còn gắn bộ điều khiển chế độ vào T6 và đo độ phủ hai cửa sổ khủng hoảng.'),
    ('WP-8','T8','t1/EF_t8_t9_src_noisy_promises.csv','Đã sinh lời hứa nhiễu, kiểm RNG tài chính bất biến và đo E. Mức cải thiện chưa đạt G17; còn phép đo Brier reliability và luồng duyệt lời hứa từ chat.'),
    ('WP-D1','Tốc độ máy phát','data/generator_benchmark.csv','Đã vector hoá và đối chiếu seed; chưa chứng minh >=5× trên 1M HĐ. Thời gian big v2 sai do biến đếm vòng lặp đã được vô hiệu hoá, giữ số gốc để kiểm toán.'),
    ('WP-D2','Hard-case','data/hard_case_fidelity.csv','Đã có 12 trường hợp và ba bản v2 sửa lumpy/discount/supply. Còn tỷ lệ phương sai khách và chuỗi gốc–thay thế–huỷ–điều chỉnh đầy đủ; contract không thay kiểm nghiệp vụ.'),
    ('WP-D3','Nguồn lớn/C2ST','data/big_worlds.csv','Bốn big worlds đã qua contract; C2ST còn không đạt. Còn marginal độc lập/DSO ngành từ BCTC VN.'),
    ('WP-D4','Dữ liệu thật bổ sung','berka/cash_metrics.csv','Đã đo Berka và các nguồn thật hiện có. Kaggle/SEC tạm bỏ theo Q1/Q2; chưa có DSO VN/khảo sát thực tế, không tự chấp nhận điều khoản.'),
    ('WP-9','Dịch vụ local','service/local_validation.csv','API/UI/nhập file/cảnh báo mã hoá/registry/retrain/weekly đã có. Mặc định NO_GO; mô hình dịch vụ riêng DN khác luồng khoa học nguồn→fine-tune. Docker engine chưa chạy; UAT ba người chưa có.'),
    ('WP-10','Chuẩn bị pilot','pilot/pilot_metrics.csv','Có biểu mẫu và mã phân tích; chưa có dữ liệu pilot, ROI đo thật hoặc người tham gia. Chưa hoàn tất nghiệm thu ngoài thực tế.'),
]


def main():
    rows=[dict(package=p,title=t,evidence='outputs/'+f,evidence_exists=(OUT/f).exists(),remaining=n) for p,t,f,n in PACKAGES]
    variants=OUT/'t1/T1_variants.csv'
    if variants.exists():
        frame=pd.read_csv(variants)
        if set(frame.setting)=={'src','tgt'}:
            for row in rows:
                if row['package']=='WP-1':row['remaining']='Đã đo A/CQR/seed/tuning và nhánh PDP/monotone, daily 28 ngày, mixture, EB ML-II. Tham số mới chưa tự đưa vào mặc định. Còn ablation không hạn và nhãn khoảng từ quan sát hợp lệ.'
    if (OUT/'t1/T9_T1_gap_reduction.csv').exists():
        for row in rows:
            if row['package']=='WP-4':row['remaining']='Đã đo lai R2/R1/ML, as-of và lan truyền T9→T1 so sổ/NH cùng ngân sách; kết quả G15/G18 theo CSV. Còn cải thiện phân bổ và hard-case recall.'
    if (OUT/'t1/BPI_no_due_ablation.csv').exists() and variants.exists():
        for row in rows:
            if row['package']=='WP-1':row['remaining']='Đã đo A/CQR/seed/tuning, bốn nhánh mô hình và BPI không hạn. Các nhánh chưa tự đưa vào mặc định. Còn phép đo nhãn khoảng từ last_seen_open thật; MLP đa nhiệm là nhánh điều kiện, chưa thử.'
    if (OUT/'t1/T3_T1_protocol.json').exists():
        protocol=json.loads((OUT/'t1/T3_T1_protocol.json').read_text(encoding='utf-8'))
        if protocol.get('complete'):
            for row in rows:
                if row['package']=='WP-2':row['remaining']='Đã đo SBA EXEMPT, T3 as-of và tranh chấp→T1 với CI cặp; đặc trưng mới chưa đưa vào mặc định. Còn hiệu chỉnh vĩ mô FY. Home Credit bỏ theo Q1.'
    if (OUT/'t8/reliability_protocol.json').exists():
        protocol=json.loads((OUT/'t8/reliability_protocol.json').read_text(encoding='utf-8'))
        if protocol.get('complete'):
            for row in rows:
                if row['package']=='WP-8':row['remaining']='Đã đo Brier reliability sạch/nhiễu với lịch sử tuần as-of, CI cặp, API và đặc tả duyệt chat (docs/04_AI_Methods/09_promise_chat_review.md). E vẫn chưa đạt G17; chưa có UAT lời hứa người thật.'
    if (OUT/'t1/DA_paired_protocol.json').exists():
        protocol=json.loads((OUT/'t1/DA_paired_protocol.json').read_text(encoding='utf-8'))
        if protocol.get('complete'):
            for row in rows:
                if row['package']=='WP-3':row['remaining']='Đã đo B, onboarding nguồn, khoảng cách miền, DA7, scaling và xác nhận DA1–DA4 cùng ngân sách 40k nguồn/đích với CI cặp, IW trên tgt/sens_*. Còn DR 1×400 so 20×20 cùng số HĐ; DA5 M3 thiếu cửa sổ hiệu chỉnh hợp lệ.'
    hardcase_protocol=OUT/'t9/hard_cases/protocol.json'
    if hardcase_protocol.exists() and json.loads(hardcase_protocol.read_text(encoding='utf-8')).get('complete'):
        for row in rows:
            if row['package']=='WP-4':row['remaining']='Đã đo lai R2/R1/ML, as-of, lan truyền T9→T1 và recall 12 thế giới hard-case trong kỳ 2024-07→2025-06 so R1/R2. G15 còn chưa đạt; còn cải thiện phân bổ và đo quanh sốc 2022 bằng mô hình nguồn trước sốc. Không chọn ngưỡng từ các test này.'
    cash_protocol=OUT/'t6/traditional/protocol.json'
    if cash_protocol.exists() and json.loads(cash_protocol.read_text(encoding='utf-8')).get('complete'):
        chronos_protocol=OUT/'t6/chronos/protocol.json'
        chronos_done=chronos_protocol.exists() and json.loads(chronos_protocol.read_text(encoding='utf-8')).get('complete')
        for row in rows:
            if row['package']=='WP-6':row['remaining']='E2E đầy đủ và oracle cùng ngân sách đã xong; thêm ETS/ARIMA/B0 cùng 14 DN×52 tuần, CI theo công ty. '+('Chronos-Bolt Tiny zero-shot đã đo, revision cố định.' if chronos_done else 'Chronos chưa có kết quả hoàn tất.')+' Còn chính sách P0/P1/P2 và phép đo copula phân tầng; trạng thái G12/G13 đọc từ CSV.'
    for path,package,done in [
        ('t6/collection_policy/protocol.json','WP-6','Đã mô phỏng P0/P1/P2 đủ 14 DN×52 tuần, q=.3/.5/.7, CI cặp theo DN. Đây là giả lập phản hồi thu nợ với lịch thu lý tưởng, chưa chứng minh tác động nhân quả hoặc ROI. Còn phép đo copula phân tầng.'),
        ('t7/regime_cash/protocol.json','WP-7','Đã đo T6 có/không bộ điều khiển trong hai cửa sổ khủng hoảng; ngưỡng chọn trên nguồn, cách test >=120 ngày. Xem CSV độ phủ và IS với CI cặp. G14 giữ kết quả phát hiện riêng; còn xác nhận trên điểm gãy thật có nhãn.'),
        ('t1/DR/protocol.json','WP-3','Đã đo DR 1×400 so 20×20 cùng số HĐ theo cặp DN, hai thời điểm nguồn riêng cho test thật/tổng hợp; có CI cặp. DA1–DA4, DA7, onboarding và scaling đã đo. DA5 M3 thiếu cửa sổ hiệu chỉnh hợp lệ.')]:
        protocol_path=OUT/path
        if protocol_path.exists() and json.loads(protocol_path.read_text(encoding='utf-8')).get('complete'):
            for row in rows:
                if row['package']==package:
                    row['remaining']=row['remaining']+' '+done if package=='WP-6' else done
    for path,package,done in [
        ('t2_t3/sba_macro_protocol.json','WP-2','Đã đo SBA EXEMPT và ablation chu kỳ tại ngày phê duyệt với CI Brier theo proxy DN, hiệu chỉnh FY; trễ công bố 90 ngày là giả định, chưa có vintage SBA thật. T3 tranh chấp→T1 đã đo, chưa tự áp dụng. Home Credit bỏ theo Q1.'),
        ('rules/extended_obligation_protocol.json','WP-5','Có registry 27 quy tắc và bộ lịch độc lập cho bảy loại nghĩa vụ bổ sung từ hồ sơ/hợp đồng; 18 tình huống CSV và kiểm thử as-of. Chưa tích hợp lịch mở rộng vào dự báo để tránh đếm trùng; còn đủ hai ca mỗi quy tắc và chuyên gia xác minh, cập nhật pháp lý 2026.')]:
        protocol_path=OUT/path
        if protocol_path.exists() and json.loads(protocol_path.read_text(encoding='utf-8')).get('complete'):
            for row in rows:
                if row['package']==package:row['remaining']=done
    for row in rows:
        if row['package']=='WP-6' and (OUT/'t6/collection_policy/protocol.json').exists() and json.loads((OUT/'t6/collection_policy/protocol.json').read_text(encoding='utf-8')).get('complete'):
            row['remaining']=row['remaining'].replace('Còn chính sách P0/P1/P2 và phép đo copula phân tầng; trạng thái G12/G13 đọc từ CSV.','Trạng thái G12/G13 đọc từ CSV.')
    listed=OUT/'data/vn_listed_protocol.json'
    if listed.exists() and json.loads(listed.read_text(encoding='utf-8')).get('complete'):
        for row in rows:
            if row['package']=='WP-D3':row['remaining']='Bốn big worlds qua contract; C2ST còn không đạt. Đã đối chiếu DSO độc lập ba DN-kỳ SMC2024/TCM2022/NTP2024, không chỉnh máy phát. Còn marginal độc lập đầy đủ và mẫu nhiều DN/ngành.'
            if row['package']=='WP-D4':row['remaining']='Đã đo Berka, nguồn thật hiện có và DSO/DPO mô tả từ ba BCTC chính chủ (SMC2024, TCM2022, NTP2024), chưa đại diện ngành/SME. Kaggle/SEC bỏ theo Q1/Q2. Còn mở rộng mẫu BCTC và khảo sát thực tế.'
    copula=OUT/'t6/copula_hierarchy/protocol.json'
    if copula.exists() and json.loads(copula.read_text(encoding='utf-8')).get('complete'):
        for row in rows:
            if row['package']=='WP-6':row['remaining']=row['remaining'].replace('Còn phép đo copula phân tầng.','Đã chọn copula một/hai nhân tố bằng IS trên nguồn và đo CI cặp trên đích; đây là khoảng thô không ACI, lịch thu lý tưởng. Chưa tự áp dụng mô hình mới.')
    iw=OUT/'t1/IW_oof/protocol.json'
    if iw.exists() and json.loads(iw.read_text(encoding='utf-8')).get('complete'):
        for row in rows:
            if row['package']=='WP-3':row['remaining']+=' Đã đo thêm IW ngoài nguyên công ty so in-sample/pooled, M6 cùng ngân sách; ablation thăm dò, không tự đổi chính sách.'
    shock=OUT/'t9/supply_shock_2022/protocol.json'
    if shock.exists() and json.loads(shock.read_text(encoding='utf-8')).get('complete'):
        for row in rows:
            if row['package']=='WP-4':
                row['remaining']=row['remaining'].replace('còn cải thiện phân bổ và đo quanh sốc 2022 bằng mô hình nguồn trước sốc.',
                    'đã đo thêm trước/trong/sau sốc cung ứng 2022 bằng mô hình học năm 2020, hiệu chỉnh 2021, giữ tau=.9. Có CI theo DN và nhóm thép/khác. Còn cải thiện phân bổ; chưa đổi G15 bằng kết quả test mới.')
    business=OUT/'rules/business_case_protocol.json'
    if business.exists():
        protocol=json.loads(business.read_text(encoding='utf-8'))
        if protocol.get('complete'):
            for row in rows:
                if row['package']=='WP-5':
                    row['remaining']=row['remaining'].replace('còn đủ hai ca mỗi quy tắc và chuyên gia xác minh, cập nhật pháp lý 2026.',
                        f"đã có {protocol['n_cases']} ca nghiệp vụ cho {protocol['n_rule_versions']} phiên bản quy tắc (tối thiểu hai ca/phiên bản). Còn chuyên gia xác minh, cập nhật pháp lý 2026 và tích hợp lịch mở rộng.")
    pd.DataFrame(rows).to_csv(OUT/'implementation/work_packages.csv',index=False)
    text='# Tiến độ triển khai kế hoạch 01–08\n\n'
    text+='Sinh bởi `scripts/implementation_status.py`. Phân biệt mã đã làm, thí nghiệm đã chạy và điều kiện nghiệm thu. **Chưa hoàn thành toàn bộ; chưa đủ điều kiện pilot.**\n\n'
    text+='Bảng kết quả chi tiết: [kết quả hiện có](../03_Evaluation/04_ket_qua_hien_co.md); [cổng hiện hành](../03_Evaluation/GATES_CURRENT.md); [kết quả chưa đạt](../03_Evaluation/KET_QUA_CHUA_DAT.md).\n\n'
    refresh=OUT/'implementation/fullweek_refresh.json'
    if refresh.exists():
        from sprint1.fullweek_refresh import JOBS
        records=json.loads(refresh.read_text(encoding='utf-8'));latest={r['job']:r for r in records}
        completed=sum(latest.get(name,{}).get('status')=='passed' for name in JOBS)
        current=[name for name in JOBS if latest.get(name,{}).get('status')=='running']
        text+=f'**Chạy lại expand fullweek ngày 21/10/2026: {completed}/{len(JOBS)} job đã hoàn tất.** '
        text+=('Đang chạy: '+', '.join(current)+'. ' if current else '')
        text+='CSV hazard trước sửa chỉ dùng kiểm toán; xem hậu tố `-fullweek` và nhật ký Sprint 1. G5/G6 v2 dùng giao thức riêng đã sửa.\n\n'
    for title,path in [('Kiểm thử','implementation/test_summary.csv'),('Nguồn lớn','data/big_worlds.csv'),('Khác biệt miền','t1/domain_distance.csv')]:
        file=OUT/path
        if file.exists():
            frame=pd.read_csv(file)
            if title=='Kiểm thử':
                for r in frame.itertuples():text+=f'- {r.environment}: {r.tests} ca, {r.failures} lỗi, bằng chứng `outputs/{r.evidence}`.\n'
            elif title=='Nguồn lớn':text+=f'- Nguồn lớn: {len(frame)} thế giới, {int(frame.n_firms.sum())} công ty, {int(frame.n_invoices.sum()):,} hoá đơn; kết quả trong `outputs/{path}`.\n'
    file=OUT/'e2e/e2e_metrics.csv'
    if file.exists():
        frame=pd.read_csv(file);full=bool(frame.full_protocol.all()) if 'full_protocol' in frame else False
        oracle=bool(frame.oracle_ablation_completed.all()) if 'oracle_ablation_completed' in frame else False
        text+=f'- E2E: đủ 14 công ty × 52 tuần = {full}; lượt oracle cùng ngân sách hoàn thành = {oracle}. Số và CI ở `outputs/e2e/e2e_metrics.csv`.\n'
    file=OUT/'t1/scaling_data_manifest.json'
    if file.exists():
        manifest=json.loads(file.read_text(encoding='utf-8'))
        text+=f'- Scaling: dữ liệu lồng nhau {manifest["sizes"]}, hoàn tất lấy mẫu = {manifest["complete"]}. '
        result=OUT/'t1/scaling_results.csv'
        text+=('Đã có bảng kết quả huấn luyện.\n' if result.exists() else 'Chưa có bảng đủ ba kích cỡ; không suy diễn DA6.\n')
    text+='\n| Gói | Bằng chứng | Phạm vi và việc còn lại |\n|---|---|---|\n'
    for row in rows:text+=f'| {row["package"]} — {row["title"]} | `{row["evidence"]}` ({"có" if row["evidence_exists"] else "chưa có"}) | {row["remaining"]} |\n'
    text+='\n## Cách tiếp tục\n\n'
    text+='- `python scripts/run_plan.py --jobs <tên job> --fail-fast`; mặc định không chạy trùng các tên lịch sử. Smoke lưu riêng, không ghi đè E2E đầy đủ.\n'
    text+='- Nhật ký: `outputs/implementation/run_status.json`; lịch sử lỗi được giữ lại. Thất bại cũ không đồng nghĩa lượt mới thất bại; tiến trình đang chạy chưa được nhận là đã xong.\n'
    text+='- Giới hạn CPU, không dùng tgt để chọn tham số, không đổi số bằng cách đổi phép đo. Chạy lại report sau khi các CSV đã ghi xong.\n'
    text+='- Không tự điền SEC_USER_AGENT, chấp nhận điều khoản Kaggle, gửi khảo sát/tin nhắn hoặc tạo số UAT/pilot. Dùng df=4, mẫu câu và file cảnh báo theo mặc định đã được cho phép.\n'
    text+='- Git của thư mục cha nằm ngoài Agent1; chưa stage/commit hay thay dữ liệu ngoài dự án. Tiến độ cũ giữ ở `TIEN_DO_2026-10-16_lich_su.md`.\n'
    (ROOT/'docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
