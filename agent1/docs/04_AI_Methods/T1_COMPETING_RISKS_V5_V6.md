# T1 v5/v6 — Phương pháp competing risks

> **Phân biệt phiên bản khi đọc 06/11/2026:** v6 trong bảng phương pháp này là bản gốc 64 feature snapshot khóa 01/11. Bản ngành + ledger ngày 05/11 có 93 feature và [protocol riêng](T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md). Không gán cash head 64 feature hoặc các điểm benchmark cũ cho bản mới.

**Cập nhật 01/11/2026.** Tài liệu này gộp phần phương pháp của hai bản tổng hợp v5/v6. Kết quả, bảng benchmark và hash của từng lần chạy đọc tại [báo cáo v5 ngày 28/10](../03_Evaluation/T1_V5_COMPETING_RISKS_2026-10-28.md) và [báo cáo v6 ngày 01/11](../03_Evaluation/T1_V6_COMPETING_RISKS_2026-11-01.md).

V5/v6 là các thử nghiệm riêng trên cohort synthetic v4. Chúng đã train model mới từ đầu; chưa thay model v4 hoặc model trong dịch vụ. V5 học trực tiếp competing risks; v6 giữ cấu trúc này, thêm đặc trưng, thử hiệu chỉnh xác suất và thêm model tiền thu.

## 1. Mô hình hazard đa lớp

Tại tuần k, với điều kiện hóa đơn còn mở ở đầu tuần, v5 dự báo bằng LightGBM `objective=multiclass`, `num_class=3` với softmax:

```text
h_open(k) + h_paid(k) + h_writeoff(k) = 1
```

Đây là một mô hình ba lớp học chung, không ghép hazard trả đủ T1 với xác suất cure T2. `open` nghĩa là không có sự kiện trong một tuần được quan sát đầy đủ.

Với S là xác suất vẫn mở và F_j là CIF của nguyên nhân đóng j:

```text
S(0) = 1; F_j(0) = 0
F_j(k) = F_j(k-1) + S(k-1) × h_j(k)
S(k)   = S(k-1) × h_open(k)
S(k) + Σ_j F_j(k) = 1
```

V5 có hai nguyên nhân đóng: paid và write-off. Core v6 thêm credit-note-only, nhưng lần train hiện có không có nhãn này: model chỉ học ba lớp hoạt động rồi ánh xạ sang vector bốn trạng thái, đặt xác suất credit-note-only bằng 0. Metadata ghi `credit_note_risk_learned=false`; hỗ trợ trong core chưa chứng minh đã học được rủi ro này.

Cả hai model học 53 tuần. Với mốc ngày giữa tuần, code dùng chuyển tiếp theo tỷ phần ngày, giả định hazard không đổi trong tuần. V4 chỉ học 13 tuần rồi ngoại suy bằng hazard trung bình bốn tuần cuối; đọc [chẩn đoán survival v4](../03_Evaluation/T1_V4_PAYMENT_SURVIVAL_DIAGNOSTIC_2026-10-28.md) để biết giới hạn của đối chứng đó.

Nguồn: [core v5](../../experiments/t1_competing_v5/core.py), [core v6](../../experiments/t1_competing_v6/core.py).

## 2. Sự kiện, event table và weekly risk set

Đơn vị đầu vào là một `(world, invoice_id, cutoff)`, với hóa đơn còn mở tại ngày cắt:

| Trường hợp | Chính sách |
|---|---|
| Paid | Tiền thu đủ khoản phải thu sau credit note đã có ngày; `paid_after_credit_note` vẫn thuộc paid |
| Write-off | Đóng tại `writeoff_date`; không mô hình hóa thu hồi sau đó |
| Credit-note-only | V5 báo lỗi; core v6 có nguyên nhân đóng riêng |
| Censoring | Không quan sát được sự kiện trước hoặc tại cuối cửa sổ nhãn |

