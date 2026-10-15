# 05 · Kế hoạch thí nghiệm (giả thuyết, biến, cách quyết định)

> **Phân loại:** [Đã suy luận] = có lập luận kỹ thuật nhưng *chưa đo*; [Cần thí nghiệm] = chưa thể kết luận. Chưa có thí nghiệm nào đã chạy với LLM trong phiên này — mọi "kỳ vọng" bên dưới là giả thuyết.

## 0. Quy ước chung
- **Dữ liệu:** dev/val/test như `2_data/07`; mọi so sánh trên **cùng** tập val với cùng seed LLM; báo bootstrap 95% CI.
- **Cấu hình nền (baseline B0):** Qwen3‑8B Q4_K_M, `think=off`, T=0, `num_ctx=8192`, 66 chỉ số **không** thu hẹp, tool‑calling gốc của Ollama, few‑shot tĩnh 3 ví dụ, prompt tiếng Việt, không verifier.
- **Cấu hình mục tiêu (B*):** thu hẹp công cụ (k=8) + tiền xử lý hints + schema ràng buộc + few‑shot kNN + verifier + khối sự kiện tất định.
- **Nguyên tắc cắt giảm:** thêm một thành phần chỉ khi cải thiện ≥ 1 điểm % ở metric mục tiêu mà không làm xấu metric Must.

