# Đợt 4 — bổ sung bằng chứng, đối chứng và đánh giá độc lập

Đã bổ sung nguồn và logic cho C4/E2/F2/F3/F4, đối chứng dương/ngoại lệ cho A5/A6/B6/B7/C1/C3/E3 và nhãn can thiệp riêng ở cấp cửa sổ cho D1–D6. [Kết quả](rule_repairs/phase4/summary_vi.md) dùng cấu hình vận hành 7 và A5 log/MAD z=3,5 của đợt 3; không chọn lại ngưỡng theo test hoặc train/chấm ML.

## Chính sách của năm rule mới

| Rule | Bằng chứng cần có | Quyết định và ngoại lệ |
| --- | --- | --- |
| C4 | Nghỉ phép theo khoảng ngày/giờ đã duyệt; log maker/checker gắn đúng giao dịch, người và thời điểm thao tác. | Thao tác trong `[starts_at, ends_at)` khi lịch nghỉ đã biết trước thao tác: 8 điểm. Quyền làm việc trong nghỉ phép phải gắn đúng người/leave/action/khoảng giờ, có người duyệt độc lập và đã biết trước thao tác. Hủy nghỉ sau thao tác không sửa trạng thái lúc thao tác. Tổng ngày nghỉ tháng không đủ. |
| E2 | Sự kiện nghỉ việc/tái tuyển dụng; kỳ công, loại chi và quyền chi của giao dịch lương. | Lương thường cho kỳ công **bắt đầu sau ngày chấm dứt**: 20 điểm/hard trigger. Truy lĩnh/quyết toán/trợ cấp/thưởng cho thời gian trước nghỉ việc, đúng số tiền/kỳ đã duyệt: loại. Kỳ công giao thời hoặc thiếu loại chi/quyền chi: information gap, 0 điểm. Tái tuyển dụng có hiệu lực đã biết được đối chiếu trước khi dùng sự kiện nghỉ cũ. |
| F2 | Log thực thi override/control bị bỏ qua; phiên bản workflow có hiệu lực và đã duyệt trước thao tác. | Bypass control bắt buộc ngoài vai trò/hạn mức được cấp: 8 điểm. Quy trình đã hoàn thành/override hợp lệ: loại. Không có chính sách: information gap, 0 điểm. Ngoại lệ một control không bao phủ các control khác trên cùng giao dịch. |
| F3 | Dãy số nội bộ khai báo theo company/series/type/year; sổ phát hành và nhật ký hủy đã duyệt. | Hai **chứng từ vật lý khác nhau**, còn hiệu lực, trùng số trong cùng series: hit ngữ cảnh 3 điểm, cần anchor độc lập để góp điểm. Khoảng trống chỉ kiểm tra dải `start_number..closed_through_number` đã khóa/được duyệt; cần xác nhận nhật ký hủy đầy đủ. Gap là hồ sơ nguồn riêng, 0 điểm giao dịch. Không dùng ID giao dịch ngẫu nhiên hoặc ép hóa đơn mọi NCC vào một dãy liên tục. |
| F4 | Sổ công nợ hóa đơn, customer, hạn trả; allocation đã xác minh gắn receipt thực; xác nhận sổ thu tiền đầy đủ đến cutoff; giải trình được duyệt/còn hiệu lực. | Dư nợ >0 và **quá hạn >60 ngày từ hạn trả**, chưa có giải trình hợp lệ: yêu cầu rà soát thu hồi công nợ, 0 điểm giao dịch. Thu đủ/giải trình đúng hồ sơ: loại. Thiếu coverage, customer chưa quan sát, sai ghép hoặc phân bổ vượt tiền thu thực: information gap; không suy thiếu receipt thành chưa trả. Không coi công nợ quá hạn là doanh thu giả. |

Nguồn nghỉ việc là bản ghi HR có phê duyệt, không phải suy đoán từ thiếu chấm công. Loại chi E2 hỗ trợ `regular_salary/backpay/final_settlement/severance/bonus`; quyền chi có ID giao dịch nên không dùng lại ngoại lệ cho một khoản khác. Lương thường sau nghỉ việc không thoát điều kiện chỉ vì số tiền vượt trần nguồn quyền chi. Các trường hợp hỗn hợp cần đối chiếu phân bổ kỳ công, chưa được tự kết luận.

E2 được thêm vào hard triggers khi có đủ nguồn xác nhận. C4/F2 vẫn là tín hiệu kiểm soát, không phải kết luận hình sự/gian lận. Điểm lớn nhất theo nhóm và recurrence giữ nguyên; F1/F2 cùng nhóm F không cộng cả hai trọng số. C4 không hỗ trợ mọi loại truy cập hệ thống: phạm vi hiện tại là maker/checker gắn chứng từ.

