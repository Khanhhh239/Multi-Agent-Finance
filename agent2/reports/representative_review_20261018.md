# Rà định tính 27 mẫu P2/A5 — 18/10/2026

**Đã đọc và ghi nhận từng mẫu:** 20 tình huống đối chứng P2 và 7 hồ sơ phát sinh từ snapshot mô phỏng 001/003 (4 thiếu mẫu, đủ 3 hit A5 mới có điểm). Kết quả do trợ lý thực hiện, không phải nghiệm thu kế toán độc lập.

Kết quả rà cách giải thích/bằng chứng/ưu tiên: **10 đạt trong phạm vi rà, 16 cần sửa/cải thiện, 1 cần quyết định nghiệp vụ**. 'Đạt' không phải chứng nhận giao dịch hợp lệ; 'cần sửa' không phải nhãn cảnh báo sai.

## Phạm vi và cách đánh giá

Mẫu được chọn có chủ đích, không ngẫu nhiên: 20 tình huống P2 bao gồm 51 dòng nguồn và 18 hồ sơ engine tính theo khóa tình huống/hồ sơ; có cả trường hợp không mở hồ sơ. Thêm 7 hồ sơ riêng của 001/003. Không cộng số dòng lịch sử của RECUR_A5 thành các hồ sơ rà độc lập.

Đã đọc giao dịch, bút toán và các liên kết, bằng chứng quy tắc, nguồn hỗ trợ được chỉ định; đối chiếu nội dung dựng bởi các hàm UI. Bản chọn và gói bằng chứng được khóa trước khi viết nhận xét. Có đọc kỳ vọng công bố để đối chiếu, nên đây không phải đánh giá mù hoặc ước lượng precision/recall. Không đọc nhãn gian lận hay oracle ẩn; 005 chỉ kiểm tra hash, không nạp hoặc chấm điểm.

Ba trục đánh giá là: người kế toán có hiểu căn cứ không; metadata/tài liệu gốc còn cần gì; ưu tiên đến từ quy tắc nào và có cần chủ kiểm soát quyết định thêm không. Chứng từ gốc thực tế chưa được cung cấp: bản kê metadata mô phỏng không thay thế tài liệu gốc. Các ngưỡng P2 là ngưỡng cố định trong snapshot, không được đợt rà này chứng nhận về tính đúng pháp luật hiện hành.

Không có trình duyệt kết nối trong phiên đã kiểm tra trước đó, nên không nghiệm thu bố cục, thao tác nhìn thấy hoặc khả năng sử dụng thực tế. Có tái hiện lỗi hàm dựng thẻ bằng payload thật; bằng chứng lưu riêng.

## Việc nên sửa trước

| Mã | Thứ tự | Phát hiện | Tiêu chí hoàn tất chính |
|---|---:|---|---|
| RR01 | 1 | Thẻ A4 không xử lý window_days=null | Thẻ A4 của RC_d3c7009ff2ea6dbf dựng được mà không có TypeError |
| RR02 | 1 | Hiển thị bằng chứng quyết định ưu tiên C4/E2 và nguồn F1 | C4 hiển thị hành động E0000418 và kỳ nghỉ 08–10/04/2025 |
| RR03 | 1 | Tách trạng thái quy đổi ngoại tệ khỏi cột sổ VND | Cả tab giao dịch và sổ của LIMIT_FOREIGN đều không hàm ý đã quy đổi VND |
| RR04 | 2 | Làm rõ tài liệu biết sau, hết hiệu lực và thời điểm biết hóa đơn đầu tiên | Người rà nhìn được chênh 11:00/12:00 ở FUTURE_INVOICE |
| RR05 | 2 | Giải thích theo số tiền thực tế, nghĩa vụ chi và căn cứ ưu tiên | Giải thích được khoản chi 3 triệu vẫn cần đối chiếu hóa đơn 12 triệu |
| RR06 | 2 | Tóm tắt chi gốc/hoàn/đảo và trạng thái hồ sơ gốc | REFUND_FULL thấy chi 5 triệu, hoàn 5 triệu và hồ sơ gốc còn chờ xác minh |
| RR07 | 3 | Giải thích vì sao không có P2 và hành động còn lại | Ba trường hợp có giải thích khác nhau và không được gọi chung là giao dịch hợp lệ |
| RR08 | 2 | Hiển thị đủ căn cứ ngoại lệ A1/A5 | Người rà xem được vì sao A1 được giải trình ở INSTALL_MIXED |
| RR09 | 2 | Chốt cách ưu tiên khi vượt hạn mức đã xác minh chỉ 1 VND | Có quyết định nghiệp vụ được ghi nhận cho trường hợp sai khác rất nhỏ |
| RR10 | 3 | Tách mức rủi ro khỏi thứ tự và hạn lấy tài liệu | Phân biệt ưu tiên xử lý yêu cầu dữ liệu với điểm nghi vấn |

