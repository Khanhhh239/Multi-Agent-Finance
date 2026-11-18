# Sổ Son — Văn phòng Kế toán số Đa tác tử (Multi-Agent Finance)

Nền tảng kế toán số tích hợp **4 Agent chuyên biệt** trong một giao diện web thống nhất (**Portal**): dùng chung một hồ sơ doanh nghiệp, một cổng tiếp nhận & niêm phong chứng từ, một ngôn ngữ thiết kế và một quy trình tạo dữ liệu đồng bộ.

## Kiến trúc hệ thống

| Thành phần | Thư mục | Cổng | Chức năng chính |
|---|---|---|---|
| **Portal (Web chung)** | `portal/` | `8800` | Quản lý hồ sơ doanh nghiệp, mở khóa mật khẩu / FaceID, phân luồng & niêm phong chứng từ, nhúng đồng bộ 4 Agent |
| **Agent 1 · Dòng tiền** | `agent1/` | `8011` | Đối soát công nợ – ngân hàng, dự báo thu chi 13–52 tuần theo kịch bản, xuất báo cáo Excel |
| **Agent 2 · Soát giao dịch** | `agent2/` | `8766` | Rà soát giao dịch bất thường kết hợp 4 nhánh: bộ 35 luật, thống kê (`RobustZ`), đồ thị quan hệ và ML (`Isolation Forest` / `ECOD`) |
| **Agent 3 · Thuế GTGT** | `agent3/` | `8640` | Đọc hóa đơn điện tử XML/ZIP, đối chiếu sao kê ngân hàng & bảng kê thuế, tra cứu căn cứ điều luật thuế GTGT |
| **Agent 4 · Hỏi đáp CFO** | `agent4/`, `agent4_chat/` | `8040` | Chuyển câu hỏi tiếng Việt thành truy vấn được kiểm soát trên kho sổ cái DuckDB chỉ đọc, giải thích nguồn minh bạch |
| **Data Pipeline** | `data_pipeline/` | — | Sinh kho dữ liệu doanh nghiệp mô phỏng **Minh Phát (MPX10)** đồng bộ xuyên suốt cả 4 Agent |
| **Giao diện chung** | `design/` | — | Bộ token giao diện Sổ Son & phông chữ *Be Vietnam Pro* đồng bộ cho Portal và 4 Agent (`python design/sync.py`) |

---

## Chạy nhanh bằng 1 lệnh duy nhất

Từ thư mục gốc dự án trên Windows PowerShell:

```powershell
.\run_web.ps1
```

*(Hoặc nhấp đúp trực tiếp vào tệp **`run_web.bat`** trong Windows Explorer).*

Lệnh `.\run_web.ps1` tự động thực hiện trọn gói:
1. Giải phóng các tiến trình cũ nếu đang chiếm cổng `8800`, `8011`, `8766`, `8640`, `8040`.
2. Khởi động dịch vụ **Ollama** nền (nếu đã cài mà chưa bật).
3. Đồng bộ cấu hình `portal/config.local.json`, hồ sơ doanh nghiệp mẫu **MPX10**, kho DuckDB của Agent 4 và mô hình phân tích của Agent 2.
4. Bật **Portal** cùng toàn bộ **4 Agent** và tự mở trình duyệt tại **http://127.0.0.1:8800**.

> Xem hướng dẫn thao tác chi tiết từng bước tại **[HUONG_DAN_CHAY_WEB.md](HUONG_DAN_CHAY_WEB.md)**.

---

## Các lệnh tiện ích chính

| Nhu cầu | Lệnh duy nhất |
|---|---|
| **Bật web + 4 Agent** | `.\run_web.ps1` *(hoặc mở `run_web.bat`)* |
| **Dừng toàn bộ hệ thống** | `.\run_web.ps1 -StopOnly` *(hoặc nhấn `Ctrl+C` tại cửa sổ đang chạy)* |
| **Tạo / đồng bộ nhanh dữ liệu & mô hình** | `.\create_data.ps1` |
| **Sinh mới toàn bộ kho dữ liệu 4 năm (MPX10)** | `.\create_data.ps1 -Full` |
| **Cài đặt môi trường từ đầu trên máy mới** | `.\setup_all.ps1` |

---

## Luồng sử dụng trên Web (`http://127.0.0.1:8800`)

1. **Hồ sơ doanh nghiệp (`#config`)**: Kiểm tra hoặc cập nhật mã đơn vị (mặc định `MPX10`), tên pháp lý, mã số thuế (`0999999905`), kỳ kê khai và định dạng ngày/số tiền.
2. **Nạp dữ liệu chung (`#data`)**:
   - Đặt mật khẩu quản trị lần đầu (tối thiểu 8 ký tự; tùy chọn đăng ký mở khóa khuôn mặt **FaceID AI 128 chiều**).
   - Kéo thả chứng từ vào ô tiếp nhận (ví dụ trọn bộ 4 tệp mẫu trong `portal/workspace/mpx10-demo-input-full/`):
     - `01_invoices.csv` → **Agent 1** (hóa đơn bán & công nợ).
     - `02_sao_ke_chung.csv` → **Agent 1 & Agent 3** (một tệp sao kê tự động chuẩn hóa cho cả dòng tiền và thuế GTGT).
     - `03_transactions.csv` *(hoặc `.xlsx`, `.json`)* → **Agent 2** (tạo snapshot giao dịch bất biến để soát xét).
     - `04_hoa_don.zip` *(hoặc `.xml`)* → **Agent 3** (tự động phân loại hóa đơn mua vào / bán ra).
   - Kiểm tra kết quả xem trước và bấm **Ghi toàn bộ dữ liệu** để niêm phong phiên bản gói chứng từ kèm chuỗi băm nhật ký SHA-256.
3. **Làm việc trên 4 phân hệ (`#agent1` → `#agent4`)**: Chuyển mượt mà giữa 4 Agent ngay trên thanh điều hướng bên trái hoặc mở sang tab riêng khi cần.

## Lưu ý bảo mật & phạm vi dữ liệu

- Toàn bộ số liệu đi kèm (`MPX10`, `C001`, `C002`, `Đại Phát`, `Sao Việt`) là **dữ liệu mô phỏng** phục vụ kiểm thử và trình diễn kỹ thuật.
- Hệ thống mặc định chỉ lắng nghe trên `127.0.0.1` (cục bộ), dữ liệu không rời khỏi máy của doanh nghiệp. Khi triển khai lên máy chủ tập trung, tham khảo thêm [docs/DEPLOY_SERVER.md](docs/DEPLOY_SERVER.md).
