# Trạng thái 35 luật Agent2 — 2026-11-14

**Phạm vi: code hiện tại, hợp đồng nhập 1.1.0 và luồng snapshot/HE mới. Đây là kiểm kê, không phải nghiệm thu nghiệp vụ hoặc sửa luật.**

| Lớp | Trạng thái |
|---|---|
| Danh mục/lõi cũ | Có 35 mã luật; mức sẵn sàng còn tùy nguồn và policy, không mặc định cả 35 đã hoàn thiện. |
| Khai báo nguồn (`rule_sources`) | Có bản đồ nguồn cho đủ 35 luật; khai báo chưa có nghĩa nguồn đã nhập được hoặc luật đã chạy. |
| Evaluator snapshot mới | Có P1 và E3 khi đủ nguồn; 33 luật chưa có evaluator đã nối. |
| HE của nhánh luật trên Portal | Mới P1 trong miền đã kiểm chứng; 34 luật chưa nối HE. |
| Schema/import 1.1.0 | 33 luật còn ít nhất một bảng/trường phụ thuộc chưa được nhận theo bản đồ nguồn hiện tại. |

“Bảng/trường chưa nối” dưới đây nói về hợp đồng nhập/adapter hiện tại, **không kết luận doanh nghiệp không có nguồn đó**. Có thể cần bổ sung bảng hoặc ánh xạ có kiểm chứng từ nguồn đã tồn tại. Không tự lấy `effective_at`/`observed_at` thay ngày ghi sổ/lập/duyệt hoặc tự điền số 0.

Nguồn được liệt kê theo khai báo trong code hiện tại. Một luật có thể có các nhánh dùng nguồn khác nhau; khi nối evaluator cần tách phần đủ nguồn và phần thiếu, không mặc định mọi trường đều cần đồng thời cho mọi nhánh. Ví dụ ngân hàng và CCCD của B1 cần được đánh giá theo căn cứ tương ứng.

“Adapter” trong bảng là **evaluator trên snapshot mới**. Phần source map đã có khai báo cho cả 35. Cột HE chỉ ghi luật đã nối; graph/RobustZ chạy riêng chưa đồng nghĩa luật B/A/D tương ứng đã hoàn thành.

