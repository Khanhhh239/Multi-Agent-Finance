# Kế hoạch nâng độ chính xác OCR — vòng 3, 28/10/2026

Trạng thái: PROPOSED. Tài liệu này là kế hoạch; không đổi extractor, model mặc
định, nhãn hay dữ liệu capture. Tiếp nối các vòng sửa bố cục ngày 27–28/10 và
`PLAN_OCR_EXTRACTION_V2.md`, tận dụng các bộ đọc vùng/profile đã có.

## 1. Baseline và cách đọc số liệu

Baseline mới: `invoice_extract_rows_20261028_v3`, 28 hồ sơ, 706 ô nhãn DRAFT:
535 khớp nhãn (75,78%), 43 điền sai, 128 thiếu/mơ hồ. Tìm thấy 57 dòng hàng;
số dòng từng hồ sơ khớp nhãn hiện có. Chưa có đánh giá holdout hoặc latency mới.

| Nhóm | Khớp | Điền sai | Thiếu/mơ hồ | Ưu tiên |
|---|---:|---:|---:|---|
| Tên và địa chỉ người mua | 22 | 23 | 11 | Cao: có nhiều giá trị sai nhưng vẫn PRESENT |
| Tên và địa chỉ người bán | 36 | 10 | 10 | Cao: chữ, dấu, vai trò và nối dòng |
| Mô tả hàng | 48 | 9 | 0 | Đọc crop và giữ mã/serial chính xác |
| VAT treatment và rate của dòng | 50 | 0 | 64 | Kiểm tra phạm vi nhãn, rồi cột thuế |
| Số lượng, đơn giá, thành tiền dòng | 157 | 1 | 13 | Ưu tiên chữ số sai/không đọc được |
| MST, số/ký hiệu, ngày, tiền tệ, tổng tiền | 222 | 0 | 30 | Bảo vệ số đúng, xử lý thiếu có evidence |

64 ô VAT thiếu tương ứng hai đầu ra treatment/rate của 32 dòng, không phải
64 lần nhận dạng độc lập. Tên và địa chỉ bên mua có 34 ô lỗi; toàn bộ tên/địa
chỉ hai bên có 54 ô lỗi. Một lỗi nguyên nhân có thể ảnh hưởng nhiều đầu ra.

Các giả thuyết trong score chưa phải nguyên nhân đã chứng minh. Phải phân biệt
chữ không được detector tìm thấy, crop sai, recognizer đọc sai, gán nhầm trường,
normalization sai, phạm vi nhãn sai và nội dung thực sự không in trên tài liệu.

## 2. P0 — Khóa cách chấm và lập bản đồ lỗi

**Làm trước mọi thay đổi model.** Lưu hash baseline, nhãn, config/runtime/model và
mọi kết quả trung gian. Giữ nguyên báo cáo 706 ô để truy lại lịch sử.

Tạo sidecar `label_evidence.json` cục bộ, ràng buộc case/hash/field, có trang/vùng
nguồn, nội dung đọc tay, phạm vi `ROW_PRINTED`, `DOCUMENT_PRINTED`, `NOT_PRINTED`,
`UNREADABLE`, `INFERRED`, cùng trạng thái kiểm tra. Không đưa nhãn vào extractor.
Chỉ dùng dữ liệu đã đối chiếu ảnh để quyết định nguyên nhân và ưu tiên.

Đã xem ảnh nguồn: trang 11 không có cột thuế suất hàng, chỉ có 10% ở phần tổng;
trang 12 có cột VAT từng dòng và có cả 8%/10%. Do đó:

- Không tính việc giữ thiếu VAT hàng không được in là lỗi recognizer.
- Không lấy thuế suất cuối hóa đơn điền cho mọi dòng, nhất là hóa đơn nhiều mức.
- Tách chỉ số đọc nội dung in trực tiếp khỏi chỉ số nghiệp vụ suy ra từ cấp hóa
  đơn. Trường suy ra cần chính sách/evidence/trạng thái riêng và vẫn review.
- Nếu sửa nhãn/protocol, tạo phiên bản mới, ghi audit và chấm lại cả baseline
  lẫn candidate bằng cùng nhãn. Công bố mẫu số mới và số ô bị loại/đổi phạm vi;
  không đưa ô loại khỏi chấm thành ô OCR đúng hoặc trộn với tỷ lệ cũ 75,78%.

Đầu ra: inventory 171 ô gắn crop/evidence và nguyên nhân đã xác minh; bảng ưu
tiên theo số nguyên nhân độc lập, mức rủi ro và chi phí khắc phục. Có thể tự đối
chiếu để phát triển, ghi SELF_CHECK_NOT_INDEPENDENT theo kế hoạch V2 hiện hành.

## 3. P1 — Khôi phục cột VAT thực sự có in

