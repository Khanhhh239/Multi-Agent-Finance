# Lựa chọn OCR baseline

> **Lịch sử lựa chọn ban đầu.** Theo yêu cầu người dùng, mặc định hiện đã đổi sang **PP-OCRv6 + VietOCR**; [báo cáo model switch](model_switch/README.md) và [runbook](model_switch/runbook.md) là hướng dẫn hiện hành. Chưa có so sánh chứng minh hybrid tốt hơn Tesseract; lựa chọn này thực hiện định hướng model của dự án.

Chọn **Tesseract 5.0.0.20211201, `vie+eng`, PSM 3**, config `tesseract-v1-psm3`. Phiên bản lấy từ executable đang chạy, không suy từ tên installer. Checksum và package/runtime versions nằm trong [runtime matrix](adapter_runtime_matrix.json).

Thứ tự chọn được khóa trong script: exact tổng tiền → exact ngày → CER → WER. Khi chất lượng bằng nhau, ưu tiên PSM 3 vì auto page segmentation phù hợp route toàn trang; latency nhỏ trên 10 mẫu không đủ để đảo lựa chọn. PSM 6 có cùng kết quả chất lượng. PSM 11 giảm CER nhẹ nhưng biến `11/10/2026` thành `1/10/2026` trên bộ mẫu này; không chọn làm mặc định chỉ vì CER thấp hơn.

| Nhóm lỗi | Quan sát / phạm vi | Hướng xử lý tiếp |
|---|---|---|
| Dấu tiếng Việt | Mất dấu/nhầm chữ trong tên và nhãn, WER còn cao | PLAN_04 giữ raw text/candidates; PLAN_05 đánh giá tập có nhãn thật |
| Tiền | `syn-01`, `syn-06` không đạt exact tổng tiền; không tự sửa chữ số | PLAN_04 trích field và evidence; PLAN_05 kiểm tra đối chiếu tổng/candidates |
| Ngày | PSM 11 thiếu chữ số; PSM 3/6 exact 10/10 trong oracle region | Giữ default 3; field localization/normalization kiểm tra riêng ở PLAN_04 |
| Ảnh mờ/perspective | Chưa có split blur/perspective có nhãn độc lập | Chưa công bố hỗ trợ chất lượng; thêm dữ liệu ở PLAN_05 |
| Bảng/cột | Có test ordering/dedup và table hints, chưa nhận dạng cell/table structure | PLAN_04 triển khai line items; không coi block order là item identity |
| Full-page text không box | Bridge biểu diễn geometry UNAVAILABLE, không bịa bbox | Review hoặc producer có geometry khi cần evidence theo trường |

Route mặc định: NATIVE_TEXT dùng native blocks; OCR/HYBRID dùng Tesseract raster chuẩn PLAN_02 và conservative merge. Không xoay/deskew/crop tự động thêm trong worker; transform chuẩn kế thừa PLAN_02. Worker báo MODEL_UNAVAILABLE khi thiếu executable/env/language data, không đổi engine ngầm.

**Fallback tự động tắt.** Chưa có quality trigger được kiểm chứng để chuyển cấu hình/engine. PSM 6/11 là cấu hình thử có version riêng, không được gọi liên tiếp để chọn số tiền thuận ý. Một lần chạy cấu hình khác tạo job/result/provenance riêng; không ghi đè result. Cross-engine và fallback có budget chỉ bổ sung khi PLAN_05 có dữ liệu chứng minh lợi ích.

Gate của chặng này là kết nối/OCR/layout chạy được và có baseline tái hiện. Chưa đạt production accuracy, field calibration hay auto acceptance. Chưa cần train OCR trước PLAN_04; ưu tiên dữ liệu có nhãn và phân tích lỗi trước quyết định train.
