# Chiến lược phát triển Agent 1 từ 24/10/2026

> **Quyết định và ưu tiên tại thời điểm 24/10.** Các câu “tiếp theo” trong thân
> bài giữ để truy vết lý do đổi hướng; chúng không giao việc mới. Đọc
> [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md), [cổng](../03_Evaluation/GATES_CURRENT.md)
> và [bộ synthetic cuối](../02_Data/23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md)
> trước khi chọn việc tiếp theo.

> Viết sau khi đo xong sprint 5–6. Mọi nhận định dựa trên kết quả đã ghi trong `docs/03_Evaluation/` và nhật ký mục 8–21.
> Người quyết định: chủ dự án. Người thực hiện: agent1-Khanh và coding agent kế tiếp.

## 1. Chẩn đoán: chúng ta đang ở đâu và vì sao chậm lại

| Điều đã chứng minh | Bằng chứng |
|---|---|
| Lõi dự báo ngày trả (T1) tốt hơn mốc đơn giản trên dữ liệu thật nước ngoài | BLEND +14,4% (Customer Invoices), +6,5% (BPI) |
| Lớp an toàn hoạt động | Cầu dao cắt 2/3 thiệt hại khi mô hình thua (BPI) |
| Dải số dư có độ phủ đúng | copula-t + ACI 0,75–0,77 trên 2 bộ đích |
| Chính sách cảnh báo đủ tốt **nếu có nhãn** | Báo giả 0,33–0,90 với nhãn thật, trên 3 bộ đích |
| **Nút thắt là độ phủ nhãn của T9**, không phải mô hình | Ablation 50/80/100% → 2,07 / 1,37 / 0,87; nhãn mềm giảm 33–62% |

| Điều đã thử nhiều vòng mà không thắng | Số vòng |
|---|---|
| G3/G4 (độ phủ, hiệu chỉnh khoảng T1) | 2 |
| G7 (tinh chỉnh 12 tháng ≥ 10%) | 2 |
| G8 (SBA, năm 2022 vỡ nợ tăng thật) | 1 (nguyên nhân nằm ở dữ liệu) |
| G15 (T9 F1 ≥ 0,8) | 3 |
| Chỉnh máy phát cho giống thật | 3 (bộ tham chiếu chỉ 6 công ty, không đủ phân biệt) |

**Kết luận chiến lược:** lợi ích biên của việc "thêm một vòng tối ưu trên dữ liệu sinh" đang giảm nhanh. Ba trần còn lại nằm ở:
1. **Thông tin** (thiếu số hoá đơn trong nội dung chuyển khoản ⇒ T9 không thể biết chắc),
2. **Dữ liệu thật** (không có doanh nghiệp Việt Nam nào; không kiểm chứng được máy phát),
3. **Định nghĩa cổng** (một số cổng đòi điều mà bài toán không cho, ví dụ G8 đòi hiệu chỉnh xuyên qua thay đổi chế độ).

Vì vậy chiến lược chuyển từ "đạt thêm cổng trên dữ liệu sinh" sang **ba mũi song song**, theo thứ tự giá trị.

---

## 2. Ba mũi chiến lược

### Mũi A — Đưa vào dữ liệu thật: chạy bóng với 3–5 doanh nghiệp (ưu tiên cao nhất)

**Vì sao:** đây là việc duy nhất biến "đúng trên dữ liệu sinh" thành "đúng với doanh nghiệp thật". Hệ thống đã sẵn sàng cho bậc 0 (chỉ ghi dự báo, không ai hành động theo).

| Việc | Đầu ra | Ai |
|---|---|---|
| A1. Gói dữ liệu tối thiểu cần xin | Danh sách: XML hoá đơn điện tử 12–18 tháng, sao kê ngân hàng cùng kỳ (CSV/Excel), sổ công nợ phải thu, số dư đầu kỳ | agent1-Khanh viết, chủ dự án gửi |
| A2. Cam kết bảo mật + ẩn danh | Văn bản 1 trang: dữ liệu ở máy cục bộ, mã hoá (store đã dùng Fernet), xoá theo yêu cầu (`delete_firm` có sẵn) | agent1-Khanh |
| A3. Kịch bản nạp một doanh nghiệp từ đầu đến cuối | Script nạp + báo cáo chất lượng dữ liệu T0 + dự báo đầu tiên trong < 1 ngày làm việc | coding agent |
| A4. Bảng theo dõi chạy bóng 8 tuần | So mỗi tuần: dự báo vs thực tế, BLEND vs B1d, độ phủ dải ACI, báo động | coding agent |
| A5. Tìm 3–5 doanh nghiệp | Quan hệ của chủ dự án; ưu tiên ngành có bán chịu (thép, dệt, nhựa, bán buôn) | **chủ dự án** |

