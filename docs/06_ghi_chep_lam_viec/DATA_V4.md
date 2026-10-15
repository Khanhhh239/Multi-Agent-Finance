# DATA_V4.md — Nghiên cứu miền gian lận nội bộ và thế giới dữ liệu v4

Ngày: 14/10/2026. Mã: `agent2/world_v4.py`, `agent2/world_v4_schemes.py`, `agent2/accounting_ext.py`, `agent2/validate_v4.py`, `agent2/feats_v4.py`. Dữ liệu: `work/data/w4_s411..413`.

**Vẫn là dữ liệu tổng hợp.** v4 sát thực tế hơn v3 về quy trình, chính sách và kiểu gian lận, nhưng không có dòng nào là dữ liệu thật của doanh nghiệp Việt Nam. Mọi con số dùng để so sánh phương pháp, không dùng để nói về doanh nghiệp thật.

Quy ước: **[Đ]** đã đọc tài liệu gốc trong phiên; **[T]** chỉ đọc tóm tắt / bài báo; **[N]** giả định thiết kế của tôi.

---

## 1. Trả lời các điểm phản biện (đã kiểm tra trên mã)

| Điểm phản biện | Kiểm tra | Xử lý trong v4 |
|---|---|---|
| Chỉ 8 doanh nghiệp | Đúng (v3 mặc định 8) | 48 công ty mỗi thế giới, mỗi công ty rút ngẫu nhiên chính sách riêng: quy mô 10–80 người, ngành, ngày trả lương (5, 10, 15, 25, cuối tháng, hoặc hai kỳ), kỳ hạn nợ NCC/khách, tỷ lệ khách trả đúng hạn, thói quen chứng từ, hạn mức tự duyệt, mức dùng tiền mặt |
| Gian lận sinh bằng công thức định trước, AI có thể học dấu vết bộ sinh | Đúng, và đã thấy thật ở v3: lương luôn trả ngày 28 nên mọi khoản lương lệch ngày dễ bị bắt | Nền sinh theo quy trình và chính sách từng công ty; mỗi kịch bản có 3 mức che giấu và ca hợp lệ giống hệt; thêm **kiểm tra lối tắt**: mô hình chỉ dùng loại nghiệp vụ + các trường vô nghĩa (phút, giây, thứ tự ID, chữ số số hóa đơn, số tiền mod 1.000) không được tốt hơn mô hình chỉ dùng loại nghiệp vụ. Kết quả 3 thế giới: mức tăng −0,044 / −0,028 / −0,003 (không có lối tắt) |
| `payroll_padding` sửa giao dịch cũ, có thể đổi số nhãn/phân phối | Sửa tại chỗ là cố ý (gian lận thật cũng sửa chính bảng lương); số dòng không đổi | v4 giữ cách này cho các kịch bản sửa bản ghi thật (nâng lương, xoay vòng công nợ) và ghi rõ trong `truth_cases`; dòng thay thế chỉ lấy từ "dòng đệm" không liên kết, nên không phá liên kết hóa đơn–thu tiền hay lịch lương |
| Chuỗi gian lận nhiều dòng, cần đánh giá theo dòng và theo vụ | Đúng | Thêm bảng `truth_cases.csv` (vụ, người thực hiện, cấp bậc, thông đồng, mức che giấu, bắt đầu/kết thúc, số dòng, thiệt hại); mọi vụ nằm trọn trong một giai đoạn (có kiểm tra) |
| Thông tin chỉ có sau giao dịch → rò rỉ theo thời gian | Đặc trưng của bạn bạn và của tôi chỉ dùng dữ liệu quá khứ (có test cắt dữ liệu tương lai) | Mọi bằng chứng mới có `observed_at`/`recorded_at` (ngày ghi nhận nghỉ việc trễ 0–10 ngày, trạng thái MST bị công bố sau, đổi tài khoản ngân hàng); đặc trưng v4 chỉ đọc bằng chứng đã ghi nhận trước thời điểm chấm |
| Nhãn "hard" có thể vẫn dễ | Đúng: độ khó do bộ sinh đặt chưa chắc là độ khó thật | v4 đổi tên thành "mức che giấu" (L0/L1/L2) và **đo độ khó thực nghiệm** theo tỷ lệ phát hiện của các phương pháp (mục 6) |
| `fraud_duplicate_payment` ghi bản sao | Không ghi đè: mỗi lần `put` lấy một dòng đệm khác; dòng gốc là `support`, dòng trùng là `fraud`, cùng `case_id` | Giữ; dòng gốc và dòng trùng liên kết qua `case_id` và số hóa đơn |
| `fraud_payroll_padding` trả `remaining` khi hết ứng viên → thiếu ngân sách | Đúng là lỗi tiềm ẩn ở v3 (không xảy ra vì validator đòi đủ ngân sách, nhưng có thể xảy ra) | v4 không còn kiểu "ngân sách giả": kịch bản không đặt được thì báo `NotApplicable` và chọn công ty/kịch bản khác; số dòng gian lận thật được đếm, không được cộng giả |
| `kickback`/`expense_padding` dùng `at + timedelta` không kiểm tra cửa sổ | Ở v3 an toàn nhờ biên 60 ngày (tối đa 48–49 ngày) nhưng mong manh; NCC ma ở v3 đã từng vượt cửa sổ (lỗi thật, đã sửa) | v4: mọi thời điểm qua hàm `clamp`, và `put` **khẳng định** dòng nằm trong giai đoạn và lập ≤ duyệt ≤ ghi sổ |

