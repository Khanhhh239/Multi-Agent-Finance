# Financial Analytics Assistant — Product Scope

**Version:** 0.1  
**Status:** Draft for contract-first review  
**Last updated:** 2026-11-05

## 1. Product definition

Financial Analytics Assistant là một hệ thống phân tích dữ liệu tài chính bằng ngôn ngữ tự nhiên.

Người dùng đặt câu hỏi bằng tiếng Việt hoặc tiếng Anh. Hệ thống xác định các metric nghiệp vụ được phép sử dụng, lập kế hoạch truy vấn dạng semantic, biên dịch thành SQL an toàn, thực thi read-only trên database, kiểm tra kết quả và trả về câu trả lời có provenance.

Sản phẩm là **governed text-to-metrics-to-SQL assistant**, không phải chatbot sinh SQL tự do.

## 2. Mục tiêu sản phẩm

### Mục tiêu chính

- Giúp finance analyst, accountant, controller và CFO truy vấn thông tin tài chính mà không cần tự viết SQL.
- Đảm bảo mọi metric đều đến từ Metric Catalog đã được phê duyệt.
- Đảm bảo LLM không thể tự ý sinh hoặc thực thi SQL nguy hiểm.
- Trả lời dựa trên kết quả database đã được kiểm tra, không dựa trên suy đoán của LLM.
- Có thể giải thích hệ thống đã hiểu câu hỏi như thế nào.
- Có thể truy vết catalog version, data watermark, policy và query fingerprint.

### Mục tiêu kỹ thuật

- Các module giao tiếp qua typed contract, không phụ thuộc implementation cụ thể.
- Có thể thay embedding model, vector index, reranker, LLM provider hoặc database adapter độc lập.
- Mọi module có thể test bằng contract test và golden test.
- Failure phải fail closed: không chắc chắn thì hỏi lại hoặc từ chối, không tự đoán để chạy query.

## 3. Đối tượng sử dụng

### Người dùng trực tiếp

- Finance analyst.
- Accounting/controller.
- CFO hoặc business user có quyền đọc dữ liệu.

### Người dùng tích hợp

- Internal dashboard.
- Internal API client.
- Chat interface nội bộ.

## 4. Phạm vi MVP

### 4.1. Loại câu hỏi hỗ trợ

- Tính một hoặc nhiều metric trong một khoảng thời gian.
- Xem time series theo ngày, tuần, tháng, quý hoặc năm nếu metric hỗ trợ.
- Breakdown theo dimension được allowlist.
- Ranking/top-k.
- So sánh kỳ trước hoặc cùng kỳ năm trước khi capability của metric cho phép.
- Lọc theo các field và operator được allowlist.
- Chọn view nghiệp vụ, ví dụ `mgmt` hoặc `tax`, khi user có quyền.

### 4.2. Metric

- Chỉ sử dụng metric có trong Metric Catalog.
- Mỗi metric có owner, trạng thái approval, unit, period type, view và dimension capability.
- Metric custom chỉ được chạy khi có handler/source đã được kiểm chứng.
- Metric chưa được owner phê duyệt phải trả về `unsupported` hoặc không được đưa vào catalog public.

### 4.3. Ngôn ngữ và dữ liệu

- MVP hỗ trợ `vi-VN` và `en-US`.
- Database được truy cập read-only.
- Mọi số liệu phải có data watermark nếu nguồn dữ liệu cung cấp.
- Dữ liệu synthetic/demo và dữ liệu production phải được phân biệt rõ trong response và release gate.

### 4.4. Kết quả trả về

Response có thể gồm:

- Câu trả lời ngắn.
- Bảng dữ liệu nếu request yêu cầu.
- Interpretation: metric, dimension, time và view đã được hiểu.
- Warning: dữ liệu partial, ratio không tính được, result bị truncate hoặc nguồn đang ở demo mode.
- Provenance: catalog hash, data watermark, source và query fingerprint.

## 5. Workflow chuẩn

```text
Query Intake
  → Metric Retrieval
      → query embedding
      → dense retrieval
      → lexical retrieval
      → fusion
      → optional expansion
      → reranking
  → Dynamic Few-shot Retrieval
  → LLM Metric Selection
  → Metrics Validation
  → Query Planning
  → Semantic Plan Validation
  → SQL Compilation
  → SQL Safety Validation
  → Read-only SQL Execution
  → Result Validation
  → Answer Generation
  → Answer Validation
  → Final Response
```

### Nguyên tắc boundary

1. Metric Retrieval chỉ tạo candidate set, không quyết định metric cuối cùng.
2. Dynamic Few-shot chỉ chọn ví dụ hướng dẫn LLM, không được cấp quyền hoặc bổ sung metric.
3. LLM chỉ được chọn metric trong candidate set.
4. Metrics Validator là authority cuối cùng cho metric.
5. Query Planner tạo semantic plan, không tạo executable SQL.
6. SQL Compiler chỉ nhận `ValidatedPlan`.
7. SQL Executor chỉ nhận query đã qua Safety Validation.
8. Answer Generator chỉ nhận result đã qua Result Validation.
9. Answer Validator phải kiểm tra mọi claim của câu trả lời dựa trên result.