**Tiêu chí lên bậc 1 (đã có trong GO_NO_GO):** ≥ 8 tuần; BLEND không thua B1d; dải phủ 75–85% trên dữ liệu thật của họ.
**Giá trị phụ quan trọng:** dữ liệu thật đầu tiên dùng được ngay để (i) kiểm định máy phát (thay bộ 6 công ty Mỹ), (ii) đo tỉ lệ chuyển khoản có số hoá đơn thật ở Việt Nam — con số quyết định trần của T9.

### Mũi B — Biến nút thắt T9 thành tính năng sản phẩm (kỹ thuật, 1–2 tuần)

**Thay đổi tư duy:** đừng cố để máy ghép 100% một mình. Ablation cho thấy cần độ phủ nhãn rất cao; trong vận hành thật, độ phủ đến từ **máy + người duyệt nhanh**. Thiết kế cho điều đó.

| Việc | Ý tưởng | Đo thế nào | Ưu tiên |
|---|---|---|---|
| **B1. Hàng chờ duyệt thông minh** | Xếp các giao dịch chờ theo "giảm báo giả nhiều nhất trên mỗi lần bấm" (giao dịch lớn, của khách nhiều hoá đơn mở, sắp tới tuần rủi ro). Kế toán chỉ cần xác nhận 1 trong 2–3 gợi ý | Mô phỏng người duyệt trả lời đúng: X% hàng chờ được duyệt → độ phủ → báo giả G13. Mục tiêu: số lần bấm/tuần để đạt báo giả ≤ 1 | **1** |
| **B2. Nhãn mềm có trọng số** | Nhãn mềm đã giúp (tgt5 đạt, tgt3 giảm 33%). Cho T1 biết nhãn nào là mềm (cột cờ + trọng số mẫu 0,3–0,5), hoặc chỉ giữ nhãn mềm của khách có lịch sử trả đều | Đăng ký trước, chọn trên nguồn, đo một lần trên **`tgt6`** mới **và** lặp lại trên `tgt3` (yêu cầu đạt cả hai) | 2 |
| **B3. "Ghi số hoá đơn khi chuyển khoản"** | Mẫu tin nhắn/QR/nội dung CK gợi ý sẵn số hoá đơn trên hoá đơn điện tử gửi khách. Quy tắc theo số hoá đơn luôn đúng 100% | Mô phỏng: tăng tỉ lệ có số HĐ 55% → 70/85% ⇒ recall T9, F1 G15, báo giả G13 | 2 |
| B4. Ghép phần cuối của thanh toán từng phần | Khi đã ghép phần đầu, phần còn lại khớp số dư ⇒ ghép phần cuối | Chọn trên nguồn | 3 |

**Quy tắc dừng cho mũi B:** nếu sau B1 + B2 mà G13 vẫn không đạt trên **cả** `tgt6` và `tgt3`, dừng tối ưu G13 trên dữ liệu sinh; coi G13 là "chờ dữ liệu thật" và chỉ đo lại khi có mũi A.

### Mũi C — Rà lại định nghĩa cổng (quyết định của chủ dự án, nửa ngày)

Không đổi cổng sau khi xem kết quả để "cho đạt". Đây là đề xuất **định nghĩa lại cho đúng mục tiêu sản phẩm**, ghi rõ lý do, giữ dòng cũ để kiểm toán.

| Cổng | Vấn đề | Đề xuất (chủ dự án quyết) |
|---|---|---|
| G3 | Đòi cov80 trong 75–85%; khoảng **rộng hơn** (0,84–0,87) an toàn hơn cho dòng tiền | Cho phép 75–90% nếu IS80 không xấu đi; hoặc giữ nguyên |
| G8 | Đòi tỉ lệ 0,8–1,25 xuyên qua thay đổi chế độ năm 2022 (vỡ nợ ×4–5) | Đổi thành "phát hiện trôi tỉ lệ gốc trong ≤ 2 quý và cảnh báo" |
| G7 | Tinh chỉnh M12 không giúp vì mô hình nguồn đã đủ tốt | Đổi thành "không xấu đi so với nguồn"; hoặc bỏ |
| G13 | Đo trên đường nhãn T9 cũ | Đo trên luồng triển khai thực (T9 + nhãn mềm + hàng chờ duyệt mô phỏng) |
| G11 | Cần chuyên gia | Giữ `out_of_scope` cho tới mũi A |

---

## 3. Lịch hai tuần đầu

