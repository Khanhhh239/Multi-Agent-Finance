# Pipeline đủ 35 luật — node doanh nghiệp

Ngày 14/11/2026 · CR-050 · kiểm chứng kỹ thuật, chưa nghiệm thu nghiệp vụ.

**Đủ 35 luật đã được nối qua nhập → kiểm tra → xác nhận lưu snapshot → phân
tích → xem kết quả.** Dùng profile nguồn đầy đủ `agent2-rule-snapshot/1.0.0`.
Đây là nối thực vào SnapshotStore và API phân tích có xác thực, tiếp nối bộ
native offline CR-047. Không chỉ thêm tên luật hoặc trả trạng thái giả.

Theo đính chính của người dùng, luật cứng là một thành phần; **không chốt
70–80%**. Giữ kernel/tham số từng luật hiện có, không đổi trọng số phối hợp
luật–thống kê–đồ thị–ML hoặc tự tính tổng từ phần còn thiếu.

## Những đầu vào đang hỗ trợ

| Đường vào | Evaluator | Mục đích |
|---|---|---|
| Finance input 1.0/1.1/1.2 hiện có | P1/E3/B5/E4 theo nguồn phiên bản | Giữ tương thích luồng canonical/ML/HE cũ |
| Agent2 rule snapshot 1.0.0 mới | Đủ 35 luật giữ lại | Nguồn rich/legacy đầy đủ của từng nghiệp vụ, xử lý tại DN |
| Worker HE hiện có | P1 và các profile giới hạn đã kiểm chứng | Chưa phải HE cho 35 luật |

Một tệp canonical ít cột không tự trở thành nguồn đủ cho 35 luật. Các luật
đã đăng ký nhưng nguồn chưa có giữ `unavailable`, matched/điểm thiếu không
trở thành false/0. Dùng đúng profile và bảng/trường được yêu cầu, không sửa
giả các cột cho qua validation.

Cập nhật 18/11/2026: trên **Nhập dữ liệu**, chọn **Nhiều nguồn cho 35 luật**
để nhập Excel nhiều sheet hoặc các CSV, ánh xạ bảng/cột, khai báo phạm vi và
xem mức sẵn sàng từng kiểm tra trước khi lưu. [Hướng dẫn thao tác](MULTI_SOURCE_IMPORT.md).
Backend chuẩn hóa về cùng profile dưới đây; JSON nguồn có sẵn vẫn dùng được.

## Định dạng nguồn mới

```json
{
  "contract_version": "agent2-rule-snapshot/1.0.0",
  "tenant_id": "demo",
  "company_id": "C001",
  "source": {
    "version": "native-rule-source/1.0.0",
    "tenant_id": "demo",
    "company_id": "C001",
    "as_of": "2025-08-12T11:00:00+07:00",
    "source_id": "erp-export-001",
    "is_simulated": true,
    "tables": {},
    "coverage": {}
  },
  "candidate_transaction_ids": ["TX001"]
}
```

Ví dụ trên chỉ minh họa khung, chưa có bản ghi để lưu. Dùng các tệp mẫu hoàn
chỉnh ở [examples/full_rules](../examples/full_rules/README.md).
`source.tables` chứa bảng giao dịch, nhân viên, NCC, hóa đơn/chứng từ thanh
toán, quyền duyệt, lịch làm việc, HR/payroll, sổ tạm ứng, log sổ cái, công nợ…
theo yêu cầu từng luật. Bảng chưa có có thể thiếu hoặc coverage partial/unknown;
luật phụ thuộc nó chưa khả dụng. Nguồn lõi phải đủ định danh và đúng kiểu.

`candidate_transaction_ids` là các giao dịch cần đưa ra kết quả, tối đa 200,
không trùng. Giao dịch lịch sử và chứng từ trong `source` là bằng chứng, không
tự biến thành hàng nghìn hồ sơ cần rà. Giữ đủ lịch sử, không cắt để vừa giới hạn.
Mỗi bảng có checksum/số dòng, phạm vi lịch sử và thời điểm khai báo được biết.
Đây là khai báo bên xuất, chưa chứng minh toàn bộ nguồn bên ngoài đầy đủ.

