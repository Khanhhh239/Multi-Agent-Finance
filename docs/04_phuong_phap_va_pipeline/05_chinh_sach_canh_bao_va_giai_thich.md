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
`reasons_for_row`: lấy tối đa 2 lý do từ luật (xếp theo trọng số học, nên luật nhiễu như số tròn không đứng đầu một vụ đã có luật mạnh) và tối đa 2 lý do từ đuôi thực thể (chỉ khi điểm ≥ 4,0 và có mẫu câu). 12 mẫu câu hiện có, ví dụ:
- "Đơn giá hóa đơn cao hơn {x}% so với trung vị các lần mua gần nhất của chính nhà cung cấp."
- "Khoản chi lương cao hơn {x}% so với mức thường lệ của chính nhân viên (ngoài tháng thưởng)."
- "Có khoản thanh toán số tiền gần giống (sai lệch dưới 3%) cho cùng nhà cung cấp trong 30 ngày nhưng khác số hóa đơn."

**Thiếu:** mẫu câu cho 15 dấu hiệu đỏ v4. Việc cần làm: thêm vào `ENTITY_REASONS`, ví dụ "Phiếu thu áp dụng cho khách A nhưng tiền đến từ tài khoản của khách B", "Lương đăng sau ngày ghi nhận nghỉ việc", "Hoàn tiền sang tài khoản không phải của khách". Cấm dùng mô hình ngôn ngữ để tự do sinh số liệu; có thể dùng để làm mượt cách diễn đạt, sau đó kiểm tra tự động mọi con số trong câu có trong bằng chứng (H14).

## 7. Giao diện rà soát
`review_ui/` (HTML, JS, CSS, ngoại tuyến, không gửi dữ liệu đi) và `start_review.py` của bạn bạn; `agent2/review_page.py` tạo trang HTML một tệp từ hàng đợi vụ. Ghi kết luận vào nhật ký kiểm toán cục bộ có khóa tệp (`sme_fraud/feedback.py`). Chưa nối với đường ống `agent2`.
