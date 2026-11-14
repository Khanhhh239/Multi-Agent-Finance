# Sổ tay vận hành Workspace Agent 1

Theo luồng hiện tại, đối chiếu 14/11/2026. [README](../../README.md) hướng dẫn khởi động; [Đại Phát](DEMO_INPUT_TRAIN_DAIPHAT.md) chứa tham số/file demo; [pipeline](../04_AI_Methods/01_pipeline_he_thong.md) mô tả kỹ thuật. Các con số dự báo phụ thuộc bundle và dữ liệu, không dùng số chụp của phiên bản trước làm đáp án.

<!-- PUBLIC_GUIDE -->
## 3. Hướng dẫn sử dụng trên web

### Bước 1 · Mở đúng doanh nghiệp và kết nối

Khởi động Workspace theo README hoặc mở từ Portal. Kiểm mã doanh nghiệp, kho và môi trường trước khi nạp dữ liệu. Dùng khóa do quản trị viên cấp trên máy đó. Khi mở từ Portal, Workspace có thể nhận kết nối từ trang cha; tab riêng dùng phiên được cấp. Không đưa khóa vào URL, ảnh, Git hoặc báo cáo.

Demo dùng kho `DEMO_` riêng với quyền diễn tập được bật; dữ liệu thật dùng kho riêng. Không đổi mã DN trên một kho để dùng chung dữ liệu.

### Bước 2 · Nạp và kiểm từng bảng

Trong **Nạp dữ liệu/Dữ liệu**, chọn bảng, CSV/XLSX/XML được hỗ trợ, đúng sheet, ngày và định dạng tiền. Giữ ID ổn định và `known_at` đúng thời điểm biết. Nạp hóa đơn → bank → payments → statements → nghĩa vụ T5 → thực trả/nhận T5 → actions khi có.

Bấm kiểm tra, rà soát ghép cột, lỗi và số dòng thêm/sửa/trùng rồi xác nhận lưu. Dòng lỗi chặn cả lần lưu. Khi dữ liệu đổi sau bản xem trước, kiểm tra lại. Nạp lại cùng ID/nội dung không cộng tiền lần nữa.

T5 là từng lần đến hạn đã biết. Bảng `expense_payments` nối nghĩa vụ với bank để trừ phần đã trả/nhận. Hoàn VAT đã duyệt được ghi thành thu riêng. Không coi lịch đã quá hạn là đã thanh toán.

### Bước 3 · Đối soát và sửa nguồn có kiểm soát

Mở **Đối soát khoản thu · T9**, tìm đề xuất, nhập người xử lý và kiểm chứng từ trước khi duyệt. Ca mơ hồ cần chọn phân bổ và ghi bằng chứng. Từ chối/đảo phải có lý do. Đề xuất chưa duyệt không làm giảm công nợ; duyệt không ghi thêm tiền bank.

Sau mỗi thay đổi, tìm đề xuất mới. Một khoản thu có thể phân bổ nhiều hóa đơn và một hóa đơn nhận nhiều lần, nhưng phải đúng khách và không vượt tiền/dư nợ. Phần thừa hoặc thiếu bằng chứng giữ chờ kiểm tra.

Sửa dữ liệu nguồn bằng màn hình xem trước ảnh hưởng rồi xác nhận; quyết định liên quan được đảo và lịch sử được giữ. Không sửa trực tiếp payment do T9 tạo. Bộ [UAT T0/T9](../../pilot/t0_t9_uat_20261110/README.md) có ca thử và đáp án riêng.

### Bước 4 · Xác nhận phạm vi ngày chốt

Chốt cùng tài khoản, ngày, số dư đầu và dữ liệu thanh toán thực sự đã đủ. Ngày giao dịch mới nhất không chứng minh đã nạp đủ. Sao kê phải khớp số dư đầu + thu − chi = số dư cuối.

Xác nhận riêng tuần lịch chi đã rà soát. Tuần có một vài khoản chi vẫn có thể chưa đầy đủ; tuần chưa biết không đồng nghĩa chi bằng 0. Không tích xác nhận chỉ để vượt bước kiểm tra.

### Bước 5 · Kiểm định và theo dõi cập nhật

Trong **Quản lý → Phiên bản & kiểm định**, xem catalog/global dự phòng, bundle đang dùng và các mốc dữ liệu/tham số/sẵn sàng. Tạo chu kỳ cập nhật sau khi xác nhận coverage. Máy chủ học tiếp từ global, chọn trên validation và kiểm audit theo thời gian.

