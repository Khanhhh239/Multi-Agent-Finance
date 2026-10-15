# Thế giới v4: cách sinh dữ liệu nền

Mã: `agent2/world_v4.py` (lớp `WorldV4`, kế thừa `WorldV3` và `SchemesMixin`). Tham số khởi tạo: `n=200000` dòng, `rate=0.004`, `seed`, `companies=48`, `fraud_company_share=0.55`, `difficulty_weights=(.15,.45,.40)`, `structured_share=0.86`.

## 1. Quy trình sinh (thứ tự)

```
make_masters  → công ty, nhân sự, nhà cung cấp, khách hàng
make_background → quy trình nền (86% số dòng) + dòng "đệm" từ bộ sinh chung (14%)
inject_fraud → vụ gian lận THAY THẾ dòng đệm (khối lượng giữ nguyên)
inject_normal_advances, inject_hard_negatives → tạm ứng bình thường, ca hợp lệ giống gian lận
finalize → bảng kế toán, chứng từ, đồ thị dòng tiền, features, labels, truth_cases
```

Gian lận chiếm chỗ của dòng đệm nên không làm thay đổi tổng số dòng, và mã giao dịch được xáo trộn nên vị trí không lộ nhãn.

## 2. Hồ sơ công ty (ngẫu nhiên hóa)

| Thuộc tính | Phân phối | Vì sao |
|---|---|---|
| Ngành | thương mại .30, bán lẻ .20, sản xuất .20, dịch vụ .20, vận tải .10 | Quy trình khác nhau (bán lẻ có giá vốn, dịch vụ nhiều tiền mặt) |
| Quy mô | siêu nhỏ .40 (10 đến 19 nhân sự), nhỏ .45 (20 đến 45), vừa .15 (46 đến 80) | Khớp phân bố DNNVV |
| Hệ số tiền | `exp(N(0, 0,45)) × {0,6; 1,0; 1,8}` theo quy mô | Quy mô số tiền khác nhau |
| Ngày trả lương | 5, 10, 10, 15, 25, cuối tháng, cuối tháng, hoặc hai kỳ 15 và cuối tháng | Phá thói quen "luôn ngày 28" của v3 |
| Kỳ hạn mua chịu | 15, 30, 30, 45, 60 ngày | |
| Kỳ hạn bán chịu | 30, 30, 45, 45, 60 ngày | |
| Tỷ lệ khách trả đúng hạn | `U(0,45; 0,72)`; nợ xấu `U(0,01; 0,05)` | Hiệu chỉnh Atradius 2025 (58% đúng hạn, 3% nợ xấu) |
| Hạn mức tự duyệt | 1, 2, 2, 3, 5 triệu đồng | |
| Số chứng từ trung bình | `U(1,3; 3,0)` | |
| Chi tiền mặt nhiều | 70% công ty bán lẻ hoặc dịch vụ | Có rút tiền về quỹ hai lần mỗi tháng |
| Ngày thuê nhà, nộp thuế | 1 đến 10; 15 đến 20 | |
| Có vụ gian lận | 55% công ty có (`fraud_mu` từ 1 đến 4), 45% không có | Hơn nửa công ty không có vụ: ngân sách cảnh báo vẫn phát ra, kéo precision gộp xuống |

## 3. Nhân sự
- Vai trò cố định ở vị trí đầu: giám đốc, kế toán trưởng, thủ quỹ, 3 kế toán viên, bán hàng, mua hàng, thủ kho; còn lại chọn ngẫu nhiên (bán hàng .28, mua hàng .08, kho .12, vận hành .49, nhân sự .03).
- Sáu người đầu vào làm 2023-01-01; người còn lại vào làm ngẫu nhiên 2018 đến 2022.
- **Luân chuyển:** 18% nhân sự từ vị trí 10 trở đi nghỉ việc ngẫu nhiên trong khoảng 640 ngày kể từ 2024-02; ngày ghi nhận nghỉ việc trễ 0 đến 10 ngày; người thay thế vào làm sau 7 đến 40 ngày; chấm công về 0 sau khi nghỉ.
- Lương theo vai trò và hệ số công ty; năm 2025 tăng theo `(mã nhân viên mod 9)%`; 30% nhân sự vận hành hoặc kho có thêm 0 đến 15% (làm thêm giờ) mỗi kỳ.

