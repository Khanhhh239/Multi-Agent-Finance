# Ca khó và ca hợp lệ giống gian lận

Độ khó của dữ liệu đến từ ba nguồn: **che giấu của kẻ gian lận**, **bình thường giống gian lận**, và **thay đổi giữa các giai đoạn**.

## 1. Ba mức che giấu

| Mức | Ý nghĩa | Ví dụ (nhà cung cấp ma) | Ví dụ (nâng lương) | Tỷ lệ |
|---|---|---|---|---:|
| L0 | Lộ rõ: chứng từ ít, ngoài giờ, tự duyệt, trùng thông tin cá nhân | Tài khoản nhà cung cấp là tài khoản nhân viên | 1,3 đến 2,0 lần | .15 |
| L1 | Có chứng từ nhưng còn dấu vết | Địa chỉ hoặc điện thoại trùng | 1,15 đến 1,35 lần | .45 |
| L2 | Chứng từ và hành vi giống bình thường | Nhà cung cấp lâu năm, không trùng gì, có phiếu nhận hàng | 1,06 đến 1,15 lần | .40 |

Kết quả đo (3 thế giới, mô hình tốt nhất L3): recall ở ngân sách 3 cảnh báo mỗi tuần giảm từ 91% (L0) xuống 79% (L1) và 69% (L2); luật tay từ 43% xuống 30% và 20%.

## 2. Ca hợp lệ giống gian lận (hard negatives)
Có 25 loại ở thế giới phát triển (khoảng 17.900 dòng, 9% số dòng), thêm 5 loại ở thế giới niêm phong. Mục đích: một mô hình chỉ đi tìm "dấu hiệu bất thường" sẽ báo nhầm các ca này.

| Loại ca hợp lệ | Giống kịch bản nào |
|---|---|
| legit_bonus_run, tet_bonus_payroll, year_end_bonus_payroll | off_cycle_payroll, fake_bonus_list, payroll_padding |
| legit_final_settlement | terminated_still_paid |
| legit_offcycle_payroll | off_cycle_payroll |
| remote_employee_payroll | ghost_employee (không chấm công) |
| legit_price_increase | price_creep, kickback_overpricing |
| legit_bulk_purchase | personal_purchase, kickback |
| new_legitimate_vendor, declared_related_party | shell_vendor, undisclosed_related_vendor |
| verified_bank_change | bank_detail_switch |
| historical_valid_invoice, legitimate_installments | duplicate_payment, split_payments |
| round_recurring_payment | số tiền tròn (thuê nhà, lương) |
| legit_sales_return | false_refund |
| legit_bad_debt_writeoff | receivable_lapping (đóng khoảng trống bằng xóa nợ) |
| legit_affiliate_payment | receivable_lapping (bên trả khác bên mua) |
| legit_inventory_writeoff | inventory_theft, unrecorded_sales_skimming |
| legit_director_advance | owner_override_transfer |
| approved_advance_extension, approved_advance_writeoff | advance_unsettled |
| legitimate_self_approval | expense_padding |
| legitimate_period_close | period_end_adjustment |
| long_approval_delay, weekend_operations | các tín hiệu về giờ giấc |

**Niêm phong (5 loại mới):** legit_volume_discount (bán giá thấp có hợp đồng khung), legit_extra_withdrawal (rút tiền mặt có chứng từ), legit_overtime_peak (làm thêm mùa cao điểm có duyệt), legit_new_lease (thuê kho thật), legit_tax_installment (nộp thuế thêm đợt).

## 3. Các yếu tố làm khó khác

| Yếu tố | Cơ chế | Mục đích |
|---|---|---|
| Hơn nửa công ty không có vụ | `fraud_mu = 0` ở 45% công ty | Ngân sách cảnh báo vẫn phát; đo precision thực tế hơn |
| Quy trình nền có tính mùa | Thưởng cuối năm, trước Tết, cuối quý | Tránh báo nhầm do mùa |
| Luân chuyển nhân sự | 18% nghỉ việc, có người thay thế | Cần phân biệt "sau nghỉ việc" hợp lệ (quyết toán) với gian lận |
| Lịch trả lương khác nhau theo công ty | 8 kiểu lịch; 35% công ty đổi kiểu ở bản niêm phong | Mô hình không học "ngày 28" |
| Gian lận nằm lẫn trong dòng sẵn có | `payroll_padding`, `overtime_inflation_group` sửa dòng lương đã có | Không có dòng "thừa" để đoán |
| Thông đồng và vụ nhiều dòng | Có vụ từ 3 người; vụ trung vị 3 đến 4 dòng | Cần đánh giá mức vụ |
| Kịch bản bị ẩn | Bỏ một kịch bản hoặc một nhánh khỏi nhãn huấn luyện | Đo khả năng bắt kiểu chưa từng thấy (tệp 09) |
| Chuyển giao sang công ty mới | Huấn luyện trên thế giới khác, áp cho thế giới đích | Đo khởi đầu lạnh |
