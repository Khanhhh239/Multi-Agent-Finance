# Rà soát việc cần sửa tiếp — 17/10/2026

**Chưa đủ cơ sở nghiệm thu vận hành chính thức. Hợp đồng công suất và export lý do tiếp nhận đã sửa; hồ sơ mẫu A4 đã có bản thử, chưa được reviewer xác nhận hoặc chọn làm mặc định.** Việc còn mở là nghiệm thu hồ sơ mẫu/công sức, replay ưu tiên theo sự kiện và nguồn thật. Chưa có bằng chứng để thêm luật hoặc đổi ngưỡng toàn hệ thống.

Tại lượt rà trước sửa công suất, mã Python khớp hash checkpoint **373 test, 7 probe đạt**; lượt đó chỉ chạy probe nhỏ và phân tích chỉ đọc trên **225.000 quan sát**. [Mã kiểm tra lịch sử](../.runtime/readiness_next_20261017/recheck.py), [kết quả và hash lịch sử](../.runtime/readiness_next_20261017/verification.json). **Lượt sửa công suất sau đó: 390/390 test và 7/7 probe đạt**, tính lại tải từ queue đã khóa, không chấm tập test benchmark hoặc fit model. [Bản sửa hiện tại](rule_review_capacity.md).

**Checkpoint bản thử A4 trước lượt sinh dữ liệu: 412/412 test và 7/7 probe đạt.** Queue thử 5.538 → 4.774 hồ sơ, giữ nguyên tập giao dịch/TP/FP; 905 gói reviewer, 0 đơn vị đã được xác nhận. Độ nhạy giữ tổng phút cho thấy còn mẫu vượt công suất ngày, nên chưa kết luận giảm công sức thực tế. [Bản thử và giới hạn](rule_a4_pattern_trial.md).

**Checkpoint sinh dữ liệu trước sửa export: 425/425 test và 7/7 probe đạt.** Đã sinh **62.182 giao dịch** trên ba seed, tám công ty mỗi seed; hai bộ reporting khớp **1.216/1.216** kỳ vọng kiểm soát nguồn F1/C4/E2/F2/F3/F4, bộ còn lại chưa chấm. Có phiếu nguồn, mapping minh họa, cache đúng hợp đồng và diễn tập R6 trên SQLite riêng. Kết quả này bổ sung kiểm chứng tích hợp; trạng thái nghiệm thu nguồn thật vẫn giữ riêng. [Dữ liệu, kết quả và cách dùng](rule_synthetic_source_readiness.md).

**Checkpoint hiện tại sau sửa export: 437/437 test, 7/7 probe đạt.** Bản export mới giải thích đủ 3.315 giao dịch được nhận thêm, gồm hai dòng chỉ nhận qua lô của bộ 005. Membership, điểm/cờ/hard trigger và 192 file nguồn/baseline được bảo vệ giữ nguyên. [Schema, kết quả và bằng chứng](rule_admission_export.md).

## 1. Cao — thống nhất công suất giữa mô phỏng và API nhận việc

**Trạng thái: đã sửa kỹ thuật.** Simulator nhận riêng số lượt/phút, dùng chung `ReviewCapacity` với API; có lịch tùy chọn, tồn cuối kỳ, thời gian xử lý tồn và hồ sơ vượt trần phút. Ca áp lực cùng cấu hình đã cho cùng kết quả API. Đã replay 120 tổ hợp tải từ sáu snapshot; 36 đối chứng nghiên cứu cũ khớp chính xác, hash 236 file bảo vệ giữ nguyên. [Thiết kế, kết quả và giới hạn](rule_review_capacity.md). Phần mô tả dưới đây giữ lại phát hiện trước sửa.

[`budget_review`](../sme_fraud/evidence_evaluation.py) tự cấp `budget × 45` phút/ngày: **5 hồ sơ = 225 phút**. [`ReviewStore`](../sme_fraud/review_store.py) dùng **5 hồ sơ = 120 phút**, hoặc 10 hồ sơ = 240 phút. Hai giới hạn hồ sơ và phút trong mô phỏng hiện gần như không độc lập: hồ sơ thường có ước lượng tối đa 45 phút nên trần `budget × 45` không siết thêm số lượt.

