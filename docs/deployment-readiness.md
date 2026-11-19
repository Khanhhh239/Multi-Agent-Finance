# Báo cáo audit sẵn sàng triển khai

Ngày audit: 2026-11-19
Phạm vi: toàn bộ repository Multi-Agent-Fin, với kiến trúc mục tiêu Vercel + Render + Neon PostgreSQL + các API LLM/embedding/reranking bên ngoài.

## Kết luận điều hành

Repository hiện chưa sẵn sàng deploy production theo kiến trúc đề xuất. Blocker lớn nhất là kiến trúc đích và kiến trúc hiện tại chưa khớp:

- Mã hiện tại dùng Portal Python làm shell/orchestrator, tự khởi động bốn agent con trên cùng máy.
- Dữ liệu nghiệp vụ đang dùng SQLite, DuckDB và file JSON/JSONL; chưa có PostgreSQL driver, schema PostgreSQL, migration PostgreSQL hay DATABASE_URL.
- Portal và Agent 2/3 mặc định chỉ bind loopback; Portal tạo URL localhost và CORS/Origin chỉ cho localhost.
- Vercel chưa có frontend build/deploy configuration. Frontend hiện là static vanilla JS gọi API bằng URL tương đối.
- Có state, key, database, legal corpus và workspace nằm trên filesystem local. Filesystem ephemeral hoặc không shared của Render không phù hợp làm persistent source of truth.
- Đang có file .env chứa giá trị không rỗng trong working tree của Agent 3 và Agent 4. Báo cáo này không ghi lại giá trị đó.

Có thể deploy sau khi tách service, chuyển persistent state sang dịch vụ bền vững/object storage, chuẩn hóa secret/config, thay loopback bằng private service URLs, bổ sung health checks và quyết định rõ phạm vi migration sang Neon. Với code hiện tại, không nên bấm deploy production.

## 1. Kiến trúc hiện tại

| Thành phần | Evidence hiện tại | Cách chạy hiện tại | Trạng thái với kiến trúc mục tiêu |
|---|---|---|---|
| Portal | portal/server.py, portal/static | Python stdlib HTTP server ở cổng 8800; có thể tự spawn Agent 1-4 | Không tương thích trực tiếp với Vercel; cần thành API gateway/backend riêng |
| Agent 1 | agent1/agent1_service/main.py | FastAPI/Uvicorn, mặc định cổng 8011 qua Portal; có SQLite, state và encryption keys | Có Dockerfile; cần persistent storage/secret management và service URL |
| Agent 2 | agent2/sme_fraud/review_server.py | HTTP server stdlib, mặc định cổng 8766, loopback-only; SQLite runtime | Cần sửa network/auth và dependency manifest; không nên spawn cùng Portal |
| Agent 3 | agent3/agent3_tax_compliance/src/assistant/web.py | FastAPI/Uvicorn, mặc định cổng 8640, loopback-only; SQLite và legal corpus | Có thể chạy Render riêng sau khi externalize data và config |
| Agent 4 | agent4/agent4/api.py | FastAPI/Uvicorn, cổng 8040 qua Portal; DuckDB và external APIs | Có /healthz và /health; demo app hiện vẫn phụ thuộc DB file |
| Frontend Portal | portal/static/index.html, portal/static/app.js | Static assets, không có package.json/build pipeline | Có thể host static trên Vercel nhưng phải cấu hình API routing/base URL |
| UI Agent 3 | agent3/agent3_tax_compliance/webui | Vite, build vào agent3/.../src/assistant/static | Là frontend con được build vào Agent 3, không phải frontend Portal |
| Database | agent3 migrations, data_pipeline, Agent 1/2/4 stores | SQLite/DuckDB/file JSON; migration chủ yếu SQLite | Neon chưa được nối vào code |
| API providers | agent3/.env.example, agent4 config | LLM/embedding/reranking qua HTTP provider bên ngoài | Phù hợp về hướng, nhưng cần secret injection, timeout/retry/quota/observability |

Tài liệu vận hành hiện tại cũng xác nhận mô hình một server local: docs/DEPLOY_SERVER.md nêu các cổng 8800, 8011, 8766, 8640, 8040 và các thư mục state/local database. README.md và HUONG_DAN_CHAY_WEB.md hướng dẫn chạy run_web.ps1, mở 127.0.0.1:8800 và khởi động toàn bộ agent cùng máy.

## 2. Phân loại phát hiện

### BLOCKER

