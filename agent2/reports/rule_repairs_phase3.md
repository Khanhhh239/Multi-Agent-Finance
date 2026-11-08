# Đợt 3 — thống nhất mô tả, phạm vi và nguồn bằng chứng

Chính sách dưới đây được chốt theo mục tiêu nghiệp vụ trước khi chấm lại test. Giữ baseline A5 log/MAD z=3,5 đã chọn trên validation đợt 2, ngưỡng hàng đợi 7 và các dataset/nhãn gốc. Không train hoặc chấm ML. [Kết quả chấm mới](rule_repairs/phase3/summary_vi.md) so với snapshot đợt 2; các báo cáo audit/đợt 1/đợt 2 vẫn là mốc lịch sử.

## Quyết định đã triển khai

| Rule | Định nghĩa hiện tại | Giới hạn cần hiểu đúng |
| --- | --- | --- |
| A3 | Trên `vendor_payment`: nhánh ≥2 khoản/3 ngày/tổng ≥85% hạn mức và ≥3 khoản/30 ngày/tổng ≥hạn mức, qua ít nhất hai NCC; từng khoản dưới hạn mức của người lập tương ứng. Gom cả nhiều người lập qua TK ngân hàng có định danh, SĐT hoặc đại diện đã biết. | Địa chỉ chung đơn lẻ không tạo liên kết A3. Tổng so với hạn mức giao dịch hiện tại. Lưu một hit với nhánh ngắn nếu cả hai nhánh cùng đạt, tránh cộng hai lần. Liên kết mạnh vẫn có thể là quan hệ hợp lệ; chưa xác minh ý định chia nhỏ trên mọi hợp đồng. |
| A4 | Cùng người lập, ≥3 khoản chi tiền/ngân hàng ở mức 80%–99% hạn mức từng khoản trong **tháng lịch**. | `near_period=rolling_30d` là lựa chọn riêng, không gọi là tháng. Loại lương/chi định kỳ có quyền chi tháng đã duyệt/as-of và tổng đã trả không vượt trần. Không tự miễn mọi payroll/rent hoặc dùng nhãn hard negative. |
| A5 | Chỉ **đuôi cao**, mục tiêu khoản chi tăng bất thường; cùng nghiệp vụ/thực thể/danh mục, tối thiểu 20 quan sát. | Không xét đuôi thấp/độ lệch tuyệt đối. `amount_tail` chỉ nhận `upper`. Log/MAD z>3,5 là mặc định đã chọn ở đợt 2; raw mean/SD z>+2 là đối chiếu. A5 vẫn là ngữ cảnh cần bằng chứng độc lập. |
| B1 | Đối chiếu toàn bộ master nhân viên/NCC đã biết tại các thời điểm chấm thành chẩn đoán riêng. Cảnh báo giao dịch trên chi NCC Có 111/112 bằng tiền/ngân hàng, gồm thuê/chi bán hàng, khi TK thụ hưởng trùng nhân viên hoặc NCC trùng căn cước. | Ghi công nợ/mua hàng không chi tiền không tự hard trigger. Bank code cần hiện diện ở cả hai phía; thiếu thì số TK thực chỉ là chẩn đoán 0 điểm. BANK_SYN là namespace định danh duy nhất của generator. CCCD/CMND đọc khi có nguồn, không tự sinh. |
| B3 | Lần phát sinh **bút toán tài chính gắn NCC đầu tiên trong lịch sử quan sát**, gồm mua ghi công nợ trước khi trả tiền. | Chưa có lịch sử trước đầu dataset; không khẳng định lần đầu suốt đời NCC. Các quan sát đồng thời là nhóm đầu đồng thời. Giữ ngoại lệ chứng từ có loại/nội dung đã xác minh và vai ngữ cảnh ở đợt 2. |
| F1 | Bút toán có log **manual**, nhập từ 0 đến 5 ngày trước khóa sổ thực của kỳ (bao gồm biên), amount>mức trọng yếu kế toán được duyệt/có hiệu lực. Hỗ trợ cả loại nghiệp vụ khác adjustment. | Cần đủ audit log, lịch khóa sổ và chính sách trọng yếu đã biết/as-of. Adjustment/cuối tháng/hạn mức người lập chỉ là proxy 0 điểm. Tự duyệt trong quyền không tự miễn F1 đã xác nhận từ ba nguồn. |

Mốc thời gian theo dữ liệu ISO có offset +07:00 của hệ thống hiện tại. Cửa sổ A3 là số giây đã trôi qua; A4 là năm-tháng lịch. Giao dịch đồng thời không nhìn thấy nhau, không phụ thuộc thứ tự ID. Quyền chi A4 không cấp độc lập cho nhiều khoản cùng thực thể/nghiệp vụ/tháng tại một timestamp: trường hợp này không được miễn tự động.

## Nguồn mới và dữ liệu chưa có

