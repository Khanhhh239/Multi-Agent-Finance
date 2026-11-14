# API phân tích snapshot — bốn nhánh

**CR-027:** contract hiện hành [snapshot-analysis/1.1.0](../sme_fraud/snapshot_analysis.schema.json), có bốn nhánh và model pin theo DN. Xem [hợp đồng và cách chỉ định artifact](FOUR_BRANCH_ANALYSIS.md). Các mô tả P1/E3 phía dưới giữ hành vi checks/groups; không đại diện toàn bộ năng lực HTTP hiện tại.

Đã có HTTP phân tích snapshot đã lưu. Chỉ nhận snapshot ID từ server và mốc `as_of`; giữ đủ giao dịch khả dụng, không tự fit hoặc chọn model. Đây là phân tích đồng bộ chỉ đọc, chưa tạo job/run được lưu hoặc đưa cảnh báo vào hàng đợi.

```http
POST /api/v1/companies/C001/snapshots/snp_<32-hex>/analyze
Authorization: Bearer <credential của backend>
Content-Type: application/json

{"as_of":"2026-10-10T11:00:00+07:00"}
```

Thay snapshot ID bằng giá trị thật từ bước commit. Không gửi các ký tự `<...>`. Endpoint cùng dịch vụ `http://127.0.0.1:8766`, cấu hình `--auth-file` và `--snapshot-db` theo [hướng dẫn snapshot](IMMUTABLE_SNAPSHOTS.md).

P1 cần [kênh/liên kết/phạm vi lịch sử theo input 1.1.0](P1_INPUTS.md). Snapshot 1.0.0 vẫn đọc được; nếu thiếu nguồn P1 thì trả unavailable, không tự nâng dữ liệu hoặc điền 0. E3 vẫn được đánh giá độc lập khi có đủ nguồn tên nhà cung cấp.

## Quyền và hai dạng kết quả

- Cần membership active và `data.import` đúng tenant/doanh nghiệp, như quyền đọc snapshot hiện có. Director không tự được đọc DN khác. Backend kiểm trước body và kiểm lại trước trả kết quả.
- Mặc định `view="review"`: DTO nghiệp vụ cho kế toán, chỉ thông tin cần đối chiếu, tiền và căn cứ; không trả score/mã luật/algorithm/threshold/model/config. Các khóa `payment_invoice` và `vendor_names` tương ứng hai đối chiếu được hỗ trợ.
- `view="technical"`: **director đúng DN + data.import**, xác minh bằng policy backend. Trả `rows[].rules.P1/E3` với status, matched, điểm/null, reasons/gaps/evidence; không phải chỉ ẩn bằng CSS. Role bị hạ trong lúc tính cũng bị chặn trước trả. Không cần model.fit hoặc quyền xác minh mới để đọc snapshot đã có chứng từ verified.

```json
{"as_of":"2026-10-10T11:00:00+07:00","view":"technical"}
```

Không nhận role, tenant_id, company_id, điểm, nguồn mới hoặc model/artifact từ body. Phiên Portal đã nối theo CR-025; qua /agent2/ dùng session Portal, backend vẫn kiểm quyền từng request. Host/Origin vẫn chỉ loopback/same-origin; không mở CORS rộng.

## Cách đọc kết quả

Contract [snapshot-analysis/1.1.0](../sme_fraud/snapshot_analysis.schema.json) có:

