# Kiểm chứng 35 luật tại node doanh nghiệp

Ngày 14/11/2026 · CR-047 · **READY_FOR_REVIEW kỹ thuật**.

Cập nhật sau CR-048: [B5/E4 đã nối vào snapshot local bằng input 1.2.0 opt-in](VENDOR_IDENTITY_SNAPSHOT.md).
Đây là bước riêng sau bộ native dưới đây; chưa mở rộng HE hoặc deploy Portal live.

Đã có bộ nhận nguồn riêng `native-rule-source/1.0.0`, gọi engine luật giữ
lại tại máy doanh nghiệp. Bộ thử C001/C002 cung cấp nguồn phù hợp để chạy
và đối chiếu đủ A1–A6, B1–B7, C1–C4, D1–D6, E1–E4, F1–F4, P1–P2, T1–T2.
Đây là bước local người dùng đã chọn trước khi mở rộng HE.

## Xem kết quả có sẵn

1. Mở [báo cáo dễ đọc](../../reports/native_rules_acceptance_20261114.html).
2. Xem ba mục của mỗi doanh nghiệp: ca cần cảnh báo, ca đối chứng và ca thiếu
   nguồn. “Đạt” nghĩa là kết quả đúng với ca thử, không có nghĩa xác nhận gian lận.
3. Bộ nguồn nằm tại `agent2/.runtime/native_rules_demo_20261114/`, có ZIP
   cùng tên ở thư mục cha. Kết quả từng gói nằm tại
   `.runtime/native_rules_results_final_20261114/` từ gốc dự án.

**Không tải bộ native này vào màn hình nhập snapshot 1.1.0.** Đây là profile
kiểm chứng local, chưa phải mapping mới của Portal. Portal vẫn có evaluator
snapshot P1/E3; nhánh luật HE vẫn chỉ P1. Không có chuyển sang tính rõ trên cloud.

## Chạy lại

Trong PowerShell tại `D:\agent22`:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_native_rule_demo.py --input-dir agent2/.runtime/native_rules_demo_20261114 --output-dir .runtime/native-rules-recheck-01
```

Chọn thư mục kết quả mới mỗi lần; công cụ không ghi đè kết quả trước. Sau khi
xong, mở `REPORT.html` trong thư mục đó. Không cần đăng nhập hoặc restart Portal.

Để sinh lại nguồn trong thư mục mới:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_native_rule_demo.py --output-dir agent2/.runtime/native-rules-data-new
```