Schema cấu trúc: [rule_snapshot.schema.json](../sme_fraud/rule_snapshot.schema.json).
Backend còn chạy các validator scalar/temporal/table của engine giữ lại;
đọc JSON Schema mà bỏ qua validator native chưa đủ kiểm tra nguồn.

## Xem danh mục và chạy

Quản lý đúng doanh nghiệp có thể đọc:

```text
GET /api/v1/companies/C001/rules/catalogue
```

Trả đủ 35 luật, bảng nguồn cần, profile chạy và giới hạn HE. Quyền quản lý
được kiểm server; tài khoản rà thông thường không đọc chi tiết thuật toán.

1. Mở màn hình **Nhập dữ liệu** tại node doanh nghiệp, chọn đúng DN. Dùng
   **Nhiều nguồn cho 35 luật** cho Excel/CSV, hoặc **Tệp chuẩn đã có** cho JSON.
2. Kiểm tra lỗi/giới hạn rồi xác nhận lưu; checksum và phiên bản được khóa.
3. Với profile mới, nút ghi **Xem 35 luật tại node doanh nghiệp**. Thời điểm
   phân tích lấy từ phạm vi nguồn đã khóa. Muốn đổi mốc cần snapshot nguồn mới.
4. Xem **vì sao**, **căn cứ** và **bước tiếp theo**. Các kiểm tra còn lại và
   chẩn đoán nhóm được thu gọn. Quản lý có view technical để đọc từng mã luật.

Endpoint phân tích vẫn là:

```text
POST /api/v1/companies/C001/snapshots/{snapshot_id}/analyze
{"as_of":"2025-08-12T11:00:00+07:00","view":"review"}
```

`view=technical` cần quyền quản lý. Output mới là
`snapshot-rule-analysis/1.0.0`; output canonical cũ giữ nguyên phiên bản.
Profile này được chọn rõ bằng loại nguồn, không phải fallback khi HE lỗi.
Dữ liệu rõ ở node DN; không gửi dữ liệu này lên worker. Không biến thành
`he-four-branch-result` hoặc giả đã mã hóa 35 luật.

## Đọc đúng kết quả

- `evaluated_hit`: có tín hiệu trong phần nguồn được đánh giá; cần chứng từ.
- `evaluated_no_hit`: đã đánh giá được, không thấy tín hiệu trong phạm vi đó.
- `unavailable`: thiếu nguồn, coverage, mẫu thống kê hoặc căn cứ cần thiết.
- `not_applicable`: ngoài loại giao dịch/phạm vi luật; không phải “không vi phạm”.
- D1–D6 và F4 nằm trong `scope_results`: chẩn đoán tập/nguồn, không gán điểm
  gian lận cho từng giao dịch. F3 giữ cả dấu vết giao dịch và nguồn chứng từ.
- B5/E4 dùng chung bằng chứng, không cộng hai lần. E3/master-quality và tín
  hiệu context không tự thành điểm cảnh báo giao dịch độc lập.

Trong view technical, `catalogue_results` là kết quả theo **source scope**;
`rows[].rule_coverage` là kết quả từng giao dịch. Hai summary được đặt riêng.
Không sao chép hit của một giao dịch lịch sử sang mọi ứng viên. Bằng chứng
nhân viên/NCC được chọn đúng phiên bản đã biết tại thời điểm thao tác.

Guard thêm của pipeline: ma trận quyền rỗng, thiếu coverage đúng thời gian,
scope mâu thuẫn/không rõ và bảng công chưa biết không bật legacy fallback;
thiếu định danh hóa đơn/thuộc tính định danh không trả no-hit giả. Có quyền
đọc snapshot không đồng nghĩa phải có quyền xác minh mới; nhập nguồn thật
có attestation cần quyền phù hợp. Không tự gắn nhãn confirmed hoặc ghi queue.