Ba vấn đề thứ tự 1 là lỗi dựng thẻ A4 với `window_days=null`, bằng chứng C4/E2 chưa hiện trên thẻ và trạng thái quy đổi VND không nhất quán giữa tab giao dịch/sổ. [Backlog có dẫn chứng và tiêu chí nghiệm thu](representative_review_20261018/backlog.json).

Ở mẫu trả nhiều đợt, `invoice.recorded_at` mang mốc đợt sau trong khi snapshot giao dịch đầu đã có thông tin hóa đơn và liên kết sổ. Đọc mã `remember_invoice` thấy bản invoice bị ghi đè theo từng giao dịch. Cần tách first-observed/last-updated hoặc phiên bản nguồn; **chưa được diễn giải phát hiện này thành detector dùng dữ liệu tương lai**, vì P2 đang đọc các trường hóa đơn trong giao dịch.

## Bảng rà từng mẫu

| Mẫu / hồ sơ | Kết quả rà | Giải thích | Ưu tiên | Chứng từ / dữ kiện còn cần |
|---|---|---|---|---|
| [FULL_BELOW](representative_review_20261018/reviews/P2_FULL_BELOW.md) | Đạt trong phạm vi rà | Dễ hiểu | Không có hồ sơ P2 | Bản hóa đơn gốc HD_CONTROL và phiếu chi để xác thực metadata; trong mẫu không thiếu trường hóa đơn bắt buộc. |
| [FULL_EQUAL](representative_review_20261018/reviews/P2_FULL_EQUAL.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Hóa đơn gốc, phiếu chi và hồ sơ nghĩa vụ chi; việc đủ trường metadata chưa xác minh tính xác thực tài liệu. |
| [FULL_BANK](representative_review_20261018/reviews/P2_FULL_BANK.md) | Đạt trong phạm vi rà | Dễ hiểu | Không có hồ sơ P2 | Ủy nhiệm chi/sao kê, hóa đơn và phê duyệt nghĩa vụ chi. Mẫu cô lập P2, không chứng nhận đã kiểm tra mọi thẩm quyền khác. |
| [NO_INVOICE](representative_review_20261018/reviews/P2_NO_INVOICE.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Hóa đơn gốc có định danh, ngày phát hành và tổng tiền; Phiếu chi, bên nhận tiền và nội dung chi cụ thể |
| [NO_DATE](representative_review_20261018/reviews/P2_NO_DATE.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Ngày phát hành và bản hóa đơn gốc HD_CONTROL; Nguồn/thời điểm chứng từ được biết trước khi đối chiếu lại |
| [FUTURE_INVOICE](representative_review_20261018/reviews/P2_FUTURE_INVOICE.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Chứng từ/nhật ký thể hiện tài liệu thực sự có trước 11:00; Giải trình thời điểm phát hành/nhập hóa đơn, không sửa ngày chỉ để khớp quy tắc |
| [INSTALL_CASH](representative_review_20261018/reviews/P2_INSTALL_CASH.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Hóa đơn 12.000.000 VND và lịch thanh toán; Hai phiếu chi, số đã trả/còn phải trả; Lịch sử phiên bản hóa đơn chứng minh đã biết ở khoản đầu |
| [INSTALL_MIXED](representative_review_20261018/reviews/P2_INSTALL_MIXED.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Hóa đơn, sao kê đợt 19.000.000 và phiếu chi 1.000.000; AGR_CONTROL/CONTRACT_CONTROL và phê duyệt gắn đúng nghĩa vụ; Lịch sử biết hóa đơn trước đợt đầu |
| [REFUND_FULL](representative_review_20261018/reviews/P2_REFUND_FULL.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý có điều kiện | Phiếu chi gốc và phiếu thu hoàn đã đối chiếu sổ quỹ; Lý do hoàn, xác nhận nhận lại tiền và liên kết chứng từ; Giải trình để người rà quyết định xử lý hồ sơ gốc |
| [REFUND_PART](representative_review_20261018/reviews/P2_REFUND_PART.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý có điều kiện | Phiếu chi 6.000.000 và phiếu thu hoàn 1.000.000; Biên bản/lý do hoàn và đối chiếu công nợ, hóa đơn liên quan |
| [REVERSAL_JOURNAL](representative_review_20261018/reviews/P2_REVERSAL_JOURNAL.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý có điều kiện | Chứng từ đảo, phê duyệt và lý do điều chỉnh; Tham chiếu bút toán gốc; chỉ xác nhận thực thu nếu có bằng chứng dòng tiền riêng |
| [RECEIPT_UNLINKED](representative_review_20261018/reviews/P2_RECEIPT_UNLINKED.md) | Cần sửa/cải thiện | Cần rõ hơn | Không có hồ sơ P2 | Phiếu thu, bên nộp tiền và lý do thu; Chứng từ gốc hoặc giải trình vì sao chưa liên kết; Đối chiếu sổ quỹ và tài khoản chi phí |
| [RECUR_CASH](representative_review_20261018/reviews/P2_RECUR_CASH.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Thỏa thuận định kỳ đã ký, hóa đơn từng kỳ, phiếu chi; Đối chiếu tiền thực trả với kỳ và mức đã duyệt |
| [RECUR_GAP](representative_review_20261018/reviews/P2_RECUR_GAP.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Hóa đơn theo từng kỳ và phiếu chi; Đối chiếu thỏa thuận định kỳ với nội dung dịch vụ/thời gian phát sinh |
| [RECUR_A5](representative_review_20261018/reviews/P2_RECUR_A5.md) | Cần sửa/cải thiện | Cần rõ hơn | Không có hồ sơ P2 | Thỏa thuận 3.000.000 VND đã được duyệt trước giao dịch và hồ sơ thực hiện kỳ hiện tại; Nguồn lịch sử cùng phạm vi tài khoản để giải thích vì sao phát sinh tín hiệu thống kê |
| [LIMIT_VERIFIED](representative_review_20261018/reviews/P2_LIMIT_VERIFIED.md) | Cần quyết định nghiệp vụ | Dễ hiểu | Cần chủ kiểm soát chốt | Quyết định hạn mức và nguyên tắc xử lý sai số/mức vượt nhỏ; Phê duyệt ngoại lệ nếu có; Hóa đơn và phiếu chi còn thiếu |
| [LIMIT_UNVERIFIED](representative_review_20261018/reviews/P2_LIMIT_UNVERIFIED.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý theo bằng chứng | Nguồn quyết định hạn mức, người và thời điểm xác minh, thời hạn hiệu lực; Hóa đơn/phiếu chi và phê duyệt ngoại lệ nếu có |
| [LIMIT_FUTURE](representative_review_20261018/reviews/P2_LIMIT_FUTURE.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Nguồn xác minh hạn mức đã có tại thời điểm chi nếu tồn tại; Nhật ký thời điểm xác minh và hóa đơn/phiếu chi |
| [LIMIT_EXPIRED](representative_review_20261018/reviews/P2_LIMIT_EXPIRED.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Quyết định hạn mức còn hiệu lực hoặc văn bản gia hạn; Thời điểm hiệu lực chính xác và hóa đơn/phiếu chi |
| [LIMIT_FOREIGN](representative_review_20261018/reviews/P2_LIMIT_FOREIGN.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý có điều kiện | Số nguyên tệ, đồng tiền, tỷ giá và thời điểm quy đổi từ nguồn xác minh; Giá trị VND đã đối chiếu cùng chứng từ gốc |
| [RC_18adf5be97ee0e84](representative_review_20261018/reviews/A5_001_TX_3103d5f23fde8b1a6f.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Hồ sơ nghỉ phép, ủy quyền/ngoại lệ thao tác, nhật ký ERP xác định người thực hiện; Hóa đơn, chứng từ ngân hàng và phê duyệt chi 102.187.000; Giải trình quy mô giao dịch so với lịch sử cùng phạm vi |
| [RC_963dc712d016c11d](representative_review_20261018/reviews/A5_001_TX_ac2d5e5d289dc9227b.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Biên bản nghiệm thu dịch vụ/bảng tính trích trước và phê duyệt kế toán; Nhật ký ERP nhập thủ công, lịch khóa sổ và chính sách trọng yếu; Hóa đơn hoặc đối soát khi đến kỳ sau |
| [IR_30749635120c8936](representative_review_20261018/reviews/A5_001_cold_information_request.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý có điều kiện | Hóa đơn có định danh/ngày/tổng tiền, phiếu chi và bên nhận; Lịch sử thực có cùng C003–TK6422–chi phí trong cửa sổ trước lúc chi, kèm thời điểm được biết; nếu không có thì giữ thiếu mẫu |
| [RC_035196cd1b97a1e1](representative_review_20261018/reviews/A5_001_cold_operational.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Nhật ký thao tác và hồ sơ nghỉ phép/ủy quyền; Chứng từ chi NCC và nguồn lịch sử đúng cửa sổ, không tự tạo thêm một mẫu chỉ để đủ 20 |
| [RC_b929346759d67338](representative_review_20261018/reviews/A5_003_TX_60bac87c93f578f6c3.md) | Cần sửa/cải thiện | Cần rõ hơn | Hợp lý theo bằng chứng | Quyết định chấm dứt hợp đồng và lịch sử tái tuyển/điều chỉnh nếu có; Bảng lương, kỳ phục vụ, quyết toán cuối cùng và phê duyệt chi; Sao kê thanh toán cho đúng người nhận |
| [IR_c39bd6eef7d31a7c](representative_review_20261018/reviews/A5_003_cold_information_request.md) | Đạt trong phạm vi rà | Dễ hiểu | Hợp lý có điều kiện | Hóa đơn có định danh/ngày/tổng tiền, phiếu chi và nội dung chi; Lịch sử cùng phạm vi trước 13/03/2024 trong cửa sổ đánh giá nếu thực có |
| [RC_d3c7009ff2ea6dbf](representative_review_20261018/reviews/A5_003_cold_operational.md) | Cần sửa/cải thiện | Lỗi dựng thẻ | Hợp lý theo bằng chứng | Chứng từ của cả 3 khoản, thẩm quyền theo thời điểm và nghĩa vụ chi tương ứng; Giải trình các khoản độc lập hoặc lịch thanh toán đã duyệt; Lịch sử cùng tài khoản nếu có; không hạ số mẫu A5 để đánh giá được |

## Ba hồ sơ A5 mới có điểm

| Bộ / hồ sơ | Số tiền đo | P99 | Mẫu | Căn cứ độc lập | Nhận xét ưu tiên |
|---|---:|---:|---:|---|---|
| 001 / `RC_18adf5be97ee0e84` | 102,187,000 | 69,986,200.00 | 44 | C4 | Trung bình/11 là có cơ sở vì C4 là tín hiệu độc lập; A5 chỉ hỗ trợ. Chưa đủ căn cứ nâng thành gian lận hoặc tăng ưu tiên chỉ vì vượt P99. |
| 001 / `RC_963dc712d016c11d` | 56,693,000 | 18,709,907.68 | 52 | F1 | Giữ trung bình/11 là hợp lý cho kiểm tra điều chỉnh có căn cứ độc lập F1. Nhập thủ công gần khóa sổ và số tiền lớn chưa chứng minh khoản trích trước là sai. |
| 003 / `RC_b929346759d67338` | 31,815,000 | 30,625,000.00 | 168 | E2 | Cao nhất/23 có cơ sở rà sớm vì E2 ghi nhận lương thường kỳ thuộc giai đoạn sau chấm dứt. Cần loại trừ quyết toán/tái tuyển bằng chứng gốc, chưa kết luận gian lận. |

A5 đều đóng góp 3 điểm. Hai hồ sơ C4/F1 giữ trung bình 11 điểm; hồ sơ E2 cao nhất 23 điểm do bằng chứng lương thường kỳ sau chấm dứt, không phải do mức vượt P99 chỉ 3,89%. **Chưa có căn cứ từ vòng rà này để đổi ngưỡng A5 hoặc gọi ba hit là cảnh báo sai.**

## Ghi chú đã lưu và bảo toàn

- [27 nhận xét đầy đủ](representative_review_20261018/manual_notes.json), [bản chọn](representative_review_20261018/selection.json), [cam kết gói bằng chứng](representative_review_20261018/packet_frozen.json).
- [Thẻ bằng chứng thực tế và lỗi dựng thẻ](representative_review_20261018/card_observations.json); nội dung các tab P2 lưu ở `representative_review_20261018/rendered_text`.
- 20 ghi chú P2 được lưu bằng reviewer `ASSISTANT_SYNTHETIC_REVIEW` trong database riêng `.runtime/representative_review_20261018/p2_reviews.sqlite3`; không ghi vào journal người dùng tại cổng 8767 hoặc nhật ký kết luận nghiệp vụ 001/003. [Bản journal riêng](representative_review_20261018/p2_assistant_journal.json).
- 1,209 tệp nguồn/kết quả giữ nguyên hash; không sửa code sản phẩm, trọng số, ngưỡng, dữ liệu 001/003/005 hoặc kết quả đã khóa. Chưa triển khai các sửa đổi trong backlog.
- Bước xác minh lần này kiểm tra đủ 27 nhận xét, đúng 3 hồ sơ A5 mới/4 thiếu mẫu, khả năng truy vết nguồn và journal qua khởi động lại. Không chạy lại toàn bộ test engine vì không thay code sản phẩm; lỗi dựng thẻ A4 là một phát hiện cần bổ sung kiểm thử khi sửa.

Muốn xem 20 ghi chú P2 trong web bằng journal riêng:

```powershell
& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe' -B -m sme_fraud.p2_controls_server --port 8768 --database .runtime/representative_review_20261018/p2_reviews.sqlite3
```

Mở `http://127.0.0.1:8768/p2-controls`; người rà hiển thị rõ là trợ lý. Bảy hồ sơ A5 có nhận xét và gói bằng chứng riêng trong bảng trên.

[Tổng hợp và kiểm tra dữ liệu](representative_review_20261018/summary.json).
