# CR-023 — API phân tích snapshot P1/E3

Đã nối và chạy HTTP analyze tại **http://127.0.0.1:8766**. Subtask kỹ thuật READY_FOR_REVIEW; R2 tổng thể **PARTIAL**, chưa nghiệm thu production hoặc pipeline đầy đủ.

## Kết quả đã kiểm

- **686 kiểm thử hồi quy pass**, 0 failure/error/skip, 352.792 giây: [JSON](native_tests.json), [log](native_tests.log). Gồm **29 ca API mới**; [API riêng](api_tests.json) cũng pass. [109 focused](focused_tests.json) là lượt trước khi bổ sung hai ca âm/quyền đa DN, đều được chạy lại trong full 686.
- [Demo HTTP trọn luồng](http_demo/summary.json): 7 thao tác upload → preview → commit → review → technical → repeat → chặn accountant technical. Hai dòng/view, P1 hit 20, E3 matched=true với score=0; một snapshot sau retry, cùng analysis ID giữa hai view. [Nguồn mô phỏng](http_demo/source.json), [review](http_demo/review.json), [technical](http_demo/technical.json).
- [Live 8766](live_summary.json): dùng lại snapshot cũ, **3/3 dòng, một nhóm duy nhất**; request lặp byte/nội dung giống nhau, accountant technical HTTP 403; DB vẫn một snapshot. [Kết quả nghiệp vụ](live_review.json). Dịch vụ cũ không còn listener khi nạp lần đầu; đã khởi động lại trên cổng trống với DB/policy cũ, không ghi đè dữ liệu hoặc dừng process khác.
- Kiểm schema trên hai view/demo/live đều qua. [Bảo toàn](preservation.json): các kernel, 33 feature, model code/runtime, input schemas và MethodScore/RuleResult không đổi. Không fit hoặc đọc model artifacts trong route này.

## Hợp đồng và quyền

`POST /api/v1/companies/{company_id}/snapshots/{snapshot_id}/analyze`, JSON có as_of timezone bắt buộc, view review mặc định hoặc technical. [Hướng dẫn](../../../../agent2/docs/SNAPSHOT_ANALYSIS_API.md), [schema](../../../../agent2/sme_fraud/snapshot_analysis.schema.json).

Host/Origin/Bearer/membership/data.import được kiểm trước body và đọc snapshot; scope tenant/DN/checksum của nguồn được giữ. View technical cần **director của đúng DN** theo policy server, gồm kiểm lại sau serialize. Một actor có thể là accountant ở C001 nhưng director ở C002; không đổi quyền C001 hoặc đọc snapshot C001 bằng URL C002, dù trùng transaction IDs. Token/role không lấy từ body. Không cần quyền evidence.verify mới khi đọc snapshot đã có chứng từ verified.

Review chỉ allowlist nghiệp vụ, không có điểm/mã luật/threshold/algorithm/config. E3 điểm đóng góp 0 vẫn hiện cần đối chiếu khi matched; P1 group hit không mất vì row score=0. Technical chỉ P1/E3, nhóm ở root và dùng refs trên rows; không trả toàn bộ graph/features/ML hoặc các luật chưa được nối. Missing/null/not_applicable giữ riêng, tiền nguyên có dấu không đổi sang float, giao dịch âm không bị lọc.

analysis_id ràng buộc source/checksum/as_of/code; global as_of không nâng cutoff quá khứ. API chỉ đọc, không lưu job/run, không cần key để tránh ghi trùng. Chưa có GET analysis ID. Tổng luật vẫn incomplete/null, analysis_complete=false là chưa đầy đủ luật, không phải HTTP thực thi lỗi.

## Giới hạn và diagnostic

Giới hạn demo đồng bộ 200 transaction records, 1.000 source records, 5 MiB output; vượt trả 413, không tự cắt dữ liệu/lịch sử. Chưa async worker/HTTP ML/Portal identity/UI/active queue. Giới hạn kỹ thuật không phê duyệt D-03/04/09 hoặc accuracy. Dữ liệu kiểm là mô phỏng.

[Diagnostic fixture đa DN](multi_company_fixture_diagnostic.json) giữ lỗi record_id danh mục DN không khớp C002; đã sửa dữ liệu test, không nới validator/API. Test mới xác minh cả role downgrade khi permissions không đổi, revoke trong lúc tính, chặn trước body, source tamper/binding mismatch, không lộ lỗi nội bộ hoặc partial rows, không fit và không ghi DB. [Provenance](provenance.json).
