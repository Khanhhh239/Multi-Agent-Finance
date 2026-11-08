# Đối chiếu thư viện quy tắc cứng — 17/10/2026

**Cập nhật P2 ngày 18/10/2026:** chính sách mặc định mới phân loại bằng chứng trước khi cộng điểm: thiếu dữ kiện 0 điểm, giữ yêu cầu bổ sung ưu tiên thấp; đủ thông tin hóa đơn để đối chiếu 8 điểm; vượt hạn mức nội bộ có xác minh đúng thời điểm 14 điểm. [Báo cáo hiện tại](cash_review_p2_20261018.md), [hợp đồng cấu hình](../examples/cash_review/README.md). Các mô tả P2 8 điểm ở dưới ghi lại hành vi của đợt triển khai 17/10; dùng `cash_review_policy=legacy_v1` khi cần tái lập hành vi đó. Các mốc ngưỡng đối chiếu của `vn_vat_v1` được giữ nguyên trong đợt chỉnh phân loại này.

## Kết quả theo yêu cầu

| Yêu cầu | Trước thay đổi | Sau thay đổi và giới hạn |
| --- | --- | --- |
| 15–20 quy tắc cứng độc lập | Có 34 mã: 31 A–F và P1/T1/T2; gồm cả chẩn đoán thống kê, alias và rule phụ thuộc nguồn | Có 35 mã sau thêm P2. Bảng dưới chọn 20 predicate nghiệp vụ phân biệt; không dùng Benford hoặc alias để đủ số lượng. Độc lập nghĩa là phát hiện theo điều kiện/bằng chứng riêng, không cần model ML; không có nghĩa mọi hit tự mở hồ sơ hoặc mọi rule đã có nguồn thật. |
| Bút toán ngoài giờ/cuối tuần/ngày lễ | Có C1, lịch ca/ngoại lệ và calendar theo dataset | Đã kiểm chứng riêng ba nhánh và calendar tùy chọn năm 2026. C1 vẫn là ngữ cảnh theo chính sách chống quá tải hiện tại; cần anchor để góp điểm. Lịch mẫu 2024–2025 không tự trở thành lịch chính thức cho năm khác. |
| Maker kiêm checker | Có C2, kiểm tra quyền tự duyệt/ủy quyền và fallback hạn mức | Đã kiểm chứng vi phạm tự mở hồ sơ hard trigger; tự duyệt hợp lệ có hit bị loại và lý do để truy vết. |
| Hóa đơn từ danh sách rủi ro thuế | B4 đọc trạng thái NCC mô phỏng; chưa có hợp đồng danh sách thuế theo MST | Đã thêm nguồn `tax_risk_history`, importer gắn tài liệu gốc, đối chiếu MST/ngày hóa đơn/phiên bản công bố và hit có chứng cứ. **Chưa có danh sách thuế thật trong lượt này, chưa kết nối tự động hoặc nghiệm thu coverage nguồn.** |
| Chi tiền mặt vượt hạn mức | Chưa có rule chuyên biệt | P2 bật mặc định: 8 điểm, không hard trigger, có thể tự vào queue. Có ngưỡng theo thời gian và hạn mức nội bộ theo công ty. Đây là cờ rà soát chứng từ/VAT, chưa phải quyết định pháp lý về khấu trừ. |
| Chuỗi khoản chi cận ngưỡng duyệt | Có A4 cùng người lập/tháng lịch, A1–A3 cho chuỗi/nhóm người nhận | Giữ chính sách A2/A4 tiếp nhận riêng; kiểm chứng ba khoản 17 triệu đến ba NCC dưới hạn mức 20 triệu, không cần model ML. |

## 20 quy tắc nghiệp vụ để đánh dấu

| Mã | Kiểm tra | Điều kiện nguồn/ngoại lệ chính |
| --- | --- | --- |
| A1 | Chia nhỏ cùng người nhận, cửa sổ ngắn | Giao dịch, định danh người nhận, nghĩa vụ chi độc lập đã xác minh |
| A2 | Chia nhỏ người lập–người nhận, cửa sổ dài | Cửa sổ 30 ngày, hồ sơ hợp đồng/trả nhiều đợt |
| A3 | Chia nhỏ qua cụm người nhận | Quan hệ còn hiệu lực, nguồn đã quan sát |
| A4 | Lặp khoản cận hạn mức | Công ty–người lập–tháng lịch, ngoại lệ gắn đúng nghĩa vụ |
| A6 | Làm tròn thanh toán vượt hóa đơn | Giá trị hóa đơn gốc |
| B1 | Định danh NCC trùng nhân viên | Ngân hàng/CCCD, phiên bản master và ngoại lệ bên liên quan |
| B2 | Quan hệ NCC–nhân viên | SĐT/địa chỉ/đại diện và đường liên kết đã biết |
| B4 | Người phát hành hóa đơn thuộc nguồn rủi ro | Trạng thái NCC hoặc danh sách thuế theo MST, thời gian và nguồn |
| B6 | NCC ngủ đông nhận khoản lớn | Lịch sử đủ dài, P90 và ngoại lệ lịch năm/mùa |
| B7 | Đổi TK sát thanh toán chưa xác minh | Thay đổi tài khoản, thời điểm callback và người duyệt |
| C1 | Thao tác ngoài lịch làm việc | Giờ maker/checker, lịch ca, ngày lễ; hit ngữ cảnh |
| C2 | Tự duyệt ngoài quyền | Maker/checker, quyền/ủy quyền, coverage ma trận |
| C3 | Duyệt rất nhanh ở thẩm quyền cao | Thời gian thao tác, cấp thẩm quyền hoặc fallback đã khai báo |
| C4 | Thao tác trong nghỉ phép | Leave, log hành động và quyền làm việc ngoại lệ |
| E1 | Lương thiếu bằng chứng làm việc | Chấm công, bằng chứng thay thế và quyền nghỉ hưởng lương |
| E2 | Lương sau chấm dứt hợp đồng | Sự kiện HR và phạm vi quyết toán cuối cùng |
| F1 | Điều chỉnh thủ công sát khóa sổ, trọng yếu | Audit log, kỳ khóa sổ và chính sách trọng yếu |
| P1 | Trả vượt tổng giá trị cùng hóa đơn | Tổng trả cùng danh tính hóa đơn, gồm đóng lô |
| P2 | Chi tiền mặt cần rà soát hạn mức/VAT | Số tiền, phương thức chi, tổng hóa đơn và thời điểm chính sách |
| T1 | Tạm ứng còn dư quá hạn | Dư nợ, hạn thanh toán và gia hạn đã biết |

