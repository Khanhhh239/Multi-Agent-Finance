# Đọc lại vùng nguồn — PLAN_06, 19/10/2026

Đã triển khai chức năng đọc lại tên, địa chỉ và mô tả dòng hàng **có block nguồn**, bằng recognizer VietOCR riêng. Không đổi detector/recognizer của OCR chính, không nâng trạng thái luật hoặc nghiệm thu PLAN_14.

## Cách dùng trên web

1. Chạy lại web bằng STOP_AGENT3 rồi OPEN_AGENT3, nhấn Ctrl+F5.
2. Mở hóa đơn ở bước **Dữ liệu hóa đơn**. Nếu bản cũ báo 0 dòng, thử **Trích xuất lại dữ liệu** trước; đọc vùng chưa bổ sung được dòng không có evidence. Với bảng hàng đã có, mở **Chi tiết** của dòng cần xử lý.
3. Bấm **Xem nguồn** ở tên, địa chỉ hoặc mô tả hàng; bấm **Đọc lại vùng chữ** bên dưới vùng nguồn.
4. Xem giá trị đã lưu, chữ đọc lại và từng vùng ảnh. Model có thể trả cả nhãn hoặc đọc sai; người dùng phải kiểm tra giá trị ứng viên.
5. Nếu phù hợp, bấm **Đưa vào bản nháp**, chỉnh thêm nếu cần, rồi **Lưu dữ liệu hóa đơn**. Lý do lưu chứa ID lượt đọc để truy nguyên. Chỉ thao tác lưu mới xác nhận dữ liệu qua correction service hiện có.

Nếu có bản nháp, cần lưu hoặc bỏ bản nháp trước khi đọc lại. Nếu không có evidence, quá nhiều vùng hoặc nguồn rời nhau, UI báo cần đối chiếu/xử lý riêng. Không tự coi chữ trống là không được in trên hóa đơn. Các trường số/ngày/MST chưa có chức năng đọc lại trong lát cắt này.

## API, dữ liệu và giới hạn

`POST /v1/records/{record_id}/reread-region?taxpayer_id=...`, cần bearer và quyền WRITE trong đúng tenant/taxpayer:

```json
{
  "expected_record_revision": 1,
  "field_path": "items.<immutable-item-id>.description"
}
```

API chỉ lấy block/bbox từ artifact của chính hồ sơ; không nhận đường dẫn ảnh, model ID hay bbox do client cung cấp. Dùng tối đa 4 dòng liên tiếp trên cùng trang, từ chối vùng cao hơn 8% trang/vùng quá lớn; không tự bỏ bớt một phần field. Crop thêm tối đa 1 pixel quanh bbox, clamp vào trang, tối đa 1 triệu pixel/crop và 2 triệu pixel/batch. Lưu pixel box, kích thước trang, hash ảnh crop, evidence/transform gốc và raw response từng dòng.

Worker chạy process riêng với giới hạn 3 GiB, tối đa 30 giây nhân số crop, một attempt. Khi worker OCR đang bận thì không xếp thêm request đọc vùng chờ vô hạn. Runtime probe có timeout riêng và nằm ngoài thời gian inference; không coi số giây model của một mẫu là SLA. Một lượt region chưa cache được xử lý tại một thời điểm trong mỗi app process.

Profile `configs/ocr/engines/vietocr_region_v1.json` dùng weights VietOCR hiện có, `beamsearch: true`, có tách dòng dài tại khoảng trắng với tối đa 4 đoạn, giữ x spans/text từng đoạn. Đây là recognizer-only, không load detector PP-OCR hoặc gửi tài liệu lên cloud. Recognition score không được gán thành xác suất đúng. Có thể thay adapter/runtime qua profile registry; chưa benchmark thêm model khác.

Sidecar `{database-stem}.region-ocr.sqlite3` lưu kết quả bất biến, scope tenant/taxpayer, actor/time, SHA-256 payload. Cache key gắn record revision/hash, OCR/profile/runtime và implementation. Lỗi worker không cache thành công; kết quả rỗng/thiếu dòng được giữ `NEEDS_REVIEW`, không có nút áp dụng. Kết quả đúng schema vẫn chỉ là `CANDIDATE`, không là phê duyệt nội dung.

