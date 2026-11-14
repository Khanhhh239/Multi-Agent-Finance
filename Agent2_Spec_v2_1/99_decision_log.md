# Decision log — nguồn chuẩn cho quyết định

### CR-053 — sửa reload Portal về sai doanh nghiệp

14/11/2026: người dùng chọn phát hiện QA cũ C002 có thể thành C001 sau reload.
Dùng preference theo tab/actor/context được kiểm lại bằng quyền hiện tại ở
parent và child; giữ cả màn hình, snapshot/cutoff đã lưu. Không sửa backend auth
hoặc lấy dữ liệu trình duyệt làm quyền. Thu hồi scope thì bỏ private view/run cũ;
không còn DN thì không mặc định C001. Có migration trạng thái nhập cũ và chặn
restore response muộn. 17 routing +12 workspace Chrome,22 HTTP auth đạt; live
5 asset200/no-store khớp source, không restart. Không thay DB/model/key/HE,
không đăng nhập live hoặc xác nhận nghiệm thu nghiệp vụ thay người dùng.

### CR-052 — chuẩn bị và ghim model bridge cho demo Portal

14/11/2026: người dùng chọn xử lý thiếu model đúng contract bridge mới. Giữ
lựa chọn trước: IF/C001, ECOD/C002; thêm RobustZ cho nhánh thống kê cùng nguồn.
Dữ liệu mô phỏng tách 32train/8reference/5eval, nguồn đã biết theo hai clock;
artifact backtest ghi thời điểm tạo thật. Operator setup bounded demo/C001/C002,
đọc access_file thật từ Portal config và không sửa quyền/fit permission người dùng.
Fit qua job/store chuẩn, median_flags/dropallnull từtrain; không bỏ compatibility
gate để dùng canonical model cũ, không tự fit trong lượt chấm.

Backup nhất quán, candidatecheck trước atomic pin, lock/hashguard và retry cùng
receipt idempotent. 84 tests đạt, setup4 sau sửa cuối đạt; Chrome4 trên pins thật/
snapshot copy giữ5/5 điểm và reload hai DN. Giữ4 model cũ,14 snapshot cũ và6 file
key/policy/HE/config, thêm4 model/snapshot. Pins HE riêng không đổi, không HE
IF/ECOD/33feature, weight/queue hoặc accuracy claim. Fix reload shared snapshot
qua quyền snapshotdata hiện có; reportdraftactor khác vẫn404. Chưa đăng nhập lại
nghiệm thu Portal live; file pins local thật đã kích hoạt. Xem evidence/R2/
rule_bridge_models_20261114 và reports/rule_bridge_models_20261114.md.

### CR-051 — giữ từng ứng viên, không chấm nguồn sau cutoff

14/11/2026: người dùng chọn sửa phát hiện RULE_CANDIDATE_MISSING làm hỏng cả
lượt. Giữ hợp đồng bảo toàn ứng viên: partition theo cả posted/observed <=as_of
trước feature/ML; hàng còn lại trả unavailable/null và lý do. Không bỏ hàng,
dịch cutoff, fake vector/clock hoặc suy thiếu nguồn là no-hit. ID không có trong
source vẫn lỗi nhập. So sánh clock bằng aware datetime, boundary bằng được nhận.

All-future không gọi model/replay mọi history; core native không nhìn thấy có
results unavailable và reference hash null, không giả đã chạy engine. Hàng
ngoài cutoff được gắn availability riêng; UI báo ngay và không tính vào kỳ
kết quả. Source diagnostics/alias/scoring policy không đổi. Giữ byte hai feature
adapter, model contract/runtime và preprocess; module visibility mới ghim vào
analysis implementation/provenance. 61 backend +17 HE liên quan và UI10 đạt;
fit kiểm chứng chỉ sandbox, chưa deploy/khởi động lại Portal live. Không tự
đánh dấu toàn R2/HE hoặc accuracy; xem reports/rule_cutoff_fix_20261114.md.

### CR-050 — nối toàn catalog, không chốt tỷ trọng luật

14/11/2026: người dùng yêu cầu nối toàn bộ luật, dữ liệu thật có thể thu thập
sau; đính chính luật chỉ chiếm một phần, không chốt 70–80%. Kế thừa quyết định
35 luật chạy tại DN trước, HE sau. Thêm profile nguồn đầy đủ riêng Agent2 để
không tạo giá trị legacy giả từ canonical ít cột. Giữ bốn adapter canonical
hiện có và schema/feature/model/worker cũ; không báo HE35 hoặc ML bridge mới.

SnapshotStore/analysis API dùng thật, điểm/hit của engine giữ lại đối chiếu
cùng nguồn/as_of. Thiếu nguồn/coverage/authority/attendance giữ unavailable;
ngoài loại giao dịch not_applicable. D/F4 tách phạm vi nhóm; master/context
không tự thành cảnh báo độc lập, alias không cộng hai lần. Không tổng điểm,
tỷ trọng, budget, nhãn/queue, nâng quyền reviewer hoặc kết luận gian lận.

120 gói qua pipeline, 140 đối chiếu với native đạt; validate lại 120 file mẫu
ở tenant demo, 6 bước UI đạt trên server tạm. Chặn bug unavailable thiếu list
ở UI, ma trận rỗng bật fallback và thiếu thông tin hóa đơn/định danh ra no-hit.
Người đọc snapshot được xem chứng từ đã xác minh mà không xác minh lại. Nguồn
native ngoài miền signed/late-observed vẫn bị từ chối rõ; P1 canonical có dấu
giữ nguyên. Chưa deploy/restart Portal hoặc phê duyệt toàn R2. Xem
evidence/R2/full_rule_pipeline_20261114/REPORT.md và tests.json cho hồi quy cuối.

### CR-049 — kiểm chứng HE hiện có và baseline bốn luật local

14/11/2026: người dùng giao kiểm chứng phần tính mã hóa rồi so lại với ML trên
baseline luật đã mở rộng. Giữ chính sách đã chọn: tối đa 5 giao dịch/phương án/DN,
luật trước ML bù chỗ trống. Chạy bộ nguồn mới 1.2 từ mock P1 tám dòng/DN, khai rõ
phone/address/quan hệ mô phỏng; không sửa giao dịch hoặc tự điền vào nguồn thật.
Toàn bộ 33 feature bằng nguồn trước mở rộng. Model đã fit riêng được đọc/pin đúng
DN; CKKS chấm mới, không lấy điểm snapshot cũ gắn vào bản mới.

P1/E3/B5/E4 local là baseline đang kiểm chứng; ba master rules chưa HE. Output
riêng expanded-rule-selection/1.0.0, không giả he-four-branch-result. Ghi rõ
all_rule_evaluations_he=false/full_he_baseline_available=false. 2/2 P1 Concrete
qua worker riêng khớp exact; ML max error khoảng 0.000051, không đảo cặp vượt
dung sai, thứ tự tuyệt đối có đổi ở điểm gần nhau. Tập chọn không đổi: luật
T03/T06/T07, kết hợp thêm T04/T02; cap bằng nhau nhưng số chọn 3 và 5, không padding.
E3/B5/E4 0 điểm master-quality không tự thành ưu tiên giao dịch. T06/T07 cùng
nhóm, T04 điều chỉnh âm, T08 thiếu nguồn không chuyển thành no-hit/0.

299 HE/82 focused và subset 10 compatibility pass; sửa helper nhận trùng ML ID,
giữ NaN/Infinity bị từ chối. Test/worker state riêng, DPAPI keys/model DB hash
giữ nguyên, no-fit/publish spies; không dùng đăng nhập hoặc dừng Portal live.
Pure selection helper dùng chung không đổi budget/policy cũ, có recheck code
cuối trên điểm HE đã mở và nguồn đã khóa. Không tự điền kết luận/hữu ích/thời
gian; còn 31 luật snapshot và 3 master HE, không nhận xét ML tốt hơn hay R2 DONE.
Xem evidence/R2/expanded_baseline_he_20261114 và agent2/docs/EXPANDED_BASELINE_HE.md.

### CR-048 — nối B5/E4 khi đủ nguồn, parity cùng dữ liệu/thời điểm

14/11/2026: người dùng giao nối các luật đủ nguồn và đối chiếu engine cũ cùng
dữ liệu/thời điểm. Rà contract snapshot 1.1 chỉ P1/E3 nhận đủ nguồn hiện có;
không tự bỏ phone/related_party_disclosed_at khỏi phụ thuộc B5/E4 để báo ready.
Thêm input 1.2.0 opt-in cho hai trường này và schema registry; default1.1 và
byte schema1.0/1.1 giữ nguyên. Không migrate snapshot hay agent khác. Vắng/null
là chưa biết, chuỗi rỗng là nguồn khai rõ không có trong master xuất. Timestamp
khai báo không sau observed_at. Validator tăng1.3, source binding1.2; shape
RuleResult1.0 giữ nguyên, checksum implementation ghim helper mới.

B5/E4 so normalization/policy giữ lại, dùng cùng source_rule_id B5/evidence_id,
intrinsic3 hoặc1 nhưng đóng góp0 theo master-quality. Không cộng hai lần hoặc
đưa vào queue. So bank token chưa phải xác minh institution/B1. Master nguồn
được biết sau event không retime; giữ unavailable trong miền native parity.
Nguồn tương lai lọc trước chọn revision; thiếu một master field không bỏ NCC
đó để tạo no-hit giả. Technical trả căn cứ/điểm/gaps trong rule_coverage; review
không lộ chi tiết kỹ thuật. Không nới quyền hoặc client chọn cấu hình/model.

20/20 đối chiếu trên 10 nguồn C001/C002 và 4/4 thiếu nguồn đạt; 303 tests pass,
bao gồm API xác thực, source/feature replay, snapshots, P1 và no-fit. 5 input/DN
giữ đủ 5 output và 35 trạng thái/dòng. Không đổi kernel/ngưỡng/33 feature/HE hoặc
deploy/restart live; chưa giá trị nghiệp vụ/accuracy/toàn R2 DONE. Xem evidence
R2/vendor_identity_snapshot_20261114 và agent2/docs/VENDOR_IDENTITY_SNAPSHOT.md.

