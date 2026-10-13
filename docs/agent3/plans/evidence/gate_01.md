# Gate PLAN_01 — 11/10/2026

**Quyết định: PASS — DONE trong phạm vi nền móng `capture-foundation-v1`.** Owner: Codex. Input: PLAN_00 `technical-functional-v1`, annotation/manifest schema v1 và NEW_PLAN; runtime proposal được cụ thể hóa bằng [decision record](plan01/runtime_decision.md).

## Task và bằng chứng

| Task | Kết quả | Artifact |
|---|---|---|
| P01-T01 | DONE | Runtime decision, lock 15 distributions, `.venv` riêng, snapshot 438 file hashes; import không nạp legacy/models |
| P01-T02 | DONE | FieldObject/status enums, exact Decimal codec, ISO date/currency types, schemas và tests float/status negatives |
| P01-T03 | DONE | Evidence page/block/span/bbox, invertible transforms, stable candidate ID, confidence basis/provenance validators |
| P01-T04 | DONE | CFR invoice/receipt/bank profile, observed/derived, immutable items/discovery, UNKNOWN direction bị reject |
| P01-T05 | DONE | Taxpayer master/context/relation contracts; [access matrix](plan01/tenant_access_matrix.md); tenant isolation/branch interval tests |
| P01-T06 | DONE | SQLite migration riêng; sources/masters/revisions/events/artifacts/job snapshots; atomic revision/audit, rollback/concurrency/hash tests |
| P01-T07 | DONE | 5 typed module protocols, StageResponse/errors, 17 generated schemas, registry, 7 valid/4 invalid examples |
| P01-T08 | DONE | App factory/config.example, offline unittest contract suite, public health route; không nối data endpoints hoặc legacy API |

Code: `agent3_tax_compliance/src/domain/`, `src/persistence/`, `src/app.py`, `src/config.py`; migrations/contracts/tests tại project. Profile mapping/compatibility và giới hạn nằm trong [contracts README](../../../../agent3_tax_compliance/contracts/README.md).

## Kiểm chứng tái hiện

Cwd root `D:\financial`:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe .\scripts\export_foundation_contracts.py
python .\scripts\validate_foundation.py
```

Validator dùng jsonschema sẵn có trong Python hệ thống, chạy domain/app tests bằng `.venv` riêng. Chạy riêng tests từ `D:\financial\agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/contracts -p test_*.py -v
```

Kết quả cuối: **22/22 tests PASS**, **17/17 schemas hợp lệ**, **7/7 producer examples qua cả schema/domain roundtrip**, **4/4 negative examples bị cả schema/domain reject**, **438 dependency files đúng hash**. Hai database legacy `tax_compliance.db`/`vector_store.db` có hash trước/sau lượt validation giống nhau. [Validation summary](plan01/validation_summary.json) chứa runtime, code/schema/example/test-output hashes và DB hashes; [test output](plan01/test_output.txt) ghi từng ca.

Các ca trọng yếu: `9007199254740993`/`0.1`/decimal nhiều chữ số roundtrip; float bị reject; UNKNOWN/PRESENT không qua; bank không seller/buyer; MST 13 số không tự match 10; hai reviewer cùng expected_revision chỉ một thắng; audit insert lỗi rollback head/revision/raw; reorder giữ item IDs; tenant/taxpayer/read-only isolation; source/master pin, raw hash và migration từ chối database không thuộc foundation.

## Giới hạn và bàn giao

- Chỉ nghiệm thu nền móng kỹ thuật; DQ-01–05 của PLAN_00 vẫn mở tại PLAN_05–06, không chứng nhận accuracy thực tế.
- App chỉ có `/v1/health`, không có data endpoint/auth provider/upload/OCR. Context phải được tạo từ authentication tin cậy trước mở API dữ liệu.
- CFR là profile capture tối thiểu, chưa phải đầy đủ ERP/XML/bank/rule-result wire schema. Protocols không phải implementations.
- Review service/rederive và job worker/retry chưa implement. Repository revision primitive không thay correction workflow PLAN_06.
- Offline environment snapshot chỉ đã kiểm trên Python 3.10.5 Windows; rebuild cần source packages đã pin hoặc pip installation trên máy sạch. Chưa đóng wheelhouse hay kiểm cài mạng/platform khác.
- TestClient có deprecation warning httpx; pinned combination chạy qua. OCR model/GPU/ZEN integration chưa nằm trong runtime mới; money engine boundary vẫn chặn tới PLAN_08.

**Bàn giao PLAN_02:** contracts/profile v1, repositories/migration, config/app factory và fixture factories đã sẵn sàng. Bước tiếp theo P02-T01 upload/security bounds và source storage, rồi detector/PDF per-page. PLAN_02 vẫn NOT_STARTED; không tự đánh dấu upload/OCR đã có. Ước lượng gốc PLAN_02 3–5 ngày công cần rà theo integration thực tế; không dùng thời gian sinh code thay nghiệm thu.
