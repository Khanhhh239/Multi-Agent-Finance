# Runtime decision — foundation-v1

Ngày: 11/10/2026. Owner: Codex. Input scope: `technical-functional-v1`; contract profile: `capture-foundation-v1`.

## Quyết định

Chọn **Python 3.10.5 Windows x64**, Pydantic **2.13.4**, FastAPI **0.139.2** cho nền móng đã kiểm chứng tại workspace. Python 3.12+ trong NEW_PLAN là đề xuất ban đầu; chặng này chưa nâng interpreter để tránh gộp migration môi trường với xây contracts. Quyết định này là runtime phát triển đã thử, không là phê duyệt runtime production. PLAN_14 phải đánh giá lại interpreter/dependencies trước release.

Môi trường mới: `agent3_tax_compliance/.venv`, tách khỏi `venv` prototype và các môi trường OCR. Tạo bằng stdlib venv không system-site-packages; provision offline **15 distributions/438 file** theo [lock](../../../../../agent3_tax_compliance/requirements-foundation.lock), lấy riêng thư viện từ môi trường hiện có. Không copy toàn bộ env, model hoặc dataset. [Snapshot](environment_snapshot.json) ghi versions và SHA-256 từng file; validator kiểm lại cả hash và phiên bản import thực tế.

Môi trường nền móng không cần OCR, OpenAI, ZEN, GPU hoặc secret để import app/domain, chạy tests hoặc export schemas. SQLite dùng stdlib, database mới `.sqlite3`; không mở database legacy khi import app hoặc tạo app.

## Kiểm tra các ranh giới

| Thành phần | Bằng chứng/quyết định |
|---|---|
| Pydantic/FastAPI | Import/app health/roundtrip/negative contracts chạy trong `.venv`; kết quả trong validation summary |
| HTTP contract client | httpx 0.28.1 tương thích ca test hiện tại; Starlette 1.3.1 cảnh báo deprecation httpx. Ghi nhận để nâng client có kiểm thử khi cần, không đổi env cũ |
| OCR bridge | Benchmark cũng có package `src`; không import chung namespace. Worker interpreter/cwd và protocol được hiện thực tại PLAN_03, model load/GPU smoke chưa thực hiện |
| PDF renderer | Inventory PLAN_00 đã kiểm PyMuPDF 1.28.2/Pillow 12.3.0 trong môi trường prototype; chưa đưa vào foundation. PLAN_02 thêm dependency cần thiết và kiểm native/scan/geometry |
| ZEN | Prototype có zen-engine 0.53.0, [spike đã có](../../../../research/ZEN_CONTRACT_SPIKE_2026_10_11.md) chứng minh không nhận Decimal và mất precision số lớn; không import vào foundation. PLAN_08 phải chứng minh money boundary trước money rules |

## Tái tạo và kiểm chứng

Từ root `D:\financial`, trên workspace có môi trường nguồn nguyên vẹn, bootstrap **chỉ khi `.venv` chưa tồn tại**:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\bootstrap_foundation.py
```

Bootstrap từ chối ghi đè `.venv`, kiểm đúng Python/platform và tất cả pinned versions trước khi tạo. Sau đó:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe .\scripts\export_foundation_contracts.py
python .\scripts\validate_foundation.py
```

Lệnh validator cuối dùng Python hệ thống có jsonschema; tests/app/domain chạy trong `.venv`. Snapshot offline phụ thuộc môi trường nguồn để rebuild. Trên máy sạch có thể tạo venv bằng Python phù hợp và cài `requirements-foundation.lock` qua pip; đường cài mạng này chưa chạy trong chặng này và không có wheelhouse độc lập. Khi đổi platform/Python, tạo snapshot mới và kiểm lại; không tuyên bố các binary snapshot dùng được xuyên platform.

Không cài ASGI server trong lock nền móng. App factory được kiểm bằng HTTP TestClient; server/upload/worker runbook thuộc PLAN_02. Môi trường hiện tại đủ tái hiện checks của PLAN_01, chưa là bộ triển khai production.