| Mã | Phát hiện và evidence | Tác động |
|---|---|---|
| B-01 | Neon không được sử dụng trong code. Không có DATABASE_URL, psycopg/asyncpg/SQLAlchemy PostgreSQL, PostgreSQL migrations hay CREATE EXTENSION. Agent 3 dùng SQLite tại src/config.py và persistence/repository.py; Agent 4 dùng DuckDB; pipeline tạo warehouse DuckDB. | Deploy Neon hiện không làm ứng dụng dùng Neon; dữ liệu production sẽ không có nơi lưu đúng kiến trúc đề xuất. |
| B-02 | portal/server.py đặt HOST = 127.0.0.1, tạo ORIGIN http://127.0.0.1:port và ORIGINS chỉ gồm localhost. agent2/review_server.py bind 127.0.0.1; Agent 3 direct main cũng bind 127.0.0.1. | Render routing/private networking không truy cập được service nếu không sửa bind và service URLs. |
| B-03 | Portal tự spawn Agent 1-4 với command, cổng và environment local trong portal/server.py; agent_url() luôn tạo http://HOST:port. | Một Render web service không phải mô hình process supervisor cho bốn service độc lập; restart/scale sẽ sai và không có service discovery. |
| B-04 | Portal không có unauthenticated /health hoặc /healthz. Health hiện tại là /api/state và route này nằm sau Origin/platform/auth guards. | Render không có health endpoint đơn giản để đánh giá instance sống; deploy có thể bị đánh dấu unhealthy hoặc health check phải dùng endpoint nghiệp vụ. |
| B-05 | Persistent state ở local filesystem: Portal workspace/pending/logs/security/audit/batches, Agent 1 SQLite và key directory, Agent 2 SQLite, Agent 3 SQLite/workspaces/legal corpus, Agent 4 DuckDB. | Filesystem ephemeral hoặc không shared giữa instance; mất state khi redeploy/scale, không đảm bảo backup/rollback. |
| B-06 | Agent 2 yêu cầu loopback Portal URL trong sme_fraud/portal_auth.py và chỉ chấp nhận 127.0.0.1/localhost; Portal bridge secret được tạo random mỗi process. | Không thể tách Agent 2 thành Render service với URL private mà không sửa trust model; token có thể đổi sau restart. |
| B-07 | Portal chỉ có shared intake password + FaceID/session local, không có IdP, user identity hoặc role/tenant model đầy đủ. portal/server.py dùng session in-memory/persisted local và một file security. | Chưa đủ cơ sở cho production auth, multi-user, audit attribution và multi-tenant finance data. |
| B-08 | Vercel chưa có vercel.json, package.json hoặc build config cho Portal. app.js gọi fetch bằng path tương đối và mọi API route giả định cùng origin. | Deploy static lên Vercel sẽ không tự gọi được Render API; auth/session/CORS/proxy chưa được xác định. |
| B-09 | Agent 3 và Agent 4 hiện có .env với các API key/token không rỗng trong working tree. Giá trị không được ghi vào báo cáo này. | Cần rotate ngay nếu file từng commit, từng upload hoặc từng chia sẻ; production phải dùng secret manager, không dùng file .env trong image. |
| B-10 | Agent 4 demo app yêu cầu AGENT4_LLM_API_KEY, AGENT4_EMBED_API_KEY và dùng demo identity/X-Demo-Persona khi thiếu claims/policy. api.py tạo demo app với DB file local. | Có nguy cơ deploy nhầm demo mode thành production, rò quyền truy cập và dùng dữ liệu synthetic/DB path không tồn tại. |

### HIGH

| Mã | Phát hiện và evidence | Tác động |
|---|---|---|
| H-01 | portal/config.example.json và config.local.json chứa port local, workspace local, provider settings và các đường dẫn runtime. portal/server.py ưu tiên config.local.json nếu tồn tại. | Dễ đóng gói nhầm local config hoặc khởi chạy production với cấu hình demo/local. |
| H-02 | Portal endpoint /api/agents/agent1/key trả agent1_key() cho browser sau guard auth/biometric không đầy đủ. | Bearer key backend có thể xuất hiện ở client; cần bỏ endpoint hoặc đổi thành server-to-server operation. |
| H-03 | CSP của Portal có frame-src http://127.0.0.1:* và http://localhost:*; Origin guard và frontend FaceID có redirect localhost. | Frontend Vercel/Render HTTPS sẽ bị CSP/Origin/redirect chặn hoặc rơi về địa chỉ local. |
| H-04 | Agent 4 API không có CORS middleware và các service khác không có cấu hình public/private rõ ràng. | Browser gọi cross-origin từ Vercel sẽ thất bại hoặc buộc mở CORS quá rộng; cần chỉ allow đúng Vercel origin và credentials policy. |
| H-05 | Tokens nội bộ AGENT2_TOKEN, AGENT3_TOKEN, AGENT4_TOKEN được tạo bằng secrets.token_urlsafe mỗi lần Portal khởi động, sau đó truyền sang child process. | Không ổn định qua restart/scale, không thể chia sẻ giữa instance; cần secret cố định/managed hoặc signed service auth. |
| H-06 | Agent 2 requirements.txt không khai báo cryptography dù batch_training_api.py và comparison store import cryptography. setup_env.sh cài thêm ngoài manifest. | Build sạch theo requirements.txt có thể fail lúc import/runtime; manifest và lock không phản ánh dependency thực. |
| H-07 | Portal không có requirements riêng; nó import các module nội bộ của Agent 1/2 và optional cryptography. Startup phụ thuộc nhiều virtualenv và working directory. | Native Render build khó tái lập; cần Docker hoặc một dependency manifest/image thống nhất. |
| H-08 | Agent 3 legal corpus khoảng 263 MB trong data và docs vận hành nói Agent 4 warehouse đầy đủ khoảng 2.3 GB; Portal workspace hiện khoảng 47 MB. | Build size, memory, cold start, deploy time và ephemeral disk vượt giả định web service nhỏ; phải dùng object storage/volume/external database hoặc build artifact rõ ràng. |
| H-09 | Không có migration/seed PostgreSQL. Các migration 001-010 của Agent 3 dùng SQLite-specific schema/PRAGMA; data_pipeline/setup_runtime.py tạo dữ liệu/warehouse local. | Không có quy trình init Neon, versioning schema, seed production-safe hoặc rollback migration. |
| H-10 | Portal import timeout hardcode 600 giây; Agent 4 HTTP/LLM timeout mặc định 180 giây; có xử lý upload file vào local pending. | Request dễ vượt timeout của proxy/platform, giữ worker lâu và gây memory/disk pressure; cần background job/object storage. |
| H-11 | HE4/HE path của Agent 2 phụ thuộc Windows DPAPI/WSL/executable và tài liệu có absolute path kiểu /home/sang. | Không chạy trên Render Linux managed runtime nếu không tách thành worker/service được hỗ trợ hoặc loại khỏi production scope. |
| H-12 | Runtime smoke import hiện pass trong các virtualenv hiện có, nhưng chưa có clean build/test trên image deploy và chưa có end-to-end qua Vercel/Render/private network. | Kết quả local không chứng minh build reproducibility hoặc routing production. |

