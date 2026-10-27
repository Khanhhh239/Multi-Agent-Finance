# Runner dữ liệu train Agent 1 (v3)

> **Đặc tả runner và cách chạy.** Các bước chốt bộ cuối đã thực hiện cho `v3_final_20261027`; xem [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md) để đọc trạng thái và kết quả, thay vì coi các câu “nên chốt” bên dưới là việc chưa làm.

Chạy từ thư mục gốc repo:

```powershell
python scripts/build_final_train.py --prefix v3_review_01 --firms 40 --train-worlds 2 --stop-after audit_worlds
```

Thứ tự cổng: **kiểm nguồn → sinh smoke → kiểm dữ liệu smoke → sinh nhiều thế giới và kiểm từng bảng → kiểm phân phối/nguồn → khóa split → train T1 → đánh giá**. Có thể dừng có chủ đích, ví dụ `--stop-after sources`, `--stop-after validate_smoke` hoặc `--stop-after audit_worlds`; chạy lại với cùng prefix chỉ tiếp tục khi config, hash nguồn và toàn bộ Parquet trùng manifest. Đổi dữ liệu/cấu hình thì chọn prefix `v3_...` mới; runner không ghi đè `src`, `tgt`, `big_*`.

`audit_worlds` lưu `outputs/data/<prefix>/readiness.json`. Với thế giới đủ 2019–2025, bước này chặn `lock_split` khi thiếu nguồn OxCGRT/WDI, tỷ số doanh thu hóa đơn thuần 2025/2019 của bất kỳ **train/validation** world nào dưới 0,6, hoặc không có họ sốc giữ riêng ở test. Cổng held-out cũng áp dụng cho smoke ngắn. Ngưỡng 0,6 chỉ phát hiện xu thế sụp đổ do máy phát, **không phải tiêu chuẩn thị trường Việt Nam**. Readiness không mở kết cục hóa đơn test; chỉ kiểm manifest và `shock_truth` để xác nhận có tuần shock trong cửa sổ đánh giá. Nếu lỗi, dữ liệu đã sinh vẫn có manifest để phân tích; không được gọi đó là bộ train cuối. Kiểm toán cũ trong báo cáo 14 được sửa tiếp ở báo cáo 15.

`data/synthetic/<world>/manifest.json` chứa seed, toàn bộ `WorldConfig`, hash config, Git commit, hash mã nguồn, hash đầu vào hiệu chỉnh/OxCGRT/WDI và SHA-256 **từng bảng**. Nguồn ngoài không có được ghi `null`, không được ngầm nhận là dữ liệu thực. Cổng nguồn bắt buộc `calibration_fit.json` hợp lệ. `scripts/world_registry.py` trả lỗi khi thiếu bất kỳ Parquet nào; `--cohort data/synthetic/v3_final_20261027_cohort.json` còn đối chiếu hash manifest thế giới.

`data/synthetic/v3_final_20261027_cohort.json` khóa từng thế giới vào `train`, `validation` hoặc `test` theo **world và seed riêng**. Nó lưu mốc chia thời gian, khoảng nhãn 120 ngày và nhịp lấy snapshot. Chạy lại với danh sách/split khác sẽ lỗi. `scripts/train_manifest.py` đọc các vai trò từ file này, huấn luyện chỉ trên `train`, lưu `model.txt` và `train.json`; đánh giá riêng `validation/test` trong `evaluation.csv`. Không có tên thế giới `src/tgt` cố định trong job v3. Các script thí nghiệm cũ vẫn dùng `src/tgt` cho kết quả lịch sử.

Runner hiện tạo ba episode **cầu, cung, giá** ở train/validation, giữ toàn bộ họ **tín dụng** riêng cho hai test: `test_000` siết tín dụng đơn lẻ, `test_001` giá tăng cùng siết tín dụng. Hai lịch bắt đầu gần mốc `origin`, dùng seed khác nhau và có `reference_event` riêng trong `shock_truth`. Đó là hai kịch bản synthetic tiền đăng ký, không phải tần suất/cường độ quan sát tại Việt Nam. Test B giữ kín **tổ hợp cơ chế**, nhưng cùng một họ tín dụng với Test A; vì vậy không được gọi là hai họ shock độc lập. Seed, split, chỉ số nguồn và hash bảng giúp tái tạo/kiểm toán, không tự chứng minh độ sát thực tế Việt Nam. Nếu thư mục thế giới đã tồn tại nhưng thiếu manifest hoặc Parquet, runner dừng để tránh nhận nhầm dữ liệu dở dang. Train v3 là ứng viên T1 cố định 200 vòng; báo cáo test không được dùng để chọn lại siêu tham số. **Tại thời điểm viết đặc tả**, bộ cuối chỉ nên chốt sau kiểm toán fidelity và đánh giá miền ngoài; kết quả chốt thực tế ngày 27/10 ở [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).
