# Rà nghiệp vụ Agent2 — C001, 12/11/2026

**Đã đối chiếu số liệu trên bộ mô phỏng; còn 3 finding, chưa ký nghiệm thu nghiệp vụ cuối cùng.** Không có thay đổi luật, model hoặc giao diện trong lượt rà này.

## Phạm vi và cách rà

Chạy đúng web: đăng nhập Portal → chọn C001 → nhập JSON → kiểm tra → xem nguồn thiếu → xác nhận lưu → xem kết quả. Chrome, API, auth và SQLite thực trong môi trường tạm riêng, không đụng phiên/mật khẩu/kho live. Chỉ thông tin hiển thị trạng thái Agent1/3/4 được giả lập để không bật chúng. Có 5 giao dịch chính và một probe bổ sung 1 giao dịch.

[Ledger tính tay](hand_expectations.json) được khóa trước khi chạy, từ một hóa đơn I001/số **0000123**, giá trị **10.000.000 đ**, và bốn phân bổ. Không lấy kết quả của engine làm đáp án kỳ vọng. JSON nguồn ngữ nghĩa [source.json](source.json), byte upload chính xác [main-uploaded.json](main-uploaded.json); checksum được đối chiếu preview và snapshot. Nguồn và chứng từ đều mô phỏng, không xác minh thanh toán thực tế.

## Bảng đối chiếu từng dòng

Đơn vị: triệu đồng. “Lũy kế dòng” chỉ dùng lịch sử trước thời điểm của dòng, không đưa khoản đồng thời vào lịch sử nhau.

| Dòng | Tiền giao dịch | Đã phân bổ trước | Phân bổ hiện tại | Lũy kế dòng | Phần vượt ở dòng | Đối chiếu kết quả |
|---|---:|---:|---:|---:|---:|---|
| OLD · 01/10 | 4 | 0 | 4 | 4 | 0 | Chưa thấy tín hiệu thanh toán vượt; số 0 dựa trên gói khai báo đủ lịch sử, không xác minh đủ sổ ngoài hệ thống. |
| A · 02/10 09:00 | 4 | 4 | 4 | 8 | 0 | Cần đối chiếu vì thuộc nhóm A+B, không phải riêng dòng vượt. |
| B · cùng thời điểm A | 4 | 4 | 4 | 8 | 0 | Như A; không đưa A vào lịch sử của B hoặc ngược lại. |
| OVER · 03/10 | 1 | 12 | 1 | 13 | 3 | Có dấu hiệu vượt lũy kế 3; khoản chi hiện tại chỉ 1. |
| MISSING · 04/10 | 2 | Chưa đủ nguồn | Chưa đủ nguồn | Chưa đủ nguồn | Chưa đủ nguồn | Thiếu kênh và liên kết phân bổ–hóa đơn; facts rỗng, khả dụng false, cần rà nullable, không tự trả lịch sử bằng 0. |

**Nhóm A+B:** 4 đã trả trước + (4 + 4) đồng thời = **12**, vượt hóa đơn 10 là **2**. API/UI chỉ có **một nhóm**, A và B cùng dẫn đến nhóm đó. Sau OVER, lũy kế 13, vượt 3. **Không cộng 2 + 3 thành 5 triệu**: đây là diễn biến của cùng hóa đơn, không phải hai khoản tổn thất độc lập.

Tổng tiền giao dịch trong tệp **15 triệu = 13 triệu đã có liên kết phân bổ + 2 triệu chưa liên kết**. Không tự gán khoản 2 triệu vào I001 hoặc coi 13 triệu là toàn bộ tiền thực trả ngoài đời. Phần vượt từ bản xuất là dấu hiệu cần đối chiếu, chưa phải tổn thất hay sai phạm được xác nhận.

NCC V001 và V_PEER có tên “North Harbor Equipment”/“North Harbour Equipment”, cùng tài khoản 00123456 trong nguồn mô phỏng, chưa có MST/định danh pháp nhân để kết luận trùng. Cả 5 dòng cùng tham chiếu V001 nên đều được nhắc rà tên NCC. **5 giao dịch cần đối chiếu không phải 5 giao dịch gian lận**, cũng không phải cả 5 đều vượt hóa đơn. Kiểm tra tên hiện chạy không xác minh chủ tài khoản hoặc danh tính pháp nhân.

## Lịch sử và nguồn thiếu

Cùng snapshot, đổi as_of qua UI (giờ Việt Nam UTC+07): 01/10 09:00 có 1 dòng; 02/10 có 3 dòng; 03/10 có 4 dòng; 30/10 có đủ 5. Những dòng đã hiện giữ nguyên kết quả/căn cứ khi chạy đến mốc sau. Không đưa OVER/MISSING vào kết quả hoặc lịch sử ở mốc trước. Rerun không tạo thêm snapshot.

Preview báo cả 5 dòng thiếu chứng từ gốc đã xác minh, phê duyệt và lịch sử tài khoản NCC. Coverage “complete/since_inception” chỉ ràng buộc nguồn đã khai báo/gửi, chưa chứng minh đủ sổ thực. Với MISSING, hệ thống giữ thiếu nguồn và không giả tổng lịch sử hoặc liên kết theo số tiền.

## Ba finding đang mở

### BR-026-01 · Ưu tiên cao · Cần quyết định phạm vi nghiệp vụ

