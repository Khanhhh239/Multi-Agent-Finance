# Multi-Agent Finance — Agent 2

Agent 2 giám sát rủi ro tài chính SME: bộ luật có bằng chứng, phân tích quan hệ, benchmark Isolation Forest và giao diện rà soát cục bộ. Xem [kiến trúc chung](docs/DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md) và [cách cài, kiểm thử, chạy từ bản clone mới](docs/AGENT2_GITHUB.md).

Bản GitHub gồm mã nguồn, test, schema, CSV mẫu chỉ có header và tài liệu/báo cáo đối chiếu. Dataset, model đã train, hàng đợi chi tiết, phản hồi người dùng và môi trường Python được tạo trên máy khi chạy. Các kết quả trong `reports/` là snapshot lịch sử; hãy dùng thư mục đầu ra mới theo hướng dẫn để chạy lại.

## Dữ liệu tổng hợp gian lận tài chính SME Việt Nam

Bộ sinh dữ liệu và benchmark Isolation Forest cho 5 doanh nghiệp SME giả lập. Mọi tên, MST, tài khoản, SĐT và địa chỉ là token tổng hợp, không phải dữ liệu của người hoặc doanh nghiệp thật. Các tỷ lệ 0,1%, 0,3%, 0,5% là kịch bản thử theo yêu cầu, **không phải số liệu đo tỷ lệ gian lận tại Việt Nam**.

Phiên bản dữ liệu hiện tại là **v2**, đã sửa biểu diễn kế toán theo TT133/TT200 cho kỳ 2024–2025. Xem [đối chiếu định khoản](reports/accounting_review.md). Bản v1 được giữ trong `outputs/sme_fraud_v1.zip`; `outputs/sme_fraud_v2.zip` là snapshot dữ liệu kế toán v2 và pipeline IF trước khi bổ sung bộ luật.

Đã bổ sung pipeline bộ luật từ [rule_class_1.md](rule_class_1.md): 6 nhóm A–F, 31 quy tắc chi tiết và P1/T1/T2 cho thanh toán trùng/tạm ứng. Xem [phạm vi triển khai và cách chạy](reports/rules_implementation.md), [benchmark Rules/Graph/IF](reports/rules/summary_vi.md). Các rule thiếu dữ liệu được ghi rõ; cảnh báo có bằng chứng, hàng đợi hồ sơ và CLI lưu phản hồi người rà soát. Gói `outputs/sme_fraud_v2_rules.zip` chứa dữ liệu v2, mã và báo cáo mới; ZIP v2 trước đó được giữ nguyên.

Đã có **giao diện rà soát MVP chạy cục bộ**: bộ lọc hồ sơ, bằng chứng/định khoản, sơ đồ quan hệ, ngân sách 5–10 hồ sơ/công ty/ngày và lưu kết luận có lịch sử. Chạy `python start_review.py`, rồi mở `http://127.0.0.1:8765`. Xem [hướng dẫn UI và phạm vi kiểm chứng](reports/review_ui.md). Gói `outputs/sme_fraud_v2_review.zip` gồm dữ liệu, nguồn UI và báo cáo; không chứa cache hay phản hồi của người dùng. Đây là MVP chưa có đăng nhập/phân quyền, chưa kiểm tra trực quan trong browser và chưa thử dữ liệu SME thật.

Ưu tiên hiện tại là **audit và hoàn thiện luật trước khi phát triển ML tiếp**. [Rule Audit 31 rule](reports/rule_audit/summary_vi.md) có bảng từng rule, 31 báo cáo chi tiết, TP/FP/precision/FPR theo ba tỷ lệ và ba kỳ, hard negatives, chồng lặp và tác động bỏ từng rule khỏi hàng đợi. [Phương pháp và cách chạy audit](reports/rule_audit_method.md) giải thích phạm vi đo được và 51 tình huống đối chứng. Đợt audit giữ nguyên dataset, detector và ngưỡng; chưa phải bản sửa luật.

