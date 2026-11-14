# Bộ thử C001/C002 đã chuẩn bị — CR-035

**CR-036:** bộ thử đã được [bật trên Portal 8800](HE_PORTAL_ACTIVATION.md). Dùng mật khẩu hiện tại; phần dưới ghi lại cách chuẩn bị ban đầu. Checker 1.1.0 khóa checksum từng snapshot và model artifact, cho phép SQLite cập nhật header/WAL khi mở mà không báo hỏng dữ liệu nhầm.

Bộ thử được lưu tại `D:/agent22/agent2/.runtime/he-company-demo`. Đây là thư mục tồn tại sau khi tắt chương trình, có dữ liệu mô phỏng, hai model đã fit riêng, snapshot và khóa được bảo vệ. **CR-036 đã bật bộ này cho Portal demo; DB/quyền cũ được giữ riêng.**

## Tệp để bạn thử

| Doanh nghiệp | Tệp đánh giá | Số giao dịch | Model |
|---|---|---|---|
| C001 | [C001_5_giao_dich.json](../.runtime/he-company-demo/data/C001_5_giao_dich.json) | 5 | Mahalanobis fit riêng cho C001 |
| C002 | [C002_5_giao_dich.json](../.runtime/he-company-demo/data/C002_5_giao_dich.json) | 5 | Mahalanobis fit riêng cho C002 |

Hai tệp đã được kiểm tra và lưu thành snapshot trong bộ thử. Sau khi bật cấu hình HE cho Portal thử nghiệm, bạn chỉ cần chọn **doanh nghiệp → bản dữ liệu có 5 bản ghi → Chạy phân tích**; không cần tải lại tệp nếu dùng đúng kho snapshot này. Nếu muốn thử chức năng nhập, dùng đúng tệp tương ứng doanh nghiệp, kiểm tra rồi xác nhận lưu. Không chỉnh sửa mã doanh nghiệp trong tệp để dùng cho công ty khác.

Trong mỗi doanh nghiệp:

- **32 giao dịch lịch sử** dùng fit model, **8 giao dịch khác** dùng tham chiếu; nằm trong tệp `data/C001_lich_su_fit.json` hoặc `data/C002_lich_su_fit.json`.
- **5 giao dịch T0–T4** dùng đánh giá thử, không nằm trong tập fit/tham chiếu. Hai doanh nghiệp cố ý trùng các mã T0–T4 để kiểm tra phạm vi dữ liệu; số tiền C002 khác C001.
- Model dùng hai biến trong hợp đồng 33 feature: log trị tuyệt đối số tiền và biểu diễn chu kỳ giờ giao dịch. Đây là profile HE kiểm chứng hiện có, không phải cả bốn nhánh hoặc đánh giá độ chính xác phát hiện sai phạm.

Không chọn bản **40 bản ghi lịch sử** làm dữ liệu đánh giá. Kỳ fit/tham chiếu là tháng 09/2026; giao dịch đánh giá là tháng 10/2026. Thử nghiệm hồi cứu trên mô phỏng, không phải bằng chứng model đã phát hiện được gian lận thực tế.

## Những gì đã có sẵn

| Thành phần | Vị trí trong thư mục bộ thử |
|---|---|
| Hai model bất biến, phân phạm vi tenant/DN | `enterprise/models.sqlite3` |
| Bốn snapshot: lịch sử + đánh giá của từng DN | `enterprise/snapshots.sqlite3` |
| Model ghim sẵn cho từng DN | `enterprise/he-ui-bindings.json` |
| Node config 1.2.0, DPAPI bắt buộc | `enterprise/node.json` |
| Khóa bọc kho phiên và khóa ký node | `enterprise/state-wrapping.dpapi.json`, `enterprise/node-signing.dpapi.json` |
| Quyền Portal demo, chưa áp dụng vào live | `enterprise/portal-access.demo.json` |
| Worker ciphertext-only và grant hai DN | `worker/bundle`, `worker/service.json`, `worker/grants.json` |
| ID model/snapshot và checksum nguồn | `prepared.json` |

Hai model tách theo doanh nghiệp trong cùng registry của node thử nghiệm. Khóa bọc và khóa ký thuộc **node DN phục vụ bộ thử**, không phải hai model dùng chung một khóa giải mã HE cố định. Mỗi lượt chấm sinh HE context/khóa riêng, ràng buộc doanh nghiệp; khi còn pending, khóa HE nằm trong checkpoint AES-GCM tại DN. Sau terminal, checkpoint được bỏ khỏi record hiện hành; kết quả vẫn được lưu mã hóa tại DN.

