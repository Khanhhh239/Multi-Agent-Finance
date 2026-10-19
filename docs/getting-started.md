# Bắt đầu với repository

## 1. Đọc theo mục đích

Đọc [tổng quan](project-overview.md), rồi chọn một nhánh:

- Hiểu nghiệp vụ: [nhu cầu và nhiệm vụ](explanation/user-needs-and-tasks.md) → [kiến trúc cash forecast](explanation/cash-forecast-architecture.md).
- Kiểm tra dữ liệu thực: [hướng dẫn dữ liệu T1](../data/T1/README.md) → [audit nguồn Séc](../research/notes/t1_czech_full_dataset_audit.md) → [cách chạy audit](how-to/audit-t1-data.md).
- Đọc phương pháp và mã: [thứ tự notebook](../notebooks/README.md) → [tổng kết kết quả lịch sử](reports/agent1-implementation-review.md) → [paper](../research/references/README.md).
- Thay đổi repo: [Contributing](CONTRIBUTING.md), và [AGENTS.md](../AGENTS.md) nếu dùng AI.

## 2. Chuẩn bị môi trường

Chạy lệnh từ gốc repo. Dùng Python 3.10 trở lên; CI của checker dùng Python 3.11. Chưa có lockfile dependency, nên lệnh cài dưới đây chỉ là môi trường khởi đầu, chưa bảo đảm tái lập thí nghiệm lịch sử.

Ví dụ PowerShell, không cần kích hoạt virtualenv:

```powershell
python -m venv .venv
.venv\Scripts\python.exe scripts/checks/check_docs.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Hai kiểm tra chỉ cần thư viện chuẩn và không đọc dữ liệu local. Trên macOS/Linux, dùng `.venv/bin/python` thay cho `.venv\Scripts\python.exe`.

Chỉ cài thư viện cho công việc cần làm:

| Công việc | Thư viện |
|---|---|
| Tải nguồn Séc; audit mẫu BPI/DC | Thư viện chuẩn Python |
| Audit đầy đủ nguồn Séc | `pandas`, `numpy` |
| Mở/chạy notebook, dựng notebook 11/12 | `jupyterlab`, `ipykernel`, `nbformat`, `nbclient` |
| Notebook mô hình và biểu đồ | `numpy`, `pandas`, `lightgbm`, `scipy`, `scikit-learn`, `matplotlib` |

Ví dụ cho audit đầy đủ:

```powershell
.venv\Scripts\python.exe -m pip install pandas numpy
```

## 3. Chọn đường chạy

Audit hai nguồn Séc độc lập với mô hình: dùng [hướng dẫn audit T1](how-to/audit-t1-data.md).

Để chạy phần dự báo thời điểm thanh toán T1, trước hết đáp ứng [đầu vào và quy tắc nhãn T1](reference/t1-data-contracts.md), rồi theo [mục lục notebook](../notebooks/README.md). Không đổi tên bảng audit thành `dataset.csv` để bỏ qua bước adapter. Công cụ dựng notebook 11/12 thực thi cell và có thể ghi đè output; chỉ dùng khi đã có đầu vào và môi trường phù hợp.

Khi báo cáo kết quả, ghi dataset/snapshot, cutoff, cách chia train/calibration/test, seed, phiên bản thư viện, metric và artifact. Kết quả lịch sử không thay thế lần chạy kiểm chứng mới.
