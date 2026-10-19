# OCR coverage, đối chứng và bảng nhiều trang — 19/10/2026

Đợt này tiếp tục PLAN_06. Đã triển khai nhánh kỹ thuật cho xử lý ảnh/phát hiện chữ, cấu hình đọc đối chứng, bảng hàng và chuẩn bị đánh giá dữ liệu chưa dùng sửa code. **Chưa nghiệm thu OCR tổng quát, chưa bật auto-accept, chưa thay recognizer chính và chưa duyệt luật/production.**

## Phần chạy trong ứng dụng

1. **Bộ đọc đối chứng theo vùng:** `vietocr_region_wide`, cùng weights VietOCR, beam search với `image_max_width=1024`, không tách dòng. Đây là cấu hình đọc khác, không phải model độc lập hoặc chứng minh hai kết quả đồng thuận là đúng. Web có nút **Đọc bằng bộ đối chứng**; đầu ra vẫn là ứng viên để đối chiếu và đưa vào draft.
2. **Tự thử đối chứng có ngân sách:** khi bộ đọc chính trả `NEEDS_REVIEW`, chỉ thử tối đa một trường bằng cấu hình đối chứng nếu còn crop budget. Tổng lượt vẫn tối đa 4 crop, tối đa 2 trường, cache/lease/2 lần thử theo revision như trước. Giữ cả primary và comparison observations; không ghi CFR. Runtime của cả hai bộ đọc được ghép vào binding trước khi nhận lượt.
3. **Bảng lặp tiêu đề/nhiều trang:** tách các vùng bảng có tiêu đề lặp trên một trang; tiếp nối cột từ trang trước chỉ khi trang hiện tại ghi rõ `Tiếp theo`/`Continued`, liên tiếp và xử lý trang thành công. Giữ block nguồn thực của trang hiện tại, item_id riêng; không coi tìm được dòng là đã đủ bảng. Trang không ghi tiếp nối không được đoán là cùng bảng. Hóa đơn nhiều nhóm thuế giữ logic từng ô hiện có; không suy thuế từ tổng tiền.
4. **Sửa lỗi timeout Windows:** Windows venv có redirector và interpreter con. Đã bổ sung dừng job có giới hạn, chờ số process giảm và retry dọn workspace trong tối đa 5 giây khi Windows chưa nhả file. Trước đó `WORKER_TIMEOUT` bị `NotADirectoryError` lúc dọn `responses.jsonl` che mất. Đã tái hiện bằng file giữ mở, rồi xác minh lại với OCR thật timeout 30 giây: trả đúng `OCRError/WORKER_TIMEOUT`, không giả thành lỗi nội dung chứng từ. Workspace cleanup không ghi đè lỗi gốc nếu OS tiếp tục giữ khóa.

## Nhánh ảnh/phát hiện chữ, có thể chạy thử riêng

- Profile beam, tiling, deskew và coverage kết hợp qua registry. Tiling có tối đa 4 ô chồng lấn, giữ box toàn trang, loại box trùng và box bị cắt ở mép trong; giới hạn thêm tối đa 200 box.
- Deskew tìm góc ±3° ở bước 0,5°, chỉ sửa nếu projection gain ≥1,20. Blank/ảnh không đủ lợi ích giữ góc 0. Lưu affine thuận/ngược; mọi polygon được đưa về raster nguồn trước khi normalizer kiểm tra bounds/area. Không đổi ảnh upload hoặc tọa độ hiển thị hóa đơn gốc.
- `CAPTURE_RENDER_DPI` hỗ trợ 150/200/300; ngân sách pixel được kiểm tra trước khi render. Thêm biến môi trường cho giới hạn trang/document pixels, không bỏ giới hạn an toàn để ép 300 DPI chạy được.
- `AGENT3_OCR_PROFILE` chỉ chọn file cấu hình nội bộ theo tên hợp lệ; không nhận model/path/config từ browser. Config, weights, code và package vẫn được pin trong runtime inventory.
- Có adapter recognition-only cho PP-OCRv6 để làm thí nghiệm cùng crop, cùng một giao thức. Bản recognizer này **chưa được chọn làm bộ đọc tên/địa chỉ trên web**.

Mở môi trường thử bằng **[OPEN_AGENT3_OCR_LAB.cmd](../../../../../OPEN_AGENT3_OCR_LAB.cmd)**: 200 DPI, profile coverage, cổng bắt đầu 8010 và DB riêng `agent3_tax_compliance/data/ocr_lab/capture.sqlite3`. Đây là cấu hình thử có thể chậm; không phải bản đã chứng minh tốt hơn. Giao diện thường vẫn mở bằng `OPEN_AGENT3.cmd` và giữ cấu hình OCR toàn trang mặc định.

## Thí nghiệm và quyết định

