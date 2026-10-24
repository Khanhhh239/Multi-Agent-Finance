# Kế hoạch chuẩn bị thí điểm sau v6

Soạn 2026-10-24, sau khi chấm niêm phong v6. Bổ sung cho [Pha E](05_pha_E_thi_diem_va_phap_ly.md) (thẩm định pháp lý, sáu mẫu biểu, đo KPI), không thay thế. Mọi số trong tệp này là **dữ liệu tổng hợp**; chưa có dữ liệu thật, tệp xuất mẫu hay đơn vị kế toán nào.

## 1. Điểm xuất phát

| Thành phần | Trạng thái | Dùng được vào thí điểm không |
|---|---|---|
| Luật, đồ thị quan hệ, đặc trưng thay đổi, ngân sách 3 cảnh báo, lý do tiếng Việt kiểm được số | Xong, có kiểm thử | **Có**, là nền của sản phẩm |
| Hàng đợi rà soát, ghi kết luận, trang nhiều khách, KPI K1 K2 K3 K5 | Xong | **Có** |
| Xếp hạng bằng học máy (L4-FB-PU) | Niêm phong: bắt 64,5% gian lận, 41,2% loại mới, báo nhầm tối đa 12,8%; trượt cổng lệch với phát triển | **Chỉ như lớp xếp thứ tự phụ**, không quảng bá con số, cần kiểm khoảng cách miền trên dữ liệu thật trước |
| Chế độ Cold (không nhãn) | Phát triển: tốt nhất 37,4% recall, không đạt chốt chặn | Chạy ở chế độ chỉ xem để đo, **không hứa mức bắt** |

Nói đúng với khách: công cụ **gợi ý thứ tự những chỗ đáng hỏi lại**, kèm lý do và chứng từ cần xin; kế toán viên quyết định.

## 2. Việc máy làm được ngay, không cần đối tác

| Mã | Việc | Đầu ra | Công sức | Phụ thuộc |
|---|---|---|---|---|
| P1 | Đóng gói mô hình v6 thành hiện vật triển khai: huấn luyện bản cuối trên cả 20 thế giới với h = 0,5, ghi hash, nối vào `pipeline_v4` như một chế độ tùy chọn; kiểm tương đương đặc trưng giữa đường ống CSV và ma trận | tệp mô hình, cấu hình, kiểm thử | 1 đến 2 ngày | không |
| P2 | Công cụ đo khoảng cách miền (Pha E bước E4.2): huấn luyện bộ phân biệt dữ liệu thật với dữ liệu sinh, báo AUC; trên 0,9 thì chỉ chạy luật và độ lệch | `scripts/domain_distance.py` | nửa ngày | chạy khi có tệp thật |
| P3 | Một trang yêu cầu tệp xuất cho đơn vị kế toán: cột nào cần xin từ phần mềm kế toán (dựa vào `data_contract.md`), ẩn danh thế nào, bao lâu lịch sử | `templates/yeu_cau_tep_xuat.md` | nửa ngày | không |
| P4 | Một trang giới thiệu cho đơn vị kế toán (việc làm, thời gian cam kết 30 phút mỗi khách mỗi tuần, dữ liệu xử lý ra sao, chưa hứa mức bắt) | `templates/gioi_thieu_don_vi_ke_toan.md`, cần luật sư duyệt | nửa ngày | không |
| P5 | Kho phản hồi "hợp lệ" dùng chung: lược đồ xuất kết luận đã ẩn danh từ kho rà soát, không chứa tên người hay mã công ty | mã xuất và kiểm thử | 1 ngày | **luật sư duyệt trước khi dùng dữ liệu thật** |

Thứ tự đề nghị: P3 và P4 trước (anh cầm đi hỏi được ngay), rồi P1, P2, P5.

### 2a. Tình trạng (cập nhật 2026-10-24 21:00)

| Mã | Trạng thái | Cách dùng |
|---|---|---|
| P1 | **Xong** | `results/v6/v6_secondary_score.joblib` (1,5 MB, SHA-256 `117d2075...ed5`, huấn luyện lại bằng `scripts/train_v6_model.py` trong 5 phút). Thêm vào cấu hình tuần hai khóa `v6_model_path` và `v6_model_sha256`; kết quả là hai cột phụ `v6_score`, `v6_percentile` trong `alerts.csv` và khóa `v6_secondary_score` trong `report.json`. **Không đổi cảnh báo nào** (có kiểm thử). Chạy thử đầu-cuối trên một công ty phát triển mất 40 giây. Mô hình tự tính hai tín hiệu không nhãn từ lịch sử công ty nên chạy được cả ở chế độ `cold`. Ghi chú: 285 trên 300 cột đặc trưng khớp giá trị với đường nghiên cứu; 11 cột là điểm hạng không nhãn tính trên lịch sử công ty thay vì cả thế giới (đúng thiết kế S2) |
| P2 | **Xong** | `python scripts/domain_distance.py --data <thư mục xuất> --company C001 --week 2026-W10 --out kq.json`; AUC trên 0,9 thì chạy luật và độ lệch, không dựa điểm v6 |
| P3, P4 | **Xong** | `templates/yeu_cau_tep_xuat.md`, `templates/gioi_thieu_don_vi_ke_toan.md` (cần luật sư duyệt) |
| P5 | **Xong** | `python scripts/export_feedback_labels.py --db ... --approval-ref <số hiệu phê duyệt pháp lý> --salt-file <tệp muối> --out ...`; từ chối chạy nếu thiếu số hiệu hoặc muối; chưa dùng cho đến khi luật sư duyệt |

## 3. Việc chỉ con người làm được

| Việc | Ai | Ghi chú |
|---|---|---|
| Thẩm định pháp lý (Pha E1): năm câu hỏi bằng văn bản, nhất là Nghị định 13/2023/NĐ-CP về dữ liệu cá nhân của nhân viên | Luật sư | Chưa có kết luận pháp lý nào trong dự án; các mẫu biểu đều chờ duyệt |
| Tìm 3 đến 5 đơn vị kế toán thử ở chế độ chỉ xem (tiêu chí Pha E3: khách 20 đến 100 nhân sự, có sổ chi tiết kèm người lập, người duyệt, thời gian, ít nhất 12 tháng) | Chủ dự án | Chưa có đơn vị nào |
| Lấy một tệp xuất mẫu thật (đã ẩn danh) từ ít nhất một phần mềm kế toán | Chủ dự án hoặc đơn vị kế toán | Hiện chỉ có bộ nhận CSV chung; chưa xác nhận bộ nhận riêng cho MISA hay hãng nào |
| Thử báo giá để đo sẵn lòng trả | Chủ dự án | Ngưỡng giả định: ít nhất 3 trên 5 đơn vị |

## 4. Điều kiện bắt đầu thí điểm

Chỉ bắt đầu khi đủ cả bốn điều kiện: (1) có biên bản tư vấn pháp lý; (2) có ít nhất một đơn vị kế toán ký thỏa thuận dữ liệu; (3) đã chạy P2 trên tệp thật và chọn chế độ phù hợp; (4) khách của đơn vị đã nhận thông báo cho nhân viên. Thiếu một điều kiện thì chưa chạy trên dữ liệu thật.

## 5. Ba điều không được làm

- Không trích dẫn con số 64,5% hay 88% như khả năng thật của sản phẩm: đó là số trên dữ liệu giả.
- Không nói "hệ thống phát hiện gian lận": nói "gợi ý đối chiếu chứng từ".
- Không dùng dữ liệu của một khách để cải thiện kết quả cho khách khác khi chưa có phê duyệt pháp lý (kho phản hồi dùng chung, P5).
