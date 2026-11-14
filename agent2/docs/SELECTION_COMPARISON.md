# So sánh chọn giao dịch: luật P1 và luật P1 kết hợp ML

Chính sách người dùng chọn ngày 14/11/2026: **ưu tiên cảnh báo luật, dùng ML
bổ sung chỗ còn trống**, tối đa **5 giao dịch/phương án/doanh nghiệp**.
Đây là phép thử lựa chọn; chưa đổi hàng đợi, trọng số hay kết luận gian lận.

## Dùng trên Portal

1. Mở [Công việc](http://127.0.0.1:8800/agent2/workspace), chọn doanh nghiệp,
   mở một lượt bốn nhánh đã hoàn tất.
2. Tại **So sánh luật và ML**, bấm **Khóa lựa chọn và so sánh**. Server khóa
   cùng run/snapshot/kỳ/model context, chính sách và danh sách lựa chọn.
3. Mở từng khoản trong **ML bổ sung** để xem căn cứ rồi ghi phiếu rà.
   Chưa có chứng từ thì ghi **Chưa đủ căn cứ**. Kết quả nghiệp vụ và hữu ích
   là hai đánh giá riêng; đánh giá hữu ích ở phần tùy chọn của phiếu.
4. Bấm **Cập nhật kết quả rà** hoặc tải lại trang. Chỉ số thay đổi theo bản
   phiếu đã lưu; tập lựa chọn không thay đổi theo kết luận người rà.
5. **Tải báo cáo so sánh** xuất JSON có mã/hash kế hoạch, nguồn, coverage,
   kết quả từng phương án, giao dịch thêm/bớt và revision phiếu được dùng.

## Đọc kết quả C001/C002

Hai bộ mô phỏng cùng kỳ 02–08/10/2026 đã có kết quả native HE lưu sẵn:

| Phương án | Giao dịch được chọn ở mỗi DN | Dùng ngân sách |
|---|---|---|
| Chỉ luật P1 | P1_T03, P1_T06, P1_T07 | 3/5 |
| Luật P1 + ML | Giữ ba khoản trên, thêm P1_T04 và P1_T02 | 5/5 |

ML không thay giao dịch của luật trong phép thử này. Luật chỉ có 3 giao dịch
cảnh báo, nên để trống 2 chỗ; không tự thêm khoản không cảnh báo cho đủ 5.
Ngân sách tối đa bằng nhau, số lượt được chọn thực tế khác nhau; chưa thể
suy phương án nào hiệu quả hơn chỉ từ số lượng 3 và 5.

P1_T06/T07 cùng nhóm đồng thời: giữ nguyên nhóm, mỗi giao dịch chiếm một chỗ
rà nhưng không coi là hai vụ gian lận độc lập. Nếu cả nhóm vượt chỗ còn lại,
nhóm bị deferred và được báo rõ, không cắt bớt thành viên cho vừa ngân sách.

Hai khoản bổ sung cần làm rõ:

- **P1_T04:** điều chỉnh âm −4 triệu ở C001, −12 triệu ở C002; P1 không áp
  dụng. ML xếp cao chưa chứng minh điều chỉnh sai hoặc gian lận.
- **P1_T02:** khoản trả 3 triệu ở C001, 9 triệu ở C002; P1 chưa thấy vượt
  nghĩa vụ hóa đơn. Đây chưa phải bằng chứng toàn bộ luật đã bỏ sót.

Toàn bộ 8 dòng vẫn nằm trong báo cáo coverage: P1 khả dụng 6, không áp dụng 1,
thiếu lịch sử 1; ML khả dụng 7, ngoài miền 1. Tập cùng khả dụng có 5 dòng;
JSON báo riêng chỉ số trên phần này, không xếp lại hạng sau khi lọc.

## Chỉ số

- **Đã chọn / tối đa:** số giao dịch thực tế, không phải số vụ gian lận.
- **Tỷ lệ cần xử lý / đã kết luận:** số khoản người rà ghi cần xử lý chia cho
  số khoản đã kết luận cần xử lý hoặc không phát hiện vấn đề. Chưa rà và
  chưa đủ căn cứ không bị biến thành cảnh báo sai; mẫu số 0 giữ null.
- **Đã kết luận / đã chọn:** đọc cùng tỷ lệ trên để tránh hiểu một phiếu đã
  kết luận là đại diện cả danh sách. Tỷ lệ trên toàn danh sách chỉ được tính
  khi tất cả giao dịch được chọn đã có kết luận rõ.
- **Hữu ích:** lấy đánh giá yes/no riêng trong phiếu. Chưa đánh giá giữ null.
- **Thời gian:** số giây kết nối đã lưu. Khoản chung dùng cùng phiếu cho hai
  phương án; đây là phân bổ thời gian, chưa phải đo hai quy trình độc lập.
- **Lợi ích thêm:** chỉ tính delta khi các khoản thêm/bớt được đánh giá đủ
  cho chỉ số tương ứng. Thiếu kết luận/hữu ích thì giữ chưa đánh giá.

Đây là thử nghiệm hồi cứu trên bộ đã xem, không có nhãn gian lận thật được
xác minh. Accuracy/recall/PR-AUC và số vụ gian lận xác nhận giữ null. Model
vẫn là profile HE hiện tại; không fit hoặc chấm HE mới khi bấm so sánh.

Kế hoạch lưu mã hóa tại node DN trong `comparisons.sqlite3`, tách theo
tenant/DN/actor/run, append-only; mở lại sau restart giữ cùng tập lựa chọn.
Mỗi báo cáo ghi revision phiếu tại lúc đọc để có thể đối chiếu bản xuất.

Tái lập kết quả kỹ thuật từ bằng chứng mô phỏng công khai, không truy cập
phiên Portal hoặc ghi phản hồi live:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/compare_rules_ml.py --output .runtime/he4/selection-demo-new
```

Lệnh cần thư mục đầu ra mới. Báo cáo offline dùng phiếu trống đã lưu trong
bằng chứng CR-043; kết quả rà mới nhất phải xem trên Portal.
