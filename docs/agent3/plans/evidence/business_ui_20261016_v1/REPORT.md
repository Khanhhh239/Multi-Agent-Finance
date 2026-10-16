# Hồ sơ nghiệp vụ trên UI — 16/10/2026

Đã nối phần chuẩn bị nghiệp vụ PLAN_09 lên giao diện `/review`. Người dùng không cần tạo JSON, tính hash hoặc dùng CLI để lưu xác nhận và bổ sung chứng cứ. Rules/taxonomy thật vẫn chưa được duyệt; đây không phải nghiệm thu độ chính xác thuế hoặc bắt đầu PLAN_14. Nhánh OCR V2 vẫn thuộc PLAN_06.

Kết quả kiểm chứng: **428/428 Python tests PASS**, **23 nhóm browser checks PASS** (12 hồ sơ nghiệp vụ, 6 compliance, 5 explanation), 4 JavaScript syntax checks và 2 client harness checks PASS. Sau hồi quy Python, bản sửa riêng UI về trạng thái upload/loading/thành công được kiểm lại bằng browser hồ sơ và JavaScript; pin mã backend được đối chiếu không đổi.

[Kết quả hồi quy](validation_summary.json) · [Browser hồ sơ](browser_business.json) · [Browser compliance](browser_compliance.json) · [Browser explanation](browser_explanation.json) · [Bảng quyết định](../business_review_20261016_v1/DECISION_TABLE.md).

## Cách mở và sử dụng

1. Nếu web đang chạy, dùng `STOP_AGENT3.cmd`, sau đó mở lại `OPEN_AGENT3.cmd`. Kết nối bằng mã truy cập như trước. Dùng Ctrl+F5 nếu trình duyệt vẫn giữ giao diện cũ.
2. Chọn hóa đơn đã xử lý. Đối chiếu/sửa và **Lưu dữ liệu hóa đơn** trước.
3. Trong khung bên phải, mở **Hồ sơ nghiệp vụ — Đối chiếu và bổ sung**. Hóa đơn gốc vẫn ở bên trái để xem đồng thời.
4. Chọn phần bạn đã có căn cứ. Phần hóa đơn gồm loại, hình thức thông thường/đặc thù, phương pháp thuế, yêu cầu khấu trừ, sự hiện diện MST và xác nhận đủ tài liệu. Không tự tick xác nhận dựa vào OCR.
5. Tại **Tài liệu dùng để đối chiếu**, chọn loại và tải PDF/PNG/JPEG. Hóa đơn gốc có sẵn. Tải tài liệu bổ sung không thay thế bản gốc và không tự biến tài liệu thành chứng cứ thanh toán hợp lệ.
6. Chọn tài liệu ở phần tương ứng, ghi căn cứ, xác nhận đã đối chiếu rồi bấm **Lưu hồ sơ nghiệp vụ**. Khi mở lại, các dữ liệu đã lưu được điền lại, ô xác nhận lần lưu mới luôn để trống.

**Chưa có catalogue/danh mục sản phẩm:** để phần phân loại dòng hàng chưa chọn. Không cần bịa mã hàng, thuế suất cơ sở hoặc đánh dấu không thuộc phụ lục để lưu phần hóa đơn/thanh toán. Hệ thống tiếp tục báo cần bổ sung phân loại.

**Thanh toán:** chọn trường hợp, kết quả đối chiếu, phương thức thực tế, số tiền VND theo định dạng Việt Nam, tài liệu và xác nhận giao dịch/đủ tiền. MST hai bên lấy từ bản hóa đơn đã lưu; nếu sai hoặc thiếu, sửa dữ liệu hóa đơn trước. Không lấy nhãn TM/CK làm proof; nộp tiền mặt vào tài khoản bên bán không được coi là chuyển khoản non-cash.

**Mua cùng ngày:** có danh sách các bản đã lưu cùng người bán/ngày và đủ dữ liệu VND. Mỗi dòng được server gắn revision/hash, không nhận số tiền tự sửa trong danh sách. Người review chọn các hóa đơn cần đối chiếu và tài liệu tổng hợp. Ô xác nhận đủ toàn bộ khoản mua mặc định **không chọn**; tập đã upload không tự chứng minh đầy đủ, kể cả nguồn ngoài hệ thống. Danh sách quét tối đa 500 chứng từ và có thông báo khi bị cắt.

