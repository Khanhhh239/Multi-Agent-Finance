# Rà nghiệp vụ C001/C002 — bản thử luồng

Mở [10 phiếu rà trống](../../Agent2_Spec_v2_1/evidence/HE/business_review_demo_20261112/packet/BAT_DAU_RÀ_NGHIỆP_VỤ.html) bằng Chrome hoặc Edge. Tệp HTML chạy tại máy doanh nghiệp, không cần server, mật khẩu Portal hoặc gửi dữ liệu ra mạng. Đây là phiếu thử tách riêng, **chưa phải chức năng đã nối vào Portal/hàng đợi**.

## Bạn làm gì đầu tiên?

1. Nhập tên người trực tiếp rà; chọn **C001**, mở phiếu **T0 — ưu tiên 1/5**.
2. Bấm **Bắt đầu rà**. Xem câu hỏi, các bản ghi nguồn và đánh dấu đúng những bản ghi đã xem.
3. Đối chiếu số tiền, ngày, NCC, hóa đơn và phân bổ. Phần nguồn của phiếu chỉ có các bản ghi đã biết tại cutoff của giao dịch, không tự lấy chứng từ đến sau.
4. Chọn kết quả và giải thích. Nếu thiếu tài liệu, chọn **Chưa đủ căn cứ**, nêu tài liệu thiếu và ai cần bổ sung gì.
5. Đánh giá lợi ích riêng: Có / Không / Chưa đánh giá. Chọn Có phải có hành động cụ thể; không tự coi điểm cao hoặc phát hiện mô phỏng là gian lận.
6. **Lưu kết quả thử**, làm tiếp các phiếu. Sau mỗi buổi bấm **Xuất kết quả JSON** và lưu trong thư mục riêng của nhóm.

Mỗi DN có 5 giao dịch theo thứ tự **T0 → T2 → T4 → T1 → T3**, từ lần chấm đã đối chiếu rõ/HE. C001/C002 trùng mã giao dịch nhưng khác case ID, snapshot, model và tập nguồn. Cả hai cùng nằm trong tệp offline mô phỏng; tệp này không thực thi phân quyền doanh nghiệp như Portal.

## Ví dụ để hiểu cách ghi, không phải kết luận có sẵn

C001/T0 có số tiền **950.003 đồng**, phân bổ A_T0 cùng số tiền, liên kết bản ghi hóa đơn I001 giá trị **20.000.000 đồng**. Hóa đơn ở đây là bản ghi dữ liệu mô phỏng, không phải tài liệu gốc. Snapshot không cung cấp phê duyệt hoặc chứng từ chuyển tiền.

Một cách ghi phù hợp khi chỉ có các nguồn này:

- **Kết quả:** Chưa đủ căn cứ.
- **Giải thích:** “Đã xem T0, A_T0 và I001; phân bổ hiện tại khớp số tiền giao dịch. Chưa có phê duyệt và chứng từ gốc để xác nhận khoản chi.”
- **Tài liệu thiếu:** “Phê duyệt chi, hóa đơn gốc/hồ sơ nghĩa vụ và chứng từ chuyển tiền.”
- **Hành động:** “Đề nghị kế toán bổ sung tài liệu để xác định người thụ hưởng, nghĩa vụ và thời điểm chi.”
- **Hữu ích:** Chưa đánh giá, cho tới khi người rà xác nhận hành động đó có giá trị trong đợt đánh giá.

Không điền sẵn kết luận trong các phiếu thật của bộ thử. Kiểm thử tự động dùng trình duyệt riêng và dữ liệu FIXTURE; những kết quả đó không được tính vào lượt rà của nhóm.

## Lưu, sửa và thời gian

Nháp/kết quả lưu trong localStorage của trình duyệt đang dùng, theo packet ID. Đổi phiếu/ẩn thẻ/tải lại sẽ tạm dừng đồng hồ, không cộng thời gian đóng trang. Đây là **thời gian hoạt động từ trình duyệt, chưa được máy chủ xác minh**; không dùng làm chứng cứ thời gian kiểm tra thực tế hoặc SLA. Tên người rà cũng là tự khai, chưa xác minh danh tính.

Kết quả đã lưu bị khóa. Bấm **Sửa kết quả — tạo phiên bản mới** để giữ bản cũ; bản tổng hợp đếm một phiếu theo phiên bản cuối, cộng thời gian các phiên bản đã lưu để không bỏ công sửa lại. Nháp chưa gửi không đưa vào báo cáo thời gian. Bản thử không có file đính kèm mới hoặc xác minh tài liệu. Checkbox “đã xem nguồn” chỉ ghi khai báo đã xem bản ghi mô phỏng.

Lưu kết quả khác doanh nghiệp hoặc thêm tệp xuất không được làm mất kết quả không liên quan. Nội dung khác nhau cùng case/revision bị báo xung đột; không tự chọn bản thắng. Exact duplicates được chống đếm trùng. Tải lại trang không đổi snapshot/model của phiếu. Nên dùng một cửa sổ cho mỗi phiếu đang rà và xuất JSON để lưu bản sao; localStorage không phải kho lưu bền vững đã xác minh.

## Kiểm tra và tổng hợp các tệp xuất

Từ `D:/agent22`:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_he_business_review.py summarize `
  --packet-file Agent2_Spec_v2_1/evidence/HE/business_review_demo_20261112/packet/packet.json `
  --feedback '<tep-xuat-buoi-1.json>' '<tep-xuat-buoi-2.json>' `
  --output-dir '<thu-muc-tong-hop-moi>'
```

Bộ tổng hợp chỉ nhận đúng packet và case, dẫn nguồn trong tập đã khóa của chính phiếu. Không quét thư mục để nhận file chứng từ ngoài manifest. JSON thêm cờ xác minh thời gian hoặc nhãn train bị từ chối. Checksum giúp phát hiện thay đổi nội dung, **không thay chữ ký người duyệt**. Không đưa tệp phản hồi có tên/ghi chú người thật vào Git; lưu nội bộ nhóm.

Kết quả `summary.json` tách:

- Đã rà / chưa rà; Chưa đủ căn cứ.
- Hữu ích / không hữu ích / chưa đánh giá. Mẫu số tỷ lệ khai báo hữu ích chỉ gồm Có + Không; không đổi Chưa đánh giá thành Không.
- Thời gian thử và số hành động hữu ích được tự khai trên phút thử, với cờ timing chưa xác minh. Nếu chưa đánh giá lợi ích thì tỷ lệ là null, không ghi 0%.
- Chưa xác minh hiệu quả nghiệp vụ, chưa có đối chứng luật, không nhãn train, chưa đề xuất mở rộng feature.

Tạo lại bộ trống phải dùng thư mục mới, đọc đúng bộ mô phỏng và báo cáo so sánh hiện có:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_he_business_review.py prepare --output-dir '<thu-muc-phieu-moi>'
```

## Điều kiện trước khi mở rộng

Giữ hai feature hiện tại. [CR-040 đã sửa HE-AC-01 trong phạm vi managed request còn TTL/state](HE_WORKER_RECOVERY.md); thông tin OPEN trong snapshot/tổng hợp tạo trước CR-040 là lịch sử, không dùng làm trạng thái kỹ thuật hiện hành. Cần hoàn tất rà với người hiểu nghiệp vụ, có đối chứng luật cùng kỳ/ngân sách và bộ nguồn thực được cấp quyền trước khi kết luận ML mang lại thêm giá trị. Bộ mô phỏng chỉ nghiệm thu thao tác/lưu/tổng hợp; không cho precision, recall, hiệu quả tài chính hoặc quyết định mở rộng model trên doanh nghiệp thật.
