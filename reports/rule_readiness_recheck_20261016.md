# Rà soát lại lớp tất định / luật cứng — 16/10/2026

**Kết luận cập nhật 17/10/2026: chưa đủ cơ sở để nghiệm thu vận hành chính thức.** R1–R8 và cơ chế nhận hồ sơ A2/A4 đã sửa kỹ thuật; đã chấm kết hợp train/validation trên ba bộ chuẩn. **373/373 test hồi quy, 7/7 probe readiness đạt.** Điểm/ngưỡng/hard trigger và model giữ nguyên; việc nhận riêng mẫu giúp thêm TP nhưng tăng FP/tải rà soát. Cần nghiệm thu nguồn/chính sách tiếp nhận và áp dụng migration khi triển khai vào bộ rà soát cũ. [Bản sửa và đánh đổi](rule_split_pattern_admission.md).

## Việc cần làm tiếp theo sau đồng bộ feature/model

Lượt đồng bộ trước sửa tiếp nhận ngày 17/10/2026 đã hoàn tất **225.000 dòng**, ba cache feature/model và **3.434 hồ sơ** trong cache SQLite riêng. Ba model đúng hợp đồng ngữ nghĩa feature, nạp/replay từ CSV chính xác; nguồn, snapshot và model gốc giữ nguyên. Validation gộp ba bộ: **FP 2.737 → 1.208, TP 198 → 194**. Đây là mô phỏng cùng seed, không phải ước lượng hiệu quả SME thật hoặc phép tách riêng tác động R1–R8. Không chấm test. [Báo cáo](rule_feature_model_sync.md), [kết quả máy đọc](feature_model_sync_20261017/summary.json).

Sau sửa tiếp nhận A2/A4: **TP 194 → 200, FP 1.208 → 2.347** trên validation, **5.538 hồ sơ** trên toàn train/validation trong cache mới. Khôi phục ngay 5/6 dòng trước đó mất cảnh báo. Ca A4 `T000081861` không đủ số khoản trong tháng 6, nên không phát cảnh báo ở dòng đầu; A1 bắt chuỗi ở khoản kế tiếp sau 5 giờ 5 phút. Điểm, hit, hard trigger, feature/model không đổi; có đối chứng cache giữ đúng ID bằng chứng E1/T1. [Chi tiết và tải theo công ty/ngày](rule_split_pattern_admission.md), [kết quả máy đọc](split_pattern_admission_20261017_v2/summary.json), [kiểm tra artifact](../.runtime/split_pattern_admission_20261017/artifact_verification.json).

Chốt R6 ngày 16/10/2026: **341/341 test hồi quy đạt**, gồm 22 test mới; **7/7 probe readiness đạt**. ID cụm/hồ sơ độc lập thứ tự nguồn, có migration tương đương một-một và lịch sử split/merge để giữ đúng phản hồi/phân công. [Bản sửa và hướng áp dụng](rule_case_identity.md), [kết quả/hash](../.runtime/case_identity_20261016/result.json). Các checkpoint trước đó là snapshot lịch sử; database/report vận hành cũ chưa được chuyển sang ID mới trong đợt này.

| Thứ tự | Việc cần làm | Điều kiện hoàn thành |
| --- | --- | --- |
| Đã hoàn tất trong lượt này | **Dựng lại feature/model và chấm kết hợp train/validation** | Đã có dataset dẫn xuất hợp lệ R7, model đúng provenance, replay cache/model/SQLite, đối chiếu hit/điểm/hồ sơ/ID và tải 1/3/5 hồ sơ/công ty/ngày; 352 test và 7 probe đạt |
| 1 — kỹ thuật đã sửa, chưa nghiệm thu chất lượng | **Tiếp nhận mẫu A2/A4 và tải rà soát** | Đã nhận riêng mẫu hợp lệ ở 4/3 điểm, không tăng hard trigger/cộng trùng họ A; áp dụng cả đóng lô, giữ tháng lịch và ngoại lệ. 373 test/7 probe đạt. FP và số hồ sơ tăng đáng kể; cần nguồn nghĩa vụ chi đầy đủ, reviewer độc lập và năng lực xử lý để nghiệm thu chính sách |
| 2 — khi áp dụng vào bộ rà soát cũ | **Migration R6 trên lịch sử người dùng thật** | Cache mới đã dựng riêng, có đối chiếu ID theo giao dịch; chưa chuyển database/feedback vận hành. Dùng snapshot/audit cũ để chỉ chuyển trạng thái tương đương một-một, rà lại hồ sơ đổi phạm vi |
| 3 — nghiệm thu chưa có bằng chứng | **Nguồn SME thật và chất lượng vận hành** | Có coverage ERP/HR/chi tiền, khóa tiêu chí trước review, kết luận độc lập và tập nghiệm thu mới giữ kín. Cổng hiện có vẫn ghi 0 đơn vị chấm mù, `awaiting_real_data` và `not_frozen` |