Các hàm gán nhãn từ chối hóa đơn có nhiều ngày kết thúc mâu thuẫn, sự kiện trước hoặc đúng ngày cắt, hoặc ngày cắt sau cuối cửa sổ nhãn. Ngày kết thúc tương lai và `closure_type` chỉ được gắn làm nhãn sau bước dựng feature as-of.

V5 dùng `label_first_event()` rồi `expand_weekly()`; v6 dùng `label_events()` rồi `expand_weekly()`. Các trường nội bộ là:

| Trường | Ý nghĩa |
|---|---|
| `cutoff` | Ngày snapshot |
| `obs_days` | Số ngày từ snapshot đến cuối cửa sổ quan sát hành chính |
| `time_days` | Số ngày đến sự kiện đã quan sát hoặc censor |
| `cause` | Nguyên nhân đóng; 0 khi không quan sát được sự kiện trong cửa sổ nhãn |

`cause=0` ở bảng snapshot biểu diễn trường hợp bị kiểm duyệt. Nhãn `open=0` ở bảng tuần biểu diễn một tuần đầy đủ không có sự kiện. Hai trường dùng chung mã số nhưng có ý nghĩa theo đơn vị quan sát khác nhau.

Với tuần `(left, right]`, chỉ tạo dòng khi:

```text
time_days > left và obs_days >= right
```

Tuần có sự kiện nhận nhãn paid/write-off/credit-note-only tương ứng; sau sự kiện không còn dòng. Nếu write-off trong tuần 8 thì tạo tuần 1–7 open, tuần 8 write-off. Nếu censor giữa tuần 8 thì chỉ tạo tuần 1–7. Chính sách bỏ tuần thiếu quan sát áp dụng cả cho hàng có sự kiện trong tuần đó, tránh chỉ giữ lại các sự kiện đã biết.

**Giới hạn của bước chuẩn bị dữ liệu hiện tại:** [event table v5](../../outputs/data/v5_competing_risks_53w_20261028/event_table.parquet) được xuất riêng để audit bằng [materialize_events.py](../../experiments/t1_competing_v5/materialize_events.py); train vẫn tự dựng frame trước khi mở rộng, chưa đọc bảng này làm đầu vào cố định. V6 lưu frame có nhãn vào cache từng World. Chưa có schema chung với `event_date`, `event_type`, `observed_until` tường minh. Logic risk set trong các thử nghiệm đã sửa; pipeline v4 vẫn dùng nhãn trả đủ cũ.

## 3. Khác biệt giữa v5 và v6

| Thành phần | V5 | V6 |
|---|---|---|
| Feature snapshot | 46 | 64, thêm 18 biến as-of |
| Feature hazard theo tuần | 46 + 7 | 64 + 7 |
| Snapshot fit | 100.000, tối đa 25.000/World | 200.000, tối đa 50.000/World |
| Lấy mẫu | Ngẫu nhiên theo World | Quota doanh nghiệp, rồi bù phần còn thiếu; không phân tầng theo nhãn tương lai |
| Công ty trong mỗi World train | Dùng cho fit model | 32 fit model, 4 fit calibration, 4 chọn calibration |
| Số vòng hazard | 120 | 160 |
| Feature/bagging fraction | 0.8 / 0.8 | 0.85 / 0.85 |
| `lambda_l2` | 5.0 | 8.0 |
| Calibration | Đo ECE, không fit hậu xử lý | Fit temperature/bias và chọn trên công ty nguồn tách riêng |
| Tiền thu từng phần | Chưa có model riêng | Cash head 120 vòng |
| Phân vị cuối kỳ | Chính sách trong protocol; chưa có batch riêng | Xuất Q10/Q50/Q90 có trạng thái |

Cả hai dùng `learning_rate=0.05`, `num_leaves=31`, `min_data_in_leaf=100`, `bagging_freq=1` và bốn luồng. V5 dùng seed gốc 17; v6 dùng `20261101`, `deterministic=true`, `force_col_wise=true`.

