# REPORT — R1, sau sửa quyền đọc BR-07 ngày 11/11/2026

- spec_version: 2.1; **PARTIAL — BR-07 đã sửa, còn BR-08 trước nghiệm thu**.
- Báo cáo hiện hành: [Sửa quyền đọc chứng từ đã xác minh](verification_read_fix_20261111/REPORT.md). Người đọc snapshot tạo feature được mà không cần quyền ghi xác minh; raw/import vẫn kiểm quyền, mọi lỗi khác và quyền đọc/revocation vẫn chặn. Adapter 1.0.1 giữ nguyên 33 cột/phép tính; chưa fit ML hoặc chuyển R2.
- Chạy lại regression: **514 tests, 7/7 mandatory IDs pass**, 0 skip/failure/error; [kết quả mới](verification_read_fix_20261111/native_tests.json). Có thêm 6 ca regression về quyền đọc/ghi xác minh. Bộ rà nghiệp vụ hiện **7/8 ca đạt**, 528 giá trị số/null vẫn khớp. BR-08 về liên kết phân bổ lịch sử thiếu revision nguồn trả 0 còn mở; xem [kết quả rà](verification_read_fix_20261111/business_review/review_checks.json).
- [Báo cáo trước sửa CR-009](business_review_20261111/REPORT.md) và baseline/evidence cũ được giữ nguyên; khi đó bộ rà 6/8 ca đạt và phát hiện hai lỗi.
- Đã nối hợp đồng CR-005, validation CR-006, snapshot CR-007 và feature/replay CR-008 theo yêu cầu người dùng.
- Báo cáo bàn giao kỹ thuật trước đợt rà CR-009: [Snapshot feature và nghiệm thu R1](feature_replay_20261111/REPORT.md).
- Gate **CR-008 trước rà**: 508 native tests, 7/7 mandatory R1 IDs pass, 0 skip/failure/error. Checker exit 0, run_id b136fe73-dc33-49c3-889c-2553ce70b4cc, release_approved=false. Kết quả này không phải xác nhận hai lỗi mới đã được sửa.
- [acceptance.json](acceptance.json), [machine report](machine_report_0.json), [command provenance](commands_result.json), [checker](feature_replay_20261111/checker_result.json).
- Snapshot bất biến → core feature nguyên bản qua adapter version mới: 33 numeric/null columns, per-row known/event cutoff, lịch sử trước nhóm đồng thời, ID/nhãn/evidence tách predictor.
- Current output: import_contract.json, snapshot_contract.json, feature_contract.json (adapter 1.0.1), fixture_manifest.json, module_map.csv và verification_read_fix_20261111/artifact_manifest.json. Manifest CR-008 giữ lại để đối chiếu phiên bản cũ.
- Demo: `agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/demo_snapshot_features.py`; chỉ dữ liệu mô phỏng và kho riêng. Không fit/chấm ML nghiệp vụ.
- Portal identity/UI/CSV/Excel, R2 model registry/fit/score và active queue chưa mở. Dữ liệu thật/production cần quyết định/nguồn/reviewer theo 99, không được suy từ fixture xanh.
- Báo cáo/kết quả trước được giữ tại feature_replay_20261111/prior_R1_REPORT.md và các thư mục CR-005/006/007; không xóa baseline hoặc đổi tolerance để đạt gate.
- Người thực hiện kỹ thuật: Codex; người duyệt thật chưa được chỉ định. Reviewer người thật mới ghi DONE. Dừng R1, không tự chuyển R2.
