# Đợt 4 — bằng chứng và đánh giá độc lập

Nguồn HR/override/số chứng từ/công nợ có phiên bản và thời điểm quan sát. C4/E2/F2 kiểm tra giao dịch; F3 gaps/F4 công nợ là hồ sơ nguồn riêng, không gán gian lận cho dòng tiền bất kỳ.
Ngưỡng A5 và vận hành giữ từ đợt 3; không chọn lại theo test. Seed test mới khác seed validation; không train/chấm ML.

Đối chứng nguồn/mẫu hình: 301/301 khớp; nhãn điều kiện rule, không phải kết luận gian lận tài chính.
Có 56 thử nghiệm cửa sổ, tạo 336 phép đối chiếu rule–scope–cutoff: 336/336 khớp nhãn can thiệp/đủ nguồn. Các phép đối chiếu trên cùng cửa sổ có phụ thuộc; không xem 336 là 336 mẫu thử độc lập. Sai khác thống kê được giữ để đo power/FP, không chỉnh nhãn hoặc ngưỡng sau khi xem test.

Nghiệm thu kỹ thuật: **135 test qua**; [validation.json](validation.json) xác nhận checksum, replay điểm, thành viên hàng đợi, ngân sách và nạp ReviewStore của sáu snapshot test. Có 14 CSV header mẫu. Chưa kiểm tra trực quan trình duyệt hoặc nguồn SME thật. Bản chấm cuối giữ nguyên dự đoán SME so với bản trước các sửa độc lập về gom override và lịch sử nhân sự.

## Test mới — hai seed, mỗi bộ 50.000 dòng toàn thời gian

| Seed | Tỷ lệ toàn bộ | Số dòng test | TP | FP | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026101402 | 0.1% | 12500 | 10 | 194 | 4.90% | 83.33% |
| 2026101402 | 0.3% | 12500 | 34 | 196 | 14.78% | 91.89% |
| 2026101402 | 0.5% | 12500 | 56 | 191 | 22.67% | 90.32% |
| 2026101403 | 0.1% | 12500 | 10 | 164 | 5.75% | 83.33% |
| 2026101403 | 0.3% | 12500 | 35 | 161 | 17.86% | 94.59% |
| 2026101403 | 0.5% | 12500 | 53 | 164 | 24.42% | 85.48% |

## Phạm vi kết luận

Các bộ SME mới vẫn là generator sáu nhóm gian lận; nguồn HR/ERP thực chưa có. Accuracy C4/E2/F2/F3/F4 trên SME thật chưa đo được. Test chứa ít fraud ở tỷ lệ thấp; metric có số mẫu, Wilson theo dòng và bootstrap theo block công ty/tháng, không chứng minh độ tin cậy trên SME thật.
control_metrics.jsonl tách điều kiện đã biết/thiếu nguồn; aggregate_metrics.jsonl dùng đơn vị cửa sổ. D3/D6 có tập đủ mẫu riêng; không hạ min_rows để ép dataset SME được đánh giá.
rule_metrics.jsonl từng bộ có điểm góp và tín hiệu riêng, hard negatives; budget_metrics.jsonl so ngân sách 1/3/5 hồ sơ mới/công ty/ngày theo bằng chứng lúc mở, không dùng điểm hoặc thành viên tương lai.
30.000 dòng đầu từ ba snapshot gốc giữ điểm/cảnh báo; đây là kiểm tra prefix, không phải chấm lại toàn bộ 300.000 dòng gốc.

[Schema, chính sách và kiểm thử](../../rule_repairs_phase4.md). Cần thu nguồn thật và kết luận rà soát độc lập trước nghiệm thu sản phẩm/ML.