Snapshot fit thực tế từ 01/04/2019–19/06/2023, stride 28 ngày; protocol đặt ngày cuối tối đa 25/06/2023. Nhãn train chốt 01/07/2024, đủ 53 tuần theo dõi. Cả hai giữ vai trò bốn World train/hai validation/hai test của [cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json). V6 chia công ty nguồn theo hash cố định; nhóm calibration lấy anchor đầu tiên đủ điều kiện từ 03/01/2022.

Nguồn: [protocol v5](../../experiments/t1_competing_v5/protocol.json), [protocol v6](../../experiments/t1_competing_v6/protocol.json), [train v5](../../outputs/data/v5_competing_risks_53w_20261028/train.json), [train v6](../../outputs/data/t1_competing_v6_20261101/train.json).

## 4. Feature và hiệu chỉnh riêng của v6

Bảy biến tuần dùng chung là `k`, `dtd_k`, `due_in_k`, `bd_in_k`, `tet_in_k`, `payrun_in_k`, `promised_in_k`. Chúng chỉ dùng thông tin lịch biết được tại cutoff; feature lịch sử không được cập nhật bằng giao dịch tương lai.

18 feature v6 bổ sung trong [features.py](../../experiments/t1_competing_v6/features.py):

| Nhóm | Feature |
|---|---|
| Lịch sử xóa nợ khách hàng | `c_closed_n_asof`, `c_writeoff_n_asof`, `c_writeoff_rate_eb_v6`, `c_writeoff_180d_n` |
| Rủi ro doanh nghiệp bán | `f_writeoff_rate_asof`, `f_writeoff_180d_rate` |
| Cơ cấu dư nợ | `c_overdue30_amount_share`, `c_overdue60_amount_share`, `c_overdue90_amount_share`, `f_overdue90_amount_share`, `c_open_amount_rel_v6` |
| Thu tiền trên hóa đơn | `i_payment_count_asof`, `i_days_since_receipt`, `i_receipt_frac_28d`, `i_receipt_frac_90d`, `i_has_receipt` |
| Điều chỉnh và dư nợ | `i_credit_frac_known`, `i_remaining_frac` |

Các lần thu, credit note và write-off được lọc theo thời điểm biết được. Không dùng cờ nợ xấu tương lai, biến ẩn máy phát hay số lần trả cuối kỳ. Whitelist dùng chung v4/v5 được giữ nguyên.

Bộ [calibration v6](../../experiments/t1_competing_v6/calibration.py) fit temperature/bias bằng log loss có regularization trên risk set của các công ty nguồn dành riêng, theo dải tuần 1–4, 5–13, 14–26, 27–53:

```text
p_mới = softmax(log(p_gốc) / temperature + bias)
```

Bộ chọn chỉ chấp nhận nếu Brier chung trung bình trên các World/mốc nguồn giảm và Brier paid 28/91 ngày không xấu quá 2% ở từng World nguồn. Lần chạy hiện tại chọn identity; đọc [calibration.json](../../outputs/data/t1_competing_v6_20261101/calibration.json) và báo cáo v6. Validation/test không tham gia lựa chọn.

Hiệu chỉnh xác suất này không ước lượng hệ số truyền kinh tế từ shock sang thanh toán. V5/v6 giữ giả định shock của máy phát v4; chưa hiệu chỉnh chúng bằng ledger SME và chuỗi kinh tế độc lập.

## 5. Tiền thu và phân vị

Cash head v6 là LightGBM `regression_l2`, nhận 64 feature snapshot cùng `horizon_days`, học riêng tại 28/91/180/365 ngày:

```text
y(h) = clip(tiền thực thu trong (cutoff, cutoff+h] / dư nợ tại cutoff, 0, 1)
tiền thu dự báo(h) = tỷ lệ dự báo(h) × dư nợ tại cutoff
```

