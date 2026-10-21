# Hợp đồng dữ liệu T0

Package hiện là **0.4.0**. Trang này duy trì phần mở rộng v0.4/v0.3, schema typed AP/AR v2 tương thích, contract GL–bank riêng của BenchRec, cùng receipt v0.1 để hồi quy. Các schema không dùng lẫn nhau. [Mã nguồn](../../t0/), [dữ liệu và lệnh](../../data/T0/README.md), [kết quả đã chạy](../reports/t0-method-review.md).

## Quy tắc đọc dữ liệu và sửa lỗi v0.4

CLI/ledger và các reader T0 dùng chung parser JSON/JSONL từ chối khóa trùng ở mọi cấp, `NaN`/`Infinity` và float tràn về vô hạn; lỗi JSONL kèm file/dòng. Writer/hash cũng từ chối số không hữu hạn. CSV adapter/BenchRec từ chối header trống/trùng, header lặp giữa dữ liệu, dòng thiếu/thừa ô hoặc quote sai; không âm thầm mất field. Chuyển tiền Decimal sang minor-unit dùng coefficient/exponent chính xác, không phụ thuộc precision của context đang chạy. Không viết lại JSON bằng chứng lịch sử để khớp hash code mới.

Allocation ledger có `tenant_id`, `currency`, `payment_currency`, `side` thì các field đó phải khớp command/endpoint; không bỏ qua metadata mâu thuẫn. `due_on` của invoice, nếu có, không trước ngày phát hành. Journal text chỉ tạo entry khi cả hai tài khoản khác nhau và có trong `allowed_accounts`. Hai invoice cùng số/scope mà mâu thuẫn tổng tiền đều chuyển review, cùng các dependency; không chọn một bản theo thứ tự ID. Duplicate delivery có cùng payload quan sát không tạo thêm posting và không làm dependency thành mơ hồ. Ghép posting sang entry phải kiểm cân bằng/kiểu tiền trước, không bỏ phần dư debit/credit.

## Phần mở rộng v0.4 — khác ngày, FX, phiên bản và journal

Phần này thay thế các giới hạn cùng ngày, thiếu FX/refund–bank và record invoice/payment một phiên bản của v0.3. Các baseline v2/v0.1 giữ nguyên. Không tự suy tỷ giá, chính sách thuế hoặc tính đầy đủ của nguồn.

### N:M qua nhiều ngày trong snapshot

`constrained_flow` giải chung các payment **đã biết trong input snapshot**, thay cho commit tham lam từng ngày. Mỗi cạnh vẫn kiểm tenant/currency/AP–AR/party và ngày invoice không sau ngày payment; cửa sổ tuổi, cap mỗi phía 12 (tối đa cấu hình 16), subset amount-only và điều kiện nghiệm duy nhất giữ nguyên. Không cắt component lớn để chọn một phần tùy ý. Chỉ có thêm ngày không biến một bài toán thiếu thông tin thành xác định được.

Payment đến ngày sau có thể làm đề xuất tại cutoff sau khác cutoff trước; không được dùng payment đó để viết lại quyết định đã commit hay kết quả cutoff trước. CLI `allocate` lọc availability/ngày nghiệp vụ trước solver; gọi Python trực tiếp phải cung cấp đúng snapshot. Dữ liệu tĩnh FinRCA vẫn không có tuyên bố historical as-of. Cửa sổ ở đây là tuổi invoice–payment, không phải cap số ngày giữa các payment.

### FX có bằng chứng và hai đơn vị tiền

`t0/fx.py` nhận quote quan sát có `source_currency,target_currency,rate_num,rate_den,rounding="half_even",quoted_on,available_on,source_ref`. Tử/mẫu là integer dương: **target minor units / source minor unit**, không phải tỷ giá major-unit. Ví dụ USD cents → VND đồng với tỷ giá giả lập 25.000 VND/USD cần tỷ số 250/1. Chuyển đổi bằng số nguyên, làm tròn half-even; không ép float/bool, không nhận kết quả làm tròn về 0. Quote phải được công bố/biết trước cutoff lệnh và `quoted_on` không sau effective date; không tự xác nhận nguồn hoặc độ mới của giá.

`allocate-fx` chỉ tạo đề xuất từ `payment.fx_remittance=[{invoice_number,invoice_amount_minor,payment_amount_minor,fx}]`. Cần party rõ, reference duy nhất, đúng AP–AR, ngày và currency pair; mỗi payment tối đa 16 dòng. Phải có availability tường minh. Amount/currency giống nhau hoặc tỷ lệ suy ngược từ hai tổng không thay thế bằng chứng quote. Tranh chấp vượt dư invoice chuyển review cho mọi payment đang tranh chấp; vượt payment cũng review. Đây là đường đề xuất riêng, không tự gộp với đề xuất cùng currency.

Ledger `suggest.allocations` cho FX dùng `amount_minor` theo **invoice currency**, `payment_amount_minor` theo **payment currency**, cùng `fx` invoice→payment. Kiểm từng giá trị theo quote; balance/reversal trừ/hoàn đúng đơn vị từng endpoint. Cùng currency hai amount phải bằng nhau, không nhận quote. Commit kiểm tổng tiêu thụ của mọi quyết định cùng/khác currency; không thể cộng hai file đề xuất rồi bỏ qua kiểm dư.

`bank_link.currency` vẫn là payment currency; quote nếu có là payment→bank. `payment_amount_minor` theo source, `bank_amount_minor` và `fee_minor` theo bank currency. Bank credit = converted gross − fee; bank debit = converted gross + fee. `bank_currency` được chuẩn hóa trong Gold. Tùy chọn `carrying_bank_minor` khai báo giá trị ghi sổ trước phí bằng bank currency; Gold tính `realized_fx_minor=(converted−carrying)` cho inflow và dấu ngược cho outflow. Đây là chênh lệch từ carrying do caller cung cấp, không tự chứng nhận sổ gốc hoặc tự tạo journal. Thiếu carrying thì không suy chênh lệch FX.