Khóa node được Windows DPAPI current-user bảo vệ. Toàn bộ thư mục mới được đặt ACL cho tài khoản Windows tạo bộ thử và SYSTEM; không sửa ACL thư mục dự án hoặc dữ liệu cũ. Cách dùng quyền kế thừa dựa trên [Microsoft icacls](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls). Worker chỉ giữ khóa ký phản hồi riêng, bảo vệ bằng ACL, **không phải khóa giải mã HE**. Đây không phải OS sandbox hay KMS; process độc hại cùng tài khoản vẫn là giới hạn hiện tại.

Không đưa thư mục `.runtime` lên Git/cloud; Git đã bỏ qua bộ thử. Giữ cả DB, file khóa và profile Windows để sử dụng lại; không tạo khóa khác đè lên bộ cũ. `auth.json` không để lại credential standalone có hạn một giờ: file này không cấp principal. Khi bật UI, node dùng authorizer Portal hiện tại. Kiểm tra CLI tự cấp credential tạm trong RAM, không lưu token vào bộ thử hoặc báo cáo.

## Kiểm tra lại bộ đã chuẩn bị

Tại `D:/agent22/agent2`:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.prepared_demo check --output-dir .runtime/he-company-demo
```

Lệnh đọc lại model/khóa đã lưu, bật một worker local tạm, chấm/lấy lại 5 kết quả mỗi DN, so với phép tính tại DN và kiểm chặn đọc chéo doanh nghiệp. Checker 1.1 dùng state riêng với web/worker live. Kết thúc tự dừng cây worker tạm; không để thêm dịch vụ kiểm tra chạy nền. Chạy lại giữ cùng job ID của tài khoản kiểm tra trong state đó, không fit hoặc sinh yêu cầu mới. Kết quả CLI thuộc actor kiểm tra riêng, không phải phiếu của người dùng Portal.

Có thể thêm `--report <duong-dan-json-moi>` để lưu báo cáo chỉ chứa kết quả kỹ thuật; không in hoặc xuất khóa/token. Tệp report phải chưa tồn tại. [Báo cáo bộ thực tế đã tạo](../../Agent2_Spec_v2_1/evidence/HE/company_preparation_20261112/REPORT.md).

## Cấu hình Portal và cách bật lại

Làm theo [HE_WEB_ANALYSIS.md](HE_WEB_ANALYSIS.md) với các file thật trong bộ thử. Cần cấu hình **cùng lúc**:

1. Worker chạy từ `worker/bundle` với `worker/service.json` tại địa chỉ đã ghim trong `enterprise/node.json` (mặc định loopback 8868).
2. Agent2 đọc đúng `enterprise/snapshots.sqlite3` và dùng `enterprise/node.json`, `enterprise/he-ui-bindings.json`.
3. Portal cấp đúng tenant `demo`, quyền C001/C002 theo file mẫu `enterprise/portal-access.demo.json` trong không gian thử nghiệm.

Chỉ đặt biến HE mà để Agent2 đọc DB snapshot live khác sẽ bị từ chối khi startup. Không ghi đè DB/quyền công ty thật bằng mẫu demo. Chưa khởi động worker cố định, thay cấu hình, mật khẩu hoặc quyền Portal live trong bước chuẩn bị này.

## Tạo bộ khác khi cần

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.prepared_demo prepare --output-dir .runtime/he-company-demo-moi
```

Chỉ dùng thư mục mới chưa tồn tại. Lệnh từ chối ghi đè bộ cũ để không mất model, khóa hoặc phiên. Nếu chuẩn bị bị gián đoạn, thư mục có `PREPARING` và không được dùng như bộ hoàn tất; không tự xóa/khôi phục bằng khóa mới. Tệp đánh giá được xuất **đúng byte nguồn đã nhập** từ kho, không tái sinh nguồn rồi giả định checksum giống nhau.

Phạm vi vẫn là Mahalanobis hai feature/8 dòng hợp lệ mỗi lượt, Windows/loopback. Chưa production, cloud public, rotation/cross-machine restore hoặc tăng tỷ trọng ML; các model/snapshot/khóa live giữ nguyên.
