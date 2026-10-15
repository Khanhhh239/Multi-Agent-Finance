# 05 · Yêu cầu chức năng, phi chức năng và phạm vi

## 1. Yêu cầu chức năng (FR)
| ID | Yêu cầu | Ưu tiên | Trạng thái hiện tại |
|---|---|---|---|
| FR‑01 | Nhận câu hỏi tiếng Việt (có/không dấu, viết tắt) và trả lời bằng tiếng Việt tự nhiên | Must | ⏳ chưa có agent loop |
| FR‑02 | Chọn **đúng chỉ số** từ thư viện 66 chỉ số bằng function calling | Must | ✅ thư viện / ⏳ router LLM |
| FR‑03 | Phân giải thời gian tất định ("tháng này", "quý trước", "6 tháng gần nhất", "từ đầu năm", "cùng kỳ năm trước") | Must | ✅ `engine/periods.py` |
| FR‑04 | Phân giải tên thực thể mờ (khách, NCC, chi nhánh, mặt hàng, phòng ban) → mã; nhiều ứng viên thì hỏi lại | Must | ✅ `ExecutionEngine.resolve_entity` |
| FR‑05 | Luôn kèm: số, đơn vị, kỳ, **trạng thái khóa sổ**, mốc dữ liệu (as‑of), khung dữ liệu (quản trị/thuế) | Must | ✅ trong kết quả engine |
| FR‑06 | So sánh kỳ trước / cùng kỳ năm trước; kỳ dở dang so **cùng số ngày** | Must | ✅ |
| FR‑07 | Phân rã theo chiều (tháng, quý, chi nhánh, nhóm SP, khách, NCC, mặt hàng, khoản mục, phòng ban, nhân viên, tài khoản) | Must | ✅ (chiều hỗ trợ theo từng chỉ số) |
| FR‑08 | "Xem cách tính": công thức, tài khoản, tổng theo TK, chứng từ lớn nhất | Must | ✅ `ExecutionEngine.explain` (chưa có UI) |
| FR‑09 | Hỏi lại khi mơ hồ (kèm 2–3 lựa chọn); từ chối khi ngoài phạm vi | Must | ⏳ |
| FR‑10 | **Citation verifier**: mọi số trong câu trả lời phải khớp kết quả công cụ | Must | ⏳ (có sẵn `extract_numbers`) |
| FR‑11 | Validator khung dữ liệu: câu hỏi thuế → `v_tax`; điều hành → `v_mgmt`; chặn gọi sai | Must | ✅ ở engine (chặn view không hợp lệ) / ⏳ ở agent |
| FR‑12 | Chống tiêm nhiễm lệnh từ dữ liệu (diễn giải chứng từ là *dữ liệu*, không phải chỉ dẫn) | Must | ⏳ (dữ liệu mẫu đã cài ca A8) |
| FR‑13 | Đề xuất hành động → bảng `pending_approvals` → người duyệt → API tất định → `audit_log` | Should | ⏳ |
| FR‑14 | Hội thoại nhiều lượt (nhớ kỳ, bộ lọc, chỉ số của lượt trước) | Should | ⏳ |
| FR‑15 | Bản tin điều hành tuần: tiền, nợ quá hạn, chi phí tăng, nghĩa vụ 15 ngày, bất thường | Should | ⏳ |
| FR‑16 | Orchestrator gọi song song Agent 1/2/3 (dự báo, bất thường, thuế) khi câu hỏi tổng hợp | Should | ⏳ (mock adapter) |
| FR‑17 | Text‑to‑SQL chỉ‑đọc dự phòng (whitelist bảng/cột, parse AST, giới hạn dòng/thời gian, chạy rồi vẫn qua verifier) | Could | ⏳ |
| FR‑18 | Giọng nói, Zalo OA, biểu đồ | Could | ⏳ |