**Đợt sửa 1 đã hoàn thành B7/E1/A2**: [logic và schema nguồn HR/hợp đồng](reports/rule_repairs_phase1.md), [kết quả chấm lại ba bộ dữ liệu](reports/rule_repairs/phase1/summary_vi.md). Chạy độc lập `python -m sme_fraud.run_rule_repairs --output reports/rule_repairs/phase1_new`; pipeline này chỉ chấm rules, không dùng ML. Snapshot audit/benchmark cũ được giữ để đối chiếu; hàng đợi mới nằm trong `reports/rule_repairs/phase1` và có lệnh mở UI riêng trong báo cáo.

**Đợt 2 đã triển khai nguồn nhiễu/cộng điểm**: [cơ chế điểm, nguồn ca/PO/chứng từ và kiểm thử](reports/rule_repairs_phase2.md), [so sánh validation/test](reports/rule_repairs/phase2/summary_vi.md). E3/B5/E4 là kiểm tra master riêng, B5/E4 chung bằng chứng; C1/A5/B3 là ngữ cảnh có điều kiện. A1 hỗ trợ trả góp xen kẽ và nguồn đơn mua đã xác minh; A5 thử baseline log/MAD trên validation. Chạy `python -m sme_fraud.run_noise_reduction --output reports/rule_repairs/phase2_new`; không train hoặc chấm ML. Snapshot mới có lệnh UI riêng trong báo cáo và có file liệt kê TP bị mất để đánh giá đánh đổi.

**Đợt 3 đã thống nhất mô tả và phạm vi rule**: [quyết định, nguồn F1/ngân hàng/căn cước và đối chứng](reports/rule_repairs_phase3.md), [kết quả so với đợt 2](reports/rule_repairs/phase3/summary_vi.md). A3 có nhánh 2 khoản/3 ngày/85%; A4 dùng tháng lịch; A5 chỉ đuôi cao; B1 tách master khỏi chi NCC; B3 xét lần phát sinh kinh tế đầu tiên; F1 chỉ góp điểm khi đủ nguồn xác nhận. `rule_class_1.md` cũng ghi rõ C1 vận hành thứ Bảy và C2 tự duyệt trong quyền. Chạy `python -m sme_fraud.run_spec_alignment --output reports/rule_repairs/phase3_new`; engine mặc định phase3, runner lịch sử ghim legacy. Chưa tự bổ sung nguồn còn thiếu hoặc triển khai ML tiếp.

**Đợt 4 đã bổ sung nguồn và đánh giá độc lập**: [schema nguồn, logic C4/E2/F2/F3/F4 và phạm vi kết luận](reports/rule_repairs_phase4.md), [đối chứng/Benford/seed SME mới](reports/rule_repairs/phase4/summary_vi.md). 301 case theo 7 seed, 56 thử nghiệm cửa sổ/336 phép đối chiếu nhóm D, 350.000 dòng SME mới ở 0,1%–0,5%. Mặc định `evidence_policy=phase4`; nguồn thiếu vẫn not_evaluable/information_gap. Source/window labels tách khỏi fraud labels; chưa nghiệm thu SME thật hoặc chuyển sang ML. Có [CSV header mẫu](examples/phase4_sources) và `python -m sme_fraud.source_snapshot` để kiểm tra F3/F4 theo cutoff mà không tạo giao dịch giả.

**Đợt 5 đã ràng buộc bằng chứng nghĩa vụ chi cho A1/A2/A4**: [chính sách, schema, đối chứng và giới hạn](reports/rule_payment_evidence.md). Ngoại lệ phải gắn đúng yêu cầu chi, PO, hóa đơn, hợp đồng hoặc lịch định kỳ đã duyệt và không vượt tổng tiền được phép. Theo quyết định nghiệp vụ, thiếu hồ sơ vẫn giữ cảnh báo hiện tại; snapshot validation chưa có các nguồn mới nên hàng đợi không đổi. Có [CSV header mẫu](examples/payment_evidence_sources) để tích hợp dữ liệu ERP/AP thật.

