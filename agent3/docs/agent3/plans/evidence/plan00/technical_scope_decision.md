# Quyết định phạm vi PLAN_00 — technical-functional-v1

Ngày: 11/10/2026. Căn cứ: người dùng chọn «phạm vi kỹ thuật để tiếp tục PLAN_01». Quyết định này thay gate dữ liệu thực tế ban đầu cho bước bàn giao nền móng; không thay hợp đồng kiến trúc của NEW_PLAN.

## Phạm vi được đóng

- Scope và field matrix, inventory, schema annotation/manifest v1, metric definitions.
- Bộ fixture do project tạo: 30 file (10 PDF text, 10 PDF scan, 10 PNG), biểu diễn 10 chứng từ logic; 2 biến thể duplicate và 6 negative expectations riêng.
- Kiểm chứng hash, status/value, evidence geometry, native text/scan, grouping/split và known duplicate variants. Các negative expectations được hiện thực thành runtime tests tại PLAN_01–06 theo module; chưa gọi chúng là test pipeline đã chạy.
- Generator ground truth đủ cho contract/functional development. Không cần independent human adjudication để bàn giao riêng phạm vi này; nhãn không được đổi thành HUMAN_CONFIRMED hoặc ADJUDICATED.

FATURA đã mapping/split/pilot nhưng không là đầu vào bắt buộc của gate kỹ thuật. Terms chưa xác minh, label review chưa độc lập: giữ accuracy eligibility false, không dùng cho training, calibration, phát hành dataset hoặc công bố accuracy theo quyết định này. MC-OCR tiếp tục QUARANTINE cho pipeline mới; giữ nguyên source và benchmark cũ.

## Các điều kiện chuyển sang nghiệm thu chất lượng

| ID | Điều kiện còn mở | Mốc chịu trách nhiệm và điều kiện chặn |
|---|---|---|
| DQ-01 | Bộ khởi đầu hóa đơn Việt Nam thực tế: 10 PDF text, 10 scan, 10 ảnh; provenance/quyền dùng rõ; variants cùng logical family | PLAN_05 kiểm kê; PLAN_06 phải đáp ứng trước khi tuyên bố nghiệm thu capture trên hóa đơn Việt Nam thực tế. Đây là functional pilot, chưa là benchmark đại diện. Nhóm thiếu phải loại khỏi tuyên bố hỗ trợ. |
| DQ-02 | Người thứ hai đối chiếu 5 ví dụ guideline, review critical labels và phân xử bất đồng trong bộ nghiệm thu | PLAN_05 trước freeze labels; PLAN_06 kiểm bằng chứng reviewer, không dùng review AI thay xác nhận độc lập |
| DQ-03 | Exact/near duplicates, vendor/template grouping, exposure history và splits đủ độc lập | PLAN_05 trước freeze accuracy test/calibration; không tune trên test |
| DQ-04 | Điều kiện sử dụng của từng dataset được chọn; FATURA/MC-OCR chỉ cần gỡ nếu đưa vào scope sử dụng tương ứng | Trước khi sử dụng dataset cho mục đích mới. Dataset chưa đủ điều kiện được giữ ngoài bộ nghiệm thu, không chặn phát triển bằng fixture project |
| DQ-05 | Baseline theo field/family, target có owner, calibration riêng nếu bật tự động | PLAN_05; PLAN_06 không bật auto-accept khi chưa đủ bằng chứng. Có thể demo kỹ thuật/manual review với confidence UNAVAILABLE và giới hạn rõ |

Không yêu cầu train OCR để đóng PLAN_00. Không dùng việc đổi scope để công bố accuracy hoặc miễn gate chất lượng sau này.

## Bàn giao và phiên bản

PLAN_01 nhận scope `technical-functional-v1`, annotation/manifest schema v1 và fixture `functional_set_v1`; nhận các giới hạn DQ-01–05. Scope này cho phép phát triển contracts/runtime/repository và các bước pipeline tiếp theo theo dependency. PLAN_01 vẫn phải vượt gate riêng trước PLAN_02.

Giữ nguyên dataset IDs, manifests, annotation status, checksums và split assignments đã tạo. Không rebuild hay sửa nhãn chỉ để đổi trạng thái quản lý công việc. Chi tiết kiểm chứng và quyết định cuối nằm trong [gate_00.md](../gate_00.md).