### Refund–bank và chỉnh sửa nhiều phiên bản

`record/kind=refund_bank_link`: `data={tenant_id,id,currency,refund_id,bank_id,refund_amount_minor,bank_amount_minor,fee_minor}`; có thể thêm `fx` và `carrying_bank_minor` như bank link. Currency source là refund/payment. AR refund cần bank debit; AP refund cần bank credit. Ngày link không trước refund/payment/bank. Có thể chia một refund qua nhiều bank hoặc một bank cho nhiều link; tổng refund slices không vượt refund và tổng bank slices **chung với bank_link** không vượt bank row. Link chỉ xác minh quan hệ, không trừ công nợ/unapplied hoặc tạo cash lần hai. Refund vẫn chỉ dùng tiền unapplied, cần reverse allocation nếu không đủ.

Gold thêm `refund_bank_links`, `refunds.bank_unlinked_minor`; `bank_unlinked` trừ cả hai loại link. Chưa suy ra refund thật sự đã tới đối tác chỉ từ caller nhập link; chưa có connector xác minh độc lập.

Invoice/payment có `version=1` khi record. Sửa bằng command mới `action=revise,kind=invoice|payment,expected_version=<version hiện hành>,data=<toàn bộ record thay thế>`. ID/tenant/currency/side/party và `effective_on` gốc phải giữ; có thể sửa số tiền, invoice number và metadata/ngày hạn hợp lệ. `available_on` là lúc nhận sửa thực tế, không được lùi ingestion; ngày nghiệp vụ nếu đưa trong data phải trùng effective. Thay scope/ngày nghiệp vụ, sửa credit/refund/bank hoặc void chứng từ vẫn cần quy trình riêng.

Không sửa payload SQLite cũ. Gold chọn phiên bản đã biết tại cutoff, kèm `document_versions` (kind/version/supersedes/sequence); snapshot trước availability của revision giữ nguyên. Version stale, giảm tiền dưới allocation/credit/refund/bank-link hoặc sửa endpoint có external outcome unknown đều bị từ chối atomically. Suggestion lưu version hai endpoint; approve/commit/verify trên bản đã sửa bị chặn. `cancel` chỉ áp dụng suggested/approved, sau đó tạo decision ID mới. Allocation đã commit giữ số tiền lịch sử, muốn đổi phải reverse; revision không sửa allocation ngầm.

### Journal nhiều dòng và detector có policy tường minh

`journal-predict` nhận JSONL record quan sát: `record_id,industry,allowed_accounts,documents`, thêm `cutoff,accounting_policy` để chạy structured engine. `industry/allowed_accounts` phục vụ baseline text; structured engine lấy chart từ policy. Từng document có `doc_id,doc_type,role,date,available_on,ocr_text,metadata` và `accounting_facts.schema="t0-journal-facts-v1"`. Fact/policy phải đến từ export/khai báo quan sát độc lập, không được tạo từ expected entries. Khi có cutoff, document thiếu availability bị unsupported, document chưa biết không được dự đoán hoặc dùng làm dependency.

Policy gồm `policy_id,functional_currency,effective_on,available_on,accounts` (alias→tên tài khoản, tên không trùng). Alias dùng tùy nghiệp vụ: `receivable,payable,cash,revenue,expense,input_tax,output_tax,fx_gain,fx_loss`; có thể thêm tài khoản opening. Không tự đoán tài khoản hoặc luật thuế từ industry.

| Chứng từ structured | Fact bắt buộc ngoài schema/party_id/currency | Chính sách |
|---|---|---|
| customer_invoice | subtotal_minor, tax_minor, total_minor, discount_minor (mặc định 0), revenue_recognition | Chỉ immediate; Nợ AR, Có revenue và output tax khai báo |
| vendor_invoice / expense_receipt | Các tổng như trên, expense_account, tax_treatment | recoverable hoặc expensed do caller khai báo; Có AP hoặc Cash |
| customer_credit_note / vendor_credit_note | Fact invoice tương ứng và reference_doc_id | Đảo nghiệp vụ gốc, phải có invoice cùng party/currency, không vượt tổng và khớp carrying |
| customer_payment / vendor_payment | amount_minor, carrying_functional_minor, reference_doc_id | Settlement invoice đã quan sát, tách cash và control account |
| customer_refund / vendor_refund | Fact settlement như trên | Tham chiếu credit note phù hợp; không thay cho kiểm unapplied của allocation ledger |

Mọi tiền là minor integer; subtotal − discount + tax phải bằng total. Nếu currency khác functional, cần quote `fx` như trên. FX settlement dùng carrying tỷ lệ half-even từ booking của chứng từ tham chiếu; chênh lệch vào fx_gain/fx_loss riêng. Không chấp nhận carrying tùy ý. Các component FX làm tròn không cộng đúng tổng chuyển unsupported, không bù tùy ý vào thuế/doanh thu. Deferred revenue, lease, deferred tax, tự xác định khả năng khấu trừ thuế và revaluation chưa hỗ trợ.

Output `postings` có nhiều dòng debit/credit cân bằng, functional currency và policy ID; `entries` là phép ghép debit–credit tương đương để tương thích evaluator cũ. Doc ID trùng nội dung không ghi lần hai; ID xung đột, tổng sai, dependency sai party/currency/ngày, tổng payment/credit vượt chứng từ gốc bị phát hiện. Cả nhóm cạnh tranh và chứng từ phụ thuộc lỗi chuyển review; thiếu dependency/policy hỗ trợ trả unknown/unsupported, không tự gán inconsistent.

