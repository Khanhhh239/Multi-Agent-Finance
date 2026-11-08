fix(agent1): unify T0/T9/T1 around reviewed cash history

Thống nhất luồng T0 Khánh → lõi phân bổ T9 từ Thắng → duyệt và ledger →
snapshot theo ngày đã biết → train/dự báo/giám sát → T10/API cho Agent 4.
Đề xuất đối soát chỉ trở thành lịch sử thu tiền sau khi được xác nhận.

- T0 chuẩn hóa ngày trên các đường nhập, giữ lịch sử khách hàng/lời hứa/lịch
  chi và đối chiếu toàn bộ nội dung nghiệp vụ khi nhập lại cùng phiên bản.
  Giao dịch ngân hàng bất biến; thay ngày biết, remittance hoặc tài khoản/kỳ
  sao kê phải báo lỗi thay vì âm thầm bỏ qua.
  Chọn phiên bản và áp dụng sự kiện hủy đều đợi ngày muộn hơn giữa
  available_on/known_at. Nhập lại sự kiện hủy nguyên nội dung giữ nguyên
  nguồn; ID nội bộ và ngày nạp lại không gây xung đột giả.
- T9 lưu quyết định mã hóa, có idempotency và đảo quyết định. Kiểm tra lại
  khách hàng, ngày lập và số tiền sau revision; write-off gắn với khách hàng
  và chứng từ ban đầu. Credit note và sửa giá trị không được tạo ngày thu
  đủ giả. Giữ nguyên mã nguồn upstream và kiểm hash theo provenance.
- T1 dựng mẫu tại từng cutoff, dùng dư nợ còn lại sau khoản thu đã biết;
  loại mẫu bị ảnh hưởng bởi khoản thu trước cutoff nhưng duyệt muộn.
  Áp dụng trạng thái mở từ ledger trước khi tính đặc trưng tổng hợp; giữ cả
  dư nợ VND còn đúng 1 đồng. Dùng ngày muộn hơn giữa available_on/known_at.
- Tách retrain/chọn phiên bản khỏi inference. Dự báo dùng model được chọn
  hoặc B1d; không tự fit T1/T4. Validation chấm cả hóa đơn chưa trả có đủ
  theo dõi và so với baseline tại 7/28/56/91 ngày.
- Thêm --prepare-only để xuất train/validation mã hóa kèm manifest, hash,
  nguồn và các cửa sổ thiếu lịch sử. Không ghi đè dataset hay tự kích hoạt
  model. Xóa retrain-demo.json lỗi thời; giữ nguồn và model nghiên cứu độc lập.

Kiểm thử toàn bộ sau lần kiểm tra tiếp: **656 passed, 2 skipped**, không có
failure/error. Bốn regression mới kiểm chứng ngày biết của revision/hủy
hóa đơn và retry sự kiện hủy. Kiểm chứng mới nhất được lưu trong
outputs/maintenance/t0_t9_t1_publish_followup_20261106.json và JUnit tương ứng;
giữ nguyên báo cáo lần rà soát trước làm bằng chứng lịch sử.
Kiểm tra Ruff lỗi nghiêm trọng, git diff --check, cú pháp JavaScript và
tham chiếu DOM của dashboard đều đạt.

Chưa có dữ liệu doanh nghiệp để dựng bộ train hoặc đo chất lượng thực tế.
Synthetic chỉ dùng kiểm tra kỹ thuật; các kết quả này không thay nghiệm thu
miền thật, không đổi NO_GO và không kích hoạt T1 V6. Việc tích hợp Agent 4
được cung cấp qua API; không có thay đổi mã Agent 4 trong đợt này.