Chuẩn bị nguồn thật có thể thực hiện song song; chỉ kết luận nghiệm thu sau khi các lỗi kỹ thuật và chính sách đánh giá đã được chốt. Chưa có cơ sở tăng số lượng luật hoặc siết ngưỡng đồng loạt từ số lượng test đạt.

## Các bản sửa và snapshot kiểm chứng

**Cập nhật sau sửa R1 (16/10/2026):** đã ngăn gộp hóa đơn thiếu số và bổ sung kiểm tra P1 cho tiền mặt không có TK nhận. Toàn bộ **198/198 test đạt** tại lần chốt R1, gồm 7 test mới. [Chi tiết bản sửa](rule_p1_payments.md).

**Cập nhật sau sửa R3 (16/10/2026):** C2/C3 đã tra nhân sự đúng ngày ký bằng chứng và thời điểm duyệt giao dịch, gồm hạn mức fallback C2. Toàn bộ **209/209 test đạt** tại lần chốt R3, gồm 11 test lịch sử mới. [Chi tiết bản sửa](rule_authority_history.md).

**Cập nhật sau sửa R4 (16/10/2026):** đã bổ sung sự kiện sau đóng lô cho P1/A1–A4, nối vào hàng đợi và UI mà không sửa điểm/hit từng dòng. Toàn bộ **227/227 test đạt** tại lần chốt R4, gồm 18 test mới. [Đặc tả, artifact và giới hạn](rule_batch_close.md).

**Cập nhật sau sửa R5 (16/10/2026):** hai bảng quyền/coverage C2/C3 đã từ chối boolean, enum, số và thời gian sai trước khi chấm. Toàn bộ **247/247 test đạt tại lần chốt R5**, gồm 20 test mới. [Miền giá trị, đối chứng và giới hạn](rule_authority_validation.md).

**Snapshot kiểm tra mở rộng sau R5, trước sửa R2 (16/10/2026):** chạy riêng 7 ca mong muốn; **7 ca chưa đạt, 0 lỗi chạy test**, 0,635 giây. Ba ca xác nhận R2/R6 còn mở tại thời điểm đó; bốn ca bổ sung xác nhận R7/R8 bên dưới. Chưa sửa detector hoặc chạy lại toàn bộ hồi quy trong lần đánh giá đó; 247 test ở trên là mốc lần chốt R5, không bao gồm 7 probe mới. [Mã tái hiện](../.runtime/readiness_followup_20261016/test_remaining_risks.py), [quan sát từng ca](../.runtime/readiness_followup_20261016/observations.json), [kết quả và hash nguồn](../.runtime/readiness_followup_20261016/result.json).

**Cập nhật sau sửa R2 (16/10/2026):** đã thống nhất ngân hàng + TK cho A1/A2, B7/callback và feature; thêm binding bất biến cho sự kiện đổi TK và trạng thái thiếu mã ngân hàng. **268/268 test hồi quy đạt tại lần chốt R2**, gồm 21 test mới. Khi đó bản sao 7 probe cũ có 2 ca R2 đạt, 5 ca R6/R7/R8 chưa đạt. [Chi tiết, nguồn mẫu và giới hạn](rule_bank_identity.md).

**Cập nhật sau sửa R8 (16/10/2026):** E1 tra người ký tại `approved_at`, B7 và feature tra tại `verified_at`; đã xử lý các đường lịch ca/chứng từ/ngoại lệ/F1 có ca tái hiện và dùng chung chỉ mục nhân sự. **292/292 test đạt**, gồm 24 test mới. Bản sao 7 probe readiness: 4 ca R2/R8 đạt, 3 ca R6/R7 chưa đạt. [Mốc thời gian, đối chứng và giới hạn nguồn](rule_signer_history.md).

