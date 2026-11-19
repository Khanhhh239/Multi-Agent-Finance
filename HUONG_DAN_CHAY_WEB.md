# Hướng dẫn Chạy Web, Tạo Dữ liệu và Sử dụng 4 Agent

Tài liệu này gom toàn bộ thao tác cài đặt, tạo dữ liệu và khởi chạy hệ thống **Sổ Son (Multi-Agent Finance)** thành các lệnh đơn giản nhất.

---

## 1. Bật Web và cả 4 Agent ngay (1 lệnh duy nhất)

Mở **PowerShell** tại thư mục gốc dự án và chạy:

```powershell
.\run_web.ps1
```

Hoặc nhấp đúp trực tiếp vào tệp **`run_web.bat`** trong thư mục dự án.

### Hệ thống sẽ tự động làm gì?
- Tự dọn các tiến trình cũ nếu cổng `8800`, `8011`, `8766`, `8640`, `8040` đang bận.
- Không tự khởi chạy mô hình cục bộ; Agent 4 dùng provider API đã cấu hình.
- Tự đồng bộ `portal/config.local.json`, hồ sơ doanh nghiệp mẫu **Minh Phát (`MPX10`, MST `0999999905`)**, kho dữ liệu DuckDB cho **Agent 4** và các mô hình thống kê/ML cho **Agent 2**.
- Khởi động **Portal** cùng **Agent 1, 2, 3, 4** và tự mở trình duyệt tại: **http://127.0.0.1:8800**

> **Cách tắt hệ thống:** Nhấn `Ctrl + C` tại cửa sổ PowerShell đang chạy, hoặc chạy lệnh `.\run_web.ps1 -StopOnly`.

### Chế độ API key cho Agent 3 và Agent 4

Portal tự đọc các tệp `.env` bị git bỏ qua tại `agent3/.env` và `agent4/.env` khi khởi động agent. Agent 4 yêu cầu đồng thời `AGENT4_LLM_API_KEY` và `AGENT4_EMBED_API_KEY`, luôn dùng `config/selection.yaml` và không có fallback cục bộ. Agent 3 dùng LLM OpenAI-compatible, embedding API và Cohere reranker theo cấu hình trong `agent3/.env`. Không cần ghi secret vào `portal/config.local.json`.

---

## 2. Tạo và đồng bộ dữ liệu (1 lệnh duy nhất)

### Chế độ nhanh (khuyên dùng hằng ngày — vài giây)
Giải nén kho dữ liệu có sẵn (hoặc dùng kho đầy đủ nếu đã sinh), trích xuất gói chứng từ mẫu và khởi tạo mô hình cho các Agent:

```powershell
.\create_data.ps1
```

### Chế độ sinh mới toàn bộ quy mô lớn (khoảng 3–5 phút)
Sinh mới từ đầu toàn bộ kho dữ liệu doanh nghiệp **Minh Phát (MPX10)** giai đoạn 2023–2026 (~19,7 triệu dòng sổ cái DuckDB, hóa đơn điện tử XML, sao kê ngân hàng, sổ giao dịch), kiểm định đối soát kế toán và đóng gói tệp nạp thử:

```powershell
.\create_data.ps1 -Full
```

Sau khi chạy xong, bộ chứng từ chuẩn để kiểm thử toàn bộ tính năng nằm sẵn tại:
- `DATA_TEST_SAN_SANG\` (9 tệp chuẩn nạp chung 4 Agent + 2 tệp bổ sung kỳ mới + 3 tệp chuyên sâu Agent 2/3)
- `portal\workspace\mpx10-demo-input-full\`

> **Đặt lại trạng thái nạp chứng từ về ban đầu (mật khẩu chuẩn `SoSon@2026`):** Chạy `.\reset_data_intake.ps1`.

---

## 3. Cài đặt trên máy mới tinh (chỉ làm 1 lần)

Yêu cầu máy cài sẵn **Python 3.12+** (khuyến nghị có `uv`). Agent 4 không yêu cầu cài mô hình cục bộ.

Trên Windows chạy:

```powershell
.\setup_all.ps1
```

Lệnh sẽ tạo 4 môi trường `.venv` lõi, đồng bộ kho văn bản luật thuế và chuẩn bị dữ liệu. Các model local nặng được bỏ qua vì Agent 3/4 đang dùng API key.

Nếu cần fallback local cho Agent 3, cài thêm Torch bản CPU và reranker:

```powershell
.\setup_all.ps1
```

Trên Linux có thể dùng:

```bash
bash setup_demo.sh
```

---

## 4. Kịch bản trải nghiệm trọn vẹn trên Web

1. **Tổng quan (`http://127.0.0.1:8800/#overview`)**
   - Kiểm tra trạng thái **4/4 Agent sẵn sàng** (từ lúc chạy `run_web.bat` đến khi cả 4 Agent sẵn sàng mất khoảng 1 phút, đo được 63 giây trên máy GPU 6 GB).