**Đợt 6 đã hoàn thiện nguồn thẩm quyền C2/C3 và ngoại lệ B6**: [chính sách, schema, đối chứng và giới hạn](reports/rule_authority_dormancy.md). C2 đọc quyền tự duyệt/ủy quyền theo phạm vi, C3 đọc cấp thẩm quyền thật khi có coverage đầy đủ, B6 đối chiếu lịch năm/mùa và tổng tiền trong kỳ. Thiếu nguồn vẫn dùng hành vi hiện tại. Có [CSV header mẫu thẩm quyền](examples/authority_sources) và lịch thanh toán trong [nguồn nghĩa vụ chi](examples/payment_evidence_sources).

## Bộ dữ liệu đã sinh

| Thư mục | Tổng quan sát | Gian lận | Tỷ lệ | Hard negatives hợp lệ |
| --- | ---: | ---: | ---: | ---: |
| `data/sme_fraud_001` | 100.000 | 100 | 0,1% | 5.000 |
| `data/sme_fraud_003` | 100.000 | 300 | 0,3% | 5.000 |
| `data/sme_fraud_005` | 100.000 | 500 | 0,5% | 5.000 |

Một quan sát là một giao dịch đã duyệt/ghi sổ hoặc một lần rà soát tạm ứng. `advance_review` là sự kiện phi tài chính, mang số dư cần kiểm tra trong `amount_vnd`, có `is_financial_entry=0` và **không có dòng sổ cái**. Tỷ lệ gian lận tính trên toàn bộ quan sát. Lọc `is_financial_entry=1` trước khi cộng dòng tiền hoặc chỉ đánh giá bút toán; khi đó phải tính lại tỷ lệ gian lận của tập đã lọc.

V2 bổ sung chứng từ kế toán hỗ trợ trong `journal_documents.csv` và `journal_lines.csv`: ghi nhận hóa đơn trước khi trả tiền, ghi nhận chi phí lương trước khi trả lương, tập hợp chi phí vào 154, chuyển khoản phải thu và dự phòng trước xóa nợ. Chứng từ hỗ trợ không thêm dòng train hoặc nhãn; file `labels.csv` và `splits.csv` được giữ nguyên byte so với v1. Không dùng tổng số dòng sổ cái làm mẫu số prevalence.

Mỗi bộ có 50.000 train, 25.000 validation, 25.000 test. Ngưỡng nghiệp vụ, ngành, mức tiền, lịch làm việc và lịch lễ là giả định mô phỏng có thể chỉnh trong mã nguồn. Đây là dữ liệu để phát triển và kiểm tra pipeline, cần hiệu chỉnh phân phối theo dữ liệu SME thật trước khi suy ra hiệu quả triển khai.

## Sáu nhóm gian lận

| `fraud_type` | Biến thể và bằng chứng mô phỏng |
| --- | --- |
| `ghost_vendor` | NCC trùng TK/SĐT/địa chỉ với nhân viên; pháp nhân mới thành lập có quan hệ NCC → người đại diện → SĐT → nhân viên; nhân viên ma nhận lương vào tài khoản dùng chung với nhân viên khác và không có chấm công. |
| `split_payments` | Khoản cận 90–99,5% hạn mức; khoản phân tán 42–88% hạn mức qua nhiều ngày; nhiều NCC có TK khác nhau nhưng chung SĐT. Hạn mức theo người lập có nhiều mức 5, 20, 50 triệu đồng. |
| `duplicate_payment` | Trả đầy đủ một hóa đơn rồi trả lại cùng NCC, số hóa đơn và số tiền; đôi khi tạo mã hóa đơn ERP khác để che việc trùng. Lần trả gốc là ngữ cảnh hợp lệ. |
| `period_end_adjustment` | Điều chỉnh cuối tháng, lập/duyệt cùng người, vào cuối tuần và giờ muộn; có cả ghi tăng doanh thu hoặc chuyển chi phí. |
| `risky_invoice` | Hóa đơn phát hành sau ngày NCC ngừng hoạt động/bỏ trốn theo lịch sử trạng thái tổng hợp; có tình huống thông tin chỉ được công bố sau giao dịch. |
| `long_outstanding_advance` | Rà soát khoản chưa hoàn ứng sau hạn 60–150 ngày hoặc xóa sổ số dư thiếu chứng từ; có giải ngân trước đó và lịch sử số dư, gia hạn, thanh toán. |