Mẫu ưu tiên: trang 12–13, sau đó các hồ sơ có cột thuế bị mất. Kiểm tra raw native
text/OCR trước khi gọi model mới: tiêu đề Việt/Anh, bbox, ranh giới cột, phần trăm,
header lặp và trang tiếp nối. Giữ mức thuế riêng mỗi dòng, KCT/KKKNT đúng nghĩa.

Sửa trong extraction/layout khi chữ đã có mà chưa được gán. Chỉ đọc lại vùng
thuế nếu token mất/sai; ô không có chữ giữ thiếu. Không lấy kết quả nhân/chia tiền
để tạo ra thuế suất hoặc số tiền đã được coi là quan sát.

Kiểm tra tổng hợp: VAT hỗn hợp, VAT chỉ in cuối hóa đơn, ô VAT trống, ký hiệu
không chịu thuế, header song ngữ/tách dòng, cột tiền thuế sát cột rate, tiếp trang.
Điều kiện qua: các ô rate được khôi phục có evidence đúng dòng; không phát sinh
rate sai hoặc làm thay đổi ô đúng của vòng 28/10. Báo cáo rate/treatment ghép cặp
để không đếm một thành công hai lần trong đánh giá nguyên nhân.

## 4. P2 — Tên/địa chỉ và nối dòng theo vai trò

Tập trung 34 lỗi tên/địa chỉ người mua trước, sau đó bên bán và mô tả hàng.

- Xác định vùng người bán/người mua bằng tiêu đề và quan hệ hình học; hỗ trợ
  các biến thể nhãn thực tế có chứng cứ. Không lấy chuỗi gần nhất bên kia cột.
- Nối đầy đủ tên/địa chỉ xuống dòng, dừng ở nhãn mới, MST, điện thoại, tài khoản,
  bảng hoặc footer. Giữ dấu, dấu câu và mã hàng; không tự sửa tên theo từ điển.
- So sánh native text/OCR riêng. Khi cả hai cho giá trị khác nhau phải giữ ứng
  viên/xung đột; không chọn theo confidence detector như thể đó là accuracy.
- Tách trường hợp OCR thật sự đọc sai chữ/dấu để chuyển sang P3; không tiếp tục
  thêm alias nhằm che lỗi recognizer.

Điểm sửa: `invoice_fields.py`, phần dựng vùng/ứng viên và bộ đọc text vùng hiện
có. Test hai bên sát nhau, tên dài, nhiều dòng, số nhà, footer nhà cung cấp và
trường hợp OCR gán một số thuần túy thành tên doanh nghiệp.

## 5. P3 — Benchmark và đọc lại crop thực tế

Các vòng trước chỉ replay OCR đã lưu. P3 phải chạy nhận dạng thật trên crop lỗi
đã kiểm tra, gồm tên/địa chỉ dài, chữ có dấu, MST/số hóa đơn, số lượng, tiền và VAT.
Crop do server xác định từ nguồn/evidence; khi chưa có vùng đủ chắc chắn thì
đánh dấu cần định vị/review, không đọc cả trang rồi lấy số gần nhất.

Tận dụng các nhánh hiện có: `primary`, `expanded`, `pdf_detail` 300 DPI và
`vietocr_region_wide`. Profile wide hiện có width 1024 và beam search; không kết
luận width tốt hơn khi đồng thời đổi beam. Tạo thí nghiệm một biến mỗi lượt:

1. Baseline cùng model/crop hiện tại.
2. Chỉ thay padding/chỉnh crop nếu crop cắt chữ có bằng chứng.
3. Chỉ thay độ rộng hoặc tách dòng dài, giữ tỷ lệ ảnh và thứ tự phần nối.
4. Chỉ thay beam search.
5. Đọc vùng PDF từ nguồn 300 DPI; so với crop phóng từ ảnh cũ, không coi upscale
   ảnh mờ là khôi phục chi tiết đã mất.
6. Đối chứng recognizer khác đã đăng ký nếu các nhánh trên còn lỗi hệ thống.

Chọn 20–30 crop DEV đại diện để sàng lọc ban đầu, rồi mở rộng theo từng loại lỗi;
không coi đây là cỡ mẫu đủ để chứng minh tổng quát. Đo CER, đúng toàn chuỗi, đúng
trường, dấu tiếng Việt, wrong-present, p50/p95, RAM và số lần gọi model. Pin hash
crop, model, config và runtime; cùng nguồn/crop/nhãn cho từng đối chứng.

Chỉ promote nhánh có lợi đo được trên loại lỗi mục tiêu và không làm hỏng ô đúng.
Đổi model mặc định hoặc fine-tune là bước sau kết quả benchmark, không phải bước
đầu. Khi hai bộ đọc bất đồng, giữ mơ hồ; đồng thuận cũng không tự chứng minh đúng.

## 6. P4 — Tìm lỗi ở trường đã PRESENT và lập lịch recovery

