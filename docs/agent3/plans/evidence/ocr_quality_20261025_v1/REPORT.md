# OCR quality — 25/10/2026

Đã triển khai công cụ tiếp nhận/khóa dataset, benchmark pipeline thật, so sánh có
gate, đọc lại ô số/thuế và render lại vùng PDF gốc ở 300 DPI. Hướng dẫn chi tiết:
[OCR_QUALITY_IMPLEMENTATION](../../OCR_QUALITY_IMPLEMENTATION.md).

## Kiểm chứng kỹ thuật

- 13 suite chính: **534 test Python PASS**. Hai test hình học PDF mới chạy riêng
  sau khi suite ingestion đã khởi động; tổng **536 test khác nhau PASS**.
- Chạy lại riêng các test evaluation/runner/cache sau lần chỉnh cuối đều PASS;
  không cộng các lượt lặp vào tổng 536.
- **9 kiểm tra syntax JavaScript và 2 bộ kiểm thử client PASS**.
- Chrome thật, HTTP/SQLite tách biệt và recognizer double: **28 kiểm tra PASS**
  (13 region, 7 automation V2, 8 capture upgrade).
- Browser kiểm tra đọc ô số lớn và thuế suất 0% vào draft; nút PDF 300 DPI;
  cache, stale response, XSS, lưu revision, mobile và bảo vệ dữ liệu đã lưu.
- Hình học crop PDF được đối chiếu pixel với bản render toàn trang ở 300 DPI,
  bao gồm CropBox lệch gốc và bốn góc xoay. Hash, giới hạn pixel và timeout worker
  được kiểm tra; timeout render không gọi recognizer hoặc sửa CFR.

[Tổng hợp kiểm chứng và hash nguồn](validation_summary.json). Công cụ chạy lại:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_ocr_quality.py --run-id regression_moi
```

Validator ghi vào thư mục local mới, không ghi đè gate lịch sử. Checkout hiện
tại chạy đầy đủ sẽ bao gồm cả hai test PDF mới ngay trong suite ingestion.

## Model thật và dữ liệu dev

Hai lượt toàn pipeline trên **một hóa đơn pilot cũ và ảnh render của chính nó**,
không phải hai hóa đơn độc lập:

| Đầu vào | Nhánh thực tế | Trường đúng/có nhãn | Điền nhưng sai | Thời gian job |
|---|---|---:|---:|---:|
| PDF có lớp chữ | HYBRID | 9/11 | 0 | 322,58 giây |
| Ảnh render | OCR | 6/11 | 2 | 311,87 giây |

Các lượt chạy có tác vụ kiểm thử song song, nhãn là nhãn dev cũ. Không dùng các
số này để chứng nhận SLA hoặc accuracy tổng quát. Nguồn/model/config/runtime và
load/inference/peak memory được lưu trong run local; raw text, nhãn, ảnh và DB
không đưa vào Git.

Đọc một vùng ngày từ PDF gốc 300 DPI bằng VietOCR thật: CANDIDATE, parse VALID,
khớp nhãn dev, khoảng 30,77 giây gồm inventory. Trường này đã đúng trước đó nên
không tính là cải thiện accuracy. Lần thử trước có WORKER_TIMEOUT khi chạy nhiều
tác vụ; thử tổng tiền bị REGION_BUDGET vì hơn 4 vùng nguồn. Các guard được giữ,
không tăng timeout hoặc bỏ giới hạn để làm kết quả có vẻ đạt.

Replay extractor trên artifact OCR cũ: **15 biến thể/9 nhóm**, giữ kết quả trước
đợt này: MST 28/30; số/ký hiệu 29/30; ngày 14/15; tổng tiền 44/44; tên 22/30.
Replay không chạy inference mới và không cộng gợi ý đọc lại vào metric CFR.

## Trạng thái nghiệm thu

- Mẫu intake đã tạo tại `agent3_tax_compliance/data/ocr_quality/intake_20261025_v1/`.
- Chưa nhận đường dẫn bộ 30–50 hóa đơn mới; chưa có nhãn được reviewer độc lập
  xác nhận. Địa chỉ/mọi ô bảng chưa được nghiệm thu trên bộ nhãn đầy đủ.
- Gate giảm lỗi 30% và thời gian 180 giây chưa đạt nghiệm thu. So sánh với chính
  một run functional 3/3 trả không đạt đúng như thiết kế: không có mức giảm lỗi,
  không đủ mẫu thời gian và nhãn chưa đầy đủ.
- Chưa chọn recognizer mới, fine-tune, bật tự xác nhận hoặc đổi profile mặc định.
  Các cải tiến detector/binding tiếp theo phải dựa vào phân loại lỗi và oracle
  trên bộ dev mới; test khóa riêng theo nhóm nguồn/bố cục.
