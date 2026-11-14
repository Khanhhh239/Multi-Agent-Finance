# Bàn giao Antigravity: nghiệm thu giao diện C001/C002 sau cập nhật 35 luật

Ngày 14/11/2026 · workspace `D:\agent22` · nhiệm vụ kiểm thử qua Portal thật.

## Bối cảnh và mục tiêu

Pipeline `agent2-rule-snapshot/1.0.0` đã nối đủ 35 luật giữ lại tại node DN.
Kiểm thử riêng đã đạt 140 ca trúng/đối chứng, 255 kiểm thử hồi quy và 6 bước UI.
Những kết quả đó chưa thay thế nghiệm thu qua đăng nhập/proxy/cấu hình Portal
đang dùng. Thực hiện nhiệm vụ này sau khi hoàn thành
[bàn giao triển khai và backup](HANDOFF_PORTAL_35_RULE_DEPLOY.md).

Mục tiêu: người dùng vào Portal, chọn đúng doanh nghiệp, nhập tệp, hiểu kết quả
kiểm tra, lưu snapshot và xem được căn cứ phân tích. Chứng minh giao diện phân
biệt bốn tình huống: có tín hiệu; đánh giá được nhưng chưa thấy tín hiệu;
thiếu nguồn; không áp dụng. Không dùng kết quả mô phỏng để công bố accuracy.

## Chuẩn bị

- Portal: `http://127.0.0.1:8800/#agent2`; mở màn hình Nhập dữ liệu của Agent2
  qua Portal. Node DN 8766; không dùng server test riêng thay cho lượt nghiệm thu.
- Dùng đăng nhập hiện có. Nếu phiên hết hạn, người dùng tự nhập mật khẩu trong
  trình duyệt. Không reset mật khẩu, bypass auth hoặc ghi token vào evidence.
- Mẫu ở `agent2/examples/full_rules/`. ZIP `full_rule_inputs_C001_C002.zip` có
  120 JSON và manifest checksum; giải nén vào thư mục QA private rồi nhập từng
  JSON, không upload ZIP. Tệp mẫu thuộc tenant `demo`, doanh nghiệp C001/C002.
- Kiểm đúng quyền tenant/DN trước. Nếu tài khoản Portal không thuộc tenant demo,
  báo trở ngại và chuẩn bị môi trường/principal test đúng scope; không sửa quyền
  live hoặc đổi tenant nguồn tùy tiện để bỏ qua lỗi 403.
- Mốc nguồn các mẫu B1 là **12/08/2025 11:00 giờ Việt Nam**; dùng as_of trong
  tệp đã khóa, không dùng thời gian hiện tại để làm kết quả khác đi.

## Ma trận nghiệm thu tối thiểu

Thực hiện cả C001 và C002 cho bốn tình huống dưới. Tên đích B1 trên giao diện
là **Tài khoản hoặc định danh NCC liên quan nhân viên**. E1 là **Căn cứ hưởng
lương**, E2 là **Kỳ lương và thông tin nghỉ việc**.

| Tình huống | Tệp/kiểm tra | Kết quả cần thấy |
|---|---|---|
| Có tín hiệu | `C001_B1_signal.json`, `C002_B1_signal.json` | B1 hiện **Cần đối chiếu**, có lý do liên quan tài khoản/định danh NCC–nhân viên và căn cứ cần xem; không kết luận gian lận |
| Đánh giá được, chưa thấy tín hiệu | `C001_B1_control.json`, `C002_B1_control.json` trong ZIP | Riêng B1 hiện **Chưa thấy tín hiệu**, không phải chưa đủ nguồn; technical nếu có quyền là evaluated_no_hit, matched=false |
| Thiếu nguồn | `C001_coverage_unknown.json`; tạo bản mô phỏng C002 tương tự theo hướng dẫn bên dưới | B1 hiện **Chưa đủ nguồn**, có lý do/cách bổ sung; technical unavailable, matched=null, score=null |
| Không áp dụng | Trên chính các tệp B1_signal là giao dịch vendor_payment, mở E1/E2 | E1/E2 hiện **Không áp dụng**, không phải chưa thấy tín hiệu; technical not_applicable, matched=null, score=null |

**Chấm pass/fail theo kiểm tra đích**, không theo tổng số cảnh báo của cả tệp.
B1_control có thể kích hoạt luật khác. Một tệp không cần đủ nguồn cho cả 35
luật; thống kê/đồ thị/ML độc lập chưa khả dụng trong profile mới là giới hạn
đã khai báo, không phải tự động lỗi triển khai. D1–D6/F4 xem ở phần tập/nguồn.

### Chuẩn bị ca thiếu nguồn C002

