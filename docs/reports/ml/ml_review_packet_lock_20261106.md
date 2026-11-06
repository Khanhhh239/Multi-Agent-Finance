# Khóa đúng tập bằng chứng và phiếu rà — 06/11/2026

Đã kiểm tra lại và siết `ml_review_packets.load_packet`, dùng chung cho CLI `collect` và nhập phiếu web. Lỗi nhận JSON thêm trực tiếp ngoài manifest đã được chặn khi đưa phiếu lên web ngày 05/11. Lượt này kiểm tra toàn bộ thư mục bằng chứng và thêm kiểm thử độc lập cho trường hợp **12 → 13**.

## Quy tắc nhận gói

- Danh mục phiếu chỉ được dựng từ các JSON được liệt kê trong manifest và đã kiểm SHA256. Quét thư mục chỉ dùng phát hiện sai khác, không bổ sung phiếu.
- Toàn bộ tệp trong `public/evidence` phải trùng danh sách đã khóa. Tệp thêm trong thư mục con, tên `.JSON` viết hoa hoặc tệp khác định dạng cũng bị từ chối. Định dạng gói hiện hành lưu mỗi phiếu thành một JSON trực tiếp trong thư mục này.
- Đường dẫn manifest phải ở dạng tương đối chuẩn, không thoát gói, không dùng bí danh/trùng đường dẫn. Khóa JSON trùng bị từ chối thay vì âm thầm lấy giá trị sau.
- Tập review_id phải khớp chính xác hợp tập chọn của các model và `review_units`. Không nhận phiếu thừa, thiếu, trùng mã, trùng cặp doanh nghiệp/giao dịch hoặc sai danh tính trong bản ghi bằng chứng. Một giao dịch được nhiều model chọn vẫn chỉ có một phiếu chung.
- `selection.csv` phải giữ đúng cột và độ rộng dòng, đúng mã phiếu/công ty/giao dịch/hash bằng chứng/model/thứ hạng, không thừa hoặc thiếu dòng. Mỗi model đã đánh giá phải có đúng ngân sách số giao dịch đã khóa trong kế hoạch.
- JSON/CSV được phân tích từ chính các byte đã xác minh checksum. Trước khi trả gói, kiểm lại manifest, danh mục tệp và nội dung dùng để nhập; thay đổi trong lúc kiểm tra bị chặn. Kết quả CLI ghi mã kế hoạch đã xác minh, không mở lại kế hoạch để lấy mã khác sau đó.
- Lỗi làm dừng cả thao tác trước khi ghi vào web hoặc tạo thư mục kết quả CLI. CSV kết quả người rà `human_reviews.csv` vẫn là tệp được phép điền và không thuộc tập bằng chứng bất biến.

## Bằng chứng và kiểm thử

**201 test Python liên quan đạt**, gồm **19 test gói mới**. Các ca mới kiểm tra tệp thứ 13, tệp lồng/viết hoa/khác đuôi, thiếu/sửa bằng chứng, phiếu có trong manifest nhưng ngoài tập chọn, trùng mã/giao dịch/model, sai công ty/bản ghi nguồn, sai ngân sách/thứ hạng/hash/schema CSV, đường dẫn không chuẩn, khóa JSON trùng và manifest/bằng chứng đổi trong lúc đọc. Mỗi ca từ chối thông thường đối chiếu cả validator, CLI và nhập web, giữ nguyên bảng phiếu/kết quả hiện có và không tạo kết quả dở dang.

Đối chiếu trực tiếp trên bản sao gói `run_02` hiện hành:

| Trường hợp | CLI | Nhập web |
| --- | --- | --- |
| Gói hợp lệ | 12 phiếu, 0 kết quả rà | Nhập lại an toàn, vẫn 12 phiếu |
| Thêm JSON thứ 13 ngoài manifest | Từ chối, không tạo thư mục kết quả | Từ chối, vẫn 12 phiếu và 0 kết quả rà |

Bản sao thử nằm tại `.runtime/ml_packet_lock_20261106/fab189dbd912/`; chi tiết trong `results.json`. Gói nguồn được so sánh toàn bộ danh mục/hash trước và sau, giữ nguyên. Không nhập kết quả người rà mô phỏng vào demo chính và không đổi nhãn, dữ liệu hoặc model.

Mã kiểm thử: `tests/test_ml_review_packets.py`. Nhật ký đạt cuối: `.runtime/ml_packet_lock_regression_20261106.log`; probe gói thật: `.runtime/ml_packet_lock_probe_20261106.py` và `.runtime/ml_packet_lock_probe_20261106.log`. Hai ca giả lập thay đổi trong lúc đọc cũng đã chạy riêng trong `.runtime/ml_packet_lock_race_tests_20261106.log`.

```powershell
python -B -m unittest test_ml_review_packets test_ml_review_web test_ml_review_api test_company_ml_comparison -q
```

Demo chính được nạp lại mã mới tại `http://127.0.0.1:8853/ml-reviews`. Gói đã nhập được lưu như snapshot trong SQLite; không đọc tệp ngoài gói từ giao diện. Không cần chạy lại huấn luyện hoặc sinh lại gói so sánh để rà tiếp.

Đối chiếu trước/sau khởi động giữ nguyên nội dung **11 bảng** dữ liệu/model/nhãn/phiếu rà; kiểm đủ **24 tệp** theo manifest. API demo xác nhận **12 phiếu, 0 phiếu đã rà**. Bằng chứng: `.runtime/ml_packet_lock_live_state_20261106.json` và `.runtime/ml_packet_lock_live_verify_20261106.py`.
