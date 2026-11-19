# Đánh giá feasibility cloud — Phase 0

Ngày đánh giá: 2026-11-19
Phạm vi: repository hiện tại và kiến trúc Vercel + Render Free + Neon Free + external AI APIs.
Trạng thái: chỉ đánh giá và lập kế hoạch; chưa refactor runtime, chưa migrate dữ liệu, chưa thay đổi business logic/UI.

## Quyết định hiện tại

### Full application: NO-GO trên đúng free tier đã nêu

Không có bằng chứng đủ để triển khai đồng thời Portal và toàn bộ bốn agent lên Render Free. Các phép đo hiện có cho thấy:

- Import của bốn agent tiêu thụ tổng cộng khoảng 503.7 MiB RSS, trước khi cộng Portal, request workload, database client, provider SDK, allocator overhead và logging.
- Cộng import Portal, tổng quan sát được khoảng 531.4 MiB. Đây không phải phép đo một process hợp nhất, nhưng là cảnh báo rõ ràng rằng modular monolith đầy đủ vượt margin 512 MB.
- Bốn Render Free web services chạy 24/7 sẽ cần khoảng 2,880 instance-hours/tháng, cao hơn 750 giờ/workspace/tháng, chưa tính deploy preview hoặc restart.
- Portal hiện spawn các agent, dùng localhost, session/file state cục bộ và không có health endpoint công khai phù hợp.
- Agent 1 có forecast stack chứa torch/Chronos/transformers; Agent 2 phụ thuộc đường chạy HE4/Concrete/DPAPI/Windows; Agent 3 có law corpus khoảng 251 MiB và SQLite; Agent 4 dùng DuckDB/local artifact. Chưa có cloud adapter cho PostgreSQL/object storage.
- Query thật của Agent 4 với smoke warehouse và mock provider đã timeout ở mốc 20 giây trong thử nghiệm; do đó chưa được coi là đạt latency hoặc functional gate.

Kết luận này là NO-GO có bằng chứng cho full application, không phải lệnh xóa hoặc vô hiệu hóa các đường chạy local.

### Agent 4 vertical slice: CONDITIONAL GO

Một slice nhỏ có thể được đánh giá tiếp trên một Render Free service nếu đáp ứng toàn bộ gate trong tài liệu này:

- Portal static được deploy trên Vercel.
- Một Gateway/Agent 4 process duy nhất, không spawn subprocess và không dùng demo persona.
- Query dùng claims/policy do server xác thực, một warehouse nhỏ immutable và external providers có timeout.
- Neon chỉ giữ control-plane metadata, audit/job state và bounded vector data; raw corpus/warehouse/report lưu object storage.
- Render filesystem chỉ là scratch cache có thể mất; không được là source of truth.
- Agent 1 forecast, Agent 2 HE4 và Agent 3 full law/OCR không thuộc slice này.

## Provider constraints đã kiểm tra

Các giới hạn dưới đây được đối chiếu với tài liệu nhà cung cấp vào ngày đánh giá:

