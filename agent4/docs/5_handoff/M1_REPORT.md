# M1 — P1 thử nghiệm, 17/10/2026

**công thức chưa được kế toán duyệt (G0.7 mở).** G0.7 **CHƯA ĐẠT**; cả 22 chỉ số Must **cần duyệt trước pilot**. Không có chữ ký duyệt giả lập.

Đã đo **10/10 câu đầu trong `reference_v0/sample-questions.md` đúng** bằng CLI thật với Qwen 4B, và ghi đủ 10 trace JSONL. Dừng tại M1 theo yêu cầu; chưa thực hiện P2–P4 hoặc chứng nhận cổng G1/pilot.

## Phạm vi đo và cách chấm

- Chạy `python -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M --samples 10 --json --trace …` bằng `eval/smoke_m1.py`, giữ trạng thái hội thoại qua 10 câu, bật phần diễn giải định tính.
- Mỗi câu đi qua hints → BM25 retriever → LLM union schema → validator → ExecutionEngine chỉ đọc → khối sự kiện → verifier. LLM không có SQL/công cụ ghi và không cung cấp số để engine tính.
- Nhãn chỉ số/kỳ/khung/nhóm được chốt tường minh; giá trị kỳ vọng tính từ bảng gốc bằng `eval.oracle`, không lấy từ ExecutionEngine hay LLM. Kiểm tổng, đủ/không trùng dòng nhóm và từng giá trị; câu 2/8 kiểm kỳ so sánh, chênh lệch và phần trăm. Kiểm display trong câu trả lời, verifier, nhãn G0.7 và ID trace.
- Kho dev seed **20251**, `data_version=v2.0`, mốc **14/10/2026**, khóa sổ đến **08/2026**. Câu 2 so cùng số ngày quý 3 (01–14/07); câu 8 so 01–14/10/2025. Kỳ hiện tại vẫn mang nhãn tạm tính.
- Ollama **0.40.5**, Python **3.12.13**, context **4096**, T=0, think=False; model digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
- Token là `prompt_eval_count`/`eval_count` thực do Ollama trả về, cộng mọi lần gọi kể cả diễn giải bị chặn. Độ trễ từng câu đo quanh `CFOAgent.ask`, gồm hints/engine và retry, chưa gồm khởi động CLI. Không thêm warmup; trạng thái model cold/warm không được khống chế, nên không coi đây là benchmark cold-start hoặc so tốc độ có kiểm soát.

## Kết quả trước/sau — cùng 10 câu dev, cùng model

| Lượt | Thay đổi | Đúng | Token vào/ra | p50 / p95 (giây) | Lỗi câu trả lời |
|---|---|---:|---:|---:|---|
| [Lượt 1](measurements/m1-first/summary.json) | Ban đầu: prompt T1.5, state gửi mỗi lượt | 9/10 | 28,678 / 1,727 | 7.20 / 16.55 | Câu 5 chọn gross_margin_pct thay gross_profit |
| [Lượt 2](measurements/m1-second/summary.json) | Thêm đơn vị VND/%, quy tắc phân biệt; bọc description metadata | 8/10 | 29,984 / 1,532 | 4.30 / 14.20 | Câu 5 còn sai; câu 6 chọn explain thay bảng khoản mục |
| [Lượt 3](measurements/m1-third/summary.json) | Hints khớp thuật ngữ registry tường minh + validator; chỉ gửi state khi có kế thừa | 10/10 | 31,702 / 1,680 | 4.11 / 6.62 | Không có lỗi theo phép chấm 10 câu |

Các câu này là demo dev đã đọc và dùng để sửa lỗi, không phải held-out. Chưa đo ảnh hưởng trên toàn bộ 22 Must, chưa chứng minh tổng quát hóa hay lợi ích riêng của từng thay đổi. Lượt ba cải thiện các câu lỗi; p95 lấy nearest-rank trên chỉ 10 mẫu (bằng mẫu lớn nhất).

## Chi tiết lượt cuối

| Câu | Chỉ số / nhóm | Oracle = engine (VND, trừ câu 4 là %) | Token vào/ra | Giây |
|---:|---|---:|---:|---:|
| 1 | net_revenue | 12,556,551,000 | 3,158 / 163 | 6.622 |
| 2 | net_revenue + so quý trước | 12,556,551,000 | 3,976 / 224 | 4.510 |
| 3 | cogs / 6 tháng | 88,058,038,508 | 3,987 / 142 | 3.278 |
| 4 | gross_margin_pct | 22.575257 | 3,015 / 193 | 3.960 |
| 5 | gross_profit / 4 dòng sản phẩm | 2,834,673,614 | 3,662 / 198 | 4.177 |
| 6 | operating_expenses / 2 khoản mục | 51,023,296 | 3,409 / 196 | 4.083 |
| 7 | operating_profit / YTD | 4,373,464,381 | 1,967 / 75 | 1.915 |
| 8 | net_profit + so cùng kỳ | 2,778,050,318 | 3,906 / 228 | 4.582 |
| 9 | cash_and_equivalents | 3,187,443,878 | 1,684 / 55 | 1.550 |
| 10 | net_cash_flow | -4,345,494,331 | 2,938 / 206 | 4.136 |

