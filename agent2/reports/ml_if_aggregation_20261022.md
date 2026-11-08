# Kiểm tra phép gộp max điểm IF thành hồ sơ — 22/10/2026

**Phép lấy điểm lớn nhất có hiệu ứng theo số thành viên, rõ hơn khi hồ sơ mở rộng. Hiệu ứng còn sau khi tách công ty/nghiệp vụ; chưa đủ bằng chứng để kết luận ưu tiên sai hoặc thay phép gộp.** Giữ nguyên max, nhánh shadow, ngân sách, membership, cửa sổ và chính sách hồ sơ thiếu điểm.

## Đơn vị phân tích

Dựng lại hồ sơ từng ngày từ đầu ra rules + graph + A5 đã khóa của 001/003. Phân tích **mọi hồ sơ giao dịch đã được admission**, gồm cả chưa được chọn rà. Mỗi tập ID thành viên khác nhau trong cùng cohort/công ty chỉ xuất hiện một lần, tại cutoff đầu tiên nhìn thấy tập đó. Không đếm lặp do tồn nhiều ngày hoặc thay rule/priority mà thành viên giữ nguyên.

| Cohort | Tập thành viên khác nhau | Đủ IF toàn bộ thành viên | Loại do lịch sử/thiếu phạm vi | Giao dịch evaluation khác nhau trong phần đủ IF |
|---|---:|---:|---:|---:|
| 001 | 820 | 568 | 252 | 773 |
| 003 | 859 | 580 | 279 | 788 |
| Tổng | 1.679 | 1.148 | 531 | 1.561 |

531 tập ngoài phạm vi ở bảng này khác **515 lượt rà baseline** của [audit độ phủ](ml_if_coverage_20261022.md): đây là tập thành viên trong toàn bộ dòng hồ sơ admission, không phải công việc được chọn ở ngân sách 5/120. Không chấm train/calibration để mở rộng phần đủ IF. Hai model được phân tích riêng; không gộp thang điểm thô giữa cohort. Điểm IF không phải xác suất gian lận.

## Ảnh hưởng của số thành viên

Điểm max trung bình trên tập thành viên đủ điểm:

| Số thành viên | 001: số tập | 001: max TB | 003: số tập | 003: max TB |
|---|---:|---:|---:|---:|
| 1 | 159 | 0,4540 | 155 | 0,4534 |
| 2 | 77 | 0,4628 | 84 | 0,4588 |
| 3–4 | 129 | 0,4687 | 126 | 0,4598 |
| 5–8 | 145 | 0,4789 | 123 | 0,4709 |
| 9+ | 58 | 0,4870 | 92 | 0,4755 |

Tương quan thứ hạng Spearman giữa số thành viên và max:

| Phân tích | 001: rho / số tập dùng | 003: rho / số tập dùng |
|---|---:|---:|
| Chưa phân tầng | 0,435 / 568 | 0,396 / 580 |
| Trong công ty | 0,470 / 568 | 0,353 / 580 |
| Trong công ty × nhóm nghiệp vụ | 0,471 / 529 | 0,400 / 541 |
| Trong công ty × nhóm nghiệp vụ × tháng xuất hiện × ưu tiên | 0,460 / 464 | 0,416 / 485 |

Phân tầng dùng thứ hạng trung bình khi bằng nhau, chuẩn hóa thứ hạng trong từng tầng và gộp phần đã trừ trung bình tầng. Chỉ dùng tầng có ít nhất 3 tập và còn biến thiên ở cả số thành viên/điểm. Ở hàng cuối, 104/568 tập của 001 và 95/580 tập của 003 không đủ điều kiện; không xem đây là hệ số đã kiểm soát mọi yếu tố hoặc suy luận nhân quả.

### Tránh coi các lần mở rộng là mẫu độc lập

485/568 tập của 001 và 491/580 tập của 003 có giao dịch xuất hiện trong tập khác. Vì vậy đã kiểm tra thêm mỗi hồ sơ một lần và nối các tập có giao dịch trùng thành thành phần liên thông:

| Cách chọn tập đủ điểm | 001: N / rho | 003: N / rho |
|---|---:|---:|
| Tập đầu tiên mỗi ID hồ sơ | 194 / 0,121 | 200 / −0,064 |
| Tập lớn nhất từng thấy mỗi ID hồ sơ | 194 / 0,417 | 200 / 0,336 |
| Tập lớn nhất mỗi thành phần trùng giao dịch | 194 / 0,417 | 200 / 0,336 |
| Tất cả tập, bỏ ưu tiên bắt buộc ở lần xuất hiện đầu | 560 / 0,436 | 572 / 0,394 |

Hai hàng lấy tập lớn nhất có **0 lượt thành viên trùng giữa các đại diện**. Sau phân tầng công ty × nghiệp vụ trên các đại diện này, rho là 0,483 (156/194 tập) và 0,409 (158/200). Việc chọn tập lớn nhất là kiểm tra độ nhạy hồi cứu, không phải chính sách xếp hàng mới. Các tập đầu tiên chủ yếu chỉ có một thành viên (159/194 và 155/200); chưa có độ trải quy mô như các hồ sơ đã mở rộng.

Đây là lý do cần giữ riêng giai đoạn mở hồ sơ và các lượt cập nhật. Khi thêm thành viên mà giữ thành viên cũ, max có thể giữ nguyên hoặc tăng; tương quan dương không tự chứng minh hồ sơ lớn bị ưu tiên sai. Các hồ sơ còn có thể phụ thuộc chung công ty/người dùng/nghiệp vụ; không báo p-value hoặc khoảng tin cậy coi các tập là độc lập.

## Công ty và loại nghiệp vụ

Có khác biệt về cả quy mô hồ sơ và phân phối điểm giữa công ty. Ví dụ trong 001: C003 có 135 tập, trung bình 5,10 thành viên, max TB 0,4870; C007 có 37 tập, trung bình 3,43 thành viên, max TB 0,4468. Trong 003: C003 có 237 tập, trung bình 7,23 thành viên, max TB 0,4698; C007 có 38 tập, trung bình 2,53 thành viên, max TB 0,4449. Không quy chênh lệch điểm này thành chênh lệch gian lận giữa công ty.

Nhóm nghiệp vụ lấy từ `txn_type` nguồn; hồ sơ có nhiều loại được ghi `mixed`, giữ nguyên số lượng của từng loại:

| Nhóm | 001: số tập / thành viên TB / max TB | 003: số tập / thành viên TB / max TB |
|---|---:|---:|
| cash_expense | 491 / 4,05 / 0,4650 | 496 / 4,65 / 0,4601 |
| mixed | 45 / 6,58 / 0,4970 | 46 / 7,39 / 0,4807 |
| vendor_payment | 17 / 1,00 / 0,4838 | 22 / 1,00 / 0,4790 |
| payroll | 8 / 1,00 / 0,4573 | 9 / 1,00 / 0,4570 |
| adjustment | 6 / 1,00 / 0,4761 | 5 / 1,20 / 0,4758 |
| selling_expense | 1 / 1,00 / 0,5186 | 2 / 1,00 / 0,5216 |

Phần đủ điểm chủ yếu là cash_expense (86,4% và 85,5% số tập). Nhóm mixed đồng thời có nhiều thành viên hơn. Vendor/payroll/selling ở đây đều là singleton; không đủ biến thiên để suy rộng hiệu ứng quy mô riêng của các nhóm này. Số mẫu selling/adjustment nhỏ, không đủ để thiết lập ngưỡng hay công thức gộp theo nghiệp vụ.

Bảng đầy đủ theo 16 cặp cohort/công ty, nhóm nghiệp vụ và công ty × nghiệp vụ nằm trong [group_statistics.csv](ml_if_aggregation_20261022/group_statistics.csv). [transaction_score_groups.csv](ml_if_aggregation_20261022/transaction_score_groups.csv) ghi riêng phân phối điểm ở cấp giao dịch evaluation để đối chiếu cơ cấu nguồn.

## Đối chứng cơ học của phép max

Với mỗi tập đủ IF, giữ **cùng cohort, công ty, số thành viên và số lượng từng txn_type**. Lấy mẫu không hoàn lại từ điểm evaluation có `posted_at` **trước cutoff đầu tiên** của tập, 1.000 lần, seed 20261022. Đối chứng vẫn lấy **max**, nhằm quan sát tác động của nhiều cơ hội lấy điểm cao. Singleton dùng kỳ vọng chính xác của pool, không cần mô phỏng. Không dùng nguồn train/calibration hoặc điểm tương lai.

