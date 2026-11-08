# Nghiệm thu luồng nghiệp vụ hai cấp — 27/10/2026

Đã sửa giao diện và chạy trọn luồng **xem bằng chứng → kế toán viên gửi → kế toán trưởng/giám đốc chốt hoặc trả lại** trên Chrome. Kiểm tra desktop và viewport **360×800, 390×844** bằng danh tính mô phỏng, dữ liệu test riêng.

## Những thay đổi chính

| Trước sửa | Sau sửa |
| --- | --- |
| Hồ sơ bị trả lại chỉ hiện nhãn trạng thái và bản rà cũ, không hiện lý do người kiểm tra đã ghi. | Hiện người trả, lý do, chứng từ còn thiếu, thời điểm và phút kiểm tra. Kế toán viên bổ sung rồi gửi lại. |
| Giao diện chưa hiển thị căn cứ kết luận cuối; người kiểm tra có thể thấy thông điệp “Chưa có kết quả…” sau khi đã chốt. | Hiện kết luận, người chốt, lý do và phút kiểm tra từ đúng sự kiện phê duyệt; có lịch sử các bước. Hồ sơ đã kết luận được xem lại. |
| Sau gửi, biểu mẫu kế toán viên trông như bước chưa gửi. | Hiện rõ đang chờ kiểm tra cuối. Việc sửa bản đang chờ nằm trong “Sửa kết quả đã gửi”, có thông báo tác động và lưu lịch sử. |
| Lỗi nằm ở thông báo phía trên, khó thấy khi đang nhập ở cuối hồ sơ. | Lỗi ngay cạnh biểu mẫu, chuyển focus đến lỗi, giữ nội dung nhập và có nút tải lại khi cần. |
| Thao tác trả lại có thể mang theo lựa chọn “Cần bổ sung” đang được chọn và vướng kiểm tra thiếu chứng từ không cần thiết cho thao tác trả lại. | Trả lại gửi lý do/phút kiểm tra riêng, không gửi một kết luận đang chọn. |

Bổ sung cảnh báo khi còn yêu cầu tài liệu chưa rà xong; lấy sẵn danh tính người cập nhật tài liệu từ phiên máy chủ, hiển thị chỉ đọc. Hướng dẫn trong app đã mô tả đúng hai cấp. Ở màn hình nhỏ, lựa chọn kết quả xếp một cột, ô nhập dùng cỡ chữ 16px, nút thao tác cao tối thiểu 44px, nội dung dài được ngắt dòng.

**“Cần bổ sung bằng chứng” vẫn giữ hồ sơ mở.** Sau khi người kiểm tra xác nhận kết quả này, kế toán viên vẫn có thể rà bổ sung và gửi lại. Đã kiểm tra nhánh này bằng hồ sơ nguồn F3, rồi chốt hợp lệ sau bổ sung. Không coi việc hoàn thành một vòng duyệt thiếu bằng chứng là đã đóng hồ sơ.

## Bằng chứng đã chạy

| Lớp kiểm chứng | Kết quả |
| --- | --- |
| Chrome thực tế | **21 kiểm tra đạt**, gồm chốt bằng kế toán trưởng, chốt bằng giám đốc, trả/bổ sung/gửi lại, hồ sơ nguồn, lỗi nhập, chế độ chỉ xem, phạm vi công ty và Back/Forward/reload. |
| Máy chủ / HTTP / audit / backup | **78/78 test đạt**, không lỗi hoặc bỏ qua. Bao gồm chống giả danh, chống tự duyệt bằng tài khoản khác của cùng người, phạm vi công ty, phiên bản hồ sơ và kiểm soát chứng từ. |
| JavaScript / renderer | **80 kiểm tra đạt** qua sáu bộ; gồm **21 test mới** cho trạng thái duyệt, hiển thị kết luận/lý do, nhánh thiếu bằng chứng, trả lại, lỗi nhập, giữ bản nháp và chống gửi trùng. |
| Trước/sau | Ba probe trên bản JavaScript lưu trước sửa xác nhận thiếu lý do trả lại, thiếu căn cứ chốt và thiếu trạng thái sửa bản đã gửi; bản mới đáp ứng cả ba. |
| Nhật ký test | Kiểm tra chuỗi hash của **25 sự kiện duyệt**, **5 sự kiện kết quả** và **3 bước yêu cầu tài liệu**. Mọi lần chốt khớp bản rà và là người khác người rà. |

Các nhánh lỗi đã thử trực tiếp trên browser:

- RC_3: yêu cầu tài liệu đang mở chặn chốt; nhận tham chiếu tài liệu vẫn chặn; sau **đã rà lại** thì chốt được. Lý do và số phút của lần chốt chưa thành công vẫn có trong lịch sử.
- RC_4: kế toán viên gửi bản cập nhật sau khi người kiểm tra đã mở tab; tab cũ bị từ chối, giữ bản nháp. Tải lại thấy bản mới; chưa tạo kết luận cuối cho ca kiểm tra này.
- RC_7: danh tính C001 không mở được chi tiết C002; chi tiết cũ được xóa và có thể chuyển sang hồ sơ hợp lệ.
- Chưa có danh tính: xem hồ sơ được, phần rà soát không có điều khiển ghi.

Ở viewport 360px, chiều rộng trang đo được 345px; ở 390px là 375px, đều không tràn ngang. Desktop quan sát ở chiều rộng 1.204–1.280px. Các tab test không ghi nhận console error. Override viewport tạm đã được dọn sau kiểm tra.

## Môi trường và cách thử lại

Launcher: [tests/review_browser_fixture.py](../../../tests/review_browser_fixture.py). Thiết lập môi trường theo [DEVELOPMENT](../../DEVELOPMENT.md), rồi chạy từ thư mục gốc:

```powershell
$env:PYTHONPATH = "$PWD;.runtime/site-packages;tests"
& $projectPython -B tests/review_browser_fixture.py
```

| Cổng loopback | Danh tính cố định tại máy chủ |
| --- | --- |
| 8791 | MÔ PHỎNG · Kế toán viên An |
| 8792 | MÔ PHỎNG · Kế toán trưởng Bình |
| 8793 | MÔ PHỎNG · Giám đốc Chi |
| 8794 | Không có danh tính, chỉ xem |

Ví dụ mở `http://127.0.0.1:8791/#scenario=003&case=RC_5`. Launcher chỉ nhận workspace con trong `.runtime/browser_workflow_20261027/`, từ chối thư mục không có marker test. Muốn một lượt sạch khác, dùng `--workspace .runtime/browser_workflow_20261027/fixture_next` khi chưa có tiến trình cùng cổng. Danh tính không lấy từ nội dung request. Đây là công cụ test; không phải luồng đăng nhập để phát hành.

## Hồ sơ kiểm chứng

- [Danh sách 21 thao tác Chrome](../../../reports/browser_workflow_20261027/browser_checks.json), [log lỗi browser](../../../reports/browser_workflow_20261027/browser_errors.json).
- [Kết quả Python](../../../reports/browser_workflow_20261027/python_results.json), [JavaScript](../../../reports/browser_workflow_20261027/javascript_results.json), [probe trước/sau](../../../reports/browser_workflow_20261027/before_after_probes.json).
- [Đối soát audit](../../../reports/browser_workflow_20261027/audit_verification.json), [trace mô phỏng](../../../reports/browser_workflow_20261027/workflow_trace.json).
- [Ảnh chốt ở 390px](../../../reports/browser_workflow_20261027/screenshots/chief_final_390.jpg), [trả lại ở 360px](../../../reports/browser_workflow_20261027/screenshots/returned_360.jpg), [chốt desktop](../../../reports/browser_workflow_20261027/screenshots/director_final_desktop.jpg), [xung đột phiên bản](../../../reports/browser_workflow_20261027/screenshots/stale_review_390.jpg).
- [Bản mã nguồn của lượt kiểm tra](../../../reports/browser_workflow_20261027/source_snapshot.zip), [hash đầu ra](../../../reports/browser_workflow_20261027/commitment.json), [đối soát file được bảo vệ](../../../reports/browser_workflow_20261027/protected_verification.json).

## Phạm vi kết luận

Hoàn thành nghiệm thu luồng hai cấp trong phạm vi trên; **không phải chạy lại toàn bộ 39 mẫu/17 luồng lịch sử**, không phải kiểm tra Safari/Firefox hoặc điện thoại thật. Backend luật, model, nguồn và các gói rà đã khóa không được sửa/chấm lại trong đợt này; database demo cổng 8774 không được dùng để thử ghi.

Không tạo tài khoản thực tế, không gửi Email/Zalo. **Toàn bộ lý do và số phút trong trace là dữ liệu mô phỏng**, không phải kết luận kế toán độc lập hoặc phút làm việc thực tế. Phần chứng minh lợi ích ML vì vậy vẫn chưa đóng; IF tiếp tục shadow. Luồng đăng nhập được giữ là công việc sau theo lựa chọn của người dùng.
