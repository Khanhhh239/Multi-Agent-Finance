Nếu sử dụng luôn API bên thứ 3 kết hợp giữa lấy ERP và Reconcile bank transactions luôn thì có Xero https://digita.vn/services/xero/ với giá 700k tới 2 triệu, QuickBook https://quickbooks.com.vn/bang-gia với giá 1 triệu 2 tới 10 triệu -> xem xét tự build dự trên các adapter


Ở đây vấn đề là dữ liệu phân mảnh, đối soát thủ công và sự
khác nhau giữa các sổ sách


# Architecture


Vậy ta sẽ dùng `Medallion Architecture`
```
┌─────────────────────────────────────────────────────────────┐
│ SOURCES                                                      │
│  ERP (MISA/FAST) ─┬─ Bank API/JetPay ─┬─ CSV/Excel upload   │
└───────────────────┼───────────────────┼─────────────────────┘
                    ▼                   ▼
           ┌───────────────────────────────────┐
           │ BRONZE (Raw) — ELT, append-only   │  ← giữ nguyên raw
           │ raw_invoices, raw_bank_txns       │
           └──────────────┬────────────────────┘
                          ▼  dbt / GX tests
           ┌───────────────────────────────────┐
           │ SILVER (Cleaned, Normalized)      │  ← event-sourced, SCD2
           │ invoices, payments,               │
           │ bank_transactions, allocations    │
           │ + reconciliation engine           │
           └──────────────┬────────────────────┘
                          ▼  dbt marts
           ┌───────────────────────────────────┐
           │ GOLD (Star Schema)                │  ← fct_* + dim_*
           │ fct_invoices, dim_customer (SCD2) │
           └──────────────┬────────────────────┘
                          ▼
                Forecast (T1–T6) + Dashboard
```


Ở đây từ các source ERP (nghiệp vụ kinh tế), Bank API/JetPay(dòng tiền thực), và CSV/Excel (các khoản mục điều chỉnh thủ công)


## Tầng Bronze
Ở đây thì ta sẽ đẩy thẳng vào data lake từ source và không đi qua bước xử lí nào cả, xem các nguồn là raw
Giữ raw để đảm bảo tầng này là source of truth -> lỗi các tầng sau thì chỉ cần chạy lại pipeline
## Tầng Sliver
Event-sourced và SCD2: lưu toàn bộ trạng thái của hóa đơn hay giao dịch để có thể đứng từ mọi thời điểm
Sử dụng dbt(biến đổi dữ liệu, theo dõi logic)/GX tests(automate test) để xử lí dữ liệu
Sau đó dùng reconciliation để kết nối giữa giao dịch và hóa đơn
## Tầng Gold
Dùng star schema để trình bày CEO/CFO, DA, và làm nguồn cho các thuật toán phía sau
Ở đây không còn các phép tính toán


# ERD
```
customers 1──N invoices 1──N invoice_lines
    │              │
    │              ├──N payment_allocations N──1 payments
    │              │                              │
    │              │                    bank_transactions (khớp qua reconciliation, KHÔNG FK trực tiếp)
    │              └──N── credit_terms
    └──1──N customer_payment_history


fixed_obligations (độc lập)
bank_accounts 1──N bank_transactions
```


# SCD Type 2
Dữ liệu khách hàng không đứng yên. Giả sử công ty A có hạn mức nợ 500 triệu và do mua sắm tốt và trả nợ đúng -> được lên hạn mức 1 tỉ -> việc thay thế sẽ làm cho các thuật toán sau này hiểu nhầm lúc thời điểm trước A cũng có hạn mức 1 tỉ
Sử dụng valid from và valid to để khoanh vùng thời điểm


# ERP
MISA: https://developer.misa.vn/products-openapi
Free tích hợp nếu sử dụng chuẩn theo Open API


# Bank API
Hiện bank không cung cấp cho SME API để lấy hóa đơn -> Cần qua bên thứ 3 để truy cập -> Sử dụng Jetpay BankHub trong hệ sinh thái MISA


# Reconciliation
```
Exact → Window → Fuzzy (auto nếu > upper, manual nếu ở giữa)
  → Optimal assignment cho phần còn lại (batch cuối ngày)
    → Manual review cho unmatched
```



