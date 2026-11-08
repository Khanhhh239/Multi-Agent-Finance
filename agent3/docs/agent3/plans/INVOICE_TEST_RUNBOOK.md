# Tự chạy và đo lỗi với bộ invoice_test

## Bộ tài liệu đã chuẩn bị

- PDF gốc được giữ nguyên trong `invoice_test/`.
- `invoice_test/prepared/pages/`: 32 PDF một trang, kèm ảnh xem nguồn.
- `invoice_test/prepared/index.html`: danh mục để mở từng PDF.
- Trang 1 là tờ khai thuế; trang 19–20 là chứng từ thuế khác, loại khỏi lượt chạy hóa đơn.
- Trang 12–13 là hai trang của cùng một hóa đơn: có bản gom riêng trong `prepared/invoices/` và chạy thành một hồ sơ.
- Tổng: 29 trang hóa đơn, **28 hồ sơ**. Đây là nguồn tài liệu thực hành đã từng dùng phát triển; tất cả giữ split `dev`, không gọi là holdout mới.
- File gốc, PDF tách, nhãn, ảnh, kết quả và DB đều nằm trong vùng bị gitignore. Không gửi hóa đơn ra API ngoài.

Tách trang giữ text/vector gốc, không raster hóa PDF đầu ra. Đã mở lại kiểm tra số trang, text, geometry và render so với nguồn. Chênh lệch raster nhỏ do antialiasing được ghi rõ trong `inventory.json`, không gọi là bit-exact. Bản thử tách ban đầu chưa đạt phép kiểm pixel tuyệt đối được giữ riêng trong `prepared_incomplete_pixelcheck/`; chỉ dùng `prepared/` cho các lệnh bên dưới.

## 1. Chạy thử 3 hóa đơn đầu

Từ PowerShell tại `D:\financial`:

```powershell
.\RUN_INVOICE_TEST.cmd
```

Mặc định chạy trang nguồn 2, 3, 4 qua pipeline production hiện có. PDF có chữ có thể dùng native text hoặc HYBRID; không báo rằng đã chạy recognizer nếu router không gọi OCR. Các trang scan cần model local. Chạy được mà chưa có nhãn **không đồng nghĩa OCR đúng**.

Lượt mới có run ID theo thời gian, DB riêng từng hồ sơ và không sửa DB demo. Lệnh in tiến độ STARTING/REVIEW/lỗi và đường dẫn cuối đến `review.html`.

Muốn chọn trang khác hoặc chạy đủ 28 hồ sơ:

```powershell
.\RUN_INVOICE_TEST.cmd run --pages 5,8,31
.\RUN_INVOICE_TEST.cmd run --pages 12
.\RUN_INVOICE_TEST.cmd run --pages all
```

Chọn 12 **hoặc** 13 luôn chạy cả hóa đơn 12–13. Chọn 1, 19 hoặc 20 sẽ bị từ chối. Đừng mở nhiều lượt cùng lúc: OCR CPU có thể mất vài phút/trang; cả bộ có thể chạy lâu. Ctrl+C dừng lượt hiện tại; dữ liệu đã chạy giữ lại, nhưng run dở không được chấm như một benchmark hoàn tất. Để mở lại báo cáo gần nhất:

```powershell
.\RUN_INVOICE_TEST.cmd report
```

Thêm `--run-id ten_moi` nếu muốn đặt tên; không tái sử dụng ID cũ. Chỉ thêm `--dedicated-machine` khi máy không chạy test/inference/tác vụ nặng khác. Mặc định không chứng nhận điều kiện đo latency. Quy ước số của bộ này được đặt `VI` từ bản in; các bộ khác cần khai báo quy ước phù hợp.

## 2. Đối chiếu để có nhãn đúng

Mở file `review.html` mà lệnh in ra. Nó nằm trong `invoice_test/results/<run_id>/`:

Giao diện hiển thị **một hóa đơn mỗi lần**. Dùng danh sách ở trên hoặc nút ←/→ để
chuyển hóa đơn; các tab **Thông tin chung / Dòng hàng / Cảnh báo** để chuyển phần
đối chiếu. Với hóa đơn nhiều trang, dùng nút chuyển trang phía trên ảnh. Nút +/−
phóng ảnh; **Vừa trang** đưa về chế độ vừa khung. Ảnh được nhúng vào HTML, không
phụ thuộc đường dẫn `file:///` nên có thể mở trực tiếp hoặc qua preview/server.

1. Xem ảnh nguồn ở trái và kết quả máy ở phải.
2. Ô máy đúng: bấm **Giá trị này đúng**. Ô sai: nhập đáp án từ ảnh; ô đó được đánh dấu đã đối chiếu.
3. Chỉ chọn **Không in** khi chắc chắn trường đó không có trên hóa đơn. Ô chưa rõ để chưa đối chiếu; không ghi `null` thay cho chưa biết.
4. Đối chiếu tên, MST, số/ngày, tổng tiền và các ô bảng. Nút **Thêm dòng nhãn bị OCR bỏ sót** cho phép bổ sung hàng nhãn; thứ tự nhãn phải theo giấy, kể cả khi máy mất dòng giữa bảng.
5. Nhập nhãn số chuẩn: `1234567.89` thay vì `1.234.567,89`; ngày `2025-03-17`; rate `0.08` cho 8%; nhóm thuế `TAXABLE_RATE`, `KCT` hoặc `KKKNT`. Đây là dạng lưu nhãn, không phải thay đổi cách nhập của UI demo.
6. Bấm **Xuất nhãn đối chiếu**. Trình duyệt tải `labels_<run_id>.json`. Di chuyển file đó vào `D:\financial\invoice_test\labels.json` hoặc dùng nguyên đường dẫn tải xuống khi chấm.

Bản nháp tự lưu trong trình duyệt đang dùng khi trình duyệt cho phép localStorage;
chuyển hóa đơn hoặc tải lại không làm mất các ô đã nhập. Xuất JSON để lưu bản sao
hoặc chuyển sang trình duyệt/máy khác; nút **Nhập nhãn đã lưu** nhận lại JSON đúng
run ID/hash nguồn. Nhãn thay đổi sau khi chấm cần chạy lại `score` để cập nhật màu.

Nhãn chưa đối chiếu không được xuất như đáp án. Kết quả OCR không tự trở thành ground truth. Nhãn từ giao diện giữ `DRAFT`, `complete=false`; muốn nghiệm thu toàn hóa đơn/độc lập cần quy trình nhãn đầy đủ và reviewer như kế hoạch OCR quality.

## 3. Chấm lỗi thực tế

Sau khi lưu file nhãn:

```powershell
.\RUN_INVOICE_TEST.cmd score --labels .\invoice_test\labels.json
```

Nếu file nằm ở Downloads, thay bằng đường dẫn đầy đủ có dấu ngoặc kép. Lệnh kiểm tra run ID và SHA-256 nguồn; nhãn của hóa đơn/lượt khác bị từ chối. Chấm chỉ đọc artifact đã có, **không chạy lại OCR** và không sửa dữ liệu capture hoặc manifest cũ.

Kết quả:

- `invoice_test/results/<run_id>/score_<thoi_gian>.json`: đúng/sai/thiếu theo nhãn, nhóm trường, thứ tự ưu tiên lỗi và giả thuyết nguyên nhân.
- `review.html` được cập nhật màu: xanh đúng, đỏ điền sai, vàng thiếu/mơ hồ.
- Nhãn được lưu thành snapshot cạnh file score; chạy lại `report` giữ kết quả chấm và nhãn gần nhất.
- `priority_errors` ưu tiên MST/số hóa đơn/tổng tiền, nhất là trường điền sai. `hypothesis` chỉ là chẩn đoán để chọn lớp cần xem (recognizer/crop, binding hoặc parser), không thay kiểm tra ảnh/crop thực tế.
- Cảnh báo kỹ thuật khi chưa có nhãn không được tính thành lỗi đã xác nhận. Báo cáo chưa nhãn không có accuracy giả bằng 0% hoặc 100%.

