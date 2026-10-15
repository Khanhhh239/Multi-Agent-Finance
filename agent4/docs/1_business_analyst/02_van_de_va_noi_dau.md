# 02 · Vấn đề, nỗi đau và bằng chứng

## 1. Phát biểu bài toán
> Làm thế nào để **cung cấp câu trả lời tài chính điều hành tức thời, chính xác và có trích dẫn nguồn, ngay cả khi dữ liệu chưa khóa sổ**, nhằm giúp **chủ doanh nghiệp / Ban điều hành DNVVN** **ra quyết định kịp thời dựa trên dữ liệu gần thời gian thực thay vì chờ chu kỳ báo cáo thủ công nhiều ngày**?

## 2. Chuỗi nguyên nhân – hậu quả
```
Khóa sổ thủ công (6–10+ ngày)  ──►  Báo cáo quản trị "đóng băng"
Dữ liệu rải rác (ERP + Excel)   ──►  Mỗi người một con số; không biết số lấy từ đâu
ERP chỉ ghi chép, không "trả lời" ──► CEO phải nhờ kế toán → hàng đợi yêu cầu ad-hoc
Công cụ chat AI chung (NL2SQL tự do) ──► Sai số nhưng nghe rất tự tin → mất niềm tin
                               ▼
        Quyết định chậm / dựa số cũ: giãn nợ muộn, nợ xấu phình, thiếu tiền bất ngờ,
        bỏ lỡ chi phí tăng bất thường, nộp chậm thuế
```

## 3. Nỗi đau theo vai trò
| Vai trò | Nỗi đau cụ thể | Hệ quả đo được |
|---|---|---|
| **CEO / chủ DN** | Muốn biết "tháng này lãi bao nhiêu, còn bao nhiêu tiền" phải chờ kế toán; sợ con số không khớp giữa các báo cáo. | Quyết định trễ nhịp báo cáo; tâm lý "không tin số". |
| **Kế toán trưởng / kế toán tổng hợp** | Bị hỏi ad-hoc liên tục (lấy số, đối chiếu, dựng Excel) khiến việc chính (hạch toán, kê khai) bị gián đoạn. | Giờ làm cho báo cáo lặp lại; rủi ro sai sót khi làm vội. |
| **Giám đốc chi nhánh / trưởng kinh doanh** | Không tự tra được công nợ khách mình phụ trách, mức đạt kế hoạch. | Thu hồi nợ chậm; thiếu cảnh báo sớm. |
| **Chủ DN lo dòng tiền** | Không biết tiền đủ chi bao lâu, tuần tới phải trả những gì. | Phải đi vay gấp (mẫu: 10 lần giải ngân hạn mức trong 21 tháng). |

## 4. Bằng chứng (đã phân loại độ tin cậy)
Ký hiệu: **A** = nguồn gốc đã kiểm chứng; **B** = trích lại từ tài liệu nhóm / báo chí, chưa đọc nguồn gốc; **C** = số suy ra từ dữ liệu mô phỏng (minh họa, *không* phải thực tế thị trường).

