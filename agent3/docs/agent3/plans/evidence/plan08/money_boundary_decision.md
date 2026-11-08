# Quyết định money boundary — 15/10/2026

**Chọn `decimal-facts-v1`: mọi tính toán/so sánh tiền thực hiện bằng Decimal trong adapter; ZEN 0.53.0 chỉ nhận strict boolean facts.** Không truyền tiền qua float, không ép Decimal string thành số trong engine. Ngưỡng non-cash vẫn ở planning, không lặp trong JDM.

Đã cài và pin engine trong venv ứng dụng, chạy lại trên máy Windows/Python 3.10.5. [Probe thực tế](money_boundary_probe.json): Decimal object bị từ chối, cộng decimal string bị lỗi, `9007199254740992 + 1` trong engine mất đơn vị. Adapter trả đúng `9007199254740993`. Không dùng một vài ví dụ cộng float đúng làm bằng chứng tài chính chính xác.

Miền hỗ trợ: hữu hạn, tối đa 60 chữ số và scale 12; reject float/bool/exponent string/NaN/Infinity, overflow và kết quả vượt scale. Không tự làm tròn. Hàm rounding riêng yêu cầu scale và HALF_UP/HALF_EVEN rõ ràng; model hiện tại không tự dùng phép làm tròn để sửa giá trị chứng từ. Sum/product tăng precision theo dữ liệu, không phụ thuộc Decimal context toàn cục. Kiểm bằng 500 cặp số seed cố định với `Fraction` làm oracle độc lập.

Engine xử lý quyết định từ facts đã tính; normalized trace của facts mang origin **ADAPTER**, policy version và evidence/hash. Matched row mang origin **ENGINE**. Raw engine trace lưu nguyên chuỗi JSON và SHA-256. Không tuyên bố engine đã tính tiền hoặc cung cấp boolean condition trace mà SDK không trả.

Phạm vi model hiện chỉ là restricted boolean decision table, hitPolicy first, explicit FAIL/REVIEW/PASS rows; adapter đối chiếu row/output/input với bảng đã pin. Các node JavaScript/custom loader/arbitrary expression không nằm trong supported contract.

Nguồn SDK sơ cấp: [GoRules Python binding](https://github.com/gorules/zen/tree/master/bindings/python). Nội dung nhánh master có thể khác 0.53.0; quyết định trên dựa vào probe phiên bản được pin tại dự án. Nâng SDK phải tạo package/runtime mới và chạy lại kiểm chứng.
