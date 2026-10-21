# Việc tiếp theo sau Rule Audit

**Ưu tiên hiện tại sau sửa export, 17/10/2026:** checkpoint **437 test/7 probe đạt**. Export lý do dòng/lô đã hoàn tất kỹ thuật; còn review bản thử A4/công sức, replay ưu tiên theo sự kiện và nguồn thật. Xem [bản sửa export](rule_admission_export.md), [việc cần sửa tiếp](rule_readiness_next_20261017.md). Không đổi ngưỡng hoặc chính sách giữ cảnh báo khi thiếu nghĩa vụ chi.

**Nguồn mô phỏng mới:** đã sinh 62.182 giao dịch trên ba seed, đủ nguồn F1/C4/E2/F2/F3/F4; hai bộ reporting khớp 1.216/1.216 kỳ vọng nguồn, một bộ holdout chưa chấm. Có mapping minh họa, hai SQLite và diễn tập R6 riêng; nguồn thật/reviewer độc lập vẫn còn thiếu. [Bộ dữ liệu và giới hạn](rule_synthetic_source_readiness.md).

## Thứ tự công việc cần xử lý

Lượt [checkpoint A4](../.runtime/a4_pattern_trial_20261017/result.json) trước đó đạt 412 test/7 probe; mặc định replay đúng queue cũ, bản thử giữ nguyên tập giao dịch/TP/FP, có kiểm tra cache và bảo vệ nguồn/model/SQLite. Lượt export mới đạt 437 test/7 probe, đối chiếu đủ ID và bằng chứng trong thư mục bổ sung. Các artifact trước giữ nguyên; chưa chuyển database/feedback vận hành cũ.

| Ưu tiên | Công việc | Kết quả cần có |
| --- | --- | --- |
| Đã hoàn tất kỹ thuật | **Đồng bộ cache/model và chấm kết hợp** | Đã dựng/chấm 225.000 dòng train/validation, replay model/cache và SQLite; có đối chiếu ID/điểm/hit/hồ sơ trước/sau tiếp nhận |
| Đã sửa kỹ thuật | **Thống nhất công suất** | Dùng chung hợp đồng lượt/phút giữa simulator/API, tách tên cấu hình nghiên cứu/UI, có lịch/tồn cuối kỳ và thời gian xử lý tồn; đã replay 120 tổ hợp trên sáu snapshot |
| Đã sửa kỹ thuật | **Hoàn thiện export** | Đã xuất CSV v2/JSONL, truy được đủ 3.315 ID mới tới hit/lô/case; membership/điểm/cờ và report đã khóa giữ nguyên |
| 2 — có bản thử, chưa đóng | **Review hồ sơ mẫu A4** | 5.538 → 4.774 hồ sơ thử, cùng tập giao dịch; 905 gói reviewer, 0 xác nhận. Cần đo việc rà trùng/phút thực tế và xử lý mẫu vượt công suất khi giữ tổng phút |
| 3 | **Replay ưu tiên theo sự kiện** | Mô phỏng cập nhật hồ sơ đang chờ từ sự kiện đã biết, chốt chính sách tái rà khi bằng chứng đổi; không lấy ưu tiên cuối snapshot cho quá khứ |
| Song song, bắt buộc trước nghiệm thu | **Nguồn thật và chất lượng vận hành** | Coverage nguồn, tiêu chí khóa trước review, kết luận độc lập và tập nghiệm thu mới giữ kín. Hiện cổng nghiệm thu vẫn có 0 đơn vị chấm mù |
| Khi triển khai bộ rà soát cũ | **Migration R6** | Dùng snapshot/audit cũ đúng phiên bản; chỉ chuyển phản hồi/phân công tương đương một-một, hồ sơ đổi phạm vi phải rà lại |

Các lỗi R1–R8 đã sửa kỹ thuật trong phạm vi từng bản. Những việc còn mở không được xem là hoàn thành nhờ 412 test qua. Nguồn thật có thể chuẩn bị song song; số lượng luật và ngưỡng chỉ điều chỉnh khi có bằng chứng về mẫu còn thiếu hoặc tải cảnh báo.

Danh sách dưới dựa trên [audit baseline](rule_audit/summary_vi.md). **Đợt 1 đã sửa B7/E1/A2**: xem [logic, nguồn bằng chứng và kiểm thử](rule_repairs_phase1.md), [kết quả chấm lại](rule_repairs/phase1/summary_vi.md). Ngưỡng vận hành giữ nguyên. Ưu tiên hoàn thiện kiểm soát và giảm cảnh báo sai trước khi phát triển ML tiếp.

