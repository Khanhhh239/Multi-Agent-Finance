# Bàn giao rà độc lập ML v4 — 24/10/2026

Trạng thái: **chưa phân công**, theo xác nhận của người dùng. Gói mới có **74 phiếu**; 0 phiếu được rà độc lập và chưa có phút xử lý thực tế.

## Đúng gói cần dùng

- Giao duy nhất [reviewer_packet.zip](ml_v4/review/reviewer_packet.zip) hoặc thư mục [public](ml_v4/review/public/README.md) cho người rà và người phân xử.
- Gói gồm 40 đầu mối IF, 2 phiếu baseline chọn khác, 16 mẫu ngẫu nhiên thuộc phần hai nhánh cùng chọn và 16 mẫu ngẫu nhiên chưa được chọn. Các nhóm này chỉ dành cho người điều phối; người rà chỉ nhận gói public đã trộn.
- Bộ 128 phiếu cũ thuộc model/feature cũ và vẫn được giữ nguyên. Rà bộ cũ không xác nhận hiệu quả của v4. Không ép gói mới đủ 128 bằng cách nhân bản hoặc cắt bớt phiếu.

## Phân công và ghi nhận

1. Chỉ định một người rà chính và một người phân xử khác người rà. Cả hai phải độc lập với phát triển/chọn model và chưa biết nhánh, điểm hoặc thứ hạng của phiếu mình rà.
2. Sau khi có người thật, ghi hai ID vào `ml_v4/review/private/reviewer_assignment.json`. Không ký thay hoặc dùng tên trợ lý để đóng cổng độc lập.
3. Đọc REVIEW_INDEX.md và từng evidence.json; điền primary_reviews.csv và adjudications.csv theo README trong public. Ghi hành động hữu ích cụ thể, căn cứ, thiếu chứng từ và phút thực tế; thiếu bằng chứng dùng unknown.
4. Đo phút active bằng đồng hồ hoặc khoảng thời gian đã trừ nghỉ; ghi riêng công rà chính và phân xử. Không dùng ước lượng 20/30 phút trong shadow làm phút thực tế.
5. Khóa biểu mẫu trước khi mở mapping private. Chạy kiểm định bằng lệnh dưới đây với thư mục output mới mỗi lần.

```powershell
& 'C:\Users\Technical Support\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m sme_fraud.independent_ml_review validate --prepared reports/rr09_ml_completion_20261024/ml_v4/review --primary reports/rr09_ml_completion_20261024/ml_v4/review/public/primary_reviews.csv --adjudications reports/rr09_ml_completion_20261024/ml_v4/review/public/adjudications.csv --output reports/rr09_ml_completion_20261024/human_validation_01
```

Sau khi kiểm định hợp lệ, đối chiếu kết quả có hành động hữu ích, phần unknown/thiếu chứng từ và phút đo được với hai nhánh tại cùng ngân sách. Không suy precision/recall gian lận hay lợi ích toàn bộ quần thể từ mẫu chẩn đoán này. Nguồn mô phỏng vẫn chưa thay thế thử nghiệm trên SME thật.

## Các việc vẫn phải xử lý trước nghiệm thu ML

- Bốn cờ khả dụng chứng từ/hóa đơn hiện đều là 0 trên 41.082 dòng. Cần thời điểm biết có căn cứ từ nguồn; không tự điền ngược hoặc dùng cờ cuối kỳ làm lịch sử.
- Shadow ghi nhận một lượt rà baseline A4 bị chậm 26 ngày khi dành suất khám phá IF. Kết quả rà và phút thực tế phải được đánh giá cùng chi phí chậm này trước khi quyết định vận hành.
- Người dùng xác nhận chưa phân công: giữ 0/74 và phút thực tế null cho đến khi có người thực hiện; việc chuẩn bị gói không đóng cổng chứng minh lợi ích.