| Ngày | Mũi A (dữ liệu thật) | Mũi B (T9 → sản phẩm) | Mũi C |
|---|---|---|---|
| 1–2 | A1, A2: gói dữ liệu + cam kết bảo mật | B1: mô phỏng hàng chờ duyệt (đăng ký trước) | Chủ dự án đọc bảng mục 2C, quyết |
| 3–5 | A5: liên hệ doanh nghiệp | B1 đo trên `tgt3`/`tgt5`; B3 mô phỏng tỉ lệ số HĐ | Cập nhật `evaluate_gates.py` theo quyết định (giữ dòng cũ) |
| 6–8 | A3: kịch bản nạp một doanh nghiệp | B2: đăng ký trước → sinh `tgt6` → đo một lần | — |
| 9–10 | A4: bảng theo dõi chạy bóng | Tổng hợp; áp quy tắc dừng | Báo cáo cổng mới |

**Mốc kiểm tra ngày 10:** (i) có ít nhất 1 doanh nghiệp đồng ý chia sẻ dữ liệu? (ii) G13 đạt trên cả 2 thế giới với luồng có hàng chờ duyệt? Nếu (i) không, toàn bộ nỗ lực tiếp theo dồn vào mũi A; kỹ thuật chỉ bảo trì.

---

## 4. Phân công để không đụng nhau

| Người | Sở hữu file | Việc |
|---|---|---|
| agent1-Khanh | `agent1/models/t9_soft_labels.py`, `agent1/eval/alert_policy.py`, `scripts/sprint5/`, tài liệu đánh giá | B1, B2, B3 (mô phỏng), A1, A2, tài liệu |
| Coding agent kế tiếp | `agent1_service/` (nạp, store, API), `scripts/sprint6/`, `t9_fast.py`, `features.py` | A3, A4, B4; **đẩy sprint6 lên git trước tiên** |
| Chủ dự án | — | A5 (tìm doanh nghiệp), quyết bảng mục 2C |

**Quy ước chung:** mọi đo lường mới đăng ký trước và commit trước khi sinh bộ đích; chạy tuần tự qua `scripts/sprint5/wait_ram_then.sh`; chỉ chép file của mình vào `.publish-repo`; `fetch` trước khi `push`.

---

## 5. Thước đo thành công của giai đoạn tới

| Mức | Định nghĩa |
|---|---|
| Tối thiểu | 1 doanh nghiệp thật chạy bóng ≥ 4 tuần; báo cáo so sánh dự báo vs thực tế |
| Tốt | 3 doanh nghiệp; BLEND không thua B1d trên dữ liệu thật của họ; dải ACI phủ 75–85% |
| Rất tốt | Thêm: G13 đạt trên dữ liệu thật với hàng chờ duyệt; tỉ lệ số HĐ trong CK đo được và T9 được chỉnh theo đó |

**Điều KHÔNG phải mục tiêu:** đạt 18/18 cổng trên dữ liệu sinh. Đó là thước đo hệ thống chạy đúng, không phải thước đo giá trị cho doanh nghiệp.

---

## Cập nhật 24/10 tối: kết quả B1 và quy tắc dừng đã kích hoạt
- B1 xong: duyệt 5/tuần đạt sát trên `tgt6` (0,970) nhưng trượt `tgt3` (1,371) ⇒ **dừng tối ưu G13 trên dữ liệu sinh** đúng quy tắc mục 2B.
- Cũng thấy: với nhãn thật, báo giả đã 0,90–0,94 ở hai thế giới khó ⇒ phần còn lại của G13 nằm ở mô hình dòng tiền/thế giới, không còn ở nhãn.
- Hàng chờ duyệt vẫn là **thiết kế sản phẩm nên giữ** (giảm 19–24% báo giả so với chỉ nhãn mềm với ~3 lượt duyệt/DN/tuần).
- **Ưu tiên kế tiếp chuyển hẳn sang mũi A** (dữ liệu thật). B2, B3 chỉ làm nếu có thời gian rảnh; không mở thêm vòng tối ưu G13 trên dữ liệu sinh.

## Cập nhật 24/10: A1 xong, A2 bản nháp
- **A1** `docs/06_Pilot/01_GOI_DU_LIEU_CAN_XIN.md` (+ PDF `agent1_goi_du_lieu.pdf`): dữ liệu tối thiểu (XML hoá đơn 12–18 tháng, sao kê cùng kỳ, số dư đầu kỳ, chi cố định), nên có, việc hằng tuần, không cần gửi, danh sách kiểm tra. Gửi được ngay.
- **A2** `docs/06_Pilot/02_CAM_KET_BAO_MAT.md` (+ PDF `agent1_cam_ket_bao_mat_NHAP.pdf`, có dấu BẢN NHÁP). **Chưa được ký** cho tới khi:
  1. pháp chế rà soát (Nghị định 13/2023/NĐ-CP);
  2. gắn ẩn danh HMAC vào bước nạp (hàm có sẵn trong `agent1_service/ingest/privacy.py` nhưng chưa dùng);
  3. chuyển `encryption.key` ra khỏi thư mục `.state/` (hiện nằm cùng `agent1.db`, `agent1_service/api.py` dòng 63–65).
  Việc 2–3 giao coding agent cùng mũi A3.
