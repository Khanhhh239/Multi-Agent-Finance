# Cải thiện OCR — vòng triển khai 25/10/2026

Tiếp tục OCR/extraction V2 trong PLAN_06. Mục tiêu là đúng và đủ với review,
chạy local, p95 khoảng 180 giây/trang scan/ảnh. Chưa thay model hoặc bật auto-accept.

## Đã triển khai

- `scripts/ocr_quality.py`: tạo mẫu tiếp nhận, khóa dataset, chạy pipeline capture thật trên DB riêng từng case và so sánh baseline/candidate. Cả PDF text, scan và ảnh đều đi qua ingestion/routing/OCR/extraction/quality hiện hành. Không dùng lại cache từ DB người dùng.
- Manifest giữ SHA-256 nguồn và nhãn, loại đầu vào, nhóm hóa đơn/nguồn/bố cục và dev/test. Cùng nhóm hoặc cùng nội dung không được nằm hai split; pilot cũ và hash file pilot không thể được đổi tên thành test. Khuyến nghị khoảng 60/40 theo **nhóm**, không chia ngẫu nhiên từng trang. Không tự suy nhà cung cấp/bố cục từ tên file.
- Nhãn chứa thông tin hai bên, số/ký hiệu/ngày, tiền tệ, tổng tiền, địa chỉ và từng ô bảng. Chuỗi Decimal được so chính xác; tên giữ phân biệt hoa/thường sau NFC/khoảng trắng. Ô chưa gán nhãn phải bỏ khỏi mapping, không dùng `null`: `null` nghĩa người gán nhãn đã xác định không in trường đó.
- Chấm đúng/sai/thiếu-mơ hồ, sai nhưng được điền, số dòng và toàn hóa đơn. Chỉ chấm toàn hóa đơn khi `complete=true` và đủ mọi trường/ô; dòng thừa hoặc thiếu làm toàn hóa đơn sai. Các dòng nhãn phải theo thứ tự in. Khi lệch hàng, metric cố ý không ghép theo tên để che lỗi cấu trúc.
- Báo cáo thời gian job, OCR theo trang, load/inference, vòng đời worker và peak memory khi sandbox cung cấp. Timeout/lỗi vẫn nằm trong mẫu số; OCR chưa đủ trang không được coi thành công. Không gọi thời gian OCR thuần là end-to-end. Gate p95 end-to-end chỉ xét job một trang scan/ảnh, cần ít nhất 20 nhóm hóa đơn; nhiều trang báo riêng, chưa chứng nhận SLA.
- Error inventory giữ giả thuyết kèm candidate/issue/block, không tự kết luận thiếu detection hay recognizer sai khi chưa có crop/text oracle đối chiếu. Artifact chi tiết và DB chỉ nằm ở `agent3_tax_compliance/data/ocr_quality/`, đã được gitignore.
- Đọc lại vùng cho số lượng, đơn giá, thành tiền, nhóm thuế và thuế suất qua API/UI hiện có. Dùng evidence đúng ô hoặc lỗi parse của ô; không mượn vùng của cột bên cạnh khi thiếu evidence. Giữ Decimal, không nối hai giá trị số cạnh tranh và không đoán `%` bị thiếu.
- Hàng đợi ưu tiên MST, số hóa đơn và tổng tiền trước các ô bảng để hai lượt đọc tự động không bị các đường dẫn `items.*` chiếm hết; ngân sách 2 field/4 crop được giữ nguyên.
- KCT/KKKNT giữ khác thuế suất 0%. Bổ sung block refs cho VAT parse lỗi để có thể đọc lại. Gợi ý vẫn vào draft qua người dùng, lưu bằng correction service; sửa nhóm thuế/rate phải đáp ứng kiểm tra nhất quán hiện có.
- Policy đọc vùng lên `region-fields-v3`, chẩn đoán lên `recovery-policy-v3`, cache gắn implementation mới. Request API cũ vẫn dùng được, không migration DB và không sửa CFR lịch sử.
- Nút **Đọc vùng PDF rõ hơn** dùng `reader=pdf_detail`: render lại crop từ PDF gốc ở 300 DPI trong subprocess có timeout/RAM, tối đa 1M pixel/crop và 2M pixel/lượt. Kiểm tra hash nguồn, giữ evidence gốc cùng clip/DPI/rotation trong observation; PDF xoay được kiểm tra bằng đối chiếu pixel. Không tự dùng cho ảnh chụp hoặc bật trong hàng đợi tự động. PDF scan chỉ có thể khai thác độ phân giải ảnh nhúng sẵn có, không tạo lại chi tiết bị mất.

Đọc PDF rõ hơn vẫn chịu kiểm tra tối đa 4 vùng nguồn, cùng trang/dòng phù hợp.
Trường có quá nhiều fragment hoặc vùng chồng lấn giữ yêu cầu review; không gộp
các box tùy tiện để vượt ngân sách. Thử tổng tiền trên một PDF dev bị chặn đúng
vì hơn 4 vùng nguồn; không gọi đây là lượt OCR thành công.

