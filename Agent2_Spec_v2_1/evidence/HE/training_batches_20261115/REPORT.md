# CR-057 — train nhiều batch bản mã

READY_FOR_REVIEW kỹ thuật. [Báo cáo](../../../../reports/he_training_batches_20261115.md)
và [hướng dẫn operator](../../../../agent2/docs/HE_TRAINING_BATCHES.md).

`native_checks.json`: Concrete thật hai doanh nghiệp, oracle, holdout và SIGKILL
C001 sau checkpoint1. `latest_worker_restart.json`: kiểm guard mới trên cached
ciphertext thật cả hai DN; không tính thêm HE. `unit_tests.json`: test IDs hợp
nhất, không cộng lặp lượt chạy. `source_hashes.json`: nguồn tại lúc tổng hợp.

Worker source hash trước native run và sau guard bổ sung ghi riêng trong báo cáo
kiểm lại. Không có khóa, ciphertext, source/holdout thật hoặc credential ở đây.
Nguồn/nhãn là mô phỏng; không xác nhận accuracy, triển khai live hoặc gate DONE.
