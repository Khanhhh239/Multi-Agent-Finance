# Nghiệm thu C001/C002 trên Portal — 12/11/2026

**Kết luận hiện tại: PARTIAL.** Các luồng bật/tắt, đọc lại kết quả và khôi phục mất kết nối đã qua kiểm tra. Worker chết đột ngột giữa phép tính, trước khi lưu bản mã kết quả, **chưa khôi phục thành công**. Không ghi ca này là đạt tiêu chí tiếp tục yêu cầu.

## Kết quả đã thực hiện

| Ca nghiệm thu | Kết quả | Bằng chứng |
|---|---|---|
| Chạy C001/C002, mỗi DN 5 giao dịch | Đạt trên Portal thử nghiệm; native HE thật, đủ 5 điểm mỗi DN | [14 kiểm tra trình duyệt](isolated_scopes/summary.json) |
| Tắt/bật qua nút Portal, xem lại | Cùng mã yêu cầu và toàn bộ kết quả, gồm từng điểm; chỉ hai lượt tính cho hai DN | [14 kiểm tra trình duyệt](isolated_scopes/summary.json) |
| Worker mất kết nối trước khi nhận phép tính | Kết nối lại hoàn tất C002 cùng mã yêu cầu, reload giữ kết quả | [Ảnh mất kết nối](isolated_scopes/02-worker-offline.png), [ảnh khôi phục](isolated_scopes/03-recovered.png) |
| Không lẫn hai DN dù trùng mã T0–T4 | Đọc status/result/resume chéo DN đều 404; catalog tách đúng snapshot, gửi snapshot DN khác bị từ chối | [14 kiểm tra trình duyệt](isolated_scopes/summary.json) |
| Tắt bằng Portal khi worker đã nhận và đang tính | Khôi phục cùng yêu cầu C001, đủ 5 điểm; một record tính ở worker | [Thử ngắt giữa chừng](native_interruption/summary.json) |
| Dừng đột ngột worker đã nhận và đang tính | **Chưa đạt phục hồi:** cùng yêu cầu C002 thành `failed / WORKER_INTERRUPTED`; không tự tạo lượt mới | [Thử ngắt giữa chừng](native_interruption/summary.json) |
| Phiên người dùng trên Portal đang chạy 8800 | **12 checks đạt**, sau khi người dùng đăng nhập trực tiếp; đủ 5 điểm/DN, tắt/bật và reconnect cùng yêu cầu, đọc chéo bị chặn | [Kết quả live](live/summary.json), [C001](live/01-c001.png), [C002 mất worker](live/02-c002-offline.png), [C002 khôi phục](live/03-c002-recovered.png) |

14 checks là bản mở rộng của lượt 11 checks cùng ngày, **không cộng thành 25**. Hai ca ngắt giữa native compute dùng Portal/node/worker subprocess thật trong fixture riêng, không sửa hoặc dừng dịch vụ live. Sau mỗi ca, model/snapshot/khóa được đối chiếu giữ nguyên. Không chạy lại 159 HE/742 regression trong lượt này vì không đổi mã sản phẩm; kết quả cũ là bằng chứng của CR-037.

## Phiên Portal 8800 sau khi người dùng đăng nhập

Người dùng xác nhận đã đăng nhập trong cửa sổ mới; Playwright dùng đúng phiên đó, không đọc mật khẩu, không tạo quyền hoặc thay cơ chế xác thực. Đã hoàn tất 12 kiểm tra live bằng bộ C001/C002 hiện có; không dùng fixture để thay kết quả live.

- C001: `herun_8bbd4940fba14dcc91ba5139d84ec653`, snapshot `snp_de7dabce8b1d42378e38b4f3a001107a`, đủ 5 dòng T0–T4. Tắt/bật bằng nút Portal rồi so toàn bộ kết quả JSON: giữ nguyên cùng job, từng điểm và bản dữ liệu.
- C002: `herun_8d3642ec0025459b910acfa954c12b9f`, snapshot `snp_29122f87a21b4829a2c92f145c28e00d`, đủ 5 dòng T0–T4. Sau khi submit, phát hiện trạng thái DN `preparing` rồi dừng đúng cây worker đã đối chiếu parent là Portal. Node còn sống; giao diện giữ yêu cầu và hiện Kết nối lại. Bấm nút đó bật worker, hoàn tất cùng job; reload tiếp tục đọc được toàn bộ kết quả giống hệt.
- Đây là mất worker **sau khi yêu cầu đã gửi nhưng trước khi worker nhận phép tính native**. Không coi ca live này là chứng minh khôi phục hard crash giữa native compute. Hai ca native thực hiện riêng như bảng trên, HE-AC-01 vẫn OPEN.
- Dùng đường dẫn C002 để đọc kết quả C001 và ngược lại đều HTTP 404. Job/result đều gắn đúng company/snapshot dù cùng mã T0–T4. Điểm hai DN gần nhau do bộ mô phỏng có cấu trúc tương tự; việc khác vài chữ số không phải bằng chứng phân quyền. Bằng chứng phân quyền là kiểm scope/snapshot và từ chối truy cập chéo.
- Model registry, DB snapshot nguồn và hai tệp khóa DPAPI trước/sau giữ nguyên. Agent1/3/4 giữ trạng thái sở hữu/chạy cũ; không có lỗi JavaScript. Kết thúc Agent2 đang chạy và worker owned/ready; không restart Portal hoặc đổi mật khẩu trong lượt này.

Các ảnh/result chỉ chứa dữ liệu mô phỏng. Không xuất token/session/khóa riêng vào evidence. Cửa sổ Chrome kiểm thử riêng tự đóng sau khi hoàn tất; không đăng xuất hoặc đóng các tab Chrome có sẵn của người dùng.

## Phần cần cải tiến

**HE-AC-01 — Khôi phục worker chết trước khi commit kết quả: OPEN.** Worker ghi nhận request đang chạy; khi khởi động lại, record dở dang được đánh dấu `WORKER_INTERRUPTED`. Node báo thất bại trên cùng job, không đổi nonce hoặc tự chấm rõ. Hành vi này đóng an toàn nhưng chưa thỏa yêu cầu tiếp tục thành công khi worker chết giữa phép tính.

Tắt qua nút Portal khác với dừng cưỡng bức: Portal dừng node rồi chờ worker hoàn tất và lưu bản mã trong grace period. Ca đó đã lấy lại được ciphertext đã lưu sau khi bật lại. Không lấy kết quả của ca tắt có kiểm soát để khẳng định phục hồi mọi crash.

Đề xuất bước sửa tiếp: thiết kế tiếp tục phép tính dựa trên đúng request hash/bản mã đã khóa, quyền còn hợp lệ và quyền sở hữu tác vụ độc quyền; ghi kết quả nguyên tử và giữ chống replay. Cần kiểm cả crash trước/sau khi claim, trước/sau khi ghi kết quả, TTL, bấm lại và hai worker tranh cùng job. Không xóa replay store, sinh nonce mới hoặc fit lại để che ca lỗi. Chưa thay cơ chế này trong lượt nghiệm thu.

## Phạm vi

Nguồn mô phỏng; Mahalanobis hai feature trong contract 33 feature, worker loopback. Đây là nghiệm thu kỹ thuật, chưa đánh giá hiệu quả phát hiện sai phạm hoặc nghiệm thu production. Người duyệt thực chưa ký; không tự chuyển R0–R6 sang DONE.