`recovery/policy.py` hiện chủ yếu lên lịch khi thiếu/mơ hồ, lặp hậu tố, ký tự lỗi
hoặc xung đột nguồn; một tên đọc sai nhưng trông hợp lệ có thể không được phát
hiện. Bổ sung trigger có chứng cứ: crop chạm biên/cắt dòng, chuỗi số thuần túy ở
trường tên, native/OCR bất đồng, phần trăm/ký tự số không hợp lệ, và sai lệch các
phép kiểm tra tổng tiền. Kiểm tra số học chỉ phát hiện nghi vấn, không tạo đáp án.

Đánh giá recall của trigger trên lỗi đã biết và false-positive trên ô đúng; lấy
mẫu kiểm tra một phần trường PRESENT không bị trigger để tìm vùng mù. Nhãn chỉ
dùng đo hiệu quả offline, không quyết định lịch đọc trong production.

Giữ ngân sách hiện tại 2 trường/4 crop mỗi lượt làm baseline. Trường dài hơn bốn
block cần cơ chế đọc đủ các dòng qua lượt có cache/dedup và giới hạn tổng diện
tích/thời gian; không âm thầm chỉ đọc một phần tên hay tăng budget toàn cục.
Ưu tiên số định danh/tiền nghi vấn, rồi tên/địa chỉ và VAT hàng có chứng cứ thiếu.
Version policy/config; đo số field/crop được xử lý, bị hoãn và chi phí recovery.

Ứng viên mới không ghi đè CFR. HUMAN_CONFIRMED được bảo vệ; người dùng xác nhận
tạo revision/audit. Không bật auto-accept hoặc suy ra độ tin cậy từ detection.

## 7. P5 — Kiểm chứng và nghiệm thu

Sau mỗi gói: test subsystem bị ảnh hưởng; replay cùng frozen OCR để tách hiệu quả
extraction khỏi recognizer; benchmark nhận dạng thật khi đổi crop/model; so sánh
cả baseline gốc lẫn `--compare-run invoice_extract_rows_20261028_v3`.

Theo dõi riêng: nhận diện chữ, gán trường, số dòng, ô số, VAT từng dòng, đúng cả
hóa đơn, wrong-present và tỷ lệ cần review. Không chỉ đo tỷ lệ ô được điền. Không
đổi nhãn/split, runtime hoặc crop giữa hai ứng viên mà không ghi nhận/chấm lại.

Gate phát triển dự kiến:

- Không phát sinh wrong-present ở nhóm quan trọng, không làm hỏng ô trước đây
  đúng trên tập regression, không giảm chất lượng bảng/địa chỉ.
- Với protocol đã audit và mẫu số cố định, đặt mục tiêu DEV >=90% field exact
  match như mục tiêu thử nghiệm, không cam kết trước khi P0/P3 hoàn tất.
- Lỗi được sửa không đổi thành giá trị suy đoán. Mọi thay đổi còn evidence đúng
  tenant/nguồn/dòng và được audit; không ghi đè giá trị đã xác nhận.
- Có đo latency đầu cuối trên workload kiểm soát và ngân sách model đã chốt;
  replay không được dùng làm số latency OCR.

Chuẩn bị bộ mới chưa dùng sửa lỗi, ưu tiên 100–200 hóa đơn đa nguồn/nhà cung cấp/
layout và chất lượng ảnh như mục tiêu thu thập ban đầu. Bao gồm PDF text, scan,
ảnh chụp, nhiều trang, nhiều mức thuế. Chia theo hóa đơn/nguồn/layout; không chia
ngẫu nhiên trang của cùng PDF vào DEV và test. Nếu chưa có bộ này, báo chưa đánh
giá holdout và tiếp tục dùng review; không gắn nhãn accuracy production.

Khóa candidate/config trước khi mở test. Báo cáo mẫu số, các nhóm chất lượng,
tỷ lệ đúng/sai và độ bất định; thấy 0 lỗi trên mẫu nhỏ không có nghĩa chính xác
100%. Bộ test đã mở để sửa phải chuyển thành DEV, thay bằng bộ chưa dùng khác.

## 8. Thứ tự triển khai và sản phẩm bàn giao

1. P0: inventory có crop + audit phạm vi nhãn, baseline/protocol phiên bản mới.
2. P1: VAT có in theo dòng, kèm regression và báo cáo trước/sau.
3. P2: gán vai trò/nối tên-địa chỉ, giữ riêng lỗi recognizer chuyển sang P3.
4. P3: benchmark crop thật và cấu hình thắng theo nhóm trường.
5. P4: trigger/recovery có giới hạn và đo false-positive/chi phí.
6. P5: chạy cuối, HTML review mới, bảng so sánh có mẫu số cố định, báo cáo DEV/
   holdout/latency tách riêng, cấu hình có thể rollback.

P0–P2 có thể dùng dữ liệu hiện tại để phát triển. P3 cần môi trường/model có sẵn
và thời gian inference thực tế. P5 cần bộ hóa đơn mới; không trì hoãn sửa lỗi
hiện tại chỉ vì chưa có holdout, nhưng cũng không dùng DEV để tuyên bố nghiệm thu.
