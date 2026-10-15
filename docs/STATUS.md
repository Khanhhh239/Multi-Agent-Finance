# Trạng thái Agent 2 (cập nhật 2026-10-15)

## 1. Đã hoàn thành và có kiểm chứng

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Đường ống phát hiện: đặc trưng quá khứ, 31 luật + đồ thị, lệch theo thực thể, mô hình không nhãn, mô hình có giám sát, chính sách cảnh báo 2+1, ca theo thực thể, lý do tiếng Việt | Chạy được đầu-cuối trên dữ liệu v3 | `agent2/pipeline.py`, thư mục `results/v3/example_run_precision` |
| Thế giới dữ liệu v3 (8 công ty) và tập niêm phong v3 (3 họ mới, đã chạy một lần) | Xong | `docs/06_ghi_chep_lam_viec/DATA.md`, `results/v3/final_sealed.json` |
| Thế giới dữ liệu v4: 30 kịch bản, 48 công ty ngẫu nhiên hóa, quy trình nền có liên kết, kiểm tra lối tắt | Xong, qua kiểm định | `agent2/world_v4*.py`, `agent2/validate_v4.py` |
| Benchmark theo thời gian trên 3 thế giới v4 | Xong | `results/v4/bench_w4/` |
| Bỏ-một-kịch bản trên thế giới v4 đầu tiên | Xong | `results/v4/lfo_w4_s411.json` |
| 3 thế giới niêm phong v4 (seed 931 đến 933, 7 kịch bản mới, 5 loại ca hợp lệ mới) | **Đã sinh và qua kiểm định, chưa chạy bộ phát hiện nào** | log sinh dữ liệu trong `docs/02_du_lieu/11_kiem_dinh_chat_luong_du_lieu.md` |
| Kiểm thử tự động | 84 bài qua (20 bài của `agent2`, 64 bài gốc của bạn bạn) | `pytest tests_agent2 tests_sme_fraud` |

## 2. Làm dở: cần coding agent kế tiếp hoàn tất

| Hạng mục | Đã có | Còn thiếu |
|---|---|---|
| So sánh phương pháp lai trên thế giới dev v4 (`agent2/eval_v4.py`) | Thế giới 411: xong P1 và P2. Thế giới 412: xong P1, P2 chạy dở (tiến trình bị ngắt) | P2 của 412 và 413, P1 của 413, P3 (doanh nghiệp mới) của cả ba |
| Chọn cấu hình theo quy tắc đăng ký trước (`agent2/select_v4.py`) | Mã viết xong, **chưa chạy lần nào** | Chạy sau khi đủ kết quả dev, ghi tệp đóng băng `work/results/v4_frozen.json` |
| Đánh giá niêm phong v4 một lần (`agent2/sealed_v4.py`) | Mã viết xong, **chưa chạy lần nào, chưa thử khô** | Thử khô trên thế giới `v4s_smoke` rồi chạy thật đúng một lần |
| Mô hình huấn luyện sẵn cho v4 | `models/pretrained_v1.joblib` huấn luyện trên v3 | Huấn luyện bản v2 trên v4 sau khi đóng băng |
| Lý do tiếng Việt cho 15 dấu hiệu đỏ của v4 | Chưa có | Bổ sung vào `ENTITY_REASONS` |

## 3. Chưa làm

- Dữ liệu doanh nghiệp thật (chưa có đối tác thí điểm); nhận dữ liệu từ MISA, hóa đơn điện tử XML.
- Chạy luật trên BPI 2019/2020 và bộ chi trả thành phố để đếm cảnh báo trên 1.000 giao dịch.
- Kiểm tra pháp lý Nghị định 13/2023/NĐ-CP cho giám sát ở mức nhân viên.
- Nối giao diện rà soát với hệ thống thật; dịch vụ API.
- Dòng hàng chi tiết trên hóa đơn (đơn giá theo mặt hàng), sao kê ngân hàng riêng.

## 4. Điều cần nói thẳng

1. AP khoảng 0,5 của mô hình có giám sát trên v4 là **giới hạn trên**: người viết bộ sinh dữ liệu cũng viết 15 đặc trưng dấu hiệu đỏ.
2. Kịch bản niêm phong v4 do cùng người viết nên chưa độc lập tuyệt đối. Biện pháp giảm thiên lệch: không thêm đặc trưng hay bộ phát hiện nào sau khi nghĩ ra các kịch bản đó, và nhãn các kịch bản đó bị ẩn khi huấn luyện.
3. Phương pháp lai (L4, hai tầng) mới có kết quả một phần; chênh lệch với L3 hiện nằm trong sai số (khoảng 3 điểm phần trăm trên khoảng 200 dòng dương). Chưa được kết luận là tốt hơn.
4. Chưa có bằng chứng về khả năng chi trả hay tần suất gian lận thật ở doanh nghiệp nhỏ Việt Nam; tính hiệu quả kinh tế dựa trên giả định (xem thư mục 03).
