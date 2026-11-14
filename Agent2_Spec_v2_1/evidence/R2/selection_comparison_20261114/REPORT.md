# Luật P1 và luật P1 + ML: thử chọn giao dịch cùng ngân sách

**READY_FOR_REVIEW cho kỹ thuật; kết quả đánh giá: technical_only /
insufficient_verified_labels. Chưa chứng minh hiệu quả phát hiện gian lận.**

## Phạm vi đã chốt

Người dùng yêu cầu so hai phương án trên cùng kỳ dữ liệu, tối đa 5 giao dịch
mỗi phương án/mỗi doanh nghiệp. Người dùng chọn **ưu tiên cảnh báo luật, ML
bổ sung chỗ trống**. Không đặt trọng số mới, không thay hàng đợi, không biến
phiếu rà thành nhãn train. Tính lựa chọn trên node DN từ kết quả đã giải mã;
worker HE không nhận dữ liệu rõ và không bị thay thuật toán/build/model/khóa.

Đây là hồi cứu trên kết quả native C001/C002 mô phỏng đã biết ở CR-043. Không
coi là test tương lai chưa từng xem; không fit, chọn lại detector hay chấm HE
mới. Source/result/review-packet công khai được kiểm checksum manifest trước
khi dùng script tái lập. Model context của API ghim artifact trong request
và HE4 plan digest của run; report có source/result/plan hash, không phát tán
model/feature contract/ngưỡng riêng cho kế toán.

## Kết quả lựa chọn

| DN | Chỉ luật | Luật + ML | ML thêm | Thay khoản luật |
|---|---|---|---|---|
| C001 | T03, T06, T07: 3/5 | T03, T06, T07, T04, T02: 5/5 | T04, T02 | 0 |
| C002 | T03, T06, T07: 3/5 | T03, T06, T07, T04, T02: 5/5 | T04, T02 | 0 |

ID đầy đủ có tiền tố `P1_`. Kỳ chung 02–08/10/2026; snapshot và mã run theo
[bằng chứng Portal CR-043](../../HE/p1_portal_recheck_20261113/REPORT.md).

T04 là điều chỉnh âm: −4 triệu ở C001 và −12 triệu ở C002, P1 không áp dụng.
T02 là khoản trả 3 triệu/9 triệu, chưa trúng P1. ML xếp cao hai khoản này
chưa chứng minh có sai phạm hoặc toàn bộ luật bỏ sót. Cần người hiểu nghiệp
vụ đối chiếu căn cứ, ghi giải thích/hành động và hữu ích riêng.

Ngân sách là **mức tối đa**, số chọn thực tế 3 và 5 khác nhau. Không bù mẫu
ngẫu nhiên hoặc biến điểm thiếu thành 0 cho đủ số. T06/T07 là cùng nhóm;
giữ cả nhóm, mỗi giao dịch chiếm một slot, không gọi thành hai vụ độc lập.
Sắp các nhóm cảnh báo P1 theo thời điểm UTC rồi ID/revision; phần ML ngoài
cảnh báo luật theo raw score giảm dần, hòa thì thời điểm/ID/revision.
Nhóm không vừa ngân sách được deferred cả nhóm, không cắt nguồn/thành viên.

Coverage mỗi DN: 8 dòng, P1 khả dụng 6/8, không áp dụng 1/8, thiếu lịch sử
1/8; ML khả dụng 7/8, ngoài miền 1/8. Tập cùng khả dụng có 5 dòng, có chỉ số
riêng trên các lựa chọn thuộc tập này và không xếp lại hạng để làm đẹp kết quả.

## Chỉ số và nguồn phản hồi

Phiếu công khai được lưu trước đây chưa có phản hồi: các chỉ số hữu ích,
precision đã kết luận, thời gian và lợi ích thêm giữ null; không báo thành
0% hoặc kết luận ML có ích. Accuracy/recall/PR-AUC/số vụ gian lận xác nhận
luôn null trong phép thử chưa có ground truth đã xác minh này.

API đọc phiếu server mới nhất, xuất vector revision và report hash. Mỗi
báo cáo gắn các revision đã đọc; không tuyên bố một transaction nguyên tử
bao trùm các phiếu đang được nhiều cửa sổ cập nhật. Tập lựa chọn bất biến,
nhận phản hồi không xếp lại hạng. Precision resolved dùng confirmed_risk /
(confirmed_risk + legitimate), báo kèm resolution coverage và unresolved;
inconclusive chưa phải false alert. Tỷ lệ trên toàn tập chọn chỉ có khi đã
kết luận đủ tập. Hữu ích dùng yes/no độc lập và báo số đã đánh giá.

Delta chỉ có khi đủ phản hồi cho các khoản thêm/bớt của chỉ số tương ứng.
Khoản chung tái dùng cùng phiếu/thời gian; số giây được phân bổ cho từng
phương án, không là đo thời gian hai quy trình độc lập hoặc xác minh người
thật đã đọc chứng từ. Không sử dụng outcome của fixture/browser như dữ liệu live.

## Kỹ thuật và nghiệm thu

| Tệp | Kết quả |
|---|---|
| focused-tests.json | 45 kiểm thử qua: lựa chọn/metric, plan sealed/restart, API/quyền, workspace/reviews và kho current/legacy HE4 |
| native-regression.json | 40 kiểm thử qua: import, Portal, static/route và quyền đọc chứng từ |
| browser-tests.json | 6 kiểm tra trình duyệt qua, không lỗi JavaScript; gồm phản hồi plan bị mất, lưu phiếu, reload và chuyển DN |
| C001-plan.json, C002-plan.json | Kế hoạch tái lập trên nguồn mô phỏng công khai đã biết |
| C001-comparison.json, C002-comparison.json, summary.json | P1 3/5, kết hợp 5/5, thêm T04/T02; kết quả hữu ích/thời gian/accuracy chưa đánh giá |
| live-smoke.json | Trang/JS mới trả 200; GET/POST comparison C001/C002 chưa đăng nhập trả 401 |
| preservation.json | 7 DB trước deploy và hash config/quyền/mật khẩu/khóa giữ nguyên; thêm kho plan riêng |

Plan append-only mã hóa AES-GCM tại DN, HKDF domain riêng từ khóa kho node
được bảo vệ sẵn. Scope tenant/DN/actor/run, ghim policy B=5, snapshot checksum,
result/model context digest và danh sách. POST gửi lại đọc cùng plan; không
nhận scores/labels/weights từ client. GET chưa tạo không ghi plan; nguồn đổi
bị chặn 409; hết quyền hoặc sai đường DN không trả plan/phiếu. Restart mở cùng
khóa/plan. Portal thêm route `/workspace/runs/{run}/comparison` theo allowlist.

Bảng kiểm JSON kèm theo phân biệt các bộ focused/native/browser, không cộng
chồng các lượt chạy. Browser dùng Portal/snapshot/review store thật trong
fixture riêng, kết quả native **đã lưu** được nạp vào kho test; không tuyên bố
compute Concrete mới. Phản hồi test tự động chỉ nằm trong fixture cô lập.
Kiểm smoke live sau deploy không tạo phiên đăng nhập giả hoặc ghi phiếu live.

Hướng dẫn: [SELECTION_COMPARISON.md](../../../../agent2/docs/SELECTION_COMPARISON.md).
