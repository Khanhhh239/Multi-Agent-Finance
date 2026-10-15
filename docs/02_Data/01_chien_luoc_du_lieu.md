# 1. Chiến lược dữ liệu

## 1.1 Sự thật cần nói thẳng

Khảo sát các cổng mở (chính phủ, học thuật, Kaggle, Zenodo, 4TU, UNU-WIDER, Ngân hàng Thế giới) **không tìm thấy bộ
dữ liệu công khai nào ghi hoá đơn và thanh toán cấp giao dịch của SME Việt Nam** (kết luận của đợt khảo sát, không
phải khẳng định tuyệt đối). Vì vậy dữ liệu của Agent 1 được xây theo ba tầng; mỗi tầng chỉ được dùng cho đúng loại
kết luận.

| Tầng | Nội dung | Mục đích | Được phép kết luận |
|---|---|---|---|
| **1. Thật, tương tự** | BPI 2019, Customer Invoices, SBA 7(a), Berka, Online Retail II | Chứng minh phương pháp trên dữ liệu thật | "Phương pháp chạy tốt trên dữ liệu thật của lĩnh vực gần" — **không** kết luận về SME VN |
| **2. Thống kê thật để hiệu chỉnh** | Atradius VN 2025, UK Payment Practices, OxCGRT VN, WDI VN, JPMorgan Chase Institute, luật VN | Đặt tham số máy phát; kiểm tra độc lập | "Phân phối biên của máy phát khớp số liệu công bố" |
| **3. Tổng hợp có nhãn** | 4 "thế giới" SME VN | Tình huống thật không có: ghi sổ lô, lời hứa, Tết, sốc, điểm gãy, sao kê | "Hệ thống xử lý được tình huống đã chèn" — **không** chứng minh hiệu quả trên DN thật |

Hiệu quả trên DN thật chỉ chứng minh được ở T13 (đối tác thật, chạy song song, có đồng ý theo NĐ 13/2023).

## 1.2 Kết hợp dữ liệu thật và tổng hợp như thế nào

```
                    ┌───────────── Tầng 2: thống kê thật ─────────────┐
                    │ Atradius VN · UK PPR · OxCGRT · WDI · luật VN   │
                    └────────────┬────────────────────────────────────┘
                                 │ hiệu chỉnh tham số (vòng lặp tự động)
                                 ▼
  Tầng 1 (thật) ◄────────── MÁY PHÁT ──────────► Tầng 3 (4 thế giới tổng hợp)
  chứng minh phương pháp      (T12)               src · tgt · sens_uk · sens_coface
        │                                                  │
        └──────────── dùng chung đặc trưng & mô hình ──────┘
              (đặc trưng bất biến miền: ngày tương đối hạn, tiền tương đối trung vị công ty)
```

Bốn cách tổng hợp và thật cùng xuất hiện trong thí nghiệm:

1. **Tiền huấn luyện tổng hợp → tinh chỉnh dữ liệu thật/đích** (fine-tune, gộp có trọng số, trọng số tỷ lệ mật độ).
2. **Huấn luyện trên tổng hợp, kiểm tra trên thật** (chuyển giao zero-shot) và **ngược lại**: nếu kết quả sụt mạnh thì
   máy phát thiếu cấu trúc — phải công bố kể cả khi xấu.
3. **Kiểm định độc lập**: dấu hiệu cấu trúc (trả cuối tuần, Benford, độ bền khách, tập trung khách) của tổng hợp so với
   bộ AR giống ERP thật — chưa dùng để chỉnh.
4. **Dùng riêng từng mảnh thật cho từng bài toán** (SBA cho T2, Online Retail cho T4, Berka cho T6/T7, BPI cho T1 P2P).

## 1.3 Hai quy tắc chống ảo tưởng

1. **Không kiểm định máy phát bằng chính số liệu đã dùng để chỉnh.** Tái tạo 58/39/3% (Atradius) chỉ chứng minh máy
   phát chạy đúng. Bằng chứng độ trung thực phải đến từ nguồn độc lập (UK PPR, bộ AR ERP, SBA, Berka).
2. **Tách ba loại kết luận** (phương pháp / chịu nhiễu / hiệu quả thật). Báo cáo luôn ghi loại nào.

## 1.4 Nguyên tắc kỹ thuật dữ liệu

| Nguyên tắc | Thực thi |
|---|---|
| Chống rò rỉ tương lai | Mọi đặc trưng tính *as-of ngày cắt T*; nhãn bị kiểm duyệt tại ngày cuối quan sát; train/cal/test tách rời theo thời gian |
| Nhãn đúng trước mô hình đúng | Ngày trả = ngày tiền về ngân hàng (không phải ngày ghi sổ); có cả cột `ledger_clear_date` để đo tác hại |
| Truy vết | `data/raw/MANIFEST.json` (URL, ngày tải, kích thước, SHA-256, giấy phép); `config.json` + seed cho mỗi thế giới |
| Đơn vị bất biến | Tiền chia trung vị công ty; ngày tương đối hạn; để chạy cho VND/USD/EUR |
| Niêm phong miền đích | `tgt` dùng seed và tham số riêng; không dùng để chọn siêu tham số của nguồn |
| Nhật ký giả định | Mọi tham số không có nguồn ghi "giả định" trong `04_may_phat_tong_hop.md` |

## 1.5 Lược đồ chuẩn (T0) — một nguồn, hai góc nhìn

Bảng chuẩn dùng chung cho dữ liệu thật và tổng hợp (cột tối thiểu):

| Bảng | Khoá | Cột chính |
|---|---|---|
| `invoices` | `invoice_id` | `firm_id, customer_id, symbol, invoice_no, issue_date, due_date, term_days, amount_net, vat_rate, amount_gross, credit_note, currency` + nhãn: `paid_date_true, first_payment_date, ledger_clear_date, paid_amount, n_payments, is_bad_debt, writeoff_date, dispute, partial` |
| `payments` | `payment_id` | `invoice_id, ledger_invoice_id, txn_id, pay_date_true, ledger_post_date, amount, kind (full/partial/final/recovery)` |
| `bank_txns` | `txn_id` | `firm_id, value_date, amount, direction, counterparty, memo, txn_type, true_customer_id, fee_deducted` |
| `promises` | — | `invoice_id, customer_id, made_date, promised_date, kept` |
| `outflows` | — | `firm_id, date, category, amount, known_in_advance` |
| `customers`/`firms` | `customer_id`/`firm_id` | thuộc tính hành vi *tiềm ẩn* (nhãn gốc) + thuộc tính quan sát được (tên, MST) |
| `events` | — | điểm gãy và vỡ nợ đã chèn (nhãn T7) |
| `macro` | `week` | `common_factor, covid_stress, credit_crunch` |
| `daily_cash` | `firm_id, date` | số dư "không can thiệp" thật (nhãn T6) |
