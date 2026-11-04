# Tồn đọng và SLA của baseline — 28/10/2026

**Đuôi chờ chủ yếu liên quan tải tồn đầu kỳ và trần phút xử lý. Chưa có bằng chứng nên thay bộ chọn hồ sơ hoặc tăng ngân sách cố định.** Đồng hồ cũ còn gộp thời gian trước khi lượt tái rà đủ điều kiện: cần đọc lại con số 21/27 ngày.

[Trạng thái dự án](../../STATUS.md) · [Hướng dẫn chạy](../../../examples/baseline_sla_audit/README.md) · [Chẩn đoán chi tiết](../../../reports/baseline_sla_20261028/diagnosis.json) · [22 cấu hình](../../../reports/baseline_sla_20261028/scenario_comparison.csv)

## Phạm vi và đối chứng

Chỉ đọc bản tích hợp ngày 28/10, hai cohort mô phỏng 001/003, tám công ty mỗi cohort, từ **01/07/2025 đến trước 01/01/2026**. Cutoff ngày là nửa đêm kế tiếp tại Việt Nam, như phép thử gốc. Đây là tái dựng hồi cứu từ đầu ra detector đã khóa, không phải log ERP hoặc thời gian làm việc của kế toán thật.

Đã tái hiện **đúng bốn baseline**: 5 suất/120 phút và 10 suất/240 phút ở cả hai cohort. Khớp từng lượt, thứ tự, scope, chi phí ước tính, loại công việc và đồng hồ chờ cũ; khớp cả tổng tồn theo ngày, tồn cuối kỳ, phút và trạng thái chờ thông tin. Tổng cấu hình chính có **2.425 lượt công việc được chọn**; một case có thể có nhiều scope/rà tiếp/tái rà.

Chạy **22 cấu hình offline** và **63 test đạt**, gồm 16 test mới. Không chấm lại luật hoặc IF, không mở model, không đọc nhãn/holdout, không ghi kết luận hoặc thay chính sách app. Các nguồn và nghiên cứu đã khóa giữ nguyên.

## 1. Con số 21/27 ngày gồm một lỗi diễn giải đồng hồ

Trong `compare_shadow.pending`, lịch tái rà lấy `ready` từ ngày đầu thấy scope và hạn hẹn cũ; chưa chặn nó tại ngày lượt tái rà thực sự có thể vào hàng đợi sau lượt rà đầu. Audit giữ đồng hồ cũ để tái hiện, đồng thời đo ngày đầu từng **work key** thật sự xuất hiện trong tập pending.

| Đồng hồ | 001 | 003 |
| --- | ---: | ---: |
| Max `wait_days` đã báo cáo | 21 ngày | 27 ngày |
| Max ngày pending không được chọn, kể từ đủ điều kiện | **20 ngày** | **26 ngày** |
| Số lượt tái rà | 172 | 176 |
| Max chờ sau khi lượt tái rà đủ điều kiện | **0 ngày** | **0 ngày** |
| Phần đồng hồ cũ cộng trước khi đủ điều kiện, cộng trên các lượt | 559 ngày | 624 ngày |

Ví dụ cụ thể:

- **001/C002, `SC_ff5a6bd29fc70525`**: rà đầu 21/07; lượt tái rà chỉ đủ điều kiện 22/07 và được chọn ngay 22/07. Đồng hồ cũ vẫn bắt đầu 01/07 nên báo 21 ngày. SLA case đã là 26/06, trước cửa sổ thử nghiệm.
- **003/C003, `SC_c54398721fe03601`**: rà đầu 27/07; tái rà đủ điều kiện và được chọn ngay 28/07. Đồng hồ cũ báo 27 ngày từ 01/07. SLA case là 23/06.

Đối soát toàn bộ lượt được chọn: **5.064 = 3.881 + 1.183 + 0**, lần lượt là tổng đồng hồ cũ, ngày thực sự pending không được chọn, phần cộng trước eligibility và khoảng rời hàng đợi. Đây là tổng trên các lượt công việc, không phải ngày của một người hoặc số hồ sơ độc lập.

Audit chưa sửa hàm gốc hoặc viết lại báo cáo cũ. Cách đo mới nằm riêng trong `selected.csv`; khi sửa metric sản xuất cần version hóa và giữ khả năng tái hiện lịch sử.

## 2. Tồn đầu kỳ là một giả định lớn của phép thử

Tồn đầu kỳ được lấy tại cutoff **trước** 01/07, không chỉ nhìn ngày mở của case. Baseline giả định chưa có lượt nào được rà trước khi bắt đầu:

| Tại đầu kỳ | 001 | 003 |
| --- | ---: | ---: |
| Scope hồ sơ đang tồn | 292 | 328 |
| Scope có SLA đã qua trước đầu kỳ | 270 | 306 |
| Công ty tạo đuôi lớn nhất | C002 | C003 |
| Scope đầu kỳ tại công ty đó | 69 | 98 |