Tùy chọn record `opening_balances={currency,as_of,available_on,balances:{account:signed_minor}}` dùng quy ước debit dương, credit âm và opening phải cân. `trial_balance` chỉ replay structured postings sau ngày as_of, cùng policy/currency; `prediction_complete=false` khi có posting chưa dự đoán được hoặc chỉ có entry text chưa chuyển sang structured postings. Cân trial balance không tự xác nhận tính đầy đủ hoặc tạo balance sheet hoàn chỉnh.

Baseline text USD mở thêm supplier invoice (Expense Category chính xác trong allowlist), utilities, loan draw/principal/interest **đã trả**, và payroll gross/employer tax/cash đã khai báo. Không tính thuế theo luật hoặc suy lịch trả nợ. Detector thêm phương trình principal và payroll cash, running balance từng dòng bank; identity conflict chỉ so invoice có issuer/counterparty đủ rõ. Các policy text khác vẫn abstain. Predictor chỉ chiếu field quan sát; nhãn expected/scenario/validation không tham gia. Mẫu chạy tổng hợp tại [examples/v04](../../data/T0/examples/v04/), không phải dữ liệu SME hoặc benchmark độc lập.

## Phần mở rộng v0.3 — phân bổ có nghiệm duy nhất và gate

Các cơ chế được đưa vào từ v0.3 dưới đây vẫn áp dụng; mô tả đã cập nhật theo v0.4. Giới hạn của các lần chạy cũ được giữ tại [báo cáo theo snapshot](../reports/t0-method-review.md), không dùng làm giới hạn của code hiện hành.

`allocate` mặc định dùng `constrained_flow` trong `t0/constrained.py`; `--method v2` giữ thuật toán allocation cũ. Bốn baseline receipt, suite v2 và BenchRec không đổi rule. Typed input vẫn có `schema=t0-invoice-payment-v2`. Với availability mô phỏng, **mọi ngày availability/nghiệp vụ phải là ISO hợp lệ trước khi lọc cutoff**, kể cả dòng nằm ngoài snapshot; ngày sai làm input lỗi, không bị âm thầm bỏ hoặc nhận là đã biết.

### Thuật toán và bằng chứng remittance

- Tạo ứng viên cùng tenant/currency/AP–AR/party và cửa sổ tuổi. Reference xung đột không fallback; party chưa biết chỉ được giải từ reference không xung đột. Amount-only vẫn cần party và đúng một subset theo cap group 3/pool 12.
- Chia đồ thị payment–invoice đã biết tại cutoff thành connected component qua các ngày. Mỗi phía tối đa `max_group_pool` (mặc định 12, giới hạn cấu hình 16); vượt cap chuyển review, không cắt nhóm.
- Chạy luồng cực đại số nguyên Edmonds–Karp với supply payment và capacity dư invoice; chỉ xét nghiệm phân bổ đạt tổng nhỏ hơn của hai phía. Không đủ flow chuyển review. Giảm capacity từng cạnh dương một minor unit rồi giải lại: nếu còn đạt cùng tổng, nghiệm không duy nhất và cả component chuyển review. Không dùng thứ tự ID/FIFO để chọn giữa các cách chia tiền. Nghiệm duy nhất về toán học vẫn phụ thuộc tính đúng của bằng chứng đầu vào, chưa chứng minh đúng nghiệp vụ.
- Reference đơn trỏ một hóa đơn nhưng có nghĩa vụ cùng party/scope/số dư giống hệt cũng chuyển review; ca reference nhầm sang ID có thật trong audit được chặn theo chính sách này. Không khẳng định phát hiện được mọi reference sai, đặc biệt khi giá trị khác nhau hoặc thông tin sai nhưng tự nhất quán.
- Payment có thể có `remittance=[{"invoice_number":"...","amount_minor":25}, ...]` **quan sát độc lập tại cutoff**. Mỗi số hóa đơn phải phân giải duy nhất, không lặp, cùng party/scope; tiền nguyên dương, tổng không vượt gross. Các cạnh này là số tiền cố định trong component; vượt dư chuyển review. Phần gross chưa chỉ định giữ unapplied. Không tạo remittance từ truth/observed allocation cần đánh giá; thiếu thông tin thì để review.

[Kế hoạch robustness](../../research/references/data-checks/t0/allocation-robustness-plan-v1.json) so `v2_full` và `constrained_flow` trên cùng intent mới, bốn profile clean/masked/noisy/stress và split theo world seed. Nhãn gồm reference sai nhưng hợp lệ, N:M duy nhất/không duy nhất và partial group có breakdown. Feature được chiếu theo allowlist trước dự đoán; truth mở lại để chấm sau khi lưu prediction. Đây là capability/regression suite tổng hợp, không phải holdout SME hoặc tái lập MILP trong paper.

### Ledger: ngày liên quan, bank link chia dòng và sao kê

Credit note/refund không được có `effective_on` trước invoice/payment tham chiếu; bank link không trước cả hai endpoint. Availability vẫn là ngày nhận thực tế, không được backdate để hợp thức hóa. Validator nằm trong transaction trước insert.

`bank_link` có `payment_amount_minor` và `bank_amount_minor` nguyên dương trên từng link. Bỏ hai field giữ hành vi toàn bộ payment/bank cũ. Với cùng currency, AR: payment slice = bank slice + fee; AP: bank slice = payment slice + fee. Tổng slice mỗi payment/bank không vượt số tiền endpoint, hỗ trợ 1:N/N:1/N:M; một link/ID chỉ ghi một lần. FX và refund–bank dùng contract v0.4 phía trên; chưa có connector xác minh nguồn độc lập.

