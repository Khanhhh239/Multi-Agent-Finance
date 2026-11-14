# CR-035 — Bộ C001/C002 đã chuẩn bị, READY_FOR_REVIEW

Đã tạo bộ thực tế tồn tại sau khi tắt chương trình tại **D:/agent22/agent2/.runtime/he-company-demo**. Mỗi doanh nghiệp có model Mahalanobis đã fit riêng, dữ liệu mô phỏng đủ 32 dòng fit + 8 tham chiếu và 5 dòng đánh giá, snapshot bất biến và cấu hình ghim model. Khóa node DPAPI và quyền thư mục riêng được áp dụng trên bộ mới. [Hướng dẫn/tệp 5 giao dịch](../../../../agent2/docs/HE_COMPANY_DEMO.md).

## Kết quả kiểm tra

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Focused preparation/reopen/no-overwrite/no-fit/source integrity | **5 pass**, exit 0 | [log cuối](focused_final.log), [execution](focused_final_execution.json) |
| Bộ thật: model/khóa/5 dòng/cross-scope/parity | **38 checks pass** | [prepared_check.json](prepared_check.json) |
| Mở lại từ process Python mới, giữ job ID | **38 checks pass** | [reopened_check.json](reopened_check.json) |
| Windows ACL thư mục bộ mới | **pass**, chỉ user hiện tại và SYSTEM, không quyền kế thừa rộng | [acl_check.json](acl_check.json) |
| Snapshot/model/luật/feature live | Không sửa, 17 core hash giữ nguyên | [preservation](preservation.json) |

Các kiểm tra 38 gồm kiểm checksum file, khóa DPAPI mở được, metadata fit, đúng 5 dòng mô phỏng, catalog model khả dụng, tệp xuất đúng source upload, trả đủ 5 điểm HE, so với model.score tại DN, idempotency và từ chối model/snapshot DN khác. Đây là bằng chứng kỹ thuật; không phải 38 tình huống nghiệp vụ hoặc metric độ chính xác phát hiện gian lận.

| DN | Fit | Tham chiếu | Đánh giá | Sai số tuyệt đối lớn nhất HE so với tại DN |
|---|---:|---:|---:|---:|
| C001 | 32 | 8 | 5 | 1,44 × 10⁻⁶ |
| C002 | 32 | 8 | 5 | 1,43 × 10⁻⁶ |

Sai số nằm trong tolerance hiện có atol=1e-3, rtol=1e-5. Hai DN có artifact ID khác nhau; snapshot và model truy cập sai DN đều bị chặn. T0–T4 trùng mã giữa hai DN nhưng vẫn nhận đúng 5 kết quả theo scope. Mở lại trả cùng hai run ID đã có; kết quả encrypted-at-rest còn đọc được bằng DPAPI key qua process mới, không fit hoặc compute lần nữa. [Tóm tắt ID và checksum dữ liệu](demo_summary.json).

## Bố trí và bảo vệ

- .runtime riêng gồm data/, enterprise/ và worker/. Dữ liệu nguồn, hai fitted artifacts và bốn snapshot ở DN. Worker bundle giữ allowlist CR-031, không thêm module DN/khóa HE. Worker chỉ tính ciphertext; checker so plaintext bằng model ở DN.
- Khóa wrapping và node-signing tạo bằng provider Windows DPAPI current-user. Đây là khóa của node phục vụ hai DN thử nghiệm; mỗi job chấm có HE context riêng ràng buộc scope, không một HE secret key dài hạn gắn vào hai model. Pending keys/checkpoints bảo vệ AES-GCM tại DN, checkpoint terminal được bỏ khỏi record hiện hành.
- Thư mục mới chỉ cấp ACL user tạo và SYSTEM, kế thừa xuống dữ liệu/key/worker signing file. Worker response-signing key không phải khóa giải mã HE và không DPAPI; file này được bảo vệ ACL. Same-user malicious process/host compromise vẫn ngoài bảo đảm, chưa KMS/sandbox/rotation.
- Không lưu raw credential fit/read trong packet. auth.json sau chuẩn bị không có principal; checker tạo auth hash trong thư mục tạm và token trong RAM, dùng actor ổn định riêng để kiểm đọc lại. Web tương lai dùng Portal authorizer, không để credential một giờ cũ làm bộ demo hỏng sau khi mở lại.
- prepare không overwrite thư mục cũ và không có tùy chọn force/delete. Marker PREPARING ngăn dùng bộ bị gián đoạn. check chỉ đọc model/snapshot và ghi riêng kho job/state; source/model/hash không đổi.

Phát hiện khi chuẩn bị: gọi lại generator có thể tạo metadata nguồn khác lần nhập ban đầu. Đã sửa exporter lấy nguyên source_blobs đã khóa checksum; bốn tệp bộ thật được thay bằng đúng nguồn gốc trong DB, **giữ nguyên fitted models và hai khóa DPAPI**. Unit mới kiểm đúng byte source upload. Hai lượt 38 checks và focused cuối đều chạy sau sửa. Lượt focused sơ bộ cũng pass; focused_final là bằng chứng cuối sau làm decoder SID độc lập mã hóa tên tài khoản Windows.

## Giới hạn và bước bật UI

Chưa bật worker cố định/HE Portal, thay membership, mật khẩu, DB hoặc model live. Bộ chuẩn bị gồm node config 1.2.0, pins, grant và mẫu quyền demo; bước sau cần cấu hình đồng bộ Portal/Agent2 đọc đúng snapshot DB riêng này. Không tự áp mẫu quyền vào doanh nghiệp thật. Sau bật, chọn snapshot **5 bản ghi**, không chọn bản lịch sử 40 bản ghi. Phiếu checker thuộc actor riêng, không phải kết quả của người dùng Portal.

Vẫn Mahalanobis hai feature/33-feature contract, backtest trên mô phỏng, không bốn nhánh HE/IF/ECOD/LOF/AE, prospective evaluation, labels hoặc accuracy claim. Không public cloud/TLS production/KMS/HA/proof worker ác ý/cross-machine restore hoặc reboot OS. Kiểm tra chỉ bật worker local tạm rồi dừng; không để thêm dịch vụ chạy nền. Thư mục dữ liệu/model/key đã được Git ignore; không commit/push hoặc đưa private files vào evidence.

Lượt này chỉ thêm module prepare/check, unit và tài liệu; không sửa runtime cũ. Bộ 145 HE + 742 native pass ở [CR-034](../web_analysis_20261112/REPORT.md) là regression trước đó, **không chạy lại trong lượt này**. 5 focused và kiểm bộ thật được chạy trực tiếp cho thay đổi mới. Chỉ READY_FOR_REVIEW bộ thử, không tự ký DONE/full gate R2/R5 hoặc nghiệm thu bảo mật/hiệu quả ML.

[Source/provenance](source_provenance.json), [kiểm tra tĩnh](validation.json), [manifest evidence](artifact_manifest.json).
