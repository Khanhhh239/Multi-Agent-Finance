# Bộ dữ liệu demo C001 / C002

Bộ này có **60 giao dịch mô phỏng cho mỗi doanh nghiệp**, từ 01/01 đến 29/02/2024. Dùng để thử nhập dữ liệu, xem lỗi, chọn model và chấm trên phiên local **8765**, bộ dữ liệu **003**.

| Tệp | Cách dùng |
| --- | --- |
| [01_C001_GIAO_DICH.csv](01_C001_GIAO_DICH.csv) | Chọn C001, nhập 60 giao dịch, đánh giá Isolation Forest |
| [02_C002_GIAO_DICH.xlsx](02_C002_GIAO_DICH.xlsx) | Chọn C002, nhập 60 giao dịch, đánh giá ECOD; đúng một sheet |
| [03_C001_THU_BAO_LOI.csv](03_C001_THU_BAO_LOI.csv) | Chọn C001, chỉ kiểm tra: cố ý có ba lỗi để xem cách ứng dụng báo lỗi |
| [BAT_DAU_O_DAY.html](BAT_DAU_O_DAY.html) | Tải về và mở bằng trình duyệt để đọc hướng dẫn từng nút bấm |

## Danh mục cần có

Các tệp khớp **danh mục mô phỏng của workspace đã hợp nhất ngày 07/11**, nguồn `data/feature_model_sync_20261017/sme_fraud_003`. Chỉ lấy mã nhân viên/NCC và tài khoản từ danh mục mô phỏng đó để tạo giao dịch mới; không sao chép giao dịch vận hành hoặc kết quả người rà.

C001 dùng các mã nhân viên như `E0000001`, `E0000003` và NCC từ `V0000001`; C002 dùng `E0000041`, `E0000043` và NCC từ `V0000081`. Danh mục phải thuộc đúng doanh nghiệp và đã tồn tại tại ngày giao dịch.

**Bản clone Git không kèm danh mục, database hoặc profile của máy phát triển.** Fixture nhỏ trong hướng dẫn cài mới dùng mã `E01`/`E02`, không khớp trực tiếp với các tệp này. Nếu mới clone, làm theo [hướng dẫn tạo demo từ bản Git](../../../docs/AGENT2_GITHUB.md) và dùng chính các tệp `SIMULATED_C001.*`/`SIMULATED_C002.*` mà fixture sinh ra; hoặc kết nối đúng danh mục trước khi nhập bộ trong thư mục này.

## Các bước demo

1. Mở `http://127.0.0.1:8765/data-import`, chọn **003 → C001** và tệp `01_C001_GIAO_DICH.csv`.
2. Bấm **Kiểm tra & tạo bản xem trước**. Khi hợp lệ có **60 dòng, 194 feature**.
3. Đọc cảnh báo, xác nhận lưu và chuyển sang ML. Lần nhập **thay toàn bộ tập ML** của công ty và xóa nhãn của tập thay thế; model đang chọn được giữ. Bản xem trước chưa thay tập dữ liệu đã lưu.
4. Chọn **Isolation Forest** và các mốc giờ Việt Nam:

   | Trường | Giá trị |
   | --- | --- |
   | Cuối kỳ train | **06/02/2024 12:00** |
   | Cuối kỳ calibration | **18/02/2024 12:00** |
   | Tỷ lệ cảnh báo tham chiếu | **10%** |

5. Bấm **Huấn luyện & đánh giá ứng viên → Xác nhận dùng vN → Chạy ML với phiên bản đang dùng**. Kỳ có **36 train / 12 calibration / 12 evaluation**.
6. Lặp lại với **C002**, tệp Excel và **ECOD**; cùng các mốc thời gian. Tải lại trang để kiểm tra mỗi công ty vẫn giữ đúng model.
7. Thử tệp `03_C001_THU_BAO_LOI.csv`: dòng 3 trùng mã, dòng 4 có dấu phẩy trong tiền, dòng 5 duyệt trước lúc tạo. Ứng dụng phải báo lỗi và chặn lưu.

Trong trang HTML, đường dẫn nhập tệp là thư mục chứa chính bộ mẫu đã tải về. Nguồn ML vẫn cần được cấu hình đúng như phần danh mục phía trên.

## Phạm vi kiểm tra

Đã kiểm tra ngày **07/11/2026** trên bản sao SQLite của workspace: cả CSV và Excel nhập 60 dòng/194 feature, IF/ECOD tách đúng 36/12/12, kích hoạt/chấm được 12 dòng và giữ model đang dùng sau bước nhập. Đã đối chiếu 1.440 ô dữ liệu Excel, mã/tài khoản kiểu văn bản và ngày giờ; tệp lỗi báo đúng ba lỗi. Database chính và danh mục giữ nguyên trong lượt thử.

Một số khoản cuối kỳ có số tiền lớn/cận hạn mức để quan sát điểm. Đây là **dữ liệu mô phỏng chưa có nhãn gian lận xác minh**; số cảnh báo tùy model/cấu hình. ML đang chạy shadow; nhập/chấm chưa tự đổi hàng đợi hồ sơ hoặc tạo gói phiếu rà mới. CatBoost cần nguồn nhãn riêng đủ điều kiện.

[Hướng dẫn sử dụng đầy đủ](../../../docs/HUONG_DAN_SU_DUNG_VA_DEMO.md) · [Báo cáo tổng quan](../../../docs/reports/app/agent2_overview_20261107.md).
