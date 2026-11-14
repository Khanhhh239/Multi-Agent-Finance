# CR-036 — Đã bật HE và kiểm luồng Portal có đăng nhập, READY_FOR_REVIEW

Portal **8800**, Agent2 **8766** và worker bản mã **8868** đang chạy. Agent2 dùng đúng bộ C001/C002 đã chuẩn bị; người dùng chỉ chọn doanh nghiệp/bản dữ liệu 5 dòng rồi chạy. [Hướng dẫn sử dụng và vận hành](../../../../agent2/docs/HE_PORTAL_ACTIVATION.md).

**Trạng thái nghiệm thu live:** người dùng đã tự đăng nhập bằng mật khẩu hiện tại và xác nhận trong chat. Helper tiếp tục qua đúng phiên đó, **7 bước pass trên Portal thật**: C001/C002 mỗi bên đủ 5 điểm đã giải mã, reload giữ nguyên mã lần chạy và 5 kết quả, không JS error. Không bypass/reset mật khẩu, chèn session hoặc dùng credential test thay user. [Báo cáo UI live](live_ui_check.json), [C001](C001-completed.png), [C002 sau reload](live-completed.png).

## Bằng chứng hiện có

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Dịch vụ/đúng cấu hình/guard/bảo toàn | pass; Portal/Agent2 auth mode portal, worker đúng public verify key; API catalog không session trả 401 | [activation_status.json](activation_status.json) |
| Trang mật khẩu hiện tại | pass; gate có password, không hiện form đặt mật khẩu mới, không JS error | [login_page_check.json](login_page_check.json) |
| UI Portal thật sau người dùng đăng nhập | **7 checks pass**, mỗi DN 5 điểm, reload giữ run ID/kết quả | [live_ui_check.json](live_ui_check.json), [ảnh C001](C001-completed.png), [ảnh C002](C002-completed.png) |
| Checker độc lập trên bộ đã bật | **40 checks pass**, không đụng state web/worker live | [packet_check.json](packet_check.json) |
| Sửa checker 1.1/SQLite reopen/no-fit/isolation/no overwrite | **7 tests pass**, exit 0 | [log cuối](focused_final.log), [execution](focused_final_execution.json) |
| Luật/đồ thị/ML/33-feature core | 17 source hash giữ nguyên | [preservation.json](preservation.json) |

40 checks kiểm metadata/nguồn/khóa/record checksum, đủ 5 dòng mỗi DN, parity và đọc chéo bị chặn trên worker kiểm tra riêng. Tách riêng bằng chứng **7 checks live** qua đăng nhập thật; không dùng 40 checks thay cho chúng. Bộ 145 HE + 742 native và 17 browser pass ở [CR-034](../web_analysis_20261112/REPORT.md) là evidence trước trên server tạm. Không chạy lại hai bộ đầy đủ trong lượt chỉ đổi config và helper checker này.

## Các thay đổi đã áp dụng

- Backup portal/config.local.json vào packet private trước khi đổi. Chỉ agents.agent2 trỏ sang snapshot/model/pins/quyền demo; env HE dùng config 1.2.0/DPAPI. Workspace, security/password, company và agent1/3/4 config không đổi. DB snapshot/model/quyền cũ không ghi đè, hai private DPAPI keys và fitted model bytehash giữ nguyên.
- Restart Portal/Agent2 để nạp code/cấu hình hiện tại. Bản Portal cũ để lại child interpreter giữ 8766 sau stop; đã đối chiếu đúng PID/command/parent rồi dừng riêng child. Không dừng Agent1. Agent1 tiếp tục cùng PID/cổng 8011, nhưng owned=false ở Portal mới vì Popen cũ không còn; không tự tái sở hữu/restart nó. Agent3/4 giữ tắt.
- Worker 8868 từ bundle allowlist, env được lọc và khóa phản hồi khớp config node; raw data/model/HE secret key không vào bundle. Health/landing mới được kiểm trực tiếp; chưa cloud public/TLS production hoặc OS sandbox.
- Mật khẩu đã cấu hình được giữ nguyên, session cũ hết khi Portal restart. Người dùng tự đăng nhập trong Chrome rồi helper kiểm các thao tác phân tích; không đọc mật khẩu/FaceID, không lưu token vào report hoặc config. Công cụ Chrome extension lỗi khi tạo tab; fallback Playwright đã được user cho phép trước đó, không làm yếu CSP hoặc auth.

## Sửa lỗi được phát hiện lúc kích hoạt

SnapshotStore chạy PRAGMA/schema init làm thay binary checksum của snapshots.sqlite3 dù snapshot/source giữ nguyên. Checker 1.0 vì khóa toàn file đã báo nhầm. Manifest 1.1 khóa **checksum từng immutable snapshot**; artifact model vẫn được kiểm ID/hash/contract/provenance đầy đủ. Đã xác minh đủ 4 snapshot khớp dữ liệu nguồn gốc và lịch sử model trước chuyển metadata, có backup manifest cũ, không refit/đổi khóa. Không lấy binary hash mới để che thay đổi record.

Checker cũng cần state tách biệt: không mở state_dir node đang bị web giữ lock, không khởi tạo WorkerStore trên bảng jobs của worker live. Nay dùng enterprise/check-state và worker/check-state, port trống và config tạm. Kết thúc dừng đúng cây tiến trình worker kiểm tra, xử lý Windows venv child để không giữ file log/port. Lượt focused đầu lỗi cleanup WinError32; đã sửa, **focused_final 7 pass** là evidence cuối. Các PID dịch vụ live giữ nguyên qua check.

## Vận hành và giới hạn

Private activation folder giữ config trước/sau, hash bảo toàn, PID/logs và trạng thái helper. Public evidence chỉ có thông tin đã lọc; không copy key blob, worker private signing key, password hash, session, browser profile hoặc cấu hình private nguyên bản. Config và packet đều Git ignored; không commit/push.

Worker là tiến trình riêng đang chạy local, chưa Windows Service/autostart sau reboot. Hướng dẫn có cách bật lại, rollback config và lưu ý không mở hai node cùng state_dir. Đổi model/nguồn không tự fit; missing/expired/no model vẫn unavailable, không plaintext fallback. Vẫn Mahalanobis 2 feature, 5 dòng mô phỏng/DN, không bốn nhánh HE/queue/accuracy/production/full gate. Chưa OS reboot hoặc cross-machine restore. R0–R6/D-11/D-12 giữ nguyên; phần kích hoạt/7 bước UI live READY_FOR_REVIEW, không tự ký DONE sản phẩm.

[Source/provenance](source_provenance.json), [kiểm tra tĩnh](validation.json), [manifest](artifact_manifest.json).
