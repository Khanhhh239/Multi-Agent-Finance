# Đối chiếu định khoản dữ liệu SME v2

V2 sửa cách biểu diễn kế toán của ba bộ dữ liệu 2024–2025. Mỗi bộ vẫn có 100.000 quan sát, 5.000 hard negatives và đúng 100/300/500 dòng gian lận. Nhãn và splits không đổi; nhật ký chi tiết nằm trong `accounting_change_log.json` của từng bộ.

| Nội dung rà soát | Bản v1 | Cách biểu diễn v2 |
| --- | --- | --- |
| Chế độ kế toán | Chưa khai báo; dùng chung 641/642 | C001/C005: TT200. C002/C003/C004: TT133. TT133 dùng 6421 bán hàng, 6422 quản lý. |
| Chi phí trong ML | One-hot độc lập 641/642 | Giữ mã gốc trong sổ; gộp thành nhóm ML 642, có biến chế độ và cặp tài khoản multi-hot. |
| Thuế đầu vào | Không có 133; toàn bộ gross vào tài sản/chi phí | Giá chưa thuế vào tài sản/chi phí, VAT vào 1331 hoặc 1332, tổng vào 331/tiền. |
| Thuế đầu ra | 131/511 trên toàn bộ gross | Nợ 131 tổng tiền; Có 511 giá chưa thuế; Có 3331 VAT. |
| Trả NCC | Có dòng 331/112, thiếu chứng từ gốc liên kết | Thêm chứng từ ghi nhận hóa đơn; trả 331/112 không ghi thêm VAT lần nữa. |
| Lương sản xuất | Chỉ có trả lương 334/112 | Thêm chi phí lương: TT133 N154/C334; TT200 N622/C334 rồi N154/C622, khi nhân sự có cost center sản xuất. |
| Vật tư và giá vốn | Thiếu 154/155; mọi ngành dùng 632/156 | TT133 N154/C152; TT200 N621/C152 rồi N154/C621. Sản xuất có 155/154 rồi 632/155; dịch vụ có 632/154; thương mại có 632/156. |
| Điều chỉnh chi phí | 642/338 nhưng không nêu nghĩa vụ | Mẫu dịch vụ đã nhận chưa đủ hóa đơn dùng chi phí/335. Không coi mọi cặp 642/338 là sai: 338 vẫn phù hợp với nghiệp vụ khác khi có căn cứ. |
| Xóa sổ tạm ứng | 138/141 bị gọi là xóa nợ | 1388/141 là chuyển sang phải thu khác. Xóa khoản phải thu dùng chi phí quản lý và/hoặc dự phòng 2293 đối ứng 1388, có hồ sơ xử lý. |
| Thiết bị giá nhỏ | Mọi thiết bị vào 211 | Với giả định một vật thể độc lập/hóa đơn, nguyên giá chưa VAT dưới 30 triệu vào 153, VAT vào 1331. Thiết bị đủ tiêu chí giả định vào 211 và VAT vào 1332. |
| Thụ hưởng | Một số bút toán không chi tiền vẫn có TK nhận và kênh bank | Tách `counterparty_account` khỏi `recipient_account`; nghiệp vụ phi tiền tệ để trống bên nhận. Thu tiền khách hàng vào TK của SME. |

