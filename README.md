# Agent 2: Trợ lý Giám sát Rủi ro Gian lận Nội bộ cho DNNVV Việt Nam

Nhánh `agent2-Khanh`. Bắt đầu từ [docs/README.md](docs/README.md) và [docs/STATUS.md](docs/STATUS.md).

| Thư mục | Nội dung |
|---|---|
| `docs/` | Tài liệu theo vai trò: kinh tế và nghiệp vụ, dữ liệu, đánh giá và hiệu quả kinh tế, phương pháp và pipeline, kế hoạch giao việc |
| `agent2/` | Bộ sinh dữ liệu v3, v4, niêm phong; đặc trưng; phương pháp; đánh giá; đường ống |
| `sme_fraud/` | Mã gốc của bạn bạn (luật, đồ thị, kế toán, phản hồi); chỉ sửa `run_rules.py` |
| `tests_agent2/`, `tests_sme_fraud/` | 84 bài kiểm thử |
| `scripts/` | Tập lệnh sinh dữ liệu và thí nghiệm đã dùng |
| `results/` | Kết quả JSON, CSV (dữ liệu tổng hợp) |
| `models/` | Mô hình huấn luyện sẵn trên v3 (`pretrained_v1.joblib`) |
| `review_ui/` | Giao diện rà soát (bạn bạn) |

Chạy kiểm thử:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
pytest tests_agent2 tests_sme_fraud -q
```

Dữ liệu sinh không nằm trong Git; xem `docs/05_ke_hoach_giao_viec/00_thiet_lap_va_quy_tac.md`. Mọi số đo là trên dữ liệu tổng hợp, không phải bằng chứng về doanh nghiệp thật.
