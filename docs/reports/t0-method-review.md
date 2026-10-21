# Kết quả và đánh giá T0

Báo cáo duy trì kết quả v0.4/v0.3/v0.2 ngày **21/10/2026**, cùng benchmark v1 ngày **19/10/2026**. Các bảng lịch sử giữ theo snapshot. [Kế hoạch tiếp tục](../../research/notes/t0_data_foundation_reconciliation.md#kế-hoạch-tiếp-tục-t0), [contract](../reference/t0-data-contracts.md) và [lệnh/output](../../data/T0/README.md) được duy trì riêng. Chưa có kiểm định SME Việt Nam hoặc bằng chứng cải thiện T1.

## Rà soát Python/JSON và dọn code — 21/10/2026

Lượt bảo trì sau mốc v0.4 sửa lỗi đọc dữ liệu và ca biên, không thay plan/ngưỡng benchmark. [Bằng chứng mới](../../research/references/data-checks/t0/python-json-maintenance-2026-10-21.json) giữ hash 50 file Python, JSON cũ, test/log và kiểm độc lập 222 artifact của lượt chạy tại `data/T0/processed/python-json-review-2026-10-21/`. Không ghi đè JSON hoặc output thí nghiệm lịch sử.

- JSON/JSONL từ chối khóa trùng/nonfinite và báo vị trí lỗi; CSV adapter/BenchRec chặn header trống/trùng/lặp và dòng mất field. Chuyển Decimal→minor-unit không còn bị context làm tròn số lớn. Assignment từ chối trọng số không hữu hạn để tránh solver treo hoặc trả kết quả vô nghĩa.
- Journal giữ dependency khi nhận lại cùng chứng từ, chặn cả hai invoice mâu thuẫn tổng, kiểm tài khoản cho phép và không bỏ phần debit/credit chưa cân. Ledger từ chối metadata allocation mâu thuẫn endpoint và due date trước issue date. [Contract hiện hành](../reference/t0-data-contracts.md#quy-tắc-đọc-dữ-liệu-và-sửa-lỗi-v04).
- Downloader Séc kiểm SHA256 cache trước khi resume và giữ raw cũ khi response thay đổi; profile mẫu xử lý số/ngày lỗi và buyer null. Đây là test response/fixture local, không gọi lại API hoặc viết lại audit nguồn Séc.
- Helper survival tham khảo xử lý input rỗng/event ngoài horizon, dùng cùng bin width khi suy luận, kiểm xác suất model và sửa median tại plateau 0,5. Có bốn test fixture; chưa train hoặc dựng lại notebook, nên output lịch sử chưa phản ánh các sửa này.

Đã gộp implementation CSV, parser JSON/JSONL vận hành và identity journal; bỏ import không dùng. Không tìm thấy module Python nào đủ bằng chứng là không còn dùng để xóa: các baseline/generator/script lưu trữ vẫn có caller, test hoặc vai trò tái lập. Hai fixture dương cũ được sửa để khai báo đúng tenant/tài khoản; giữ test chống input sai riêng.

**204/204 unittest đạt**, gồm **23 ca hồi quy mới**. Checker Python/JSON mới trong CI kiểm 50 `.py`, 30 `.json`, bốn `.jsonl` và không thực thi code được quét; checker tài liệu đạt. Test module mới với `python -S` chạy 19 ca đạt và skip nhóm helper cần numpy/pandas. Cả 11 lượt gọi CLI mẫu và assertion đầu ra đạt, gồm ledger nhập lại nguyên key, Gold trước/sau revision, FX, journal/trial balance, generate/allocate và receipt reconcile/evaluate. Audit offline tám nguồn fixture đọc được cache; vẫn giữ một access gap ERPNext đã có.

Pipeline offline trên cache hiện có đạt **9/9 technical checks**, technical exit 0 và quality exit 4; hash 19 module T0 và 222 artifact khớp sau chạy. Metric FinBalance journal/detector giữ nguyên so với mốc v0.4 bên dưới; không nhận là tăng chất lượng nguồn. Checker chỉ quét file repo duy trì, bỏ raw/interim/processed, dependency và code bên ngoài. Chưa chạy train/notebook, live API/ERP/bank hoặc kiểm định SME; không cam kết mọi lỗi tiềm ẩn đã được loại bỏ.

## Mở rộng nghiệp vụ và journal v0.4 — 21/10/2026

V0.4 bổ sung cả hai nhóm công việc: N:M qua nhiều ngày **trong snapshot đã biết**, FX có quote rational minor-unit/half-even và hai amount độc lập, refund–bank chia dòng, revision invoice/payment giữ lịch sử/cutoff và chặn decision stale. Journal có engine theo policy/facts quan sát, postings nhiều dòng, thuế/discount khai báo, credit/payment/refund, carrying/FX và trial balance; baseline text mở thêm supplier/utilities/loan/payroll. Detector thêm dependency/overflow/tax-component/duplicate, running bank balance và phương trình loan/payroll. [Contract v0.4](../reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal) là nơi duy trì schema/chính sách/giới hạn.

Lượt kiểm chứng của mốc mở rộng v0.4: `python -m t0 run-offline --output data/T0/processed/offline-v4-2026-10-21-verified --gate technical`, giữ nguyên cache raw và plan benchmark. [Bằng chứng pipeline v0.4](../../research/references/data-checks/t0/offline-evaluation-v4-2026-10-21.json) khóa hash code và **222 artifact**; chín check kỹ thuật đạt, gate technical exit 0, quality exit 4, `production_ready=false`. Các output v3/v2/v1 không ghi đè. Không thay ngưỡng/cap sau khi đọc metric; suite đã xem, không gọi là holdout mù.

**181 test đạt**, thêm 33 test contract cho khác ngày/cutoff, FX so với Decimal half-even độc lập, bảo toàn tiền hai currency/reverse, split refund/shared bank budget, revision/history/persistence/stale/unknown, journal nhiều dòng/dependency/carrying/credit tax/không dùng nhãn và CLI. [Bằng chứng kiểm thử/ví dụ](../../research/references/data-checks/t0/extension-verification-v4-2026-10-21.json) giữ hash test, input tổng hợp, log và output CLI. Các [ví dụ v0.4](../../data/T0/examples/v04/) đã chạy: FX 100 USD cents→25.000 VND; ledger 11 command với refund đã link và invoice revision 100→120 chỉ hiện từ 01/02; journal hai posting/ba entry và trial balance cân. Đây là fixture tự viết, chưa phải dữ liệu SME.

### Kết quả và đánh đổi

| Journal FinBalance development, 143 records / 1.873 expected entries | v0.3 | v0.4 |
|---|---:|---:|
| Entry dự đoán / đúng | 90 / 54 | 255 / 156 |
| Precision | 60,00% | 61,18% |
| Recall toàn pool | 2,88% | 8,33% |
| Record đúng toàn bộ journal | 10 | 4 |

Coverage entry tăng nhờ extractor text mới nhưng số entry sai cũng tăng từ 36 lên 99 và exact journal giảm. Vì vậy **không nhận là cải thiện mọi chiều hoặc đủ để tự ghi sổ**. Structured policy engine chưa có những fact/policy độc lập trong corpus FinBalance này; phần mới được kiểm bằng contract fixture, không dựng fact từ expected entries để tăng điểm. Replay balance sheet hẹp vẫn 1/2 record đúng.

Detector trên cùng FinBalance development vẫn **8 TP, 3 FP**, 15 positive và 117 negative abstain: precision 72,73%, recall toàn pool 34,78%, decision coverage 7,69%. Các check mới có test nhưng **chưa cải thiện metric nguồn này**. Không gọi arithmetic detector là broad accounting classifier; thiếu policy hoặc dependency trả unknown, không coi là negative.

Robustness test mean của `constrained_flow` trên plan cũ (hai seed/profile), precision/recall: clean **100/65,22%**, masked **100/52,72%**, noisy **100/61,14%**, stress **100/50,54%**. Ghép component khác ngày tăng ràng buộc và có thể làm cả nhóm chuyển review; không bảo đảm recall tăng ở mọi profile (v3 masked 54,08%, stress 49,46%). Fixture N:M khác ngày độc lập kiểm đúng ba cạnh 40/30/30; snapshot trước payment cuối vẫn abstain, không dùng thông tin tương lai.

FinRCA proposals auto clean/corrupted là **2.521/2.393**, thấp hơn v3 2.623/2.523 do giải component chung; invariant đạt nhưng matching quality vẫn `null`, không gọi giảm/tăng auto là giảm/tăng độ đúng. RecBench giữ 73.828/73.828 link đúng trong universe đủ endpoint; FISCUS giữ 4/4 ca bank. Gold demo kiểm thêm refund–bank, không tạo cash hai lần.

### Giới hạn còn lại

N:M vẫn có cap và phụ thuộc reference/remittance; FX chỉ dùng quote/carrying đã cung cấp, chưa có rate feed, revaluation hoặc bộ tối ưu chung cùng/khác currency. Revision giữ scope/ngày gốc, chưa sửa mọi loại chứng từ. Refund–bank chưa có connector xác minh thật. Journal thiếu deferred revenue/lease/deferred tax và nhiều policy kế toán; text recall thấp, detector chưa vượt chất lượng cũ. Cần export/nhãn/policy/availability SME độc lập để kiểm chứng; chưa chạy PDF/OCR/main eval hoặc pipeline T1. Các hạn chế này là phần chưa hoàn tất, không được che bằng việc test kỹ thuật đạt.

## Sửa lỗi và mở rộng v0.3 — 21/10/2026

**Snapshot v0.3.** Các giới hạn khác ngày/FX/refund–bank/version/journal được mở rộng tại v0.4 phía trên; số liệu dưới giữ nguyên lịch sử.

Đã sửa validation ngày input trước lọc cutoff, chặn credit note/refund/bank link có hiệu lực trước endpoint và parser settlement không còn ép float/bool thành tiền nguyên. Đường `allocate`/proposals FinRCA mặc định dùng `constrained_flow`; vẫn có `--method v2` để hồi quy. Thuật toán mới giải integer max-flow và kiểm nghiệm duy nhất theo connected component có cap, hỗ trợ N:M cùng ngày và partial group có remittance số tiền quan sát; reference đơn có nghĩa vụ tương đương chuyển review. Ledger hỗ trợ bank link chia dòng và statement equation/totals/continuity với completeness do caller khai báo. [Contract và giới hạn](../reference/t0-data-contracts.md#phần-mở-rộng-v03--phân-bổ-có-nghiệm-duy-nhất-và-gate) duy trì chi tiết, không coi nghiệm duy nhất là bằng chứng dữ liệu đầu vào luôn đúng.

Chạy `python -m t0 run-offline --output data/T0/processed/offline-v3-2026-10-21-final --gate technical`, hoàn toàn bằng cache local. [Bằng chứng v0.3](../../research/references/data-checks/t0/offline-evaluation-v3-2026-10-21.json) giữ hash code/plan, môi trường và **222 artifact**: 56 lượt suite v2 và 32 lượt robustness mới, mỗi lượt kiểm đảo input, cùng các task nguồn/ledger riêng. **148 test đạt**, gồm oracle vét cạn độc lập cho 1.296 bài toán flow nhỏ, regression cutoff, scope, remittance, bank slices, statement, late arrival, detector và gate. Bộ robustness đóng cấu hình trước lượt chạy, không thay ngưỡng/cap theo metric test; đây là phát triển/hồi quy tổng hợp, chưa phải thử nghiệm mù.

Bảng dưới là mean test của **cùng bộ robustness mới**, hai seed mỗi profile, chấm đúng cả cạnh và số tiền; không so trực tiếp với điểm của suite v2/v1 khác universe. Mỗi ô precision / recall (%):

| Phương pháp | clean | masked | noisy | stress |
|---|---:|---:|---:|---:|
| v2_full | 91,67 / 47,83 | 95,15 / 42,66 | 92,96 / 50,27 | 93,21 / 41,03 |
| constrained_flow | 100 / 65,22 | 100 / 54,08 | 100 / 61,68 | 100 / 49,46 |

Trên clean, test của flow đúng **48/48 cạnh `unique_nm`** và **32/32 cạnh `explicit_partial_group`**, so với 16/48 và 0/32 của v2. Cả hai phương pháp giữ recall 0 ở các ca partial/nhóm không xác định được; flow review reference nhầm sang hóa đơn tương đương, không ép thành positive. Flow có 0 tiền gán sai theo từng currency trong suite; không suy precision 100% thành bảo đảm SME. Noise ngày có thể tách component qua ngày, làm giảm recall; N:M khác ngày còn ngoài phạm vi solver. Tiền thừa chưa có chỉ định vẫn giữ unapplied.

FinRCA proposals clean/corrupted vẫn 2.623/2.523 auto; matching quality vẫn `null` vì chưa có oracle độc lập phù hợp. RecBench vẫn đúng 73.828/73.828 link, recall 99,828% trong universe đủ endpoint. FISCUS 4/4 ca bank đạt. Demo statement có opening 500, net movements 880 và closing 1.380, đúng tổng credits/debits; không tự coi snapshot doanh nghiệp là đầy đủ. Kiểm thử split bank bảo toàn cả gross/net/fee cho AP và AR, và nhiều payment cùng bank.

FinBalance giữ baseline journal 54/90 entry đúng trong 1.873 expected entries (precision 60%, recall 2,88%). Detector inconsistency mới kiểm số học USD khai báo (line/subtotal/tax/bank), identity và trả unknown khi chưa đủ policy. Trên **coverage development đã xem**, có **8 TP, 3 FP, 15 positive và 117 negative abstain**: precision **72,73%**, recall toàn pool **34,78%**, decision coverage **7,69%**. Không có kết luận broad consistency hay tự ghi sổ; detector này còn yếu, không kiểm luật thuế hoặc các policy lease/FX/deferred tax. Nhãn/scenario/validation metadata không được predictor dùng. Development inspection và cải thiện detector được tách khỏi test tổng hợp allocation.

`assessment` ghi mọi gate kỹ thuật đạt, execution đủ cache, nhưng **quality/evidence chưa hoàn tất**, `production_ready=false`; gate quality trả 4. Thiếu nguồn trả 3 được kiểm bằng runner local thật. Các phát hiện của lượt audit phía dưới đã được xử lý ở đường mặc định v0.3 hoặc biến thành guard/gate có test; baseline v2 vẫn giữ hành vi lịch sử để so sánh. FX, refund–bank verification, sửa chứng từ nhiều version, connector, dữ liệu SME và pipeline T1 vẫn chưa được bổ sung giả định. Tiến độ tiếp tục được duy trì tại kế hoạch T0.

Đã chạy thêm `--verify-existing data/T0/processed/reconciliation-v1 --output data/T0/processed/verify-v1-after-v3-2026-10-21`: **84 lượt invoice, 60 bộ dự đoán BenchRec và bốn matcher BenchRec gốc được kiểm định lại**, giữ nguyên metric/hash dự đoán, không sửa file lịch sử hoặc tune. [Bằng chứng hồi quy sau v0.3](../../research/references/data-checks/t0/reconciliation-verification-after-v3-2026-10-21.json) khóa hash code xác minh.

## Kết quả offline v0.2 — 21/10/2026

**Snapshot v0.2, trước các mở rộng v0.3/v0.4.** Mốc này đã chạy đường offline của kế hoạch M0–M3, cùng nhánh payout–bank M4 và baseline journal giới hạn M5. [Contract typed](../reference/t0-data-contracts.md#contract-v02--invoicepayment-và-ledger-offline), [hướng dẫn CLI hiện hành](../../data/T0/README.md#output-offline-và-lệnh-thành-phần) và [tiến độ](../../research/notes/t0_data_foundation_reconciliation.md#tiến-độ-và-phần-còn-thiếu) được duy trì riêng. Giới hạn và metric bên dưới chỉ mô tả lần chạy này; không có thêm dữ liệu SME, huấn luyện hoặc kết quả T1 mới.

Lệnh đã chạy: `python -m t0 run-offline --output data/T0/processed/offline-v2-2026-10-21-verified`, dùng cache khóa revision ngày 20/10 và [cấu hình v2](../../research/references/data-checks/t0/ar-benchmark-plan-v2.json). [Bằng chứng kết quả](../../research/references/data-checks/t0/offline-evaluation-2026-10-21.json) giữ hash code, môi trường, raw manifest/provenance và **124 artifact** trong lượt chạy.

Sau lượt chạy này, tên script/cấu hình/bằng chứng T0 được chuẩn hóa và import thừa được bỏ; JSON bằng chứng giữ nguyên byte, gồm cả đường dẫn/hash tại thời điểm chạy. Các số liệu dưới đây thuộc snapshot đã ghi, chưa phải kết quả chạy lại sau đợt dọn file. [Vị trí code và quy ước tên hiện tại](../reference/repository-structure.md#chọn-script-theo-mục-đích).

### AR invoice–payment: baseline và ablation

Bộ v2 tách invoice number/ID, payment gross/bank net, obligation sau credit đã biết và cutoff mô phỏng; oracle sinh từ intent trước khi che reference. Mỗi split có hai seed, hai profile và bảy phương pháp, tổng **56 lượt**. Đây là bộ mới khác v1, nên không so trực tiếp điểm với bảng ngày 19/10. Các seed đã được xem trong quá trình phát triển/kiểm tra, không nhận là holdout mù. Không chọn lại threshold bằng test.

Bảng lấy mean **test**, mỗi ô precision / recall (%) chấm cả cạnh lẫn số tiền chính xác:

| Phương pháp | clean | masked |
|---|---:|---:|
| exact_reference | 100 / 23,08 | 100 / 12,02 |
| amount_date | 100 / 23,08 | 100 / 23,08 |
| scored_global | 100 / 23,08 | 100 / 23,08 |
| reference_then_global | 100 / 53,85 | 100 / 40,38 |
| v2_no_amount_groups | 100 / 61,54 | 100 / 41,83 |
| v2_no_overpayment | 100 / 69,23 | 100 / 62,50 |
| v2_full | 100 / 76,92 | 100 / 66,83 |

Ablation `v2_no_amount_groups` chỉ bỏ subset amount-only, vẫn giữ nhóm reference rõ. V2 tăng coverage nhờ xử lý tiền thừa có reference và subset duy nhất trong block party. Partial group chưa rõ số tiền từng invoice, ambiguous và overflow chuyển review; tiền thừa giữ unapplied. Tất cả lượt có **0 tiền gán sai trong universe mô phỏng**, 0 invariant errors và output ổn định khi đảo thứ tự input. Không suy precision 100% thành SLA SME: tập nhỏ, party được tách để kiểm cơ chế và phân bố tình huống chủ động cân bằng. Cần thêm dữ liệu/nhãn độc lập, đặc biệt reference sai nhưng hợp lệ và ca tranh chấp thực tế.

### FinRCA AP: audit và đề xuất, chưa chấm khôi phục

Adapter xác minh mười CSV clean/full, giữ lineage dòng/hash và không mở test/challenge RCA. Clean nhận 8.000 invoice, 6.000 payment, 7.080 observed allocation, 6.063 bank và 54 statement. Corrupted có 8.147 invoice nguồn: **8.100 nhận, 47 tổng tiền âm cách ly**, không tự lấy trị tuyệt đối hoặc suy là credit note. 6.200 payment, 7.180 allocation và 6.263 bank được giữ.

Trong corrupted, adapter báo **100 invoice dương partial và 100 invoice dương overallocated**, với 218 allocation rows bị đánh dấu invoice overflow. Phép so Decimal trên toàn raw vẫn báo **147** invoice có allocation sum lớn hơn invoice total, gồm 47 tổng âm; hai số có universe khác nhau và đều được lưu. Không che ca lỗi để tăng điểm. Proposals clean/corrupted lần lượt 2.623/2.523 payment có đề xuất auto theo thuật toán, nhưng **matching quality vẫn `null`** vì chưa xác minh oracle độc lập/exhaustive. Auto không đồng nghĩa đúng hoặc đã commit.

Toàn bộ 54/57 statement tự cân opening + credits − debits = closing, nhưng đối chiếu theo posted month có **18/19** statement chưa khớp transaction totals; theo transaction month là **54/57**. Chưa kết luận nguyên nhân hay scope sao kê đầy đủ. Kết quả chứng minh rằng statement tự cân chưa đủ xác nhận đối soát sổ–bank. Không sử dụng reference join làm bank-link truth.

### RecBench: chỉ payout–bank

Có 73.955 payout và 75.138 bank, trong đó **1.436 payout âm**, được giữ signed minor và kiểm direction; không ép thành receipt dương. Trong 75.002 truth edges, **73.955 nhóm đủ endpoint, 1.047 thiếu payout**; 136 bank là negative được xác nhận bởi label và không có truth. Có thêm 25 bank label nonmatchable nhưng có truth, được báo riêng.

Matcher đề xuất **73.828 link và đúng 73.828** theo oracle nguồn trong universe đủ quan sát: precision **100%**, recall **99,828%**. Không đề xuất trên 1.047 unknown hoặc 161 bank label nonmatchable. Endpoint coverage truth là **98,604%**; không xóa phần thiếu khỏi báo cáo tổng. Kết quả ổn định theo thứ tự input, runtime matcher khoảng 1,07 giây trên môi trường đã lưu. Đây là nguồn synthetic đã xem; chưa tải ledger/settlement, chưa chạy evaluator chính thức hoặc unbundling, không phải invoice allocation/SME.

### Ledger, FISCUS và Gold

SQLite lưu command nguyên payload cùng key, transaction kiểm invariant trước insert. Approval không ghi tiền; external result unknown cần verify trước retry/commit khác hoặc credit/refund có liên quan; cùng key trả sequence/hash cũ. Reverse gỡ đúng allocation gốc một lần. Fixture mẫu kiểm face 1.000, credit 100, gross payment 1.100, bank net 1.080 và fee 20: trước verify còn nợ 900, sau verify còn 0 và unapplied 200. Reverse khôi phục nợ 900, refund 200 dùng credit; cash chuyển động sau bank refund là 880, không suy từ approval.

Cả **4/4 fixture bank reconciliation của FISCUS** đúng status và financial effect qua store local; 21 case domain khác được ghi unsupported. Gold xuất năm cutoff với invoice/payment residual, bank movements và lineage/hash. Unit tests kiểm persistence qua reopen, mismatch key, invalid insert rollback, late arrival, unknown/retry và reversal. Chưa có connector tự xác minh nguồn, ledger chỉnh sửa chứng từ nhiều version, FX/split bank links, số dư bank đầy đủ hoặc chứng nhận concurrency/production. Gold mẫu chưa phải tập train T1.

### FinBalance: baseline journal còn yếu

Trên **143 coverage records**, baseline supplied-text USD/no-tax dự đoán **90 entry, đúng 54** trong **1.873 expected entries**: precision **60%**, recall toàn pool **2,88%**. Có 10 record exact journal; chỉ 2 record đủ phạm vi replay balance sheet và 1 record đúng. Unsupported posting documents được giữ trong mẫu số/decisions; expected output không dùng để tạo prediction. Chưa có inconsistency classifier, quality phần đó là `null`.

Kết quả này **chưa phù hợp tự ghi sổ**. Cần cải thiện kiểm tra inconsistency, chính sách tài khoản/ghi nhận doanh thu, tax/FX và document dependencies trên development trước khi mở test mới. Hiện chưa đọc PDF hoặc chạy OCR, chưa có main eval, và journal baseline không tự commit vào allocation ledger.

## Rà soát mức độ đầy đủ của code — 21/10/2026

**Snapshot trước sửa v0.3.** Các phát hiện và số liệu phía dưới giữ lịch sử; trạng thái xử lý và kiểm chứng mới nằm ở mục v0.3 phía trên.

Lượt này rà soát code T0 trước sửa v0.3, test và source notebook tham khảo; **đã thử nhiều kịch bản nhưng chưa đầy đủ thuật toán, đánh giá hoặc tích hợp của toàn dự án**. [Bằng chứng rà soát](../../research/references/data-checks/t0/code-review-2026-10-21.json) ghi hash code/plan, lệnh, kết quả và các ca biên bổ sung. Đây là kiểm tra có phạm vi, chưa phải audit mọi cell notebook hay chứng nhận production.

Đã chạy lại `python scripts/checks/check_docs.py` (35 Markdown đạt), `python -m unittest discover -s tests -v` (**124 test đạt**) và `python -m t0 run-offline --output data/T0/processed/offline-review-2026-10-21` (exit 0, 124 artifact được hash trước khi thêm bằng chứng probe). Lượt offline dùng cache local, không train, gọi mạng hoặc ghi đè output cũ. Các chỉ số chất lượng chính khớp bảng v0.2 phía trên: AR `v2_full` test precision 100%, recall clean 76,92%/masked 66,83%; RecBench precision 100%, recall 99,828% trong universe đủ endpoint; FinBalance precision 60%, recall 2,88%; FinRCA matching quality vẫn `null`. Runtime thuộc từng lượt riêng.

Các kịch bản đã có test gồm partial/group/overpayment, mơ hồ và cạnh tranh, cap nhóm, tenant/currency/AP–AR, tiền nguyên và scale, cutoff/late arrival/version ở receipt v0.1, retry/persistence/rollback/unknown/verify/reverse ở ledger, raw hash và endpoint unknown ở evaluator. Suite AR v2 có 56 lượt, nhưng chỉ hai profile clean/masked và hai seed test mỗi profile; noisy/stress rộng hơn thuộc benchmark v1 lịch sử, không mặc định được kế thừa thành coverage v2.

Các phát hiện **chưa sửa tại thời điểm rà soát trước v0.3**, sau đó đã xử lý hoặc bổ sung guard/gate tại các mốc phía trên:

| Phát hiện | Bằng chứng và hệ quả |
|---|---|
| Thiếu validation ngày khả dụng tại input `allocate` mô phỏng | `load_allocation_input` so sánh chuỗi `available_on` trước khi kiểm ngày từng dòng. Fixture có `available_on=""` hoặc `"2025-01-00"` vẫn được nhìn thấy và sinh allocation; `"2025-1-1"` lại bị loại âm thầm. Cần xác thực ngày trước khi lọc cutoff và thêm regression test. |
| Reference sai nhưng trỏ đúng một hóa đơn có thật | Hai invoice cùng party/currency/amount, truth là I1 nhưng remittance ghi số I2: v2 tạo đề xuất `auto` cho I2, invariant vẫn đạt, precision/recall fixture bằng 0. Đây là counterexample về giới hạn bằng chứng quan sát, không phải ước lượng tỷ lệ sai trên SME; bộ v2 hiện chỉ che reference, chưa mô phỏng đầy đủ kiểu sai này. |
| Chưa chặn ngày điều chỉnh trước endpoint | Ledger nhận credit note effective 01/01 tham chiếu invoice effective 20/01, và refund trước effective payment tương tự, khi các record đã được nhận theo đúng thứ tự availability. Đã kiểm tồn tại/scope, chưa kiểm thứ tự hiệu lực của các record liên quan; khác với kiểm late arrival đã có. Cần chốt chính sách nghiệp vụ và bổ sung validator/test tương ứng. |
| Exit 0 chưa phải gate chất lượng đầy đủ | `run_all` chỉ đưa AR invariant/order và FISCUS vào `checks`; FinBalance recall thấp, FinRCA quality `null` hoặc nguồn `unavailable` không tự làm lệnh thất bại. Cần đọc từng task và phần thiếu; không dùng exit code để kết luận hoàn tất. |

Thuật toán hiện có là bốn baseline receipt, assignment Hungarian cho nhánh 1:1, reference/partial/tiền thừa và subset giới hạn của v2, bốn baseline GL–bank riêng, payout–bank và journal baseline hẹp. Chưa tái lập các mô hình MILP/graph/entity matching trong nghiên cứu; chưa có phân bổ N:M tổng quát, FX/split bank link, classifier inconsistency hoặc đối soát số dư bank đầy đủ. Không cần triển khai mọi thuật toán trong paper mới được coi là đủ; cần xác định phạm vi mục tiêu và kiểm chứng các ca bắt buộc của phạm vi đó.

Với toàn dự án, đã kiểm kê source notebook 01–12 có baseline, LightGBM phân vị, conformal, Monte Carlo, survival và backtest tham khảo; **không thực thi/train lại** vì thiếu `data/dataset.csv`, `data/processed/` và model lịch sử. Code T1 mới chưa triển khai; các task T0–T13 vẫn có phần thiết kế chưa thành pipeline tích hợp. [Tiến độ và phần còn thiếu](../../research/notes/t0_data_foundation_reconciliation.md#tiến-độ-và-phần-còn-thiếu) tiếp tục là nơi duy trì kế hoạch; ưu tiên xử lý validation ngày, mở rộng fixture reference sai và chốt oracle trước khi dùng điểm số để tự động ghi sổ.

## Cơ sở nghiên cứu

Đã đối chiếu các phần liên quan của R3/R4/R5/R7 trong repo, đọc thêm nghiên cứu Xero và tài liệu nghiệp vụ trực tiếp. [Script nghiên cứu](../../scripts/data_audit/research_t0_reconciliation.py) đã chạy: chín nguồn truy cập được, tám PDF local đã trích xuất text, có hash và số trang trong [bằng chứng](../../research/references/data-checks/t0/reconciliation-research-2026-10-19.json). Đây là kiểm tra nguồn và đọc tài liệu, không phải tái lập kết quả các paper. URL, ngày kiểm tra, phiên bản và giới hạn nằm trong artifact; không tái phân phối nội dung nguồn tải bổ sung.

| Nguồn | Bằng chứng dùng cho thiết kế | Giới hạn áp dụng |
|---|---|---|
| [Wu và cộng sự, SSMP, bản ECAI mở rộng 2025](https://arxiv.org/html/2508.19218v1), đã có PDF R7 | Hai tập bản ghi có thể khớp theo nhóm rời nhau; tìm nhóm có chi phí tổ hợp. Cần đo cả chất lượng và công tính | Paper tập trung tổng tiền; tổng bằng nhau chưa đủ xác nhận đúng đối tác/chứng từ. Baseline nhóm dưới đây là thuật toán giới hạn, không phải tái lập MILP của paper |
| [Munoz, Jalili, Tafakori, 2025, bản journal pre-proof](https://www.newswise.com/pdf_docs/176364346984800_1-s2.0-S2405918825000224-main.pdf), DOI [10.1016/j.jfds.2025.100170](https://doi.org/10.1016/j.jfds.2025.100170) | Nghiên cứu Xero tại một doanh nghiệp có nhãn bookkeeper; mô tả giao dịch nhiễu và khó khăn 1–N. Dùng repeated runs để xem biến thiên | Không có corpus Xero để tái lập, không triển khai graph/Top Boundary Ranking trong đợt nghiên cứu 19/10. Không lấy tỷ lệ nhóm hay accuracy của doanh nghiệp đó làm tỷ lệ SME Việt Nam |
| [Ditto, R5](https://arxiv.org/abs/2004.00584v3), cùng R3/R4 có sẵn | Tách sinh ứng viên và quyết định cặp; kiểm tra chất lượng, lịch sử và thông tin đã biết | Entity matching không tự giải quyết tiền, scope và N–M; không suy từ benchmark thực thể sang hiệu quả phân bổ |
| [ERPNext Payment Reconciliation](https://docs.frappe.io/erpnext/payment-reconciliation) | Có trả từng phần, một khoản trả nhiều hóa đơn, nhiều khoản trả một hóa đơn và tiền thừa chưa phân bổ; phân bổ giới hạn theo dư tiền/dư hóa đơn, company và party | Đây là tài liệu chức năng, không đo tần suất trong thị trường hay chứng minh rule tự động chính xác |
| [ERPNext Bank Reconciliation](https://docs.frappe.io/erpnext/bank-reconciliation), [ACCA FA2](https://www.accaglobal.com/content/dam/acca/global/PDF-students/fia/examreports/fa2/FA2%20S22-A23%20examiner%27s%20report.pdf) | Có chênh ngày, phí, giao dịch nhập trùng; cần phân biệt ngày ghi sổ và ngày clear | Phí, lỗi sổ và chênh thời gian có cách xử lý khác nhau; không được xóa chênh lệch bằng ép ghép |
| [Dynamics 365: invoice matching](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching) | Trong AP, invoice matching còn có nghĩa kiểm tra invoice với PO và phiếu nhận hàng | Bộ này chấm ghép tiền/hóa đơn và GL–bank, chưa chấm two/three-way PO–receipt–invoice |
| [Operartis BenchRec](https://www.operartis.com/benchrec), [dataset card Kaggle](https://www.kaggle.com/datasets/benchmarkteam/benchrec-real-world-cash-reconciliation-dataset) | Dữ liệu GL–bank đã che thông tin; nhãn là tập allocation-key, chấp nhận dự đoán không rỗng bằng hoặc là tập con của nhãn | Nguồn gốc và chất lượng nhãn theo chủ nguồn. Chưa có evaluator chính thức chạy được; cách chấm local bám mô tả và được unit test |

**Cơ sở benchmark v1:** tách hai đường đánh giá. BenchRec kiểm tra GL–bank thật theo nhãn công bố. Bộ tình huống tổng hợp kiểm tra phân bổ khoản thu vào hóa đơn, nơi cần kiểm soát rõ tiền thừa, trả từng phần và công nợ. Không gộp metric hai đường thành một accuracy chung.

## Thiết kế benchmark v1

[Kế hoạch v1](../../research/references/data-checks/t0/reconciliation-benchmark-plan-v1.json) được ghi trước khi chạy chấm BenchRec. Cấu hình số, seed và hash được lưu trong output. Không train hoặc chọn ngưỡng trong đợt này; các phương pháp hóa đơn cũ giữ nguyên. Tập solution BenchRec từng được kiểm tra cấu trúc trước đây, nên **không gọi đây là blind holdout**. Trong harness v1, mọi dự đoán BenchRec được lưu trước khi đọc solution để chấm; không dùng kết quả test để sửa rule/ngưỡng.

### Bộ tình huống hóa đơn

`t0/scenarios.py` tạo ý định thanh toán trước, sau đó mới tạo/biến đổi dữ liệu quan sát. Nhãn link và số tiền xuất phát từ ý định, không chạy matcher để sinh đáp án. ID ngẫu nhiên không mã hóa tình huống. Các profile cùng seed dùng cùng ý định và số tiền; hash của thế giới gốc dùng kiểm tra việc này.

| Tình huống | Đáp án và điều cần kiểm tra | Nguồn trong kế hoạch |
|---|---|---|
| Trả đủ, trả nhiều lần, một khoản trả hai hóa đơn | Đúng ID và đúng số tiền trên từng cạnh; không phân bổ vượt dư | ERP-PAYMENT; SSMP/RMIT cho nhóm |
| Chuyển thừa | Phân bổ bằng dư hóa đơn; phần thừa còn chưa phân bổ. Không tự tăng giá trị hóa đơn | ERP-PAYMENT |
| Thu ròng có phí, hóa đơn được giảm bởi credit note | Chỉ tiền ngân hàng thực thu vào nhãn cash; phí/credit lưu thành event điều chỉnh riêng | ERP-BANK, ACCA, ERP-PAYMENT |
| Hai hóa đơn cùng khách/tiền/ngày, nội dung thiếu rõ ràng | Một nhãn theo ý định, nhưng dữ liệu quan sát có thể không phân biệt được. Để duyệt là hành vi hợp lệ; không ép recall 100% | RMIT/DITTO |
| Hóa đơn chưa trả, khoản thu không có invoice | Không có cạnh cash đúng; không lấy mọi giao dịch làm positive | ERP-PAYMENT/ERP-BANK |
| Hoàn tiền âm | Phải bị cách ly khỏi matcher chỉ nhận khoản thu dương; không được biến thành thu mới | ERP-BANK; giới hạn contract receipt v0.1 |
| Hóa đơn đến sau cutoff, sửa hồi tố, nhập lặp, tenant/currency khác | Chỉ chấm endpoint hợp lệ tại cutoff; nhập lặp không đổi phân bổ; không ghép chéo scope | ERP-BANK/ERP-PAYMENT và R3/R4 trong repo |

Tám block mỗi dataset, hai seed validation và năm seed test, ba profile: 21 dataset, 84 lượt matcher chính và 84 replay. `clean` giữ thông tin; `noisy` che mã/identity 10%, sửa tên 10%, dịch ngày settlement tối đa một ngày; `stress` dùng 30%/30%/ba ngày. Hai profile sau có delivery trùng. Ca nghiệp vụ khó như mơ hồ, trả gộp vẫn có trong clean: **clean nói về dữ liệu quan sát, không có nghĩa mọi ca đều dễ**.

Các mức 10%/30%, cửa sổ ngày, số nhóm và tiền phí minh họa là mức kiểm tra độ bền công khai do thiết kế. Các nguồn xác nhận cơ chế nghiệp vụ, **không xác nhận các con số đó là phân bố thực tế**. Số lượng ca cân bằng dùng tìm điểm yếu, không ước lượng accuracy thị trường. Ground truth độc lập với phương pháp nhưng vẫn do mô phỏng, chưa được kế toán SME gán nhãn độc lập.

Đường receipt v0.1 chưa hạch toán đầy đủ phí/credit note/refund; report ghi `unsupported_event_counts`, vẫn chấm riêng cạnh tiền dương và kiểm tra cách ly hoàn tiền. Không gọi kết quả này là đối soát số dư/công nợ cuối kỳ hoàn chỉnh. Ngày cash trong bộ này theo booked date nên MAE ngày chỉ kiểm tra truyền ngày, không chứng minh khôi phục ngày khả dụng.

### BenchRec

Chạy toàn bộ 37.123 A và 32.048 B eval, không lấy mẫu thuận lợi. Adapter chỉ đưa ID, tiền Decimal có dấu, currency, account, value date và transaction reference vào baseline; A_allocation được tái tạo từ field nguồn để xuất đáp án, không dùng làm điểm tương đồng. Loại match metadata, `wasPreviouslyMismatched`, target/solution và submission tham khảo khỏi đầu vào thuật toán. Không suy dấu amount từ DR/CR vì mã hai phía ngược nhau.

[Audit train riêng](../../research/references/data-checks/t0/benchrec-train-semantics-2026-10-19.json) đã chạy theo matchId lịch sử: 51.980 nhóm có cả A/B, cùng currency/account và nhãn B đều thuộc tập key A của nhóm. Trong đó 49.443 nhóm cân tổng tiền có dấu, 2.537 nhóm không cân. Chưa đủ thông tin quy nguyên nhân cho phí, điều chỉnh hay lỗi nhãn; giữ raw và không xóa nhóm đó. Ràng buộc cân tiền của baseline có thể làm giảm recall trên nguồn này. Nhãn allocation-key có tính nhất quán theo nhóm không đồng nghĩa có ground truth chính xác cho tiền từng cạnh.

Bốn baseline cố định: `exact_amount_date` (tiền/ngày trùng và duy nhất), `nearest_date` (cùng tiền, ngày gần nhất duy nhất trong 14 ngày), `text_mutual` (cùng tiền, điểm 0,7 Jaccard reference + 0,3 gần ngày; ngưỡng 0,65, margin 0,10), `bounded_group_sum` (exact trước, tìm duy nhất nhóm 2–3 A cùng ngày/scope/dấu; tối đa 12 ứng viên). Mọi đề xuất cạnh tranh cùng A đều bị để lại duyệt; không chọn theo thứ tự nhập. Nhóm vượt giới hạn được đếm, không cắt bớt rồi giả vờ đã tìm đủ. Chưa giải quyết tổng quát N:M, nhóm trộn dấu, phí hoặc partial theo ID.

BenchRec `original` giữ nguyên dữ liệu thực đã che thông tin, không gọi nó là clean. `noisy`/`stress` che reference B 10%/30%, làm sai value date B tối đa 1/3 ngày; giữ tiền, A và nhãn nguyên. Mỗi profile chạy năm seed: 60 lượt chính và 60 lần đảo thứ tự để kiểm tra ổn định. Đây là **dữ liệu thật có biến đổi kiểm soát**, không phải nguồn thực mới. Chạy offline trên toàn bộ pool, chưa tái lập availability theo từng ngày.

Chấm precision, match rate (B đúng / B có nhãn), exact-set precision/recall bổ sung, coverage/review, tiền tuyệt đối gán sai theo currency, runtime và hash khi đảo thứ tự. Tập dự đoán phải không rỗng mới được tính đúng theo subset; nhãn trống không thành true positive. Tiền sai ở đây là toàn bộ trị tuyệt đối của B có allocation sai, không phải tiền sai trên từng cạnh invoice. Không cộng currency hay so trực tiếp hai định nghĩa tiền sai.

Mean/std/range và bootstrap ghép cặp theo seed là mô tả độ nhạy với nhiễu. Năm lần chạy cùng BenchRec không tạo năm doanh nghiệp độc lập; interval không đo khả năng khái quát sang SME. Runtime chỉ gồm matcher, không gồm đọc CSV, audit hay replay; báo median/max, không gọi max của năm lần là p95 production. Ngưỡng precision 99,8% trên dataset card là yêu cầu của nguồn, chưa phải bảo đảm tự động hóa tại doanh nghiệp.

## Kết quả benchmark v1 — 19/10/2026

Chạy từ **14:11:38 đến 14:23:35 UTC** bằng Python 3.13.5 trên Windows, cấu hình kế hoạch v1 không đổi. [Bằng chứng tổng hợp](../../research/references/data-checks/t0/reconciliation-benchmark-2026-10-19.json) có cấu hình, hash code/raw, thống kê và so sánh ghép cặp. Bản đầy đủ local: `data/T0/processed/reconciliation-v1/report.json`; dự đoán và input ở cùng thư mục. Tại thời điểm kết thúc lượt chạy, hash code trùng hash lúc bắt đầu; sửa đổi kiểm tra đầu vào sau đó được ghi trong [bằng chứng kiểm định lại](../../research/references/data-checks/t0/reconciliation-verification-2026-10-19.json). Không train, sửa ngưỡng hoặc chọn rule sau khi xem metric.

Tổng cộng **144 lượt chính và 144 lượt replay**: 84 cho bộ hóa đơn (gồm validation/test), 60 cho BenchRec. Tất cả replay giữ hash kết quả, không có lỗi ràng buộc phân bổ. Tính tái lập này không đồng nghĩa chính xác nghiệp vụ hoặc vững trước nhiễu.

### BenchRec: precision cao trên bản gốc, suy giảm dưới nhiễu

Đơn vị trong hai cột chất lượng là %, mean của năm seed. Match rate chỉ tính trên 31.836 B có nhãn; 212 B null vẫn được giữ để phạt ghép sai. Tập eval có 1.779 B mang nhiều allocation-key; mọi key nhãn đều có trong A. Toàn bộ B eval thuộc **một account, USD**, nên không có bằng chứng khái quát sang nhiều công ty/tài khoản.

| Profile | Phương pháp | Precision | Match rate | Median giây/lượt |
|---|---|---:|---:|---:|
| original | exact_amount_date | 99,888 | 58,597 | 2,145 |
| original | nearest_date | 99,824 | 58,930 | 2,236 |
| original | text_mutual | Không xác định | 0 | 3,867 |
| original | bounded_group_sum | 99,888 | 58,597 | 11,712 |
| noisy | exact_amount_date | 97,715 | 19,180 | 1,557 |
| noisy | nearest_date | 99,354 | 57,794 | 2,310 |
| noisy | text_mutual | Không xác định | 0 | 3,729 |
| noisy | bounded_group_sum | 97,715 | 19,180 | 15,496 |
| stress | exact_amount_date | 94,222 | 8,306 | 1,511 |
| stress | nearest_date | 98,791 | 56,915 | 2,098 |
| stress | text_mutual | Không xác định | 0 | 3,372 |
| stress | bounded_group_sum | 94,222 | 8,306 | 13,793 |

Trên bản gốc, exact đề xuất 18.676 B, đúng 18.655 và sai 21; nearest đề xuất 18.794 B, đúng 18.761 và sai 33. Trị tuyệt đối tiền B có allocation sai lần lượt là **32.212.058,76 USD** và **26.540.766,55 USD** theo số tiền nguồn. Đây là tiền trên dữ liệu đã che thông tin, không suy thành mức thiệt hại thực hoặc quy mô SME.

Độ lệch chuẩn precision ở stress: exact **0,585 điểm phần trăm**, nearest **0,067 điểm phần trăm**; match rate tương ứng **0,095** và **0,053 điểm phần trăm**. Bản original có metric giống nhau ở cả năm lần vì thuật toán xác định, không có nhiễu. Với nearest, median runtime khoảng 2,1–2,3 giây; max ghi nhận trên original 2,908 giây. Không suy runtime này sang hạ tầng khác hoặc quy mô lớn hơn.

`bounded_group_sum` không thêm dự đoán nào so với exact trong cả ba profile nhưng tốn thời gian hơn. Trên original, 12.898 B có pool nhóm vượt cap; giới hạn blocking/nhóm hiện tại không mang lại lợi ích ở nguồn này. **Không kết luận khớp nhóm nói chung vô ích** hoặc tăng cap theo test để làm đẹp kết quả.

`text_mutual` không đưa ra dự đoán trong mọi lượt: precision là `null`, không phải 100%. Cấu hình text cố định hiện không hữu ích trên nguồn này; chưa đủ bằng chứng quy nguyên nhân riêng cho obfuscation, khác kiểu mô tả hay ngưỡng chưa hiệu chỉnh. Giữ kết quả thất bại, không hạ ngưỡng bằng solution.

Các rule tiền/ngày vượt 99,8% ở điểm ước lượng trên original, nhưng không giữ mức đó khi tăng nhiễu. Vì vậy **chưa chấp nhận tự động ghi sổ**; các con số không chứng nhận precision production, độ đúng của A ID, phân bổ invoice hay số dư cuối kỳ.

### Hóa đơn tổng hợp: nêu rõ phương pháp xử lý được ca nào

Bảng chỉ lấy test, mỗi ô là **precision / recall (%)**, mean năm seed; không trộn validation. Đây là capability suite cân bằng tình huống, không phải ước lượng hiệu quả SME.

| Phương pháp | clean | noisy | stress |
|---|---:|---:|---:|
| exact_reference | 100 / 13,51 | 100 / 12,16 | 100 / 11,08 |
| amount_date | 98,18 / 12,97 | 90,21 / 12,97 | 82,91 / 12,97 |
| scored_global | 100 / 13,24 | 98,00 / 13,24 | 96,18 / 13,24 |
| reference_then_global | 100 / 78,38 | 99,64 / 73,24 | 99,11 / 59,46 |

Trên clean, hybrid xử lý được partial/group và cạnh tiền dương của fee/credit note; chưa xử lý tiền thừa và ca mơ hồ. Không gọi việc nhận đúng cash edge là đã hạch toán phí/credit. Mỗi dataset có tám fee adjustment, tám credit note và tám refund chưa được matcher hỗ trợ đầy đủ; refund âm được cách ly. Tám cạnh late-arrival bị loại khỏi universe chấm tại cutoff, không bị đổi thành negative.

Hybrid stress có recall **59,46 ± 5,32 điểm phần trăm** (mean ± sample std), precision **99,11 ± 1,23 điểm phần trăm**; median 0,164 giây/lượt. Các con số tốt hơn baseline 1–1 trong tập này phù hợp với việc nó có nhánh partial/group, nhưng chưa chứng minh tốt hơn trên doanh nghiệp. Tập hiện tại còn chủ động có mã invoice khi chưa bị che; cần kiểm tra tần suất/thông tin thực tế trước khi suy coverage ngoài mẫu.

Kiểm định lại input, nhãn, metric và replay được lưu trong [bằng chứng maintenance v1](../../research/references/data-checks/t0/reconciliation-verification-2026-10-19.json). Kết quả v1 giữ để hồi quy; giới hạn receipt v0.1 không phủ nhận khả năng ledger v0.2. Các việc phát triển tiếp được duy trì tại kế hoạch T0, tránh giữ một backlog thứ hai trong báo cáo.
