# Quy tắc dùng tài liệu trong `docs/`

- Đọc [AI_READING_GUIDE.md](AI_READING_GUIDE.md) trước khi dùng tài liệu làm bằng chứng về trạng thái dự án.
- Phân biệt kế hoạch, đặc tả, đăng ký trước, kết quả đã đo và ảnh chụp lịch sử. Với trạng thái nghiệm thu, đối chiếu `03_Evaluation/03_cong_nghiem_thu.md` và CSV gốc; với provenance synthetic, đối chiếu `02_Data/07_bo_danh_gia.md` và cohort JSON v4. Metadata còn giữ không có nghĩa Parquet còn đủ để chạy lại.
- Trước khi chạy lại, kiểm tồn kho ở `02_Data/README.md` và file thực tế. Ngày 14/11/2026, `data/` còn 10 cặp config/manifest template và 3 JSON cohort/design/calibration; không có raw/Parquet. Các thư mục làm việc `raw/interim/processed` do mã tự tạo, hiện trống. `02_Data/02_du_lieu_that_dung.md` ghi nguồn từng thử và giới hạn; cần khôi phục raw/manifest/hash đúng phiên bản trước khi dùng.
- `05_Coding_Agent_Plan/` giữ quy trình phát triển/kiểm chứng; `06_Pilot/` giữ hướng dẫn vận hành, demo và chuẩn bị dữ liệu. Không thêm nhật ký Markdown trùng với hợp đồng hoặc artifact chạy máy.
- Không xóa báo cáo lịch sử chỉ vì kết luận cũ đã bị thay thế; ghi rõ ngày, phiên bản và bằng chứng khi cập nhật kết luận.
