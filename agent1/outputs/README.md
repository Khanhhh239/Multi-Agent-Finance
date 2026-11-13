# Output của pipeline hiện tại (14/11/2026)

Đã dọn output theo pipeline T1 global → local, partial adapter, T6 và T10
đang được dịch vụ sử dụng. Catalog mặc định được xác định từ
`agent1/adaptive/t1_catalog.py`, không suy theo tên model hoặc ngày mới nhất.

| Thành phần | Đường dẫn trong `outputs/` | Lý do giữ |
|---|---|---|
| Catalog đang phục vụ | `t1/settlement_partial_catalog_v2_20261113/` | Bốn model global, prior partial, replay và hash để nạp bundle. |
| Nguồn đóng gói catalog | `t1/aligned_cashcalendar_20261113/` và `t1/global_local_catalog_v1_20261113/default/metadata.json` | Giữ bốn trial được chọn, đầy đủ model/receipt/validation, prepared data và contract; catalog v1 chỉ còn metadata cấu phần G0 mà script đóng gói đọc. |
| Dữ liệu và nguồn train lại | `t1/aligned_refit_20261112/`, `t1/compact_world_20261112/` | Giữ 22 World đủ payload/manifest, prepared data, thiết kế/seed và cache cha được builder sửa nhãn đọc; 71 context Workspace cha gồm model, prediction và receipt phải khớp nhau. Model/trial refit trước sửa nhãn đã dọn. |
| Nguồn đối chiếu của builder | `t1/landmark18_survival_cash_20261112/`, `t1/compact_ensemble_20261112_v3/` và 22 file `.py` trong `t1/global_local_families_20261113/source_snapshot/agent1/adaptive/` | Chỉ giữ reference artifact/prepared cần cho audit và module frozen mà `historical_workspace.py` còn import; các kết quả/per-context ablation và Workspace cũ đã dọn. Đây không phải model active. |
| T6 | 36 file trong `t6/`: input/bảng baseline T1, checkpoint tham chiếu Đại Phát và cấu hình/manifest | Chỉ giữ các đầu vào runner T1 còn đọc và bằng chứng dạng bảng; snapshot mã, cache, debug và payload backtest cũ đã dọn. Bằng chứng partial T6 bản cuối ở `implementation/`. |
| T9 hiện tại | `implementation/t9_canonical_runtime_verification.json`; mã trong `../agent1/reconciliation/` | Runtime dùng constrained flow và ledger; không nạp artifact từ `outputs/t9/`. Thư mục output benchmark cũ này đã dọn hết. |
| Kiểm chứng bản triển khai | T1 partial v2, T6 partial paths và T10 bundle ngày 13/11 trong `implementation/` | Giữ bộ kết quả T6 `fresh_synthetic_final/`, XML/receipt hiện hành và ví dụ T10. Smoke T1 v1 và payload T6 trung gian đã dọn. |
| Cấu hình synthetic | `../data/synthetic/` và 16 file recipe còn lại trong `data/` | Cohort/config/manifest nguồn v4 vẫn dùng để sinh World mới. Model, snapshot mã và kết quả v4 cũ trong `outputs/data/` đã dọn vì pipeline hiện tại không đọc chúng. |
| Quyết định và kiểm toán | Một `review_receipt.json` trong `analysis/`, `maintenance/`, cấu hình/gate được giữ | Receipt được tài liệu pipeline dẫn trực tiếp; các phân tích tiền triển khai đã dọn. |
| Review T1 hiện tại | 19 file trong `review/t1_ui_20261114/` và `review/t1_deep_20261114/` | Hai báo cáo lỗi còn mở, test/probe tái hiện, bằng chứng JSON/manifest, JUnit cuối và bốn ảnh chính. Chín file mã được manifest review ghi nhận vẫn khớp hash khi dọn. |