Để giữ sáu nhóm chính, nhân viên ma là biến thể `ghost_employee_payroll` của nhóm đối tượng ma `ghost_vendor`. Trên dữ liệu nghiệp vụ, lương luôn dùng `employee_id`, tài khoản 334/112, **không dùng `vendor_id`**.

Không phải mọi dòng gian lận đều khác biệt rõ ngay lúc xuất hiện. Khoản đầu của một chuỗi chia nhỏ có thể chưa bất thường; trạng thái NCC công bố sau đó chưa được biết lúc thanh toán; thông đồng vẫn có thể đủ giấy tờ. Nhãn thể hiện ý đồ/kết quả được cài trong mô phỏng, còn đặc trưng chỉ phản ánh bằng chứng có thể quan sát. Không gán nhãn gian lận tự động chỉ vì một dấu hiệu rủi ro xuất hiện.

## Dữ liệu hợp lệ và hard negatives

Nền có thanh toán NCC, mua hàng, nguyên vật liệu, bán hàng, thu tiền khách hàng, tiền mặt, lương, giá vốn, thuê nhà, khấu hao, thiết bị/công cụ, thuế, chi phí bán hàng và chu trình tạm ứng. Có các tài khoản 111, 112, 131, 1331, 1332, 1388, 141, 152, 153, 154, 155, 156, 211, 214, 2293, 331, 334, 335, 3331, 511, 632 và chi phí theo chế độ kế toán.

`C001/C005` dùng TT200, `C002/C003/C004` dùng TT133. Sổ cái TT133 dùng 6421 cho bán hàng, 6422 cho quản lý; TT200 dùng 641/642 và có bước 621/622 → 154 khi phù hợp. Features gộp 641/642/6421/6422 thành nhóm chi phí 642 và có biến `framework_tt133`; không còn `debit_641`/`credit_641` độc lập. Cặp `pair_*` là multi-hot theo mọi cặp xuất hiện trong bút toán, gồm dòng VAT; tần suất lịch sử của cặp chính chỉ tính từ quá khứ.

`recipient_account` chỉ phản ánh bên nhận khi có dòng tiền. Với ghi nhận công nợ, xuất vật tư, khấu hao, xóa nợ…, trường này để trống và `payment_channel=journal`. `counterparty_account` lưu thông tin đối tác riêng. Thu tiền khách hàng vào tài khoản của công ty.

Số tiền dùng phân phối lognormal theo ngành, có chi định kỳ tròn và một số giao dịch lớn hợp lệ. Giờ muộn và cuối tuần có xác suất khác ngày thường, thứ 7 khác chủ nhật. Độ trễ duyệt là hỗn hợp lognormal và đuôi dài nhiều ngày. Các tỷ lệ này là cấu hình sinh, không phải ước lượng thực địa.

5% số quan sát được cài làm hard negatives riêng và mang nhãn 0, gồm:

- Đổi TK NCC có callback, người duyệt và thời điểm xác minh trước thanh toán.
- Tự duyệt trong hạn mức cho phép; điều chỉnh cuối kỳ vào cuối tuần, tự duyệt hợp lệ và đủ chứng từ.
- Vận hành cuối tuần, chi thuê nhà tròn, duyệt trễ nhiều ngày.
- Hai đợt thanh toán cùng số tiền và cùng hóa đơn nhưng tổng chỉ bằng giá trị hóa đơn.
- NCC mới nhưng có giao nhận; bên liên quan đã công bố; thanh toán hóa đơn hợp lệ trước khi NCC ngừng hoạt động.
- Lương nhân viên từ xa không có lượt chấm công nhưng có bằng chứng làm việc thay thế.
- Tạm ứng được gia hạn trước hạn, xóa sổ có phê duyệt và hồ sơ hỗ trợ.