F3 gap và F4 aging được lưu ở `evidence_findings.jsonl`/`controlled_source_findings.jsonl`, tách khỏi `rule_hits.jsonl` của giao dịch. Có thể kiểm tra vào ngày không có giao dịch bằng [source_snapshot.py](../sme_fraud/source_snapshot.py), không cần tạo bút toán giả làm đồng hồ. Cutoff có timezone, được chuẩn hóa về +07:00. Hóa đơn/công nợ dựa trên sổ chi tiết nguồn; chưa kiểm chứng đầy đủ BCTC/số dư đầu kỳ, bù trừ, ngoại tệ và mọi loại điều chỉnh VAT.

## Schema và cách nạp nguồn

[Schema máy đọc](../sme_fraud/evidence_sources.schema.json) và [14 CSV mẫu chỉ có header](../examples/phase4_sources) cung cấp các cột. Các file này là hợp đồng đầu vào; không có dữ liệu SME thật được tự điền.

| File | Nội dung nghiệp vụ |
| --- | --- |
| `leave_periods.csv` | `leave_id, employee_id, starts_at, ends_at` và phê duyệt |
| `system_actions.csv` | `action_id, transaction_id, employee_id, action, action_at, evidence_id` |
| `leave_activity_authorizations.csv` | Quyền làm việc trong một leave/action/khoảng giờ, có phê duyệt |
| `employment_events.csv` | `employment_event_id, employee_id, event_type=termination/rehire, effective_date` và phê duyệt |
| `payroll_settlements.csv` | `settlement_id, employee_id, transaction_id, payroll_period, payment_kind, service_period_start/end, authorized_amount_vnd` và phê duyệt |
| `workflow_policies.csv` | `workflow_policy_id, control_id, txn_type, required, allow_override, authorized_override_roles, override_max_vnd, effective_from/to` và phê duyệt |
| `override_events.csv` | `override_id, transaction_id, actor_id, operation_at, control_id, status=executed, normal_workflow_completed, evidence_id` |
| `document_series.csv` | `series_id, fiscal_year, document_type, start_number, closed_through_number, closed_at, cancellation_log_complete` và phê duyệt |
| `document_register.csv` | `register_id, series_id, document_id, document_number, transaction_id, issued_at, state=issued, evidence_id` |
| `document_cancellations.csv` | `cancellation_id, series_id, document_id, document_number` và phê duyệt |
| `receivable_invoices.csv` | `invoice_id, customer_id, gross_vnd, issued_at, due_at, status=issued, evidence_id`; đây là sổ chi tiết công nợ nguồn |
| `receipt_allocations.csv` | `allocation_id, invoice_id, customer_id, receipt_transaction_id, amount_vnd, status=verified, verifier_id, verified_at, evidence_id` |
| `receipt_coverage.csv` | `coverage_id, covered_from, covered_through` và phê duyệt xác nhận dữ liệu thu tiền đầy đủ đến cutoff |
| `receivable_explanations.csv` | `explanation_id, invoice_id, reason, effective_from, expires_at` và phê duyệt |

Tất cả có `company_id, observed_at`; file có phê duyệt thêm `status, approver_id, approved_at, evidence_on_file, evidence_id`. Cờ dùng 0/1; VND nguyên; date dùng YYYY-MM-DD; timestamp nguồn ISO +07:00. `authorized_override_roles` phân tách bằng `|`. Giải trình F4 hỗ trợ `payment_plan/dispute/credit_note_pending` và phải còn hiệu lực.

Mỗi source ID giữ nguyên ràng buộc entity/giao dịch/company/series qua các phiên bản; revision là bản ghi đầy đủ, kể cả trạng thái thu hồi. Latest revision lấy tại **thời điểm thao tác** cho C4/F2 và tại cutoff cho nguồn còn lại. ID trống, revision cùng timestamp mâu thuẫn, đổi ràng buộc nguồn hoặc thiếu cột bắt buộc bị từ chối. Loader chỉ đọc allowlist, kiểm SHA-256 của file trong `manifest.json` và không đọc nhãn vào detector. Cần bổ sung entry `files[filename]` với số dòng/SHA đúng khi gắn nguồn vào một dataset mới; không sửa manifest của dataset gốc để giả có hồ sơ.