**Cập nhật sau sửa R7 (16/10/2026):** đã kiểm định nguồn cấp ngoại lệ trước feature/chấm luật, từ chối cờ ngoài 0/1, enum/số/ngày giờ sai; sửa chronology callback trong fixture/generator. **319/319 test đạt**, gồm 27 test mới. Bản sao probe: 6 ca R2/R7/R8 đạt, 1 ca R6 chưa đạt. [Hợp đồng và giới hạn nguồn cũ](rule_exception_validation.md).

**Cập nhật sau sửa R6 (16/10/2026):** đã chuẩn hóa khóa cụm theo thành viên tại thời điểm quan sát, chọn owner ổn định và ánh xạ hồ sơ tương đương khi nạp lại. Giữ nhật ký gốc/admissions; split/merge hoặc đổi bằng chứng không thừa hưởng kết luận đóng hồ sơ. **341/341 test đạt**, gồm 22 test mới; **7/7 probe đạt**. [Chính sách migration và giới hạn](rule_case_identity.md).

Đợt audit ban đầu chỉ kiểm tra mã và khả năng sử dụng, không thay ngưỡng, trọng số, mã detector hoặc dữ liệu nghiệp vụ; kết quả 191/9 ca dưới đây là snapshot trước các bản sửa R1/R3/R4/R5. Không huấn luyện/chấm ML và không chấm lại các tập benchmark lớn. Các số precision bên dưới là kết quả lịch sử được dẫn nguồn, không phải kết quả benchmark mới.

## Bằng chứng kiểm tra

- Chạy lại bộ kiểm thử hiện có: **191/191 đạt**, 42,001 giây.
- Bổ sung **9 ca kiểm tra biên** bên ngoài thư mục `tests`: **9 ca không đạt hành vi mong muốn**, không có lỗi chạy test. Trong đó 7 ca thuộc 5 nhóm lỗi kỹ thuật; 2 ca cùng timestamp thể hiện khoảng trống của chính sách hiện tại.
- [Mã ca tái hiện](../.runtime/readiness_recheck_20261016/test_readiness_edges.py), [log lần chạy cuối](../.runtime/readiness_recheck_20261016/audit_probes_final.log), [kết quả và hash mã nguồn](../.runtime/readiness_recheck_20261016/result.json).

Các ca bổ sung ban đầu cố ý mô tả hành vi cần đạt và được giữ làm snapshot lịch sử. Các bản sửa đã có hồi quy chính thức theo đường dẫn riêng ở từng mục; R4 kiểm tra sự kiện lô thay cho yêu cầu có hit theo dòng.

## Danh sách cần sửa

| Mã | Ưu tiên | Phát hiện đã tái hiện | Việc cần sửa |
| --- | --- | --- | --- |
| R1 | Đã sửa kỹ thuật | P1 từng gộp các hóa đơn không có số; đồng thời bỏ qua thanh toán tiền mặt không có TK nhận | Đã kiểm tra định danh, tách P1 khỏi điều kiện có TK nhận; [198 test đạt](rule_p1_payments.md) |
| R2 | Đã sửa kỹ thuật | A1/B7 từng coi cùng số TK ở hai ngân hàng khác nhau là cùng TK | Đã thống nhất A1/A2, B7/callback, feature và binding nguồn; thiếu ngân hàng ghi gap; [268 test đạt](rule_bank_identity.md) |
| R3 | Đã sửa kỹ thuật | C2 từng mất ngoại lệ hợp lệ sau revision chỉ đổi tên; C3 cũng dùng nhân sự lúc ghi sổ | Đã tra nhân sự theo ngày ký/hành động, gồm fallback C2; [209 test đạt](rule_authority_history.md) |
| R4 | Đã sửa kỹ thuật | Cùng timestamp từng không có kiểm tra tổng lô cho P1/A1 | Đã kiểm tra đóng lô P1/A1–A4, nối hàng đợi/UI và giữ điểm dòng; [227 test đạt](rule_batch_close.md) |
| R5 | Đã sửa kỹ thuật | `self_approval_allowed=2` từng được chấp nhận thay vì từ chối dữ liệu sai | Đã kiểm định boolean/enum/số/ngày giờ cho quyền và coverage trước khi chấm; [247 test đạt](rule_authority_validation.md) |
| R6 | Đã sửa kỹ thuật | Root UnionFind từng làm ID đổi theo thứ tự nguồn | Khóa cụm theo thành viên, owner ổn định, alias tương đương và lịch sử tách/gộp; [341 test đạt](rule_case_identity.md) |
| R7 | Đã sửa kỹ thuật | E1/B7 từng coi cờ `2` là bằng chứng hợp lệ | Đã kiểm định miền giá trị trước feature/chấm luật, gồm nguồn HR/workflow/chi tiền; [319 test đạt](rule_exception_validation.md) |
| R8 | Đã sửa kỹ thuật | Snapshot đổi tên người ký từng làm E1/B7 từ 0 thành 20 điểm cứng | Đã tra đúng ngày ký/callback, đồng bộ feature và các helper có ca tái hiện; [292 test đạt](rule_signer_history.md) |

