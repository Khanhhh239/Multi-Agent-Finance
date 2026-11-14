# Chức năng nghiệp vụ (R4)

**BẮT BUỘC:** RULE-MONEY-01, RULE-LABEL-01, RULE-CASE-01, RULE-TENANT-01. Dùng schema và trạng thái tại [04](04_contracts_states_modules.md).

## Đối chiếu

Một màn hình độc lập liệt kê giá trị nghĩa vụ hiệu lực, tiền phân bổ, còn lại, vượt, trạng thái và bằng chứng. Xét trả nhiều đợt, hoàn/hủy, điều chỉnh, nhiều-nhiều qua allocation và tiền tệ. Gợi ý ghép cần người có quyền xác nhận; thay allocation tạo revision. Còn phải trả, unmatched và missing document là tình trạng nghiệp vụ, mapping target theo D-08.

## Hồ sơ

DocumentRequirementPolicy theo loại nghiệp vụ, điều kiện và version. DocumentChecklist mô tả yêu cầu, bằng chứng, trạng thái và thời điểm kiểm tra. Có file không đồng nghĩa đã xác minh; không có nguồn dữ liệu khác với xác nhận thiếu hồ sơ. Tạo task bổ sung với owner/due_at. Đây là policy nội bộ; không mặc định bảo đảm mọi nghĩa vụ pháp luật.

## Khắc phục

ActionTask gắn case hoặc obligation, có assignee, deadline, kết quả, bằng chứng hoàn tất và revision. Kết luận vụ, trạng thái task và phê duyệt nhãn độc lập. Đóng case không tự hoàn tất task. Mở lại/hủy cần lý do; hoàn tất cần bằng chứng theo policy. Chuyển tiền/sửa sổ nằm ở hệ thống nghiệp vụ với quyền riêng.

Ví dụ HD78 đã trả bởi T096, T105 trả tiếp: T105 là ứng viên, T096 là bằng chứng. Xác nhận chênh lệch → giao task đối chiếu NCC → ghi nhận chứng từ hoàn/điều chỉnh → xác nhận kết quả. Giữ nguyên lịch sử.

## Báo cáo

Dashboard: vụ mới/đã kết luận/treo; task quá hạn; thời gian; tỷ lệ hồ sơ đủ; kết quả đối chiếu; loại sai lệch lặp lại. Tiền liên quan, chênh lệch, tổn thất xác nhận và thu hồi có trường riêng; chưa biết null. Aggregation có chống trùng và ghi scope/as_of/version.

IssueType: data_issue, missing_document, payment_discrepancy, process_exception, unexplained_anomaly. Không tự chuyển issue thành nhãn ML.

## Sau MVP — ĐỀ XUẤT

Pre-payment khi có payment intent/revision và kiểm tra lại sát lúc thực hiện; hồ sơ NCC có bằng chứng; tra cứu ngôn ngữ tự nhiên sau API phân quyền. Không mở rộng sang sổ cái, dòng tiền hoặc tín dụng trước khi thống nhất trách nhiệm với các agent khác.
