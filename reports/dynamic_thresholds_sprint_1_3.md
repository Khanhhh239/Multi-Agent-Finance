# Sprint 1.3 — Ngưỡng động theo doanh nghiệp và tài khoản

Ngày cập nhật: 17/10/2026. Đã bổ sung module tính phân phối, tích hợp baseline A5 và job xuất/cập nhật bảng tham số riêng cho từng công ty. **520/520 kiểm thử đạt, gồm 24 kiểm thử mới**. Kết quả tại [current.json](../.runtime/dynamic_thresholds_20261017/current.json), [log đầy đủ](../.runtime/dynamic_thresholds_20261017/current.log).

## Đối chiếu đầu việc

| Yêu cầu | Triển khai |
| --- | --- |
| Phân phối riêng theo doanh nghiệp và tài khoản chi phí | Khóa thống kê gồm `company_id`, **nguyên mã tài khoản chi tiết**, `measurement`, `family`. Không gộp 641/642 hoặc 6421/6422; không mượn phân phối công ty khác. |
| P95/P99 hoặc μ+kσ | Mỗi dòng tham số có cả ba thống kê; `method` chọn ngưỡng áp dụng. Mặc định P99; σ là độ lệch chuẩn mẫu (`ddof=1`), k mặc định 3. |
| Rolling 30/60/90 ngày | Xuất đồng thời ba cửa sổ; `dynamic_window_days` chọn cửa sổ đánh giá. Mặc định 90 ngày. |
| Chu kỳ chốt lương/thanh toán công nợ | Phân phối có điều kiện theo ngày trong tháng ±2 ngày; thêm ngữ cảnh cách cuối tháng 0/1/2 ngày ±2. Tách nhóm payroll/payables/general_expense. |
| Bảng tham số tự cập nhật theo công ty | CSV/JSON chung, CSV riêng từng công ty; CLI một lô hoặc `--watch`. Snapshot có checksum, khóa writer và con trỏ `latest.json` công bố nguyên tử. |

## File nên đánh dấu và đọc theo thứ tự

1. [threshold_sources.py](../sme_fraud/threshold_sources.py): xác định **số tiền nào được đem so sánh**, lấy từ bút toán hay dòng tiền; đây là phần cần đọc trước công thức.
2. [dynamic_thresholds.py](../sme_fraud/dynamic_thresholds.py): `ThresholdPolicy`, `advance`, `parameters_for`, `evaluate`, `parameter_table`; cửa sổ, chu kỳ, điều kiện đủ mẫu và bằng chứng.
3. [rules.py](../sme_fraud/rules.py): cấu hình mặc định, `score_rules`, nhánh A5 và metadata coverage. Nhánh A5 mới dùng `rolling_account`; có thể ghim `log_mad`/`raw` khi chạy lại chính sách cũ.
4. [sync_dynamic_thresholds.py](../sme_fraud/sync_dynamic_thresholds.py): đọc nguồn đủ, kiểm manifest, tính bảng, quản lý phiên bản và cập nhật định kỳ.
5. [threshold_artifacts.py](../sme_fraud/threshold_artifacts.py), [config mẫu](../examples/dynamic_thresholds/config.json): hợp đồng file và các tham số vận hành. `run_rules.py` và `sync_feature_model.py` cũng xuất bảng khi baseline mới được bật.
6. [test_dynamic_thresholds.py](../tests/test_dynamic_thresholds.py), [test_dynamic_threshold_sources.py](../tests/test_dynamic_threshold_sources.py), [test_dynamic_threshold_sync.py](../tests/test_dynamic_threshold_sync.py): ví dụ kiểm chứng phép tính, nguồn kế toán, thời gian và cập nhật.

## Ý nghĩa kế toán của một mẫu

`expense_debit` là **tổng Nợ dương trên một chứng từ và một tài khoản chi phí**, không lấy tổng trị giá hóa đơn gồm VAT. Đọc các tài khoản bắt đầu bằng 6, 8 hoặc 154; loại tài sản/VAT và không bù trừ Có với Nợ. Giữ nguyên tiểu khoản. Chứng từ ghi nhận chi phí độc lập như trích lương/ghi nhận hóa đơn được dùng làm lịch sử, kể cả không gắn một giao dịch thanh toán.

