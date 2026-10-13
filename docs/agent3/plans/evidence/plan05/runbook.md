# PLAN_05 — Quality, calibration và review policy

Ngày: 13/10/2026. Phạm vi hiện hành: **kiểm tra chất lượng và manual review**. Chưa có calibration/threshold được nghiệm thu cho dữ liệu thực. Không chạy lại OCR, train model hoặc thêm dependency vào app env.

## Chạy assessment

Cwd: `D:\financial\agent3_tax_compliance`. Dùng cấu hình `CAPTURE_DATABASE_PATH`, auth grants và worker token của [runbook PLAN_02](../plan02/runbook.md). Token phải có WRITE cho taxpayer; không đưa token vào log/report.

```powershell
.venv/Scripts/python.exe -m src.quality.cli --taxpayer-id <taxpayer-id> --artifact-id <extraction-artifact-id>
```

Artifact ID lấy từ worker PLAN_04. Mặc định dùng head revision của CFR; có thể chọn revision đã lưu bằng `--revision <n>`. Repository kiểm tra source/hash/master và derive lại để đối chiếu. Nếu observed sửa mà derived còn cũ, worker báo lỗi `stale derived fields; rederive before quality`; PLAN_06 phải gọi rederive và lưu revision trước khi đánh giá.

Policy mặc định: `configs/quality/quality_policy_v1.yaml`. File dùng JSON syntax hợp lệ trong YAML, đọc bằng stdlib để giữ nguyên dependency. `--policy <file>` cho phép dùng policy có version khác. Policy v1 bắt buộc auto-accept false, thresholds null; không thể bật tự chấp nhận chỉ bằng đổi cờ. Khi đủ dữ liệu, việc hỗ trợ production acceptance cần một phiên bản policy/contract được kiểm chứng riêng.

## Đọc và giải thích kết quả

`GET /v1/quality-assessments/{assessment_id}?taxpayer_id=...` yêu cầu bearer auth. Trả assessment gắn record revision, input/extraction/policy/calibration/implementation hashes, completeness, field validity/reliability, recommendations và disposition.

- **Completeness** chỉ đo có dữ liệu trong mẫu số profile; INVOICE và RECEIPT có expectations riêng. NOT_APPLICABLE và NOT_PROVIDED_BY_SOURCE được loại khỏi mẫu số và báo count riêng. Ratio null khi mẫu số bằng 0. Không coi đó là 100%.
- **Critical completeness** báo riêng MST, số/ngày hóa đơn, currency và gross; tổng coverage cao không bù cho critical field thiếu. Items không đầy đủ có issue độc lập, kể cả overall fields đủ.
- **Validation VALID** nghĩa là hình dạng/format hợp lệ, chưa chứng minh OCR đọc đúng, MST tồn tại hoặc chứng từ hợp lệ pháp lý. Không có checksum MST chưa được xác minh.
- **INVALID_EXTRACTION** khác **INVALID_SOURCE_CONTENT**. Chỉ gán source invalid khi có kiểm chứng fidelity cho raw source; OCR đọc không parse được vẫn không đủ để khẳng định nguồn sai. Arithmetic mismatch mang classification UNKNOWN, yêu cầu đối chiếu.
- **Confidence** aggregate chỉ gồm field PRESENT, VALID, có calibration đúng scope/version và xác minh được mapping từ score. Báo count/coverage/mean/min; không lấy trung bình detection score. DETERMINISTIC/HUMAN_CONFIRMED không bị đổi thành probability=1.
- **eligible_within_policy** là tín hiệu kỹ thuật cho field đã có fidelity/human proof được xác minh, không phải tự chấp nhận chứng từ. Phiên bản hiện hành mọi `auto_accepted=false`, `review_required=true`.