2. **Hồ sơ doanh nghiệp (`#config`)**
   - Hồ sơ mặc định đã điền sẵn **Công ty CP Phân phối và Dịch vụ Minh Phát (`MPX10`)**, MST **`0999999905`**, định dạng ngày `yyyy-mm-dd` (`iso`) và số tiền `plain`.

3. **Nạp dữ liệu chung (`#data`)**
   - Mở khóa bằng mật khẩu quản trị (lần đầu tiên sử dụng, nhập mật khẩu tối thiểu 8 ký tự để thiết lập; nếu quên mật khẩu khi thử nghiệm cục bộ, xóa tệp `portal/workspace/intake_security.json` rồi tải lại trang).
   - Chọn cùng lúc cả **4 tệp** trong thư mục `portal\workspace\mpx10-demo-input-full\`:
     - `01_invoices.csv` → **Agent 1** nhận hóa đơn bán.
     - `02_sao_ke_chung.csv` → **Sao kê dùng chung**, tự chuẩn hóa đồng thời cho cả **Agent 1** và **Agent 3**.
     - `03_transactions.csv` → **Agent 2** kiểm tra hợp đồng dữ liệu và chuẩn bị snapshot giao dịch ngân hàng.
     - `04_hoa_don.zip` → **Agent 3** giải nén và phân loại hóa đơn điện tử XML mua vào / bán ra.
   - Bấm **Xác nhận và tiếp tục** → **Ghi toàn bộ dữ liệu** (bấm xác nhận lần 2 khi có tệp Agent 2) để niêm phong gói chứng từ.

4. **Kiểm tra trên từng Agent**
   - **Agent 1 — Quản trị Dòng tiền (`#agent1`)**: Xem dữ liệu hóa đơn/sao kê đã đối soát, chạy dự báo dòng tiền 13 tuần và xuất báo cáo Excel.
   - **Agent 2 — Soát xét Giao dịch (`#agent2`)**: Doanh nghiệp `MPX10` (hoặc `C001`, `C002`) tự động đồng bộ theo phiên Portal; chọn snapshot vừa lưu hoặc tải mẫu để chạy phân tích 4 nhánh (Luật, Thống kê, Đồ thị, ML).
   - **Agent 3 — Tuân thủ Thuế GTGT (`#agent3`)**: Tự động mở đúng không gian MST `0999999905`; bấm phân tích để đối chiếu hóa đơn XML với sao kê ngân hàng và hỏi đáp điều khoản luật thuế.
   - **Agent 4 — Trợ lý CFO & Sổ cái (`#agent4`)**: Bấm câu hỏi gợi ý như *"Doanh thu thuần quý 3 năm 2026 là bao nhiêu?"* (kết quả kho MPX10 đầy đủ: **3.447.235.086.468 đồng**) và mở mục **Kiểm tra nguồn** để đối chiếu chỉ tiêu, kỳ dữ liệu và sổ quản trị/thuế.

---

## 5. Xử lý nhanh sự cố thường gặp

- **Báo cổng đang bận (`8800` / `8011` / `8766` / `8640` / `8040`)**: Chỉ cần chạy lại `.\run_web.ps1`, script sẽ tự động dọn sạch tiến trình cũ trước khi bật mới.
- **Quên mật khẩu mở khóa Nạp dữ liệu**: Xóa tệp `portal\workspace\intake_security.json`, tải lại trang `#data` để đặt mật khẩu mới.
- **Dùng FaceID trên trình duyệt**: Chuẩn camera trình duyệt yêu cầu mở qua địa chỉ `http://localhost:8800` thay vì IP `127.0.0.1:8800` (giao diện sẽ tự gợi ý chuyển hướng khi bấm nút FaceID).


