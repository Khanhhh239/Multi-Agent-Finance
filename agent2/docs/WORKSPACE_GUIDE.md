# Sử dụng Agent2 trên Portal

Mở [Agent2](http://127.0.0.1:8800/agent2/workspace) sau khi đăng nhập Portal.
Nếu dịch vụ chưa bật, vào Portal → Agent2 → **Bật Agent2**.

## 1. Chọn doanh nghiệp và dữ liệu

Trang **Công việc** hiển thị dữ liệu đã lưu và các lần phân tích của doanh
nghiệp đang chọn. Mỗi kết quả gắn với đúng bản dữ liệu, thời điểm nguồn được
biết và mã lần chạy. Chuyển doanh nghiệp sẽ xóa nội dung đang hiển thị của
doanh nghiệp trước.

Để thử nhanh, mở kết quả P1 đã hoàn tất:

| Doanh nghiệp | Lần phân tích |
|---|---|
| C001 | [8 giao dịch](http://127.0.0.1:8800/agent2/workspace#company=C001&run=herun_a41f1c89c0b04bb9bd85021731bdaf7f) |
| C002 | [8 giao dịch](http://127.0.0.1:8800/agent2/workspace#company=C002&run=herun_83f30523ede5495a97a9957a07a000dc) |

Đây là dữ liệu mô phỏng; mở kết quả cũ không thực hiện lại phép tính mã hóa.

## 2. Nhập dữ liệu mới

Bấm **Nhập dữ liệu mới** → chọn tệp CSV, Excel hoặc JSON theo mẫu trên màn
hình → **Kiểm tra dữ liệu** → đọc lỗi/cảnh báo → xác nhận → lưu.

CSV dùng cột `table`; Excel dùng các sheet nguồn và `metadata` theo mẫu.
Không phải mọi tệp sao kê có tên cột tùy ý đều nhập trực tiếp được. Lỗi sẽ chỉ
rõ dòng, trường và cách sửa. Thay tệp hoặc mapping phải kiểm tra lại.
Việc lưu tạo snapshot mới, không thay dữ liệu hoặc kết quả đã lưu trước đó.

## 3. Chạy phân tích

Chọn **Phân tích bản này** hoặc tiếp tục từ màn hình nhập, sau đó bấm
**Chạy phân tích**. Server chọn phiên bản phân tích đã cấu hình cho doanh
nghiệp; không tự fit model khi chấm. Bản lịch sử chuẩn bị phiên bản được
phân biệt với bản dữ liệu đánh giá.

Luồng hiện tại tính các profile HE đã triển khai: P1, đồ thị giới hạn,
RobustZ hai biến và Mahalanobis hai feature. Node doanh nghiệp giữ dữ liệu rõ,
model và khóa; worker tính trên bản mã rồi trả bản mã để node giải mã.
Các profile này chưa bao phủ toàn bộ catalog luật hoặc mọi model không nhãn.

Phép tính HE có thể mất hàng chục phút. Có thể tải lại trang hoặc mở lại
lượt đã lưu. Khi mất kết nối, dùng **Kết nối lại / Tiếp tục** để giữ cùng yêu
cầu. Lượt đã thất bại được giữ trong lịch sử; sau khi khắc phục nguyên nhân,
chọn **Chạy lại bằng lượt mới** để tạo yêu cầu mới rõ ràng.

## 4. Đối chiếu và ghi kết quả

Sau khi hoàn tất, chọn **Mở hồ sơ rà và báo cáo**. Màn hình giữ đủ mọi giao
dịch của lần chạy; đây chưa phải hàng đợi được tự xếp hạng theo chính sách.

Mở một giao dịch để đọc điều cần làm rõ, lý do và bước tiếp theo. Mở
**Chứng từ và nguồn đối chiếu**, xem các bản ghi và chọn căn cứ đã đọc.
Hóa đơn, phân bổ, lịch sử, điều chỉnh và nhóm thanh toán đồng thời được
trình bày theo nguồn hiện có. Liên kết chỉ cho biết quan hệ cần đối chiếu.

Bấm **Bắt đầu rà**, chọn một kết quả rồi ghi giải thích và hành động:

- **Có vấn đề cần xử lý:** đã có căn cứ xác nhận sai lệch cần sửa/chuyển xử lý.
- **Không phát hiện vấn đề:** đã đối chiếu đủ và giải thích được bất thường.
- **Chưa đủ căn cứ:** nêu tài liệu hoặc thông tin còn thiếu.

Có thể bổ sung PDF/ảnh tối đa 2 MB/tệp. Tài liệu bổ sung chưa tự trở thành
chứng từ gốc đã xác minh. Bấm **Lưu kết quả rà**; kết quả, căn cứ, thời gian
kết nối và lịch sử sửa lưu tại server. Nếu mất phản hồi, bấm lưu lại để gửi
lại cùng yêu cầu. Bộ đếm không chứng nhận người dùng thực sự đọc chứng từ.

## 5. Tải báo cáo

**Tải báo cáo CSV** để mở trong Excel, hoặc **Tải báo cáo JSON** để giữ thêm
căn cứ và lịch sử. Báo cáo lấy bản kết quả đã lưu mới nhất của đúng doanh
nghiệp/lượt chạy; nội dung chưa lưu trên màn hình không nằm trong báo cáo.

Để thử giá trị bổ sung của ML, mở **So sánh luật và ML** trong lượt bốn nhánh
đã hoàn tất, bấm **Khóa lựa chọn và so sánh**. Phép thử giữ cảnh báo P1 rồi
dùng ML bổ sung chỗ trống, tối đa 5 giao dịch/phương án. Mở khoản ML thêm
để rà, sau đó cập nhật chỉ số hoặc tải báo cáo. [Cách đọc kết quả](SELECTION_COMPARISON.md).

Thiếu nguồn là **chưa khả dụng**, không phải giao dịch hợp lệ. Điểm bất thường
chưa phải xác suất gian lận. Phản hồi rà hiện chưa tự thành nhãn huấn luyện.
Cấu hình chuyên môn chỉ hiển thị cho quyền quản lý; Portal hiện dùng danh tính
workspace chung, chưa xác minh từng cá nhân rà soát.
