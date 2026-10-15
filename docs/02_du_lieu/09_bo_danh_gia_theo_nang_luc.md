# Bộ dữ liệu đánh giá theo từng năng lực

Mỗi năng lực có một cách chia dữ liệu riêng. Bảng này là bản đồ giữa **câu hỏi** và **cách chia**.

| # | Năng lực / câu hỏi | Bộ dữ liệu và cách chia | Mã chạy | Chỉ số chính |
|---|---|---|---|---|
| E1 | Bắt kịch bản đã biết trong tương lai gần (triển khai thực tế) | Một thế giới; huấn luyện 2024, kiểm định nửa đầu 2025, kiểm thử nửa cuối 2025 (P1) | `agent2/bench.py`, `eval_v4.py` | Recall@B3, AP, vụ tìm thấy, báo nhầm |
| E2 | Bắt kịch bản **chưa từng thấy** (một kịch bản) | Bỏ toàn bộ nhãn một kịch bản khỏi huấn luyện; kiểm thử trên chính nó (bỏ-một-họ) | `bench.run_leave_family_out` | Recall@B3 theo kịch bản |
| E3 | Bắt **nhánh ACFE chưa từng thấy** | Ẩn nhãn một nhánh (billing, payroll, ...) khỏi huấn luyện và kiểm định, dòng giữ nguyên nhãn 0 như gian lận chưa phát hiện (P2) | `eval_v4.p2_unseen_branch` | Recall@B3 trung bình nhánh |
| E4 | Công ty mới (khởi đầu lạnh có huấn luyện sẵn) | Huấn luyện trên thế giới khác; thực thể và hệ quy chiếu chỉ khớp trên lịch sử không nhãn của thế giới đích (P3) | `eval_v4.p3_new_firm`, `final_eval.py` | Recall@B3, precision |
| E5 | Công ty chưa thấy trong cùng thế giới | Bỏ-một-công-ty | `bench.run_leave_company_out` | AP, recall |
| E6 | Kiểm thử cuối độc lập, kịch bản mới | Thế giới niêm phong; nhãn của kịch bản mới bị ẩn khi huấn luyện; chạy một lần | `agent2/sealed_v4.py` (chưa chạy); v3: `final_eval.py` đã chạy | Recall@B3 chung, kịch bản đã biết, kịch bản mới, báo nhầm ca hợp lệ mới |
| E7 | Chất lượng khởi đầu lạnh (không nhãn) | Chỉ lịch sử không nhãn; không huấn luyện có giám sát | Kênh Novelty trong `eval_v4.py` | Recall@B3, báo nhầm |
| E8 | Báo nhầm trên ca hợp lệ giống gian lận | Cột `hard_negative_type` | `metrics.operating_point` | Tỷ lệ cảnh báo trên ca hợp lệ khó |
| E9 | Ổn định theo thời gian / độ trôi | Chia theo tháng, hoặc huấn luyện 6 tháng kiểm thử 6 tháng | (chưa có) | Độ giảm recall theo tháng |
| E10 | Học từ phản hồi | Mô phỏng 52 tuần với nhiễu nhãn 0%, 15%, 30% | `agent2/feedback_sim.py` | Số dòng gian lận tìm được tích lũy |
| E11 | Độ nhạy tham số sinh | Lưới ở tệp 07 mục 4 | (chưa có) | Thứ hạng phương pháp |
| E12 | Đối chiếu ngoài | ERP Fraud Data, DFKI | `agent2/external.py` | AP |
| E13 | Mức vụ | Mọi thí nghiệm trên | `metrics.case_stats` | Vụ tìm thấy, độ trễ |
| E14 | Giải thích | Kiểm tra mọi con số trong câu giải thích có trong bằng chứng | (chưa có) | Tỷ lệ câu đúng |

## Quy ước chung
- Ngân sách mặc định B3: 3 cảnh báo mỗi công ty mỗi tuần; B1: 1 cảnh báo.
- Ngưỡng và tham chiếu chỉ lấy từ giai đoạn kiểm định; **nhãn kiểm thử không được dùng để chọn gì**.
- Bootstrap theo vụ (không theo dòng) cho khoảng tin cậy.
- Mọi số báo cáo kèm số dòng dương của tập kiểm thử (khoảng 200 dòng ở mỗi thế giới 200.000 dòng) vì sai số của recall khoảng 3 điểm phần trăm.
