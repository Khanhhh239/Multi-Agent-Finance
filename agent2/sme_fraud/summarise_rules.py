"""Aggregate completed, fixed-policy rule benchmarks without selecting a winner."""
import argparse
import json
from pathlib import Path


def summarise(root):
    reports = [json.loads((root / f'sme_fraud_{tag}' / 'comparison.json').read_text(encoding='utf-8'))
               for tag in ('001', '003', '005')]
    lines = ['# So sánh bộ luật, đồ thị quan hệ và Isolation Forest', '',
        'Ba bộ dữ liệu tổng hợp v2, cùng seed. Mỗi bộ có 25.000 quan sát test; ngân sách xếp hạng 0,3% = 75 cảnh báo.',
        'Điểm luật/ensemble không phải xác suất gian lận. Trọng số được đặt theo file luật trước khi đọc nhãn test.', '',
        '| Tỷ lệ gian lận | Phương án | AP | Phát hiện | Precision@75 | Recall | Cảnh báo sai | Recall theo vụ |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for report in reports:
        for name, model in report['models'].items():
            selected = model['fixed_capacity']
            lines.append(f"| {report['test_fraud_rows']/report['test_rows']:.1%} | {name} | {model['average_precision']:.4f} | "
                         f"{selected['tp']} | {selected['precision']:.1%} | {selected['recall']:.1%} | {selected['fp']} | {selected['case_recall']['recall']:.1%} |")
    lines += ['', '## Diễn giải và phạm vi', '',
        '- Sáu nhóm A–F có 31 rule. Năm rule C4/E2/F2/F3/F4 chưa đánh giá được vì thiếu nguồn dữ liệu cần thiết; không coi thiếu dữ liệu là không có vi phạm.',
        '- B1/B4/B7/E3/F1 và A3/D3/D4 có phạm vi hoặc phương pháp thay thế được ghi trong rule_coverage.json.',
        '- P1 (thanh toán vượt hóa đơn), T1 (tạm ứng quá hạn), T2 (xóa nợ thiếu hồ sơ) bổ sung phạm vi sáu kịch bản gian lận ban đầu.',
        '- Rules dùng đối chiếu trực tiếp; Rules+Graph thêm chia nhỏ qua mạng lưới và quan hệ NCC–người đại diện–nhân viên.',
        '- D1–D6 là chẩn đoán theo tập giao dịch tại từng thời điểm; không tăng điểm một giao dịch chỉ vì tập không theo Benford.',
        '- Ngưỡng validation giữ mọi trường hợp bằng điểm nên có thể vượt ngân sách. Precision@75 so sánh cùng sức chứa, không phải ngưỡng vận hành.',
        '- Hàng đợi case_queue.csv dùng ngưỡng nghiệp vụ mặc định; ưu tiên/SLA/chủ hồ sơ là gợi ý mô phỏng. Đã có UI rà soát cục bộ (xem ../review_ui.md), chưa gửi thông báo.',
        '- File rule_hits.jsonl lưu dữ kiện, liên kết giao dịch, đường đi đồ thị và lý do ngoại lệ đã biết.',
        '- Chỉ dùng dữ liệu tổng hợp, một seed và doanh nghiệp đã biết qua thời gian. Cần tập mới được giữ kín, nhiều seed và dữ liệu SME thật để nghiệm thu.',
        '- Không chọn trọng số/đổi luật dựa trên nhãn test của báo cáo này; không cập nhật ngưỡng tự động theo phản hồi.', '',
        '## Cảnh báo sai trên hard negatives ở cùng sức chứa', '',
        '| Bộ | Phương án | Nhóm hợp lệ | Số mẫu | Cảnh báo sai | FPR |', '| --- | --- | --- | ---: | ---: | ---: |']
    for report in reports:
        for name, model in report['models'].items():
            for item in model['fixed_capacity']['hard_negatives']:
                lines.append(f"| {report['test_fraud_rows']/report['test_rows']:.1%} | {name} | {item['name']} | {item['rows']} | {item['false_alerts']} | {item['fpr']:.2%} |")
    (root / 'summary_vi.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (root / 'summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=Path('reports/rules'))
    args = parser.parse_args()
    summarise(args.reports)
    print(args.reports / 'summary_vi.md')


if __name__ == '__main__':
    main()