Model không nhận xác suất paid làm feature. Ràng buộc theo chân trời và bước xuất giữ tiền thu tích lũy không giảm, không vượt dư nợ. Cash head hiện chỉ hỗ trợ cohort VND không có điều chỉnh FX.

Đối chứng tiền thu là proxy `dư nợ × P_v5(paid trước h)`. Phép so sánh này chưa đánh giá toàn bộ T6. Hai đơn vị WAPE khác nhau:

```text
WAPE hóa đơn = Σ_i |dự báo_i − thực thu_i| / Σ_i thực thu_i
WAPE công ty = Σ_f |Σ_i∈f dự báo_i − Σ_i∈f thực thu_i| / Σ_i thực thu_i
```

Gộp nhiều World dùng trọng số tổng tiền thực thu. Sai số có thể triệt tiêu trong từng công ty nên không tráo đổi hai metric.

Q10/Q50/Q90 là nghịch đảo CIF paid vô điều kiện. V6 xuất null kèm `not_reached_by_365` khi chưa đạt ngưỡng trong 365 ngày. V5 quy định chính sách chưa đạt trong protocol nhưng chưa có batch phân vị cuối kỳ riêng. Không gán ngày 365 thành ngày trả, ngoại suy ngoài chân trời hoặc suy ra chắc chắn không bao giờ trả từ trạng thái chưa đạt.

## 6. Đọc benchmark và tái lập

| Nguồn | Dùng để đọc |
|---|---|
| [Báo cáo v5](../03_Evaluation/T1_V5_COMPETING_RISKS_2026-10-28.md) | P0–P4, event table, Aalen–Johansen, so sánh v4/v5 và trường hợp chưa đạt |
| [Báo cáo v6](../03_Evaluation/T1_V6_COMPETING_RISKS_2026-11-01.md) | Xác suất, cash head, bootstrap, subgroup, rolling, inference và ca chưa đạt |
| [Quick start v5](../../experiments/t1_competing_v5/README.md) / [v6](../../experiments/t1_competing_v6/README.md) | Lệnh chạy, stage và môi trường |

Brier nhiều trạng thái là trung bình tổng bình phương sai số với nhãn one-hot, không chia thêm cho số trạng thái. ECE dùng tối đa 10 bin gần bằng số lượng trong từng World. Gap là xác suất dự báo trung bình trừ tần suất quan sát. Các bảng gộp xác suất dùng trọng số số hóa đơn của từng World; ECE gộp là trung bình ECE từng World, không chia bin lại trên toàn tập.

Aalen–Johansen trong benchmark v5 mô tả CIF quan sát trên holdout; với đủ theo dõi, nó trùng tần suất sự kiện. Baseline tần suất của v6 được fit riêng từ anchor train. Đối chứng v4 giữ xác suất paid, đặt các cause đóng khác bằng 0.

Benchmark chính dùng anchor đủ theo dõi dài hạn. V6 còn có bootstrap ghép cặp theo công ty, hai ngày cắt rolling và hai seed fresh cùng máy phát/họ shock. Các World cũ đã được xem trong phát triển nên chỉ là chẩn đoán; fresh seed chưa thay cho ledger thật hoặc một họ shock mới. Chưa kiểm IPCW trên cohort gần hiện tại bị kiểm duyệt mạnh, CI qua nhiều World hay xác suất ngoài 365 ngày.

V5/v6 đồng thời đổi nhiều thành phần; chưa có ablation quy mức cải thiện cho riêng feature, lấy mẫu hoặc số vòng. Model tiền thu chưa tốt đồng đều. Các runner kiểm hash và từ chối ghi đè artifact khác cấu hình/mã đã khóa; giữ protocol, manifest, model, source snapshot và báo cáo có hash. Các kết quả nghiên cứu không thay trạng thái [cổng sản phẩm](../03_Evaluation/GATES_CURRENT.md).
