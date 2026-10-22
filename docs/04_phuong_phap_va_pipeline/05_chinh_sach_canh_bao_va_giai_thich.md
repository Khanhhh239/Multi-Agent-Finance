# Chính sách cảnh báo và giải thích

Mã: `agent2/alerting.py`, `agent2/metrics.py` (`weekly_alerts`), `agent2/review_page.py`, `review_ui/`.

## 1. Ngân sách
Mặc định B = 3 cảnh báo cho mỗi cặp (công ty, tuần). Lấy B dòng điểm cao nhất; hòa thì phá bằng nhiễu 1e-9. Lý do: người dùng thật có ngân sách chú ý cố định; hệ thống phải xếp hạng chứ không đặt ngưỡng.

**Khe thăm dò (exploit/explore).** `exploit = ceil(2B/3)`, `explore = B − exploit`; với B = 3 là 2 và 1. Hàm `select_mixed`: chọn `exploit` dòng đầu theo điểm mô hình chính; chọn tiếp `explore` dòng theo điểm Novelty trong số dòng còn lại.
**Lý do [N]:** mô hình học trước coi bộ phát hiện chưa từng giúp ở họ đã học là vô ích, nên không thấy họ mới. Một khe luôn giao cho kênh không học giữ cửa cho kiểu mới.

## 2. Kiểm soát tỷ lệ phát hiện sai (tùy chọn)
p-giá trị conformal: `p = (1 + #{điểm hiệu chỉnh ≥ điểm}) / (n + 1)` so với giai đoạn hiệu chỉnh; sau đó Benjamini–Hochberg ở mức `q`. Cơ sở: Bates, Candès và cộng sự, *Testing for Outliers with Conformal p-values* (Annals of Statistics 2023) [T]. **Bảo đảm chỉ nói về "lạ so với bình thường của chính công ty", không phải precision gian lận**, và giai đoạn hiệu chỉnh có thể chứa gian lận chưa gán nhãn. Cần dạng có trọng số khi dữ liệu trôi. Bật bằng `--fdr`.

## 3. Gộp vụ
Các dòng bị cảnh báo gộp theo (công ty, thực thể, tuần). Thực thể = nhà cung cấp nếu có, nếu không thì nhân viên, nếu không thì người lập (`metrics.entity_key`). Một vụ = một mục trong hàng đợi.

## 4. Ưu tiên và thời hạn

| Hạng theo điểm vụ | Mức | Thời hạn | Việc cần làm |
|---|---|---:|---|
| Trong 10% đầu hoặc có hard trigger | `cao_nhat` | 24 giờ | Dừng chi hoặc kiểm tra ngay: đối chiếu hợp đồng, hóa đơn, người nhận tiền |
| Đến 50% | `cao` | 48 giờ | Yêu cầu chứng từ gốc, hỏi người lập và người duyệt |
| Còn lại | `trung_binh` | 168 giờ | Đối chiếu hóa đơn điện tử và sao kê, ghi kết luận |

Thời hạn xử lý là **mô phỏng theo mức ưu tiên** (`sla_basis = mo_phong_theo_muc_uu_tien`), không phải số liệu thật.

## 5. Độ tin cậy
`Confidence` là hồi quy isotonic từ điểm vụ sang tỷ lệ trúng quan sát trên kiểm định (mức thực thể-tuần). **Nhãn chỉ có trong mô phỏng**; ở dữ liệu thật phải thay bằng phản hồi người rà soát.

## 6. Lý do bằng tiếng Việt

Cập nhật 2026-10-22 theo code hiện tại. Đường ống tuần (`agent2/pipeline_v4.py`, hàm `explain_alerts`) ghép lý do cho mỗi dòng được cảnh báo theo thứ tự cố định:

| Thứ tự | Nguồn | Tối đa | Điều kiện | Code |
|---|---|---|---|---|
| 1 | Luật đã kích hoạt (A1, A2 có số lần, cửa sổ, tổng tiền, hạn mức; C3 có số giây duyệt) | 2 | luật có bằng chứng đủ trường | `explain_v4.rule_observations` |
| 2 | 15 dấu hiệu đỏ v4 (phiếu thu khác tài khoản khách, lương sau nghỉ việc, hoàn tiền sang tài khoản lạ, ...) | 2 | đuôi thực thể từ 4,0 trở lên, hoặc dấu hiệu nhị phân bật | `explain_v4.V4_REASONS`, `observations` |
| 3 | Đuôi thực thể của bộ phát hiện cũ (đơn giá, lương, gần trùng, tiền mặt sát hạn mức) | 2 | đuôi từ 4,0 trở lên, giá trị đo được hợp lệ | `explain_v4.entity_observations` |
| 4 | Quan sát biến động v5 so với lịch sử của chính đối tượng (lương, đơn giá, hóa đơn bán, công nợ quá hạn, trả hàng và xóa nợ, khoản định kỳ, tạm ứng) | 1 | đuôi EntityDeviation2 từ 4,0 trở lên | `explain_v5.change_observations`, `change_ops.ChangeExplainer` |
| 5 | Câu dự phòng "ưu tiên theo điểm xếp hạng" | 1 | chỉ khi bốn nguồn trên không có câu nào | `explain_alerts` |

Nguyên tắc chung:
- Mọi con số trong câu phải có trong bằng chứng của chính dòng đó; `explain_check.check` kiểm tra tự động, sai thì đường ống dừng với lỗi chứ không xuất câu sai.
- Câu mô tả một quan sát cần đối chiếu, không mô tả con người và không kết luận gian lận.
- Không dùng mô hình ngôn ngữ để sinh số liệu.
- Nguồn 4 (v5) **chỉ thêm lời giải thích**: nó không thay đổi dòng nào được cảnh báo hay thứ tự xếp hạng. Bộ EntityDeviation2 được khớp trên lịch sử không nhãn của chính công ty. Hai đặc trưng liên kết hóa đơn bị loại ở R1 v1.3 (lối tắt của bộ sinh dữ liệu, xem hạn chế L11) cũng không được dùng để giải thích.
- Dữ liệu xuất thật có thể thiếu một số cột (đơn giá, hóa đơn được áp, người thu tiền, mã tạm ứng) hoặc thiếu bảng công ty; `change_ops.lenient_change_features` coi cột thiếu là rỗng và kỳ hạn công nợ mặc định 30 ngày. Nếu bước này lỗi, báo cáo tuần ghi `change_observations = "skipped: <loại lỗi>"` và đường ống vẫn chạy với nguồn 1 đến 3.
- Tỷ lệ dòng chỉ có câu dự phòng được ghi trong báo cáo tuần (`ranking_only_explanations`); trong thí điểm cần theo dõi chỉ số này cùng K2 (`scripts/pilot_kpis.py`, phân theo họ tín hiệu).

## 7. Giao diện rà soát

Có hai lối vào, đều ngoại tuyến hoặc nội bộ, không gửi dữ liệu ra ngoài:
- Dịch vụ `agent2/service.py` (Flask): tải dữ liệu, chấm điểm tuần, hàng đợi vụ, ghi kết luận vào kho rà soát SQLite. Giao diện `review_ui/v4.html` (kèm `v4.js`, `v4.css`) và trang danh mục khách `review_ui/portfolio.html` (GET `/portfolio`, chỉ đọc, chỉ khóa của công ty dịch vụ). Hướng dẫn vận hành: `docs/05_ke_hoach_giao_viec/huong_dan_van_hanh.md`; hướng dẫn cho người rà soát: `docs/05_ke_hoach_giao_viec/huong_dan_ke_toan_vien.md`.
- Trang HTML một tệp do `agent2/review_page.py` tạo từ hàng đợi vụ, dùng khi chưa dựng dịch vụ.

Chỉ số thí điểm K1, K2, K3, K5 đọc trực tiếp từ kho rà soát bằng `scripts/pilot_kpis.py` (chỉ đọc).
