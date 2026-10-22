# IF shadow so với rules + graph + A5 — 22/10/2026

**Đã chạy IF shadow và so sánh hai nhánh trên cùng trần hồ sơ/phút mỗi công ty mỗi ngày.** Trên hai bộ mô phỏng, IF thay đổi lựa chọn ở 15 cặp công ty/ngày với ngân sách 5 hồ sơ/120 phút; với ngân sách 10 hồ sơ/240 phút, tập được chọn giống nhau. Chưa có kết luận kế toán độc lập nên **chưa chứng minh tăng số hồ sơ hữu ích**.

## Phạm vi và cách so sánh đã khóa

- Nguồn 001/003 `synthetic-source-world-v1`, cùng hai IF đã huấn luyện; suy luận lại **11.811 giao dịch** thuộc 01/07–31/12/2025. Hash điểm của từng bộ trùng lượt shadow trước; không fit hoặc chỉnh threshold.
- Mỗi bộ có 8 công ty mô phỏng, 184 ngày lịch. Tổng hai bộ là **2.944 cặp công ty/ngày**; không diễn giải thành 16 SME thật độc lập. Cửa sổ này đã được chấm kỹ thuật trước đó, không phải một phép đánh giá thực địa chưa từng xem.
- Baseline lấy scores/hits/graph/A5 và batch/source findings đã khóa trong `pipeline_rehearsal_20261018_v2`; graph bật, A5 rolling account P99/90 ngày. Không chạy lại detector hoặc thay điểm/quy tắc.
- Hai nhánh dùng cùng dòng hồ sơ theo cutoff, phạm vi nguồn, trần hồ sơ/phút, lịch mọi ngày và giả định công sức. Baseline sắp priority → max_score → thời điểm mở → ID. IF chỉ đổi thứ tự hồ sơ `transaction` trong cùng priority, bằng max điểm thành viên đã biết; vị trí thiếu/khuyết điểm được giữ tại thứ tự baseline, không điền 0.
- Các lượt `cao_nhat` và hồ sơ ngoài loại `transaction` mà baseline chọn được giữ cho nhánh IF nếu chưa rà cùng work scope. Không mở hồ sơ chỉ vì điểm IF. Trường hợp tràn suất bắt buộc vẫn ghi tồn trong ledger; chỉ số không đẩy suất bắt buộc không có nghĩa mọi hồ sơ khẩn đã được xử lý.
- `evaluation_plan.json` ở mỗi bộ được ghi trước khi suy luận/chọn hồ sơ. [Cách chạy và toàn bộ giả định](../examples/ml_shadow_comparison/README.md).

## Ngân sách chính: 5 hồ sơ/120 phút mỗi công ty/ngày

Các số bên dưới là **lượt rà work scope mô phỏng**, gồm lượt tiếp theo khi phạm vi hồ sơ thay đổi; không phải số hồ sơ hữu ích hoặc giao dịch gian lận.

| Chỉ số, tổng 001/003 | Baseline | IF shadow |
|---|---:|---:|
| Lượt rà được chọn | 2.436 | 2.435 |
| Hồ sơ khác nhau được chọn | 1.118 | 1.118 |
| Phút rà ước lượng | 54.001 | 53.976 |
| Chờ trung bình, ngày trong sổ mô phỏng | 2,271 | 2,267 |
| Work scope còn tồn tại cuối kỳ | 180 | 180 |
| Phút tồn cuối kỳ ước lượng | 4.836 | 4.836 |
| Hồ sơ chờ thông tin tại cuối kỳ | 32 | 32 |

Hai nhánh trùng **2.417 lượt chọn cùng ngày**. Có 15 cặp công ty/ngày đổi tập được chọn (trong 1.206 cặp có lượt chọn), cùng 111 cặp đổi thứ tự kể cả khi tập không đổi. Theo từng bộ, số cặp đổi tập là **001: 5**, **003: 10**.

Trong các work scope cả hai nhánh đều rà trong kỳ, IF đưa **12 scope lên sớm hơn**, **5 scope muộn hơn**, mức muộn lớn nhất **1 ngày**. Có 2 phiên bản work scope baseline đã rà mà IF không có lượt đối ứng đến hết kỳ, và 1 phiên bản ở chiều ngược lại. Pending cũ có thể được gộp vào phiên bản phạm vi mới trước khi được chọn: baseline ghi 28 phiên bản như vậy, IF 29. Không tự coi phiên bản chưa có lượt đối ứng là hợp lệ, gian lận bị bỏ sót, hoặc hồ sơ vẫn chưa được rà ở phiên bản mới.

Chênh **25 phút ước lượng** đi cùng chênh số lượt/phiên bản được chọn, chưa phải thời gian thực tế tiết kiệm. Tổng số hồ sơ khác nhau được chọn và tồn cuối kỳ không cải thiện trong mô phỏng này.

## Đối chứng: 10 hồ sơ/240 phút mỗi công ty/ngày

Hai nhánh chọn cùng **2.544 lượt rà**, **1.178 hồ sơ khác nhau**, tiêu dùng cùng **56.481 phút ước lượng** và còn cùng **100 work scope tồn cuối kỳ / 2.776 phút ước lượng**. IF đổi thứ tự ở 101 cặp công ty/ngày nhưng không đổi tập được chọn hoặc ngày rà của work scope. Không suy từ đổi thứ tự sang lợi ích khi chưa có outcome.

## Độ phủ và các điều kiện vận hành

