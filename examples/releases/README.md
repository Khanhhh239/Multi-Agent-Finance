# Dùng gói phát hành đã kiểm chứng

[Hướng dẫn đầy đủ](../../RELEASES.md) có trong gói tại `app/RELEASES.md`. [Biên bản nghiệm thu kỹ thuật](../../docs/reports/operations/release_20261019.md) ghi rõ phạm vi đã kiểm chứng.

Gói chính: `.publish/releases/sme-review-0.1.0-win64-py312.zip`, kèm file `.sha256`. Profile web/backup: Windows x64, CPython 3.12; thư viện được khóa theo `requirements-review-lock.txt`, tải thành wheel và ghi SHA256 trong `requirements.lock` của gói. Môi trường đã kiểm chứng dùng Python 3.12.7. Gói không kèm dữ liệu/model hoặc Python hệ thống.

Giải nén vào thư mục mới bằng công cụ ZIP hoặc lệnh `unpack`, rồi gọi `app/manage_release.py install`. Không đổi execution policy và không cài thư viện vào Python global. Ví dụ từ workspace:

```powershell
$releasePython = 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe'
& $releasePython -B manage_release.py unpack --archive .publish/releases/sme-review-0.1.0-win64-py312.zip --output .runtime/package_NEW
& $releasePython -B .runtime/package_NEW/app/manage_release.py install --release .runtime/package_NEW --output .runtime/install_NEW
```

Các thư mục `_NEW` phải chưa tồn tại. `installation.json` xác nhận cài xong, phiên bản code/schema, các thư viện thực tế và `pip check`. Nếu môi trường hỏng hoặc bị di chuyển, tạo bản cài mới từ gói đã giữ; không trộn thư viện của hai phiên bản.

Đã cài hai runtime riêng tại `.runtime/release_20261019/installations/review010` và `candidate011`. Bản `0.1.1+rehearsal` chỉ đổi metadata phiên bản để diễn tập; không phải bản có tính năng nghiệp vụ mới để đưa vào vận hành. Gói chính được phát hành cục bộ là `0.1.0`.

## Kiểm tra backup và phiên bản tương thích

```powershell
& $releasePython -B manage_release.py resolve --installations .runtime/release_20261019/installations --backup .runtime/backup_restore_20261019/final/backup_live_demo
& $releasePython -B manage_release.py restore --installation .runtime/release_20261019/installations/review010 --backup .runtime/backup_restore_20261019/final/backup_live_demo --output .runtime/restored_legacy_NEW
```

Manifest backup gốc được giữ nguyên. Chỉ runtime có hợp đồng đúng mới được mở backup đó; định dạng/schema chưa biết bị chặn. Việc tăng `APP_VERSION` không tự tạo khả năng chuyển schema. Giữ ZIP và wheelhouse từng release cùng lịch sử backup.

## Nâng cấp/rollback và dữ liệu phát sinh

Các bước đều ngoại tuyến: dừng web bằng `stop`, chờ tiến trình thoát, dừng mọi CLI/worker ghi trực tiếp vào revision. `run` giữ khóa deployment nên lệnh nâng cấp/quay lại từ manager sẽ bị chặn khi web còn chạy. Các dịch vụ demo cũ không trỏ vào deployment mới không bị dừng.

Trên bản diễn tập `.runtime/release_20261019/deployment_main`, đã kiểm chứng chụp checkpoint → phục hồi ứng viên → đối chiếu toàn bộ bảng/lịch sử → HTTP probe → đổi active. Lỗi probe giả lập giữ active cũ. Rollback bằng con trỏ chỉ cho phép khi chưa có ghi mới và bản trước còn nguyên.

Nếu đã có ghi mới, **không đổi con trỏ về dữ liệu cũ**. Với cặp runtime có hợp đồng backup và schema khớp chính xác như hai bản diễn tập, có thể quay về code trước qua chính luồng checkpoint/restore bằng lệnh `upgrade` với installation đích là bản cũ:

```powershell
& $releasePython -B manage_release.py upgrade --deployment DEPLOYMENT --installation INSTALLATION_CU
```

Lệnh này sao lưu **dữ liệu hiện hành**, phục hồi sang một revision mới dưới runtime cũ và yêu cầu hash mọi bảng/lịch sử giữ nguyên trước cutover. Đây là đường chuyển `8 → 8` có runtime khớp; không phải adapter chung cho mọi downgrade. Nếu hợp đồng runtime/schema khác, lệnh bị chặn và cần adapter nguồn/đích riêng đã được kiểm chứng. [Bằng chứng giữ ghi chú mới khi quay về](../../reports/release_20261019/postwrite_recovery.json).

Bản sao diễn tập có dữ liệu phát sinh ở `.runtime/release_20261019/deployment_postwrite`; ghi chú `SIM_RELEASE_UAT` ở đây chỉ để kiểm thử. Nhật ký gốc và nhận xét kế toán thực tế không bị thay đổi. Các thông báo vẫn dry-run.

Tác vụ backup 02:00 hiện vẫn phục vụ demo gốc. Khi thực sự chuyển vận hành sang deployment mới, cấu hình nguồn/kho backup tương ứng và đối chiếu lại lịch; không để job tiếp tục trỏ nhầm revision cũ. Luồng phát hành này chưa có zero-downtime, migration schema 9 hay tự chuyển model ML.
