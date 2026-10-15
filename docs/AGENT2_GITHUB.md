# Agent 2 trong Multi-Agent Finance

Mã nguồn được lấy từ workspace `agent22` ngày 15/10/2026. Tài liệu kiến trúc sẵn có của repo nằm tại [DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md](DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md).

| Đường dẫn | Nội dung |
| --- | --- |
| `sme_fraud/` | Bộ sinh dữ liệu, đặc trưng, luật, đồ thị, chính sách bằng chứng, đánh giá và API rà soát |
| `tests/` | Kiểm thử kế toán, luật, tính nhân quả, lịch sử đồ thị, nguồn bằng chứng và API |
| `review_ui/` | Giao diện HTML/CSS/JavaScript chạy cục bộ |
| `examples/` | Schema CSV chỉ chứa header và tiêu chí nghiệm thu mẫu |
| `reports/` | Tài liệu nghiệp vụ, audit, thay đổi luật và snapshot kết quả Markdown/JSON |
| `requirements*.txt` | Phụ thuộc và phiên bản benchmark |
| `agent2.md`, `road_map.md`, `rule_class_1.md`, `rule_gian_lan.md` | Thiết kế, lộ trình và đặc tả nghiệp vụ |

Dataset, model nhị phân, CSV/JSONL kết quả từng dòng, ZIP, SQLite, log, cache và thư viện cài sẵn được bỏ qua bằng `.gitignore`. Báo cáo lịch sử có thể nhắc tới các file này; cần sinh lại nếu muốn đối chiếu từng dòng hoặc mở giao diện rà soát.

## Cài đặt và kiểm thử

Dùng Python 3.10 trở lên. Ví dụ dưới đây chạy trong PowerShell tại thư mục repo và gọi trực tiếp Python của môi trường ảo.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force .runtime | Out-Null
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements-lock.txt` giữ các phiên bản của benchmark lịch sử; dùng file đó khi cần tái lập đúng môi trường tương thích.

## Chạy một kịch bản mới và mở giao diện

Các lệnh sau tạo bộ 100.000 quan sát ở tỷ lệ mô phỏng 0,3%, train IF và chạy bộ luật. Dùng thư mục đầu ra mới vì pipeline chủ động từ chối ghi đè kết quả có sẵn.

```powershell
.\.venv\Scripts\python.exe -m sme_fraud.generate --output data/sme_fraud_003 --rows 100000 --fraud-rate 0.003 --seed 42 --companies 5
.\.venv\Scripts\python.exe -m sme_fraud.validate --data data/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.evaluate --data data/sme_fraud_003 --output reports/local_if/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.run_rules --data data/sme_fraud_003 --output reports/local_rules/sme_fraud_003 --if-model reports/local_if/sme_fraud_003/isolation_forest.joblib
.\.venv\Scripts\python.exe -m sme_fraud.review_server --data-root data --reports-root reports/local_rules
```

Mở `http://127.0.0.1:8765`; dùng `Ctrl+C` để dừng server. Dữ liệu và các thư mục `reports/local*` được Git bỏ qua.

Ưu tiên và trạng thái nghiệp vụ hiện tại nằm tại [rule_audit_priorities.md](../reports/rule_audit_priorities.md), [bằng chứng nghĩa vụ chi](../reports/rule_payment_evidence.md), [lịch sử đồ thị](../reports/rule_graph_history.md) và [nguồn thẩm quyền](../reports/rule_authority_dormancy.md).
