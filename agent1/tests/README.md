# Kiểm thử Agent 1

Chạy từ gốc repository, nơi có `agent1/` và `.venv/`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest agent1/tests/adaptive -q
.\.venv\Scripts\python.exe -X utf8 -m pytest agent1/tests -q
$uiTests = Get-ChildItem agent1/tests/adaptive -Filter '*.test.cjs' | Select-Object -ExpandProperty FullName
node --test @uiTests
```

Chọn nhóm phù hợp trước; không bắt buộc chạy toàn bộ cho một sửa tài liệu. Pytest chạy `test_*.py`, Node chạy `.test.cjs`. Test trình duyệt cần Playwright/Chrome; thiếu phụ thuộc có thể skip. Test PowerShell cần PowerShell 7, nhánh model tùy chọn có thể cần Torch. Các test dựa trên World đã dọn cần đúng dữ liệu, không tự xem skip là đã kiểm được nhánh đó.

| Nhóm | Điểm kiểm chính |
|---|---|
| `adaptive/test_t0_t9_uat_pack.py` và tests ingest/reconciliation | Chuẩn hóa, tiền nguyên, retry, phân bổ/đảo/sửa nguồn và lịch sử |
| Tests T1 periodic, registry, partial/global bundle | Nhãn/coverage, mốc thời gian, lựa chọn/audit và identity registry |
| Tests T5, T6 operating/new-company/scope/acceptance | Bảo toàn tiền, nhánh bổ sung, scope, calibration và giao thức chấm |
| Tests T10/cash explanations, UI `.test.cjs` | Snapshot/replay, giải thích/kịch bản và hiển thị |

`conftest.py` cung cấp import/CPU/fixture; `adaptive/conftest.py` hỗ trợ trình duyệt và Portal. Các ca thử dùng app/client/kho riêng. Không nối bài thử vào kho SME thật.

Tests nghiên cứu v4/v5/v6 vẫn kiểm mã còn caller; đọc [thí nghiệm](../experiments/README.md) và [tồn kho dữ liệu](../docs/02_Data/README.md) trước khi chạy. Test cơ chế, benchmark synthetic và chất lượng triển khai SME là các bằng chứng khác nhau; tiêu chí ở [nghiệm thu](../docs/03_Evaluation/03_cong_nghiem_thu.md).
