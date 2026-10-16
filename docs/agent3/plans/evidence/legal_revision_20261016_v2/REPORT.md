# Cập nhật căn cứ và kiểm thử nghiệp vụ — 16/10/2026

Phạm vi: thực hiện bước 1–3 sau khi chuẩn bị corpus PLAN_12, củng cố dữ liệu PLAN_07–09. Đây là bản kỹ thuật DRAFT, chưa nghiệm thu pháp lý, chưa triển khai PLAN_14 hay mở auto-accept. Nhánh OCR V2 vẫn thuộc PLAN_06.

## 1. Đã bổ sung và sửa gì

| Phần | Kết quả | Giới hạn |
|---|---|---|
| NĐ 123/2020 | Đối chiếu Điều 10 khoản 4 và một phần ngoại lệ khoản 14 trên PDF gốc; thêm trích đoạn runtime | Model nội dung chỉ kiểm tra sự hiện diện MST bên bán, không kiểm tra toàn bộ Điều 10 |
| NĐ 70/2025 | Đối chiếu phần sửa Điều 10 tại Điều 1 khoản 7 và ngoại lệ được trích | Không suy ngoại lệ MST bên mua thành ngoại lệ MST bên bán |
| NĐ 359/2025 | Sửa quan hệ văn bản: bổ sung khoản 1b Điều 4, bãi bỏ khoản 3 Điều 37 và khoản 3 Điều 39 của NĐ 181 | Không dùng làm căn cứ sửa Điều 26; bỏ mốc tách payment giả tạo 01/01/2026 |
| NĐ 174/2025 | Chỉ mục native text + vị trí từ cho 73 trang phụ lục, trang PDF 5–77; trích đầy đủ Phụ lục II theo hai giai đoạn | Chưa duyệt từng hàng của toàn bộ phụ lục, chưa mapping mã hàng doanh nghiệp |
| Corpus runtime V2 | 21 trích đoạn từ 8 văn bản, đủ locator đã chọn cho 7/7 rule versions mới | Coverage locator không có nghĩa đủ tất cả điều kiện thuế |

Nguồn chính: [NĐ 123 PDF](https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/10/123.signed_01.pdf), [NĐ 70 PDF](https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/3/70-nd-cp.signed.pdf), [NĐ 359 Công báo](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-359-2025-nd-cp-468511.htm), [NĐ 174 PDF Công báo](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2025/6/45374/57334-1-2025895-896174-2025-nd-cp.pdf). URL/hash từng văn bản nằm trong registry; trang, text hash và giới hạn trích dẫn nằm trong corpus. Source bytes được kiểm tra SHA-256 trước khi build.

## 2. Phiên bản và thời gian

- Registry `legal-registry-20261016-v2`, ruleset `technical-draft-ruleset-20261016-v2`, model package `technical-draft-20261016-v2`, corpus `legal-excerpts-20261016-v2`.
- Nội dung hóa đơn: ba giai đoạn 01/07/2022, 01/06/2025, 01/07/2026. NĐ 123/70 và TT 32 có mốc kết thúc registry 01/07/2026.
- Thanh toán: hai giai đoạn trước/từ 20/06/2026 theo NĐ 144. Chỉ hỗ trợ trường hợp STANDARD, không giả quyết định cho trả chậm/trả góp hoặc trường hợp đặc thù.
- VAT giảm thuế: tách 2025/2026 theo Phụ lục II. Chỉ kiểm tra 8% khi phương pháp DEDUCTION, treatment TAXABLE_RATE và có phân loại REDUCTION_CANDIDATE độc lập, được duyệt. 10% trong trường hợp chưa được phân loại không tự bị kết luận sai.
- Hạn hỗ trợ kỹ thuật hiện tại: **đến hết 16/10/2026**, biểu diễn `supported_to = 2026-10-17` exclusive. Đây là hạn rà soát dữ liệu, không phải ngày luật hết hiệu lực. NĐ 174 có mốc hết giai đoạn 01/01/2027 exclusive.
- Ngày thiếu, ngoài cửa sổ hoặc chưa có version phải dừng chọn rule; không lấy bản mới nhất thay thế.

