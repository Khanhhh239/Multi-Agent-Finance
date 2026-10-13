# Đổi OCR mặc định sang PP-OCRv6 + VietOCR

Ngày: **12/10/2026**. Đây là bổ sung cho PLAN_03 theo yêu cầu chọn model của người dùng. Báo cáo Tesseract gốc được giữ làm lịch sử; không dùng kết quả cũ để kết luận hybrid tốt hơn.

Mặc định mới: **PP-OCRv6 TextDetection + VietOCR `vgg_transformer`**, config `ppocrv6-vietocr-cpu-v1`, trọng số local `transformerocr.pth`. PaddleOCR 3.7.0, PaddlePaddle 3.3.1, Torch 2.13.0, VietOCR 0.3.13 theo probe environment thực tế. Chưa train hoặc tải model mới.

Thiết kế mới có [run config và registry engine](../../../../../../agent3_tax_compliance/configs/ocr/README.md). Thay engine có adapter sẵn bằng JSON; bridge không import framework và PLAN_04 không phụ thuộc loại model. App default pointer, CLI và bridge cùng dùng config. Tesseract vẫn có thể gọi bằng config riêng, không là fallback tự động.

## Kiểm chứng

- Smoke thật: 27 detections trên ảnh project, khoảng 65 giây CPU (load khoảng 26 giây, inference 36 giây), peak committed memory khoảng 1,3 GiB. Chi tiết/hash trong [smoke report](ppocrv6_vietocr.smoke.json).
- Baseline integration: **5 tài liệu / 6 trang**, gồm PNG, PDF native tiếng Việt, PDF scan 2 trang, hybrid và native PDF crop/rotation. **4 trang gọi OCR**, hai trang native bỏ qua model; tất cả COMPLETE. [Baseline](baseline_summary.json) giữ paths/hash/raw responses và worker metrics.
- Re-enter cùng ingestion/config/runtime dùng artifact đã commit, không inference lại. Tests riêng kiểm tra retry/crash, model correlation, isolation, tenant scope, cache invalidation và runtime profile thay thế.
- [Validation](validation_summary.json) là gate hiện hành sau đổi model. Contract profile mới `ocr-v1.1/` có 12 schemas, bổ sung EngineProfile, model ID và detector score semantics; profile `ocr-v1/` cũ giữ nguyên.

## Giới hạn

Model switch được nghiệm thu chức năng, chưa là benchmark chất lượng hoặc chứng minh tốt hơn Tesseract. Smoke vẫn có chữ/số đọc sai; cần PLAN_04 trích candidates/evidence và PLAN_05 đánh giá có nhãn trước auto acceptance. Detector confidence không được dùng làm VietOCR recognition confidence.

Mặc định CPU, timeout tối đa 600 giây/trang mỗi attempt, memory cap 6 GiB, 2 attempts cho timeout/transient IO; crash/model unavailable không tự retry/fallback. Process limit 2 cho Windows venv redirector và Python; không thêm executable OCR con như Tesseract. Model được load lại cho mỗi page worker, nên startup đáng kể; persistent serving chưa triển khai.

Orientation classifier trong hybrid tắt để giữ nguyên raster/transform PLAN_02. Chưa nghiệm thu ảnh có chữ xoay mà không có PDF/EXIF orientation metadata. EasyOCR và PP-OCRv6 Medium có declarative profile nhưng chưa chạy nghiệm thu bridge mới.

[Runbook hiện hành](runbook.md) · [Thiết kế thêm/thay engine](../../../../../../agent3_tax_compliance/configs/ocr/README.md)
