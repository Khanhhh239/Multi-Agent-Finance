# Bảo toàn nhãn khi bổ sung CSV — 06/11/2026

Đã sửa lỗi tải thêm một nhãn làm tập hiện hành giảm 15 → 1. `CompanyML.update_labels` gộp theo doanh nghiệp và mã giao dịch, giữ nhãn không có trong tệp. Cập nhật nhãn không thay giao dịch, byte ma trận feature, lịch sử nhập thô, artifact hoặc model đang dùng.

## Quy tắc xử lý

- Nhãn mới được thêm. Tải lại nhãn giống cả kết luận/người rà/căn cứ/thời điểm là thao tác lặp an toàn: giữ nhãn, revision và lịch sử cũ. Hai cách ghi múi giờ của cùng thời điểm được coi là giống nhau.
- Thay đổi kết luận 0/1 **hoặc** người rà, căn cứ, thời điểm đều là xung đột. Mặc định chặn cả lô; không lưu riêng các dòng còn lại trước khi người dùng quyết định.
- Web hiển thị số nhãn đang có, số thêm/trùng/xung đột/tổng sau lưu và bảng đối chiếu cũ/mới. Chọn **Giữ nhãn cũ** để bỏ qua các dòng xung đột và thêm các nhãn mới; hoặc **Sửa các nhãn xung đột** kèm lý do và xác nhận. Chính sách áp dụng cho mọi xung đột trong tệp; muốn sửa riêng một phần, tách tệp theo quyết định đã đối chiếu.
- Xem trước chỉ đọc. Quyết định ràng buộc với doanh nghiệp, bộ dữ liệu, revision và toàn bộ nội dung nhãn đã phân tích. CSV đổi hoặc phiên khác cập nhật nhãn/dữ liệu phải xem trước lại. Lưu trong một giao dịch SQLite `BEGIN IMMEDIATE` và kiểm revision trước khi ghi.
- Tệp rỗng/chỉ tiêu đề, mã trùng, sai công ty/giao dịch, thiếu căn cứ, chưa xác nhận, thời gian sai và CSV sai số cột đều bị chặn. Không có chế độ xóa/thay toàn bộ nhãn trong thao tác bổ sung.
- API cập nhật nguồn kết nối kèm CSV cũng gộp các nhãn còn hợp lệ cho giao dịch/feature không đổi và chặn xung đột. Khi trên web đã có tập ML, tải CSV nhãn đi qua luồng xem trước nhãn riêng.

Lịch sử thay đổi chi tiết nằm trong `company_ml_label_changes`: người thao tác được máy chủ xác thực, revision trước/sau, nhãn trước/sau, lý do và thống kê. Sự kiện `labels_updated` trong chuỗi hash tham chiếu thao tác và checksum; đọc lịch sử kiểm tra lại checksum. API trạng thái chỉ trả tham chiếu/thống kê, không đưa toàn bộ nhãn lịch sử vào phản hồi. Sao lưu/khôi phục giữ bảng mới như các bảng nghiệp vụ khác.

## Kiểm thử

- **182 test Python liên quan đạt**: bộ hồi quy 181 test và một test bổ sung backup/restore nhãn, lịch sử sửa và bổ sung tiếp sau khôi phục. Có 15 ca dịch vụ nhãn và 2 ca API mới, kiểm tra nguyên tử, quyền/công ty/holdout, revision cũ, nguồn rà thay đổi và CSV lỗi.
- **137 kiểm tra JavaScript đạt**, trong đó 19 test luồng cấu hình ML gồm 6 ca xem trước/quyết định/lỗi mạng/phản hồi trễ mới. Tổng 83 test entry của Node, với năm script cũ tự báo thêm số kiểm tra chi tiết.
- **36/36 kiểm tra Playwright đạt** trên Chrome headless, desktop 1365×1000 và mobile 390×844: 15 → 15 khi tải lại, 15 → 16 khi thêm mới, giữ/sửa xung đột, reload, lỗi CSV, mất kết nối, bản nháp, cập nhật ở phiên khác, phân quyền và giữ dữ liệu/model doanh nghiệp khác. Đã xem ảnh giao diện mobile; bảng đối chiếu cuộn ngang trong vùng của nó.

Bằng chứng cục bộ: `.runtime/label_merge_regression.log`, `.runtime/label_merge_backup_test.log`, `.runtime/label_merge_all_js_tests.log`, `.runtime/company_ml_labels_e2e_1793965419060/results.json` và ảnh desktop/mobile cùng thư mục. Lỗi mạng được mô phỏng bằng chặn request trong Playwright. Mọi nhãn/kết luận thử là mô phỏng trên database riêng.

Demo chính đã mở lại bằng mã mới tại `http://127.0.0.1:8853/company-ml`. Đối chiếu trước/sau giữ nguyên nội dung 10 bảng dữ liệu/model/lịch sử/phiếu rà hiện có, kiểm lại đủ 24 tệp trong gói so sánh `run_02`; không nạp nhãn kiểm thử vào demo này. Bảng audit nhãn mới được tạo rỗng. API xem trước mới trả lỗi đúng cho CSV chỉ có tiêu đề. Bằng chứng: `.runtime/label_merge_live_state_20261106.json` và script kiểm tra cùng tiền tố.

Demo kiểm thử nhãn tại `http://127.0.0.1:8859/company-ml`, kế toán viên chỉ xem ở cổng 8860. Chạy lại toàn bộ bài thử cần một thư mục QA mới vì bài thử có ghi nhãn mô phỏng:

```powershell
python -B tests/company_ml_labels_demo.py --port 8859 --root .runtime/labels_qa_new
$env:LABELS_DEMO_ROOT = 'D:\agent22\.runtime\labels_qa_new'
node tests/company_ml_labels_e2e.js
```

## Giới hạn

Bản sửa ngăn mất nhãn ở các lần bổ sung tiếp theo; không tự khôi phục những nhãn đã bị mất trước đó. Khôi phục cần CSV gốc hoặc bản sao lưu có nguồn xác nhận. Thay thế toàn bộ **tập giao dịch** ở màn hình nhập CSV/Excel vẫn là thao tác riêng có xác nhận và làm mất hiệu lực nhãn cũ như trước. Sửa nhãn cập nhật revision nên ứng viên chưa kích hoạt phải được đánh giá lại; model đang dùng vẫn được giữ và không tự huấn luyện/kích hoạt lại.
