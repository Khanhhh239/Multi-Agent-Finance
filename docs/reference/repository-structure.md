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
│   ├── reference/                    # Cấu trúc repo, hợp đồng dữ liệu T0 và T1
│   ├── explanation/                  # Nhu cầu, kiến trúc, kế hoạch thiết kế
│   ├── decisions/                    # Quyết định có bối cảnh và hệ quả
│   ├── reports/                      # Đánh giá có phạm vi/ngày chốt
│   └── archive/                      # Bản trạng thái/hướng dẫn đã cũ
├── data/
│   ├── README.md
│   ├── T0/                           # BenchRec, bộ tổng hợp, audit nguồn; xem README
│   └── T1/                           # README, raw, interim theo task
├── t0/                               # CLI v0.4: flow/FX, versioned ledger, journal/policy, evaluator/gate
├── reference_notebooks/              # Bộ notebook cũ, chỉ dùng tham khảo
│   ├── README.md
│   ├── 01_…ipynb → 12_…ipynb        # Pipeline thực nghiệm lịch sử
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
│       │   ├── t0/                   # Benchmark, nguồn nghiên cứu và bằng chứng kiểm tra T0
│       │   └── t1-t8/                # Rà soát khả năng truy cập nguồn T1–T8
│       ├── code/                     # Mã tham khảo bên ngoài
│       └── papers/                   # PDF và manifest nguồn tải
├── scripts/
│   ├── data_download/                # Tải raw và manifest nguồn
│   ├── data_audit/                   # Kiểm tra dữ liệu local, xuất thống kê/bảng audit
│   ├── notebooks/                    # Công cụ dựng lại notebook tham khảo 11/12
│   ├── checks/                       # Kiểm tra repository, không cần dữ liệu mô hình
│   └── archive/t0/                   # Khảo sát nguồn và generator/benchmark T0 ban đầu, chỉ tái lập
└── tests/                            # Checker tài liệu và invariant/evaluator/assignment T0
```

Không tạo package `src/`, thư mục task rỗng hoặc cấu trúc production khi chưa có mã tương ứng. Khi có dữ liệu task mới, theo quy ước tại [data README](../../data/README.md). Đầu vào/output lịch sử chưa có được ghi trong [overview](../project-overview.md), không biểu diễn như thư mục đã tồn tại trong cây trên.

Thư mục `notebooks/` trước đây đã đổi thành `reference_notebooks/`, chỉ dùng để tham khảo. Code T1 mới sẽ được xây riêng; hiện chưa có thư mục triển khai mới. `scripts/notebooks/` vẫn giữ công cụ dựng lại bộ tham khảo.

Trong `research/notes/`, lựa chọn nguồn T1 được duy trì tại [đề xuất dataset](../../research/notes/t1_dataset_recommendation.md); quy mô và chất lượng hai nguồn Séc tại [audit toàn bộ](../../research/notes/t1_czech_full_dataset_audit.md). Ghi chú cũ `t1_payment_timing_data_sources.md` đã được bỏ vì các khuyến nghị đã bị thay thế.

## Chọn script theo mục đích

T0 v0.4 dùng `python -m t0 run-offline` cho toàn bộ task có cache với gate execution/technical/quality riêng; `generate`/`benchmark` giữ suite v2, `benchmark-robustness` so v2 với constrained flow. `allocate` nhận typed AP/AR và mặc định constrained flow qua nhiều ngày, `allocate-fx` nhận remittance có quote; `ledger`/`gold` xử lý quyết định/version local. `journal-predict` chạy input quan sát/policy; `journal` chấm nguồn FinBalance. `reconcile`/`evaluate` giữ contract receipt v0.1. [Lệnh và output](../../data/T0/README.md), [contract](t0-data-contracts.md).

| Module lõi | Vai trò |
|---|---|
| `t0/data.py` | Snapshot/quality v0.1, source gate, JSON/JSONL nghiêm ngặt, CSV kiểm header/độ rộng dòng, hash và writer receipt bất biến dùng để tái lập |
| `t0/allocation.py` | Typed AP/AR, reference partial/tiền thừa, subset giới hạn và abstention |
| `t0/constrained.py` | Đồ thị reference/observed remittance qua nhiều ngày trong snapshot, max-flow số nguyên và kiểm nghiệm duy nhất, review khi mơ hồ/rủi ro/vượt cap |
| `t0/fx.py` | Quote minor-unit tường minh, chuyển đổi rational/half-even và đề xuất observed FX remittance riêng |
| `t0/balances.py` | Statement equation, tổng bank theo account/kỳ, opening–closing continuity và completeness khai báo |
| `t0/robustness.py` | Intent generator và benchmark riêng cho reference sai, N:M, partial remittance, clean/masked/noisy/stress |
| `t0/gates.py` | Gate execution/technical/quality, thiếu bằng chứng và exit code; không chứng nhận production |
| `t0/adapters.py` | Hash/provenance, FinRCA AP clean/corrupted, quarantine/split/statement audit |
| `t0/ledger.py` | SQLite command/idempotency, decision state, version invoice/payment, FX allocation/bank/refund links và Gold |
| `t0/offline.py` | Generator intent AR v2, bốn baseline + ba ablation, fixture FISCUS và runner từng task |
| `t0/settlement.py` | RecBench payout–bank riêng, giữ signed amount và unknown endpoints |
| `t0/journal.py` | Text/policy → journal, detector arithmetic/identity/dependencies với abstention; expected chỉ trong evaluator |
| `t0/journal_policy.py` | Policy/facts quan sát → postings nhiều dòng, carrying FX, debit-credit pairing và trial balance |
| `t0/matching.py`, `evaluation.py` | Bốn baseline/phép chấm receipt v0.1 giữ cho so sánh và harness lịch sử |
| `t0/scenarios.py`, `benchrec.py` | Bộ tình huống nghiên cứu v1 và adapter/baseline GL–bank riêng |

Chạy từ gốc repo; mỗi script tự xác định gốc repo theo `__file__`. Thư mục script chia theo thao tác; tên file ghi task/nguồn khi công cụ chỉ áp dụng cho phạm vi đó.

Tên file T0 dùng `snake_case.py` cho Python và `kebab-case.json` cho cấu hình/bằng chứng. Script độc lập theo mẫu `<hành_động>_t0_<đối_tượng>.py`; module trong package `t0/` dùng tên vai trò, test theo `test_t0_<phạm_vi>.py`. Hậu tố `v01` ở generator/benchmark receipt lưu trữ phân biệt contract v0.1 với suite nghiên cứu v1 và AR v2. JSON kế hoạch có version; JSON kết quả có ngày chạy. Giữ tên manifest/artifact do pipeline hoặc nguồn ngoài quy định, không đổi raw hay output lịch sử.

| Script | Mục đích và hướng dẫn |
|---|---|
| [data_download/download_t0_benchrec.py](../../scripts/data_download/download_t0_benchrec.py) | Tải BenchRec Kaggle v3 bằng URL công khai, khóa hash ZIP/CSV, giữ raw bất biến; [lệnh chạy](../../data/T0/README.md#benchrec-kaggle--đối-soát-glbank) |
| [data_download/download_czech_t1_datasets.py](../../scripts/data_download/download_czech_t1_datasets.py) | Tải raw và manifest hai nguồn Séc; [quy trình T1](../how-to/audit-t1-data.md) |
| [data_audit/audit_czech_t1_datasets.py](../../scripts/data_audit/audit_czech_t1_datasets.py) | Audit toàn bộ snapshot local; xuất CSV interim và JSON thống kê |
| [data_audit/audit_t1_source_samples.py](../../scripts/data_audit/audit_t1_source_samples.py) | Profile các mẫu local; không tải mạng, không đại diện toàn bộ dataset |
| [data_audit/audit_t0_benchrec.py](../../scripts/data_audit/audit_t0_benchrec.py) | Preflight và tùy chọn kiểm tra nhóm train; script audit không chạy matcher; [phạm vi và lệnh](../../data/T0/README.md#benchrec-kaggle--đối-soát-glbank) |
| [data_audit/benchmark_t0_reconciliation.py](../../scripts/data_audit/benchmark_t0_reconciliation.py) | Chạy benchmark cố định hoặc `--verify-existing` để kiểm định lịch sử; chặn ghi đè output dở dang; [cách chạy](../../data/T0/README.md#chạy-benchmark-nghiên-cứu-và-benchrec) |
| [data_audit/research_t0_reconciliation.py](../../scripts/data_audit/research_t0_reconciliation.py) | Lưu hash nguồn học thuật/nghiệp vụ, đọc PDF trong repo; không chạy mô hình của paper; [tổng hợp nghiên cứu](../reports/t0-method-review.md#cơ-sở-nghiên-cứu) |
| [data_audit/research_t0_fixture_sources.py](../../scripts/data_audit/research_t0_fixture_sources.py) | Tải file công khai khóa revision, parse AST và audit mẫu CSV/JSONL; có `--offline` kiểm tra cache. [Kết quả fixture/synthetic và giới hạn](../../research/notes/t0_data_foundation_reconciliation.md#mở-rộng-nguồn-fixture-và-benchmark--20102026); chưa chạy code nguồn ngoài hoặc matcher |
| [notebooks/build_notebook.py](../../scripts/notebooks/build_notebook.py) | Thực thi nguồn `.py` trong `reference_notebooks/` để dựng notebook tham khảo 11/12; [điều kiện chạy](../../reference_notebooks/README.md) |
| [checks/check_docs.py](../../scripts/checks/check_docs.py) | Kiểm tra tài liệu bắt buộc và link nội bộ; [lệnh kiểm tra](../CONTRIBUTING.md) |
| [checks/check_code.py](../../scripts/checks/check_code.py) | Biên dịch kiểm tra Python và đọc JSON/JSONL của repo mà không thực thi; bỏ raw/output/dependency/mã ngoài, chạy trong CI |

### Khảo sát T0 đã lưu trữ

`scripts/archive/t0/` giữ code khảo sát nguồn bị loại và generator/vòng benchmark ban đầu, không nằm trong đường CLI hiện tại. Các test hồi quy vẫn chạy. Bằng chứng cũ nằm ở `research/references/data-checks/t0/archive/`, giữ nguyên byte; đường dẫn/hash code trong JSON là thông tin tại thời điểm chạy, không được viết lại theo vị trí mới.

Các module lưu trữ dưới đây vẫn có logic audit/generator và test riêng, không phải wrapper thừa. Writer receipt dùng trực tiếp `t0.data.save_receipt_dataset`; đã bỏ alias tái xuất và import không dùng. Benchmark receipt lưu trữ ghi hash cả runner/generator đã chuyển thư mục, ngoài các module lõi, trong lượt chạy mới.

Reader CSV BenchRec dùng trực tiếp implementation chung tại `t0.data`; adapter trả danh sách qua cùng reader. Parser JSON/JSONL của CLI, ledger, plan và script T0 vận hành dùng chung contract nghiêm ngặt. Nhận diện payload journal nằm ở `journal_policy.observed_identity`, được detector và dependency resolver dùng chung; giữ các tên import công khai đang có caller.

| Script lưu trữ | Cách chạy từ gốc repo |
|---|---|
| [archive/t0/audit_t0_moneyvis.py](../../scripts/archive/t0/audit_t0_moneyvis.py) | `python -m scripts.archive.t0.audit_t0_moneyvis --output <file-moi.json>`: audit MoneyVis local; thêm `--download` nếu cần tải raw |
| [archive/t0/audit_t0_source_survey.py](../../scripts/archive/t0/audit_t0_source_survey.py) | `python -m scripts.archive.t0.audit_t0_source_survey --output <file-moi.json>`: audit khảo sát CityVizor/DC và các nguồn cũ; thêm `--download` để cho phép request khi cache chưa có |
| [archive/t0/research_t0_additional_sources.py](../../scripts/archive/t0/research_t0_additional_sources.py) | Script khảo sát truy cập/schema cũ; dùng `--help`, chọn `--output` mới; có thể gọi mạng khi thiếu cache |
| [archive/t0/generate_t0_receipts_v01.py](../../scripts/archive/t0/generate_t0_receipts_v01.py) | Hàm `generate` ban đầu, version khóa 0.1.0; chỉ test/tái lập lịch sử, không phải generator CLI hiện tại |
| [archive/t0/benchmark_t0_receipts_v01.py](../../scripts/archive/t0/benchmark_t0_receipts_v01.py) | Vòng `benchmark` ban đầu, gọi bằng Python khi cần tái lập; dùng output mới. Phép chấm receipt vẫn ở lõi |

Hai wrapper `download_moneyvis_t0.py`/`download_t0_source_survey.py` đã bỏ; `audit-real`/`audit-sources` không còn trong CLI `t0`. Chức năng tải/audit tương ứng được gom trong hai module lưu trữ, tách biệt với matcher và source gate còn ở lõi.


