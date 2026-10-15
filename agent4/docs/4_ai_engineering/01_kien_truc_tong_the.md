# 01 · Kiến trúc tổng thể và pipeline

> Trạng thái: các khối **[ĐÃ CÓ]** nằm trong `agent4/engine` & `agent4/datagen`; các khối **[CHƯA]** là việc giao ở `5_handoff`.

## 1. Nguyên lý
**"Lõi tất định – vỏ LLM"**: LLM *không* tính, *không* viết SQL tài chính, *không* thực thi. Nó (1) hiểu ý, (2) chọn công cụ/tham số trong một không gian đã được thu hẹp và kiểm chứng, (3) diễn giải kết quả có sẵn. Mọi bước LLM đều bị bao bởi bộ tiền xử lý tất định ở trước và bộ xác minh tất định ở sau.

## 2. Sơ đồ khối
```
                    ┌────────────────────────────────────────────────────────────┐
 Người dùng ──────► │ L4  Giao diện: chat web/mobile · (Zalo) · bản tin tuần       │
                    └───────────────┬────────────────────────────────────────────┘
                                    ▼
                    ┌────────────────────────────────────────────────────────────┐
                    │ Gateway [CHƯA]: xác thực · vai trò/phạm vi (chi nhánh) · rate limit │
                    └───────────────┬────────────────────────────────────────────┘
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ L3  ORCHESTRATOR [CHƯA]  (vòng lặp tối đa 4–5 bước, trạng thái hội thoại, nhật ký)         │
 │                                                                                          │
 │  ① Tiền xử lý tất định ──► ② Thu hẹp công cụ ──► ③ LLM (Qwen ≤ 10B) ──► ④ Validator       │
 │  • chuẩn hóa chữ/dấu         • BM25 (+embedding)     • chọn công cụ/args     • JSON schema │
 │  • periods.extract_periods   • top‑k chỉ số + điểm   • hoặc hỏi lại/từ chối  • view rule  │
 │  • detect_comparison         • gợi ý khung/view      (T=0, schema ràng buộc)  • period ok  │
 │  • resolve_entity (mờ)       • phát hiện mơ hồ                                • entity ok  │
 │  • cue: thuế / hành động /                                    ▲  sửa lỗi có chẩn đoán ≤2  │
 │    ngoài phạm vi                                              └───────────────────┐        │
 │                                                                                    ▼        │
 │  ⑤ Thực thi công cụ (ExecutionEngine, DB chỉ‑đọc) ──► ⑥ Đóng gói kết quả (display strings,  │
 │                                                          nhãn kỳ/khung/tạm tính, lineage_id) │
 │  ⑦ Soạn trả lời: "khối sự kiện" tất định + 1–2 câu diễn giải do LLM (T thấp)               │
 │  ⑧ VERIFIER: mọi số ∈ tập số công cụ · có nhãn bắt buộc · không mệnh đề không nguồn        │
 │        ├── đạt → trả lời + nút "Xem cách tính"                                             │
 │        └── trượt → sinh lại ≤ 2 lần → cuối cùng trả "khối sự kiện" tất định (suy biến)       │
 │  ⑨ Nhật ký kiểm toán (chuỗi băm)                                                           │
 └───────────────┬──────────────────────────────────────────────────────────────────────────┘
                 ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ L2  CÔNG CỤ (LLM nhìn thấy ≤ 8)                                                             │
 │  query_metric · explain_metric · find_entity · list_metrics · propose_action               │
 │  orchestrate_agents (A1/A2/A3, mock) · run_readonly_sql (cờ tính năng) · ask_clarification · refuse │
 └───────────────┬──────────────────────────────────────────────────────────────────────────┘
                 ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ L1  LÕI TẤT ĐỊNH [ĐÃ CÓ]   agent4/engine                                                    │
 │  metrics.py (66 chỉ số) · engine.py (query/compare/explain/filters/status) · custom*.py     │
 │  periods.py · formatting.py (hiển thị & phân tích số VN)                                    │
 └───────────────┬──────────────────────────────────────────────────────────────────────────┘
                 ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ L0  DỮ LIỆU [ĐÃ CÓ]  DuckDB: gl_entry + dim_* + sổ chi tiết · views v_mgmt / v_tax          │
 │     Ops DB [CHƯA]: pending_approvals · audit_log · conversations                           │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Phân chia trách nhiệm (ai làm gì)
| Việc | Tất định (code) | LLM |
|---|---|---|
| Tính doanh thu, lãi, DSO… | ✔ | ✘ |
| Đổi "quý trước" thành ngày | ✔ `periods.py` | ✘ (chỉ truyền cụm từ/token) |
| Khớp "Hoàng Long" → mã khách | ✔ `resolve_entity` | ✘ |
| Chọn chỉ số trong ≤ 8 ứng viên | gợi ý + kiểm | ✔ quyết định |
| Phát hiện mơ hồ / ngoài phạm vi | quy tắc cứng + điểm retrieval | ✔ xác nhận |
| Chọn khung `mgmt`/`tax` | luật + validator | ✔ đề xuất |
| Viết số vào câu trả lời | ✔ khối sự kiện | ✘ không tự viết số mới |
| Diễn giải ngắn, gợi ý bước tiếp | — | ✔ (bị verifier kiểm) |
| Thực thi hành động | ✔ handler tất định sau phê duyệt | ✘ |

## 4. Hợp đồng dữ liệu giữa các khối
### 4.1 Lời gọi `query_metric` (LLM → validator → engine)
```json
{"metric":"net_revenue","period":"last_quarter","compare_to":"previous_period",
 "group_by":null,"filters":{"branch":"Hà Nội"},"view":"mgmt","top_k":null,"params":null}