Ở ngân sách chính, baseline chọn 1.659 lượt rà hồ sơ giao dịch: **1.144 lượt đủ điểm IF (khoảng 69%)**, 515 lượt thiếu/khuyết điểm nên giữ thứ tự baseline. Nhánh IF tương ứng 1.658/1.143/515 lượt. Mỗi nhánh còn **777 lượt ngoài loại transaction** được giữ theo baseline. Độ phủ tính trên lượt rà; các thống kê trên toàn bộ snapshot mỗi ngày có mẫu số riêng trong JSON, bao gồm cả scope đã rà trước đó.

Các scope thiếu điểm chủ yếu có thành viên ngoài cửa sổ evaluation hoặc không có điểm thành viên đầy đủ. Không chấm lại train/calibration để lấp độ phủ. Lấy max có thể ưu ái hồ sơ nhiều thành viên; thống kê kích thước nằm trong summary từng bộ. Chưa có outcome để hiệu chỉnh cách gộp.

Hai nhánh bắt đầu với các scope trước kỳ vẫn còn hoạt động tại cutoff đầu, không nhập kết luận production. Sau một lượt mô phỏng, ledger ghi đã thực hiện lượt rà/yêu cầu, không sinh kết luận nghiệp vụ. Thiếu thông tin được để chờ; nguồn có lịch rà lại hiện hữu được một follow-up khi đến hạn. Work scope đã rà không bị đếm lại chỉ vì ngày/cutoff đổi. Thay đổi bằng chứng/phạm vi cần lượt tiếp theo; pending chưa rà được gộp vào phiên bản hiện tại, hoặc rút khi nguồn hết điều kiện.

Ước lượng phút dùng snapshot **as-of**, không lấy công sức hoặc điểm/thành viên của snapshot cuối để chọn trong quá khứ. Lượt tiếp theo có chi phí `max(10, ceil(phút cơ sở/2))` theo giả định công sức đã khai báo; các hành vi/công sức này chưa được đo từ kế toán. Tồn cuối kỳ dừng ở 31/12, không tự xả tiếp sau evaluation.

## Tính đúng phiên bản và kiểm chứng

File `case_queue.py` hiện tại khác hash ghi ngày 18/10; các module phụ thuộc được kiểm tra vẫn khớp. Runner ghi cả hai hash, khóa mã dựng queue hiện tại và xác nhận nó tái dựng đúng **556/556 scope (001)** và **594/594 scope (003)** của snapshot cuối trước khi suy luận. Mỗi ngày sau đó chỉ dùng prefix có thời điểm trước cutoff. Không có snapshot trung gian lịch sử để chứng nhận từng ngày trùng một implementation cũ; baseline của phép thử là mã queue hiện tại chạy trên đầu ra detector đã khóa. Không sửa file/mã/hash trong baseline cũ.

**88 kiểm thử đạt, 0 failure/error/skipped**, gồm các kiểm tra đối chứng ngân sách hồ sơ/phút, cutoff, vị trí thiếu IF, priority/tie, suất bắt buộc, tràn suất, chuyển tồn, đổi scope, thông tin chưa đủ, fingerprint model và compatibility. [Kết quả](ml_shadow_comparison_20261022/tests.json), [log](ml_shadow_comparison_20261022/tests.log).

Trên cả hai cấu hình ngân sách: **0 vi phạm ngân sách, 0 suất bắt buộc đã chọn bị IF đẩy ra**. Lượt thực chạy dưới chặn `fit` và chặn mở nhãn/splits/oracle; 005 chỉ băm opaque ở kiểm tra bảo toàn. **1.240 tệp bảo toàn không đổi**; model, nguồn, baseline, queue vận hành và kết luận không bị cập nhật; 0 thông báo gửi ra ngoài. [Biên bản kiểm chứng](ml_shadow_comparison_20261022/verification.json).

## Artifact và bước tiếp theo

- [Tổng hợp chỉ số](ml_shadow_comparison_20261022/analysis.json).
- [So sánh 001](ml_shadow_comparison_20261022/sme_fraud_001/comparison.json), [kế hoạch 001](ml_shadow_comparison_20261022/sme_fraud_001/evaluation_plan.json), [chọn từng ngày, ngân sách 5](ml_shadow_comparison_20261022/sme_fraud_001/budget_5/daily_comparison.csv).
- [So sánh 003](ml_shadow_comparison_20261022/sme_fraud_003/comparison.json), [kế hoạch 003](ml_shadow_comparison_20261022/sme_fraud_003/evaluation_plan.json), [chọn từng ngày, ngân sách 5](ml_shadow_comparison_20261022/sme_fraud_003/budget_5/daily_comparison.csv).
- Phiếu hợp các scope để rà, không lộ nhánh/thứ hạng/IF: [001](ml_shadow_comparison_20261022/sme_fraud_001/review_union.blind.csv), [003](ml_shadow_comparison_20261022/sme_fraud_003/review_union.blind.csv). Các cột outcome/người rà/phút thực tế còn trống. File `selections.private.csv` đi kèm từng ngân sách có điểm/nhánh, không dùng làm phiếu rà mù.

Giữ baseline hiện hành. Lượt thử cho thấy can thiệp thứ tự có tác động chọn mẫu nhỏ dưới các ràng buộc này, chưa chứng minh IF có ích hơn và cũng chưa chứng minh IF không có ích. Muốn đánh giá lợi ích cần người rà độc lập xác định hồ sơ có hành động hữu ích, thiếu chứng từ và phút thực tế, cùng mẫu tham chiếu và phân xử đã chốt trước. Lượt này chưa thực hiện mẫu ngẫu nhiên tham chiếu hay phân xử; precision/recall/gain vẫn để `null`. Nguồn SME thật, protocol pilot và lợi ích vận hành tiếp tục chờ.