Một số trường hợp hợp lệ vẫn có thể bị IF xếp là bất thường. Báo cáo đo riêng FPR trên từng loại hard negative để nhìn thấy việc này.

## Các file trong mỗi bộ

| File | Cách dùng |
| --- | --- |
| `transactions.csv` | Dữ liệu nghiệp vụ không chứa nhãn, vụ việc hay tên kịch bản. ID giao dịch được tráo ngẫu nhiên độc lập với gian lận. |
| `features.csv` | Ma trận số dành cho IF; chỉ `transaction_id` là khóa. **Bỏ khóa này khỏi X**. Danh sách đặc trưng cho phép nằm trong `manifest.json`. |
| `labels.csv` | `is_fraud`, loại, biến thể, `case_id`, vai trò dòng trong vụ việc, loại hard negative, khả năng quan sát. Chỉ dùng đánh giá/đối chiếu. |
| `splits.csv` | Ánh xạ ID sang train/validation/test theo thời gian. |
| `companies.csv`, `vendors.csv`, `customers.csv`, `employees.csv` | Danh mục doanh nghiệp, NCC, khách hàng, nhân viên giả lập. Đọc `recorded_at` để truy vấn theo thời điểm. |
| `invoices.csv` | Hóa đơn gồm giá chưa thuế, VAT, tổng tiền; có hóa đơn mua và bán. Thuế suất 10% là giả định minh họa cho nhóm hàng/dịch vụ được mô phỏng, không xác định quyền khấu trừ theo pháp luật thuế. |
| `journal_documents.csv`, `journal_lines.csv` | Chứng từ và bút toán nhiều dòng, Nợ=Có. `transaction_id` chỉ có ở chứng từ chính được chấm điểm; chứng từ hỗ trợ có `is_scored_observation=0` và ID chứng từ riêng. |
| `document_links.csv`, `account_flow_edges.csv` | Liên kết chứng từ và cạnh Có → Nợ theo luồng ghi nhận kế toán, có thời điểm quan sát và định danh nhân viên/NCC/hóa đơn. Đây là luồng sổ cái, không đồng nghĩa chuyển tiền ngân hàng. |
| `vendor_status_history.csv`, `bank_account_changes.csv` | Lịch sử có cả thời điểm hiệu lực, quan sát và xác minh. Không lấy trạng thái cuối kỳ để điền ngược quá khứ. |
| `entity_links.csv`, `attendance.csv` | Cạnh đồ thị đã biết và chấm công lũy kế đã quan sát đến ngày 25 của tháng. |
| `advances.csv`, `advance_events.csv` | Giải ngân, hạn gốc, gia hạn, thanh toán và xóa sổ. Không đưa trạng thái quyết toán tương lai vào X. |
| `calendar.csv` | Các ngày lễ minh họa, có nguồn `illustrative_simulation_calendar`; không phải lịch nghỉ lễ đầy đủ theo luật. |
| `manifest.json`, `data_dictionary.json`, `validation.json` | Cấu hình, số lượng/tỷ lệ theo split, checksum, danh sách/định nghĩa đặc trưng và kết quả kiểm tra. |
| `accounting_validation.json`, `accounting_change_log.json` | Đối chiếu chế độ kế toán, VAT, liên kết chứng từ và thống kê thay đổi so với v1. |

CSV có UTF-8 BOM để mở tiếng Việt trong Excel; số VND lưu dạng số nguyên, không kèm dấu phân cách hoặc đơn vị. Đọc các mã/tài khoản bằng `dtype=str` khi cần giữ chúng là định danh.

## Chia tập và chống rò rỉ