`record/kind=bank_statement` có `id,tenant_id,currency,account_id,start_on,end_on,opening_minor,closing_minor,credits_minor,debits_minor,transactions_complete`. Opening/closing là integer có dấu; credit/debit không âm; end không sau effective. Bank record phải có `account_id` tương ứng để đối chiếu, ngày nghiệp vụ là effective. Không nhận statement chồng kỳ trong cùng tenant/currency/account. Gold thêm `bank_reconciliation` và `bank_unlinked`: kiểm phương trình statement, tổng bank credits/debits trong kỳ, closing difference và continuity khi hai kỳ kề nhau. `matched_declared_complete` cần caller xác nhận đầy đủ giao dịch; thiếu xác nhận trả `unknown_completeness`, mismatch vẫn giữ nguyên để audit. Kỳ trống/gap/đầu kỳ không được suy đoán. Bank đến sau F không thay kết quả snapshot F. Đây là đối chiếu nguồn đã cung cấp, chưa chứng nhận tính đầy đủ từ ngân hàng.

### Journal inconsistency và gate đánh giá

`t0/journal.py` bổ sung detector trên text quan sát: kiểm tổng dòng/subtotal/tax amount khai báo USD, opening + bank movements = closing và document/invoice identity mâu thuẫn. Không suy tỷ lệ/luật thuế từ các phép tính này. Ngoài policy hỗ trợ trả `null`, không coi thiếu bằng chứng là consistent. `expected_inconsistency` chỉ dùng ở evaluator; không dùng scenario/validation metadata làm feature. Báo confusion counts, precision, recall toàn pool (abstained positive vẫn trong mẫu số), decision coverage; không suy detector hẹp thành kiểm chứng mọi chuẩn kế toán. Journal baseline vẫn giới hạn và không tự commit.

`run-offline` có `assessment` tách execution, technical, quality và evidence. `--gate technical` mặc định: exit 3 nếu thiếu task, exit 1 nếu technical fail, exit 0 chỉ xác nhận kỹ thuật. `--gate quality` thêm exit 4 nếu chất lượng chưa đạt hoặc còn `null`. Policy phát triển trong `t0/gates.py` ghi vào evidence: precision tối thiểu 0,998; recall AR/journal 0,8 và settlement 0,95. Đây là gate công khai để lộ khoảng thiếu, chưa hiệu chỉnh theo rủi ro SME hoặc SLA production. `production_ready` giữ false khi thiếu nhãn/availability/connector và holdout thực; không thể biến exit 0 thành chứng nhận hoàn thiện.

## Contract v0.2 — invoice–payment và ledger offline

Schema typed được đưa vào từ v0.2 và tiếp tục dùng trong v0.4; phần dưới mô tả contract hiện hành. Thuật toán allocator v2 được giữ riêng cho benchmark/hồi quy, không phải mặc định của `allocate`.

Code: `t0/allocation.py`, `adapters.py`, `ledger.py`, `offline.py`, `settlement.py`, `journal.py`. Chỉ dùng thư viện chuẩn, không gọi ERP API hoặc tự duyệt/ghi sổ từ dự đoán. [Cấu hình AR v2](../../research/references/data-checks/t0/ar-benchmark-plan-v2.json) khóa phương pháp, split thế giới, feature và ngân sách; bốn baseline receipt không thay thuật toán.

### Dataset typed và phép phân bổ

Dataset dẫn xuất có `manifest.json` với `schema=t0-invoice-payment-v2`, `availability=simulated` hoặc `static_retrospective`, `cutoff` khi có mô phỏng và `truth_exhaustive`. Các file `invoices.jsonl`/`payments.jsonl` dùng `id` riêng, khóa `(tenant_id,id)` duy nhất mỗi bảng; `truth.jsonl` hoặc `observed_allocations.jsonl` được tách khỏi input matcher.

| Bảng | Field matcher dùng và ý nghĩa |
|---|---|
| Invoice | `tenant_id`, `id`, `invoice_number`, `side` AP/AR, `party_id`, `currency`, `amount_minor`, `issued_on`. `invoice_number` là số quan sát trong remittance, khác ID nội bộ. `due_on` chỉ cần khi chiếu về baseline v0.1. |
| Payment | `tenant_id`, `id`, `side`, `party_id` (rỗng nếu chưa biết), `currency`, `amount_minor` gross, `payment_on`, `reference` quan sát. AP là khoản chi có hướng riêng, không đổi thành AR. |
| Allocation | `tenant_id`, `invoice_id`, `payment_id`, `side`, `currency`, `amount_minor`; một cạnh một tổng tiền dương. Tổng không vượt invoice hoặc payment; cùng tenant/currency/side/party, payment không trước invoice. |

`amount_minor` luôn là `int > 0`, từ chối bool/float. Adapter Decimal chỉ đổi theo scale khai báo (VND/JPY=0, USD/EUR/GBP/CAD/INR=2), không làm tròn hoặc lấy trị tuyệt đối. Invoice amount của bộ AR v2 là **nghĩa vụ mở sau điều chỉnh đã biết**, không mặc định là face value; fixture ledger riêng kiểm tra face/credit/allocated đầy đủ. Payment không đồng nghĩa bank cash; `fee_net` dùng gross payment, còn bank net/phí kiểm tra riêng ở ledger.

Matcher v2 tạo index invoice number và block tenant/currency/side/party. Reference rõ có thể phân bổ partial hoặc trả hết nợ rồi giữ tiền thừa unapplied. Nhiều reference chỉ tự đề xuất khi trả hết các dư đã nêu; partial group chưa xác định số tiền từng invoice chuyển review. Amount-only cần party đã biết và đúng **một** subset, tối đa pool 12/group 3. Overflow, tập con mơ hồ và tranh chấp invoice cùng ngày chuyển review; không cắt pool để chọn tùy ý. `auto` trong output là đề xuất thuật toán, **không phải commit**. Review/unmatched vẫn giữ toàn bộ tiền chưa phân bổ.

`allocate` không mở truth, mặc định dùng constrained flow; `--method v2` chọn allocator cũ. Input mô phỏng được lọc cả availability và ngày nghiệp vụ theo cutoff; pool tĩnh FinRCA từ chối tùy chọn cutoff vì chưa có availability thật. Raw research không đổi policy để vượt gate. Dữ liệu typed không được chạy nhầm qua `reconcile`/`evaluate` v0.1.

