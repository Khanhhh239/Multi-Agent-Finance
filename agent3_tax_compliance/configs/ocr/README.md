# Chọn và bổ sung OCR engine

Mặc định ứng dụng: **PP-OCRv6 detector + VietOCR vgg_transformer**, CPU. Điểm chọn duy nhất là [default.json](default.json), trỏ tới [ppocrv6_vietocr.json](ppocrv6_vietocr.json). `OCRBridge(settings)` và CLI không có `--config` đều đọc điểm chọn này. Các default Tesseract trong wire model `OCRConfig`/`OCRBridgeRequest` được giữ để đọc hợp đồng cũ; không phải lựa chọn mặc định của ứng dụng.

Có hai lớp cấu hình:

| Lớp | Nội dung | Ví dụ |
|---|---|---|
| Run config | model_id, config version, timeout/RAM/retry, tuning parameters | `ppocrv6_vietocr.json` |
| Engine profile | benchmark adapter, interpreter/env riêng, dependencies, model assets, environment flags, path parameters, process limit | `engines/ppocrv6_vietocr.json` |

Ứng dụng không import Paddle/Torch/VietOCR hoặc benchmark `src`. Worker dùng factory `create_adapter` của benchmark. Mọi engine trả cùng OCRResult 1.1, qua correlation → normalizer → layout merge → normalized document; PLAN_04 chỉ phụ thuộc hợp đồng này.

## Đổi sang engine đã đăng ký

1. Tạo run config có `model_id` đúng với engine profile, `version` mới và resource budget phù hợp.
2. Trỏ `default.json` tới run config đó, hoặc truyền `--config` cho một lần chạy riêng.
3. Chạy `scripts/smoke_ocr_engine.py --config <path>` từ workspace root, sau đó kiểm tra normalization/evidence trên tập cần hỗ trợ.

Ví dụ Tesseract đã có run config riêng `tesseract_psm3.json`. Profile cho `ppocrv6_medium` và `easyocr` cũng có sẵn nhưng **chưa nghiệm thu inference qua bridge mới**; không coi việc có profile là đã hỗ trợ production. Không fallback tự động khi engine lỗi.

## Bổ sung engine mới

1. Chuẩn bị interpreter riêng và model local trong benchmark. Không cài chung framework vào app env.
2. Nếu benchmark đã có adapter tương ứng, chỉ thêm `engines/<model_id>.json` và run config. Nếu chưa, hiện thực một `BaseAdapter` và đăng ký trong benchmark factory; không sửa bridge/normalizer/CFR.
3. Khai báo tất cả trọng số, model definitions và adapter source files trong `assets`/`source_files` để fingerprint/cache đổi khi model thay đổi. Khai báo distributions để ghi runtime versions; kiểm tra môi trường trước chạy.
4. `path_parameters` là các khóa dotted trong adapter_config, được resolve tương đối từ benchmark root. Đường dẫn thoát root bị từ chối. Runtime paths và environment chỉ lấy từ trusted profile.
5. `parameters` chỉ chấp nhận tên có trong `adapter_config.application_parameters` của profile. Các profile hiện tại chưa mở tuning parameters. `psm`/`language` là trường tương thích riêng cho Tesseract; engine khác bỏ qua chúng.
6. Dùng geometry trên raster đầu vào. Nếu engine tự xoay/resize, adapter phải map polygon về raster gốc trước trả kết quả. Profile hybrid hiện tắt orientation classifier; PLAN_02 cung cấp PDF rotation/EXIF transform.
7. Chạy smoke thật và contract/recovery tests, ghi provenance/budget/limitations. Full-page text không có box phải là geometry UNAVAILABLE.

Runtime fingerprint gồm profile, model files, adapter source, package metadata/RECORD và versions; cache key còn gồm full run config, page artifact/hash và bridge implementation. Các thư viện framework lớn không được hash toàn bộ mỗi lần chạy; isolation/integrity hardening đầy đủ thuộc PLAN_14. Result cũ bất biến và vẫn giữ model/config provenance riêng.

VietOCR adapter hiện không trả recognizer confidence. Score từ PP-OCRv6 là **DETECTION**, không phải độ đúng của text; `score_semantics=ENGINE_HEURISTIC_NOT_CALIBRATED`. Không dùng trực tiếp cho field acceptance.
