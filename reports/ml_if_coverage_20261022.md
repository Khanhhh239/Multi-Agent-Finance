# Độ phủ Isolation Forest — 22/10/2026

**515/1.659 lượt rà giao dịch của baseline thiếu điểm IF đầy đủ đều có thành viên trước evaluation.** Gồm 454 lượt chỉ có lịch sử và 61 lượt trộn calibration với evaluation; không phát hiện lỗi dữ liệu trong các tệp đã khóa. Không chấm bổ sung train/calibration, đổi mẫu số, cửa sổ, model, ngưỡng hoặc hàng đợi.

## Mẫu số và cửa sổ

Hai cohort mô phỏng 001/003, ngân sách chính **5 hồ sơ/120 phút mỗi công ty/ngày**. Baseline có 2.436 lượt rà: 1.659 lượt hồ sơ giao dịch và 777 lượt loại khác. Một hồ sơ có thể được rà tiếp khi phạm vi thay đổi hoặc đến lịch rà lại. 1.659 là lượt công việc, không phải giao dịch hay hồ sơ duy nhất (có 860 ID hồ sơ giao dịch).

Theo `posted_at`, đầu bao gồm/cuối loại trừ, giờ Việt Nam:

| Tập | Từ | Đến trước |
|---|---|---|
| Train | 01/01/2024 | 01/01/2025 |
| Calibration | 01/01/2025 | 01/07/2025 |
| Evaluation | 01/07/2025 | 01/01/2026 |

Baseline đưa cả tồn đọng trước evaluation vào hàng đợi ban đầu. IF chỉ có điểm của giao dịch evaluation. Hồ sơ chỉ được gán điểm IF khi **tất cả thành viên** có điểm; điểm phần evaluation không đại diện cho hồ sơ trộn lịch sử.

## Tách 515 lượt thiếu điểm

| Thành viên hồ sơ | 001 | 003 | Tổng lượt |
|---|---:|---:|---:|
| Chỉ train | 121 | 143 | 264 |
| Chỉ calibration | 83 | 97 | 180 |
| Train + calibration | 6 | 4 | 10 |
| Calibration + evaluation | 35 | 26 | 61 |
| **Tổng thiếu điểm IF đầy đủ** | **245** | **270** | **515** |
| Lỗi dữ liệu phát hiện trong các lượt trên | 0 | 0 | **0** |

454 lượt đầu không có thành viên evaluation. 61 lượt cuối có điểm cho thành viên evaluation; thành viên calibration được chủ ý loại khỏi chấm IF. Các lượt thiếu điểm giữ vị trí theo baseline. Không điền 0, lấy điểm tối đa của phần có điểm, bỏ thành viên lịch sử hoặc chấm ngược lịch sử để tăng tỷ lệ phủ.

## Hai mẫu số cần báo cáo song song

| Chỉ tiêu | Kết quả | Ý nghĩa |
|---|---:|---|
| Lượt baseline có IF đầy đủ / tất cả lượt hồ sơ giao dịch | **1.144/1.659 = 68,96%** | Độ phủ trên công việc baseline |
| Lượt có IF đầy đủ / lượt chỉ chứa thành viên evaluation | **1.144/1.144 = 100%** | Tính đầy đủ trong phần đủ điều kiện |
| Giao dịch evaluation có điểm hợp lệ / toàn bộ giao dịch evaluation | **11.811/11.811 = 100%** | Cấp giao dịch, khác cấp hồ sơ |

**31,04% công việc baseline vẫn chưa thể xếp lại bằng IF** theo chính sách hiện tại. 100% trên phần đủ điều kiện không thay thế 68,96% trên toàn bộ công việc, không chứng minh lợi ích phát hiện hoặc tiết kiệm thời gian. Hồ sơ bắt buộc vẫn tuân theo chính sách pin của so sánh đã khóa.

| Cohort | Giao dịch nguồn | Evaluation | Điểm evaluation hợp lệ | Feature hợp lệ |
|---|---:|---:|---:|---:|
| 001 | 20.559 | 5.934 | 5.934 | 20.559 |
| 003 | 20.523 | 5.877 | 5.877 | 20.523 |
| **Tổng** | **41.082** | **11.811** | **11.811** | **41.082** |

Audit kiểm tra feature thiếu/sai độ rộng/không hữu hạn ở float32; điểm thiếu, không hữu hạn, sai run/company/thời điểm hoặc ngoài evaluation; ID trùng, không tồn tại, liên kết chéo công ty và thành viên sau cutoff. Hash nguồn, model, training record, điểm và mã dựng snapshot phải khớp bản đã khóa. Membership được tính lại theo thời gian và từng lượt được nối với đúng phạm vi hồ sơ tại cutoff. Không phát hiện lỗi trong các dữ liệu này; đây chưa phải xác minh nghiệp vụ của nguồn SME thật.

## Nhánh IF và ngân sách nhạy cảm

| Ngân sách/ngày | Nhánh | Lượt giao dịch | IF đầy đủ | Chỉ lịch sử | Trộn lịch sử/evaluation | Lỗi dữ liệu |
|---|---|---:|---:|---:|---:|---:|
| 5 hồ sơ / 120 phút | Baseline | 1.659 | 1.144 | 454 | 61 | 0 |
| 5 hồ sơ / 120 phút | IF shadow | 1.658 | 1.143 | 454 | 61 | 0 |
| 10 hồ sơ / 240 phút | Baseline | 1.675 | 1.148 | 460 | 67 | 0 |
| 10 hồ sơ / 240 phút | IF shadow | 1.675 | 1.148 | 460 | 67 | 0 |

Không cộng bốn hàng thành số hồ sơ độc lập. Bảng theo tháng/công ty có trong `coverage_breakdown.csv` của từng cohort.

## Bằng chứng và kiểm chứng

- [Tổng hợp máy đọc được](ml_if_coverage_20261022/summary.json), [biên bản kiểm chứng](ml_if_coverage_20261022/verification.json).
- Cohort [001](ml_if_coverage_20261022/sme_fraud_001/summary.json), [003](ml_if_coverage_20261022/sme_fraud_003/summary.json): `source_member_coverage.csv` cho từng giao dịch, `selected_review_coverage.private.csv` cho từng lượt, `selected_member_coverage.private.csv` nối lượt với thành viên, cùng commitment hash đầu vào/đầu ra. Tệp `.private.csv` có nhánh/ID hồ sơ, không đưa vào gói reviewer mù.
- [Mã audit](../sme_fraud/audit_if_coverage.py), [kiểm thử](../tests/test_if_coverage.py), [cách chạy](../examples/ml_if_coverage/README.md).

**62 kiểm thử liên quan đạt**, gồm 19 kiểm thử mới. Audit cả hai cohort chạy với chặn `fit`/`score_samples`; **1.424 tệp bảo toàn không đổi**, gồm nguồn, model, baseline, shadow, phân chia thời gian và gói reviewer. Holdout 005 chỉ hash như khối byte để kiểm tra bảo toàn, không phân tích/chấm. Không đọc nhãn/oracle/split; không tạo điểm mới hoặc kết luận rà soát độc lập.

Đã giải thích đủ 515 lượt; chưa có lỗi dữ liệu cần sửa trong phạm vi này. Giữ loại lịch sử khỏi IF, tiếp tục đo lợi ích trên toàn bộ ngân sách rà và ghi riêng phần IF có thể tác động. [Rà soát độc lập/phút xử lý thực tế](ml_independent_review_20261022.md) vẫn chờ người thực hiện.
