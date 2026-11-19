# Kiến trúc di trú cloud — Phase 0 và phương án đề xuất

Ngày đánh giá: 2026-11-19
Phạm vi: Portal, Agent 1-4, persistence, frontend, external AI APIs, Vercel, Render Free, Neon Free và object storage.

## Quyết định kiến trúc

**Full application trên đúng các giới hạn free-tier đã nêu: NO-GO ở thời điểm hiện tại.**

**Agent 4 vertical slice + Portal static frontend: CONDITIONAL GO**, chỉ sau khi hoàn tất các benchmark/query/auth gates trong docs/cloud-evaluation.md.

**Phương án full functionality thực tế:** hybrid hoặc paid infrastructure. Giữ local deployment làm baseline, chuyển dần control-plane và artifact storage lên cloud; Agent 1 forecasting, Agent 2 HE4 và Agent 3 law/OCR không được giả định chạy trên Render Free nếu chưa có benchmark sạch chứng minh.

Lý do không thể tuyên bố GO cho toàn bộ hệ thống:

- Bốn agent hiện là bốn runtime/dependency graph khác nhau, được Portal khởi động bằng subprocess.
- Mỗi agent import trong môi trường hiện tại đã dùng khoảng 62.8–226.4 MB RSS; tổng bốn process theo số đo import là khoảng 515.8 MB, chưa tính Portal, database cache, request buffers hoặc workload.
- Không có một virtualenv hiện có import được cả bốn agent: agent4 thiếu cryptography khi thử import Agent 1; agent1 thiếu duckdb khi thử import Agent 4; các environment khác thiếu finance_input, lxml hoặc anyio tùy hướng.
- Render Free chỉ có 512 MB RAM và 0.1 CPU mỗi instance, filesystem ephemeral, không persistent disk, không scale ngang và Free web service không nhận private network traffic.
- Neon Free có 1 GB PostgreSQL/project; legal corpus SQLite hiện khoảng 263 MB, warehouse đầy đủ được tài liệu mô tả khoảng 2.3 GB, chưa tính indexes, application state và vector embeddings.
- Các request hiện tại có thể kéo dài tới 600 giây cho import hoặc 180–360 giây cho AI, trong khi Vercel external rewrite có giới hạn 120 giây.

## Ràng buộc nhà cung cấp đã kiểm chứng

| Nền tảng | Giới hạn/tính năng đã kiểm chứng | Hệ quả thiết kế |
|---|---|---|
| Render Free | 0.1 CPU, 512 MB RAM; 750 Free instance hours/workspace/tháng; spin down sau 15 phút idle và cold start khoảng một phút; filesystem ephemeral; không persistent disk, không scale quá một instance, không nhận private network traffic | Chỉ một public backend nhỏ là phù hợp; không chạy five-service topology, không lưu SQLite/DuckDB mutable trên disk, không dùng inter-service private URL |
| Render web service | Phải bind 0.0.0.0 và port platform cấp; web service có thể giao tiếp private với service khác trên private network ở tier hỗ trợ | Code hiện bind loopback; Render Free không thể dùng làm private agent service nhận traffic |
| Vercel static | Static assets có thể deploy không cần server; static upload limit trên Hobby là 100 MB; external rewrites hoạt động như reverse proxy; proxied request timeout tối đa 120 giây | Portal static 10.06 MiB/24 files phù hợp; không proxy import/LLM dài; cần vercel.json hoặc API base rõ ràng |
| Neon Free | 1 GB PostgreSQL/project; 100 CU-hours/project/tháng; tối đa 2 CU/8 GB RAM; scale-to-zero sau 5 phút; 5 GB public transfer/project/tháng; 10 branches; 1 manual snapshot và 6 giờ instant restore | Phù hợp control-plane nhỏ, không phù hợp chứa toàn bộ raw documents/lawbase/warehouse; phải export backup riêng |
| Neon pgvector | pgvector có trên mọi plan; bật bằng CREATE EXTENSION IF NOT EXISTS vector; extension cài theo database | Có thể lưu một bounded embedding index, nhưng phải chốt dimension, index và quota trước khi nạp |
| Neon Object Storage | Free plan hiện bao gồm 5 GB/project, S3-compatible và đi cùng branch theo tài liệu sản phẩm | Có thể lưu raw uploads/artifacts nhỏ; phải có retention, checksum, private access và quota guard |
| Cloudflare R2, phương án phụ | 10 GB-month storage, 1M Class A, 10M Class B/tháng miễn phí; egress Internet miễn phí theo pricing hiện hành | Có thể tách object storage khỏi Neon; cần thêm account/provider và policy data residency |
| Render Free Postgres | Render Free Postgres có giới hạn/free lifecycle riêng và không thay thế Neon trong kiến trúc này | Không dùng Render Postgres làm system of record; dùng Neon như yêu cầu ban đầu |

