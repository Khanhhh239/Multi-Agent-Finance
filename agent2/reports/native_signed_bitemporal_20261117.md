# Đầu vào có dấu và nguồn đến muộn cho profile 35 luật

Ngày: 2026-11-17. Phạm vi: node doanh nghiệp, dữ liệu mô phỏng; chưa deploy.

## Thay đổi

Nguồn `agent2-rule-snapshot/1.0.0` giữ nguyên hợp đồng cấu trúc. Validator
`rule-snapshot-validator/1.1.0` nhận số tiền giao dịch nguyên VND có dấu,
không `abs`, điền 0 hoặc sửa `posted_at`/`observed_at` trong snapshot gốc.
Hạn mức, giá trị hóa đơn và các trường chính sách không được tự mở sang số âm.

Adapter `native-signed-bitemporal/1.0.0` dùng hai mốc cho từng ứng viên:

- Ngày nghiệp vụ: `posted_at`.
- Mốc giao dịch được biết: `max(posted_at, observed_at)`.
- Lịch sử có ngày nghiệp vụ trước ứng viên và đã được biết tại mốc của nó.
- Các giao dịch cùng timestamp không nhìn nhau như lịch sử; kiểm tra tổng
  nhóm diễn ra riêng sau khi đóng batch.
- Nguồn chứng minh quyền/ngoại lệ vẫn phải được biết tại thời điểm mà luật
  kiểm tra. Nguồn đến muộn không được hợp thức hóa hoặc sửa kết quả quá khứ.
- Thống kê tháng chỉ dùng giao dịch đã được biết trước mốc khóa tháng.

Thiếu bằng chứng ràng buộc cần thiết trả `unavailable`, `matched=null`,
`score=null`, có lý do theo từng ứng viên/luật. Một ứng viên thiếu giá trị
hóa đơn không làm ứng viên khác có đủ nguồn bị mất khả năng đánh giá.
Không biết cấu hình doanh nghiệp tại thời điểm giao dịch cũng không được
trả thành `evaluated_no_hit`.

Kết quả technical có hash nguồn và receipt của từng nhóm replay: hai mốc,
hash context, hash kết quả engine, số giao dịch lịch sử và hash danh sách ID.
Không nhân toàn bộ lịch sử vào từng receipt. Tối đa 200 nhóm thời điểm ứng
viên; lịch sử giữ đầy đủ theo giới hạn profile, không tự cắt để vừa bộ tính.

## Đối chứng tính tay

| Tình huống | Kết quả mong đợi |
|---|---|
| Hóa đơn 100 triệu; đã trả 80, điều chỉnh -20, trả thêm 30 | Tổng 90 triệu: P1 không có tín hiệu |
| Cùng lịch sử trên, trả thêm 50 | Tổng 110 triệu: P1 vượt 10 triệu |
| Đã điều chỉnh -20; hai khoản đồng thời 70 và 70 | Mỗi khoản nhìn lịch sử -20; batch tổng 120, vượt 20 triệu |
| Khoản 80 triệu ghi sổ 10/08 nhưng đến 12/08 mới được biết; khoản ngày 11/08 là 30 triệu | Khoản ngày 11/08 không được nhìn thấy khoản 80 triệu |
| Sau khi nguồn 80 triệu đến, ngày 12/08 trả tiếp 10 triệu | Tổng 120 triệu: P1 vượt 20 triệu |
| Bút toán điều chỉnh -30 triệu, mức trọng yếu 20 triệu, đủ log thủ công/lịch khóa sổ/chính sách | F1 có tín hiệu theo độ lớn 30 triệu; bằng chứng giữ -30 triệu |
| Log thủ công chỉ được biết sau thời điểm kiểm tra | F1 chưa đủ căn cứ, không đổi thành không có tín hiệu |
| Thêm phiên bản log tương lai vào snapshot mới | Không đổi kết quả tại thời điểm nghiệp vụ cũ |
| Một dòng sổ cái có cả Nợ và Có khác 0 | Từ chối, nêu đúng trường/dòng; không bỏ qua vì có số âm |

Các ca còn kiểm tra C001/C002, đủ 35 trạng thái mỗi ứng viên, tính bất biến
snapshot, thứ tự nguồn, số âm trong feature/evidence và độ chặt kiểu dữ liệu.

Kiểm thử nằm tại `tests/test_native_signed_bitemporal.py`; hồi quy bao gồm
native rules, snapshot/cutoff, bridge ML, engine parity, nguồn ngưỡng động,
import, feature, gate phát hành, shadow plan và bundle workspace.

Lượt kiểm tra cuối: **284 test qua, 242,334 giây**, gồm 15 test mới trong
`test_native_signed_bitemporal`. Có kiểm thử source/snapshot và HTTP bundle
trên kho tạm; không nghiệm thu giao diện Portal đang chạy hoặc HE thật.

Các module chạy cùng nhau bằng `python -m unittest ... -q`:

```text
test_native_signed_bitemporal test_native_rule_node test_rule_snapshot
test_rule_snapshot_cutoff test_rule_snapshot_ml_bridge test_rules
test_rule_repairs test_rule_parity test_dynamic_threshold_sources
test_dynamic_thresholds test_feature_evidence_timing test_core_rule_requirements
test_snapshots test_snapshot_features test_pipeline_release
test_release_shadow_plan test_bundle_workspace
```

Dùng Python trong `agent2/.venv`; `PYTHONPATH` gồm `agent2`,
`shared/finance_input/src`, `agent2/tests`, `agent2/tests_he`.

## Giới hạn được giữ rõ

- Nhận một số âm không xác minh rằng bút toán điều chỉnh đó hợp lệ.
- P1 hỗ trợ tổng thanh toán có dấu trên cùng định danh hóa đơn. F1 dùng độ
  lớn để so mức trọng yếu nhưng giữ dấu trong bằng chứng.
- Chưa tự đặt chính sách số âm cho A1–A6, B3/B6, C2/C3, E1/E2, F2, P2,
  T1/T2. Nếu giao dịch âm thuộc phạm vi kiểm tra, luật tương ứng chưa khả
  dụng. Lịch sử thanh toán âm liên quan cũng chưa được tự diễn giải cho
  luật chia nhỏ/cận hạn mức hoặc NCC mới/ngủ đông.
- A5 upper-tail không chấm sổ cái có dấu bằng cách đổi số âm thành dương;
  nguồn đó giữ lý do chưa hỗ trợ miền. Các dòng của một chứng từ có dấu
  không bị lấy từng phần để tạo một tổng chi phí dương giả.
- Phiên bản master vẫn yêu cầu `recorded_at == observed_at`; chưa hỗ trợ
  sửa master có ngày hiệu lực cũ và ngày được biết khác nhau.
- Native source completeness vẫn là khai báo của bên xuất dữ liệu, chưa
  phải xác minh tính đầy đủ từ hệ thống kế toán độc lập.
- Không mở rộng HE/cloud, thay trọng số, tự fit khi chấm hoặc đưa vụ vào
  production. Kết quả mô phỏng không chứng minh hiệu quả phát hiện gian lận.

## Khi triển khai sau này

Thay đổi mã bridge làm đổi fingerprint feature; runtime bundle cũng thay đổi.
Model/bundle cũ vẫn giữ ghim cũ và phải bị chặn nếu không tương thích. Cần
fit/validation/qualification mới trên nguồn đã khóa trước khi kích hoạt; không
sửa metadata model hoặc bundle để vượt gate. Bản sửa không ghi lại model,
khóa, snapshot hay phiên phân tích hiện hành.
