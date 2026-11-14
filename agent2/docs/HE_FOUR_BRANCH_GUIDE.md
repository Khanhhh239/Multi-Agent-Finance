# Dùng Agent2 bốn nhánh trên Portal local

Bản kiểm chứng kỹ thuật ngày 13/11/2026. Dùng C001/C002 mô phỏng để thử thao tác;
kết quả chưa chứng minh hiệu quả trên doanh nghiệp thật.

Để thử P1 có đủ nguồn, dùng [bộ demo 5 ca / 8 bản ghi](../examples/he4_p1/README.md).
Bộ 5 giao dịch cũ bên dưới vẫn giữ để kiểm tra trường hợp chưa đủ nguồn P1.

## Xem lại bộ P1 mới: 8 giao dịch mỗi doanh nghiệp

1. Đăng nhập [Portal](http://127.0.0.1:8800), mở **Agent2 → Chạy phân tích**.
2. Chọn C001 hoặc C002. Bản P1 mới có **8 bản ghi, kỳ 02–08/10/2026**, lưu
   ngày 13/11/2026. [Bộ nguồn và bảng đối chiếu](../examples/he4_p1/README.md).
3. Mở **Xem lại lần phân tích đã lưu**, chọn đúng mã bên dưới để xem trạng
   thái và kết quả khi hoàn tất. Thao tác này mở yêu cầu đã có.

| Doanh nghiệp | Mã lần chạy của bộ P1 mới |
|---|---|
| C001 | `herun_a41f1c89c0b04bb9bd85021731bdaf7f` |
| C002 | `herun_83f30523ede5495a97a9957a07a000dc` |

Trong từng phiếu, mở **Chứng từ và nguồn đối chiếu** để xem hóa đơn, phân bổ,
khoản điều chỉnh và phạm vi lịch sử. Các bản ghi vẫn mang nhãn **Dữ liệu mô phỏng**.
Muốn thực hiện một lượt chấm mới thì dùng **Chạy phân tích**; phép tính HE có
thể mất hàng chục phút cho cả tệp trên máy hiện tại. Nếu Portal khóa phiên,
đăng nhập lại rồi mở đúng yêu cầu đã lưu để tiếp tục.

[Báo cáo đối chiếu Portal](../../Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113/REPORT.md)
ghi riêng kết quả đã quan sát và phần còn đang thực hiện.

## Thử bộ 5 giao dịch cũ và ghi phiếu rà

1. Mở [Portal](http://127.0.0.1:8800), đăng nhập bằng mật khẩu hiện có. Sau lần
   nâng cấp này cần đăng nhập lại; mật khẩu không bị thay đổi.
2. Mở [Chạy phân tích](http://127.0.0.1:8800/agent2/encrypted-analysis). Chọn
   doanh nghiệp, chọn bản dữ liệu **5 giao dịch kỳ tháng 10/2026** rồi bấm
   **Chạy phân tích**. Bản 40 giao dịch tháng 9 là lịch sử chuẩn bị model;
   các giao dịch đã dùng để fit không được chấm như dữ liệu mới.
3. Chờ xử lý. Phép tính mã hóa có thể mất vài phút mỗi nhánh. Khi mất kết nối
   hoặc tắt/bật lại Agent2, mở lại và bấm tiếp tục yêu cầu đã lưu. Không nhập
   lại dữ liệu hoặc tạo model/khóa mới để khôi phục.
4. Mỗi giao dịch có bốn phần: đối chiếu P1, thống kê lịch sử, đồ thị liên kết và
   ML Mahalanobis. **Chưa khả dụng** nghĩa là chưa có nguồn/model/miền tính phù
   hợp; không có nghĩa giao dịch hợp lệ. P1 hiện chỉ là một phần catalog luật.
5. Mở phiếu rà bên dưới, đọc điều cần làm rõ và nguồn đối chiếu, bấm **Bắt đầu
   rà**, chọn căn cứ đã xem rồi ghi kết quả. Thiếu tài liệu chọn **Chưa đủ căn
   cứ**, ghi tài liệu cần bổ sung. Có thể đính kèm PDF/ảnh; tệp bổ sung chưa tự
   trở thành chứng từ gốc đã xác minh.
6. Bấm **Lưu kết quả rà**. Bộ đếm chỉ ghi khoảng kết nối khi lưu, không chứng
   nhận người thực sự đọc tài liệu. Lọc **Chưa ghi kết quả / Đã ghi kết quả**
   để theo dõi. Tải báo cáo rà lấy bản đã lưu trên server, gồm lịch sử sửa.

Trong phần mở rộng **Lịch sử phân tích**, chọn lại một lần chạy để xem đúng
snapshot, kỳ nguồn và phiếu của lần đó. Không cộng điểm bốn nhánh thành xác
suất sai phạm; hiện chưa có policy tổng hợp được duyệt.

## Nhập dữ liệu mới

Mở [Nhập dữ liệu](http://127.0.0.1:8800/agent2/data-import). Chọn doanh nghiệp → tải tệp →
xem kết quả kiểm tra → xác nhận lưu → tiếp tục phân tích mã hóa.

Dùng mẫu CSV/Excel trên màn hình: tệp chứa giao dịch cùng các bảng nguồn liên
quan theo hợp đồng, không phải mọi tệp sao kê đều nhập trực tiếp được. CSV có
cột `table`; Excel dùng sheet theo tên bảng và sheet `metadata`. Chưa có tự
ánh xạ tùy ý mọi tên cột của doanh nghiệp.

- Mã giao dịch, mã nhân viên, tài khoản Excel để **Text** để giữ số 0 đầu.
- Số tiền giữ số âm hợp lệ. Tiền lớn trong Excel phải để Text để tránh Excel
  tự làm tròn; không dùng công thức thay giá trị.
- Mốc ISO có múi giờ được giữ nguyên; giờ thiếu múi giờ được hiểu là giờ Việt
  Nam như hướng dẫn nhập. Ngày dạng 01/02/2026 cần chọn DMY/MDY rõ trong tùy
  chọn, không tự đoán ngày/tháng.
- Sửa đúng dòng/trường hoặc sheet/dòng mà thông báo chỉ ra rồi kiểm tra lại.
  Đổi tệp hay tùy chọn phải kiểm tra lại trước khi lưu.
- Thiếu chứng từ/lịch sử có thể giới hạn từng nhánh phân tích. Không tự điền
  lịch sử thiếu thành số 0 và không tự cắt nguồn cho vừa circuit.

## Người quản lý phân tích

[Cấu hình phân tích](http://127.0.0.1:8800/agent2/analysis-settings) kiểm quyền
quản lý theo doanh nghiệp ở backend. Chuẩn bị/kích hoạt cần thêm quyền
`model.fit`; ứng dụng không tự cấp quyền này.

Chọn dữ liệu lịch sử, kỳ train, tập đối chiếu, kỳ đánh giá; lưu nháp → chuẩn bị
model → kiểm tra trạng thái → kích hoạt. Kích hoạt bị chặn khi doanh nghiệp
còn yêu cầu phân tích chưa xong. Phiên bản cũ vẫn dùng trong lúc chuẩn bị mới.
Fit gián đoạn cần xem lại trạng thái và chủ động chuẩn bị lại.

Bản này giữ hai feature đã kiểm chứng cho RobustZ/Mahalanobis. Không có chức
năng tự chọn trọng số, ngân sách hoặc bắt buộc chuyển hồ sơ theo policy chưa
được duyệt. Ngưỡng 20 dòng trên màn hình là giới hạn kỹ thuật của phép thử,
không phải tiêu chí đủ dữ liệu để chứng minh độ chính xác.

## Người vận hành

Từ thư mục `D:\agent22`:

```powershell
agent1\.venv\Scripts\python.exe portal/server.py --start-agent2
```

Hoặc mở Portal rồi dùng **Bật Agent2 / Tắt Agent2**. Portal kiểm khóa và worker
trước khi chạy; tắt giữ model, khóa và yêu cầu. Không chạy thêm một bản Agent2
khác vào cùng cổng/kho trạng thái. Cổng hiện dùng: 8800, 8766, 8868 và 8869.

Node doanh nghiệp giữ dữ liệu rõ, model, khóa bí mật và kết quả giải mã. Worker
chỉ nhận bản mã, evaluation keys công khai và metadata giao thức. Worker HE4
đang chạy WSL local; chưa triển khai tới máy cloud bên ngoài.

Các giới hạn, kiểm thử, backup và phần chưa hoàn thành nằm trong
[báo cáo CR-041](HE_FOUR_BRANCH_PROGRESS.md).

Khi chuẩn bị máy Linux mới, dùng Python 3.12/venv riêng và cài Torch CPU trước:

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-he4-linux.txt
```

Windows dùng requirements-he.txt trong venv Agent2; không cài Concrete vào venv
Windows. Build circuit, provision khóa, cấu hình đường dẫn WSL và preflight là
bước chuẩn bị riêng của người vận hành, không tự thực hiện khi người rà chấm.
Script prepare_he4_managed_demo.py chỉ dùng cho hai DN mô phỏng đã có, từ chối
ghi đè thư mục deployment hoặc chuẩn bị nguồn thật theo cấu hình demo.
