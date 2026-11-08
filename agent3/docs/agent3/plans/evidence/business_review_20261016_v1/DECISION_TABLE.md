# Bảng quyết định nghiệp vụ — bản kỹ thuật 16/10/2026

Bảng này định nghĩa phạm vi chuẩn bị đầu vào cho ba check hiện có của PLAN_09. Không phải bảng đủ điều kiện khấu trừ thuế hay toàn bộ nội dung bắt buộc của hóa đơn. `READY_FOR_TECHNICAL_CHECK` nghĩa là đủ đầu vào cho một check hẹp; planner vẫn kiểm quality, phiên bản, nguồn và publication. Không có tax verdict ở endpoint readiness.

## Điều kiện chung

| Điều kiện | Hành vi |
|---|---|
| Thiếu ngày lập hoặc ngày không đáng tin cậy | Không chọn latest; cần review |
| Ngoài cửa sổ rule, hiện đến hết 16/10/2026 | Không chọn version; cần cập nhật registry có nguồn |
| Dossier khác tenant, taxpayer, record, revision hoặc hash | Từ chối |
| File chứng cứ khác SHA-256 hoặc đường dẫn thoát evidence root | Từ chối nhập |
| Reviewer khác actor đăng nhập / không có WRITE | Từ chối nhập |
| Hóa đơn đã sửa | Dossier cũ vẫn lưu lịch sử nhưng không dùng cho revision mới |
| Rule DRAFT hoặc taxonomy chưa duyệt | Không mở execution thật dù readiness đủ input |

## 1. Nội dung hóa đơn — chỉ kiểm tra hiện diện MST người bán

| Trường hợp | Chuẩn bị | Giới hạn |
|---|---|---|
| VAT thông thường, đủ toàn bộ tài liệu, reviewer xác nhận MST có mặt, CFR/quality nhất quán | Observation PRESENT_VALUE | Check hiện diện có thể chạy khi rule được duyệt |
| VAT thông thường, đủ tài liệu, reviewer xác nhận thiếu; CFR thật sự MISSING | Observation CONFIRMED_ABSENT | Có cơ sở kiểm check thiếu MST; không lấy OCR trống làm xác nhận |
| CFR AMBIGUOUS, OCR bỏ sót, tài liệu chưa đầy đủ, xác nhận mâu thuẫn | Cần review, không sinh observation hợp lệ | Không FAIL vì OCR không thấy |
| SPECIAL/UNKNOWN form | Cần xác định ngoại lệ; không bind invoice kind vào check thông thường | Chưa thực thi ngoại lệ hóa đơn đặc thù |
| SALE/OTHER đã xác nhận | Ngoài phạm vi check VAT này | Không đồng nghĩa hóa đơn hợp lệ hoặc không cần MST |

Căn cứ nguồn đã pin: NĐ 123 Điều 10 khoản 4 / một phần khoản 14; NĐ 70 Điều 1 khoản 7; từ 01/07/2026 NĐ 254 Điều 10 cùng phần dẫn chiếu ngoại lệ. Ngoại lệ thông tin **người mua** không được dùng để miễn thông tin **người bán**. Các ngoại lệ ngoài phần đã trích cần đối chiếu tiếp, không mở rule cho chúng.

## 2. VAT giảm thuế — phân loại độc lập trước khi nhìn rate

| Trường hợp | Phân loại / hành vi |
|---|---|
| Có hồ sơ sản phẩm độc lập; base rate 10%; đã đối chiếu ngữ cảnh pháp luật; không thuộc cả Phụ lục I và II đúng giai đoạn; DEDUCTION + TAXABLE_RATE | REDUCTION_CANDIDATE cho **item_id và revision đã review** |
| Cùng phân loại trên nhưng in 8% | Đủ input cho check 8%; không suy ngược phân loại từ rate |
| Cùng phân loại trên nhưng in 10% | Gắn bất nhất `RATE_DIFFERS_FROM_SCOPED_EIGHT_PERCENT`; check ZEN có thể FAIL khi đã duyệt phạm vi |
| Thuộc Phụ lục I hoặc II | REDUCTION_EXCLUDED, ngoài check giảm 8%; không tự kết luận phải 10% |
| Base rate 5%, 0% hoặc mức khác 10% | Ngoài check giảm 8% này |
| KCT/KKKNT | Giữ treatment đặc biệt; không ép thành rate số |
| DIRECT | Ngoài check rate 8% theo phương pháp khấu trừ; chưa triển khai giảm tỷ lệ trên doanh thu |
| Thiếu catalogue/hợp đồng, chỉ có hóa đơn hoặc tên hàng | Cần review; không đoán bằng keyword, HS hoặc rate đã in |
| Một trong hai phụ lục UNKNOWN hoặc legal_context_checked=false | Cần review |
| Hồ sơ phân loại không đúng ngày / đi qua 01/01/2026 mà không tách | Từ chối hoặc cần review theo trường hợp |