Chỉ thao tác trên bản sao dữ liệu mô phỏng, không sửa tệp gốc/ZIP/snapshot đã
lưu. Sao `C002_B1_signal.json` thành `C002_coverage_unknown.json` trong thư mục
QA; đặt `source.coverage[table].status = "unknown"` cho các khai báo coverage.
Giữ tenant/company, bản ghi, thời gian và checksum/count của từng bảng như cũ
vì không đổi nội dung bảng. Ghi checksum mới của toàn tệp trong manifest QA.
Đưa bản mới qua kiểm tra và lưu snapshot mới; không dùng preview của tệp cũ.
Không thêm expected label, score hoặc kết luận vào JSON đầu vào.

## Các bước thao tác cho mỗi ca

1. Chọn DN đúng với `company_id` trong tệp. Chọn JSON, bấm kiểm tra. Ghi tên tệp,
   checksum, DN và thông báo lỗi/cảnh báo. Nếu có lỗi phải hiểu được trường/lý do
   và cách sửa; không xác nhận lưu để bỏ qua lỗi. Coverage unknown hợp lệ được
   nhận kèm giới hạn phân tích, không báo giả là tệp sai định dạng.
2. Xem kết quả kiểm tra và xác nhận lưu. Ghi snapshot ID/checksum/as_of đã tạo.
   Mỗi mẫu B1 có **1 ứng viên** `AUDIT_0000`; lịch sử vẫn ở source, không tự
   biến thành nhiều giao dịch cần rà.
3. Bấm **Xem 35 luật tại node doanh nghiệp**. Xác nhận response thuộc
   `snapshot-rule-analysis/1.0.0`, đúng DN/snapshot/as_of và row_count=1.
   Đây là đường chạy local được chọn bằng profile, không chấm HE35.
4. Xem lý do, căn cứ và bước tiếp theo của kiểm tra đích. Mở **Các kiểm tra khác**
   để tìm no-signal/thiếu nguồn/không áp dụng; chúng được thu gọn mặc định.
   Ghi kết quả theo ma trận, không đánh fail chỉ vì phần mở rộng đang đóng.
5. Tải lại trang, thử mở lại snapshot/kết quả đã lưu. Kiểm đúng nguồn và ID;
   nếu UI chưa cho xem lại thì ghi lỗi cụ thể, không nhập lại tệp để coi là pass.
   Gửi lại cùng yêu cầu lưu phải giữ idempotency; một lần upload mới là thao tác
   khác, không dùng nó để kiểm chống gửi trùng của yêu cầu cũ.

## Kiểm quyền và cách ly doanh nghiệp

Hai mẫu C001/C002 cố ý cùng transaction_id `AUDIT_0000`. Phải dùng khóa gồm
tenant/DN/snapshot khi đối chiếu; cùng mã giao dịch không có nghĩa cùng hồ sơ.
Đổi DN trên UI không được hiển thị kết quả còn sót của DN trước. Thử tệp C002
khi DN chọn là C001 phải bị chặn rõ, không lưu vào C001 hoặc tự đổi company_id.

Tài khoản có quyền cả hai DN được đọc cả hai theo scope; không coi đó là lộ dữ
liệu. Muốn kiểm 403 ngoài quyền dùng principal test chỉ được C001; không hạ hoặc
nâng quyền tài khoản live. Catalogue/technical vẫn chỉ mở cho quản lý đúng DN.
Người rà thông thường vẫn xem được lý do/căn cứ/hành động mà không cần technical.

## Bằng chứng và đầu ra cần bàn giao

Tạo báo cáo QA private gồm bảng:

| DN | Tệp + checksum | Snapshot ID | Analysis ID | Kiểm tra đích | Trạng thái mong đợi/thực tế | Pass/fail | Bằng chứng/lỗi |
|---|---|---|---|---|---|---|---|

Chụp màn hình tối thiểu bốn trạng thái, ghi browser console và HTTP status khi
lỗi. Lưu JSON response đã loại thông tin đăng nhập nếu cần. Không lưu header
Authorization, cookie, mật khẩu, DB/khóa/config private vào báo cáo hoặc Git.
Nếu sửa lỗi UI/proxy thì liệt kê file, nguyên nhân, kiểm thử lại ca lỗi và các
ca liên quan; không sửa engine/ngưỡng hoặc tạo dữ liệu giả cho kết quả đạt.

Hoàn tất khi cả hai DN đạt bốn trạng thái, nguồn/snapshot không nhầm, kiểm
quyền đạt và luồng HE cũ không bị sửa. Nếu chưa đủ điều kiện đăng nhập/quyền/
triển khai, ghi **chưa chạy/blocked** đúng nguyên nhân; không thay bằng kết quả
server test rồi ghi đã nghiệm thu Portal. Không tự push Git hoặc kết luận độ
chính xác gian lận.

Tham chiếu: [hướng dẫn nguồn và kết quả](FULL_RULE_PIPELINE.md),
[mẫu nhập](../examples/full_rules/README.md),
[bằng chứng kỹ thuật CR-050](../../Agent2_Spec_v2_1/evidence/R2/full_rule_pipeline_20261114/REPORT.md).
