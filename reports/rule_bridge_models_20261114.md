# Model cho bridge nguồn đầy đủ đã được ghim — 14/11/2026

**Đã chuẩn bị và kích hoạt cấu hình local cho C001/C002.** Model cũ có contract
canonical không bị sửa hoặc gắn lại nhãn tương thích. Thêm bốn artifact mới:

| DN | ML | Thống kê | Kết quả trên batch thử |
|---|---|---|---|
| C001 | Isolation Forest | RobustZ | 5/5 dòng có kết quả cả hai nhánh |
| C002 | ECOD | RobustZ | 5/5 dòng có kết quả cả hai nhánh |

Model dùng contract `rule-snapshot-point-in-time/1.0.0`, cùng thứ tự 33 cột,
khác fingerprint canonical. Từng DN fit riêng 32 dòng lịch sử, 8 dòng reference
và đánh giá 5 giao dịch mới, tách ID và cả event/known-time. Dữ liệu train có
trước kỳ đánh giá. Artifact được tạo hiện tại ở chế độ **backtest**, không giả
đã triển khai model tại thời điểm lịch sử 2025.

## Chuẩn bị và kích hoạt

Producer cố định cho nguồn mô phỏng C001/C002; không nhận nguồn thật hoặc
company/tenant tùy ý. Portal access_file thực tế được đọc từ config và kiểm
grants trước khi chuẩn bị, kiểm lại trong thao tác và lúc kích hoạt. Operator
offline có service context riêng cho demo, không cấp model.fit/director cho
tài khoản Portal. Không có endpoint fit mới hoặc nhận pickle từ trình duyệt.

Fit chạy bằng method_jobs/MethodStore, ngoài request phân tích. Chọn 33 cột,
minimum_history=20 là thiết lập kỹ thuật demo; policy median_flags học từ train.
8 cột structurally unmapped giữ null/mask và được loại cố định khi all-null ở
train, không suy hóa đơn/phân bổ/hạn mức phê duyệt từ header giao dịch.

Đã backup SQLite nhất quán và file local-analysis-bindings trước khi append.
Kiểm chứng candidate bindings xong mới thay file bằng atomic replace có lock,
kiểm hash cấu hình/quyền chưa đổi. Giữ các binding tenant/DN khác. Retry kích
hoạt cùng receipt chỉ kiểm lại, không fit hoặc tạo model mới.

`AnalysisResources` đọc pins ở mỗi lượt chạy, nên thay binding có hiệu lực cho
request sau mà không cần restart Portal. Các artifact ID được ghim tường minh;
không lookup latest hoặc vô hiệu hóa gate contract. Hai đường HE giữ nguyên.

## Kiểm chứng đã chạy

- 84 test backend/bridge/cutoff/API/model job đạt; bốn test setup/kích hoạt
  chạy lại sau bổ sung idempotent activation đều đạt (không cộng overlap thành88).
- Candidate và bindings Portal thật đều cho 5/5 ML + 5/5 thống kê mỗi DN;
  lệnh check ở process Python mới đọc lại cùng artifact/snapshot/analysis IDs.
- Chrome qua backend thử với **model DB và binding đang dùng cho Portal**, bản
  sao snapshot SQLite: 4 bước hai DN đạt, không lỗi JS. Thấy đủ 5 dòng có điểm
  và reload giữ cùng snapshot/as_of/analysis ID. Không dùng đăng nhập live.
- 4 model cũ không đổi manifest/payload hash; 14 snapshot cũ không đổi checksum.
  Tổng model tăng 4 → 8; thêm đúng 4 snapshot (train/evaluation mỗi DN).
- 6 file config/quyền/HE pins/khóa được đối chiếu không đổi. Trong cấu hình đang
  chạy, chỉ file local-analysis-bindings được đổi để kích hoạt.

Phát hiện và sửa thêm reload snapshot chia sẻ: snapshot thuộc DN đọc được,
nhưng report của import gốc thuộc operator. UI giữ quyền draft như cũ; khi
report 403/404, đọc cutoff từ snapshot data đã kiểm checksum qua endpoint đọc
có cùng scope. Test xác nhận accountant vẫn không đọc report operator (404),
nhưng khôi phục được snapshot/ML. Không nâng quyền để cho test qua.

Nguồn mẫu và [hướng dẫn thử](../agent2/examples/rule_bridge_models/README.md).
Các template ít nguồn/khác kỳ vẫn có thể unavailable hoặc điểm không có giá
trị nghiệp vụ; không coi 5/5 demo tính được là độ chính xác gian lận.

## Phạm vi còn giới hạn

Các model mới xử lý tại DN, `he_execution=false`; không HE IF/ECOD/33 feature.
Không đổi ngân sách/trọng số/mandatory routing hoặc đưa kết luận vào queue.
Các điểm là empirical midrank với reference nhỏ, chưa calibration xác suất.
Muốn dùng cho doanh nghiệp thật cần nguồn và fit/reference/đánh giá nghiệp vụ
riêng, không dùng bộ demo này làm bằng chứng accuracy.

Lượt này đã kích hoạt file cấu hình thật; kiểm tra UI dùng backend riêng để
không thay quyền hoặc tạo giao dịch/job kiểm thử trên Portal live. Chưa thực
hiện lại quy trình đăng nhập người dùng trên Portal live và không push Git.

## Vận hành và rollback

Private preparation/backup:
`agent2/.runtime/he-company-demo/enterprise/rule-bridge-models-20261114/`.
Giữ nguyên model/snapshot/phiên cũ. Nếu cần rollback pins, đối chiếu cấu hình
chưa có cập nhật mới rồi khôi phục backup analysis-bindings.json; không restore
DB cũ vì sẽ mất phát sinh. Không xóa artifact chỉ vì đổi model được chọn.

Kiểm lại, không fit:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_rule_bridge_models.py check --output agent2/.runtime/he-company-demo/enterprise/rule-bridge-models-20261114
```

`prepare` cần output mới và chỉ dùng bộ mô phỏng đã chốt; `activate` yêu cầu
receipt hợp lệ, đúng quyền/cấu hình. Không dùng lệnh chuẩn bị lại trong lúc chấm.
Backup DB/model/config private không đưa lên Git; evidence công khai chỉ lấy
báo cáo/mẫu mô phỏng và screenshot đã xóa credential.
