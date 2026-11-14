# Runtime — đặc tả triển khai

**BẮT BUỘC:** áp RULE-REUSE-01, RULE-TIME-01, RULE-FIT-01, RULE-SCORE-01, RULE-CASE-01, RULE-RELEASE-01 trong [00](00_INDEX_va_quy_tac.md). Schema/state dùng [04](04_contracts_states_modules.md). Ngưỡng xem [99](99_decision_log.md).

## Dữ liệu và feature (R1)

Dùng transactions, vendors/bank_history, invoices, payment_allocations, employees/approvals, supporting_documents. Mọi bảng có tenant, định danh và thời điểm quan sát phù hợp. Posted-mode là cấu hình thử D-02. Pre-payment cần contract riêng.

Kiểm tra kiểu, thứ tự thời gian khi áp dụng, trùng ID và liên kết danh mục. Không từ chối bút toán điều chỉnh chỉ vì số âm. Replay nhóm đồng thời từ lịch sử trước nhóm. Nhiều hóa đơn–nhiều khoản chi phải qua allocation.

Feature đề xuất: amount_to_vendor_median, days_since_bank_change, bank_change_verified, prior_paid_same_invoice, projected_overpayment_vnd, prior_invoice_payment_count, approval_limit_ratio, creator_equals_approver, reference_count và missing flags. FeatureContract khai báo cột/thứ tự/dtype/đơn vị/cửa sổ/peer group/cách chia 0 và missing. Không dùng ID, nhãn, template/seed sinh hay kết luận tương lai làm predictor. Lưu nguồn bằng chứng để truy lại.

## Detector và adapter (R2)

Giữ luật có điều kiện/ngoại lệ đúng, hàm điểm/xác suất, đồ thị tại as_of và ML không nhãn hiện có. Map output thành MethodScore. Adapter score không gửi alert, không đổi active config.

| Phương pháp | Thành phần cần có để chấm |
|---|---|
| EntityDeviation | Lịch sử/peer group tham chiếu đủ điều kiện |
| ECOD/HBOS | Phân phối đã fit và transform tương thích |
| IF | Cây đã fit, preprocess và schema |
| AE | Trọng số, preprocess và schema |

Tối thiểu lịch sử theo D-03. IF/HBOS/AE không bắt buộc bật tất cả. Fit job tạo artifact theo DN, version và snapshot; request inference chỉ load/score. Thiếu khả năng trả unavailable rõ lý do. Graph chỉ trả quan hệ/bằng chứng đã biết, không suy ý định gian lận.

Chuẩn hóa theo reference quá khứ cố định; thống nhất chiều điểm, định nghĩa ties. Hàm score cũ phải xác định là probability/rank/heuristic trước tái sử dụng. Weighted average là ứng viên, trọng số và fallback theo D-04; không tự chọn số sản xuất.

## Orchestration, vụ và policy (R3)

Snapshot → feature → mọi phương pháp khả dụng → score matrix → ensemble → case → policy → queue. Các phương pháp trả dữ liệu, chỉ policy/delivery tạo quyết định gửi.

Gộp theo DN + họ vấn đề + nghĩa vụ/chứng từ; cùng NCC chưa đủ. Giữ candidate_ids và evidence_ids riêng. Đề xuất max-score trên candidates (D-05); không tăng điểm chỉ vì nhiều bằng chứng. Case stable ID và revision, thay đổi đáng kể mới xét gửi lại.

Policy tuyến bắt buộc theo D-07; ưu tiên áp ngưỡng đã khóa rồi budget D-06; lưu mọi lý do không gửi. Backlog xét lại theo hiệu lực. Atomic budget reservation và delivery idempotency bảo đảm concurrency. Shadow dùng namespace riêng và không chiếm budget active.

## Đánh giá và vận hành (R6)

Tách train/history, validation chọn tổ hợp, validation policy/ngưỡng, test tương lai; giữ cùng episode trong một tập. Chấm ngoài mẫu theo thời gian. So baseline mới/cũ ở cùng case policy/budget khi so detector; khi thay policy, báo riêng ảnh hưởng từng thay đổi.

Báo số vụ đúng, precision trên vụ có kết luận, tỷ lệ có kết luận, false alerts/DN/tuần, thời gian thao tác và thời gian chờ riêng, tài nguyên và fallback. Rà mẫu không cảnh báo với xác suất lấy mẫu để ước lượng bỏ sót. Release gate theo D-09; số liệu synthetic không thay validation thật. Drift kích hoạt điều tra, không tự phát hành model.

Lưu bundle gồm feature/preprocess/model/reference/ensemble/fallback/grouping/policy versions; rollback đổi bundle tương thích và giữ audit, feedback, delivery ledger.