| Luật | Nội dung | Nguồn cần | Thiếu trong đường nhập 1.1.0 | Evaluator snapshot | HE luật |
|---|---|---|---|---|---|
| A1 | Chia nhỏ cùng người nhận trong 3 ngày | Giao dịch; Lịch sử giao dịch; Phê duyệt; Ma trận thẩm quyền; Hóa đơn; Phân bổ thanh toán; Chứng từ; Yêu cầu chi/liên kết PO; Thỏa thuận thanh toán | Bảng chưa nối: Ma trận thẩm quyền, Yêu cầu chi/liên kết PO, Thỏa thuận thanh toán | Chưa | Chưa |
| A2 | Chia nhỏ cùng người lập/người nhận trong 30 ngày | Giao dịch; Lịch sử giao dịch; Phê duyệt; Ma trận thẩm quyền; Hóa đơn; Phân bổ thanh toán; Chứng từ; Yêu cầu chi/liên kết PO; Thỏa thuận thanh toán | Bảng chưa nối: Ma trận thẩm quyền, Yêu cầu chi/liên kết PO, Thỏa thuận thanh toán | Chưa | Chưa |
| A3 | Chia nhỏ qua cụm người nhận liên kết | Giao dịch; Lịch sử giao dịch; Phê duyệt; Ma trận thẩm quyền; Hóa đơn; Phân bổ thanh toán; Chứng từ; Yêu cầu chi/liên kết PO; Thỏa thuận thanh toán; Lịch sử liên kết đối tượng; Danh mục NCC; Danh mục nhân viên | Bảng chưa nối: Ma trận thẩm quyền, Yêu cầu chi/liên kết PO, Thỏa thuận thanh toán, Lịch sử liên kết đối tượng; Trường chưa có: `vendors.phone`, `employees.address`, `employees.phone` | Chưa | Chưa |
| A4 | Người lập có nhiều khoản cận hạn mức | Giao dịch; Lịch sử giao dịch; Phê duyệt; Ma trận thẩm quyền; Hóa đơn; Phân bổ thanh toán; Chứng từ; Yêu cầu chi/liên kết PO; Thỏa thuận thanh toán; Lịch trả định kỳ | Bảng chưa nối: Ma trận thẩm quyền, Yêu cầu chi/liên kết PO, Thỏa thuận thanh toán, Lịch trả định kỳ | Chưa | Chưa |
| A5 | Số tiền tròn lệch baseline lịch sử | Giao dịch; Lịch sử giao dịch; Chứng từ sổ cái; Dòng sổ cái; Lịch vận hành; Lịch trả định kỳ | Bảng chưa nối: Chứng từ sổ cái, Dòng sổ cái, Lịch vận hành, Lịch trả định kỳ | Chưa | Chưa |
| A6 | Thanh toán làm tròn vượt hóa đơn gốc | Giao dịch; Hóa đơn; Phân bổ thanh toán | Trường chưa có: `invoices.net_vnd`, `invoices.vat_vnd` | Chưa | Chưa |
| B1 | Tài khoản hoặc căn cước NCC trùng nhân viên | Giao dịch; NCC liên quan; Danh mục nhân viên | Trường chưa có: `vendors.national_id`, `vendors.related_party_disclosed_at` | Chưa | Chưa |
| B2 | Thông tin hoặc người đại diện NCC liên kết nhân viên | NCC liên quan; Danh mục nhân viên; Lịch sử liên kết đối tượng | Bảng chưa nối: Lịch sử liên kết đối tượng; Trường chưa có: `vendors.phone`, `vendors.related_party_disclosed_at`, `employees.address`, `employees.phone` | Chưa | Chưa |
| B3 | NCC mới thành lập nhận giao dịch lớn đầu tiên | Giao dịch; NCC liên quan; Lịch sử giao dịch; Phê duyệt; Chứng từ | Trường chưa có: `vendors.registered_at` | Chưa | Chưa |
| B4 | Trạng thái người phát hành hóa đơn rủi ro | Hóa đơn; NCC liên quan; Lịch sử rủi ro nguồn thuế; Chứng từ | Bảng chưa nối: Lịch sử rủi ro nguồn thuế | Chưa | Chưa |
| B5 | Nhiều NCC chung thông tin định danh | NCC liên quan; Danh mục NCC | Trường chưa có: `vendors.phone`, `vendors.related_party_disclosed_at` | Chưa | Chưa |
| B6 | NCC ngủ đông nhận khoản lớn | Giao dịch; NCC liên quan; Lịch sử giao dịch; Lịch trả NCC theo mùa/kỳ | Bảng chưa nối: Lịch trả NCC theo mùa/kỳ | Chưa | Chưa |
| B7 | Đổi tài khoản gần ngày thanh toán chưa xác minh | Giao dịch; NCC liên quan; Lịch sử tài khoản NCC; Thay đổi TK/callback/người duyệt; Danh mục nhân viên | Bảng chưa nối: Thay đổi TK/callback/người duyệt | Chưa | Chưa |
| C1 | Lập hoặc duyệt ngoài lịch vận hành | Giao dịch; Phê duyệt; Người lập; Danh mục nhân viên; Doanh nghiệp; Lịch vận hành; Lịch ngày nghỉ | Bảng chưa nối: Lịch vận hành, Lịch ngày nghỉ; Trường chưa có: `transactions.created_at`, `approvals.approved_at`, `companies.saturday_operations` | Chưa | Chưa |
| C2 | Tự duyệt vượt quyền được cấp | Giao dịch; Người lập; Phê duyệt; Ma trận thẩm quyền; Phạm vi lịch sử quyền | Bảng chưa nối: Ma trận thẩm quyền, Phạm vi lịch sử quyền; Trường chưa có: `employees.self_approval_limit_vnd`, `approvals.approved_at` | Chưa | Chưa |
| C3 | Duyệt dưới 60 giây ở cấp thẩm quyền cao | Giao dịch; Phê duyệt; Ma trận thẩm quyền; Phạm vi lịch sử quyền | Bảng chưa nối: Ma trận thẩm quyền, Phạm vi lịch sử quyền; Trường chưa có: `transactions.created_at`, `approvals.approved_at` | Chưa | Chưa |
| C4 | Thao tác trong kỳ nghỉ phép chính thức | Giao dịch; Phê duyệt; Kỳ nghỉ phép; Log thao tác; Ủy quyền làm việc khi nghỉ | Bảng chưa nối: Kỳ nghỉ phép, Log thao tác, Ủy quyền làm việc khi nghỉ; Trường chưa có: `transactions.created_at`, `approvals.approved_at` | Chưa | Chưa |
| D1 | Benford chữ số đầu | Giao dịch; Lịch sử giao dịch | Trường chưa có: `transactions.is_financial_entry`, `transactions.posted_at` | Chưa | Chưa |
| D2 | Benford chữ số thứ hai | Giao dịch; Lịch sử giao dịch | Trường chưa có: `transactions.is_financial_entry`, `transactions.posted_at` | Chưa | Chưa |
| D3 | Hai chữ số đầu sát hạn mức | Giao dịch; Lịch sử giao dịch; Phê duyệt | Trường chưa có: `transactions.is_financial_entry`, `transactions.posted_at` | Chưa | Chưa |
| D4 | Đuôi số đặc biệt vượt baseline | Giao dịch; Lịch sử giao dịch | Trường chưa có: `transactions.is_financial_entry`, `transactions.posted_at` | Chưa | Chưa |
| D5 | MAD chữ số đầu | Giao dịch; Lịch sử giao dịch | Trường chưa có: `transactions.is_financial_entry`, `transactions.posted_at` | Chưa | Chưa |
| D6 | Benford theo phân đoạn | Giao dịch; Lịch sử giao dịch | Trường chưa có: `transactions.department`, `transactions.is_financial_entry`, `transactions.posted_at`, `transactions.project_id` | Chưa | Chưa |
| E1 | Lương không có chấm công hoặc bằng chứng thay thế | Giao dịch; Nhân viên liên quan; Chứng từ; Quyền hưởng lương; Chấm công/bằng chứng làm việc | Bảng chưa nối: Quyền hưởng lương, Chấm công/bằng chứng làm việc; Trường chưa có: `transactions.payroll_period` | Chưa | Chưa |
| E2 | Lương sau chấm dứt hợp đồng | Giao dịch; Nhân viên liên quan; Chứng từ; Quyền hưởng lương; Sự kiện nhân sự; Quyết toán/truy lĩnh lương | Bảng chưa nối: Quyền hưởng lương, Sự kiện nhân sự, Quyết toán/truy lĩnh lương; Trường chưa có: `transactions.payroll_period` | Chưa | Chưa |
| E3 | Tên NCC tương tự | NCC liên quan; Danh mục NCC | Không thiếu trường khai báo ở mức schema; vẫn phải kiểm dữ liệu, liên kết và lịch sử thực tế. | Có, phụ thuộc nguồn | Chưa |
| E4 | NCC trùng định danh | NCC liên quan; Danh mục NCC | Trường chưa có: `vendors.phone`, `vendors.related_party_disclosed_at` | Chưa | Chưa |
| F1 | Điều chỉnh thủ công sát khóa sổ và trọng yếu | Giao dịch; Log nguồn bút toán; Lịch khóa sổ; Chính sách trọng yếu | Bảng chưa nối: Log nguồn bút toán, Lịch khóa sổ, Chính sách trọng yếu | Chưa | Chưa |
| F2 | Quản lý ghi đè quy trình | Giao dịch; Phê duyệt; Quy trình chuẩn; Log ghi đè quy trình | Bảng chưa nối: Quy trình chuẩn, Log ghi đè quy trình; Trường chưa có: `approvals.approved_at` | Chưa | Chưa |
| F3 | Khoảng trống/trùng số chứng từ | Dải số chứng từ; Sổ đăng ký chứng từ; Sổ hủy chứng từ | Bảng chưa nối: Dải số chứng từ, Sổ đăng ký chứng từ, Sổ hủy chứng từ | Chưa | Chưa |
| F4 | Doanh thu/công nợ kéo dài chưa đối chiếu tiền | Giao dịch; Hóa đơn phải thu; Phân bổ thu tiền; Phạm vi lịch sử thu; Giải trình công nợ | Bảng chưa nối: Hóa đơn phải thu, Phân bổ thu tiền, Phạm vi lịch sử thu, Giải trình công nợ | Chưa | Chưa |
| P1 | Thanh toán vượt tổng giá trị cùng hóa đơn | Giao dịch; Hóa đơn gốc/điều chỉnh; Phân bổ hiện tại/trước đó/đồng thời; Giao dịch thanh toán/điều chỉnh; NCC của nghĩa vụ; Khai báo phạm vi lịch sử/manifest | Không thiếu trường khai báo ở mức schema; vẫn phải kiểm dữ liệu, liên kết và lịch sử thực tế. | Có, phụ thuộc nguồn | Có P1, giới hạn |
| P2 | Chi tiền mặt cần rà soát hạn mức và chứng từ VAT | Giao dịch; Hóa đơn; Chứng từ; Chính sách chi tiền mặt | Bảng chưa nối: Chính sách chi tiền mặt; Trường chưa có: `transactions.vat_treatment`, `invoices.vat_vnd` | Chưa | Chưa |
| T1 | Tạm ứng còn dư nợ quá hạn | Sổ tạm ứng; Sự kiện giải ngân/hoàn ứng/xóa nợ; Giao dịch | Bảng chưa nối: Sổ tạm ứng, Sự kiện giải ngân/hoàn ứng/xóa nợ; Trường chưa có: `transactions.advance_id` | Chưa | Chưa |
| T2 | Xóa nợ tạm ứng thiếu hồ sơ | Sổ tạm ứng; Sự kiện giải ngân/hoàn ứng/xóa nợ; Giao dịch; Chứng từ | Bảng chưa nối: Sổ tạm ứng, Sự kiện giải ngân/hoàn ứng/xóa nợ; Trường chưa có: `transactions.advance_id` | Chưa | Chưa |