```
`period` chấp nhận token (`this_month`, `2026-Q3`, `ytd`, `last_6_months`…), cụm tiếng Việt, hoặc khoảng ngày — **luôn được `resolve_period` xử lý**, LLM không tính ngày.

### 4.2 Kết quả engine (rút gọn)
```json
{"metric_id":"net_revenue","value":55787000000,"display":"55,79 tỷ đồng","unit":"VND",
 "period":{"type":"flow","start_date":"2026-07-01","end_date":"2026-09-30"},"period_label":"quý 3/2026",
 "view":"mgmt","data_status":"Tạm tính – chưa khóa sổ (09/2026)","data_through":"2026-10-14",
 "comparison":{"period":{"label":"quý 2/2026"},"display":"52,3 tỷ đồng","delta_pct_display":"+6,6%","direction":"tăng"},
 "rows":[…],"notes":[…],
 "audit_trail":{"accounts_involved":["511","521"],"entry_count":3915,"formula":"…","lineage_id":"L-1a2b3c4d5e"}}
```
(Các trường `_sql`, `_sql_params` chỉ dùng cho log/kiểm toán, **không** đưa vào prompt.)

### 4.3 Gói thông tin gửi LLM để diễn giải ("facts pack")
Chỉ chứa: `label`, `display`, `period_label`, `data_status`, `comparison.*display`, tối đa 8 dòng `rows` (label + display + share), `notes`, và cờ cảnh báo. **Không** số thô float, không SQL, không văn bản tự do chưa được bọc (xem `04`).

## 5. Luồng cho các loại câu hỏi
| Loại | Đường đi |
|---|---|
| Tra số / so sánh / phân rã | ①→②→③ `query_metric` →④→⑤→⑥→⑦→⑧ |
| Mơ hồ | ②→③ `ask_clarification(options)` → trả hỏi lại (không số) |
| Ngoài phạm vi / không an toàn | ① cue hoặc ③ `refuse` → trả lời từ chối + gợi ý trong phạm vi |
| "Xem cách tính" | `explain_metric` (lấy từ `lineage_id` của câu trước) |
| Tên thực thể mơ hồ | `FilterError.candidates` → hỏi lại chọn thực thể |
| Câu hỏi tổng hợp ("tháng này có gì bất thường?") | `orchestrate_agents` song song A1/A2/A3 + `expense_spikes`, `overdue_receivables`, `unbalanced_journals` → bản tin |
| Hành động | `propose_action` → `pending_approvals` → UI duyệt → handler → `audit_log` |
| Ngoài thư viện chỉ số | `run_readonly_sql` (nếu bật): sinh SQL → AST validator → chạy → verifier |

## 6. Trạng thái hội thoại (nhiều lượt)
`ConversationState`: `last_metric`, `last_period`, `last_filters`, `last_group_by`, `last_view`, `last_result` (nén), `pending_clarification`. Quy tắc: **tham số nêu rõ ở lượt mới ghi đè**; cụm "còn", "vậy", "thế", "cùng kỳ đó" kích hoạt kế thừa; "tháng đó/khách ấy" tham chiếu `last_*`; trạng thái hết hạn sau 15 phút hoặc đổi chủ đề rõ rệt. Trạng thái được đưa vào prompt dưới dạng khối YAML ngắn (≤ 80 token).

## 7. Suy biến an toàn (graceful degradation)
| Sự cố | Hành vi |
|---|---|
| LLM không phản hồi/timeout | Chế độ tra cứu bằng form (chọn chỉ số + kỳ) gọi thẳng engine |
| Verifier trượt 3 lần | Trả "khối sự kiện" tất định, không diễn giải |
| Engine lỗi | Thông báo rõ nguyên nhân (không bịa số), ghi log |
| Dữ liệu chưa đủ (chưa có bảng lương tháng hiện tại…) | Nêu giới hạn trong `notes` |
