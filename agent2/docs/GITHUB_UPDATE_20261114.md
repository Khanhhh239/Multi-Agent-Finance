# Agent2 v2.1 — gói cập nhật GitHub 14/11/2026

Gói được tạo từ đầu nhánh `platform-Khanh` mới nhất tại thời điểm chuẩn bị
(`198d290`), rồi đưa mã Agent2 hiện tại và phần tích hợp cần thiết vào. Không
thay cây mã nguồn Agent1, Agent3 hoặc Agent4; giữ thiết kế Portal mới, iframe
riêng cho từng Agent và cơ chế lưu phiên đăng nhập của nhóm.

Đây là bản thay Agent2 cũ bằng pipeline v2.1 đã xây dựng, gồm snapshot bất
biến, nguồn point-in-time, 35 luật tại node doanh nghiệp, thống kê/đồ thị/ML
không nhãn, adapter HE có giới hạn và luồng nhập–phân tích–phiếu rà–báo cáo.
Các màn hình và báo cáo sinh tự động của pipeline cũ đã bỏ khỏi Agent2 trước
đó không được khôi phục vào gói này. Giới hạn từng nhánh vẫn theo hướng dẫn;
không tuyên bố đã có HE cho cả 35 luật hoặc độ chính xác trên dữ liệu thật.

Phần ngoài `agent2` chỉ gồm tích hợp Portal của Agent2, gói hợp đồng đầu vào
`shared/finance_input`, đặc tả/bằng chứng `Agent2_Spec_v2_1`, báo cáo Agent2
được tham chiếu và quy tắc bỏ qua runtime. Không chứa database, model đã fit,
khóa, mật khẩu, phiên đăng nhập hoặc cấu hình local; môi trường mới phải
chuẩn bị quyền, kho model và cấu hình riêng theo tài liệu.

Kiểm tra lại **sau khi ghép vào Portal mới**:

- 64 test backend: quyền Portal, cutoff snapshot, chuẩn bị/pin model bridge,
  API phân tích và 35 luật trên nguồn đầy đủ.
- 17 kiểm tra Chrome routing: C001/C002, reload ngoài Portal, snapshot/as_of,
  tab riêng, đổi actor, thu hồi quyền, storage hỏng và phản hồi muộn.
- 12 kiểm tra Chrome luồng làm việc: nhập CSV/Excel, chấm CKKS thật, phiếu rà
  lưu trên server, retry, xem lại kết quả và xuất báo cáo.

Tất cả đạt trong môi trường tạm; không restart hoặc thay trạng thái Portal
live. Routing fixture chọn metadata landing HE4, không chạy circuit HE4;
lifecycle fit/activate trên màn hình cấu hình không nằm trong lần thử routing.

[Kết quả kiểm tra gói](github_update_20261114_checks.json).