Nguồn chính thức:

- [Render Free](https://render.com/docs/free)
- [Render compute plans](https://render.com/docs/compute-plans)
- [Render web services](https://render.com/docs/web-services)
- [Vercel limits](https://vercel.com/docs/limits)
- [Vercel rewrites](https://vercel.com/docs/routing/rewrites)
- [Neon plans](https://neon.com/docs/introduction/plans)
- [Neon pgvector](https://neon.com/docs/extensions/pgvector)
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)

## Bằng chứng từ repository

### Current topology

- Portal: portal/server.py, stdlib HTTP server, mặc định cổng 8800, tự spawn Agent 1-4, host 127.0.0.1.
- Agent 1: agent1/agent1_service/main.py và api.py, FastAPI/Uvicorn, SQLite state, encryption/pseudonym keys, optional forecast stack.
- Agent 2: agent2/sme_fraud/review_server.py, stdlib ThreadingHTTPServer, loopback-only, nhiều SQLite stores, optional HE/HE4.
- Agent 3: agent3/agent3_tax_compliance/src/assistant/web.py, FastAPI, raw-body uploads, local workspaces, SQLite foundation migrations, legal corpus SQLite.
- Agent 4: agent4/agent4/api.py, governed query pipeline, read-only DuckDB warehouse, external LLM/embedding APIs.
- Portal UI: portal/static/index.html và app.js, raw static assets, fetch URL tương đối, bốn iframe agent.
- Không có render.yaml, vercel.json, root Dockerfile, root dependency manifest hay DATABASE_URL/driver PostgreSQL.

### Persistence

- Agent 1 tạo agent1.db, token và encryption/pseudonym keys trong local directories.
- Agent 2 tạo snapshots, models, cases, remediation, review/release/batch SQLite stores.
- Agent 3 migrations 001-010 là SQLite-specific, có append-only triggers, BLOB raw data, lease/job tables và JSON payload.
- Agent 4 dùng DuckDB file; warehouse smoke hiện có 46 objects, 55,955 gl_entry rows và 24.39 MB.
- Legal corpus hiện có 17 SQLite tables, 882 documents, 27,729 chunks, 54,482 provisions và kích thước khoảng 262,942,720 bytes.
- Portal dùng JSON/JSONL state cho workspace, security, audit, batch và pending files.

## So sánh các phương án

### Phương án A — Modular monolith trên một Render Free web service

Mô hình:

- Vercel chỉ phục vụ Portal static.
- Một Render Free public web service chứa Gateway và một subset agent route.
- Agent routes dùng adapter/registry/lazy import, không dùng Portal subprocess.
- Neon lưu control-plane metadata và auth/audit nhỏ.
- Neon Object Storage hoặc R2 lưu raw documents/artifacts.
- Agent 4 dùng một immutable, small, versioned warehouse artifact; không tạo warehouse lớn trên request path.

Ưu điểm:

- Một service dùng khoảng 744 giờ trong tháng 31 ngày, còn nằm dưới quota 750 nếu luôn chạy; nhiều service sẽ vượt quota.
- Không phụ thuộc Free private-network ingress giữa agents.
- Giữ được nhiều business logic hiện tại bằng adapter thay vì rewrite.
- Vercel chỉ xử lý static assets; backend có một public origin duy nhất.
- Agent 4 có thể khởi chạy với khoảng 75 MB RSS cho health-only slice trong benchmark hiện tại.

Nhược điểm/blocker:

- Full import của các agent không có dependency environment dùng chung và tổng RSS hiện đã vượt 512 MB theo số đo cộng dồn.
- Import toàn bộ module ngay startup sẽ làm cold start và memory xấu; lazy import chỉ giảm startup nếu request không đụng agent đó, không giải quyết peak khi chạy đồng thời.
- 0.1 CPU không phù hợp train forecast, OCR, law sync hoặc batch fraud analysis.
- Không thể lưu local mutable SQLite/DuckDB sau restart.
- Request dài bị giới hạn bởi Vercel rewrite 120 giây.
- Cần tách async job, nhưng Render Free không có one-off job và không có reliable worker/private queue miễn phí.

Kết luận: đây là **primary candidate cho cloud slice**, không phải bằng chứng rằng full application tương thích.

### Phương án B — Deploy riêng Portal, Agent 1, Agent 2, Agent 3, Agent 4

Mô hình: năm Render web services, mỗi service có public URL vì Render Free không nhận private network traffic.

Ưu điểm:

- Cách ly dependency và peak memory theo service.
- Có thể giữ entry point/business logic từng agent nhiều hơn.
- Có thể scale/roll back độc lập ở tier trả phí.

Blocker:

- 5 service x 24 x 31 = 3,720 instance-hours/tháng, cao hơn nhiều quota 750; ngay cả bốn agent cũng là 2,976 giờ trước khi tính Portal.
- Public agent endpoints làm tăng attack surface; current auth/Origin contracts phụ thuộc localhost.
- Free service không nhận private network traffic, nên không thể dùng private agent URLs như tài liệu Docker Compose.
- Mỗi service spin down độc lập, cold-start dây chuyền làm Portal iframe/health behavior không ổn định.
- Filesystem ephemeral trên từng service làm state inconsistent.

Kết luận: **NO-GO trên Render Free**; chỉ xem xét trên paid/private topology sau khi chốt service contracts.

### Phương án C — Hybrid

Mô hình:

- Vercel: static Portal.
- Một Render Free backend: Gateway + Agent 4 minimal slice.
- Neon: tenant/control-plane, auth mapping, audit metadata, small vector metadata.
- Object storage: raw uploads, immutable legal/document artifacts, reports và warehouse snapshots nhỏ.
- Agent 1 full forecast, Agent 2 review/HE, Agent 3 OCR/law sync chạy local hoặc trên paid worker/service; cloud backend gọi qua một public authenticated job API chỉ khi có infrastructure phù hợp.
- DuckDB giữ read-only cho analytical artifact nhỏ, không phải mutable database và không phải full warehouse trên Render.

Ưu điểm:

- Phù hợp nhất với quota giờ và 512 MB.
- Bảo toàn local deployment/full functionality trong giai đoạn đầu.
- Cloud slice có thể chứng minh auth, query, UI routing và external provider flow mà không giả vờ toàn bộ workload đã cloud-ready.
- Có đường nâng cấp rõ sang paid private services.

Nhược điểm:

- Không phải full cloud migration; người dùng phải chấp nhận feature placement.
- Cần đồng bộ identity, job status, artifact checksum giữa local worker và cloud.
- External public job API phải thiết kế chống replay/SSRF và không lộ tài chính.

Kết luận: **RECOMMENDED** cho Phase 0/Phase 1.

## Thiết kế modular monolith được khuyến nghị

### Boundary

Một process cloud chỉ có các module sau:

1. API gateway và health.
2. Authentication/session verification và policy context.
3. Agent 4 governed query slice.
4. Metadata/audit adapters cho Neon.
5. Object storage adapter.
6. Provider clients có timeout ngắn, retry bounded và circuit breaker.
7. Async job status facade, chưa chạy heavy job trong free process.

Agent 1-3 không được import eager vào process slice. Từng route đăng ký bằng capability registry; code business hiện tại được gọi qua adapter khi capability được bật trong môi trường đủ tài nguyên.

### Lazy initialization

- Import FastAPI/Gateway/Agent 4 core ở startup.
- Không load legal corpus, reranker, torch, HE runtime hoặc forecast model ở startup.
- DuckDB connection mở read-only theo request scope hoặc bounded cache; đóng khi app shutdown.
- Provider clients dùng một shared HTTP client với timeout thấp hơn 120 giây.
- Không gọi LLM trong liveness/readiness.
- Không background warm-up gọi provider trên Render Free.
- Chỉ cho phép một concurrent expensive query trong free slice; request sau nhận 429/503 retryable.
- Dùng cache key có model/version/tenant/filter fingerprint; không cache raw confidential payload.

### Resource lifecycle

- Startup chỉ validate config, schema, provider key presence và artifact manifest.
- Readiness fail nếu required artifact không có checksum hợp lệ.
- Shutdown đóng HTTP client, DuckDB read-only connection và database pool.
- Không tạo key/token ngẫu nhiên trong filesystem ephemeral.
- Không chạy subprocess hoặc daemon worker trong web process.
- Không nhận upload trực tiếp vào Render filesystem; upload signed URL tới object storage, sau đó ghi metadata/job vào Neon.

## Routing, iframe, streaming và timeout

Frontend hiện có bốn iframe trong portal/static/index.html. Vì Vercel static và Render backend khác origin:

- Ưu tiên Vercel rewrite các API/agent route về một Gateway public origin để giữ same-origin browser behavior.
- Nếu iframe trỏ trực tiếp sang service khác, phải sửa CSP frame-src, frame-ancestors, Origin guard, cookie domain và CORS; không dùng wildcard.
- Không proxy upload/import dài qua Vercel rewrite.
- Current frontend dùng JSON fetch, chưa có SSE/WebSocket streaming contract cho Agent 4. Giữ response JSON bounded trong slice.
- Các operation dài phải trả job_id và để frontend poll; không chờ một HTTP request quá 90 giây.
- Agent 4 query budget: đặt hard timeout ứng dụng nhỏ hơn 90 giây, tổng gateway/Vercel budget nhỏ hơn 120 giây.
- Agent 1/2/3 heavy jobs phải chạy local/paid worker; cloud route chỉ trả trạng thái và artifact URI sau khi có auth.

## Security boundary

Không dùng create_demo_app, X-Demo-Persona hoặc shared demo identity trong production slice.

Gateway phải:

- Xác minh user/session/tenant và tạo server-owned policy.
- Không trả Agent 1 bearer key cho browser.
- Dùng service credential riêng cho Neon/object storage/provider.
- Allow-list đúng Vercel production/preview origins.
- Dùng Secure/HttpOnly/SameSite cookie nếu cookie session được giữ.
- Có CSRF protection cho mutation.
- Không log API key, Authorization header, raw financial document hoặc prompt nhạy cảm.
- Gắn correlation ID và audit actor/tenant vào request.
- Rate-limit query/upload/job endpoints.

## Phạm vi không được giả định tương thích free-tier

| Chức năng | Kết luận |
|---|---|
| Agent 1 forecast với torch/Chronos và training/adaptation | Không chứng minh được trên 0.1 CPU/512 MB; giữ local/paid worker |
| Agent 2 HE4/Concrete/Windows DPAPI/WSL | Không tương thích Render Free Linux theo evidence hiện tại; loại khỏi cloud slice |
| Agent 2 batch encrypted training và nhiều SQLite stores | Không chạy đồng bộ trong free web process; cần worker/paid service |
| Agent 3 OCR/lawbase full corpus, local reranker và law sync | Không phù hợp filesystem/RAM/CPU free; giữ artifact immutable hoặc paid worker |
| Agent 4 full 2.3 GB warehouse | Không đặt trên Render Free/Neon DB; chỉ dùng small read-only slice hoặc external warehouse |
| Portal local JSON/session/intake files | Không dùng làm durable source of truth trên Render |
| Full multi-tenant production finance | NO-GO cho free tier cho đến khi auth, tenant isolation, persistence và backup hoàn chỉnh |

## Tiêu chí chuyển từ hybrid sang full cloud

Chỉ reconsider full cloud khi:

- Một clean container chứa target modules và dependency lock chạy được.
- P95 peak RSS của workload đồng thời có margin ít nhất 20% dưới 512 MB.
- Agent 1-3 được benchmark bằng production-like fixtures, không chỉ import.
- Không còn local mutable source of truth trong request path.
- Migrations và rollback Neon đã diễn tập.
- Heavy jobs có worker/queue tier phù hợp.
- Auth/tenant/audit regression pass.
- Chi phí/quota không phụ thuộc vào giả định Free service luôn thức hoặc private network miễn phí.
