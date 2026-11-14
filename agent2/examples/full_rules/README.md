# Mẫu nguồn đầy đủ cho pipeline 35 luật

Các JSON ở đây dùng tenant **demo**, doanh nghiệp C001/C002 và dữ liệu mô
phỏng. Cần quyền đúng tenant/doanh nghiệp. Tất cả 35 evaluator được gọi;
không có nghĩa mỗi tệp có đủ nguồn hoặc có tín hiệu của cả 35 luật.

- `C001_B1_signal.json`, `C002_B1_signal.json`: tài khoản/định danh NCC liên
  quan nhân viên, có căn cứ và bước đối chiếu.
- `C001_C2_signal.json`: tự duyệt, nguồn thẩm quyền được khai rõ.
- `C001_E2_signal.json`: kỳ lương và thông tin nghỉ việc cần kiểm tra.
- `C001_F4_signal.json`: chẩn đoán công nợ theo nguồn, không gán thành lỗi
  của riêng giao dịch.
- `C001_coverage_unknown.json`: giữ dữ liệu nhưng coverage chưa rõ; luật
  tương ứng phải chưa khả dụng, không được tự coi không vi phạm.

Không có nhãn hay kết quả kỳ vọng trong nguồn. Đây không phải chứng từ gốc
đã xác minh hoặc dữ liệu để công bố độ chính xác gian lận.

[Tải bộ 120 tệp C001/C002](full_rule_inputs_C001_C002.zip). Giải nén rồi nhập
một JSON mỗi lần; không tải ZIP vào ô nhập dữ liệu. Manifest có checksum từng
tệp. Các tên signal/control chỉ là kịch bản thử, không phải nhãn trong nguồn.

Tạo lại bằng `agent2/.venv/Scripts/python.exe agent2/scripts/prepare_full_rule_inputs.py`
sau khi có bộ nguồn native demo CR-047. Script chỉ đổi tenant cho dữ liệu mô
phỏng của producer `native-demo`, từ chối áp dụng vào nguồn doanh nghiệp thật.

[Hướng dẫn nhập, phân tích và schema](../../docs/FULL_RULE_PIPELINE.md).