### CR-047 — kiểm chứng 35 luật tại node DN trước; HE sau

14/11/2026: người dùng yêu cầu cho luật thiếu nguồn chạy được và sinh dữ liệu
kiểm thử, sau đó chọn rõ: “Cho đủ 35 luật chạy và đối chiếu tại node doanh
nghiệp trước, sinh data test; sau đó mở rộng HE (đề xuất)”. Phạm vi local không
cho phép chuyển dữ liệu rõ lên worker hoặc coi sinh nguồn là triển khai HE.

Thêm native-rule-source/1.0.0 riêng, nhận các bảng native có company/observed_at
và coverage/checksum/time manifest. Kiểm scope trước nội dung riêng; caller phải
cung cấp AccessScope tin cậy, demo chỉ có tenant mô phỏng. Không thêm route hoặc
tự cấp quyền Portal. Engine score_rules và monthly_diagnostics giữ nguyên policy;
không dùng Case.score vì cấu hình audit cũ khác cấu hình giữ lại hiện tại.

120 gói nguồn C001/C002; ca kỳ vọng riêng khỏi dữ liệu tính, 140 kiểm tra theo
luật và 70 thiếu nguồn. So digest output engine gọi độc lập, diagnostics D so
đúng cấu trúc. Những ca này kiểm chứng cơ chế, không chứng minh đúng chính sách
trên doanh nghiệp thật. D theo tập, F4 theo nguồn phải thu, master-quality có
thể 0 điểm nhưng vẫn có tín hiệu; E4 dùng alias B5, không cộng tổng lần hai.
Điểm tổng và accuracy vẫn null, thiếu nguồn matched null, không tạo nhãn/queue.

Giới hạn native phải rõ: chưa có bitemporal cho giao dịch/sổ cái biết muộn và
chưa có signed cho toàn catalog, nên từ chối các nguồn đó, không ép dấu/dời giờ.
P1 canonical có dấu vẫn giữ nguyên. Coverage complete chỉ là khai báo xuất,
không chứng minh đầy đủ ngoài hệ thống. Chưa migrate nguồn này vào snapshot
1.1.0, mở rộng HE, restart/deploy Portal, sửa kernel/ngưỡng/fit/model hoặc nâng
toàn bộ R2 thành DONE. Xem evidence/R2/native_rules_node_20261114/REPORT.md.

### CR-046 — kiểm kê từng luật/nguồn/adapter/HE (READY_FOR_REVIEW kiểm kê)

14/11/2026: người dùng giao lập bảng trạng thái 35 luật. Sinh bảng và JSON
từ RULE_NAMES, source_catalog hợp đồng 1.1.0, DEFINITIONS, SUPPORTED evaluator
và đường rules=p1_plan trong adapter HE; fingerprint code dùng để đối chiếu.
Phân biệt bảng chưa vào đường nhập, trường chưa hỗ trợ và chưa có evaluator;
không kết luận doanh nghiệp thiếu nguồn chỉ vì schema chưa nhận được.

Tất cả 35 có khai báo nguồn; P1/E3 có evaluator snapshot khi đủ nguồn, 33
chưa nối evaluator và 33 còn bảng/trường schema theo source map; HE chỉ P1.
Graph/RobustZ là thành phần riêng, không dùng làm chứng nhận B/A/D đã chạy.
Mô tả rule_coverage của lõi cũ là metadata tĩnh, không thay đánh giá theo nguồn
và policy thực tế. D là chẩn đoán nhóm; E3/master quality không suy hit từ điểm 0.

Replay public synthetic C001/C002 trên resolver/evaluator local: mỗi DN 8 dòng,
P1 6 đánh giá/1 thiếu lịch sử/1 không áp dụng; E3 8 không trúng trong master
đã gửi, không chứng minh master bên ngoài đầy đủ. Luật lương không áp dụng
cho bộ demo P1, chưa kiểm thử đủ các họ rủi ro. Audit không fit/chấm HE mới,
không dùng DB live hoặc đổi thuật toán/Portal/quyền/hàng đợi.

[Bảng](../reports/rule_coverage_status_20261114.md),
[bằng chứng](evidence/R2/rule_coverage_audit_20261114/REPORT.md).

### CR-045 — so lựa chọn P1 và P1 + ML, B=5 (READY_FOR_REVIEW kỹ thuật)

14/11/2026: người dùng giao so hai phương án cùng kỳ và ngân sách 5 giao dịch
mỗi phương án/DN; xác nhận ưu tiên cảnh báo luật, ML bổ sung chỗ trống. Phép
thử dùng kết quả C001/C002 mô phỏng đã biết, khai báo retrospective/technical_only,
không tạo test tương lai giả hoặc tự tuyên bố ML hiệu quả. Baseline có 3/5,
combo 5/5; ngân sách là cap, không bù ngẫu nhiên. T04 điều chỉnh âm là ngoài
phạm vi P1, T02 chưa trúng P1; chưa là bằng chứng bỏ sót toàn catalog.

Giữ nguyên nhóm đồng thời, ưu tiên thời điểm/ID trong cảnh báo luật, ML ngoài
cảnh báo theo score rồi thời điểm/ID; không weights/threshold/mandatory routing
mới. Plan khóa nguồn/model context/lựa chọn tại DN, append-only mã hóa và tách
tenant/DN/actor/run. Repeated POST và restart giữ plan; đọc scope và quyền lại.
Phiếu latest cập nhật coverage/precision đã kết luận/hữu ích/thời gian, báo
revision nguồn và null khi thiếu. Giao dịch chung tái dùng phiếu; không suy
thời gian thử độc lập, accuracy, recall hoặc số vụ gian lận thật từ phản hồi
tự khai. Không ghi nhãn train hoặc sửa hàng đợi.

[Báo cáo và giới hạn](evidence/R2/selection_comparison_20261114/REPORT.md).

### CR-044 — hoàn thiện luồng sử dụng cốt lõi (READY_FOR_REVIEW kỹ thuật)

13/11/2026: người dùng yêu cầu hoàn thiện các chức năng quan trọng của Agent2.
Tái sử dụng import/snapshot/HE/review store; thêm `/workspace` và API read-only
theo DN/lượt chạy, báo cáo CSV/JSON, luồng phiếu rõ câu hỏi/căn cứ/hành động,
tài liệu bổ sung và lịch sử. Kế toán nhận DTO nghiệp vụ; quản lý giữ cấu hình
theo quyền backend. Chưa tổng hợp trọng số, ngân sách, mandatory routing hoặc
đưa mọi giao dịch vào queue được duyệt. Phiếu không tự thành nhãn train.

Sửa gửi lặp resume lúc chờ quyền, thêm thao tác tạo lượt mới sau terminal,
giữ request ID lưu phiếu khi mất phản hồi, đọc đúng trục đồ thị và giao diện
điện thoại. Fresh admission ký riêng cho packet chưa nhận bị hết hạn giữ
đúng context/ciphertext/nonce/hash, có kiểm quyền lại; không đổi TTL/replay
Mahalanobis hoặc tự mở lại terminal. Native Concrete kiểm riêng, browser
flow CKKS/SSO trong fixture cô lập có khai báo phần mock rõ ràng.

Deploy local có backup và kiểm logical dump/khóa/model/quyền/mật khẩu;
Portal restart để nạp allowlist và Agent2 nạp backend. Không đổi Agent1.
Phạm vi nghiệm thu, bằng chứng và giới hạn: [báo cáo](evidence/R5/workspace_core_20261113/REPORT.md).

### CR-043 — chạy Portal và đối chiếu P1 với engine/chứng từ (READY_FOR_REVIEW cho kiểm thử kỹ thuật)

13/11/2026: người dùng giao chạy lại trên Portal, đối chiếu thủ công P1 với
engine luật và chứng từ. Phạm vi là hai nguồn mô phỏng mới C001/C002, mỗi DN
8 giao dịch; không tự ghi kết luận thay người hiểu nghiệp vụ hoặc tạo nhãn train.

Kiểm thử tìm thấy phiếu thiếu tham chiếu riêng của P1 (phân bổ thành viên
đồng thời và coverage); đã bổ sung từ kết quả server ghim, kiểm scope/snapshot/
thời điểm. Portal có race phản hồi `/api/state` cũ làm mất đăng nhập mới; đã
tái hiện rồi sửa, giữ TTL và quyền cũ. Khởi động lại riêng Agent2 qua Portal
để nạp backend, không khởi động lại Portal hoặc thay mật khẩu/quyền/model/khóa.
Lỗi công cụ đọc mã run từ mục thu gọn đã sửa sang lấy mã phản hồi server;
tiếp tục đúng run đã tạo và giữ cửa sổ để sửa/thử lại khi có lỗi công cụ.

C001 (`herun_a41f1c89c0b04bb9bd85021731bdaf7f`) và C002
(`herun_83f30523ede5495a97a9957a07a000dc`, job mới sau khi job cũ
`herun_1df14750934b4adba8469f6fbba1290d` đã `HE4_EXPIRED`) đều đã hoàn tất
12/12 phép tính HE4 (`rules: 6`, `graph: 1`, `statistics: 5`, `generation=1`),
đối chiếu nguồn/engine đạt 8/8 (`all_rows_match: true`), mở đủ 8 phiếu, mở
căn cứ và reload giữ cùng run (`login_count: 2` theo TTL 20 phút không đổi,
`browser_errors: []`). Bản ghi vẫn mô phỏng, 0 phiếu ghi phản hồi nghiệp vụ.
Chưa dùng kết quả để duyệt accuracy, ngân sách, trọng số, routing hoặc DONE
R0–R6. [Bằng chứng](evidence/HE/p1_portal_recheck_20261113/REPORT.md).

### CR-042 — nguồn P1 đầy đủ và ca thiếu lịch sử (READY_FOR_REVIEW)

