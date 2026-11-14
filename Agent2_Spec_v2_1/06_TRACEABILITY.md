# Ma trận truy vết

BẮT BUỘC: test_catalog.json là nguồn ID/expected/milestone. Một test phần mềm phải mang ID trong tên testcase JUnit hoặc JSON. R0 ghi hiện trạng từng FLOW: present/not_present/not_testable; không dựng lỗi đỏ giả nếu repo không mắc. Present cần baseline regression đỏ hoặc blocker tái hiện; absent cần chứng cứ xanh.

| RULE | Mandatory test IDs |
|---|---|
| RULE-REUSE-01 | R0-01, R2-01 |
| RULE-TIME-01 | R1-02, R1-06, R2-05 |
| RULE-TENANT-01 | R1-07, R4-06, R5-02, R5-06 |
| RULE-LABEL-01 | R4-03, R5-07 |
| RULE-FIT-01 | R2-04, R2-05 |
| RULE-SCORE-01 | R2-03, R2-06, R2-07 |
| RULE-CASE-01 | R3-01, R3-04 |
| RULE-RELEASE-01 | R5-08, R6-03 |
| RULE-HE-01 | R6-06 |
| RULE-UI-01 | R5-03, R5-04 |
| RULE-MONEY-01 | R4-01, R4-02, R4-05 |
| RULE-IMPORT-01 | R1-03, R1-04 |
| RULE-TASK-01 | R0-04 |

| FLOW | Lỗi cần kiểm | Mốc sửa | Test xanh sau sửa |
|---|---|---|---|
| FLOW-01 | ML chỉ chạy sau flag luật | R2 | R2-03 |
| FLOW-02 | Top-K trong detector | R2 | R2-07 |
| FLOW-03 | Budget trước gộp | R3 | R3-01 |
| FLOW-04 | Danh mục tương lai | R1 | R1-02 |
| FLOW-05 | Missing thành 0/xác suất giả | R2 | R2-06 |
| FLOW-06 | Fit ngay trong scoring | R2 | R2-04 |
| FLOW-07 | Hai UI hai đường chấm | R5 | R5-04 |
| FLOW-08 | Rerun double-send | R3 | R3-04 |