Đã loại output cũ của competing risks v5/v6, practical v6, unified, benchmark
Khánh, các phép đo T1–T9/e2e/sprint cũ, bản sao `legacy_expand`, ảnh UI và kết
quả kiểm thử cũ không thuộc chuỗi trên. Không xóa mã nguồn gốc, test, tài liệu,
dữ liệu nguồn, kho doanh nghiệp, khóa hoặc môi trường Python.

Cấu hình World, manifest, cohort và protocol thực sự chứa thiết kế/seed sinh
dữ liệu được giữ nguyên đường dẫn và nội dung, kể cả trong thư mục của lượt
đã nghỉ dùng. Kết quả chỉ nhắc tới World/seed không được coi là cấu hình.
Vì vậy một số thư mục cũ chỉ còn metadata. Manifest lịch sử không
có nghĩa mọi payload nó từng liệt kê còn tồn tại; lệnh nghiên cứu cũ có thể
cần sinh dữ liệu/chạy lại kết quả. Không sửa hash lịch sử để vượt kiểm tra.

Danh sách từng file đã xóa, dung lượng và SHA-256, cùng hash các file được
bảo vệ nằm trong [hồ sơ dọn](maintenance/current_pipeline_cleanup_20261114.json).
Kết quả kiểm thử liên quan nằm trong
[JUnit](maintenance/current_pipeline_cleanup_20261114_tests.xml).

Rà riêng `analysis/` sau lượt dọn chung: xóa thêm **39/49 file** gồm kết quả
V6/unified, bản sao share, chẩn đoán Workspace cũ và nghiên cứu global/local
trước khi triển khai partial bundle. Còn đúng **10 file**: ba manifest, năm
protocol có seed World, một thiết kế sinh dữ liệu và receipt được dẫn ở trên.
Không có file bị xóa trong lượt này là đầu vào runtime/train lại hiện tại;
tham chiếu từ runner thí nghiệm cũ chỉ phục vụ nghiên cứu đã nghỉ dùng.
Xem [phân loại từng file và hash bảo vệ](maintenance/analysis_cleanup_20261114.json).

Rà riêng `data/`: xóa thêm **70/86 file**, gồm model/snapshot v4 cũ, kết quả
v4/v5/v6/unified, calibration, log kiểm tra và sidecar của cache đã xóa. Còn
**16 file** chứa protocol/seed/shock, registry holdout hoặc cấu hình generator
đầy đủ. Giữ nguyên cả bản amendment có nhúng thiết kế World. Không coi file
chỉ chứa số đo hoặc hash của cấu hình là bản cấu hình cần giữ.

Đã kiểm lại cấu hình/manifest/vai trò của **14 World** trong recipe hiện tại
và đóng gói thành công catalog mới ở thư mục tạm từ nguồn `outputs/t1/`,
không cần các output data vừa xóa. Catalog đang phục vụ giữ nguyên hash;
không kích hoạt hoặc ghi đè artifact. Xem
[hồ sơ dọn data](maintenance/data_cleanup_20261114.json).

Rà tiếp `e2e/`, `g13/`, `implementation/`, `maintenance/`: xóa **50 file**
và **10 thư mục rỗng**, tổng dung lượng file khoảng **12,33 MiB**.

| Thư mục | Trước → sau | Nội dung đã loại |
|---|---|---|
| `e2e/` | 3 → 0 | Metadata benchmark 52 tuần cũ; thư mục đã xóa. |
| `g13/` | 2 → 0 | Kết quả chọn policy và metadata backtest cũ; thư mục đã xóa. |
| `implementation/` | 73 → 43 | Smoke T1 v1 trước partial v2; hai bộ dữ liệu/dự báo T6 trung gian. Giữ protocol khóa seed của cả hai lượt. |
| `maintenance/` | 26 → 12 | 15 báo cáo/log/inventory cũ; thêm một hồ sơ dọn mới. Còn bảy manifest khôi phục/dedup và năm hồ sơ của lượt dọn hiện tại, tính cả JUnit. |

