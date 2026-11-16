# CR-060 — validation bundle và queue shadow

**READY_FOR_REVIEW kỹ thuật; production/toàn R6 BLOCKED.**
Ngày16/11/2026, tiếp tục handoff release/rollback người dùng gửi. Base commit
`f203b39828f567171916b5b4744728ed4b63d17f`, chưa commit/push thay đổi lượt này.
Không restart/deploy Portal live hoặc thay data/model/key/phiên/quyền live.

## Đã làm và đo

- Bundle1.1/profile snapshot_case_shadow ghim study, normalization/reference,
  calibration, selected arm/fallback, grouping, threshold/case budget/mandatory/
  backlog; runtime và source/model hashes được kiểm. Registry/producer/CLI
  trusted enterprise, UI chỉ chọn plan_id, không upload metric/policy/model.
- Luồng actual snapshot → real MethodStore → selected arm → coalescing → shadow
  queue → persisted observation. Gate preview không ghi queue hoặc cấp quota.
- Execution checkpoint được commit trước queue mutation; receipt gắn pin. Test
  os._exit(77) sau queue commit/trước observation khôi phục bằng checkpoint,
  không score lại bằng bundle mới và không tăng reservation.
-119 test regression qua;37 test release/linked chạy lại sau chỉnh cuối qua;
 37 là tập con của119, không cộng thành156 test khác nhau. Fail/error/skip=0.
-5 nhóm Playwright Chrome/Portal thật cô lập qua: C001/C002 chọn đúng plan, tạo/
  gate/duyệt/chạy đến queue, reload khôi phục kết quả, cô lập DN và mobile không
  tràn. Cùng URL chỉ đổi #company cũng tải đúng DN, không giữ plan DN trước.
- Demo thực tế mỗi DN14 candidates →12 vụ, giữ3 reservation. Chạy bundle đổi
  policy version/ML weight không gửi lại3 vụ cũ:0 reservation mới,3 already_notified.
  Rollback revision3 giữ reservation [3,3,3], observation cũ và snapshot nguyên.
  Namespace active luôn trống. Các số3/weight/threshold đều fixture thử, không
  phải quyết định ngân sách/trọng số sản xuất hoặc phép so5 giao dịch.
- Kiểm model/reference/calibrator/study/runtime/scope/cutoff; giao dịch trước
  selection/calibration/reference nhận unavailable/null, không fallback vượt thời
  điểm. Đổi calendar_week sang calendar_month bị chặn để tránh reset quota.

## Lệnh đã chạy

PYTHONPATH=`D:/agent22/shared/finance_input/src`, cwd=`D:/agent22`.

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_pipeline_release --suite test_release_shadow_plan --suite test_validation_study --suite test_case_queue --suite test_remediation --suite test_he4_config_api --suite test_portal_auth --suite test_workspace_api --suite test_pipeline_benchmark --suite test_batch_training_portal --report .runtime/release-acceptance-20261116/linked-regression-v2.json
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_release_shadow_plan --suite test_pipeline_release --report .runtime/release-acceptance-20261116/linked-focused-final.json
agent2/.venv/Scripts/python.exe agent2/scripts/check_release_shadow_ui.py --output .runtime/release-acceptance-20261116/linked-browser-final
agent2/.venv/Scripts/python.exe agent2/scripts/run_release_shadow_acceptance.py --output .runtime/release-acceptance-20261116/linked-demo-final
node --check agent2/sme_fraud/web/pipeline-releases.js
```

Exit0 cho các lệnh cuối. linked-browser-v1 giữ failure khi deep-link chỉ đổi hash
chưa có hashchange handler; v2/final qua sau sửa. Evidence cũ không bị xóa/ghi đè.
JSON regression/focused/browser/comparison/release gate/rollback và SHA manifest
được lưu bên cạnh. Mã mới: release_shadow_plan.py, pipeline_release_gate.schema.json,
register_shadow_release_plan.py, check_release_shadow_ui.py,
run_release_shadow_acceptance.py, test_release_shadow_plan.py. Sửa nhỏ release
service/store/schema/API, review_server, case_queue_store, release UI.

## Giới hạn và gate chưa đủ

1. Thực thi ở DN bằng dữ liệu rõ, không gửi raw cloud. Model không nhãn thực sự
   fit/score từ MethodStore; không chạy HE trong task này. Dữ liệu supervised
   scorer trong fixture validation là mô phỏng, không được dùng làm executable
   selected arm hoặc gọi thành bằng chứng HE. Không chọn trọng số mới cho live.
2. Study được ghim chưa là phê duyệt D-09. Case policy fixture chưa được benchmark
   chất lượng cấp vụ riêng; thay case weight chỉ kiểm cơ chế release/rollback,
   không chứng minh ensemble hoặc policy tốt hơn trên doanh nghiệp thật.
3. Chưa executor full HE/supervised-shadow theo bundle, vòng đời code/key migration
   và nghiệm thu delivery thật. Quyết định owner D-04/05/06/07/09/17/18/19 còn mở;
   không có đường bật production ở profile này và không tự đóng gate.
4. Monitoring đã nối availability/fallback/case/deferred/quota/queue processing;
   phút rà, thời gian chờ, chất lượng và drift chưa có nguồn đủ nên null. Chưa
   tự nối toàn bộ hồ sơ/review/task UI vào lượt bundle, không đổi job cũ.
5. Full R6-01/02/03/04/05/06 vẫn BLOCKED theo phạm vi còn thiếu, không thay
   stage_commands mapping hoặc đánh dấu DONE. Gate kỹ thuật có bằng chứng riêng;
   không gọi các fixture pass là hiệu quả phát hiện gian lận hoặc production-ready.

Hướng dẫn producer/CLI/UI: `agent2/docs/PIPELINE_RELEASE.md` phần CR-060.
