# Sửa lịch sử nhân sự trong C2/C3

Ngày kiểm tra: 16/10/2026. Đã sửa phát hiện R3 trong [báo cáo readiness](rule_readiness_recheck_20261016.md). Trọng số C2/C3, ngưỡng tốc độ duyệt 60 giây và điều kiện hiệu lực/thu hồi nguồn thẩm quyền giữ nguyên.

## Hành vi sau sửa

C2/C3 dùng hai mốc thời gian riêng:

- **Người ký coverage hoặc quyền:** tra snapshot nhân sự đã được quan sát tại `record.approved_at`. Cập nhật tên hoặc thông tin nhân sự sau ngày ký không làm bằng chứng hợp lệ mất hiệu lực.
- **Người lập/người duyệt giao dịch:** tra snapshot tại `transaction.approved_at` để đối chiếu vai trò và công ty. Thay đổi sau lúc duyệt, trước lúc ghi sổ không cấp thêm hoặc tước quyền cho hành động đã xảy ra.

Với `spec_policy=phase3`, C2 không có coverage hợp lệ vẫn dùng hạn mức master, nhưng lấy hạn mức **đã biết tại lúc duyệt**. Một lần giảm/tăng hạn mức sau hành động không đổi kết luận cũ. Runner `spec_policy=legacy` giữ hành vi lịch sử.

Nhân sự chưa có bản ghi được quan sát tại mốc kiểm tra không được dùng để xác nhận quyền. Khi nhân sự chuyển công ty, engine chọn revision đúng thời điểm trước rồi mới kiểm tra công ty, tránh phục hồi nhầm snapshot cũ của công ty trước. Bằng chứng ký hợp lệ trước chuyển công ty vẫn được giữ.

Coverage/quyền vẫn được truy vấn theo thời điểm duyệt giao dịch. Thu hồi quan sát sau hành động không đổi kết luận tại hành động; thu hồi trước hành động không cấp ngoại lệ. C3 thiếu coverage vẫn giữ proxy số tiền theo chính sách hiện hành.

Ví dụ đã kiểm chứng:

- Tự duyệt 9 triệu có quyền hợp lệ: C2 vẫn **0 điểm, không hard trigger** sau khi đổi tên người ký ma trận hoặc người ký quyền.
- Giao dịch 1 triệu được người có quyền cấp cao duyệt trong 30 giây: C3 vẫn **8 điểm** sau cập nhật hồ sơ; không bị mất tín hiệu do quay về proxy 50 triệu.
- Vai trò/hạn mức mới chỉ có sau lúc duyệt không được dùng để hợp thức hóa hành động trước đó.

## Mã và kiểm thử

[Tra phiên bản nhân sự](../sme_fraud/authority_policy.py#L97) dùng lịch sử theo `employee_id` ổn định và tìm revision gần nhất không sau cutoff. [Xác minh người ký](../sme_fraud/authority_policy.py#L109) dùng ngày ký nguồn; [đối chiếu người thực hiện](../sme_fraud/authority_policy.py#L130) dùng thời điểm hành động. [C2 fallback trong engine](../sme_fraud/rules.py#L729) cũng lấy đúng snapshot tại lúc duyệt.

Đã thêm **11 test lịch sử** trong [test_authority_and_dormancy.py](../tests/test_authority_and_dormancy.py#L160), bao phủ:

1. C2: đổi tên người ký coverage và người ký quyền độc lập.
2. C3: cập nhật hồ sơ hai người ký không làm mất quyền cấp cao.
3. C2: vai trò trước/sau duyệt, cả hướng cấp quyền và mất quyền.
4. C3: vai trò trước/sau duyệt, cả hướng phát hiện và không phát hiện.
5. C2 fallback: tăng/giảm hạn mức sau hành động.
6. Người ký nguồn chỉ được quan sát sau ngày ký không xác nhận được quyền.
7. Người thực hiện chỉ được quan sát sau hành động không nhận ngoại lệ C2.
8. Revision nhân sự tương lai không đổi kết quả C2/C3 quá khứ.
9. Thu hồi coverage/quyền trước và sau hành động.
10. Công ty của người ký tại ngày ký, trước/sau chuyển công ty.
11. Công ty của người duyệt C3 tại hành động, trước/sau chuyển công ty.

Toàn bộ **209/209 test đạt**, không failure/error, gồm 198 test trước đó và 11 test mới. [Kết quả máy đọc](../.runtime/authority_history_20261016/result.json), [log](../.runtime/authority_history_20261016/tests.log).

```powershell
python -B -m unittest discover -s tests
```

## Phạm vi còn lại

Bản R3 ban đầu áp dụng cho C2/C3. Từ bản [R8](rule_signer_history.md), E1/B7 và các helper đã kiểm chứng cũng tra theo thời điểm, dùng cùng chỉ mục nhân sự. Cần giữ lịch sử snapshot với ID ổn định và `recorded_at`; trạng thái cuối kỳ không đủ để tái hiện vai trò/hạn mức trước đó.

Chưa chấm lại benchmark lớn hoặc nghiệm thu IAM/ERP thật. R4 đã có [kiểm tra đóng lô](rule_batch_close.md), R5 đã có [kiểm định miền giá trị quyền](rule_authority_validation.md), R2 đã có [định danh ngân hàng thống nhất](rule_bank_identity.md), R8 đã có [lịch sử người ký dùng chung](rule_signer_history.md), R7 đã có [kiểm định nguồn ngoại lệ](rule_exception_validation.md), R6 đã có [định danh và migration hồ sơ](rule_case_identity.md). Bước tích hợp/nghiệm thu còn thiếu được ghi tại báo cáo readiness.
