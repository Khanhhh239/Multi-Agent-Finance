# Evidence tooling v2.1

Setup: `python3 -m pip install -r scripts/requirements.txt`.
R0: `python3 scripts/check_evidence.py R0` hoặc `python3 scripts/run_stage.py R0` — kiểm inventory, không cần map lệnh test.
R1–R6: map stage_commands.json rồi chạy run_stage.py; điền acceptance theo kết quả mới, chạy check_evidence.py.

Mỗi command: {"argv":["verified-runner","..."],"timeout_seconds":60,"format":"junit","report_path":"path/to/fresh-report.xml"}. Cwd là repo thật. tool_version_commands là các argv trả version. Không copy command ví dụ thành command thật khi chưa xác minh.
JSON report: {"tests":[{"id":"R1-01","status":"pass"}]}. Mọi test trong report phải có trạng thái pass/fail; skipped/xfail/pending không được đổi thành pass. JUnit skipped ở bất kỳ testcase đều bị chặn. Mandatory IDs phải xuất hiện trong testcase name. Command reports có hash/run_id và acceptance phải cùng run.

Checker kiểm consistency/schema, không chứng minh AI không sửa cả test/report/script hoặc người duyệt thật. Dùng protected CI/branch, review test assertions và quyền người duyệt khi cần trust boundary. Chưa xác minh repository thì không tuyên bố đã test app.
