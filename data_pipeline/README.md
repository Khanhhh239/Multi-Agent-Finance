# Bộ dữ liệu Minh Phát MPX10

Bản 3.0.0 dùng seed `20261108`, số dư đầu kỳ ngày 31/12/2022, nghiệp vụ từ 01/01/2023 đến 14/10/2026 và khóa sổ đến hết tháng 08/2026. Kho có 7 chi nhánh, 5.000 nhân viên, 18.000 khách hàng, 1.200 nhà cung cấp và 4.000 mã hàng/dịch vụ. Đây là doanh nghiệp mô phỏng. Quy mô và cơ cấu phân phối tham chiếu công bố của Digiworld. [Công bố Digiworld](https://digiworld.com.vn/thong-cao-bao-chi/digiworld-ch%C3%ADnh-th%E1%BB%A9c-v%C6%B0%E1%BB%A3t-ng%C6%B0%E1%BB%A1ng-t%E1%BB%B7-%C4%91%C3%B4-h%C6%B0%E1%BB%9Bng-t%E1%BB%9Bi-t%C4%83ng-tr%C6%B0%E1%BB%9Fng-k%E1%BB%B7-l%E1%BB%A5c-n%C4%83m-2026)

| Agent | Dữ liệu nạp | Khóa ghép và phạm vi |
| --- | --- | --- |
| A1 | 50.000 hóa đơn, 11.020 khoản thu, 135.046 dòng ngân hàng, 3 kỳ sao kê, 8.000 khoản chi dự kiến, 110 lần liên hệ | `invoice_id` ghép hóa đơn với khoản thu và liên hệ. `bank_id` ghép khoản thu với sao kê. Lấy hóa đơn gần nhất tương thích từ tháng 09–10/2026, loại hóa đơn điều chỉnh hoặc có khoản thu trước ngày lập. Sao kê đủ dòng theo các kỳ tháng 08–10. |
| A2 | 10.000 giao dịch, danh mục doanh nghiệp và đối tác, lịch nghỉ, chứng từ và dòng định khoản | `transaction_id` là mã bút toán gốc, `document_id` ghép đầu và dòng chứng từ. `source_account_code` giữ tài khoản gốc. Tập gần nhất từ 11–14/10/2026. Thời điểm tạo lấy từ nguồn, thời điểm duyệt và ghi sổ phục vụ rà soát được mô phỏng. |
| A3 | 2.500 XML hóa đơn mua, 2.500 XML hóa đơn bán, 461 dòng ngân hàng, 2.500 dòng bảng kê mua | MST người bán, mẫu số, ký hiệu và số hóa đơn xác định chứng từ. Ngày lập thuộc 01–14/10/2026. Sao kê chỉ gồm giao dịch gắn với chứng từ được chọn. XML mô phỏng không ký số, báo cáo A3 dùng bộ luật nháp. |
| A4 | DuckDB đầy đủ, 19.784.697 dòng sổ cái, 5.110.372 bút toán, 1.302.000 hóa đơn bán và 183.999 hóa đơn mua | `journal_id` nối nghiệp vụ với sổ cái. `invoice_id` hoặc `bill_id` nối hóa đơn với chi tiết và thanh toán. |

CSV dùng UTF-8, tiền VND dạng số nguyên, ngày ISO `YYYY-MM-DD`, dấu thời gian A2 có múi giờ `+07:00`. Mã chứng từ, mã đối tác và MST phải đọc như chuỗi. Tệp `inputs/manifest.json` kê đường dẫn, kích thước và SHA-256 cho mỗi tệp. Header của từng CSV là hợp đồng cột cho agent nhận. Khi đổi dữ liệu nguồn, giữ khóa ổn định, đối chiếu tổng trước thuế + VAT = tổng thanh toán, và kiểm tra số dư đầu kỳ + thu − chi = số dư cuối kỳ trước khi ghi.

Doanh thu thuần 2023–2025 lần lượt khoảng 9.773, 10.771 và 11.971 tỷ đồng. Doanh thu 2026 đến 14/10 khoảng 10.391 tỷ đồng. Đối soát kho kiểm tra số dư công nợ, tồn kho, khóa ngoại, kỳ khóa sổ và các kịch bản trong `ground_truth`. Bút toán `TEST-UNBALANCED` cố ý lệch 1.000 đồng. `metric_baseline.json` có 56 chỉ tiêu thực thi được và 10 chỉ tiêu thiếu bộ xử lý trong A4 hiện tại. A2 ghi nhận 902 lượt khớp quy tắc, 0 hồ sơ đạt điều kiện đưa vào hàng đợi và chưa có mô hình huấn luyện cho tập mới.

Hệ tài khoản tương thích TT133 của code. Thuế suất VAT 10%, lịch làm việc theo ngày trong tuần, các khoản khấu trừ lương và lãi vay là giả định mô phỏng. Phiên bản này chưa mô phỏng lô thu gộp, hồ sơ XML thay thế thực tế và kịch bản dư nợ sát hạn mức. `validation.json` và `reproducibility.json` lưu kết quả kiểm tra. Kiểm tra tái lập chạy hai lần trên cấu hình nhỏ.

Từ thư mục gốc, dùng Python của A4 để tạo và kiểm tra kho. Chọn thư mục đích mới trong `portal/workspace/datasets`.

```powershell
$dataset = 'portal/workspace/datasets/enterprise-x10-v3-next'
.\agent4\.venv\Scripts\python.exe data_pipeline/enterprise.py --out $dataset
.\agent4\.venv\Scripts\python.exe data_pipeline/validate.py $dataset
.\agent4\.venv\Scripts\python.exe data_pipeline/export.py $dataset
.\agent4\.venv\Scripts\python.exe data_pipeline/metric_baseline.py $dataset
```

Chạy `data_pipeline/stage.py <thư mục dữ liệu> a1`, `a2`, `a3` lần lượt bằng Python của agent tương ứng để kiểm tra bằng bộ đọc và tạo trạng thái vận hành. Sau đó trỏ cấu hình A2 đến `runtime/a2` tại vị trí đã tạo, chép trạng thái và khóa A1 vào thư mục riêng của mã doanh nghiệp, chép workspace A3 theo MST, đặt `AGENT4_DB` đến `warehouse.duckdb` và khởi động portal với hồ sơ MPX10. Thư mục dữ liệu, cơ sở dữ liệu và khóa nằm trong các đường dẫn được Git bỏ qua.

Phiên bản đang dùng trên máy nằm trong `portal/workspace/datasets/enterprise-x10-v3-candidate02`. Để quay lại Sao Việt, dừng portal và các agent, phục hồi `portal/config.local.json` và `portal/workspace/company.json` từ `previous-configuration`, rồi khởi động lại. Cấu hình cũ trỏ đến các dữ liệu cũ vẫn lưu ở vị trí ban đầu.
