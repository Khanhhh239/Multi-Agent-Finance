# Báo cáo đánh giá "35 luật" so với "35 luật + ML"

## 1. Phạm vi, hợp đồng và điều kiện cố định

- **Profile dữ liệu**: `agent2-rule-snapshot/1.0.0` (đánh giá tại node doanh nghiệp local, `he_execution=false`).
- **Contract ML**: `rule-snapshot-point-in-time/1.0.0` (33 cột; 8 cột cấu trúc không có bảng nguồn trên native giữ `null` kèm lý do và chạy qua `missing_policy='median_flags'`).
- **Chính sách chọn đã khóa**: `rules_first_fill/1.0.0`, ngân sách tối đa `budget=5` giao dịch/doanh nghiệp, `selection_uses_feedback=false`, `operational_queue_changed=false`.
  - Phương án **Chỉ 35 luật**: giữ nguyên các giao dịch có tín hiệu cảnh báo nghiệp vụ đủ căn cứ (`rule_state='alert'`), giữ nguyên cụm cảnh báo đồng thời (`P1/A1/A2/A3/A4`), tối đa 5; không điền ngẫu nhiên nếu dưới 5.
  - Phương án **35 luật + ML**: giữ nguyên danh sách của **Chỉ 35 luật**; dùng điểm ML đã fit riêng trước đó cho từng doanh nghiệp để xếp hạng các ứng viên không trúng luật còn lại và bù vào đúng phần ngân sách còn trống (tổng `<= 5`).
- **Tách riêng ngoài hàng chọn giao dịch**:
  - `B5/E4/E3` (`master_quality`): không cộng điểm hoặc đẩy giao dịch thành `alert`; `B5/E4` được gộp theo chứng từ dùng chung (`master_quality_dedup_groups`).
  - `D1–D6, F4` (`SCOPE_RULES`): giữ tại `scope_results` / `scope_diagnostics`, không chuyển thành cảnh báo từng dòng giao dịch.
  - `history_only` (`42` giao dịch trước `2026-10-01T00:00:00+07:00`): chỉ dùng làm lịch sử quy chiếu và fit offline trước kỳ đánh giá (`fit` 2026-07-01..2026-09-21), không nằm trong `25` ứng viên đánh giá kỳ `2026-10-02..2026-10-19`.

## 2. Kết quả thử nghiệm trên dữ liệu giả lập > 5 ứng viên (`C001` & `C002`)