## Cách chạy

Từ `D:\financial`, dùng Python của app. Mọi `run-id` là tên mới, không ghi đè run cũ.

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/ocr_quality.py template --run-id intake_v1
```

Điền file `agent3_tax_compliance/data/ocr_quality/intake_v1/intake.json` bằng nguồn
được phép dùng trong workspace. Tham khảo `label_fields.json` cạnh đó. Chọn
`pdf_text`, `pdf_scan` hoặc `photo` theo **đầu vào thực tế**; ảnh render của PDF
không phải ảnh chụp mới. Khai báo cùng `group_id` cho các biến thể cùng hóa đơn;
cùng `source_group`/`layout_group` phải ở cùng split. Mẫu mặc định không có nhãn,
không tự đưa kết quả OCR làm ground truth.

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/ocr_quality.py seal --input agent3_tax_compliance/data/ocr_quality/intake_v1/intake.json --run-id dataset_v1
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/ocr_quality.py run --manifest agent3_tax_compliance/data/ocr_quality/dataset_v1/manifest.json --run-id baseline_v1
# Sau khi sửa trên dev, chạy cùng manifest với run-id candidate_v1.
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/ocr_quality.py compare --baseline agent3_tax_compliance/data/ocr_quality/baseline_v1/report.json --candidate agent3_tax_compliance/data/ocr_quality/candidate_v1/report.json --run-id compare_v1
```

`run` hỗ trợ `--config <OCRConfig.json>` và `--render-dpi 150|200|300` cho thí nghiệm;
giữ trần pixel hiện hành. 300 DPI có thể bị từ chối vì vượt ngân sách, không tự nâng trần.
Thời gian worker/retry lấy từ config và được ghi lại; mục tiêu 180 giây là gate
đánh giá, không âm thầm đổi timeout production để khiến mẫu khó biến mất.
Chỉ thêm `--dedicated-machine` khi máy không chạy kiểm thử/inference/tác vụ nặng
khác; nếu không có điều kiện này gate thời gian không thể PASS. Các run dở dang
hoặc hash nguồn thay đổi trước khi kết thúc bị từ chối khi so sánh.

Chỉ mở test sau khi khóa candidate:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/ocr_quality.py run --manifest agent3_tax_compliance/data/ocr_quality/dataset_v1/manifest.json --split test --open-test --run-id test_v1
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_ocr_quality.py --run-id regression_v1
```

Nếu dùng lỗi test để sửa tiếp, coi bộ đó là dev và thu test mới. Công cụ ghi
split/code/config/hash từng run; không thể tự biết coder đã nhìn một tài liệu
ngoài công cụ. Trách nhiệm khai báo `used_for_tuning` và nhóm nguồn phải được giữ.

`pilot-intake --run-id pilot_intake_v1` tạo intake **dev** từ pilot cũ (kèm ảnh
render tương quan, được đánh dấu `derived_render`), chỉ phục vụ smoke/hồi quy.

## Gate và công việc còn chờ dữ liệu

So sánh chỉ chấp nhận cùng manifest/split/case/nhãn. Gate kỹ thuật yêu cầu giảm
ít nhất 30% lỗi trường, không phát sinh WRONG_PRESENT mới ở MST/số hóa đơn/tổng
tiền, không giảm ô bảng/địa chỉ hoặc mất đúng số dòng, không lỗi xử lý và đạt gate
thời gian. Nhãn phải đầy đủ header/địa chỉ/mọi ô bảng để gate kỹ thuật có thể đạt;
không coi phần chưa gán nhãn là không có lỗi. Các gate chưa đủ mẫu giữ pending;
lệnh compare trả exit 1 khi chưa đạt.
`release_approved` luôn false: người phụ trách phải xem kết quả và hồi quy trước
khi đổi cấu hình mặc định.

Chưa có 30–50 hóa đơn mới hoặc reviewer độc lập. Nhãn pilot là DRAFT. Do đó chưa
thể nghiệm thu mục tiêu giảm lỗi, chứng nhận accuracy hoặc chọn model mới trên
dữ liệu độc lập. Đợt này không giả lập holdout, không coi test synthetic là OCR
accuracy và không tuyên bố hoàn tất toàn bộ 10–15 ngày công của kế hoạch.

Khi có dữ liệu: xác nhận nhãn bằng người nghiệp vụ (review_status VERIFIED cùng
reviewer), khóa manifest mới, phân loại 10–20 lỗi, chạy oracle crop cắt tay/text
đã sửa bằng các công cụ OCR V2 hiện có. Chỉ thực hiện nhánh detector/crop,
recognizer hoặc binding/bảng được phép đo chỉ ra. Đọc vùng PDF 300 DPI hiện là
lựa chọn thủ công, cần đo lợi ích trước khi dùng tự động. Fine-tune chưa triển khai.
