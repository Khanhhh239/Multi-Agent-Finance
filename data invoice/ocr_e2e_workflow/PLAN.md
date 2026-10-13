# Kế hoạch đánh giá OCR end-to-end cho Agent 3

## 0. Quy tắc bắt buộc về phạm vi làm việc

Thư mục gốc của toàn bộ workflow là:

```text
D:\financial\data invoice\ocr_e2e_workflow
```

Mọi mã nguồn, môi trường Python, manifest, cấu hình, model tải về, cache, log, dự đoán, metric, hình minh họa và báo cáo sinh ra trong quá trình đánh giá **phải nằm trong thư mục này**.

Dữ liệu gốc bên ngoài workflow chỉ được đọc, không được đổi tên, sửa, di chuyển hoặc ghi đè:

```text
../mcocr_train_df.csv
../text_recognition_train_data.txt
../text_recognition_val_data.txt
../text_recognition_mcocr_data/
../train_images/train_images/
../dataset/text_detector/txt/
../kie_data/kie_data/
```

Không dùng trực tiếp thư mục gốc để lưu kết quả chạy thử. Mỗi lần chạy phải tạo một `run_id` riêng dưới `runs/`. Không đưa ảnh, nhãn hoặc dự đoán của tập test vào mã hậu xử lý theo cách thủ công.

Các ngoại lệ là phần mềm hệ thống đã có sẵn, chẳng hạn driver CUDA. Nếu dùng ngoại lệ, phải ghi phiên bản và đường dẫn vào metadata của lần chạy.

## 1. Phạm vi end-to-end cần đánh giá

Trong workflow này, “end-to-end” được định nghĩa là:

```text
Ảnh hóa đơn đầy đủ
    -> phát hiện vùng chữ
    -> nhận dạng chữ
    -> chuẩn hóa kết quả
    -> trích xuất bốn trường nghiệp vụ
    -> JSON đầu vào chuẩn hóa cho Agent 3
```

Bốn trường có nhãn trong bộ dữ liệu hiện tại:

- `SELLER`: tên người bán.
- `ADDRESS`: địa chỉ người bán.
- `TIMESTAMP`: ngày giờ giao dịch.
- `TOTAL_COST`: tổng tiền/thành tiền cần quan tâm.

Workflow này chưa đánh giá toàn bộ kết luận thuế của Agent 3. GoRules ZEN, RAG và LLM Explainer chỉ có thể được đánh giá end-to-end sau khi có ground truth cho kết luận thuế. Đầu ra hiện tại dừng ở `Canonical Invoice JSON`, là đầu vào của lớp chuẩn hóa giao dịch.

Phải tách ba bài kiểm tra để tránh diễn giải sai kết quả:

1. **Text detection:** ảnh đầy đủ -> polygon vùng chữ. Ground truth lấy từ `kie_data/kie_data/boxes_and_transcripts`; polygon được scale từ ảnh KIE sang kích thước ảnh đầu vào chuẩn.
2. **Text recognition:** crop chữ chuẩn -> chuỗi ký tự. Ground truth lấy từ `text_recognition_val_data.txt`.
3. **Business end-to-end:** ảnh đầy đủ -> bốn trường nghiệp vụ. Ground truth lấy từ `mcocr_train_df.csv` trên danh sách hóa đơn test đã khóa.

Không gọi bài kiểm tra thứ ba là “độ chính xác toàn bộ văn bản trên hóa đơn”, vì CSV chỉ gán nhãn các trường nghiệp vụ. File KIE có nhiều transcript trống, do đó không đủ sạch để làm ground truth nhận dạng toàn trang nếu chưa được kiểm tra và sửa nhãn.

## 2. Câu hỏi benchmark phải trả lời

Benchmark phải cho biết:

1. Model nào phát hiện vùng chữ tốt nhất trên hóa đơn thực tế?
2. Model nào nhận dạng tiếng Việt tốt nhất khi crop chữ đã đúng?
3. Pipeline nào lấy đúng `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST` từ ảnh đầy đủ?
4. Lỗi xuất phát từ detector, recognizer hay bộ hậu xử lý?
5. Model nào đạt độ chính xác nghiệp vụ tốt nhất trong giới hạn tốc độ và tài nguyên triển khai?
6. Mức độ suy giảm theo chất lượng ảnh (`anno_image_quality`) là bao nhiêu?
7. Kết quả có ổn định khi chạy lại với cùng cấu hình hay không?

Ưu tiên chọn model cho Agent 3 theo thứ tự:

1. `TOTAL_COST` numeric exact match.
2. `TIMESTAMP` normalized exact match.
3. `SELLER` normalized exact match.
4. Recall của các trường nghiệp vụ.
5. Detection F1 và CER/WER.
6. Độ trễ, RAM/VRAM và độ phức tạp triển khai.

Không chọn model chỉ vì CER trung bình thấp nếu model thường đọc sai tổng tiền hoặc ngày giao dịch.

## 3. Cấu trúc thư mục workflow

Khi bắt đầu triển khai, tạo đúng cấu trúc sau bên trong `ocr_e2e_workflow`:

```text
ocr_e2e_workflow/
├── PLAN.md
├── README.md
├── .gitignore
├── envs/
│   ├── evaluator/
│   └── <model_id>/
├── requirements/
│   ├── evaluator.txt
│   ├── easyocr.txt
│   ├── ppocrv6.txt
│   ├── paddleocr_vl.txt
│   ├── tesseract.txt
│   ├── vietocr.txt
│   ├── surya.txt
│   ├── glm_ocr.txt
│   └── optional_vlms.txt
├── configs/
│   ├── benchmark.yaml
│   ├── normalization.yaml
│   ├── field_extraction.yaml
│   └── models/
│       ├── easyocr.yaml
│       ├── ppocrv6_medium.yaml
│       ├── ppocrv6_vietocr.yaml
│       ├── paddleocr_vl_1_6.yaml
│       ├── tesseract.yaml
│       ├── vietocr.yaml
│       ├── surya_ocr_2.yaml
│       ├── glm_ocr.yaml
│       ├── hunyuan_ocr_1_5.yaml
│       ├── chandra_ocr_2.yaml
│       └── dots_mocr.yaml
├── data/
│   ├── manifests/
│   │   ├── source_inventory.json
│   │   ├── recognition_train.jsonl
│   │   ├── recognition_test.jsonl
│   │   ├── full_image_dev.jsonl
│   │   └── full_image_test.jsonl
│   ├── ground_truth/
│   │   ├── detection/
│   │   ├── fields/
│   │   └── validation_report.json
│   └── samples/
├── src/
│   ├── __init__.py
│   ├── cli.py
│   ├── contracts.py
│   ├── prepare/
│   │   ├── inventory.py
│   │   ├── build_splits.py
│   │   ├── build_detection_gt.py
│   │   ├── build_field_gt.py
│   │   └── validate_data.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── easyocr_adapter.py
│   │   ├── ppocrv6_adapter.py
│   │   ├── paddleocr_vl_adapter.py
│   │   ├── tesseract_adapter.py
│   │   ├── vietocr_adapter.py
│   │   ├── surya_adapter.py
│   │   ├── glm_ocr_adapter.py
│   │   ├── hunyuan_ocr_adapter.py
│   │   ├── chandra_adapter.py
│   │   └── dots_mocr_adapter.py
│   ├── postprocess/
│   │   ├── text_normalizer.py
│   │   ├── reading_order.py
│   │   ├── timestamp_parser.py
│   │   ├── money_parser.py
│   │   └── field_extractor.py
│   ├── metrics/
│   │   ├── detection.py
│   │   ├── recognition.py
│   │   ├── text_spotting.py
│   │   ├── fields.py
│   │   ├── hallucination.py
│   │   ├── performance.py
│   │   └── confidence_interval.py
│   └── reporting/
│       ├── aggregate.py
│       ├── error_analysis.py
│       └── render_report.py
├── tests/
│   ├── test_manifest.py
│   ├── test_normalization.py
│   ├── test_matching.py
│   ├── test_vietnamese_charset.py
│   ├── test_money_parser.py
│   └── test_timestamp_parser.py
├── artifacts/
│   ├── models/
│   └── cache/
├── runs/
└── reports/
    ├── figures/
    ├── leaderboard_pipeline.csv
    ├── leaderboard_vlm.csv
    └── FINAL_REPORT.md
```

Ảnh gốc không cần sao chép vào workflow vì tốn dung lượng. Manifest lưu đường dẫn tương đối, kích thước file và checksum để bảo đảm đúng dữ liệu. Nếu phải tạo ảnh trung gian, chỉ ghi vào `runs/<run_id>/intermediate/`.

Các biến cache phải trỏ vào workflow, ví dụ:

```powershell
$env:HF_HOME = "$PWD\artifacts\cache\huggingface"
$env:TORCH_HOME = "$PWD\artifacts\cache\torch"
$env:PIP_CACHE_DIR = "$PWD\artifacts\cache\pip"
$env:PYTHONUTF8 = "1"
```

Adapter EasyOCR phải truyền `model_storage_directory` vào `artifacts/models/easyocr`. Các adapter khác cũng phải nhận model directory từ config, không tự tải model vào thư mục người dùng.

## 4. Phân rã công việc chi tiết

### WF-01 — Khởi tạo và khóa phạm vi workflow

**Việc làm**

- Tạo cấu trúc thư mục ở Mục 3.
- Tạo môi trường `envs/evaluator` cho evaluator và môi trường riêng `envs/<model_id>` cho adapter khi thư viện xung đột phiên bản. Tất cả môi trường vẫn nằm trong workflow.
- Tạo `README.md` ghi lệnh cài đặt, chuẩn bị dữ liệu, chạy model và tổng hợp kết quả.
- Tạo `.gitignore` cho `envs`, model, cache, dữ liệu trung gian và kết quả lớn.
- Chốt seed cho Python, NumPy, PyTorch và các model hỗ trợ seed.
- Lưu phiên bản Python, hệ điều hành, CPU, GPU, CUDA, thư viện vào mỗi lần chạy.

**Đầu ra**

- Workflow chạy được từ chính thư mục này.
- Không phát sinh cache/model/result ở thư mục gốc `data invoice`.

**Tiêu chí hoàn thành**

- Chạy kiểm tra filesystem và xác nhận không có file mới ngoài `ocr_e2e_workflow`.
- Môi trường có thể tái tạo từ các file requirements đã khóa phiên bản và model revision/commit.

### WF-02 — Kiểm kê và kiểm tra dữ liệu nguồn

**Việc làm**

