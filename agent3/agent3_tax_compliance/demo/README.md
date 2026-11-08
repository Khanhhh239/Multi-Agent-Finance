# Demo Agent 3 trong 10 phút

Agent 3 là trợ lý thuế cho doanh nghiệp nhỏ và vừa: rà hóa đơn, sao kê, bảng kê cổng thuế, chỉ ra khoản thuế đầu vào có nguy cơ bị loại, vì sao, theo điều luật nào, nên làm gì. Chạy hoàn toàn trên máy này.

## Bật ứng dụng

Bấm đúp `chay_agent3.bat` (trong thư mục `agent3_tax_compliance`). Trình duyệt mở `http://127.0.0.1:8640`. Cần Ollama đang chạy nếu muốn dùng các phần AI.

## Hai cách demo

| Cách | Khi nào dùng | Làm gì |
|---|---|---|
| **A. Dữ liệu có sẵn** (30 giây) | Cho người xem trước | Ở trang đầu bấm **"Xem thử với dữ liệu mô phỏng"**. Có sẵn doanh nghiệp Vật liệu Xây dựng Minh An: 47 hóa đơn mua vào, 45 giao dịch ngân hàng, 21 việc cần xử lý, thuế có nguy cơ 11.998.000 đồng. |
| **B. Tự nạp từng bước** (10 phút) | Cho người muốn thấy cả quy trình | Làm theo `DN_Phan_mem_Sao_Viet/HUONG_DAN.md`: thiết lập một công ty công nghệ thông tin, thả 6 tệp, xem kết quả. |

## Trong thư mục này

```
agent3_demo/
  README.md                       tệp này
  DN_Phan_mem_Sao_Viet/
    HUONG_DAN.md                  làm gì, nhập gì, phải thấy gì
    A_tha_vao_Nap_nhanh/          6 tệp: chọn hết rồi thả vào Nạp dữ liệu
    B_nhap_o_Quan_tri/            1 tệp: danh sách doanh nghiệp rủi ro
```

Dữ liệu là mô phỏng, không phải doanh nghiệp thật.

Tài liệu đầy đủ (kinh tế, kỹ thuật, hướng dẫn): `agent3_docs/AGENT3_MO_TA_VA_HUONG_DAN.pdf`.
