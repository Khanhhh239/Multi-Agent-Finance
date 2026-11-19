# Cloud resource budget và Phase 0 benchmark

Ngày đo: 2026-11-19
Mục tiêu: ghi lại số đo thực tế, giới hạn nhà cung cấp và phần chưa đo được; không tuyên bố tương thích nếu chưa có bằng chứng.

## Kết luận

- Agent 4 health-only slice: có bằng chứng sơ bộ phù hợp về memory, nhưng chưa chứng minh query end-to-end với warehouse/provider trong giới hạn Vercel/Render.
- Từng agent riêng lẻ: import RSS hiện thấp hơn 512 MB, nhưng Agent 1/3 workload thật và Agent 2 HE4 chưa benchmark.
- Full modular monolith: chưa đo được trong một clean environment; tổng RSS bốn agent theo import/server smoke đã ở hoặc vượt 512 MB trước workload. Không đủ bằng chứng để GO.
- Separate deployments trên Render Free: NO-GO về giờ chạy/private networking, dù từng agent có thể fit memory riêng.
- Benchmark network server: bị sandbox chặn socket bind với PermissionError; không dùng kết quả này để kết luận application bind production.

## Giới hạn platform đã xác minh

| Hạn mức | Giá trị/ảnh hưởng |
|---|---|
| Render Free memory | 512 MB mỗi instance |
| Render Free CPU | 0.1 CPU mỗi instance |
| Render Free instance hours | 750 giờ/workspace/tháng |
| Render Free storage | Filesystem ephemeral; mất khi restart/redeploy/spin down |
| Render Free availability | Spin down sau 15 phút idle; cold start khoảng một phút |
| Render Free topology | Không scale quá một instance; không nhận private network traffic |
| Neon Free database | 1 GB/project; writes tăng storage fail khi vượt quota |
| Neon Free compute | 100 CU-hours/project/tháng; scale-to-zero sau 5 phút |
| Neon Free network | 5 GB public transfer/project/tháng; private networking không có trên Free |
| Neon Free object storage | 5 GB/project theo plans hiện hành |
| Vercel Hobby static upload | 100 MB |
| Vercel external rewrite | Proxied request timeout tối đa 120 giây |

Nguồn:

- [Render Free](https://render.com/docs/free)
- [Render compute plans](https://render.com/docs/compute-plans)
- [Vercel limits](https://vercel.com/docs/limits)
- [Vercel rewrites](https://vercel.com/docs/routing/rewrites)
- [Neon plans](https://neon.com/docs/introduction/plans)
- [Neon pgvector](https://neon.com/docs/extensions/pgvector)

## Benchmark methodology

Các phép đo sau đây chỉ đọc source/database hoặc chạy app trong temporary directory dưới /tmp. Không ghi secret thật và không xóa database hiện có.

- Import benchmark dùng /usr/bin/time với Python executable của từng agent.
- Server startup benchmark dùng timeout và health probe; sandbox hiện không cho tạo socket listen.
- Agent 4 slice benchmark dùng httpx ASGITransport, không cần socket.
- Các số RSS là maximum resident set size của process; import RSS không phải peak của workload thật.
- Kiểm thử có thể tạo .pytest_cache/tmp artifacts; không phải deployment result.

## Import RSS và startup

| Thành phần | Python environment | Import elapsed | Max RSS | Evidence |
|---|---|---:|---:|---|
| Portal import | system Python | 0.09 s | 28,356 KB | import portal.server |
| Agent 1 import | agent1/.venv | 1.42 s | 226,440 KB | import agent1_service.main |
| Agent 2 import | agent2/.venv | 1.07 s | 153,172 KB | import sme_fraud.review_server |
| Agent 3 import | agent3/.venv | 0.31 s | 62,804 KB | import src.assistant.web |
| Agent 4 import | agent4/.venv | 0.45 s | 73,392 KB | import agent4.api |

Tổng bốn agent theo import RSS: 515,808 KB, xấp xỉ 503.7 MiB. Đây là phép cộng các process độc lập, không phải single-process measurement; nó cũng chưa tính Portal, database page cache, request body, Python allocator, concurrent task, model load hoặc child process. Thêm Portal import là khoảng 531.4 MiB theo phép cộng thô.

Server startup attempt trong sandbox:

| Service | Max RSS quan sát được | Kết quả |
|---|---:|---|
| Agent 1 Uvicorn | 229,368 KB | App startup complete nhưng bind bị sandbox từ chối |
| Agent 2 stdlib server | 155,148 KB | Socket creation PermissionError |
| Agent 3 Uvicorn | 80,916 KB | App startup complete nhưng bind bị sandbox từ chối |
| Agent 4 Uvicorn | 77,140 KB | App startup complete nhưng bind bị sandbox từ chối |

Các số trên chỉ là startup process trước khi phục vụ request; không phải compatibility proof.

## Dependency environment evidence

Một environment chung chưa tồn tại:

| Python environment | Import Agent 1 | Import Agent 2 | Import Agent 3 | Import Agent 4 |
|---|---|---|---|---|
| agent1/.venv | OK | FAIL thiếu finance_input khi thử từ root | FAIL thiếu lxml | FAIL thiếu duckdb |
| agent2/.venv | FAIL thiếu pandas | OK | FAIL thiếu anyio | FAIL thiếu fastapi |
| agent3/.venv | FAIL thiếu pandas | FAIL thiếu finance_input | OK | FAIL thiếu cryptography |
| agent4/.venv | FAIL thiếu cryptography | FAIL thiếu finance_input | FAIL thiếu cryptography | OK |

Một số fail có thể do PYTHONPATH khi smoke thử, nhưng chúng vẫn cho thấy repository không có clean unified packaging contract. Agent 2 requirements.txt cũng không khai báo trực tiếp cryptography trong khi source import cryptography; cryptography chỉ xuất hiện trong requirements-he*.txt và environment hiện tại.

Pip check chưa chạy được vì các venv hiện có không cài module pip. Cần dùng clean image/uv lock/constraints trong milestone packaging; không coi environment hiện tại là reproducible build.

## Agent 4 minimal vertical slice

Đã chạy slice không mở socket:

- create_app với MetricSelectionConfig mặc định.
- ASGITransport gọi /healthz và /health.
- Cả hai trả HTTP 200.
- elapsed: 0.38 s.
- max RSS: 75,168 KB, xấp xỉ 73.4 MiB.
- Không gọi provider, không mở full warehouse query và không chứng minh upload/query latency.

Đây là baseline tốt cho health/config slice, không phải baseline của Agent 4 functional query. Một thử nghiệm query với smoke DuckDB warehouse và mock config bị timeout sau 20 giây; chưa đủ evidence để kết luận warehouse/query path phù hợp. Vì vậy query gate vẫn OPEN.

Vertical slice cần benchmark lại bằng:

1. Small immutable warehouse artifact có checksum.
2. Agent 4 create_app production mode, không create_demo_app.
3. Mock provider để đo deterministic query path.
4. External provider contract test riêng có timeout.
5. 1, 5 và 10 concurrent requests.
6. Cold start sau process restart.
7. Response size và p95 latency qua Vercel-like 120-second proxy.

## Test baseline đã chạy

| Suite/command | Kết quả | Diễn giải |
|---|---|---|
| Agent 4 tests/contracts/test_remote_metric_selection.py | 23 passed | Provider wire/config contracts hiện pass trong venv Agent 4 |
| Portal test_portal_security_and_intake.py | 56 passed, 5 errors | 5 error ở fixture mở socket do sandbox PermissionError; không phải kết luận code production pass |
| Agent 2 test suite | Chưa chạy | agent2/.venv không có pytest |
| Agent 1 selected security tests | timeout ở 20–25 giây | Chưa có baseline pass/fail đáng tin; cần chạy trong CI/runtime đầy đủ |
| Agent 3 selected web tests | timeout ở 20–25 giây | Chưa có baseline pass/fail đáng tin; có startup warm-up/local artifact effects |
| Full all-agent suite | Chưa chạy | 300 test files được phát hiện; scope lớn và dirty tree |

Không được dùng các kết quả trên làm chứng nhận regression-free. Chúng là baseline audit để thiết kế CI.

## Budget theo phương án

### Modular monolith full application

| Hạng mục | Ước tính/evidence | Đánh giá |
|---|---:|---|
| Import agent modules | khoảng 504 MiB cộng bốn process | Không có margin dưới 512 MB |
| Portal + import | khoảng 531 MiB phép cộng thô | Không chứng minh được |
| Agent 1 forecast | Có torch/transformers trong requirements-forecast.txt | CPU 0.1 và memory chưa benchmark, NO-GO |
| Agent 2 HE4 | requirements-he4-linux có torch/Concrete/cryptography; code còn Windows/WSL assumptions | NO-GO |
| Agent 3 full law/OCR | legal corpus 262,942,720 bytes; model/workload chưa đo | NO-GO nếu không externalize/lazy |
| Agent 4 health-only | 73.4 MiB | Có margin sơ bộ cho slice |
| Request timeout | current A1 600s; A4 180–360s; Vercel proxy 120s | Cần async/polling hoặc direct backend |

### Separate service topology

| Hạng mục | Giá trị |
|---|---:|
| 1 Gateway luôn chạy trong tháng 31 ngày | 744 giờ |
| 4 agent services luôn chạy trong tháng 31 ngày | 2,976 giờ |
| Gateway + 4 agents | 3,720 giờ |
| Free allowance/workspace | 750 giờ |

Free spin-down có thể làm usage thấp hơn, nhưng không nên dùng spin-down làm reliability strategy cho financial app. Topology năm service vẫn vượt quota nếu có traffic giữ service thức.

### Data/storage

| Data | Current evidence | Free-tier placement |
|---|---:|---|
| Portal static | 10.06 MiB, 24 files | Vercel static phù hợp |
| Agent 3 legal corpus | khoảng 263 MB, 17 tables | Object storage; chỉ metadata/chunks bounded vào Neon |
| Agent 4 smoke warehouse | 24.39 MB | Có thể là immutable slice nếu query benchmark pass |
| Agent 4 full warehouse | tài liệu mô tả khoảng 2.3 GB | Không đặt trong Neon 1 GB; không tải mỗi cold start Render Free |
| SQLite/JSON mutable state | nhiều file theo từng agent | Neon tables/object storage; không lưu Render filesystem |
| Embedding vectors | chưa có current Postgres schema | Chỉ nạp sau khi chốt dimensions/index/storage budget |

## Resource budget đề xuất cho conditional slice

Các ngưỡng này là acceptance targets, không phải kết quả đã đạt:

| Metric | Target trước khi GO | Điều kiện fail |
|---|---:|---|
| Cold start app | < 30 s sau khi process được cấp CPU | Import/warm-up provider/corpus dài hơn |
| Peak RSS | < 400 MiB, để lại khoảng 20% margin trên 512 MB | > 410 MiB trong bất kỳ p95 run nào |
| Health p95 | < 250 ms không gọi provider/DB nặng | Health phụ thuộc LLM hoặc warehouse scan |
| Query p95 | < 60 s; hard timeout < 90 s | Có khả năng chạm 120s Vercel proxy |
| Concurrent expensive queries | 1 trong Free slice | Nhiều request làm OOM/CPU starvation |
| Neon DB usage | < 800 MB với 20% headroom | > 800 MB hoặc write fail gần 1 GB |
| Neon object usage | < 4 GB với 20% headroom | Artifact vượt 4 GB hoặc không có retention |
| Render usage | Một backend; forecast theo traffic không vượt 750 giờ | Cần nhiều service luôn thức |
| Public transfer | Dưới 4 GB/tháng app budget | Chạm 5 GB Neon hoặc provider bandwidth cap |

## Kết luận budget

- GO có điều kiện: Portal static + Agent 4 health/metrics/query slice sau khi query benchmark, auth và storage budget pass.
- NO-GO: full four-agent modular monolith trên Render Free.
- NO-GO: five-service Render Free topology.
- GO sau khi nâng tier: full hybrid/private topology với worker/volume/private network và database budget phù hợp.

## Phase 1 measured packaging evidence

Ngày đo: 2026-11-19

| Hạng mục | Đo thực tế | Ý nghĩa |
|---|---:|---|
| Agent 4 cloud image logical size | 424,260,709 bytes (~404.7 MiB) | Cao so với image tối thiểu; không phải RAM runtime nhưng cần theo dõi cold pull/storage |
| Container memory tại health-only | 49.57 MiB | Có margin sơ bộ; chưa áp dụng cgroup Render 512 MiB/0.1 CPU |
| Process deterministic query peak | 112.4 MiB | Dưới target 400 MiB trong run đơn lẻ |
| Smoke warehouse | 24,391,680 bytes | Phù hợp artifact nhỏ; không đại diện full warehouse ~2.3 GB |
| Vercel static output | 11,854,097 bytes (~11.3 MiB) | Dưới budget static 100 MB; chưa bao gồm backend/API |

Không được suy ra từ các số trên rằng external provider query hoặc full Portal đã fit Render Free. Cần ba cold runs, concurrency profile, cgroup limit, provider latency và Gateway auth trước khi chuyển conditional slice thành GO.
