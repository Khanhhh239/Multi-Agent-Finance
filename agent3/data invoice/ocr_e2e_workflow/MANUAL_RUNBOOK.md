# Hướng dẫn chạy thủ công benchmark OCR

Tài liệu này dành cho các bước mất nhiều thời gian. Mọi lệnh phải chạy từ thư mục `ocr_e2e_workflow`; không cài chung các model vào một môi trường Python.

## 1. Kiểm tra nhanh trước khi chạy dài

```powershell
Set-Location "D:\financial\data invoice\ocr_e2e_workflow"
$env:PYTHONUTF8 = "1"
$env:HF_HOME = "$PWD\artifacts\cache\huggingface"
$env:TORCH_HOME = "$PWD\artifacts\cache\torch"
$env:PADDLE_PDX_CACHE_HOME = "$PWD\artifacts\cache\paddlex"

.\envs\evaluator\Scripts\python.exe -m src.cli validate-data
.\envs\evaluator\Scripts\python.exe -m pytest -q
```

Kết quả kiểm thử code hiện tại là `34 passed`. Hai file KIE thiếu nhãn detection được ghi thành warning, không làm dừng benchmark.

## 2. Chạy pilot trước, không chạy toàn bộ ngay

### Một lệnh chạy tất cả model khả dụng trên 100 mẫu

Lệnh sau lần lượt chạy 100 ảnh toàn trang và 100 recognition crop cho mỗi model, evaluate ngay sau từng model, rồi tạo report, CSV và biểu đồ:

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli benchmark-suite --split dev --limit 100 --suite-id dev100_all
```

Nếu tiếp tục run `dev100_all` đã tạo trước bản sửa hybrid, lệnh trên sẽ giữ các prediction thành công, thử lại những dòng `worker_native_crash` và chạy tiếp các mẫu chưa xong. Run này trộn prediction trước/sau khi đổi cách gọi detector, nên chỉ dùng để kiểm tra pipeline hoàn tất; **không dùng điểm của nó làm benchmark cuối cùng**. Để đo sạch `ppocrv6_vietocr` với cùng 100 mẫu, chạy suite riêng (bước này mất nhiều thời gian trên CPU):

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli benchmark-suite --split dev --limit 100 --suite-id dev100_vietocr_v2 --model ppocrv6_vietocr
```

Run mới lưu ở `runs/dev100_vietocr_v2_ppocrv6_vietocr/`; báo cáo riêng ở `reports/suites/dev100_vietocr_v2/`. Nếu ngắt giữa chừng, chạy lại đúng lệnh trên để resume.

Model chưa có môi trường hoặc cần GPU nhưng máy không có CUDA sẽ được ghi là `skipped`; suite vẫn chạy model tiếp theo. Trên máy hiện tại, lệnh sẽ chạy `tesseract`, `easyocr`, `ppocrv6_medium` và `ppocrv6_vietocr`. Khi chạy lại cùng `suite-id`, model đã hoàn tất sẽ được tái sử dụng và evaluate lại. Model bị ngắt hoặc native crash sẽ đọc JSONL đã ghi, bỏ dòng cuối bị hỏng nếu có và tiếp tục từ mẫu chưa hoàn thành. Nếu cùng một mẫu làm worker native crash mà không tạo thêm prediction, mẫu đó được ghi là `failed`, được tính vào failure rate và worker khởi động lại để tiếp tục mẫu kế tiếp; tối đa 10 mẫu lỗi cho mỗi phase.

Kết quả riêng của suite nằm tại:

```text
reports/suites/dev100_all/
├── RESULTS.md
├── leaderboard.csv
├── status.json
└── charts/
    ├── detection_f1.svg
    ├── recognition_cer.svg
    ├── all_four_fields_accuracy.svg
    └── latency_p95_ms.svg
```

`reports/FINAL_REPORT.md` và hai leaderboard tổng cũng được cập nhật tự động khi suite kết thúc.

### Chạy riêng một model để kiểm tra

Mỗi model nên chạy 25 ảnh/crop trên `dev` trước. Thay `<model>` bằng một model trong bảng dưới đây và đặt `run-id` khác nhau.

Trong khi chạy, terminal hiển thị hai thanh `tqdm`: `Full images` và `Recognition crops`. Mỗi thanh cho biết số mẫu đã xong, tốc độ và ETA. Kết quả được ghi từng dòng vào JSONL nên có thể kiểm tra số mẫu đã hoàn thành ngay trong thư mục run.

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli run --model <model> --split dev --limit 25 --run-id pilot_<model>_25

