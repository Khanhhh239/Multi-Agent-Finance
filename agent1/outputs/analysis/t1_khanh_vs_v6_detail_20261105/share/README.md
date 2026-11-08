# Gói so sánh T1 gửi Khánh

Mở [T1_V6_SO_SANH_GUI_KHANH.md](T1_V6_SO_SANH_GUI_KHANH.md) để đọc báo cáo.
Các đường dẫn bằng chứng trực tiếp trong bản này dùng file đi kèm.

Đối chứng gồm HazardGBM mặc định từ mã Khánh tại commit 70c0ceb, tái train
trên cùng 200.000 snapshot, và model V6 đã khóa ngày 01/11. Đây không phải
booster lịch sử Khánh đã push. Chấm cùng 65.221 anchor trên sáu World.

Kết quả chính: Brier Paid 28/91 ngày giảm 1,67%, ở 365 ngày giảm 25,72%.
Cash head V6 tốt hơn khi gộp theo công ty ở 91–365 ngày, nhưng kém hơn
ở từng hóa đơn. Báo cáo ghi đầy đủ CI, kết quả từng World, các nhóm quá
hạn và các trường hợp V6 chưa thắng.

Gói gồm báo cáo, CSV/JSON bằng chứng, metadata, kiểm thử đã lưu và mã
nguồn đối chứng. Gói không chứa các World Parquet, trọng số model hoặc
môi trường Python; chạy lại toàn bộ cần repo và dữ liệu gốc theo protocol.
SHA-256 của các file đi kèm nằm trong MANIFEST.json.