## 1. Danh sách giả thuyết
| ID | Giả thuyết | Trạng thái | Biến | Metric chính | Kỳ vọng (giả thuyết) | Quy tắc quyết định |
|---|---|---|---|---|---|---|
| **H1** | Thu hẹp công cụ bằng retrieval nâng TSA so với đưa đủ 66 | Đã suy luận | k ∈ {66, 20, 12, 8, 5}; BM25 / embedding / lai | TSA, top‑k recall, latency | k=8 lai: TSA +10–20 điểm so với 66; recall ≥ 99% | Chọn k nhỏ nhất đạt recall ≥ 99% |
| **H2** | Bộ phân giải ngày/thực thể tất định giảm lỗi tham số | Đã suy luận | LLM tự điền vs "hints có sẵn" vs "điền sẵn, LLM xác nhận" | Arg exact‑match, Period F1 | Period F1 ≥ 97% khi dùng hints | Chọn cấu hình thấp nhất đạt G1.2 |
| **H3** | Giải mã ràng buộc JSON‑schema tốt hơn tool‑calling gốc cho model nhỏ | Cần thí nghiệm | {native tools, `format`=schema, grammar llama.cpp} | Schema‑valid, TSA, latency | Schema‑valid ~100%; TSA ± 2 điểm | Chọn cách ổn định và nhanh hơn |
| **H4** | Qwen3‑8B (think off) ≥ Qwen3‑4B‑2507; `think=on` chỉ lợi cho ca khó | Cần thí nghiệm | model × think {off,on} × độ khó | TSA, Arg, p50/p95 | 8B hơn 4B 3–6 điểm; think +2–5 điểm ca khó, ×3 độ trễ | Dùng think có điều kiện theo điểm retrieval |
| **H5** | "Khối sự kiện tất định + diễn giải ngắn" ổn định hơn LLM viết toàn bộ | Đã suy luận | {LLM tự do, template, hybrid} | Numeric faithfulness, CSAT giả lập | Hybrid đạt faith 100% sau verifier | Chọn hybrid trừ khi người dùng thấy cứng |
| **H6** | Verifier + sinh lại ≤ 2 lần đưa faithfulness → 100% với chi phí độ trễ nhỏ | Đã suy luận | độ chặt mệnh đề nhân quả {off, mức 1, mức 2}; số lần thử | Recall lỗi, FP, retry, latency | Recall ≥ 99%, FP ≤ 2% | Chọn mức chặt nhất có FP ≤ 2% |
| **H7** | Few‑shot kNN (3) tốt hơn tĩnh | Cần thí nghiệm | {0, 3 tĩnh, 3 kNN, 5 kNN, 8 kNN} | TSA, Arg, token | kNN 3–5 +3–8 điểm so với tĩnh | Chọn n nhỏ nhất bão hòa |
| **H8** | System tiếng Anh + ví dụ VN ≥ system tiếng Việt | Cần thí nghiệm | {VN, EN, song ngữ} | TSA, Arg | Chênh ≤ 3 điểm | Chọn theo điểm; ưu tiên VN nếu hòa |
| **H9** | Bộ phân loại ý định nhẹ trước LLM (PhoBERT/fastText) cải thiện hỏi lại/từ chối | Cần thí nghiệm | {LLM‑only, classifier‑first, hybrid} | Clarify P/R, Refuse recall, over‑refusal | Hybrid giảm over‑refusal 30–50% | Chọn nếu giảm lỗi mà không tăng độ trễ > 100 ms |
| **H10** | Hai lượt (ý định → tham số) tốt hơn một lượt cho ca khó | Cần thí nghiệm | {1 lượt, 2 lượt, 2 lượt có điều kiện} | TSA, Arg khó | +2–4 điểm ca khó, +1 s | Chỉ dùng có điều kiện |
| **H11** | Self‑consistency (k=3, bỏ phiếu tham số) sửa lỗi ngẫu nhiên | Cần thí nghiệm | k ∈ {1,3,5}, T ∈ {0,0.3} | Arg, stability, latency | +1–3 điểm, ×k độ trễ | Thường không đáng; chỉ khi leo thang |
| **H12** | QLoRA Qwen3‑4B trên dữ liệu tổng hợp cải thiện TSA/Arg ngoài mẫu | Cần thí nghiệm | {không FT, FT 5k, FT 20k} × {có/không few‑shot} | TSA, Arg trên *kho khác* | +3–8 điểm trên val, giảm phụ thuộc few‑shot; rủi ro quá khớp | Chỉ nhận nếu cải thiện trên test seed khác & E‑gold |
| **H13** | Lượng tử hóa Q4_K_M đủ (so Q5_K_M/Q8) | Cần thí nghiệm | quant × model | TSA, Arg, VRAM, tok/s | Chênh ≤ 1,5 điểm | Chọn nhỏ nhất đủ |
| **H14** | Text‑to‑SQL có kiểm soát tối thiểu hóa rủi ro nhưng chính xác thấp | Đã suy luận | {tắt, bật whitelist+AST+verifier} | Exec‑acc, an toàn, refusal | Exec‑acc 40–60% trên E9 | Bật theo cờ, luôn qua verifier |
| **H15** | Hội thoại nhiều lượt cần slot‑carryover tất định | Đã suy luận | {LLM tự nhớ, slot rule, hybrid} | E7 task success | Hybrid ≥ 85% | Chọn hybrid |
| **H16** | Bản tin chủ động bằng quy tắc + LLM tóm tắt đạt recall ca cài | Cần thí nghiệm | {rule top‑N, rule + LLM xếp hạng} | E10 precision/recall | Recall ≥ 90% ca cài | |
| **H‑biz** | Nhìn thấy sớm công nợ quá hạn đổi hành vi thu hồi (giảm DSO) | Giả thuyết kinh tế | pilot trước/sau | ΔDSO, nợ quá hạn | −3 ngày (kịch bản cơ sở) | Quyết định tiếp tục đầu tư (`3_evaluation/02,03`) |

## 2. Thiết kế chi tiết cho các thí nghiệm then chốt
### H1 — Thu hẹp công cụ
- **Chỉ mục:** văn bản = `label + description + synonyms + examples` (chuẩn hóa có/không dấu). BM25 (rank_bm25) và embedding (`multilingual-e5-small` trên CPU). **Lai**: điểm = 0,6·BM25_norm + 0,4·cosine; thử trọng số {0, .3, .5, .7, 1}.
- **Đo:** top‑k recall trên E1 theo độ khó/nhiễu; TSA của LLM với tập ứng viên; thời gian retrieval (mục tiêu < 30 ms).
- **Điểm mơ hồ:** `margin = s1 − s2`, `s1`. Hiệu chỉnh ngưỡng `(s1<τ1 hoặc margin<τ2)` ⇒ cho phép hỏi lại; chọn (τ1, τ2) tối đa hóa F1 hỏi‑lại trên E3 mà không làm giảm TSA E1.
- **Phân tích lỗi:** nhóm nhầm lẫn (ma trận nhầm giữa các cặp chỉ số), đề xuất sửa `synonyms`/mô tả.