Các manifest khôi phục lưu mapping/hash, không tự khôi phục được payload đã
mất; chúng không phải bằng chứng dữ liệu lịch sử còn đầy đủ. Cấu hình World,
manifest dữ liệu và catalog phục vụ không thay đổi. Xem
[phân loại, hash và kiểm chứng](maintenance/e2e_g13_implementation_maintenance_cleanup_20261114.json).

Protocol T6 final còn giữ nguyên nhưng khóa source khác mã hiện tại; không
sửa hash để ép chạy lại. Kết quả lưu được kiểm toàn vẹn riêng, còn dự báo
runtime hiện tại được kiểm bằng fixture mới trong bộ nhớ.

Rà riêng `t6/`: từ **755 xuống 36 file**, xóa **719 file**, **103 thư mục
rỗng**, tổng dung lượng file **111,98 MiB** (không đồng nghĩa dung lượng đĩa
thực thu hồi vì có hardlink).

| Thư mục | Trước → sau | Lý do giữ phần còn lại |
|---|---|---|
| `baseline_workspace_20261112/` | 5 → 0 | Lượt lỗi `invalid_source_changed`, không có đầu vào hiện tại cần giữ. |
| `baseline_workspace_20261112_frozen/` | 194 → 2 | Chỉ còn manifest dữ liệu và calibration generator; phép đo fallback đã được thay thế. |
| `baseline_workspace_trained_t1_20261112/` | 210 → 14 | Sáu bảng input, manifest, weekly/summary mà `compare_workspace.py` và benchmark T1 đọc; protocol/bảng kết quả, receipt lịch sử và calibration. |
| `global_scope_no_new_credit_20261113/` | 337 → 20 | Bốn checkpoint/receipt và bảng AR được runner thích nghi Đại Phát đọc; bảng/report/receipt lịch sử, protocol chứa stress recipe, manifest và calibration. |
| Các nhánh Chronos/ETS/copula/collection-policy cũ và `run_metadata.json` | 9 → 0 | Metadata/checkpoint benchmark cũ, không chứa cấu hình sinh World và không được pipeline hiện tại đọc. |

Đã xóa snapshot mã, bytecode, debug, model baseline không còn được đọc,
80 plan và 16 fixture stress của phép đo global cũ, cùng bản sao global release.
Các report/verification còn giữ là hồ sơ lịch sử; không thể dùng chúng để
khẳng định cây output lịch sử vẫn đầy đủ. Bộ `verify_results.py` cũ và replay
toàn bộ bằng `verify_t6_global.py` không còn đủ payload ở các thư mục này.
Muốn tái lập nghiên cứu phải dùng nguồn/runtime phù hợp và thư mục chạy mới,
không sửa protocol/hash cũ. Không thay đổi bằng chứng partial T6 final trong
`implementation/`, World/config nguồn, manifest hoặc catalog đang phục vụ.
Xem [danh sách xóa, lý do và kiểm chứng](maintenance/t6_cleanup_20261114.json).

Kiểm sau dọn: 5.798 hash bảo vệ không đổi; input baseline khớp fingerprint,
52 tuần số dư/đẳng thức sai số khớp dữ liệu ngân hàng và summary. Đủ 12 file
tham chiếu mà runner thích nghi đọc; bốn checkpoint khớp receipt. Catalog
hiện tại nạp thành công và dự báo mới 13 tuần chạy được, T10 khớp partial
identity. Đây là kiểm tra sau dọn, không chạy lại toàn bộ backtest lịch sử.

Rà riêng `t9/`: xóa toàn bộ **16 file** (**35.633 byte**, khoảng **34,8 KiB**)
và **17 thư mục rỗng**, tính cả thư mục gốc. Gồm 12 dấu `complete.json`
không còn bảng kết quả đi kèm, một protocol hard-case, policy/ngưỡng nguồn
Sprint 3, protocol chấm sốc cung ứng và metadata model đã mất trọng số.
Các file chỉ chứa kết quả chọn model/ngưỡng, hash và cửa sổ chấm điểm;
không chứa cấu hình generator hoặc manifest dữ liệu cần giữ.

