# Kiểm định nguồn cấp ngoại lệ — R7, 16/10/2026

**R7 đã sửa kỹ thuật:** E1 từ chối `payroll_entitlements.evidence_on_file=2`; B7 và feature ngân hàng từ chối `bank_account_changes.callback_verified=2`. Nguồn sai gây `ValueError` chỉ rõ bảng/ID/trường, trước khi cấp ngoại lệ. **319/319 test hồi quy đạt** tại lần chốt R7, gồm 27 test mới; hai probe R7 đạt. R6 sau đó đã có [định danh và migration hồ sơ](rule_case_identity.md), 341 test và 7/7 probe đạt.

## Hợp đồng dữ liệu

[`exception_validation.py`](../sme_fraud/exception_validation.py) khai báo miền giá trị theo bảng. [Schema nguồn chi](../sme_fraud/payment_evidence.schema.json) và [schema HR/workflow/chứng từ/công nợ](../sme_fraud/evidence_sources.schema.json) dẫn tới hợp đồng này. Quyền/coverage C2/C3 tiếp tục có [validator R5](rule_authority_validation.md).

| Loại dữ liệu | Chấp nhận | Từ chối |
| --- | --- | --- |
| Cờ | Native `False/True`, số nguyên `0/1`, CSV chính xác `"0"/"1"` | `2`, `-1`, float `1.0`, chuỗi true/yes, rỗng, null, list/dict, khoảng trắng |
| Số tiền, dung sai, số lượng | Số nguyên không âm, CSV `[0-9]+`; trần giao dịch phải dương | Boolean làm số tiền, số thực, âm, dấu phân cách, exponent, NaN/Infinity, null |
| Ngày công, năm, số chứng từ | Ngày 0–31, số ngày làm việc yêu cầu 1–31; năm 1–9999; số chứng từ dương | Ngoài miền hoặc sai kiểu; khoảng số chứng từ đảo ngược/quá giới hạn |
| Enum | Tập giá trị được khai báo theo nguồn: trạng thái, loại nghỉ/chi, tần suất, loại lịch/chứng từ, hành động, sự kiện, lý do giải trình | Giá trị lạ/sai hoa thường/sai kiểu; không tự sửa thành giá trị mặc định |
| Ngày giờ | Ngày lịch thật `YYYY-MM-DD`; timestamp thật `YYYY-MM-DDTHH:MM:SS+07:00`; kỳ `YYYY-MM`, giờ `HH:MM`, cửa sổ năm `MM-DD` | Ngày không tồn tại, giờ sai, thiếu múi giờ, offset khác chuẩn, độ chính xác khác chuẩn, khoảng đảo ngược |
| ID/bằng chứng | Chuỗi, giữ số 0 đầu; ID nguồn/công ty không rỗng | ID sai kiểu, khoảng trắng quanh ID, bằng chứng chỉ có khoảng trắng |

Ngày ký/xác minh/thao tác không được sau `observed_at` khi trường được cung cấp. Callback yêu cầu `verified_at <= observed_at <= thời_điểm_chấm`. Các khoảng hiệu lực, nghỉ phép, kỳ phục vụ, đối soát và hạn trả phải đúng thứ tự. Lịch làm việc qua đêm và cửa sổ mùa đi qua cuối năm vẫn hợp lệ; cửa sổ năm cho phép 29/02. Nguồn định kỳ hỗ trợ ngày hoặc timestamp nhưng hai đầu phải cùng định dạng.

Kiểm định không đòi ngày hiệu lực/đóng sổ luôn ở quá khứ: nguồn đã biết có thể công bố lịch tương lai. Toàn bộ revision, kể cả tương lai hoặc thu hồi, đều được kiểm định trước khi lọc theo thời điểm. Dữ liệu hợp lệ được sao chép/chuẩn hóa; không sửa snapshot của bên gọi.

## Phạm vi và điểm chặn