Ngoài ra, khi làm v4 tôi phát hiện thêm một lỗi trong mã gốc của bạn bạn: phần tạm ứng (`advance`, `inject_normal_advances`) và giao dịch mặc định chọn ngẫu nhiên nhân viên **kể cả người chưa vào làm**. v3 không lộ ra vì mọi nhân viên đều vào làm từ 2023; v4 có tuyển dụng thay thế nên validator bắt được. Đã sửa trong v4 (bản gốc giữ nguyên để tái lập số cũ).

---

## 2. Nghiên cứu miền

### 2.1. Cây phân loại ACFE và số liệu hiệu chỉnh (ACFE, *Occupational Fraud 2024: A Report to the Nations*, 1.921 vụ, 138 nước) [Đ, đọc lại bản PDF]
- Ba nhánh: chiếm đoạt tài sản (tiền: skimming, cash larceny, chi khống gồm billing, payroll, expense reimbursement, check/payment tampering, register disbursements; hàng hóa và tài sản khác), tham nhũng (xung đột lợi ích, hối lộ, lại quả, thông thầu), gian lận báo cáo tài chính.
- Cấp bậc người thực hiện: nhân viên 37% (thiệt hại trung vị 60.000 USD), quản lý 41% (184.000 USD), chủ/lãnh đạo 19% (500.000 USD). Thời gian kéo dài trung vị: 8 / 18 / 24 tháng.
- Thông đồng: 1 người 46%, 2 người 18%, 3 người trở lên 36%.
- Che giấu: 89% vụ có che giấu; phổ biến nhất là tạo chứng từ giấy giả (41%) và sửa chứng từ giấy (37%).
- Dấu hiệu hành vi: sống vượt khả năng 39%, khó khăn tài chính 27%, quan hệ thân thiết bất thường với NCC/khách 20%.
- Tốc độ thiệt hại chung: 9.900 USD/tháng.
- Tỷ lệ loại gian lận ở tổ chức dưới 100 nhân sự (Phần 6): billing 31%, check/payment tampering 23%, expense 20%, skimming 19%, cash larceny 17%, cash on hand 16%, payroll 14%, noncash 20%, corruption 44%, báo cáo tài chính 8%.