Quyền/role của actor lấy từ phiên bản master tại thao tác; approver/verifier lấy tại chính lần phê duyệt/xác minh. Sửa hồ sơ sau đó không xóa phê duyệt quá khứ hoặc cấp ngược quyền override. Đây là kiểm tra nhân quả của nguồn; chưa có đầy đủ ma trận thẩm quyền duyệt mọi chính sách HR/workflow. B6 vẫn chưa có ngoại lệ hợp đồng năm/mùa vụ đầy đủ; C3 vẫn dùng proxy số tiền. Các giới hạn này cần nguồn và đối chứng nghiệp vụ thêm trước nghiệm thu.

Receipt F4 phải là giao dịch `customer_receipt`, cùng company/customer, tài chính, tiền/ngân hàng, đã posted; xác minh không trước thời điểm thu thực. Tổng phân bổ trên cùng receipt không vượt số tiền thu; mỗi allocation ID chỉ giữ phiên bản mới nhất. Coverage không thể xác nhận tương lai: `covered_through <= observed_at <= cutoff` và phải bao phủ đến chính cutoff. Thực tế có thể chọn cutoff là thời điểm đồng bộ bank/AR hoàn chỉnh thay vì cố khẳng định dữ liệu phút hiện tại đã đầy đủ.

## Đối chứng và nhóm D

[source_cases.jsonl](rule_repairs/phase4/source_cases.jsonl) lưu đầu vào kế toán/bằng chứng sau chuẩn hóa nhưng trước chấm, [source_truth.jsonl](rule_repairs/phase4/source_truth.jsonl) lưu kỳ vọng được khai báo trước. Mỗi case là một dataset độc lập; không nối các case bằng ID nội bộ giống nhau. Có 43 biến thể × 7 seed = **301 case**, gồm 2 seed train, 2 validation và 3 test. Nhãn là điều kiện rule đã biết, không phải nhãn tội gian lận.

A5 có cao/thấp/bình thường; A6 có làm tròn vượt hóa đơn và trả dưới gross; B6 có ngủ đông vượt P90 và đối chứng thấp hơn P90; B7 có đổi TK chờ hiệu lực/unverified và callback độc lập hợp lệ; C1 có ngoài giờ và ca đêm đã duyệt; C3 có thời gian duyệt 10–30 giây và 600 giây; E3 có biến thể cố ý, tên gần giống của pháp nhân hợp lệ và tên khác biệt. E3 gần giống hợp lệ vẫn có thể là candidate tên, nhưng 0 điểm/master và không tự hard trigger. C3 vẫn dùng số tiền làm proxy thẩm quyền; chưa có đầy đủ ma trận duyệt.

Nhóm D dùng **56 tập cửa sổ độc lập theo seed/pattern**, tạo **336 phép đối chiếu rule–scope–cutoff**, gồm phân phối tự nhiên, can thiệp chữ số đầu/thứ hai, tăng đuôi tròn, tăng số tiền gần hạn mức, cặp 98/99 ở số tiền rất thấp, mẫu quá nhỏ và khoản cố định hợp lệ. Cửa sổ đủ mẫu dùng 3.000 dòng baseline +3.000 dòng current; không lấy một dòng gian lận để gọi toàn cửa sổ là gian lận.

D3 phase4 giữ kiểm tra hai chữ số đầu nhưng yêu cầu các số tiền thực trong 80%–dưới 100% hạn mức cho phần excess cận ngưỡng. Baseline kỳ vọng còn là kiểm tra sàng lọc toàn phân phối, không phải một kiểm định nhân quả về né duyệt. D6 hỗ trợ creator, department và project_id. Không hạ min_rows: 300 cho chữ số đầu, 1.000 cho chữ số hai/cặp, cùng kiểm tra độ rộng/đa dạng/ô kỳ vọng. Các dataset SME thực tế mô phỏng vẫn có thể không đủ D3; tập dense là stress test năng lực, không chứng minh SME nào cũng có volume phù hợp.

Phase4 dùng BY cho các p-value ở cùng cutoff vì có phân đoạn phụ thuộc/chồng lặp. D5 là MAD mô tả, D4 là so tỷ lệ đuôi với baseline quá khứ, không được gán ý nghĩa p-value. D4 đuôi có baseline bằng 0 là unknown/partial, không tính như negative đúng. Tham chiếu phương pháp: [SciPy chi-square](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html), [SciPy điều chỉnh FDR](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html). Các bộ min_rows/baseline/tham số VND là chính sách của dự án, không phải quy định của SciPy hoặc pháp luật Việt Nam.

## Đánh giá và giới hạn nghiệm thu