**Đợt 2 đã triển khai xử lý nguồn nhiễu và phân vai điểm**: [thiết kế và nguồn mới](rule_repairs_phase2.md), [validation/test sau sửa](rule_repairs/phase2/summary_vi.md). Số liệu trong bảng dưới vẫn là mốc audit trước sửa. Các nguồn lịch ca/PO/chứng từ còn thiếu trong dataset gốc; kết quả không thay thế nghiệm thu trên dữ liệu SME thật.

## 1. Đã sửa lỗi thời gian và ngoại lệ đã tái hiện

| Rule | Phát hiện | Hướng sửa | Kiểm tra bắt buộc |
| --- | --- | --- | --- |
| B7 | Sự kiện đổi TK quan sát trước ngày hiệu lực bị mất khi có giao dịch ở giữa hai mốc | Giữ sự kiện chờ hiệu lực; xử lý phiên bản/as-of thống nhất với feature | Cảnh báo sau hiệu lực, không cảnh báo trước; callback độc lập hợp lệ vẫn loại; dữ liệu tương lai không đổi kết quả quá khứ |
| E1 | Nghỉ hưởng lương đã duyệt vẫn bị gắn cờ lương ma | Đọc loại nghỉ/quyền hưởng lương, kỳ công và ngày quan sát; thêm ngoại lệ có bằng chứng | Nghỉ hưởng lương và làm việc từ xa hợp lệ không hard trigger; mẫu ghost payroll vẫn phát hiện; thiếu chấm công không tự quy thành 0 ngày |
| A2 | Ngoại lệ trả góp dùng cửa sổ A1; ba đợt cách nhau 7 ngày bị gắn cờ | Đối chiếu cùng hóa đơn/hợp đồng trên cửa sổ tương ứng và tổng tiền đã trả | Trả góp chưa vượt gross có hồ sơ được loại; trả trùng/vượt tổng vẫn giữ P1; hóa đơn độc lập không được tự gọi là trả góp |

E1 cần nguồn nghỉ phép và quyền hưởng lương rõ ràng; chỉ có tổng số ngày nghỉ trong tháng chưa đủ triển khai mọi ngoại lệ thực tế.

Ba lỗi trên đã khớp đối chứng sau sửa. E1 bổ sung nguồn `payroll_entitlements` đã duyệt/as-of; A2 hỗ trợ thỏa thuận `supplier_payment_agreements`. Dataset gốc không được tự điền hồ sơ HR/hợp đồng. Các số liệu ở phần 2 vẫn là mốc audit trước sửa; số liệu mới ở báo cáo đợt 1.

## 2. Đã triển khai xử lý nguồn nhiễu và cơ chế cộng điểm

Số liệu dưới đây là **test 0,3%**, còn thứ tự tối ưu nên căn cứ validation và kỳ vọng nghiệp vụ. FP là theo nhãn gian lận mô phỏng; không phải mọi trường hợp đều là lỗi predicate.

| Rule | Phát hiện audit | Việc nên làm |
| --- | --- | --- |
| E3 | 12.625 FP; hit trên toàn bộ dòng có NCC; tất cả 2.043 tên NCC cùng tiền tố giả lập | Đánh giá lại chất lượng/tính đại diện của tên master; thử tên thật hoặc tập tên đa dạng độc lập, tên gần giống hợp lệ và biến thể cố ý. Tách kiểm tra master khỏi cảnh báo giao dịch cứng |
| C1 | 10.372 FP; 78/96 giao dịch weekend_operations vẫn có hit | Đọc lịch ca và thời điểm lập/duyệt riêng. Giữ ngữ cảnh, thử chính sách kết hợp cần bằng chứng độc lập trước khi đẩy hồ sơ |
| A1/A2 | 392/148 FP; trả góp hợp lệ vẫn bị bắt 9/5 dòng | Liên kết yêu cầu chi/đơn hàng/hợp đồng; phân biệt nhiều hóa đơn độc lập với chủ đích chia nhỏ. Ngoại lệ phải gắn chứng từ cụ thể, không bỏ toàn bộ NCC |
| A5 | 931 FP; nền có đuôi phải dài và nhiều số tiền tròn | Đối chiếu baseline cùng nghiệp vụ/quy mô, kiểm tra chi định kỳ. Thử thay đổi baseline trên validation; chưa coi số tròn hoặc vượt 2 sigma là gian lận độc lập |
| B3 | 15 FP đều thuộc new_legitimate_vendor | Rà 15 hồ sơ: tiêu chí số lượng chứng từ/giao nhận đang bỏ sót ngoại lệ hợp lệ. Cần loại chứng từ và xác minh nội dung, thay vì chỉ đếm hồ sơ |
| B5/E4 | Hit trùng hoàn toàn: 1.154 dòng, 1.144 FP | Thống nhất một bằng chứng master, giữ mã rule để truy vết nếu cần. Địa chỉ văn phòng chung hoặc bên liên quan công bố cần phân loại riêng |

