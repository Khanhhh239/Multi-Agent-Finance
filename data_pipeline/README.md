# Data Pipeline — Bộ dữ liệu Minh Phát (MPX10) & Đồng bộ Runtime

Thư mục `data_pipeline/` sinh kho dữ liệu kế toán tổng hợp **Minh Phát (`MPX10`, MST `0999999905`)** nhất quán cho cả 4 Agent và tự động đồng bộ cấu hình vận hành của toàn nền tảng.

## Tóm tắt quy mô dữ liệu đầy đủ (Seed `20261108`)

- **Kỳ dữ liệu**: Số dư đầu kỳ `31/12/2022`, phát sinh từ `01/01/2023` đến `14/10/2026`, khóa sổ đến hết `08/2026`.
- **Agent 4 (`warehouse.duckdb`)**: ~19,78 triệu dòng sổ cái, 5,11 triệu bút toán, 1,30 triệu hóa đơn bán, 184 nghìn hóa đơn mua.
- **Agent 1 (`inputs/a1/`)**: Hóa đơn bán, tiền khách trả, sao kê ngân hàng, kỳ sao kê, lịch chi cố định và lịch sử nhắc nợ.
- **Agent 2 (`inputs/a2/`)**: 10.000 bút toán giao dịch gần nhất kèm danh mục doanh nghiệp, đối tác, nhân sự và chứng từ.
- **Agent 3 (`inputs/a3/`)**: Hóa đơn điện tử XML mua vào / bán ra, sao kê ngân hàng và bảng kê mua vào.

## Cách chạy nhanh nhất

Từ thư mục gốc dự án:

```powershell
# Chế độ nhanh: dùng kho sẵn có / giải nén kho mẫu + tạo gói nạp thử + khởi tạo mô hình Agent 2
.\create_data.ps1

# Chế độ đầy đủ: sinh mới toàn bộ kho 4 năm + kiểm định kế toán + xuất tệp cho cả 4 Agent
.\create_data.ps1 -Full
```

## Các tệp chính trong `data_pipeline/`

| Tệp | Chức năng |
|---|---|
| `setup_runtime.py` | Điều phối tự động: kiểm tra/sinh kho DuckDB, tạo gói `mpx10-demo-input-full`, đồng bộ `portal/config.local.json`, `company.json`, `agent2_access.json` và huấn luyện sẵn mô hình địa phương cho Agent 2 |
| `enterprise.py` | Sinh kho dữ liệu doanh nghiệp DuckDB (`--smoke` cho bản nhỏ, mặc định cho bản đầy đủ) |
| `validate.py` | Đối soát phương trình kế toán, công nợ, tồn kho, khóa ngoại và tạo `validation.json` |
| `export.py` | Trích xuất các bảng CSV và gói hóa đơn XML chuẩn hóa từ kho DuckDB sang định dạng của Agent 1, 2, 3 |
| `demo_inputs.py` | Đóng gói bộ 4 tệp gọn nhẹ (`01_invoices.csv`, `02_sao_ke_chung.csv`, `03_transactions.csv`, `04_hoa_don.zip`) để trình diễn nạp chung qua Portal |
| `stage.py` | Công cụ kiểm chứng nạp trực tiếp vào kho riêng của từng Agent |
