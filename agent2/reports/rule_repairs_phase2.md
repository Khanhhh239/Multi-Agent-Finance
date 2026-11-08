# Đợt 2: nguồn nhiễu và cơ chế cộng điểm

Đã triển khai phân vai tín hiệu, nguồn lịch ca/chứng từ và baseline A5 mới. [Kết quả validation/test](rule_repairs/phase2/summary_vi.md) so với snapshot sau đợt 1, cùng ngưỡng vận hành 7. Dữ liệu, nhãn, feature cache và model gốc được giữ để đối chiếu.

## Tách vai trò của tín hiệu

| Vai trò | Rule | Cách vận hành |
| --- | --- | --- |
| Chất lượng master | E3, B5/E4 | Lưu phát hiện riêng, không cộng điểm giao dịch; không tự gộp hai pháp nhân hoặc kết luận gian lận |
| Ngữ cảnh | C1, A5, B3 | Giữ hit và dữ kiện. Chỉ góp điểm khi cùng giao dịch đã có bằng chứng độc lập đủ ngưỡng vận hành |
| Kiểm tra giao dịch | Các rule còn lại | Gộp max theo nhóm như trước; hard trigger được giữ. A4/A2 yếu vẫn không tự cộng chồng trong cùng nhóm A |

`intrinsic_points` ghi trọng số trước phân vai, `points` ghi phần thực sự góp vào điểm giao dịch. `scoring_role`, `score_reason` và `anchor_rule_ids` giúp phân biệt ngữ cảnh với bằng chứng chính. Ngoại lệ hợp lệ vẫn có 0 điểm và không hard trigger.

C1/A5/B3 không được dùng để biến một cụm tín hiệu yếu thành hồ sơ vận hành. A5 không bổ sung điểm cho một anchor cùng nhóm A vì cùng dựa vào số tiền. Điểm tái diễn chỉ cộng khi base đủ ngưỡng; cùng timestamp vẫn cập nhật lịch sử sau cả batch.

Đây là phân loại và thay đổi cách cộng điểm, không phải chứng minh mọi predicate đúng. Giảm số dòng góp điểm không đồng nghĩa FP logic của tín hiệu bằng 0. Các tín hiệu yếu chưa đủ nguồn còn trong `rule_hits.jsonl` để đối chiếu và thu thập bằng chứng.

## E3: dữ liệu tên và đối chứng độc lập

Tên dạng `Công ty mô phỏng đối tác <số>` không chứa danh xưng phân biệt để kiểm tra fuzzy match. Engine ghi vấn đề vào `master_name_quality.csv`, thay vì so hàng nghìn tên cùng tiền tố rồi chấm rủi ro lên mọi giao dịch.

Tên có nội dung được chuẩn hóa Unicode/không dấu và loại các từ pháp nhân thông dụng. So khớp vẫn là SequenceMatcher, ngưỡng 85%; chưa phải mô hình xác minh pháp nhân. Không sửa tên master gốc hoặc dựa vào nhãn gian lận để tạo tên mới.

`name_challenge.csv` có 540 cặp tên hư cấu ở seed riêng: biến thể dấu câu/loại hình pháp nhân, tên tương đồng của hai bên liên quan hợp lệ và tên độc lập cùng loại hình. Quan hệ và kỳ vọng được khai báo trước khi chạy matcher. Cặp gần giống không đồng nghĩa cùng thực thể hoặc gian lận; MST hư cấu và trạng thái công bố quan hệ được giữ để minh họa đối chiếu sau so khớp. Chưa dùng tên thật hay xác nhận hiệu quả trên master SME thật.

## B5/E4: một bằng chứng master

B5 là mã chuẩn của hit, E4 được giữ trong `aliases`. Cặp rule dùng cùng `evidence_id`, cùng dữ kiện. `master_findings.jsonl` gộp lần xuất hiện theo ID bằng chứng, có số lần xuất hiện và thời điểm đầu/cuối; không tạo hai phiếu kiểm tra cùng nội dung.

Chỉ chung địa chỉ được ghi `shared_address_only`, khác với chung TK/SĐT. `declared_vendor_ids` chỉ liệt kê các NCC đã công bố quan hệ trước lúc chấm, không tự cấp ngoại lệ cho cả cụm hoặc miễn kiểm tra B1/A3. Đồ thị và các kiểm tra giao dịch liên quan nhân viên vẫn hoạt động.

UI hiển thị một card `B5 / E4`, phân biệt thông tin danh mục với ngữ cảnh và ngoại lệ. Các kiểm tra master không nằm trong bộ lọc hồ sơ giao dịch của snapshot mới. Phần master ngoài hàng đợi giao dịch có trong artifact riêng.

