# 01 · Metric đánh giá kỹ thuật

> Nguyên tắc: **đo từng tầng riêng**, rồi đo end‑to‑end. Một agent đúng 90% end‑to‑end nhưng "đúng nhờ may" ở tầng định tuyến sẽ gãy khi đổi model. Ngưỡng là **mục tiêu thiết kế** (chưa có kết quả đo) trừ khi ghi khác.

## 1. Sơ đồ tầng đo
```
Câu hỏi ─► [L1 Hiểu ý] ─► [L2 Chọn công cụ] ─► [L3 Tham số] ─► [L4 Lõi tính] ─► [L5 Diễn giải] ─► [L6 Xác minh] ─► Trả lời
            E1/E3/E4      E1                    E2             V1–V10           E6                E6/E8
```

## 2. Metric theo tầng
### L1–L2. Hiểu ý & chọn công cụ (E1, E3, E4, E5)
| Metric | Định nghĩa | Mục tiêu |
|---|---|---|
| Tool‑selection accuracy (TSA) | Tỷ lệ mẫu chọn đúng công cụ + đúng `metric` | ≥ 95% (có thu hẹp công cụ) |
| Top‑k recall của bộ thu hẹp | Chỉ số đúng nằm trong k=8 ứng viên | ≥ 99% |
| View accuracy | Đúng `mgmt/tax` | ≥ 98% (kế hoạch nhóm) |
| Clarify precision / recall | Hỏi lại đúng lúc / không bỏ sót mơ hồ | ≥ 90% / ≥ 90% |
| Refuse recall / over‑refusal | Từ chối đúng ngoài phạm vi / từ chối nhầm câu hợp lệ | ≥ 98% / ≤ 3% |
| Hallucinated‑tool rate | Gọi công cụ không tồn tại | 0% |

### L3. Tham số (E2)
| Metric | Định nghĩa | Mục tiêu |
|---|---|---|
| Arg exact‑match | Toàn bộ tham số khớp sau chuẩn hóa | ≥ 90% |
| Period F1 | Khoảng ngày khớp (so khoảng đã resolve) | ≥ 97% |
| Entity resolution acc | Tên mờ → đúng mã | ≥ 95% |
| Group‑by acc | Chiều phân rã đúng | ≥ 95% |
| Compare‑mode acc | Đúng `previous_period` / `same_period_last_year` | ≥ 97% |
| Schema‑valid rate | Lời gọi hợp lệ JSON schema ngay lần đầu | ≥ 99% (có ràng buộc) |

### L4. Lõi tính (kiểm thử xác định, không có LLM)
| Metric | Định nghĩa | Mục tiêu |
|---|---|---|
| Golden pass rate | Chỉ số × kỳ khớp oracle SQL độc lập (dung sai 0 đồng với VND, 1e‑6 với tỷ số) | **100%** |
| Invariant pass | Phương trình kế toán, tổng nhóm = tổng, đối soát sổ chi tiết | 100% |
| Reproducibility | Cùng seed → cùng băm | 100% |
| Query latency | p95 trên kho 150k dòng / 5M dòng | ≤ 1 s / ≤ 5 s |

### L5–L6. Diễn giải & xác minh (E6, E8)
| Metric | Định nghĩa | Mục tiêu |
|---|---|---|
| **Numeric faithfulness** | Mọi số trong câu trả lời thuộc tập số của kết quả công cụ (dung sai làm tròn) | **100%** sau verifier |
| Unsupported‑claim rate | Mệnh đề nhân quả/nguyên nhân không có số làm cơ sở | ≤ 2% |
| Verifier recall (lỗi tiêm vào) | Bắt ≥ 99% lỗi số/đơn vị/kỳ | ≥ 99% |
| Verifier false‑positive | Chặn nhầm câu đúng | ≤ 2% |
| Caveat coverage | Câu trả lời có nhãn kỳ/khung/tạm tính khi cần | 100% |
| Injection block rate | Ca tiêm nhiễm không làm đổi hành vi/số | 100% |
| Unauthorized action rate | Hành động thực thi không qua duyệt | 0 |

### End‑to‑end
| Metric | Định nghĩa | Mục tiêu |
|---|---|---|
| **Answer accuracy** | Số + kỳ + khung đúng (so oracle) trên E‑gold | ≥ 90% (kế hoạch nhóm) |
| Task success (đa lượt) | E7 kịch bản hoàn thành đúng | ≥ 85% |
| Right‑behavior rate | Đúng hành vi trả lời/hỏi lại/từ chối | ≥ 93% |
| Latency p50 / p95 | Từ lúc hỏi đến câu trả lời cuối | ≤ 6 s / ≤ 15 s (GPU 6 GB) |
| Tokens/Q | Token vào+ra trung bình | ≤ 2.500 |
| Tool calls/Q | Số lần gọi trung bình | ≤ 1,6 |
| Retry rate | Tỷ lệ cần thử lại do lỗi lược đồ/verifier | ≤ 10% |

## 3. Cách chấm chi tiết
1. **Chuẩn hóa trước khi so**: period token ↔ khoảng ngày (qua `resolve_period`), thực thể → mã, thứ tự khóa JSON bỏ qua, giá trị mặc định có thể bỏ.
2. **Dung sai số**: VND tuyệt đối 0; hiển thị làm tròn (tỷ 2 chữ số, triệu 1–2 chữ số) được chấp nhận nếu |giá trị − làm tròn| ≤ nửa đơn vị hiển thị; `%` ±0,05 điểm.
3. **Faithfulness**: dùng `formatting.extract_numbers` → quy về VND/%/ngày → khớp với tập số (giá trị, các hàng bảng, so sánh, thành phần) của *mọi* kết quả công cụ trong lượt; số "plain" nhỏ (số lượng, năm) được phép nếu thuộc kỳ/đếm.
4. **Bootstrap 95% CI** cho mọi tỷ lệ; báo cáo kèm n.
5. **Phân tầng**: báo kết quả theo nhóm câu hỏi (Q1–Q10), độ khó, nhiễu ngôn ngữ, model.

## 4. Metric đặc thù cho model nhỏ (so sánh Qwen3‑8B vs Qwen3‑4B‑2507)
| Metric | Ý nghĩa |
|---|---|
| Call‑omission rate | Bỏ qua việc gọi công cụ khi lẽ ra phải gọi (lỗi phổ biến của model 7–8B) |
| Wrong‑field rate | Sai tên trường/enum |
| Thinking overhead | Token & giây thêm khi bật `think` so với tắt |
| Stability @ T=0 | Chạy lặp 5 lần cho cùng câu → tỷ lệ cùng lời gọi |
| Context sensitivity | Độ chính xác khi tăng độ dài hội thoại (2/5/10 lượt) |
| Quantization drop | Chênh lệch giữa Q4_K_M / Q5 / Q8 |

## 5. Metric cho Text‑to‑SQL dự phòng (E9)
Execution accuracy · AST‑safety (0 câu ghi/ngoài whitelist) · Refusal‑when‑out‑of‑schema ≥ 90% · Giới hạn dòng/thời gian 100% tuân thủ. **Kỳ vọng thực tế:** thấp hơn đường chính; chỉ bật khi không có chỉ số phù hợp.
