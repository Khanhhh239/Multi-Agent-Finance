# Yêu cầu sản phẩm và phạm vi hiện tại

Đối chiếu Workspace ngày 14/11/2026. Chi tiết kỹ thuật nằm trong [README dịch vụ](../../agent1_service/README.md), [T1 + partial](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md), [T6](../04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) và [T10](../04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md). Bảng dưới mô tả hành vi, không chứng nhận chất lượng mô hình.

## Hành trình sử dụng

1. Kết nối Workspace từ Portal hoặc dịch vụ local; chọn đúng doanh nghiệp.
2. Nạp CSV/Excel/XML, ghép cột, chọn định dạng ngày/tiền, xem trước và xác nhận lưu. Có lỗi thì sửa trước khi ghi.
3. Kiểm tra sổ dữ liệu, lịch sử nạp và đề xuất đối soát T9; duyệt, từ chối hoặc phân bổ thủ công có bằng chứng. Chỉ quyết định đã duyệt mới đổi công nợ.
4. Xác nhận phạm vi thanh toán và lịch nghĩa vụ còn phải trả. Kiểm định/huấn luyện tách khỏi tạo dự báo; đọc trạng thái phiên bản và audit.
5. Chọn ngày chốt, số dư đầu, ngưỡng cảnh báo và kỳ dự báo; tạo kế hoạch mới.
6. Xem khoản cần chú ý, giải thích, phân rã thu chi và kịch bản; xuất Excel/bằng chứng, đối chiếu thực tế khi có dữ liệu mới.

## Chức năng

| Mã | Phạm vi phục vụ |
|---|---|
| FR-01 · T0 | Kiểm dữ liệu và quan hệ, tiền VND chính xác, lịch sử snapshot/nguồn/ngày biết; hỗ trợ vòng đời chứng từ theo hợp đồng nạp |
| FR-02 · T9 | Đề xuất một/nhiều hóa đơn và trả một phần; có duyệt/từ chối/đảo, chặn vượt tiền hoặc công nợ; `auto` là mức đề xuất, vẫn cần duyệt |
| FR-03 · T1 | Catalog global Neural/LightGBM/XGBoost, học tiếp theo doanh nghiệp, chọn cùng partial adapter qua validation/audit; cập nhật theo chu kỳ và chờ nhãn khi cần |
| FR-04 · Partial | Tách xác suất tất toán khỏi xác suất/tỷ lệ thu một phần; dùng cùng bundle cho kiểm định, dự báo và mô phỏng |
| FR-05 · T5 | Nghĩa vụ cố định/hồ sơ đã biết, thanh toán nghĩa vụ và phần còn lại; khoản đến/quá hạn chưa trả được chuyển theo quy tắc hoặc ngày dự kiến mới |
| FR-06 · T6 | Kế hoạch 1–52 tuần, mặc định 13; kỳ vọng, P10/P50/P90 và nguy cơ thiếu tiền; mô phỏng nhiều lần thu trên dư nợ còn lại |
| FR-07 · Hoạt động | Ước lượng thu/chi hoạt động khi bật và đủ lịch sử, kiểm phạm vi tài khoản; nhánh thu hóa đơn mới không tự bật |
| FR-08 · T10 | SHAP T1 tại mốc 4 tuần, bằng chứng tất toán/partial, giải thích ưu tiên và phân rã kế toán; số có nguồn từ engine/template |
| FR-09 · Kịch bản | Phát lại T6 theo bundle/dữ liệu đã lưu, khách chậm hoặc dời chi; lưu so sánh kỳ vọng, phân vị và xác suất thiếu tiền |
| FR-10 · Truy vết | Lưu phiên bản, snapshot, manifest/bằng chứng và export; đổi active hoặc nạp mới không sửa kế hoạch cũ |

T2/T3/T4/T7/T8/T11–T13 là mã nhiệm vụ nghiên cứu; sự tồn tại của mô-đun/kết quả cũ chưa có nghĩa mọi đầu ra đó đang bật trên giao diện. Không còn dùng catalog T1 học mới từ đầu tại Workspace; Workspace trong tài liệu này chỉ ứng dụng người dùng.

## Tiêu chí UAT và vận hành

| Nhóm | Cách kiểm |
|---|---|
| Nạp dữ liệu | Lỗi chỉ đúng dòng/cột; lần xem trước chưa ghi; gửi lại cùng xác nhận không nhân đôi thanh toán |
| Đối soát | Chỉ duyệt mới đổi dư nợ, không vượt nguồn; đảo quyết định phục hồi đúng và giữ lịch sử |
| Ngày chốt | Không dùng giao dịch/phiên bản chỉ biết sau cutoff; xác nhận phạm vi thiếu phải được nêu |
| Chi | Chỉ tính nghĩa vụ còn lại; thiếu xác nhận không tự xem là đã thanh toán |
| Tiền và phân rã | Số dư đầu + thu − chi = số dư cuối; không cộng P10 từng hóa đơn thành P10 danh mục |
| Giải thích | Phản ánh đúng model/partial/snapshot; thiếu cơ sở thì báo thiếu; SHAP tất toán không bị gọi là giải thích tiền |
| Kịch bản | Cùng nguồn ngẫu nhiên với baseline; tiền ngoài kỳ ghi riêng; đây là độ nhạy trong mô hình |
| Phiên bản/export | Mở kế hoạch cũ giữ đúng bằng chứng; Excel/JSON khớp số chưa làm tròn |
| Khả năng hiểu | Người dùng chỉ đúng tuần cần chú ý, phạm vi dự báo và giới hạn; cần thử nghiệm thực tế |

Mục tiêu hiệu năng/SLA cần benchmark theo quy mô và cấu hình trước khi cam kết. Chất lượng xác suất, độ phủ, cảnh báo và pilot dùng [cổng hiện hành](../03_Evaluation/03_cong_nghiem_thu.md), không dùng số test hoặc bảng tháng 10 để thay.

## Ranh giới

Không tự chuyển tiền, vay, thanh toán hoặc liên hệ khách; không tự xóa chênh lệch thành phí hay xóa nợ. Luồng hiện tại chưa cam kết Zalo/chat, tự kết nối mọi cổng hóa đơn, dự phòng pháp lý, thanh khoản hợp nhất đa tài khoản hay đa tiền tệ đầy đủ. Lời hứa/liên hệ được ghi thành dữ liệu có cấu trúc.

Nghĩa vụ cần hồ sơ/ngày hiệu lực và rà soát pháp lý trước dùng thật. Dữ liệu doanh nghiệp cần quyền sử dụng và kiểm soát truy cập phù hợp; hợp đồng triển khai đọc ở [bảo mật](../security_privacy.md). Tài liệu BA không thay văn bản pháp lý hoặc chứng nhận tuân thủ.