- **Render:** 150/200/300 DPI trên một PDF dev giữ 135 native block IDs; sai khác bbox chuẩn hóa tối đa dưới 0,001 do làm tròn pixel. 300 DPI tạo 8.702.320 pixel, vượt giới hạn trang mặc định 8M và bị từ chối đúng. Thí nghiệm render dùng trần 12M riêng; không phải bằng chứng OCR chính xác hơn. Xem [render_summary.json](render_summary.json).
- **Detector thật:** chấm độ phủ bbox so với native font spans trên một PDF dev, bao gồm bản xoay tổng hợp +2°. Đây là proxy coverage, không phải nhãn polygon độc lập hay field accuracy. Normalizer kiểm tra lại quyền sở hữu/dimensions/bounds/area. Các lượt chạy và transform ở [detection_summary.json](detection_summary.json); bản xoay cùng hóa đơn không được tính là hóa đơn mới.
- **OCR toàn trang:** baseline 150 DPI đầu tiên hoàn tất, khoảng 21 giây load + 161 giây infer trên CPU ở lượt đo đó. Beam/tiles/deskew 200 DPI chưa hoàn tất trong các lượt 240 giây, vì vậy **không promote** sang mặc định. Một lượt 30 giây sau sửa cleanup xác minh timeout đã được báo đúng. [ablation_runs.json](ablation_runs.json) giữ kết quả thất bại và giới hạn, không coi timeout là accuracy bằng 0 hay âm thầm bỏ mẫu.
- **Charset:** dictionary local PP-OCRv6 thiếu 88/134 ký tự tiếng Việt dựng sẵn được kiểm tra từ vocab VietOCR. Đây là audit nội dung cấu hình, chưa đánh giá toàn bộ tokenizer/chuỗi tổ hợp Unicode và không chứng minh chất lượng model trên mọi ngôn ngữ. Đủ lý do để chưa dùng nó thay VietOCR cho tên/địa chỉ; cần benchmark riêng. [charset_audit.json](charset_audit.json).
- **Đọc cấu hình rộng thật:** đã chạy trên một crop tên khó. Kết quả khác bộ đọc chính nhưng vẫn không khớp exact với nhãn agent; không tự chọn làm giá trị đúng. [wide_comparison.json](wide_comparison.json) chỉ công bố metadata, không công bố tên doanh nghiệp/raw OCR.
- **Extraction regression pilot:** chạy lại 15 biến thể/9 nhóm với OCR artifact đã giữ/native reader hiện tại, các nhóm field có nhãn không giảm so với round 3. [pilot_score.json](pilot_score.json). Không cộng kết quả thí nghiệm detector hoặc cấu hình rộng vào accuracy của CFR đã lưu.

Thời gian đo trên CPU này, tách load/inference; cached elapsed không phải latency sample. Thí nghiệm toàn trang PP-OCRv6 recognizer đã được dừng, không có accuracy score hợp lệ. Không công bố SLA từ các lượt này.

## Dữ liệu test mới và phần chưa thể nghiệm thu

Đã có công cụ seal manifest/hash, chặn dùng lại group/source/layout từ dev, chặn đường dẫn ngoài workspace và kiểm tra input không đổi sau khi khóa. Manifest hiện là **PENDING_UNSEEN_DATA**, không phải tập holdout đã đạt yêu cầu. Không chia lại pilot từng dùng sửa code rồi gọi là test mới. Xem [holdout_status.json](holdout_status.json).

Cần hóa đơn thuộc nguồn/bố cục mới và nhãn đủ trường/ô bảng để chấm. Việc coder tự đối chiếu trên UI vẫn dùng được cho kiểm thử kỹ thuật, nhưng không tạo ra nhãn độc lập hay khoảng tin cậy với mẫu lớn. Chưa có bằng chứng đạt mục tiêu 98%/95% ngoài pilot hoặc đọc đủ mọi trường trên mọi ảnh; ảnh mất chữ và trường không in không thể được phục hồi bằng đoán.

## Kiểm thử, chạy lại và rollback

[validation_summary.json](validation_summary.json) ghi hồi quy Python/Chrome/JavaScript; [lab_startup.json](lab_startup.json) ghi smoke cấu hình/HTTP trên DB tách biệt. Các test mới gồm affine/blank/góc nghiêng/giới hạn pixel, tile offset/trùng/mép cắt/budget, lựa chọn profile không nhận path tùy ý, bảng lặp/tiếp nối và không đoán trang khác, cached comparison, fallback không vượt crop budget, holdout leakage/tamper và lỗi file lock Windows. Worker có 5 test recognition crops qua riêng trong môi trường OCR.

**Kết quả cuối: 504 test Python của app, 57 nhóm kiểm tra Chrome, 9 kiểm tra JavaScript đều qua; thêm 5 test worker crops và 4 kiểm tra smoke lab qua riêng.** Lượt cuối chạy lại toàn bộ sau khi chốt mã nguồn. Các lỗi timeout/cleanup và thử nghiệm chưa đạt ở trên được giữ trong báo cáo, không dùng số test phần mềm làm accuracy OCR.

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_ocr_coverage.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/benchmark_render_geometry.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/benchmark_detection_coverage.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/benchmark_ocr_coverage.py --variant beam200 --case charity_2023-p1 --timeout 240
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/audit_ocr_models.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/prepare_ocr_holdout.py
```

Raw responses, PDF/ảnh, DB, crops, tracebacks và nhãn có giá trị chứng từ giữ local trong thư mục gitignore. Muốn rollback thí nghiệm: dừng lab và mở `OPEN_AGENT3.cmd`; chưa thay pointer mặc định hoặc rewrite hồ sơ cũ.

API nhận dạng đối chứng tham khảo [tài liệu TextRecognition chính thức của PaddleOCR](https://www.paddleocr.ai/main/version3.x/module_usage/text_recognition.html). Khả năng API của nhà phát triển không được dùng thay kết quả benchmark của dự án.
