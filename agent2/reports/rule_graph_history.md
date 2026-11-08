# Sửa lịch sử liên kết A3/B2

Ngày kiểm tra: 14/10/2026. Đã sửa trong `sme_fraud/rules.py`; không thay ngưỡng hoặc trọng số rule.

## Lỗi và hành vi sau sửa

Trước sửa, đồ thị giữ mọi cạnh từng quan sát. Xóa đường dẫn khỏi adjacency riêng cũng chưa đủ: UnionFind không thể tách cụm đã gộp. Ngoài ra, `entity_links` chứa bản sao TK/SĐT/người đại diện từ master có thể giữ liên kết đã bị thay thế.

Đồ thị hiện lưu phiên bản mới nhất đã quan sát cho từng `(company_id, source_id, link_type)`. Các loại liên kết mạnh là `bank_account`, `phone`, `representative`:

- Snapshot master thay thế giá trị cũ; giá trị rỗng đóng liên kết, kể cả đổi mã ngân hàng nhưng giữ số tài khoản. Số tài khoản thực cần mã ngân hàng theo chính sách đợt 3.
- Đọc `representative_id` từ master NCC; đổi/xóa người đại diện cũng loại đường dẫn cũ qua người đó.
- `entity_links` không có `status` được hiểu là `active`. Phiên bản mới với `status=revoked/deleted/inactive` đóng liên kết được chỉ định; target rỗng đóng cả slot. Thu hồi giá trị cũ không xóa giá trị thay thế đang hợp lệ. Thu hồi TK thực có số TK nhưng thiếu mã ngân hàng không đủ để đóng định danh đã xác định. `status` khác bị từ chối.
- Bản ghi master thắng bản sao `entity_links` có cùng thời điểm; bản ghi quan sát cũ hơn không thể phục hồi liên kết đã đóng. Một xác nhận liên kết mới hơn master có thể thay thế trường tương ứng; cần đồng bộ master nếu muốn kết quả đối chiếu trực tiếp B2 phản ánh thay đổi đó.
- Hai giá trị mâu thuẫn từ cùng loại nguồn, cùng slot và cùng thời điểm bị từ chối; không chọn tùy theo thứ tự dòng đầu vào.
- Chỉ dựng lại adjacency và UnionFind của công ty có thay đổi, sau khi đọc đủ nguồn đến thời điểm giao dịch. Các TK/SĐT/bằng chứng khác còn hiệu lực được giữ.

A3 gom các NCC đang liên kết tại giao dịch đang chấm; khoản chi của NCC đã tách cụm không tham gia tổng của cụm đó. Giao dịch và bằng chứng cảnh báo quá khứ được giữ theo trạng thái lúc phát hiện. B2 tìm đường đi trên cùng đồ thị hiện hành. `case_entity` cũng lấy thành phần liên thông đã dựng lại.

## Kiểm chứng

Đã viết đối chứng trước sửa: 9 test ban đầu tái hiện 10 lỗi assertion, tính cả subtest đổi/xóa trường. Sau sửa có **16 test lịch sử đồ thị**, gồm:

- A3 tách cụm ở cả nhánh 3 ngày và 30 ngày.
- Đổi/xóa SĐT NCC; đổi TK/SĐT nhân viên; đổi mã ngân hàng cùng số TK.
- Đổi/xóa đại diện; thay/thu hồi liên hệ của đại diện; tái xác nhận về sau.
- Giữ bằng chứng TK độc lập khi xóa SĐT; cách ly công ty.
- Thu hồi đúng giá trị, không xóa quan hệ thay thế; thiếu mã ngân hàng không thu hồi định danh đã xác định.
- Xóa đúng thời điểm của một batch giao dịch; ưu tiên master tại cùng thời điểm; nguồn mâu thuẫn; dữ liệu tương lai không đổi điểm, hit và đường dẫn quá khứ.

**Toàn bộ 151 test qua**, không failure/error. [Kết quả test](../.runtime/graph_history_test_result.json), [log](../.runtime/graph_history_tests.log), [test mới](../tests/test_graph_history.py).

Chấm lại **37.500 dòng train/validation** của seed validation `2026101401`, tỷ lệ toàn bộ dataset 0,3%, so snapshot đợt 4. Không chấm split test và không chọn lại cấu hình.

| Split | Rule/hàng đợi | TP trước → sau | FP trước → sau |
| --- | --- | ---: | ---: |
| Train | A3 | 4 → 4 | 1 → 1 |
| Train | B2 | 9 → 9 | 0 → 0 |
| Train | Hàng đợi | 63 → 63 | 332 → 332 |
| Validation | A3 | 0 → 0 | 1 → 1 |
| Validation | B2 | 5 → 5 | 0 → 0 |
| Validation | Hàng đợi | 30 → 30 | 169 → 169 |

Tập hit góp điểm A3/B2 và thành viên hàng đợi không thêm/bớt dòng; không diễn giải kết quả này thành giảm FP. Nhãn trong bảng là gian lận mô phỏng, không phải kết luận độc lập về điều kiện rule.

Kiểm tra các predicate khác không đổi; replay điểm/recurrence chính xác; hàng đợi có đúng thành viên và không trùng giao dịch. Snapshot mới có 594 cảnh báo/514 hồ sơ cho train+validation. Checksum dataset và báo cáo nền giữ nguyên; không dùng module ML. [Kết quả và checksum](rule_repairs/graph_history_final/seed_2026101401/sme_fraud_003/comparison.json).

## Phạm vi còn lại

Nguồn hiện biểu diễn **một giá trị hiện hành cho mỗi source/type**. Nhiều tài khoản/đại diện đồng thời cần schema định danh từng quan hệ và chính sách hiệu lực riêng trước khi nạp; không gộp vào slot đơn này. Mốc hiệu lực đồ thị là thời điểm quan sát (`recorded_at`/`observed_at`); chưa hỗ trợ lịch hiệu lực tương lai riêng cho `entity_links`.

Phải giữ lịch sử snapshot và bản ghi thu hồi. Xóa vật lý dòng nguồn rồi chạy lại không thể tái hiện quan hệ trước khi xóa. Bản ghi rỗng thể hiện đóng liên kết trong nguồn hiện tại, không tự chứng minh bên liên quan đã độc lập về mặt pháp lý.

Các feature đồ thị ML lịch sử (`graph_employee_count`, `linked_vendor_count`) chưa chuyển sang chính sách này; A3/B2 sử dụng trực tiếp đồ thị đã sửa và không đọc hai feature đó. Cần thống nhất pipeline feature trước bước ML. Các báo cáo phase 1–4 và database feedback/UI cũ vẫn là snapshot lịch sử, không tự cập nhật theo code mới.

## Chạy lại

```powershell
python -B -m unittest discover -s tests -p test_graph_history.py -v
python -B -m unittest discover -s tests -v
```

Runner đối chiếu `.runtime/verify_graph_history.py` nhận thư mục kết quả qua đối số đầu tiên và từ chối ghi đè thư mục đã có. Không cần sinh lại database để kiểm tra lịch sử liên kết.

```powershell
python -B .runtime/verify_graph_history.py reports/rule_repairs/graph_history_new/seed_2026101401/sme_fraud_003
```