## Việc cần làm cho từng luật

| Luật | Việc còn thiếu để đưa vào luồng mới |
|---|---|
| A1 | Nối yêu cầu chi–PO–hóa đơn–hợp đồng và quyền theo thời điểm; đối chiếu engine cho khoản trả nhiều đợt hợp lệ và nhóm đồng thời. |
| A2 | Như A1, thêm lịch sử toàn nghĩa vụ và cửa sổ 30 ngày; không dùng phần lịch sử thiếu như đã trả bằng 0. |
| A3 | Như A1, thêm phiên bản liên kết/cụm và rút liên kết; graph thành phần chưa thay thế luật chia nhỏ qua cụm. |
| A4 | Nối lịch định kỳ và quyền/phê duyệt; kiểm ngoại lệ lương/chi định kỳ, giữ chính sách kỳ của engine. |
| A5 | Nối lịch sử sổ cái/lịch hoạt động/chi định kỳ đúng thời điểm; đối chiếu baseline và tiêu chí làm tròn. RobustZ riêng chưa phải A5. |
| A6 | Bổ sung phần giá trị gốc/thuế của hóa đơn và liên kết phân bổ; đối chiếu làm tròn và điều chỉnh có dấu. |
| B1 | Nối định danh ngân hàng/CCCD và khai báo bên liên quan; phân biệt thiếu mã ngân hàng với trùng đã xác định. Graph chưa là B1. |
| B2 | Nối lịch sử quan hệ và thuộc tính liên hệ; không gom chỉ từ địa chỉ đơn lẻ hoặc dùng cạnh đến muộn cho quá khứ. |
| B3 | Bổ sung ngày thành lập và đủ lịch sử xác định lần giao dịch đầu; làm rõ phạm vi mua/giao dịch kinh tế/thanh toán theo chính sách. |
| B4 | Nối feed thuế có nguồn, ngày hiệu lực/công bố/được biết và checksum; không suy trạng thái hiện tại cho hóa đơn quá khứ. |
| B5 | Nối thông tin master và khai báo quan hệ; tách phát hiện chất lượng master, không tự cộng điểm giao dịch hai lần với E4. |
| B6 | Nối lịch sử và lịch trả theo mùa/kỳ; phân biệt ngủ đông với khoản chi định kỳ được duyệt. |
| B7 | Nối sự kiện đổi tài khoản, callback và phê duyệt đúng thời điểm; lịch sử TK hiện có chưa thay toàn bộ sự kiện xác minh. |
| C1 | Bổ sung thời điểm lập/duyệt và lịch vận hành/nghỉ; không lấy observed_at/effective_at thay thời gian thao tác. |
| C2 | Nối ma trận quyền/ủy quyền cùng coverage; hạn mức trên nhân viên/giao dịch chưa thay quyền được duyệt. |
| C3 | Nối hai mốc lập–duyệt và cấp quyền thực tế; đối chiếu trường hợp duyệt tự động/được phép theo chính sách. |
| C4 | Nối khoảng nghỉ phép, log thao tác và ủy quyền ngoại lệ; tổng ngày nghỉ theo tháng chưa đủ. |
| D1 | Nối ngày ghi sổ/cờ bút toán tài chính và lịch sử đủ điều kiện; đánh giá theo nhóm, không coi p-value là xác suất gian lận. |
| D2 | Như D1, giữ tập đủ điều kiện cho chữ số thứ hai và mẫu tối thiểu theo engine. |
| D3 | Như D1, thêm hạn mức/phân đoạn người lập; tín hiệu thống kê chưa chứng minh ý đồ. |
| D4 | Nối lịch sử đuôi số kỳ trước, không giả phân bố đều; kiểm sàng lọc số tiền đủ điều kiện. |
| D5 | Nối mẫu Benford đủ điều kiện, đối chiếu MAD trên nhóm; RobustZ hai biến không thay MAD chữ số đầu. |
| D6 | Như D1, thêm phòng ban/dự án và đủ mẫu từng phân đoạn; không gộp doanh nghiệp hoặc nhóm thiếu dữ liệu. |
| E1 | Nối kỳ lương/chấm công/quyền hưởng và bằng chứng thay thế; thiếu chấm công chưa tự là lương sai. |
| E2 | Nối nghỉ việc/tái tuyển dụng, kỳ công và hồ sơ quyết toán/truy lĩnh; không kết luận chỉ từ ngày chuyển tiền. |
| E3 | Giữ evaluator tên hiện có; chuẩn bị thiết kế so chuỗi HE nếu mở rộng. Điểm chất lượng master bằng 0 vẫn có thể matched=true. |
| E4 | Như B5, bổ sung thuộc tính định danh/khai báo quan hệ và tách chất lượng master; không coi graph hiện tại là E4 đã hoàn thành. |
| F1 | Nối log thủ công, lịch khóa sổ và mức trọng yếu được duyệt; loại suy diễn từ nhãn adjustment/cuối tháng. |
| F2 | Nối quy trình bắt buộc, log override và quyền ngoại lệ; không suy ghi đè chỉ từ người duyệt. |
| F3 | Nối dải số, sổ đăng ký và sổ hủy đầy đủ; ID giao dịch ngẫu nhiên chưa phải số chứng từ. |
| F4 | Nối hóa đơn phải thu, thu tiền/phân bổ, coverage và giải trình; không suy chưa thu tiền chỉ từ số dư/tài khoản. |
| P1 | Giữ adapter đã có; cần đủ kênh/liên kết/coverage và trong miền HE. Kiểm thêm nguồn thật, không tự cắt lịch sử cho vừa giới hạn. |
| P2 | Nối VAT và chính sách tiền mặt theo hiệu lực; kiểm chứng phân loại bằng chứng, không tự kết luận xử lý thuế. |
| T1 | Nối sổ tạm ứng và sự kiện có dấu, hạn gốc/gia hạn; đối chiếu dư nợ tại cutoff, không suy từ chi tiền đơn lẻ. |
| T2 | Như T1, thêm sự kiện xóa nợ và hồ sơ/ủy quyền; thiếu hồ sơ cần trả thiếu nguồn, không tự khẳng định gian lận. |