Audit đạt mới tự kích hoạt bundle hợp lệ. Thiếu mẫu/không thắng thì giữ bản hiện tại. Incumbent quá mới có thể cần lưu cặp dự báo và chờ challenger đủ nhãn 91 ngày. Ngày đến lịch cập nhật chưa bảo đảm scheduler đã chạy; phải có tác vụ được gọi và xem trạng thái thực tế.

Người có quyền có thể chọn lại phiên bản hợp lệ đã lưu; không kích hoạt model local cũ đã nghỉ dùng. Global dự phòng không có nghĩa đã học riêng cho DN. Không xóa phiên bản đang dùng hoặc được kế hoạch tham chiếu. Đọc [T1 + partial](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md) khi cần chi tiết audit.

### Bước 6 · Lập và đọc kế hoạch

Chọn ngày dự báo, kỳ 1–52 tuần (mặc định 13), số dư đầu, mức sàn và phạm vi chi đã xác nhận. Chỉ bật ước lượng hoạt động khi có learner đủ điều kiện trên đúng tài khoản; nhánh này tối đa 13 tuần và thu hóa đơn mới mặc định tắt. Forecast không học lại model trong lúc tính.

Kiểm nhãn nguồn phục vụ và phần giả định. Tiền dự thu gồm tất toán và các lần partial trên dư nợ còn lại; lịch T5 chỉ tính phần còn phải trả/nhận. Danh mục dự thu vẫn gồm khoản tạm hoãn liên hệ. Không nhân rủi ro xóa nợ lần nữa vào tiền.

Đường số dư kỳ vọng, median/P50, phân vị mô phỏng thô và dải đã hiệu chỉnh có ý nghĩa riêng. Số dư kỳ vọng dương vẫn có thể đi cùng nguy cơ xuống dưới mức sàn. Rủi ro chung theo khách là kịch bản stress; xác suất chưa được chứng nhận trên SME thật. Đọc cả phạm vi chưa biết và trạng thái hiệu chỉnh, không chỉ biểu đồ.

### Bước 7 · Truy xuống bằng chứng và khoản cần chú ý

Mở bằng chứng tiền theo tuần/hóa đơn/khách, profile partial và nguồn hỗ trợ. Phân rã số dư phải cộng khớp số dư đầu + thu − chi; đây không là phân rã P10 hoặc tác động nhân quả.

**Giải thích** ở hóa đơn nói về xác suất tất toán bốn tuần của T1, không là cam kết tiền về. Khi thiếu cơ sở diễn giải, giữ thông báo thiếu bằng chứng. **Vì sao ưu tiên?** cho công thức, điểm và quy tắc thứ tự của hàng đợi; dự báo mới dùng cùng xác suất T1 đang phục vụ, bản lịch sử giữ nguồn đã lưu. Lời hứa/tranh chấp không tự là điểm cộng riêng và ưu tiên không chứng minh gọi điện sẽ thu thêm tiền.

### Bước 8 · Thử kịch bản từ kế hoạch đã lưu

Từ đúng forecast, chọn khách và chậm thu thêm hoặc một nghĩa vụ và dời chi. T10 phát lại baseline, chạy T6 trên cùng snapshot/bundle/seed rồi lưu kết quả riêng. Xem thay đổi kỳ vọng, phân vị thô, nguy cơ thiếu tiền và phần thu/chi bị đẩy ra ngoài kỳ. Dời ra ngoài kỳ không xóa công nợ/nghĩa vụ.

Kịch bản không sửa sổ kế toán. Nếu engine/runtime không khớp, hệ thống có thể trả 409; cần phục hồi môi trường đúng bản hoặc tạo forecast mới. Không lấy model hiện tại để giải thích thay forecast cũ. Chi tiết ở [T10](../04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

### Bước 9 · Mở lại, xuất và đối chiếu

Trong **Kế hoạch đã lưu**, mở đúng ID, ngày chốt, dữ liệu, bundle và giả định. Xuất Excel từ bản đang xem; ngoài kế hoạch và hàng đợi còn có các sheet phân rã, T5, partial và identity T10. Không cố định số sheet theo hướng dẫn cũ.

Khi có thực tế, nạp sao kê/phân bổ và thực trả T5 rồi đối chiếu đúng kế hoạch. Truth được chốt theo ngày biết, đúng tài khoản; bỏ tuần thiếu coverage. Forecast được tạo sau khi biết kết quả chỉ là hồi cứu. Chất lượng và tiêu chí dùng thật theo [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md); quan sát người dùng theo [bộ pilot](../../pilot/BO_PILOT_SME.md).
