# Bộ rà soát độc lập cho IF shadow — 22/10/2026

**Đã chuẩn bị 69 phiếu có bằng chứng theo thời điểm, chưa có kết luận rà độc lập.** Bộ phiếu gồm toàn bộ 37 mẫu bất đồng tại ngân sách chính 5 hồ sơ/120 phút và 32 mẫu tham chiếu ngẫu nhiên. Người rà chính và người phân xử chưa được phân công; các kết luận, chữ ký và phút thực tế đều để trống.

## Giao cho người rà

Chỉ giao [reviewer_packet.zip](ml_independent_review_20261022/reviewer_packet.zip), hoặc thư mục `public`. Gói ZIP không chứa `private`, điểm IF, nhánh, thứ hạng hay lý do lấy mẫu.

- [Hướng dẫn reviewer](ml_independent_review_20261022/public/README.md).
- [Danh sách 69 phiếu và bằng chứng](ml_independent_review_20261022/public/REVIEW_INDEX.md).
- [Phiếu rà chính](ml_independent_review_20261022/public/primary_reviews.csv).
- [Phiếu phân xử](ml_independent_review_20261022/public/adjudications.csv).

Mỗi phiếu có mã ẩn danh, mã công ty đã thay thế, cutoff và fingerprint bằng chứng. Giao dịch thành viên, các giao dịch liên quan, chứng từ/sổ và ngữ cảnh công ty nằm trong `evidence/<mã>/evidence.json`. Chỉ các dòng nguồn có thông tin thời điểm phù hợp mới được đưa vào; không bổ sung ngược master/chứng từ hiện tại vào quá khứ. Không công bố số lượng/ID dòng nguồn bị loại vì nằm trong tương lai. Tham chiếu lịch làm việc tĩnh được ghi đúng vai trò nguồn mô phỏng.

Gói này dùng **nguồn mô phỏng 001/003**, không phải scan chứng từ hay bản xuất SME thật. Các trường `evidence_on_file` là lời khai trong nguồn; người rà phải ghi thiếu tài liệu/unknown khi chưa thể kết luận. Review người thật trên bộ mô phỏng không tự đóng cổng hiệu quả thực địa.

## Lấy mẫu đã khóa trước khi lập phiếu

| Nhóm, chỉ có trong bản quản lý riêng | Số mẫu |
|---|---:|
| Toàn bộ khác biệt lựa chọn cùng ngày giữa hai nhánh | 37 |
| Mẫu ngẫu nhiên hai nhánh cùng chọn | 16 |
| Mẫu ngẫu nhiên đang chờ mà không nhánh nào chọn trong ngày | 16 |
| Tổng | 69 |

Đơn vị lấy mẫu là **ảnh chụp hồ sơ tại một cutoff ngày**, có thể cùng hồ sơ ở những ngày/phạm vi khác nhau. Không gọi 69 phiếu là 69 vụ độc lập.

Mẫu tham chiếu phân tầng theo bộ mô phỏng × công ty × trạng thái chọn. Với mỗi bộ/công ty, lấy một mẫu cùng chọn và một mẫu chưa được chọn; loại các mẫu bất đồng khỏi pool tham chiếu. Seed cố định **20261022**; thứ tự ngẫu nhiên được xác định bằng SHA256(seed, tầng, ID), không dùng điểm IF hoặc outcome. Xác suất chọn và mẫu số mỗi tầng được lưu riêng. Thứ tự phiếu công khai được trộn bằng một hash khác, không lộ nhóm.

Pool là các scope đã được baseline tiếp nhận và đang pending trong ít nhất một sổ nghiên cứu. Nó **không bao gồm toàn bộ giao dịch chưa được detector tiếp nhận**. Mẫu tham chiếu hỗ trợ rà thiên lệch lựa chọn trong pool này, không ước lượng recall gian lận toàn quần thể. Một mẫu mỗi tầng còn ít để suy độ bất định cho triển khai thực tế; chưa có tiêu chí lợi ích hoặc phương pháp ước lượng tổng thể được phê duyệt.

Các ledger pending được tái dựng và đối chiếu với từng bản ghi đã chọn đã khóa: ID scope, cutoff, work key và số phút ước lượng phải khớp. Không chạy lại model hoặc sửa kết quả shadow để lấy mẫu thuận lợi. [Kế hoạch lấy mẫu riêng](ml_independent_review_20261022/private/selection_plan.json), [mẫu số các tầng riêng](ml_independent_review_20261022/private/sampling_populations.json) dành cho người quản lý nghiên cứu, không đưa cho reviewer trước khi hoàn tất rà mù.

## Các kết quả cần người thật ghi

