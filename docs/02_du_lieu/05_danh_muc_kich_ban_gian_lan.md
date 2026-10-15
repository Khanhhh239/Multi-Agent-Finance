# Danh mục kịch bản gian lận (37)

Mã: `agent2/world_v4_schemes.py` (30 kịch bản phát triển, `SCHEMES`) và `agent2/world_v4_sealed.py` (7 kịch bản niêm phong, `NOVEL`). "Trọng số" là xác suất chọn kịch bản khi sinh thêm vụ sau khi mỗi kịch bản đã có mặt ở cả ba giai đoạn. Nhánh theo cây gian lận ACFE.

## 1. Mỗi vụ gian lận có những thuộc tính

| Thuộc tính | Cách chọn | Nguồn |
|---|---|---|
| Người thực hiện | Cấp: nhân viên .37, quản lý .41, chủ hoặc lãnh đạo .19 (chọn trong số vai trò phù hợp kịch bản); vai trò theo kịch bản | ACFE 2024 [Đ] |
| Thông đồng | Một người .46, hai .18, từ ba .36 (thực tế sinh .54 có đồng phạm) | ACFE 2024 [Đ] |
| Mức che giấu | L0 .15, L1 .45, L2 .40 | ACFE: 89% có che giấu [Đ]; tỷ lệ L1 và L2 là [G] |
| Thời gian vụ | Nhân viên 30 đến 110 ngày, quản lý 45 đến 150, lãnh đạo 60 đến 170 | [G]: **nén** so với ACFE (8, 18, 24 tháng) để vừa cửa sổ 6 đến 12 tháng |
| Quy mô số tiền | `8 triệu × hệ số công ty × {1; 2,2; 4,5}` theo cấp × `U(0,6; 1,6)` | [G] |
| Giai đoạn | Một vụ nằm trọn trong huấn luyện, kiểm định hoặc kiểm thử | Nguyên tắc P8 |

## 2. Kịch bản phát triển (30)

