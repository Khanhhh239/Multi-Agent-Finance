# 01 · Tóm tắt điều hành — Agent 4 "CFO ảo"

> Đọc 3 phút. Chi tiết xem các file 02–07 cùng thư mục.

## Sản phẩm là gì
Một **trợ lý hội thoại tiếng Việt** cho chủ doanh nghiệp / CEO / CFO của doanh nghiệp vừa và nhỏ (DNVVN), trả lời các câu hỏi tài chính điều hành ("tháng này lãi bao nhiêu?", "khách nào đang nợ nhiều nhất?", "chi phí nào tăng bất thường?") **ngay trên dữ liệu chưa khóa sổ**, bằng **số liệu có nguồn, có mốc thời gian, truy vết được về từng chứng từ**.

## Nguyên tắc thiết kế cốt lõi
| # | Nguyên tắc | Hệ quả thiết kế |
|---|---|---|
| 1 | **Lõi tất định – vỏ LLM** | Mọi con số do thư viện chỉ số (SQL kiểm định) tính; LLM chỉ hiểu câu hỏi, chọn công cụ, diễn giải. |
| 2 | **Không bao giờ bịa số** | Citation verifier chặn số không có trong kết quả công cụ; mơ hồ thì hỏi lại, ngoài phạm vi thì từ chối. |
| 3 | **Một nguồn – hai khung** | Khung *quản trị* (toàn bộ giao dịch) và khung *thuế* (chỉ khoản được trừ) cùng từ một sổ cái; validator cấm trộn. |
| 4 | **Người quyết định** | Mọi hành động chỉ ở dạng *đề xuất → người duyệt → API tất định thực thi → nhật ký kiểm toán*. |
| 5 | **Chạy được trên model ≤ 10B** | Qwen3‑8B / Qwen3‑4B‑Instruct tại chỗ (dữ liệu tài chính không rời doanh nghiệp). |

## Vì sao có giá trị (số liệu minh họa từ doanh nghiệp mẫu)
Doanh nghiệp mẫu "Minh Phát" (dữ liệu tổng hợp, xem `2_data/03`): doanh thu 2025 ≈ **185,6 tỷ đồng**, lợi nhuận sau thuế **1,57 tỷ (0,85%)**, phải thu **47,6 tỷ** trong đó **9,2 tỷ quá hạn > 30 ngày**, riêng một khách hàng chiếm **8,05 tỷ**; vay ngân hàng **25,1 tỷ**. Biên lợi nhuận mỏng + vốn lưu động lớn ⇒ *một vài ngày DSO hay một khoản nợ xấu* quyết định lãi hay lỗ. Đó là nơi một "CFO ảo" trả lời tức thời tạo giá trị.

## Giá trị kinh tế tóm tắt (chi tiết: `3_evaluation/03`)
| Kịch bản | Lợi ích / năm | Chi phí vận hành / năm | Hoàn vốn (xây riêng cho 1 DN) |
|---|---|---|---|
| Thận trọng | ≈ 0,26 tỷ | ≈ 0,18 tỷ | > 10 năm (không khả thi nếu xây riêng) |
| Cơ sở | ≈ 0,57 tỷ | ≈ 0,18 tỷ | ≈ 2,3 năm |
| Lạc quan | ≈ 0,87 tỷ | ≈ 0,18 tỷ | ≈ 1,3 năm |

**Kết luận trung thực:** với một doanh nghiệp đơn lẻ, chỉ khả thi nếu giảm được ≥ ~1,2 ngày DSO *và* tiết kiệm giờ kế toán; mô hình thương mại hợp lý là **đa khách hàng (SaaS / tích hợp vào phần mềm kế toán)** — từ ~10 khách hàng, chi phí phân bổ ≈ 90 triệu/khách/năm.

## Trạng thái hiện tại (14/10/2026)
- ✅ **Dữ liệu**: bộ sinh doanh nghiệp mẫu hoàn chỉnh (140.583 dòng sổ cái, đối soát sổ chi tiết = sổ cái 100%).
- ✅ **Lõi chỉ số**: 66 chỉ số, bộ phân giải thời gian, so sánh kỳ, truy vết, trạng thái khóa sổ; 12/12 test hợp đồng v0 xanh.
- ⏳ **Chưa làm**: vòng lặp agent + công cụ + guardrail + verifier + API/UI + bộ đánh giá + chạy thử Qwen. Toàn bộ giao việc ở `5_handoff/`.

## Bản đồ tài liệu
`1_business_analyst` (file này) → `2_data` → `3_evaluation` → `4_ai_engineering` → `5_handoff`.
