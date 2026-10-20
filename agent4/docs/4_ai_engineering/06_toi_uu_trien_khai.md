# 06 · Tối ưu triển khai: tốc độ, bộ nhớ, chi phí

> Phần lớn là **ước tính kỹ thuật** (đã tính tay) — cần đo thực tế; các số đo nhóm phải điền vào bảng ở cuối.

## 1. Ngân sách VRAM (GPU phát triển: RTX 4050 Laptop 6 GB)
**KV‑cache** cho Qwen3‑4B/8B (36 lớp, 8 đầu KV, head‑dim 128, fp16): 2 × 36 × 8 × 128 × 2 byte = **147.456 byte/token ≈ 0,144 MB/token**.
| Cấu hình | Trọng số | KV @4k | KV @8k | Tổng ≈ | Vừa 6 GB? |
|---|---|---|---|---|---|
| Qwen3‑4B‑2507 Q4_K_M | 2,5 GB | 0,6 GB | 1,2 GB | 3,1–3,7 GB (+đệm) | ✔ thoải mái |
| Qwen3‑8B Q4_K_M | 5,2 GB | 0,6 GB | 1,2 GB | 5,8–6,4 GB (+đệm) | ✘/biên: có thể phải đẩy một phần lớp sang CPU |
| Qwen3‑8B Q4_K_M + KV q8_0 | 5,2 GB | 0,3 GB | 0,6 GB | 5,5–5,8 GB | biên |
Hệ quả: trên GPU 6 GB, **4B‑2507 là mặc định thực tế**; 8B cần `num_gpu` cân nhắc, KV lượng tử hóa, hoặc GPU ≥ 12 GB.
(Thiết kế prompt ngắn ~1,5–2k token để `num_ctx` 4096–8192 là đủ.)

## 2. Độ trễ — nơi tiêu tốn
| Giai đoạn | Nguồn chi phí | Cách giảm |
|---|---|---|
| Prefill prompt (~1,5k token) | Tính lại mỗi lượt | **Giữ tiền tố cố định** (system + tool header) để KV cache dùng lại; đưa phần thay đổi (enum, ví dụ, câu hỏi) về cuối |
| Sinh lời gọi (~60–120 token) | Giải mã tuần tự | `num_predict` thấp; schema ngắn; khóa đơn giản |
| Truy vấn engine | DuckDB | Chỉ mục dạng cột, `gl_wide` đã sắp xếp theo ngày; chạy đồng thời ≥ 2 truy vấn |
| Sinh diễn giải (~80–150 token) | Giải mã | Giới hạn ≤ 2 câu; khối sự kiện tất định không tốn token |
| Verifier / sinh lại | Chạy lại | Chỉ sinh lại phần diễn giải, không gọi lại công cụ |
Mục tiêu: p50 ≤ 6 s trên 4B‑2507 / 6 GB; p95 ≤ 15 s.

## 3. Cấu hình Ollama gợi ý
```
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0        # giảm ~50% KV; kiểm tra chất lượng (H13)
OLLAMA_NUM_PARALLEL=1            # 6 GB: tránh nhân đôi KV; tăng khi VRAM thừa
OLLAMA_MAX_LOADED_MODELS=1
# mỗi request:
options: {temperature:0, top_k:20, top_p:0.8, num_ctx:8192, num_predict:384, repeat_penalty:1.05}
keep_alive: "30m"                # tránh nạp lại
```
Lưu ý: không đặt `num_ctx` thì Ollama dùng ngữ cảnh ngắn mặc định → prompt bị cắt âm thầm (lỗi phổ biến); luôn đặt rõ `num_ctx` và `num_predict`.

## 4. Lựa chọn máy chủ suy luận
| Lựa chọn | Khi nào | Ưu | Nhược |
|---|---|---|---|
| **Ollama** | Dev, demo, 1 DN | Dễ, đã có | Giải mã ràng buộc hạn chế (JSON schema có; grammar kém linh hoạt); song song hạn chế |
| **llama.cpp server** | Cần GBNF, kiểm soát sâu | Grammar mạnh, nhẹ | Tự quản lý |
| **vLLM** (GPU ≥ 16 GB) | Đa khách hàng, tải cao | Prefix caching, guided decoding (xgrammar), batching liên tục | Cần GPU lớn, cấu hình phức tạp |
| **Model nháp (speculative)** Qwen3‑0.6B | Giảm độ trễ sinh | Tăng tốc 1,5–2× (lý thuyết) | Phức tạp; đo trước |
Quyết định: dev bằng Ollama, đo song song llama.cpp (H3); sản xuất đa khách hàng cân nhắc vLLM.

