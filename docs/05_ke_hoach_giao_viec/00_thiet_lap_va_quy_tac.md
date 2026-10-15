# Thiết lập và quy tắc

## 1. Môi trường

| Mục | Giá trị đã dùng |
|---|---|
| Hệ điều hành | Windows 11 (PowerShell). Lệnh dưới đây ghi PowerShell; Linux dùng cú pháp tương đương |
| Python | 3.12.14 |
| Gói | `numpy 2.5.4`, `pandas 3.0.6`, `scikit-learn 1.9.1`, `lightgbm 4.7.0`, `scipy 1.18.1`, `joblib 1.6.0`, `pyarrow 26.0.0`, `pytest 9.1.1` (đầy đủ: `requirements.txt`) |
| Máy | 16 GB RAM, 20 luồng; một thế giới cần 1 đến 3 GB RAM khi huấn luyện |

```powershell
git clone https://github.com/Khanhhh239/Multi-Agent-Finance.git ; cd Multi-Agent-Finance
git checkout agent2-Khanh
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path          # bắt buộc; KHÔNG chạy python -I (chế độ cô lập bỏ thư mục hiện tại)
pytest tests_agent2 tests_sme_fraud -q          # mong đợi: 84 passed
```

## 2. Bản đồ kho mã

```
agent2/                 gói của tôi
  world_v3.py           thế giới v3 (kế thừa bạn bạn)
  world_v4.py           thế giới v4: hồ sơ công ty, quy trình nền, bút toán
  world_v4_schemes.py   30 kịch bản phát triển (SCHEMES), cơ chế vụ
  world_v4_sealed.py    thế giới niêm phong v4: 7 kịch bản mới (NOVEL), 5 ca hợp lệ mới
  world_sealed.py       niêm phong v3 (đã chạy một lần)
  accounting_ext.py     5 loại bút toán mới, kiểm tra kế toán mở rộng
  validate_v3.py, validate_v4.py   kiểm định thế giới
  feats.py              31 đặc trưng baseline thực thể
  feats_v4.py           15 dấu hiệu đỏ v4
  data.py               nạp thế giới thành bảng phân tích, bộ nhớ đệm
  methods.py            luật, IF, ECOD, HBOS, AE, EntityDeviation, LightGBM (Supervised), CES, Gate, Blend, RankFusion
  hybrid.py             L4, cân bằng họ, hai tầng (Collective), Novelty, đặc trưng bộ nhớ
  metrics.py            Recall@B, AP, ca khó, vụ, bootstrap
  alerting.py           khe 2+1, conformal, gộp vụ, lý do tiếng Việt
  bench.py              benchmark v3 và v4 (theo thời gian, bỏ-một-họ, bỏ-một-công-ty)
  final_eval.py         chéo thế giới và niêm phong v3
  eval_v4.py            so sánh phương pháp lai trên v4 (P1, P2, P3)  [đang chạy dở]
  select_v4.py          chọn và đóng băng cấu hình                     [CHƯA CHẠY]
  sealed_v4.py          đánh giá niêm phong v4 một lần                 [CHƯA CHẠY, CHƯA THỬ KHÔ]
  pipeline.py           đường ống đầu-cuối (v3)
  train_pretrained.py   huấn luyện CES và L3 sẵn
  feedback_sim.py, external.py, review_page.py, aggregate.py
sme_fraud/              mã gốc của bạn bạn (luật, đồ thị, kế toán, phản hồi, bộ sinh v2); chỉ sửa run_rules.py
tests_agent2/           20 bài
tests_sme_fraud/        64 bài của bạn bạn
review_ui/, start_review.py    giao diện rà soát của bạn bạn
models/pretrained_v1.joblib    CES và L3 huấn luyện trên v3 (KHÔNG dùng cho v4)
results/v3/, results/v4/       kết quả JSON và CSV
scripts/                tập lệnh sinh dữ liệu và thí nghiệm đã dùng
docs/                   tài liệu
```

## 3. Dữ liệu không nằm trong Git: sinh lại và kiểm dấu vân tay

