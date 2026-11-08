# 02 · Rà soát nguồn dữ liệu có sẵn: dùng / không dùng

Mục tiêu: nói rõ **cái gì có thể dùng**, **dùng vào việc gì**, **vì sao loại**. Không có bộ nào là sổ cái DNVVN Việt Nam thật → không bộ nào thay được dữ liệu tổng hợp; chúng dùng để **hiệu chỉnh phân phối** hoặc **làm benchmark năng lực**.

## 1. Bảng tổng hợp
| Nguồn | Loại | Quy mô / đặc điểm | Dùng cho Agent 4? | Dùng vào việc |
|---|---|---|---|---|
| **Customer Invoices (Kaggle, pradumn203)** | Hóa đơn bán + ngày thanh toán | ~50.000 dòng × 19 cột (bản sao GitHub đã kiểm tra bởi phiên Agent 1) | ✅ một phần | Hiệu chỉnh *phân phối độ trễ thanh toán* (hình dạng đuôi dày, tỷ lệ chưa đóng) |
| **Global B2B / bộ thứ 3 (sonalisingh1411)** | Hóa đơn | Chưa xác minh được (cần CSV) | ⚪ chưa | Chỉ để đối chiếu nếu có CSV |
| **Atradius Payment Practices (VN 2025)** | Khảo sát tập quán thanh toán | Chỉ số tổng hợp, không có dòng | ✅ tham số | Mức trễ trung bình ~1 tháng → hiệu chỉnh `late_mean_days` (xem `04`) |
| **Spider 2.0 / BIRD / Spider‑lite** | Benchmark NL→SQL | Schema doanh nghiệp thật, truy vấn dài | ✅ benchmark | Thiết kế bộ E9; bằng chứng "NL2SQL tự do kém" |
| **FinQA, ConvFinQA, TAT‑QA** | QA số học tài chính (Anh) | Báo cáo công ty niêm yết | ✅ một phần | Mẫu câu hỏi hội thoại tài chính, kiểm tra suy luận số; **không** dùng trực tiếp (khác ngôn ngữ/chuẩn) |
| **BFCL, τ‑bench, ToolBench** | Benchmark function calling / agent | Công cụ tổng quát | ✅ benchmark | Phương pháp đo "chọn đúng công cụ/tham số" cho model nhỏ |
| **Báo cáo tài chính công ty niêm yết VN** (HOSE/HNX: nhà phân phối CNTT/thiết bị) | BCTC công khai | Số liệu tổng hợp, không có bút toán | ✅ calibration | Biên lợi nhuận gộp, vòng quay hàng tồn, DSO để bảo đảm DN mẫu không phi thực tế. *Lưu ý bản quyền/điều khoản nguồn dữ liệu; chỉ lấy tỷ số.* |
| **Thống kê doanh nghiệp (Tổng cục Thống kê / sách trắng DNNVV)** | Thống kê | Quy mô, ngành, lao động | ✅ calibration | Phân bố quy mô công ty mẫu khi sinh nhiều DN |
| **Checkbook NYC (chi tiêu công NYC)** | Chi trả NCC thật | ≥ 100k dòng | ⚪ chủ yếu cho Agent 2 | Có thể dùng thử *kiểm thử hiệu năng* của engine ở quy mô lớn (chỉ AP) |
| **MC‑OCR (hóa đơn VN)** | Ảnh hóa đơn | Thuộc Agent 3 | ❌ | Không liên quan lõi chỉ số |
| **ULB Credit Card Fraud** | Giao dịch thẻ | Thuộc Agent 2 | ❌ | Không liên quan Agent 4 |
| **Dữ liệu ERP/kế toán thật của DN** | Sổ cái thật | Không công khai | ✅ *cần xin* | Pilot: chạy engine trên bản ẩn danh để phát hiện lệch giả định (`06`) |

## 2. Chi tiết các nguồn "dùng một phần"

### 2.1 Customer Invoices (Kaggle)
- **Kết quả kiểm tra từ phiên Agent 1** (bản sao công khai, có thể khác bản Kaggle):
  - *Nghiêng về ERP thật*: mã điều khoản thanh toán kiểu SAP với số ngày đến hạn cố định theo mã; chỉ 0,34% ngày thanh toán rơi cuối tuần; danh tính khách giải thích 46,5% phương sai số ngày trễ.
  - *Nghiêng về bị biến đổi*: 1.461 mã khách nhưng 4.292 tên (tên đổi ngẫu nhiên theo dòng); hóa đơn từ 03/2020 gần như đều "chưa đóng" dù trung vị trả chỉ 15 ngày → giống chia theo ngày do người ra đề.
  - Độ trễ ngắn hơn nhiều khảo sát Atradius Việt Nam (P95 ≈ 11 ngày so với ~1 tháng).
- **Kết luận dùng:** gọi là "dữ liệu công nợ có cấu trúc giống ERP, nguồn gốc không xác định" — **không** gọi là dữ liệu thật. Chỉ dùng để *so hình dạng phân phối* (đuôi, hành vi theo khách), **không** dùng để hiệu chỉnh mức trễ tuyệt đối cho Việt Nam.
- **Cách dùng cụ thể:** xem `06` mục "Hiệu chỉnh hành vi thanh toán".

### 2.2 Atradius (khảo sát tập quán thanh toán)
Cho mức trễ trung bình phổ biến của DN VN (~30 ngày nhưng khác nhau theo ngành); dùng làm *neo* cho tham số `late_mean_days` của phân khúc "GOV" và "ENT" (hiện đặt 38 và 18 ngày — **giả định**, cần hiệu chỉnh sau khi lấy số).

### 2.3 Báo cáo tài chính niêm yết
Dùng để kiểm tra: *biên gộp 19%* của DN mẫu có hợp lý so với nhà phân phối lớn (thường thấp hơn, vì quy mô, ít dịch vụ) — DN mẫu là **đại lý giá trị gia tăng (VAR) có dịch vụ biên ~55–60%**, nên biên gộp tổng cao hơn nhà phân phối thuần. Nhóm cần điền khoảng tham chiếu thật.

## 3. Nguồn **không** dùng và lý do
| Nguồn | Lý do loại |
|---|---|
| Dữ liệu chứng khoán, giá cổ phiếu | Ngoài phạm vi (từ chối trong E4) |
| Bộ dữ liệu fraud (ULB…) | Thuộc Agent 2; không giúp đo chọn‑công‑cụ |
| Ảnh hóa đơn (MC‑OCR) | Thuộc Agent 3; Agent 4 làm việc trên sổ cái số |
| Dữ liệu khách hàng thật khi chưa có đồng thuận | Cam kết pháp lý/đạo đức của dự án |

## 4. Quy tắc sử dụng nguồn công khai
1. Ghi **giấy phép & điều khoản** của từng bộ trước khi tải.
2. Chỉ lưu **thống kê tóm tắt** (phân vị, tỷ số) vào repo, **không** commit dữ liệu thô lớn.
3. Mọi tham số lấy từ nguồn ngoài phải có dòng trong `04_quy_tac_sinh_du_lieu.md` ghi nguồn + ngày.
4. Dữ liệu cá nhân (tên, MST, lương) trong dữ liệu mẫu là **hư cấu**.
