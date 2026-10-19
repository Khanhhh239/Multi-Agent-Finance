# Cập nhật bộ luật SME Fraud — 17/10/2026

Bộ luật `sme_fraud/`, UI `review_ui/`, test `tests/`, schema và báo cáo được đồng bộ từ workspace `agent22` vào nhánh `agent2-Khanh`. Pipeline `agent2/`, bộ tài liệu theo vai trò, script, model và kết quả đã có trên nhánh tiếp tục được giữ lại. Biến thể benchmark `Rules+Graph gated by IF` cũng được giữ trong `sme_fraud.run_rules`.

Adapter kế toán v4 đăng ký năm loại giao dịch mở rộng vào lớp kiểm tra nguồn, giữ nguyên `generate.PAIRS` và hợp đồng cột feature. Fixture callback B7 của bộ test cũ được bổ sung mã ngân hàng theo định danh hiện tại. Có kiểm thử từ chối loại giao dịch lạ và cờ nguồn sai sau khi cài adapter.

## Những phần mới

- Kiểm tra P1, lịch sử người ký/thẩm quyền, kiểm tra nguồn ngoại lệ và định danh ngân hàng.
- Đóng lô, ID cụm/hồ sơ ổn định, đối chiếu split/merge và migration trạng thái rà soát.
- Hợp đồng feature/model có provenance, runner dựng lại feature và đánh giá train/validation.
- Tiếp nhận riêng mẫu chia nhỏ A2/A4 vào hàng đợi mà vẫn giữ nguyên điểm và hard trigger.

Xem [readiness hiện tại](../reports/rule_readiness_recheck_20261016.md), [đồng bộ feature/model](../reports/rule_feature_model_sync.md), [tiếp nhận A2/A4](../reports/rule_split_pattern_admission.md) và [hướng dẫn đầy đủ của workspace](06_ghi_chep_lam_viec/SME_FRAUD_README.md).

## Cài đặt và kiểm thử bộ luật

Dùng Python 3.10 trở lên. Có thể dùng môi trường đầy đủ theo `requirements.txt` của nhánh, hoặc môi trường riêng chỉ cho bộ luật:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sme-fraud.txt
New-Item -ItemType Directory -Force .runtime | Out-Null
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

`requirements-lock.txt` ghi phiên bản benchmark lịch sử. `tests/` là bộ kiểm thử hồi quy hiện tại của workspace; `tests_sme_fraud/` giữ bộ kiểm thử có trước trên nhánh. Bộ kiểm thử pipeline `agent2/` dùng pytest và môi trường trong `requirements.txt`.

## Chạy từ bản clone mới

Sinh dữ liệu, train model và chạy rules vào thư mục mới để giữ nguyên báo cáo lịch sử:

```powershell
.\.venv\Scripts\python.exe -m sme_fraud.generate --output data/sme_fraud_003 --rows 100000 --fraud-rate 0.003 --seed 42 --companies 5
.\.venv\Scripts\python.exe -m sme_fraud.validate --data data/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.evaluate --data data/sme_fraud_003 --output reports/local_if/sme_fraud_003
.\.venv\Scripts\python.exe -m sme_fraud.run_rules --data data/sme_fraud_003 --output reports/local_rules/sme_fraud_003 --if-model reports/local_if/sme_fraud_003/isolation_forest.joblib
.\.venv\Scripts\python.exe -m sme_fraud.review_server --data-root data --reports-root reports/local_rules
```

Mở `http://127.0.0.1:8765`; dừng server bằng `Ctrl+C`. Các runner đồng bộ và đánh giá lịch sử cần đủ dataset, snapshot và model baseline; xem điều kiện trong từng báo cáo trước khi chạy.

## Phạm vi file đồng bộ

Kiểm chứng bản cập nhật ngày 17/10/2026: **373 test unittest**, **85 test pytest tương thích và 18 subtest** đều đạt. File Python/JSON được kiểm tra cú pháp, CSV mẫu được kiểm tra chỉ có header; các mẫu khóa/token được rà trong nội dung chuẩn bị commit. Log kiểm thử được lưu cục bộ trong `.runtime/`.

Bản cập nhật gồm mã nguồn, schema, CSV mẫu chỉ chứa header, tài liệu và snapshot Markdown/JSON. Dataset, model mới, runtime, cache, phản hồi người dùng, SQLite, CSV/JSONL kết quả từng dòng và JSON dự đoán/ID hồ sơ chi tiết được giữ trên máy. Các liên kết trong báo cáo tới `.runtime/` hoặc artifact chi tiết chỉ có nội dung sau khi chạy lại trên máy.

Các chỉ số đánh giá trong báo cáo là kết quả dữ liệu tổng hợp. Trạng thái nghiệm thu vận hành được ghi riêng trong báo cáo readiness.