- `analysis_id`: binding snapshot/checksum + as_of chuẩn hóa + phiên bản mã. Cùng nguồn/mốc/mã có cùng ID, kể cả hai view. Đây chưa phải ID một job được lưu để GET lại.
- `snapshot`: mã DN, snapshot ID, phiên bản hợp đồng và checksums. Kết quả luôn gắn với nguồn đã commit, không nhận file chưa lưu.
- `as_of`: mốc toàn yêu cầu; `rows[].knowledge_at` là cutoff riêng của từng dòng theo R1. Chứng từ đến muộn không sửa quá khứ. Không có dòng đủ điều kiện thì `row_count=0`, không tự kết luận không vi phạm.
- `rows`: đủ giao dịch khả dụng, giữ revision và số tiền VND nguyên có dấu; không bỏ dòng không trúng luật hoặc điều chỉnh âm. JSON money là integer theo hợp đồng chung, không đổi sang float.
- `groups`: mỗi nhóm đồng thời chỉ một lần; rows dùng group refs. Đây là kết quả kiểm nhóm, chưa phải case/alert hoặc ngân sách rà soát.
- `summary.analysis_complete=false`: **chưa đánh giá toàn bộ bộ luật**, không phải HTTP chạy lỗi. Technical aggregate vẫn rules_incomplete/null, không cộng hai điểm thành tổng rủi ro.

View review có `needs_review`, `no_signal`, `unavailable`, `not_applicable`. `needs_review` nullable; thiếu nguồn không biến thành false/0. Nếu P1 chỉ có group hit thì row nghiệp vụ vẫn chỉ rõ cần rà và tham chiếu nhóm. E3 tên gần giống vẫn cần đối chiếu khi điểm đóng góp kỹ thuật bằng 0; không phải kết luận gian lận. Evidence refs phân biệt simulated/source_export; nguồn xuất không tự là chứng từ gốc đã xác minh.

View technical giữ RuleResult P1/E3. P1 `details.simultaneous_checks` được chuyển thành `details.simultaneous_group_refs` tới root groups để không nhân bản nhóm trên mọi dòng. Row score và group points tách riêng. Các luật khác, đồ thị, feature và ML không được gửi trong response API này.

## Lỗi và giới hạn kỹ thuật

| HTTP | Ý nghĩa |
|---|---|
| 200 | Có kết quả; từng check vẫn có thể unavailable hoặc not_applicable |
| 400 | Sai body/view/as_of, thiếu timezone, ID sai định dạng, query không hỗ trợ |
| 401 / 403 | Thiếu/hết hạn/thu hồi credential, sai DN, Origin/Host hoặc không có role kỹ thuật |
| 404 | Snapshot không có trong tenant/doanh nghiệp được phép; không phân biệt snapshot DN khác |
| 405 | Route hỗ trợ POST; GET/PUT bị chặn |
| 409 | Quyền thay đổi trong lúc xử lý |
| 413 | Vượt giới hạn đồng bộ hoặc kết quả quá lớn; không trả phần bị cắt |
| 422 | Snapshot không thỏa điều kiện nguồn/feature khi đọc lại |
| 500 / 503 | Lỗi toàn vẹn/xử lý hoặc kho chưa sẵn sàng; không có partial rows/traceback |

Bản demo đồng bộ giới hạn **200 transaction records, 1.000 source records trong snapshot, 5 MiB response**. Đây là giới hạn kỹ thuật, không phải quality gate hoặc chính sách phát hiện. Không tự cắt lịch sử để ép qua giới hạn; cần snapshot thử nhỏ đủ liên kết, hoặc worker/job riêng ở bước sau. API không ghi kết quả/queue, nên retry không tạo snapshot hoặc trạng thái nghiệp vụ mới; không bắt buộc Idempotency-Key.

## Chạy demo HTTP trọn luồng

Từ repo, chọn thư mục kết quả chưa tồn tại:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_snapshot_analysis.py --output-dir agent2/.runtime/analysis-http-demo
```

Demo tự tạo server cổng tạm, DB/policy mô phỏng riêng và hai role; upload → preview → commit → analyze → repeat. Lưu source/manifest/response hai view; credential không được in/lưu trong evidence. Server demo được đóng sau chạy, không thay dịch vụ 8766 đang dùng.

Canonical rules mới hỗ trợ P1/E3; thống kê/graph/ML đã nối riêng theo CR-027, chưa phải pipeline/quality gate hoàn chỉnh hoặc bằng chứng accuracy. Không thay kernel, feature, model, weight hoặc active config; màn hình nhập và bốn nhánh hiện theo CR-024/027.
