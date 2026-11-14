# Chọn doanh nghiệp → chọn dữ liệu → Chạy phân tích — CR-034

Đã nối giao diện cho luồng **Mahalanobis trên bản mã**. Mở Agent2 trong Portal, bấm **Chạy phân tích bảo mật**, chọn doanh nghiệp được cấp quyền và bản dữ liệu đã lưu, rồi bấm **Chạy phân tích**. Người dùng không nhập thuật toán, artifact ID hoặc khóa. [Báo cáo và ảnh kiểm thử](../../Agent2_Spec_v2_1/evidence/HE/web_analysis_20261112/REPORT.md).

## Người dùng thao tác

1. Đăng nhập Portal như hiện tại. Trong Agent2, mở liên kết **Chạy phân tích bảo mật** ở đầu trang nhập dữ liệu; đường dẫn qua Portal là `/agent2/encrypted-analysis`.
2. Chọn doanh nghiệp và bản dữ liệu. Danh sách hiển thị số bản ghi, ngày lưu và phần cuối mã bản dữ liệu để phân biệt; phần mô tả có kỳ nguồn và nhãn khi có dữ liệu mô phỏng. Chưa có dữ liệu thì vào **Nhập dữ liệu mới**, kiểm tra và lưu trước.
3. Bấm **Chạy phân tích**. Màn hình hiển thị đang gửi/chờ worker/nhận/giải mã và kết quả. Model do người quản lý ghim sẵn riêng theo tenant/doanh nghiệp.

Tải lại trang sẽ dùng phiếu theo dõi đã lưu trên trình duyệt để lấy lại đúng yêu cầu/kết quả. Nếu mất kết nối, bấm **Tiếp tục phân tích**; không xóa dữ liệu trình duyệt hoặc đổi sang máy khác để retry một yêu cầu đang chờ. Nếu node restart, giao diện tự resume bằng phiên Portal hiện tại khi vẫn đúng owner/quyền. Không lưu bearer token hoặc khóa HE vào phiếu; chỉ có owner hash, company/snapshot ID, idempotency key và job ID.

Kết quả có nguồn dữ liệu, mốc nguồn được biết và mã lần chạy. Mốc `as_of` cố định bằng **thời điểm tạo snapshot**, không thay đổi mỗi lần tải lại trang. Đây là lựa chọn bảo toàn cùng một yêu cầu trên dữ liệu bất biến; muốn nguồn mới thì nhập và lưu snapshot mới. Số bản ghi nguồn có thể khác số giao dịch hợp lệ theo thời điểm/phiên bản được chấm.

Đổi doanh nghiệp/dữ liệu sẽ hủy việc chờ ở trang và xóa kết quả cũ khỏi màn hình; job phía DN vẫn được lưu. Chọn lại đúng bản dữ liệu sẽ theo dõi job cũ. Quyền được kiểm ở mọi API và kiểm định kỳ trên giao diện; mất phiên/quyền thì bỏ màn hình kết quả. Portal hiện vẫn là danh tính workspace chung theo CR-025, chưa tài khoản cá nhân.

Thiếu model hoặc metadata không tương thích thì không cho bắt đầu lượt mới. Dòng thiếu nguồn/ngoài kỳ huấn luyện–đánh giá vẫn trả chưa khả dụng kèm hướng xử lý, không hiển thị điểm 0 giả. Chưa có ngưỡng kết luận giao dịch cần rà; điểm mở trong **Xem điểm bất thường**, không phải xác suất sai phạm hoặc độ chính xác của ML.

## Người vận hành bật tính năng

Mặc định backend chưa bật HE; màn hình báo **Phân tích bảo mật chưa được bật cho node này**, không chuyển sang chấm plaintext. Luồng bốn nhánh local tại trang nhập dữ liệu tiếp tục là chức năng riêng.

Chuẩn bị trước:

- Worker ciphertext-only đang chạy với grant public key node đúng tenant/DN theo [HE_TWO_SERVICES.md](HE_TWO_SERVICES.md).
- Model Mahalanobis đã fit offline tại DN, lưu MethodStore hiện hành, tương thích contract 33 feature theo [HE_REGISTRY_EXPORT.md](HE_REGISTRY_EXPORT.md). Không có fit/đổi model từ màn hình này.
- Node config **he-enterprise-service/1.2.0**, hai khóa DPAPI current-user và thư mục state riêng theo [HE_KEYS_AND_SESSIONS.md](HE_KEYS_AND_SESSIONS.md). Dùng đường dẫn tuyệt đối. Kho snapshot trong config phải **đúng cùng DB** của màn hình nhập, không chỉ cùng tên file.
- File ghim model phía server như sau (thay ID mẫu bằng artifact thật đã kiểm):

```json
{
  "version": "he-ui-bindings/1.0.0",
  "bindings": [
    {"tenant_id": "demo", "company_id": "C001", "artifact_id": "mth_<64-hex-thuc>"},
    {"tenant_id": "demo", "company_id": "C002", "artifact_id": "mth_<64-hex-thuc>"}
  ]
}
```

