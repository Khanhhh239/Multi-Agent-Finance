# Benchmark chung từ snapshot và model shadow đã duyệt

Đây là phần đầu của bước benchmark trong pipeline gốc: tạo ma trận kết quả trên
cùng nguồn/cutoff để kiểm tra các phương pháp trước khi chọn ensemble. Version
`agent2-pipeline-benchmark/0.1.0`, trạng thái `technical_only`.

## Đã nối

Backend đọc lần chạy shadow đã lưu trong kho server, dùng cùng snapshot và as_of
để gọi engine 35 luật và các adapter ML/thống kê/đồ thị hiện có. Ma trận giữ đủ
ứng viên trong `candidate_transaction_ids`; bản ghi chỉ làm lịch sử không tự
trở thành ứng viên. Mỗi dòng có ID/revision, các luật/nguồn còn thiếu, MethodScore,
căn cứ graph và điểm supervised shadow. Model thiếu giữ unavailable/null.

Model có giám sát là model đã train HE, nhận/giải mã và phê duyệt shadow tại DN.
Benchmark chỉ đọc điểm shadow đã lưu và chấm các nhánh local khác; không train
HE mới hoặc gửi dữ liệu rõ lên worker. Không nhận feature, điểm hoặc nhãn tự
khai từ trình duyệt.

Các phương án thử dùng chính sách đã chốt `rules_first_fill/1.0.0`, tối đa **5
giao dịch/phương án/DN**:

- Chỉ 35 luật.
- 35 luật + một model không nhãn được ghim theo DN.
- 35 luật + supervised shadow đã duyệt.

Luật giữ thứ tự/nhóm cảnh báo hiện có, ML chỉ bổ sung phần ngân sách còn trống.
Không trộn điểm raw của các model khác thang đo. Không tự đặt trọng số, percentile,
ngưỡng gian lận hoặc policy vụ sản xuất. Có nhiều model không nhãn thì phải chọn
`ml_method` tường minh. Model chưa ghim vẫn được báo thiếu, không tự fit.

Giao dịch đã thấy trong train/holdout supervised được đánh dấu và loại khỏi tất
cả phương án thử, vẫn hiện trong ma trận. Nếu một thành viên nhóm liên quan bị
loại thì cả nhóm không được so sánh như một phần nhóm đã cắt. Thiếu nguồn luật
được giữ riêng; ML bổ sung ở vùng đó chưa chứng minh luật bỏ sót.

Report ghim snapshot/checksum, cutoff, analysis/shadow hash, model/approval pins,
feature contract, mã nguồn benchmark/selection và `report_sha256`. Không chốt
precision/recall/thời gian rà vì chưa nối nhãn/phiếu rà vào báo cáo này. Kế hoạch
này là retrospective trên lần chạy đã có, chưa phải EvaluationPlan niêm phong
trước test theo spec05.

## API/CLI

API kỹ thuật chỉ cho **director** đúng doanh nghiệp:

`POST /agent2/api/v1/companies/{company}/pipeline-benchmarks`

```json
{"shadow_run_id":"shrun_1_REPLACE_WITH_SAVED_ID","ml_method":"isolation_forest"}
```

`ml_method` tùy chọn khi không có hoặc chỉ có một model. Body không được chứa
X, score, labels, tenant, role hoặc feature fingerprint tự khai. Dùng phiên Portal
hiện tại; endpoint dùng cùng manager đang mở, không nạp một DB/khóa thứ hai.

CLI lưu báo cáo tại doanh nghiệp:

```powershell
python agent2/scripts/benchmark_shadow_snapshot.py --config <benchmark-config.json> --token-file <portal-session-file> --shadow-run-id <saved-shadow-run-id> --output <new-private-report.json>
```

Config:

```json
{"portal_url":"http://127.0.0.1:8800","company_id":"C001","ml_method":"isolation_forest"}
```

Không đặt token trực tiếp lên argv hoặc gửi qua chat. File output mới để không
ghi đè báo cáo cũ. Chưa có nút benchmark mới trên giao diện; API/CLI cần backend
và Portal nạp code/allowlist mới trước khi dùng trên phiên live.

## Giới hạn đang giữ

- Engine 35 luật hiện yêu cầu cutoff trùng `source.as_of` đã khóa. Shadow hỗ trợ
  replay sớm hơn, nhưng benchmark không tự đổi cutoff để ghép hai kết quả khác
  kỳ; trả `RULE_CUTOFF_MISMATCH`. Tạo nguồn phù hợp trước khi so sánh.
- Đầu vào hiện cần profile nguồn đầy đủ `agent2-rule-snapshot/1.0.0`. Canonical
  ít nguồn chưa có đủ baseline35 cho báo cáo này.
- Benchmark per-transaction B=5 khác budget vụ sản xuất D-06 còn chưa chốt.
- Chưa chọn ensemble/fallback qua validation, chưa release gate chất lượng,
  case delivery/budget ledger, bundle rollback hoặc xác nhận hiệu quả trên DN thật.