Sinh **350.000 dòng mới**, 7 bộ 50.000 dòng: 1 seed validation tại 0,3%; 2 seed test tại mỗi tỷ lệ 0,1%/0,3%/0,5%. Mỗi bộ giữ thời gian train/validation/test 50%/25%/25%; mỗi test có 12.500 dòng và lần lượt 12/37/62 fraud nên bất định còn lớn. Không fit mô hình trên phần train; phần này chỉ tạo lịch sử nhân quả cho rule.

Các bộ SME mới vẫn là generator sáu nhóm, **chưa có nguồn HR/ERP/AR thật**. Vì vậy không có độ chính xác triển khai thực tế của năm rule mới trên các bộ này; conformance của nguồn được đo riêng bằng case. Không đổi label/master gốc để làm đẹp precision, không biến số case đối chứng đạt thành precision gian lận.

`evaluation.json` chứa TP/FP/precision/recall, số mẫu, Wilson theo dòng, bootstrap 299 lần theo block company/tháng, hard negatives và replay. Bootstrap mô tả bất định của các mô phỏng đã chấm; ít company/seed và phân phối generator chưa đại diện SME thật. `rule_metrics.jsonl` tách góp điểm và tín hiệu chưa loại, không coi mọi FP nhãn tài chính là predicate sai. `budget_metrics.jsonl` so ngân sách 1/3/5 hồ sơ mới/công ty/ngày theo điểm/priority lúc **mở**, chỉ ghi công phát hiện fraud đã quan sát trong ngày mở; không dùng điểm/thành viên tương lai. Chưa mô hình hóa toàn bộ backlog, tái rà soát hoặc SLA thực tế.

F3 gaps/F4 aging chưa có màn hình source riêng trong UI; đọc JSONL hoặc dùng CLI snapshot. Ngân sách trên chỉ đo hàng đợi giao dịch, chưa cộng công việc rà soát các hồ sơ nguồn này. Database QA seed riêng, không thay feedback/DB hiện có. Kiểm tra backend không thay kiểm tra trực quan trình duyệt.

Ba prefix 10.000 dòng của snapshot gốc giữ nguyên điểm/cảnh báo: kiểm 30.000 dòng quá khứ, **không phải chấm lại toàn bộ 300.000 dòng gốc**. Dataset gốc, nhãn, mô hình và phản hồi người dùng giữ nguyên. Runner/fixture đợt 1–3 ghim `evidence_policy=disabled`; engine mới mặc định phase4. Benford giữ definition legacy nếu không truyền phase4 để đọc lại pipeline lịch sử.

Nghiệm thu kỹ thuật: **135 test qua**, 301/301 case điều kiện nguồn, 336/336 phép đối chiếu rule–cửa sổ. [validation.json](rule_repairs/phase4/validation.json) có checksum, frozen plan, replay, hàng đợi, ngân sách và kiểm tra backend ReviewStore cho hai seed test/sáu snapshot. Các tỷ lệ 100% này chỉ là conformance trên đối chứng đã xây dựng, không phải precision gian lận thực tế. Test SME 0,3% chỉ đạt precision 14,78%/17,86% với FP 196/161; vẫn cần nguồn và rà soát nghiệp vụ để giảm nhiễu.

## Chạy lại

```powershell
python -m unittest discover -s tests -v
python -m sme_fraud.run_evidence_evaluation --output reports/rule_repairs/phase4_new --data-root data/rule_evidence_phase4_new
# Chấm lại đầu vào đã có, không sinh/ghi đè dataset:
python -m sme_fraud.run_evidence_evaluation --reuse-data --output reports/rule_repairs/phase4_rescore --data-root data/rule_evidence_phase4
python -m sme_fraud.source_snapshot --data data/your_sme_with_evidence --as-of 2025-09-30T23:59:59+07:00 --output reports/your_sme/source_findings_20250930.jsonl
# Xem hàng đợi seed mới với database riêng:
python -m sme_fraud.review_server --data-root data/rule_evidence_phase4/seed_2026101402 --reports-root reports/rule_repairs/phase4/seed_2026101402 --database .runtime/review/phase4_seed_2026101402.sqlite3 --port 8769
```

Sau đợt này cần thu nguồn HR/ERP/thu tiền thực, chuẩn hóa revision/coverage và lấy kết luận rà soát độc lập trên tập SME mới. Tiếp tục xử lý FP từ A1/A2 và liên kết nghiệp vụ; chưa đạt cổng chất lượng để quay lại ML chỉ vì các đối chứng đặc tả đã qua.
