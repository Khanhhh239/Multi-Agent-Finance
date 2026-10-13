# Gate PLAN_02 — 12/10/2026

**Quyết định: PASS — DONE trong scope kỹ thuật `ingestion-v1`.** Owner: Codex. Input: PLAN_00 technical-functional-v1, PLAN_01 capture-foundation-v1, project-generated functional_set_v1. Không mở scope accuracy hóa đơn thật hoặc OCR inference.

## Bằng chứng theo task

| Task | Kết quả | Artifact/kiểm chứng |
|---|---|---|
| P02-T01 | DONE | ingestion/upload.py, api.py, auth.py, config.py; stream + byte/time limit, UUID staging, tenant/master pin, MIME/path tests |
| P02-T02 | DONE | detector.py; PDF/PNG/JPEG signature + MIME + extension; ZIP/XLSX, OLE2/XLS, UNKNOWN_XML bị từ chối rõ, không unzip/invoice-route |
| P02-T03 | DONE | pdf_reader.py + reader_worker.py + sandbox.py; native/render, page/pixel/text/object budgets; timeout và Windows Job Object thực tế |
| P02-T04 | DONE | PageArtifact route/reasons/regions/policy-v1.1 trong document manifests; native/scan/mixed/hidden/HYBRID/garbage và NBSP regression |
| P02-T05 | DONE | preprocess.py; affine/inverse, crop origin, PDF 0/90/180/270, EXIF6 e2e/all8 math transforms; inverse bbox tolerance 0.0001 point trong tests |
| P02-T06 | DONE | migration 002 + IngestionRepository; immutable source, manifests/renders, idempotency, job snapshot và extraction outbox atomic |
| P02-T07 | DONE | [Native baseline](plan02/native_pdf_baseline.md), [summary](plan02/baseline_summary.json); 30 source files/32 pages + 11 extra fixtures |
| P02-T08 | DONE | Process thực thoát os._exit sau raw commit/trước enqueue; recover không mất raw/audit; expired lease, stale token, rollback/outbox, bounded retry và cleanup tests; [runbook](plan02/runbook.md) |

Source tại `agent3_tax_compliance/src/ingestion/`, schemas tại `contracts/ingestion-v1/`. [Hồ sơ implementation/limits](plan02/README.md) ghi profile và các điều kiện hỗ trợ thực sự. SQLite migration chỉ nâng schema foundation 1→2; không sửa migrations 001 hoặc database prototype.

## Commands và kết quả

Cwd `D:\financial`:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/export_ingestion_contracts.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/build_plan02_baseline.py
python scripts/validate_plan02.py
```

**45/45 tests PASS**: 22 foundation regression + 23 ingestion. **7/7 schemas** hợp lệ Draft 2020-12; **38 document manifests** qua schema validation. 30 original project files là 10 logical documents (không giả là 30 hóa đơn độc lập); route confusion trên 32 trang: **11 native→NATIVE_TEXT**, **21 scan/image→OCR**. Thêm 11 fixtures, 8 thành công và 3 negative documents đúng typed error (encrypted/corrupt/oversized), không enqueue extraction cho failure.

Baseline reader latency median khoảng **123 ms/document**, max khoảng **180 ms**, 30 original samples; là parse/native/layout/render trong worker, không gồm OCR/process startup, không là production SLO. Reading-order heuristic chưa chứng minh nhiều cột/line-items. Invisible text không được tính thành native text; HYBRID yêu cầu dedup ở PLAN_03.

[Validation summary](plan02/validation_summary.json) chứa nguồn code hashes, snapshots/versions của 20 distributions (771 files), test counts/output hashes, baseline hash và hai database legacy hashes không đổi. Tests chạy bằng `.venv` riêng Python 3.10.5 Windows; schema validator dùng Python hệ thống có jsonschema. [Contract test output](plan02/contracts_test_output.txt), [ingestion output](plan02/ingestion_test_output.txt). PLAN_01 evidence giữ là lịch sử, không bị ghi đè bằng kết quả PLAN_02.

Các ca an toàn/recovery đã kiểm: cross-tenant HTTP đọc không thấy dữ liệu, viewer không upload, missing/invalid token, path traversal, spoof MIME, unknown XML/ZIP/OLE2, slow upload timeout và cleanup, stream overflow, source/audit rollback không có job, concurrent same-key chỉ một ingestion, same-key khác hash/config → 409, page/pixel limits, memory cap, timeout retries hữu hạn, document/outbox/audit commit cùng transaction, migration giữ rows v1 và từ chối database ngoài foundation.

## Giới hạn và bàn giao

- API raw byte stream + local Bearer hash-grant adapter; chưa có UI/multipart/SSO. Chỉ mở dữ liệu sau credential scope và master revision được provision. Worker hữu hạn bằng CLI, không daemon tự chạy từ API.
- Windows venv redirector + interpreter dùng 2 process trong Job Object, **tổng** memory cap 512 MiB; suspended-before-assign tránh race inheritance. POSIX path chưa kiểm trên host này. Đây là containment tài nguyên, chưa thay security sandbox production.
- Profile giữ raw gốc và canonical PNG; processed raster hiện identity sau PDF/EXIF orientation. Chưa tự detect deskew/crop nội dung. Native bbox là normalized render, có affine về unrotated PDF crop và crop_origin rõ.
- Strict reader từ chối repaired/password-protected PDF và multi-frame image; nhận diện source không hứa mọi layout sẽ đọc được. Glyph/layout diagnostics không là calibrated confidence.
- Parser job SUCCEEDED nghĩa document/page artifacts đã commit. Extraction outbox QUEUED chưa có consumer/model tới PLAN_03; chưa có field extraction/CFR hoặc kết luận thuế.
- DQ-01–05 về dữ liệu thật/nhãn độc lập/calibration vẫn chặn nghiệm thu chất lượng ở PLAN_05–06. FATURA/MC-OCR không được dùng trong baseline này.
- TestClient hiện có deprecation warning httpx/Starlette; pinned combination vượt checks. Runtime/production rollout được đánh giá lại ở PLAN_14.

**Bàn giao:** PLAN_03 nhận DocumentArtifact/PageArtifact schemas, render endpoint/storage, PageRouteDecision fields + native blocks/evidence/transform IDs và extraction outbox. PLAN_04 nhận source_order/reading_order/raw text+bbox, không suy confidence từ glyph ratio. PLAN_03 vẫn NOT_STARTED; bước kế tiếp chọn OCR worker interpreter/adapter và dedup native/OCR theo route.