Kịch bản chạy từ [run_rule35_ml_comparison.py](file:///D:/agent22/agent2/scripts/run_rule35_ml_comparison.py) và nguồn [rule35_ml_eval_demo.py](file:///D:/agent22/agent2/sme_fraud/rule35_ml_eval_demo.py), sử dụng [rule35_comparison.py](file:///D:/agent22/agent2/sme_fraud/rule35_comparison.py) và lưu kế hoạch khóa bất biến trong `ComparisonStore` cùng bộ phiếu rà khởi tạo trống trong `ReviewStore` tại `D:\agent22\.runtime\rule35-ml-eval`:

| Chỉ số | C001 (`isolation_forest`) | C002 (`ecod`) |
| --- | --- | --- |
| Snapshot ID đánh giá | `snp_9973175520304a91bf9db2af5c4661ed` | `snp_8dffff0a35a1425487278d35eff1afa7` |
| Analysis ID (`technical`) | `ana_dae5f986cc5b90f24661192dea069d0c4969c3ce354fa1e59943e02ddcd6c76b` | `ana_8446f27b2f7753110ec2a71b6ff0e6558ccfc3c334e3887c955f248ebcfbe153` |
| Model Artifact Pin | `mth_9f2b14e4a5684889dad5f20036a8e5af94c9176766db4e6be8dafdecb77248f2` | `mth_bfd97d9185a6e14e3b65829fa46215748423c74c2dbc8f01aa0bd7d5964ec48e` |
| Số ứng viên (`history_only`) | `25` ứng viên (`42` lịch sử bị loại khỏi hàng chọn) | `25` ứng viên (`42` lịch sử bị loại khỏi hàng chọn) |
| Đánh giá luật sạch (`all_applicable_evaluated`) | `25 / 25` | `25 / 25` |
| Điểm ML khả dụng | `25 / 25` | `25 / 25` |
| Master-quality `B5/E4` (sau gộp trùng) | `22` dòng liên quan → `1` nhóm evidence duy nhất | `22` dòng liên quan → `1` nhóm evidence duy nhất |
| **Chỉ 35 luật** (`selected / budget`) | **`3 / 5`** (`2` chỗ trống, không điền ngẫu nhiên) | **`4 / 5`** (`1` chỗ trống; 0 luật `P1`, đủ 4 họ `A/B/E`) |
| **35 luật + ML** (`selected / budget`) | **`5 / 5`** (giữ `3` luật + ML thêm `2`) | **`5 / 5`** (giữ `4` luật + ML thêm `1`) |
| Phân loại phần ML thêm | `2` ca `all_applicable_rules_evaluated_no_hit` | `1` ca `all_applicable_rules_evaluated_no_hit` |
| Phiếu đã có kết luận người rà (`resolved`) | `0 / 5` (`pending = 5`, `accuracy = null`) | `0 / 5` (`pending = 5`, `accuracy = null`) |
| Thời gian rà (`saved_connected_seconds`) | `null` (chờ người rà thực hiện trên `ReviewStore`) | `null` (chờ người rà thực hiện trên `ReviewStore`) |

### Chi tiết từng dòng được chọn và lý do

#### Doanh nghiệp `C001` (`isolation_forest`, cutoff `2026-10-20T00:00:00+07:00`)

1. **Nhóm nền 35 luật (3 giao dịch)**:
   - `C1_EV_01_P1A` (`15,000,000 VND`, `2026-10-02T10:00:00+07:00`): `rule35_alert` — trúng luật `P1` trong cụm đồng thời `BE_e33b80e301644afff62d` (chi cùng hóa đơn vượt tổng hóa đơn). Điểm `isolation_forest = 0.5724`.
   - `C1_EV_02_P1B` (`14,000,000 VND`, `2026-10-02T10:00:00+07:00`): `rule35_alert` — cùng cụm đồng thời `BE_e33b80e301644afff62d` với `C1_EV_01_P1A`, giữ nguyên cả cặp (`2` slot). Điểm `isolation_forest = 0.5704`.
   - `C1_EV_03_C2` (`16,000,000 VND`, `2026-10-05T10:00:00+07:00`): `rule35_alert` — tự duyệt vượt hạn mức cá nhân (`C2`; kèm `A5`). Điểm `isolation_forest = 0.3910` (thứ tự lấy theo nhóm luật nghiệp vụ trước).
2. **Phần ML bổ sung vào 2 chỗ trống (`ml_filled_remaining_slots`)**:
   - `C1_EV_06_PAYROLL` (`22,000,000 VND`, `kind=payroll`): **`all_applicable_rules_evaluated_no_hit`**, điểm `isolation_forest = 0.7720` (xếp hạng #1 ngoài luật). *Lưu ý kỹ thuật*: khoản lương này hợp lệ theo `E1/E2`, nhưng bị `Isolation Forest` đẩy lên hạng #1 do tỉ lệ `payroll` rất thấp (`2/42`) trong tập huấn luyện — minh họa rõ ML không thay thế xác minh chứng từ của người rà.
   - `C1_EV_08_ML_SECOND` (`68,421,900 VND`, `kind=vendor_payment`): **`all_applicable_rules_evaluated_no_hit`**, điểm `isolation_forest = 0.5888` (xếp hạng #2 ngoài luật) — khoản chi lớn lệch nền lịch sử, thiếu chứng từ `transaction_documents` và lệch bút toán kế toán (`journal_imbalance`), chưa kích hoạt luật cứng nào.

#### Doanh nghiệp `C002` (`ecod`, cutoff `2026-10-20T00:00:00+07:00`)

1. **Nhóm nền 35 luật (4 giao dịch — toàn bộ nằm ngoài `P1`)**:
   - `C2_EV_01_A6` (`7,500,000 VND`, `2026-10-02T10:00:00+07:00`): `rule35_alert` — trúng `A6` (thanh toán làm tròn vượt hóa đơn gốc). Nếu giữ baseline `P1` cũ sẽ chọn `0` ca này.
   - `C2_EV_02_B1` (`4,200,000 VND`, `2026-10-05T10:00:00+07:00`): `rule35_alert` — trúng `B1, B2` (tài khoản NCC trùng nhân viên).
   - `C2_EV_03_B2` (`4,500,000 VND`, `2026-10-06T10:00:00+07:00`): `rule35_alert` — trúng `B2` (điện thoại và địa chỉ NCC trùng nhân viên).
   - `C2_EV_04_E2` (`22,200,000 VND`, `kind=payroll`, `2026-10-07T10:00:00+07:00`): `rule35_alert` — trúng `E2` (chi lương định kỳ cho kỳ công sau ngày chấm dứt hợp đồng).
2. **Phần ML bổ sung vào 1 chỗ trống (`ml_filled_remaining_slots`)**:
   - `C2_EV_07_ML_CLEAN` (`175,642,300 VND`, `kind=vendor_payment`): **`all_applicable_rules_evaluated_no_hit`**, điểm `ecod = 30.7640` — giá trị chi đột biến, thiếu tài liệu `transaction_documents` và lệch cân đối định khoản, không kích hoạt luật nghiệp vụ nào.

## 3. Phân định rõ: đã chứng minh về mặt kỹ thuật vs cần người rà xác nhận

### Đã chứng minh bằng chạy thực nghiệm & kiểm thử tự động

1. Baseline **35 luật đầy đủ** thay thế thực sự cho baseline `P1`/4 luật cũ: trên `C002`, baseline cũ chọn `0/5` ca trong khi baseline 35 luật chọn `4/5` ca (`A6, B1, B2, E2`); kết quả luật giữ bất biến tuyệt đối khi có hoặc không gắn ML (`native_reference_sha256` và `rule_coverage` trùng khớp).
2. Chính sách `rules_first_fill/1.0.0` (ngân sách 5) được thực thi cứng: giữ đủ cụm đồng thời, hoãn cả cụm khi vượt phần chỗ trống còn lại (`deferred_rule_alerts`), không thêm ML khi đủ 5 chỗ (`budget_full_no_slots` với thông điệp `"không còn chỗ trong ngân sách"`), giữ nguyên danh sách 35 luật khi ML không khả dụng (`ml_unavailable`), và phân tách ML thêm trên nền luật sạch (`all_applicable_rules_evaluated_no_hit`) vs nền thiếu nguồn (`partial_rule_source_gap`).
3. Tách riêng hoàn toàn `D1–D6, F4` tại `scope_diagnostics`, gộp trùng `B5/E4`, loại toàn bộ 42 dòng `history_only` khỏi tập ứng viên, cô lập theo doanh nghiệp/phiếu (`SHARED_AUDIT_00`), và khóa bất biến kế hoạch trong `ComparisonStore` qua khởi động lại mà không tái lựa chọn khi lưu phản hồi `ReviewStore`.
4. Kiểm thử đường HTTP `POST`/`GET /api/v1/companies/<company>/analyses/<ana_...>/comparison` kiểm tra khóa kế hoạch, phân quyền `director` vs `accountant` (`403`), từ chối sai ngân sách/chính sách (`400`) và che điểm/artifact nhạy cảm (`raw_score`, `artifact_id`).

### Chưa thể kết luận nếu thiếu xác nhận từ người rà & dữ liệu thực

- **Chưa đo được precision/độ hữu ích thực tế**: vì kho `ReviewStore` khởi tạo sạch (`pending = 5/5`, `resolved = 0`), nên mọi chỉ số `accuracy`, `declared_precision_resolved`, `declared_useful_transactions` và `saved_connected_seconds` đang giữ `null`. Không tự bịa nhãn hoặc công rà.
- **Công rà tăng thêm (`35 luật + ML` so với `35 luật`)**: trong cấu hình C001/C002 này là `+2` phiếu ở `C001` và `+1` phiếu ở `C002` cần rà bổ sung; thời gian rà tăng thêm thực tế phụ thuộc thao tác kiểm tra đồng hồ `ReviewStore` của kiểm toán viên (và được quy đổi kiểu `shared_transaction_review_attribution_not_independent_arms`, không phải thí nghiệm mù đôi hai nhánh độc lập).
- **Giới hạn dữ liệu giả lập**: đây là mẫu đối chứng tổng hợp (`is_simulated=True`), cho thấy khả năng ML vừa bắt được ca lệch hồ sơ/định khoản chưa trúng luật (`C1_EV_08_ML_SECOND`, `C2_EV_07_ML_CLEAN`), vừa có thể đẩy giao dịch hiếm nhưng hợp lệ lên hạng cao (`C1_EV_06_PAYROLL`). Việc đánh giá giá trị nghiệp vụ thực sự đòi hỏi chạy trên mẫu dữ liệu thực và hoàn tất rà trên `ReviewStore`.

