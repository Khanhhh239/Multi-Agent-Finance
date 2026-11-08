# Dữ liệu V2 trong PLAN_06

Ngày: 14/10/2026. Người dùng xác nhận cho phép người code tự test trên UI. Đây là tự đối chiếu kỹ thuật, không phải nhãn độc lập.

| Công việc | Người thực hiện trong đợt này | Trạng thái |
|---|---|---|
| Baseline, công cụ, sửa code, báo cáo | Codex trong workspace | Đang thực hiện |
| Kiểm tra crop bằng mắt | Codex, có lưu nhãn/crop local | Một crop tên VNPT đã đối chiếu; nhãn pilot cũ giữ nguyên nguồn gốc |
| Nghiệm thu UI | Người dùng/người code theo xác nhận trong phiên | Chưa có lượt người dùng thực hiện được ghi nhận cho V2 |
| Dữ liệu public mới | Codex tìm/tải; dữ liệu ở local | 1 PDF nguồn mới tải được, 2 nguồn Bkav không truy cập được |
| Nhãn test độc lập và người giữ test | Chưa chỉ định | PENDING; không chặn phát triển kỹ thuật |

Toàn bộ 9 case có nhãn pilot cũ thuộc dev/regression, bao gồm hai case từng gọi là same_template_check. Tên cũ không mang ý nghĩa holdout độc lập. Ba ảnh scan chỉ là raster từ PDF, không cộng thành hóa đơn độc lập.

Nguồn mới được lưu ở `data invoice/ocr_extraction_v2/holdout_candidates_network_02`, có manifest URL/hash. PDF mới chưa được mở/extract để tuning, chưa xác nhận họ bố cục hoặc chọn trang hóa đơn; trạng thái chỉ là HOLDOUT_CANDIDATE_NOT_VALIDATED. Không dùng kết quả tìm kiếm làm nhãn và không tính cả PDF hồ sơ thành nhiều hóa đơn.

Chưa có 100 hóa đơn độc lập hoặc cặp PDF/XML đã đối chiếu. Mốc D3 của kế hoạch dữ liệu chưa diễn ra; chưa có phép đo năng suất gán nhãn 10 hóa đơn, nên 5–11 ngày công nhãn vẫn là dự báo. Statistical gate ≥150/600 mẫu từng field còn PENDING. Không đổi điều kiện này thành PASS chỉ vì người code tự kiểm tra UI.