## 2. Yêu cầu phi chức năng (NFR)
| ID | Nhóm | Yêu cầu | Cách đo |
|---|---|---|---|
| NFR‑A1 | Chính xác | **0 số sai/không nguồn** lọt tới người dùng (trên bộ kiểm thử) | verifier + `E6` |
| NFR‑A2 | Chính xác | Độ chính xác trả lời bộ 300 câu ≥ 90% (so SQL chạy tay) | `3_evaluation/01` |
| NFR‑P1 | Hiệu năng | p50 ≤ 6 s, p95 ≤ 15 s mỗi câu đơn trên GPU 6 GB (Qwen3‑4B/8B Q4) | đo trên máy dev |
| NFR‑P2 | Hiệu năng | Truy vấn chỉ số ≤ 1 s trên kho 150k dòng; ≤ 5 s trên 5 triệu dòng | benchmark engine |
| NFR‑S1 | Bảo mật | Model chạy tại chỗ; không gửi sổ cái ra dịch vụ ngoài mặc định | kiểm tra mạng |
| NFR‑S2 | Bảo mật | Phân quyền: CEO/CFO toàn bộ; GĐ chi nhánh chỉ chi nhánh/nhân viên của mình (row‑level filter bắt buộc ở engine) | test phân quyền |
| NFR‑S3 | Bảo mật | Kết nối DB **chỉ‑đọc**; agent không có công cụ ghi vào sổ cái | cấu hình + test |
| NFR‑S4 | An toàn | 100% tấn công tiêm nhiễm trong bộ red‑team bị chặn | `E8` |
| NFR‑T1 | Kiểm toán | Mỗi câu trả lời có `lineage_id`, truy vết tới chứng từ; mọi hành động có nhật ký bất biến | test |
| NFR‑R1 | Tin cậy | Lõi chạy được khi LLM lỗi (chế độ "tra chỉ số" bằng form) | test suy biến |
| NFR‑U1 | Trải nghiệm | Số hiển thị dạng Việt Nam (tỷ/triệu, dấu phẩy thập phân), có nhãn tạm tính | review UI |
| NFR‑C1 | Tuân thủ | Nhãn "AI‑generated"; con người quyết định cuối; log theo luật AI/dữ liệu cá nhân | rà soát pháp lý |

## 3. Phạm vi
**Trong phạm vi v1 (đến demo)**
- Một doanh nghiệp, TT133, tiền VND, dữ liệu mô phỏng + connector CSV/DuckDB.
- Hỏi–đáp chỉ số, so sánh, phân rã, công nợ, dòng tiền lịch sử, thuế (ước tính), bất thường mức "quy tắc".
- Hội thoại nhiều lượt, bản tin tuần, đề xuất hành động có phê duyệt, nhật ký kiểm toán.

**Ngoài phạm vi v1**
- Dự báo (Agent 1), phát hiện gian lận học máy (Agent 2), diễn giải luật thuế (Agent 3) — chỉ có *mock adapter* để thử orchestration.
- Đa tiền tệ, hợp nhất tập đoàn, kế toán TT200/TT99 đầy đủ (cấu trúc đã chuẩn bị: hỗ trợ mã 521/641).
- Thực thi ghi dữ liệu vào ERP; tự động nộp thuế/thanh toán.

## 4. User stories tiêu biểu (kèm tiêu chí chấp nhận ngắn)
| US | Là… tôi muốn… | Chấp nhận khi |
|---|---|---|
| US‑1 | CEO — hỏi "doanh thu tháng này" | Trả đúng số lũy kế đến as‑of, ghi "tạm tính – chưa khóa sổ (10/2026)", so sánh cùng số ngày với tháng trước |
| US‑2 | CEO — "khách nào nợ nhiều nhất" | Top‑N có số dư, tuổi nợ lớn nhất; tổng khớp `ar_balance` |
| US‑3 | KTT — "vì sao lợi nhuận quý này thấp" | Agent gọi ≥ 2 công cụ (giá vốn/biên theo SP, chi phí tăng), nêu nguyên nhân có số từ công cụ, không suy diễn ngoài dữ liệu |
| US‑4 | GĐ chi nhánh — "công nợ khách của tôi" | Chỉ thấy dữ liệu chi nhánh mình; hỏi dữ liệu chi nhánh khác bị từ chối |
| US‑5 | CEO — "Lãi bao nhiêu?" | Agent hỏi lại: lợi nhuận gộp / trước thuế / sau thuế? kỳ nào? |
| US‑6 | CEO — "xóa chứng từ lệch đi" | Agent từ chối thực thi, chỉ đề xuất rà soát qua kế toán |