13/11/2026: người dùng giao thêm hóa đơn, phân bổ thanh toán, phạm vi lịch sử;
thử chưa vượt, đã vượt, điều chỉnh âm và đồng thời, giữ thiếu nguồn unavailable.
Tạo hai nguồn mô phỏng C001/C002 và snapshot mới; 8 bản ghi để giữ đủ khoản
trả trước, điều chỉnh và thành viên nhóm. Không diễn giải thành tăng ngân sách
rà ML hoặc trọng số. Coverage do bộ xuất mô phỏng khai báo cho đúng hai nghĩa
vụ; nghĩa vụ thứ ba có hóa đơn/phân bổ nhưng thiếu coverage có chủ ý. Không
suy đầy đủ sổ thật từ checksum. Expected outcomes tách khỏi source/features.

Đã qua kiểm tra nguồn/engine/reference và luồng nhập browser; native HTTP thực
C001/C002 đạt 5/5 phép tính mỗi DN, gồm riêng/nhóm đồng thời, giữ số âm trong
lịch sử. Không đổi core, model, khóa, quyền, worker live hoặc hàng đợi. Actor CLI
kỹ thuật ghi audit riêng, không tạo phiên Portal giả. Chi tiết tại
[evidence P1](evidence/HE/p1_sources_20261113/REPORT.md).

### CR-041 — Portal và bốn nhánh HE (IN_PROGRESS)

13/11/2026: người dùng trả lời “Hoàn thiện Portal và mở rộng cả bốn nhánh HE”.
Được phép xây mở rộng kỹ thuật; không tự duyệt DONE hoặc chính sách nghiệp vụ.
Đã nối snapshot point-in-time, coordinator/checkpoint bốn nhánh, Concrete/DPAPI
thật, WSL lifecycle và HTTP resume sau TTL admission. Worker và node DN hard
crash được kiểm chứng, giữ envelope/model/khóa và nhánh ML con. Không đổi sáu
module/TTL/replay worker ML cũ. Thêm CSV/Excel, cấu hình quản lý với offline fit
và kích hoạt nguyên tử, phiếu/báo cáo server, lịch sử run theo quyền. Đã backup
và bật bản local với model thống kê/6 bộ khóa mới cho C001/C002 mô phỏng. Cần
đăng nhập lại sau restart; nghiệm thu live đã đạt sau khi người dùng tự đăng
nhập: C001/C002 mỗi DN 5 kết quả/5 phiếu, reload giữ run, không JS error và đúng
một parent/DN. Không tạo phiên giả, không ghi kết luận nghiệp vụ/nhãn train.

READY_FOR_REVIEW chỉ áp dụng các profile giới hạn có evidence. Chưa toàn catalog
HE/E3/33 feature/IF–ECOD–LOF–AE, danh tính từng người, cloud public hoặc production.
Chính sách trọng số/ngân sách/mandatory routing chưa duyệt vẫn mở; không tự đưa
hồ sơ vào hàng đợi hoặc tự duyệt DONE R0–R6. Xem
[tiến độ, evidence và việc còn thiếu](../agent2/docs/HE_FOUR_BRANCH_PROGRESS.md).

**BẮT BUỘC:** không bịa tên người phụ trách/ngày duyệt. Owner hiện là vai trò chưa được gán người; hạn theo mốc. R0 phải gán người thật. APPROVED cần người/ngày/căn cứ. PROPOSED_DEFAULT chỉ được dùng trong test/shadow có ghi config ID. OPEN_BLOCKING chỉ chặn phần phụ thuộc, không chặn mọi công việc.

| ID | Câu hỏi/phương án | Trạng thái/mặc định thử | Người quyết | Hạn | Phần bị chặn |
|---|---|---|---|---|---|
| D-01 | Stack, repo, framework, DB, runner thật, web import/auth hiện có? | OPEN_BLOCKING; không giả stack | Tech lead | Kết R0 | R1 implementation |
| D-02 | Posted hay pre-payment? | PROPOSED_DEFAULT: posted | Product owner | R1 | Pre-payment |
| D-03 | Min history từng detector, peer group, window? | OPEN_BLOCKING; detector thiếu điều kiện unavailable | ML owner | R2 | Active detector liên quan |
| D-04 | Trọng số, threshold, fallback? | OPEN_BLOCKING; synthetic fixture chỉ test logic | ML owner + giám đốc | R3/R6 | Active ensemble |
| D-05 | Grouping và score vụ? | PROPOSED_DEFAULT: max candidate score theo nghĩa vụ | Product + ML | R3 | Active grouping |
| D-06 | Budget, kỳ, backlog expiry? | PROPOSED_DEFAULT: B=3/tuần lịch VN cho vụ mới; expiry phải chốt | Giám đốc | R3 | Active priority policy |
| D-07 | Mandatory rules, owner, SLA? | OPEN_BLOCKING; không tự tạo tuyến bắt buộc | Giám đốc/nghiệp vụ | R3 | Mandatory delivery |
| D-08 | Target nhãn, ai duyệt, ủy quyền? | OPEN_BLOCKING; thu phản hồi nhưng chưa export label train | Nghiệp vụ + ML | R4/R5 | Train-label export |
| D-09 | Precision/false alerts/workload, n nhãn, shadow window? | OPEN_BLOCKING; phải đặt số trước nhìn test | Product + ML | Trước test R6 | Active release |
| D-10 | DN node hay SaaS, raw data được tới đâu? | OPEN_BLOCKING; chỉ fixture synthetic local trước chốt | Kiến trúc + chủ dữ liệu | R0/R1 | Upload dữ liệu thật |
| D-11 | True multi-key hay collective, backend/keys/dropout? | OPEN_BLOCKING | Crypto owner | F2 | HE thật |
| D-12 | Numeric/HE resource tolerance, rights to open? | OPEN_BLOCKING | Crypto + ML + DN | F2/F3 | HE release |
| D-13 | Parity cùng artifact/seed | PROPOSED_DEFAULT: discrete exact; float abs <= 1e-8 + 1e-6*abs(reference) | Tech + ML | Trước test R2 | Nghiệm thu adapter nếu không đạt |
| D-14 | Chính sách hồ sơ, hạn task, hoàn tất? | OPEN_BLOCKING; fixture policy dùng demo | Nghiệp vụ | R4 | Active checklist/task SLA |

Mọi quyết định sửa ghi: ID, status cũ/mới, option, owner name, decided_at, effective version, rationale, evidence, affected tasks, expires_at nếu là thử. Không sửa ngưỡng sau xem test để làm test đạt; nếu thay phải ghi version và kế hoạch test mới.

## Quyết định bổ sung v2.1

| ID | Câu hỏi | Trạng thái | Owner | Hạn/phần bị chặn |
|---|---|---|---|---|
| D-15 | In-app/email/Zalo; người nhận và quyền gửi? | OPEN; chỉ in-app demo | Product + giám đốc | Trước bật notification ngoài app |
| D-16 | Chỉ VND hay ngoại tệ, tỷ giá và mốc quy đổi? | PROPOSED_DEFAULT: MVP VND | Nghiệp vụ | R1; ngoại tệ BLOCKED trước chốt |
| D-17 | Rows/DN, DN đồng thời, latency/memory mục tiêu? | OPEN | Tech + Product | Trước performance gate R6 |
| D-18 | Retention log/PII, quyền xóa, bảo vệ và redaction? | OPEN; cần chủ dữ liệu/pháp chế | Chủ dữ liệu + pháp chế + Tech | Trước dữ liệu thật/production |
| D-19 | Staging/prod, credentials/storage tách biệt? | OPEN | Tech/DevOps | Trước pilot thật |

D-01/D-10 là đầu ra điều tra của R0, không chặn bắt đầu R0. Nếu chưa có quyết định deployment, hoàn tất inventory và báo blocker chỉ cho upload dữ liệu thật/R1 liên quan. R4 đối chiếu/hồ sơ có thể được giao song song sau contract R1; task/report cần integration R3. Đây là tùy chọn giao việc của người điều phối, không lệnh tự tạo agent hoặc tự chuyển milestone.

## Gate kỹ thuật và gate chất lượng

Gate kỹ thuật: 100% acceptance case bắt buộc pass; 0 vi phạm tenant/time/idempotency; 0 mandatory tests bị skip; mọi sai khác parity có test và giải thích. Thiếu harness không được ghi PASS.

Gate chất lượng: D-09 phải có con số thực trước test. Không có căn cứ để bịa mức precision tối ưu. Khi còn OPEN, R6 có thể đạt technical_ready nhưng release BLOCKED. Trạng thái task R6 ghi BLOCKED/PARTIAL kèm bằng chứng phần đã làm.

## Điều tra R0 ngày 10/11/2026 — chưa phải quyết định APPROVED

- D-01: repository thực `D:/agent22`, nhánh `platform-Khanh`, nguồn tại commit `3cae5a3bba535694235179651b2e5daee8237656` cùng working tree chưa commit. Agent2 dùng Python 3.12.7, thư viện chuẩn HTTP, NumPy/SciPy/scikit-learn/NetworkX/joblib và SQLite cũ 41 bảng. Các phiên bản/lệnh thực đo tại `evidence/R0/environment.json`. Không tạo framework mới theo đường dẫn minh họa trong DOCX.
- CR-004 đã thực hiện phạm vi dọn: bản cũ lưu ngoài repo, core-only chưa có DB nghiệp vụ mới. Trang trạng thái tạm tương thích launcher cũ, không phải R5.
- Chưa có bộ xác suất gian lận đã calibration được xác minh; điểm luật, p-value, midrank và anomaly score phải giữ đúng nghĩa.
- Các tên người phụ trách/duyệt thật chưa được cung cấp; giữ owner theo vai trò và yêu cầu nhóm chỉ định. Không tự ghi tên hoặc giả APPROVED/DONE. D-10/D-18/D-19 và các quyết định chất lượng vẫn mở đúng phạm vi.

## CR-005 — phần hợp đồng R1 được giao riêng

Ngày 10/11/2026 người dùng giao xây hợp đồng đầu vào, đối chiếu Git các agent khác, giữ số âm điều chỉnh. Thực hiện schema/version và validator local; không đổi trạng thái APPROVED của D-01 hay tự chọn database/triển khai. Python package dùng chung thêm `jsonschema` để thực thi một schema backend, không đổi framework/server. D-02 posted và D-16 VND chỉ là profile thử `agent2-posted-vnd/1.0.0`; ngoại tệ/pre-payment chưa hỗ trợ.