## Đối chiếu trên hai bộ mô phỏng đã lưu

Chạy lại resolver/evaluator local trên nguồn C001/C002 công khai đã khóa checksum, mỗi DN 8 giao dịch. Không gọi worker, không fit, không truy cập DB hoặc phiếu live. Mốc `as_of` lấy từ run đã lưu. Đây chưa là kiểm thử đủ các họ rủi ro: bộ này chủ yếu phục vụ P1, không có ca lương/nghỉ phép/override đầy đủ.

| Luật | C001: đã đánh giá / thiếu nguồn hoặc evaluator / không áp dụng | C002: đã đánh giá / thiếu nguồn hoặc evaluator / không áp dụng |
|---|---|---|
| A1 | 0 / 7 / 1 | 0 / 7 / 1 |
| A2 | 0 / 7 / 1 | 0 / 7 / 1 |
| A3 | 0 / 7 / 1 | 0 / 7 / 1 |
| A4 | 0 / 8 / 0 | 0 / 8 / 0 |
| A5 | 0 / 8 / 0 | 0 / 8 / 0 |
| A6 | 0 / 7 / 1 | 0 / 7 / 1 |
| B1 | 0 / 8 / 0 | 0 / 8 / 0 |
| B2 | 0 / 8 / 0 | 0 / 8 / 0 |
| B3 | 0 / 8 / 0 | 0 / 8 / 0 |
| B4 | 0 / 8 / 0 | 0 / 8 / 0 |
| B5 | 0 / 8 / 0 | 0 / 8 / 0 |
| B6 | 0 / 7 / 1 | 0 / 7 / 1 |
| B7 | 0 / 7 / 1 | 0 / 7 / 1 |
| C1 | 0 / 8 / 0 | 0 / 8 / 0 |
| C2 | 0 / 8 / 0 | 0 / 8 / 0 |
| C3 | 0 / 8 / 0 | 0 / 8 / 0 |
| C4 | 0 / 8 / 0 | 0 / 8 / 0 |
| D1 | 0 / 8 / 0 | 0 / 8 / 0 |
| D2 | 0 / 8 / 0 | 0 / 8 / 0 |
| D3 | 0 / 8 / 0 | 0 / 8 / 0 |
| D4 | 0 / 8 / 0 | 0 / 8 / 0 |
| D5 | 0 / 8 / 0 | 0 / 8 / 0 |
| D6 | 0 / 8 / 0 | 0 / 8 / 0 |
| E1 | 0 / 0 / 8 | 0 / 0 / 8 |
| E2 | 0 / 0 / 8 | 0 / 0 / 8 |
| E3 | 8 / 0 / 0 | 8 / 0 / 0 |
| E4 | 0 / 8 / 0 | 0 / 8 / 0 |
| F1 | 0 / 8 / 0 | 0 / 8 / 0 |
| F2 | 0 / 8 / 0 | 0 / 8 / 0 |
| F3 | 0 / 8 / 0 | 0 / 8 / 0 |
| F4 | 0 / 8 / 0 | 0 / 8 / 0 |
| P1 | 6 / 1 / 1 | 6 / 1 / 1 |
| P2 | 0 / 8 / 0 | 0 / 8 / 0 |
| T1 | 0 / 8 / 0 | 0 / 8 / 0 |
| T2 | 0 / 8 / 0 | 0 / 8 / 0 |

