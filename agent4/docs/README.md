# Tài liệu Agent 4 — "CFO ảo" (Trợ lý điều hành tài chính tức thời)

> Nhánh `agent4-Khanh` · Cập nhật 14/10/2026 · Ngôn ngữ: tiếng Việt.
> **Trạng thái một câu:** dữ liệu + lõi chỉ số đã xây xong và có test hợp đồng; **agent LLM, đánh giá, sản phẩm chưa xây** — toàn bộ giao việc ở `5_handoff/`.

## Cách đọc theo vai trò
| Bạn là… | Đọc theo thứ tự |
|---|---|
| Lãnh đạo / người ra quyết định | `1_business_analyst/01` → `3_evaluation/03` (chi phí–lợi ích) → `5_handoff/01` (trạng thái thật) |
| Business analyst / nhà nghiên cứu kinh tế | `1_business_analyst/01–07` → `3_evaluation/02,03` |
| Data scientist / data analyst | `2_data/01–08` |
| Tester / QA / người đánh giá | `3_evaluation/01–05` → `2_data/07` |
| AI engineer / researcher | `4_ai_engineering/01–06` |
| **Coding agent / dev tiếp nhận** | `5_handoff/00_START_HERE.md` → `01` → `02` → thẻ việc `03–05` |

## Mục lục
### 1_business_analyst — Kinh tế, tài chính, yêu cầu sản phẩm
| File | Nội dung |
|---|---|
| `01_tom_tat_dieu_hanh` | Sản phẩm, nguyên tắc, giá trị, trạng thái (1 trang) |
| `02_van_de_va_noi_dau` | Phát biểu bài toán, nỗi đau theo vai trò, bằng chứng (có phân loại tin cậy), backlog vấn đề |
| `03_phan_tich_kinh_te_thi_truong` | Bối cảnh vĩ mô/pháp lý, cầu, cạnh tranh, cách thị trường đánh giá, định cỡ thị trường, mô hình kinh doanh |
| `04_nguoi_dung_va_nhu_cau` | Persona, hành trình, taxonomy câu hỏi, truy vết nhu cầu → chỉ số |
| `05_yeu_cau_va_pham_vi` | FR/NFR, phạm vi, user stories |
| `06_rui_ro_va_phap_ly` | Ma trận rủi ro, pháp lý (TT99/TT133, Luật AI, dữ liệu cá nhân), ứng phó sự cố |
| `07_nguon_tham_khao` | Nguồn và mức tin cậy; việc xác minh còn tồn |

### 2_data — Dữ liệu
| File | Nội dung |
|---|---|
| `01_chien_luoc_du_lieu` | Dual‑track, nguyên tắc, lớp dữ liệu, năng lực ↔ dữ liệu |
| `02_nguon_du_lieu_that_va_danh_gia` | Nguồn có sẵn: dùng/không dùng, lý do |
| `03_doanh_nghiep_mau_va_luoc_do` | Hồ sơ "Minh Phát", kho DuckDB, bảng/cột, đặc thù TT133, hai khung |
| `04_quy_tac_sinh_du_lieu` | Mọi quy tắc & tham số của bộ mô phỏng |
| `05_hard_case_va_kich_ban` | A1–A10 + cấu trúc + hard case dự kiến |
| `06_quy_mo_va_ket_hop_that_synthetic` | Mở rộng đa công ty/quy mô lớn; hiệu chỉnh từ dữ liệu thật; fidelity |
| `07_bo_du_lieu_danh_gia` | Hợp đồng dữ liệu E1–E12, ví dụ bản ghi, cách sinh |
| `08_kiem_dinh_chat_luong_du_lieu` | Đã kiểm gì, còn thiếu gì, giới hạn |

### 3_evaluation — Đánh giá & kinh tế
| File | Nội dung |
|---|---|
| `01_metric_ky_thuat` | Metric theo tầng, mục tiêu, cách chấm |
| `02_metric_kinh_te_nghiep_vu` | KPI kinh tế/nghiệp vụ, thiết kế pilot trước–sau |
| `03_mo_hinh_chi_phi_loi_ich` | **Phép tính chi phí xây & lợi ích trước/sau**, 3 kịch bản, độ nhạy, đa khách hàng |
| `04_ke_hoach_kiem_thu` | Kim tự tháp test, oracle độc lập, red‑team, quy trình |
| `05_tieu_chi_nghiem_thu` | Cổng G0/G1/G2, định nghĩa "xong" |

### 4_ai_engineering — Phương pháp & hệ thống
| File | Nội dung |
|---|---|
| `01_kien_truc_tong_the` | Sơ đồ khối, phân chia trách nhiệm, hợp đồng dữ liệu, suy biến |
| `02_chien_luoc_model_nho_qwen` | Lỗi của model ≤ 10B và cách chặn; prompt; thinking; tinh chỉnh |
| `03_lop_chi_so_va_cong_cu` | 66 chỉ số, API lõi, bộ công cụ cho LLM (hợp đồng) |
| `04_guardrails_xac_minh_phe_duyet` | Phạm vi/quyền, tiêm nhiễm, **verifier số**, phê duyệt, nhật ký |
| `05_ke_hoach_thi_nghiem` | 16 giả thuyết, biến, kỳ vọng, quy tắc quyết định, quét tham số |
| `06_toi_uu_trien_khai` | VRAM, độ trễ, Ollama/llama.cpp/vLLM, bảng số đo cần điền |

### 5_handoff — Giao việc
| File | Nội dung |
|---|---|
| `00_START_HERE` | Bắt đầu: thứ tự đọc, lệnh đầu tiên, 7 quy tắc |
| `01_hien_trang_va_khoang_trong` | Có/chưa có, bản đồ mã, quyết định đã chốt, lỗi đã biết |
| `02_ke_hoach_cong_viec` | WBS, phụ thuộc, đường găng, mốc |
| `03_the_viec_p0_p1_loi_va_agent` | Thẻ chi tiết: kiểm chứng lõi + xây agent |
| `04_the_viec_p2_du_lieu_danh_gia_thi_nghiem` | Thẻ chi tiết: sinh E1–E10, runner, thí nghiệm |
| `05_the_viec_p3_p4_san_pham_va_pilot` | Thẻ chi tiết: ops/approval, API, UI, bản tin, mock A1/2/3, SQL, pilot |
| `06_runbook_moi_truong` | Cài đặt, biến môi trường, sự cố thường gặp |
| `FORMULA_REVIEW.md` | Bảng 65 chỉ số để rà soát công thức (sinh tự động) |
| `DECISIONS.md` | Nhật ký quyết định |

## Quy ước ký hiệu trong tài liệu
✅ đã có & đã kiểm · ⏳ chưa làm · ❌ không có · 🔎 cần đối chiếu văn bản gốc · **[Giả định]** số/điều kiện do nhóm đặt, cần xác thực · Tin cậy A/B/C (xem `1_business_analyst/07`).
