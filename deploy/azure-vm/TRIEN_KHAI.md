# Triển khai bản demo lên Azure VM — checklist

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Doanh nghiệp | Cả 4 agent dùng chung doanh nghiệp mô phỏng **Minh Phát (MPX10, MST 0999999905)**. Agent 4 chỉ đọc được kho sổ cái của Minh Phát, nên các agent còn lại cũng dùng doanh nghiệp này. Trên VM, mã DN và MST bị khóa (`MAF_LOCK_COMPANY=1`); các trường khác của hồ sơ vẫn sửa được. |
| Embedding | Agent 3 (tìm luật) và Agent 4 (chọn chỉ tiêu) embed bằng model local **`bge-m3:567m`** qua Ollama, không dùng OpenRouter. Trên máy nhóm là Ollama cài trên Windows (`127.0.0.1:11434`); trên VM là container `ollama` trong `compose.yaml`, tự tải model ở lần chạy đầu. Model ghi ở `.env` và ở `compose.yaml` phải giống nhau. |
| Dữ liệu có sẵn trên VM | Kho luật đã embed bằng `bge-m3:567m` (nằm trong image), kho ERP Minh Phát **bản full** cho Agent 4, mô hình Agent 2 đã fit sẵn cho MPX10/C001/C002, hồ sơ MPX10, mật khẩu nạp dữ liệu `SoSon@2026`. |
| Dữ liệu BTC tự nạp | Gói 9 tệp `01_Goi_Chuan_Nap_Chung_4_Agent_MPX10`. Agent 1, 2, 3 chưa có dữ liệu nào từ gói này. Agent 2 chỉ có sẵn dữ liệu mẫu (`bootstrap-MPX10`) và dữ liệu huấn luyện (`huan_luyen_MPX10`) để mô hình chạy được; tệp 07 đã được gỡ khỏi `state/` ngày 21/11, nên khi BTC nạp, Agent 2 ghi tệp 07 như dữ liệu mới. |
| Hóa đơn XML của Agent 3 | Giữ bộ tình huống rủi ro thuế (gốc Sao Việt, đã đổi sang MST của Minh Phát). Khi giới thiệu thì gọi là "bộ tình huống rủi ro thuế cài thêm". |
| Bảo vệ trang | Cả host Portal (gồm Portal, Agent 2, Agent 4) cần tài khoản `SITE_USER`. `/station/` dùng tài khoản riêng. Host Agent 1 và Agent 3 để mở vì Portal nhúng chúng trong iframe; hai host này chỉ chứa dữ liệu mô phỏng. |
| Build | Build image trên máy nhóm. VM chỉ nạp image (`docker load`) rồi chạy `up --no-build`. |
| Cấu hình | Dùng một file `.env` duy nhất ở thư mục gốc; mọi lệnh compose đều thêm `--env-file ../../.env`. |

## 0. Việc phải làm trước, nếu không demo sẽ lỗi