| Provider | Giới hạn/đặc tính | Hệ quả |
|---|---|---|
| Render Free | 512 MB RAM, 0.1 CPU; 750 Free instance-hours/workspace/tháng; spin down sau 15 phút idle; filesystem ephemeral; không có persistent disk; không scale quá một instance; Free web service không nhận private network traffic | Không chạy bốn service 24/7; không dùng SQLite/DuckDB/local upload làm dữ liệu bền vững; cold start và CPU phải nằm trong budget. Xem [Render Free](https://render.com/docs/free), [compute plans](https://render.com/docs/compute-plans), [web services](https://render.com/docs/web-services). |
| Vercel Hobby | Static file upload limit 100 MB; proxy request timeout tối đa 120 giây; external rewrites được cấu hình qua vercel.json | Portal static hiện khoảng 10.06 MiB, nên phù hợp về kích thước; query dài không được phụ thuộc vào proxy sync. Xem [Vercel limits](https://vercel.com/docs/limits), [rewrites](https://vercel.com/docs/routing/rewrites). |
| Neon Free | 1 GB storage/project, 100 CU-hours/project/tháng, tối đa 2 CU/8 GB, scale-to-zero sau 5 phút, 5 GB public transfer/project/tháng, private network transfer không có trên Free | Chỉ lưu control plane và metadata bounded; phải dùng pooled connection và budget query. Xem [Neon plans](https://neon.com/docs/introduction/plans), [pooling](https://neon.com/docs/connect/connection-pooling). |
| Neon pgvector | pgvector có trên mọi plan; extension tạo bằng CREATE EXTENSION IF NOT EXISTS vector | Có thể dùng cho embedding có giới hạn, nhưng không nhét toàn bộ legal corpus/warehouse vào 1 GB. Xem [Neon pgvector](https://neon.com/docs/extensions/pgvector). |
| Cloudflare R2 | Free allowance gồm 10 GB-month storage, 1M Class A và 10M Class B operations/tháng; egress miễn phí theo pricing hiện hành | Có thể là adapter object storage thử nghiệm, nhưng retention, số lần đọc và multipart upload phải được budget. Xem [R2 pricing](https://developers.cloudflare.com/r2/pricing/). |

Render Free được xem là preview/conditional tier trong kế hoạch này, không phải durability hoặc availability tier production. Neon/R2 có thể giữ dữ liệu bền hơn, nhưng không thay thế yêu cầu backup, retention, access policy và restore rehearsal.

## Bằng chứng repository và benchmark

### Bảng evidence

| Khu vực | Evidence thực tế | Phân loại | Ý nghĩa deployment |
|---|---|---:|---|
| Portal | portal/server.py mặc định bind 127.0.0.1, tạo URL/port agent 8011/8766/8640/8040, spawn subprocess khi start-all, ghi workspace/log/session JSON/JSONL cục bộ | BLOCKER | Cần cloud mode riêng, bind theo PORT, không spawn agent, persistence adapter và health/readiness |
| Portal frontend | portal/static có 24 file, khoảng 10.06 MiB; app.js dùng relative fetch; index có iframe cho agent; chưa có vercel.json/API proxy | HIGH | Static Vercel khả thi về kích thước nhưng cần rewrite/base URL/CSP/iframe contract |
| Agent 1 | Import max RSS 226,440 KB; startup attempt max RSS 229,368 KB; forecast requirements chứa torch/Chronos/transformers | BLOCKER | Không cài forecast stack trong Free web image nếu chưa có benchmark; ingest cần tách khỏi forecast |
| Agent 2 | Import max RSS 153,172 KB; server mặc định 127.0.0.1; requirements.txt thiếu cryptography dù source import trực tiếp; HE4/Concrete/DPAPI/Windows assumptions | BLOCKER | HE4 không được giả định chạy Linux Free; portable path phải được đánh giá riêng |
| Agent 3 | Import max RSS 62,804 KB; startup attempt 80,916 KB; SQLite foundation; startup warm-up; 262,942,720-byte corpus, 882 documents, 27,729 chunks, 54,482 provisions | HIGH | Không lưu corpus/workspace trên Render; cần external object storage và lazy init |
| Agent 4 | Import max RSS 73,392 KB; startup attempt 77,140 KB; có /healthz và /health; DuckDB/local warehouse; external selection config | HIGH | Đây là ứng viên slice, nhưng query, artifact lifecycle và production auth chưa được chứng minh |
| Persistence | Không có DATABASE_URL, PostgreSQL driver production, migration PostgreSQL, CREATE EXTENSION hoặc pgvector trong source; state phân tán ở SQLite, DuckDB, JSON/JSONL | BLOCKER | Neon chưa thể là backend persistence hiện tại |
| Secrets | agent3/.env có non-empty API key values; Portal có generated agent tokens và Agent 1 key endpoint; values không được đưa vào tài liệu này | BLOCKER | Cần secret rotation/audit, server-only secret handling và loại bỏ browser key exposure |
| Dependency matrix | Không có unified production environment; cross-import lần lượt fail vì thiếu cryptography, finance_input, lxml, duckdb, pandas, anyio, fastapi tùy venv; pip check không chạy vì các venv không có pip module | BLOCKER | Cần clean lock/build matrix trước khi hợp nhất |

### Kết quả phép đo hiện có

Các số dưới đây là phép đo import/startup trong venv hiện có, không phải cam kết hiệu năng production:

| Process | Import RSS max | Startup RSS max | Startup result |
|---|---:|---:|---|
| Portal | 28,356 KB | chưa có server benchmark riêng | import thành công |
| Agent 1 | 226,440 KB | 229,368 KB | app khởi tạo; socket bind bị sandbox chặn |
| Agent 2 | 153,172 KB | 155,148 KB | server khởi tạo; socket bind bị sandbox chặn |
| Agent 3 | 62,804 KB | 80,916 KB | app khởi tạo; socket bind bị sandbox chặn |
| Agent 4 | 73,392 KB | 77,140 KB | app khởi tạo; socket bind bị sandbox chặn |

Tổng import bốn agent là 515,808 KB, xấp xỉ 503.7 MiB. Cộng Portal là 544,164 KB, xấp xỉ 531.4 MiB. Phép cộng này không chứng minh một process sẽ giữ đúng tổng đó, nhưng không được dùng để tuyên bố fit 512 MB; nó chỉ cho thấy cần benchmark process thực tế và phải có margin.

Agent 4 ASGI health smoke đã trả:

- /healthz: HTTP 200, {"status":"live"}.
- /health: HTTP 200, {"status":"ok","demo_mode":false}.
- elapsed khoảng 0.38 giây, max RSS 75,168 KB.
- test_remote_metric_selection.py: 23 test passed.
- Query với smoke warehouse và mock provider timeout sau 20 giây; query chưa đạt gate.

Portal security test đã có 56 passed và 5 errors do fixture mở socket bị sandbox môi trường đánh giá chặn; đây không phải bằng chứng app pass hoàn toàn. Một số test chọn lọc của Agent 1 và Agent 3 timeout; Agent 2 venv chưa có pytest. Full suite chưa chạy.

Server bind benchmark bị giới hạn bởi sandbox (PermissionError/could not bind), vì vậy startup RSS ở trên là evidence khởi tạo chứ không phải HTTP-serving benchmark hoàn chỉnh.

## Baseline chức năng cần khóa trước migration

Mỗi baseline phải chạy từ clean checkout, fixture fingerprint và dependency lock đã ghi nhận. Không dùng external API key thật trong test.

| Component | Baseline bắt buộc | Regression evidence |
|---|---|---|
| Portal | Static asset matrix; state/session/auth; bank intake; agent health proxy; iframe render; Agent 1 key không lộ cho browser | Portal test suites hiện có, asset 404 scan, security header scan |
| Agent 1 | Health; intake validation; reconciliation; idempotency; access control; no-PII logs | Golden input/output + DB row/hash counts |
| Agent 2 | Portal auth; snapshot/review; case queue; remediation; replay integrity | Portable Linux path và HE4 path tách biệt; không mock HE4 để coi là pass |
| Agent 3 | /api/schema; XML/bank ingestion; workspace artifacts; citations/source hashes; law retrieval | Golden fixtures, corpus manifest/hash, provider failure tests |
| Agent 4 | /healthz, /health; catalog/metrics; governed query; policy denial; tenant isolation; provider timeout/fallback | Golden query output từ immutable smoke warehouse; query latency/RSS |
| Cross-cutting | Secrets không xuất hiện trong response/log/build; CORS allowlist; CSRF/cookie; restart recovery; idempotent retries | Dynamic security scan, log scan, restart/restore rehearsal |

Baseline hiện tại chưa đủ để gọi full application regression-ready vì full suite chưa chạy và một số test bị timeout hoặc thiếu dependency.

## Minimal Agent 4 vertical slice

### Phạm vi

1. Vercel phục vụ portal/static và chỉ rewrite các route API ngắn tới một Gateway backend.
2. Gateway và Agent 4 chạy trong một process/container nhỏ, không dùng --start-all, không spawn Agent 1-3.
3. GET /healthz là liveness không auth; /readyz kiểm tra config/provider/database theo timeout ngắn.
4. Query nhận identity đã xác thực ở server boundary; claims và server policy không lấy từ X-Demo-Persona hoặc input browser.
5. Warehouse là artifact nhỏ, immutable, versioned và có SHA-256 manifest.
6. LLM/embedding/reranking là external API với timeout, retry có giới hạn, concurrency semaphore và lexical fallback khi phù hợp.
7. Neon giữ tenant/policy/audit/job/artifact metadata và vector table bounded; object storage giữ raw artifact/report/warehouse.
8. Không upload raw files vào Render local disk, không dùng local SQLite/DuckDB làm source of truth, không cài torch/transformers/Concrete trong image.

### Không thuộc slice

- Agent 1 forecast/training.
- Agent 2 HE4/Concrete/DPAPI.
- Agent 3 full lawbase/OCR/sync.
- Demo persona, browser-facing agent bearer keys, direct public agent URLs.
- Synchronous query vượt request timeout; công việc dài phải chuyển job/poll hoặc background tier khác.

### Điều kiện chấp nhận slice

- Production mode từ chối request thiếu claims/policy bằng 401/403 trước model/retrieval/SQL.
- /healthz không khởi tạo model nặng và không phụ thuộc provider.
- Query golden output khớp local fixture.
- Peak RSS dưới gate 400 MiB trong ba cold runs và concurrency test.
- Không mất durable state sau restart; restore được artifact theo manifest.
- CORS/iframe/CSP chạy trên Vercel preview và production allowlist.

## So sánh kiến trúc

| Phương án | Ưu điểm | Rủi ro/chi phí | Đánh giá trên free tier |
|---|---|---|---|
| Modular monolith đầy đủ | Giảm network hop; giữ shared contracts; đơn giản hóa deploy | Import/dependency và runtime memory cộng dồn; Portal hiện còn subprocess/local state; một process lỗi ảnh hưởng mọi agent | NO-GO hiện tại cho full app; là hướng đúng cho Gateway + Agent 4 slice |
| Bốn agent deployments riêng | Cô lập failure và dependency; scale độc lập | Vượt 750 instance-hours nếu chạy thường trực; mỗi service vẫn cần bind/auth/persistence; Agent 1/2/3 có blocker riêng | NO-GO trên Render Free |
| Hybrid | Vercel static + Render bounded Gateway/Agent 4 + Neon/R2; agents nặng local/paid | Có hai operational domains; phải giữ capability matrix và đồng bộ contract | RECOMMENDED cho Phase 0/preview |

## GO/NO-GO gates

Thiếu evidence được tính là FAIL/OPEN, không được mặc định PASS.

| Gate | Điều kiện GO | Trạng thái hiện tại |
|---|---|---|
| G0 — Release hygiene | Không có secret value trong Git/build/log; rotation hoàn tất; clean working tree hoặc artifact provenance rõ | NO-GO: .env có key values và working tree dirty |
| G1 — Dependency | Clean image cài frozen lock; import Gateway + Agent 4; pip check/tương đương pass | NO-GO: cross-venv import thiếu package; chưa có unified lock |
| G2 — Memory | Three cold runs, concurrency 1/5/10, peak RSS < 400 MiB; không OOM | OPEN/NO-GO: mới có import/startup evidence; tổng import vượt 512 MB |
| G3 — Startup/health | Bind 0.0.0.0:$PORT; health p95 < 250 ms; readiness timeout bounded; graceful shutdown | OPEN: sandbox chặn bind, chưa có Render smoke |
| G4 — Query | Golden output đúng; p95 < 60 s; hard timeout < 90 s; provider failure bounded | NO-GO: query thử nghiệm timeout 20 s |
| G5 — Durability | Restart không mất source of truth; Neon/object restore rehearsal; Render disk chỉ scratch | NO-GO: source hiện vẫn SQLite/DuckDB/JSON local |
| G6 — Security | Auth/policy/tenant isolation; no demo mode; no browser secret; CORS exact allowlist; CSRF/cookie tests | NO-GO: Agent 1 key endpoint/browser exposure và demo/local assumptions còn tồn tại |
| G7 — Functional regression | Tất cả golden baselines của capability được chọn pass; full-app exclusions được ghi rõ | OPEN: selected tests timeout/thiếu pytest; full suite chưa chạy |
| G8 — Quota/storage | Render hours, Neon 1 GB/CU/transfer, object retention đều dưới budget có margin | OPEN: chưa có production traffic profile |
| G9 — Rollback | Vercel rollback, Render image rollback, Neon additive migration/branch restore, object retention tested | OPEN: chưa có migration/restore rehearsal |

## Explicit stop conditions

Phải dừng full migration và giữ local/hybrid nếu xảy ra một trong các điều sau:

1. Peak RSS vượt 400 MiB hoặc OOM ở workload target.
2. Query cần hơn 90 giây hoặc không kiểm soát được provider retry/concurrency.
3. Cần local filesystem, SQLite/DuckDB mutable hoặc process-local session để giữ dữ liệu sau restart.
4. Không chứng minh được PostgreSQL migration counts/hashes và tenant isolation.
5. Agent 2 HE4 cần Windows/DPAPI/WSL hoặc runtime vượt free tier.
6. Agent 1 forecast cần torch/model footprint hoặc CPU vượt budget.
7. Agent 3 corpus/OCR/law sync vượt storage, CPU, memory, licensing hoặc request budget.
8. Auth/CORS/iframe regression chưa pass hoặc secret xuất hiện trong browser/log/image.
9. Free quota không đủ cho uptime, traffic và rollback rehearsal.

## Kết luận và thứ tự quyết định

1. Quyết định hiện tại: không deploy full application lên Render Free.
2. Duy trì local deployment làm baseline; không xóa database hoặc local artifacts.
3. Ưu tiên chứng minh Agent 4 vertical slice theo CM-000 đến CM-031 trong roadmap.
4. Chỉ sau khi G0-G9 pass mới xem xét mở rộng Agent 1/3; Agent 2 HE4 cần runtime/owner riêng.
5. Nếu bất kỳ gate nào vẫn FAIL, phát hành hybrid hoặc nâng tier; không gọi đó là full cloud migration.

## Phase 1 implementation evidence — query diagnosis

Ngày đo: 2026-11-19
Issue: CM-002 / phần chẩn đoán timeout trước CM-011.

### Root cause đã xác nhận

Query deterministic với smoke warehouse bị treo ở đường chạy cũ sau khi gọi execute_safe_sql qua asyncio.to_thread. Gọi cùng hàm DuckDB đồng bộ hoàn tất khoảng 32 ms, nhưng Future của worker không hoàn tất trong runtime Python 3.12 + DuckDB 2.0.0 hiện tại; request không đi tiếp tới result validation hoặc answer generation. Đây là lỗi lifecycle/threading của đường DuckDB, không phải lý do để tăng timeout.

Đã sửa theo hướng nhỏ nhất:

- SQL DuckDB read-only chạy đồng bộ trong event loop, có DuckDB interrupt timer và query deadline hiện hữu.
- Đọc warehouse watermark cũng không còn đi qua thread worker.
- Retrieval có synchronous provider/index path trong free slice; không tạo thêm thread pool cho NumPy/httpx stack.
- Bổ sung trace stage/status/error chỉ ghi code, stage, retryable và type; không ghi SQL, rows, prompt hoặc credentials.
- Giữ public selection result contract cũ; breakdown chi tiết chỉ xuất hiện trong PipelineTrace/structured observability.

### Evidence sau sửa

Command:

    ./.venv/bin/python scripts/benchmark_cloud_query.py --provider-mode deterministic --output /tmp/agent4-phase1-query.json

Kết quả trên smoke warehouse 24,391,680 bytes:

| Metric | Kết quả |
|---|---:|
| Query | Doanh thu thuần tháng 08/2026? |
| Status | ready |
| Row count | 1 |
| End-to-end elapsed | 37.751 ms |
| Peak process RSS | 114,820 KB, xấp xỉ 112.1 MiB |
| SQL execution | 28.782 ms |
| Metric selection | 2.577 ms |
| Planning | 3.656 ms |
| Result validation | 0.043 ms |
| Answer generation/validation | 0.334 ms |
| Stage errors | none |

Selection breakdown hiện ghi nhận được gồm llm_metric_selection, dense_index, embedding, dense_retrieval, lexical_retrieval và reranking khi chạy hybrid config. Run deterministic ở trên dùng full_catalog + hashing/mock để cô lập application/DuckDB path; chưa phải bằng chứng latency của external provider.

### Test evidence

- test_cloud_pipeline_trace.py, test_metric_selection_recovery.py và test_cache_governance.py: 40 passed.
- Regression cache test trước đó bị treo vì retrieval worker; sau khi bỏ thread path chạy xong trong giới hạn 30 giây.
- Query response khớp governed pipeline: ready, một dòng, không có error.

### Gate update

- G2 memory: đạt sơ bộ cho deterministic slice với 112.1 MiB process peak; chưa phải container benchmark dưới giới hạn CPU/RAM Render.
- G4 query: đạt cho local deterministic path; external embedding/LLM latency và failure budget vẫn OPEN.
- G7 functional: đạt các test subset trên; full suite và golden external-provider regression vẫn OPEN.
- G3/G5/G6/G8/G9: chưa thay đổi; deployment foundation, Neon persistence, auth/CORS, quota và rollback vẫn OPEN.