### 2.2. Thủ đoạn thật ở Việt Nam (báo chí và bản án) [T]
| Thủ đoạn | Ví dụ | Kịch bản v4 |
|---|---|---|
| Lập khống chứng từ chi, tái sử dụng hóa đơn đã thanh toán, scan chữ ký giám đốc | Công ty Khải Đệ ([PLO](https://plo.vn/2-nu-ke-toan-dung-but-than-chiem-doat-tien-cong-ty-post423482.html), [ZNews](https://znews.vn/ke-toan-lap-khong-chung-tu-qua-mat-ba-chu-chiem-doat-tien-ty-post1605592.html)) | `duplicate_payment`, `expense_fictitious`, `cash_larceny` |
| Sửa số tiền trên phiếu đề xuất/bảng lương sau khi giám đốc ký ("bút thần") | Công ty DTC, 536 triệu ([PLO](https://plo.vn/2-nu-ke-toan-dung-but-than-chiem-doat-tien-cong-ty-post423482.html)) | `overbilling_excess_payment`, `payroll_padding` |
| Nâng khống công nợ khách, hủy phiếu thu | Kế toán trưởng cá độ ([Báo Pháp luật](https://baophapluat.vn/ke-toan-truong-me-ca-do-64-lan-sut-thung-quy-cong-ty-post266657.html)) | `receivable_lapping`, `false_refund` |
| Giả chữ ký trên ủy nhiệm chi, sửa ảnh "chi tiết giao dịch" để giả đã nộp tiền | Công ty Lê Minh Long, hơn 17 tỷ ([VOH](https://voh.com.vn/phap-luat/nu-ke-toan-gia-chu-ky-lanh-dao-chiem-doat-hon-17-ty-dong-537851.html)) | `altered_payee`, `bank_detail_switch` |
| Nhân viên kinh doanh thu công nợ không nộp về công ty | Công ty Lê Huy, gần 1,5 tỷ từ 18 cửa hàng ([Báo Pháp luật](https://baophapluat.vn/nhan-vien-kinh-doanh-chiem-doat-tien-ty-cua-cong-ty-de-tieu-xai-ca-nhan-post467395.html)) | `receivable_lapping` |
| Lập khống danh sách nhận lương / nâng hệ số lương | Trường THCS Giồng Ông Tố, 7,59 tỷ ([Tuổi Trẻ](https://tuoitre.vn/de-nghi-truy-to-ke-toan-truong-hoc-lap-khong-danh-sach-nhan-luong-de-chiem-doat-7-5-ti-dong-20221101131641329.htm)) | `ghost_employee`, `payroll_padding` |
| Lập khống danh sách chi thưởng | 770 triệu ([PLO](https://plo.vn/2-nhan-vien-lap-khong-danh-sach-chi-thuong-chiem-doat-770-trieu-dong-post739502.html)) | `fake_bonus_list` |
| Lập khống chứng từ suất ăn công nhân | Bắc Ninh, hơn 1,1 tỷ ([Tiền Phong](https://tienphong.vn/lap-khong-chung-tu-suat-an-cong-nhan-chiem-doat-hon-11-ty-dong-post1858878.tpo)) | `expense_fictitious` |
| Thủ kho tự lập phiếu xuất, tuồn hàng bán ra ngoài | VINACO, hơn 900 triệu ([Báo Văn hóa](https://baovanhoa.vn/phap-luat/khoi-to-thu-kho-tuon-hang-cua-cong-ty-ra-ben-ngoai-ban-72387.html)); thủ kho Massan, 348 triệu ([VnBusiness](https://vnbusiness.vn/thu-kho-cua-cong-ty-massan-linh-7-nam-tu.html)) | `inventory_theft`, `unrecorded_sales_skimming` |
| Cửa hàng trưởng điều chỉnh doanh thu sau giờ chốt | Bản án 103/2022/HS-PT ([Thư viện pháp luật](https://thuvienphapluat.vn/banan/ban-an/ban-an-ve-toi-tham-o-tai-san-so-1032022hspt-237679)) | `false_refund`, `unrecorded_sales_skimming` |
| Mua hóa đơn của doanh nghiệp ma, doanh nghiệp bỏ địa chỉ kinh doanh | Phần 6; các bài hướng dẫn tra cứu DN rủi ro cao về hóa đơn [T] | `invoice_mill` (trạng thái "bỏ địa chỉ" chỉ được công bố sau) |

### 2.3. Hiệu chỉnh phía công nợ phải thu
Atradius Payment Practices Barometer Việt Nam 2025 (đã đọc gốc ở phiên Agent 1, `agent1_data/calibration_vn.json`): 65% doanh số B2B bán chịu, kỳ hạn trung bình 45 ngày, 58% giá trị hóa đơn trả đúng hạn, 39% trễ (khoảng một tháng), 3% nợ xấu. v4 rút cho mỗi công ty tỷ lệ đúng hạn trong 45–72%, nợ xấu 1–5%, kỳ hạn 30/45/60 ngày, trễ 5–60 ngày.

### 2.4. Tài liệu về sinh dữ liệu
- Tritscher và cộng sự 2022 (ERPsim, trò chơi có người chơi gian lận) và 2024 (KI 2024, sinh dữ liệu bằng mô phỏng đa tác tử có nhãn giải thích) [T]: ủng hộ hướng mô phỏng theo quy trình và tác nhân thay vì chèn ngẫu nhiên.
- Benchmark 2026 về dữ liệu tổng hợp cho gian lận (arXiv 2604.13125) [T]: bộ sinh dạng bảng thường mất tín hiệu hành vi (thời gian, tốc độ, nhiều tài khoản); mô phỏng mã hóa bằng tay không tổng quát sang mẫu mới → lý do v4 vẫn phải có họ niêm phong và kiểm tra lối tắt.

---

## 3. Danh mục 30 kịch bản (v4)

Mỗi kịch bản là một **vụ** có người thực hiện theo vai trò, cấp bậc, thông đồng và mức che giấu. Cột "Ca hợp lệ giống" là mồi đo báo nhầm.

| Nhánh ACFE | Kịch bản | Dấu vết trong dữ liệu | L0 / L1 / L2 | Ca hợp lệ giống |
|---|---|---|---|---|
| Billing | `shell_vendor` | NCC mới nhận tiền định kỳ, không nhận hàng | TK NCC = TK nhân viên / địa chỉ, người đại diện liên kết nhân viên / NCC "cũ" không trùng thông tin | NCC mới hợp lệ, bên liên quan đã công bố |
| Billing | `invoice_mill` | NCC đăng ký dưới 60 ngày, hóa đơn dịch vụ số tròn; "bỏ địa chỉ" công bố sau | trạng thái đã công bố / công bố sau thanh toán | hóa đơn lịch sử hợp lệ |
| Billing | `overbilling_excess_payment` | khoản trả thêm cùng số hóa đơn, tiền vào TK lạ | TK nhân viên / TK lạ | trả góp hợp lệ |
| Billing | `personal_purchase` | mua ở cửa hàng bán lẻ cuối tuần, không nhận hàng | cuối tuần, buổi tối / ngày thường có chứng từ | mua công cụ hợp lệ |
| Billing | `split_payments`, `vendor_burst` | nhiều khoản sát hạn mức / loạt chi buổi tối | — | trả góp, chi cuối tuần hợp lệ |
| Payment tampering | `duplicate_payment` | trả trùng | cùng số HĐ / số HĐ mới / lệch ±3% | trả góp hợp lệ |
| Payment tampering | `altered_payee` | người nhận không có trong danh mục NCC; NCC thật được trả lại sau | TK nhân viên / TK lạ | đổi TK đã xác minh |
| Payment tampering | `bank_detail_switch` | đổi TK NCC không xác minh, trả, rồi đổi lại | — | đổi TK có gọi lại xác minh |
| Payroll | `ghost_employee`, `fake_bonus_list` | người nhận lương/thưởng không có chấm công | TK nhân viên / không chấm công / chấm công giả | nhân sự làm từ xa, đợt thưởng toàn công ty |
| Payroll | `payroll_padding`, `terminated_still_paid`, `off_cycle_payroll` | lương cao bất thường; lương sau nghỉ việc; lương ngoài lịch | mức nâng 30–100% / 15–35% / 6–15% | thưởng Tết, quyết toán nghỉ việc, ứng lương có duyệt |
| Expense | `expense_fictitious`, `expense_padding`, `expense_duplicate_claim`, `advance_unsettled` | chi tiếp khách định kỳ; sát hạn mức tự duyệt; nộp trùng; tạm ứng không hoàn | không chứng từ / chứng từ giả / như thật | tự duyệt hợp lệ, gia hạn tạm ứng |
| Skimming | `receivable_lapping` | tiền khách sau áp cho hóa đơn khách trước; người trả ≠ khách; cuối chuỗi xóa nợ hoặc giảm trừ | xóa nợ / giảm trừ có chứng từ | khách trả hộ công ty liên kết, xóa nợ khó đòi có hồ sơ |
| Skimming | `false_refund`, `unrecorded_sales_skimming` | giảm trừ + hoàn tiền vào TK không phải khách; khai hàng hỏng | — | trả hàng hợp lệ, hao hụt kiểm kê |
| Cash | `cash_larceny` | thủ quỹ chi tiền mặt số tròn, chứng từ yếu | — | chi tiền mặt thường |
| Noncash | `inventory_theft` | xuất hủy ngoài kỳ kiểm kê, lặp lại | ngoài kỳ / ghép vào cuối tháng | hao hụt kiểm kê quý |
| Corruption | `kickback_overpricing`, `price_creep`, `bid_rotation`, `undisclosed_related_vendor` | đơn giá cao hơn lịch sử / tăng dần / nhóm NCC chung người đại diện thay phiên / NCC sân sau tăng dần khối lượng | mức tăng giá và mức liên kết khác nhau | tăng giá hợp lệ, mua dồn hợp lệ |
| Financial statement | `period_end_adjustment`, `fictitious_revenue_cutoff` | bút toán tay cuối kỳ; doanh thu cuối quý rồi giảm trừ kỳ sau | — | chốt kỳ hợp lệ |
| Owner override | `owner_override_transfer` | giám đốc tự duyệt tạm ứng lớn, không hoàn | — | tạm ứng giám đốc có hoàn ứng |

Nghiệp vụ mới (định khoản đơn giản theo mẫu, không phải tư vấn thuế): `sales_return` Nợ 511/Có 131, `customer_refund` Nợ 131/Có 112, `bad_debt_writeoff` Nợ 642/Có 131, `inventory_writeoff` Nợ 632/Có 156, `cash_withdrawal` Nợ 111/Có 112. Kiểm toán sổ của bạn bạn được mở rộng để các bút toán này vẫn qua kiểm tra cân đối.

---

## 4. Thiết kế thế giới v4 [N]

**Nền theo quy trình:** lương hằng tháng cho mọi nhân viên đang làm theo lịch trả của công ty (tăng lương 2025); quyết toán nghỉ việc; thuê nhà, thuế GTGT, khấu hao theo ngày cố định; hóa đơn bán → thu tiền theo hành vi khách (đúng hạn / trễ / nợ xấu → xóa nợ có hồ sơ sau 180–260 ngày); giá vốn cho thương mại/bán lẻ; hàng trả lại 2%; mua hàng trả theo kỳ hạn NCC vào ngày chạy thanh toán trong tuần; chi tiền mặt và rút quỹ hai lần một tháng; hao hụt kiểm kê quý; đợt thưởng Tết/cuối năm. Dòng "đệm" (khoảng 14%) là giao dịch rời rạc như v3, và chỉ dòng đệm bị thay bằng dòng gian lận.

**Vụ gian lận:** khoảng 55% công ty có ít nhất một vụ; vụ được rút theo trọng số ACFE cho tổ chức dưới 100 nhân sự; người thực hiện theo cấp (thực tế đạt: nhân viên 40%, quản lý 51%, chủ 9% so với ACFE 37/41/19, chủ thấp hơn vì chỉ một số kịch bản phù hợp giám đốc); thông đồng 46/18/36% như ACFE; thời gian 1–4 tháng (nhân viên), 1,5–5 tháng (quản lý), 2–6 tháng (chủ), ngắn hơn ACFE vì mỗi vụ phải nằm trọn trong một giai đoạn kiểm thử; thiệt hại tăng dần theo thời gian.

**Quy mô thiệt hại:** trung vị khoảng 38 triệu đồng/vụ, phân vị 90 khoảng 137 triệu (thế giới 411). Thấp hơn nhiều so với ACFE (vụ đã điều tra) vì là SME nhỏ và vụ bị cắt ngắn; đây là giả định.

## 5. Thống kê ba thế giới (`validation_v4.json`)

| | w4_s411 | w4_s412 | w4_s413 |
|---|---:|---:|---:|
| Dòng | 200.000 | 200.000 | 200.000 |
| Dòng gian lận (tỷ lệ) | 800 (0,40%) | 801 (0,40%) | 806 (0,40%) |
| Vụ / kịch bản | 194 / 30 | 196 / 30 | 190 / 30 |
| Công ty có vụ / tổng | 20 / 48 | 28 / 48 | 28 / 48 |
| Mức che giấu L0 / L1 / L2 | 35 / 78 / 81 | 34 / 90 / 72 | 26 / 90 / 74 |
| Kiểm tra lối tắt (AUC loại / loại+vô nghĩa) | 0,790 / 0,746 | 0,779 / 0,752 | 0,799 / 0,796 |

Mỗi thế giới có 25 loại ca hợp lệ giống gian lận (khoảng 17.900 dòng ở thế giới 411), 26 loại nghiệp vụ. Mọi kiểm tra đều qua: trình tự thời gian, khóa ngoại, không có dữ liệu chủ tương lai, liên kết thu tiền–hóa đơn, lương sau nghỉ việc chỉ xuất hiện dưới dạng quyết toán hợp lệ hoặc gian lận có nhãn, sổ cân Nợ = Có, đủ 30 kịch bản ở cả 3 giai đoạn, mỗi vụ trong một giai đoạn, số dòng trong `truth_cases` khớp nhãn.

## 6. Độ khó thực nghiệm theo kịch bản

Giao thức theo thời gian (huấn luyện 2024, kiểm thử nửa cuối 2025), trung bình 3 thế giới 411–413, ngân sách B3 theo từng công ty mỗi tuần. Nguồn: `work/results/bench_w4/*.json` (`python -m agent2.aggregate work/results/bench_w4`). Toàn bộ là dữ liệu tổng hợp, không phải bằng chứng về doanh nghiệp thật.

### 6.1 Tổng quan

| Phương pháp | AP | Recall@B3 | Vụ tìm thấy@B3 | Báo nhầm ca giống gian lận |
|---|---:|---:|---:|---:|
| Luật + đồ thị (của bạn bạn) | 0,079 ± 0,022 | 27,0% | 42,7% | 16,5% |
| IF[friend190] | 0,004 | 7,0% | 18,4% | 23,0% |
| AE (không giám sát) | 0,096 ± 0,015 | 37,0% | 60,4% | 32,2% |
| Lệch so với chính thực thể (EntityDeviation) | 0,025 | 34,5% | 52,6% | 13,4% |
| max(Luật, Entity) | 0,078 | 39,4% | 59,8% | 15,6% |
| LightGBM, 190 đặc trưng của bạn bạn | 0,069 ± 0,071 | 42,1% | 61,6% | 14,0% |
| LightGBM + đặc trưng kỹ thuật + luật (L3) | **0,577 ± 0,058** | **77,5%** | 87,0% | 16,5% |
| max(L3, Luật, Entity) | 0,281 | 76,0% | **90,5%** | 14,6% |

Đọc kết quả:
- v4 khó hơn hẳn v3: luật tay chỉ còn AP khoảng 0,08 vì 30 kịch bản phần lớn nằm ngoài phạm vi 9 luật ban đầu, và mỗi kịch bản có ca hợp lệ "mồi" giống hệt bề ngoài.
- 190 đặc trưng của bạn bạn không mô tả được các quy trình mới (thu tiền, lương theo lịch, xóa nợ, hủy hàng), nên LightGBM chỉ đạt AP 0,07. Khi thêm 15 dấu hiệu đỏ của v4 (`agent2/feats_v4.py`), AP lên 0,57. **Cảnh báo:** các đặc trưng này do cùng người viết bộ sinh thiết kế, nên mức tăng này là giới hạn trên; trên dữ liệu thật mức tăng sẽ nhỏ hơn.
- Precision@B3 chỉ khoảng 4,5% vì tỷ lệ gian lận 0,4% và hơn nửa số công ty không có vụ nào nhưng vẫn nhận đủ ngân sách cảnh báo. Đây là đặc điểm của ngân sách cố định theo công ty, không phải lỗi mô hình.

### 6.2 Theo mức che giấu (Recall@B3, %)

| Phương pháp | L0 (lộ) | L1 (che một phần) | L2 (che kỹ) |
|---|---:|---:|---:|
| Luật + đồ thị | 43 | 30 | 20 |
| EntityDeviation | 31 | 37 | 35 |
| LightGBM[friend190] | 55 | 41 | 36 |
| L3 | 91 | 79 | 69 |
| max(L3, Luật, Entity) | 88 | 80 | 68 |

Mức che giấu có tác dụng như thiết kế: luật giảm từ 43 xuống 20, mô hình tốt nhất giảm từ 91 xuống 69. EntityDeviation gần như không đổi theo mức che giấu, vì nó so với lịch sử của chính nhân viên hay nhà cung cấp chứ không dựa vào dấu vết chứng từ.

### 6.3 Theo kịch bản (Recall@B3, %, trung bình 3 thế giới)

Khó nhất với mô hình tốt nhất (L3):

| Kịch bản | Luật | Entity | LGBM190 | L3 | max(L3,R,E) | Vì sao khó |
|---|---:|---:|---:|---:|---:|---|
| payroll_padding | 0 | 79 | 0 | 4 | 79 | Chỉ tăng vài phần trăm lương; chỉ phát hiện được khi so với lịch sử của chính người đó |
| vendor_burst | 17 | 10 | 17 | 27 | 17 | Nhà cung cấp thật, đơn giá thật, chỉ tần suất tăng |
| price_creep | 19 | 86 | 23 | 39 | 64 | Giá tăng dần từng ít một |
| expense_duplicate_claim | 0 | 3 | 33 | 47 | 47 | Hai chứng từ khác số, cùng nội dung |
| kickback_overpricing | 39 | 68 | 20 | 48 | 70 | Giá cao nhưng trong biên độ thị trường |
| personal_purchase | 15 | 10 | 20 | 51 | 51 | Hàng mua thật, chỉ khác mục đích |
| off_cycle_payroll | 0 | 45 | 31 | 52 | 52 | Có ca hợp lệ (thưởng, quyết toán) cùng dạng |
| split_payments | 37 | 13 | 39 | 55 | 55 | Mỗi khoản dưới hạn mức |

Dễ nhất (L3 ≥ 96%): overbilling_excess_payment, terminated_still_paid, unrecorded_sales_skimming, cash_larceny, altered_payee, undisclosed_related_vendor, expense_fictitious, inventory_theft.

Kết luận thiết kế: không có phương pháp đơn lẻ nào phủ hết. Lệch theo thực thể bắt được nhóm "rỉ rả" (payroll_padding, price_creep, kickback) mà mô hình có giám sát bỏ qua. Vì vậy kiến trúc kết hợp (CES hoặc max-fusion) vẫn cần thiết.

### 6.4 Kịch bản chưa từng thấy (bỏ một kịch bản khi huấn luyện, thế giới 411)

Mỗi lần bỏ toàn bộ nhãn của một kịch bản khỏi tập huấn luyện, rồi đo recall@B3 trên chính kịch bản đó ở tập kiểm thử. Trung bình 30 kịch bản:

| Phương pháp | Recall@B3 khi kịch bản chưa từng thấy |
|---|---:|
| Luật + đồ thị | 30,4% |
| EntityDeviation | 31,8% |
| LightGBM[friend190] | 35,7% |
| max(Luật, Entity) | 44,9% |
| L3 | 62,2% |
| max(L3, Luật, Entity) | **70,2%** |

- Không phương pháp nào bắt được ghost_employee khi chưa từng thấy (0%).
- vendor_burst đạt 10% và receivable_lapping 19%.
- expense_padding: L3 đạt 0% nhưng Entity đạt 67%.

Chỉ một thế giới, mỗi kịch bản ở tập kiểm thử chỉ có từ 1 đến 27 dòng gian lận (trung vị khoảng 6) nên sai số lớn; con số dùng để xếp hạng, không dùng để báo cáo độ chính xác. Kết quả gốc: `work/results/lfo_w4_s411.json`.

## 7. Điều v4 vẫn chưa làm được

- Không có dòng hàng hóa đơn đầy đủ (chỉ đơn giá và số lượng một dòng), không có sao kê ngân hàng riêng, không có tồn kho theo mã hàng; một số kịch bản (bán không ghi doanh thu, trộm hàng) vì vậy chỉ để lại dấu vết gián tiếp.
- Hành vi được mã hóa bằng tay: mô hình học trên v4 có thể quen với cách tôi viết kịch bản. Cần tiếp tục: (1) tập niêm phong với kịch bản mới viết bởi người khác; (2) dữ liệu thật từ doanh nghiệp đối tác.
- Ngưỡng, tỷ lệ, thiệt hại là giả định; chỉ cơ cấu người thực hiện, thông đồng và hành vi thanh toán của khách có nguồn.

## 8. Cách chạy
```powershell
$env:PYTHONPATH = (Get-Location)
python -m agent2.world_v4 --output work/data/w4_s411 --rows 200000 --fraud-rate 0.004 --seed 411 --companies 48
python -m agent2.validate_v4 --data work/data/w4_s411
python -m agent2.bench --data work/data/w4_s411 --out work/results/bench_w4 --skip-transfer
```
