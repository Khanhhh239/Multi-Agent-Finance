# Thu gọn Agent2 ngày 10/11/2026

Theo chỉ đạo mới và [đặc tả v2.1](../../Agent2_Spec_v2_1/00_INDEX_va_quy_tac.md), bản làm việc chỉ giữ bốn nhóm phân tích cùng dependency và kiểm thử cần thiết.

- Luật, feature và graph giữ nguyên mã và kết quả trên fixture đối chứng.
- Isolation Forest, ECOD, LOF và Autoencoder giữ thuật toán; catalog không còn CatBoost hoặc bộ chọn bằng tiêm mẫu. Fit không nhận nhãn ngoài.
- Các primitive thống kê không nhãn được tách nguyên từ code cũ; vẫn cần reference/fit lịch sử. P-value và percentile không được trình bày thành xác suất gian lận.
- 23 module kiểm thử cũ được giữ; thêm kiểm tra parity, không fit khi score và trang trạng thái. Baseline cũ 357 test qua; candidate 363 test qua, không skip.
- 3.173 file nguồn/dữ liệu/báo cáo cũ được kiểm checksum tại `D:/agent22_legacy_20261110/agent2`. Môi trường `.venv` dùng lại tại `agent2/.venv`.

Web, database, dataset, model đang ghim, phiếu rà, thông báo và release cũ được lưu ngoài bản làm việc. Không tự chuyển các kết luận/nhãn hoặc cấu hình active sang pipeline mới. API cũ trả 410; cổng 8766 chỉ hiển thị trang chuyển đổi.

Đã đọc DOCX nguồn (hash đúng manifest) và kiểm tra 34 checksum gốc của bộ đặc tả. Các đường dẫn schema.py/methods.py/pipeline_v4.py trong DOCX là tham chiếu thiết kế; repo thực dùng namespace sme_fraud.

Mốc hiện tại là **R0 READY_FOR_REVIEW**, không phải R1–R6 đã triển khai. [Báo cáo đầy đủ, inventory, state migration và các FLOW chưa test được](../../Agent2_Spec_v2_1/evidence/R0/REPORT.md).
