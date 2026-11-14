# 04 · Pipeline và phương pháp Agent 1 hiện tại

Đối chiếu mã phục vụ ngày **14/11/2026**. Điểm vào sản phẩm là `agent1_service/workspace/api.py` và `agent1/adaptive/`; `/forecast` research và các script benchmark cũ có protocol riêng.

| Đọc theo thứ tự | Nội dung chính |
|---|---|
| [Pipeline đầu-cuối](01_pipeline_he_thong.md) | Nạp → đối soát → snapshot → học/chọn bundle → dự báo → giải thích → đối chiếu thực tế |
| [T0/T9](02_t0_t9_du_lieu_va_doi_soat.md) | Ngày biết, vòng đời chứng từ, phân bổ có duyệt, lịch sử và công nợ |
| [T1 + partial](T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md) | Global → học tiếp local, nhãn 91 ngày, adapter, validation/audit và cập nhật định kỳ |
| [T5 và hoạt động](04_t4_t5_thu_moi_va_chi.md) | Nghĩa vụ còn lại, thanh toán thực tế, hoàn VAT và ước lượng thu/chi tùy chọn |
| [T6](T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) | Thu nhiều lần, kỳ vọng/median/dải tiền, phạm vi và hiệu chỉnh |
| [T10](T10_BUNDLE_EVIDENCE_2026-11-13.md) | SHAP, bằng chứng tiền, snapshot bất biến và chạy lại kịch bản |

Các file có ngày trong tên T1/T6/T10 là **đặc tả đang dùng**, đã gộp phần vận hành còn hiệu lực và bỏ nhật ký sửa lỗi/số ca test theo từng lượt. Quy tắc đánh giá và kiểm thử tập trung ở [Evaluation](../03_Evaluation/README.md).

Luồng T1 hiện chọn bundle global hoặc học tiếp từ global, không chọn ensemble local học từ đầu. T6 dùng `settlement-partial-paths-v4`; adapter tiền là `settlement-partial-cash-v2`. T10 đọc đúng forecast đã lưu, chưa dùng LLM để tính/diễn đạt kết quả. Phương pháp competing risks v5/v6, unified prototype, các quyết định chọn model cũ và log nghiên cứu đã bỏ khỏi bộ tài liệu vận hành.

Mã/artifact/CSV trong `outputs/` giữ bằng chứng đúng phiên bản; các tài liệu này không chạy lại benchmark, thay model active hoặc xác nhận chất lượng trên doanh nghiệp thật. Tồn kho nguồn nằm ở [Data README](../02_Data/README.md).