Ngay trên tập lượt tồn đầu kỳ **thực tế baseline đã chọn**, C002/001 có 72 lượt gồm tái rà, tốn 2.238 phút ước tính; C003/003 có 98 lượt, tốn 2.928 phút. Với 120 phút/ngày, cận dưới lần lượt là **19 và 25 ngày phục vụ**, trước khi tính giới hạn đóng gói, ngày lượt tái rà đủ điều kiện và việc mới. Cận dưới này có điều kiện trên tập công việc của đối chứng, không phải lời khẳng định mọi chính sách đều phải xử lý cùng tập phiên bản.

Nếu giả định tồn đầu kỳ và các lượt tái rà cũ đã đến hạn đều đã xử lý, giữ 5/120, max chờ đủ điều kiện còn **1/0 ngày**. Giả định đó cũng thay lịch sử tính chi phí rà tiếp, nên không được cộng chênh lệch với tác động tăng công suất để tạo “tỷ lệ nguyên nhân”. Không dùng nó để tự đóng hồ sơ cũ hoặc xác nhận ai đã rà thật.

## 3. Trần phút có vai trò lớn hơn việc chỉ tăng số suất

Các số sau là max chờ của **lượt đã đủ điều kiện**, lịch bảy ngày/tuần trừ dòng cuối:

| Kịch bản offline | 001 | 003 |
| --- | ---: | ---: |
| Hiện tại: 5 suất / 120 phút | 20 | 26 |
| Chỉ tăng suất: 10 / 120 | 20 | 25 |
| Chỉ tăng phút: 5 / 240 | 14 | 19 |
| Tăng cả hai: 10 / 240 | 9 | 13 |
| Giả định đã xử lý tồn đầu kỳ, 5 / 120 | 1 | 0 |
| Giả định đã xử lý tồn đầu kỳ, 10 / 240 | 0 | 0 |
| FIFO trong mức ưu tiên, giữ lượt bắt buộc | 20 | 26 |
| EDF trong mức ưu tiên, giữ lượt bắt buộc | 20 | 26 |
| EDF chỉ giữ hard, chẩn đoán nới điều kiện | 20 | 26 |
| Không giới hạn công suất, chẩn đoán | 0 | 0 |
| Chỉ làm thứ Hai–thứ Sáu, 5 / 120 | 28 | 37 |

Các nhánh không luôn chọn cùng tập phiên bản: công suất và lịch sử rà thay đổi việc scope được rà hay bị coalesce trước khi chọn. File so sánh luôn kèm phần chỉ có ở từng nhánh, tồn chưa chọn và phiên bản bị thay; không chỉ tính phần giao nhau.

Lý do cuối ngày một đầu việc pending không được chọn:

| Giới hạn đang chặn | 001 | 003 |
| --- | ---: | ---: |
| Chỉ hết suất | 147 | 232 |
| Chỉ không đủ phút cho đầu việc | 1.278 | 942 |
| Cả suất và phút | 525 | 1.223 |

Đơn vị là số lần một đầu việc chờ tại cutoff, không phải số case duy nhất. Không có trường hợp không giải thích được mà đầu việc vẫn vừa toàn bộ ngân sách còn trống. Phút lẻ còn dư nhưng không đủ cho một đầu việc không được xem là có thể chia nhỏ công việc.

Mức sử dụng phút trên **toàn bộ** cửa sổ chỉ khoảng 14,9%/15,6%; số trung bình này che tải dồn đầu kỳ và cuối kỳ, không chứng minh công suất luôn đủ ở từng công ty/ngày. Chưa có phút đo thực tế để chốt định biên hoặc một ngân sách cố định mới. Kịch bản thứ Hai–thứ Sáu là độ nhạy, không xác nhận lịch làm việc thật hay suy thêm ngày lễ.

## 4. Đổi thứ tự chưa giải quyết đuôi chờ

FIFO không đổi tập/ngày chọn trên dữ liệu này khi giữ suất bắt buộc. EDF có giữ suất bắt buộc làm 7/28 lượt thường sớm hơn nhưng 6/21 lượt khác chậm hơn, tối đa thêm **2/4 ngày**; max chờ vẫn 20/26. Không có cơ sở chọn EDF làm mặc định.

Nhánh EDF chỉ giữ hard được ghi rõ là chẩn đoán: nó không giữ đầy đủ các scope nontransaction của đối chứng, có lượt nguồn chậm thêm hoặc không còn được chọn đúng phiên bản. Không đề xuất áp dụng nhánh này.

**32 lượt ưu tiên cao nhất** trong baseline đều được chọn ngay ngày đủ điều kiện, không phải các lượt chờ 20/26 ngày. Max chờ mức trung bình là 2/6 ngày; đuôi 20/26 nằm ở mức thấp. Tám lượt cao nhất mỗi cohort vẫn mang SLA đã quá hạn trước ngày đủ điều kiện, nên không thể suy “chọn ngay ngày” thành “đã hoàn thành SLA”.