Nguồn sinh hard-case là `scripts/build_hard_cases.py`, `agent1/synth/world.py`
và `agent1/synth/hard_cases.py`; cấu hình/manifest nguồn nằm dưới
`../data/synthetic/`. Các nguồn này giữ nguyên. Tham chiếu trong runner/gate/
report nghiên cứu cũ không phải phụ thuộc của runtime T9 hiện tại; không
chạy lại gate hoặc sửa kết quả nghiệm thu. Muốn chạy nghiên cứu cũ cần sinh
lại dữ liệu và kết quả tương ứng. Xem
[danh sách xóa, hash và kiểm chứng](maintenance/t9_cleanup_20261114.json).

Rà riêng `t1/`: **5.099 → 874 file**, xóa **4.225 file** và **760 thư mục
rỗng**. Tổng kích thước file từ **656,39 xuống 212,36 MiB**, loại **444,04
MiB**; có hardlink nên không coi đây là số byte đĩa thực thu hồi.

| Nhánh | Trước → sau | Phần còn giữ |
|---|---|---|
| `settlement_partial_catalog_v2_20261113/` | 13 → 13 | Toàn bộ catalog đang phục vụ, không đổi byte nào. |
| `aligned_cashcalendar_20261113/` | 534 → 118 | Bốn trial `customer_0`, `neural_0`, `lightgbm_1`, `xgboost_1`, dữ liệu đã sửa nhãn, contract/replay/reference và tóm tắt. |
| `aligned_refit_20261112/` | 614 → 441 | World, prepared/local rows, cache Workspace cha, frozen lock và thiết kế dùng để dựng lại dữ liệu đã sửa nhãn. |
| `compact_world_20261112/` | 256 → 229 | World đủ bảng/manifest, sampling landmarks, inventory và giao thức nguồn. |
| `landmark18_survival_cash_20261112/` | 208 → 38 | Artifact đối chiếu, prepared alignment, survival reference và cấu hình/lock cần giải thích chúng. |
| `compact_ensemble_20261112_v3/` | 168 → 8 | Artifact đối chiếu 10 feature và protocol/frozen. |
| `global_local_families_20261113/` | 1.271 → 22 | Chỉ các module frozen thực sự còn được helper import hoặc hash khi train. |
| `neural_data_ablation_20261113/` | 1.338 → 0 | Đã dọn toàn bộ mô hình/census/prediction/result của nghiên cứu development cũ. |
| `workspace_worlds_20261112/` | 315 → 0 | Đã dọn toàn bộ checkpoint/plan/SHAP và kết quả đối chiếu cũ. |
| `dai_phat_adaptation_20261113/` | 348 → 3 | Chỉ protocol có nhúng thiết kế World, manifest input và calibration generator. |
| `global_local_catalog_v1_20261113/` | 12 → 1 | Chỉ `default/metadata.json` để lấy thành viên/trọng số G0; không còn là catalog nạp độc lập. |
| Các file/nhánh legacy còn lại | 22 → 1 | Chỉ giữ `scaling_data_manifest.json`; model tuning, DA/DR/P4, inference và ngưỡng onboarding nghiên cứu cũ đã dọn. |

Giữ nguyên **59 file cấu hình/manifest/thiết kế sinh World**, kể cả bản lịch
sử. Dữ liệu nguồn, source generator, serving catalog, output T6 và bằng chứng
partial/T10 trong `implementation/` không đổi. Các cache adaptation đã sửa
nhãn có thể dựng lại từ parent; không giữ payload chỉ để mọi verifier nghiên
cứu cũ tiếp tục chạy tại chỗ. Protocol/receipt lịch sử vẫn giữ hash gốc; không
ép resume bằng cách sửa khóa source. Chạy lại nghiên cứu đã nghỉ dùng cần
thư mục mới và source/runtime phù hợp.

