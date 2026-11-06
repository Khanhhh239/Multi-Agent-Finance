# Phiếu rà cảnh báo ML trên web — 05/11/2026

Đã đưa 12 phiếu của gói so sánh C001/C002 lên `/ml-reviews`. Có dữ kiện, nhận xét/căn cứ, tham chiếu chứng từ, hành động hữu ích, lưu nháp và xác nhận kết quả theo người rà. Đồng hồ bắt đầu/tạm dừng/tiếp tục nằm trước bảng dữ kiện để người dùng bật trước khi kiểm tra.

Demo hiện có: **http://127.0.0.1:8765/ml-reviews**, đã hợp nhất về phiên dùng chính ngày 07/11. Giữ nguyên 12 phiếu C001/C002 và 0 kết quả rà; từ menu hoặc `/company-ml` có liên kết mở phiếu. Cổng 8853/8854 ở biên bản lịch sử đã dừng. Tất cả nguồn và danh tính ở demo là mô phỏng. [Chi tiết hợp nhất](../app/unified_local_20261107.md).

## Cách sử dụng

1. Chọn lượt đánh giá và doanh nghiệp, mở một giao dịch trong danh sách. Bấm **Bắt đầu / tiếp tục** để nhận phiếu và đo thời gian, rồi đối chiếu dữ kiện/chứng từ.
2. Chọn **Hữu ích**, **Không cần hành động — đã đủ căn cứ** hoặc **Chưa đủ căn cứ**. Ghi lý do, tài liệu còn thiếu và tham chiếu đã kiểm tra. Khi đánh dấu hữu ích, phải có hành động nghiệp vụ cụ thể.
3. Bấm **Tạm dừng** khi nghỉ. Có thể lưu bản nháp để tiếp tục sau; tải lại giữ đúng phiếu/doanh nghiệp, nội dung đã lưu và thời gian đã xác nhận.
4. Kiểm tra thời gian, tích xác nhận đã trực tiếp rà, rồi bấm **Xác nhận đã rà**. Lưu kết quả sẽ dừng đồng hồ trước. Chuyển phiếu sẽ dừng phiên đang chạy và lưu bản nháp đã nhập nếu đã nhận phiếu.
5. Kế toán trưởng/giám đốc có thể xuất CSV theo phạm vi được cấp. Bảng tổng hợp tên model chỉ mở khi toàn bộ phiếu trong phạm vi tài khoản đã hoàn tất; trước đó chỉ có tiến độ và phút đã ghi nhận.

Màn hình rà không gửi tên model, điểm, thứ hạng hoặc tập chọn riêng vào dữ liệu công khai. Cùng giao dịch xuất hiện ở nhiều model được rà một lần; khi tổng hợp, kết quả và thời gian của giao dịch đó được quy về từng danh sách model, còn tổng công sức thực tế chỉ đếm một lần. `unknown` được báo riêng, không biến thành không hữu ích. Không tự chọn/kích hoạt model hoặc chuyển kết quả hữu ích thành nhãn gian lận/CatBoost.

## Đo và lưu thời gian

Thời gian được tính ở máy chủ; trình duyệt hiển thị đồng hồ bằng đồng hồ đơn điệu và không được gửi số phút tùy ý. Mỗi phiên có token riêng, phiên bản phiếu và người sở hữu. Heartbeat mỗi 10 giây xác nhận các khoảng đang kiểm tra. Thời gian tạm dừng không được cộng.

Khi tab bị ẩn, giao diện yêu cầu tạm dừng. Khi mất kết nối quá 30 giây hoặc mất tab/phiên, phần đuôi chưa được xác nhận bị bỏ thay vì tự suy đoán là thời gian làm việc. **Dừng phiên cũ để tiếp tục** giữ các khoảng đã xác nhận và cho bắt đầu lại. Cơ chế này có thể bỏ phần làm việc cuối chưa gửi được khi mất mạng; người rà cần kiểm tra số thời gian trước xác nhận. Giới hạn mỗi phiếu là 24 giờ.

Sau lỗi mạng/phiên xung đột, các nút ghi bị khóa để người dùng tải lại trạng thái. Không tự gửi lại POST. Nội dung chưa lưu được giữ trên màn hình khi dùng nút tải lại; phiên CSRF mới được lấy lại sau khi server khởi động lại. Hai tab cùng sửa hoặc người khác ghi đè bị chặn bằng revision, token và danh tính máy chủ.

## Quyền và dữ liệu

- Quyền `ml_review`: kế toán viên/kế toán trưởng/giám đốc, giới hạn theo doanh nghiệp trong danh tính máy chủ. Bấm bắt đầu nhận quyền sửa phiếu; chỉ đúng người dùng và person_id đã nhận được sửa. Người khác trong cùng doanh nghiệp có thể xem nhưng không ghi đè. Chưa có luồng chuyển người phụ trách.
- Quyền xem tổng hợp/xuất CSV: `ml_manage` của kế toán trưởng/giám đốc. Dữ liệu công ty khác bị lọc; nhân viên C001 không xem hoặc ghi phiếu C002.
- Phiếu chưa có đủ kết quả, căn cứ/tham chiếu, thời gian đo và xác nhận thì không được chốt. Hành động bắt buộc khi `useful=yes`. Kết quả này là người rà xác nhận, chưa phải nghiệm thu độc lập hoặc phê duyệt kết luận kế toán.
- Các bảng `ml_review_packets`, `ml_review_units`, `ml_review_work`, `ml_review_events` nằm cùng SQLite. Có revision, trạng thái/nhật ký và kiểm tra hash trạng thái; đọc danh sách/chi tiết/tổng hợp trong transaction để nhất quán khi có hai phiên. Backup/restore hiện hữu giữ được gói, bản nháp, thời gian và kết quả; không cần đọc lại thư mục nguồn sau restore.
- Dữ liệu/model/nhãn vận hành và file của gói so sánh gốc giữ nguyên. Kết quả web nằm trong SQLite; CSV được xuất theo yêu cầu, tương thích `company_ml_comparison collect`.