Bỏ riêng E3 ở validation giảm 465 FP nhưng cũng mất 2 TP; bỏ C1 giảm 364 FP nhưng mất 1 TP. Các kết quả này chưa đủ để quyết định tắt rule. B5/E4 đã chung nhóm điểm nên bỏ một rule riêng không làm giảm điểm; chồng lặp vẫn gây nhiễu khi đọc bằng chứng.

## 3. Đã triển khai thống nhất các điểm khác mô tả

[Chính sách và nguồn dữ liệu đợt 3](rule_repairs_phase3.md), [kết quả chấm lại](rule_repairs/phase3/summary_vi.md). Engine mặc định `spec_policy=phase3`; runner/fixture lịch sử ghim `legacy` để giữ đối chứng cũ. Các mục dưới là yêu cầu ban đầu; quyết định triển khai được ghi ngay sau bảng.

- **A3:** bổ sung hoặc ghi rõ việc chưa hỗ trợ nhánh 2 khoản/3 ngày/85% hạn mức. Địa chỉ đơn lẻ là liên kết yếu, cần bối cảnh trước khi gom.
- **A4:** chọn tháng lịch hay 30 ngày trượt; sửa mô tả và đối chứng theo chính sách đã chọn. Kiểm tra lương/chi định kỳ hợp lệ cận hạn mức.
- **A5:** xác nhận chỉ xét đuôi cao hay độ lệch hai phía. Không tự mở rộng đuôi thấp trước khi làm rõ mục tiêu nghiệp vụ.
- **B1:** xác nhận kiểm tra toàn master hay chỉ khoản chi NCC; bổ sung các khoản thuê/chi bán hàng nhận qua ngân hàng, mã ngân hàng và CCCD nếu có nguồn.
- **B3:** xác nhận “giao dịch đầu tiên” là lần mua/giao dịch kinh tế hay lần thanh toán tiền đầu tiên.
- **F1:** bổ sung dấu vết bút toán thủ công, lịch khóa sổ và mức trọng yếu được duyệt; hạn mức người lập chỉ là proxy hiện tại.

Các khác biệt có chủ đích như tự duyệt hợp lệ C2 và vận hành thứ Bảy C1 cần được cập nhật trong tài liệu rule để test không hiểu chúng là lỗi.

Đã bổ sung nhánh ngắn A3; A4 chọn tháng lịch và ngoại lệ có trần chi tháng; A5 giữ đuôi cao. B1 tách toàn master đã biết khỏi cảnh báo chi NCC, hỗ trợ thuê/chi bán hàng và nguồn ngân hàng/căn cước khi có. B3 dùng nghiệp vụ kinh tế đầu tiên trong lịch sử quan sát. F1 cần đủ ba nguồn xác nhận; proxy chưa đủ nguồn giữ 0 điểm. [Tài liệu rule](../rule_class_1.md) đã thống nhất C1/C2 và sáu định nghĩa trên. Nguồn mới vẫn thiếu trong dataset gốc, nên đây chưa phải xác nhận luật đã hoàn thiện trên SME thật.

## 4. Đã bổ sung cơ chế bằng chứng và đánh giá phần còn thiếu

Đợt 4: [schema/chính sách/giới hạn](rule_repairs_phase4.md), [kết quả source/window controls và seed mới](rule_repairs/phase4/summary_vi.md). Có 14 nguồn tùy chọn và CLI kiểm tra source theo cutoff; C4/E2/F2, F3 duplicates và F3 gaps/F4 aging được phân vai riêng. Các yêu cầu ban đầu dưới đây vẫn cần nguồn SME thật để nghiệm thu, không chỉ dữ liệu đối chứng.