1. `condition_present`: true/false/unknown theo điều kiện nghiệp vụ có căn cứ.
2. `actionable`: true nếu có hành động nghiệp vụ/kiểm soát cụ thể, có lý do vượt ngoài yêu cầu tài liệu chung; false khi đủ căn cứ không cần hành động đó; unknown khi chưa thể quyết định. Đây không phải nhãn gian lận.
3. `document_request_needed`, tài liệu còn thiếu, hành động đề xuất, lý do và tham chiếu tên bảng bằng chứng. Thiếu dữ kiện không bị tự đổi thành false.
4. Phút rà **đo thực tế**. `timing_method` phải là `measured_stopwatch` hoặc `measured_interval`; `estimated` không được chấp nhận. Nếu dùng khoảng thời gian, phút active phải khớp thời gian kết thúc trừ bắt đầu và nghỉ. Phút phân xử được ghi riêng, không cộng lẫn vào công sức primary.
5. Mã người rà, thời điểm ký và xác nhận độc lập với phát triển/chọn model, chưa thấy nhánh/điểm của mẫu. Người phân xử phải là một người khác và có xác nhận riêng.

Nhận xét `ASSISTANT_SYNTHETIC_REVIEW`, kết quả oracle mô phỏng hay kiểm thử kỹ thuật trước đây không được nhập thành kết luận độc lập. Không tự điền tên người, outcome hoặc thời gian bằng giá trị giả.

## Phân công và nhập kết quả

[reviewer_assignment.json](ml_independent_review_20261022/private/reviewer_assignment.json) hiện `unassigned`, hai mã người còn `null`. Chủ nghiên cứu ghi đúng người thật sau khi phân công; người rà tự xác nhận độc lập/mù trong phiếu. Không tự gán người dùng hoặc trợ lý làm reviewer.

Sau khi nhận hai file đã điền, chạy bằng môi trường Python hiện hành:

```powershell
python -B -m sme_fraud.independent_ml_review validate `
  --prepared reports/ml_independent_review_20261022 `
  --primary <primary_reviews_da_dien.csv> `
  --adjudications <adjudications_da_dien.csv> `
  --output reports/my_independent_review_validation
```

Validator kiểm tra binding ID/evidence, hash nguồn chỉ đọc, người được phân công, hai người khác nhau, xác nhận độc lập/mù, kết luận unknown, tài liệu thiếu, tham chiếu, thời điểm và thời gian đo thực tế. Kết quả chưa phân xử được giữ pending; unresolved được báo riêng, không tính như âm tính. Công cụ kiểm tra tính đầy đủ/nhất quán của lời xác nhận, không tự xác minh danh tính hay năng lực nghiệp vụ của người ký.

Phút rà mẫu tham chiếu và phút phân xử có trường tổng riêng. Đây là chi phí thu thập outcome ngoài mô phỏng chọn hồ sơ cũ, chưa phải số phút tiết kiệm do IF. Báo cáo gain/precision/recall vẫn `null` cho đến khi có kết luận đủ điều kiện và phương pháp phân tích phù hợp.

## Kiểm chứng và trạng thái thực tế

**30 kiểm thử liên quan đạt, 0 failure/error/skipped**: kiểm tra chọn mẫu tái lập, không lấy trùng nhóm bắt buộc, nguồn theo cutoff/công ty, không lộ dự đoán, identity/hash bị sửa, người ký không độc lập, unknown không thành âm tính, phút ước lượng/không hữu hạn/không khớp clock, và bảo vệ dữ kiện chỉ đọc. [Kết quả](ml_independent_review_20261022/tests.json), [log](ml_independent_review_20261022/tests.log).

Kiểm tra toàn bộ 69 gói bằng chứng xác nhận không chứa trường mô hình bị cấm, không có dòng khác công ty hoặc ngoài cutoff được cho phép. ZIP chỉ chứa phần công khai. Hai mẫu nhập vẫn trống; lượt kiểm tra ban đầu ghi **69 pending, 0 kết luận độc lập, phút thực tế null**. [Trạng thái nhập ban đầu](ml_independent_review_20261022/private/initial_validation/review_status.json).

**1.269 tệp bảo toàn không đổi**; 0 fit, 0 suy luận mới, 0 nhãn/oracle được đọc, 005 chỉ băm opaque trong kiểm tra bảo toàn. Không đổi model, baseline, hàng đợi hay kết luận người dùng; 0 lần gửi ra ngoài. [Biên bản máy đọc](ml_independent_review_20261022/verification.json).

Việc còn thiếu là người rà chính, người phân xử và các phiếu có kết luận/phút thực tế. Chưa thể báo bước rà độc lập đã hoàn tất hoặc xác nhận lợi ích ML.
