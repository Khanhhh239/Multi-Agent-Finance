# CR-018 — bổ sung đầu vào P1

Đã hoàn tất phần hợp đồng, kiểm tra backend và gắn nguồn P1. **Chưa bật evaluator P1; R2 tổng thể PARTIAL.**

## Thay đổi

- Input **1.1.0** thêm transactions.payment_channel và payment_history_coverage. Kênh phải khai báo rõ; không đoán từ tài khoản 111/112, bank_code hoặc mô tả. Schema 1.0.0 lưu riêng và tiếp tục được đọc; snapshot mới ghi phiên bản thật của payload.
- Liên kết giao dịch–phân bổ–hóa đơn đúng tenant/doanh nghiệp/ID/revision. Kiểm mốc nguồn được biết, phạm vi lịch sử, manifest membership/count/hash. Giữ số âm và điều chỉnh hợp lệ; vượt giá trị hóa đơn không phải lỗi định dạng nhập.
- Coverage do nguồn khai báo gồm invoice refs, khoảng thời gian, history_basis, coverage_status và export_id. Complete + since_inception chỉ đủ nguồn khi manifest nhất quán và còn hiệu lực tại cutoff. Đây không phải xác minh độc lập rằng đầy đủ sổ bên ngoài.
- Thiếu/unknown/other channel, không có coverage, partial/unknown/bounded, claim stale hoặc mâu thuẫn đều có lý do unavailable. Không tự tính số đã trả bằng 0, suy opening balance hoặc fallback claim complete cũ khi claim mới hạn chế hơn.
- RuleInputs **1.1.0**, validator/report **1.2.0**; preview context khóa cả hai schema và code kiểm P1. Đổi tệp/mapping/code phải kiểm tra lại. Quyền và checksum snapshot vẫn được kiểm; không thêm quyền xác minh vào đường đọc.

## Bằng chứng

- [616 kiểm thử hồi quy](native_tests.json): 0 lỗi/thất bại/bỏ qua, 599.421 giây; gồm **19 ca P1**. [Log](native_tests.log).
- [148 kiểm thử tập trung](focused_tests.json) đã qua trước khi thêm ca thứ 19 về mốc since_inception; hồi quy 616 kiểm tra trạng thái cuối cùng. [Chẩn đoán ban đầu](initial_compat_tests.json) có 1 ca kỳ vọng cũ, đã cập nhật lý do thiếu phạm vi lịch sử và qua hồi quy cuối.
- [Demo backend](demo/summary.json): khai báo đủ → input ready; thiếu kênh/partial → giữ dữ liệu và unavailable; manifest sai → reject. Upload → preview → commit tạo snapshot 1.1.0; retry cùng yêu cầu giữ cùng snapshot, **6/6** giao dịch có kết quả.
- Kiểm thử tách hai doanh nghiệp cùng mã, nguồn đến muộn không đổi quá khứ, không dùng preview cũ khi sửa tệp/mapping, snapshot 1.0.0 giữ nguyên, điều chỉnh âm, manifest bị sửa và không bỏ dòng khi thiếu nguồn.
- [Provenance](provenance.json) ghi hash bảo toàn kernel/model implementation, feature contract 33 cột không đổi và schema 1.0.0 được lưu đúng byte. Không fit model hoặc thay active config.

## Giới hạn và bước sau

P1 source ready chỉ xác nhận cấu trúc và khai báo nguồn nhất quán. **RuleResult P1 vẫn unavailable, score/matched=null, reason=rule_evaluator_unavailable**. Chưa tính tổng thanh toán, cảnh báo vượt hóa đơn, nối queue hoặc kết luận hiệu quả ML. Evaluator và đối chiếu engine là nhiệm vụ tiếp theo cần giao riêng.

Luồng thử hiện là JSON/backend, không phải bổ sung CSV/Excel/UI. Dữ liệu demo là mô phỏng, không dùng làm nhãn, accuracy hoặc nghiệm thu dữ liệu thật. [Hướng dẫn](../../../../agent2/docs/P1_INPUTS.md), [mẫu](../../../../agent2/tests/fixtures/input_p1_v1_1.json).