**Ca tái hiện:** năm hồ sơ cùng công ty, mỗi hồ sơ 45 phút, cùng đến trong một ngày. Mô phỏng nhận cả năm; gọi API `admit` thật trên SQLite fixture chỉ nhận hai hồ sơ, dùng 90/120 phút; hồ sơ thứ ba bị từ chối vì vượt phút. Không phải lỗi predicate hoặc lỗi API kiểm soát công suất. [Đối chứng](../.runtime/readiness_next_20261017/workload_probes.json).

Đã kiểm tra độ nhạy trên **sáu snapshot validation trước/sau A2/A4**, giữ nguyên thứ hạng lúc mở và ước lượng công sức: chuyển từ 225 xuống 120 phút **không làm tăng số lượt phải chuyển ngày trên chính dữ liệu này**. Trước A2/A4 cả ba bộ đều 0; sau sửa lần lượt 6/7/9 ở cả hai mức phút. Công sức của các hồ sơ hiện có còn thấp nên chênh lệch chỉ lộ ở ca áp lực. Không được diễn giải ca áp lực thành backlog tăng đã quan sát trên benchmark. Phép tính 225 phút đối chiếu khớp chỉ số đã lưu trước khi thử 120 phút. [Mã](../.runtime/readiness_next_20261017/capacity_analysis.py), [kết quả](../.runtime/readiness_next_20261017/capacity_analysis.json).

**Yêu cầu đã triển khai:** truyền riêng số lượt và số phút vào simulator; dùng chung hợp đồng công suất với API. Kịch bản 1/3/5 hồ sơ nghiên cứu được giữ với số phút và tên riêng, tách khỏi cấu hình UI. Đã bổ sung lịch làm việc, backlog tại ngày kết thúc kỳ và thời gian giải phóng backlog; mặc định vẫn là mọi ngày lịch, có phân tích độ nhạy T2–T6.

**Điều kiện đóng đã đạt:** cùng fixture cho cùng kết quả nhận/hoãn giữa simulator và API ở cùng lượt/phút, có đối chứng đủ lượt nhưng thiếu phút. Đã tính lại **tải** từ queue đã khóa; không fit lại IF hoặc thay điểm rule. Đây chưa phải nghiệm thu công suất theo thời gian SME thực tế.

## 2. Cao — đánh giá hồ sơ mẫu chung cho A4 và giảm việc rà trùng

**Trạng thái: đã triển khai bản thử, chưa đóng điều kiện reviewer.** Chỉ khoản A4 yếu vào mẫu người lập–tháng; hard/A2/hỗn hợp giữ hồ sơ hiện hành và liên kết theo bằng chứng. ID mẫu ổn định, phạm vi/bằng chứng đổi không tự nhận kết luận/phân công cũ. Mặc định vẫn là queue NCC. Đã so sánh toàn queue/tải trên 225.000 dòng, giữ TP/FP và hard trigger; chưa có reviewer xác nhận giảm việc, có trường hợp vượt phút khi không giả định tiết kiệm. [Thiết kế, gói reviewer và kết quả](rule_a4_pattern_trial.md). Các số chẩn đoán dưới đây là đầu vào của bản thử, không dùng để chọn ngưỡng.

A4 xét **công ty + người lập + kỳ**, nhưng queue thường gom theo **cụm NCC/người nhận**. Ca nhỏ có năm khoản 17 triệu đến năm NCC độc lập, cùng người lập trong một tháng: ba khoản cuối đều chỉ có A4 3 điểm, không hard trigger, và tạo **ba hồ sơ NCC** cho cùng chuỗi A4. Bằng chứng A4 của các hồ sơ lặp lại các khoản trước trong chuỗi. Đây là kết quả đúng với cách gom hiện hành; chưa đủ cơ sở gọi ba hồ sơ là ba cảnh báo sai. [Nguồn, hit và hồ sơ của ca tái hiện](../.runtime/readiness_next_20261017/a4_scope_probe.json).

Trên phần **mới được nhận của validation**, phân rã theo `review_rule_ids` của dòng:

| Nhóm dòng mới | Dòng | Gian lận mô phỏng | Dòng thường |
| --- | ---: | ---: | ---: |
| Chỉ A2 | 306 | 4 | 302 |
| A2 và A4 | 24 | 1 | 23 |
| Chỉ A4 | 813 | 1 | 812 |
| Chỉ nhận qua đóng lô, không có lý do ở dòng | 2 | 0 | 2 |
| **Tổng** | **1.145** | **6** | **1.139** |

Đây là chẩn đoán trên các dự đoán đã khóa, không phải nhãn dùng để chọn chính sách. Tỷ lệ 6/1.145 ≈ **0,52%** chỉ mô tả phần nhận thêm theo nhãn gian lận mô phỏng; không phải độ đúng predicate hoặc kết luận reviewer. Ba bộ cùng seed, không phải ba mẫu thực địa độc lập.

Nhóm chỉ-A4 mới có **73/72/70** phạm vi người lập–tháng chạm từ hai hồ sơ trở lên trong ba bộ. Một phạm vi chỉ là ứng viên tổ chức công việc: chưa chứng minh các khoản cùng nghĩa vụ hoặc các hồ sơ có thể gộp an toàn. Không lấy số phạm vi hay số tham chiếu lặp để trừ cơ học khỏi 5.538 hồ sơ.

**Đã có bản thử; cần nghiệm thu:** reviewer đối chiếu phạm vi, đo việc rà trùng và thời gian, chỉ rõ trường hợp giữ nhiệm vụ nghĩa vụ riêng hoặc tách phiên. Giữ đối chiếu nghĩa vụ chi–PO–hóa đơn và lịch định kỳ của rule gốc; **thiếu hồ sơ nghĩa vụ chi vẫn giữ cảnh báo theo chính sách hiện hành**, không tự thêm ngoại lệ để giảm FP.

**Điều kiện đóng:** giảm công việc lặp được reviewer xác nhận ở cấp hồ sơ; giữ nguyên phủ mẫu cần rà, thời điểm phát hiện, ngân hàng R2, tháng lịch A4 và hard trigger. So sánh toàn queue dưới cùng ngân sách; khóa phương án trước đợt nghiệm thu mới. Không tắt A4 hoặc nâng/hạ ngưỡng theo bảng nhãn này.

## 3. Vừa — replay công việc theo sự kiện sau mở hồ sơ

Simulator cố ý chỉ xếp hạng bằng sự kiện `opened`; nó không cập nhật hồ sơ đang chờ khi có `escalated`/`batch_closed`. **Ca tái hiện:** một hồ sơ mở ở mức trung bình phải chờ qua ngày; sáng hôm sau đã lên `cao_nhat` 20 điểm nhưng vẫn bị hồ sơ mới `cao` 14 điểm xử lý trước. [Thứ tự sự kiện và lịch xử lý](../.runtime/readiness_next_20261017/workload_probes.json).

Đây là giới hạn của chính sách **opening evidence only** đang được khai báo, không phải bằng chứng UI đang xếp hard trigger sai. UI đọc mức ưu tiên hiện tại từ queue. Chưa nên dùng mô phỏng này để kết luận thời gian phản ứng với hard trigger mới hoặc SLA vận hành. Ngoài ra, ước lượng phút lấy từ quy mô hồ sơ cuối snapshot; chưa phải công sức biết tại mỗi thời điểm.

**Cần cải tiến:** khi mô phỏng vận hành, cập nhật mức ưu tiên/công sức từ sự kiện đã biết tại cutoff xử lý; không lấy mức ưu tiên cuối snapshot cho quá khứ. Chốt chính sách tái rà khi đã xử lý rồi xuất hiện bằng chứng mới, tách khỏi lượt nhận ban đầu và khỏi diagnostic nhãn tại lúc mở. Có test hồ sơ đang chờ lên hard trigger, bằng chứng tương lai, và không tính trùng công việc.

## 4. Vừa — xuất lý do tiếp nhận đầy đủ cho hồ sơ đóng lô