### Decision event, retry và Gold

Mỗi dòng lệnh ledger là `{"idempotency_key":"...","command":{...}}`. Command chung có `tenant_id`, `action`, `effective_on`, `available_on`; ngày theo `YYYY-MM-DD`. Thứ tự ingestion theo SQLite sequence, availability không đi lùi; effective phải không muộn hơn available. Không nhận scheduled future-effective hoặc sửa đè event cũ; invoice/payment có thể thêm revision theo contract v0.4. Late arrival/hồi tố giữ ngày nhận thật, không backdate availability.

| Action/kind | Payload và tác động |
|---|---|
| `record` / `invoice`, `payment` | `data`: `tenant_id,id,currency,amount_minor,side,party_id`; invoice thêm `invoice_number`. Khởi tạo version 1; ID lặp dưới key mới bị từ chối. |
| `revise` / `invoice`, `payment` | Full replacement record và `expected_version`; tạo event/version mới, giữ scope và ngày nghiệp vụ. Không sửa event cũ. |
| `record` / `bank` | `data`: `tenant_id,id,currency,amount_minor,direction=credit/debit`. Chỉ bank tạo chuyển động cash; mỗi bank ID một lần, không suy cash từ approval. |
| `record` / `credit_note` | `data` thêm `invoice_id`, giảm nghĩa vụ, không tạo cash; không vượt dư sau allocation. |
| `record` / `refund` | `data` thêm `payment_id`, dùng unapplied credit, không tự đổi allocation. Cần reverse allocation trước nếu không đủ credit; giao dịch bank hoàn tiền là record riêng. |
| `record` / `bank_link` | Payment–bank slices, phí và FX theo các mục trên; tổng tiêu thụ không vượt endpoint. Phí không làm giảm thêm công nợ. |
| `record` / `refund_bank_link` | Refund–bank slices chia sẻ budget bank với `bank_link`; không tạo cash lần hai. |
| `record` / `bank_statement` | Số dư đầu/cuối kỳ, tổng credits/debits và completeness khai báo; dùng đối chiếu bank theo account/kỳ. |
| `suggest` | `decision_id`, `allocations=[{invoice_id,payment_id,amount_minor}]`; kiểm tra endpoint/scope nhưng chưa ghi tiền. |
| `approve` | suggested → approved; không ghi tiền. |
| `cancel` | Hủy suggested/approved, dùng decision ID mới khi đề xuất lại; không thay reversal của allocation đã commit. |
| `commit` | approved + `external_result=verified` → committed, áp allocation một lần; `unknown` → review_required, không giả định thành công/thất bại. |
| `verify` | review_required + `external_result=committed/not_committed` → committed/approved. Outcome do người gọi xác nhận; không phải connector tự xác minh nguồn. |
| `reverse` | committed → reversed, gỡ đúng allocation gốc một lần; không tạo cash và không sửa lịch sử. |

SQLite transaction bao quanh lookup key, kiểm tra replay và insert: cùng key/cùng payload trả sequence/hash cũ; cùng key khác payload hoặc transition/số tiền sai bị từ chối, không đổi số dư. Unknown chặn commit mới trên invoice/payment giao nhau đến khi xác minh. Tính atomic áp dụng **từng command**, không phải cả file JSONL; file nhập dở có thể chạy lại với nguyên key. Đây là ledger local, chưa chứng nhận concurrency/connector bên ngoài.

`gold` replay event có available/effective không sau F, xuất invoice face/credit/allocated/outstanding, payment unapplied/refunded, decision state, document versions, bank/refund links, chuyển động bank theo tenant/currency và lineage sequence/hash. Event nhận sau F không thay snapshot F. Statement cung cấp opening/closing khai báo cho `bank_reconciliation`; thiếu statement/completeness thì không suy số dư đầy đủ từ tổng chuyển động. Chưa có lịch sử SME hoặc feature T1 đã xác minh.

### Mapping nguồn và universe chấm

| Nguồn | Mapping/điều kiện chấm hiện hành |
|---|---|
| FinRCA | Invoice number giữ riêng invoice ID; vendor → party; payment → AP gross; bank giữ direction và transaction/posted date. Chỉ đọc mười CSV clean/full đã xác minh hash, không mở test/challenge RCA. `lineage` giữ file/hash/row. Allocation corrupted vẫn xuất kèm reason; negative invoice cách ly. Clean/corrupted cùng connected component allocation ở cùng split nội bộ development/validation. Bank chưa có oracle/split ghép nên không chấm bank-link; cả chất lượng khôi phục allocation là `null` tới khi oracle phù hợp được xác minh. |
| AR synthetic | Oracle từ intent trước khi che reference; cùng seed và biến thể ở cùng split. Báo exact edge **và amount**, candidate recall, tiền sai/thiếu/unapplied theo currency, tình huống, overflow/runtime/order stability. Late arrival ngoài cutoff báo riêng, không thành negative. Hai seed test mỗi profile chỉ là kiểm chứng máy phát và đã xem trong phát triển. |
| RecBench | Task riêng payout–bank; giữ signed minor và kiểm direction credit/debit. Feature chỉ payout amount/currency/reference/expected arrival và bank amount/currency/reference/value date/direction. Reference xung đột không fallback sang amount; competing payout claims review. Truth thiếu endpoint là unknown, explicit negative cần `is_matchable=false` và không có truth. Báo riêng negative-label có truth, dự đoán trên unknown/nonmatchable; không tự giải thích hoặc xóa endpoint vắng. |
| FISCUS | Chạy đúng bốn fixture bank reconciliation qua state store dự án; 21 ca domain khác báo unsupported. So status và financial effect riêng, không cộng vào accuracy matching. |
| FinBalance | Baseline text giới hạn và detector số học/identity/dependency/running balance; phạm vi policy nêu ở v0.4. Chỉ dùng field quan sát, lưu dự đoán trước evaluator expected journal/balance sheet. Unsupported document vẫn được đếm; detector báo unknown khi thiếu bằng chứng. Replay balance sheet chỉ chart đơn giản và record không còn posting doc unsupported. Corpus chưa có policy/facts độc lập để đánh giá structured engine; entry không tự đưa vào ledger. |