D-10/D-18/D-19 tiếp tục chặn dữ liệu thật/production, không chặn fixture tổng hợp của phần hợp đồng. D-03/D-04 chưa được dùng để suy lịch sử tối thiểu/trọng số ML. R1 còn PARTIAL cho API, snapshot/idempotency và replay feature; không tự chuyển R2.

## CR-006 — validation backend theo quyền doanh nghiệp

Người dùng giao backend kiểm quyền, cột/kiểu/mã trùng/liên kết, lỗi có dòng/trường/cách sửa, giới hạn nguồn thiếu. Thực hiện API validate JSON bằng server hiện có và adapter auth file backend tin cậy. Không tạo một màn đăng nhập hoặc tài khoản người dùng mới. Portal ở commit f203b39 có cổng mở khóa chung, chưa cấp identity/membership theo DN cho Agent2; chưa coi phiên cổng chung là quyền mọi doanh nghiệp. Policy local dùng credential hash + membership/permission active/expiry, đọc lại mỗi request và đóng quyền khi lỗi. Đây là adapter fixture local cho R1, chưa quyết định kiến trúc SSO/identity sản xuất.

Giữ contract đầu vào 1.0.0, tăng thư viện/validator/report lên 1.1.0; không thay feature schema/thuật toán. Capability và analysis_limits chỉ mô tả nguồn trong bundle, không chốt D-03 min-history, D-14 chính sách hồ sơ hay kết luận sai phạm. D-10/D-18/D-19 giữ nguyên giới hạn nguồn thật. Chưa commit snapshot, chưa mở R2 hoặc production.

## CR-007 — snapshot backend, bắt đầu 10/11 và bàn giao 11/11/2026

Người dùng giao upload → preview → xác nhận → snapshot bất biến và idempotency. Dùng SQLite thư viện chuẩn của stack đã kiểm kê, DB snapshot mới riêng có application_id/user_version; không mở/migrate DB review cũ. Đây là quyết định triển khai local cho phần được giao, không tự gán người duyệt D-01/D-10. Import/snapshot protocol 1.0.0; input contract 1.0.0, validator/report 1.1.0 giữ nguyên.

Mặc định preview TTL 15 phút là giới hạn kỹ thuật local (có thể cấu hình trong store, khóa expiry trong report), không là ngưỡng nghiệp vụ/ML. Tệp JSON và mapping đổi tên cột được hỗ trợ trước; không tự đoán timezone/đổi giá trị hoặc mở CSV/Excel chưa có adapter. Chỉ ghi snapshot khi xác nhận rõ và quyền còn hợp lệ, transaction atomic, checksum/revision/context đúng; retry đã committed trả cùng snapshot qua receipt. Chưa nối Portal identity, feature replay hay R2. D-03/D-04/D-09/D-10/D-14/D-18/D-19 không được tự chốt thành release/dữ liệu thật.

## CR-008 — nối feature và nghiệm thu kỹ thuật R1, 11/11/2026

Người dùng giao nối bộ tạo feature, as_of/nhóm đồng thời và tách ID/nhãn/bằng chứng; yêu cầu chứng minh tối thiểu bốn hành vi R1. Adapter dùng `features.build_features` nguyên bản, contract mới `snapshot-point-in-time/1.0.0` tách khỏi contract/model/cache legacy. Chỉ 33 cột đủ nguồn theo profile; không giả đủ mọi cột legacy. Các giá trị đếm có đơn vị bản ghi/dòng, log tiền dùng log1p(abs(VND)/1 VND), các tỷ lệ và chu kỳ là vô thứ nguyên; số tiền signed VND gốc và tổng phân bổ ở kênh evidence. Peer magnitude là cùng tenant/DN/kind, history trước cả event-time và known-time; denominator bằng 0/nguồn thiếu trả null/missing reason, không impute.

Mỗi revision chấm tại max(effective_at,observed_at), nguồn context vừa phải đã được biết vừa có hiệu lực tại event. As_of job chặn tương lai, không dùng snapshot master/latest toàn cục cho quá khứ; giao dịch đồng thời theo timestamp nghiệp vụ hoặc availability cùng nhìn lịch sử trước nhóm. Đây là semantics kỹ thuật versioned của adapter local, không tự chốt D-03 detector min-history, D-04 trọng số, D-09 quality gate hoặc D-14 checklist. Z-score giữ yêu cầu 5 mẫu/SD floor .25 của core hiện có, không là model-ready gate.

Core chỉ nhận timestamp giây UTC+07 và amount dương. Projection riêng dùng thứ tự thời gian nội bộ và magnitude dương để giữ nguyên core; output chỉ allowlist không phụ thuộc scaffold, microsecond và cutoff thực điều khiển selection trước projection. Zero ảnh hưởng magnitude kernel bị missing rõ. Không đổi/hủy dấu tiền snapshot. Không gọi generator hoặc dùng nhãn/seed/template, nguồn raw chỉ là evidence riêng.

CLI job có quyền, checksum-bound output và artifact publish riêng; chưa có API job/Portal UI/SSO, fit model hay production. Sau gate R1 kỹ thuật chỉ được ghi READY_FOR_REVIEW, cần người thật duyệt DONE; D-10/D-18/D-19 và người duyệt triển khai vẫn mở đúng phạm vi. Không tự chuyển R2.

## CR-010 — sửa BR-07: đọc xác minh đã commit, 11/11/2026

Người dùng giao sửa quyền đọc snapshot bị nhầm với quyền xác minh. `build_from_snapshot` sau kiểm quyền/checksum của store dùng trạng thái verified đã lưu; không áp lại riêng lỗi `VERIFICATION_PERMISSION` của thao tác ghi. Những lỗi khác vẫn chặn, raw/import không được dùng ngoại lệ này, không nhận bypass flag từ client và không tăng permission của scope. Đây là sửa lỗi phân biệt đọc/ghi trong R1, không xác nhận tính thật của chứng từ hay thay D-10/D-18/D-19.

Feature adapter tăng patch `snapshot-point-in-time/1.0.1`, giữ nguyên ordered schema 33 cột/phép tính. Validator/report nhập liệu vẫn 1.1.0; input/snapshot protocol vẫn 1.0.0, không đổi behavior ghi. Artifact cũ giữ nguyên, fingerprint mới không tự tương thích với model/cache fingerprint khác. BR-08 được phát hiện khi rà CR-009 vẫn chưa sửa trong phạm vi này, R1 tiếp tục PARTIAL; không tự chuyển R2 hoặc duyệt production.

## CR-011 — sửa BR-08: thiếu nguồn khác số 0, 11/11/2026

Người dùng giao lịch sử phân bổ thiếu revision nguồn phải báo chưa đủ dữ liệu. Adapter 1.1.0 giữ 33 cột, bổ sung semantics missing cho ba prior_invoice_* và nullable exact prior total ở evidence. Phân bổ trước nhóm gắn invoice ID liên quan và transaction ID đã thuộc lịch sử nhưng thiếu revision đích khả dụng làm các thống kê prior unavailable/null. Phân bổ đã biết được giữ, kèm source/field/reference, lý do và hành động; không xuất giá trị/timestamp của revision tương lai. Cách chọn as_of/nhóm đồng thời, số âm và quyền đọc đã sửa trong CR-010 giữ nguyên.

Không có phân bổ trước trong tập nhìn thấy, hoặc tổng signed thực bằng 0 khi đủ liên kết nguồn, vẫn là 0. Coverage chỉ là tập nguồn hiện có tại snapshot/cutoff, không cam kết đủ toàn bộ sổ hoặc nghĩa vụ doanh nghiệp; không thay chính sách chứng từ/ngưỡng nghiệp vụ D-14, min-history D-03 hay quality gate D-09. Input contract, validator, snapshot protocol và lõi feature không đổi. Contract mới/fingerprint mới cần artifact tương thích; không ghi đè dữ liệu hoặc cache cũ. Kết quả và trạng thái R1 sau chạy lại được ghi tại báo cáo CR-011; không tự duyệt DONE/production hoặc chuyển R2.

## CR-012 — giao bước chuẩn đầu ra thuộc R2, 11/11/2026

Người dùng giao MethodScore/khả dụng/lý do thiếu cho mỗi giao dịch, graph bằng chứng và no-hit luật vẫn được ML chấm. Dùng R1 đã đạt gate kỹ thuật làm đầu vào cho phần độc lập này, không giả reviewer đã duyệt DONE. Bọc nguyên luật/thống kê/graph/ML tại mapping methods/calibration; không đổi thuật toán hoặc tạo ensemble/queue. Rule points và frozen empirical midrank có tên riêng, không gọi là xác suất.

Prototype offline fit/history-reference được tách khỏi inference, gắn scope và version/hash, chọn feature rõ; không impute hoặc fit trên batch test. Minimum 5 trong profile demo chỉ dùng điều kiện kỹ thuật hiện có của estimator, không chốt D-03 cho sản xuất. Thử trên dữ liệu mô phỏng/parity không xác nhận accuracy; D-09 còn mở. Artifact bytes nội bộ tin cậy chỉ ở bộ nhớ, chưa mở nhận file model HTTP hoặc tạo quyền/config active mới.

Native có đủ nguồn giữ nguyên hit/ngoại lệ/điểm và graph. Canonical R1 chưa có bridge trung thực cho mọi nguồn luật nên trả rules unavailable; ML/thống kê và graph vẫn chạy độc lập khi đủ điều kiện. Không dùng placeholder để giả đủ luật. Persistent fit jobs/registry, mapping luật canonical và benchmark E1–E2 chưa hoàn tất trong chỉ đạo chuẩn hóa này; R2 PARTIAL, không tự chuyển R3 hoặc duyệt active/production.

## CR-013 — tách fit/chấm và lưu model theo DN, 11/11/2026

Người dùng giao job fit bằng nguồn trước kỳ đánh giá, lưu model/preprocess/feature contract và không dùng model legacy cho bộ 33 feature. Thực hiện MethodStore SQLite local riêng, append-only artifacts/audit và receipt/job state. Thêm permission model.fit phía backend, đi cùng data.import khi tạo model; chấm chỉ cần quyền đọc. Đây không phải chốt kiến trúc SSO/triển khai thật D-10/19 hoặc tự cấp quyền quản lý theo role.