.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id pilot_<model>_25
.\envs\evaluator\Scripts\python.exe -m src.cli report
```

Các model đã có môi trường trên máy Windows này:

| Model | Trạng thái | Thời gian tham khảo trên CPU |
|---|---|---:|
| `tesseract` | chạy được | khoảng 2 giây/ảnh |
| `easyocr` | chạy được | khoảng 14 giây/ảnh |
| `ppocrv6_medium` | chạy được | khoảng 30–100 giây/ảnh |
| `ppocrv6_vietocr` | chạy được | ảnh thử khó mất 207 giây; tốc độ phụ thuộc số crop chữ |

Số liệu trên chỉ dùng để dự kiến thời gian. Chúng được đo từ smoke run 1–2 ảnh và không phải kết luận chất lượng.

## 3. Chạy toàn bộ dev khi pilot đã đạt

Bỏ `--limit` để chạy 922 ảnh dev và toàn bộ recognition train crop. Đây là bước dài; chạy từng model một.

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli run --model tesseract --split dev --run-id dev_tesseract_full

.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id dev_tesseract_full
```

Lặp lại với `easyocr`, `ppocrv6_medium` và `ppocrv6_vietocr`. Không dùng tập `test` để chọn model.

Sau khi so sánh báo cáo dev, chỉ chạy 1–2 model tốt nhất trên test:

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli run --model <model_thang_dev> --split test --run-id test_<model_thang_dev>_full

.\envs\evaluator\Scripts\python.exe -m src.cli evaluate --run-id test_<model_thang_dev>_full
.\envs\evaluator\Scripts\python.exe -m src.cli report
```

## 4. Chạy model GPU trên Kaggle

Bật GPU trong **Notebook settings → Accelerator → GPU**. Sao chép toàn bộ thư mục `data invoice` sang `/kaggle/working` để workflow ghi được `envs`, `artifacts`, `runs` và `reports`. Các đường dẫn model tự đổi từ `Scripts/python.exe` sang `bin/python` trên Linux.

Trong cell shell:

```bash
cd "/kaggle/working/data invoice/ocr_e2e_workflow"
export PYTHONUTF8=1
export HF_HOME="$PWD/artifacts/cache/huggingface"
export TORCH_HOME="$PWD/artifacts/cache/torch"
export PADDLE_PDX_CACHE_HOME="$PWD/artifacts/cache/paddlex"

python -m venv envs/evaluator
envs/evaluator/bin/python -m pip install -r requirements/evaluator.txt
envs/evaluator/bin/python -m src.cli validate-data
```

Cài và chạy **một model mỗi phiên** để tránh xung đột dependency và đầy ổ đĩa:

```bash
envs/evaluator/bin/python -m src.cli setup-env --model paddleocr_vl_1_6
envs/evaluator/bin/python -m src.cli smoke-test --model paddleocr_vl_1_6
envs/evaluator/bin/python -m src.cli run --model paddleocr_vl_1_6 --split dev --limit 25 --run-id pilot_paddleocr_vl_1_6_25
envs/evaluator/bin/python -m src.cli evaluate --run-id pilot_paddleocr_vl_1_6_25
```

Thứ tự đề xuất cho các model còn lại:

1. `paddleocr_vl_1_6`
2. `surya_ocr_2`
3. `glm_ocr`
4. `hunyuan_ocr_1_5`
5. `chandra_ocr_2`
6. `dots_mocr`

`dots_mocr` yêu cầu Python 3.12 trở lên. `HunyuanOCR` và `Chandra OCR 2` cần kiểm tra/chấp nhận điều khoản model trước khi tải. Nếu Hugging Face yêu cầu token, đăng nhập trong Kaggle bằng secret `HF_TOKEN`, không ghi token vào notebook hoặc repository.

## 5. File cần lấy sau mỗi phiên Kaggle

Tải về hoặc lưu thành Kaggle Output các thư mục sau:

```text
runs/<run_id>/
reports/
artifacts/models/             # chỉ cần khi muốn tái sử dụng trọng số
```

Khi đưa kết quả về máy Windows, chép `runs/<run_id>` vào đúng thư mục `runs/`, rồi chạy:

```powershell
.\envs\evaluator\Scripts\python.exe -m src.cli report
```

Không so sánh các model từ các run có số lượng mẫu khác nhau. `leaderboard_pipeline.csv` và `leaderboard_vlm.csv` có cột `full_images` và `recognition_crops` để kiểm tra điều này.