- [ ] Cài Ollama trên máy nhóm (https://ollama.com/download, bản Windows dùng được GPU) rồi chạy `ollama pull bge-m3:567m`. Embedding không còn gọi OpenRouter nên không bị giới hạn 50 request/ngày (lỗi HTTP 429 `free-models-per-day` hôm 21/11).
- [ ] Kiểm tra hạn mức Groq của `AGENT3_LLM_API_KEY` và `AGENT4_LLM_API_KEY` (model `qwen/qwen3.8-27b`). Hai agent cùng gọi model này trong suốt buổi chấm.

## 1. Trên máy nhóm

```powershell
# a. Embed kho luật bằng bge-m3 qua Ollama local (Ollama phải đang chạy)
cd "agent3\agent3_tax_compliance"
..\.venv\Scripts\python -m src.lawbase.cli embed
```

Lần chạy đầu, lệnh báo vectơ cũ (`nvidia/nemotron-3.5-embed-8b:free`, 4096 chiều) không khớp model mới, xóa chúng và embed lại toàn bộ 4706 đoạn. Nếu lệnh dừng giữa chừng thì chạy lại; xong khi lệnh in `đã thêm 0 vectơ`. (`cli status` không hiển thị số vectơ, nên không dùng nó để kiểm tra.)

```sh
# b. Bật Docker Desktop, tắt web local (.\run_web.ps1 -StopOnly), rồi build và xuất image (Git Bash)
cd deploy/azure-vm
docker compose --env-file ../../.env -f compose.yaml build maf-demo
docker save maf-demo:latest | gzip > ~/maf-demo.tar.gz

# c. Dữ liệu cho VM. Thư mục state/ đã được dựng ngày 21/11; dựng lại thì chạy:
#    python deploy/azure-vm/collect-state.py --source D:/SoSon_BTC_test/SoSon --force
tar -czf ~/state-pristine.tgz state

# d. Kiểm tra cú pháp Caddyfile. MSYS_NO_PATHCONV=1 ngăn Git Bash đổi /etc/caddy/... thành C:/Program Files/Git/etc/...
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e PORTAL_HOST=a.example.com -e AGENT1_HOST=b.example.com -e AGENT3_HOST=c.example.com \
  -e STATION_USER=x -e STATION_PASSWORD_HASH='$2b$04$tD2RtC0/beYGpbjVBPu7hOQF4IKKDEP8WXu/0CGZklqTqq2XXy38m' \
  -e SITE_USER=y -e SITE_PASSWORD_HASH='$2b$04$tD2RtC0/beYGpbjVBPu7hOQF4IKKDEP8WXu/0CGZklqTqq2XXy38m' \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
```

## 2. Tạo Azure VM

- [ ] Ubuntu 24.04 **x86-64**, ổ 128 GB trở lên, IP public tĩnh. VM hiện tại là **Standard_B4s_v2** (4 vCPU / 16 GB, Japan East): đủ chạy cả 3 container (lúc rảnh dùng khoảng 2 GB RAM). Dòng B là CPU burstable: khi chạy nặng lâu (nhiều giám khảo cùng phân tích Agent 2, hỏi Agent 4) thì hết credit CPU và bị giảm tốc. Muốn chắc hơn trong buổi chấm thì đổi size sang Standard_D8s_v5 (8 vCPU / 32 GB) trước giờ chấm, đổi lại sau đó; đổi size cần dừng VM vài phút, dữ liệu trên ổ vẫn giữ.
- [ ] NSG: mở 80 và 443; cổng 22 chỉ mở cho IP của nhóm. Không mở 8800, 8011, 8640, 8766, 8040, 8890, 11434.
- [ ] DNS: 3 bản ghi A (portal, agent1, agent3) trỏ về IP của VM. Không có tên miền thì dùng sslip.io, viết IP bằng gạch ngang như trong `.env`: VM hiện tại (IP `20.46.171.174`) là `portal.20-46-171-174.sslip.io`, `agent1.20-46-171-174.sslip.io`, `agent3.20-46-171-174.sslip.io`.
- [ ] Cài Docker: `curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER`, rồi đăng xuất và đăng nhập lại. Ghi lại kết quả `id -u` và `id -g`.

## 3. Sửa `.env` ở thư mục gốc, rồi chép lên VM

- [ ] `PORTAL_HOST`, `AGENT1_HOST`, `AGENT3_HOST` = 3 tên miền ở bước 2.
- [ ] `MAF_UID`, `MAF_GID` = kết quả `id -u` và `id -g` trên VM.
- [ ] Các biến đã có sẵn: `AGENT3_LLM_API_KEY`, `AGENT4_LLM_API_KEY` (Groq), `AGENT3_RERANK_API_KEY` (Cohere), `AGENT3_ADMIN_PASSWORD`, `STATION_*`, `SITE_*`. Các biến `*_EMBED_*` trong `.env` chỉ dùng trên máy nhóm; trên VM, `compose.yaml` ghi đè chúng để trỏ vào container `ollama`. Mật khẩu dạng chữ của `SITE_USER` nằm ở dòng ghi chú ngay phía trên.

```sh
ssh <vm> 'mkdir -p ~/soson/deploy/azure-vm'
scp ~/maf-demo.tar.gz ~/state-pristine.tgz <vm>:~/
scp .env <vm>:~/soson/.env
scp deploy/azure-vm/compose.yaml deploy/azure-vm/Caddyfile <vm>:~/soson/deploy/azure-vm/
```

## 4. Khởi động trên VM

```sh
cd ~/soson/deploy/azure-vm
gunzip -c ~/maf-demo.tar.gz | docker load
tar -xzf ~/state-pristine.tgz
docker compose --env-file ../../.env -f compose.yaml up -d --no-build
docker compose --env-file ../../.env -f compose.yaml logs -f maf-demo
```

Lần đầu, container `maf-demo-ollama` tải `bge-m3:567m` (khoảng 1,2 GB) vào volume `ollama_models`. Xem bằng `docker compose --env-file ../../.env -f compose.yaml logs -f ollama`, chờ tới dòng `success`. Trước lúc đó Agent 4 chưa trả lời được và Agent 3 chỉ tìm luật theo từ khóa.

Nếu compose báo thiếu thư mục build, xóa khối `build:` trong bản `compose.yaml` trên VM.

## 5. Tự kiểm tra, rồi đưa về trạng thái sạch

- [ ] `https://<PORTAL_HOST>` hỏi tài khoản `SITE_USER`; Trang Tổng quan báo 4/4 agent sẵn sàng.
- [ ] Hồ sơ là MPX10 / 0999999905; thử đổi mã DN thì bị từ chối.
- [ ] Trang `#data` mở khóa được bằng `SoSon@2026`, không hiện màn hình đặt mật khẩu mới.
- [ ] Agent 4: hỏi "Doanh thu thuần quý 3 năm 2026 là bao nhiêu?" ra **3.459.561.433.330**.
- [ ] Agent 3: tìm điều luật có kết quả. Kho luật đủ vectơ khi lệnh sau in ra hai số bằng nhau (4706 4706):
  `docker compose --env-file ../../.env -f compose.yaml exec maf-demo python -c "import sqlite3; print(*sqlite3.connect('/state/agent3/legal_corpus.sqlite3').execute('SELECT (SELECT COUNT(*) FROM chunk_vec), (SELECT COUNT(*) FROM chunks)').fetchone())"`
- [ ] Nạp gói 9 tệp. Agent 1 chạy được dự báo 13 tuần; Agent 2 "Phân tích" ra đủ 4 nhánh; Agent 3 phân tích được.
- [ ] Agent 1 và Agent 3 hiển thị được trong Portal.
- [ ] `/station/` đăng nhập được bằng `STATION_USER`.

Đưa về trạng thái sạch trước khi gửi link cho BTC:

```sh
docker compose --env-file ../../.env -f compose.yaml down
rm -rf state && tar -xzf ~/state-pristine.tgz
docker compose --env-file ../../.env -f compose.yaml up -d --no-build
```

## 6. Gửi cho BTC

- Link `https://<PORTAL_HOST>` và tài khoản `SITE_USER` cùng mật khẩu.
- Mật khẩu Nạp dữ liệu: `SoSon@2026`.
- File zip `DATA_TEST_MAF_SOSON`. Trước khi nén, sửa `00_THONG_TIN_DANG_NHAP_VA_TOM_TAT.txt`: đổi địa chỉ web thành `https://<PORTAL_HOST>` và thêm tài khoản trang.
- Ghi chú kèm theo:
  - Cả 4 agent dùng chung doanh nghiệp mô phỏng Minh Phát; Agent 4 đọc kho ERP mô phỏng của Minh Phát.
  - Các giám khảo dùng chung một trang nên sẽ thấy dữ liệu của nhau.
  - Chỉ nạp dữ liệu mô phỏng.
  - Phân tích mã hóa HE Concrete không có trên bản web; huấn luyện chung CKKS qua máy trạm thì có.

## 7. Vận hành

Viết tắt `dc` = `docker compose --env-file ../../.env -f compose.yaml`, chạy trong `~/soson/deploy/azure-vm`.

| Việc | Lệnh |
|---|---|
| Đổi API key hoặc mật khẩu | Sửa `~/soson/.env`, rồi chạy `dc up -d --no-build`. Không dùng `restart`, vì lệnh này không đọc lại file. |
| Xem log | `dc logs -f maf-demo`; embedding: `dc logs -f ollama` |
| Đưa về trạng thái sạch | Làm như cuối mục 5. |
| Cập nhật image | Làm lại mục 1b, chép image lên VM, `docker load`, rồi `dc up -d --no-build`. Nếu image mới có kho luật mới: xóa `state/agent3/legal_corpus.sqlite3` trước khi chạy lại. Model embedding nằm trong volume `ollama_models`, không bị mất khi đưa về trạng thái sạch. |
| Sau cuộc thi | `dc down`, rồi deallocate hoặc xóa VM. |
