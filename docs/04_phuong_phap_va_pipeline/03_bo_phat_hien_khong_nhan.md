# Bộ phát hiện không cần nhãn

Mã: `agent2/methods.py`. Chế độ **U**: khớp trên lịch sử không nhãn của chính công ty (giai đoạn huấn luyện); không đọc `is_fraud`.

## 1. EntityDeviation (thiết kế của tôi [N])

**Ý tưởng.** Nhiều gian lận không làm giao dịch "lạ" so với cả công ty, mà làm nó "lạ" so với **chính thực thể**: một nhà cung cấp bỗng tăng giá, một nhân viên bỗng được trả nhiều hơn, một người lập bỗng chi nhiều khoản sát hạn mức. Vì vậy mỗi bộ phát hiện so một đại lượng của dòng với phân phối **của cùng loại dòng** trong giai đoạn huấn luyện, chỉ khi thực thể có đủ lịch sử.

**Cách tính.** Với mỗi bộ phát hiện `d` có điều kiện kích hoạt `active_d` (ví dụ `price_n ≥ 3`):
```
tail_d(x) = (số điểm tham chiếu ≥ x + 1) / (số điểm tham chiếu + 1)     đuôi phải thực nghiệm
điểm_d    = −log(tail_d)       nếu active_d, ngược lại 0
điểm      = max_d điểm_d
```
Tham chiếu là các giá trị của đại lượng ở dòng thỏa `active_d` trong giai đoạn huấn luyện; nếu ít hơn 20 điểm tham chiếu thì bộ phát hiện tắt. Điểm lớn nghĩa là hiếm: `điểm = 4` tương ứng xác suất đuôi khoảng 1,8%; ngưỡng đưa vào lý do là 4,0.

**25 bộ phát hiện:**
- 12 bộ gốc: `price_logratio`, `price_logz`, `price_shift3`, `p_logratio` (lương, tách tháng thưởng), `p_logratio_bonus`, `cu_logratio`, `near_dup_other_invoice_30d`, `near_dup_30d`, `creator_cash_near_selflimit_30d`, `amount_selflimit_ratio`, `creator_unsupported_selfcash_30d`, `v_days_dormant_amount`.
- 13 bộ v4: 13 trong 15 dấu hiệu đỏ ở tệp 02 mục 3 (`receipt_days_late` và `offquarter_writeoff` chưa có bộ riêng; `writeoff_overdue_days` được đảo dấu thành `writeoff_recency`). Tự bỏ qua nếu thiếu cột.

**Vì sao max chứ không cộng:** mỗi kịch bản bật một bộ phát hiện; cộng làm loãng tín hiệu mạnh bằng nhiều bộ im lặng. **Đánh đổi:** max dễ phát nhiều cảnh báo hơn nếu có một bộ nhiễu.

**Kết quả [M]:** v4 AP 0,025 nhưng recall@B3 34,5% và rất mạnh ở kịch bản lẫn trong hành vi: `payroll_padding` 79%, `price_creep` 86%, `altered_payee` 100%, `terminated_still_paid` 92%.

## 2. ECOD (cài lại [Đ cho ý tưởng, T cho chi tiết bài])

Li và cộng sự (TKDE 2023): không tham số; với mỗi đặc trưng tính xác suất đuôi trái và phải từ CDF thực nghiệm; điểm = max của tổng `−log` đuôi trái, tổng đuôi phải và tổng đuôi theo hướng lệch của phân phối. Bỏ đặc trưng hằng. Có hàm `explain` trả đặc trưng đóng góp lớn nhất.
**Kết quả:** AP 0,006 trên v4: yếu vì đặc trưng một biến không bắt được bất thường theo thực thể.

## 3. HBOS (cài lại [K])
Biểu đồ tần suất 20 ô phân vị theo từng đặc trưng; điểm = tổng `−log(mật độ)`. Ngoài khoảng thì lấy nửa mật độ nhỏ nhất. **Kết quả:** AP 0,007; nhanh nhưng yếu.

## 4. Isolation Forest [K]
300 cây, `max_samples = min(2048, n)`. Chạy trên 190 đặc trưng gốc (đường cơ sở của bạn bạn) hoặc trên đặc trưng liên tục cộng baseline thực thể (loại các cột mã hóa loại nghiệp vụ và tài khoản để điểm không bị chi phối bởi loại giao dịch hiếm). **Kết quả:** AP 0,004 đến 0,006 trên v4.

## 5. Autoencoder (Schreyer và cộng sự 2017 [Đ]; bản thu gọn của tôi)
MLP (48, 12, 48), kích hoạt ReLU, 60 vòng, lô 256, tốc độ học 1e-3; đầu vào chuẩn hóa phân vị về phân phối chuẩn (`QuantileTransformer`, 200 phân vị); điểm = sai số tái tạo bình phương trung bình. Khác bài gốc: bài gốc mã hóa thuộc tính phân loại nhị phân và huấn luyện mỗi sổ cái một mạng; ở đây dùng đặc trưng số. **Kết quả:** AP 0,096, recall@B3 37% nhưng báo nhầm ca khó 32%: mạnh ở bất thường nhưng khó phân biệt "lạ nhưng hợp lệ".

## 6. Luật (bạn bạn)
Điểm cộng có trọng số tay; chế độ đồ thị. **Kết quả:** v3 AP 0,24; v4 AP 0,079. Cần giữ vì giải thích được và bắt các kiểu mà không thống kê nào bắt được (trùng định danh nhà cung cấp và nhân viên).

## 7. Kết hợp không cần nhãn

| Phương pháp | Công thức | Mục đích |
|---|---|---|
| **Novelty** | `max(hạng luật, hạng EntityDeviation) + 0,001 × trung bình hạng` | Kênh cảnh báo không học; hạng so với phân phối kiểm định |
| Gate | `điểm luật + 0,5 × hạng ECOD` | Luật quyết định thứ tự; điểm thống kê chỉ phá hòa và cứu dòng luật bỏ sót. Sửa blend 80/20 của bạn bạn |
| Blend 80/20 (bạn bạn) | `0,8 × hạng luật + 0,2 × hạng IF` | Đường cơ sở; IF yếu làm tụt dòng đã trúng luật |
| RankFusion | `max` hoặc trung bình của các hạng đã chuẩn hóa | Hợp nhất tổng quát |

**Kiểm chứng trên dữ liệu của chính bạn bạn (`sme_fraud_003`):** Rules+Graph "gated by IF" AP 0,665, so với ensemble 80/20 AP 0,4525 và Rules+Graph 0,6136 (biến thể thêm vào `run_rules.py`).

## 8. Điều đúc kết
1. Không có phương pháp không nhãn nào thắng ổn định (ADBench [Đ]; ERP Fraud Data cho cùng kết luận [M]). Đừng tìm "bộ phát hiện tốt nhất"; kết hợp theo kịch bản.
2. Học sâu không giám sát không vượt phương pháp nông trên dữ liệu bảng (ADBench).
3. Giá trị của nhóm không nhãn là **phủ khoảng trống của mô hình có giám sát** (kịch bản chưa thấy), không phải thay thế nó.
