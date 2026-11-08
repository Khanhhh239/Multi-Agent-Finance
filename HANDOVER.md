# Bàn giao nhanh: web chung bốn agent (nhánh `platform-Khanh`, 08/11/2026)

Dữ liệu trong mọi bản chạy thử đều là dữ liệu mô phỏng. Chưa có số liệu doanh nghiệp thật.

## 1. Có gì trong nhánh

| Thư mục | Nội dung |
|---|---|
| `agent1/`, `agent2/`, `agent3/`, `agent4/` | Code bốn agent, lấy nguyên từ `agent1-Khanh`, `agent2-Khanh-sosoat`, `agent3-core-adapt`, `Agent4` (thư mục `agent4`) |
| `portal/` | Web chung bằng thư viện chuẩn Python: `server.py`, giao diện trong `portal/static/` |
| `design/` | Bộ thiết kế chung: `platform-theme.css`, `platform-theme.js`, phông Be Vietnam Pro, `sync.py` |
| `agent4_chat/` | Khung chat Agent 4, nhóm Agent 4 tự chỉnh trong thư mục này |
| `README.md` | Cách chạy và luồng dùng |

## 2. Chạy

1. Chép `portal/config.example.json` thành `portal/config.local.json`. Khai báo `python` cho agent nào chưa có `.venv` trong thư mục của nó.
2. Chạy `python portal/server.py --start-all`, mở http://127.0.0.1:8800.
3. Agent 2 cần thư mục demo `agent2/.runtime/platform`, dựng bằng `agent2/scripts/make_company_ml_big_demo.py --root .runtime/platform`. Bộ này thiếu vài cột danh mục (`self_approval_limit_vnd`, `registered_at`...) nên phải thêm vào `employees.csv` và `vendors.csv` mới nhận được tệp nhập.
4. Agent 3 cần kho luật và mô hình. Hai thư mục này không nằm trong git: `agent3/agent3_tax_compliance/data/lawbase` và `.../models`. Trên máy của Khanh chúng là liên kết thư mục tới `Downloads/agent3_run/...`.
5. Agent 4 cần `python -m agent4.datagen.build --out data/cfo_warehouse.duckdb --seed 20251` và môi trường riêng (`agent4/.venv`).

## 3. Nạp dữ liệu một lần, có mật khẩu (trang Nạp dữ liệu)

- Một nơi thả tệp cho Agent 1, 2, 3. Portal nhận dạng tệp, chạy bước xem trước của agent nhận, chỉ ghi khi bấm "Niêm phong và ghi".
- Hàng chờ được gắn với hồ sơ đang chọn lúc nạp. Khi đổi mã doanh nghiệp, portal hiển thị hàng chờ của mã mới. Khi sửa mã liên kết hoặc định dạng nhập, tệp cũ cần kiểm tra lại. Tệp chờ từ bản cũ chưa gắn hồ sơ cũng cần bấm "Kiểm tra lại" để gắn với hồ sơ đang mở.
- Mật khẩu nạp dữ liệu đặt lần đầu ở trang này, lưu dạng băm scrypt trong `portal/workspace/intake_security.json`. Phiên 20 phút, sai 5 lần thì khóa 60 giây. Quên mật khẩu thì xóa tệp đó.
- Mỗi lần ghi là một phiên bản của gói (`portal/workspace/batches.json`), có mã băm của danh sách tệp. Từ phiên bản thứ hai trở đi bắt buộc nhập lý do (ít nhất 10 ký tự).
- Sau khi có gói niêm phong, sửa cấu hình doanh nghiệp cũng cần mở khóa.
- Nhật ký `portal/workspace/audit.jsonl` nối băm từng dòng, trang có nút kiểm tra chuỗi.
- Hàng chờ có cột kỳ dữ liệu. Nếu kỳ của các agent không giao nhau, trang cảnh báo.
- Trong khung portal, mục nhập dữ liệu riêng của từng agent bị ẩn bằng CSS. Các API nhập của agent vẫn mở trên máy cục bộ. Chưa chặn ở tầng agent.
- Định dạng tệp của ba agent vẫn khác nhau. Portal chưa chuyển đổi giữa các định dạng và không tự tạo dữ liệu thay thế.

## 4. Giao diện chung

- Một phông (Be Vietnam Pro, đóng gói sẵn, không gọi mạng; nặng nhất là 600), màu nhấn xanh biển `#096b66` và thanh ba màu mảnh ở đầu trang. Agent 4 đọc cùng bộ biến trực tiếp từ portal.
- Nguồn duy nhất là `design/platform-theme.css`. Sửa xong chạy `python design/sync.py`: lệnh chép vào từng agent, thêm hoặc làm mới thẻ liên kết có mã băm nội dung. `python design/sync.py --check` dùng để kiểm tra.
- Agent 1 đổi biến `--green`, `--ink`... Agent 2 đổi `--blue`, `--navy`. Agent 3 đổi biến Carbon `--cds-*` (ghi đè cả trên `body.cds--g10`).
- Agent 2 phục vụ tệp theme qua `agent2/sme_fraud/platform_theme.py`. Agent 1 và Agent 3 dùng thư mục tĩnh sẵn có.
- Trang Tổng quan dùng ảnh thật Hội An về đêm, Eo Gió ở Quy Nhơn và đảo Bé Lý Sơn ở Quảng Ngãi. Tệp WebP nằm trong `portal/static/places/`. Tác giả, ảnh gốc và giấy phép Wikimedia Commons nằm ở cuối trang Tổng quan.

## 5. Sửa trong code agent (đều không đổi hành vi khi chạy riêng)

- Agent 1: `workspace/api.py` đọc `AGENT1_FRAME_ANCESTORS`; `ui/workspace/app.js` nhận khóa từ trang cha trên localhost.
- Agent 2: `review_server.py` đọc `SOSOAT_FRAME_ANCESTORS`; thêm `platform_theme.py` và hai dòng nối vào `review_server.py`, `p2_controls_server.py`.
- Agent 3: chỉ thêm tệp theme và thẻ liên kết vào `index.html`.

## 6. Còn thiếu, người nhận nên làm tiếp

1. Đã kiểm tra Tổng quan trên Chrome từ 320 đến 1440 px, luồng nạp trên điện thoại và việc tải theme ở cả bốn khung agent. Còn kiểm thử chi tiết các màn hình nghiệp vụ bên trong từng agent.
2. Chưa chạy bộ kiểm thử của Agent 2 và Agent 3 sau khi thêm theme. Chỉ chạy lại một bài kiểm tra tiêu đề bảo mật của Agent 1 (đạt).
3. Agent 4 dùng kho demo cố định, chưa nhận tệp, chưa dùng hồ sơ doanh nghiệp.
4. Doanh nghiệp tạo ở Agent 3 qua portal chưa có các quy định chi tiêu gợi ý sẵn. Agent 3 cần mật khẩu quản trị riêng, portal chỉ chuyển mật khẩu đó một lần.
5. Khóa chống sửa mới ở tầng portal. Muốn chặn thật phải thêm kiểm tra ở API nhập của từng agent.
6. Nhiều mã có thể chạy song song chưa được hỗ trợ: portal chạy một doanh nghiệp tại một thời điểm.
