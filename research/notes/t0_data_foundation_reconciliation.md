# T0 — Nền dữ liệu và đối soát

Cập nhật **21/10/2026**. Trang này duy trì định hướng dữ liệu, đánh giá nguồn và [kế hoạch tiếp tục T0](#kế-hoạch-tiếp-tục-t0). [Contract](../../docs/reference/t0-data-contracts.md) duy trì schema/ràng buộc; [README T0](../../data/T0/README.md) duy trì lệnh/output; [báo cáo](../../docs/reports/t0-method-review.md) duy trì số liệu thực nghiệm.

## Ý tưởng nền tảng

T0 liên kết **invoice → allocation → payment ↔ bank transaction**, giữ riêng công nợ và chuyển động tiền. Payment ghi trong ERP chưa chứng minh tiền đã khả dụng tại ngân hàng. Nguồn đã xác nhận mapping được tiếp nhận/kiểm tra; phần thiếu mapping mới dùng matcher để đề xuất, để review nếu không đủ bằng chứng.

Ba lớp dữ liệu là trách nhiệm logic:

- **Bronze:** raw bất biến cùng nguồn, revision/batch, thời điểm nhận và hash; lỗi vẫn giữ nguyên.
- **Silver:** chuẩn hóa tiền/ngày/khóa/hướng AP–AR, lineage và kiểm tra scope/bảo toàn tiền; dòng không hợp lệ được cách ly có lý do.
- **Gold:** trạng thái công nợ/chuyển động tiền theo cutoff, có công thức và lineage. Feature T1 cần contract/nhãn riêng, chưa tự có từ Gold mẫu.

Code v0.4 có adapter FinRCA, typed allocation/FX, SQLite decision ledger/Gold và version invoice/payment bằng event mới. Receipt v0.1 giữ để hồi quy. Revision hiện giữ scope/ngày nghiệp vụ, chưa có sửa mọi loại chứng từ hoặc toàn bộ ERD doanh nghiệp, invoice lines, credit terms, connector và lịch nghĩa vụ. [Contract hiện tại](../../docs/reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal) là nơi duy trì chi tiết.

### Lịch sử và thời điểm biết dữ liệu

Phải tách hiệu lực nghiệp vụ và thời điểm dữ liệu khả dụng. Sửa hiệu lực ngày 10 nhưng nhận ngày 12 không được đi vào snapshot ngày 11. SCD2 theo hiệu lực chưa đủ cho late arrival; nhiều bản export cũng chưa chứng minh thu đủ event ERP. Contract hiện dùng độ phân giải ngày; SQLite sequence giữ thứ tự command.

Credit note giảm nợ nhưng không tạo cash. Gross payment, bank net, phí và refund có tác động riêng; phần chưa xác minh không được cân bằng bằng ghép ép. Giới hạn bank-link/FX và state transition được định nghĩa tại contract, tránh duy trì thêm schema ở đây.

## Nguồn thực và khảo sát đã loại — 19/10/2026

Chưa có corpus invoice–bank SME Việt Nam với nhãn độc lập. BenchRec là dữ liệu **GL–bank thực đã che thông tin theo chủ nguồn**, có snapshot Kaggle v3, adapter và benchmark riêng; [nguồn/lệnh tải](../../data/T0/README.md#benchrec-kaggle--đối-soát-glbank), [kết quả](../../docs/reports/t0-method-review.md#kết-quả-benchmark-v1--19102026). GL không mặc định là invoice; allocation-key không cung cấp nhãn tiền từng cạnh hóa đơn.

Các khảo sát dưới đây không phải input matcher hiện tại. [Mục lục bằng chứng lưu trữ](../references/README.md#bằng-chứng-t0-đã-lưu-trữ) giữ URL, ngày kiểm tra, hash, số liệu/lỗi và code tái lập; không cần duy trì lại toàn bộ thống kê nguồn bị loại trong kế hoạch.

| Nguồn đã khảo sát | Kết luận trong phạm vi đã kiểm tra |
|---|---|
| MoneyVis | Sao kê retail một phía; thiếu invoice, currency xác nhận và nhãn phân bổ; không dùng đánh giá matching hóa đơn |
| CityVizor, National Archives UK, DC PASS | Dòng kế toán/công bố chi, grain và độ đầy đủ khác nhau; chưa có sao kê độc lập và truth invoice–bank. DC cho T1 được đánh giá tại [note nguồn T1](t1_dataset_recommendation.md) |
| Wigan, Open Collective, Berka | Các URL đã thử lỗi truy cập; chưa có audit đủ điều kiện matching, không kết luận mọi kênh tải đều hỏng |
| Ukraine Spending | API đã thử reset/timeout; chưa xác minh khóa nối/chứng từ/nhãn |
| Xero/RMIT | Đã đọc nghiên cứu và repository mô hình; chưa có corpus được cấp quyền. Link arXiv `2506.14516` đã kiểm tra là LiveRAG, không phải bài bank reconciliation |
| DocILE, Bankstatemently | Trích xuất chứng từ hoặc synthetic parsing; không cung cấp truth phân bổ SME theo phạm vi đã kiểm tra |
| MISA/ERPNext schema | Tham chiếu tích hợp; chưa có export doanh nghiệp/connector đã chạy. Ưu tiên mẫu export thật trước API |

Lỗi yêu cầu đăng ký BenchRec trong khảo sát cũ chỉ áp dụng đường Operartis; snapshot Kaggle đã tải thành công sau đó. Không dùng kết luận truy cập cũ để phủ nhận dữ liệu đang có. Không gửi liên hệ hoặc đăng ký thay người dùng trong các lượt khảo sát.

## Mở rộng nguồn fixture và benchmark — 20/10/2026

Script [nghiên cứu nguồn](../../scripts/data_audit/research_t0_fixture_sources.py) đã tải **47 file từ 8 nguồn**, khóa revision và giữ một lỗi HTTP 404. [Bằng chứng](../references/data-checks/t0/fixture-source-research-2026-10-20.json) giữ URL, ngày kiểm tra, byte/hash, license scope và audit. Raw ở `data/T0/raw/fixture_research/2026-10-20/`, ngoài Git. Đợt này chỉ tải/static inspection/audit, chưa chạy matcher; kết quả v0.2 ngày 21/10 được báo riêng.

### Nguồn tải được và phạm vi sử dụng

| Nguồn | Đã tải/kiểm tra bằng code | Giá trị và giới hạn |
|---|---|---|
| [FinRCA-AI-Bench](https://github.com/PratikGhawate/FinRCA-AI-Bench), commit `76c93ec` | 15 file: README/license/taxonomy, 5 bảng `raw_clean`, 5 bảng `benchmark/full`, nhãn **train**. Clean có 8.000 invoice, 6.000 payment, 7.080 allocation và 6.063 bank transaction; bản có lỗi có 8.147/6.200/7.180/6.263 tương ứng | Đã có adapter/audit AP v0.2. Có invoice–payment–allocation–bank và nhãn nguyên nhân lỗi; là **AP synthetic**, không phải AR SME. Repository có MIT cho phần mềm; chưa thấy giấy phép dataset riêng trong các file đã kiểm tra, không tự suy quyền tái phân phối toàn bộ data |
| [RecBench của End Close](https://huggingface.co/datasets/end-close/recbench), revision `8cf65de` | 7 file của tier small: card/manifest, 73.955 payout, 75.138 bank rows, 75.002 cạnh payout–bank và hai bảng nhãn | **Ưu tiên đối soát settlement.** Card tuyên bố synthetic, CC BY 4.0; khác **BenchRec** đã có. Chưa tải ledger/settlement_lines, chưa kiểm tra code generator/evaluator. Số nhỏ/lớn trong card không thay thế số dòng thực đã đếm |
| [FinBalance](https://github.com/Devansh1105/finbalance), commit `a1062b7`; [paper tác giả](https://arxiv.org/abs/2606.15949) | 5 file; parse đầy đủ **143 coverage records**, chứa **2.567 document objects**, gồm 230 `customer_invoice`, 173 `bank_statement`, 212 `payment_advice`, 21 `credit_memo`; có `expected_entries`/`expected_balance_sheet` | Hữu ích cho chứng từ → journal/đối chiếu kế toán. Là **generated benchmark**, chưa phải nhãn tiền từng cạnh invoice–bank. V0.2 có baseline journal/replay chart giới hạn; chưa tải PDF hoặc chạy model/paper. `DATA_LICENSE.md` ghi CC BY 4.0 cho dữ liệu sinh; code Apache-2.0 |
| [ERPNext test Payment Reconciliation](https://github.com/frappe/erpnext/blob/064e673b84ff119ed995f261a5e47446d8259b19/erpnext/accounts/doctype/payment_reconciliation/test_payment_reconciliation.py) và [Bank Transaction](https://github.com/frappe/erpnext/blob/064e673b84ff119ed995f261a5e47446d8259b19/erpnext/accounts/doctype/bank_transaction/test_bank_transaction.py) | Tải license và hai file test, parse AST để liệt kê ca. Code có trả từng phần, credit note, chênh tỷ giá, ứng trước, hủy/sửa liên kết bank | Nguồn kỳ vọng nghiệp vụ, **chưa chạy test gốc**, chưa xuất database. Chạy native cần Frappe/ERPNext và DB. GPL-3.0 cho phần mềm; không phải dữ liệu doanh nghiệp thực |
| [OCA/account-reconcile 18.0](https://github.com/OCA/account-reconcile/tree/18.0), commit `2da3bc0` | License/module manifest, test mass-reconcile và CSV nhập sổ **3 dòng**; parse AST/CSV | Mẫu parser và quy trình lịch sử/duyệt, không phải corpus matcher. Module đã kiểm tra ghi AGPL-3; cần đọc license từng module. Chưa chạy Odoo/PostgreSQL |
| [FISCUS workflow fixtures](https://data.mendeley.com/datasets/w7tk797ngc/1), [bản HF](https://huggingface.co/datasets/keaxe21/fiscus-financial-workflow-state-fixtures), revision `8617823` | **25 JSONL records** thuộc 8 domain; hash JSONL trùng checksum Mendeley công bố. Có 4 ca bank reconciliation | Hữu ích cho idempotency, kết quả nguồn chưa rõ, quyền duyệt và reversal. Là **fixture trạng thái**, không có corpus số tiền để chấm thuật toán matching. Nguồn công bố CC BY 4.0 |
| [Invoice reconciliation sample](https://github.com/RichieGarafola/invoice-reconciliation-tool), commit `ed946c2` | 35 invoice, 33 payment, generator/license; cộng payment theo ID bằng Decimal: 22 paid, 2 partial, 10 unpaid, 1 overpaid; không có payment mồ côi | Fixture nhỏ để thử dư nợ/aging. Payment **đã chứa invoice_id**, không dùng thành feature rồi báo độ chính xác tự tìm invoice. Không có sao kê độc lập. Mẫu constructed, repository MIT |
| [Invoice-payment-matcher](https://github.com/realtonkaa/invoice-payment-matcher), commit `1b1e4a4` | License/README, CSV fixture **4 dòng**, ba invoice `.txt` | Demo parser/khớp, không xác minh là SME thật; chưa có nhãn độc lập đầy đủ. Không chạy matcher/OCR/LLM. Repository MIT; mô tả demo trong README không đồng nhất với CSV fixture đã tải |

**Đính chính link demo ERPNext:** `erpnext/setup/demo_data/payment_entry.json` được trang web đã lập chỉ mục nhắc tới nhưng trả **404 ở commit `064e673`**. Không dùng link nhánh `develop` như một dataset còn tải được. Hai file test ở trên đã tải thành công và có hash; không dùng cache kết quả tìm kiếm để bù file mất.

### Phạm vi audit và cách dùng nhãn

FinRCA có AP clean/corrupted và observed allocations, nhưng chưa xác minh oracle độc lập/exhaustive để chấm tự khôi phục. V0.2 đã bổ sung statement–transaction totals và continuity audit; các chênh lệch và cách phân biệt 147 raw/100 positive overallocated được duy trì tại [báo cáo v0.2](../../docs/reports/t0-method-review.md#finrca-ap-audit-và-đề-xuất-chưa-chấm-khôi-phục). Statement tự cân chưa chứng minh sao kê đầy đủ.

RecBench thiếu 1.047 payout endpoint trong truth; giữ unknown, không đổi thành negative. CSV local có hash riêng, chưa xác minh Parquet release. FinBalance expected journal, FISCUS expected state và nhãn RCA chỉ dành cho audit/evaluator, không làm feature thuật toán. ERPNext/OCA chỉ được đọc tĩnh, chưa chạy native.

Quyền phần mềm không tự cấp quyền phân phối dữ liệu. Đặc biệt dataset FinRCA còn cần làm rõ điều kiện dùng; giữ raw/provenance và xuất dataset dẫn xuất có policy/lineage riêng.

## Kế hoạch tiếp tục T0

M0–M3 đã có triển khai offline trong phạm vi contract; M4–M5 mới hỗ trợ một phần; M6 cần dữ liệu đối tác. Không còn yêu cầu chờ pilot trước khi phát triển offline. Kết quả từng task được giữ riêng, không cộng GL–bank, allocation, workflow và journal thành một accuracy.

### Tiến độ và phần còn thiếu

| Mốc | Đã có trong code | Phần còn thiếu |
|---|---|---|
| M0 | Typed AP/AR, cutoff/idempotency, bank slices/statement; v0.4 thêm FX quote, refund–bank và version giá trị invoice/payment | Availability/quote/carrying SME; sửa scope/ngày nghiệp vụ và các loại chứng từ khác; chargeback |
| M1 | FinRCA mười CSV clean/full được hash-check, chuẩn hóa/lineage/quarantine; split union component cả hai stage; statement equation và so transaction totals theo cả transaction/posted month; fixture AR intent + ledger credit/phí/refund/late arrival/reverse | Oracle bank-link/repair chưa xác minh nên quality `null`; 47 invoice âm cách ly, chưa suy thành credit note; chưa chạy ERPNext native |
| M2 | Baseline/v2 giữ nguyên; v0.4 giải constrained flow qua nhiều ngày trong snapshot, FX remittance tường minh và guard reference mâu thuẫn; 32 lượt robustness cùng test contract mới | N:M còn cap/bằng chứng, không phát hiện mọi reference sai; FX proposal riêng, kiểm tiêu thụ chung khi commit; chưa có SME holdout hoặc split BenchRec mới |
| M3 | SQLite retry/decision/reversal, version guard và cancel stale suggestion; Gold có statement, lịch sử version, FX/refund links; bốn fixture bank FISCUS | Completeness/outcome/quote/carrying do caller cung cấp, chưa có ERP API; thiếu số dư SME/nhãn T1; 21 fixture domain khác chưa hỗ trợ |
| M4 | Payout–bank RecBench có matcher/evaluator riêng, giữ dấu âm và báo unknown endpoint | Ledger/settlement/unbundling, generator/evaluator chính thức và hash Parquet chưa xác minh |
| M5 | Journal structured policy/facts nhiều dòng, VAT khai báo/discount, credit/payment/refund, carrying/FX và trial balance; text baseline thêm supplier/utilities/loan/payroll; detector dependency/tổng/trùng/running balance | Engine structured mới kiểm trên fixture, chưa có corpus SME; text còn sai/recall thấp; thiếu deferred/lease/revaluation, main/PDF/OCR; không tự commit journal |
| M6 | Không có kết quả SME/T1 mới | Vẫn thiếu đối tác/dữ liệu/nhãn/availability và pipeline T1/backtest |

[Lệnh/output v0.4](../../data/T0/README.md#chạy-t0-v04), [contract](../../docs/reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal) và [kết quả thực chạy theo version](../../docs/reports/t0-method-review.md) là tiêu chí đối chiếu phần đã triển khai. Không nhận toàn bộ mốc đã hoàn tất hoặc gọi Gold mẫu là tập train T1.

### Thứ tự công việc tiếp theo

1. **FinRCA:** xác minh mapping/provenance clean–corrupted và oracle allocation/bank-link; giải thích scope/date của statement totals. Nếu chưa đủ nhãn, tiếp tục audit/proposals và giữ matching quality `null`.
2. **Allocation AR:** v0.4 đã giải khác ngày trong snapshot và FX tường minh; tiếp tục reference sai nhưng tự nhất quán, remittance thiếu và component lớn. Giữ baseline và dữ liệu ngoài mẫu độc lập khi có; không tune theo test đã xem.
3. **Ledger/Gold:** kiểm định quote/carrying/version/refund links trên export có nguồn, số dư đầu kỳ và completeness. Sửa scope/ngày/loại chứng từ khác, connector/API/concurrency thật cần thiết kế riêng.
4. **M4–M5:** bổ sung RecBench ledger/settlement cùng oracle trước unbundling; nối export quan sát vào structured journal mà không lấy policy từ nhãn, kiểm định các chính sách chưa hỗ trợ. Text coverage còn yếu, detector metric chưa tăng trên FinBalance đã xem. Chưa cần OCR/LLM để tiếp tục allocation.
5. **M6 song song:** tìm pilot/export có nhãn và lịch sử availability; sau đó mới kiểm định lợi ích thực tế và tác động T1.

Allocator hiện hành dùng max-flow có kiểm nghiệm duy nhất để giải nhóm reference/amount đã xác định; không tối ưu chi phí từ nhãn. Chỉ thử min-cost flow hoặc MILP/CP-SAT khi phân tích lỗi và nhãn cho thấy cần; giữ cùng ngân sách thời gian, báo timeout/overflow. Không tăng cap/hạ ngưỡng theo test đã xem rồi gọi là cải thiện độc lập.

### Điều kiện đánh giá

Contract duy trì feature allowlist, scope/tiền/cutoff, universe và metric theo task. Các ràng buộc cần giữ khi mở rộng:

- Clean/corrupted và biến thể của cùng thế giới/connected component ở cùng split; không dùng allocation corrupted/reference join làm đáp án tự xác nhận.
- BenchRec eval/v1, AR v2, FinRCA full, RecBench small, FinBalance coverage và FISCUS đã được xem trong phát triển/hồi quy; không gọi là holdout mù. Nhãn RCA test/challenge chưa mở cũng chưa chứng minh pool độc lập với full đã audit.
- Báo cả tổng universe, phần đủ endpoint, unknown và unsupported. Chỉ báo chất lượng tự ghép khi oracle phù hợp/đủ nhãn; tỷ lệ auto không phải precision.
- Lưu cấu hình trước dự đoán, hash raw/normalized/code, split, seed, budget, môi trường và artifact. Không ghi đè bằng chứng cũ hoặc tháo source gate để chạy raw nghiên cứu.

Mục tiêu kỹ thuật là không vi phạm scope/bảo toàn tiền, không ghi lặp khi retry và không dùng dữ liệu tương lai trong phạm vi kiểm thử. Đây chưa là bảo đảm ngoài mẫu; precision chấp nhận tự động hóa và runtime cần chốt theo validation/rủi ro thực tế. Seed lặp không tạo thêm doanh nghiệp.

### Khoảng trống dữ liệu và cách tiếp tục

| Thiếu gì hiện nay? | Vẫn làm được ngay | Cần bổ sung trước khi tuyên bố hoàn thành |
|---|---|---|
| Invoice–bank AR SME Việt Nam có nhãn positive/null/unknown độc lập | M0–M5 offline; AR capability bằng synthetic, AP bằng FinRCA | Pilot có quyền dùng, cùng đơn vị/kỳ; kế toán xác nhận mapping/điều chỉnh và phạm vi quan sát |
| Payment–bank oracle và nhãn nhóm đầy đủ | Audit reference, endpoint, scope và candidate coverage | Nhãn nguồn hoặc sự kiện xác nhận liên kết; nếu không có, giữ task audit, không tự sinh truth bằng matcher |
| Số dư đầu kỳ, sao kê đầy đủ và công nợ đầu kỳ trong phạm vi mục tiêu | Kiểm tra phương trình statement FinRCA; dựng balance trong mô phỏng | Đối chiếu statement với transaction theo account/currency/kỳ, liên tục opening–closing và sổ công nợ; dòng statement tự cân chưa đủ |
| Receipt/availability và lịch sử sửa/đảo thực tế | Fixture late arrival/reversal, snapshot/replay mô phỏng | Export lặp hoặc log nhận/event có timestamp; export cuối kỳ không khôi phục được thông tin đã biết trong quá khứ |
| Tần suất partial/fee/FX/refund, mô tả bank và lỗi dữ liệu thực | Sensitivity grid và tập ca cân bằng | Mẫu SME đại diện và xác nhận cơ chế; không gán tần suất generator thành tần suất thị trường |
| Một số bảng/điều kiện dùng đã nêu ở M1/M4/M5 | Tiếp tục nguồn/bảng hiện đã audit; giữ provenance và phần chưa chạy | Làm rõ quyền dataset FinRCA; tải/audit RecBench ledger/settlement; xác minh oracle, evaluator và FinBalance main/PDF khi cần |

Pilot khám phá đề xuất **2–3 tháng**: hóa đơn/công nợ đầu kỳ, payments và allocations, sao kê kèm opening/closing, bank links nếu có, credit note/phí/FX/refund và các lần sửa/đảo. Giữ cả hóa đơn chưa trả, bank-only và ca chưa rõ; xin lịch sử nhận theo đợt thay vì chỉ một export cuối kỳ. Đây là phạm vi thu thập ban đầu, không phải số mẫu đủ để chứng nhận production. Cần thêm kỳ và doanh nghiệp độc lập trước khi suy rộng.
