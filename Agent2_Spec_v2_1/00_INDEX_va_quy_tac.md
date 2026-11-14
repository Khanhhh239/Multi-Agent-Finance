# Agent2 — Bộ đặc tả v2.1

Ngày 10/11/2026. Trạng thái: đặc tả đã tổ chức lại; chưa kiểm tra repository, chưa nghiệm thu phần mềm.

## Bắt đầu

Đọc file này, `99_decision_log.md`, rồi `tasks/R0.md`. Mỗi lượt chỉ làm một task card được giao; kết thúc dừng lại và báo cáo, không tự chuyển mốc. Dùng [98_PROGRESS.md](98_PROGRESS.md) theo dõi; trạng thái ban đầu đều NOT_STARTED. AI chỉ nâng tới READY_FOR_REVIEW; người duyệt ghi DONE. Thay đổi chỉ đạo lưu CHANGE_REQUESTS.md.

## Đọc gì cho mốc nào

| Mốc | Đọc đặc tả | Phụ thuộc | Sản phẩm |
|---|---|---|---|
| R0 | 04_contracts_states_modules; 99; tasks/R0 | Repo và nguồn | Inventory, môi trường, test map |
| R1 | 01 mục dữ liệu/feature; 03 mục import; 04 | R0 | Snapshot và validation chung |
| R2 | 01 mục detector; 04; 05; 06 | R1 | Adapter và fit/refit không nhãn |
| R3 | 01 mục phối hợp/vụ; 04 | R2 | Orchestrator, queue, budget |
| R4 | 02; 04 | R1 cho đối chiếu/hồ sơ; R3 cho tích hợp | Đối chiếu, hồ sơ, khắc phục, báo cáo |
| R5 | 03; 04 | R4 | Hai UI, auth và config lifecycle |
| R6 | 05; 99; 04; 06 | R5 | Shadow, nghiệm thu, rollback |
| F1–F3 | 90_future_TH1_TH2 | Giao việc riêng | Synthetic/HE; không chặn R0–R6 |

Tên file bắt đầu bằng số trong bảng trỏ tới file cùng tiền tố trong thư mục. Mọi task card liệt kê liên kết và đầu ra cụ thể.

## Quy tắc bất biến — nguồn chuẩn duy nhất

Tất cả các RULE dưới đây là **BẮT BUỘC**. Các file khác trỏ ID; thay đổi quy tắc phải sửa tại đây và kiểm tra impact.

| ID | Quy tắc |
|---|---|
| RULE-REUSE-01 | Kiểm kê và bọc adapter cho luật, điểm/xác suất, đồ thị, ML không nhãn dùng được; chỉ thay phần sai có bằng chứng |
| RULE-TIME-01 | Feature/quan hệ chỉ dùng thông tin đã biết tại as_of; nhóm đồng thời chấm trước cập nhật lịch sử |
| RULE-TENANT-01 | Backend kiểm tra tenant và quyền trên mọi đường đọc/ghi/job/export; không dựa vào nút ẩn |
| RULE-LABEL-01 | Nhãn confirmed 0/1 phải có căn cứ và phạm vi; unreviewed/inconclusive là null; điểm model và giao dịch bằng chứng không tự sinh nhãn |
| RULE-FIT-01 | ML không nhãn được fit/refit lịch sử trong job riêng có version; không fit trong request chấm; thiếu artifact cần thiết trả unavailable |
| RULE-SCORE-01 | Chấm mọi dòng khả dụng trước flags; thiếu điểm là null; percentile/heuristic không phải xác suất; fallback phải được đánh giá |
| RULE-CASE-01 | Gộp theo nghĩa vụ/bằng chứng đúng DN trước budget; tách candidate và evidence; rerun/retry/concurrency không gửi trùng |
| RULE-RELEASE-01 | Đổi cấu hình bằng revision, kiểm định và shadow; giữ audit/rollback; không active khi gate chưa đạt |
| RULE-HE-01 | Không giả HE bằng plaintext; khóa/phiên/giao thức phải tương thích; raw data không lên cloud chỉ vì UI dùng chung |
| RULE-UI-01 | Kế toán được thấy căn cứ/giới hạn và hành động; ẩn thuật toán/tham số cả trong DTO; giám đốc cấu hình trong quyền DN |
| RULE-MONEY-01 | Tiền VND dùng số nguyên, giữ dấu điều chỉnh; không gộp tiền liên quan thành tổn thất hoặc cộng trùng |
| RULE-IMPORT-01 | Backend xác nhận import, snapshot/version bất biến; preview và commit cùng hash/context; reject/quarantine tường minh |
| RULE-TASK-01 | Mỗi task kết thúc bằng báo cáo và dừng; thiếu quyết định chặn thì báo BLOCKED, tiếp tục phần độc lập trong chính task |

## Cách đọc mức yêu cầu

- **BẮT BUỘC:** các RULE, schema/state contract, đầu ra và acceptance task.
- **ĐỀ XUẤT:** chỉ áp trong phạm vi thử nghiệm được ghi trong decision log; ghi ID cấu hình đã dùng.
- **CHƯA CHỐT:** có owner theo vai trò, hạn theo milestone và phạm vi bị chặn ở decision log; không tự suy thành đã duyệt.
- Ví dụ số liệu không là ngưỡng sản xuất. Tiêu chí kỹ thuật có thể chốt cố định; ngưỡng chất lượng cần dữ liệu/owner quyết định.

## Nguồn và độ ưu tiên

Quyết định người dùng mới nhất → quyết định APPROVED trong 99 → RULE → hợp đồng 04 → task card → chi tiết 01–03 → phụ lục 90 → tài liệu nguồn. Mâu thuẫn phải ghi issue, không âm thầm chọn.

Nguồn DOCX được kèm trong `sources/`; `sources/manifest.json` ghi hash. Bản v1.3 nằm ở archive/, chỉ giữ dạng lịch sử, không nạp mặc định cho mọi task. Nếu nguồn không có trong gói, R0 phải ghi thiếu, không giả đã đọc. Bộ tài liệu này không xác nhận stack/đường dẫn repo chưa được kiểm kê.

## Changelog

- v1.0: pipeline, TH1/TH2 và runtime.
- v1.1: hai UI theo quyền, import dùng chung, rõ ML không nhãn.
- v1.2: chức năng nghiệp vụ và tái cấu trúc R0–R6.
- v1.3: xác nhận ML không nhãn vẫn cần fit/refit.
- v2.1: tách file theo milestone; task card riêng; decision log, contract/state chuẩn, tiến độ, lệnh kiểm tra và nguồn đóng gói. Không tuyên bố đã triển khai R0–R6.

- v2.1: sửa vòng phụ thuộc R0; checker/runner JUnit/JSON có timeout và provenance; FLOW/RULE traceability; fixture owner; 05_evaluation riêng; reviewer gate và CR log. Kiểm toàn bộ gói bằng SHA256SUMS.
