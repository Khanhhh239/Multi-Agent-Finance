# T1 v6 — chạy thử nghiệm ngày 01/11/2026

- [Phương pháp chung v5/v6](../../docs/04_AI_Methods/T1_COMPETING_RISKS_V5_V6.md): hazard, risk set, feature, calibration và cash head.
- [Báo cáo v6](../../docs/03_Evaluation/T1_V6_COMPETING_RISKS_2026-11-01.md): benchmark, inference và các ca chưa đạt. Bộ chọn giữ identity; v6 chưa thay model dịch vụ.

Tại gốc dự án, dùng môi trường Python khớp artifact:

```powershell
.\.venv\Scripts\python.exe -m pip install -r experiments/t1_competing_v6/requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q
.\.venv\Scripts\python.exe -m experiments.t1_competing_v6.run --stage all
```

Các stage riêng: `prepare`, `train`, `calibrate`, `fresh`, `evaluate`, `infer`.
Artifact ghi vào `outputs/data/t1_competing_v6_20261101/`; hai World mới ghi
vào `data/synthetic/v6_holdout_20261101_000/` và `..._001/`.

`protocol.json` khóa cấu hình trước khi fit. Giữ nguyên mã dùng chung, dữ liệu,
artifact v4/v5 và nguồn v5 để các phép kiểm hash tiếp tục khớp.
`preservation_before.json`/`preservation_after.json` và snapshot mã nguồn là
bằng chứng tái lập. File mới được tạo bằng chế độ exclusive; đổi cấu hình hoặc
mã sau khi khóa artifact cần thư mục/phiên bản mới.
