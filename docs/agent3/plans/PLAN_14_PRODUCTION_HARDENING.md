# PLAN_14 — Bảo mật, quan sát, tải và phát hành có thể phục hồi

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_13](PLAN_13_ERP_CONNECTOR.md) · Sau: [PLAN_15](PLAN_15_RECONCILIATION_FUTURE.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Đưa phạm vi đã nghiệm thu vào môi trường vận hành với dữ liệu được bảo vệ, tài nguyên bị giới hạn và khả năng khôi phục được chứng minh.

- Phụ thuộc bắt buộc: PLAN_09 và mọi adapter/feature được chọn cho release đã đạt gate.
- Ước lượng: **5–10 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 12, 13, 14, 16.
- Đầu vào: Release manifest, supported adapter list, data classification, expected traffic và retention requirements.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Auth, upload bounds, worker isolation và audit đã phải có từ chặng đầu; PLAN_14 kiểm sâu và hoàn thiện vận hành, không trì hoãn các bảo vệ tối thiểu tới cuối.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/deploy/; src/security/; src/observability/; tests/security/; tests/load/; operations runbooks`

ReleaseManifest pin code/schema/models/config/rules/legal/taxonomy/calibration. Telemetry dùng request/job/evaluation IDs, stage/model versions, latency/resource/error counters; không chứa raw invoice/MST/account. Backup/replay phải bảo toàn audit và artifact hashes.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P14-T01 — Threat/data-flow review theo phạm vi

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Rà upload/parser/worker/storage/API/provider/connector và cross-tenant boundaries; gán issue owner và mức ưu tiên theo dữ liệu thật.
- Đầu ra: threat_review.md.
- Kiểm chứng: Chỉ yêu cầu kiểm liên quan feature đã chọn; không gán unsupported connector vào release.

### P14-T02 — AuthZ và evidence access

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Test object-level authorization mọi endpoint/job/export/evidence URL; secret rotation và least privilege.
- Đầu ra: security report.
- Kiểm chứng: Tenant A không đoán ID rồi truy cập artifact B; expired evidence links bị chặn.

### P14-T03 — Resource/load tests có workload

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Xác định pages/file, concurrent jobs, peak queue; đo CPU/RAM/VRAM, p95 và backlog drain. Tách cold model load khỏi warm path.
- Đầu ra: capacity_report.md.
- Kiểm chứng: Giới hạn concurrency ngăn OOM; quá tải trả queue/backpressure rõ, không silently drop jobs.

### P14-T04 — Observability và alerts

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Metrics stage latency/errors/review rate/calibration drift/coverage và queue age. Logs masked; dashboard triage theo request/evaluation IDs.
- Đầu ra: dashboards + alert runbook.
- Kiểm chứng: Alert thử lỗi worker/queue có người xử lý và next steps; không lộ nội dung chứng từ.

### P14-T05 — Backup/restore và retention

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Backup database + raw/artifact store nhất quán; chạy restore drill, kiểm hash/revision/audit, xử lý retention/deletion theo policy đã xác định.
- Đầu ra: restore_report.md.
- Kiểm chứng: Restore có replay evaluation; không chỉ chứng minh tạo được file backup.

### P14-T06 — Migration/release/rollback

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Test migration trên copy có dữ liệu mẫu, schema compatibility, canary scope và rollback plan; old evaluations vẫn đọc được theo version.
- Đầu ra: release_runbook.md.
- Kiểm chứng: Rollback code không làm hỏng records mới; không xóa legacy database.

### P14-T07 — Adversarial regression

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Upload XXE/zip bomb/corrupt PDF, API idempotency conflicts, stale outcomes, correction races và prompt injection nếu có LLM.
- Đầu ra: release_regression_report.
- Kiểm chứng: Các invariants tiền/version/unknown/tenant vẫn qua dưới retry và lỗi.

### P14-T08 — Operational acceptance

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chốt workload SLO bằng capacity thực đo, recovery targets bằng restore test; diễn tập incident, lập danh sách còn hạn chế. Chuẩn bị package/config cụ thể trước bước phát hành môi trường thực.
- Đầu ra: gate_14.md + release manifest.
- Kiểm chứng: Không ghi production ready chỉ vì test unit qua; mọi thành phần trong manifest có evidence và runbook.

## 5. Tiến độ bên trong chặng

- Ngày 1–2: threat review/AuthZ và workload definition.
- Ngày 3–4: capacity/limits/observability.
- Ngày 5–6: backup/restore và migrations.
- Ngày 7–10: regression, incident drill và release package.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Queue backlog tăng khi OCR worker chết.
- [ ] Access evidence của tenant khác qua signed link.
- [ ] Restore database nhưng thiếu raw artifact.
- [ ] Rollback trong lúc có evaluations schema mới.
- [ ] Logs chứa full MST/account bị phát hiện và chặn.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** M4: release scope qua isolation/resource/recovery/version checks; backup restore thực chạy; có SLO và operator runbook từ số đo. Việc triển khai môi trường thực theo quyền và hạ tầng của phiên triển khai, không tự coi tài liệu này là đã deploy.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_14.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: Vận hành theo release manifest; PLAN_15 là feature riêng cần gate riêng, không lẫn với hardening.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