`cash_outflow` là khoản thanh toán VND có Có 111/112 và kênh bank/cash. Theo dõi riêng theo tài khoản Nợ, gồm 331 trả NCC và 334 trả lương; khoản tất toán này **không trở thành lần ghi nhận chi phí thứ hai**. Với giao dịch có Nợ chi phí và dòng tiền cùng lúc, A5 ưu tiên đo lường chi phí; hai thang đo không bị gộp vào cùng phân phối.

Nếu toàn bộ nguồn không có journal_lines, dùng `transaction_amount` riêng cho tài khoản chi phí trên giao dịch; tên đo lường thể hiện rõ hạn chế này. Khi đã cung cấp ledger, không tự thay các chứng từ chi phí còn thiếu bằng trị giá gộp. Nguồn cần có đầy đủ giao dịch/chứng từ cho phạm vi công ty; chưa tự đối soát tính đầy đủ sổ cái. Không tính thống kê từ SQLite chỉ chứa các hồ sơ cảnh báo vì đó là mẫu đã được chọn lọc.

## Thời gian, công thức và chu kỳ

Mọi thời gian phải có múi giờ và được đổi về +07:00. `known_at = max(event_at, observed_at)`; lịch sử đánh giá chỉ chứa mẫu **đã biết trước thời điểm đánh giá**, trong cửa sổ `[cutoff − N ngày, cutoff)`. Giao dịch cùng timestamp không đi vào baseline của nhau; dữ liệu tương lai/đến muộn không sửa bằng chứng cũ. Với bảng xuất ở cutoff, biên phải bao gồm cutoff để phục vụ **lần đánh giá tiếp theo**. Muốn phát lại quá khứ phải dùng instance mới và `evaluate`, không áp bảng cuối kỳ cho giao dịch đầu kỳ.

