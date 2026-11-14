# CR-027 — Bốn nhánh phân tích snapshot

**READY_FOR_REVIEW cho tích hợp được giao; R2/R5 vẫn PARTIAL.** Backend/API/UI đã nối luật nghiệp vụ, thống kê, đồ thị và ML không nhãn trong cùng một lần chấm snapshot. [Hướng dẫn sử dụng và ghim model](../../../../agent2/docs/FOUR_BRANCH_ANALYSIS.md).

## Kết quả thực hiện

- `snapshot-analysis/1.1.0` giữ đủ giao dịch, bốn nhánh/trạng thái mỗi dòng, giới hạn nguồn và mã lần phân tích. Giao dịch không trúng P1/E3 vẫn được thống kê/ML chấm.
- Ghim artifact bất biến theo tenant/doanh nghiệp phía server; chỉ mở MethodStore read-only sau kiểm quyền. Không chọn latest, không nhận model từ browser, không fit hoặc ghi model khi chấm. Sai DN/tenant/feature/runtime/tiền xử lý/thời gian hoặc thiếu model trả unavailable/null kèm lý do.
- Thống kê/ML hiển thị vị trí tương đối trên tập reference đóng băng, không gán xác suất hoặc đặt ngưỡng/cảnh báo. Đồ thị cho quan hệ/căn cứ, có chọn nút và danh sách nguồn; không cộng thành điểm rủi ro.
- Accountant chỉ nhận business DTO. Technical view vẫn cần director đúng DN. Giữ quyền Portal, auth lại trước trả và binding recheck; thiếu nguồn không thành số 0 hay no-hit.
- Giữ nguồn thiếu trên kết quả sau lưu; thêm tên NCC/số hóa đơn vào căn cứ. BR-026-02/03 đã cải thiện trình bày trong phạm vi này, vẫn cần người rà xác nhận. BR-026-01 (khoản thanh toán đầu vượt hóa đơn) còn mở, không sửa policy P1.

## Kiểm thử đã chạy

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Toàn bộ backend Agent2 | 742 pass, 0 fail/error/skip; process exit 0 | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Portal regression | 11 pass, process exit 0 | [log](portal_regression.log), [execution](portal_execution.json) |
| Demo bốn nhánh qua Portal/Chrome | 14 kiểm tra pass | [summary](company_demo_reviewed/summary.json) |
| UI nhập local regression | 19 kiểm tra pass | [report](local_browser/browser_tests.json) |
| Portal SSO/UI regression | 16 kiểm tra pass | [report](portal_browser/portal_browser_tests.json) |

Demo chính thức là **company_demo_reviewed**: C001 RobustZ + Isolation Forest, C002 RobustZ + ECOD; fit riêng bốn artifact bằng job offline trên lịch sử/reference trước kỳ đánh giá, sau đó bỏ quyền fit khỏi principal web. Mỗi DN có 5 dòng không trúng luật nhưng thống kê/ML vẫn available. Kiểm thiếu model/sai method, reload, màn hình 390px, tương tác đồ thị và không lỗi JavaScript. Fit/model-write spy bằng 0 trong inference; model DB không đổi. Nguồn và model đều mô phỏng, không chứng minh accuracy.

[Ảnh C001](company_demo_reviewed/C001-four-branches.png), [C002](company_demo_reviewed/C002-four-branches.png), [mobile](company_demo_reviewed/mobile.png). `company_demo` là lần chẩn đoán phát hiện vùng click SVG; đã thêm hit rectangle rồi chạy lại. `company_demo_final` là lượt pass trước khi chỉnh thứ tự nhánh. Chỉ `company_demo_reviewed` dùng làm bằng chứng browser cuối cùng.

## Dịch vụ hiện chạy

Đã cập nhật **riêng Agent2** bằng stop/start của Portal, không khởi động lại Portal hoặc đổi mật khẩu/quyền. Mở **http://127.0.0.1:8800/#agent2**. Snapshot cũ giữ nguyên ID/checksum (1 snapshot/3 dòng). Frontend mới được phục vụ, backend mode Portal; HTTP dùng credential local cũ vẫn bị từ chối 401.

Kho live chưa có artifact được ghim: luật partial, thống kê/ML unavailable, đồ thị available cho 3 dòng. Kiểm read-only nội bộ dùng credential worker đã có scope, không fit, không phải HTTP fallback. Không tạo/biết mật khẩu Portal và không tuyên bố đã chạy phân tích qua phiên Portal thật của người dùng; positive authenticated browser test dùng Portal/DB tạm. [Tóm tắt live](live_summary.json), [kết quả chẩn đoán](live_snapshot_read_only.json).

## Giới hạn còn lại

- Canonical rules hiện chỉ có evaluator P1/E3; các luật còn lại chưa khả dụng, tổng luật incomplete/null. Không gọi tích hợp này là hoàn tất 35 luật.
- Chưa đặt ngưỡng/ensemble, tăng trọng số, nối queue/active bundle hoặc duyệt production/full gate. Không kết luận sai phạm từ thứ hạng/đồ thị.
- Chưa có dữ liệu thật/đối chiếu nghiệp vụ để chứng minh hiệu quả ML. Muốn chấm live cần job fit riêng và pin đúng model theo hướng dẫn; model demo không tự được chuyển sang live.
- Portal vẫn dùng phiên mật khẩu workspace chung, chưa phải tài khoản riêng từng người. Nhập tệp vẫn JSON contract hiện hành.

[Provenance](provenance.json), [bảo toàn kernel/feature/model](preservation.json), [manifest hash các evidence](artifact_manifest.json).
