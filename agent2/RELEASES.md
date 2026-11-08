# Cài đặt, nâng cấp và khôi phục phiên bản Sổ Soát

Bản đầu có số phiên bản ứng dụng `0.1.0`, schema ReviewStore `8`, schema journal P2 `1`. Phiên bản ứng dụng, schema, định dạng backup và hợp đồng model/feature được ghi riêng; tăng số phiên bản ứng dụng không tự đổi schema hoặc model.

Gói phát hành dành cho **Windows x64, CPython 3.12**. Bên trong có `release.json`, mã/HTML/JS tại `app/`, wheel thư viện tại `wheels/` và `requirements.lock` có SHA256. Không đóng gói dữ liệu doanh nghiệp, model, token hay môi trường `.runtime` của máy phát triển. Wheel là thành phần theo nền tảng; không dùng gói Windows này để cài Linux hoặc Python khác.

## Cài vào thư mục sạch, ngoại tuyến

Giả sử gói được giải nén tại `D:\SoSoatPackage`, Python 3.12 đã có sẵn:

```powershell
$releasePython = 'C:\Path\To\Python312\python.exe'
& $releasePython -B D:\SoSoatPackage\app\manage_release.py verify --release D:\SoSoatPackage
& $releasePython -B D:\SoSoatPackage\app\manage_release.py install --release D:\SoSoatPackage --output D:\SoSoatInstall\v010
```

Thư mục cài phải chưa tồn tại. Installer xác minh checksum, tạo venv tại vị trí cuối cùng rồi cài wheel bằng `--no-index --require-hashes`; không dùng thư viện global/user site và không tải mạng khi cài. Không cần chạy `Activate.ps1` hoặc đổi execution policy. `installation.json` chỉ được ghi sau khi phiên bản thư viện, môi trường cách ly và `pip check` đều đạt. Cài dở thiếu receipt được giữ để điều tra, không tự ghi đè. Venv không được di chuyển; cần cài lại ở vị trí mới.

`requirements-review-lock.txt` là profile web/backup theo môi trường được nghiệm thu. `requirements-lock.txt` cũ phục vụ môi trường benchmark khác và được giữ riêng. Release này không tự chuyển model/feature cũ hoặc huấn luyện lại; các kiểm tra provenance ML vẫn áp dụng.

## Mở bản sao lưu cũ

Giữ gói phát hành và wheelhouse của từng runtime cùng bản backup. Sau khi cài các phiên bản vào các thư mục riêng, có thể tìm runtime khớp:

```powershell
& $releasePython -B D:\SoSoatPackage\app\manage_release.py resolve --installations D:\SoSoatInstall --backup D:\Backups\run_OLD
& $releasePython -B D:\SoSoatPackage\app\manage_release.py restore --installation D:\SoSoatInstall\v010 --backup D:\Backups\run_OLD --output D:\SoSoatData\restored_NEW
```

Hỗ trợ gói ReviewStore v1 và gói tổng hợp ReviewStore/P2 v1 khi có runtime khớp chính xác. Resolver chọn từ các bản đã cài và xác minh; không chạy code từ nội dung backup hoặc sửa manifest để ép tương thích. Chưa có runtime khớp thì cài lại gói phát hành đã lưu. Runtime legacy không còn mã/gói tương ứng không được tự dựng lại bằng phỏng đoán.

## Chuyển phiên bản theo luồng ngoại tuyến

```powershell
& $releasePython -B D:\SoSoatPackage\app\manage_release.py initialize --installation D:\SoSoatInstall\v010 --backup D:\Backups\run_OLD --output D:\SoSoatDeploy
& $releasePython -B D:\SoSoatPackage\app\manage_release.py run --deployment D:\SoSoatDeploy --port 8773
```

Lệnh `run` giữ khóa deployment trong suốt thời gian phục vụ web. Trước nâng cấp, dừng web do manager khởi chạy bằng `stop --deployment D:\SoSoatDeploy`, chờ tiến trình kết thúc; dừng cả mọi CLI/worker khác đang ghi trực tiếp vào revision đó. Không mở revision bằng lệnh web/CLI cũ để bỏ qua khóa. Các dịch vụ demo khác không trỏ vào deployment này không bị dừng.

Cài ứng viên vào một thư mục mới rồi chạy:

```powershell
& $releasePython -B D:\SoSoatPackage\app\manage_release.py upgrade --deployment D:\SoSoatDeploy --installation D:\SoSoatInstall\vNEW
& $releasePython -B D:\SoSoatPackage\app\manage_release.py status --deployment D:\SoSoatDeploy
```

Manager chụp checkpoint bằng runtime đang chạy, phục hồi sang revision mới, đối chiếu hash toàn bộ dữ liệu nghiệp vụ và thử HTTP bằng runtime ứng viên. Chỉ đổi con trỏ active sau khi mọi bước đạt. Thất bại giữ active cũ, lưu lịch sử lỗi và giữ revision dở để điều tra; không nâng cấp trực tiếp trên DB đang dùng. Hai lần kiểm tra nguồn trước/sau phát hiện ghi ngoài quy trình trong lúc chuẩn bị, nhưng không thay thế yêu cầu dừng mọi writer.

## Ma trận chuyển đổi và quay lại

| Nguồn → đích | Hành vi hỗ trợ |
|---|---|
| Review schema 8/P2 schema 1, cùng hợp đồng runtime backup | Sao chụp/khôi phục sang revision mới, rebase binding/fingerprint đường dẫn bằng API đã kiểm chứng; giữ nguyên các bảng nghiệp vụ |
| Code khác hợp đồng runtime nhưng backup cũ có release khớp | Mở bằng release khớp; chưa tự chuyển sang code mới |
| Schema/runtime chưa có adapter được kiểm chứng | Chặn nâng cấp, giữ active cũ; cần adapter chỉ rõ phiên bản nguồn/đích và kiểm chứng dữ liệu trước/sau |

Không tuyên bố đã có migration sang schema 9 hoặc mọi phiên bản tương lai. Các bản ứng viên dùng riêng cho diễn tập được gắn phiên bản `+rehearsal`, không coi là bản có tính năng nghiệp vụ mới.

```powershell
& $releasePython -B D:\SoSoatPackage\app\manage_release.py rollback --deployment D:\SoSoatDeploy
```

Rollback kiểm tra bản trước còn nguyên và bản active chưa có ghi mới kể từ lúc kích hoạt. Nếu đã có kết luận, yêu cầu tài liệu, admission hoặc ghi chú P2 mới, lệnh bị chặn để giữ dữ liệu đó; cần checkpoint và adapter chuyển ngược được duyệt, không đổi con trỏ để bỏ mất lịch sử. Khi ứng viên lỗi trước kích hoạt, không có bước đảo dữ liệu vì active chưa đổi.

Thông báo trong luồng cài/diễn tập/deployment vẫn dry-run, không tự gửi Email/Zalo. Tác vụ backup Windows hiện có giữ nguyên; nếu dùng deployment mới để vận hành, cần cấu hình nguồn backup riêng và kiểm tra lại lịch sau cutover, không tự đổi job đang phục vụ demo khác.

Tham khảo cơ chế: [venv](https://docs.python.org/3.12/library/venv.html), [pip repeatable installs và wheelhouse](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
