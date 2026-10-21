# Sprint 1.2 — Đồ thị quan hệ thực thể NetworkX, 17/10/2026

## Trạng thái

Đã triển khai và kiểm thử kỹ thuật các nhiệm vụ của Sprint 1.2. NetworkX **3.6.1** có trong Python của môi trường và đã được khai báo trong requirements/lock. **496/496 test đạt**, gồm **26 test mới**; [kết quả](../.runtime/entity_graph_20261017/current.json), [log](../.runtime/entity_graph_20261017/current.log).

Đã chạy đồng bộ mẫu trên nguồn train/validation đã khóa `data/feature_model_sync_20261017/sme_fraud_003`, cutoff **30/06/2025 23:59:59 +07:00**: **5 công ty, 9.998 nút, 8.188 cạnh, 171 nhóm quan hệ**. Đây là dữ liệu mô phỏng; nhóm quan hệ không phải số vụ gian lận, số TP hoặc số hồ sơ mới. Snapshot đầy đủ không bị giới hạn số nút như truy vấn hiển thị.

[Con trỏ snapshot](entity_graph_20261017/latest.json), [JSON đầy đủ](entity_graph_20261017/snapshots/1ea27a144c7885c0b9395aad49018b489b2f1070e84da9215ecf5e9b9288f7af.json), [kết quả chạy mẫu](../.runtime/entity_graph_20261017/demo.json).

[Đối chiếu artifact độc lập](../.runtime/entity_graph_20261017/artifact_validation.json) đã xác nhận hash snapshot và nguồn giữ đúng, mọi cạnh tham chiếu nút tồn tại, thời điểm cạnh không vượt cutoff và xuất đầy đủ. Sáu loại nút: 500 nhân viên, 1.672 NCC, 2.152 TK ngân hàng, 1.862 SĐT, 2.140 địa chỉ, 1.672 MST. Các nhóm của bản mẫu gồm 158 nhóm NCC–nhân viên chung SĐT, 8 nhóm chung TK và 5 nhóm NCC chung địa chỉ; nhánh NCC chung TK có đối chứng riêng trong test dù bản mẫu này không phát sinh nhóm đó.

## Đối chiếu đầu việc

| Đầu việc | Triển khai |
| --- | --- |
| Đồ thị đa phân bằng NetworkX trong bộ nhớ | `EntityGraph.graph` là `networkx.MultiGraph`, 6 loại nút employee/vendor/bank_account/phone/address/tax_code. Loại nút và quan hệ được ghi rõ trong JSON. |
| Thành phần liên thông | `components()` dùng NetworkX, ID ổn định theo công ty và thành viên; có cả thực thể cô lập. |
| Truy vấn đường đi | `shortest_path()` giới hạn độ sâu, lọc loại quan hệ; trả nút, cạnh, số bước và bằng chứng nguồn. Thứ tự nạp được chuẩn hóa để kết quả không phụ thuộc thứ tự file. |
| NCC trùng TK/SĐT nhân viên | Findings nhóm `vendor_employee_shared_bank_account`, `vendor_employee_shared_phone`, giữ danh sách NCC/nhân viên và ID cạnh chứng cứ. |
| Mạng NCC trùng địa chỉ/TK | Findings nhóm `vendors_shared_address`, `vendors_shared_bank_account`. Địa chỉ là quan hệ ngữ cảnh yếu. |
| Đồng bộ theo lô định kỳ | CLI `sme_fraud.sync_entity_graph`, chế độ một lần hoặc `--watch --interval-seconds`. Có wrapper PowerShell, kiểm manifest/checksum, khóa một writer, snapshot có hash và công bố con trỏ nguyên tử. |
| JSON hỗ trợ hiển thị | Node-link JSON có `nodes`/`links`, components/findings, cutoff, phạm vi và cờ giới hạn. Có JSON Schema, HTTP API và cửa sổ mạng lưới từ hồ sơ UI. |

## File cần đọc

- [entity_graph.py](../sme_fraud/entity_graph.py): dựng đồ thị, chuẩn hóa định danh, truy vấn và trích xuất.
- [sync_entity_graph.py](../sme_fraud/sync_entity_graph.py): đọc nguồn, kiểm checksum và công bố snapshot.
- [entity_network.schema.json](../sme_fraud/entity_network.schema.json): hợp đồng JSON node-link.
- [review_store.py](../sme_fraud/review_store.py), [review_server.py](../sme_fraud/review_server.py): cache lịch sử và HTTP API.
- [app.js](../review_ui/app.js): nút **Mở mạng lưới thực thể liên quan** và sơ đồ theo sáu loại thực thể.
- `tests/test_entity_graph.py`, `tests/test_entity_graph_sync.py`, `tests/test_entity_graph_review.py`: đối chứng qua module, file, SQLite và HTTP thật.

## Hợp đồng nguồn và thời gian

Nguồn gồm `employees.csv`, `vendors.csv`, `entity_links.csv`; job đồng bộ còn đọc `companies.csv` và kiểm hash các file với manifest. Employee/vendor lấy phiên bản `recorded_at` mới nhất đã biết tại cutoff. Link đọc `observed_at`, hỗ trợ `active/revoked/deleted/inactive`; nếu có `effective_at` trong tương lai thì chưa áp dụng. Giá trị mới/xóa sẽ tách lại thành phần; không giữ cạnh cũ do union-find chỉ biết gộp. Master tại cùng thời điểm ưu tiên hơn link phản chiếu; xóa một giá trị cũ không hủy giá trị đã được thay thế.