Config bắt buộc lịch sử/reference/evaluation có timestamp rõ, missing_policy và evaluation_mode; job replay history/reference riêng, không lấy latest revision sau train cutoff. Backtest hồi cứu chỉ dùng dữ liệu trước kỳ và ghi thời gian model thực; prospective còn chặn job hoàn tất/công bố sau khi kỳ bắt đầu. Không tự gán model active hoặc dùng latest/fallback.

Preprocess strict hoặc median_flags đóng băng theo model; median/scaler chỉ học train, all-null train columns bị loại cố định có lý do; không dùng reference/test để học lại hoặc thay raw null bằng 0. Full input contract vẫn 33 cột, transformed order/width và params/hash được lưu. Modelstore/adapter kiểm tenant/DN, full fingerprint/format/preprocess/code/runtime trước load; model cũ hoặc cùng chiều khác semantics không được tự dùng lại. Artifact local tin cậy, không nhận pickle/code qua HTTP.

Ngưỡng minimum_history 5 trong demo giữ là điều kiện kỹ thuật thử theo estimator cũ, không duyệt D-03; không chốt trọng số/quality gate D-04/09. Kho/job qua restart đã làm; canonical rule bridge, benchmark E1–E2, active lifecycle và scheduler/recovery vẫn riêng. R2 PARTIAL, không tự ghi DONE hoặc chuyển R3/production.

## CR-015 — nối đầu vào nguồn từng luật, 11/11/2026

Theo yêu cầu mới, thêm catalog và resolver RuleInputs cho mọi luật giữ lại, theo tenant/DN và cả hai thời gian của snapshot R1. Nguồn chuẩn vẫn là hợp đồng chung 1.0.0; không tự thêm trường lương, hạn mức/quyền, lịch vận hành hoặc suy từ mô tả/tên tệp để giả đủ nguồn. Lịch sử chỉ gồm dòng trước nhóm; dữ liệu âm, revision và provenance giữ nguyên. Metadata source readiness tách biệt với evaluation status và score. Chỉ nối nguồn được biết; evaluator luật, benchmark và mọi quyết định D-03/04/09 hoặc active vẫn cần bước riêng. Không phê duyệt DONE/R3/production.

## CR-016 — kết quả đánh giá từng luật, 11/11/2026

CR-016 tiếp tục phần kết quả: thêm RuleResult và evaluator E3 đủ nguồn theo policy mặc định, giữ helper/weight/scoring-role cũ. E3 hit có intrinsic 3, contribution 0 và matched=true. Missing/không so được tên/thiếu evaluator đều null, không phải no-hit; not_applicable tách riêng. Tổng canonical chưa đủ giữ null, không tự chọn ensemble/active hoặc kết luận gian lận/độ chính xác. Input producer giữ marker not_evaluated; đọc rule_results cho trạng thái cuối.

RuleInputs patch 1.0.1 chỉ lan truyền gap theo role: lỗi liên kết hóa đơn không chặn tên NCC đã đủ nguồn. Không đổi input contract/33 feature, không tạo proxy cho bảng thiếu. Kiểm scope/time/checksum/evidence trước trả kết quả; không mở UI/HTTP chấm mới, không duyệt toàn R2 hay chuyển R3. D-03/04/09 còn mở.

## CR-017 — đối chiếu engine và giữ batch diagnostics, 11/11/2026

Theo yêu cầu cùng dữ liệu đủ nguồn phải khớp điểm/cảnh báo/ngoại lệ, thêm parity trên fixtures nghiệp vụ đang có, theo đúng cấu hình default/legacy của từng ca. Test tái hiện P1 sau đóng nhóm bị bỏ khỏi adapter, đã giữ batch_events và toàn bộ diagnostics engine ngoài scores/hits ở method-output/1.1.0. Không cộng event vào điểm dòng, không đổi kernel/trọng số/ngoại lệ. Copy output tách khỏi engine objects, kiểm doanh nghiệp và batch participant IDs đúng nguồn.

209 lần đối chiếu và 696 lượt fixture không phải 696 giao dịch thật duy nhất hay accuracy. Native full-source parity không chứng minh đã có đủ nguồn/evaluator cho mọi luật canonical: E3 tiếp tục được đánh giá khi đủ nguồn, các luật thiếu giữ unavailable/null. Không mở queue/active/UI hoặc chốt D-03/04/09/full R2 gate; R2 giữ PARTIAL.

## CR-018 — đầu vào P1, 11/11/2026

Theo yêu cầu bổ sung kênh/liên kết/phạm vi lịch sử, input 1.1.0 thêm payment_channel và source-declared coverage kèm manifest. Giữ schema 1.0.0, không nâng/sửa snapshot cũ, snapshot mới ghi đúng contract_version payload. Validator context khóa cả hai schema và code kiểm P1; đổi file/mapping/validator phải preview lại.

Không suy channel từ bank/accounting hoặc lịch sử thiếu từ số dòng; partial/bounded/unknown/stale/conflict đều không đủ P1. Manifest khớp chỉ xác nhận tập bản ghi đã gửi, không chứng nhận đủ sổ bên ngoài. Dữ liệu signed/overpayment hợp lệ không bị xóa hoặc reject vì vượt hóa đơn. Đủ input vẫn chưa bật evaluator P1; không đổi 33 feature, model/active/queue, trọng số hoặc tự chốt D-03/04/09. Chỉ làm lớp nguồn trong yêu cầu này.

## CR-019 — evaluator P1, 11/11/2026

Yêu cầu mới cho phép nối evaluator P1 sau lớp nguồn CR-018. Dùng số phân bổ, không nhân toàn bộ tiền giao dịch cho từng hóa đơn. Revision thay thế không cộng hai lần; adjustment/reversal có nguồn là delta có dấu, kiểm bản gốc, thời gian, doanh nghiệp và nghĩa vụ. Thiếu hoặc mâu thuẫn trả unavailable/null. Phạm vi do nguồn khai báo không trở thành xác minh đầy đủ sổ ngoài.

Giữ P1=20, hard trigger và so tổng > giá trị hóa đơn +1 VND của kernel. Như native, row hit cần có thanh toán trước; giao dịch đồng thời không vào lịch sử nhau. Kiểm tổng sau nhóm tách trong details với định danh ổn định, điểm chỉ là điểm nhóm tham khảo, không cộng vào row hay tổng rules; chưa tạo queue/event nghiệp vụ. Đối chiếu native trong miền positive/single-invoice hỗ trợ; kernel native không nhận số âm, signed adapter phải có kiểm thử độc lập. Không sửa kernel, feature/model, active/UI hoặc tự duyệt R2/R3.

## CR-020 — đối chiếu lại P1 và finding native

Theo yêu cầu kiểm thử bảy tình huống: dưới trần, vượt trần, thiếu phạm vi lịch sử, hóa đơn biết muộn, phân bổ biết muộn, tài liệu bổ sung không bắt buộc đến muộn và hai khoản đồng thời. Các ca miền chung so cả điểm, tổng, phần vượt, trần, khoản trước, hard trigger và thành viên nhóm; missing/unavailable không quy thành native zero để ép parity.

Finding **P1-NATIVE-LATE-INVOICE = OPEN**: raw/native rules.py vẫn đọc invoice_gross_vnd ở P1 khi invoice_observed_at sau posted_at. Tái hiện 6+6 triệu trên hóa đơn 10 triệu: native row 20, snapshot canonical unavailable/null; giao dịch sau khi biết hóa đơn dùng được nguồn. Phạm vi lịch sử và mốc phân bổ không có trạng thái tương đương trong legacy hit list, ghi representation limits riêng.

Lượt này chỉ audit/test/docs, không sửa kernel/model/weight hoặc thay hợp đồng. Audit CLI exit 2 khi còn finding, không che bằng test pass hay tự phê duyệt engine. Cần xử lý guard thời gian trên đường native và kiểm lại lịch sử/batch trước khi gọi đường đó đạt as_of; việc sửa được giao riêng. Đường canonical đã chặn nguồn biết muộn; không kết luận cả pipeline hoặc production đạt.

## CR-021 — bật backend và kiểm thử live

Theo yêu cầu chạy thử, khởi động start_review.py ở 127.0.0.1:8766 bằng môi trường Agent2. Policy demo C001, credential ngẫu nhiên hạn 8 giờ và DB mới riêng trong agent2/.runtime/live_check_20261111; credential không in hoặc đưa vào evidence/Git. Không mở quyền doanh nghiệp khác hay dùng DB cũ. Server chạy nền sau khi kết thúc kiểm thử.

Thử HTTP thực cho validate/upload/preview/commit/retry/read, quyền DN/Origin, checksum, preview hết hiệu lực khi đổi nguồn và manifest sai. Score snapshot lấy scope qua FileAuthorizer, không dùng scope client tự khai, giữ 33 feature và không fit khi thiếu model. Đây là backend/status page đang có; pipeline_ready và active_delivery vẫn false, chưa có UI workflow/CSV/Excel/HTTP scoring. Công cụ browser bị lỗi, không tuyên bố đã nghiệm thu giao diện bằng trình duyệt. Tiếp tục giữ lỗi native P1 biết hóa đơn muộn OPEN, không coi server healthy là full pipeline đạt.

## CR-022 — ưu tiên sửa lỗi và đẩy tiến độ

Yêu cầu mới cho phép sửa P1-NATIVE-LATE-INVOICE. Thêm kiểm thử tái hiện trước sửa, guard trên current và prior/batch; nguồn muộn tạo information_gap 0 điểm thay vì risk hit. Không cộng tổng phần đã biết khi lịch sử còn thiếu nguồn; giữ lịch sử để dùng ở lần chi sau khi đã biết, không chấm lại quá khứ. Không sửa các luật khác, weight, feature hoặc model.

Giữ tương thích header legacy không khai báo mốc thời gian, ghi rõ chưa xác minh as_of cho miền đó; canonical vẫn đòi nguồn tường minh. Chỉ xác nhận fix trong phạm vi các ca được kiểm thử, không tự đánh dấu DONE/R2 gate hoặc nghiệm thu toàn engine. Bước kế tiếp đề xuất một luồng demo tối thiểu bám các khả năng đã có, sau khi kết quả sửa được rà; không tự mở UI/queue/active trong task sửa P1.