## 5. Nợ SLA cũ, SLA phát sinh và thiếu chứng từ là ba trạng thái khác nhau

Không dựng giờ hoàn thành từ một ngày chọn. So với **SLA của case** đã lưu:

| Các lượt được chọn | 001 | 003 | Tổng hai phép thử |
| --- | ---: | ---: | ---: |
| Ngày chọn chắc chắn sau hạn | 475 | 520 | 995 |
| Trong đó hạn đã qua trước đầu ngày đủ điều kiện | 463 | 506 | 969 |
| Cả ngày đầu đủ điều kiện còn trước hạn, sau đó được chọn muộn | 11 | 9 | 20 |
| Hạn nằm trong ngày đầu đủ điều kiện, thiếu giờ thực tế để tách | 1 | 5 | 6 |
| Ngày chọn trùng ngày chứa hạn, chưa kết luận đúng/trễ giờ | 15 | 8 | 23 |
| Toàn bộ ngày chọn còn trước hạn | 696 | 711 | 1.407 |

Trong 969 lượt đã mang nợ trước ngày đủ điều kiện, 789 kế thừa deadline của case tồn từ đầu kỳ; 180 là deadline đã qua trước khi **scope công việc** tương ứng đủ điều kiện. Deadline trên cùng work key không bị đổi trong các trace này. Hai mươi lượt có trễ phát sinh rõ theo độ phân giải ngày; sáu lượt còn lại không đủ dữ kiện giờ để quy toàn bộ cho hàng đợi. Đây vẫn là SLA **ngày chọn rà**, chưa phải nghiệm thu SLA hoàn thành.

Deadline tái rà (`rereview_due_at`) được xuất riêng, không đánh đồng với SLA case (`sla_due_at`), không tự dời ngày để làm đẹp tỷ lệ.

Cuối cửa sổ còn **91/89 lượt chưa được chọn**, tổng 2.443/2.405 phút ước tính. Chúng mới đủ điều kiện trong ngày 31/12 nên tuổi chờ theo ngày có cận dưới 0; không được dùng số này để khẳng định đã xử lý hết tồn. Có **28/37 scope chưa rà bị thay bằng scope mới**, được ghi riêng, không tính là đã xử lý hữu ích.

Ngoài hàng đợi chưa chọn, có **342/335 scope chờ thông tin** mà lượt rà tương ứng đã được tính xong trong ledger mô phỏng. Không có lượt tái rà còn pending chồng lên nhóm đó ở cutoff cuối. Tăng suất rà không tự tạo ra chứng từ hoặc đóng được các case này. Tất cả là trạng thái mô phỏng; không phải kế toán viên đã rà thật.

## Việc nên làm trước khi đổi chính sách

1. Version hóa đồng hồ chờ theo từng lượt đủ điều kiện; giữ metric cũ để tái hiện. Audit này đã xuất hai đồng hồ cạnh nhau, chưa sửa lịch hoặc bộ chọn hiện hành.
2. Khi nhập lịch sử, xác nhận trạng thái đầu kỳ: chưa rà, đã rà, chờ chứng từ, hoặc chờ tái rà. Không mặc định tất cả đều chưa rà hoặc đều đã xong.
3. Chuẩn bị đợt xử lý tồn riêng theo công ty, ưu tiên đo nhu cầu **phút** và giữ suất bắt buộc. Chưa tăng ngân sách cố định hoặc lấy chênh lệch giả định làm số nhân sự cần tuyển.
4. Chốt lịch làm việc và mốc `available_at/eligible_from/selected_at/started_at/completed_at` có căn cứ. Tách hạn rà, hạn bổ sung và hạn tái rà; không reset nợ SLA cũ tại đầu kỳ.
5. Giữ bộ chọn hiện tại trong lúc đo thêm. FIFO/EDF đã thử chưa cho lợi ích đủ rõ; IF tiếp tục shadow và không phải nguyên nhân của tồn baseline trong phép kiểm tra này.

## Bằng chứng

[Kế hoạch trước chạy](../../../reports/baseline_sla_20261028/evaluation_plan.json) · [Tổng hợp](../../../reports/baseline_sla_20261028/summary.json) · [Test](../../../reports/baseline_sla_20261028/tests.json) · [Đối soát](../../../reports/baseline_sla_20261028/verification.json).

Từng cohort có `opening_load.json`, `reference_reproduction.json`, cache frames có hash; từng cấu hình có `selected.csv`, `daily.csv`, `blocked.csv`, `censored.csv`, `work_scopes.csv`. Không dùng app feedback mô phỏng, gói reviewer cũ hoặc phút giả lập như kết quả độc lập.
