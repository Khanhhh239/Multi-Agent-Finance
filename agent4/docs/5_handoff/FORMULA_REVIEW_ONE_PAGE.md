# Phiếu rà soát 22 chỉ số ưu tiên — P1 thử nghiệm

**G0.7: CHƯA ĐẠT — công thức chưa được kế toán duyệt (G0.7 mở).**

Nguồn: 22 dòng **Must** của [FORMULA_REVIEW.md](FORMULA_REVIEW.md). Ví dụ lấy từ cột Engine Q3/2026, dữ liệu tổng hợp seed 20251; đơn vị đồng, trừ hệ số và ngày. Số thập phân làm tròn 2 chữ số, hệ số 6 chữ số. Đối chiếu kỹ thuật không phải phê duyệt kế toán.

| Chỉ số | Công thức bằng lời | Ví dụ Q3/2026 | Câu hỏi xác nhận | Trạng thái |
|---|---|---:|---|---|
| Doanh thu thuần (`net_revenue`) | Có 511 trừ Nợ 511 và Nợ 521; loại kết chuyển 911. | 55.792.824.000 | Đồng ý cách giảm trừ theo chế độ đang áp dụng? | cần duyệt trước pilot |
| Giá vốn (`cogs`) | Nợ 632 trừ Có 632; loại kết chuyển. | 45.852.513.186 | Đồng ý dấu và phạm vi bút toán? | cần duyệt trước pilot |
| Lợi nhuận gộp (`gross_profit`) | Doanh thu thuần trừ giá vốn. | 9.940.310.814 | Đồng ý hai thành phần này? | cần duyệt trước pilot |
| Chi phí hoạt động (`operating_expenses`) | Nợ 642 trừ Có 642, cộng 641 nếu áp dụng. | 10.115.939.723 | Có cần cộng tài khoản 641? | cần duyệt trước pilot |
| Lợi nhuận trước thuế (`profit_before_tax`) | Lợi nhuận thuần kinh doanh cộng thu nhập khác, trừ chi phí khác. | −666.387.909 | Đồng ý phạm vi thu nhập và chi phí? | cần duyệt trước pilot |
| Lợi nhuận sau thuế (`net_profit`) | Lợi nhuận trước thuế trừ chi phí thuế TNDN 821. | −666.387.909 | Đồng ý dùng chi phí ghi nhận tại 821? | cần duyệt trước pilot |
| Chi phí lương (`salary_expense`) | Nợ 6421/6422/154 thuộc lương, thưởng, đối ứng Có 334/335. | 5.250.914.000 | Đồng ý tài khoản và khoản mục được chọn? | cần duyệt trước pilot |
| Chi phí nhân sự (`labor_cost`) | Nợ 6421/6422/154 thuộc lương, thưởng và bảo hiểm. | 6.326.001.323 | Đồng ý phạm vi bảo hiểm được cộng? | cần duyệt trước pilot |
| Tiền (`cash_and_equivalents`) | Số dư Nợ 111 và 112 lũy kế cuối kỳ. | 7.532.938.209 | Đồng ý phạm vi tiền và ngày chốt? | cần duyệt trước pilot |
| Phải thu (`ar_balance`) | Nợ 131 trừ Có 131 lũy kế. | 42.130.662.400 | Đồng ý bù trừ để ra số thuần? | cần duyệt trước pilot |
| Phải trả (`ap_balance`) | Có 331 trừ Nợ 331 lũy kế. | 20.726.235.400 | Đồng ý bù trừ để ra số thuần? | cần duyệt trước pilot |
| Tồn kho (`inventory_value`) | Số dư Nợ các tài khoản 151 đến 157 lũy kế. | 25.112.419.304 | Đồng ý phạm vi tài khoản tồn kho? | cần duyệt trước pilot |
| Thuế phải nộp (`tax_payable`) | Số dư Có 333 lũy kế. | 59.114.716 | Khung thuế mặc định phản ánh đúng nghĩa vụ? | cần duyệt trước pilot |
| Thanh toán hiện hành (`current_ratio`) | Tài sản ngắn hạn chia nợ ngắn hạn. | 1,860344 lần | Đồng ý phạm vi ngắn hạn và xử lý mẫu số bằng không? | cần duyệt trước pilot |
| Dòng tiền thuần (`net_cash_flow`) | Phát sinh Nợ trừ Có của 111 và 112 trong kỳ. | 1.623.124.499 | Đồng ý tổng biến động tiền trong kỳ? | cần duyệt trước pilot |
| Tuổi nợ phải thu (`ar_aging`) | Phân nhóm số còn phải thu theo hạn; trả trước, chiết khấu chưa phân bổ cấn hóa đơn cũ nhất. | 42.130.662.400 | Đồng ý cách cấn trừ hóa đơn cũ nhất? | cần duyệt trước pilot |
| Phải thu quá hạn (`overdue_receivables`) | Cộng số phải thu dương có hạn trước ngày cuối kỳ trừ N ngày. | 9.350.058.600 | Đồng ý ngưỡng N và cách xét ngày quá hạn? | cần duyệt trước pilot |
| Ngày thu tiền (`dso`) | Bình quân dư 131 đầu, cuối kỳ chia doanh số bán chịu, nhân số ngày kỳ. | 61,60 ngày | Đồng ý doanh số gồm VAT và xử lý mẫu số bằng không? | cần duyệt trước pilot |
| Phải trả sắp hạn (`ap_due_soon`) | Cộng số còn phải trả có hạn không sau ngày dữ liệu cộng N ngày. | 7.413.093.000 | Đồng ý ngưỡng N và việc gồm khoản quá hạn? | cần duyệt trước pilot |
| Nghĩa vụ sắp tới (`upcoming_obligations`) | Cộng 331 đến hạn, dư 333/338/334, lương ước tính và lịch trả vay. | 1.746.666.626 | Đồng ý ước tính lương, lãi và phạm vi quá hạn? | cần duyệt trước pilot |
| Chi phí tăng bất thường (`expense_spikes`) | Chi phí khoản mục kỳ này trừ bình quân ba tháng trước, xếp mức tăng. | 2.584.507.333,33 | Đồng ý so tổng quý với bình quân tháng? | cần duyệt trước pilot |
| Thu nhập chịu thuế (`taxable_income`) | Trên khung thuế: doanh thu 511/515/711 trừ chi phí 632/642/635/811 đủ điều kiện. | −480.778.168 | Đồng ý điều kiện lọc và các khoản điều chỉnh thuế? | cần duyệt trước pilot |

Các ví dụ tuổi nợ/phải trả/nghĩa vụ/bất thường là giá trị tổng hợp đã ghi trong hồ sơ gốc; chưa có phân rã hay tham số N trên phiếu này. Kế toán cần đối chiếu định nghĩa đầy đủ khi chốt. **Chưa có xác nhận hoặc chữ ký phê duyệt.**