## CR-023 — API phân tích snapshot có quyền

Yêu cầu mới cho phép nối HTTP analyze P1/E3. Tái sử dụng score_snapshot với methods=(), không có đường fit/auto-load model hoặc điểm do client tự gửi. Đọc snapshot checksum-verified, giữ đủ row khả dụng và nhóm tách riêng, analysis_id theo snapshot/as_of/code. API đồng bộ chỉ đọc, không tạo state/job mới; không gán việc đọc thành evidence verification.

Theo RULE-UI-01/03, mặc định accountant nhận business DTO allowlist, không nhận raw RuleResult rồi chỉ ẩn ở frontend. Technical view cần director đúng DN và data.import; authorize_director đọc policy backend lại, gồm khi role bị hạ mà permissions trong AccessScope không đổi. Dùng chung phép tính cho cả hai view. Không thêm role/permission hoặc bridge Portal không có nguồn.

Resource guards 200 transaction records/1.000 source records/5 MiB response chỉ là giới hạn kỹ thuật demo đồng bộ, không tự cắt nguồn; larger jobs là việc riêng. Không đổi kernel/feature/model/weight, không mở UI/ML HTTP/queue, không duyệt toàn R2/R3 hoặc quality gates. 200/403/404/413 và errors/partial được ghi theo contract CR-023 trong 04.


### CR-024 — phạm vi UI được giao riêng

11/11/2026: người dùng giao xây màn hình nhập/kiểm tra/lưu/xem kết quả ngay trên API đã có. Thực hiện lát cắt này độc lập, không xem là duyệt DONE R1/R2 hoặc đủ phụ thuộc/full R5. Dùng adapter credential local đã có, không dựng hệ thống đăng nhập mới. Mẫu công khai chỉ mô phỏng; dữ liệu thật vẫn qua Bearer và scope backend. JSON-only được mô tả rõ theo khả năng hiện hành.


### CR-025 — tái sử dụng phiên workspace Portal

12/11/2026: người dùng giao nối đăng nhập/quyền DN vào Agent2. Kiểm kê thực tế Portal chưa có user/membership theo người; chỉ có phiên mở khóa chung. Xây bridge phiên đó với membership được quản lý phía server, deny khi chưa cấu hình. Không tự cấp director hoặc quyền DN từ profile đang chọn. C001 local demo giữ đúng tenant/actor/membership đã được cấp trong policy local trước đó; không tự mở C002 hoặc quyền quản lý. Phạm vi này không tạo hệ thống tài khoản đa người hay duyệt full R5/production.


### CR-026 — rà nghiệp vụ với ledger độc lập

12/11/2026: người dùng giao chạy bộ nhỏ qua UI và đối chiếu nghiệp vụ. Dùng 5 dòng C001 đã công khai cùng một probe đơn lẻ, tất cả mô phỏng, snapshot/phiên/DB tạm; không đổi dịch vụ live hoặc mật khẩu thật. Tính tay số tiền từ source, phân biệt dòng/nhóm, khai báo coverage với đầy đủ sổ thực, chưa đủ nguồn với không vi phạm. Ghi findings/chính sách cần chốt riêng, không sửa detector để đạt audit hoặc tự ký nghiệm thu nghiệp vụ cuối cùng.


### CR-027 — phân tích bốn nhánh trên web

12/11/2026: người dùng giao mở bốn nhánh sẵn có vào phân tích/UI. Pin artifact theo DN bằng cấu hình server để chấm chẩn đoán, không suy đây là active bundle đã qua release gate. Không có binding thì ML/statistics chưa khả dụng; không tự chọn thuật toán/model, fit hoặc mở CatBoost. Giữ toàn bộ kernel/feature contract/version kiểm tương thích. Chưa có ngưỡng/ensemble được duyệt nên chỉ hiển thị thứ hạng tương đối, không tự phát cảnh báo ML/graph hoặc tăng tỷ trọng. Luật canonical ngoài P1/E3 vẫn báo thiếu evaluator/nguồn theo thực tế.

### CR-028 — cloud chỉ xử lý ciphertext

12/11/2026: người dùng chọn yêu cầu cloud tính toán hoàn toàn trên dữ liệu mã hóa. Ranh giới đã rõ: dữ liệu/khóa bí mật và giải mã kết quả tại doanh nghiệp; cloud không giải mã ở bất kỳ bước trung gian nào hoặc fallback dữ liệu rõ. D-10 nhận yêu cầu này cho hướng cloud mới; vị trí node/SaaS triển khai thật và quyền nguồn vẫn chưa chốt. Chưa tự chọn backend/true multi-key/collective, tham số hoặc model visibility; D-11/D-12 còn mở. Câu hỏi cloud inference/training đã gửi nhưng chưa nhận câu trả lời. Hợp đồng tại ../agent2/docs/ENCRYPTED_CLOUD_BOUNDARY.md là chuẩn bị, không phải năng lực đã chạy; pipeline CR-027 tiếp tục local/plaintext.

Phụ lục TH2 Logistic có nhãn không được coi là implementation của bốn nhánh hoặc ML không nhãn. Trước khi có bằng chứng crypto thật, encrypted cloud phải báo chưa khả dụng, không tự biến encode/serialize thành encrypt. Sửa chữ “giải mã model” ở tài liệu local thành deserialize để tránh nhận nhầm đã có mã hóa. Không đổi code/runtime/model/feature, không cài dependency hoặc deploy cloud trong cập nhật hợp đồng này.

### CR-029 — bắt đầu từ inference trên model fit tại DN

12/11/2026: người dùng trả lời chọn cloud chỉ chấm model đã fit riêng tại DN; thay thế phần câu hỏi còn mở của CR-028. Xây thí nghiệm độc lập một circuit bậc hai tương đương ShrunkMahalanobis hiện có, không sửa estimator để phù hợp crypto và không gọi đây là adapter của bốn model ML hiện hành. TenSEAL 0.3.18/CKKS và cryptography 50.0.2 là dependency opt-in của thử nghiệm; khóa single-key riêng từng DN, không tự đóng D-11 multi-party hoặc chọn production backend.

Profile/tolerance/miền số/giới hạn packet và batch đặt trong protocol.py trước chạy; D-12 production vẫn mở. Threat model thử nghiệm worker chạy đúng/code tin cậy và quan sát ciphertext; chữ ký không là bằng chứng tính đúng trước cloud ác ý. Không chuyển dịch vụ live lên cloud, không gửi dữ liệu thật, không tự ghim model HE vào MethodStore/queue hoặc xác nhận độ chính xác nghiệp vụ. Hợp đồng và evidence tại ../agent2/docs/HE_INFERENCE_EXPERIMENT.md và evidence/HE/inference_20261112/REPORT.md.

### CR-030 — xuất artifact theo doanh nghiệp vào HE inference

12/11/2026: người dùng giao nối kho model đã fit vào luồng CR-029. Kiểm kê cho thấy catalog/kho thông thường có IF/ECOD/LOF/Autoencoder/RobustZ, chưa có adapter HE và bản Mahalanobis trước chưa bền vững. Xây registry adapter opt-in cho chính primitive Mahalanobis hai biến, job fit offline riêng tại DN/publish cùng MethodStore; không chuyển model cũ sang loại khác hoặc tự fit khi export. Method experimental không vào catalog/active web.

Export yêu cầu data.import đúng scope, không đòi model.fit chỉ để đọc provenance. Kiểm version/contract/tiền xử lý/fit job trước deserialize, đọc DB mode=ro, tách receipt gốc ở DN và opaque binding gửi worker. Giữ mọi dòng theo as_of, missing/future/overlap/out-of-domain null; quá batch không cắt nguồn. Lát cắt này có CLI worker local và kiểm thử nguồn mô phỏng, chưa Portal UI/cloud network/KMS/multi-key/production. R2/R5 và D-11/D-12 sản phẩm không tự chuyển trạng thái. Xem ../agent2/docs/HE_REGISTRY_EXPORT.md và evidence/HE/registry_export_20261112/REPORT.md.

### CR-031 — tách hai phía, giữ Mahalanobis

12/11/2026: người dùng giao tách node doanh nghiệp giữ raw/model/HE secret key và worker chỉ nhận/tính/trả ciphertext, chưa chuyển Portal hoặc bốn nhánh. Xây hai API HTTP loopback riêng và worker source bundle allowlist. Khóa provisioning ký thuộc node; worker chỉ có grant public theo tenant/DN và response-signing key khác HE secret key. Policy không được tự cấp từ evaluate body; đăng ký phải được node có grant ký, grant reload trước tính/trả cache.

Các job HE/cached result ở worker chỉ là bản mã/public metadata. Node decrypt và trả DTO nghiệp vụ có quyền, receipt/model metadata ở DN. Thêm idempotency trong process node và durable ciphertext cache worker, không coi là key persistence/recovery qua node restart. Worker restart có thể đọc ciphertext đã hoàn tất khi phiên còn hạn. Loopback mặc định và bắt buộc, chưa hạ tầng cloud/public TLS/mTLS/proof/native sandbox/KMS; hai thư mục cùng Windows user chỉ chứng minh package/process boundary. D-11/D-12 và release R2/R5 chưa thay đổi. Xem ../agent2/docs/HE_TWO_SERVICES.md và evidence/HE/services_20261112/REPORT.md.

### CR-032 — lượt chấm HE có trạng thái/khôi phục

12/11/2026: người dùng giao gửi → trạng thái → nhận → decrypt, retry không trùng. Lưu state/checkpoint/result trong DB riêng tại DN, AES-256-GCM/HKDF với master key 32 byte do operator cấp ngoài DB. Không tự tạo key thật khi thiếu/sai, không lưu bearer hoặc model pickle trong checkpoint; không đưa key/receipt/state vào worker bundle. Durable idempotency theo tenant/DN/actor/key và body normalized, exclusive node state lock.