P95/P99 dùng nội suy tuyến tính. μ là trung bình số tiền VND, σ mẫu có `ddof=1`; áp ngưỡng một phía `amount > threshold`, bằng ngưỡng không cảnh báo. Loại sai số nội suy nhỏ hơn một phần triệu đồng ở ranh giới số nguyên. Đối chiếu định nghĩa: [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html), [NumPy std](https://numpy.org/doc/stable/reference/generated/numpy.std.html). Không giả định dữ liệu có phân phối chuẩn và không diễn giải μ+3σ thành xác suất gian lận.

Ngữ cảnh tháng chỉ được dùng khi có tối thiểu 20 mẫu trong cửa sổ đang chọn **và** đủ hỗ trợ từ ít nhất 3 tháng trong lịch sử 180 ngày. Hỗ trợ chu kỳ được chốt theo dữ liệu trước 00:00 mỗi ngày; số tiền phân phối vẫn tính trên cửa sổ trượt 30/60/90. Ngày 31 được đối chiếu với ngày cuối của tháng ngắn; khoảng cách tới cuối tháng xử lý cả tháng 28/29 ngày. Nếu cả hai ngữ cảnh đủ mẫu, chọn theo số tháng/số mẫu lịch sử, rồi số mẫu cửa sổ; cuối tháng thắng khi hòa. Không dùng số tiền hiện tại hoặc nhãn để chọn ngữ cảnh có lợi hơn.

Thiếu lịch sử chu kỳ thì dùng `all_days` của **chính khóa thống kê đó**; thiếu cả lịch sử chung thì `threshold_vnd=null`, `insufficient_history` và không phát tín hiệu. Các dòng theo pha ghi cả `threshold_vnd` riêng và `effective_threshold_vnd`/`fallback_basis`; không được thay null bằng 0. Tần suất ít có thể cần chỉnh cấu hình sau khi đánh giá nguồn thật. Cơ chế này học tính lặp theo lịch, chưa đọc lịch chốt lương/hạn thanh toán hợp đồng hoặc dịch ngày nghỉ từ ERP.

## Cách chạy và đọc bảng

Một lô tái lập từ nguồn train/validation hiện có:

```powershell
python -B -m sme_fraud.sync_dynamic_thresholds --data data/feature_model_sync_20261017/sme_fraud_003 --output .runtime/dynamic_thresholds/sme_fraud_003 --config examples/dynamic_thresholds/config.json --as-of 2025-06-30T23:59:59+07:00
```

Cập nhật mỗi giờ, cutoff theo đồng hồ Việt Nam:

```powershell
python -B -m sme_fraud.sync_dynamic_thresholds --data data/sme_real_export --output .runtime/dynamic_thresholds/sme_real --config examples/dynamic_thresholds/config.json --watch --interval-seconds 3600
```

[run_dynamic_threshold_sync.ps1](../run_dynamic_threshold_sync.ps1) hỗ trợ `-PythonExecutable`, `-Data`, `-Output`, `-Config`, `-Once`, `-AsOf`, `-IntervalSeconds`. Có thể dùng `-Once` dưới scheduler của hệ thống. `--watch` đọc lại config và dữ liệu mỗi lô; bên xuất ERP phải công bố bộ nguồn/manifest nhất quán. Job kiểm checksum các file được phép đọc; không nạp features, labels, splits hay model.

```python
from sme_fraud.sync_dynamic_thresholds import load_snapshot
saved = load_snapshot(".runtime/dynamic_thresholds/sme_real")
rows = saved["parameters"]
company_csv = saved["company_files"]["C001"]
folder = "snapshots/" + saved["fingerprint"]
```

`load_snapshot` kiểm commit và hash mọi file của lô. CSV có một dòng cho mỗi khóa × cửa sổ × pha: mặc định 35 pha (all_days + 31 ngày + 3 khoảng cuối tháng), 105 dòng/khóa. Các cột chính gồm `as_of`, `window_start`, `sample_count`, `mean_vnd`, `std_vnd`, `p95_vnd`, `p99_vnd`, `mean_plus_k_std_vnd`, `method`, `threshold_vnd`, `status`, `parameter_id`, `history_sha256` và số tháng hỗ trợ chu kỳ. Khi tắt cycle, chỉ còn ba dòng/khóa.

Snapshot giữ hash nguồn, manifest, code và policy; tên CSV riêng dùng hash company_id để tránh định danh trở thành đường dẫn. Chạy cùng nguồn/cấu hình/cutoff không tạo phiên bản mới. Lô lỗi giữ con trỏ trước; watermark không được lùi. Snapshot cũ giữ lại. Nếu tiến trình bị kill cứng, cần xác minh writer đã dừng trước khi gỡ khóa `.threshold-sync.lock` còn sót.

## Bản mẫu và phạm vi nghiệm thu

[Con trỏ bảng mẫu](dynamic_thresholds_20261017/latest.json), [đối chiếu độc lập và danh sách CSV theo công ty](../.runtime/dynamic_thresholds_20261017/demo.json). Nguồn `data/feature_model_sync_20261017/sme_fraud_003`, cutoff 30/06/2025 23:59:59 +07:00: 5 công ty, 71.898 quan sát đã biết, 7.875 dòng tham số; 2.229 dòng đủ điều kiện, 5.646 dòng thiếu mẫu. Đã đối chiếu độc lập 225 phân phối all_days và hash nguồn trước/sau. Số dòng tham số không phải số cảnh báo hoặc số vụ gian lận.

Baseline A5 mặc định mới thay log/MAD bằng rolling-account; vẫn giữ phạm vi **số tiền tròn**, điểm ngữ cảnh và yêu cầu bằng chứng độc lập của A5. API module `evaluate` so được cả số tiền không tròn. Không dùng phân vị để thay hạn mức pháp lý hay thẩm quyền phê duyệt. Chưa chấm lại benchmark lớn, chỉnh trọng số, huấn luyện IF hoặc ghi đè hồ sơ vận hành/snapshot cũ trong lượt này.

Đã nghiệm thu kỹ thuật trên dữ liệu mô phỏng. P99/90 ngày/20 mẫu/k=3 là cấu hình khởi đầu, chưa được hiệu chỉnh và nghiệm thu bằng nguồn SME thật. Đã có khả năng chạy định kỳ; **chưa bật tiến trình nền hoặc đăng ký Windows Scheduled Task**. Bước tiếp theo là nối nguồn sổ cái đầy đủ, kiểm tra tài khoản/nhóm nghiệp vụ và lựa chọn cấu hình trên train/validation trước khi vận hành.
