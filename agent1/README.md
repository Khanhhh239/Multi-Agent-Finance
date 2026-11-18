# Agent 1 · Quản trị & Dự báo Dòng tiền

Phân hệ dự báo dòng tiền doanh nghiệp theo tuần (1–52 tuần, mặc định 13 tuần), đối soát hóa đơn – sao kê ngân hàng, phân tích kịch bản thu chậm và xuất báo cáo Excel.

## Chức năng chính

- **Tiếp nhận & Đối soát (`T0` / `T9`)**: Chuẩn hóa 6 nguồn dữ liệu (hóa đơn bán, tiền khách trả, dòng sao kê ngân hàng, kỳ sao kê, lịch chi cố định `T5` và lịch sử nhắc nợ).
- **Mô hình thu hồi công nợ (`T1`)**: Kết hợp catalog toàn cục (`outputs/t1/settlement_partial_catalog_v3_20261114/catalog.json`) và học thích nghi theo doanh nghiệp cho cả thanh toán đủ lẫn thanh toán từng phần.
- **Dự báo & Giải thích (`T6` / `T10`)**: Dự báo phân phối dòng tiền ròng (`P10` / `P50` / `P90`), cảnh báo nguy cơ thiếu hụt tiền mặt và truy xuất bằng chứng từng khoản mục.

## Chạy trong nền tảng chung (Khuyên dùng)

Từ thư mục gốc repo:

```powershell
.\run_web.ps1
```

Agent 1 chạy tại cổng `8011` và được nhúng tự động tại `http://127.0.0.1:8800/#agent1` (tự nhận khóa truy cập và định dạng ngày/số tiền từ hồ sơ doanh nghiệp trên Portal).

## Chạy độc lập & Kiểm thử

```powershell
# Chạy dịch vụ độc lập
.\agent1\scripts\start-business.ps1 -Port 8011 -Company SME

# Chạy kiểm thử tự động
.\agent1\.venv\Scripts\python.exe -m pytest agent1/tests -q
```
