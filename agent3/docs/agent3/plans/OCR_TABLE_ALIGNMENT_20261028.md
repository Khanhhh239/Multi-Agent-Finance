# Ghép cột và dòng bảng hàng — 28/10/2026

## Phạm vi triển khai

Tiếp tục từ `invoice_extract_fix_20261027`, tập trung vào bảng mất trên trang 31
và mô tả/đơn giá lệch dòng trên trang 16. Không thay nhãn để sửa số liệu và không
chạy lại model OCR trong phép so sánh này.

- Nhận diện cặp tiêu đề thuế suất/tiền thuế bị OCR gộp thành một khối. Vị trí
  tách ước lượng chỉ dùng để dựng ranh giới cột; evidence và bbox nguồn giữ nguyên.
- Cho phép hai đoạn tiêu đề xuống dòng có bbox chồng nhẹ theo chiều dọc;
  không ghép các nhãn nằm ngang thành một tiêu đề xuống dòng.
- Bổ sung tiêu đề cột chiết khấu để số tiền không bị dồn sang cột thành tiền.
- Thêm `spatial_row_alignment.py`: dùng các ô thành tiền quan sát được làm mốc
  dòng cho bảng có số thứ tự, số lượng và đơn giá rõ ràng. Nếu không đủ điều kiện
  hình học/số mốc, giữ cơ chế trích xuất cũ.
- Ghép phần thập phân xuống dòng chỉ khi chữ số và dấu phân cách đều hiện diện,
  cùng cột và liền kề. Cột đơn giá đủ số ô mới được ghép theo thứ tự một-một;
  ô đơn giá thiếu không lấy số của dòng sau hay tính từ thành tiền/số lượng.
- Giữ số serial và mã hàng trong ngoặc ở mô tả liền trước khi có căn cứ về
  khoảng cách/đầu dòng. Loại tiêu đề dịch tiếng Anh và dòng đánh số cột khỏi dữ liệu.

## Bất biến

Các giá trị OCR như `B9.000`, `B%`, chữ số thiếu hoặc chuỗi không phân tích được
vẫn phải thiếu/mơ hồ, không được sửa theo nhãn hoặc phép nhân. Không tự điền số
lượng, thuế suất hay đặt trạng thái bảng đầy đủ chỉ vì tìm thấy nhiều dòng hơn.
ID block, tenant, nguồn, transform và evidence của giá trị vẫn thuộc tài liệu gốc.

Thay đổi áp dụng trong extractor dùng chung; các bản ghi đang chạy/đã được người
dùng xác nhận không được cập nhật trực tiếp. Lượt replay tạo artifact mới riêng,
SQLite baseline chỉ được đọc. Dữ liệu nguồn, nhãn và các báo cáo chứa nội dung hóa
đơn tiếp tục nằm ngoài Git.

## Kiểm tra

Thêm các regression tổng hợp: đơn giá thập phân và serial xuống dòng, đơn giá
thiếu, tiêu đề thuế bị gộp nhưng evidence không đổi, dòng đánh số cột, sản phẩm
có tên bắt đầu bằng serial ở dòng xa, tiêu đề dịch tiếng Anh không thành mô tả,
và ô tiền hỏng ở đầu bảng không làm dồn các dòng sau. Lệnh so sánh cũng có test
cho việc chấm lại cùng nhãn, nguồn/quan sát khác nhau và lượt trước chưa hoàn tất.

Lệnh đối chiếu dùng cùng nguồn/nhãn với lượt trước:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/replay_invoice_extraction.py --baseline-run invoice_test_20261026_100400_442193 --compare-run invoice_extract_fix_20261027 --labels invoice_test/labels_canonical_invoice_test_20261026_100400_442193.json --run-id invoice_extract_rows_20261028_v3
.\RUN_INVOICE_TEST.cmd score --run-id invoice_extract_rows_20261028_v3 --labels agent3_tax_compliance/data/ocr_quality/invoice_extract_rows_20261028_v3/labels.json
```

Nhãn vẫn DRAFT, chưa đầy đủ, trên bộ DEV đã dùng sửa lỗi; không phải holdout.
Chưa đo lại độ trễ OCR đầu cuối, không cho phép auto-accept hoặc tự nghiệm thu.

## Kết quả đối chiếu DEV

So với bản sửa ngày 27/10 trên cùng 28 hồ sơ và 706 ô nhãn:

| Chỉ số | Bản trước | Bản mới |
|---|---:|---:|
| Ô khớp nhãn | 489 | 535 |
| Ô điền sai | 42 | 43 |
| Ô thiếu/mơ hồ | 175 | 128 |
| Dòng hàng được tìm thấy | 48 | 57 |

Sai/thiếu giảm 21,20% so với bản trước; giảm 55,12% so với baseline gốc.
Không có trường trước đây đúng bị giảm chất lượng và không có WRONG_PRESENT
mới thuộc nhóm quan trọng. Mỗi hồ sơ có số dòng bằng nhãn DRAFT; không đồng nghĩa
tất cả nội dung dòng đã đúng. Trang 31 khôi phục 9 dòng, từ 9 lên 50/67 ô khớp;
trang 16 từ 17 lên 22/31 ô khớp. Không sửa các chữ số/thuế suất hỏng theo nhãn.

Nhãn chưa đầy đủ, chưa đo latency, và mức giảm lỗi của riêng vòng này dưới ngưỡng
30% trong bộ gate đang có: `technical_gate_passed=false`, `release_approved=false`.
Tổng ô điền sai tăng một ô khi dữ liệu trước đây thiếu được trích xuất; không gọi
đây là bản đã giải quyết toàn bộ lỗi OCR.

Suite trích xuất cuối: 81 test tổng hợp PASS. Bộ pilot cũ 15 biến thể / 9 nhóm
hóa đơn giữ nguyên số trường header đúng/sai, trong đó tổng tiền 44/44.
Báo cáo và ảnh riêng: `invoice_test/results/invoice_extract_rows_20261028_v3/`.
Đối chiếu bản trước: `agent3_tax_compliance/data/ocr_quality/invoice_extract_rows_20261028_v3/comparison_previous.json`.

## Xác nhận cuối

566 test Python PASS theo kết quả cuối; 81 test trong đó thuộc suite trích xuất.
Các kiểm tra cú pháp JavaScript, client Node và bốn runner Chrome đều PASS.
Kiểm tra HTTP riêng trên HTML mới qua sáu kiểm tra, tải được ảnh, chỉ dựng một
hồ sơ/ảnh tại một thời điểm, không có lỗi JavaScript hoặc tràn ngang màn hình.

Lượt kiểm tra rộng ban đầu ghi nhận hai lỗi và vẫn được giữ nguyên: regression
tiêu đề dịch trong mô tả và race của bài test chờ request đọc lại vùng ảnh. Đã
sửa, chạy lại toàn suite trích xuất và runner vùng ảnh; không bỏ qua assertion.
Runner vùng ảnh giờ đợi interception thực tế trong tối đa năm giây, thay vì xem
trạng thái nút bị vô hiệu hóa là bằng chứng request đã tới trình duyệt.

Metadata tổng hợp và log chạy lại: `agent3_tax_compliance/data/ocr_quality/validation_invoice_rows_20261028/verification_final.json`.
Báo cáo này tham chiếu cả log lỗi ban đầu lẫn lần chạy lại PASS và hash mã cuối.