## 5. Tối ưu retrieval & dữ liệu
- BM25 trong bộ nhớ (66 tài liệu) < 1 ms; embedding chỉ cho 66 mô tả + câu hỏi (CPU, ~10–20 ms/câu với model nhỏ).
- Few‑shot kNN: chỉ mục 300–1000 ví dụ, tính trước embedding.
- DuckDB: kết nối **một** per process, `threads` = số lõi; `gl_wide` sắp xếp theo `posting_date`; với 5–10 triệu dòng cân nhắc phân vùng Parquet theo tháng + `ANALYZE`; cache kết quả truy vấn theo `(metric, period, filters, view, data_version)` (TTL ngắn khi có giao dịch mới).
- **Vô hiệu hóa cache** khi `data_through` đổi hoặc có bút toán lùi ngày.

## 6. Chi phí vận hành mô hình (ước tính)
| Mục | Giá trị |
|---|---|
| Điện năng GPU mobile ~60–80 W khi suy luận | ≈ 0,05 kWh/giờ hoạt động thực; nhỏ so với khấu hao |
| Token/câu hỏi (mục tiêu) | ≤ 2.500 (vào+ra) |
| 1 DN, 300 câu/ngày | ≈ 0,75 triệu token/ngày — không có phí API khi tự lưu trữ |
| Đối chứng API (tham khảo) | cùng tải ở model cỡ lớn qua API: tính theo bảng giá tại thời điểm (không dùng mặc định) |

## 7. Giám sát khi chạy
Số liệu: độ trễ từng giai đoạn · tỷ lệ retry/verifier fallback · tỷ lệ hỏi lại/từ chối · tỷ lệ `suspicious_text` · lỗi engine theo loại · mức dùng VRAM. Cảnh báo khi `verifier_fallback` > 5% hoặc `call_omission` tăng đột biến sau khi đổi model/prompt.

## 8. Bảng ghi số đo — P2 thử nghiệm

**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở).

| Cấu hình | VRAM đỉnh lấy mẫu (MiB) | Prefill median (ms/call) | tok/s sinh | p50 / p95 E2E (ms) | TSA | Ghi chú |
|---|---:|---:|---:|---:|---:|---|
| 4B Q4 · ctx8192 · KV q8_0 | 3269 | 231.2 | 58.8 | 1810.5 / 4564.0 | 1.000 | TRAIN n=38; E1 n=10; latency n=30; API errors=0; length stops=0; context shifts=0 |
| 8B Q4 · ctx4096 · KV q8_0 | 4132 | 748.7 | 11.9 | 12161.9 / 14196.9 | 1.000 | TRAIN n=37; E1 n=10; latency n=30; API errors=0; length stops=0; context shifts=0 |
| 8B Q4 · ctx8192 · KV q8_0 | 4102 | 1208.2 | 10.1 | 13134.3 / 20325.0 | 1.000 | TRAIN n=38; E1 n=10; latency n=30; API errors=0; length stops=0; context shifts=0 |
| 8B think=on · đợi H4 | chưa đo | chưa đo | chưa đo | chưa đo | chưa đo | Không suy diễn số đo |

Lựa chọn ổn định trong phép thử hữu hạn: chưa có cấu hình8B thỏa điều kiện đã đo. Nguồn/điều kiện: `docs/5_handoff/measurements/p2_8b_stability_decision.json`. Không đồng nghĩa đã qua long soak hoặc G1.

Nguồn: `docs/5_handoff/measurements/p2_hardware_train.json`. Cùng mẫu TRAIN:10 E1,10 hội thoại E7,10 câu nhiều chỉ số,10 câu vì sao. k8, schema, hints bật, static3, think tắt. E2E n30 loại thời gian toàn hội thoại E7; n thực tế ghi từng dòng. Cold preload đo riêng trong JSON.

VRAM là đỉnh quan sát toàn GPU (gồm màn hình/tác vụ khác), lấy mẫu khoảng1 giây; không phải allocator peak. Máy dùng chung, chưa có kiểm soát tải nền hoặc long soak. TSA ở đây là TRAIN, không thay thế kết quả val/test hay chứng nhận G1. Chọn cấu hình8B ổn định theo API/context/truncation thực đo và xem độ đúng riêng; không suy diễn rằng n nhỏ bảo đảm mọi tải.