Các cột trên là số giao dịch, không phải số vụ gian lận. Với P1, nhóm đồng thời có kết quả riêng ngoài kết quả từng giao dịch. `not_applicable` không chứng minh luật đã kiểm thử đủ; `unavailable` không phải không vi phạm. JSON kèm theo tách `source_statuses`, `result_statuses` và nguyên nhân thiếu cụ thể.

E3 dùng SequenceMatcher trên tên chuẩn hóa, chưa có so chuỗi HE; vai trò là chất lượng master nên điểm giao dịch bằng 0 vẫn có thể có tín hiệu. B5/E4 cũng cần giữ riêng vai trò chất lượng master theo policy. Nhóm D là chẩn đoán thống kê theo nhóm, không mặc định điểm gian lận riêng cho từng giao dịch.

P1 HE giới hạn tối đa 4 source amounts trong mỗi tổng, đầu vào signed64/tính signed128; không tự cắt lịch sử để vừa miền. Graph tối đa 4 đối tượng, chỉ thuộc tính master theo thời điểm, chưa lịch sử cạnh đầy đủ. RobustZ hai biến là nhánh thống kê riêng. Các thành phần này chưa thay thế 35 luật.

## Căn cứ và cách tái lập

- [Danh mục và mô tả mức phủ lõi cũ](../agent2/sme_fraud/rules.py). Metadata `rule_coverage()` là mô tả tĩnh; `score_rules()` còn điều chỉnh theo nguồn/policy, không lấy metadata tĩnh làm chứng nhận sẵn sàng.
- [Bản đồ nguồn](../agent2/sme_fraud/rule_sources.py), [hợp đồng nhập](../agent2/sme_fraud/imports.py), [schema 1.1.0](../shared/finance_input/src/finance_input/input.schema.json).
- [Evaluator snapshot](../agent2/sme_fraud/rule_evaluation.py): allowlist `SUPPORTED` hiện P1/E3; các luật khác trả thiếu nguồn hoặc thiếu evaluator.
- [Adapter snapshot → HE](../agent2/experiments/he4/snapshot_adapter.py): nhánh rules gọi `p1_plan`; graph/statistics là nhánh riêng.
- [JSON chi tiết](rule_coverage_status_20261114.json): field/role/table, gaps theo từng luật, fingerprint code và kết quả replay.
- [Bằng chứng P1 native trên Portal trước đây](../Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113/REPORT.md); audit này không chạy HE mới.

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/audit_rule_coverage.py --output-dir .runtime/rule-coverage-new --audit-date 2026-11-14
```

Dùng thư mục đầu ra mới. Ngày trên là ngày lập bảng, không dùng thay `as_of` nghiệp vụ. Audit chỉ xuất báo cáo; không thay schema, detector, model, quyền, hàng đợi hoặc Portal.