| Quy mô | 001: max thật TB / max đối chứng TB | 003: max thật TB / max đối chứng TB |
|---|---:|---:|
| 1 | 0,4540 / 0,4562 | 0,4534 / 0,4541 |
| 2 | 0,4628 / 0,4693 | 0,4588 / 0,4649 |
| 3–4 | 0,4687 / 0,4767 | 0,4598 / 0,4700 |
| 5–8 | 0,4789 / 0,4850 | 0,4709 / 0,4820 |
| 9+ | 0,4870 / 0,4959 | 0,4755 / 0,4940 |

Đối chứng tăng theo quy mô, phù hợp với hiệu ứng cơ học của max. Tuy nhiên nó phá quan hệ giữa các thành viên cùng cụm và không tái hiện điều kiện admission/rule/graph. Pool có chứa giao dịch của chính hồ sơ. 9 tập của 001 và 6 tập của 003 dùng hết ít nhất một pool loại nghiệp vụ; 7 và 5 tập dùng hết mọi pool. Sai số Monte Carlo lớn nhất của trung bình đối chứng lần lượt khoảng 0,00073 và 0,00078, khác hoàn toàn bất định về hiệu quả nghiệp vụ.

Chênh lệch `max thật − kỳ vọng đối chứng` chỉ là chẩn đoán: tương quan với quy mô là −0,062 và −0,328 trên toàn bộ tập đủ điểm. **Không coi chênh lệch này là điểm đã hiệu chỉnh**, xác suất hoặc phương án gộp đã được chứng minh tốt hơn; đặc biệt kết quả 003 cho thấy không thể dùng đối chứng như một phép chuẩn hóa sẵn để triển khai.

## Quyết định sau kiểm tra

Giữ phép max hiện tại. Khi thử phương án khác, đối chứng phải giữ cùng membership, phần đủ IF, công ty/nghiệp vụ/giai đoạn hồ sơ, ưu tiên bắt buộc và ngân sách 5/120 (10/240 là nhạy cảm). Đánh giá bằng kết luận độc lập, hành động hữu ích, thiếu chứng từ và phút thực tế, có phân tầng theo các yếu tố trên; không chọn phương án chỉ vì giảm tương quan với số thành viên.

[Rà độc lập](ml_independent_review_20261022.md) vẫn chưa có outcome/phút đo thực tế. Audit này chỉ dùng nguồn mô phỏng, có admission theo baseline và evaluation đã chấm kỹ thuật trước đó; không đại diện mọi giao dịch hoặc chứng minh lợi ích vận hành.

## Bằng chứng và tái lập

- [Tổng hợp](ml_if_aggregation_20261022/summary.json), [kiểm tra phụ thuộc/lặp thành viên](ml_if_aggregation_20261022/dependence/summary.json), [kiểm chứng](ml_if_aggregation_20261022/verification.json).
- Mỗi cohort có `analysis_plan.json` được ghi trước khi tính thống kê, `member_sets.private.csv`, `selected_reviews.private.csv`, thống kê nhóm và commitment hash. [selection_size_groups.csv](ml_if_aggregation_20261022/selection_size_groups.csv) đối chiếu các lượt đủ điểm ở cả hai ngân sách/nhánh; số lượt khớp audit độ phủ.
- [Cách chạy](../examples/ml_if_aggregation/README.md), [mã chính](../sme_fraud/audit_if_aggregation.py), [kiểm tra phụ thuộc](../sme_fraud/audit_if_aggregation_dependence.py).

**55 kiểm thử liên quan đạt, gồm 20 kiểm thử mới. 1.447 tệp bảo toàn không đổi.** Audit chính chặn `fit`, `score_samples` và deserialization model; không chấm thêm giao dịch, thử phép gộp khác, đổi thứ tự, đọc nhãn/oracle/split hoặc ghi outcome. Holdout 005 chỉ hash byte để kiểm tra bảo toàn, không phân tích/chấm. Các tệp `.private.csv` giữ nội bộ, không đưa vào gói reviewer mù.
