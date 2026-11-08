# Cách đọc `outputs/` (cập nhật 06/11/2026)

Thư mục này chứa **bằng chứng của nhiều lần chạy**, không phải một bảng kết quả
duy nhất. Đọc ngày, cohort, `measurement_version` và giao thức trước khi so hai
file. CSV/JSON ghi kết quả của một lần chạy; sự tồn tại của file không chứng minh
hiệu quả trên doanh nghiệp Việt Nam thật.

**Dọn ngày 06/11/2026:** đã xóa output `release_gate_audit_20261026`, các bộ
v3 candidate/final/pilot, hai readiness JSON v3 và inference/chẩn đoán trần v3
theo yêu cầu. Các báo cáo riêng về ứng viên, bộ train cuối và inference v3
cùng hồ sơ dọn dữ liệu cũng đã xóa. V4, v5/v6, practical v6, benchmark
Khánh và unified v2 vẫn giữ.

| Cần biết | Nguồn đọc trước | Giới hạn |
|---|---|---|
| Cổng nghiệm thu sản phẩm | `implementation/gates.csv`, rồi [bảng diễn giải](../docs/03_Evaluation/GATES_CURRENT.md) và CSV trong cột `evidence` | G11 nằm ngoài phạm vi **giai đoạn chỉ synthetic**; pilot thật vẫn NO-GO và vẫn cần chuyên gia xác minh G11. |
| Bộ train synthetic hiện dùng | `data/v4_shortpay_4shock_20261028/`; [cohort v4](../data/synthetic/v4_shortpay_4shock_20261028_cohort.json), [báo cáo v4](../docs/02_Data/25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md) | Tám World sau sửa `short_pay`; giữ `source_snapshot.zip` và JSON hash để tái lập mã chưa commit lúc train. GO kỹ thuật không đổi cổng sản phẩm. |
| Inference T1 v4 cuối kỳ | `t1/v4_shortpay_4shock_20261028_inference_2025-12-31/` | 39.377 hóa đơn còn mở tại 31/12/2025; xem báo cáo v4 và đánh giá có xử lý kiểm duyệt trước khi diễn giải chất lượng. |
| Thử nghiệm competing risks v5 | `data/v5_competing_risks_53w_20261028/`; [báo cáo v5](../docs/03_Evaluation/T1_V5_COMPETING_RISKS_2026-10-28.md) | Thử nghiệm riêng trên cohort v4; chưa thay thế T1 v4 trong sản phẩm. |
| Thử nghiệm T1 v6 | `data/t1_competing_v6_20261101/`; [báo cáo v6](../docs/03_Evaluation/T1_V6_COMPETING_RISKS_2026-11-01.md) | Train/đánh giá/inference riêng, bảo toàn v4/v5. Brier giảm nhẹ, nhưng hiệu chuẩn ở World khó và cash head chưa đạt đồng đều; chưa thay model dịch vụ. |
| Kết quả mô hình cũ và ablation | `t1/`, `t2_t3/`, `t4/`, `t6/`, `t7/`, `t8/`, `t9/`, `e2e/`, `g13/`, `tgt2/`, `berka/`, `sprint5/`, `rules/`, `wp0/` | Những thư mục này thuộc nhiều giao thức và tập test khác nhau. Không trộn vào `v3_final_20261027` hoặc dùng test để chọn lại mô hình. |
| Dịch vụ và pilot | `service/`, `pilot/` | `service/docker_check.json` là lần kiểm ngày 20/10, Docker không khởi động. `pilot/privacy_t9_parity.csv` đo ẩn danh trên synthetic; `pilot/pilot_metrics.csv` **chưa có**, nên chưa có kết quả pilot thật. |

## Bản lưu và ảnh chụp lịch sử

- `*.legacy_expand.csv` là 181 bản sao trước khi sửa `expand`, có SHA-256 trong
  `implementation/legacy_expand_backups.json`. Kiểm tra ngày 27/10: đủ 181 file,
  tất cả hash khớp; 110 file hiện vẫn trùng byte với bản đang dùng, 71 file đã
  khác. Giữ chúng để đối chiếu giao thức, không tự chọn bản nào có điểm đẹp hơn.
- `implementation/run_status.json` ghi cả các lần thất bại hoặc gián đoạn.
  `implementation/test_summary.csv` và hai JUnit XML ghi **316 ca của lần chạy
  cũ**, không phải số test của mã đang chỉnh. `implementation/report_reproducibility.json`
  là phép kiểm ngày 20/10; `implementation/publish_manifest.json` là ảnh chụp
  công bố cũ. Hai file này còn nhắc `docs/RESULTS_TABLES.md` đã được bỏ vì trùng
  với báo cáo Evaluation, nên không dùng chúng để khẳng định working tree hiện tại
  đã qua kiểm tái lập hoặc đã được công bố.
- Một số `run_summary.json` lưu đường dẫn tuyệt đối của máy lúc chạy. Khi mở ở
  workspace khác, tìm file theo đường dẫn tương đối trong repo và kiểm hash;
  không chạy lại trực tiếp đường dẫn tuyệt đối cũ.

Artifact v4 ở `data/v4_shortpay_4shock_20261028/` còn giữ; model v3 đã xóa.
Model nghiên cứu chưa được phép triển khai cho doanh nghiệp thật. Không dùng
đường dẫn hoặc hướng dẫn Git LFS của v3 trong tài liệu cũ như xác nhận rằng
dữ liệu v3 còn trong workspace; đọc tồn kho hiện tại và manifest trước khi chạy.

## Dọn lưu trữ 31/10/2026

Xem [báo cáo dọn file](maintenance/cleanup_2026-10-31.md) và
[manifest SHA-256](maintenance/cleanup_2026-10-31.json). Các bản sao payload T0
đã được gộp về ba bộ `final` còn nguyên; báo cáo/metadata của từng lần chạy vẫn
giữ lại. Dùng [script khôi phục](../scripts/restore_cleanup_duplicates.ps1)
khi cần đủ đường dẫn cũ. Các cohort synthetic, model, snapshot mã nguồn và
181 bản `legacy_expand` được giữ nguyên.

## Rà soát tài liệu 01/11/2026

Hai bản tổng hợp phương pháp v5/v6 đã gộp thành
[một tài liệu chung](../docs/04_AI_Methods/T1_COMPETING_RISKS_V5_V6.md).
Các bảng benchmark v6 bổ sung được đưa vào báo cáo Evaluation v6.
Tại lần rà soát 01/11, báo cáo v3/v4/v5, model, dữ liệu, snapshot mã và các
manifest hash được giữ để tái lập. Đợt dọn 06/11 đã bỏ dữ liệu và output v3
như ghi ở đầu trang; báo cáo lịch sử vẫn giữ, không chứng nhận khả năng chạy lại.
