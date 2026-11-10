# Hướng dẫn demo nạp dữ liệu chung

Demo này minh họa việc nạp **một tệp sao kê** trên portal và ghi cho **cả Agent 1 và Agent 3**. Tệp mẫu có hai giao dịch giả lập, một khoản thu 12.000.000 đồng và một khoản chi 8.500.000 đồng.

## Chuẩn bị

1. Checkout nhánh `platform-Khanh` và chạy portal cùng các agent theo [README](README.md). Mở [Nạp dữ liệu](http://127.0.0.1:8800/#data).
2. Dùng một hồ sơ doanh nghiệp dành riêng cho demo. Lưu mã công ty và MST hợp lệ trong **Hồ sơ doanh nghiệp**, rồi tạo workspace cùng MST cho A3 nếu chưa có. A1 và A3 phải ở trạng thái đang chạy. Nếu A1 bắt buộc dùng danh mục tài khoản, thêm tài khoản mẫu `000012345678` vào danh mục của **môi trường thử** hoặc dùng mã tài khoản thử đã đăng ký nhất quán trong tệp.
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