### MEDIUM

| Mã | Phát hiện và evidence | Tác động |
|---|---|---|
| M-01 | run_web.ps1 kill các cổng 8800/8011/8766/8640/8040, tạo/mở nhiều venv và mở browser 127.0.0.1. | Chỉ là launcher local, không dùng làm Render start command. |
| M-02 | Agent 3 web UI dùng Vite proxy /api đến 127.0.0.1:8640 và build output vào source static; Portal frontend lại là raw static riêng. | Có hai frontend flow và hai API topology; dễ build nhầm artifact hoặc trỏ nhầm backend. |
| M-03 | Agent 4 có cả pyproject.toml, requirements.txt và uv.lock; requirements có dependency rộng/unpinned tương đối so với lock. | Supply-chain/reproducibility và cold start khó dự đoán nếu Render không dùng lockfile đúng cách. |
| M-04 | Agent 3 import anyio nhưng không khai báo trực tiếp; có nhiều dependency runtime dùng theo transitive dependency. | Clean environment có thể thay đổi khi dependency upstream đổi; cần direct dependency audit. |
| M-05 | Mặc định Agent 4 AS_OF_DATE là ngày cố định 2026-10-14, last closed month là 2026-08; Agent 4 database defaults là data/*.duckdb. | Production có thể trả số liệu stale hoặc không tìm thấy file nếu không set explicit runtime config. |
| M-06 | Portal tạo WORK/PENDING/LOGS lúc import module và dùng các file JSON/JSONL làm state/audit. | Import failure do read-only filesystem hoặc race khi scale; audit durability chưa đảm bảo. |
| M-07 | Auth/session TTL 20 phút, session map in-memory và cookie/header custom; chưa có CSRF/session rotation/central session store được cấu hình cho cross-origin Vercel. | Có rủi ro logout ngẫu nhiên, replay, CSRF hoặc behavior khác giữa nhiều instance. |
| M-08 | Không thấy observability deployment hoàn chỉnh: metrics/logging chỉ ở Agent 4, Portal log_message bị no-op và chưa có error tracking/correlation ID chung. | Khó điều tra lỗi production, timeout provider và partial failure giữa agents. |

### LOW

| Mã | Phát hiện và evidence | Tác động |
|---|---|---|
| L-01 | README/docstrings còn hướng dẫn 127.0.0.1 và Windows PowerShell. | Tạo drift với runbook production, nhưng không phải runtime blocker sau khi thay config. |
| L-02 | Không có render.yaml, vercel.json, root Dockerfile, Procfile hoặc CI deployment pipeline. | Thiếu hạ tầng-as-code và reviewable deployment contract. |
| L-03 | Working tree đã dirty trước khi audit, gồm nhiều file modified/untracked. | Không nên release từ trạng thái hiện tại; cần chốt commit/tag sạch trước migration/deploy. |

## 3. Hardcoded URLs, ports, paths và development-only config

Các evidence chính:

- portal/server.py đặt HOST 127.0.0.1, cổng mặc định 8800, ORIGINS localhost và các agent ports 8011/8766/8640/8040.
- portal/server.py agent_url() ghép http://HOST:port; các launcher truyền --portal-url ORIGIN.
- agent2/sme_fraud/review_server.py bind 127.0.0.1 và portal_auth.py từ chối hostname ngoài localhost.
- agent3/.../src/assistant/web.py direct main bind 127.0.0.1:8640.
- agent3/webui/vite.config.js proxy API đến 127.0.0.1:8640.
- portal/static/app.js có redirect FaceID giữa 127.0.0.1 và localhost.
- portal/static/index.html và agent4_chat HTML dùng root-relative assets/API, không có API base runtime.
- Default paths gồm portal/workspace, data/workspaces, data/foundation/capture.sqlite3, data/lawbase/legal_corpus.sqlite3, data/cfo_warehouse.duckdb và data/cfo_ops.duckdb.
- Agent 2 HE4 integration có WSL/Windows assumptions; cần loại khỏi deployment target hoặc thiết kế runtime riêng.

Required change: mọi host/port/base URL/path phải lấy từ environment hoặc managed config; bind 0.0.0.0; dùng PORT do platform cấp; service-to-service URL phải là private URL; data path phải trỏ volume/object storage/database rõ ràng.

## 4. Environment variables và secret inventory

Danh sách dưới đây chỉ là tên biến. Không có giá trị bí mật trong báo cáo.

### Provider/API và Agent 3

AGENT3_LLM_API_KEY, AGENT3_LLM_PROVIDER, AGENT3_LLM_BASE_URL, AGENT3_LLM_MODEL, AGENT3_EMBED_API_KEY, AGENT3_EMBED_PROVIDER, AGENT3_EMBED_BASE_URL, AGENT3_EMBED_MODEL, AGENT3_RERANK_API_KEY, AGENT3_RERANK_PROVIDER, AGENT3_RERANK_URL, AGENT3_RERANK_MODEL, AGENT3_WORKSPACES, AGENT3_ADMIN_STORE, AGENT3_COMPANY_PROFILE_FILE, AGENT3_PORTAL_URL, AGENT3_PLATFORM_TOKEN, AGENT3_DEMO_COMPANY, AGENT3_PORT, AGENT3_OCR_PROFILE.

### Agent 4

AGENT4_DEMO_MODE, AGENT4_DEMO_TOKEN, AGENT4_LLM_API_KEY, AGENT4_LLM_PROVIDER, AGENT4_LLM_BASE_URL, AGENT4_LLM_MODEL, AGENT4_LLM_TEMPERATURE, AGENT4_LLM_NUM_CTX, AGENT4_LLM_THINK, AGENT4_LLM_TIMEOUT, AGENT4_EMBED_API_KEY, AGENT4_EMBED_PROVIDER, AGENT4_EMBED_BASE_URL, AGENT4_EMBED_MODEL, AGENT4_EMBED_DIMENSIONS, AGENT4_RETRIEVAL_MODE, AGENT4_SELECTION_CONFIG, AGENT4_METRIC_SELECTION_CONFIG, AGENT4_DB, AGENT4_DB_PATH, AGENT4_OPS_DB, AGENT4_GROUND_TRUTH, AGENT4_MAX_QUESTION_LENGTH, AGENT4_DEFAULT_ROW_CAP, AGENT4_QUERY_TIMEOUT_MS, AGENT4_REPORTING_DATA_WATERMARK, AGENT4_REPORTING_LAST_CLOSED_MONTH, AGENT4_AS_OF, AGENT4_LAST_CLOSED_MONTH, AGENT4_DATA_DIR, AGENT4_WAREHOUSE_TENANT_ID, AGENT4_PORT.

### Agent 1

AGENT1_THREADS, AGENT1_STATE_DIR, AGENT1_KEY_DIR, AGENT1_FIRM_ID, AGENT1_RESEARCH_MODE, AGENT1_COMPANY_PROFILE_FILE, AGENT1_DEMO_TRAINING, AGENT1_FRAME_ANCESTORS, AGENT1_REPORT_PASSWORD_FILE, AGENT1_REPORT_DIR, AGENT1_BANK_ACCOUNTS_FILE, AGENT1_PSEUDONYMIZE, AGENT1_AGENT4_TOKEN, AGENT1_VIEWER_TOKEN, AGENT1_TRAIN_SECONDS, AGENT1_TRAIN_MIB, AGENT1_NEURAL_MAX_ITER, AGENT1_T1_GLOBAL_CATALOG.

### Agent 2 và bridge/HE

AGENT2_WORKSPACE_DIR, AGENT2_BATCH_TRAINING_CONFIG, AGENT2_CASE_QUEUE_DB, AGENT2_REMEDIATION_DB, AGENT2_AUTH_FILE, AGENT2_PORTAL_URL, AGENT2_PORTAL_BRIDGE_SECRET, AGENT2_SNAPSHOT_DB, AGENT2_MODEL_DB, AGENT2_ANALYSIS_BINDINGS, AGENT2_HE_NODE_CONFIG, AGENT2_HE_BINDINGS, AGENT2_HE4_CONFIG, AGENT2_HE_PYTHON, AGENT2_WSL_DISTRO, AGENT2_HE_AGGREGATOR_URL, AGENT2_RELEASE_CONFIG, SOSOAT_FRAME_ANCESTORS, AGENT2_PORT.

### Portal/runtime và platform

MAF_PORTAL_CONFIG, PORT, HOST, PYTHONDONTWRITEBYTECODE, OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, DATABASE_URL.

DATABASE_URL hiện được liệt kê như biến đích cần bổ sung; repository chưa đọc biến này cho production database.

Secret finding: agent3/.env và agent4/.env đang có các API/token variables không rỗng. Cần kiểm tra git history, CI logs, container layers và mọi bản backup; nếu đã từng lộ thì rotate trước deploy. Không đưa .env vào image hoặc artifact.

## 5. Dependency và reproducibility audit

- Agent 1 có Dockerfile, requirements-service.txt và requirements-lock.txt nhưng Dockerfile chỉ mô tả Agent 1. Dockerfile dùng state volume /state và cổng nội bộ 8000, trong khi compose map host 8011.
- Agent 2 requirements.txt thiếu cryptography dù source import cryptography; setup_env.sh cài thêm ngoài manifest. Đây là HIGH.
- Agent 3 có requirements.txt nhưng không có lockfile Python; frontend có package.json và package-lock nên có thể dùng npm ci. Vite output được ghi vào source tree của backend.
- Agent 4 có pyproject.toml, requirements.txt và uv.lock; cần chọn một nguồn dependency duy nhất khi build.
- Portal không có requirements riêng và import code từ các agent; native build riêng sẽ không reproducible nếu không tạo image/manifest hợp nhất.
- Runtime import smoke trong các virtualenv hiện có đã pass cho agent1_service.main, sme_fraud.review_server, src.assistant.web và agent4.api. Đây chỉ là smoke trên môi trường hiện tại, chưa phải clean build.
- Cần chạy clean install/test trong image target, kiểm tra architecture wheel, timeout, package size và lockfile trước khi release.

## 6. Backend entry points, startup và health

| Service | Entry point hiện tại | Health hiện tại | Đánh giá deploy |
|---|---|---|---|
| Portal | python portal/server.py hoặc portal/server.py --start-all | Không có unauthenticated health; /api/state bị auth/Origin guard | BLOCKER; cần /healthz và không spawn child processes |
| Agent 1 | uvicorn agent1_service.main:app --host 0.0.0.0 --port 8000 trong agent1/Dockerfile | /health trả status nhưng pilot_ready false/forecast gate NO_GO | Có entry point, cần health semantics production và persistence |
| Agent 2 | python -m sme_fraud.review_server --port ... | /api/health; pipeline_ready false/release gate full_spec_not_approved | Health hiện mô tả readiness nghiệp vụ là chưa sẵn sàng; cần liveness/readiness tách biệt |
| Agent 3 | python -m src.assistant.web; default 127.0.0.1:8640 | Portal gọi /api/schema; src/app.py có /v1/health nhưng không phải entry point Portal dùng | Cần endpoint/version/health contract thống nhất |
| Agent 4 | uvicorn agent4.api:create_demo_app --factory --host ... --port ... | /healthz liveness; /health có status/DB metadata | Gần nhất với Render nhưng phải bỏ demo identity và file DB local |

Exact target startup contract sau remediation:

- Mỗi Render service bind 0.0.0.0 và đọc PORT.
- Chỉ Portal/Gateway public; Agent 1-4 private, hoặc chỉ expose qua gateway.
- Mỗi service có /healthz liveness không yêu cầu user auth và /readyz readiness kiểm tra dependency nhẹ.
- Render health check dùng /healthz; không dùng endpoint có database query nặng hoặc provider call.
- Portal không chạy subprocess; gọi agent bằng private service URLs và managed service credentials.

## 7. Frontend build và API base URL

Portal frontend hiện không có build step: portal/static/index.html, app.css, app.js và face-api/model assets được phục vụ trực tiếp. app.js dùng fetch(path) với path tương đối và gửi X-Platform/X-Session. Vì vậy:

- Vercel cần một static project trỏ tới portal/static hoặc một build artifact tương đương.
- Cần quyết định API mode: Vercel rewrites /api/* tới public Portal API, hoặc frontend dùng runtime API base URL. Cả hai đều chưa tồn tại trong repo.
- Nếu dùng cross-origin API, cần cookie SameSite/Secure, allowed origins, credentials policy, CSRF protection và preflight handling.
- Vercel phải phục vụ các route/assets /brand, /design, /face-api.min.js, /models và chat assets mà index.html/agent4_chat đang tham chiếu.
- Agent 3 Vite app là artifact khác; build command hiện tại là npm run build trong agent3/.../webui, output agent3/.../src/assistant/static và dev proxy trỏ loopback. Không được nhầm artifact này với Portal frontend.

## 8. Database, migrations, seed và initialization

Evidence hiện tại:

- Agent 3 có migrations 001_foundation.sql đến 010_xml_extractions.sql, SQLite-specific, được repository.py áp dụng vào capture.sqlite3.
- Agent 1 dùng SQLite state/database và key files.
- Agent 2 dùng nhiều SQLite stores gồm snapshot/case/remediation/model artifacts.
- Agent 4 dùng DuckDB warehouse/ops DB và có seed/demo data.
- data_pipeline/enterprise.py tạo DuckDB schema/data; setup_runtime.py sync/unpack warehouse và provision Agent 2 runtime.
- Legal corpus nằm trong SQLite/file data khoảng 263 MB; docs/DEPLOY_SERVER.md mô tả warehouse đầy đủ khoảng 2.3 GB.
- Không có migration runner cho Neon, seed transaction, extension declaration, backup/restore hoặc schema version contract.

Neon readiness: FAIL. Phải chọn một trong hai hướng trước khi triển khai:

1. Neon là system of record mới: viết PostgreSQL schema/migrations, port persistence layer và seed/rollback; thay SQLite/DuckDB paths trong request path.
2. Neon chỉ dành cho metadata/auth/job state: ghi rõ DuckDB/SQLite chỉ là read-only build artifact hoặc batch artifact, đặt trên object storage/volume và không dùng làm multi-instance mutable store.

Với financial production, hướng 1 hoặc một thiết kế hybrid được kiểm soát rõ ràng là cần thiết. Không thể chỉ tạo Neon database rồi deploy code hiện tại.

## 9. CORS, authentication và security

Các điểm cần xử lý trước production:

- CORS/Origin hiện gắn localhost; phải allow chính xác Vercel production/preview origins nếu cần, không dùng wildcard cùng credentials.
- CSP frame-src hiện chứa localhost; phải thay bằng HTTPS origins hợp lệ hoặc loại iframe nếu không cần.
- Agent 4 chưa có CORS/auth middleware. Chỉ nên cho Portal gateway gọi private URL; nếu browser gọi trực tiếp thì phải có auth và CORS chặt.
- Portal có shared password, FaceID local model, custom headers và local session file; cần threat model, rate limit, lockout, secure cookies, CSRF, secret rotation và audit identity.
- Endpoint trả Agent 1 key cho browser là không phù hợp production.
- Tokens bridge random theo process không phù hợp scale; dùng Render secret env cố định, mTLS/service JWT hoặc signed internal request.
- Các upload tài chính phải validate size/type, antivirus/content scan, object storage presigned upload, retention và encryption at rest.
- Không log API keys, authorization headers, raw financial documents hoặc provider prompts. Portal log_message hiện no-op nhưng agent logs cần review.
- Demo flags AGENT4_DEMO_MODE, AGENT4_DEMO_TOKEN, X-Demo-Persona và demo company phải bị disable/blocked trong production.

## 10. Local model, persistent file và cloud incompatibility

- Agent 2 HE4 runtime gọi WSL/Windows/DPAPI và có artifact/config phụ thuộc local executable. Không phù hợp Render Linux managed web service.
- Agent 3 legal corpus và workspace là local files; không phù hợp scale out nếu không mount persistent volume/object storage.
- Agent 4 DuckDB là single-file mutable/read path; không phù hợp nhiều web instances cùng ghi hoặc rolling deploy không coordinated.
- Agent 1 key directory và SQLite state cần persistent disk/secret backup. Render ephemeral filesystem sẽ làm mất key/state sau restart.
- Portal pending uploads/logs/audit/security/batches là local files; cần PostgreSQL/object storage/centralized logs.
- Python multi-process/child-process model của Portal cần được loại bỏ; Render service lifecycle không bảo đảm child processes cùng tồn tại sau deploy/restart.
- Các defaults ngày dữ liệu và demo seed có thể làm production stale hoặc không deterministic nếu không set explicit.

## 11. Resource và runtime risk

Tham chiếu hiện tại trong docs/DEPLOY_SERVER.md đề xuất khoảng 8 vCPU, 32 GB RAM và 200 GB disk cho mô hình all-in-one. Con số này không phải sizing đã benchmark, nhưng cho thấy workload không phù hợp với một web service nhỏ:

- Agent 3 dense reranker/lawbase được docs mô tả khoảng 2.2 GB model/runtime và legal corpus khoảng 263 MB.
- Agent 4 warehouse đầy đủ được docs mô tả khoảng 2.3 GB.
- Agent 1 forecast extras có torch/Chronos trong requirements-forecast.txt.
- Upload/import 600 giây và LLM call 180 giây làm tăng concurrent memory/worker occupancy.
- Vercel serverless không phù hợp chạy Python Portal, long-running import, local SQLite/DuckDB hoặc subprocess orchestration.

Khuyến nghị sizing sau remediation: benchmark từng service riêng trên production-like data; bắt đầu Agent 3/4 bằng dedicated instances có RAM đủ cho corpus/model, Agent 1 bằng worker có disk/CPU theo import/forecast, và không scale service có mutable local DB theo chiều ngang cho tới khi persistence được externalize.

## 12. Exact deployment configuration đích

Đây là cấu hình đích cần đạt sau remediation; các mục đánh dấu “cần bổ sung” hiện chưa có trong repository.

### Vercel: Portal static frontend

| Setting | Giá trị đích |
|---|---|
| Project root | portal/static, hoặc artifact static được build từ thư mục này |
| Framework | Other / static |
| Install command | Không cần nếu giữ raw static; nếu thêm build thì npm ci |
| Build command | Không có, hoặc command build frontend được chốt trong repo |
| Output directory | . trong project root |
| Public URL | https://<vercel-project-domain> |
| API routing | Rewrites /api/* và các agent4 chat API tới HTTPS Portal/Gateway Render |
| Environment | Chỉ public API base/config; không đặt LLM keys, DB URLs hay service tokens |
| Required change | Thêm API base/runtime config, Vercel rewrites hoặc gateway URL; sửa CSP/Origin/cookie/CORS |

### Render: Portal/Gateway

| Setting | Giá trị đích |
|---|---|
| Type | Web Service, Docker image khuyến nghị |
| Public exposure | Có, chỉ gateway |
| Bind | 0.0.0.0:$PORT |
| Health path | /healthz, cần bổ sung unauthenticated |
| Start command | python -m portal.server sau khi portal được chuyển thành gateway không spawn child processes |
| Build | Image chứa dependency của Portal và các client/contract cần thiết; không dùng run_web.ps1 |
| State | Neon/object storage/central logs; không dùng portal/workspace local làm source of truth |
| Networking | AGENT1_URL, AGENT2_URL, AGENT3_URL, AGENT4_URL là private service URLs |
| Required change | Bỏ HOST/port localhost, bỏ subprocess launch, service auth ổn định, health endpoint, persistent state |

### Render: Agent 1

| Setting | Giá trị đích |
|---|---|
| Type | Web Service/Background worker tùy import contract |
| Image | Có thể bắt đầu từ agent1/Dockerfile nhưng phải pin base/dependencies và bổ sung production config |
| Start | uvicorn agent1_service.main:app --host 0.0.0.0 --port $PORT |
| Health | /health liveness; thêm readiness riêng nếu cần DB/key validation |
| Storage | Managed PostgreSQL/object storage; nếu bắt buộc file key/state thì persistent disk, backup và single-writer |
| Secrets | AGENT1_KEY_DIR logic không được tạo key mới ngẫu nhiên sau mỗi deploy; dùng managed secret/key lifecycle |
| Access | Private network; request auth từ Gateway |

### Render: Agent 2

| Setting | Giá trị đích |
|---|---|
| Type | Web Service private |
| Start | python -m sme_fraud.review_server --port $PORT sau khi hỗ trợ 0.0.0.0 và private Portal URL |
| Health | Tách /healthz liveness khỏi /api/health readiness/business gate |
| Dependencies | Bổ sung cryptography trực tiếp vào manifest/lock |
| Storage | External DB/object storage hoặc persistent single-writer disk |
| HE | Không bật HE4 trên web service Render; tách worker/runtime riêng hoặc loại khỏi release |
| Auth | Signed service auth/private URL; không hardcode localhost-only authorizer |

### Render: Agent 3

| Setting | Giá trị đích |
|---|---|
| Type | Web Service private |
| Start | uvicorn src.assistant.web:app --host 0.0.0.0 --port $PORT, với PYTHONPATH/working directory được image cố định |
| Build | Python dependency lock mới; frontend dùng npm ci && npm run build trước khi image final |
| Health | Chọn một contract duy nhất, ví dụ /healthz và /readyz; đồng bộ với Portal |
| Storage | Neon/object storage cho workspace/metadata; legal corpus immutable trong versioned object/image nếu kích thước cho phép |
| APIs | AGENT3_LLM_API_KEY, AGENT3_EMBED_API_KEY, AGENT3_RERANK_API_KEY qua secret manager |
| Required change | Bỏ loopback defaults, externalize SQLite/workspaces, add PostgreSQL migration or documented artifact store |

### Render: Agent 4

| Setting | Giá trị đích |
|---|---|
| Type | Web Service private |
| Start | uvicorn agent4.api:create_app --factory --host 0.0.0.0 --port $PORT cho production app; không dùng create_demo_app |
| Health | /healthz liveness; /health/ready hoặc /readyz kiểm tra warehouse/config |
| Storage | Không dùng DuckDB file mutable trong nhiều instance; dùng external warehouse/object artifact với single-reader contract hoặc chuyển query state cần thiết sang Neon |
| Secrets | AGENT4_LLM_API_KEY và AGENT4_EMBED_API_KEY qua Render secret env |
| Demo | AGENT4_DEMO_MODE không set/false; chặn X-Demo-Persona và demo token |
| Required change | Production claims/policy auth, stable tenant identity, non-demo DB/config and request timeout budget |

### Neon PostgreSQL

| Setting | Giá trị đích |
|---|---|
| Connection | DATABASE_URL/pooled connection URL trong Render secret env; không commit |
| Schema | Versioned PostgreSQL migrations, extension declarations và schema owner |
| Init | Migration job/release command chạy trước web service; seed idempotent chỉ cho reference data |
| Backup | Neon backup/branch/restore procedure được kiểm thử |
| Rollback | Expand/contract migrations; không rollback bằng cách xóa schema hoặc reset production |

## 13. Required changes theo thứ tự

1. Chốt service boundary: Vercel static Portal UI, một Gateway Render, Agent 1-4 là private services hoặc hợp nhất có chủ ý.
2. Quyết định Neon là system of record nào; viết schema/migrations/adapter và data migration plan.
3. Tạo production config contract: PORT, bind host, service URLs, CORS origins, cookie domain, auth secrets, provider endpoints, timeouts.
4. Bỏ Portal subprocess/autostart và localhost-only trust; bổ sung healthz/readyz.
5. Externalize state, upload, audit, legal corpus và warehouse; xác định persistent volume/object storage/Neon cho từng loại.
6. Sửa dependency manifests, pin/lock cho mọi service; tạo image/CI clean build.
7. Tắt toàn bộ demo paths, rotate secrets và kiểm tra git history/artifact layers.
8. Thêm integration test chạy qua HTTPS Vercel-like origin tới Render-like services và external providers mocked.
9. Benchmark import/rerank/LLM/warehouse theo concurrency và giới hạn timeout của platform.
10. Chốt release commit sạch, backup và migration rehearsal trước production.

## 14. Deployment procedure

### Chuẩn bị

1. Tạo release branch/tag từ commit sạch; không deploy working tree hiện tại.
2. Rotate mọi key đã từng tồn tại trong .env hoặc artifact không chắc chắn.
3. Tạo Neon project/branch production, lấy pooled connection string vào secret manager.
4. Tạo object storage/persistent storage cho upload, legal corpus, reports và immutable warehouse artifacts.
5. Build/test images trong CI từ lockfile; không dùng setup_env.sh hoặc run_web.ps1.

### Triển khai

1. Chạy database migration release job; kiểm tra schema version và seed/reference data.
2. Deploy Agent 1-4 private services; chờ /healthz và /readyz pass.
3. Deploy Gateway Render với private URLs và service credentials; kiểm tra gateway /healthz.
4. Deploy Vercel static frontend với API rewrites/base URL và production origin.
5. Chạy smoke test đăng nhập, upload một fixture không nhạy cảm, gọi từng agent và kiểm tra audit trail.
6. Mở traffic theo canary/preview domain; theo dõi error rate, latency, provider quota, DB connections và disk/object growth.

### Rollback

1. Nếu lỗi application, giữ DB schema tương thích và rollback Vercel/Gateway/agent image về version trước.
2. Không rollback schema destructive. Dùng migration expand/contract hoặc forward fix.
3. Nếu migration lỗi, dừng traffic ghi, restore Neon branch/backup theo runbook đã diễn tập và kiểm tra consistency.
4. Nếu provider/API key lỗi, disable feature/route có vấn đề và rotate key; không xóa audit/data.
5. Sau rollback, chạy lại health, auth, read-only query và reconciliation trước khi mở traffic.

## 15. Post-deployment testing checklist

### Build và platform

- [ ] Tất cả service build từ clean checkout, lockfile và image digest đã lưu.
- [ ] Vercel phục vụ index, CSS, JS, brand, model assets và chat assets không 404.
- [ ] Render service bind 0.0.0.0:$PORT, restart không làm mất state cần giữ.
- [ ] /healthz không yêu cầu auth; /readyz phản ánh đúng dependency.

### Network và auth

- [ ] Browser từ production Vercel origin gọi được Gateway HTTPS.
- [ ] Preflight/CORS chỉ cho origin hợp lệ; credentials/cookie có Secure và SameSite đúng.
- [ ] Agent private không truy cập trực tiếp từ Internet.
- [ ] Portal không trả bearer key nội bộ cho browser.
- [ ] Service tokens ổn định qua restart, rotate được và không xuất hiện trong log.
- [ ] Rate limit, brute-force protection, CSRF và session expiry đã test.

### Data và database

- [ ] Neon migration version đúng, indexes/constraints/extensions đúng và pooled connection ổn định.
- [ ] Seed idempotent; không seed demo tenant/company vào production.
- [ ] Upload lớn, duplicate upload, retry và partial failure không làm mất file hoặc tạo state mồ côi.
- [ ] Backup/restore và rollback rehearsal đã có bằng chứng.
- [ ] Multi-instance không dùng chung mutable SQLite/DuckDB local file.

### Agent chức năng

- [ ] Agent 1 health/import/reconciliation chạy với fixture an toàn.
- [ ] Agent 2 review, snapshot, auth bridge và release gate pass đúng policy.
- [ ] Agent 3 XML/statement ingestion, lawbase retrieval, embed/rerank fallback và external API timeout pass.
- [ ] Agent 4 query, tenant/claims/policy auth, metric selection và timeout pass; demo persona bị chặn.
- [ ] Provider quota, 429, 5xx, timeout và malformed response có retry/backoff/fail-safe.

### Security và vận hành

- [ ] Secret scan chạy trên source, git history, CI artifact, Docker layers và logs.
- [ ] Không có localhost/127.0.0.1 trong production bundle/config ngoại trừ test fixture được loại khỏi build.
- [ ] CSP, HSTS, X-Content-Type-Options, Referrer-Policy và upload limits đã kiểm tra.
- [ ] Logs có request/correlation ID nhưng không chứa secret, bearer token hoặc raw financial documents.
- [ ] Alerts cho 5xx, latency, provider failure, DB connection exhaustion, disk/object growth và auth failures.
- [ ] Runbook rollback, restore và key rotation đã được một người khác diễn tập.

## 16. Tiêu chí go/no-go

GO chỉ khi toàn bộ BLOCKER đã đóng và tối thiểu các HIGH H-01, H-02, H-03, H-04, H-05, H-06, H-07, H-08, H-09, H-10 được xác minh bằng test/deploy evidence. Nếu giữ nguyên thiết kế hiện tại, quyết định phù hợp là NO-GO cho Vercel + Render + Neon production; chỉ local/demo single-host mới có thể tiếp tục theo các launcher hiện có.