## 6. Không thuộc phạm vi MVP

- Cho user nhập và chạy SQL trực tiếp.
- LLM tự sinh SQL rồi chạy thẳng trên database.
- `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `COPY`, `ATTACH` hoặc bất kỳ write operation nào.
- Tự động tạo metric/formula mới từ câu hỏi.
- Tự động suy diễn business definition khi Metric Catalog không có metric phù hợp.
- Forecasting, recommendation, anomaly detection và scenario planning.
- Thực hiện payment, journal posting hoặc hành động tài chính.
- Tự động khám phá schema production và đưa toàn bộ schema cho LLM.
- Dùng dữ liệu synthetic để tuyên bố đã đạt production data qualification.
- Multi-tenant production nếu database chưa có tenant key, DB grant hoặc RLS thật.

## 7. Môi trường sản phẩm

### 7.1. Synthetic/local

Mục đích:

- Phát triển module.
- Chạy unit/integration test.
- Kiểm tra compiler, safety boundary và pipeline.
- Đánh giá retrieval trên dữ liệu được kiểm soát.

Không được dùng kết quả môi trường này để tuyên bố dữ liệu tài chính production đã đúng.

### 7.2. Staging

Phải có:

- Database mapping gần production.
- Auth context giả lập nhưng có tenant boundary.
- Catalog approval snapshot.
- LLM/embedding provider đã chốt hoặc mock có behavior tương đương.
- Evaluation set độc lập.
- Load test và failure injection.

### 7.3. Production

Phải có:

- Tenant isolation được chứng minh bằng DB policy/RLS hoặc cơ chế tương đương.
- Read-only database role.
- Secrets đi qua secret manager.
- Audit log và trace không chứa raw financial data ngoài chính sách retention.
- Monitoring, alerting, timeout, rate limit và circuit breaker.
- Domain owner ký duyệt metric/công thức.
- Incident và rollback runbook.

## 8. Trạng thái cuối của một request

```text
ready
needs_clarification
unsupported
forbidden
no_data
temporarily_unavailable
error
```

### Ý nghĩa

- `ready`: answer và result đã qua các validation gate.
- `needs_clarification`: thiếu thông tin làm thay đổi ý nghĩa truy vấn.
- `unsupported`: metric, dimension, operation hoặc data source chưa được hỗ trợ.
- `forbidden`: user không có quyền truy cập.
- `no_data`: truy vấn hợp lệ nhưng không có dữ liệu phù hợp.
- `temporarily_unavailable`: provider hoặc database tạm thời không sẵn sàng.
- `error`: lỗi hệ thống hoặc contract không thể xử lý an toàn.

## 9. Production readiness gates

Không được gọi là production-ready nếu còn một trong các blocker sau:

- Chưa xác định tenant key và isolation boundary.
- Chưa có database mapping và role production.
- Metric chưa có finance/domain owner approval.
- Chưa có evaluation set đủ lớn, có golden answer và được review độc lập.
- Chưa chốt provider, model version, timeout, cost budget và outage policy.
- Chưa có latency/concurrency target.
- Chưa có logging, monitoring, retention và data residency policy.
- Chưa có adversarial/security test cho prompt injection, unauthorized metric và unsafe SQL.

## 10. Definition of Done cấp sản phẩm

Sản phẩm được coi là hoàn thành một milestone khi:

- Contract của tất cả module đã được review và version hóa.
- Có unit, contract, integration và regression tests.
- Có happy path, clarification path, unsupported path, forbidden path và provider failure path.
- Có metric retrieval evaluation và end-to-end answer evaluation.
- Có security tests chứng minh LLM không bypass được policy và SQL safety gate.
- Có provenance đầy đủ trong final response.
- Có runbook cho provider/database unavailable.
- Có tài liệu rõ phần synthetic qualification và phần real-data qualification.

## 11. Thứ tự triển khai sau khi scope được duyệt

1. Freeze request/response contract.
2. Freeze Metric Catalog và database mapping.
3. Freeze Metric Retrieval và Dynamic Few-shot contracts.
4. Implement/verify Metrics Validation.
5. Implement/verify Query Planning và Plan Validation.
6. Implement/verify SQL Compiler và SQL Safety.
7. Implement database adapter và Result Validation.
8. Implement grounded Answer Generation và Answer Validation.
9. Thêm observability, evaluation và load test.
10. Chỉ sau đó tích hợp database production thật.

## 12. Open decisions cần owner chốt

- Danh sách metric production và finance owner tương ứng.
- Định nghĩa chính thức của từng metric và reconciliation rule.
- Database engine, role, tenant key và RLS strategy.
- Embedding model, index technology và refresh policy.
- LLM provider, model, timeout, token budget và fallback.
- Dynamic few-shot bank ownership, review process và versioning.
- SLO latency, concurrency, cost/request và availability.
- Log retention, data masking và data residency.