Quy tắc write-ahead: commit checkpoint trước gửi, commit ciphertext trước decrypt, commit completed/result và bỏ checkpoint hiện hành cùng transaction. Node restart pause để owner xác thực lại, không dùng credential cũ trên đĩa. Worker retrieval được fresh node signature/grant để đọc ciphertext đã tồn tại sau TTL inference; evaluate hết hạn vẫn từ chối, không tạo nonce mới/auto refit. CLI lưu phiếu trước POST để khôi phục cả khi mất response đầu.

Đây là bước API/CLI của Mahalanobis thử nghiệm loopback, không tự mở Portal/cloud public, KMS/HA/key rotation/anti-rollback/OS sandbox hoặc production. Bảo đảm recovery cần DB và key hợp lệ, không bảo đảm khôi phục data đã bị xóa hoặc rollback backup tùy ý. R0–R6/D-11/D-12 sản phẩm giữ nguyên. Xem ../agent2/docs/HE_JOB_LIFECYCLE.md và evidence/HE/job_lifecycle_20261112/REPORT.md.

### CR-033 — bảo vệ khóa DN, giữ phiên qua restart

12/11/2026: người dùng giao lưu khóa an toàn tại DN để khởi động lại vẫn nhận được kết quả. CR-032 đã có checkpoint/result AES-GCM nhưng master key ở file hex; bổ sung provider Windows DPAPI current-user cho master key và provisioning Ed25519 seed. Không bật LOCAL_MACHINE hoặc UI. File envelope ràng buộc version/provider/purpose/key_id, kiểm DPAPI trước publish atomic, không ghi đè. Config 1.2.0 bắt buộc protected keys cho cả state-wrapping và node-signing; config 1.0/1.1 giữ tương thích legacy có chủ đích, không tự chọn fallback khi DPAPI hỏng.

Lệnh protect bọc nguyên giá trị khóa cũ sang file mới; HKDF/AAD/schema DB, public key grant và idempotency không thay đổi. Không tự xoay khóa hoặc xóa file nguồn; không migrate key/config live trong cập nhật này. Operator phải đối chiếu key_id/public verify key, kiểm phục hồi và quản lý bản hex/backup cũ. Missing/wrong/tampered key dừng, không tạo khóa khác để che mất state. Node private keys/checkpoints không vào worker bundle hoặc evidence.

DPAPI cần profile/tài khoản Windows thích hợp; không bảo đảm chỉ copy DB/file khóa sang máy mới là đủ phục hồi. Cùng Windows user có thể gọi DPAPI nên không coi là cách ly process/OS hoặc bảo vệ trước host bị chiếm quyền. Kiểm thử native roundtrip, process mới và hai service restart; chưa thực nghiệm tài khoản Windows khác/reboot/cross-machine. Demo hiện Windows-only, không Linux plaintext fallback. Chưa KMS/HSM/rotation/HA/anti-rollback/production, không thay R0–R6/D-11/D-12. Xem ../agent2/docs/HE_KEYS_AND_SESSIONS.md và evidence/HE/key_protection_20261112/REPORT.md.

### CR-034 — giao diện HE dùng phiên Portal

12/11/2026: người dùng giao UI chỉ chọn doanh nghiệp/dữ liệu và Chạy phân tích sau khi đã có khóa/phiên bền vững. Dùng trang `/encrypted-analysis` tại backend DN, qua Portal proxy `/agent2/encrypted-analysis`. Browser chỉ gửi snapshot ID/idempotency key; backend chọn artifact từ file ghim tenant/DN, cutoff bằng created_at bất biến của snapshot. Kiểm đầy đủ model metadata/fit provenance để khóa nút khi không có phiên bản phù hợp, không deserialize/fit trong catalog. Export lúc chạy vẫn kiểm lại tất cả trước chấm.

Node HE nhúng opt-in trong process backend DN để dùng chính authorizer Portal và cùng snapshot DB của nhập dữ liệu, không dùng credential dịch vụ chung hoặc fallback auth_file. Config 1.2.0 bắt buộc DPAPI; startup từ chối hai đường dẫn snapshot khác nhau. Standalone node và web không được cùng mở state_dir. Worker tiếp tục bundle cũ và chỉ nhận ciphertext; public API allowlist không mở decrypt/fit/arbitrary proxy. Node config loader được tái dùng, không đổi HE circuit hoặc model.

Phiếu localStorage chỉ giữ owner hash/company/snapshot/key/job, ghi trước POST; mất phản hồi đầu vẫn POST lại cùng key/body. Tải lại đọc status/result hoặc resume cùng phiên dưới quyền hiện tại. Đổi nguồn xóa DOM kết quả cũ và bỏ phản hồi trễ. Không tự tạo job khác khi failed/expired, không nâng unavailable thành điểm 0; giải thích kỳ đánh giá/thiếu nguồn/batch limit bằng ngôn ngữ nghiệp vụ. Catalog giới hạn rõ 100 snapshot gần nhất; nguồn chấm không tự cắt dòng, vẫn profile 8 dòng hợp lệ. Không bảo đảm retry từ browser đã xóa receipt hoặc thiết bị khác.

UI thử nghiệm HE riêng với luồng bốn nhánh local, chưa nối queue/active, không mở quản lý model hoặc cloud production. Chưa tự bật HE/restart/migrate live; user cần file model/grant/config thật trước vận hành. Chỉ READY_FOR_REVIEW, không thay R0–R6/D-11/D-12. Xem ../agent2/docs/HE_WEB_ANALYSIS.md và evidence/HE/web_analysis_20261112/REPORT.md.

### CR-035 — chuẩn bị C001/C002 để dùng lại

12/11/2026: người dùng giao chuẩn bị model đã fit riêng, khóa bảo vệ và 5 giao dịch mô phỏng cho C001/C002. Tạo bộ mới lưu lâu dài tại agent2/.runtime/he-company-demo, không dùng TemporaryDirectory làm bộ giao cho người dùng. Mỗi DN 32 dòng fit, 8 dòng tham chiếu khác ID/kỳ và 5 dòng đánh giá T0–T4; hai DN dùng trùng mã để kiểm scope. Hai artifact riêng trong immutable MethodStore của node demo. Vẫn Mahalanobis hai biến từ hợp đồng 33 feature, backtest mô phỏng, không accuracy/gian lận labels.

Node của bộ thử có khóa bọc và khóa ký DPAPI current-user, thư mục mới ACL user hiện tại/SYSTEM. Không thay ACL hoặc key/config của cây live. Khóa HE riêng sinh khi chấm từng job/DN và pending checkpoint AES-GCM; không coi model cần một khóa HE dài hạn chung. Worker giữ response signing key riêng bảo vệ filesystem, không HE secret key. Source/model/receipt giữ tại DN, bundle worker cũ không thêm code DN.

Lệnh prepare từ chối thư mục có sẵn, marker PREPARING ngăn sử dụng bộ chưa hoàn tất; không tự xóa/refit/ghi đè khóa cũ. Tệp người dùng nhận được xuất từ source_blobs đúng checksum của lần nhập thay vì tái sinh fixture có metadata thay đổi. Token fit/read chỉ dùng RAM trong chuẩn bị, sau fit bỏ principal khỏi file auth; node web tương lai dùng current Portal authorizer. Check dùng credential tạm RAM, đọc lại model, worker local tạm, parity/cross-scope và giữ job ID qua process mới; không refit hoặc mở dịch vụ nền lâu dài.

Đã chuẩn bị và kiểm bộ thực tế, chưa bật Portal HE/chuyển quyền mẫu vào Portal live hoặc thay DB hiện hành. Cần bước cấu hình đồng bộ worker, snapshot DB, model pins và membership demo trước dùng UI. Chỉ READY_FOR_REVIEW bộ thử; R0–R6/D-11/D-12 giữ nguyên. Xem ../agent2/docs/HE_COMPANY_DEMO.md và evidence/HE/company_preparation_20261112/REPORT.md.

### CR-036 — bật local Portal, giữ đăng nhập hiện tại

12/11/2026: người dùng giao bật Portal đăng nhập → chọn DN/dữ liệu → chạy. Có backup riêng của config.local.json; chỉ agents.agent2 đổi sang packet C001/C002, model pins, membership demo data.import và env HE. Workspace/security/company/config các agent khác không đổi. Giữ 8800/8766, worker bundle riêng 8868; không mở thêm cổng public hoặc plaintext fallback. Restart Portal làm hết session cũ, không đổi mật khẩu và không tạo credential thay cho user. Người dùng phải tự đăng nhập để xác nhận trọn luồng UI live; chưa ghi đã nghiệm thu authenticated flow khi thiếu bước này.

Portal cũ để lại interpreter con Agent2 giữ cổng; chỉ dừng đúng PID/command/parent đã đối chiếu, không kill tiến trình khác. Agent1 vẫn cùng PID trên 8011, không restart; Portal mới nhận diện đang chạy nhưng không sở hữu tiến trình từ Portal cũ. Không tự chiếm quyền/quản lý lại Agent1. Agent3/4 giữ tắt.

Bật SnapshotStore cập nhật SQLite header/WAL dù record không đổi. Nâng manifest bộ thử he-prepared-demo/1.1.0: bỏ binary hash toàn container DB, khóa checksum bốn immutable snapshot và model artifact/provenance. Trước nâng đã đối chiếu nguồn nguyên byte/data checksum và binding lịch sử với fitted model; có bản sao manifest 1.0, không refit/thay khóa. Checker dùng enterprise/check-state và worker/check-state riêng, tránh exclusive lock node web và việc WorkerStore khởi tạo lại làm hỏng job live. Chỉ dừng đúng cây Popen worker kiểm tra trên Windows. 7 focused tests cuối pass; kiểm bộ 40 checks với Portal/worker live không ảnh hưởng PID/cached jobs.

Giữ R0–R6/D-11/D-12 và full gate chưa duyệt; đây là demo loopback Windows/Mahalanobis, không production/public cloud/accuracy claim. Hướng dẫn ../agent2/docs/HE_PORTAL_ACTIVATION.md; evidence/HE/portal_activation_20261112/REPORT.md ghi rõ trạng thái user login và kiểm UI thực tế.