### R1 — định danh và phạm vi P1

**Trạng thái: đã sửa mã và bổ sung hồi quy.** Mô tả dưới đây là ca tái hiện trước sửa; hành vi hiện tại và giới hạn tại [rule_p1_payments.md](rule_p1_payments.md).

Hai khoản 9 triệu, mỗi khoản khai gross 9 triệu nhưng `invoice_number=''`, bị cộng vào cùng khóa `(company, vendor, '')`; khoản thứ hai nhận **P1 20 điểm, hard trigger**. Thiếu số hóa đơn không chứng minh hai khoản thuộc cùng hóa đơn. Cần dùng khóa hóa đơn chuẩn đã đối soát; khi chưa đủ định danh thì ghi thiếu dữ kiện thay vì tự gộp khóa rỗng.

Ở chiều ngược lại, hai lần trả 9 triệu cho cùng hóa đơn 9 triệu, khác ngày, `payment_channel=cash`, Có 111 và không có tài khoản nhận, **không có P1**. Nguyên nhân: cả khối kiểm tra hóa đơn nằm dưới `if payment and recipient`.

Vị trí: [điều kiện đầu khối](../sme_fraud/rules.py#L476), [khóa hóa đơn](../sme_fraud/rules.py#L484), [predicate P1](../sme_fraud/rules.py#L562). Hai ca: `test_missing_invoice_number_is_not_a_shared_invoice`, `test_cash_invoice_overpayment_does_not_require_a_bank_account`.

Cần tách phạm vi kiểm tra hạn mức theo người nhận khỏi kiểm tra nghĩa vụ hóa đơn. Giữ khả năng nhận ra cùng hóa đơn thật dù có nhiều mã ERP; không chỉ đổi khóa sang `invoice_id` một cách máy móc.

### R2 — định danh tài khoản chưa thống nhất

**Trạng thái: đã sửa và bổ sung 21 test hồi quy.** Mô tả dưới đây là ca tái hiện trước sửa; hai probe R2 đã đạt, xem [rule_bank_identity.md](rule_bank_identity.md) về hành vi hiện tại, binding callback, dữ liệu thiếu và cache feature.

Hai NCC nhận 9 triệu/ngày vào cùng chuỗi `0123456789` nhưng có `recipient_bank_code` khác nhau vẫn tạo **A1 8 điểm**. Một sự kiện đổi TK ở `BANK_A` cũng tạo **B7 20 điểm, hard trigger** khi khoản chi thực tế đến cùng số TK ở `BANK_B`.

Vị trí: [khóa người nhận A1/A2](../sme_fraud/rules.py#L458), [lưu lịch sử](../sme_fraud/rules.py#L796), [đối chiếu B7](../sme_fraud/temporal_evidence.py#L56). Hai ca: `test_different_banks_do_not_share_a_recipient`, `test_bank_change_for_other_bank_is_not_a_payment_match`.

B1 và đồ thị đã có `bank_identity`, nhưng A1/A2 và B7 chưa dùng thống nhất. Cần bổ sung định danh ngân hàng cho nguồn đổi TK, khóa lịch sử và bằng chứng callback; rà cả feature dùng chung. Nguồn TK thực thiếu ngân hàng cần có trạng thái chưa xác nhận rõ ràng. Chính sách giữ cảnh báo khi thiếu hồ sơ nghĩa vụ chi vẫn là quyết định nghiệp vụ hiện hành; không tự thay đổi chính sách đó để che lỗi ghép TK.

### R3 — phiên bản nhân sự làm vô hiệu bằng chứng cũ

**Trạng thái: đã sửa C2/C3 và bổ sung hồi quy.** Mô tả dưới đây là ca tái hiện trước sửa; hành vi hiện tại, đối chứng C3 và giới hạn tại [rule_authority_history.md](rule_authority_history.md).

Ca tự duyệt 9 triệu có coverage và quyền đã duyệt hợp lệ ban đầu có **C2 0 điểm**. Chỉ thêm snapshot nhân sự đổi tên giám đốc, quan sát sau ngày phê duyệt ma trận nhưng trước giao dịch, kết quả thành **C2 20 điểm, hard trigger**.

`ApprovalAuthority` nhận `staff` hiện tại lúc ghi sổ. `approved_evidence` so `recorded_at` của snapshot hiện tại với ngày phê duyệt cũ, nên bản cập nhật thông thường làm coverage/quyền bị coi là chưa hợp lệ. C3 dùng cùng đường xác minh và cũng cần được kiểm tra; ca tái hiện trực tiếp lần này là C2.

Vị trí: [xác minh thẩm quyền](../sme_fraud/authority_policy.py#L90), [điều kiện nhân sự](../sme_fraud/temporal_evidence.py#L71). Ca: `test_master_revision_does_not_cancel_old_authority_approval`.

Cần tra người phê duyệt bằng chứng tại `record.approved_at`; tra vai trò người thực hiện tại thời điểm duyệt giao dịch. Rà tiếp E1/B7 và các helper còn nhận `staff` hiện tại để bảo đảm cùng nguyên tắc.

### R4 — khoảng trống có chủ đích với giao dịch đồng thời

**Trạng thái: đã bổ sung kiểm tra sau đóng lô.** Các tình huống dưới đây mô tả trước sửa; hiện P1/A1–A4 có sự kiện lô riêng, được kiểm tra bằng [hồi quy và đặc tả mới](rule_batch_close.md).

Hai khoản cùng timestamp trả tổng 18 triệu cho hóa đơn 9 triệu **không có P1**. Hai khoản cùng timestamp, mỗi khoản 9 triệu, hạn mức 20 triệu **không có A1**. Cả hai chỉ thấy lịch sử trước batch; sau commit chưa có phát hiện tổng lô.

Đây là **giới hạn thiết kế đang được test cũ bảo vệ**, không phải lỗi hồi quy mới: [test hiện hành](../tests/test_rules.py#L36), [commit cuối batch](../sme_fraud/rules.py#L786). Hai ca audit: `test_simultaneous_invoice_overpayment_is_detected`, `test_simultaneous_split_is_detected`.

Bản sửa giữ bất biến điểm/feature theo dòng và thêm sự kiện ở lúc đóng lô, không dùng thứ tự ID để giả lập thứ tự xảy ra. A2/A3/A4 cũng có đối chứng lô. Hai probe audit gốc được giữ làm lịch sử; hồi quy chính thức kiểm tra `batch_events` theo đặc tả đã chọn.

### R5 — giá trị quyền sai vẫn được dùng cấp ngoại lệ

**Trạng thái: đã sửa hai bảng quyền/coverage C2/C3 và bổ sung hồi quy.** Mô tả dưới đây là ca tái hiện trước sửa; hành vi hiện tại và phạm vi kiểm định tại [rule_authority_validation.md](rule_authority_validation.md).

Nguồn quyền có `self_approval_allowed=2` không bị từ chối; phép chuyển `bool(_integer(...))` coi giá trị này là đúng. Kiểm tra hiện tại chủ yếu bảo đảm có cột/ID và không mâu thuẫn revision, chưa kiểm tra chặt miền giá trị.

Vị trí: [nạp revision](../sme_fraud/authority_policy.py#L36), [chuyển boolean](../sme_fraud/authority_policy.py#L168). Ca: `test_invalid_boolean_cannot_grant_self_approval`.

Cần từ chối boolean ngoài 0/1, enum không hợp lệ, số không hợp lệ và khoảng hiệu lực đảo ngược trước khi chấm; bổ sung kiểm tra nhất quán cho coverage và các nguồn cấp ngoại lệ. Schema mô tả và checksum không tự bảo đảm nội dung nguồn hợp lệ.

### R6 — ID hồ sơ phụ thuộc thứ tự nguồn

**Trạng thái: đã sửa và bổ sung 22 test hồi quy.** Probe đảo nguồn đã đạt, có đối chứng migration phản hồi/phân công và split/merge; [định danh, ánh xạ và hướng áp dụng](rule_case_identity.md). Mô tả và tiêu chí bên dưới là phát hiện trước sửa.

Cùng dữ liệu và giao dịch, chỉ đảo thứ tự bảng NCC có các snapshot cùng timestamp, root cụm đổi từ `entity:V0000013` sang `entity:V0000015`. ID hàng đợi thực tế đổi từ **`RC_8991c3826efb5d65`** sang **`RC_29e63b58497be224`**.

Vị trí: [dựng lại cụm](../sme_fraud/rules.py#L227), [lấy root làm case_entity](../sme_fraud/rules.py#L776), [tạo ID hồ sơ](../sme_fraud/case_queue.py#L69). Ca: `test_reordering_same_timestamp_masters_preserves_case_identity`.

Cần chuẩn hóa thứ tự cạnh và dùng định danh cụm ổn định cho các đầu vào tương đương. Việc cụm thật sự đổi theo thời gian cần có chính sách phiên bản/ánh xạ riêng. Nếu tiếp tục lấy root theo thứ tự nhập, chạy lại cùng dữ liệu có thể tách liên kết với kết luận/việc phân công cũ.

**Tiêu chí đóng R6:** dùng khóa cụm chuẩn độc lập root UnionFind, không đưa dữ liệu tương lai vào định danh. Đối chứng các phép đảo nguồn và replay trên cùng snapshot phải giữ hit/điểm/thành viên/ID hồ sơ. Khi cụm thật sự tách/gộp, cần chính sách phiên bản/ánh xạ riêng; đối chiếu với hồ sơ đã lưu trước khi nạp lại để giữ đúng liên kết phản hồi và phân công. Chưa coi tác động lên database phản hồi là lỗi mất dữ liệu đã được tái hiện; ca đã xác nhận hiện tại là ID thay đổi.

### R7 — kiểm định quyền chưa phủ các nguồn ngoại lệ khác

**Trạng thái: đã sửa và bổ sung 27 test hồi quy.** Hai probe E1/B7 đã đạt; [hợp đồng chung, phạm vi kiểm định và xử lý nguồn cũ](rule_exception_validation.md). Mô tả/tiêu chí bên dưới ghi lại phát hiện trước sửa.

R5 đã kiểm định hai bảng quyền/coverage C2/C3; helper bằng chứng dùng chung chưa có cùng bảo đảm. Ca nghỉ hưởng lương có `payroll_entitlements.evidence_on_file=2` vẫn được E1 coi là ngoại lệ hợp lệ, **0 điểm/không hard trigger**. Sự kiện đổi TK có `bank_account_changes.callback_verified=2` cũng được B7 coi đã xác minh, **0 điểm/không hard trigger**. Các ca yêu cầu từ chối nguồn sai đều không đạt; không có `ValueError`.

Vị trí: [`approved_evidence` và đường đối chiếu callback](../sme_fraud/temporal_evidence.py) còn dùng `int(flag)` như điều kiện boolean. `PaymentEvidence` và `EvidenceBook` còn chủ yếu kiểm tra cột/ID/revision, chưa có validator miền giá trị tương đương R5 cho mọi trường.

Cần hợp đồng kiểm định chung cho các nguồn cấp ngoại lệ: cờ 0/1, enum, số VND/ngày công, ngày giờ/khoảng hiệu lực; đối soát binding và công ty đúng trường hợp. Nguồn sai phải bị từ chối hoặc cách ly có trạng thái rõ ràng trước khi xét ngoại lệ. Hai ca đã xác nhận trực tiếp là E1/B7; các nguồn còn lại cần rà và thêm đối chứng, chưa khẳng định tất cả đều tái hiện cùng lỗi.

**Tiêu chí đóng R7:**

- Kiểm định trước khi dùng nguồn để cấp ngoại lệ; không dùng ép kiểu có giá trị mặc định để làm dữ liệu sai trở thành hợp lệ, không âm thầm chuyển nguồn sai sang fallback. Cờ 0 hợp lệ nhưng không xác minh phải tiếp tục không cấp ngoại lệ.
- Thêm đối chứng native/CSV cho 0/1 hợp lệ, cờ 2/-1/rỗng/sai kiểu; enum lạ, số thực/NaN/Infinity, ngày giờ sai, khoảng đảo ngược và các quan hệ thời gian theo từng nguồn. Fixture/generator cũng cần tuân thủ cùng hợp đồng, không chỉnh kỳ vọng chỉ để bỏ qua dữ liệu sai.
- Hai probe R7 đã có phải đạt; giữ hồi quy source revision, thu hồi, nguồn tương lai, độc lập, ngân hàng R2 và lịch sử người ký R8. Các nguồn khác chỉ ghi là lỗi đã xác nhận sau khi có ca tái hiện.

### R8 — lịch sử người ký chưa thống nhất ngoài C2/C3

**Trạng thái: đã sửa và bổ sung 24 test hồi quy.** Mô tả dưới đây là ca tái hiện trước sửa; hai probe E1/B7 đã đạt, cùng các đối chứng helper tại [rule_signer_history.md](rule_signer_history.md).

Ca E1 có nghỉ hưởng lương và ca B7 có callback độc lập hợp lệ đều bắt đầu ở **0 điểm, không hard trigger**. Chỉ thêm snapshot người ký đổi `full_name`, `recorded_at` sau lúc ký và trước giao dịch, cả hai trở thành **20 điểm, hard trigger**. Quyền, chứng từ, công ty và vai trò không thay đổi.

Đường gọi E1/B7 vẫn truyền `staff` hiện tại lúc ghi sổ cho helper xác minh. Snapshot mới có `recorded_at` sau ngày ký khiến chứng từ hợp lệ bị coi là chưa hợp lệ. R3 đã khắc phục C2/C3; không phải R3 hồi quy, mà là phạm vi dùng helper lịch sử chưa đồng nhất.

Cần chọn snapshot người ký tại `approved_at` cho E1, `verified_at` cho callback B7; kiểm tra độc lập và công ty theo đúng thời điểm. Feature ngân hàng phải dùng cùng nguyên tắc với rule. Rà các helper lịch ca/chứng từ/ngoại lệ còn nhận master hiện tại; chỉ nâng thành phát hiện đã xác nhận khi có ca tái hiện.

## Khi lớp tất định là phần chính của agent2

Trong mã hiện tại, [hàng đợi](../sme_fraud/run_rules.py#L78) được dựng từ kết quả luật trước khi tính ensemble. Công thức [80% rule/graph + 20% Isolation Forest](../sme_fraud/run_rules.py#L123) nằm trong bước so sánh benchmark, dùng thứ hạng tham chiếu validation. Tỷ lệ này là trọng số thiết kế của phép gộp điểm; không chứng minh 80% recall, độ chính xác hoặc mức hoàn thiện. Các sự kiện đóng lô đi qua hàng đợi riêng; benchmark theo điểm từng dòng chưa tự nhận điểm của sự kiện lô.

Ưu tiên hiện tại là hoàn thiện cơ chế dùng chung và kiểm chứng, rồi bổ sung luật theo mẫu gian lận chưa được bao phủ có bằng chứng độc lập. Không tăng số luật hay siết ngưỡng đồng loạt dựa trên lượng cảnh báo. Lộ trình đề xuất:

1. R1–R8 đã sửa kỹ thuật; khi đưa queue mới vào bộ rà soát đang có, chạy migration R6 với cache/nhật ký cũ được giữ lại. Không xem alias tương đương là quyền chuyển kết luận sang cụm đã đổi phạm vi.
2. Thống nhất định danh, validator và tra nguồn theo thời điểm giữa rule, feature, kiểm tra lô và bằng chứng. Giữ phân biệt **đã kiểm tra không thấy vi phạm**, **thiếu nguồn** và **nguồn không hợp lệ** theo từng rule/công ty.
3. Kiểm tra replay/tính bất biến khi đảo nguồn, nạp trùng và thêm revision tương lai. Chốt hợp đồng cho giao dịch hoàn/hủy/đảo, nhiều TK đồng thời và mapping ERP theo dữ liệu thật trước khi tuyên bố hỗ trợ; lần này chưa kiểm định các nhánh đó.
4. **Đã chấm kết hợp train/validation ngày 17/10/2026** tại [báo cáo đồng bộ](rule_feature_model_sync.md), có trace từng ID/điểm/hit, loại gian lận/hard negatives, hồ sơ, từng rule/công ty và tải rà soát. Rà các ca mất cảnh báo chia nhỏ trước khi chốt chính sách; các mốc precision lịch sử bên dưới chỉ là snapshot cũ.
5. Nghiệm thu nguồn SME thật và kết luận độc lập. Khi dùng ensemble cho vận hành, chốt chính sách ưu tiên hard trigger, thứ hạng tín hiệu mềm và ngân sách hồ sơ; kiểm thử để điểm ML không làm mất hồ sơ luật cứng cần rà soát. Đây là yêu cầu thiết kế tiếp theo, chưa phải lỗi triệt tiêu hard trigger đã được tái hiện trong hàng đợi hiện tại.

## Các việc cần hoàn thành ngoài sửa predicate

**Nghiệm thu dữ liệu thật vẫn chưa đạt.** [Báo cáo nguồn hiện tại](rule_repairs/real_source_acceptance/summary_vi.md) ghi F1/C4/E2/F2/F3/F4 đều `awaiting_real_data`, có **0 đơn vị chấm mù**, chính sách ngưỡng `not_frozen`. Cần nạp nguồn ERP/HR/công nợ có coverage, khóa tiêu chí trước review, rồi nghiệm thu bằng kết luận độc lập. Cổng hiện có chỉ bao phủ sáu rule này; cần bằng chứng sử dụng thật cho các rule cứng còn lại trước khi kết luận toàn lớp đã đạt.

**Nhiễu vận hành còn đáng kể.** [Benchmark phase 4 đã có](rule_repairs/phase4/summary_vi.md) ở tỷ lệ mô phỏng 0,3% ghi 34 TP/196 FP và 35 TP/161 FP, precision **14,78%–17,86%** theo dòng cảnh báo. Các sửa gần đây chấm lại train/validation trên nguồn mới còn rỗng nên hàng đợi không đổi; đó là kiểm tra tương thích, chưa chứng minh giảm FP. FP theo nhãn gian lận mô phỏng không đồng nghĩa mọi predicate tương ứng đều sai.

Cần đo cả điều kiện rule và kết luận rà soát, precision/recall theo rule, số hồ sơ và thời gian xử lý theo doanh nghiệp/ngày, information gap và khoảng bất định. Hiệu chỉnh trên train/validation; nghiệm thu trên tập mới giữ kín. Không tự tắt rule hoặc hạ ngưỡng theo số FP này.

Nguồn đồ thị còn giới hạn một giá trị hiện hành cho mỗi source/type và hiệu lực theo thời điểm quan sát, như [báo cáo lịch sử đồ thị](rule_graph_history.md) đã nêu. Nếu nguồn thật có nhiều TK/đại diện đồng thời hoặc hiệu lực tương lai riêng, phải mở rộng hợp đồng dữ liệu trước khi nhập.

## Điều kiện kiểm tra lại sau sửa

1. Các ca R1/R2/R3/R5/R6/R7/R8 đạt; R4 có đặc tả phát hiện sau batch và đối chứng phù hợp, vẫn giữ tính nhân quả của điểm quá khứ.
2. Bộ kiểm thử hiện có tiếp tục đạt; thêm các ca mới vào hồi quy chính thức cùng bản sửa.
3. Chấm lại train/validation để đối chiếu tập hit, điểm, hàng đợi và ID hồ sơ; giải thích được mọi thay đổi. Không cộng delta từng rule thay cho kiểm tra kết hợp.
4. Kiểm thử nạp dữ liệu thật: thiếu định danh, khác ngân hàng, revision, dữ liệu sai, chi tiền mặt, nhiều khoản cùng timestamp và thứ tự nguồn khác nhau.
5. Nghiệm thu nguồn/nhãn độc lập và tải rà soát thực tế trước khi công bố lớp luật đủ sẵn sàng vận hành.