Mỗi lượt ghi experiment trước dự đoán, code/plan hash và môi trường; dữ liệu/prediction/truth có hash và nằm output mới. Kết quả các task giữ riêng. Dữ liệu thật SME, oracle payment–bank FinRCA, RecBench ledger/settlement, FinBalance policy rộng/PDF, nguồn quote FX độc lập, connector và đo tác động T1 vẫn thiếu.

## Contract bổ sung BenchRec GL–bank

Chỉ áp dụng cho snapshot Kaggle version 3 và `t0/benchrec.py`, không thay schema receipt v0.1 hoặc typed AP/AR v0.2. [Thiết kế và cơ sở nghiên cứu](../reports/t0-method-review.md#thiết-kế-benchmark-v1), [lệnh chạy](../../data/T0/README.md).

- Mỗi dòng CSV là A (sổ) hoặc B (ngân hàng), bắt buộc đúng một phía. ID duy nhất từng phía. Adapter xác minh byte/hash từ manifest trước khi parse, dùng allowlist field. Tiền là `Decimal` hữu hạn khác zero có dấu nguyên bản; không lật dấu theo DR/CR, không ngầm lấy trị tuyệt đối để ghép. Không giả định scale currency để chuyển sang schema invoice.
- Feature: `id`, `amount`, `date` từ valueDate, `currency`, `account`, `reference`. ID chỉ dùng định danh/thứ tự tái lập, không chấm tương đồng. Historical match fields, `wasPreviouslyMismatched`, target, solution và submission không được đưa vào matcher. Không dùng thứ tự dòng nguồn để suy quan hệ.
- `A_allocation` được tái tạo đúng từng ký tự bằng `currencyCode_valueDate_account_transactionAttributes`, kiểm tra bằng khóa nguồn rồi giữ làm dictionary output. Không chấm điểm hay blocking theo allocation. Tương đồng text hiện chỉ dùng transactionReferences.
- Nhãn B: chuỗi rỗng, một key, hoặc `[key1,key2,...]`. Giữ khoảng trắng trong key. Nhãn phải phủ đúng toàn bộ B, không lặp ID; key vắng trong A được báo là không thể đạt, không xóa nhãn. Đây là tập đặc tính nghiệp vụ, không xác định duy nhất A ID hoặc phân bổ tiền mỗi cạnh.
- Đầu ra mỗi B có danh sách A ID và tập key không rỗng. Kiểm tra scope currency/account, tổng tiền có dấu bằng B, A không dùng lặp, output key đúng dictionary. Phương pháp hiện tại không ghép chung nhiều B; nhãn N:1/N:M có thể không đạt dù allocation-key hợp lệ.
- Đúng theo card khi tập key dự đoán **không rỗng** và là tập con của tập nhãn. Precision chia số B đúng cho số B dự đoán; match rate chia số B đúng cho B có nhãn không rỗng. Báo thêm exact-set metrics. Không dự đoán thì precision `null`; nhãn rỗng không tạo true positive.
- Tiền gán sai = tổng `abs(B_amount)` trên B có key sai, báo riêng currency. Đây là metric mức giao dịch B, không đồng nghĩa tiền sai từng cạnh invoice. B chưa ghép gọi là cần xem lại, không khẳng định lỗi nghiệp vụ.
- Toàn bộ dự đoán được lưu trước khi load solution trong runner. Đây là đánh giá pool tĩnh; không có cutoff/availability giả định từ importDate. Chưa kiểm định production online hoặc tái lập evaluator chính thức. Nhãn độc lập với code matcher nhưng chưa được nhóm dự án gán nhãn lại.

Harness v1 nằm ở `scripts/data_audit/benchmark_t0_reconciliation.py`, cấu hình cố định trong `reconciliation-benchmark-plan-v1.json`, generator nghiên cứu ở `t0/scenarios.py`. Generator/benchmark tổng hợp ban đầu đã chuyển sang `scripts/archive/t0/`; writer receipt bất biến và evaluator còn ở lõi để tái lập. Số seed, mức nhiễu và giới hạn v1 được duy trì trong [báo cáo](../reports/t0-method-review.md#thiết-kế-benchmark-v1), không dùng tỷ lệ tình huống cân bằng làm tỷ lệ SME.

Các lượt benchmark từ chối thư mục output không rỗng, kiểm tra split/seed/noise và cấu hình số hợp lệ. Dự đoán invoice phải qua invariant trước khi chấm; không được gộp cạnh để che cạnh lặp. BenchRec chấm key yêu cầu danh sách key không rỗng, duy nhất; invariant tài chính kiểm tra riêng A ID/tiền/scope. Lỗi replay hoặc invariant làm lệnh benchmark trả lỗi. `--verify-existing` kiểm định input/nhãn/dự đoán/metric đã lưu bằng code hiện tại và ghi bằng chứng vào output mới; không thay thế kết quả lịch sử hoặc tune theo test.

## Contract receipt v0.1 — hồi quy

Các mục dưới chỉ áp dụng `reconcile`/`evaluate` và baseline lịch sử, không mô tả toàn bộ khả năng package hiện hành.

### Đầu vào và đơn vị mỗi dòng (grain)

JSON Lines UTF-8, mỗi dòng là một object. Không dùng float cho tiền. `amount_minor` là số nguyên theo đơn vị nhỏ nhất của currency do adapter xác định: VND dùng đồng, USD dùng cent. Không cộng tiền giữa các currency. Không đưa tổng tiền đã trả, nhãn hoặc trạng thái suy ra từ tương lai vào input matcher.

| File | Đơn vị một dòng | Khóa bản ghi |
|---|---|---|
| `invoices.jsonl` | Một phiên bản hóa đơn | `tenant_id`, `invoice_id`, `version` |
| `bank.jsonl` | Một phiên bản giao dịch thu ngân hàng | `tenant_id`, `transaction_id`, `version` |
| `truth.jsonl` | Một phân bổ đúng giữa giao dịch và hóa đơn | `tenant_id`, `transaction_id`, `invoice_id` |

`invoice_id` phải duy nhất trong tenant và xuất hiện trong reference nếu muốn dùng rule theo mã. Khi ERP dùng ID nội bộ khác số hóa đơn, adapter phải cung cấp mapping phù hợp; receipt v0.1 chưa tách `invoice_number`. Một giao dịch có thể trả nhiều hóa đơn; một hóa đơn có thể nhận nhiều giao dịch. Một cạnh có một tổng phân bổ tại cutoff; muốn lưu từng quyết định/đảo cần bảng event riêng, không thuộc đường receipt v0.1.

Các field chung bắt buộc:

| Field | Quy ước |
|---|---|
| `tenant_id` | Chuỗi không rỗng, phân biệt doanh nghiệp |
| `version` | Số nguyên dương, tăng theo phiên bản, không tăng lùi ngày availability |
| `currency` | Mã ba chữ cái ASCII viết hoa; adapter chịu trách nhiệm xác minh mã và scale |
| `amount_minor` | Số nguyên dương; `bool`, float, số âm và zero đều bị tách lỗi |
| `effective_on` | Ngày phiên bản có hiệu lực nghiệp vụ |
| `available_on` | Ngày pipeline thực sự dùng được dữ liệu, sau độ trễ nhận/chuẩn hóa; có thể muộn hơn ngày nghiệp vụ |

Ngày dùng đúng định dạng `YYYY-MM-DD`. Receipt v0.1 có độ phân giải **ngày**, chưa mô tả thứ tự sự kiện trong ngày.

Hóa đơn còn có `invoice_id`, `customer_id` không rỗng, `customer_name` (chuỗi, có thể rỗng), `issued_on`, `due_on`. `due_on >= issued_on`; due date được yêu cầu bởi các baseline dùng cửa sổ ngày, không phải điều kiện chung cho mọi giải pháp T0/T1.

Ngân hàng còn có `transaction_id`, `customer_id`, `counterparty`, `reference` (đều là chuỗi; có thể rỗng), `booked_on`. `customer_id` của bank chỉ điền khi đã biết ở cutoff từ nguồn độc lập. Không lấy mapping customer từ truth. `booked_on` là ngày ghi nhận ngân hàng trong thí nghiệm, chưa xác nhận là value date hoặc thời điểm tiền dùng được.

### Snapshot tại ngày F

1. Chỉ xét dòng có `available_on <= F`. Nội dung sửa đổi nhận sau F không được làm thay đổi snapshot cũ.
2. Delivery giống hệt được bỏ trùng. Hai payload khác nhau có cùng khóa/phiên bản làm cả bản ghi bị cách ly, tránh chọn theo thứ tự file.
3. Kiểm tra các phiên bản đã biết. Phiên bản lỗi không được khiến hệ thống âm thầm dùng lại phiên bản cũ. Chọn version cao nhất có `effective_on <= F` và ngày issue/booked không vượt F.
4. Giữ raw nguyên trạng. Trả riêng số dòng tương lai, delivery trùng và danh sách lỗi; không sửa raw hoặc đoán ngày/tiền để chạy qua gate.

Ví dụ: giao dịch xảy ra ngày 10 nhưng nhận ngày 12 chỉ dùng được từ ngày 12. Hóa đơn sửa hồi tố nhận ngày 20 không làm thay đổi snapshot ngày 19. Đây là phép chọn as-of trên dữ liệu phiên bản, chưa phải database bitemporal có transaction hoặc event store bền vững.

### Phương pháp và quyết định

Tất cả phương pháp đều chặn tenant/currency/customer đã biết không khớp, giao dịch trước ngày phát hành và tuổi hóa đơn vượt `max_age_days` (mặc định 120). Chúng nhận **snapshot đã kiểm tra**, không nhận truth.

| Tên CLI | Cách xử lý |
|---|---|
| `exact_reference` | Mã hóa đơn trong reference và số tiền bằng dư hóa đơn; chỉ một hóa đơn mỗi lần |
| `amount_date` | Khớp số tiền bằng dư và ngày bank cách due không quá 14 ngày; chỉ tự động nếu không mơ hồ |
| `scored_global` | Sinh cặp cùng số tiền; điểm theo mã, customer/tên và gần due; chặn ngưỡng/mơ hồ, gán 1–1 tối đa tổng điểm bằng Hungarian có lựa chọn không khớp |
| `reference_then_global` | Xử lý mã rõ trước: trả từng phần một hóa đơn, hoặc trả gộp đúng tổng dư các hóa đơn được nhắc và cùng customer; sau đó áp dụng scorer/gán 1–1 cho phần còn lại |

Điểm scorer không có mã = `0.65 × identity + 0.25 × name_similarity + 0.10 × due_proximity`. `identity=1` khi có customer bank đã xác nhận, nếu thiếu thì dùng name similarity. Text chuẩn hóa dấu/chữ hoa/ký tự phân cách; so tên bằng `SequenceMatcher`. Mã đúng cho điểm 1, vẫn phải qua các ràng buộc tiền/phạm vi.

Tên rỗng không được coi là bằng chứng trùng tên. Với phương pháp có scorer, nếu reference nhắc một mã hóa đơn đã biết trong tenant, không tự động chuyển sang hóa đơn ngoài các mã đó chỉ vì số tiền/tên khớp. Baseline `amount_date` cố ý chỉ dùng tiền và ngày.

Ngưỡng mặc định 0.72, margin 0.08 là **cấu hình kỹ thuật chưa hiệu chỉnh**, không phải xác suất đúng. Một cặp chỉ được giữ nếu đạt ngưỡng và hơn các lựa chọn cạnh tranh của bank/invoice đủ margin; vì gate bảo thủ này, assignment thường ít xung đột còn lại. Không suy từ Hungarian rằng chất lượng nghiệp vụ tối ưu. Các rule theo mã xử lý bank theo ngày rồi ID, tính chất ưu tiên này được giữ cố định cho khả năng tái lập.

Output gồm `allocations.jsonl` (tiền, ngày, lý do, điểm), `decisions.jsonl` (`auto`, `review`, `unmatched`) và `audit.json` (quality, cutoff, cấu hình, hash input và kết quả). `review` có ứng viên nhưng chưa tự động; `unmatched` không có ứng viên theo phương pháp hiện tại. Đây là gợi ý offline, chưa ghi vào sổ ERP. `auto` vẫn có thể sai và cần được đo.

Kiểm tra phân bổ: endpoint tồn tại cùng tenant/currency; số tiền nguyên dương; không lặp cạnh; tổng phân bổ không vượt hóa đơn hoặc khoản thu; `payment_on = booked_on` và không trước ngày phát hành. Tiền chưa phân bổ được giữ riêng. Kiểm tra này bảo đảm tính nhất quán nội bộ, chưa chứng minh số dư ngân hàng khớp sổ.

### Đánh giá chất lượng và ổn định

Truth (nhãn phân bổ đúng) phải độc lập và đầy đủ cho toàn bộ phạm vi được chấm, bao gồm khoản thu không ứng với hóa đơn nào. CLI `evaluate` yêu cầu `--truth-exhaustive` để người chạy xác nhận điều kiện này. Chỉ có một ít cặp đúng chưa đủ để kết luận precision. Chưa có truth thì chạy `reconcile`, chỉ xem chất lượng dữ liệu, tỷ lệ xử lý và các ràng buộc phân bổ.

- Một cạnh đúng cần đúng cả hai ID, currency và số tiền. Precision = cạnh đúng / cạnh tự động; recall = cạnh đúng / cạnh truth có endpoint hợp lệ, quan sát được tại F. Nếu mẫu số zero thì trả `null`. Có đếm riêng truth bị loại vì endpoint chưa có trong snapshot; ID truth không tồn tại trong raw bị báo lỗi.
- Candidate recall = cạnh truth xuất hiện trong tập ứng viên trước ngưỡng / cạnh truth. Ứng viên phụ thuộc phương pháp và số dư sau các rule trước đó; không so chỉ số này mà bỏ qua khác biệt blocking.
- Báo riêng tỷ lệ auto/review/unmatched trên **khoản thu**, và kết quả từng scenario. Tỷ lệ auto cao không tự chứng minh khớp đúng.
- Theo từng currency: tiền gán vượt số đúng trên mỗi cạnh, tiền truth còn thiếu và tiền chưa phân bổ. Không quy đổi tỷ giá ngầm; tiền thiếu và gán sai là hai đại lượng riêng.
- Sai số `payment_on` chỉ tính trên cạnh đúng. Vì matcher chép ngày bank, đây chủ yếu là kiểm tra truyền ngày, chưa đánh giá khả năng khôi phục ngày tiền khả dụng thật.
- Đo runtime matcher, không gồm đọc file, snapshot hoặc replay. Kiểm tra hash phân bổ không đổi khi đảo thứ tự và nạp lặp dữ liệu; unit test thêm sửa hồi tố, availability, phạm vi và bảo toàn tiền.

Bộ benchmark tổng hợp ban đầu, nay ở `scripts/archive/t0/benchmark_t0_receipts_v01.py`, có ba profile `clean/noisy/stress`, mỗi profile 3 seed validation (11–13) và 5 seed test (101–105), cùng input cho cả bốn phương pháp. Không train hoặc tune ngưỡng trong harness. Báo mean/std/min/max theo seed và bootstrap chênh lệch recall ghép cặp so baseline. Khoảng này chỉ phản ánh biến thiên máy phát, không đại diện bất định ngoài doanh nghiệp. Sau khi xem test, cần seed/bộ test mới nếu tiếp tục tune theo kết quả đó. Benchmark nhiều seed này chưa thay thế backtest rolling-origin của dữ liệu thật.

### Giới hạn đường receipt v0.1

Các audit nguồn một phía chưa phải adapter vào schema hóa đơn. Riêng BenchRec có adapter GL–bank và harness riêng theo contract ở trên; [quy trình và kết quả](../../data/T0/README.md). `reconcile`/`evaluate` vẫn chặn manifest có `use_policy=inspection_only_excluded_from_matching` qua `t0/data.py`, độc lập với collector đã lưu trữ; gate này không tự xác minh mọi input hoặc quyền tái sử dụng. Không sinh hóa đơn/nhãn, suy currency hoặc đặt availability bằng ngày giao dịch để bù field thiếu.

Receipt v0.1 không xử lý payment ledger, credit note/phí/refund, FX hoặc reversal; giao dịch âm vẫn bị cách ly ở đường này. Ledger và FX v0.4 là các đường riêng, không thay đổi ý nghĩa kết quả receipt. Connector MISA/FAST/ngân hàng, chargeback, số dư ngân hàng được xác minh đầy đủ và kiểm chứng SME/T1 vẫn chưa có.

[Kế hoạch tiếp tục T0](../../research/notes/t0_data_foundation_reconciliation.md#kế-hoạch-tiếp-tục-t0) theo contract hiện hành ở đầu trang. Các snapshot research vẫn giữ policy chỉ kiểm tra; nhãn RCA, reference join hoặc expected journal không tự đáp ứng `truth-exhaustive` cho invoice–bank.
