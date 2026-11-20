# Agent 3 · Trợ lý Tuân thủ Thuế GTGT

Phân hệ kiểm tra hóa đơn điện tử, đối chiếu chứng từ thanh toán không dùng tiền mặt và tra cứu căn cứ pháp lý thuế GTGT cho doanh nghiệp.

## Cấu trúc thư mục

- **`agent3_tax_compliance/`**: Ứng dụng FastAPI chính đang phục vụ trên nền tảng Sổ Son (cổng `8640`), bao gồm bộ đọc hóa đơn XML/ZIP, đối chiếu sao kê & bảng kê thuế, kho luật `lawbase` và trợ lý hỏi đáp điều khoản luật.

## Chạy trong nền tảng chung (Khuyên dùng)

Từ thư mục gốc repo:

```powershell
.\run_web.ps1
```

Agent 3 tự động đồng bộ mã số thuế và hồ sơ doanh nghiệp từ Portal, hiển thị trực tiếp tại `http://127.0.0.1:8800/#agent3`. Xem chi tiết cấu trúc bên trong tại [agent3_tax_compliance/README.md](agent3_tax_compliance/README.md).
