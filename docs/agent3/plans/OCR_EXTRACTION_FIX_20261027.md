# Sửa phân tách và trích xuất hóa đơn — 27/10/2026

## Thay đổi

- Chỉ nhận số hóa đơn đúng định dạng; loại nhãn `Số` của cột số lượng trong
  vùng tiêu đề bảng. Hai số hóa đơn khác nhau thật sự vẫn dẫn đến `REVIEW_SPLIT`,
  kể cả khi hóa đơn thứ hai nằm dưới bảng của hóa đơn thứ nhất trên cùng trang.
- Ghép tiêu đề cột xuống dòng trong phạm vi hình học giới hạn; hỗ trợ khoảng trắng
  OCR bị mất, cột `SL`, tiêu đề số lượng, thành tiền và thuế suất tách nhiều dòng.
  Mỗi giá trị vẫn giữ tham chiếu block/evidence gốc.
- Đọc tổng tiền theo bộ ba tiêu đề tiền hàng/thuế/thanh toán gần nhất, giữ thứ tự
  cột khi số căn phải, loại cột chiết khấu đứng trước và giữ các tổng mâu thuẫn
  dưới dạng `AMBIGUOUS`. Không suy ra tiền thuế hoặc tự sửa số bằng phép tính.
- Giữ dòng có số thứ tự, số lượng và đơn giá quan sát được dù ô thành tiền
  không đọc được; ô lỗi vẫn thiếu. Loại công thức đánh số cột, dòng tổng hợp thuế
  khỏi bảng hàng; giữ ngày tháng xuống dòng trong mô tả dịch vụ.
- Thêm `scripts/replay_invoice_extraction.py`: tạo artifact mới từ OCR đã lưu,
  đọc SQLite nguồn ở chế độ chỉ đọc, kiểm tra hash payload và định danh tenant/
  hồ sơ/nguồn, đóng băng nhãn và so sánh cùng tập trường với baseline.

## Cách chạy lại

Từ thư mục gốc PowerShell, chọn run ID chưa tồn tại:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/replay_invoice_extraction.py --baseline-run invoice_test_20261026_100400_442193 --labels invoice_test/labels_canonical_invoice_test_20261026_100400_442193.json --run-id invoice_extract_my_fix_002
.\RUN_INVOICE_TEST.cmd score --run-id invoice_extract_my_fix_002 --labels agent3_tax_compliance/data/ocr_quality/invoice_extract_my_fix_002/labels.json
```

Hướng dẫn đầy đủ: [INVOICE_TEST_RUNBOOK.md](INVOICE_TEST_RUNBOOK.md).
Ảnh, nhãn và SQLite chỉ nằm trong thư mục dữ liệu bị Git bỏ qua.

## Giới hạn

Đây là đánh giá DEV trên dữ liệu đã dùng để sửa lỗi, với nhãn `DRAFT`,
`complete=false`. Replay giữ nguyên OCR đầu vào, không gọi model và không đo
latency OCR đầu cuối. Không dùng các tỷ lệ bên dưới làm độ chính xác trên bộ
holdout độc lập hoặc bằng chứng cho auto-accept. Các bài kiểm tra tổng hợp được
báo cáo riêng với số liệu đối chiếu trên hóa đơn thực tế.

Các trường hợp OCR đọc sai tên, địa chỉ, mô tả hoặc chữ số vẫn cần xử lý ở lớp
nhận dạng/crop tiếp theo; bản sửa không lấy nhãn làm giá trị đầu vào của extractor.


## Kết quả và bằng chứng

Mở [trang đối chiếu mới](../../../invoice_test/results/invoice_extract_fix_20261027/review.html)
để xem từng ô cùng ảnh nguồn.

| Chỉ số trên cùng 28 hồ sơ / 706 ô nhãn | Baseline | Bản sửa |
|---|---:|---:|
| Ô khớp nhãn | 325 (46,03%) | 489 (69,26%) |
| Ô điền sai | 40 | 42 |
| Ô thiếu hoặc mơ hồ | 341 | 175 |
| Dòng hàng được tìm thấy | 23 | 48 |
| Hồ sơ bị REVIEW_SPLIT | 5 | 0 |

Số lỗi sai/thiếu giảm 381 → 217 (43,04%). Không có ô WRONG_PRESENT mới thuộc nhóm quan trọng; các tổng thuế sai trên trang 7, 9 và 15 đã được sửa. Tổng số ô điền sai vẫn tăng 40 → 42 khi các hồ sơ trước đây bị chặn được mở lại; bản sửa chưa giải quyết toàn bộ lỗi.

Nhãn có 57 dòng hàng; trang 31 còn mất bảng 9 dòng do OCR tiêu đề và nội dung lỗi. Trang 16 có mô tả/đơn giá lệch dòng cần sửa tiếp. Các ô chưa đọc rõ vẫn giữ thiếu hoặc mơ hồ, không được bù bằng nhãn hay phép tính.

Đánh giá này dùng cùng ảnh và quan sát OCR đã lưu, không chạy lại model. Nhãn là DRAFT/không đầy đủ, dữ liệu DEV đã dùng sửa lỗi, chưa đo latency đầu cuối: release_approved=false; không tự chấp nhận kết quả hoặc coi đây là accuracy holdout.

Baseline, nhãn gốc và SQLite nguồn không bị sửa. Bản sao nhãn đã chuẩn hóa định dạng thuế suất, ngày và mã số thuế, có audit riêng; cả hai bản được chấm bằng cùng nhãn.

Đã qua 71 test trích xuất tổng hợp trên mã cuối. Lượt kiểm tra rộng hơn trước bước siết vùng nhãn/cột cuối đã qua 550 test Python, JavaScript và 4 runner Chrome. Bộ pilot cũ 15 biến thể / 9 nhóm hóa đơn giữ nguyên số trường header đúng/sai, trong đó tổng tiền vẫn 44/44. Các số liệu này không phải holdout độc lập.

Báo cáo: invoice_test/results/invoice_extract_fix_20261027/. Hash nguồn và metadata: agent3_tax_compliance/data/ocr_quality/invoice_extract_fix_20261027/report.json.
