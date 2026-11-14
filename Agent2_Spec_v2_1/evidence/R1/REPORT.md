# REPORT — R1, sau sửa BR-07/08 ngày 11/11/2026

- spec_version: 2.1; **READY_FOR_REVIEW — BR-07 và BR-08 đã sửa, chờ người duyệt thật**.
- Báo cáo hiện hành: [Sửa lịch sử thiếu nguồn](prior_history_fix_20261111/REPORT.md). Các prior feature và exact total thiếu revision nguồn trả null/missing với allocation provenance và cách bổ sung; số 0 thật vẫn giữ. Adapter 1.1.0 giữ 33 cột, semantics missing/evidence được version. [Sửa quyền đọc trước đó](verification_read_fix_20261111/REPORT.md) tiếp tục có regression đạt; chưa fit ML hoặc chuyển R2.
- Gate formal mới: **527 tests, 7/7 mandatory IDs pass**, 0 skip/failure/error, 168,080 giây; [kết quả](prior_history_fix_20261111/native_tests.json). Checker exit 0, run_id `5759a8dd-9b06-4143-aaca-640fa1e876c2`, release_approved=false. Có 13 ca mới về lịch sử thiếu nguồn, 6 ca quyền đọc đã thêm trước đó. Bộ rà nghiệp vụ hiện **8/8 ca đạt**, 528 giá trị số/null vẫn khớp; [kết quả rà](prior_history_fix_20261111/business_review/review_checks.json).
- [Báo cáo trước sửa CR-009](business_review_20261111/REPORT.md) và baseline/evidence cũ được giữ nguyên; khi đó bộ rà 6/8 ca đạt và phát hiện hai lỗi.
- Đã nối hợp đồng CR-005, validation CR-006, snapshot CR-007 và feature/replay CR-008 theo yêu cầu người dùng.
- Báo cáo bàn giao kỹ thuật trước đợt rà CR-009: [Snapshot feature và nghiệm thu R1](feature_replay_20261111/REPORT.md).
- Gate **CR-008 trước rà**: 508 native tests, 7/7 mandatory R1 IDs pass, 0 skip/failure/error. Checker exit 0, run_id b136fe73-dc33-49c3-889c-2553ce70b4cc, release_approved=false. Kết quả này không phải xác nhận hai lỗi mới đã được sửa.
- [acceptance.json](acceptance.json), [machine report](machine_report_0.json), [command provenance](commands_result.json), [checker hiện hành](prior_history_fix_20261111/checker_result.json).
- Snapshot bất biến → core feature nguyên bản qua adapter version mới: 33 numeric/null columns, per-row known/event cutoff, lịch sử trước nhóm đồng thời, ID/nhãn/evidence tách predictor.
- Current output: import_contract.json, snapshot_contract.json, feature_contract.json (adapter 1.1.0), fixture_manifest.json, module_map.csv và prior_history_fix_20261111/artifact_manifest.json. Các manifest cũ giữ lại để đối chiếu phiên bản trước.
- Demo: `agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/demo_snapshot_features.py`; chỉ dữ liệu mô phỏng và kho riêng. Không fit/chấm ML nghiệp vụ.
- Portal identity/UI/CSV/Excel, R2 model registry/fit/score và active queue chưa mở. Dữ liệu thật/production cần quyết định/nguồn/reviewer theo 99, không được suy từ fixture xanh.
- Báo cáo/kết quả trước được giữ tại feature_replay_20261111/prior_R1_REPORT.md và các thư mục CR-005/006/007; không xóa baseline hoặc đổi tolerance để đạt gate.
- Người thực hiện kỹ thuật: Codex; người duyệt thật chưa được chỉ định. Reviewer người thật mới ghi DONE. Dừng R1, không tự chuyển R2.