- `load_inputs`, `build_features`, `score_rules` cùng kiểm định nguồn. Truyền cache feature hoặc tắt một policy không bỏ qua kiểm định nguồn sai.
- `EmployeeHistory`, `BankChangeHistory`, `PaymentEvidence`, `EvidenceBook` kiểm định dữ liệu của chúng khi được gọi riêng. Helper phê duyệt/callback không còn dùng `int(2)` như quyền hợp lệ.
- Bao phủ quyền nghỉ/lương E1, callback B7, PO/chứng từ/yêu cầu chi/hợp đồng, lịch chi định kỳ/năm/mùa, lịch ca, nhật ký/đóng sổ/trọng yếu và 14 nguồn HR/workflow/chứng từ/công nợ. Kiểm tra thêm cờ hợp đồng, chấm công thay thế, lịch công ty, hồ sơ tạm ứng, khai báo quan hệ NCC và các cờ/số/ngày chứng từ giao dịch dùng cho ngoại lệ.
- Ràng buộc công ty, người ký độc lập, ngân hàng R2, lịch sử người ký R8, revision/thu hồi và trần tiền vẫn do các predicate nghiệp vụ kiểm tra sau validator. Đúng kiểu dữ liệu không tự chứng minh có quyền.

**Thiếu bằng chứng khác với bằng chứng sai.** Cờ 0 hợp lệ không cấp ngoại lệ. Trường chứng từ/người ký/thời điểm ký rỗng được phép thể hiện thiếu hồ sơ và không cấp ngoại lệ; `invoice_gross_vnd` tùy chọn trong nguồn chứng từ được phép rỗng để thể hiện thiếu giá trị. Các trạng thái draft/pending/rejected/revoked hoặc unverified được giữ khi phù hợp nguồn, không trở thành approved/verified. Chính sách giữ cảnh báo khi thiếu hồ sơ nghĩa vụ chi vẫn như hiện hành. Bản sửa không thay trọng số/ngưỡng hoặc lấy fallback để che nguồn sai.

## Dữ liệu mẫu và nguồn cũ

Fixture `Case.change(verified=True)` và hard negative `verified_bank_change` của generator trước đây có `verified_at > observed_at`. Đã sửa mẫu để bản ghi đã xác minh chỉ được quan sát từ thời điểm callback; nguồn hẹn đổi tài khoản và revision callback vẫn được kiểm tra theo thời điểm.

Dataset tổng hợp cũ chứa quan hệ thời gian sai này sẽ bị validator mới từ chối. Giữ nguyên snapshot/artifact cũ; tạo dataset dẫn xuất mới từ generator đã sửa rồi dựng lại feature và kiểm tra tương thích model. Không tự sửa ngày quan sát trên chứng từ thật: phải đối chiếu nguồn để bổ sung revision đúng hoặc loại nguồn sai khỏi đầu vào đã được xác nhận. Không đổi manifest/hash để hợp thức hóa dữ liệu sai.

## Kiểm chứng và giới hạn

- [27 test R7](../tests/test_exception_validation.py) kiểm tra lỗi E1/B7, native/CSV, enum/số/ngày giờ, khoảng đảo ngược, ID chứng từ, nguồn tương lai/thu hồi, cache, constructor và bộ nạp CSV có checksum đúng. Các ngoại lệ hợp lệ, cờ 0 và bằng chứng thiếu có đối chứng riêng.
- **319/319 test đạt**: gồm 292 test trước và 27 test R7. [Log đầy đủ](../.runtime/exception_validation_20261016/tests.log), [kết quả/hash](../.runtime/exception_validation_20261016/result.json). [Hai test đỏ trước sửa](../.runtime/exception_validation_20261016/before_fix.log).
- Bản sao 7 probe readiness: **6 đạt**, **1 chưa đạt** là R6, **0 lỗi chạy test**. Hai ca R2, hai ca R7, hai ca R8 đều đạt. [Quan sát từng ca](../.runtime/exception_validation_20261016/observations.json), [log](../.runtime/exception_validation_20261016/readiness_probes.log). Artifact lịch sử được giữ nguyên.

Chưa chạy lại benchmark lớn/train–validation kết hợp, dựng lại cache/model hoặc nghiệm thu nguồn SME thật. Chưa khẳng định mọi kiểu dữ liệu ERP hoặc nghiệp vụ hoàn/hủy/đảo đã được hỗ trợ. R6 đã sửa kỹ thuật; tiếp theo là đồng bộ dataset/feature/model, áp migration vào đúng bộ hồ sơ và nghiệm thu theo [readiness](rule_readiness_recheck_20261016.md).
