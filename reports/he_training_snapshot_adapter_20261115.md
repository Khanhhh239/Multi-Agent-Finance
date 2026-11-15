# Snapshot nghiệp vụ → dữ liệu train HE — 15/11/2026

**READY_FOR_REVIEW kỹ thuật.** Đã nối snapshot đã commit vào bước chuẩn bị
dữ liệu train của prototype HE; không còn bắt buộc tự nhập ma trận 4x2.

## Đầu vào và mapping

Adapter đọc kho snapshot bằng mode=ro/query_only, kiểm quyền/checksum và gọi
lại bộ feature point-in-time hiện có. Hỗ trợ canonical 1.0/1.1/1.2 và profile
nguồn đầy đủ `agent2-rule-snapshot/1.0.0`.

Hai cột theo thứ tự `round_million`, `creator_equals_approver` được giữ nguyên
0/1, chỉ đổi biểu diễn số sang int64. Thiếu người duyệt hoặc nguồn không đủ
không thành0. Không scale/round/clip, không chuyển số tiền/mã giao dịch/nhãn/
điểm luật vào predictor. Đây là mapping nối luồng, chưa chứng minh giá trị dự báo.

Chọn rõ **4 ID/revision** và kỳ `[start,end)`; không lấy bốn dòng đầu, chọn theo
cảnh báo hay cắt lịch sử. Giữ đủ từng dòng kết quả kiểm tra. Có lỗi thì x=null,
không provision/encrypt theo lệnh prepare-snapshot; preview chưa tạo khóa HE.

## Các ràng buộc đã kiểm

- Đúng tenant/company/snapshot, kể cả hai DN có cùng transaction IDs.
- Giao dịch/phiên bản đã khả dụng tại as_of, nằm trong kỳ train.
- Chứng từ/phê duyệt đến muộn không đổi feature của quá khứ; coverage được
  khai báo sau as_of không bật được feature cho kỳ quá khứ.
- Null/missing và giá trị ngoài miền có lỗi dòng/trường/cách sửa; không impute.
- Mapping/source/selection/window/code thay đổi không dùng lại preview cũ.
- DB chỉ đọc, không tạo kho rỗng hoặc yêu cầu evidence.verify chỉ để đọc nguồn
  đã lưu. Chuẩn bị dữ liệu train cần model.fit.
- Nguồn mô phỏng và thật không bị trộn rồi nhận nhãn thật.

`plan_sha256` khóa snapshot/checksum, cutoff/window, rows/revision, mapping và
source feature contract/code hashes. Kế hoạch được ghi trong dataset đã ký tại
DN và theo model candidate sau này. Cloud không nhận provenance/ID nguồn rõ.

## Kết quả

| Phần kiểm | Kết quả |
|---|---|
| Adapter snapshot và regression prototype training | 28 test qua |
| Snapshot mô phỏng đã commit → Concrete encryption → HTTP signed receipt | C001/C002, 2/2 qua |
| X tính tay trước chạy, theo thứ tự bốn giao dịch | [[1,1],[0,0],[1,0],[0,1]], khớp cả hai DN |
| Retry prepare/upload | Giữ cùng dataset/biên nhận |
| Template nhãn | Các nhãn vẫn null, đúng dataset đã upload |
| Jobs train tạo trong phép thử này | 0 |

Nghiệm thu native dùng context DPAPI mô phỏng thật từ prototype trước, không
sinh lại/đổi khóa, không dùng khóa/model/DB Portal live. Phép thử xác nhận đầu
vào và upload, **không tuyên bố đã train model mới hoặc đo accuracy gian lận**.

## Dùng và xem bằng chứng

[Hướng dẫn](../agent2/docs/HE_TRAINING_SNAPSHOT_ADAPTER.md),
[request mẫu](../agent2/examples/encrypted_training/snapshot-request.example.json),
[bằng chứng](../Agent2_Spec_v2_1/evidence/HE/training_snapshot_adapter_20261115/REPORT.md).

CLI có `preview-snapshot` và `prepare-snapshot`. Xem preview, ghi hash đã duyệt
vào config operator rồi mới mã hóa; tiếp tục upload/xác minh nhãn/confirm bằng
luồng hiện có. Cần kho snapshot và build/context HE đã được cấp riêng.

Chưa mở rộng batch quá4, chưa train đủ33 feature, chưa có màn hình Portal mới.
Mapping chỉ gồm hai biến binary; circuit lượng tử hóa thô có thể không cập
nhật weights trên một số batch. Model mang mapping snapshot cần fingerprint
tương ứng khi chấm shadow; không dùng ma trận demo không rõ mapping.

Không sửa core feature/engine, contract33, model/DB/khóa/quyền hay dịch vụ live;
không tự tạo nhãn gian lận, thay queue hoặc chốt DONE R0–R6. Chưa push Git.
