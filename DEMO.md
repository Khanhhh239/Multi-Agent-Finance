# Hướng dẫn demo nạp dữ liệu chung

## Demo Minh Phát MPX10

Hồ sơ chung là **MPX10**, MST mô phỏng **0999999905**, ngày trong tệp theo ISO và tiền VND dạng số nguyên. A1–A3 nhận dữ liệu qua portal. A4 truy vấn kho DuckDB Minh Phát đã cấu hình trên máy chủ.

Trong `portal/config.local.json`, đăng ký đúng cặp mã doanh nghiệp và MST để A3 mở workspace mô phỏng:

```json
"demo_company": { "code": "MPX10", "tax_code": "0999999905" }
```

Workspace A3 đã chuẩn bị phải nằm tại `<AGENT3_WORKSPACES>/0999999905` và giữ `"simulated": true`. Khởi động lại portal cùng các agent sau khi đổi cấu hình. Với hồ sơ doanh nghiệp thật, để `demo_company` là `null`. Có thể chọn một cấu hình thử riêng bằng biến môi trường `MAF_PORTAL_CONFIG`. Cấu hình thử cần dùng cổng riêng và thư mục dữ liệu riêng, gồm `agents.agent1.storage_root`, workspace A3 và bản A2 được phục hồi bằng công cụ `sme_fraud.review_backup`.

Từ thư mục gốc, tạo gói nhỏ từ bản xuất MPX10 đã dựng theo [pipeline](data_pipeline/README.md):

```powershell
python data_pipeline/demo_inputs.py portal/workspace/datasets/enterprise-x10-v3-candidate02 portal/workspace/mpx10-demo-input
```

Chọn cả bốn tệp trong **Nạp dữ liệu chung** của môi trường thử. Giữ nguyên tệp ZIP hóa đơn và xác nhận thay dữ liệu A2 khi portal yêu cầu.

| Tệp | Kết quả mong đợi |
| --- | --- |
| `01_invoices.csv` | A1 nhận hai hóa đơn từ kho Minh Phát. |
| `02_sao_ke_chung.csv` | A1 và A3 cùng nhận hai khoản thu theo cùng mã giao dịch, ngày và số tiền. Có thể mở Đối soát A1 để xem hai khoản thu. |
| `03_transactions.csv` | A2 kiểm tra và nạp 10.000 giao dịch. Hàng đợi của bản MPX10 hiện không có hồ sơ đạt điều kiện rà soát. |
| `04_hoa_don.zip` | A3 phân loại một hóa đơn mua và hai hóa đơn bán. Sau phân tích, báo cáo hiển thị ba hóa đơn và hai giao dịch ngân hàng. |

Trong **Hỏi Đáp**, thử câu “Doanh thu thuần quý 3 năm 2026 là bao nhiêu?” rồi mở **Kiểm tra nguồn**. Kết quả của kho MPX10 là **3.447.235.086.468 đồng**. Nạp lại sao kê nguyên nội dung dưới tên khác phải báo tệp đã ghi vào A1 và A3, số phiên bản gói không tăng.

## Demo chỉ với sao kê

Demo này minh họa việc nạp **một tệp sao kê** trên portal và ghi cho **cả Agent 1 và Agent 3**. Tệp mẫu có hai giao dịch giả lập, một khoản thu 12.000.000 đồng và một khoản chi 8.500.000 đồng.

## Chuẩn bị

1. Checkout nhánh `platform-Khanh` và chạy portal cùng các agent theo [README](README.md). Mở [Nạp dữ liệu](http://127.0.0.1:8800/#data).
2. Dùng một hồ sơ doanh nghiệp dành riêng cho demo. Lưu mã công ty và MST hợp lệ trong **Hồ sơ doanh nghiệp** của portal; A3 tự đồng bộ, không tạo workspace riêng. Bật A1 và A3 từ portal. Nếu vừa cập nhật code, khởi động lại portal và các agent để nhận bản mới. Nếu A1 bắt buộc dùng danh mục tài khoản, thêm tài khoản mẫu `000012345678` vào danh mục của **môi trường thử** hoặc dùng mã tài khoản thử đã đăng ký nhất quán trong tệp.
3. Lấy tệp [sao-ke-chung.csv](portal/static/samples/sao-ke-chung.csv). Khi portal đang chạy, cũng có thể tải từ [mục mẫu sao kê](http://127.0.0.1:8800/samples/sao-ke-chung.csv). Giữ tài khoản và mã giao dịch ở dạng văn bản nếu mở hoặc lưu lại bằng Excel.

## Trình diễn và kết quả mong đợi

| Bước | Kết quả cần thấy |
| --- | --- |
| Mở khóa **Nạp dữ liệu** và chọn `sao-ke-chung.csv` một lần. | Hàng chờ chỉ có **một tệp**, nhãn **Sao kê dùng chung**, với kết quả kiểm tra riêng cho A1 và A3. Mỗi agent thấy hai dòng. |
| Khi cả hai sẵn sàng, bấm **Niêm phong và ghi** và xác nhận. | Lịch sử gói có một tệp với kết quả **Đã ghi** cho cả hai agent. Nếu hồ sơ đã có phiên bản gói, điền lý do bổ sung theo yêu cầu trên màn hình. |
| Mở A1 để xem nguồn dữ liệu, rồi mở A3 để xem tệp ngân hàng. | Với kho thử trống, A1 có hai dòng sao kê. A3 có một tệp sao kê đã chuẩn hóa. Khi chạy phân tích A3, bảng ngân hàng hiện hai giao dịch và thông tin đối ứng. |
| Thử nạp lại nguyên tệp, kể cả đổi tên. | Portal báo tệp đã được ghi cho cả hai agent. Số dòng không tăng. |

Tệp mẫu chỉ có sao kê. Để trình diễn ghép hóa đơn trên A3, cần thêm XML có số tiền và thông tin đối ứng phù hợp. Để lập dự báo A1, cần thêm sổ công nợ, tiền thu hoặc lịch chi phù hợp với kịch bản.

## Các tệp demo khác

| Dữ liệu | Vị trí | Dùng cho |
| --- | --- | --- |
| Sao kê chung hai dòng | [CSV mẫu](portal/static/samples/sao-ke-chung.csv) | Demo một lần nạp cho A1 và A3 |
| Đại Phát | [Sáu bảng đầu vào](agent1/pilot/demo_dai_phat) | Demo riêng A1 |
| Giao dịch mẫu | [CSV/Excel mẫu](agent2/examples/company_ml/demo_data_20261107) | Demo riêng A2 |
| Sao Việt | [XML, sao kê và bảng kê mẫu](agent3/agent3_tax_compliance/demo/DN_Phan_mem_Sao_Viet) | Demo riêng A3 |
| Minh Phát MPX10 | [Kho DuckDB nén qua Git LFS](portal/workspace/datasets/enterprise-x10-v3-candidate02/warehouse.duckdb.zlib) và [hướng dẫn dựng dữ liệu](data_pipeline/README.md) | Kho gốc A4 và nguồn xuất tập con A1–A3. Các tập con đã nạp sẵn không nằm trong Git. A4 vẫn dùng kho cấu hình trên máy chủ. |

Các bộ mẫu riêng mang mã công ty khác nhau. Khi cần trình diễn cùng một công ty trên cả bốn agent, dùng pipeline MPX10 và cấu hình cùng hồ sơ theo hướng dẫn. Để chạy kiểm thử luồng sao kê mà không ghi vào kho đang dùng, chạy `python -m unittest portal.test_bank_intake -v` tại thư mục gốc.
