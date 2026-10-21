# Tài liệu và mã tham khảo

| Thư mục | Mục đích |
|---|---|
| `bibliography/` | Danh mục đọc có chú giải và BibTeX để trích dẫn |
| `data-checks/` | Bằng chứng kiểm tra dữ liệu, chia theo phạm vi task; không phải input huấn luyện |
| `papers/` | Bản PDF nguyên gốc và manifest tải paper |
| `code/` | Mã tham khảo bên ngoài, tách khỏi script vận hành của repo |

Giữ các file có vai trò trích dẫn, đối chiếu kết quả hoặc truy nguyên nguồn. Kết quả mẫu, audit toàn bộ và nhật ký toàn vẹn có phạm vi khác nhau; không coi chúng là các bản sao thay thế cho nhau.

## Bằng chứng kiểm tra dữ liệu

Lệnh chạy và đường dẫn dữ liệu: [T0](../../data/T0/README.md), [T1](../../data/T1/README.md), [quy trình audit T1](../../docs/how-to/audit-t1-data.md). Bảng dưới là mục lục bằng chứng; kết luận từng nguồn, [kế hoạch và tiến độ T0](../notes/t0_data_foundation_reconciliation.md#tiến-độ-và-phần-còn-thiếu) được duy trì tại note T0. Audit nguồn, cấu hình thí nghiệm và kết quả chạy phương pháp là các loại bằng chứng khác nhau.

Bằng chứng T0 hiện dùng nằm trong `data-checks/t0/`; khảo sát nguồn bị loại và benchmark ban đầu ở `data-checks/t0/archive/`, giữ nguyên byte/hash. Đường dẫn code và đoạn Python bên trong chúng là lịch sử, không phải lệnh hiện hành; tra [code lưu trữ](../../docs/reference/repository-structure.md#khảo-sát-t0-đã-lưu-trữ) khi cần tái lập. Không xóa JSON chỉ vì ngày cũ nếu nó là bằng chứng duy nhất cho một kết luận còn được trích dẫn.

T0 dùng [quy ước tên file](../../docs/reference/repository-structure.md#chọn-script-theo-mục-đích). Mục lục dưới đây dùng tên hiện hành; tên/đường dẫn code trong JSON vẫn là thông tin tại thời điểm chạy. Không viết lại nội dung bằng chứng chỉ để khớp vị trí file mới.

| Bằng chứng | Phạm vi |
|---|---|
| [Rà soát Python/JSON](data-checks/t0/python-json-maintenance-2026-10-21.json) | 204 test (23 ca mới), 50 hash Python, 11 lượt CLI, pipeline 9/9 technical checks và xác minh 222 artifact; giữ JSON lịch sử, không train/chạy API. [Phát hiện và giới hạn](../../docs/reports/t0-method-review.md#rà-soát-pythonjson-và-dọn-code--21102026) |
| [Kế hoạch benchmark v2](data-checks/t0/ar-benchmark-plan-v2.json) | Contract/split/feature/ngân sách AR typed, bốn baseline và ba ablation. Không phải kết quả |
| [Kế hoạch robustness allocation](data-checks/t0/allocation-robustness-plan-v1.json) | So v2 với constrained flow trên reference sai/N:M/remittance và noise; split/allowlist/ngân sách khóa trước chạy |
| [Đánh giá offline v0.4](data-checks/t0/offline-evaluation-v4-2026-10-21.json) | Pipeline trên code khác ngày/FX/version/journal mới, chín check kỹ thuật và hash 222 artifact; journal/detector còn hạn chế. [Kết quả và đánh đổi](../../docs/reports/t0-method-review.md#mở-rộng-nghiệp-vụ-và-journal-v04--21102026) |
| [Kiểm chứng nghiệp vụ/ví dụ v0.4](data-checks/t0/extension-verification-v4-2026-10-21.json) | 181 unittest (33 test mới), hash code/test/log và ví dụ CLI FX/refund/version/structured journal/trial balance; fixture tổng hợp, không phải SME |
| [Đánh giá offline v0.3](data-checks/t0/offline-evaluation-v3-2026-10-21.json) | 56 lượt v2 và 32 lượt robustness, source tasks/ledger và hash 222 artifact; gate kỹ thuật/chất lượng riêng. [Kết quả và giới hạn](../../docs/reports/t0-method-review.md#sửa-lỗi-và-mở-rộng-v03--21102026) |
| [Kiểm định v1 sau mở rộng v0.3](data-checks/t0/reconciliation-verification-after-v3-2026-10-21.json) | Xác minh lại 84 lượt invoice, 60 bộ dự đoán và bốn matcher BenchRec với code mới; không ghi đè lịch sử hoặc tune |
| [Đánh giá offline v0.2](data-checks/t0/offline-evaluation-2026-10-21.json) | 56 lượt AR, audit/proposal FinRCA, payout–bank RecBench, journal giới hạn FinBalance, bốn fixture FISCUS và Gold local; hash code/124 artifact. [Kết quả và giới hạn](../../docs/reports/t0-method-review.md#kết-quả-offline-v02--21102026) |
| [Rà soát code trước sửa v0.3](data-checks/t0/code-review-2026-10-21.json) | Snapshot 124 test và probe validation ngày/reference/điều chỉnh trước sửa. [Phát hiện lịch sử và giới hạn phạm vi](../../docs/reports/t0-method-review.md#rà-soát-mức-độ-đầy-đủ-của-code--21102026) |
| [Nguồn nghiên cứu reconciliation](data-checks/t0/reconciliation-research-2026-10-19.json) | Chín nguồn học thuật/nghiệp vụ và tám PDF sẵn có: URL, thời điểm, hash. [Tổng hợp và ánh xạ kịch bản](../../docs/reports/t0-method-review.md#cơ-sở-nghiên-cứu) |
| [Kế hoạch benchmark v1](data-checks/t0/reconciliation-benchmark-plan-v1.json) | Cấu hình khóa trước lượt chấm mới: seed, mức nhiễu, bốn baseline GL–bank, cơ sở và giới hạn. Không phải kết quả thí nghiệm |
| [Audit nhóm train BenchRec](data-checks/t0/benchrec-train-semantics-2026-10-19.json) | Kiểm tra tổng tiền có dấu, scope và nhãn theo matchId lịch sử trên train; ghi chênh lệch, không sửa raw hoặc dùng eval để chọn rule |
| [Benchmark nghiên cứu: invoice và BenchRec](data-checks/t0/reconciliation-benchmark-2026-10-19.json) | 84 lượt hóa đơn tổng hợp + 60 lượt GL–bank thật/biến đổi nhiễu, kèm replay; hash/config, quality, runtime và so sánh ghép cặp. [Bảng kết quả và giới hạn](../../docs/reports/t0-method-review.md#kết-quả-benchmark-v1--19102026) |
| [Rà soát và kiểm định lại T0](data-checks/t0/reconciliation-verification-2026-10-19.json) | Xác minh input/ground truth, 84 lượt hóa đơn, 60 bộ dự đoán và chạy lại bốn matcher BenchRec gốc; giữ kết quả lịch sử. [Giới hạn receipt v0.1](../../docs/reference/t0-data-contracts.md#giới-hạn-đường-receipt-v01) |
| [Fixture và benchmark T0 bổ sung](data-checks/t0/fixture-source-research-2026-10-20.json) | 47 file khóa revision từ 8 nguồn; static AST và audit CSV/JSONL synthetic, giữ một lỗi 404. Không chạy matcher/ERP hoặc bổ sung corpus SME thật. [Đánh giá và giới hạn](../notes/t0_data_foundation_reconciliation.md#mở-rộng-nguồn-fixture-và-benchmark--20102026) |
| [Kiểm tra khả năng truy cập T1–T8](data-checks/t1-t8/data_sources_t1_t8_access_checks.json) | Tình trạng nguồn khi rà soát |
| [Kiểm tra sâu dataset T1](data-checks/t1/t1_dataset_deep_checks.json) | URL, field và nhật ký kiểm tra nguồn |
| [Profile mẫu](data-checks/t1/t1_dataset_sample_profiles.json) | Kết quả mẫu lịch sử, gồm mẫu Séc đã được thay bằng bản tải đầy đủ |
| [Audit toàn bộ hai nguồn Séc](data-checks/t1/czech_t1_full_audit.json) | Thống kê và gate; [diễn giải kết quả](../notes/t1_czech_full_dataset_audit.md) |
| [Kiểm chứng tải và sắp xếp](data-checks/t1/czech_t1_full_verification.json) | Bản ghi kiểm tra lịch sử cho snapshot 2026-10-18; không phải kết quả chạy lại của checkout hiện tại |
| [Nhật ký tổ chức dữ liệu](data-checks/t1/t1_data_organization.json) | Lưu hash các file giữ lại và dấu vết hợp nhất metadata/chuyển dữ liệu ngày 19/10/2026 |

### Bằng chứng T0 đã lưu trữ

| Bằng chứng | Lý do giữ |
|---|---|
| [Link Kaggle/arXiv người dùng cung cấp](data-checks/t0/archive/user-links-2026-10-19.json) | Nhật ký truy cập ban đầu; metadata Kaggle đã được bổ sung bằng snapshot/audit BenchRec hiện dùng. arXiv 2506.14516 là LiveRAG, khác nghiên cứu bank reconciliation |
| [BenchRec Kaggle: structural preflight](data-checks/t0/archive/benchrec-kaggle-preflight-2026-10-19.json) | Audit nhóm train đã chứa lại cùng profile và identity checks, bổ sung kiểm tra nhóm. Giữ bản trước để truy nguyên thời điểm/hash audit, không dùng như kết quả độc lập thứ hai |
| [Benchmark tổng hợp ban đầu](data-checks/t0/archive/benchmark-baseline.json) | Mốc hồi quy/lịch sử; harness hiện tại dùng kế hoạch reconciliation v1 riêng |
| [Audit MoneyVis](data-checks/t0/archive/moneyvis-source-audit.json) | Bằng chứng loại nguồn retail một phía, kiểm tra phương trình số dư |
| [Khảo sát nhiều nguồn](data-checks/t0/archive/real-source-survey-2026-10-19.json) | Grain, lỗi dữ liệu và giới hạn CityVizor/National Archives/DC; không đủ nhãn invoice–bank |
| [Nghiên cứu nguồn bổ sung](data-checks/t0/archive/additional-source-research-2026-10-19.json) | Truy cập/provenance/schema của sáu hướng cũ, chưa phải dataset nghiệp vụ |
| [Lần thử truy cập lại](data-checks/t0/archive/access-followup-2026-10-19.json) | Lỗi Ukraine và đường Operartis cần đăng ký tại thời điểm thử; không áp dụng kết luận đó cho snapshot Kaggle đã tải sau này |

Đọc kết quả AR v2 của `run-offline` tại `<output>/ar/report.json`, robustness tại `<output>/robustness/report.json`, còn harness invoice/BenchRec v1 ghi `<output>/report.json`. Chọn đúng task, split/profile/method trước khi so sánh; cấu trúc metric và đường dẫn đầy đủ nằm trong [hướng dẫn T0](../../data/T0/README.md). `processed/benchmark/benchmark.json` thuộc generator ban đầu đã lưu trữ, không phải kết quả CLI hiện hành.

Script audit T1 chỉ ghi lại JSON audit/profile tương ứng trong `data-checks/t1/`; các file kiểm tra truy cập và nhật ký lịch sử còn lại được giữ để đối chiếu, không tự tái tạo bằng hai script audit. Khi chuyển các file bằng chứng, giữ nguyên nội dung JSON để bảo toàn provenance.

## Paper và mã tham khảo

Xem thêm [danh mục 8 paper cho T0](bibliography/t0_reading_list.md): kiến trúc dữ liệu, temporal history, chất lượng dữ liệu và đối soát. Có bản PDF trong `papers/t0/`, [manifest nguồn tải](papers/t0/manifest.json) và [BibTeX](bibliography/t0_references.bib).

Các PDF và mã R dưới đây là tài liệu bên ngoài được lưu trong dự án. Tên file được đặt lại theo tiêu đề/chủ đề đọc từ tài liệu; nội dung file được giữ nguyên.

| Tài liệu | Liên quan |
|---|---|
| [Regression Quantiles](papers/regression_quantiles.pdf) | Nền tảng hồi quy phân vị |
| [LightGBM: A Highly Efficient Gradient Boosting Decision Tree](papers/lightgbm_efficient_gradient_boosting.pdf) | Thuật toán boosting dùng cho dự báo phân vị |
| [Conformalized Quantile Regression](papers/conformalized_quantile_regression.pdf) | Hiệu chỉnh khoảng dự báo |
| [Invoice level forecasting with discrete survival methods for effective forecasting of account receivables in supply chain](papers/invoice_forecasting_discrete_survival.pdf) | Dự báo thời điểm trả bằng survival; [mã R đi kèm](code/invoice_forecasting_discrete_survival.R) |
| [A framework for modelling customer invoice payment predictions](papers/customer_invoice_payment_prediction_framework.pdf) | Khung dự báo thanh toán, survival và Survival-Boost |
| [Predicting late payment of sales invoices with statistical learning methods](papers/predicting_late_payment_sales_invoices.pdf) | Luận văn về dự báo trả chậm và đối chứng theo lịch sử khách |
| [Selective review of offline change point detection methods](papers/offline_change_point_detection_review.pdf) | Phát hiện điểm gãy và công cụ `ruptures` |

Mã R là mã tham khảo của bài báo, không phải một bước trong pipeline notebook Python. Khi chạy riêng, cần chuẩn bị dữ liệu, gói R và đường dẫn theo yêu cầu của script gốc.