- Train: 01/01/2024–31/12/2024; validation: 01/01/2025–30/06/2025; test: 01/07/2025–31/12/2025, múi giờ UTC+7.
- Cả dòng gian lận lẫn dòng hỗ trợ của một `case_id` nằm trong một split. Mỗi SME có thể xuất hiện qua cả ba kỳ; đây là bài toán theo dõi SME đã biết, không phải thử trên công ty hoàn toàn mới.
- Thời điểm chấm điểm là `posted_at`, sau khi đã lập và duyệt. Mô hình hiện tại không dùng để chặn giao dịch trước phê duyệt; muốn chấm trước duyệt phải bỏ các đặc trưng chưa có.
- Cửa sổ 3/7/30 ngày và baseline tiền chỉ dùng giao dịch có `posted_at` trước dòng hiện tại. Các dòng cùng thời điểm không thấy nhau khi tạo đặc trưng.
- Đồ thị, nhân sự, chấm công, lịch sử NCC, đổi TK và gia hạn chỉ dùng bản ghi đã quan sát. Tình trạng hóa đơn được đối chiếu cả ngày phát hành lẫn ngày trả tiền.
- IF fit trên toàn bộ train có lẫn tỷ lệ gian lận thấp, không dùng `y`, không bỏ gian lận dựa trên nhãn và không cân bằng/SMOTE test.
- Ngưỡng lấy từ phân vị điểm validation chưa gán nhãn theo ngân sách cảnh báo 0,1/0,3/0,5%. Không chọn ngưỡng bằng nhãn hoặc phân vị test. Ngân sách cảnh báo không phải tỷ lệ gian lận.
- Điểm là `-model.score_samples(X)`: cao hơn nghĩa là bất thường hơn. `contamination="auto"` chỉ phục vụ cơ chế ngưỡng mặc định của sklearn; benchmark dùng ngưỡng validation riêng.

## Chạy lại

Python 3.10+; bộ sinh và kiểm tra cấu trúc chỉ cần thư viện chuẩn. Phần train cần các gói trong `requirements.txt`.
`requirements-lock.txt` ghi phiên bản đã dùng cho benchmark này để tái lập kết quả trong môi trường tương thích.

```powershell
python -m pip install -r requirements.txt
python -m sme_fraud.generate --output data/my_sme_003 --rows 100000 --fraud-rate 0.003 --seed 42 --companies 5
python -m sme_fraud.validate --data data/my_sme_003
python -m sme_fraud.evaluate --data data/my_sme_003 --output reports/my_sme_003 --alert-budget 0.003
python -m unittest discover -s tests -v
```

Nghiệm thu các rule cần nguồn HR/ERP/công nợ thật dùng quy trình hai bước dưới đây. Bước `prepare` tạo phiếu chấm mù và khóa hash dự đoán; bước `evaluate` chỉ chấp nhận khi coverage, review độc lập và ngưỡng phê duyệt đều hợp lệ.

```powershell
python -m sme_fraud.real_source_acceptance prepare --data data/sme_real_export --from 2025-01-01T00:00:00+07:00 --as-of 2025-12-31T23:59:59+07:00 --criteria reviews/acceptance_criteria.json --output reports/real_acceptance/prepared
python -m sme_fraud.real_source_acceptance evaluate --data data/sme_real_export --prepared reports/real_acceptance/prepared --reviews reviews/review_conclusions.csv --coverage reviews/coverage_attestations.csv --criteria reviews/acceptance_criteria.json --output reports/real_acceptance/result
```

Xem [phương pháp nghiệm thu nguồn thật](reports/rule_source_acceptance.md). Các dataset generator trong repository không thể nhận trạng thái `accepted` từ quy trình này.

`--fraud-rate 0.001` là 0,1%, `0.005` là 0,5%. Với tỷ lệ thấp, dùng số quan sát đủ để có tối thiểu 48 dòng gian lận cho các biến thể. Generator không ghi đè thư mục dữ liệu/báo cáo đã có nội dung; dùng tên mới cho một seed hoặc cấu hình mới.

Trong máy hiện tại, Python nằm trong runtime Codex và sklearn đã được cài riêng vào `.runtime/site-packages`. Có thể dùng `./run_benchmark.ps1 -OutputRoot data/new_run -ReportRoot reports/new_run` để tự tìm Python và sinh/kiểm tra/train cả ba tỷ lệ. Script này không tự tải hay cài thêm thư viện.