Mức sẵn sàng hiển thị theo **hồ sơ đã lưu**. “Đủ dữ liệu để kiểm tra/đủ đầu vào cho check” không phải PASS thuế. Nút kiểm tra thuế hiện có giữ workflow cũ; không tự chạy các rule DRAFT bằng hồ sơ vừa nhập.

## Trạng thái lỗi và dữ liệu chưa lưu

- Có bản nháp dữ liệu hóa đơn: lưu hoặc bỏ bản nháp đó trước khi lưu/tải chứng cứ hồ sơ.
- Có bản nháp hồ sơ khi muốn sửa hóa đơn: lưu hồ sơ trước, hoặc dùng **Tải lại hồ sơ / bỏ bản nháp** để bỏ rồi lưu dữ liệu hóa đơn. Không âm thầm mang xác nhận sang revision mới.
- Hai phiên cùng lưu: server kiểm expected review ID; phiên đến sau thấy xung đột và giữ giá trị đang nhập. Chỉ bỏ bản nháp khi người dùng đồng ý tải lại.
- File lỗi/quá dung lượng: báo lỗi, không ghi thêm chứng cứ, giữ khả năng chọn tệp/thử lại.
- Credential READ: xem hồ sơ/tải tài liệu, không ghi nhận xác nhận hoặc upload.
- Sửa hóa đơn tạo revision mới: phần hồ sơ mở lại ở trạng thái chưa có xác nhận cho bản mới; hồ sơ cũ còn trong kho riêng. Chưa thêm màn hình duyệt lịch sử hồ sơ nghiệp vụ riêng.

## Hợp đồng và bảo toàn dữ liệu

Thêm API editor, lưu review, upload/download tài liệu và danh sách cùng ngày. Browser chỉ gửi lệnh xác nhận; server tự lấy actor từ credential, scope, revision/hash CFR, source file và timestamp. Không nhận reviewer/hash/PaymentProof hoặc legal approval do caller tự gán. Save cần WRITE và Idempotency-Key; lưu trùng cùng nội dung không tạo dossier mới. Expected record revision và review ID chống trộn dữ liệu/xung đột.

Upload dùng raw body có auth trước khi đọc stream, giới hạn dung lượng/thời gian, kiểm magic PDF/PNG/JPEG và SHA-256. Chỉ kiểm loại tệp/bảo toàn bytes, không xác minh nội dung ngân hàng/catalogue bằng parser hay model. File giữ ngoài Git theo scope/hash, tên file chỉ là nhãn hiển thị bằng textContent. Download có auth/object scope, attachment và nosniff; không nhúng PDF bổ sung thành nội dung thực thi trong trang.

Kho SQLite/evidence của bước backend được tái sử dụng, thêm bảng metadata tài liệu và request idempotency. Không migrate hay sửa CFR/raw/quality/evaluation cũ. Mã planning/rules/orchestration đã pin giữ nguyên; kiểm replay V1 nằm trong hồi quy.

Các giới hạn còn lại: chưa có mapping SKU thật, chưa đối chiếu bank statement tự động/chữ ký số, chưa phân bổ thanh toán một phần, chưa giải quyết toàn bộ ngoại lệ hóa đơn, chưa mở tax release. Hồ sơ là xác nhận của operator có tài liệu, không phải bằng chứng rằng xác nhận luôn đúng.

## Kiểm thử và tái hiện

Python: 12 suites, gồm API upload/save/scope, idempotency, save song song, raw chunked upload vượt giới hạn, readonly, chống gán trường server và tài liệu khác record. Browser Chrome thật: mở/lưu/tải lại, lỗi upload/thử lại, payment/product/ledger round trip, download đúng bytes, filename không chạy HTML, conflict giữ draft, sửa CFR làm cũ dossier, desktop/mobile 390px. Fixture tổng hợp; không lấy số test làm legal accuracy.

```powershell
# Từ D:\financial, venv workspace hiện có
agent3_tax_compliance/.venv/Scripts/python.exe scripts/validate_business_ui.py
```

Script ghi evidence mới tại thư mục này, không ghi đè báo cáo backend/legal V1/V2. Ảnh desktop/mobile và tài liệu test nằm trong data local bị gitignore. Số ca và kết quả thực chạy nằm trong validation_summary.json.
