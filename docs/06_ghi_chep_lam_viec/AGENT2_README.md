# Agent 2 — Giám sát rủi ro / phát hiện gian lận nội bộ cho doanh nghiệp nhỏ và vừa Việt Nam

Gói `agent2/` xây trên dự án của bạn bạn (`sme_fraud/`: bộ sinh dữ liệu, kế toán TT133/TT200, 190 đặc trưng, 31 luật A–F). Bản gốc nguyên vẹn nằm ở `friend_zipp/`; bản làm việc ở `sme_fraud/`. Nhật ký việc đã làm: [AGENT2_WORKLOG.md](AGENT2_WORKLOG.md). Báo cáo kết quả: [AGENT2_REPORT_VI.md](AGENT2_REPORT_VI.md).

## Luồng xử lý

```
bảng ERP/kế toán (giao dịch, NCC, nhân viên, hóa đơn, chấm công, đổi tài khoản NH, ...)
   |  sme_fraud.features      190 đặc trưng, chỉ dùng dữ liệu trước thời điểm chấm điểm
   |  agent2.feats            đặc trưng theo thực thể: đơn giá NCC, lương từng nhân viên, người lập/người duyệt,
   |                          khoản gần trùng, tự duyệt tiền mặt thiếu chứng từ (cũng chỉ dùng quá khứ)
   v
 tiếng nói 1: 31 luật + đồ thị quan hệ        (sme_fraud.rules, giải thích được, không cần huấn luyện)
 tiếng nói 2: lệch so với lịch sử thực thể    (agent2.methods.EntityDeviation, không nhãn, khớp trên chính doanh nghiệp)
 tiếng nói 3: đã học trước                    CES (13 trọng số + 1 hằng số, đọc được)  hoặc  L3 (LightGBM)  huấn luyện trên thế giới khác
   v
 chọn cảnh báo: mỗi công ty mỗi tuần B khe  = 2/3 khe cho tiếng nói đã học + 1/3 khe cho kênh "mới lạ" (max xếp hạng của 1 và 2)
   v
 hồ sơ theo thực thể (NCC / nhân viên) + lý do tiếng Việt xếp theo trọng số + mức ưu tiên + hành động gợi ý
   v
 cases.csv, case_queue.csv (cột tương thích công cụ của bạn bạn), review.html (trang rà soát ngoại tuyến), report.json
   v
 phản hồi một chạm (xác nhận / không phải / cần thêm thông tin) --> agent2.feedback_sim mô phỏng cách dùng
```

Ba hồ sơ vận hành: `cold` (chưa có gì học trước), `precision` (mặc định, CES), `wide` (L3, phủ rộng hơn, báo nhầm nhiều hơn).

## Chạy

```powershell
# môi trường (Python thực tế của máy đã bị xoá; venv dựng từ runtime codex)
.\.venv\Scripts\python.exe -m pip install numpy pandas scikit-learn scipy joblib pytest lightgbm xgboost pyarrow rapidfuzz networkx matplotlib
$env:PYTHONPATH = (Get-Location)

# 1. sinh dữ liệu (kế thừa bộ sinh của bạn bạn)
python -m agent2.world_v3 --output work/data/w3_s201 --rows 100000 --fraud-rate 0.003 --seed 201 --companies 8
python -m agent2.validate_v3 --data work/data/w3_s201

# 2. so sánh các phương pháp, nhiều seed
python -m agent2.bench --data work/data/w3_s201 work/data/w3_s202 --out work/results/bench
python -m agent2.aggregate work/results/bench

# 3. học trước hai tiếng nói và chạy toàn bộ đường ống
python -m agent2.train_pretrained --worlds work/data/w3_s201 work/data/w3_s202 --out models/pretrained_v1.joblib
python -m agent2.pipeline --data work/data/w3_s205 --out work/runs/s205 --profile precision --pretrained models/pretrained_v1.joblib
python -m agent2.review_page --cases work/runs/s205/cases.csv --out work/runs/s205/review.html

# 4. kiểm thử
python -m pytest tests_agent2 -q          # 11+ test mới
cd friend_zipp/zipp && python -m pytest tests -q   # 64 test gốc
```

## Tệp chính

| Tệp | Vai trò |
|---|---|
| `agent2/world_v3.py` | Thế giới dữ liệu v3: NCC onboard rải đều, độ phổ biến Zipf, đơn giá theo NCC, mùa vụ Tết, 3 mức khó, 3 họ gian lận không có luật viết sẵn, mồi hợp lệ |
| `agent2/world_sealed.py` | Tập niêm phong: 3 họ mới (`price_creep`, `off_cycle_payroll`, `vendor_burst`), chạy một lần |
| `agent2/validate_v3.py` | Kiểm tra cấu trúc, trình tự thời gian, bút toán cân, cách ly nhãn, và các lỗi "lộ nhãn" của v2 |
| `agent2/feats.py` | Đặc trưng theo thực thể (nhân quả) |
| `agent2/methods.py` | IF, ECOD, HBOS, autoencoder, EntityDeviation, RuleLogit, CalibratedStack, LightGBM, các kiểu hợp nhất |
| `agent2/metrics.py` | AP, ngân sách theo công ty–tuần, hồ sơ theo thực thể, độ trễ, báo nhầm ca giống gian lận, bootstrap theo vụ |
| `agent2/bench.py`, `final_eval.py`, `aggregate.py` | Giao thức: theo thời gian, bỏ một họ, bỏ một công ty, chéo thế giới, niêm phong |
| `agent2/alerting.py` | Chọn cảnh báo (khe thăm dò, conformal/BH), hồ sơ, lý do và hành động tiếng Việt |
| `agent2/feedback_sim.py` | Mô phỏng vòng phản hồi theo tuần: nới ngưỡng so với học lại trọng số, có nhiễu và mẫu kiểm toán |
| `agent2/external.py` | Kiểm tra trên DFKI General Ledger và ERP Fraud Data (Würzburg) |
| `agent2/pipeline.py`, `train_pretrained.py`, `review_page.py` | Đường ống đầu–cuối, huấn luyện trước, trang rà soát cho người không chuyên |

## Điều cần nhớ khi đọc kết quả

- Mọi số đo là **trên dữ liệu tổng hợp**. Không dùng để nói về doanh nghiệp thật. Các mô hình đã học trước chỉ tốt bằng mức độ mà thế giới tổng hợp giống thực tế.
- Số đo trong cùng phân phối với dữ liệu huấn luyện (AP 0,8–0,97 của mô hình có giám sát) là **vòng tròn**; số đáng tin là số trên họ gian lận chưa thấy và trên tập niêm phong.
- Mỗi đơn vị "một nhãn" là một giao dịch; tỷ lệ gian lận 0,3% nên ROC-AUC luôn cao (0,85–0,99) kể cả khi AP thấp. Không dùng ROC-AUC làm tiêu chí.
- Dữ liệu cần thêm để phát hiện "mua đắt": đơn giá và số lượng từng dòng hàng trong hóa đơn điện tử XML (có trong dữ liệu hóa đơn theo Nghị định 123/2020). Chỉ từ tổng tiền thanh toán, họ này gần như không phát hiện được.