Định danh ngân hàng gồm **mã ngân hàng + số tài khoản**, giữ số 0 đầu. Số tài khoản thực thiếu mã ngân hàng vẫn có nút riêng cho từng thực thể, ghi chưa xác nhận, không tự ghép chỉ từ dãy số. Namespace `BANK_SYN` dùng theo bảo đảm riêng của generator. SĐT chuẩn hóa định dạng +84/0084; MST ghép chính xác 10/13 chữ số, không tự ghép chi nhánh với công ty mẹ. Token mô phỏng có namespace riêng. Không tạo nút dùng chung cho trường trống.

Địa chỉ dùng chuẩn hóa văn bản chính xác, chưa có bộ giải địa chỉ hành chính hoặc fuzzy matching. Các trường chưa nhận diện được được ghi information gap. Không suy MST nhân viên từ CCCD. Link chỉ gắn vào employee/vendor đã biết trong công ty; đại diện pháp luật thuộc đồ thị chứng cứ cũ, chưa phải loại nút thứ bảy của module này.

SQLite lưu các phiên bản nguồn cho mạng lưới; hồ sơ truy vấn tại `last_seen_at`, không dùng profile tương lai thay cho lịch sử. Phiên bản cache UI lên 5; các bảng kết luận/phân công/admission không bị xóa bởi việc bổ sung graph. Test đã xác nhận giữ event hash kết luận khi cập nhật nguồn quan hệ.

## Cách gọi

Một lô tái lập, ghi vào output riêng:

```powershell
python -m sme_fraud.sync_entity_graph --data data/feature_model_sync_20261017/sme_fraud_003 --output .runtime/entity_graph/sme_fraud_003 --as-of 2025-06-30T23:59:59+07:00
```

Đồng bộ theo chu kỳ một giờ; cutoff tăng theo giờ Việt Nam:

```powershell
python -m sme_fraud.sync_entity_graph --data data/feature_model_sync_20261017/sme_fraud_003 --output .runtime/entity_graph/sme_fraud_003 --watch --interval-seconds 3600
```

[run_entity_graph_sync.ps1](../run_entity_graph_sync.ps1) hỗ trợ `-PythonExecutable`, `-Data`, `-Output`, `-IntervalSeconds`, `-Once`, `-AsOf`. Có thể dùng `-Once` làm action của scheduler hiện có, hoặc chạy `--watch` dưới process supervisor. Chưa đăng ký Windows Scheduled Task hoặc bật daemon lâu dài trong lượt này.

Reader gọi `load_snapshot(output)` để kiểm con trỏ/hash và đọc lô đầy đủ đã commit. Lô lỗi giữ nguyên `latest.json`; không lùi watermark, muốn xem lịch sử dùng output riêng. Khóa `.graph-sync.lock` ngăn hai writer; nếu tiến trình bị kill cứng cần xác minh writer đã dừng trước khi gỡ khóa treo. Snapshot cũ được giữ, chưa có chính sách tự dọn lưu trữ.

Python:

```python
from sme_fraud.entity_graph import EntityGraph

graph = EntityGraph(tables, "C001", "2025-06-30T23:59:59+07:00")
vendor = graph.actor("vendor", vendor_id)
employee = graph.actor("employee", employee_id)
path = graph.shortest_path(vendor, employee, relations=["bank_account", "phone"])
network = graph.to_json([vendor], depth=2, max_nodes=200)
```

HTTP GET khi server review đang chạy:

```text
/api/entity-graph?scenario=003&company=C001&as_of=2025-06-30T23%3A59%3A59%2B07%3A00
```

Lọc `entity_type=vendor&entity_id=...`; thêm `target_type=employee&target_id=...&relations=bank_account,phone&depth=2` để lấy đường đi. Truy vấn mạng có `depth` tối đa 6 và `max_nodes` tối đa 1.000; phần bị cắt ghi rõ trong `scope`. Không phát finding giả như đầy đủ khi thiếu nút thành viên trong phần trả về.

## Phạm vi và kiểm chứng giao diện

`KnownGraph` tiếp tục phục vụ chính sách chấm A3/B2 và danh tính hồ sơ đã audit. `EntityGraph` phục vụ truy vấn sáu loại thực thể và ngữ cảnh dữ liệu chủ rộng hơn. Shared address/MST không tự thành quan hệ cùng người nhận, không thêm điểm hoặc tự tạo hồ sơ. Các đường chứng cứ rule cũ và phản hồi reviewer được giữ nguyên.

UI thêm cửa sổ mạng lưới từ hồ sơ, giữ riêng phần cạnh bằng chứng hiện hành. Đã kiểm cú pháp JavaScript và API thật. **Chưa kiểm tra trực quan trong browser**: môi trường trả danh sách browser rỗng và không mở được IAB; [kết quả kiểm tra JS](../.runtime/entity_graph_20261017/javascript_check.json). Cần kiểm tra trực quan khi có browser trước nghiệm thu trải nghiệm.

Đã triển khai đồng bộ từ snapshot CSV/manifest; chưa kết nối ERP trực tiếp, chưa kích hoạt lịch nền hoặc chạy migration trên database vận hành của người dùng. Job công bố graph JSON độc lập; UI đọc nguồn đã nạp vào cache review và cần refresh cache theo snapshot phù hợp khi triển khai. Không chấm lại rule/model benchmark hoặc kết luận hiệu quả phát hiện từ 171 nhóm quan hệ.

Tài liệu API tham chiếu: [NetworkX MultiGraph](https://networkx.org/documentation/stable/reference/classes/multigraph.html), [connected components](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.connected_components.html), [node-link JSON](https://networkx.org/documentation/stable/reference/readwrite/generated/networkx.readwrite.json_graph.node_link_data.html).