## 4. Nhà cung cấp
- Số lượng `int(nhân sự × U(1,5; 3,5)) + 20`; phân loại: hàng hóa .40, vật tư .20, dịch vụ .25, tiện ích .05, bán lẻ .10; nhà cung cấp số 0 là chủ nhà.
- Trọng số chọn theo `1/(1+j)^0,9 × U(0,6; 1,4)` (một số nhà cung cấp chiếm phần lớn giao dịch).
- Số tiền mỗi lần: lognormal, trung bình `log(8 triệu × hệ số)` cộng `N(0; 0,9)`, độ lệch `U(0,18; 0,35)`.
- 12% nhà cung cấp tăng giá thật 15 đến 30% từ một ngày bất kỳ sau 2024-09 (ca hợp lệ `legit_price_increase`).
- Một số cặp nhà cung cấp có tên "Chi nhánh" của nhau; một số nhà cung cấp là người quen khai báo (`related_party_disclosed_at`).

## 5. Khách hàng
- 8 đến 20 (bán lẻ) hoặc 15 đến 45; hành vi `good` / `late` / `bad` theo hồ sơ công ty; mỗi khách có người phụ trách (nhân viên bán hàng đang làm việc); mỗi 12 khách có một cặp công ty liên kết (khách này trả hộ khách kia, ca hợp lệ `legit_affiliate_payment`).

## 6. Quy trình nền

| Quy trình | Chi tiết |
|---|---|
| Lương | Vào các ngày trả lương của công ty (dời về ngày làm việc), người lập là kế toán, người duyệt là giám đốc; quyết toán nghỉ việc có nhãn hợp lệ; thưởng tháng 1 và 12 (50% công ty) |
| Bán hàng | Hóa đơn bán → (giá vốn nếu thương mại, bán lẻ) → 2% trả hàng có biên bản → thu tiền: khách tốt trả trước hạn 0 đến 10 ngày; khách trễ trả hạn cộng 5 đến 60 ngày; khách xấu và 1% ngẫu nhiên bị xóa nợ sau hạn cộng 180 đến 260 ngày với hồ sơ đối chiếu |
| Mua hàng | Thanh toán sau hóa đơn đúng kỳ hạn cộng `U(-5; 10)` ngày, gom về ngày chạy lệnh cố định của công ty nếu có |
| Chi phí | Thuê nhà, nộp thuế, khấu hao hằng tháng; chi tiền mặt theo hạn mức; rút tiền ngân hàng về quỹ |
| Kho | Hủy hàng hao hụt kiểm kê cuối quý có biên bản (ca hợp lệ) |
| Tạm ứng | Cấp và quyết toán đúng hạn; vài ca gia hạn, xóa nợ có duyệt |
| Dòng đệm (14%) | Giao dịch chung từ bộ sinh gốc để giữ sự đa dạng và để làm "chỗ" cho dòng gian lận |

## 7. Kế toán
- Hai chế độ: Thông tư 133 (DN nhỏ) và Thông tư 200; mỗi giao dịch có cặp tài khoản nợ có, chứng từ nhật ký (`journal_documents`), dòng bút toán (`journal_lines`), thuế GTGT đầu vào và đầu ra, chứng từ liên kết.
- Năm loại bút toán mới trong v4: `sales_return` (Nợ 511 Có 131), `customer_refund` (Nợ 131 Có 112), `bad_debt_writeoff` (Nợ 642 Có 131), `inventory_writeoff` (Nợ 632 Có 156), `cash_withdrawal` (Nợ 111 Có 112) — `agent2/accounting_ext.py`.
- Kiểm tra sổ cân Nợ bằng Có và quy tắc của bạn bạn đã chạy qua `check_accounting_v4`.

## 8. Quy tắc thời gian
Thứ tự `created_at ≤ approved_at ≤ posted_at` trong cửa sổ giai đoạn của dòng; giờ làm việc 8 đến 17 (gian lận mức L0 có thể ngoài giờ); ngày lễ theo lịch minh họa; thứ Bảy làm việc với xác suất thấp hơn.