Tổng **31,702 token vào / 1,680 token ra**, **36 lần gọi model**. Tổng thời gian trong 10 câu **38,812 giây**; cả driver CLI và chấm oracle **41.278 giây**. p50 **4.109 giây**, p95 **6.622 giây**.

## Lỗi quan sát và cơ chế suy biến

- Trong lượt cuối, model diễn giải vẫn sinh chữ số: **23 lần bị chặn** bởi NUMERIC_COMMENTARY (trong đó 2 lần còn có UNSUPPORTED_NUMBER). **7/10 câu** trả nguyên khối sự kiện sau khi hết số lần thử; 3 câu có diễn giải định tính hợp lệ. Toàn bộ 10 khối sự kiện qua verifier; không có số lạ từ các lần diễn giải bị chặn được trả cho người dùng. Đây là hạn chế chất lượng/chi phí diễn giải đã quan sát, chưa tối ưu thêm sau M1.
- Không có lời gọi schema/validator thất bại, LLM unavailable hay lỗi xác minh khối sự kiện trong lượt cuối. Trường mặc định/kỳ/nhóm vẫn được validator chuẩn hóa và ghi lời gọi trước/sau trong trace.
- Trước M1: hai thực thể nhận nhầm “kinh doanh” → phòng KD và “còn” → sản phẩm CON đã sửa và có test hồi quy. Hai lần DuckDB OutOfMemory được khắc phục bằng 4 threads/512MB và unload model sau integration test; không bỏ test. HTTP500 với 8B/context8192 được ghi nhận; context4096 dùng cho test thật và CLI, chưa chứng minh 8K ổn định.
- Lỗi Git ignore `data/` của monorepo từng bỏ sót fixture; đã backfill các file được theo dõi, helper chỉ force-add đường dẫn đã commit, không đẩy kho DuckDB. Chi tiết lịch sử ở `DECISIONS.md`.

## Kiểm chứng và giới hạn

Toàn bộ suite trước commit cuối: **2,586 passed, 0 skipped/failed**, **64.525 giây** theo JUnit (stdout pytest: 64,55s), bật `AGENT4_RUN_LLM=1` gồm cả 4B/8B thật. [Số đo test](measurements/t1_10_tests.json); XML tại `artifacts/t1_10-final-pytest.xml` trong workspace. Không bỏ test sau lỗi bộ nhớ.

- Unit/component: retriever smoke dev 100 câu recall@8=100%; guardrail 40 attack/100 benign, A8 kho thật; verifier 320 lỗi tiêm/200 diễn đạt đúng. Đây là những tập test hữu hạn, không thay cho đánh giá lớn E1–E10.
- M1 giữ một chỉ số chính mỗi lượt; chưa hỗ trợ đủ câu hỏi nhiều chỉ số. Bảng hiển thị tối đa 8 dòng và có nhãn cắt; 3 bảng trong 10 câu này chỉ có 6/4/2 dòng nên không bị cắt.
- Verifier kiểm số, đơn vị, kỳ, nhãn và anchor tất định; chưa chứng minh mọi quan hệ ngữ nghĩa/nhân quả trong văn bản tự do. Diễn giải bị giới hạn định tính.
- **Chưa đo:** bộ đánh giá lớn, held-out seed 71/9001, chất lượng trả lời 8B, tải đồng thời/quy mô đầy đủ, mức sẵn sàng pilot. **Chưa có:** kế toán duyệt G0.7, API/UI/ops approval P3, pilot P4.
- Phiếu kế toán [một trang, 22 Must](FORMULA_REVIEW_ONE_PAGE.pdf); bảng kỹ thuật [66 chỉ số](FORMULA_REVIEW.md) vẫn giữ nguyên hồ sơ chờ duyệt.

## Bằng chứng và chạy lại

- [Summary lượt cuối](measurements/m1-third/summary.json), [10 câu trả lời](measurements/m1-third/responses.jsonl), [10 trace JSONL](measurements/m1-third/trace.jsonl). Giữ cả lượt 1 và 2 để xem lỗi ban đầu.
- Mỗi trace có ID, UTC timestamp, bước, preview/hash prompt, lời gọi, lineage, lỗi verifier, token và ms; không có raw SQL.

```powershell
$env:AGENT4_RUN_LLM='1'
./.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=artifacts/t1_10-final-pytest.xml
./.venv/Scripts/python.exe -X utf8 -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M
# Driver yêu cầu run-id mới, không ghi đè chứng cứ cũ:
./.venv/Scripts/python.exe -X utf8 -m eval.smoke_m1 --run-id m1-repeat
```

**công thức chưa được kế toán duyệt (G0.7 mở).** Dừng tại M1 thử nghiệm; G0.7 vẫn **CHƯA ĐẠT**.