Không dùng ID giả ở trên để chạy. Ghim theo cả tenant và doanh nghiệp; duplicate/sai định dạng bị từ chối, không tự tìm model mới nhất. Catalog kiểm checksum/version/contract/provenance trước khi bật nút mà không deserialize payload hoặc fit. Khi chấm, exporter vẫn kiểm đầy đủ lần nữa trước deserialize, tạo feature và mã hóa.

Đặt hai biến môi trường **trước khi khởi động Portal** để launcher truyền cho Agent2:

```powershell
$env:AGENT2_HE_NODE_CONFIG = 'D:/du-lieu-rieng-DN/he-node.json'
$env:AGENT2_HE_BINDINGS = 'D:/du-lieu-rieng-DN/he-ui-bindings.json'
```

Các đường dẫn là ví dụ; người vận hành dùng file thật. Sau đó khởi động Portal/Agent2 theo [PORTAL_AUTH.md](PORTAL_AUTH.md). Nếu backend chạy thủ công, dùng hai tùy chọn tương đương `--he-node-config <node.json> --he-bindings <bindings.json>` cùng `--snapshot-db` và cấu hình xác thực hiện có.

Node được nhúng **tại backend Agent2 của DN**, dùng chính authorizer Portal hiện tại; `auth_file` trong node config vẫn thuộc định dạng standalone nhưng không được dùng làm fallback khi nhúng. Không có token dịch vụ chung để thay danh tính người dùng. Model, dữ liệu rõ, DPAPI keys và decrypt đều ở process DN; worker vẫn tách riêng/bundle ciphertext-only. Không đồng thời bật standalone enterprise_server và backend web trên cùng state_dir; kho phiên có exclusive lock.

Luồng local ngoài Portal tại `/encrypted-analysis` dùng credential backend cũ cho thử nghiệm; chỉ chế độ đó có form kết nối. Trong Portal không hiển thị form này. Không gửi password Portal thay cho credential backend, không đặt khóa/session trên URL và không mở CORS tới worker.

## API giao diện

Tất cả route theo `/api/v1/companies/{company}/he/`, quyền `data.import` và authorizer hiện tại. Qua Portal dùng proxy cùng origin, không cấp browser truy cập node/worker khác origin.

| Route | Mục đích |
|---|---|
| GET `datasets` | Tối đa 100 snapshot mới nhất trong đúng tenant/DN, checksum/metadata đã kiểm; thông báo nếu danh sách giới hạn. Không trả dữ liệu nguồn, model hoặc file khóa |
| POST `jobs`, body `{"snapshot_id":"snp_..."}` + Idempotency-Key | Backend chọn artifact và cutoff, tạo/đọc lại cùng durable job; không nhận thiết lập model/quyền/khóa từ body |
| GET `jobs/{job}` | Theo dõi trạng thái owner hiện tại |
| GET `jobs/{job}/result` | Kết quả đã giải mã tại DN, kiểm quyền trước trả |
| POST `jobs/{job}/resume`, body `{}` | Tiếp tục đúng phiên sau restart/xác thực lại |

Chỉ thêm allowlist các route này vào Portal; không mở `/decrypt`, `/fit`, arbitrary proxy hoặc `/v1` worker. API cũ của enterprise node không thay đổi. Thiếu cấu hình/provider/worker, lỗi nguồn hoặc quyền đều báo rõ và không có plaintext fallback.

## Phạm vi và kiểm thử

HE vẫn là thử nghiệm Mahalanobis **hai feature**, tối đa **8 dòng hợp lệ mỗi lượt** từ nguồn snapshot đầy đủ, không tự cắt dòng/lịch sử. Không tự mở rộng bốn nhánh HE hoặc đưa điểm vào queue/active. Chưa cloud public/TLS production, native sandbox/KMS/rotation/HA hoặc proof trước worker ác ý. Khóa/phiên có điều kiện khôi phục trong tài liệu CR-033; không bảo đảm phục hồi nếu mất state/profile/receipt/browser storage.

Kiểm thử dùng Portal, node DN và worker thật trong thư mục tạm với dữ liệu mô phỏng; không sửa khóa/config/DB live:

```powershell
& .venv/Scripts/python.exe -X utf8 -B scripts/test_he_analysis_ui.py --output-dir '<thu-muc-moi-chua-ton-tai>'
& .venv/Scripts/python.exe -X utf8 -B scripts/run_he_tests.py --report '<he-tests-moi.json>'
```

Browser test cần Playwright và Chrome đã có trên máy. Các ảnh desktop/mobile, kiểm mất kết nối/reload/cùng run ID, missing model/current permissions và nguồn không đổi được lưu trong báo cáo. Đây là READY_FOR_REVIEW cho UI HE thử nghiệm, không nghiệm thu bảo mật/độ chính xác hoặc hoàn tất R2/R5 sản phẩm.
