# Lịch sử người ký và người thao tác — R8, 16/10/2026

**R8 đã sửa kỹ thuật:** E1 tra người ký quyền nghỉ hưởng lương tại `approved_at`; B7 và feature ngân hàng tra người xác minh callback tại `verified_at`. Snapshot đổi tên hoặc chuyển công ty sau lúc ký không vô hiệu chứng từ hợp lệ đã ký trước đó. **292/292 test hồi quy đạt**, gồm 24 test mới.

## Tra nhân sự theo thời điểm

[`EmployeeHistory`](../sme_fraud/temporal_evidence.py) lưu snapshot đầy đủ theo `employee_id` và `recorded_at`, chọn revision mới nhất có `recorded_at <= thời_điểm_cần_tra`. Chọn revision trên toàn bộ lịch sử của ID trước khi kiểm tra công ty; không lọc công ty rồi làm sống lại snapshot cũ trước một lần chuyển công ty.

Nguồn cần ID nhân sự ổn định/toàn cục và các snapshot lịch sử đầy đủ, không chỉ hồ sơ cuối kỳ. Nhân sự chưa được biết lúc ký không được thêm ngược để cấp ngoại lệ. Timestamp tiếp tục dùng cùng chuẩn ISO/múi giờ của engine; bản sửa này không thay hợp đồng kiểm định scalar R7.

Các revision cùng ID/thời điểm phải giống nhau; bản trùng tương đương được gộp, bản khác nội dung bị từ chối bằng `ValueError` để không chọn theo thứ tự nhập. Chỉ mục giữ bản sao dữ liệu, không sửa bảng của bên gọi. Truy vấn một người dùng tìm kiếm nhị phân; mapping snapshot dùng cache giới hạn 512 mốc thời gian cho từng đối tượng lịch sử.

Các helper chấp nhận `EmployeeHistory` hoặc mapping đã được chọn sẵn đúng thời điểm. Mapping chỉ chứa master hiện tại không đủ để khôi phục lịch sử chữ ký; các đường gọi nội bộ đã chuyển sang lịch sử hoặc mapping theo ngày ký.

| Đường kiểm tra | Mốc tra snapshot | Đối chứng |
| --- | --- | --- |
| E1/quyền nghỉ hưởng lương | Người ký tại `approved_at`; yêu cầu độc lập với người hưởng lương giữ nguyên | Đổi tên/chuyển công ty sau ký vẫn 0 điểm; sai công ty lúc ký hoặc người ký chưa được biết vẫn không cấp ngoại lệ |
| B7/callback và feature | Người xác minh tại `verified_at`, độc lập với người lập giao dịch | Đổi tên sau callback giữ 0 điểm và `bank_change_verified=1`; sai công ty lúc callback không được xác minh |
| C1/lịch làm việc | Người ký lịch tại `approved_at`; người lập/duyệt tại thời điểm thao tác riêng | Quyền lịch không mất do đổi tên người ký; vai trò sau thao tác không thay vai trò lúc thao tác |
| PO/chứng từ/ngoại lệ A1/A2, B3 | Người xác minh tại `verified_at`; thỏa thuận tại `approved_at` | Liên kết PO độc lập và bộ chứng từ đúng loại vẫn được công nhận sau revision người xác minh |
| Quyền chi theo kỳ A4, chi định kỳ A5 | Người duyệt nguồn tại `approved_at`; các trần tiền/kỳ giữ nguyên | Revision tên không làm mất ngoại lệ; không tăng trần đã được duyệt |
| F1/nhật ký và nguồn đóng sổ | Người nhập tại `entered_at`; người ký lịch/trọng yếu tại `approved_at` | Revision sau nhập/ký không làm mất bằng chứng manual và nguồn trọng yếu đã được xác nhận |
| C2/C3, PaymentEvidence, EvidencePolicy | Giữ mốc ký/hành động đã có, dùng cùng chỉ mục lịch sử | Toàn bộ hồi quy R3, nguồn chi và nguồn HR/quy trình tiếp tục đạt |

Các ca tái hiện trước sửa xác nhận lỗi ngoài E1/B7 ở C1, PO/chứng từ B3, quyền chi theo kỳ và F1; các đường này đã sửa cùng R8. A5 và checker chưa được biết có thêm đối chứng hành vi hiện tại. Không tự nâng các helper chưa có ca tái hiện thành phát hiện mới.

