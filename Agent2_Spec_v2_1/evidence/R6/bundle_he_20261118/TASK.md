# CR-063 — nối HE thật vào bộ điều phối bundle chung

Nguồn: người dùng giao 18/11/2026, yêu cầu nối các worker HE hiện có vào bộ điều
phối bundle chung thay vì chỉ chạy shadow tại doanh nghiệp; nhánh chưa hỗ trợ trả
`unavailable`, giữ truy vết `snapshot_id`, `run_id`, `bundle_id` và tách bằng chứng
Concrete FHE thật khỏi kiểm thử mô phỏng giao thức.

Phạm vi: nối `BundleHE` (`bundle-he4-native/1.0.0`) với `FourJobs` và worker
Concrete (`P1`, `C3`, `B1`, `B5/E4`) trên snapshot nguồn 35 luật; 30 luật còn lại
và thống kê/ML contract 33 feature giữ `unavailable`. Giải mã, áp chính sách,
gộp vụ, xét ngân sách, hàng đợi shadow, phiếu rà, xử lý task và báo cáo chạy tại
doanh nghiệp. Không deploy/restart Portal live, không push GitHub, không phê duyệt
production hoặc toàn bộ R6.