Các tên file `*_v1.json` trong registry và `models/manifest.json` hiện là compatibility head để giữ nguyên loader đã pin. Nội dung chứa version V2 rõ ràng, có bản snapshot tên ngày riêng. V1 được lưu nguyên byte tại `rules/registry/versions/20261014-v1/`, kèm byte pins. Core planning/rules/orchestration không đổi mã nguồn; report cũ giữ snapshot và replay riêng.

Contract hiện tại chỉ có invoice kind VAT/SALE/OTHER, chưa mô hình hóa subtype hóa đơn đặc thù. Vì vậy không dùng một enum tưởng tượng để tuyên bố đã xử lý mọi ngoại lệ. Tất cả model thật vẫn DRAFT; cần bổ sung xử lý subtype và phê duyệt trước khi cho chạy nghiệp vụ thật.

## 3. Kiểm thử bước 3

Các tình huống dùng chứng từ tổng hợp và bản sao model chỉ được promote trong bộ nhớ của test; không publish phê duyệt giả vào registry.

| Tình huống | Kết quả mong đợi |
|---|---|
| Ngày trước/đúng mốc thay luật, tất cả ngày được hỗ trợ | Chọn đúng một version, không gap/overlap |
| Thiếu ngày, trước cửa sổ, từ 17/10/2026 | Không chọn latest |
| DRAFT thực tế | Không gọi engine, không phát PASS/FAIL thuế |
| Có MST / nguồn đầy đủ xác nhận thiếu MST | Native ZEN trả PASS/FAIL cho đúng check hiện diện |
| OCR trống hoặc thiếu bằng chứng xác nhận vắng mặt | REVIEW hoặc cần input; không tự FAIL pháp lý |
| 4.999.999 / 5.000.000 / 5.000.001 VND | Áp dụng ngưỡng bao gồm 5 triệu; dưới ngưỡng cần ledger đủ |
| 3 triệu + 2 triệu cùng người bán/ngày | Cộng theo nhóm; khác người bán/ngày không cộng |
| Ledger thiếu hoặc sai revision | UNKNOWN |
| Thanh toán SPECIAL, ngoại tệ, số âm | UNKNOWN trong MVP này |
| Bằng chứng non-cash đúng phạm vi và true/false | Native ZEN PASS/FAIL cho check tương ứng |
| Bằng chứng thiếu, sai taxpayer, revision hoặc record hash | Từ chối bind engine context |
| VAT 8%/10% với phân loại độc lập trong fixture | Native ZEN PASS/FAIL theo check giảm thuế |
| VAT 8% không có phân loại, taxonomy thật chưa duyệt | UNKNOWN, không suy nhóm pháp lý từ rate |
| KCT/KKKNT hoặc phương pháp DIRECT | Ngoài phạm vi check giảm thuế 8%, không ép thành số |
| MST sai định dạng, quality cũ | Contract/gate từ chối trước engine |
| Report V1 và V2 cùng tồn tại | Replay cả hai, report V1 không đổi |

Số kiểm thử và kết quả thực chạy: [validation_summary.json](validation_summary.json). Browser trên Chrome thực: [browser_explanation.json](browser_explanation.json), [browser_compliance.json](browser_compliance.json). Browser dùng invoice tổng hợp và provider giả lập cho LLM; không phải suy luận Qwen thật hoặc đo độ chính xác thuế thực tế.

## 4. Chạy lại và việc còn lại

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_legal_revision_v2.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/validate_legal_revision_v2.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/check_explanation_browser.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/check_compliance_browser.py
```

Builder cần các PDF cache local đã khớp source pin tại `agent3_tax_compliance/data/plan12_legal_corpus/sources`; không tự lấy nguồn khác thay thế khi hash lệch. Các script corpus V1 đọc archive V1 để giữ kết quả lịch sử. Evidence cũ là snapshot lịch sử, không dùng làm trạng thái hiện tại.

Trước nghiệm thu nghiệp vụ: duyệt mapping hàng thật và ngoại lệ theo từng family, xác nhận các rule/check đúng phạm vi, mở rộng case thực được phép sử dụng, duyệt corpus/retrieval độc lập, cập nhật cửa sổ nguồn khi rà soát tiếp. Model Qwen chưa được bật. Bản này không thay thế các công việc đó bằng số lượng test kỹ thuật.