Ví dụ lấy đúng X:

```python
import json
import pandas as pd
from sklearn.ensemble import IsolationForest

folder = "data/sme_fraud_003"
meta = json.load(open(f"{folder}/manifest.json", encoding="utf-8"))
features = pd.read_csv(f"{folder}/features.csv")
split = pd.read_csv(f"{folder}/splits.csv").set_index("transaction_id")["split"]
mask = features["transaction_id"].map(split).eq("train")
X_train = features.loc[mask, meta["feature_columns"]]
model = IsolationForest(n_estimators=300, max_samples=2048,
                        contamination="auto", random_state=42, n_jobs=-1)
model.fit(X_train)  # Không join labels.csv vào X.
```

## Đánh giá và giới hạn

Mỗi thư mục `reports/sme_fraud_00x` có `report_vi.md`, `metrics.json`, điểm từng dòng test, đường precision–recall rút gọn và model đã fit. Mô hình lưu kèm thứ tự đặc trưng và ngưỡng để tái sử dụng.

Kết quả v2 nằm trong `reports/summary_vi.md`, đã fit lại với ma trận đặc trưng mới và báo cáo riêng FPR theo TT133/TT200. Model v1 không tương thích với thứ tự/số cột của v2. Việc sửa định khoản không đảm bảo IF đạt chất lượng vận hành; cần đánh giá trên dữ liệu thật và kiểm tra từng hard negative.

Metric chính là Average Precision (AP), precision/recall ở ngưỡng validation, precision@25/50/100/250, recall theo sáu nhóm/biến thể/vụ việc và FPR trên hard negatives. AP từ `average_precision_score` không đồng nhất với diện tích PR tích phân hình thang. ROC-AUC chỉ là số tham khảo.

Ở 0,1%, test chỉ có 25 dòng gian lận, mỗi nhóm khoảng 4–5 dòng. Một seed không đủ để kết luận chắc về từng nhóm. Báo cáo có khoảng Wilson mô tả theo dòng; các dòng cùng vụ có tương quan, nên khoảng này không thay thế khoảng tin cậy bootstrap theo vụ. Muốn ước lượng ổn hơn, tăng quy mô và chạy nhiều seed, đánh giá cả công ty chưa thấy.

Các mẫu kế toán có VAT nhiều dòng và liên kết sản xuất/công nợ nhưng chưa đối chiếu số dư đầu-cuối kỳ hoặc lập bộ BCTC đầy đủ. Mẫu thiết bị giả định mỗi hóa đơn là một vật thể độc lập: dưới 30 triệu giá chưa thuế đi vào 153, thiết bị đủ tiêu chí giả định đi vào 211. Chưa mô phỏng PIT/BHXH, khấu hao theo từng tài sản hoặc xác định đủ điều kiện hoàn/khấu trừ VAT. Trạng thái NCC là tổng hợp, không truy vấn cơ quan thuế. Cặp đúng và chứng từ cân bằng vẫn có thể là giao dịch khống.

`pair_supported_for_scenario` kiểm tra mẫu nghiệp vụ được hỗ trợ, không phải danh sách đầy đủ mọi cặp được phép bởi pháp luật. Không tự kết luận một cặp hiếm hoặc ngoài mẫu là gian lận. TT99 áp dụng cho năm tài chính bắt đầu từ 01/01/2026; v2 giữ phạm vi lịch sử 2024–2025, chưa triển khai TT99.

Nguồn phương pháp: [IsolationForest và hướng điểm/ngưỡng](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html), [tránh data leakage](https://scikit-learn.org/stable/common_pitfalls.html), [đánh giá theo thời gian](https://scikit-learn.org/stable/modules/cross_validation.html), [Average Precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html). Phân phối, hạn mức và nhãn nghiệp vụ trong bộ này là giả định sinh dữ liệu, không được dẫn từ các tài liệu sklearn.
