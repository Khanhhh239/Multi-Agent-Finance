# CR-024 — màn hình nhập → kiểm tra → lưu → kết quả

Trạng thái **READY_FOR_REVIEW cho lát cắt UI được giao**, R5 tổng thể **PARTIAL**. Chưa có duyệt nghiệp vụ/production hoặc full R2/R4/R5 gate. Nguồn chỉ mô phỏng.

## Kết quả

Root http://127.0.0.1:8766/ đã là màn hình mới, gọi HTTP API và kho snapshot thực. Chọn DN từ membership active phía backend, nhập JSON UTF-8, kiểm tra lỗi dòng/trường/cách sửa và các phần thiếu nguồn trước khi xác nhận lưu. Đổi tệp/DN phải kiểm tra lại, xác nhận tệp cùng SHA256, preview còn hạn; commit giữ key chống trùng khi mất phản hồi. Snapshot bất biến, không thay bản cũ.

View review hiển thị DN/snapshot/checksum/analysis_id/as_of/kỳ giao dịch. Mỗi kiểm tra có lý do, căn cứ có thời điểm, nguồn còn thiếu và bước tiếp theo. unavailable khác no_signal; bộ lọc no_signal không nhận dòng còn cảnh báo/thiếu kiểm tra. Nhóm thanh toán tách riêng một lần. VND 18 chữ số giữ chính xác bằng parser chuỗi/BigInt; nguồn nhập không đổi byte, nội dung không được dùng làm HTML.

## Bằng chứng

- **692/692 backend tests pass**, 0 failures/errors/skips, 336.962 giây: [JSON](native_tests.json), [log](native_tests.log). Trong đó 6 test mới kiểm danh sách DN theo policy, hết hạn/thu hồi, guard Host/Origin/query, static allowlist/CSP và mẫu công khai chỉ synthetic; root test cập nhật theo hành vi mới.
- **19/19 browser scenarios pass** trên Chrome qua Playwright, context/SQLite/policy tạm riêng: [report](browser_tests.json). Có invalid credential, lỗi dòng/JSON, thiếu nguồn, acknowledgment, mất phản hồi sau commit rồi retry, 5→5 dòng, nhóm duy nhất, as_of UTC+07, không đọc tương lai, reload cần xác thực lại, không lưu token vào browser storage, đổi tệp/DN, sai scope/thu hồi quyền, tệp bị sửa sau preview, preview hết hạn, VND lớn, XSS, mobile 390px và không lỗi JavaScript.
- Live cổng 8766: root/health/asset/context 200, Chrome đọc lại snapshot có sẵn, trả 3 dòng/1 nhóm. Số snapshot **1 → 1**, không ghi/fit/active/queue: [live summary](live_summary.json).
- [01-preview.png](01-preview.png), [02-results.png](02-results.png), [03-mobile.png](03-mobile.png), [04-live-results.png](04-live-results.png) đã xem trực quan. Thiếu nguồn rút gọn và mở chi tiết theo mục; không có tràn ngang trên 390px.
- [preservation.json](preservation.json): 8 kernel giữ nguyên so CR-023; không đổi hợp đồng feature/model, evaluator/score/weight hoặc các API snapshot/analysis gốc.
- [provenance.json](provenance.json) khóa command, commit nền và hash source của working tree đang sửa, không suy HEAD là source đã commit.

## Giới hạn và hướng dẫn

Xem [hướng dẫn](../../../../agent2/docs/IMPORT_WORKBENCH.md). JSON-only, chưa CSV/Excel/mapping UI. Mẫu public chỉ tenant demo/C001 và có 5 giao dịch synthetic; không lộ dữ liệu tải riêng. Phân tích hiện chỉ thanh toán hóa đơn/tên NCC, tối đa 200 transaction records/1.000 source records, không tự cắt dữ liệu. Thiếu nguồn/chứng từ chưa là không vi phạm.

Chưa nối Portal SSO/hai UI/quy trình cấu hình. UI kết nối bằng credential local do backend cấp, bearer chỉ ở bộ nhớ trang, reload phải kết nối lại; sessionStorage chỉ chứa tham chiếu snapshot/as_of. Policy/mã/kho demo giữ riêng trong .runtime và gitignore, không ghi secrets vào báo cáo. Cần quản lý cấp credential còn hiệu lực; không có tài khoản/quyền mặc định. HTTP ML/full rules/queue vẫn chưa mở.

Task kết thúc ở đây; không tự chuyển milestone hoặc ghi DONE.

## Ghi chú runner và bàn giao

PowerShell wrapper trả 1 khi redirect stderr của unittest bằng `*>`, dù JSON và cuối log xác nhận 692/692 pass. Đã tái hiện riêng bằng process Python chủ động exit 0 và ghi stderr: wrapper báo 1; đọc `$LASTEXITCODE` ngay sau cho native exit 0. Không ghi native exit của lần chạy gốc là đã quan sát được: provenance để null, ghi riêng wrapper/diagnostic. Không có test thất bại hoặc bị bỏ qua.

Kiểm tra bàn giao theo ngày client 12/11/2026: health cổng 8766 HTTP 200, credential demo còn hiệu lực, 13 hash source khớp provenance đã kiểm thử.