## C1: lịch làm việc, hai thời điểm riêng

Nguồn `operating_schedules` hỗ trợ lịch theo công ty, vai trò hoặc nhân viên; áp dụng riêng cho `maker`/`checker`. Bản ghi phải được duyệt, có dẫn chiếu bằng chứng, được quan sát trước chính thời điểm thao tác và có hiệu lực.

Kiểm tra giờ lập và giờ duyệt dùng phiên bản nguồn tại từng mốc. Lịch được hủy giữa hai mốc không làm mất quyền vận hành đã có ở mốc lập. Hỗ trợ ca qua đêm, thứ trong tuần và quyền làm ngày lễ; lịch nhân viên/vai trò cụ thể ưu tiên hơn lịch công ty. Khi thiếu nguồn lịch, giữ lịch mặc định cũ và ghi C1 như ngữ cảnh, không suy từ nhãn weekend_operations rằng tất cả Chủ nhật đều hợp lệ.

Schema `operating_schedules.csv`: `schedule_id`, `company_id`, `employee_id`/`role` tùy chọn, `action` (`all/maker/checker`), `weekdays` (`0`=thứ Hai đến `6`=Chủ nhật, phân cách dấu phẩy), `start_time`, `end_time` (`HH:MM`, cuối ca không bao gồm), `holiday_work_allowed`, `effective_from`, `effective_to`, `status=approved`, `evidence_id`, `evidence_on_file`, `approver_id`, `approved_at`, `observed_at`.

## A1/A2: gắn chứng từ cụ thể

A1 dùng cùng kiểm tra trả góp của A2 nhưng trên cửa sổ ngắn. Các đợt của hóa đơn hiện tại vẫn được loại khi có hóa đơn khác xen kẽ; không gọi hóa đơn khác là trả góp. Tổng đã trả cho hóa đơn trên toàn lịch sử và trần hợp đồng đã duyệt vẫn được kiểm tra. P1 tiếp tục phát hiện trả vượt gross.

Nguồn `procurement_links` liên kết từng giao dịch với yêu cầu chi và PO đã xác minh. Chỉ các khoản có **cả yêu cầu và PO khác nhau**, cùng đúng công ty/NCC và bằng chứng xác minh, mới được loại khỏi cụm của chứng từ hiện tại. Cùng yêu cầu/PO hoặc nguồn chưa xác minh vẫn được giữ. Mã `project_id` hay chuỗi `request_id` tự khai trong giao dịch không tự cấp ngoại lệ; không miễn toàn bộ NCC.

Schema `procurement_links.csv`: `link_id`, `company_id`, `vendor_id`, `transaction_id`, `request_id`, `purchase_order_id`, `status=verified`, `evidence_id`, `verifier_id`, `verified_at`, `observed_at`. Các cập nhật quan hệ phải có mốc quan sát mới. Nếu có hợp đồng/lịch trả góp, dùng nguồn `supplier_payment_agreements` của đợt 1 để đối chiếu trần.

Dataset gốc chưa có nguồn này. Phần giảm nhiễu do phân biệt đơn mua độc lập được kiểm tra bằng fixture có nguồn; không tự suy đơn mua từ nhãn gian lận, tên NCC hoặc mã dự án giả lập. Các cụm A1 chưa có nguồn nghiệp vụ độc lập vẫn cần rà soát; đây là phần việc còn lại để giảm FP tiếp.

## A5: lịch sử phù hợp, đuôi dài và chi định kỳ

Thử baseline cũ và ba mức cắt 2,5/3,0/3,5 cho baseline `log_mad` trên validation 0,3%. Mỗi cấu hình phải giữ đối chứng khoản 3 triệu sau 25 khoản quanh 1 triệu. Chọn theo tín hiệu trên hard negatives và dòng nền của validation; A5 chưa có nhãn gian lận dương riêng nên không tối ưu “recall A5” từ mọi loại gian lận.

Baseline mới dùng cùng công ty, loại nghiệp vụ, NCC/nhân viên/khách hàng hoặc phòng ban, và danh mục chi phí/nghiệp vụ. Không fallback gộp NCC ít lịch sử với NCC khác quy mô. Lịch sử tối đa 256 quan sát trong 180 ngày, tối thiểu 20 mẫu; không đủ lịch sử thì chưa đánh giá.

