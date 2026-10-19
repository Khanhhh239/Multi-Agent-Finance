# Cấu trúc repository

Đây là bản mô tả cây thư mục chính. Các README khác liên kết tới trang này thay vì chép lại toàn bộ cây.

```text
.
├── AGENTS.md                         # Quy tắc cho AI
├── README.md                         # Điểm vào cho người đọc
├── .github/
│   ├── pull_request_template.md      # Nội dung và tác động tài liệu của PR
│   └── workflows/docs.yml            # Kiểm tra tài liệu tự động
├── docs/
│   ├── README.md                     # Mục lục
│   ├── project-overview.md           # Phạm vi, trạng thái hiện tại
│   ├── getting-started.md            # Môi trường và lộ trình đọc/chạy
│   ├── CONTRIBUTING.md               # Quy trình, bảng cập nhật tài liệu, kiểm tra
│   ├── how-to/audit-t1-data.md        # Tải và kiểm tra dữ liệu
│   ├── reference/                    # Cấu trúc repo, hợp đồng dữ liệu T1 (t1-data-contracts.md)
│   ├── explanation/                  # Nhu cầu, kiến trúc, kế hoạch thiết kế
│   ├── decisions/                    # Quyết định có bối cảnh và hệ quả
│   ├── reports/                      # Đánh giá có phạm vi/ngày chốt
│   └── archive/                      # Bản trạng thái/hướng dẫn đã cũ
├── data/
│   ├── README.md
│   └── T1/                           # README, raw, interim theo task
├── notebooks/
│   ├── README.md
│   ├── 01_…ipynb → 12_…ipynb        # Pipeline thực nghiệm
│   ├── 11_…py, 12_…py               # Nguồn chính của notebook 11/12
│   ├── survival_utils.py             # Logic dùng chung
│   └── archive/                      # Notebook tổng hợp cũ
├── research/
│   ├── notes/                        # Nghiên cứu phương pháp và nguồn dữ liệu
│   ├── reports/                      # Báo cáo LaTeX
│   └── references/
│       ├── README.md                 # Mục lục và phạm vi bằng chứng
│       ├── bibliography/             # Danh mục đọc và BibTeX
│       ├── data-checks/
│       │   ├── t1/                   # Kiểm tra nguồn, profile, audit và toàn vẹn T1
│       │   └── t1-t8/                # Rà soát khả năng truy cập nguồn T1–T8
│       ├── code/                     # Mã tham khảo bên ngoài
│       └── papers/                   # PDF và manifest nguồn tải
├── scripts/
│   ├── data_download/                # Tải raw và manifest nguồn
│   ├── data_audit/                   # Kiểm tra dữ liệu local, xuất thống kê/bảng audit
│   ├── notebooks/                    # Dựng notebook từ nguồn Python
│   └── checks/                       # Kiểm tra repository, không cần dữ liệu mô hình
└── tests/                            # Kiểm tra tự động độc lập dữ liệu thật
```

Không tạo package `src/`, thư mục task rỗng hoặc cấu trúc production khi chưa có mã tương ứng. Khi có dữ liệu task mới, theo quy ước tại [data README](../../data/README.md). Đầu vào/output lịch sử chưa có được ghi trong [overview](../project-overview.md), không biểu diễn như thư mục đã tồn tại trong cây trên.

## Chọn script theo mục đích

Chạy từ gốc repo; mỗi script tự xác định gốc repo theo `__file__`. Thư mục script chia theo thao tác; tên file ghi task/nguồn khi công cụ chỉ áp dụng cho phạm vi đó.

| Script | Mục đích và hướng dẫn |
|---|---|
| [data_download/download_czech_t1_datasets.py](../../scripts/data_download/download_czech_t1_datasets.py) | Tải raw và manifest hai nguồn Séc; [quy trình T1](../how-to/audit-t1-data.md) |
| [data_audit/audit_czech_t1_datasets.py](../../scripts/data_audit/audit_czech_t1_datasets.py) | Audit toàn bộ snapshot local; xuất CSV interim và JSON thống kê |
| [data_audit/audit_t1_source_samples.py](../../scripts/data_audit/audit_t1_source_samples.py) | Profile các mẫu local; không tải mạng, không đại diện toàn bộ dataset |
| [notebooks/build_notebook.py](../../scripts/notebooks/build_notebook.py) | Thực thi nguồn `.py` để dựng notebook 11/12; [điều kiện chạy](../../notebooks/README.md) |
| [checks/check_docs.py](../../scripts/checks/check_docs.py) | Kiểm tra tài liệu bắt buộc và link nội bộ; [lệnh kiểm tra](../CONTRIBUTING.md) |