Căn cứ: [NĐ 174 Công báo gốc](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2025/6/45374/57334-1-2025895-896174-2025-nd-cp.pdf), Điều 1 khoản 1–2; Phụ lục I trang PDF 5–72, II trang 73–75. Giai đoạn II/2025 khác II/2026. Cần xét ghi chú phụ lục, bản chất hàng hóa và hiệu lực luật thuế liên quan; không phân loại đồ uống hay điều hòa chỉ bằng tên gọi. Thời hạn giảm thuế theo văn bản khác với cửa sổ rà soát kỹ thuật của hệ thống.

Hiện đây là mapping theo từng dòng chứng từ, **chưa có danh mục SKU thật để duyệt và tái sử dụng xuyên hóa đơn**. Product code được lưu làm tham chiếu, không tự tái áp kết quả cho một item khác. Taxonomy toàn cục vẫn chưa được promote.

## 3. Thanh toán — điều kiện áp dụng và chứng cứ tách riêng

| Trường hợp | Hành vi |
|---|---|
| STANDARD, mua vào/khấu trừ, một hóa đơn VND ≥5 triệu gồm VAT | Planner xét áp dụng yêu cầu chứng cứ |
| Dưới 5 triệu, ledger đầy đủ, tổng cùng người bán/ngày ≥5 triệu | Planner xét áp dụng theo nhóm |
| Dưới 5 triệu, ledger đầy đủ, tổng nhóm <5 triệu | Ngoài phạm vi check chứng cứ theo ngưỡng này |
| Dưới 5 triệu, ledger thiếu hoặc không xác nhận đầy đủ | UNKNOWN; không kết luận miễn điều kiện |
| Ledger có hóa đơn sai tenant, sai revision/hash hoặc dữ liệu khác bản đã lưu | Từ chối; kiểm lại cả khi đọc readiness |
| Bank statement đã đối chiếu thực hiện, đúng hai bên, VND, thanh toán đủ và khớp gross | Sinh PaymentProof true |
| Cash receipt đã đối chiếu thực hiện, đúng hai bên, thanh toán đủ và khớp gross | Sinh PaymentProof false cho check non-cash |
| Chỉ có “TM/CK”, lệnh chưa xác nhận thực hiện, chưa thanh toán hoặc thiếu chứng từ | Không sinh false/true; cần review |
| Thanh toán một phần, số phân bổ vượt gross, trả chậm/trả góp hoặc SPECIAL | Chưa hỗ trợ, cần review |
| Ngoại tệ, số âm, MST hai bên lệch, phụ thuộc chất lượng chưa đủ | Chưa đủ input; không sinh proof |

Căn cứ: [NĐ 181 PDF gốc](https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/181nd.signed.pdf), Điều 26 trang 32–34; NĐ 144 Điều 4 sửa trường hợp tại điểm g từ 20/06/2026. NĐ 359 không được dùng làm mốc sửa Điều 26. Chứng từ do bên mua nộp tiền mặt vào tài khoản bên bán không được tự coi là non-cash; reviewer phải xác định đúng bản chất, không chỉ thấy có ngân hàng.

Ledger completeness và bản chất settlement là xác nhận của operator dựa trên tài liệu; file hash không xác minh nội dung thay người đối chiếu. Chưa có bank connector/reconciliation tự động trong phạm vi này.