Tính trung vị trên `log1p(amount)`, MAD là trung vị khoảng cách tuyệt đối tới trung vị. Scale là `max(0,25; MAD/0,67448975)`. Chỉ xét đuôi cao; các giả định floor/cửa sổ/ngưỡng là cấu hình thử của dự án. Đây là **median absolute deviation**, khác MAD Benford D5. [Định nghĩa và chuẩn hóa MAD của SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html).

Nguồn `recurring_payments` loại các khoản đúng thỏa thuận định kỳ đã duyệt, theo đúng đối tượng, nghiệp vụ và trần dung sai. Schema: `pattern_id`, `company_id`, `vendor_id`/`employee_id`, `txn_type`, `expected_amount_vnd`, `tolerance_vnd`, `effective_from`, `effective_to`, `status=approved`, `evidence_id`, `evidence_on_file`, `approver_id`, `approved_at`, `observed_at`. Khoản tròn số hoặc từ khóa “thuê văn phòng” không tự cấp ngoại lệ.

## B3: rà hồ sơ và bằng chứng giao nhận

`b3_review.csv` trích đúng các hồ sơ trước đây bị B3 bắt và mang nhãn new_legitimate_vendor, gồm số chứng từ, cờ giao nhận và nguồn loại chứng từ thực có. Nhãn này không được đưa vào detector hoặc dùng để tự tạo xác nhận giao hàng.

Không dùng số lượng chứng từ để coi giao nhận đã hợp lệ. Nguồn `transaction_documents` cần invoice, PO/contract và goods_receipt/service_acceptance cho đúng giao dịch/NCC, có người xác minh đã biết và mốc xác minh/quan sát phù hợp. Khi đủ bộ, lưu ngoại lệ xác minh. Thiếu bộ chứng từ được ghi `needs_typed_fulfilment_evidence`; tuổi NCC và khoản lớn là ngữ cảnh, vẫn có thể hỗ trợ một quan hệ nhân viên/đổi TK/trạng thái thuế độc lập.

Schema `transaction_documents.csv`: `record_id`, `company_id`, `vendor_id`, `transaction_id`, `document_type`, `status=verified`, `evidence_id`, `verifier_id`, `verified_at`, `observed_at`. Cập nhật/hủy giữ ID ổn định, có `observed_at` mới. Trạng thái xác minh đến từ nguồn chứng từ tin cậy; engine chưa tự OCR hay kiểm tra nội dung hồ sơ với bên thứ ba.

## Kiểm chứng, version và phần còn lại

Đã qua 83 kiểm thử toàn dự án, gồm 17 kiểm thử mới cho master/alias, ca hợp lệ, hai mốc thời gian, hủy lịch giữa hai mốc, nguồn tương lai, đơn mua độc lập, cùng yêu cầu chi, chứng từ loại đúng, baseline tách NCC và bảo toàn hard trigger. JavaScript UI được kiểm tra cú pháp; kiểm tra backend hàng đợi không thay thế kiểm tra trực quan trong browser.

Nguồn mới là tùy chọn và chưa có trong dataset gốc. File CSV thêm vào dataset có manifest phải có checksum trong `manifest.files`; loader không nhận nguồn bị đổi hoặc thiếu checksum. Không tạo thêm nguồn dựa trên truth, không sửa cache/model cũ.

`noise_policy=phase2` là hành vi mới mặc định; `noise_policy=legacy` giữ chính sách điểm sau đợt 1 để đối chiếu. CLI đợt 1 được ghim `legacy`; helper fixture audit cũ cũng giữ policy đó để bảo toàn các kỳ vọng lịch sử. Snapshot cũ không được ghi đè.

Hàng đợi mới vẫn có thể mất một số TP trước đây chỉ đủ điểm nhờ tên giả lập hoặc tổ hợp ngữ cảnh. `lost_true_detections.csv` liệt kê cả validation/test để xem kịch bản và bằng chứng cần bổ sung. Không gọi sự mất này là hết gian lận; không dùng kết quả trên một seed tổng hợp để nghiệm thu. Cần nguồn PO/lịch ca/giao nhận và master có tên đại diện hơn, test mới giữ kín và xác nhận rà soát để tiến tới luật cứng đáng tin cậy.

```powershell
python -m unittest discover -s tests -v
python -m sme_fraud.run_noise_reduction --output reports/rule_repairs/phase2_new
python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase2 --database .runtime/review/phase2.sqlite3 --port 8767
```

Mở UI mới tại `http://127.0.0.1:8767` sau khi chạy lệnh. Hàng đợi/cổng cũ và phản hồi người dùng được giữ tại snapshot cũ.
