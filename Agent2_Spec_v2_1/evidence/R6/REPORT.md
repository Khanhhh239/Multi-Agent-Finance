# CR-059 — nghiệm thu release infrastructure/staging

**READY_FOR_REVIEW kỹ thuật; toàn R6/production BLOCKED.**
Ngày địa phương:16/11/2026. Base commit `f203b39828f567171916b5b4744728ed4b63d17f`;
thay đổi lượt này chưa commit/push. Mã nguồn ở `D:/agent22/agent2`, tích hợp Portal
ở `D:/agent22/portal/agent2_bridge.py`. Không triển khai hoặc restart live.

## Kết quả đã đo

-100 test regression qua, fail/error/skip=0; riêng release24 ca.
-8 nhóm Playwright Chrome/Portal thật cô lập qua: C001 tạo/duyệt/chạy4 giao dịch,
  reload xem lại, resume bundle cũ sau switch, rollback revision3, production
  blocked, C002 độc lập/reload đúng DN, desktop/mobile và thu hồi quyền director.
- Hard-crash tiến trình thật sau INSERT activation nhưng trước pointer/commit:
  transaction rollback toàn phần; restart/retry chỉ tạo1 activation.
- Hai connection cùng revision chỉ1 thành công/1 conflict; retry sau mất phản hồi
  không tăng revision; model thực fit offline được ghim và kiểm reference/preprocess.
- Rollback không đổi dữ liệu logic của snapshot, queue/budget/outbox, task và label
  stores. Recover outbox cũ không thêm case; không restore toàn DB.
- Demo C001/C002 so replay baseline/candidate cùng snapshot/as_of, cùng detector
  pins: kết quả giống nhau theo checksum. Đây là thay metadata bundle, **không phải
  thử model tốt hơn hoặc so hiệu quả nghiệp vụ ở budget5**.

## Lệnh và evidence

Đặt PYTHONPATH=`D:/agent22/shared/finance_input/src` từ root repo.

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_pipeline_release --suite test_case_queue --suite test_workspace_api --suite test_portal_auth --suite test_he4_config_api --suite test_remediation --suite test_batch_training_portal --suite test_pipeline_benchmark --report .runtime/release-acceptance-20261116/regression-final.json
agent2/.venv/Scripts/python.exe agent2/scripts/check_pipeline_release_ui.py --output .runtime/release-acceptance-20261116/browser-v3
agent2/.venv/Scripts/python.exe agent2/scripts/run_pipeline_release_acceptance.py --test-report .runtime/release-acceptance-20261116/regression-final.json --output .runtime/release-acceptance-20261116/demo-v1
node --check agent2/sme_fraud/web/pipeline-releases.js
```

Exit0 cho cả4 lệnh. Bản JSON chi tiết đã sao chép vào thư mục evidence này;
manifest SHA256 ghi nguồn đo. Browser v1/v2 giữ lại failure mobile do CSP chặn
inline style. Bản v3 chuyển CSS sang asset cùng origin và không tràn viewport.
Không nới CSP hoặc xóa evidence cũ.

File chính: pipeline_release_store.py, pipeline_release.py, pipeline_release_api.py,
pipeline_release.schema.json, web/pipeline-releases.*, tests_he/test_pipeline_release.py,
scripts/check_pipeline_release_ui.py, scripts/run_pipeline_release_acceptance.py.
Tích hợp nhỏ review_server/workbench/case_queue_api và Portal allowlist/settings link.
Hướng dẫn: `agent2/docs/PIPELINE_RELEASE.md`.

## Gate và phần còn thiếu

R6-01 BLOCKED: chưa chạy/chứng minh mọi mandatory R1–R5 cùng full gate mapping.
R6-02 BLOCKED: replay smoke không thay baseline/candidate quality study cùng budget.
R6-03 BLOCKED toàn pipeline: đã đạt phần pointer/DB preservation và outbox fixture;
chưa HE/ensemble/delivery release end-to-end cùng một bundle.
R6-04 BLOCKED: runtime/availability đã đo; drift/fallback/backlog/review metric
attribution và trigger policy chưa nối đầy đủ, giữ null/lý do.
R6-05 BLOCKED: D-09 và D-04/05/06/07/17/18/19 chưa được owner chốt.
R6-06 BLOCKED toàn profile: executor staging là local-clear, công bố he_execution
false, không gửi raw cloud; chưa nghiệm thu full HE release thật trong task này.

Staging duyệt24h chỉ dùng kiểm chứng kỹ thuật, không là ngưỡng chất lượng sản xuất.
Production không có đường bật trong profile hiện tại. Cần full executor và policy/
quality evidence adapter có approval tin cậy trước khi mở production. Các API cũ
không tự được coi là đã ghim release; trên node bật release service, tạo vụ active
mới qua evaluate/reevaluate bị chặn. Giao nhận đã lưu/phiếu/task giữ luồng cũ.
Workspace Portal chưa xác minh danh tính người duyệt độc lập. Không tuyên bố dữ
liệu mô phỏng chứng minh khả năng phát hiện gian lận thật.
