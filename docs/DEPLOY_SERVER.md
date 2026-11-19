# Gợi ý triển khai Sổ Son lên server

Nhánh `platform-Khanh`, 18/11/2026. Mục tiêu: một server chạy ổn định cho demo giám khảo hoặc pilot với doanh nghiệp thật, dữ liệu không rời máy chủ của doanh nghiệp.

## 1. Hệ thống gồm những gì (cần cấp phát gì)

| Thành phần | Công nghệ | Cổng | Dữ liệu và tài nguyên |
|---|---|---|---|
| Portal | Python chuẩn, `portal/server.py` | 8800 | JSON và tệp trong `portal/workspace` (mật khẩu băm, phiên bản gói, nhật ký) |
| Agent 1 Dòng tiền | FastAPI, pandas, sklearn | 8011 | SQLite và khóa trong `agent1/.state-business-firm-<mã>-data`; vài GB RAM khi huấn luyện |
| Agent 2 Soát giao dịch | Python chuẩn, sklearn, networkx | 8766 | SQLite snapshot và mô hình trong `agent2/.runtime/platform`; HE cần Concrete trên Linux |
| Agent 3 Thuế GTGT | FastAPI, torch, transformers | 8640 | Kho luật `data/lawbase` (khoảng 400 MB, riêng `legal_corpus.sqlite3` 364 MB), mô hình xếp hạng lại 2,2 GB, không gian làm việc theo MST |
| Agent 4 Hỏi đáp | FastAPI, DuckDB | 8040 | DuckDB chỉ đọc (bản đầy đủ 2,3 GB) |

Phần cứng đề xuất cho một doanh nghiệp: 8 vCPU, 32 GB RAM, ổ SSD 200 GB. Agent 4 dùng API provider; cần cấu hình secret và giới hạn timeout/rate của provider thay vì GPU cục bộ.

## 2. Kiến trúc đề xuất: một máy Linux, Docker Compose, một cổng vào

```
Internet --> Caddy hoặc Nginx (HTTPS, tên miền, giới hạn tốc độ)
               |--> portal :8800            (duy nhất công khai)
               |--> mạng nội bộ Docker: agent1 agent2 agent3 agent4
```

- Chỉ mở cổng 443. Bốn agent nằm trong mạng nội bộ Docker, không publish cổng ra ngoài.
- Mỗi thành phần một container, thư mục dữ liệu mount thành volume riêng (để sao lưu và nâng cấp không mất dữ liệu).
- `agent1/compose.yaml` và `Dockerfile` của Agent 1 đã có; cần viết thêm cho Portal, Agent 2, 3, 4 theo cùng kiểu (python:3.12-slim, `pip install -r requirements`, chạy bằng `uvicorn` hoặc `python -m`).

## 3. Những chỗ trong mã phải sửa trước khi đưa lên server

Đây là việc thật sự, không chỉ là cấu hình:

1. **Portal đang khóa vào `127.0.0.1`.** `HOST = '127.0.0.1'` trong `portal/server.py`; hàm kiểm tra Host chỉ nhận `127.0.0.1` và `localhost`; `frame-src` và `frame-ancestors` của CSP cũng chỉ cho localhost. Cần tham số hóa bằng biến môi trường (địa chỉ nghe, tên miền công khai, danh sách origin được phép).
2. **Địa chỉ agent trong portal** được ghép cứng `http://127.0.0.1:<cổng>`. Trong Compose phải là tên dịch vụ (`http://agent1:8000`...). Nên đọc từ `config.local.json`.
3. **Portal đang tự bật agent bằng tiến trình con** (`--start-all`). Trên server nên để Docker/systemd quản lý, portal chỉ kiểm tra sức khỏe. Cần chế độ "không tự bật".
4. **Xác thực.** Hiện một mật khẩu nạp dữ liệu dùng chung và FaceID gắn với `localhost`. Với server cần đăng nhập từng người (OIDC của Google Workspace, Microsoft Entra hoặc Keycloak), phân quyền theo vai trò (kế toán, giám đốc, kiểm toán) và ghi người thao tác vào nhật ký. FaceID trên mạng cần HTTPS (WebAuthn bắt buộc), nên giữ như yếu tố thứ hai tùy chọn.
5. **Windows DPAPI của Agent 2** (bọc khóa HE) không có trên Linux: thay bằng tệp khóa trong secret của Docker hoặc KMS.
6. **Bí mật.** Token nội bộ giữa portal và agent đang sinh ngẫu nhiên mỗi lần khởi động; trên server dùng biến môi trường cố định lấy từ trình quản lý bí mật, không đưa vào Git.
7. **Agent 4 đang ở chế độ demo** (`create_demo_app`, hai vai trò giả). Bản thật dùng `create_app` với claims và chính sách do portal cấp theo người đăng nhập.
8. **Đồng bộ phiên bản dữ liệu.** SQLite và DuckDB phù hợp một doanh nghiệp, một tiến trình. Nhiều doanh nghiệp hoặc nhiều bản sao cần chuyển sang PostgreSQL cho trạng thái và tách kho DuckDB theo doanh nghiệp (portal hiện chỉ chạy một doanh nghiệp một lúc).

## 4. Lộ trình triển khai (từ nhanh đến chắc)

| Bước | Việc | Thời gian |
|---|---|---|
| A. Demo công khai tạm | Chạy nguyên bản trên một VPS GPU, mở qua tunnel (Cloudflare Tunnel hoặc Tailscale) có mật khẩu; không sửa mã | 0,5 ngày |
| B. Một server, Docker Compose | Làm mục 3 các điểm 1, 2, 3, 6; thêm Caddy và HTTPS; sao lưu volume hằng đêm | 3 đến 5 ngày |
| C. Cho doanh nghiệp thật dùng thử | Điểm 4, 5, 7: đăng nhập từng người, phân quyền, nhật ký người thao tác, kiểm thử bảo mật cơ bản (OWASP), chính sách lưu và xóa dữ liệu | 2 đến 3 tuần |
| D. Nhiều doanh nghiệp | Điểm 8, tách tenant, hàng đợi cho tác vụ nặng (huấn luyện A1, nhập tệp lớn A2), giám sát (Prometheus, Grafana) | 1 đến 2 tháng |

## 5. Sao lưu, giám sát, vận hành

- Sao lưu hằng đêm: `portal/workspace`, `agent1/.state-*`, `agent2/.runtime`, `agent3/.../data` (không cần sao lưu `lawbase/cache`), kho DuckDB và `intake_security.json`. Thử khôi phục mỗi tháng.
- Giám sát: mỗi agent đã có `/health`; thêm kiểm tra từ bên ngoài (UptimeRobot hoặc Prometheus blackbox) và cảnh báo khi hỏi đáp chậm quá 60 giây hoặc ổ đĩa trên 85%.
- Nhật ký: gom log của năm container về một nơi (Loki hoặc tệp xoay vòng); nhật ký nối băm của portal giữ nguyên làm bằng chứng.
- Cập nhật kho luật: chạy `python -m src.lawbase.cli sync` hằng tuần bằng lịch (cron), sau đó `check-ruleset` để cảnh báo khi một căn cứ luật hết hiệu lực.
- API provider: ghim model/prompt version trong config, đặt timeout/rate limit và không ghi secret vào log.

## 6. Rủi ro cần nói rõ khi chào hàng

- Dữ liệu doanh nghiệp thật chưa được kiểm chứng ở bất kỳ agent nào; luật đang ở trạng thái nháp, chưa có chuyên gia thuế duyệt.
- Kết quả để tham khảo và có người duyệt; không thay kết luận của cơ quan thuế hay kiểm toán.
- Phụ thuộc API provider: lỗi quota, timeout hoặc gián đoạn mạng phải được giám sát và hiển thị là trạng thái retryable.