C4 cần nghỉ phép theo ngày và log thao tác; E2 cần ngày nghỉ việc, kỳ lương và loại chi quyết toán; F2 cần log override/quy trình; F3 cần sổ đăng ký số chứng từ và nhật ký hủy; F4 cần ghép thu tiền–hóa đơn, hạn trả và giải trình công nợ.

A5/A6/B6/B7/C1/C3/E3 cần kịch bản dương độc lập phù hợp từng điều kiện. Hiện A6/B6/B7 không có hit hoạt động trong ba bộ; đó chưa phải bằng chứng rule hoàn thiện. D1–D6 cần nhãn can thiệp phân phối ở cấp cửa sổ; D3/D6 không có cửa sổ test đủ điều kiện, cần rà lại phân đoạn/quy mô trước khi đánh giá tác dụng.

Đã có 301 case nguồn/mẫu hình theo 7 seed; nhóm D có 56 thử nghiệm cửa sổ, 336 phép đối chiếu rule–scope–cutoff. Tập dense đủ D3/D6; dataset SME volume thấp vẫn được bỏ qua đúng chính sách. Sinh/chấm 350.000 dòng mới trên 1 seed validation và 2 seed test ở 0,1%–0,5%, báo cáo điểm góp/tín hiệu, hard negatives, khoảng bất định và ngân sách 1/3/5 hồ sơ/công ty/ngày. Không train/chấm ML. Dữ liệu SME thật, nguồn HR/ERP/thu tiền và kết luận rà soát độc lập vẫn chưa có.

## Tiêu chí kiểm tra sau sửa

Cập nhật A1/A2/A4: đã bổ sung bằng chứng ràng buộc yêu cầu chi–PO–hóa đơn, hợp đồng và lịch định kỳ, kiểm tra tổng toàn lịch sử/kỳ. Thiếu nguồn giữ cảnh báo theo quyết định nghiệp vụ; validation cũ không có nguồn nên không đổi hàng đợi. [Chi tiết và schema](rule_payment_evidence.md).

Cập nhật lịch sử đồ thị A3/B2: đã sửa thay thế/thu hồi cạnh và tách lại cụm; 151 test qua, chấm lại train/validation không đổi tập cảnh báo trên snapshot được đối chiếu. [Chi tiết và giới hạn nguồn](rule_graph_history.md).

Cập nhật thẩm quyền C2/C3 và B6: đã bổ sung coverage ma trận, quyền tự duyệt/ủy quyền theo phạm vi, cấp thẩm quyền thật của checker và lịch thanh toán năm/mùa có trần kỳ. Thiếu nguồn giữ fallback hiện tại; validation cũ không có nguồn nên không đổi hàng đợi. [Chi tiết và schema](rule_authority_dormancy.md).

Cập nhật P1 (16/10/2026): đã ngăn gộp hóa đơn thiếu số và kiểm tra vượt hóa đơn cho chi tiền mặt không có tài khoản nhận. Thiếu định danh ghi information_gap, 0 điểm, không hard trigger. 198/198 test đạt tại lần chốt R1; [chi tiết bản sửa và giới hạn](rule_p1_payments.md).

Cập nhật lịch sử nhân sự C2/C3 (16/10/2026): đã tra người ký bằng chứng tại ngày ký và vai trò/công ty người thực hiện tại lúc duyệt; C2 fallback dùng hạn mức tại lúc duyệt. 209/209 test đạt tại lần chốt R3; [chi tiết và giới hạn](rule_authority_history.md).

Cập nhật kiểm tra đóng lô (16/10/2026): đã phát hiện tổng vượt hóa đơn và chia nhỏ cùng timestamp bằng sự kiện lô P1/A1–A4, nối hàng đợi/UI và giữ nguyên điểm từng dòng. 227/227 test đạt tại lần chốt R4; [đặc tả và giới hạn](rule_batch_close.md).

Cập nhật kiểm định quyền R5 (16/10/2026): đã từ chối cờ boolean ngoài miền hợp lệ, enum sai, hạn mức và ngày giờ sai cho cả quyền/coverage C2/C3 trước khi chấm. Không còn ép `self_approval_allowed=2` thành có quyền. 247/247 test đạt tại lần chốt R5, gồm 20 test mới; [miền dữ liệu và đối chứng](rule_authority_validation.md).