- Đọc ba nguồn nhãn chính: recognition list, detection polygon và CSV trường nghiệp vụ.
- Kiểm tra mọi đường dẫn ảnh có tồn tại.
- Ghi SHA-256, kích thước ảnh, width/height, số polygon, số field vào `source_inventory.json`.
- Phát hiện ảnh trùng checksum, nhãn trùng, nhãn rỗng và đường dẫn không tồn tại.
- Đọc file bằng UTF-8 trực tiếp; không dùng chuỗi đã bị mojibake do terminal làm ground truth.
- Chuẩn hóa lỗi nhãn `TOTAL_TOTAL_COST` thành `TOTAL_COST` trong bản ground truth dẫn xuất. Không sửa CSV gốc.
- Thống kê các file KIE thiếu và transcript rỗng. Chỉ dùng chúng cho phân tích phụ nếu đã xác minh.

**Đầu ra**

- `data/manifests/source_inventory.json`.
- `data/ground_truth/validation_report.json`.
- Bảng thống kê số ảnh, crop, polygon và field theo nhãn.

**Tiêu chí hoàn thành**

- Mọi lỗi dữ liệu đều được liệt kê bằng `image_id`.
- Không âm thầm loại mẫu; mỗi mẫu bị loại phải có `exclusion_reason`.

### WF-03 — Tạo và khóa tập dev/test

Tập test phải được suy ra từ `text_recognition_val_data.txt`:

```text
mcocr_public_145014ftvdj_4.jpg
    -> bỏ hậu tố _4
    -> mcocr_public_145014ftvdj.jpg
```

Theo kiểm kê hiện tại, tập recognition validation có 1.300 crop thuộc khoảng 231 hóa đơn nguồn. Con số cuối cùng phải được script xác nhận, không hard-code vào evaluator.

**Việc làm**

- Parse từng dòng bằng cách tách tại tab đầu tiên để giữ nguyên text chứa khoảng trắng.
- Dùng regex chỉ bỏ hậu tố chỉ số crop cuối tên file.
- Loại trùng nhưng giữ thứ tự ổn định.
- Ánh xạ source ID sang ảnh trong `train_images/train_images`.
- Tạo `full_image_test.jsonl` cho các hóa đơn nguồn của recognition validation.
- Các hóa đơn còn lại tạo `full_image_dev.jsonl`.
- Kiểm tra giao nhau giữa dev/test bằng cả `image_id` và checksum; yêu cầu bằng 0.
- Khóa manifest bằng checksum và không thay đổi sau khi benchmark chính thức bắt đầu.

**Đầu ra**

- `recognition_train.jsonl` và `recognition_test.jsonl`.
- `full_image_dev.jsonl` và `full_image_test.jsonl`.
- Báo cáo leakage và checksum của bốn manifest.

**Tiêu chí hoàn thành**

- Không có source receipt xuất hiện ở cả dev và test.
- 100% ảnh test tồn tại và mở được.
- Việc điều chỉnh hậu xử lý chỉ dùng dev; không xem kết quả test để sửa luật rồi chạy lại như một thử nghiệm độc lập.

### WF-04 — Xây ground truth thống nhất

**Detection ground truth**

- Parse mỗi dòng trong `kie_data/kie_data/boxes_and_transcripts` thành polygon bốn điểm. Các nhãn này khớp với ảnh sạch trong `kie_data/kie_data/images`; tọa độ phải được scale sang ảnh đầy đủ trong manifest trước khi chấm.
- Giữ `dataset/text_detector/txt` để kiểm tra trực quan dữ liệu rectified/red-overlay, không dùng làm ground truth cho ảnh đầu vào gốc.
- Tách transcript và nhãn ở cuối dòng một cách có kiểm soát, kể cả khi transcript chứa dấu phẩy.
- Kiểm tra polygon nằm trong biên ảnh, không tự cắt và có diện tích dương.
- Detection GT dùng polygon cho metric detector. Transcript KIE chỉ phục vụ phân tích phụ vì còn ô rỗng/sai và chưa đủ sạch để chấm nhận dạng toàn trang.

**Recognition ground truth**

- Dùng đúng 1.300 cặp crop–text của file validation sau khi script xác nhận.
- Lưu cả `text_raw` và `text_normalized`.
- Không dùng crop augmentation ở `data0_or_180` hay `data0.7` làm test độc lập.

**Field ground truth**

- Parse `anno_polygons`, `anno_texts`, `anno_labels` an toàn bằng `ast.literal_eval` và phép tách `|||`.
- Bảo toàn từng field instance; không ghép trước khi đánh giá box-level.
- Lưu `anno_image_quality` để phân tích theo chất lượng ảnh.
- Với nhiều `ADDRESS` hoặc `TOTAL_COST`, lưu danh sách theo thứ tự đọc và thêm một tầng canonical business value riêng.
- Canonical value của `TIMESTAMP` và `TOTAL_COST` phải được tạo bằng parser xác định, sau đó xuất danh sách lỗi để kiểm tra thủ công trên dev.

**Tiêu chí hoàn thành**

- Số polygon, text và label khớp nhau trên từng ảnh.
- Không có nhãn ngoài schema sau khi ánh xạ lỗi đánh máy đã biết.
- Ground truth dẫn xuất giữ liên kết tới file và dòng nguồn để audit.

### WF-05 — Định nghĩa hợp đồng adapter chung

Mọi model phải trả cùng một JSON, không để evaluator gọi API riêng của từng thư viện. Contract phải chứa được cả pipeline detector–recognizer và OCR VLM sinh văn bản toàn trang:

```json
{
  "schema_version": "1.1",
  "run_id": "20260922_easyocr_v1",
  "model_id": "easyocr",
  "output_mode": "boxes_and_text",
  "image_id": "mcocr_public_xxx.jpg",
  "image_width": 768,
  "image_height": 1024,
  "load_time_ms": 1250.0,
  "inference_time_ms": 420.0,
  "document_text_raw": "Tổng tiền: 150.000đ",
  "structured_blocks": [],
  "detections": [
    {
      "polygon": [[10, 10], [100, 10], [100, 30], [10, 30]],
      "text_raw": "Tổng tiền: 150.000đ",
      "confidence": 0.93
    }
  ],
  "error": null
}
```

**Quy tắc**

- Tọa độ dùng pixel của ảnh gốc, không dùng tọa độ ảnh resize.
- Polygon theo cùng chiều và cùng quy ước ở mọi adapter.
- `output_mode` nhận một trong ba giá trị: `boxes_and_text`, `full_page_text`, `structured_document`.
- OCR VLM không trả tọa độ phải ghi `detections: []`, giữ output trong `document_text_raw`/`structured_blocks`, và nhận metric detection là `N/A`. Không suy diễn polygon giả từ Markdown hoặc thứ tự dòng.
- Confidence nằm trong `[0, 1]`; nếu model không có confidence thì ghi `null`.
- Đo `load_time_ms` riêng với `inference_time_ms`.
- Một ảnh lỗi vẫn phải có record với trường `error`; không được bỏ qua.
- Lưu output thô trước mọi chuẩn hóa vào `runs/<run_id>/predictions/raw.jsonl`.

### WF-06 — Bộ chuẩn hóa dùng chung

Tạo hai chế độ đánh giá:

1. **Strict:** so sánh chuỗi Unicode sau khi trim khoảng trắng đầu/cuối.
2. **Normalized:** NFC Unicode, chuẩn hóa khoảng trắng, dấu câu được cấu hình và quy tắc đơn vị tiền tệ.

Không xóa dấu tiếng Việt trong metric chính. Có thể báo thêm metric accent-insensitive để chẩn đoán, nhưng không dùng nó thay cho CER/WER chính.

Chuẩn hóa phải là hàm dùng chung cho mọi model. Các thay đổi đối với `normalization.yaml` phải được version hóa và chốt trước lần chạy test cuối.

### WF-07 — Cài baseline và các model SOTA

Danh sách được chia theo mức ưu tiên để workflow vẫn hoàn thành được trên GPU Kaggle phổ thông.

**Nhóm bắt buộc — baseline và pipeline thực dụng**

| Model ID | Detection | Recognition | Output chính | Vai trò |
|---|---|---|---|---|
| `tesseract` | Tesseract | Tesseract | Box + text | Baseline CPU truyền thống |
| `easyocr` | EasyOCR | EasyOCR | Polygon + text + confidence | Baseline nhẹ, dễ tích hợp |
| `ppocrv6_medium` | PP-OCRv6 Medium | PP-OCRv6 Medium | Polygon + text + confidence | Pipeline OCR hiện đại, hỗ trợ tiếng Việt |
| `ppocrv6_vietocr` | PP-OCRv6 Medium | VietOCR | Polygon + text | Detector mới kết hợp recognizer chuyên tiếng Việt |

**Nhóm bắt buộc — OCR VLM/document parser**

| Model ID | Quy mô tham chiếu | Output chính | Vai trò |
|---|---:|---|---|
| `paddleocr_vl_1_6` | khoảng 0.9B | Text spotting/tài liệu có cấu trúc | Ứng viên document parser chính của PaddleOCR |
| `surya_ocr_2` | khoảng 650M | Full-page OCR, layout, reading order và detection | Ứng viên nhỏ, có công bố đánh giá tiếng Việt |
| `glm_ocr` | khoảng 0.9B | Markdown/JSON có cấu trúc | Ứng viên OCR VLM gọn cho tài liệu phức tạp |

**Nhóm mở rộng — chỉ chạy khi còn GPU và thời gian**

| Model ID | Quy mô tham chiếu | Lý do để thử | Điều kiện |
|---|---:|---|---|
| `hunyuan_ocr_1_5` | lightweight OCR VLM | Kiểm tra OCR end-to-end đa ngôn ngữ và hallucination | Ghi rõ license và backend |
| `chandra_ocr_2` | khoảng 4B | Mạnh về layout, form, bảng và OCR đa ngôn ngữ | Cần nhiều VRAM hơn; kiểm tra license weight |
| `dots_mocr` | khoảng 3B | Document parsing và reading order mạnh | Chưa có bằng chứng riêng đủ mạnh cho tiếng Việt |

TrOCR không còn nằm trong benchmark chính. Chỉ giữ như baseline lịch sử nếu còn tài nguyên; ưu tiên GPU cho các model OCR/document parser mới ở trên.

Mỗi model có config riêng gồm model name, revision/commit, weight checksum, ngôn ngữ, prompt, kích thước ảnh, threshold, device, dtype/quantization, decoding parameters, backend và đường dẫn weight. Với model sinh văn bản, cố định `temperature=0` hoặc chế độ deterministic tương đương nếu backend hỗ trợ.

Phải chạy ba nhóm thí nghiệm:

1. **Full pipeline có tọa độ:** detector và recognizer gốc của EasyOCR/PP-OCRv6. Nhóm này được chấm detection, recognition, text spotting và field extraction.
2. **Shared detector:** dùng polygon GT hoặc cùng detector để so sánh PP-OCRv6 recognition với VietOCR một cách công bằng. Recognition crop benchmark là phép so sánh chính.
3. **OCR VLM toàn trang:** dùng nguyên ảnh và prompt đã khóa. Nhóm này được chấm field accuracy, recognition trên phần có ground truth, reading order, omission, insertion/hallucination chẩn đoán và hiệu năng. Detection là `N/A` nếu model không trả tọa độ thật.

#### Smoke test tiếng Việt trước benchmark

Trước khi chạy toàn bộ dữ liệu, tạo fixture trong `tests/fixtures/` chứa:

```text
ă â ê ô ơ ư – Ă Â Ê Ô Ơ Ư
ấ ầ ẩ ẫ ậ – ớ ờ ở ỡ ợ – ứ ừ ử ữ ự
Tổng tiền: 1.234.567đ – Thời gian: 15/08/2020 10:44
```

Mọi recognizer phải chạy fixture này và lưu CER cùng danh sách ký tự không thể phát ra. PP-OCRv6 phải ghi cả checksum dictionary vì đã từng có báo cáo dictionary thiếu ký tự tiếng Việt có dấu. Smoke test chỉ phát hiện lỗi charset/cấu hình; không thay thế benchmark trên hóa đơn thật.

Nguồn phiên bản tham chiếu khi khóa model:

- [PP-OCRv6 và danh sách ngôn ngữ](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md).
- [Báo cáo ký tự tiếng Việt của PP-OCRv6](https://github.com/PaddlePaddle/PaddleOCR/issues/18254).
- [PaddleOCR-VL-1.6](https://github.com/PaddlePaddle/PaddleOCR).
- [Surya OCR 2](https://github.com/datalab-to/surya).
- [GLM-OCR](https://github.com/zai-org/GLM-OCR).
- [HunyuanOCR-1.5](https://github.com/Tencent-Hunyuan/HunyuanOCR).
- [Chandra OCR 2](https://github.com/datalab-to/chandra).
- [dots.mocr](https://github.com/rednote-hilab/dots.mocr).

Không fine-tune trên tập test. Nếu fine-tune model, tạo run riêng, ghi rõ dữ liệu huấn luyện và luôn giữ baseline pretrained để so sánh. Các tuyên bố SOTA từ nguồn model chỉ dùng để chọn ứng viên; quyết định cho Agent 3 phải dựa trên benchmark hóa đơn tiếng Việt trong workflow này.

### WF-08 — Metric phát hiện vùng chữ

Ghép prediction với ground truth bằng polygon IoU và thuật toán matching một-một; không để nhiều prediction cùng ăn một ground truth.

Báo cáo:

- Precision, Recall, F1 tại IoU `0.50` là metric chính.
- Precision, Recall, F1 tại IoU `0.30` và `0.70` để phân tích độ nhạy.
- Số false positive, false negative và polygon không hợp lệ.
- Kết quả micro trung bình toàn bộ box và macro trung bình theo ảnh.

Chạy trên detection GT toàn trang. Vì detection GT không có transcript, không tính CER/WER từ nguồn này.

### WF-09 — Metric nhận dạng chữ

Chạy trực tiếp trên crop chuẩn của recognition test để tách lỗi recognizer khỏi detector.

Với OCR VLM, dùng cùng crop và một prompt cố định dạng “chép nguyên văn nội dung nhìn thấy, không giải thích”. Nếu model/backend không hỗ trợ crop recognition độc lập, ghi metric recognition là `N/A` và nêu rõ trong báo cáo; không tự ghép kết quả toàn trang để tạo điểm crop giả.

Báo cáo cả strict và normalized:

- Character Error Rate (CER).
- Word Error Rate (WER).
- Exact Match (EM).
- Normalized Edit Similarity: `1 - edit_distance / max(len(gt), len(pred))`.
- Tỷ lệ crop lỗi/không trả kết quả.
- CER theo độ dài text và theo nhóm ký tự có dấu, số, ngày giờ, tiền tệ.

CER/WER phải được tính bằng tổng edit distance chia tổng độ dài tham chiếu, đồng thời báo macro trung bình theo crop để thấy ảnh hưởng của chuỗi ngắn.

### WF-10 — Metric text spotting end-to-end

Một prediction được tính đúng khi:

- polygon match ground truth tại IoU `>= 0.50`; và
- text đạt điều kiện tương ứng.

Báo cáo hai mức:

- **E2E Exact F1:** text normalized exact match.
- **E2E Soft F1:** normalized edit similarity `>= 0.80`.

Text spotting toàn trang chỉ được tính nếu ground truth có transcript đầy đủ và đã được kiểm định. Với dữ liệu hiện tại, metric text spotting chính áp dụng cho các polygon field trong `mcocr_train_df.csv`; kết quả phải ghi tên là **key-field text spotting**, không phải full-page transcription.

Chỉ model trả polygon/bbox thật mới được xếp hạng text spotting. Model chỉ trả Markdown/HTML/plain text nhận `N/A` ở metric IoU và text spotting.

### WF-11 — Trích xuất trường nghiệp vụ

Xây một bộ hậu xử lý chung, dùng cùng output OCR cho mọi model. Đây là chế độ đánh giá chính để đo chất lượng OCR mà không cho từng model dùng luật trích xuất riêng:

1. Sắp xếp box theo reading order.
2. Tìm keyword và ứng viên theo khoảng cách hình học.
3. Ghép dòng cho `SELLER` và `ADDRESS`.
4. Parse nhiều định dạng ngày giờ cho `TIMESTAMP`.
5. Parse dấu chấm/phẩy, ký hiệu tiền và chữ `đ` cho `TOTAL_COST`.
6. Nếu có nhiều tổng tiền, chấm điểm theo keyword như “tổng thanh toán”, “phải trả”, vị trí và giá trị; không dùng ground truth khi chọn ứng viên.
7. Trả về confidence, evidence box IDs và lý do chọn.

Đầu ra chuẩn:

```json
{
  "image_id": "mcocr_public_xxx.jpg",
  "seller": {"value": "...", "confidence": 0.91, "evidence_ids": [1]},
  "address": {"value": "...", "confidence": 0.82, "evidence_ids": [2, 3]},
  "timestamp": {"value": "2020-08-15T10:44:08", "confidence": 0.88, "evidence_ids": [4]},
  "total_cost": {"value": 150000, "currency": "VND", "confidence": 0.95, "evidence_ids": [5]},
  "missing_fields": []
}
```

Báo cáo:

- `SELLER`: normalized EM, CER và recall.
- `ADDRESS`: CER, normalized edit similarity và recall.
- `TIMESTAMP`: canonical exact match, date-only accuracy và parse failure rate.
- `TOTAL_COST`: numeric exact match, recall và parse failure rate.
- Field micro/macro F1 ở mức instance nếu đánh giá polygon + label.
- Tỷ lệ hóa đơn đủ cả bốn trường.

Với `TOTAL_COST`, numeric exact match là metric chính. Sai khác một chữ số được tính sai; metric tolerance chỉ được báo bổ sung để phân tích.

Đối với OCR VLM có khả năng trả JSON trực tiếp, chạy thêm một chế độ phụ `direct_structured_extraction` với prompt/schema đã khóa. Kết quả này nằm ở bảng riêng và không thay thế chế độ hậu xử lý chung. Phải lưu nguyên prompt, raw response, số lần JSON parse thất bại và field không có bằng chứng trong ảnh.

#### Metric omission và hallucination chẩn đoán

Do chưa có transcript đầy đủ toàn trang, không được công bố “hallucination rate toàn ảnh” như một metric chính. Chỉ báo các đại lượng có ground truth hoặc kiểm chứng được:

- Levenshtein insertion rate trên 1.300 crop recognition.
- Tỷ lệ model sinh text trên fixture trắng/gần trắng.
- Tỷ lệ field dự đoán sai và không có chuỗi bằng chứng tương ứng trong output OCR.
- Tỷ lệ VLM trả lời giải thích, Markdown thừa hoặc giá trị ngoài JSON schema khi prompt yêu cầu structured output.
- Danh sách mẫu nghi ngờ hallucination để kiểm tra thủ công, không gộp vào một tỷ lệ toàn trang nếu ground truth chưa đầy đủ.

### WF-12 — Đo hiệu năng triển khai

Mỗi cấu hình cần:

- 5–10 ảnh warm-up trước khi đo.
- Đo model load time một lần.
- Đo latency từng ảnh và báo mean, median, p90, p95, p99.
- Đo throughput ảnh/phút với batch size được ghi rõ.
- Ghi peak RAM và VRAM.
- Ghi kích thước model trên đĩa.
- Ghi CPU/GPU, số thread, precision và kích thước đầu vào.
- Với VLM, ghi thêm input/output token count, max tokens, backend, quantization và thời gian decode.
- Chạy ít nhất hai lần để kiểm tra độ ổn định; nếu kết quả chênh đáng kể thì chạy lần thứ ba.

Không so latency CPU của model này với GPU của model khác trong cùng cột. Leaderboard phải tách theo hardware/device.

### WF-13 — Phân tích lỗi

Sinh các danh sách và ảnh overlay trong `reports/figures`:

- 20 mẫu CER cao nhất.
- 20 mẫu `TOTAL_COST` sai.
- 20 mẫu `TIMESTAMP` sai hoặc parse thất bại.
- False negative detector có diện tích lớn.
- False positive detector có confidence cao.
- Mẫu khác nhau giữa strict và normalized.
- Crop có insertion rate cao và ảnh trắng vẫn sinh text.
- Field do VLM sinh ra nhưng không có evidence trong output OCR.
- Kết quả theo các nhóm `anno_image_quality`.
- Lỗi do xoay ảnh, mờ, tương phản thấp, chữ nhỏ, dấu tiếng Việt, bố cục nhiều cột và nền nhiễu.

Mỗi lỗi cần gắn nhãn nguyên nhân ở mức:

```text
DETECTION / RECOGNITION / READING_ORDER / FIELD_SELECTION /
NORMALIZATION / HALLUCINATION / OMISSION / GT_QUALITY / UNSUPPORTED_FORMAT
```

Không sửa model theo một lỗi test riêng lẻ. Lỗi test chỉ dùng để kết luận; thay đổi thuật toán phải được phát triển trên dev rồi thực hiện một lần đánh giá test cuối có version mới.

### WF-14 — Báo cáo và lựa chọn model

Không gộp tất cả model vào một thứ hạng duy nhất khi chúng không hỗ trợ cùng output. Tạo hai bảng:

- `leaderboard_pipeline.csv`: các model có polygon/bbox thật, chấm đủ detection và text spotting.
- `leaderboard_vlm.csv`: các OCR VLM/document parser, tập trung vào field accuracy, recognition có ground truth, omission/insertion và hiệu năng.

Hai bảng tối thiểu có các cột phù hợp sau:

```text
model_id, model_revision, run_id, output_mode, location_support, device,
detection_precision_50, detection_recall_50, detection_f1_50,
recognition_cer, recognition_wer, recognition_em,
key_field_e2e_exact_f1, key_field_e2e_soft_f1,
seller_em, address_similarity,
timestamp_exact_accuracy, total_cost_exact_accuracy,
all_four_fields_accuracy,
vietnamese_charset_pass_rate, insertion_rate,
blank_image_text_rate, unsupported_field_rate, json_parse_failure_rate,
latency_p50_ms, latency_p95_ms,
peak_ram_mb, peak_vram_mb, model_size_mb, failure_rate
```

Metric không áp dụng phải ghi `N/A`, không ghi `0`, vì `0` có nghĩa model đã được đánh giá và thất bại hoàn toàn.

`FINAL_REPORT.md` phải gồm:

- Phiên bản dữ liệu và checksum manifest.
- Cấu hình đầy đủ từng model.
- Bảng kết quả tổng hợp kèm bootstrap 95% confidence interval cho metric nghiệp vụ chính.
- Kết quả theo chất lượng ảnh.
- Phân tích lỗi và ví dụ trực quan.
- Chi phí/tốc độ triển khai.
- Model được đề xuất và lý do dựa trên ưu tiên nghiệp vụ.
- Các giới hạn của ground truth hiện tại.
- Đề xuất dữ liệu cần gán nhãn thêm.

### WF-15 — Đóng gói đầu ra cho Agent 3

Adapter thắng benchmark phải được bọc sau một interface ổn định, nhưng bản đóng gói và mọi thử nghiệm vẫn nằm trong workflow cho đến khi được duyệt tích hợp.

Hợp đồng bàn giao gồm:

- `Canonical Invoice JSON`.
- Confidence ở mức field.
- `missing_fields` và cờ `requires_review`.
- Evidence polygon/text để audit.
- Model version, config version và preprocessing version.
- Quy tắc: field thiếu hoặc confidence dưới ngưỡng không được đoán; chuyển `REVIEW` trước khi vào Rule ZEN.

Chỉ sau khi benchmark, báo cáo và contract được duyệt mới sao chép module tối thiểu cần thiết sang `agent3_tax_compliance`. Không trộn mã thử nghiệm benchmark vào code production.

## 5. Trình tự chạy dự kiến

Các lệnh dưới đây là giao diện mục tiêu cần được hiện thực trong `src/cli.py`:

```powershell
Set-Location "D:\financial\data invoice\ocr_e2e_workflow"

py -3.10 -m venv envs\evaluator
.\envs\evaluator\Scripts\python.exe -m pip install -r requirements\evaluator.txt

$env:PYTHONUTF8 = "1"
$env:HF_HOME = "$PWD\artifacts\cache\huggingface"
$env:TORCH_HOME = "$PWD\artifacts\cache\torch"
$env:PIP_CACHE_DIR = "$PWD\artifacts\cache\pip"

.\envs\evaluator\Scripts\python.exe -m src.cli --config configs\benchmark.yaml inventory
.\envs\evaluator\Scripts\python.exe -m src.cli --config configs\benchmark.yaml prepare
.\envs\evaluator\Scripts\python.exe -m src.cli --config configs\benchmark.yaml validate-data
.\envs\evaluator\Scripts\python.exe -m src.cli smoke-test --all-models

# Pilot thống nhất 100 mẫu: run -> evaluate -> report -> CSV/SVG cho mọi model khả dụng
.\envs\evaluator\Scripts\python.exe -m src.cli benchmark-suite --split dev --limit 100 --suite-id dev100_all

.\envs\evaluator\Scripts\python.exe -m src.cli run --model ppocrv6_medium --split dev
.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id <DEV_RUN_ID>

.\envs\evaluator\Scripts\python.exe -m src.cli run --model ppocrv6_medium --split test
.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id <TEST_RUN_ID>

.\envs\evaluator\Scripts\python.exe -m src.cli report
```

`src.cli run` phải gọi Python executable được khai báo trong config của từng model, ví dụ `envs/ppocrv6_medium/Scripts/python.exe`, rồi giao tiếp qua JSONL. Cách này tránh xung đột PaddlePaddle, PyTorch, Transformers, vLLM và các phiên bản CUDA nhưng vẫn giữ toàn bộ môi trường trong workflow.

Mỗi run tạo:

```text
runs/<run_id>/
├── config.snapshot.json
├── environment.json
├── manifest.sha256.json
├── logs/
├── predictions/
│   ├── raw.jsonl
│   ├── normalized.jsonl
│   └── fields.jsonl
├── metrics/
│   ├── detection.json
│   ├── recognition.json
│   ├── text_spotting.json
│   ├── fields.json
│   └── performance.json
└── intermediate/
```

## 6. Kế hoạch kiểm thử mã benchmark

Chỉ viết test cho phần có nguy cơ làm sai kết luận:

- Tách crop filename thành source image ID.
- Phát hiện giao nhau dev/test.
- Parse polygon có dấu phẩy rỗng cuối dòng.
- Ghép prediction–ground truth một-một theo IoU.
- CER/WER trên các ví dụ nhỏ có đáp án biết trước.
- Unicode NFC và chuẩn hóa khoảng trắng.
- Parse số tiền như `150.000đ`, `150,000`, `150 000 VND`.
- Parse các định dạng ngày giờ trong dữ liệu.
- Không biến transcript rỗng thành prediction đúng.
- Không bỏ record khi adapter gặp lỗi.
- Fixture tiếng Việt kiểm tra được ký tự có dấu và ghi đúng dictionary/model revision.
- Model không có polygon nhận `N/A`, không nhận `0` ở detection/text spotting.
- Structured output sai schema được tính vào `json_parse_failure_rate`.
- Ảnh trắng sinh text được ghi vào metric hallucination chẩn đoán.

Sau mỗi thay đổi metric hoặc normalization, phải chạy lại toàn bộ test trước khi tạo leaderboard.

## 7. Cam kết tiến độ đề xuất

| Giai đoạn | Công việc | Thời lượng dự kiến | Sản phẩm bàn giao |
|---|---|---:|---|
| 1 | WF-01 đến WF-04 | 1–2 ngày | Workflow, manifest, split và ground truth sạch |
| 2 | WF-05, WF-06, WF-08, WF-09 | 1–2 ngày | Contract, normalization và evaluator cơ bản |
| 3 | Tesseract, EasyOCR, PP-OCRv6 Medium | 1–2 ngày | Baseline và leaderboard pipeline ban đầu |
| 4 | PP-OCRv6 + VietOCR, PaddleOCR-VL-1.6, Surya OCR 2, GLM-OCR | 3–5 ngày | So sánh shared detector và OCR VLM cốt lõi |
| 5 | WF-11 đến WF-13 | 2–3 ngày | Field extraction, performance và error analysis |
| 6 | HunyuanOCR/Chandra/dots.mocr nếu đủ tài nguyên | 2–4 ngày tùy chọn | Leaderboard VLM mở rộng |
| 7 | WF-14, WF-15 | 1–2 ngày | Báo cáo cuối và contract bàn giao Agent 3 |

Tiến độ phụ thuộc vào thời gian tải model và phần cứng chạy inference. Không rút ngắn bằng cách dùng tập test để tinh chỉnh threshold.

## 8. Điều kiện nghiệm thu

Workflow chỉ được coi là hoàn tất khi đáp ứng đủ:

- Toàn bộ file sinh ra nằm trong `ocr_e2e_workflow`.
- Dữ liệu gốc không thay đổi checksum.
- Manifest dev/test tái tạo được và không leakage.
- Mọi model tuân theo cùng output contract.
- Model và dictionary vượt qua smoke test charset tiếng Việt hoặc được đánh dấu không đủ điều kiện.
- Có kết quả detection, recognition, key-field end-to-end và field business.
- Detection/text spotting của model không có tọa độ được ghi `N/A` và nằm trong bảng VLM riêng.
- Metric strict và normalized được báo riêng.
- `TOTAL_COST` và `TIMESTAMP` được đánh giá sau canonical parsing.
- Có latency p50/p95, RAM/VRAM và failure rate.
- Có phân tích theo chất lượng ảnh và danh sách lỗi điển hình.
- Có config snapshot, environment metadata và model version cho từng run.
- Có hai leaderboard pipeline/VLM và báo cáo cuối giải thích vì sao chọn model.
- Đầu ra thắng benchmark chuyển được thành Canonical Invoice JSON và hỗ trợ `REVIEW` khi thiếu/không chắc chắn.

## 9. Rủi ro và giới hạn cần ghi rõ trong báo cáo

- Recognition validation chỉ đại diện cho các crop đã có nhãn, không phải toàn bộ text trên hóa đơn.
- CSV field có thể gán cùng nhãn `TOTAL_COST` cho cả keyword và giá trị; cần tách metric box-level khỏi canonical business value.
- KIE transcript có nhiều ô rỗng và một số file thiếu; không dùng làm ground truth nhận dạng toàn trang trước khi làm sạch.
- Tập `val_images` có nhãn mẫu/dummy ở các file CSV liên quan; không dùng để tính CER/WER hay field accuracy.
- Các tập `data0_or_180` và `data0.7` có dấu hiệu là dữ liệu dẫn xuất/augmentation; không được coi là test độc lập.
- Dữ liệu có thể chưa bao phủ đủ hóa đơn điện tử mới, ảnh điện thoại, PDF scan và nhà cung cấp dài đuôi. Model được chọn cần được kiểm tra lại khi có dữ liệu Agent 3 thực tế.
- OCR tốt không tự động đồng nghĩa với kết luận thuế đúng. Sau giai đoạn này vẫn cần benchmark riêng cho canonical transaction mapping, Rule ZEN, retrieval và citation verification.
- PP-OCRv6 từng có báo cáo thiếu một số ký tự tiếng Việt trong dictionary; phải khóa model revision, checksum dictionary và chạy fixture trước khi dùng kết quả.
- OCR VLM có thể sinh chuỗi hợp ngữ nhưng không xuất hiện trong ảnh. Do transcript toàn trang chưa đầy đủ, chỉ được báo metric hallucination tại nơi có ground truth hoặc evidence kiểm chứng được.
- Surya và Chandra có điều kiện license riêng cho model weight; báo cáo phải tách quyền dùng nghiên cứu khỏi quyền triển khai thương mại.