## Mã hóa đồng cấu (HE) — tự thiết lập

`run_web.bat` tự gọi `scripts/setup_he.py` ở lần chạy đầu (sau đó bỏ qua). Script này, trên chính máy chạy:
cài TenSEAL; cài WSL Ubuntu-24.04 nếu thiếu (lần đầu có thể cần khởi động lại Windows rồi chạy lại); dựng `/opt/he4-venv` (Python 3.12, torch CPU, Concrete-Python 2.11.0);
biên dịch các mạch TFHE vào `.runtime/he4`; sinh khóa node/worker (Windows DPAPI, riêng từng máy), dữ liệu mô phỏng C001/C002, cấu hình Portal;
kích hoạt hàng đợi điều tra, mô hình và gói phát hành. Không có khóa hay bản dựng nào nằm trong git. Làm lại từ đầu: xóa `.runtime/he-ready.json` rồi chạy lại.
Giao diện Agent 2 luôn là bản "Hàng đợi & điều tra" và "Huấn luyện & mô hình"; trang cũ (index/workspace) đã bị xóa.

## Agent 2 — Phân tích, huấn luyện và máy trạm huấn luyện mã hóa

`run_web.bat` bật luôn máy trạm huấn luyện ở **http://127.0.0.1:8890** cùng web chung 8800. Muốn bật riêng máy trạm (khi web chung đã chạy):

```
agent2\.venv\Scripts\python.exe station\server.py --port 8890
```

Máy trạm gọi backend Agent 2 qua cổng nội bộ 8766 bằng khóa trạm tự sinh (`agent2/.runtime/station-secret.txt`), nên cần bật web chung trước.

**1. Phân tích rủi ro (tab Tổng quan)**
- Nạp gói 9 tệp ở "Nạp dữ liệu" (tệp `07_so_giao_dich_ngan_hang_A2.csv` được giữ đủ cột để chạy luật).
- Lần đầu: vào tab "Huấn luyện & mô hình", bước 2, bấm chọn **tất cả** tệp trong `DATA_TEST_MAF_SOSON\input-A2-training` rồi "Bắt đầu huấn luyện", sau đó phê duyệt ở bước 3.
- Về tab "Tổng quan", bấm "Phân tích dữ liệu mới nhất". Điểm gồm luật, thống kê, đồ thị, ML không nhãn; mô hình có nhãn chỉ tham gia khi doanh nghiệp đã đồng bộ mô hình chung.

**2. Đóng góp huấn luyện chung (3 doanh nghiệp)** — làm theo `DATA_TEST_MAF_SOSON\input-A2-dong-gop\00_HUONG_DAN.txt`:
- Mỗi doanh nghiệp (MPX10, C001, C002): tab "Đóng góp huấn luyện" → chọn tệp CSV của mình → "Mã hóa và gửi lên trạm".
  Dữ liệu được mã hóa CKKS bằng khóa riêng của doanh nghiệp (khóa nằm ở `agent2/.runtime/.../he-training-companies/<mã DN>`); trạm chỉ nhận bản mã và nhãn.
- Mở máy trạm 8890 → thấy các doanh nghiệp "Đã gửi" → "Huấn luyện trên dữ liệu đã mã hóa". Trạm tính gradient trên bản mã, mỗi doanh nghiệp chỉ giải mã tổng gradient của mình; kiểm định trên 10% dữ liệu giữ lại; chỉ cập nhật phiên bản trọng số khi tốt hơn (ngưỡng chọn để recall ≥ 90%).
- Quay lại từng doanh nghiệp → "Đồng bộ mô hình về doanh nghiệp" → bấm Phân tích lại ở tab Tổng quan.

Sinh lại dữ liệu demo: `python scripts/make_a2_training_input.py <thư mục> MPX10` và `python scripts/make_a2_contribution_input.py <thư mục>`.