### H3 — Cơ chế đầu ra
Ba nhánh với cùng prompt: (a) `tools=[…]` của Ollama (template riêng của model); (b) `format=<JSON schema union>`; (c) llama.cpp + GBNF (nếu có). Đo: tỷ lệ phân tích được, TSA, độ trễ, mức thiếu `tool_call` khi lẽ ra phải gọi. Nếu (a) có call‑omission ≥ 3% và (b) gần 0% ⇒ chọn (b).

### H4 — Model & thinking
Lưới 2 model × `think` × độ khó (easy/medium/hard theo E1). Ghi **token sinh**, độ trễ, TSA, Arg. Quy tắc bật `think`: khi retrieval `s1<τ1` hoặc câu chứa ≥ 2 mệnh đề; xác định lợi ích biên so với 2 lượt (H10).

### H6 — Verifier
Tập lỗi tiêm vào (E6): đổi chữ số, đổi tỷ↔triệu, đổi dấu, xóa nhãn tạm tính, thêm số bịa, đổi kỳ, hoán vị hai số. Đo recall theo loại lỗi. Đo FP trên câu trả lời đúng (có làm tròn/diễn đạt khác: "gần 8 tỷ", "khoảng 62 ngày").

### H7/H8 — Prompt
Thiết kế giai thừa nhỏ: ngôn ngữ {VN, EN} × few‑shot {0, 3 kNN, 5 kNN} × có/không khối HINTS = 12 ô; chạy 3 lần seed để ước lượng phương sai; ANOVA đơn giản chọn yếu tố có tác động.

### H12 — Tinh chỉnh
- **Dữ liệu train:** 20k cặp từ E1/E2 (templates × đồng nghĩa × nhiễu), *không* dùng câu val/test và *không* dùng seed kho test.
- **Cấu hình khởi đầu:** QLoRA r=16, α=32, dropout 0,05, lr 2e‑4 cosine, 2 epoch, chuỗi ≤ 768, batch hiệu dụng 16; chỉ huấn luyện phần trả lời (mask prompt).
- **Đo:** TSA/Arg trên val/test và trên **kho hoàn toàn khác** (ngành khác); kiểm tra quên: hành vi hỏi lại/từ chối, an toàn (E8) không xấu đi.
- **Điều kiện dừng:** nếu cải thiện < 2 điểm so với B* (đã có đòn bẩy 1–4) ⇒ không đáng tinh chỉnh.

## 3. Quét tham số (sau khi chọn kiến trúc)
| Tham số | Lưới | Ghi chú |
|---|---|---|
| `temperature` | 0; 0,1; 0,3 (diễn giải) | Gọi công cụ: 0 |
| `top_p` / `top_k` | 1,0/∞; 0,8/20 | Qwen khuyến nghị top_k 20 cho non‑thinking |
| `repeat_penalty` | 1,0; 1,05 | Tránh lặp ở phần diễn giải |
| `num_ctx` | 4096; 8192; 12288 | Ảnh hưởng VRAM/độ trễ; cần ≥ prompt+output |
| `num_predict` | 256/384 (gọi); 300/450 (diễn giải) | Giới hạn trôi |
| k ứng viên | 5–12 | H1 |
| số ví dụ | 0–8 | H7 |
| ngưỡng hỏi lại (τ1, τ2) | lưới 2D | E3 |
| số lần sinh lại verifier | 0–3 | H6 |
| `keep_alive`, `num_parallel`, KV cache | xem `06` | Hiệu năng |

## 4. Thứ tự thực hiện (rẻ → đắt)
1. Baseline B0 trên val (đo trần dưới) — 1 ngày.
2. H2 → H1 → H3 (thành phần tất định, ít tốn GPU).
3. H4 → H7/H8 → H10.
4. H5/H6 (diễn giải & verifier) → chốt B*.
5. H9, H15, H16, H14 (tính năng mở rộng).
6. H13 (lượng tử hóa) và tối ưu tốc độ (`06`).
7. H12 (tinh chỉnh) chỉ nếu chưa đạt G1.
8. H‑biz (pilot).

## 5. Báo cáo thí nghiệm
Mỗi thí nghiệm một file `eval/experiments/Hxx_<tên>.md`: giả thuyết · cấu hình · dữ liệu · kết quả (bảng + CI) · phân tích lỗi (≥ 10 ví dụ) · quyết định · bước tiếp. Số liệu thô lưu `eval/results/<date>/<run_id>.jsonl` để tái lập.
