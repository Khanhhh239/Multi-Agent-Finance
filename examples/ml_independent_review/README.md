# Chuẩn bị và nhập review độc lập cho phép so sánh IF

Module [independent_ml_review.py](../../sme_fraud/independent_ml_review.py) chuẩn bị phiếu mù từ phép so sánh đã khóa và kiểm tra dữ liệu do người thật nhập. Nó không tạo outcome hoặc tự đóng cổng SME thật.

```powershell
python -B -m sme_fraud.independent_ml_review prepare `
  --comparison-root reports/ml_shadow_comparison_20261022 `
  --seed 20261022 `
  --output reports/my_blind_review_packet
```

Đầu ra mới gồm `public/`, `private/`, `reviewer_packet.zip` và `summary.json`. Chỉ giao ZIP hoặc `public/` cho reviewer. `private/` chứa nhánh/điểm/lý do chọn/mẫu số lấy mẫu và danh sách phân công, không đưa vào rà mù. Kế hoạch được khóa trước khi lập phiếu; đổi seed/thiết kế sau khi đã xem outcome phải tạo phiên bản nghiên cứu mới.

Thiết kế hiện hành lấy toàn bộ bất đồng ở ngân sách chính 5/120, cùng một mẫu cùng chọn và một mẫu chưa được chọn cho mỗi bộ/công ty. Pool tham chiếu là các scope pending trong mô phỏng, không phải tất cả giao dịch hay nhãn gian lận thực địa. Xác suất chọn được lưu trong mapping riêng; chưa chạy ước lượng hiệu quả tổng thể từ các trọng số này.

Mỗi mẫu có nguồn đã lọc theo cutoff/công ty, mã phiếu ẩn danh, phiếu primary và phiếu phân xử. Điền true/false/unknown cho điều kiện/hành động; tách tài liệu thiếu; đo phút bằng đồng hồ hoặc khoảng thời gian thực tế. Không dùng estimated_minutes của simulator. Độc lập/mù phải được người ký xác nhận đúng thực tế; hai người ký khác nhau.

Ghi hai mã người thật vào `private/reviewer_assignment.json` sau khi phân công. Không dùng mã trợ lý/bot hoặc tự ký thay người khác. Khi nhận dữ liệu:

```powershell
python -B -m sme_fraud.independent_ml_review validate `
  --prepared reports/my_blind_review_packet `
  --primary primary_reviews_da_dien.csv `
  --adjudications adjudications_da_dien.csv `
  --output reports/my_review_validation
```

Output kiểm tra phải mới và không nằm trong phần công khai của reviewer. Evidence/manifest/mapping gốc bị sửa sẽ bị từ chối. Thiếu người ký hoặc chưa phân xử giữ pending; thời gian thiếu không thành 0; unknown không thành âm tính. Phút mẫu tham chiếu, primary và phân xử được tổng hợp riêng, chưa tự suy thành lợi ích vận hành.

[Bộ 69 phiếu đã chuẩn bị và trạng thái thực tế](../../reports/ml_independent_review_20261022.md). Hiện chưa có kết luận độc lập; không dùng kết quả kiểm thử hoặc ghi chú của trợ lý thay review người thật.
