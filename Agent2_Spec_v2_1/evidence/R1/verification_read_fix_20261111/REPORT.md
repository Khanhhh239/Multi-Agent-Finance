# Sửa BR-07 — quyền đọc chứng từ đã xác minh

Ngày 11/11/2026, CR-010, spec 2.1. Đã sửa trong phạm vi người dùng giao. R1 vẫn **PARTIAL** vì BR-08 về lịch sử phân bổ thiếu nguồn còn mở; đây không phải phê duyệt dữ liệu thật/production.

## Thay đổi và ranh giới quyền

Trước sửa, `build_from_snapshot` gọi đường raw `build_feature_rows`, áp lại quyền ghi nhận xác minh của người chạy job. Người được phép đọc cùng snapshot nhưng không có `evidence.verify` nhận lỗi 422.

Sau sửa, `build_from_snapshot` chỉ chọn nhánh đọc nội bộ **sau** khi store đã kiểm scope và checksum manifest/dữ liệu. Nhánh này không áp lại riêng lỗi `VERIFICATION_PERMISSION`: đây là đọc trạng thái đã được xác nhận tại commit, không phải thao tác xác minh mới. Toàn bộ lỗi validation khác vẫn chặn. Không sửa chứng từ, bổ sung quyền cho scope hoặc đưa cờ bỏ kiểm tra vào API/DTO.

`build_feature_rows` raw/offline, validate, preview và commit vẫn kiểm quyền xác minh như trước. Quyền tenant/DN, đọc snapshot và thu hồi quyền trước xuất vẫn giữ nguyên. Code thay đổi tại `agent2/sme_fraud/snapshot_features.py`; không thay `imports.py`, auth, store, schema chung hoặc kernel số học.

Feature adapter patch **1.0.1**, giữ nguyên 33 cột. Contract ghi rõ hành vi đọc, version/fingerprint mới phân biệt artifact. Artifact cũ không bị ghi đè; không tự khai báo model/cache khác fingerprint là tương thích. `evidence/R1/feature_contract.json` là contract hiện hành; bản 1.0.0 vẫn nằm trong evidence CR-008/009.

## Kiểm chứng

- **Trước sửa:** thêm 6 regression tests, chạy thật có 2 error (job đọc verified và ca thu hồi quyền sau build đều bị chặn quá sớm), 4 pass. [JSON](before_tests.json), [log](before_tests.log).
- **Sau sửa:** 71 focused tests pass, gồm 6 ca mới, snapshot features và hợp đồng đầu vào. [JSON](focused_tests.json), [log](focused_tests.log).
- Tài khoản chỉ có `data.import` tạo được artifact từ snapshot verified; số chứng từ original verified của T001 = 1. Bytes snapshot trước/sau và permission của người đọc không đổi.
- Cùng tài khoản không thể commit một import verified mới; raw builder vẫn từ chối. Các lỗi verification missing/time/reference/tenant khác không được bỏ qua. Sai DN hoặc thiếu quyền đọc bị chặn; thu hồi credential sau build không để lại output.
- Chạy lại bộ rà nghiệp vụ: **528 giá trị số/null vẫn khớp, BR-07 pass; tổng 7/8 ca pass, BR-08 fail như đã báo trước**. [Kết quả](business_review/review_checks.json), [log](business_review.log). Exit 1 của công cụ rà là lỗi BR-08 còn mở, không phải tuyên bố toàn bộ R1 đã đạt.
- Demo chạy thành công; [log demo](demo.log). Artifact mới nằm trong kho `.runtime/feature_demo`, tách khỏi evidence trước.
- Native regression: **514 tests, 7/7 mandatory IDs pass**, 0 skip/failure/error, 163,932 giây. [JSON](native_tests.json), [log](native_tests.log); tổng hợp trong `provenance.json`.
- Đối chiếu channels trước/sau, checksum nguồn và lệnh thực thi: [provenance.json](provenance.json). Fixture chuẩn, lõi cũ và báo cáo trước được giữ nguyên.

## Chạy lại

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py `
  --suite test_snapshot_verification_access --report agent2/.runtime/verification-read-tests.json
```

Ca kiểm tra quyền dùng nguồn giả lập với metadata verified để thử đường đọc/ghi, không phải chứng từ gốc thực tế. Người duyệt nghiệp vụ chưa được chỉ định; không ghi DONE hoặc chuyển mốc. Bước tiếp theo của R1 là xử lý BR-08 theo yêu cầu riêng.
