# Kết quả đánh giá từng luật — CR-016

CR-023 đã có [HTTP phân tích snapshot P1/E3](SNAPSHOT_ANALYSIS_API.md). Mặc định trả DTO nghiệp vụ theo quyền; RuleResult/điểm kỹ thuật chỉ director đúng DN. Chỉ nhóm HTTP P1 được chuyển ra root groups và dùng refs, không đổi kết quả hay schema core bên dưới. CR-027 hiện có UI/HTTP bốn nhánh; phần luật ngoài P1/E3 vẫn chưa được đánh giá đầy đủ.

Backend/CLI snapshot score trả `methods.rules.details.rule_results`, phiên bản `rule-results/1.0.0`, theo schema `sme_fraud/rule_results.schema.json`. Mỗi giao dịch vẫn có đủ 35 kết quả luật. Hiện E3 và [P1](P1_EVALUATION.md) chạy khi đủ nguồn và nội dung nhất quán; các luật còn thiếu bảng/trường/evaluator chưa được chạy.

| status | available | matched | intrinsic_points / score | Ý nghĩa |
|---|---|---|---|---|
| evaluated_hit | true | true | Điểm gốc / điểm đóng góp theo chính sách | Đã kiểm tra và có tín hiệu, chưa kết luận gian lận |
| evaluated_no_hit | true | false | 0 / 0 | Không thấy tín hiệu trong dữ liệu nhìn thấy; không xác nhận giao dịch hợp lệ hoặc đầy đủ sổ |
| unavailable | false | null | null / null | Thiếu nguồn, nội dung không đủ thông tin hoặc chưa có evaluator; xem reason và gaps |
| not_applicable | false | null | null / null | Ngoài phạm vi luật; không phải không trúng luật |

`evidence_refs` chỉ đúng bảng, ID, revision và thời điểm nguồn dùng đánh giá. `source_checksum` khóa payload; `implementation` và `configuration` khóa phiên bản và chính sách thực. Nguồn khác doanh nghiệp, quá cutoff hoặc payload/evidence không khớp đầu vào bị chặn. Không gọi fit khi chấm.

## Ví dụ E3

Tên NCC `North Harbor Equipment` tương tự `North Harbour Equipment` vượt ngưỡng mặc định của engine giữ lại:

```json
{
  "rule_id": "E3",
  "status": "evaluated_hit",
  "available": true,
  "matched": true,
  "intrinsic_points": 3,
  "score": 0,
  "reason": null
}
```

Điểm đóng góp bằng 0 vì E3 thuộc `master_quality`: giữ tín hiệu rà chất lượng master, không cộng thành rủi ro giao dịch. **Không dùng score=0 để suy ra không trúng luật; đọc status/matched.** Căn cứ gồm NCC đối chiếu, similarity, threshold và source references. Tái sử dụng name_key/name_similarity/assign_noise_points, WEIGHTS/DEFAULT_CONFIG hiện hành; không đổi trọng số.

Tên là chuỗi số hoặc mẫu bộ chuẩn hóa không so được: `unavailable`, `matched=null`, điểm null và `name_content_insufficient`. Không bỏ qua tên chưa so được rồi tuyên bố không trùng.

C2 thiếu ma trận quyền đã duyệt: `status=unavailable`, `reason.code=rule_sources_unavailable`; gaps chỉ ra bảng/trường và cách bổ sung. Nguồn ready nhưng evaluator chưa được kiểm chứng: `rule_evaluator_unavailable`, không điền 0.

## Tổng và phạm vi

`rule_results.aggregate` và MethodScore rules tổng vẫn `available=false`, `score=null`, `reason.code=rules_incomplete`. Không cộng điểm từng phần thành tổng để đưa vào hàng đợi. Native profile đầy đủ nguồn vẫn dùng nguyên engine tổng hợp cũ.

`rule_inputs` là biên nhận bước chuẩn bị nguồn; marker `evaluation_status=not_evaluated` ở đó không phải kết quả cuối. Đọc `rule_results` để biết luật đã chạy. Resolver patch `rule-inputs/1.0.1` chỉ lan truyền gap theo vai trò nguồn: lỗi liên kết hóa đơn không tự vô hiệu hóa E3 khi nguồn tên vẫn đủ.

Chỉ dùng nguồn tại cutoff riêng của giao dịch, lọc cả hai clock trước revision. Nguồn đến muộn không sửa kết quả quá khứ; bằng chứng không vào feature/nhãn. Backend đọc input contract 1.0.0/1.1.0; P1 cần nguồn mới 1.1.0. Feature contract 33 cột giữ nguyên. Hash adapter mới khiến model lưu với hash code cũ bị từ chối theo CR-013; cần fit job riêng, không tự fit khi chấm.

## Kiểm thử

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py --suite test_rule_evaluation --suite test_rule_sources --suite test_method_adapters --suite test_method_jobs --report agent2/.runtime/rule-result-tests.json
```

Chưa mở UI/HTTP chấm mới, active model, ensemble hoặc hàng đợi. Đây chưa phải nghiệm thu toàn R2 hay bằng chứng độ chính xác ML.
