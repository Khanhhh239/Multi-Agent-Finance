# Đối chiếu chấm rõ và chấm mã hóa

Mở [bảng kết quả sau sửa khôi phục CR-040](../../Agent2_Spec_v2_1/evidence/HE/worker_recovery_20261112/comparison/comparison.html) để xem điểm, thứ tự, thời gian và khôi phục. [Bản Markdown mới](../../Agent2_Spec_v2_1/evidence/HE/worker_recovery_20261112/comparison/REPORT.md) và [JSON từng lượt mới](../../Agent2_Spec_v2_1/evidence/HE/worker_recovery_20261112/comparison/comparison.json) dành cho đối chiếu lại. [Lượt đo trước sửa](../../Agent2_Spec_v2_1/evidence/HE/plaintext_comparison_20261112/run/comparison.html) giữ nguyên như bằng chứng lịch sử; kết quả hard crash 0/2 thuộc bản cũ.

## Cách chạy

Từ `D:/agent22`:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/compare_he_plaintext.py `
  --output-dir '<thu-muc-ket-qua-moi>' `
  --repetitions 5 --recovery-repetitions 1 --budget 5
```

Thư mục kết quả phải chưa tồn tại và nằm ngoài packet nguồn. Mặc định dùng bộ mô phỏng `.runtime/he-company-demo` hiện có, mỗi DN 5 giao dịch, model Mahalanobis đã fit riêng. Không fit, đổi ngưỡng, chọn model khác hoặc nạp dữ liệu thật. Có thể chỉ định packet mô phỏng khác bằng `--packet`; phải đúng manifest/checksum/DPAPI/config tương thích. Dùng tài khoản Windows đã bảo vệ khóa.

Lệnh chỉ đọc model/snapshot/khóa nguồn, tạo node và worker trong thư mục thử nghiệm riêng, kết nối loopback với port tự chọn. Các tiến trình thử tự dừng khi hoàn tất; Portal và worker live không bị dừng hoặc thay cấu hình. Không cần đăng nhập Portal để chạy bộ đo này. File quyền tạm chỉ có credential ngẫu nhiên phục vụ phép thử tại DN, không dùng phiên hoặc mật khẩu người dùng.

## Hiểu từng nhóm chỉ số

| Chỉ số | Trả lời câu hỏi gì? |
|---|---|
| Sai số lớn nhất / trung bình | Điểm HE lệch bao nhiêu so với model rõ trên đúng dữ liệu? |
| Cùng thứ tự / Spearman / cặp đảo đáng kể | Phép tính gần đúng có làm đổi ưu tiên giữa các giao dịch không? |
| Top-k trùng | Hai cách có chọn cùng tập giao dịch trong ngân sách đó không? Top-5 trên 5 mẫu bao phủ tất cả, nên riêng chỉ số này chưa chứng minh gì về lợi ích chọn cảnh báo. |
| Thời gian rõ / HE p50, p95 | Mất bao lâu để hoàn tất một lượt chấm mới? Số lượt nhỏ nên p95 chỉ mô tả mẫu. |
| Thành công / số lần ngắt xác nhận | Với từng loại sự cố cụ thể, cùng yêu cầu có khôi phục được đủ điểm đúng không? |

Ngưỡng số học giữ nguyên profile HE: `abs(HE − rõ) <= 0.001 + 0.00001 * abs(rõ)`. Không chỉnh ngưỡng sau khi xem kết quả. Ghép theo `(record_id, revision)` trong đúng doanh nghiệp/model/snapshot/as_of; không ghép theo vị trí dòng. Thiếu, trùng, unavailable hoặc điểm không hữu hạn làm phép đối chiếu báo lỗi, không tự bỏ dòng để đạt.

Thứ tự từ điểm bất thường cao xuống thấp, hòa điểm dùng định danh để trình bày ổn định. Cặp có khoảng cách dưới tổng ngân sách sai số hai điểm không tính là đảo thứ tự đáng kể. Báo cả thứ tự chính xác và thứ tự có xét sai số, không giấu dao động ở điểm gần nhau. Điểm tham chiếu bằng hoặc gần 0 (`abs(rõ) <= 1e-12`) không dùng tính sai số tương đối vì tỷ lệ không xác định hoặc không ổn định; báo số dòng này và null nếu không còn dòng tính được, thay vì gán 0%.

## Đo thời gian và sự cố

Mỗi doanh nghiệp làm nóng một lượt rõ và một lượt HE, loại khỏi số đo. Sau đó đo 5 lượt, đảo thứ tự rõ-trước/HE-trước xen kẽ. Mỗi HE dùng yêu cầu mới và kiểm số record worker; không lấy cache để làm tốc độ chấm mới trông nhanh hơn.

- Rõ: quyền DN, đọc/kiểm model đã lưu, tạo feature snapshot, preprocessing và score. Báo thêm thời gian riêng lời gọi score trong JSON; không so riêng score này với toàn bộ pipeline HE.
- HE: từ `HEWorkbench.submit` đến đủ kết quả giải mã đã lưu. Gồm readiness có chữ ký, model/feature, mã hóa, ghi checkpoint, HTTP worker, nhận/giải mã và polling 5 ms. Chưa gồm Portal/trình duyệt, fit hoặc khởi động dịch vụ.
- Khôi phục: đo từ lúc bắt đầu mở lại worker/node tới trạng thái cuối; có chi phí khởi động. Nếu thất bại thì không gán thời gian đó thành “thời gian khôi phục thành công”.

Mặc định mỗi DN một ca cho mỗi kiểu, tổng hai ca/kiểu:

1. Ngắt worker khi DN đã nhận yêu cầu và đang chuẩn bị, worker chưa claim phép tính; mở lại và tiếp tục cùng job.
2. Thấy worker đang tính rồi đóng node có kiểm soát bằng `Jobs.close`, chờ phép tính hoàn tất trước khi mở lại cùng state. Đây là phép thử đường shutdown của node; lượt nghiệm thu Portal trước đã kiểm nút Bật/Tắt thực tế.
3. Thấy worker đang tính rồi dừng cưỡng bức trước commit. Phải xác nhận record còn `running` sau kill; nếu compute đã kịp commit thì ca ngắt chưa xác nhận, không tính vào mẫu số thành công.

Ca khôi phục chỉ thành công khi cùng job, một record worker mới và đủ điểm khớp model rõ. Các ca ngắt hụt được báo riêng. `WORKER_INTERRUPTED` là **khôi phục thất bại**, dù cơ chế giữ nguyên job và đóng an toàn hoạt động đúng. Không gộp các loại sự cố thành một tỷ lệ duy nhất.

Trạng thái báo cáo `partial` khi còn lỗi số học/thứ tự đáng kể, ca chưa ngắt được hoặc khôi phục thất bại. CLI hoàn thành báo cáo có thể trả exit 0 dù status partial; đó không phải ký duyệt sản phẩm. Không dùng bảng này để tuyên bố precision/recall/gian lận, SLA hoặc cloud production.