Disposition ưu tiên REVIEW_SPLIT → REQUEST_DATA → REEXTRACT → REVIEW. Recommendations có reason/action/field và issue refs. Thiếu trang/dòng yêu cầu REQUEST_DATA; không bắt reviewer đoán giá trị. Hành động sửa/review task/UI thuộc PLAN_06. Quality không đưa tax verdict PASS/FAIL.

## Calibration và nguồn bằng chứng

`src.quality.calibration.fit` có binned mapping đơn giản với smoothing, sample/bin support và holdout Brier/ECE/reliability; `threshold_report` báo false acceptance, coverage, precision và Wilson interval 95%. Đây là công cụ để kiểm chứng khi có dataset đủ điều kiện, chưa có model calibration production được provision.

Fit chỉ nhận FIT/HOLDOUT; từ chối TEST/DEVELOPMENT và rò rỉ logical document, source hash hoặc template/vendor group giữa splits. Scope khóa field/family/engine ID, engine config version, runtime hash (gồm model assets theo PLAN_03), preprocess/extractor/score kind. Đổi trọng số/cấu hình nhưng giữ tên engine cũng mất scope. Detection score bị từ chối làm text correctness probability. Group có sample/bin không đủ hoặc domain/bin không được support trả UNAVAILABLE. Fixture synthetic dù gắn đủ flags chức năng chỉ tạo FUNCTIONAL_ONLY; predict production không dùng mapping đó.

Đầu ra VALIDATED của công cụ fit chỉ xác nhận mapping và kiểm tra dữ liệu/holdout đã cung cấp; **không tự chứng nhận target nghiệp vụ hoặc bật acceptance**. Cần owner, target, ngưỡng chọn trên holdout và frozen release test riêng. Các flags quyền dùng/nhãn/freeze cần bằng chứng của người quản lý dataset; không coi flags trong file là tự xác minh quyền hay chuyên môn reviewer.

Tham chiếu phương pháp: [scikit-learn calibration guide](https://scikit-learn.org/stable/modules/calibration). Hướng dẫn nhấn mạnh dữ liệu calibration phải độc lập; Brier không phải thước đo riêng cho calibration. App không cài hoặc import scikit-learn.

## Persistence và replay

Migration `005_quality.sql` nâng foundation DB 1–4 lên 5, thêm `quality_assessments` append-only. Lưu assessment + đầy đủ replay inputs + audit trong cùng transaction. Duplicate/concurrent call cùng input dùng lại assessment. Policy/content/version hoặc record revision đổi tạo assessment mới; không ghi đè cái cũ. Default-head call kiểm tra head lại trước commit.

`QualityRepository.inputs(ctx, payer, assessment_id)` lấy snapshot có hash. `replay(inputs, assessment)` tái hiện cùng IDs/timestamp/versions; so sánh implementation hash trước khi dùng code mới để replay lịch sử. CLI/API không nhận tùy ý source fidelity hay human verification proof từ client. Nhánh fidelity/XML và human confirmation được kiểm thử chức năng; connector xác minh proof thật thuộc PLAN_06/các adapter sau.

## Tái hiện gate

Cwd `D:\financial`:

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_quality_contracts.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_quality_baseline.py
python scripts/validate_quality.py
```

Builder tái dùng baseline PLAN_04, tạo DB bản sao và snapshots trong `data invoice/plan05_local/`. Không migrate bản baseline trước. Validator dùng system Python có jsonschema, gọi test bằng app env và ghi report vào `evidence/plan05/`, giữ report chặng trước nguyên vẹn.

Máy chưa có baseline local cần tái hiện PLAN_02–04 trước. Unit/integration tests quality độc lập với DB baseline local:

```powershell
Set-Location agent3_tax_compliance
.venv/Scripts/python.exe -m unittest discover -s tests/quality -v
```

Không sửa code trong lúc builder/validator chạy. Sau sửa implementation, chạy lại builder để snapshots khớp fingerprint. Dữ liệu hóa đơn thật/DB/token lưu ngoài git theo policy.
