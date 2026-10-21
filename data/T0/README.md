# Dữ liệu T0 và cách chạy

**T0 v0.4 có N:M khác ngày trong snapshot, FX có quote quan sát, refund–bank, phiên bản invoice/payment và journal nhiều dòng theo policy tường minh.** Pipeline offline giữ AR tổng hợp, AP FinRCA, payout–bank RecBench, journal/detector giới hạn và ledger/Gold. BenchRec tiếp tục là task GL–bank riêng. Chưa có dữ liệu invoice–bank SME được gán nhãn độc lập.

[Kế hoạch thực hiện hợp nhất và tiến độ](../../research/notes/t0_data_foundation_reconciliation.md#tiến-độ-và-phần-còn-thiếu) phân biệt phần đã code, phạm vi kiểm chứng và các mốc còn thiếu. [Contract v0.4 và schema tương thích](../../docs/reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal) là nguồn chính cho mapping, tiền, cutoff và quyết định.

Chạy từ gốc repo với Python 3.10+. Matcher và benchmark chỉ dùng thư viện chuẩn. Raw/output local nằm ngoài Git. [Hợp đồng dữ liệu và metric](../../docs/reference/t0-data-contracts.md) quy định cách đọc kết quả; [báo cáo T0](../../docs/reports/t0-method-review.md) duy trì kết quả và giới hạn từng task.

Sau lượt rà soát Python/JSON, parser/CSV và journal/ledger kiểm chặt input hơn; input trước đây bị nhận nhầm có thể chuyển lỗi/review. [Quy tắc hiện hành](../../docs/reference/t0-data-contracts.md#quy-tắc-đọc-dữ-liệu-và-sửa-lỗi-v04), [kết quả kiểm chứng và phần code đã gộp](../../docs/reports/t0-method-review.md#rà-soát-pythonjson-và-dọn-code--21102026). Chạy `python scripts/checks/check_code.py` để kiểm cú pháp Python/JSON/JSONL của repo mà không thực thi notebook hoặc đụng raw/output.

## Chạy T0 v0.4

```powershell
python -m t0 run-offline --output data/T0/processed/offline-v4-new --gate technical
python -m t0 allocate-fx --input data/T0/examples/v04 --cutoff 2025-01-31 --output data/T0/processed/fx-example-new
python -m t0 journal-predict --input data/T0/examples/v04/journal-policy.jsonl --output data/T0/processed/journal-policy-new
python -m t0 ledger --input data/T0/examples/v04/ledger.jsonl --store data/T0/processed/ledger-v04-new.sqlite
python -m t0 gold --store data/T0/processed/ledger-v04-new.sqlite --cutoff 2025-01-31 --output data/T0/processed/gold-before-revision-new.json
python -m t0 gold --store data/T0/processed/ledger-v04-new.sqlite --cutoff 2025-02-01 --output data/T0/processed/gold-after-revision-new.json
```

[Mẫu v0.4](examples/v04/) là fixture tự viết tổng hợp, không phải nguồn doanh nghiệp. FX example có invoice 100 USD cents và payment 25.000 VND, quote minor-unit 250/1. Ledger example có reverse/refund/link và revision đến sau; hai Gold lần lượt giữ invoice 100 và 120 cents. Journal example có thuế/chiết khấu khai báo, payment và trial balance. Lệnh chỉ lưu local; không gửi ERP, ngân hàng hoặc tự commit dự đoán. Giữ source_ref/time/policy quan sát khi thay bằng input thật.

`allocate-fx` tạo đề xuất riêng; không cộng với output `allocate` rồi coi dư đã được kiểm chung. Ledger kiểm dư khi commit. `journal-predict` nhận input JSONL không cần nhãn; `journal` vẫn là evaluator nguồn FinBalance riêng, không tự bổ sung policy/facts từ expected entries. [Contract chi tiết](../../docs/reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal) quy định field, cap, rounding, version và trường hợp unsupported.

## Benchmark và gate hiện hành

```powershell
python -m t0 benchmark-robustness --output data/T0/processed/robustness-new
```

`allocate` và proposals FinRCA mặc định dùng `constrained_flow`; thêm `--method v2` ở `allocate` để đối chiếu thuật toán cũ. `generate`/`benchmark` vẫn là suite v2 cố định. Lượt offline chạy thêm 32 lượt robustness (hai split × hai seed × bốn profile × hai phương pháp), giữ riêng tại `robustness/`. Remittance số tiền cần đến từ nguồn quan sát; [schema và giới hạn](../../docs/reference/t0-data-contracts.md#thuật-toán-và-bằng-chứng-remittance).

Đọc `assessment` trong `evidence.json`: exit 0 với gate technical chỉ xác nhận kỹ thuật. Thiếu task trả 3, lỗi technical trả 1; chọn `--gate quality` trả thêm 4 khi quality còn thiếu/không đạt. Cả evidence và output dở vẫn được giữ, lần khác dùng output mới. Hiện chưa có đầy đủ bằng chứng để gate quality đạt. FinBalance thêm `inconsistency_quality` với abstention; Gold mẫu thêm `bank_reconciliation` dựa trên statement khai báo và `bank_unlinked`.

## Output offline và lệnh thành phần

`run-offline` ở đầu trang chạy hoàn toàn local trên cache fixture đã tải. Thiếu snapshot ghi `unavailable`, quality `null` và trả exit 3; cache sai hash làm lượt chạy báo lỗi. Output chưa hoàn tất vẫn được giữ, lần sau dùng tên mới. `--sources` cho phép chọn root cache khác. Không train, không gọi ERP/bank API, không chạy code upstream.

| Output | Nội dung |
|---|---|
| `ar/` | Experiment/code/plan hash, 56 lượt (hai split × hai seed × hai profile × bảy phương pháp); input/truth/prediction tách file, summary và metric từng scenario/currency |
| `robustness/` | 32 lượt so v2 với constrained flow trên bốn profile, gồm reference sai, N:M và remittance |
| `finrca/clean`, `finrca/corrupted` | Typed invoice/payment/bank, observed allocation + reason, quarantine có raw/lineage, audit statement và proposals. Chất lượng matching `null`, không coi observed allocation là repair oracle |
| `recbench/` | Prediction payout–bank lưu trước khi chấm, universe đầy đủ/endpoint thiếu/negative/unknown; signed payout giữ nguyên |
| `finbalance/` | Prediction journal từ text, unsupported documents và metric trên 143 coverage records; không tự ghi journal vào ledger |
| `fiscus/` | SQLite từng fixture bank và so transition/financial effect; domain khác không được nhận là đã hỗ trợ |
| `ledger/` | JSONL lệnh mẫu, SQLite idempotent, Gold năm cutoff cho credit/phí/unknown/verify/reverse/refund |
| `evidence.json` | Tổng hợp theo task, giới hạn dữ liệu, code/plan hash và hash artifact |

Các lệnh thành phần dùng output mới:

```powershell
python -m t0 benchmark --output data/T0/processed/ar-new
python -m t0 generate --seed 2101 --blocks 4 --profile clean --output data/T0/interim/ar-input-new
python -m t0 allocate --input data/T0/interim/ar-input-new --output data/T0/processed/ar-proposals-new
python -m t0 adapt-finrca --output data/T0/interim/finrca-new
python -m t0 allocate --input data/T0/interim/finrca-new/clean --output data/T0/processed/ap-proposals-new
python -m t0 settlement --output data/T0/processed/settlement-new
python -m t0 journal --output data/T0/processed/journal-new
python -m t0 fiscus --output data/T0/processed/fiscus-new
python -m t0 ledger-demo --output data/T0/processed/ledger-demo-new
```

`generate`/`benchmark` dùng suite v2. Generator/benchmark receipt ban đầu nằm ở `scripts/archive/t0/` để tái lập; `reconcile`/`evaluate` dành riêng cho schema receipt v0.1, còn `allocate` dành cho typed AP/AR. `auto` chỉ là đề xuất, không duyệt/commit.

Nhập lệnh mẫu và đọc Gold từ ledger khác:

```powershell
python -m t0 ledger --input data/T0/processed/ledger-demo-new/commands.jsonl --store data/T0/processed/ledger-import-new.sqlite
python -m t0 gold --store data/T0/processed/ledger-import-new.sqlite --cutoff 2025-02-01 --output data/T0/processed/gold-import-new.json
```

Nhập lại **cùng file/key** trả kết quả trước, không tạo hiệu ứng mới. File lỗi giữa chừng giữ các command đã commit; sửa dữ liệu dùng key/transition đúng contract, không viết lại lịch sử. CLI Gold từ chối ghi đè. Đây là ví dụ mô phỏng, chưa có importer ERP hoặc chuyển dự đoán thành phê duyệt tự động.

[Kết quả và hạn chế theo snapshot](../../docs/reports/t0-method-review.md) được giữ riêng cho từng mốc; tên thư mục output không chọn phiên bản code. Muốn tái lập metric lịch sử cần đúng code hash/cấu hình được ghi trong bằng chứng.

## BenchRec Kaggle — đối soát GL–bank

Snapshot [Kaggle version 3](https://www.kaggle.com/datasets/benchmarkteam/benchrec-real-world-cash-reconciliation-dataset) đã tải ngày 19/10/2026 qua API công khai. Bên phát hành mô tả đây là dữ liệu thực đã làm mờ thông tin và ghi license CC BY 4.0. Raw, bốn CSV và manifest hash nằm tại `data/T0/raw/benchrec_kaggle/2026-10-19-v3/`.

```powershell
python scripts/data_download/download_t0_benchrec.py
python scripts/data_audit/audit_t0_benchrec.py
```

Downloader khóa version/hash, xác minh lại snapshot có sẵn và không ghi đè raw. Audit kiểm tra toàn bộ CSV, ID, tiền/ngày và độ phủ nhãn; báo cáo mặc định tại `data/T0/processed/source-audits/benchrec-kaggle.json`. Thêm `--train-semantics` để kiểm tra nhóm theo `matchId` trên train; không sửa nhóm chênh lệch tiền. [Bằng chứng audit](../../research/references/data-checks/t0/benchrec-train-semantics-2026-10-19.json).

BenchRec dùng adapter `t0/benchrec.py` và harness bên dưới. Manifest giữ cờ `inspection_only_excluded_from_matching` để chặn chạy nhầm bằng CLI hóa đơn `reconcile`/`evaluate`. File submission tham khảo không dùng làm ground truth.

## Fixture và benchmark bổ sung — 20/10/2026

Đã tải snapshot khóa revision của tám nguồn ERPNext/OCA, RecBench, FinRCA, FinBalance, FISCUS và hai demo invoice. [Audit nguồn ngày 20/10](../../research/references/data-checks/t0/fixture-source-research-2026-10-20.json) chỉ là nghiên cứu; pipeline hiện có adapter/task riêng, không thay byte raw. [Điều kiện sử dụng và phần đã audit](../../research/notes/t0_data_foundation_reconciliation.md#mở-rộng-nguồn-fixture-và-benchmark--20102026).

```powershell
python scripts/data_audit/research_t0_fixture_sources.py --output data/T0/processed/source-audits/fixture-research-new.json
python scripts/data_audit/research_t0_fixture_sources.py --offline --output data/T0/processed/source-audits/fixture-research-verify-new.json
```

Script chỉ dùng thư viện chuẩn, giữ raw ở `data/T0/raw/fixture_research/2026-10-20/`; cache được kiểm tra hash/byte/spec, kể cả lỗi truy cập. Không ghi đè output. Muốn thử tải lại lỗi, chọn `--input` và `--output` mới. Mỗi response giới hạn 16 MB; chỉ tải các file được khai báo, không tải toàn bộ tier lớn/PDF hoặc cài/chạy ERP/code nguồn ngoài. `--offline` không gọi mạng. Nhãn chỉ dùng audit, không cấp cho matcher. Snapshot có policy `inspection_only_excluded_from_matching`, không phải input `reconcile`/`evaluate`.

RecBench của End Close là synthetic settlement benchmark, khác BenchRec GL–bank ở trên. FinRCA là AP synthetic; FinBalance là chứng từ/kế toán tổng hợp; FISCUS là fixture trạng thái. Không coi chúng là dữ liệu SME thực. CSV RecBench được giữ hash riêng, chưa xác minh hash Parquet của release manifest. ERPNext demo payment JSON có lỗi 404 ở commit đã khóa; hai file test vẫn đọc được.

### Chọn dữ liệu cho công việc tiếp theo

Các đường dẫn dưới đây là cache local đã tải, ngoài Git; checkout mới cần chạy downloader/audit ở trên. Trạng thái code cập nhật 21/10/2026.

| Nguồn trong `data/T0/` | Dùng ngay | Chưa có/không được suy ra |
|---|---|---|
| `raw/benchrec_kaggle/2026-10-19-v3/` | Harness GL–bank và kiểm định kết quả v1 | Invoice allocation truth, availability lịch sử, holdout SME |
| `raw/fixture_research/2026-10-20/finrca/` | Adapter/audit đa bảng AP clean/corrupted, proposals có invariant | Oracle payment–bank/repair allocation chưa xác minh; quyền dataset riêng chưa rõ |
| `raw/fixture_research/2026-10-20/erpnext/` | Hai file test tham chiếu để viết fixture dự án | Native ERPNext/DB chạy được, export doanh nghiệp; demo payment JSON không tải được |
| `raw/fixture_research/2026-10-20/fiscus/` | Chạy bốn fixture bank qua decision store local | 21 ca domain khác, API/concurrency thật |
| `raw/fixture_research/2026-10-20/recbench/` | Adapter/evaluator payout–bank tier small | Ledger/settlement, giải thích 1.047 payout endpoint vắng, evaluator chính thức và unbundling |
| `raw/fixture_research/2026-10-20/finbalance/` | Text → journal giới hạn, detector số học/dependency và replay chart đơn giản | Policy/facts độc lập cho structured engine; kiểm chứng kế toán rộng, main eval và PDF local |
| `processed/reconciliation-v1/invoice-datasets/` | Bộ tình huống AR có oracle và benchmark v1 để hồi quy | Không dùng làm test cho ledger/FX/version hiện hành; tỷ lệ tình huống chưa đại diện SME |

Nguồn fixture giữ policy chỉ nghiên cứu. Khi viết adapter, xuất dataset dẫn xuất riêng có lineage, task/direction, mapping/scale, feature allowlist, split và nhãn tách khỏi input; không sửa raw/manifest để chạy qua gate. FinRCA AP không chạy bằng cách đổi khoản chi thành khoản thu dương. Nếu thiếu truth exhaustive hoặc lịch sử khả dụng, chỉ báo audit/coverage hoặc đánh giá hồi cứu theo đúng phạm vi.

Harness v1 bên dưới chỉ chạy **BenchRec và synthetic AR v1**. Pipeline hiện hành chạy các task bổ sung bằng lệnh ở đầu trang; [khoảng trống dữ liệu và điều kiện hoàn thành](../../research/notes/t0_data_foundation_reconciliation.md#khoảng-trống-dữ-liệu-và-cách-tiếp-tục) vẫn áp dụng.

## Chạy benchmark nghiên cứu và BenchRec

Sau khi tải raw, chạy cả hai task vào thư mục mới hoặc rỗng:

```powershell
python scripts/data_audit/benchmark_t0_reconciliation.py --output data/T0/processed/reconciliation-v1-new
```

Lệnh dùng [kế hoạch v1](../../research/references/data-checks/t0/reconciliation-benchmark-plan-v1.json), không train/tune. Có thể chọn `--only invoice` hoặc `--only benchrec`; task invoice không cần raw BenchRec. Mỗi lần chạy dùng output riêng, kể cả lần trước bị dở dang.

| Output trong thư mục đã chọn | Nội dung |
|---|---|
| `experiment.json` | Cấu hình và hash code, lưu trước dự đoán |
| `report.json`, `evidence.json` | Kết quả từng lượt và bản tổng hợp |
| `invoice-datasets/` | Input tổng hợp, ground truth và manifest |
| `benchrec-predictions/` | Dự đoán GL–bank đã lưu trước khi đọc nhãn chấm |

Đọc `invoice.summary` với `split="test"`, hoặc `benchrec.summary`. Không gộp điểm hai task. Bộ invoice có `clean/noisy/stress`; BenchRec có `original/noisy/stress`, trong đó `original` không được bảo đảm sạch. Tỷ lệ tình huống, mức nhiễu và ngưỡng là cấu hình thử độ nhạy, chưa được ước lượng từ SME.

Nhãn BenchRec do bên phát hành cung cấp, chưa được nhóm gán nhãn lại độc lập. Cách chấm chính chấp nhận một tập con không rỗng của nhóm nhãn đúng; đọc thêm `exact_set_precision`/`exact_set_recall` trong [contract GL–bank](../../docs/reference/t0-data-contracts.md#contract-bổ-sung-benchrec-glbank). Precision cao chưa chứng minh đúng từng ID giao dịch hoặc phân bổ hóa đơn SME. Solution đã được kiểm tra cấu trúc trước thí nghiệm, nên đây chưa phải đánh giá mù.

Kết quả đã chạy được giữ tại `data/T0/processed/reconciliation-v1/`; [bảng kết quả và giới hạn](../../docs/reports/t0-method-review.md#kết-quả-benchmark-v1--19102026), [bằng chứng tổng hợp](../../research/references/data-checks/t0/reconciliation-benchmark-2026-10-19.json). Các baseline này chưa đủ cơ sở tự động ghi sổ.

## Kiểm định lại kết quả đã lưu

```powershell
python scripts/data_audit/benchmark_t0_reconciliation.py --verify-existing data/T0/processed/reconciliation-v1 --output data/T0/processed/verify-v1-new
```

Output phải mới hoặc rỗng. Lệnh kiểm tra hash input/ground truth, chạy lại và đối chiếu metric hóa đơn, chấm lại các bộ dự đoán BenchRec và chạy lại bốn matcher trên BenchRec gốc. Kết quả ghi vào `verification.json`; dữ liệu và báo cáo cũ được giữ nguyên.

## Nguồn tham khảo và khảo sát trước đây

Các khảo sát MoneyVis, CityVizor, National Archives UK, DC PASS và nguồn bổ sung được giữ để truy nguyên quyết định; chúng chưa cung cấp nhãn phù hợp cho matcher hóa đơn. Không dùng các nguồn bị loại để train/tune hoặc xếp hạng phương pháp. Chi tiết nằm ở [note nguồn T0](../../research/notes/t0_data_foundation_reconciliation.md); audit, lỗi truy cập và script tương ứng được tra qua [mục lục bằng chứng](../../research/references/README.md#bằng-chứng-kiểm-tra-dữ-liệu) và [danh sách script](../../docs/reference/repository-structure.md#chọn-script-theo-mục-đích).

[Lệnh tái lập collector lưu trữ](../../docs/reference/repository-structure.md#khảo-sát-t0-đã-lưu-trữ) yêu cầu output mới; tải MoneyVis/khảo sát cũ cần cờ `--download` rõ ràng. Source gate vẫn ở `t0/data.py`, áp dụng cho `reconcile`/`evaluate` như trước.

Để lưu lại nguồn học thuật/nghiệp vụ của kế hoạch hiện tại:

```powershell
python scripts/data_audit/research_t0_reconciliation.py --output data/T0/processed/source-audits/reconciliation-research-new.json
```

Script cần thêm `pypdf`, chỉ tải nguồn/đọc text; không chạy mô hình trong paper. Nó dùng cache tại `data/T0/raw/reconciliation_research/2026-10-19/`, từ chối cache thiếu hoặc sai hash/spec và không ghi đè report. Dùng `--input` mới khi cần snapshot mới. [Nhật ký URL/hash đã lưu](../../research/references/data-checks/t0/reconciliation-research-2026-10-19.json).

Bộ tổng hợp ban đầu và benchmark cũ chỉ còn phục vụ kiểm thử hồi quy/tái lập: [bằng chứng lịch sử lưu trữ](../../research/references/data-checks/t0/archive/benchmark-baseline.json). Vị trí code và phạm vi hồi quy nằm trong [cấu trúc repo](../../docs/reference/repository-structure.md#khảo-sát-t0-đã-lưu-trữ).
