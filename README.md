# Agent 2: Trợ lý Giám sát Rủi ro Gian lận Nội bộ cho DNNVV Việt Nam

Nhánh `agent2-Khanh`. Bắt đầu từ [docs/README.md](docs/README.md) và [docs/STATUS.md](docs/STATUS.md).

Vòng tiếp nhận v4 đã hoàn tất A1 đến A5, chọn L4-FB và đánh giá niêm phong trên dữ liệu tổng hợp. **Dừng theo M2:** recall S1 là 41,31%, dưới ngưỡng 50%; G5 không đạt. Không huấn luyện v2 hoặc triển khai tiếp. Xem [báo cáo niêm phong](docs/03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md) và [trạng thái](docs/STATUS.md). Bộ API, giao diện và [hướng dẫn vận hành cục bộ](docs/05_ke_hoach_giao_viec/huong_dan_van_hanh.md) là hiện vật nghiên cứu đã chuẩn bị, chưa được chấp nhận để thí điểm.

Vòng v5 được chủ dự án giao riêng sau M2: [hậu kiểm R0](docs/03_danh_gia_va_hieu_qua_kinh_te/08_mo_xe_niem_phong_v4.md) đã hoàn tất, [đăng ký trước R1](docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md) **đang chờ duyệt**. Không bắt đầu R2 trước khi chủ dự án trả lời “duyệt”. Kết luận và tệp niêm phong v4 giữ nguyên.

| Thư mục | Nội dung |
|---|---|
| `docs/` | Tài liệu theo vai trò: kinh tế và nghiệp vụ, dữ liệu, đánh giá và hiệu quả kinh tế, phương pháp và pipeline, kế hoạch giao việc |
| `agent2/` | Bộ sinh dữ liệu v3, v4, niêm phong; đặc trưng; phương pháp; đánh giá; đường ống |
| `sme_fraud/` | Mã gốc của bạn bạn (luật, đồ thị, kế toán, phản hồi); chỉ sửa `run_rules.py` |
| `tests_agent2/`, `tests_sme_fraud/` | Kiểm thử phương pháp, đầu vào, đường ống, API và mã gốc |
| `scripts/` | Tập lệnh sinh dữ liệu và thí nghiệm đã dùng |
| `results/` | Kết quả JSON, CSV (dữ liệu tổng hợp) |
| `models/` | Mô hình huấn luyện sẵn trên v3 (`pretrained_v1.joblib`) |
| `review_ui/` | Giao diện rà soát v4 nối API, cùng giao diện gốc |

Chạy kiểm thử:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
pytest tests_agent2 tests_sme_fraud -q
```

Dữ liệu sinh không nằm trong Git; xem `docs/05_ke_hoach_giao_viec/00_thiet_lap_va_quy_tac.md`. Mọi số đo là trên dữ liệu tổng hợp, không phải bằng chứng về doanh nghiệp thật.