Các kết luận về tài khoản dựa trên phần hướng dẫn TK 133/141/154/138/229/334/335/641/642 trong [TT200 – CSDL VBPL](https://vbpl.moj.gov.vn/botuphap/Pages/vbpq-toanvan.aspx?ItemID=66801) và [TT133 – bản chép toàn văn của văn bản](https://lawplayer.com/vn/act/vn-vbpl-113560). Đường dẫn bản gốc: [Công báo TT200](https://congbao.chinhphu.vn/van-ban/thong-tu-so-200-2014-tt-btc-6697/3529.htm), [Công báo TT133](https://congbao.chinhphu.vn/van-ban/thong-tu-so-133-2016-tt-btc-21048.htm).

Mốc 30 triệu là một trong các tiêu chí TSCĐ, còn phải xét lợi ích kinh tế, thời gian sử dụng và nguyên giá tin cậy. Dữ liệu này giả định thiết bị lớn thỏa các tiêu chí còn lại, không phân loại toàn bộ tài sản thực tế chỉ bằng giá. [Bộ Tài chính – tiêu chí TSCĐ theo TT45](https://qlg.mof.gov.vn/hoidapcstc/home/cthoidap/149525).

## Ví dụ VAT và xóa nợ

Mua vật liệu 110 triệu, gồm giá chưa thuế 100 triệu và VAT giả định 10 triệu:

- Nợ 152: 100 triệu.
- Nợ 1331: 10 triệu.
- Có 331: 110 triệu.
- Khi trả tiền: Nợ 331/Có 112: 110 triệu. Không ghi Nợ 1331 lần thứ hai.

Khoản tạm ứng được chuyển thành khoản phải bồi thường: Nợ 1388/Có 141. Khi có căn cứ xử lý khoản phải thu không thu hồi, mẫu ghi Nợ chi phí quản lý phần chưa có dự phòng, Nợ 2293 phần đã có dự phòng, Có 1388 tổng khoản xóa. `evidence_on_file=0` là tín hiệu thiếu hồ sơ tại lúc ghi sổ; nó không được lấy từ trạng thái hoàn tất tương lai.

## Đặc trưng nghiệp vụ

Các cột mới gồm cặp tài khoản chuẩn hóa, tần suất cặp chỉ dùng quá khứ, chênh lệch Nợ/Có, tỷ lệ VAT và đối chiếu net/VAT/gross; Nợ 331 trả vào TK nhân viên; Nợ 141 có NCC nhận; xóa nợ thiếu hồ sơ; tỷ lệ chi phí gắn vào sản xuất. Không đưa nhãn, `case_id` hoặc tên kịch bản vào X.

`pair_supported_for_scenario` dùng tập mẫu của benchmark. Cặp ngoài mẫu phải được rà soát theo chứng từ/nội dung nghiệp vụ; không tự coi là trái luật hoặc gian lận. Những gian lận như hóa đơn khống, nhân viên ma vẫn có thể định khoản đúng về hình thức.

`account_flow_edges.csv` biểu diễn luồng ghi sổ Có → Nợ, không mặc nhiên là chuyển tiền ngân hàng. Khi xây GNN, ghép bằng `document_id`, `employee_id`, `vendor_id`, `invoice_id`; chỉ dùng cạnh và liên kết có `observed_at` không vượt thời điểm cần chấm điểm. Chứng từ hỗ trợ không có nhãn riêng và không được cộng vào mẫu số tỷ lệ gian lận của tập train.

## Phạm vi thời gian và kiểm tra

TT200 được dùng cho giai đoạn 2024–2025 của bộ này. TT99 áp dụng cho năm tài chính bắt đầu từ hoặc sau 01/01/2026; việc triển khai dữ liệu từ kỳ đó cần rule version TT99 riêng. [Bộ Tài chính – thời điểm áp dụng TT99](https://portal.mof.gov.vn/hoidapcstc/home/cthoidap/159102).

Kiểm tra gồm mã tài khoản theo chế độ, cặp theo mẫu nghiệp vụ, Nợ=Có trên mọi chứng từ chính/hỗ trợ, VAT và làm tròn, không ghi VAT hai lần, lịch sử chuyển/xóa nợ, thời điểm liên kết chứng từ, giữ nguyên nhãn/splits và chống dữ liệu tương lai. Kết quả định lượng theo ba bộ nằm trong `reports/accounting_review.json` và `accounting_validation.json` từng bộ.

Chưa kiểm tra số dư đầu/cuối kỳ, toàn bộ điều kiện khấu trừ/hoàn thuế, lương/PIT/BHXH hoặc bộ BCTC đầy đủ. Các kiểm tra đạt nghĩa là đúng phạm vi mẫu mô phỏng và cấu trúc sổ; không chứng minh giao dịch thực tế hoặc quyền khấu trừ VAT.