Dữ liệu sinh xác định theo seed, nhưng phải kiểm xem bản sinh lại có khớp. Chạy từ thư mục gốc kho:

```powershell
New-Item -ItemType Directory -Force work\data, work\results | Out-Null
python scripts/gen_w4b.py     # w4_s411..413, mất khoảng 3 đến 4 phút mỗi thế giới
python scripts/gen_s4.py      # s4_s931..933 (niêm phong), mất khoảng 2 đến 4 phút mỗi thế giới
```

**Dấu vân tay mong đợi** (trong `validation_v4.json` của từng thế giới); nếu lệch, bản sinh lại **không** giống bản đã đo và mọi so sánh với `results/` phải coi là không tương thích:

| Thế giới | Dòng gian lận | Số vụ | Số kịch bản |
|---|---:|---:|---:|
| w4_s411 | 800 | 194 | 30 |
| w4_s412 | 801 | 196 | 30 |
| w4_s413 | 806 | 190 | 30 |
| s4_s931 | 800 | 154 | 37 |
| s4_s932 | 801 | 174 | 37 |
| s4_s933 | 807 | 150 | 37 |

Hai tập lệnh sinh từ `work/` nhưng được lưu ở `scripts/`; chúng chèn `sys.path` là thư mục hiện tại nên phải chạy từ thư mục gốc kho. `gen_*.py` từ chối ghi đè thư mục không rỗng.

## 4. Quy tắc không được vi phạm

| # | Quy tắc | Vì sao |
|---|---|---|
| R1 | **Không chạy bộ phát hiện nào trên `s4_s931..933` trừ trong `sealed_v4.py` sau khi có tệp đóng băng.** Không in, không "xem thử", không dùng làm tập kiểm định | Tập niêm phong chỉ có giá trị một lần |
| R2 | **Không sửa `hybrid.py`, `eval_v4.py`, `methods.py`, `feats_v4.py`, `feats.py`, `data.py` sau khi đóng băng** cho đến khi chạy niêm phong xong (`sealed_v4.py` kiểm băm và từ chối nếu khác) | Cấu hình phải đúng là cái đã chọn |
| R3 | Chọn cấu hình bằng tập phát triển và quy tắc đã đăng ký (`AGENT2_WORKLOG.md` mục 14); **không đổi quy tắc sau khi thấy kết quả** | Tránh chọn theo kết quả mong muốn |
| R4 | Không dùng nhãn kiểm thử để chọn gì (ngưỡng, siêu tham số, đặc trưng) | Rò rỉ |
| R5 | Không thêm đặc trưng hay bộ phát hiện nhắm vào 7 kịch bản niêm phong (`NOVEL` trong `world_v4_sealed.py`) trước khi chạy niêm phong | Giữ tính "chưa từng thấy" |
| R6 | Mọi số đo đều trên dữ liệu tổng hợp: ghi rõ "tổng hợp" trong báo cáo | Trung thực |
| R7 | Không đưa dữ liệu doanh nghiệp thật lên Git hay dịch vụ ngoài; ẩn danh hóa; tuân thủ Nghị định 13/2023/NĐ-CP | Pháp lý |
| R8 | Không tải bộ dữ liệu ngoài lớn (BPI, ICIJ...) khi chưa hỏi người sở hữu dự án (nêu tên tệp, nguồn, dung lượng) | Quy trình |
| R9 | Không cam kết hiệu năng thật cho khách dựa trên số tổng hợp | Trung thực |
| R10 | Tiếng Việt trang trọng trong tài liệu; không dùng ký hiệu "~" và "&" | Quy ước của người dùng |

## 5. Nếu cần sửa mã đã đóng băng trước khi chạy niêm phong
Chỉ khi có lỗi thật (không phải để cải thiện kết quả): sửa, ghi nhật ký (nêu lỗi và bằng chứng), chạy lại `select_v4` trên tập phát triển để tạo tệp đóng băng mới (xóa tệp cũ có ghi nhật ký), rồi mới chạy niêm phong.