Chạy kiểm thử ranh giới và đối chiếu adapter hiện có:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_r1_tests.py --report .runtime/native-rules-tests-new.json --suite test_native_rule_node --suite test_rule_parity --suite test_rule_evaluation --suite test_rule_sources
```

## Bộ thử gồm gì?

| Nội dung | Phạm vi |
|---|---|
| Nguồn | 120 gói JSON, 60 gói mỗi doanh nghiệp |
| Ca trúng và đối chứng | 140 kiểm tra theo luật, 2 ca × 35 luật × 2 DN |
| Thiếu nguồn | 70 kiểm tra, 1 ca × 35 luật × 2 DN |
| Đối chiếu | Gọi độc lập engine giữ lại trên cùng nguồn; so cả diagnostics D |
| Nhóm D | Gói riêng 3.001 giao dịch, có kỳ nền và kỳ đánh giá |
| Kết quả kỳ vọng | Nằm ngoài nguồn, trong `manifest.json`; không dùng khi tính luật |

Mỗi ca có nguồn dành cho tình huống đang kiểm tra. Không diễn giải một gói
nhỏ của riêng một luật thành nguồn đủ cho toàn bộ 35 luật. C001/C002 cố ý
dùng lại mã giao dịch để kiểm tra tách doanh nghiệp.

Ví dụ gồm: chia nhỏ so với trả góp có ràng buộc; thông tin NCC trùng;
đổi tài khoản; thẩm quyền và nghỉ phép; lương sau nghỉ việc so với truy lĩnh;
ghi đè quy trình; số chứng từ; công nợ quá hạn có/không có giải trình;
thanh toán vượt hóa đơn; tạm ứng quá hạn và xóa nợ thiếu hồ sơ.

## Cách đọc đầu ra

- `evaluated_hit`: nguồn trong phạm vi đã đủ và có tín hiệu theo luật.
- `evaluated_no_hit`: đã đánh giá được, không có tín hiệu trong phạm vi đó.
- `unavailable`: thiếu nguồn, thiếu phạm vi lịch sử, thiếu căn cứ hoặc mẫu
  thống kê chưa đủ; `matched=null`, không đổi thành “không vi phạm”.
- D là chẩn đoán tập dữ liệu, F4 theo khoản phải thu; B5/E3/E4 theo master.
  Chúng không tự trở thành điểm của từng giao dịch. E4 giữ alias B5 của engine,
  không cộng điểm lần hai.
- Điểm tổng và độ chính xác giữ `null`. Có checksum nguồn/cấu hình và kết quả
  engine để truy đối chiếu; không tạo model, nhãn hoặc hàng đợi mới.

`native_rule_node.evaluate_bundle(bundle, scope)` yêu cầu `AccessScope` do
caller tin cậy cung cấp, một doanh nghiệp và quyền `data.import`. Đây là hàm
local, chưa có endpoint công khai. CLI demo chỉ nhận tenant mô phỏng và gói
`is_simulated=true`; scope demo không cấp quyền đọc dữ liệu Portal.

## Bảo vệ và giới hạn

Mỗi dòng phải có doanh nghiệp và `observed_at`. Manifest có số dòng, checksum,
phạm vi thời gian và trạng thái nguồn. Sửa nguồn phải xuất lại manifest; thiếu
khai báo đủ nguồn làm luật liên quan chưa khả dụng. Khai báo “complete” của
bên xuất không thay xác minh tính đầy đủ từ hệ thống gốc.

Không đọc bằng chứng biết sau `as_of`. Giao dịch sau cutoff vẫn có mã và lý do
chưa xử lý trong `unavailable_transactions`. Nguồn nhân viên/NCC phải đã được
biết tại thời điểm thao tác. Nhãn, feature có sẵn và kết quả kỳ vọng bị chặn khỏi
nguồn tính luật. Thiếu mã ngân hàng hoặc giá trị hóa đơn không tạo no-hit giả.

**Profile native giữ miền đầu vào của engine cũ:** số tiền âm hoặc bản ghi
giao dịch/sổ cái được biết muộn sau ngày ghi sổ bị từ chối rõ ràng, không lấy
trị tuyệt đối, điền 0 hoặc dời thời gian. Muốn nhận các trường hợp này cho đủ
35 luật cần adapter có dấu và bitemporal tiếp theo. P1 canonical hiện có vẫn
hỗ trợ điều chỉnh âm; không bị thay thế bởi profile này. Giá trị hóa đơn rỗng
sai kiểu bị từ chối; nguồn native khai giá trị hóa đơn 0 được coi là thiếu căn cứ
cho P1/A6, không phải hóa đơn đã được xác minh bằng 0.

Gói tối đa 64 MB/30.000 bản ghi. Chưa phải connector nguồn thật, hợp đồng nhập
chung mới, thay đổi chính sách thuế, nghiệm thu nghiệp vụ hoặc chứng minh hiệu
quả phát hiện gian lận. Chưa mở rộng HE, sửa trọng số/ngưỡng hoặc deploy Portal.

Chi tiết: [bằng chứng kiểm thử](../../Agent2_Spec_v2_1/evidence/R2/native_rules_node_20261114/REPORT.md),
[bảng kiểm kê snapshot/HE trước bước này](../../reports/rule_coverage_status_20261114.md).
