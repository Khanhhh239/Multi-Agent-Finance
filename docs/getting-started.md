# Bắt đầu với repository

## 1. Đọc theo mục đích

Đọc [tổng quan](project-overview.md), rồi chọn một nhánh:

- Hiểu nghiệp vụ: [nhu cầu và nhiệm vụ](explanation/user-needs-and-tasks.md) → [kiến trúc cash forecast](explanation/cash-forecast-architecture.md).
- Kiểm tra dữ liệu thực: [hướng dẫn dữ liệu T1](../data/T1/README.md) → [audit nguồn Séc](../research/notes/t1_czech_full_dataset_audit.md) → [cách chạy audit](how-to/audit-t1-data.md).
- Phát triển T0: [kế hoạch hợp nhất và dữ liệu còn thiếu](../research/notes/t0_data_foundation_reconciliation.md#kế-hoạch-tiếp-tục-t0) → [dữ liệu và lệnh đang có](../data/T0/README.md) → [hợp đồng T0](reference/t0-data-contracts.md).
- Đọc phương pháp và mã tham khảo: [bộ notebook cũ](../reference_notebooks/README.md) → [tổng kết kết quả lịch sử](reports/agent1-implementation-review.md) → [paper](../research/references/README.md).
- Thay đổi repo: [Contributing](CONTRIBUTING.md), và [AGENTS.md](../AGENTS.md) nếu dùng AI.

## 2. Chuẩn bị môi trường

Chạy lệnh từ gốc repo. Dùng Python 3.10 trở lên; CI của checker dùng Python 3.11. Chưa có lockfile dependency, nên lệnh cài dưới đây chỉ là môi trường khởi đầu, chưa bảo đảm tái lập thí nghiệm lịch sử.

Ví dụ PowerShell, không cần kích hoạt virtualenv:

```powershell
python -m venv .venv
.venv\Scripts\python.exe scripts/checks/check_docs.py
.venv\Scripts\python.exe scripts/checks/check_code.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Các checker và test T0 chỉ cần thư viện chuẩn, không đọc raw local. Nhóm test helper tham khảo dùng fixture nhỏ khi có `numpy`/`pandas`; thiếu dependency sẽ báo `skipped`. Checker Python/JSON không thực thi notebook hoặc code mô hình. Trên macOS/Linux, dùng `.venv/bin/python` thay cho `.venv\Scripts\python.exe`.

Chỉ cài thư viện cho công việc cần làm:

| Công việc | Thư viện |
|---|---|
| T0: tạo dữ liệu, đối soát, benchmark và unit test | Thư viện chuẩn Python |
| T0: tải/audit fixture FinRCA, RecBench, FinBalance, ERPNext, FISCUS | Thư viện chuẩn Python; tải mạng chỉ khi chưa có cache |
| Tải nguồn Séc; audit mẫu BPI/DC | Thư viện chuẩn Python |
| Audit đầy đủ nguồn Séc | `pandas`, `numpy` |
| Mở/chạy notebook, dựng notebook 11/12 | `jupyterlab`, `ipykernel`, `nbformat`, `nbclient` |
| Notebook mô hình và biểu đồ | `numpy`, `pandas`, `lightgbm`, `scipy`, `scikit-learn`, `matplotlib` |

Ví dụ cho audit đầy đủ:

```powershell
.venv\Scripts\python.exe -m pip install pandas numpy
```

## 3. Chọn đường chạy

T0 v0.4 dùng `python -m t0 run-offline --output data/T0/processed/offline-new --gate technical` để chạy các task riêng trên cache hiện có. Thiếu cache ghi `unavailable` và trả exit 3; gate kỹ thuật đạt chưa đồng nghĩa quality đạt. `--gate quality` trả 4 nếu chất lượng/nhãn còn thiếu. `benchmark` giữ suite v2; `benchmark-robustness` so với flow hiện tại. `allocate` mặc định flow qua các ngày đã biết, thêm `--method v2` để hồi quy. `allocate-fx` và `journal-predict` có [ví dụ v0.4 chạy từ đầu](../data/T0/README.md#chạy-t0-v04), gồm ledger/refund/version và Gold trước/sau revision. Chưa có dữ liệu invoice–bank SME hoặc connector ERP.

M0–M3 đã có triển khai offline theo [contract hiện tại](reference/t0-data-contracts.md); các khoảng trống và phần M4–M6 còn lại nằm trong [kế hoạch](../research/notes/t0_data_foundation_reconciliation.md#tiến-độ-và-phần-còn-thiếu). Harness `scripts/data_audit/benchmark_t0_reconciliation.py` tiếp tục dành cho kết quả v1 và BenchRec; không trộn điểm GL–bank với invoice–payment.

Để kiểm tra lại snapshot nghiên cứu đã tải mà không chạy matcher:

```powershell
python scripts/data_audit/research_t0_fixture_sources.py --offline --output data/T0/processed/source-audits/fixture-verify-new.json
```

Nếu cache chưa có, bỏ `--offline` để tải các file đã khai báo; chọn output mới cho mỗi lần chạy. Xem [phạm vi snapshot và phần còn thiếu](../data/T0/README.md#chọn-dữ-liệu-cho-công-việc-tiếp-theo). Script này không cần cài ERPNext, chạy code upstream, OCR hoặc mô hình. Raw research vẫn chỉ-audit; adapter xuất dữ liệu dẫn xuất riêng, không tháo gate trên raw.

Audit hai nguồn Séc độc lập với mô hình: dùng [hướng dẫn audit T1](how-to/audit-t1-data.md).

Code T1 mới chưa được triển khai. Khi xây code mới, xác định đầu vào, nhãn và cutoff theo [hợp đồng dữ liệu T1](reference/t1-data-contracts.md); các mapping của pipeline cũ chỉ là tham khảo. Không đổi tên bảng audit thành `dataset.csv` để bỏ qua bước chuẩn hóa và xác minh nhãn.

Nếu cần tái lập thí nghiệm cũ, xem [mục lục notebook tham khảo](../reference_notebooks/README.md). Công cụ dựng notebook 11/12 thực thi cell và có thể ghi đè output; chỉ dùng khi đã có đầu vào và môi trường phù hợp.

Khi báo cáo kết quả, ghi dataset/snapshot, cutoff, cách chia train/calibration/test, seed, phiên bản thư viện, metric và artifact. Kết quả lịch sử không thay thế lần chạy kiểm chứng mới.
