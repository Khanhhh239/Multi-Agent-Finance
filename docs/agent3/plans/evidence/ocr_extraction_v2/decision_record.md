# Quyết định nhánh — PLAN_06 / OCR extraction V2

Ngày: 14/10/2026. Trạng thái: quyết định kỹ thuật tạm thời trên dev; chưa nghiệm thu tổng quát.

Baseline đã đóng băng trước khi sửa adapter, ở `data invoice/ocr_extraction_v2/plan06_v20_frozen_01`. 9 case native, 3 case scan và 3 case hybrid dùng cùng nhãn chọn lọc pilot; không phải 15 hóa đơn độc lập. Không đổi nhãn theo output để tăng điểm.

1. **Chọn V2-1 xử lý dòng dài**: crop VNPT được xem trực tiếp còn đầy đủ chữ; dòng dài bị đọc sai. Thử đơn biến resize 512/768/1024, sau đó thử tách tại khoảng trắng rõ ràng. Tăng width bị loại do tệ hơn; split được đưa vào profile thử nghiệm riêng để kiểm tra toàn trang. Chưa bật default theo một crop.
2. **Chọn phần hẹp V2-3 financial field binding**: tổng thanh toán bằng 0 trên Viettel điều chỉnh nằm lệch baseline so với nhãn. Không suy ra số 0 bằng phép tính; phải gắn đúng value block và giữ evidence. Viết regression về lệch dòng, tránh lấy giá trị hàng trước và giữ ambiguity nếu có hai số.
3. **Hoãn V2-2 PP-OCRv6 recognizer** nếu charset preflight local không pass. Kiểm tra dictionary và decoder thực tế đi kèm weights; không chỉ dựa `lang=vi`. Không sửa dictionary để vá weights tại chỗ.
4. **Chưa chọn** nâng DPI, deskew, rectification toàn pipeline, tiling, semantic extractor/VLM và fine-tune. Chưa có oracle/dữ liệu đủ để quy phần lỗi còn lại cho các kỹ thuật này. Có helper geometry thử nghiệm không đồng nghĩa bật runtime.
5. **Giữ manual review và default V1** trong khi so sánh. Một nguồn public mới chỉ là holdout candidate; nhãn/khả năng độc lập chưa xác nhận. Theo user steering, tự test UI được dùng cho gate kỹ thuật, không được thay statistical gate.

Inventory sinh tự động chỉ nêu giả thuyết. Chuỗi expected xuất hiện bên trong một block có thể vẫn kèm OCR rác, nên `FIELD_UNBOUND` không tự chứng minh text đã hoàn toàn đúng. Phân loại root cause cuối cần crop, parser trace và oracle; không cộng các lỗi scan/hybrid thành số hóa đơn độc lập.

Ngân sách vòng này: 3 width + 1 split trên crop, một split toàn trang trên 3 case scan, một sửa binding hẹp. Các oracle read/layout đầy đủ trên 10–20 lỗi vẫn PENDING; normalizer probe dùng canonical labels chỉ là sanity check, không phải raw-transcription oracle.