| # | Bằng chứng | Giá trị | Độ tin cậy | Ý nghĩa |
|---|---|---|---|---|
| E1 | Thời gian khóa sổ trung vị (APQC) | 6,4 ngày làm việc; nhóm chậm > 10 ngày | B (từ `Agent4.md` của nhóm) | Độ trễ là hệ thống, không cá biệt. |
| E2 | Tỷ lệ doanh nghiệp vẫn dùng Excel làm công cụ chính | 94% (khảo sát G‑Accon 2026) | B | Khoảng trống công nghệ lớn. |
| E3 | NL2SQL tự do trên schema doanh nghiệp thật (Spider 2.0) | GPT‑4o 10,1% / o1‑preview 17,1% | B | Không thể để LLM tự viết SQL tài chính → cần lớp chỉ số kiểm định. |
| E4 | Trợ lý ảo MISA AVA (VnExpress/VietNamNet 2024) | công bố: tra cứu nhanh hơn ~5 lần, tiết kiệm ~80% thời gian tìm báo cáo | B (số tự công bố của nhà cung cấp) | Người dùng kế toán VN *đã chấp nhận* trợ lý ra lệnh bằng ngôn ngữ tự nhiên. |
| E5 | Zalo OA tiếp cận > 74 triệu người dùng | 74 triệu | B | Kênh đẩy bản tin chủ động phù hợp thói quen VN. |
| E6 | DNVVN chiếm tuyệt đại đa số doanh nghiệp VN | nguồn khác nhau nêu 97–98%; ~60% lao động; ~40% GDP | B (số thay đổi theo nguồn) | Quy mô thị trường lớn nhưng năng lực tài chính‑IT yếu. |
| E7 | Chuyển đổi số SME | ~75% mới ở giai đoạn bắt đầu/số hóa một phần (báo cáo không nêu rõ năm) | B | Nhu cầu tự phục vụ dữ liệu nhưng chưa có hạ tầng. |
| E8 | Doanh nghiệp mẫu: DSO | 53 ngày (2025) → 62 ngày (Q3/2026) | C | Mô phỏng một DN phân phối có khách lớn mất khả năng trả. |
| E9 | Doanh nghiệp mẫu: nợ quá hạn > 30 ngày | 9,17 tỷ / phải thu 47,63 tỷ (19%); 83,6% do 1 khách (7,67 tỷ) | C | Cho thấy giá trị cảnh báo sớm tập trung vào *ít khách lớn*. |
| E10 | Doanh nghiệp mẫu: biên lợi nhuận sau thuế | 0,85% (2025) | C | Thặng dư mỏng ⇒ nhạy với DSO, nợ xấu, chi phí tăng. |

> **Giới hạn:** các số E1–E7 chưa được đối chiếu nguồn gốc trong phiên này (chỉ E6–E7 tìm lại được qua tìm kiếm web, nguồn không thống nhất). Trước khi đưa vào hồ sơ chính thức cần tra APQC, G‑Accon, Spider 2.0 và công bố MISA trực tiếp (xem `07_nguon_tham_khao.md`).

## 5. Các vấn đề cần giải quyết (problem backlog)
| ID | Vấn đề | Năng lực sản phẩm giải quyết | Ưu tiên |
|---|---|---|---|
| P1 | Không có kênh hỏi–đáp tức thời về số liệu | Hội thoại + 66 chỉ số (doanh thu, lãi, tiền, công nợ, tồn kho, thuế…) | Must |
| P2 | Số liệu không kiểm chứng được, sợ "ảo giác" | Truy vết ("Xem cách tính"), verifier, nhãn as‑of | Must |
| P3 | Dữ liệu chưa khóa sổ → sợ dùng số tạm | Nhãn "Tạm tính – chưa khóa sổ (tháng …)" tự động | Must |
| P4 | Trộn số quản trị với số thuế | Hai khung `v_mgmt`/`v_tax`, validator cứng | Must |
| P5 | Câu hỏi mơ hồ ("lãi" là lãi gì?) | Hỏi lại 2–3 lựa chọn, không đoán | Must |
| P6 | Thiếu cảnh báo chủ động | Bản tin điều hành hằng tuần (chi phí tăng, nợ quá hạn, nghĩa vụ sắp tới) | Should |
| P7 | Hành động sau phân tích (giãn nợ, chặn tạm ứng…) không có kiểm soát | Đề xuất → phê duyệt → nhật ký | Should |
| P8 | Hỏi câu ngoài thư viện chỉ số | Text‑to‑SQL chỉ‑đọc có kiểm soát (đường dự phòng) | Could |
| P9 | Bảo mật/riêng tư dữ liệu tài chính | Model chạy tại chỗ, nhật ký, phân quyền | Must |

## 6. Định nghĩa "thành công" ở góc nhìn người dùng
1. Chủ DN hỏi một câu và nhận **đúng số trong < 10 giây**, kèm "tính đến ngày …, tạm tính/khóa sổ".
2. Bấm "Xem cách tính" thấy công thức, các tài khoản và các chứng từ lớn nhất cấu thành.
3. Câu hỏi mơ hồ được hỏi lại; câu hỏi ngoài phạm vi được từ chối lịch sự, không trả số bịa.
4. Kế toán trưởng **giảm rõ rệt** số yêu cầu lấy số ad‑hoc (mục tiêu định lượng ở `3_evaluation/02`).
