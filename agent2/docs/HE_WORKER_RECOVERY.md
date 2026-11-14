# Khôi phục worker chết giữa phép tính — CR-040

Người dùng tiếp tục dùng **Bật Agent2 / Kết nối lại** trên Portal. Node giữ yêu cầu/checkpoint đã mã hóa; worker mới xử lý tiếp **đúng request cũ**. Không đổi model, khóa, HE context, nonce hoặc mã yêu cầu để che lỗi. [Báo cáo lần sửa](../../Agent2_Spec_v2_1/evidence/HE/worker_recovery_20261112/REPORT.md).

## Cơ chế

1. Worker giữ khóa file hệ điều hành trên thư mục state, chỉ một worker thực thi tác vụ từ kho đó trên máy/local disk này. Worker thứ hai không được mở kho rồi sửa trạng thái của worker đang sống. Khóa tự nhả khi process chết. Shutdown có kiểm soát chờ các phép tính đang hoạt động hoàn tất trước khi nhả khóa.
2. Khi nhận bản mã hợp lệ, worker lưu tuple `(tenant, company, session, nonce)`, SHA256 của **toàn bộ envelope có chữ ký**, attempt token và generation trong transaction SQLite. Cùng nonce nhưng nội dung khác bị từ chối trước native parse. Một request đang chạy trả trạng thái bận; gửi lặp không tạo thêm job.
3. Replay ledger vẫn giữ bảng nonce cũ. Yêu cầu managed mới có thêm binding hash trong bảng riêng, ghi nonce + hash nguyên tử. Lời gọi standalone vẫn từ chối replay như trước. Chỉ callback nội bộ của worker sở hữu đúng attempt mới cho resume một hash đã khóa; API không có cờ bỏ kiểm replay.
4. Khi worker chết, tác vụ managed `running` chuyển thành `retryable` sau khi worker mới lấy được khóa độc quyền. Attempt cũ bị vô hiệu. Node hỏi kết quả; nếu chưa có, gửi lại đúng packet/checkpoint hiện có và worker tái kiểm chữ ký, grant, policy và thời hạn trước khi claim attempt mới.
5. Kết quả ciphertext chỉ được commit bởi attempt đang sở hữu đúng request hash. Kết quả đã commit không bị callback cũ ghi đè. Nếu chết sau commit nhưng trước reply, trả lại đúng cache; không tính lại. Nếu chết trước commit, worker có thể **thực hiện lại phép toán trên cùng bản mã**; vẫn chỉ một job logic và một kết quả commit, không cam kết native compute chạy đúng một lần.

Node tiếp tục giải mã bằng HE context đã lưu tại doanh nghiệp. Worker không nhận HE secret key, model rõ hoặc dữ liệu rõ. Không fit hoặc chọn model mới khi retry. Cách chấm, ngưỡng số học và hợp đồng 33 feature/hai feature được chọn giữ nguyên.

## Phạm vi và dữ liệu cũ

- Chỉ resume **managed request có hash binding**, chưa terminal, trong thời hạn ban đầu tối đa 300 giây, còn nguyên checkpoint và kho worker. Không gia hạn TTL bằng việc restart.
- Khóa/quyền hiện tại vẫn được kiểm: thay pin, revoke grant/membership hoặc hết phiên đăng nhập không được bỏ qua. Node restart chờ chủ yêu cầu xác thực lại, rồi dùng cùng private context/packet đã lưu.
- Worker DB chuyển `user_version` 0 → 2 trong transaction, thêm attempt/generation; cache completed và các bản failed cũ giữ nguyên. Replay table nonce cũ không bị xóa hoặc đặt lại.
- Legacy nonce không có hash binding vẫn bị xem là đã dùng; tác vụ legacy đang dở báo `WORKER_INTERRUPTED_LEGACY`. Không tự mở lại failed/expired cũ: chúng có thể đã mất private checkpoint sau terminal. Những bằng chứng 0/2 trước CR-040 là lịch sử, không viết lại thành pass.
- Hết TTL khi chưa có kết quả thì expired; đã có cache thì fresh signed retrieval vẫn có thể lấy ciphertext cũ theo quyền hiện hành như trước. Không chấm rõ dự phòng hoặc sinh nonce khác.
- Mất/rollback/chép state không đồng bộ, xóa replay DB, mất khóa, shared network filesystem, nhiều máy hoặc worker ác ý chưa nằm trong bảo đảm. Đây là một worker process mỗi state trên máy local, không phải bộ điều phối phân tán hoặc proof tính toán đúng.

Khi nâng bản đang chạy, dừng đúng Agent2/worker do Portal sở hữu, sao lưu state/manifest, thay bundle từ allowlist mới rồi bật lại. Không đổi DB snapshot/model, key files, quyền, mật khẩu hoặc config Portal. Không tự rollback DB/replay về bản sao cũ sau khi đã có yêu cầu mới vì có thể tái dùng nonce. Không cần restart Portal để thay riêng worker/node.

## Kiểm thử có thể chạy lại

```powershell
cd D:/agent22/agent2
& .venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests_he -p test_worker_recovery.py -v
& .venv/Scripts/python.exe -X utf8 -B scripts/run_he_tests.py --report '<he-tests-moi.json>'
```

Các điểm ngắt thử nằm trong bootstrap test riêng, không có fault flags trên API: sau claim; sau replay reservation đã commit; sau phép tính native trước commit; sau cache commit trước reply. Kiểm cả restart worker lẫn node, đúng hash/private context, số điểm/parity, một job logic, stale attempt, hai process tranh state, request đổi nội dung có chữ ký hợp lệ, hết hạn và revoke grant. Fixture model/khóa/snapshot trước/sau được đối chiếu giữ nguyên.