Cập nhật định danh ngân hàng R2 (16/10/2026): đã sửa khóa lịch sử A1/A2, B7/callback, feature tài khoản và binding sự kiện đổi TK; nguồn thực thiếu mã ngân hàng ghi information_gap, không tự ghép. 268/268 test đạt tại lần chốt R2, gồm 21 test mới; [hướng dẫn dữ liệu/cache và đối chứng](rule_bank_identity.md).

Cập nhật lịch sử người ký R8 (16/10/2026): E1/B7 và feature chọn snapshot tại ngày ký/xác minh; đã xử lý các helper lịch ca, chứng từ/PO, ngoại lệ và F1 có ca tái hiện, giữ đối chứng C2/C3. 292/292 test đạt tại lần chốt R8; [chi tiết và 24 test mới](rule_signer_history.md).

Cập nhật kiểm định ngoại lệ R7 (16/10/2026): nguồn sai bị từ chối bằng lỗi bảng/ID/trường trước feature/chấm luật; E1/B7 không còn cấp ngoại lệ với cờ `2`. 319/319 test đạt tại lần chốt R7, gồm 27 test mới; [hợp đồng dữ liệu và lưu ý nguồn cũ](rule_exception_validation.md).

Cập nhật định danh hồ sơ R6 (16/10/2026): khóa cụm theo thành viên, owner theo thời điểm, migration hồ sơ tương đương giữ phản hồi/phân công/lượt nhận việc; hồ sơ tách/gộp đổi phạm vi phải rà lại. 341/341 test đạt, 7/7 probe đạt; [chính sách và cách áp dụng](rule_case_identity.md).

Cập nhật đồng bộ feature/model (17/10/2026): đã dựng lại **225.000 dòng train/validation** cho ba bộ chuẩn, fit lại ba IF, thêm kiểm tra provenance cache/model và nạp/replay artifact chính xác; dựng cache rà soát riêng cho **3.434 hồ sơ**. **352/352 test và 7/7 probe đạt**; chưa chấm test, chưa chuyển database/feedback vận hành cũ. Trên validation mô phỏng, **FP 2.737 → 1.208, TP 198 → 194**; cần ưu tiên rà mẫu chia nhỏ A2/A4 có hit nhưng chưa vào queue sau giảm nhiễu và A4 qua ranh giới tháng. Không tự siết/hạ ngưỡng toàn bộ. [Chi tiết, từng bộ và giới hạn nguồn](rule_feature_model_sync.md).

Cập nhật tiếp nhận mẫu chia nhỏ A2/A4 (17/10/2026): đã thêm chính sách nhận hồ sơ riêng cho hit còn hợp lệ, ở cả dòng đơn và đóng lô, giữ điểm 4/3, họ A lấy max, ngưỡng 7 và hard trigger. **373/373 test, 7/7 probe đạt**. Validation: **TP 194 → 200, FP 1.208 → 2.347**; tổng hồ sơ train/validation **3.434 → 5.538**. Khôi phục 5/6 dòng bị mất trước đó; ca A4 còn lại đúng tháng lịch, A1 bắt chuỗi ở khoản kế tiếp. Đã giữ ID bằng chứng E1/T1 ổn định khi đọc cache. Chưa nghiệm thu chất lượng/tải hoặc chuyển database vận hành. [Bản sửa và đánh đổi](rule_split_pattern_admission.md).

Chạy lại các fixture lệch và đối chứng hợp lệ, kiểm tra quan sát theo thời gian, đo TP/FP/hard negatives riêng từng rule và tác động toàn hàng đợi. Kiểm tra thay đổi kết hợp bằng đối chứng chung; không cộng delta bỏ từng rule.

Tối ưu trên train/validation; nghiệm thu trên test mới giữ kín, nhiều seed và dữ liệu SME thật có kết luận rà soát. Đánh giá precision cùng số mẫu/khoảng bất định, độ bao phủ từng kịch bản và ngân sách hồ sơ của kế toán. Sau khi các kiểm soát này đạt yêu cầu mới quay lại ML.

## Trạng thái nghiệm thu nguồn bổ sung

Đã có pipeline chấm mù và cổng nghiệm thu cho F1/C4/E2/F2/F3/F4 tại [rule_source_acceptance.md](rule_source_acceptance.md). Pipeline khóa prediction trước review, yêu cầu coverage nguồn thật theo công ty và kết luận của hai người độc lập. Các bộ trong workspace chưa có nguồn HR/ERP/công nợ SME thật nên sáu rule vẫn ở `awaiting_real_data`; 301/301 case phase 4 chỉ chứng minh conformance kỹ thuật.