Probe tách riêng: **FIRST_OVER trả/phân bổ 11 triệu, hóa đơn 10 triệu, không có khoản trả trước**, chỉ một NCC để không bị cảnh báo tên che lấp. Phép tính trong facts đúng: 11 − 10 = **1 triệu vượt**. Nhưng P1 trả **no_signal**, màn hình “Chưa thấy tín hiệu”, tổng cần đối chiếu **0**. [Nguồn](first-payment-source.json), [kết quả](first-payment-results.json), [ảnh đầy đủ](first-payment-results-full.png).

Điều này khớp điều kiện policy native hiện có: P1 cần có khoản thanh toán trước. **Không phải phép cộng bị sai, nhưng là khoảng trống phạm vi phát hiện cần chủ nghiệp vụ chốt.** Cùng màn hình vừa có “Phần vượt: 1.000.000 đ”, vừa có trạng thái xanh dễ khiến người dùng bỏ qua. Đề xuất ưu tiên: xác định có cảnh báo độc lập cho phân bổ vượt nghĩa vụ ngay từ khoản đầu không; xét nguồn tạm ứng/hợp đồng/điều chỉnh hợp lệ, rồi mới sửa policy hoặc cách trình bày. Không tự kết luận đã thanh toán sai hoặc tự đổi luật/trọng số trong lần audit.

### BR-026-02 · Ưu tiên vừa · Giới hạn nguồn bị mất ngữ cảnh sau lưu

Preview có cảnh báo thiếu chứng từ/phê duyệt/lịch sử ngân hàng cho cả 5 dòng, nhưng bị ẩn khi chuyển sang kết quả. Kết quả chỉ có thẻ **1 kiểm tra chưa đủ nguồn** (P1 của MISSING); trong probe còn là **0**. Các con số này đúng phạm vi hai kiểm tra đang chạy, **không có nghĩa chỉ một hoặc không còn giao dịch thiếu chứng từ**. [Preview](main-preview.json), [kết quả](main-results.json), [quan sát UI](presentation_observations.json).

Đề xuất: giữ tóm tắt giới hạn nguồn của snapshot ngay trên kết quả, ghi rõ bộ đếm chỉ cho các kiểm tra đang chạy. Ví dụ “Chưa có chứng từ gốc đã xác minh: 5/5 giao dịch”, không suy sang trạng thái hợp lệ hoặc đủ căn cứ kết luận.

### BR-026-03 · Ưu tiên vừa · Căn cứ khó dùng cho người rà

DTO/giao diện hiện cho ID I001/V001/V_PEER và version nhưng chưa hiện số hóa đơn **0000123** hoặc cặp tên NCC từ nguồn. Muốn hiểu vì sao cần rà, người sử dụng phải mở JSON. [Kết quả](main-results.json), [nguồn](source.json), [ảnh giao dịch thiếu nguồn](main-missing-full.png).

Đề xuất: thêm các trường nghiệp vụ được phép như số/ngày hóa đơn, tên NCC đang xét và tên bản ghi đối chiếu, nguồn và thời điểm biết; giữ phân biệt mô phỏng/bản xuất/chứng từ gốc. Không cần đưa điểm, tên thuật toán hoặc ngưỡng xuống DTO kế toán.

## Kết quả và giới hạn nghiệm thu

- **56 đối chiếu tự động hóa lại ledger/HTTP/render/checksum/as_of đều đạt**, không lỗi JavaScript: [checks](checks.json). Đây là kiểm tra phép tính và sự nhất quán, **không phải 56 phê duyệt nghiệp vụ hoặc chứng minh hiệu quả model**.
- Đã mở ảnh đầy đủ và đọc lại: [5 dòng](main-results-full.png), [MISSING](main-missing-full.png), [khoản đầu vượt](first-payment-results-full.png). Ảnh trong khung Portal không dùng làm bằng chứng đầy đủ vì có thể bị cắt ở mép iframe.
- Hai snapshot riêng: bộ chính và probe; toàn bộ tạm và đã giữ dữ liệu/receipt/checksum để tái lập. [Summary](summary.json), [findings](findings.json), [provenance](provenance.json), [hash source không đổi](source_preservation.json).
- Chưa có chứng từ thật, chủ nghiệp vụ ký duyệt, đối chứng điều chỉnh âm/nhiều hóa đơn/ngoại lệ tạm ứng trong lượt rà này; chưa đánh giá ML/đồ thị/thống kê ngoài hai kiểm tra đang chạy.

**Kết luận:** số liệu 5 dòng khớp nguồn mô phỏng và phép tính độc lập; chưa chốt nghiệm thu nghiệp vụ cuối cùng do ba finding trên. Ưu tiên chốt phạm vi khoản đầu vượt hóa đơn, giữ giới hạn nguồn ở màn hình kết quả, rồi bổ sung căn cứ dễ đọc trước khi rà dữ liệu thật.

Tái lập từ root repo, chọn thư mục mới rỗng:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/review_small_business_flow.py --output-dir <thu-muc-moi>
```

Không cần đổi mật khẩu/phiên live; script tự tạo môi trường Portal/auth/DB mô phỏng. Bộ ban đầu 52 checks ở thư mục business_review_20261112 giữ làm lịch sử; bộ final hiện hành thêm ảnh/tab đầy đủ và đối chiếu render, không coi “no_signal” của probe là tiêu chí thành công.
