# Quy tắc dùng tài liệu trong `docs/`

- Đọc [AI_READING_GUIDE.md](AI_READING_GUIDE.md) trước khi dùng tài liệu làm bằng chứng về trạng thái dự án.
- Phân biệt kế hoạch, đặc tả, đăng ký trước, kết quả đã đo và ảnh chụp lịch sử. Với trạng thái nghiệm thu, đối chiếu `03_Evaluation/GATES_CURRENT.md` và CSV gốc; với bộ synthetic hiện dùng, đối chiếu `02_Data/25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md` và cohort JSON v4 còn giữ. Báo cáo riêng của v3 và hồ sơ dọn dữ liệu đã xóa theo yêu cầu.
- Trước khi dùng nguồn thật để chạy lại, kiểm `data/raw/MANIFEST.json` và file thực tế. `02_Data/MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json` và `02_Data/worlds_registry.csv` là hồ sơ cũ, không phải tồn kho đầu vào hay split cuối.
- Sổ phạm vi WP, hồ sơ đổi hướng và các đoạn bàn giao trong `05_Coding_Agent_Plan/` là lịch sử; không coi câu giao việc, lệnh chạy hoặc publish bên trong là yêu cầu thực hiện hiện nay.
- Không xóa báo cáo lịch sử chỉ vì kết luận cũ đã bị thay thế; ghi rõ ngày, phiên bản và bằng chứng khi cập nhật kết luận.