Hồ sơ, raw OCR và reviewer correction không bị ghi đè. API từ chối revision cũ trước khi đọc và kiểm tra lại revision sau model. UI bỏ response đến muộn khi đổi trường/hồ sơ/đơn vị; không ghi lên bản nháp đang sửa. Khi lưu sau đối chiếu, correction service giữ evidence trường gốc và lý do chứa recovery ID; các bbox crop/raw response mới truy nguyên ở sidecar, không giả thành candidate đã có sẵn của extractor.

## Thử trên dữ liệu thật

Chạy trên bản sao SQLite của DB local, đọc live DB bằng `mode=ro` khi backup. Không sửa hồ sơ người dùng và không tự tạo nhãn HUMAN_CONFIRMED trên hồ sơ thật.

- Mẫu dev từng mất bảng: extraction trước đó đã phục hồi 0 → 1 dòng. Lần này tập trung lỗi lặp từ cuối mô tả, không tính lại thành một lần cải thiện table accuracy.
- Ablation cùng crop đầu: greedy + crop giữ nguyên vẫn lặp từ; inset 2/4 px và beam search đều bỏ phần chữ dư trên mẫu đó. Chỉ chọn **beam trên crop không inset**, tránh áp dụng cắt dọc làm mất dấu trên tài liệu khác. Giữ riêng kết quả thử, không chỉnh default OCR chính.
- Kiểm thử Chrome + API + model thật: đọc 2 crop, lượt đầu khoảng **10,46 giây**, lượt xác minh cuối khoảng **9,37 giây**, tên hàng không còn lặp từ cuối; bản đã lưu không đổi; không có JavaScript error. Nhãn do agent tự nhìn nguồn, không phải nghiệm thu độc lập.
- Replay 4 nguồn dev: 3 lượt trả ứng viên (2 thay đổi, 1 giữ nguyên), 1 trường vượt ngân sách block được từ chối. Lượt đầu dùng cache; các lượt còn lại khoảng 7,76 và 8,57 giây. **Chưa chấm đúng/sai các ứng viên còn lại**, không lấy changed/fill rate làm accuracy.

Metadata đã bỏ nội dung chứng từ: [model_and_dev.json](model_and_dev.json). Raw text, crop, screenshot và DB chỉ lưu local ngoài Git. Mọi mẫu trên đều là dev đã được dùng chẩn đoán/sửa code, không giả làm holdout.

## Kiểm thử và chạy lại

Chạy bộ hồi quy hiện tại từ root:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_region_recovery.py
```

Chạy riêng crop/adapter trong environment model:

```powershell
cd "data invoice/ocr_e2e_workflow"
.\envs\ppocrv6_vietocr\Scripts\python.exe -m unittest discover -s tests -p test_recognition_crops.py -v
```

Kết quả tổng hợp ở [validation_summary.json](validation_summary.json); browser region ở [browser_region.json](browser_region.json). Bài test Chrome dùng fixture tổng hợp và reader double, tách riêng lượt model thật nêu trên. Kiểm tra auth/scope/strict revision, crop edges/integrity, timeout/retry/cache, revision thay đổi giữa chừng, không sửa hồ sơ gốc, thao tác lưu, response muộn, XSS và mobile/desktop. Browser cũng phát hiện nhãn tuyệt đối của bảng làm tràn trang khi mở chi tiết; đã đặt containing block cho field header và kiểm tra lại.

Kết quả cuối: **459 Python tests, 47 nhóm Chrome, 7 JavaScript syntax checks + 2 client harness checks** qua; thêm **5 crop/adapter tests** trong environment OCR qua. Sau hồi quy đầy đủ, harness DOM được bổ sung CustomEvent cho sự kiện chọn trường và chạy lại toàn bộ JS; cache key được bổ sung hash parent worker/protocol/registry, rồi chạy lại 16 bài recovery và lượt Chrome/model thật. Core workflow/replay thuế giữ nguyên hash.

## Chưa làm

- Chưa render PDF ở DPI khác, chưa chọn crop bằng chuột, chưa tìm lại chữ bị detector bỏ sót hoặc tách block nhiều dòng bằng layout model mới.
- Chưa tự gọi regional OCR trong chuỗi automation, chưa tự chọn kết quả giữa hai model hoặc tự xác nhận field. Không dùng agreement hoặc beam search để tuyên bố giá trị chắc chắn đúng.
- Chưa benchmark accuracy trên holdout/calibration. Không công bố độ chính xác tổng quát từ một lỗi đã sửa.
- Không thay đổi Qwen/explanation hoặc nghiệm thu pháp lý trong đợt này.
