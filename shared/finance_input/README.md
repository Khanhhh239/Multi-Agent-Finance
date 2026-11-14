# Hợp đồng đầu vào 1.0.0/1.1.0 — thư viện kiểm tra 1.2.0

CR-048 thêm **input 1.2.0 opt-in** cho kiểm tra master B5/E4 tại Agent2:
`vendors.phone`, `vendors.related_party_disclosed_at`. Mặc định `schema()` vẫn
trả 1.1.0; hai schema 1.0.0/1.1.0 không thay đổi, không tự nâng dữ liệu hoặc
migrate Agent1/3/4. Trường vắng/null là chưa biết; chuỗi rỗng được nguồn khai rõ
là không có số điện thoại/khai báo quan hệ trong bản xuất. Xem
[cách dùng và giới hạn](../../agent2/docs/VENDOR_IDENTITY_SNAPSHOT.md).

Input 1.1.0 thêm payment_channel và payment_history_coverage cho nguồn P1. `schema()` trả bản mới; `schema("1.0.0")` đọc schema cũ bất biến, `check_core` chọn theo phiên bản payload. Không tự nâng dữ liệu cũ hoặc suy kênh/lịch sử. [Hướng dẫn P1](../../agent2/docs/P1_INPUTS.md). Các agent khác chưa được tự migrate.

Package nhỏ, độc lập với framework và database của từng agent. Đã được Agent2 dùng qua profile; Agent1/3/4 chưa được chuyển đổi. [Đặc tả và mapping](../../agent2/docs/INPUT_DATA_CONTRACT.md).

```powershell
# Từ root repository; dùng môi trường Python của ứng dụng muốn tích hợp
python -m pip install -e ./shared/finance_input
```

- `finance_input.schema(version=None)`: registry schema theo phiên bản, mặc định 1.1.0.
- `check_core(bundle, scope)`: kiểm schema, kiểu số nguyên chính xác, tenant, định danh, revision và thời điểm. Từ chối toàn gói khi lỗi, không bỏ dòng.
- `AccessScope`: context do backend đã xác thực cung cấp; không nhận context quyền do browser tự khai. Thư viện không đăng nhập hay cấp quyền.
- `json_io.loads`: giữ số nguyên chính xác, chặn khóa JSON trùng và NaN/Infinity; dùng cho adapter HTTP/policy backend.
- `money.minor/major`: trích **nguyên mã** Agent1, không import ứng dụng Agent1. Commit/path/hash trong [UPSTREAM.json](UPSTREAM.json). Agent2 bọc thêm `parse_vnd` và profile riêng.
- Agent khác có thể gọi core và profile riêng, không phải thỏa điều kiện phân tích Agent2.

Schema dùng format `source-timestamp`; khi chạy Python phải dùng validator/format checker của package. Chỉ đọc JSON Schema bằng một công cụ bỏ qua format sẽ không đủ kiểm tra ngày lịch thực tế. Không có tự nhận diện ngày địa phương hoặc chuyển đổi ngoại tệ.

Không phải file uploader, snapshot store, authentication middleware hay chứng nhận dữ liệu gốc. `capabilities` do Agent2 trả chỉ phản ánh có nguồn, không chứng minh đủ lịch sử cho model.