Các CSV tùy chọn phải được khai báo SHA-256 trong `manifest.json`; loader từ chối file có checksum thiếu/lệch. Không join `labels.csv` hoặc loại hard negative vào engine. Bản ghi cần ID ổn định và `observed_at` để giữ phiên bản, kể cả phiên bản thu hồi; tương lai không sửa điểm quá khứ.

Ba nguồn F1 có các cột sau:

| File | Cột bắt buộc |
| --- | --- |
| `journal_audit_log.csv` | `audit_id, company_id, employee_id, transaction_id, entry_origin, entered_at, observed_at, evidence_id` |
| `closing_periods.csv` | `closing_id, company_id, period_start, period_end, closing_at, status, approver_id, approved_at, observed_at, evidence_on_file, evidence_id` |
| `materiality_policies.csv` | `policy_id, company_id, effective_from, effective_to, materiality_vnd, status, approver_id, approved_at, observed_at, evidence_on_file, evidence_id` |

`entry_origin` là `manual` hoặc `automatic`; log gắn đúng người lập và giao dịch. `entered_at <= observed_at <= posted_at` và người lập đã có trong master lúc nhập. Phiên bản automatic mới nhất không cho dùng một phiên bản manual cũ. Kỳ và khoảng hiệu lực dùng ngày `YYYY-MM-DD`; thời điểm nhập/khóa/duyệt/quan sát dùng ISO +07:00. Kỳ khóa phải bao gồm ngày posted; khoảng cách tới khóa tính từ thời điểm nhập trong log, không dùng ngày cuối tháng làm thay thế.

Lịch khóa và chính sách trọng yếu cần `status=approved`, evidence ID, `evidence_on_file=1`, người duyệt cùng công ty đã biết tại lúc duyệt, `approved_at <= observed_at <= posted_at`. Nguồn công ty không khai báo `employee_id`/`vendor_id`. Đây là kiểm tra nguồn hỗ trợ hiện tại; chưa có ma trận thẩm quyền duyệt chính sách/SoD đầy đủ.

B1 đọc thêm `bank_code` trên master nhân viên/NCC, `recipient_bank_code` trên giao dịch và `national_id` trên master. Số định danh được giữ dạng chuỗi, không mất số 0 đầu. Với số TK thực, engine cần mã ngân hàng chuẩn hóa thống nhất; không đoán ngân hàng từ độ dài/số TK hoặc tự lấy mã NCC khi mã ngân hàng thụ hưởng chưa biết. Số 9/12 chữ số chỉ là định dạng được hỗ trợ, không xác minh danh tính hay tính chính xác căn cước.

A4 dùng nguồn `payroll_entitlements` đã duyệt: `leave_type=regular_payroll` hoặc `paid_leave`, đúng `employee_id/payroll_period`, hợp đồng lao động có hồ sơ, người duyệt khác người nhận và tổng đã trả trong tháng không vượt `entitled_amount_vnd`. Đây là quyền chi số tiền, không thay ngoại lệ E1 về ngày nghỉ hưởng lương. Chi định kỳ dùng `recurring_payments` của đợt 2, bổ sung `frequency=monthly`, đúng nghiệp vụ/thực thể, khoảng hiệu lực và số tiền ±tolerance; tổng tháng không vượt expected+tolerance. Chưa tự miễn định kỳ tuần/quý/năm. Khoản định kỳ đã được miễn A4 lúc chi vẫn lưu ID ngoại lệ trong lịch sử để truy vết.

Dataset gốc không được tự bổ sung nguồn bên trên. Vì vậy F1 chưa có bằng chứng xác nhận trên ba dataset gốc; giảm điểm proxy không phải chứng minh F1 đã chính xác. B3 chỉ nhìn `transactions` tài chính đã quan sát: chứng từ phụ trợ tạo khi chuẩn hóa kế toán và sổ mua ngoài hệ thống chưa được nạp như một lịch sử kinh tế độc lập. Cần nguồn sổ mua/lịch sử mở đầu khi đưa vào SME thật.

Đối chiếu B1 master được lưu ở `master_identity_findings.jsonl`, tách khỏi hàng đợi giao dịch. Đây là các ảnh chụp bằng chứng as-of đã khử trùng ID, không phải số NCC gian lận. File này chưa có màn hình master riêng trong UI. Phiên bản master chưa quan sát tại thời điểm chấm không xuất hiện; bộ dữ liệu không có giao dịch thì cần một công cụ kiểm tra master với cutoff riêng, hiện chưa triển khai.

Cập nhật 14/10/2026: giới hạn giữ cạnh master cũ của A3/B2 đã được sửa. Đồ thị thay thế/đóng liên kết theo phiên bản quan sát, loại bản sao cũ trong `entity_links` và dựng lại cả thành phần liên thông khi nguồn đổi. B1 trực tiếp vẫn dùng phiên bản master hiện tại. [Chính sách, kiểm chứng và phạm vi còn lại](rule_graph_history.md). Các số liệu đợt 3 bên dưới là snapshot lịch sử, không phải số liệu chấm lại bản sửa này.

