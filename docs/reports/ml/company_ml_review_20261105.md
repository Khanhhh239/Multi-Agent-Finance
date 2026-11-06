# Rà lại luồng nhập và đánh giá ML — 05/11/2026

Đã kiểm tra mã nhập dữ liệu, cập nhật nhãn, chọn model và tổng hợp phiếu rà. Hai lỗi dưới đây được tái hiện trên workspace mô phỏng riêng, không sửa database demo hoặc gói so sánh `run_02`. Lượt này ghi nhận vấn đề, chưa sửa mã nghiệp vụ.

## Lỗi cần sửa trước

### 1. Bổ sung nhãn đang thay thế toàn bộ tập nhãn

**Đã sửa ngày 06/11:** gộp theo mã giao dịch, giữ nhãn không liên quan, xem trước và quyết định xung đột rõ ràng; lưu lịch sử sửa nhãn. [Bản sửa và kiểm thử](company_ml_labels_20261106.md). Phần bên dưới ghi lại lỗi trước khi sửa.

`CompanyML.update_labels` bỏ tập nhãn cũ khi đọc `_data`, rồi ghi lại riêng kết quả `labels_csv` của tệp mới. Trong khi đó, giao diện mô tả thao tác là bổ sung nhãn.

- Vị trí: `sme_fraud/company_ml.py:224–230`; mô tả giao diện tại `review_ui/company_ml.js:56`.
- Tái hiện: nạp 15 nhãn hợp lệ, tiếp theo tải một nhãn thuộc cùng tập giao dịch. `labels_count` giảm **15 → 1**; 14 nhãn không có trong tệp mới biến mất khỏi tập ML hiện hành. Giao dịch và feature vẫn còn.
- Ảnh hưởng: mất độ phủ nhãn hiện hành, có thể làm CatBoost mất điều kiện train hoặc thay đổi phần evaluation có nhãn. Đây không phải thao tác thay thế tập giao dịch CSV/Excel vốn đã có cảnh báo riêng.
- Hướng sửa: mặc định giữ nhãn hiện có và bổ sung theo transaction_id. Quy định rõ cách xử lý nhãn xung đột; muốn thay toàn bộ cần chế độ riêng, mô tả và xác nhận rõ. Lưu dấu vết thay đổi nhãn.
- Kiểm thử cần thêm: tệp bổ sung một nhãn không làm mất các nhãn không liên quan; nhãn xung đột/không cùng doanh nghiệp/sai revision bị xử lý đúng.

### 2. Tổng hợp phiếu nhận thêm bằng chứng không nằm trong manifest

**Đã sửa khi đưa phiếu rà lên web ngày 05/11:** web và CLI cùng kiểm tra manifest, tập review_id và dòng chọn trước khi nhận bằng chứng; JSON thêm ngoài gói bị chặn. [Chi tiết và kiểm thử](ml_review_web_20261105.md).

**Siết và xác minh lại ngày 06/11:** kiểm tra toàn bộ thư mục bằng chứng, dùng đúng byte đã xác minh checksum, đối chiếu ngân sách/schema và thêm 19 test gói. Probe bản sao `run_02` xác nhận tệp thứ 13 bị từ chối, số phiếu đã nhập vẫn là 12. [Bản sửa và bằng chứng](ml_review_packet_lock_20261106.md). Các gạch đầu dòng tiếp theo ghi lại lỗi trước khi sửa.

`collect` kiểm checksum các tệp được liệt kê trong manifest, nhưng sau đó lại quét tất cả `public/evidence/*.json` để tạo danh mục phiếu. Tệp thêm sau khi khóa gói vẫn được đưa vào danh mục này.

- Vị trí: `sme_fraud/company_ml_comparison.py:225–233`.
- Tái hiện trên bản sao: thêm một JSON bằng chứng ngoài manifest, giữ nguyên mọi tệp đã khóa và giữ phiếu kết quả trống. Tổng hợp vẫn chạy, `review_units` đổi **12 → 13**. Không nhập kết quả người rà giả lập trong probe này.
- Ảnh hưởng: thống kê quy mô phiếu không còn ràng buộc với tập chọn đã khóa. Theo cách tổng hợp hiện tại, nếu kết quả cho phiếu ngoài tập chọn được thêm vào, phần tổng số phiếu/phút duy nhất cũng có thể bị tính sai.
- Hướng sửa: chỉ đọc bằng chứng đã được liệt kê và kiểm checksum; đối chiếu tập review_id với hợp của `selected_review_ids`, chặn ID trùng, thừa hoặc sai phạm vi doanh nghiệp. Không tạo thêm phiếu bằng cách quét thư mục không được kiểm soát.
- Kiểm thử cần thêm: JSON ngoài manifest, ID trùng/ngoài tập chọn, bằng chứng thêm vào và phiếu cho giao dịch không thuộc tập chọn đều bị từ chối.

## Giao diện cần làm rõ

**Đã xử lý hai điểm giao diện bên dưới ngày 05/11:** có API điều kiện dùng chung với backend, kiểm tra theo kỳ và kiểm tra artifact trước chấm/giữ. [Biên bản sửa và kiểm thử](company_ml_readiness_20261105.md). Lỗi manifest đã được sửa ngày 05/11; lỗi mất nhãn đã được sửa ngày 06/11 theo các liên kết phía trên.

- **CatBoost:** `review_ui/company_ml.js:61` chỉ kiểm tra có ít nhất một nhãn để mở lựa chọn. Backend kiểm đủ mọi dòng train, đủ hai lớp và thời điểm biết nhãn. Cần hiển thị độ phủ nhãn cho đúng kỳ train và lý do chưa đủ điều kiện; tránh để người dùng bấm huấn luyện rồi mới nhận lỗi. Backend hiện vẫn chặn đúng.
- **Model không tương thích:** `review_ui/company_ml.js:59` đã có thông báo khác định dạng/feature, nhưng điều kiện mở nút giữ/chấm ở dòng 46 chưa xét tương thích. Backend vẫn từ chối; giao diện nên khóa nút và nêu bước khắc phục.

## Cải tiến sau khi sửa lỗi

1. Đưa phiếu rà và tổng hợp so sánh lên web, có ghi nhận căn cứ, hành động hữu ích và bộ đếm phút kiểm tra/tạm dừng. Phân biệt `unknown` với không hữu ích và giữ dữ kiện dành cho người rà tách khỏi điểm/model.
2. Bổ sung chế độ nhập nối thêm hoặc cập nhật có kiểm soát theo mã giao dịch. Phiên bản hiện tại thay thế toàn bộ tập ML; cần dựng lại feature lịch sử nhất quán và giữ revision/audit khi thêm chế độ mới.
3. Mở rộng nguồn master/chứng từ/dòng bút toán và lịch sử nghiệp vụ có thời điểm quan sát. Luồng nhập hiện chỉ có master và lịch nghỉ kết nối; các feature phụ thuộc nguồn thiếu có thể bằng 0. Việc này ảnh hưởng ý nghĩa dữ liệu trước khi bàn tối ưu thuật toán.

## Bằng chứng

- Script kiểm tra cô lập: `.runtime/probe_ml_review_20261105.py`.
- Kết quả: `.runtime/company_ml_audit_20261105/371ae80e11a8/probe_results.json`.
- Gói so sánh gốc giữ nguyên; chưa có kết quả rà hữu ích/phút thực tế được tạo. Số 136 test đạt ở lượt trước không bao phủ hai trường hợp mới phát hiện này.

Ưu tiên: bảo toàn nhãn → khóa chính xác tập bằng chứng → đồng bộ điều kiện UI/backend → màn hình rà và các nguồn bổ sung.