Trong khi rà A5, có ca xác nhận thêm: nguồn chi định kỳ cấp công ty với `vendor_id=''`, `employee_id=''` được lập chỉ mục ở khóa rỗng, trong khi đường tra dùng `None`, nên mất ngoại lệ trước cả bước kiểm tra người ký. Đã chuẩn hóa khóa thực thể trống về `None`; đối chứng A5 kiểm tra cả cột nhân viên vắng và ô rỗng, rồi kiểm tra tiếp revision người duyệt. Các nguồn có ID NCC/nhân viên cụ thể vẫn giữ khóa riêng.

## Đường gọi đã cập nhật

- [`temporal_evidence`](../sme_fraud/temporal_evidence.py): tra người ký cho `approved_evidence`, quyền E1 và callback B7.
- [`rules`](../sme_fraud/rules.py) và [`features`](../sme_fraud/features.py): truyền cùng loại lịch sử vào helper chứng từ/callback; B1/đồ thị hiện hành vẫn dùng master đúng phạm vi riêng.
- [`noise_policy`](../sme_fraud/noise_policy.py), [`spec_policy`](../sme_fraud/spec_policy.py): chữ ký/xác minh đúng ngày, vai trò lịch ca đúng lúc thao tác, người nhập F1 đúng lúc nhập. Checker chưa biết không được mượn danh tính maker để áp lịch riêng của maker.
- [`authority_policy`](../sme_fraud/authority_policy.py), [`payment_evidence`](../sme_fraud/payment_evidence.py), [`evidence_policy`](../sme_fraud/evidence_policy.py): dùng chung chỉ mục, giữ API tra snapshot và các điều kiện quyền/coverage/binding/độc lập đã có.
- Kiểm tra đóng lô nhận lịch sử cho các helper ngoại lệ, không thay điểm hoặc thời điểm phát hiện lô.

## Kiểm chứng

**292/292 test đạt**, 56,731 giây, không failure/error, gồm 268 test trước và [24 test mới](../tests/test_signer_history.py). [Log](../.runtime/signer_history_20261016/tests.log), [kết quả và hash](../.runtime/signer_history_20261016/result.json).

```powershell
python -B -m unittest discover -s tests
```

Đối chứng bao gồm đổi tên, chuyển công ty trước/sau ký, chuyển đi rồi quay lại, biên `recorded_at == lúc ký`, người ký được thêm sau ký, tự ký, revision/bằng chứng tương lai, thu hồi quyền/callback không tác động ngược, vai trò tại thao tác, chứng từ/PO/lịch ca/trọng yếu, thứ tự snapshot, bản trùng và revision xung đột.

Chạy lại bản sao 7 probe readiness: **4 ca đạt** (2 R2 + 2 R8), **3 ca chưa đạt** (1 R6 + 2 R7), không lỗi chạy test; [quan sát](../.runtime/signer_history_20261016/observations.json), [log probe](../.runtime/signer_history_20261016/readiness_probes.log). Artifact trước các bản sửa được giữ nguyên.

## Phạm vi còn lại

R6 sau đó đã có [định danh cụm chuẩn và migration hồ sơ](rule_case_identity.md), 341 test và 7/7 probe đạt. R7 đã có [kiểm định miền giá trị nguồn cấp ngoại lệ](rule_exception_validation.md): hai probe cờ `2` đã đạt, 319/319 test hồi quy đạt tại lần chốt R7. Các kết quả 292 test/7 probe phía trên là snapshot R8. Không thay ngưỡng, trọng số hoặc chính sách thiếu bằng chứng trong bản R8.

Tên/thứ tự cột feature giữ nguyên; nội dung `bank_change_verified` có thể thay đổi trên nguồn có revision nhân sự. Cache feature/model cũ không tự được cập nhật: cần tạo dataset dẫn xuất mới, dựng lại feature và đối chiếu trước khi dùng cùng model. Nguồn chỉ có snapshot cuối kỳ chưa đủ tái hiện các chữ ký cũ.

Chưa chấm lại benchmark lớn, huấn luyện ML hoặc nghiệm thu SME thật. Tích hợp các bản sửa và các điều kiện nghiệm thu vận hành tiếp tục ở [báo cáo readiness](rule_readiness_recheck_20261016.md).