## Kiểm chứng và giới hạn còn lại

Đã replay 120 gói C001/C002 qua snapshot thực, đối chiếu 140 ca trúng/đối
chứng với engine giữ lại. Nhóm D dùng tập 3.001 dòng để kiểm mẫu đủ; kết quả
không chứng minh accuracy trên doanh nghiệp thật. Xem [báo cáo](../../Agent2_Spec_v2_1/evidence/R2/full_rule_pipeline_20261114/REPORT.md).

Tối đa 10 MB/tệp, 200 ứng viên và 30.000 bản ghi nguồn ở profile này; API
đồng bộ còn có giới hạn output. Từ bản cập nhật 2026-11-17, giao dịch âm và
giao dịch/sổ cái ghi nhận muộn được nhận mà không sửa nguồn. Adapter
`native-signed-bitemporal/1.0.0` replay tối đa 200 nhóm thời điểm ứng viên,
giữ toàn bộ lịch sử được cung cấp. Không cắt lịch sử để vừa giới hạn.

- Số tiền giao dịch là số nguyên VND có dấu, tối đa 18 chữ số. Không mở rộng
  số âm sang hạn mức, tổng hóa đơn hay các trường chính sách vốn không âm.
- Mỗi ứng viên có ngày nghiệp vụ `posted_at` và mốc được biết `observed_at`.
  Chỉ hiện ứng viên khi cả hai không sau `as_of`. Lịch sử phải được biết tại
  `max(posted_at, observed_at)` của ứng viên và có ngày nghiệp vụ trước nó;
  giao dịch cùng ngày/giờ ghi sổ vẫn được xử lý theo batch riêng.
- Quyền, ngoại lệ và chứng từ của luật vẫn phải được biết ở thời điểm nghiệp
  vụ/thao tác mà luật kiểm tra. Không dùng chứng từ đến muộn để hợp thức hóa
  quá khứ. Thiếu chứng từ ràng buộc cần thiết trả `unavailable`, độc lập từng
  luật/ứng viên; chẩn đoán tháng giữ tập đã biết trước mốc khóa tháng.
- P1 dùng tổng thanh toán có dấu trên cùng định danh hóa đơn; không `abs`
  hoặc điền 0. F1 so độ lớn khoản điều chỉnh với mức trọng yếu đã duyệt,
  đồng thời giữ số tiền có dấu trong bằng chứng. Đây là tín hiệu cần rà,
  không chứng minh bút toán điều chỉnh sai hoặc gian lận.
- Các chính sách số âm chưa được định nghĩa cho A1–A6, B3/B6, C2/C3,
  E1/E2, F2, P2, T1/T2 giữ `unavailable` khi giao dịch âm thuộc phạm vi luật.
  Lịch sử thanh toán âm có liên quan cũng chưa được tự diễn giải cho luật
  chia nhỏ/cận hạn mức hoặc NCC mới/ngủ đông. Quy tắc ngoài loại giao dịch
  vẫn là `not_applicable`. A5 upper-tail chưa áp dụng cho sổ cái có dấu.
- Phiên bản master vẫn cần `recorded_at == observed_at`; chưa hỗ trợ sửa
  lịch sử master bằng một ngày hiệu lực cũ và ngày được biết khác nhau.

View technical có `rule_execution_provenance` với hash nguồn, hai mốc thời
gian, hash context, số dòng và hash định danh lịch sử theo nhóm replay.
Snapshot gốc và các kết quả đã lưu không bị cập nhật ngược.

Bridge 33 feature và các nhánh local đã được nối; thiếu model hoặc model sai
contract giữ `unavailable`. Thay đổi bridge/runtime cần fit/qualification mới,
không sửa ghim của model/bundle cũ để bỏ qua kiểm tra tương thích. Full-catalog
HE chưa được triển khai. Bản sửa đầu vào này chưa deploy/restart Portal.