## Những khác biệt có chủ đích C1/C2

`rule_class_1.md` đã cập nhật lịch vận hành C1 và quyền tự duyệt C2. C1 đối chiếu riêng lúc lập/lúc duyệt với lịch đã biết tại chính thao tác đó. Thứ Bảy có quyền vận hành công ty hoặc ca cuối tuần đã duyệt là hợp lệ; không miễn chỉ vì có nhãn `weekend_operations`. Thiếu lịch ca dùng khung mặc định hiện tại; ngoài giờ chỉ là ngữ cảnh.

C2 lưu hit bị loại khi tự duyệt trong `self_approval_limit_vnd` trên master đã biết; vượt quyền vẫn hard trigger. Đây là phạm vi quyền số tiền đang hỗ trợ, chưa thay ma trận SoD/ủy quyền theo nghiệp vụ. Test không được coi mọi tự duyệt hoặc thứ Bảy là vi phạm mặc định.

## Kiểm tra và tái lập

`tests/test_spec_policy.py` có 26 đối chứng độc lập: biên cửa sổ/tổng A3; tháng 31 ngày/qua tháng A4; lương/chi định kỳ và không dùng lại trần chi; đuôi thấp/cao A5; thuê/chi bán hàng, master không chi tiền, ngân hàng/CCCD và nhân viên được quan sát muộn B1; mua ghi công nợ trước trả tiền và đồng thời B3; log manual/automatic, lịch khóa giữa tháng, trọng yếu khác hạn mức, thu hồi/nguồn muộn/sai công ty và nghiệp vụ khác adjustment cho F1.

Runner chấm lại ba bộ, kiểm tra dữ liệu/baseline/source hash, tái tính điểm và recurrence từ hits, đối chiếu hàng đợi không trùng/thiếu thành viên; giữ tập hit B2/B4/B7/C2/E1/P1/T2 và tập ứng viên các luật không sửa. C1/A5/B3 có thể đổi điểm góp do anchor mới nhưng không đồng nghĩa sửa predicate. Benford dùng lại snapshot đợt 2, khai báo rõ không chấm lại D. Audit đọc phạm vi B1/F1 theo config đã lưu; snapshot thiếu `spec_policy` dùng phạm vi legacy, không đổi mẫu số của audit lịch sử. Hai test riêng bảo vệ việc phân phiên bản này.

Trong `comparison.json`, `candidates_after/unsuppressed_after` là bộ đếm theo mã rule. Với hàng `operational`, hai trường này không áp dụng (giá trị 0); số cảnh báo thực lấy từ `after.alerts`. Tỷ lệ FP/TP của bảng tổng hợp tính trên toàn bộ split, khác độ chính xác predicate ở tập đủ nguồn.

Kết quả test 0,3%: TP 67→68, FP 458→443, precision 12,76%→13,31%. A4 góp điểm trên FP giảm 470→287 nhưng đây không phải 183 cảnh báo biến mất, vì điểm A4 thấp và có luật chồng lặp. F1 góp điểm trên TP giảm 5→0 do thiếu nguồn, các dòng này vẫn được phát hiện bởi bằng chứng khác. Cả ba bộ không mất TP khỏi hàng đợi test; không suy ra độ nhạy F1 trên nguồn thật từ kết quả này. Hàng đợi toàn thời gian còn 1.759/1.947/2.118 giao dịch ở ba bộ, tương ứng 1.397/1.550/1.682 hồ sơ.

Nghiệm thu kỹ thuật: **111 test qua**, gồm 26 đối chứng nghiệp vụ mới và 2 đối chứng phạm vi audit. [validation.json](rule_repairs/phase3/validation.json) xác nhận hash, replay điểm, thành viên hàng đợi và nạp snapshot vào ReviewStore của cả ba bộ; [controlled_cases.csv](rule_repairs/phase3/controlled_cases.csv) liệt kê đối chứng nghiệp vụ. Chưa thực hiện kiểm tra trực quan bằng trình duyệt. Database QA riêng `.runtime/review/phase3_qa.sqlite3`, không thay phản hồi/DB vận hành cũ.

```powershell
python -m unittest discover -s tests -v
python -m sme_fraud.run_spec_alignment --output reports/rule_repairs/phase3_new
python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase3 --database .runtime/review/phase3.sqlite3 --port 8768
```

Lệnh UI đọc snapshot mới vào database riêng; phản hồi người dùng và database cũ giữ nguyên. Launcher `start_review.py` vẫn trỏ snapshot mặc định cũ. Các runner đợt 1/đợt 2 và fixture audit lịch sử được ghim `spec_policy=legacy`; engine mới mặc định `phase3`. Khi chấm lại config lịch sử thiếu khóa này, phải thêm khóa legacy tường minh. Kết quả mới không thay thế benchmark nhiều seed/test mới giữ kín và dữ liệu SME có kết luận rà soát độc lập.