| Kịch bản | Nhánh ACFE | Trọng số | Vai trò thực hiện | Mô tả và nguồn gốc |
|---|---|---:|---|---|
| shell_vendor | billing | .10 | kế toán, KTT, mua hàng | Nhà cung cấp ma nhận tiền; L0 trùng tài khoản nhân viên, L1 trùng địa chỉ hoặc điện thoại, L2 nhà cung cấp cũ không trùng |
| invoice_mill | billing | .06 | KTT, giám đốc | Mua hóa đơn của doanh nghiệp ma rồi rút tiền |
| overbilling_excess_payment | billing | .05 | kế toán, KTT | Chi thêm sau khi ký duyệt (vụ DTC) |
| personal_purchase | billing | .04 | giám đốc, KTT, mua hàng | Mua đồ cá nhân bằng tiền công ty |
| split_payments | billing | .05 | kế toán, KTT, mua hàng | Chia nhỏ khoản chi né hạn mức duyệt |
| vendor_burst | billing | .02 | kế toán | Nhiều khoản chi nhiều nhà cung cấp trong một buổi tối |
| duplicate_payment | payment_tampering | .04 | kế toán, KTT | Thanh toán lại hóa đơn đã trả: L0 giống hệt, L1 số hóa đơn mới, L2 số mới cộng lệch tiền (vụ Khải Đệ) |
| altered_payee | payment_tampering | .07 | kế toán, thủ quỹ, KTT | Đổi người nhận trên lệnh chi |
| bank_detail_switch | payment_tampering | .05 | kế toán, KTT | Đổi tài khoản nhà cung cấp, chi, đổi lại |
| ghost_employee | payroll | .04 | KTT, nhân sự, kế toán | Nhân sự ma; L2 có chấm công giả |
| payroll_padding | payroll | .04 | KTT, nhân sự, kế toán | Nâng khống lương một người: L0 1,3 đến 2,0 lần, L2 1,06 đến 1,15 |
| terminated_still_paid | payroll | .03 | nhân sự, KTT, kế toán | Người đã nghỉ vẫn có lương |
| fake_bonus_list | payroll | .03 | nhân sự, KTT | Danh sách chi thưởng khống (vụ 770 triệu) |
| off_cycle_payroll | payroll | .02 | kế toán, KTT | Chi lương ngoài kỳ cho người quen |
| expense_fictitious | expense | .07 | bán hàng, vận hành, mua hàng | Chứng từ tiếp khách, suất ăn khống (vụ Bắc Ninh 1,1 tỷ) |
| expense_padding | expense | .05 | kế toán, thủ quỹ | Chi tiền mặt sát hạn mức tự duyệt |
| expense_duplicate_claim | expense | .04 | bán hàng, vận hành, mua hàng | Nộp trùng chứng từ |
| advance_unsettled | expense | .04 | bán hàng, vận hành, mua hàng, kho | Tạm ứng không hoàn |
| receivable_lapping | skimming | .08 | bán hàng | Giữ tiền thu của khách A, lấy tiền khách B bù cho A, xoay vòng; khoảng trống cuối được đóng bằng trả hàng (L2) hoặc xóa nợ (vụ Lê Huy 1,5 tỷ) |
| unrecorded_sales_skimming | skimming | .05 | bán hàng, kho | Bán không ghi doanh thu, khai hàng hỏng để bù |
| false_refund | skimming | .05 | bán hàng, kế toán | Trả hàng khống rồi hoàn tiền vào tài khoản không phải của khách |
| cash_larceny | cash_larceny | .10 | thủ quỹ | Rút tiền quỹ, chứng từ chi khống |
| inventory_theft | noncash | .10 | thủ kho | Phiếu xuất khống, khai hao hụt (vụ VINACO, Massan) |
| kickback_overpricing | corruption | .09 | mua hàng, KTT | Giá mua cao hơn thị trường 10 đến 70% |
| price_creep | corruption | .05 | mua hàng | Tăng giá dần 1,2 đến 4% mỗi lần |
| bid_rotation | corruption | .05 | mua hàng, giám đốc | Nhóm nhà cung cấp quân xanh quân đỏ thay phiên trúng giá cao |
| undisclosed_related_vendor | corruption | .06 | mua hàng, giám đốc, KTT | Nhà cung cấp sân sau, khối lượng tăng dần |
| period_end_adjustment | financial_statement | .03 | KTT, giám đốc | Bút toán tay cuối kỳ, ngoài giờ |
| fictitious_revenue_cutoff | financial_statement | .03 | giám đốc, KTT | Doanh thu khống cuối quý rồi đảo lại kỳ sau |
| owner_override_transfer | owner_override | .03 | giám đốc | Giám đốc tự duyệt tạm ứng lớn không hoàn |

## 3. Kịch bản niêm phong (7), chưa từng dùng khi phát triển

| Kịch bản | Nhánh | Mô tả | Nguồn gốc ý tưởng |
|---|---|---|---|
| phantom_sales_real_dealers | financial_statement | Hóa đơn bán cho đại lý thật, hàng không giao; L1 đóng bằng trả hàng sau 20 đến 60 ngày; L2 đóng bằng xóa nợ sau 150 đến 220 ngày | Vụ Sebang Battery Vina [Đ] |
| underpriced_sales_kickback | corruption | Nhiều hóa đơn bán thấp hơn mức thường lệ của một khách 10 đến 50% | Cùng vụ (bán rẻ 8 đến 10% so với giá niêm yết); ACFE sales schemes |
| cash_withdrawal_skim | cash_larceny | Rút tiền ngân hàng về quỹ ngoài kế hoạch hai lần mỗi tháng; L2 ngày lệch gần kỳ rút | Vụ thủ quỹ Bảo Định [Đ] |
| advance_kiting | expense | Tạm ứng mới thanh toán tạm ứng cũ, số tiền tăng dần, cái cuối không hoàn | Phân tích thủ đoạn ở [T] |
| overtime_inflation_group | payroll | Nâng lương làm thêm của 3 đến 6 công nhân cùng lúc do người lập lương | Biến thể của payroll_padding |
| fake_lease_vendor | billing | Tiền thuê kho hằng tháng cho kho không tồn tại | ACFE billing |
| fake_tax_payment | payment_tampering | Ủy nhiệm chi nộp thuế sang tài khoản khác | ACFE check and payment tampering |

Cảnh báo trung thực: kịch bản niêm phong do cùng người viết; để giảm thiên lệch không thêm đặc trưng hay bộ phát hiện nào cho chúng sau khi nghĩ ra, và nhãn của chúng bị ẩn khi huấn luyện (tệp 09).