Để mở/chấm một lượt cũ, thêm `--run-id <id>` vào `report` hoặc `score`.

## So sánh bản sửa trích xuất trên OCR đã lưu

Khi đã có baseline và nhãn chuẩn, chạy một lượt riêng để kiểm tra thay đổi bộ
trích xuất mà không tải model hoặc nhận dạng lại ảnh:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/replay_invoice_extraction.py --baseline-run invoice_test_20261026_100400_442193 --labels invoice_test/labels_canonical_invoice_test_20261026_100400_442193.json --run-id invoice_extract_my_fix_001
.\RUN_INVOICE_TEST.cmd score --run-id invoice_extract_my_fix_001 --labels agent3_tax_compliance/data/ocr_quality/invoice_extract_my_fix_001/labels.json
```

Chọn run ID mới mỗi lần; thư mục đã tồn tại sẽ bị từ chối. Thay baseline và file
nhãn theo lượt thực tế của bạn. Lệnh yêu cầu nhãn phủ cùng tập hồ sơ, đúng run ID
baseline và đúng hash nguồn. Ngày trong nhãn dùng ISO `YYYY-MM-DD`, mã số thuế
dùng chuỗi chữ số, tiền dùng số thập phân chuẩn và thuế suất dùng `0.08` cho 8%.
Giữ nguyên số 0 đầu của số hóa đơn. Không dùng nhãn để sửa nội dung OCR đầu vào.

Kết quả nằm trong `agent3_tax_compliance/data/ocr_quality/<run-id>/`:
`report.json`, `baseline_scored_report.json`, `comparison.json`, `labels.json`
và các artifact mới cho từng hồ sơ. Baseline và SQLite nguồn chỉ được đọc;
hash payload OCR và định danh tenant/nguồn phải khớp artifact gốc. Bản replay
không ghi vào cơ sở dữ liệu capture hoặc sửa các giá trị đã được xác nhận.

`FROZEN_OCR_EXTRACTION_REPLAY` chỉ đo khả năng trích xuất từ quan sát đã lưu;
không đo lại chất lượng nhận dạng model hoặc độ trễ OCR đầu cuối. So sánh chấm
cả baseline lẫn candidate bằng cùng nhãn. Nhãn DRAFT, thiếu nhãn đầy đủ hoặc
chưa đo latency vẫn không đủ điều kiện nghiệm thu/phát hành.

## Kiểm tra công cụ

Khi sửa tiếp trên một bản đã đánh giá, thêm `--compare-run <run-id-ban-truoc>`
vào lệnh `replay_invoice_extraction.py`. Công cụ chấm lại artifact của bản trước
bằng cùng nhãn hiện tại, kiểm tra cùng tập hồ sơ, nguồn, tenant và hash quan sát
OCR, rồi ghi `comparison_previous.json` cùng `previous_fix_scored_report.json`.
Kiểm tra báo cáo này để tránh một bản sửa tốt hơn baseline gốc nhưng làm hỏng
những ô đã đúng ở lượt sửa gần nhất. Lượt so sánh trước phải hoàn tất và hợp lệ.

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/check_invoice_test_browser.py
```

Bài này dùng PDF tổng hợp, Chrome thật, xuất nhãn và chấm một lỗi cố ý; không tải hoặc chạy model OCR thật và không dùng làm bằng chứng accuracy trên hóa đơn của bạn.

Kiểm chứng cập nhật ngày 26/10/2026: 53 test Python thuộc suite quality và 14 kiểm tra Chrome PASS (8 kiểm tra xuất/chấm/nhập/lưu nháp với fixture tổng hợp, 6 kiểm tra UI qua HTTP trên đủ 28 hồ sơ). Ảnh nhúng tải được khi mở qua HTTP; trang chỉ dựng một hóa đơn và một ảnh nguồn tại một thời điểm. Toàn bộ 32 trang thực đã được mở lại đối chiếu text/geometry/render và xem gallery sau tách; không coi các phép kiểm tách PDF hoặc UI là độ chính xác OCR.
