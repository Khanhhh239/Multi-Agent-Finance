# CR-021 — bật Agent2 và kiểm thử trực tiếp

**Agent2 đang chạy tại http://127.0.0.1:8766**, loopback, trang trạng thái + backend hiện có. Không phải UI nghiệp vụ R5. Server được giữ chạy sau kiểm thử.

- [24 kiểm tra HTTP thực](live_http/summary.json) đều qua: health/status; kiểm quyền trước dữ liệu (401/403), Origin lạ; validate dữ liệu và lỗi có dòng/trường/cách sửa; upload/preview/commit; retry; đọc manifest/data và checksum; chặn snapshot khác DN; đổi source làm preview cũ bị từ chối 409; manifest sai bị từ chối 422; route cũ 410.
- Snapshot được lưu qua **HTTP**, sau đó dùng quyền do FileAuthorizer xác nhận để tạo feature/chấm bằng Python. [3/3 dòng](live_http/score-results.json), [33 feature](live_http/features.json); hai khoản đồng thời mỗi row 0, một group check 20. Tổng rules còn null. ECOD thiếu artifact trả artifact_missing, không tự fit.
- Sau retry chỉ có **1 snapshot** trong DB demo; có 3 import dùng thử (một committed, một đổi source chưa lưu, một manifest sai). Payload đọc lại đúng checksum, không bị chấm ghi đè.
- [76 kiểm thử backend](backend_tests.json) qua, 0 lỗi/thất bại/bỏ qua, 27.751 giây: validate/auth, snapshot protocol và transition server. [Log](backend_tests.log).
- [Audit P1 hiện tại](p1_audit/summary.json): 7 ca; canonical assertions đạt, nhưng **exit 2** vì **P1-NATIVE-LATE-INVOICE vẫn OPEN** ở raw/native. Chưa sửa thuật toán trong lượt bật/test này, không gọi là nghiệm thu engine.

## Cấu hình đang dùng

Runtime mới riêng: agent2/.runtime/live_check_20261111; DB snapshots.sqlite3. Chỉ fixture tenant demo/C001, credential local ngẫu nhiên hạn 8 giờ; không có token trong báo cáo/evidence. Không dùng DB cũ, không thay active/model hoặc fit nghiệp vụ. Chi tiết PID, thời điểm và lệnh chạy ở [provenance](provenance.json). Không dừng nhầm process khác; server 8766 vẫn được giữ chạy.

Health pipeline_ready=false và active_delivery=false là giới hạn đúng hiện trạng. Có JSON import và job/score Python/CLI, chưa có màn hình nhập CSV/Excel, chọn model, HTTP scoring, hồ sơ/hàng đợi mới hoặc Portal identity. Các route cũ trả 410 theo thiết kế. Mở URL hiện chỉ thấy trang trạng thái.

IAB không khả dụng và Chrome automation lỗi timeoutMs; đã thử kết nối browser nhưng không xác nhận giao diện bằng trình duyệt. Kiểm tra trang bằng HTTP (200/HTML); không tuyên bố đã kiểm thao tác UI chưa tồn tại. User có thể mở link trực tiếp trên máy.

## Lỗi và việc tiếp theo

Ưu tiên sửa guard thời gian P1 raw/native và rà lịch sử/batch trước khi dùng đường đó cho nguồn đến muộn. Canonical snapshot đang chặn đúng, nhưng toàn pipeline vẫn R2 PARTIAL. UI nghiệp vụ và tích hợp đầy đủ là việc riêng, không phải lỗi cài đặt server. Mã chấm/sources/schema giữ nguyên theo hash CR-019; [CR-020](../p1_recheck_20261111/REPORT.md) có chi tiết finding.