Các rule khác vẫn được giữ trong thư viện. Các nhánh phụ thuộc nguồn phải trả rõ thiếu dữ liệu; danh sách 20 không phải chứng nhận đã nghiệm thu thực địa.

## Chính sách P2 và căn cứ thời gian

Điều kiện thanh toán không dùng tiền mặt là một điều kiện khấu trừ VAT, không phải lệnh cấm mọi giao dịch tiền mặt. Mức cũ từ 20 triệu đồng trở lên theo Điều 15 Thông tư 219/2013/TT-BTC đã sửa đổi; từ 01/07/2025, Điều 26 Nghị định 181/2025/NĐ-CP quy định mức từ 5 triệu đồng trở lên, tính trên giá có VAT. Nghị định 144/2026/NĐ-CP sửa nhánh trả chậm/trả góp và vẫn dùng mức 5 triệu.

Nguồn đối chiếu: [giải thích mức 20 triệu trên Cổng Chính phủ](https://cms.baochinhphu.vn/xuat-hoa-don-sai-gia-va-thue-xu-ly-the-nao-102220429164908844.htm), [Điều 26 và mức 5 triệu](https://chinhsachonline.chinhphu.vn/hoa-don-phat-sinh-ngoai-gio-hanh-chinh-co-duoc-khau-tru-thue-83735.htm), [hiệu lực 01/07/2025](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-181-2025-nd-cp-quy-dinh-chi-tiet-thi-hanh-mot-so-dieu-cua-luat-thue-gia-tri-gia-tang-119250707172930626.htm), [sửa đổi 144/2026](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-144-2026-nd-cp-sua-doi-bo-sung-mot-so-quy-dinh-ve-thue-gia-tri-gia-tang-119260507074113983.htm).

Sàng lọc P2 dùng cả số tiền chi và giá trị hóa đơn, biên ngưỡng VAT là `>=`; hạn mức nội bộ là `>`. Khoản trả sau 01/07/2025 cho hóa đơn trước ngày đó được gắn `transition_review_required` khi đạt mức sàng lọc mới; cần người rà xác định điều khoản chuyển tiếp thực tế. Chưa gộp nhiều hóa đơn cùng NCC/ngày, tự xử lý hoàn/đảo, suy số VAT đã kê khai hoặc tự chấp nhận ngoại lệ pháp lý. Những giới hạn này không được diễn giải thành hỗ trợ đầy đủ kiểm tra khấu trừ VAT.

## Thay đổi và kiểm chứng

Mã mới: `sme_fraud/cash_controls.py`, `sme_fraud/tax_risk.py`, `sme_fraud/tax_risk_sources.schema.json`. Engine và coverage đã nối P2/B4; importer và header/config có tại [examples/tax_risk_sources](../examples/tax_risk_sources/README.md).

Đối chứng lịch sử `Case` và runner sửa luật cũ ghim P2 tắt nếu snapshot chưa khai báo chính sách này. Runner replay tiếp nhận A2/A4 lấy chính sách khác từ config baseline, để thay đổi thư viện hiện tại không âm thầm làm sai phép so sánh điểm đã khóa. Engine mặc định và lượt chấm mới bật P2. Không sửa model, điểm/hit/queue hoặc database của các snapshot benchmark đã lưu.

Trước thay đổi: **437/437 test đạt**. Sau thay đổi: **470/470 test đạt, không failure/error; gồm 33 test mới**, lượt cuối chạy 93,135 giây. Các kiểm thử bổ sung nằm trong `tests/test_cash_controls.py`, `tests/test_tax_risk.py`, `tests/test_core_rule_requirements.py`; gồm biên thời gian/giá trị, trả một phần hóa đơn, chứng từ tương lai cả trong cùng ngày, ngoại tệ, phạm vi công ty, gỡ khỏi danh sách, MST chi nhánh, hash nguồn/manifest, chặn nhãn đi vào bằng chứng và luồng vào queue. [Kết quả](../.runtime/rule_requirements_20261017/current.json), [log](../.runtime/rule_requirements_20261017/current.log).

P2 có thể tăng số hồ sơ ở các lượt chấm mới; chưa chạy lại benchmark lớn hoặc dùng nhãn để điều chỉnh điểm. Cần chấm lại trên output mới và đo tải trước khi thay queue vận hành. Nghiệm thu nguồn thật F1/C4/E2/F2/F3/F4 vẫn theo cổng hiện hành.