**Trạng thái: đã sửa kỹ thuật.** CSV v2 tách lý do dòng/lý do hiệu lực, ID hồ sơ/lô, rule sự kiện và reference tới JSONL bằng chứng cho mọi ID nhận thêm. Đã xuất riêng từ snapshot cũ, đối chiếu đủ 3.315/3.315 ID, không thay điểm/cờ dòng hoặc commitment cũ. [Bản sửa](rule_admission_export.md), [kết quả đối chiếu](admission_export_20261017_v1/summary.json). Mô tả dưới đây giữ lại phát hiện trước sửa.

Hai dòng `T000021842`, `T000068394` của bộ `005` vào hồ sơ qua A4 sau đóng lô, nhưng `added_admissions.csv.admission_basis/review_rule_ids` lấy từ dòng nên rỗng; điểm/cờ cảnh báo dòng vẫn đúng là 0. Có thể lần ngược bằng case và batch event, nhưng file delta chưa tự giải thích được nguyên nhân. [Giải thích artifact hiện tại](rule_artifact_inventory.md).

**Điều kiện đóng đã đạt:** tách rõ `row_admission_basis`, `effective_admission_basis`, `case_ids`, `batch_event_ids`, `event_rule_ids` và `admission_evidence_ref`. Mỗi ID mới có đường dẫn tới record bằng chứng cụ thể. Điểm/cờ dòng và report đã khóa giữ nguyên; bản mới có commitment riêng và đối chiếu membership.

## 5. Bắt buộc trước nghiệm thu — nguồn thật và triển khai lịch sử

Cổng F1/C4/E2/F2/F3/F4 vẫn **`awaiting_real_data`**, **0 đơn vị nguồn thật chấm mù**, tiêu chí **`not_frozen`**. Đây là khoảng trống bằng chứng lớn nhất; thêm test hoặc thêm luật không đóng được. Cần mapping/coverage ERP–HR–chi tiền, tiêu chí khóa trước review, reviewer độc lập và tập nghiệm thu mới. [Readiness nguồn](rule_repairs/real_source_acceptance/readiness.json), [quy trình](rule_source_acceptance.md).

Do hiện chưa có nguồn thật, đã tạo [bộ mô phỏng v2](rule_synthetic_source_readiness.md) với **3.312 đơn vị trong phiếu nguồn**, chưa có kết luận của con người; **2.208 đơn vị** thuộc hai bộ đã có dự đoán khóa, **1.104** thuộc holdout chưa chấm. Tiêu chí đã khóa cho **diễn tập tổng hợp**, không thay thế `not_frozen` của nghiệm thu thật. Hai bộ có 1.216 oracle điều kiện nguồn được đối chiếu, gồm 192 trường hợp thiếu bằng chứng; nghiệp vụ nền chưa có nhãn gian lận. Ngưỡng, điểm, hard trigger và chính sách thiếu hồ sơ nghĩa vụ chi giữ nguyên.

Khi đưa queue vào bộ rà soát có lịch sử người dùng, chạy migration R6 trên snapshot/audit đúng phiên bản; chỉ chuyển trường hợp tương đương một-một. Nếu có nhu cầu nhiều tài khoản đồng thời, hoàn/hủy/đảo giao dịch, chốt hợp đồng nguồn và đối chứng riêng trước khi tuyên bố hỗ trợ. Các nhánh này vẫn là giới hạn chưa được nghiệm thu, không phải lỗi mới đã tái hiện trong lượt này.

Diễn tập R6 mới dùng bản sao synthetic và sự kiện `SIM_REHEARSAL_BOT`: đã giữ đúng feedback/phân công/admission với ID tương đương, không truyền feedback/admission sang hồ sơ đổi bằng chứng, audit giữ nguyên hash. Chưa migration dữ liệu người dùng. Các nhánh hoàn/đảo/nhiều tài khoản mới chỉ được kiểm tra từ chối/cách ly ở tầng nguồn thô.

**Thứ tự đề xuất hiện tại:** hoàn thiện replay sự kiện; song song review bản thử A4, đo công sức và thu nguồn thật để khóa đợt nghiệm thu. Chưa cần mở rộng ML hoặc tăng số luật chỉ vì lớp tất định chiếm 80% trọng số thiết kế.
