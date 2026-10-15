# Agent 2 — Trợ lý Giám sát Rủi ro Gian lận Nội bộ cho doanh nghiệp nhỏ và vừa Việt Nam

Bộ tài liệu này mô tả toàn bộ công việc đã làm cho Agent 2 và phần việc còn lại. Mỗi thư mục là một vai trò; mỗi tệp chỉ nói một chủ đề để đọc nhanh.

**Đọc trước:** [STATUS.md](STATUS.md) (đã làm gì, chưa làm gì, điều gì chưa kiểm chứng).

## Bản đồ thư mục

| Thư mục | Vai trò người viết | Trả lời câu hỏi |
|---|---|---|
| [01_phan_tich_kinh_te_va_nghiep_vu](01_phan_tich_kinh_te_va_nghiep_vu/README.md) | BA, nhà nghiên cứu kinh tế tài chính | Vấn đề là gì, đau ở đâu, bằng chứng, ai cần, thị trường nhìn ra sao, sản phẩm phải làm gì |
| [02_du_lieu](02_du_lieu/README.md) | Data scientist, data analyst | Dùng dữ liệu gì, vì sao phải sinh, sinh thế nào, khó đến mức nào, đánh giá từng năng lực ra sao |
| [03_danh_gia_va_hieu_qua_kinh_te](03_danh_gia_va_hieu_qua_kinh_te/README.md) | Tester, BA đánh giá | Đo kỹ thuật và kinh tế bằng chỉ số nào, chi phí xây dựng, doanh nghiệp tiết kiệm bao nhiêu |
| [04_phuong_phap_va_pipeline](04_phuong_phap_va_pipeline/README.md) | AI engineer, AI researcher | Pipeline, mô hình, tham số, vì sao thiết kế như vậy, thí nghiệm đã chạy và cần chạy |
| [05_ke_hoach_giao_viec](05_ke_hoach_giao_viec/README.md) | Người vạch chiến lược | Việc còn lại cho coding agent kế tiếp, từng bước, từng tệp, từng giả thuyết |
| [06_ghi_chep_lam_viec](06_ghi_chep_lam_viec) | Nhật ký gốc | Nhật ký, báo cáo, tài liệu dữ liệu và phương pháp các phiên trước (giữ nguyên để truy vết) |
| [07_tai_lieu_tham_khao](07_tai_lieu_tham_khao) | Nghiên cứu nền | Phần 6 và Phần 8 của hồ sơ "Phòng Kế toán Số" (nguồn dữ liệu và đánh giá phương pháp) |

## Quy ước độ tin cậy dùng trong mọi tệp

| Ký hiệu | Nghĩa |
|---|---|
| **[Đ]** | Đã đọc tài liệu gốc (báo cáo, bài báo, bản án) |
| **[T]** | Chỉ đọc bản tóm tắt, bài báo đưa tin lại hoặc kết quả tìm kiếm; cần đối chiếu nguồn gốc trước khi trích dẫn chính thức |
| **[G]** | Giả định của người viết, không có nguồn; phải kiểm chứng ở giai đoạn thí điểm |
| **[N]** | Thiết kế hoặc suy luận của người viết |
| **[M]** | Số đo từ thí nghiệm trên dữ liệu tổng hợp của dự án (không phải bằng chứng về doanh nghiệp thật) |

## Ba nguyên tắc không được vi phạm

1. **Mọi số đo mô hình hiện có là trên dữ liệu tổng hợp.** Không dùng để khẳng định độ chính xác trên doanh nghiệp thật.
2. **Tập niêm phong chỉ chạy đúng một lần**, với cấu hình đã đóng băng. Không chỉnh gì sau khi xem kết quả của nó.
3. **Hệ thống chỉ gắn cờ giao dịch và đưa lý do**; con người quyết định. Không kết luận về cá nhân (Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân).
