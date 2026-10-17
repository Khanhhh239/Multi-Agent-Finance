# Agent 2 — nhánh agent2-Sang

Bản cập nhật của workspace `agent22` ngày 17/10/2026 được chuyển từ lần đẩy `f593a78` sang nhánh **`agent2-Sang`**. Nhánh giữ mã nguồn `sme_fraud/`, giao diện `review_ui/`, bộ test `tests/`, schema, mẫu nguồn và báo cáo của workspace.

Các thay đổi gồm bằng chứng nghĩa vụ chi và thẩm quyền theo lịch sử, định danh ngân hàng, đóng lô, ID hồ sơ, hợp đồng feature/model và tiếp nhận mẫu A2/A4. Xem [readiness](../reports/rule_readiness_recheck_20261016.md), [feature/model](../reports/rule_feature_model_sync.md), [A2/A4](../reports/rule_split_pattern_admission.md) và [README đầy đủ](../README.md).

## Cài đặt và kiểm thử

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force .runtime | Out-Null
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

`requirements-lock.txt` giữ phiên bản benchmark lịch sử. Đã chạy lại **373/373 test hồi quy đạt** trên nhánh đích; log nằm cục bộ trong `.runtime/github_move_agent2_sang_tests.log`.

## Chạy từ bản clone mới

```powershell
.\.venv\Scripts\python.exe -m sme_fraud.generate --output data/sme_fraud_003 --rows 100000 --fraud-rate 0.003 --seed 42 --companies 5
.\.venv\Scripts\python.exe -m sme_fraud.validate --data data/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.evaluate --data data/sme_fraud_003 --output reports/local_if/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.run_rules --data data/sme_fraud_003 --output reports/local_rules/sme_fraud_003 --if-model reports/local_if/sme_fraud_003/isolation_forest.joblib
.\.venv\Scripts\python.exe -m sme_fraud.review_server --data-root data --reports-root reports/local_rules
```

Mở `http://127.0.0.1:8765`. Dùng thư mục đầu ra mới vì pipeline từ chối ghi đè snapshot đã có.

Bản Git gồm mã nguồn, test, schema, CSV mẫu chỉ có header và snapshot Markdown/JSON. Dataset, model, runtime, cache, SQLite, phản hồi người dùng và kết quả chi tiết từng dòng được giữ cục bộ. Các chỉ số trong báo cáo là kết quả trên dữ liệu tổng hợp; trạng thái nghiệm thu vận hành nằm trong báo cáo readiness.
