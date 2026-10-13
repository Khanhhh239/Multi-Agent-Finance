# OCR end-to-end workflow

Các bước chạy lâu và hướng dẫn Kaggle nằm trong [MANUAL_RUNBOOK.md](MANUAL_RUNBOOK.md).

Workflow này đánh giá OCR trên bộ dữ liệu MCOCR mà không sửa dữ liệu nguồn. Mọi môi trường, model, cache, manifest và kết quả đều được lưu trong thư mục hiện tại.

## Khởi tạo evaluator

```powershell
Set-Location "D:\financial\data invoice\ocr_e2e_workflow"
py -3.10 -m venv envs\evaluator
.\envs\evaluator\Scripts\python.exe -m pip install -r requirements\evaluator.txt
$env:PYTHONPATH = "$PWD"
```

## Chuẩn bị dữ liệu

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli inventory
.\envs\evaluator\Scripts\python.exe -m src.cli prepare
.\envs\evaluator\Scripts\python.exe -m src.cli validate-data
```

## Chạy model và đánh giá

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli run --model easyocr --split dev
.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id <RUN_ID>
.\envs\evaluator\Scripts\python.exe -m src.cli report
```

Mỗi model đọc cấu hình trong `configs/models`. Các model lớn có môi trường riêng dưới `envs/<model_id>`; adapter trao đổi với evaluator qua JSONL.

Để kiểm tra cài đặt nhanh trước khi benchmark:

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli smoke-test --model easyocr --model ppocrv6_medium
```

PP-OCRv6 dùng detector, recognizer và bộ phân loại hướng trang nằm trong `artifacts/models/ppocrv6_medium`. Backend oneDNN được tắt trên Windows vì không tương thích với graph hiện tại của Paddle 3.3.1.

## Nguyên tắc

- Không chỉnh sửa hoặc sao chép dữ liệu nguồn.
- Không tinh chỉnh threshold trên tập test.
- Model không trả tọa độ nhận `N/A` ở detection/text spotting.
- Mọi run lưu snapshot config, môi trường và checksum manifest.
- Chỉ so sánh latency trên cùng loại phần cứng.

Xem [PLAN.md](PLAN.md) để biết đầy đủ thiết kế, metric và điều kiện nghiệm thu.