Kiểm sau dọn: **1.665 hash bảo vệ** khớp; **22 World/264 bảng**, **66 cặp
prepared/receipt** và **71 context Workspace cha** khớp manifest/receipt.
Đã audit lại recipe/vai trò của 14 World nguồn, đóng gói catalog riêng trong
thư mục tạm; dự báo của bốn họ model, partial prior và replay khớp bản đang
phục vụ. Đã dựng mới **tám snapshot train đã sửa nhãn** từ parent và ledger,
đối chiếu toàn bộ dataframe khớp dữ liệu hiện tại. Fixture F013 còn đọc được;
dự báo mới 13 tuần chạy thành công và T10 khớp partial identity. Không train
lại toàn bộ model hoặc kích hoạt tenant trong lúc dọn. Bốn bộ test T1 periodic,
landmark/refit, global/local families và neural data ablation: **41 passed**,
10 warning về convergence với ngân sách test nhỏ và deprecation TestClient.
Xem [phân loại từng file, hash và kiểm chứng](maintenance/t1_cleanup_20261114.json).

Rà tiếp `review/`, `rules/`, `t2_t3/`, `t7/`, `t8/`, `tgt2/`, `ui_checks/`,
`wp0/` và hai file ngoài cùng: **56 → 20 file**, xóa **36 file** (tổng kích
thước **6,95 MiB**) và **22 thư mục rỗng**.

| Phạm vi | Trước → sau | Xử lý |
|---|---|---|
| `review/` | 32 → 19 | Bỏ hai bytecode, mười ảnh phụ và XML ba probe ban đầu đã được `review_probes.xml` thay thế. Giữ báo cáo/test lỗi T1 còn mở cùng bốn ảnh training/saved forecast desktop/mobile. |
| `rules/`, `t2_t3/`, `t7/`, `t8/`, `tgt2/`, `wp0/` | 9 → 0 | Bỏ metadata hoàn tất, protocol chấm điểm, policy CUSUM và tóm tắt benchmark cũ; không chứa recipe sinh World hoặc manifest dữ liệu. |
| `ui_checks/` | 13 → 0 | Bỏ JSON fixture forecast/train và ảnh kiểm tra UI cũ ngày 11/11; có bằng chứng review hiện tại ở trên. |
| Hai file ngoài cùng | 2 → 1 | Giữ/cập nhật `README.md`; bỏ `roi_scenarios.json`, là kết quả tính ROI có thể tạo lại bằng `scripts/roi_calc.py`. |

Các protocol đã bỏ chỉ ghi hash/cửa sổ đánh giá, ngưỡng hoặc seed mô phỏng/
chọn mẫu kiểm thử; chúng không phải cấu hình generator World. Cấu hình/
manifest nguồn synthetic, source T2/T3/T7/T8/rules và catalog đang chạy vẫn
giữ nguyên. Script tổng hợp nghiên cứu cũ có thể cần tạo lại output; không
chạy lại gate hoặc thay trạng thái nghiệm thu. Báo cáo review giữ nguyên nội
dung lịch sử nên có thể nhắc ảnh phụ/XML ban đầu đã dọn; bằng chứng chính,
JSON DOM/layout và XML probe đầy đủ vẫn còn. Test tái hiện trong review là
bằng chứng lỗi còn mở, không phải bộ test đã sửa lỗi.

Kiểm sau dọn: **1.556 file ngoài phạm vi xóa** cùng **19 file review còn giữ**
khớp SHA-256; catalog bốn model nạp được, dự báo mới 13 tuần và định danh
partial T10 khớp. Test hiện có về global bundle/SHAP/replay: **1 passed**,
một warning deprecation TestClient. Xem
[danh sách xóa, lý do và hash bảo vệ](maintenance/remaining_outputs_cleanup_20261114.json).

Các artifact synthetic và kiểm thử phần mềm không chứng nhận chất lượng dự
báo trên doanh nghiệp thật hoặc tự thay đổi trạng thái nghiệm thu.