## Kiểm tra gói bằng chứng

**Bổ sung 06/11:** đã siết danh mục mọi tệp trong thư mục bằng chứng, xác minh lại thay đổi trong lúc đọc, kiểm schema/ngân sách và thêm 19 test gói độc lập. Thử bản sao `run_02` với JSON thứ 13 bị chặn ở cả CLI/web; bộ hồi quy mới 201 test đạt. [Quy tắc và bằng chứng mới](ml_review_packet_lock_20261106.md).

`ml_review_packets.load_packet` xác minh manifest/checksum trước nhập, chỉ nhận chính xác các JSON bằng chứng được liệt kê, đối chiếu tập review_id với các model và dòng chọn, chặn trùng/thừa/sai công ty/ngân sách. Web sao chép snapshot đã xác minh vào SQLite, không nhận đường dẫn tùy ý từ giao diện và không nạp model pickle khi rà.

CLI `collect` cũng dùng bộ kiểm tra này. Đã sửa lỗi nhận tệp bằng chứng thêm ngoài manifest được nêu trong biên bản rà trước; thêm JSON ngoài gói sẽ bị từ chối thay vì tăng số phiếu 12 → 13. Lỗi bổ sung nhãn ở chức năng khác đã được sửa trong [cập nhật riêng ngày 06/11](company_ml_labels_20261106.md).

## Cấu hình và kiểm thử

Máy chủ có thể nhập gói đã khóa bằng đối số `ml_review_roots` của `make_server`, hoặc cờ CLI lặp lại:

```powershell
python -B -m sme_fraud.review_server --ml-review-comparison .runtime/company_ml_comparison_20261104/run_02
```

Dùng các đối số nguồn/database và tích hợp danh tính phù hợp như server hiện có. Không có danh tính máy chủ thì không mở quyền ghi. Demo `tests/data_import_demo.py` tự kết nối gói C001/C002 này nếu đã có; gói đã nhập vẫn nằm trong SQLite sau restart.

- **165 test Python liên quan đạt**, gồm 12 test service và 3 test API mới: phân quyền/phạm vi, dữ kiện không lộ model, thời gian chạy/nghỉ/hết hạn/khôi phục, hai tab và nonce sai, xác nhận/hành động/căn cứ, nháp/restart, tổng hợp `unknown`, CSV tương thích, gói thừa và backup/restore. Chạy lại 15 test service/API sau các chỉnh sửa cuối cùng.
- **131 kiểm tra JavaScript trong 12 bộ đạt**, gồm đồng hồ định dạng, escape dữ kiện, không hiển thị trường model riêng, tổng hợp chưa đủ phiếu và tách thời gian duy nhất/theo model.
- **27/27 kiểm tra Playwright trên Chrome đạt**: bắt đầu/dừng/tiếp tục với thời gian thật, loại thời gian nghỉ, lưu nháp/tải lại, thiếu hành động bị từ chối, xác nhận/CSV, đổi công ty/tải lại, quyền chỉ C001 và chủ sở hữu, lỗi mạng/giữ nội dung/khôi phục phiên, viewport 390 px không tràn. Trong Chrome headless, sự kiện tab ẩn được mô phỏng bằng `visibilitychange`; chưa kiểm chứng chuyển tab trên điện thoại vật lý.

Workspace kiểm thử riêng: `tests/ml_reviews_demo.py`, cổng **8857/8858**, database `.runtime/ml_reviews_demo_20261105/review.sqlite3`. Các phiếu `SIMULATED` được nhập trong kiểm thử chỉ tồn tại ở database này, không đưa vào demo 8853 hoặc gói nguồn.

Nhật ký: `.runtime/ml_review_web_tests.log`, `.runtime/ml_review_web_regression.log`, `.runtime/ml_review_web_final_service_tests.log`, `.runtime/ml_review_web_js_tests.log`. Bằng chứng browser cuối nằm trong `.runtime/ml_reviews_e2e_1793855417008/` (`results.json`, ảnh desktop/mobile và CSV mô phỏng). Ảnh kiểm tra chỉ đọc trên demo 8853: `.runtime/ml_reviews_live_20261105/ready.png`, hiển thị C001 có 0/6 phiếu xác nhận, đồng hồ 00:00:00 và nút bắt đầu mở.

Đối chiếu triển khai: demo 8853 có đủ **12 phiếu, 0 phiếu đã rà**; 8854 chỉ thấy C001. Revision dữ liệu và binding model của C001/C002 vẫn khớp `run_02`. Gói này vẫn chỉ là mô phỏng, chưa có chứng từ gốc để nghiệm thu chất lượng phát hiện trên doanh nghiệp thật.
