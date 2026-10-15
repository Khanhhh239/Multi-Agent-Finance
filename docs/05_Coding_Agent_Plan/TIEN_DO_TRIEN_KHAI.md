# Tiến độ triển khai file 01–06

Phạm vi: sáu file hiện có; chưa triển khai WP-9/WP-10 (file 07 chưa có).
Các mục chưa có thí nghiệm chuẩn không được coi là hoàn thành hoặc đổi cổng thành đạt.

## Nhật ký 15/10/2026

- Đã đọc tài liệu nền và đối chiếu mã, dữ liệu, CSV hiện có. Bộ kiểm thử trước sửa: 15 đạt.
- B, E/F, T6 đã có CSV trên đĩa; trạng thái “chưa chạy” trong tài liệu không đủ để kết luận.
- Phát hiện rò rỉ trung vị tiền: `SnapshotBuilder` dùng toàn bộ hoá đơn tương lai.
  Đã chuyển sang tập hoá đơn biết tại từng cutoff và cửa sổ onboarding; thêm ca đối nghịch.
- Phát hiện hiệu chỉnh A dùng các snapshot cùng cửa sổ train và lấy phân vị mốc từ ngày O
  cho cả những cutoff hiệu chỉnh trước O. Đã tách train trước cửa sổ hiệu chỉnh và thêm B1d as-of.
- Phát hiện ensemble/CQR kế thừa CDF của mô hình gốc dù đã đổi phân vị.
  Đã tính lại phân phối từ chính phân vị; thêm lưới 9 phân vị và PCHIP cho QLGBM.
- Đã thêm hợp đồng 10 bảng, ràng buộc khoá/tham chiếu/tiền/số dư và cột đặc trưng cấm.
  Dữ liệu gốc cả bốn thế giới đạt 68/68 kiểm tra mỗi thế giới.
  Ngày sổ FIFO có thể đi trước ngày tiền của HĐ bị gán nhầm: đo tỷ lệ này như nhiễu sổ,
  không dùng quan hệ `ledger_post_date >= pay_date_true` làm bất biến.
- Đã thêm phiên bản phụ thuộc, lệnh PowerShell và cache snapshot có dấu vết nguồn/tham số/mã.
- Thí nghiệm A đang chạy lại; giữ bản cũ tại `outputs/t1/A_rolling_origin_src.v1.csv`.
  Số cũ có lỗi as-of không được dùng để khẳng định các cổng sau khi sửa đo.

## Những điều phải giữ khi tiếp tục

- `AGENT1_THREADS<=6`, `OMP_NUM_THREADS<=4`; hiện dùng 4 luồng.
- Không ghi đè thế giới `src/tgt/sens_*` khi sửa máy phát; sinh tên/seed riêng.
- Không dùng `tgt` để chọn tham số hoặc chiến lược; khoá thiết kế trước khi đánh giá.
- Không coi smoke test là bằng chứng đạt G1–G18. Kết quả và CI phải lấy từ CSV.
- Không tự điền SEC_USER_AGENT, chấp nhận điều khoản Kaggle hoặc gửi khảo sát cho người khác.
- Git hiện được nhận từ thư mục cha ngoài dự án; không stage/commit hay sửa dữ liệu ngoài Agent1.
