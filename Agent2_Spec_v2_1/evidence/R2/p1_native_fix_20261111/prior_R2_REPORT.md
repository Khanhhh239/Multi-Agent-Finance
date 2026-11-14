# R2 — Agent2 đang chạy local, pipeline còn PARTIAL

CR-021: bật backend tại http://127.0.0.1:8766 và giữ server chạy. [24 HTTP checks](live_run_20261111/live_http/summary.json) và [76 backend tests](live_run_20261111/backend_tests.json) qua. Snapshot lưu qua HTTP chấm đủ 3 dòng/33 feature; retry giữ một snapshot, thiếu model trả unavailable không fit. [Báo cáo chạy trực tiếp](live_run_20261111/REPORT.md).

Đây là status page/backend, chưa UI nghiệp vụ mới/CSV/Excel/HTTP scoring/queue/Portal identity. pipeline_ready=false, active_delivery=false. Runtime demo riêng, không DB cũ/active model.

**P1-NATIVE-LATE-INVOICE vẫn OPEN:** [audit chạy lại](live_run_20261111/p1_audit/summary.json) exit 2. Canonical chặn nguồn muộn đúng; raw/native vẫn đọc hóa đơn biết sau khoản chi. Chưa sửa thuật toán hay nghiệm thu toàn engine. R2 giữ PARTIAL; còn evaluator khác/benchmark/active/UI và D-03/04/09.

Lịch sử: [CR-020](p1_recheck_20261111/REPORT.md), [CR-019 và 640 regression](p1_evaluation_20261111/REPORT.md). 640 là lượt trước, không phải chạy lại CR-021; mã chấm không đổi. Overview/index trước được lưu trong live_run_20261111.