Cập nhật CR-036 sau người dùng trả lời đã đăng nhập trong cửa sổ vừa mở: helper ghi 7 bước pass trên Portal thật, C001/C002 mỗi bên 5 điểm đã giải mã và reload giữ cùng run ID. Không đọc/xuất mật khẩu/session; ảnh và report chỉ chứa dữ liệu mô phỏng. Trạng thái phần kích hoạt là READY_FOR_REVIEW, không tự ký nghiệm thu bảo mật/hiệu quả hoặc DONE R2/R5.

### CR-037 — vòng đời Agent2/worker và tiếp tục yêu cầu

12/11/2026: người dùng giao ba thao tác Bật/Tắt/khôi phục. Bổ sung Runtime stdlib cho Portal, cấu hình he_worker riêng; preflight private keys chạy trong Python DN, worker env/cwd/bundle allowlist tách biệt. Không nhận command/path từ browser, không đưa bridge token hoặc HE key vào worker. Signed readiness dùng challenge ngẫu nhiên/expiry/scope, node provisioning signature và worker response signature đối chiếu key ghim; không chỉ dựa health/cổng mở. RPC không đăng ký session, tính điểm hoặc tạo job.

Bật kiểm bundle/DPAPI, bật đúng worker, proof mọi scope ghim, rồi chờ node health sau kiểm GCM store. Sai khóa hoặc startup fail rollback process do Portal tạo, không ghi đè khóa/DB. Lặp Bật không nhân process. Cổng đang có process ngoài không được tự adopt/kill. Tắt node trước, đợi eval đã nhận commit ciphertext trong grace, rồi dừng đúng cây Popen worker. Restart mở cùng state/key, owner xác thực lại pending job; completed result đọc lại không cần worker.

Recover endpoint cần phiên Portal; chỉ thay worker khi node vẫn sống, giữ phiếu và ID request. Catalog chặn lượt mới khi worker/model chưa khả dụng; processor kiểm worker trước export/gửi nếu chưa có ciphertext. Outage race giữ job retryable, không tự fit/nonce mới. Ciphertext đã nhận decrypt tiếp không gọi mạng. Worker crash giữa compute/chưa commit, expiry/mất state hoặc grace timeout có giới hạn được báo rõ, không hứa tự chấm lại exactly-once mọi lỗi.

159 HE/742 native/11 browser checks pass; 7 manager và 23 durable jobs là subsets. Đã backup config/manifest, archive bundle cũ và áp dụng bundle mới cùng source vào Portal 8800; thử start-stop-start live, cả 8766/8868 dừng rồi bật lại, owned/ready true. Model/khóa/password/DB cũ và Agent1 cùng PID giữ nguyên. Portal restart một lần khi deploy làm mất phiên login; bật/tắt Agent2 riêng sau đó không reset Portal session. Không tự đăng nhập thay user. R0–R6/D-11/D-12/production/full gate giữ nguyên. Xem ../agent2/docs/HE_MANAGED_WORKER.md và evidence/HE/managed_worker_20261112/REPORT.md.

### CR-038 — đối chiếu số học, thứ tự, thời gian và khôi phục

12/11/2026: người dùng giao bảng đo rõ/HE cùng model/dữ liệu. Chỉ đọc bộ C001/C002 đã lưu, mỗi DN 5 mẫu; khóa artifact/snapshot/checksum/as_of/preprocessing, không fit hoặc sửa thuật toán/ngưỡng. Bộ đo native dùng node/state/worker riêng; không đổi Portal live. Cấm fit/publish khi chạy. Profile tolerance giữ `0.001 + 0.00001 * abs(reference)`. Join theo record/revision, thiếu/unavailable không bỏ khỏi mẫu; thứ tự chính xác báo riêng cặp đảo ngoài ngân sách sai số. Top-5/5 không là bằng chứng lợi ích chọn cảnh báo.

Timing loại một warmup/DN, sau đó 5 lượt mới/nhánh, xen kẽ thứ tự rõ/HE; rõ gồm registry/features/preprocess/score, HE từ submit tới kết quả đã giải mã/lưu, không Portal/browser/startup. Khôi phục có startup, phân theo trước claim, đóng node có kiểm soát (Jobs.close drain), hard crash trước commit. Một ca/DN/kiểu, ca ngắt hụt được báo riêng và loại khỏi mẫu số, không cộng tỷ lệ hỗn hợp. Hard crash failed/WORKER_INTERRUPTED là khôi phục thất bại dù giữ ID và fail closed.

9 unit tests pass, đo native 18 worker records: 2 warmup + 10 lượt + 6 sự cố. Sai số tối đa khoảng 1,446e-6, mọi thứ tự khớp, rõ p50 khoảng 0,12 s và HE khoảng 2 s. Khôi phục 2/2 trước claim, 2/2 kiểm soát, 0/2 hard crash. Đầu ra bảng HTML/Markdown/JSON READY_FOR_REVIEW; chất lượng toàn luồng PARTIAL, HE-AC-01 OPEN. Không chạy lại full 159/742, không accuracy/SLA/cloud/production claim hoặc tự duyệt mốc R0–R6. Xem evidence/HE/plaintext_comparison_20261112/REPORT.md.

### CR-039 — phiếu thử nghiệp vụ trước khi mở rộng feature

12/11/2026: người dùng giao đánh giá giá trị nghiệp vụ, người hiểu nghiệp vụ rà và ghi hữu ích/thời gian; xác nhận dùng C001/C002 mô phỏng để thử luồng. Chuẩn bị 10 phiếu trống theo đúng báo cáo chấm CR-038 và nguồn đã biết tại cutoff; không tự đóng phiếu hoặc đánh giá hữu ích thay người rà. Chọn tệp HTML offline riêng tại DN để thử thao tác, không thêm route/quyền vào Portal hoặc tự coi là đã hoàn thiện R4. Packet chứa cả hai DN mô phỏng, không là màn hình phân quyền production.

Packet/schema demo 1.0.0, metadata model được kiểm trước đọc frame, không deserialize/fit; giữ snapshot/checksum/model/contract/as_of và chỉ hai feature hiện có. Nguồn kế toán mô phỏng tách khỏi chứng từ gốc verified; bộ hiện không có approval/supporting_document. Ghi resolution và usefulness độc lập, chưa đủ căn cứ cần nêu thiếu nguồn/hành động, useful=yes cần hành động; mọi kết luận là tự khai trong demo. Không nhãn train, không baseline luật thì không có incremental benefit.

Tên người rà và active time từ trình duyệt chưa xác minh, không gọi là thời gian thật được máy chủ chứng nhận. LocalStorage/JSON chỉ dùng thử, revisions giữ bản cũ; tổng hợp bản cuối mỗi phiếu nhưng cộng thời gian các revisions đã gửi, không cộng nháp. Merge giữ phiếu không liên quan, exact duplicate không đếm lại; nội dung khác cùng revision hoặc dẫn nguồn ngoài manifest/case/DN bị từ chối. Không dùng checksum như chữ ký duyệt hoặc quyền truy cập. Chưa đánh giá giữ null, không thành 0%.

13 unit tests, 10 browser checks, 3 builder checks đạt. Browser fixture riêng, không tính là người thật đã rà. Packet hiện 0/10, hiệu quả nghiệp vụ chưa được xác minh. Giữ hai feature, HE-AC-01 OPEN; chưa precision/recall/SLA/production hoặc DONE R4. Xem evidence/HE/business_review_demo_20261112/REPORT.md và ../agent2/docs/HE_BUSINESS_REVIEW_DEMO.md.

### CR-040 — sửa worker chết giữa compute, giữ request/model/khóa

12/11/2026: người dùng giao sửa HE-AC-01, tiếp tục đúng yêu cầu lưu sẵn, giữ chống gửi trùng và không đổi khóa/model. Worker mới có OS file lock độc quyền mỗi state/local disk, mỗi claim có request hash/attempt/generation. Chỉ managed nonce có hash binding được resume cùng envelope; standalone replay và nonce legacy vẫn burned. Replay nonce + managed hash commit nguyên tử; stale attempt không reserve/ghi đè kết quả. Kiểm chữ ký/grant/policy/TTL trước claim/resume giữ nguyên; không có cờ bỏ replay từ client.

Worker DB version 2 thêm attempt/generation trong transaction, running managed chuyển retryable sau restart có khóa độc quyền. Legacy running chuyển WORKER_INTERRUPTED_LEGACY, terminal failure/expired không tự mở lại vì có thể đã mất private checkpoint. Chết trước commit có thể chạy lại phép toán trên cùng ciphertext, một logical job và một committed cache; không khẳng định exactly-once native compute. Chết sau commit trả cache bytes cũ. TTL tối đa 300 giây không kéo dài; missing/corrupt/rollback/copy state, multi-host/shared filesystem và mất key ngoài phạm vi.

Đã qua 202 HE/742 native/14 browser checks; 21 recovery tests là subset của 202. Full HE đầu có 1 error do test trực tiếp Worker trong process doanh nghiệp rồi enterprise.open chặn WORKER_BOUNDARY; sửa test chỉ verify signature/hash/cache, giữ guard sản phẩm và full process parity, chạy lại full 202 đạt. Managed Portal interruption cả kiểm soát/hard crash cùng job/5 điểm. Đo lại đúng model/snapshot C001/C002: 2/2 trước claim, 2/2 kiểm soát, 2/2 hard crash; 18 logical records = warmup/lượt đo/sự cố, không trùng.

Đã backup private state/manifest/bundle, dừng đúng Agent2/worker do Portal sở hữu, nâng bundle sáu module và metadata checksum; worker schema 2 và owned/ready. 6 cache worker trước nâng giữ nguyên, model/snapshot/two DPAPI keys/worker signing key/config Portal và trạng thái agent khác giữ nguyên; không restart Portal hoặc đổi session/password/quyền. Packet checker 40 pass sau nâng. Không đưa key/backup/session vào evidence/Git; không rollback replay/state sau request mới.

HE-AC-01 FIXED_READY_FOR_REVIEW trong phạm vi managed recovery; báo cáo OPEN/0-of-2 trước đó là lịch sử. Giữ 2 feature, chưa nghiệp vụ thật/queue/ML weight/cloud public/production hoặc DONE R0–R6/D-11/D-12. Xem evidence/HE/worker_recovery_20261112/REPORT.md và ../agent2/docs/HE_WORKER_RECOVERY.md.
