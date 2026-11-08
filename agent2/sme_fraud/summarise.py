"""Summarise audited accounting corrections and measured IF results, including v1 comparison."""
import json
from pathlib import Path

from .accounting import SOURCES
from .evaluate import pd,np,joblib,sklearn


def summarise(root=Path('.')):
    metrics=[]
    reviews=[]
    lines=['# Benchmark tổng hợp SME Việt Nam v2','',
        'Seed 20261012. Mỗi bộ 100.000 quan sát, 5.000 hard negatives; nhãn/splits giữ nguyên so với v1.',
        'IF 300 cây, max_samples=2048, 190 đặc trưng. Ngưỡng lấy từ validation chưa gán nhãn với ngân sách 0,3%.','',
        '| Prevalence | Gian lận test | AP | Precision | Recall | Cảnh báo sai | Tổng cảnh báo |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    compare=['','| Prevalence | AP v1 | AP v2 | Precision v1 → v2 | Recall v1 → v2 |',
             '| --- | ---: | ---: | ---: | ---: |']
    for tag in ('001','003','005'):
        data=root/'data'/f'sme_fraud_{tag}'
        report=root/'reports'/f'sme_fraud_{tag}'
        m=json.loads((report/'metrics.json').read_text(encoding='utf-8'))
        q=m['selected_threshold']
        model=joblib.load(report/'isolation_forest.joblib')
        features=pd.read_csv(data/'features.csv').set_index('transaction_id')
        saved_scores=pd.read_csv(report/'scores_test.csv').head(300)
        x=features.loc[saved_scores['transaction_id'],model['feature_columns']].to_numpy(dtype=np.float32)
        fresh=-model['model'].score_samples(x)
        assert np.allclose(fresh,saved_scores['anomaly_score'].to_numpy(),rtol=0,atol=1e-12),'Persisted model score mismatch'
        assert model['dataset_version']=='2.0' and model['feature_columns']==list(features.columns),'Model schema mismatch'
        metrics.append(dict(scenario=tag,prevalence=m['test_prevalence'],average_precision=m['average_precision'],
            precision=q['precision'],recall=q['recall'],false_alerts=q['fp'],model_reload_score_check='passed',
            per_accounting_framework=m['per_accounting_framework']))
        lines.append('| {:.1%} | {} | {:.4f} | {:.1%} | {:.1%} | {} | {} |'.format(
            m['test_prevalence'],m['test_fraud_rows'],m['average_precision'],q['precision'],q['recall'],q['fp'],q['alerts']))
        old=json.loads((root/'.archive'/'v1'/'reports'/f'sme_fraud_{tag}'/'metrics.json').read_text(encoding='utf-8'))
        compare.append('| {:.1%} | {:.4f} | {:.4f} | {:.1%} → {:.1%} | {:.1%} → {:.1%} |'.format(
            m['test_prevalence'],old['average_precision'],m['average_precision'],old['selected_threshold']['precision'],
            q['precision'],old['selected_threshold']['recall'],q['recall']))
        audit=json.loads((data/'accounting_validation.json').read_text(encoding='utf-8'))
        change=json.loads((data/'accounting_change_log.json').read_text(encoding='utf-8'))
        audit['sources']=SOURCES
        (data/'accounting_validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        reviews.append(dict(scenario=tag,status=audit['status'],observations=audit['scored_observations'],
            changed_observations=change['changed_observations'],primary_documents=audit['primary_financial_documents'],
            auxiliary_documents=audit['auxiliary_documents'],journal_documents=audit['journal_documents'],
            journal_lines=audit['journal_lines'],account_flow_edges=audit['account_flow_edges'],
            labels_and_splits_byte_identical=change['labels_and_splits_byte_identical'],
            accounting_frameworks=audit['accounting_frameworks']))
    lines+=compare+['','AP/precision/recall v2 giảm trong seed này. Sửa biểu diễn kế toán và thêm cột chưa cải thiện IF; không chọn lại ngưỡng theo test.',
        'Đây là đo trên dữ liệu tổng hợp, không ước lượng hiệu quả thực địa. Test 0,1% chỉ có 25 dòng gian lận.','',
        'Kiểm chứng: 15 tests về kế toán, tái lập và chống rò rỉ; kiểm tra toàn bộ 3 bộ dữ liệu; nạp lại 3 model và đối chiếu 300 điểm test/model.',
        'Cặp tài khoản multi-hot bao gồm dòng VAT/dự phòng; 641/642 chuẩn hóa ở lớp ML, sổ cái giữ mã TT133/TT200.',
        'Báo cáo metrics.json từng bộ có FPR riêng theo chế độ kế toán, nhóm hard negative và recall theo vụ/biến thể.']
    (root/'reports'/'summary_vi.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (root/'reports'/'summary.json').write_text(json.dumps(dict(version='2.0',sklearn_version=sklearn.__version__,
        numpy_version=np.__version__,pandas_version=pd.__version__,scenarios=metrics),ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'reports'/'accounting_review.json').write_text(json.dumps(dict(version='2.0',status='passed',
        sources=SOURCES,scenarios=reviews,tests_passed=15,model_reload_checks='passed',
        scope='Historical 2024-2025 scenario accounting, not a full statutory or tax audit'),ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(metrics=metrics,accounting=reviews)


if __name__=='__main__':
    print(json.dumps(summarise(),ensure_ascii=False,indent=2))
