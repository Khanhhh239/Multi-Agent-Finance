# PLAN_04 — Chạy extraction và kiểm chứng

Ngày: 12/10/2026. Runtime ứng dụng: `agent3_tax_compliance/.venv/Scripts/python.exe` (Python 3.10.5). Không thêm dependency, tải model hoặc train OCR. OCR mặc định vẫn là PP-OCRv6 + VietOCR; extraction chỉ nhận `NormalizedDocumentExtraction`.

## Chạy một tài liệu

Cwd: `D:\financial\agent3_tax_compliance`. Dùng cùng cấu hình auth/database của [PLAN_02](../plan02/runbook.md). `CAPTURE_WORKER_TOKEN` là credential có quyền WRITE cho taxpayer; không ghi token vào tài liệu/log.

```powershell
.venv/Scripts/python.exe -m src.extraction.cli --taxpayer-id <taxpayer-id> --ingestion-id <ingestion-id> --ocr-config-key <config-key>
```

`config-key` lấy từ kết quả worker PLAN_03. Phải có OCR result đã commit, kể cả native-text result. Worker extraction không chạy lại OCR. Lần đầu tạo CFR revision 1 + artifact + audit trong cùng transaction; gọi lại cùng input/profile/code/master trả artifact cũ, giữ `item_id`. Profile hoặc code thay đổi tạo artifact và record mới, không tự sửa record trước.

Profile tùy chọn qua `--profile <file.json>`:

```json
{"version":"invoice-vi-v1","number_locale":"AUTO","date_order":"DMY","default_currency":null,"currency_policy_reference":null}
```

`AUTO` tiền giữ các cách parse cạnh tranh (ví dụ `1.234`); `date_order=AUTO` giữ hai ngày khi `03/04/2026` mơ hồ. Chọn VI/EN hoặc DMY/MDY bằng profile có version theo nguồn đã xác nhận. Không tự mặc định VND; currency fallback cần cả currency và policy reference. Không làm tròn tiền: bước tính thuế/nghiệp vụ phải cung cấp rounding policy riêng sau này.

## Đọc kết quả và evidence

Các endpoint đều yêu cầu `Authorization: Bearer …` và query `taxpayer_id`:

- `GET /v1/cfr-extractions/{artifact_id}`: artifact có CFR, candidates/raw scores, identity map, VAT groups, derivation DAG và issues.
- `GET /v1/cfr-extractions/{artifact_id}/evidence/{candidate_id}`: kiểm tra hash/scope/block/span rồi trả vùng render và vùng gốc, crop origin, transform/OCR/extractor versions. Dùng API raw/page image của PLAN_02 để hiển thị vùng.

`record=null` + `segmentation.status=REVIEW_SPLIT` khi có các số hóa đơn cạnh tranh. Không gộp nhiều hóa đơn thành một CFR. Trường hợp không có đủ nhãn để phát hiện boundary vẫn yêu cầu review; parser chưa chứng minh một file chỉ có một hóa đơn.

**Consumer phải đọc `review_required` từ artifact.** `PRESENT` chỉ nghĩa là parser có giá trị quan sát, chưa chứng nhận đúng hoặc hợp lệ. Phiên bản này bắt buộc `review_required=true`; không dùng CFR độc lập để tự động duyệt hoặc ra kết luận thuế. Scores detector nằm ở `candidates[*].raw_scores`, field confidence vẫn UNAVAILABLE.

## Replay / correction / item identity

```python
updated_record, manifest, issues = rederive(observed_revision, pinned_master, profile, relations)
affected = affected_nodes(previous_manifest, ("parties.seller.tax_id",))
```

Import từ `src.canonicalization.derive`. Reviewer sửa observed field phải gọi lại `rederive` trước quality/planning. Hàm giữ totals quan sát, thay toàn bộ derived direction/counterparty/totals, tạo manifest hash và issues mới. Caller PLAN_06 chịu trách nhiệm lưu revision và audit correction; PLAN_04 chưa có endpoint sửa.

`canonicalize(...)` nhận đầy đủ normalized document, format, master/profile, identity map, record/artifact IDs, timestamp và extractor hash; cùng input cho cùng output. `extract(...)` là lớp cấp UUID/timestamp và fingerprint implementation. `allocate(...)` trong `identity.py` yêu cầu mapping tường minh khi re-extract. Đổi tập IDs phải có SPLIT/MERGE lineage bao phủ đủ IDs cũ/mới; không fuzzy match theo tên, tiền hoặc line number. Foundation `append_revision` vẫn giữ nguyên tập item IDs; lưu revision split/merge thuộc PLAN_06.

## Schema / storage

7 schema mới: `agent3_tax_compliance/contracts/extraction-v1/`. CFR foundation giữ schema cũ; VAT group/identity/DAG nằm trong extraction artifact. Artifact mới chỉ thêm lớp bao, không thay wire contract OCR.

Migration `004_extraction.sql` nâng DB foundation từ 1/2/3 lên 4, thêm `cfr_extractions` append-only. Không migrate DB prototype. Baseline chỉ dùng hai bản sao tại `data invoice/plan04_local/{native,hybrid}.sqlite3`; DB/evidence PLAN_02–03 giữ nguyên. Không đưa dữ liệu hóa đơn thật/token/DB vào git.

## Tái hiện kiểm chứng

Cwd: `D:\financial`:

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_extraction_contracts.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_extraction_baseline.py
python scripts/validate_extraction.py
```

Hai lệnh đầu dùng app env; validator dùng Python có `jsonschema`, gọi test bằng app env. Baseline tái dùng artifacts/SQLite local đã có của PLAN_02–03; không tải dữ liệu hoặc gọi OCR. Nó kiểm tra idempotence, pure replay, schema, resolve evidence và lưu predicted CFR ở `data invoice/plan04_local/`. Nếu máy mới chưa có baseline local, cần tái hiện PLAN_02–03 trước; các kiểm thử self-contained vẫn chạy được:

```powershell
Set-Location agent3_tax_compliance
.venv/Scripts/python.exe -m unittest discover -s tests/extraction_v1 -v
```

Validator ghi report mới trong `evidence/plan04/`; không ghi đè report chặng trước. Chạy lại builder sau khi sửa implementation để kết quả và fingerprint khớp. Không sửa code trong lúc baseline/validator đang chạy.
