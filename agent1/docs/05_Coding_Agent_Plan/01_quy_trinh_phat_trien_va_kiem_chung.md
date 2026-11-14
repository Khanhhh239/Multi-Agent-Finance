# Quy trình phát triển và kiểm chứng

Áp dụng cho Workspace hiện tại; đối chiếu mã ngày 14/11/2026. Đây là hướng dẫn thực hiện thay đổi, không là nhật ký hoặc danh sách công việc đã nghiệm thu.

## Xác định đúng luồng

Đọc [pipeline](../04_AI_Methods/01_pipeline_he_thong.md), xác định hợp đồng bị ảnh hưởng rồi lần theo điểm vào:

| Phạm vi thay đổi | Mã và hợp đồng cần đối chiếu |
|---|---|
| Nhập, sửa nguồn và công nợ | `agent1/adaptive/data.py`, `agent1_service/workspace/api.py`, `reconciliation.py`; [T0/T9](../04_AI_Methods/02_t0_t9_du_lieu_va_doi_soat.md) |
| Nhãn, học tiếp, validation/audit | `t1_data.py`, `t1_update.py`, `t1_catalog.py`, `workspace/t1_lifecycle.py`; [T1 + partial](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md) |
| Nghĩa vụ và hoạt động | `obligations.py`, `obligation_imports.py`, `operating.py`; [T5](../04_AI_Methods/04_t4_t5_thu_moi_va_chi.md) |
| Dự báo và chấm thực tế | `methods.py`, `cash_adapter.py`, `cash_history.py`; [T6](../04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) |
| Giải thích, kịch bản, export | `t10_explanations.py`, `cash_explanations.py`, `workspace/forecast_export.py`, UI Workspace; [T10](../04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md) |

Các tên file ngắn trong bảng thuộc `agent1/adaptive/`; riêng `workspace/` thuộc `agent1_service/`, và `reconciliation.py` là adapter trong `agent1_service/workspace/`. API `/v1` là luồng doanh nghiệp; `/forecast` và các runner nghiên cứu có hợp đồng riêng. Không lấy kết quả của một luồng để xác nhận luồng khác.

## Thay đổi trên dữ liệu và kho thử riêng

Giữ nguyên thay đổi đang có của người khác. Dùng kho, khóa và cổng riêng cho diễn tập; không nạp fixture vào kho SME. Không đưa token, mật khẩu, dữ liệu thật hoặc bản giải mã vào Git.

Giữ các bất biến: tiền ngân hàng chỉ ghi một lần; phân bổ không vượt tiền/dư nợ và đúng khách; ngày nghiệp vụ khác ngày biết; thiếu coverage phải censor. T1/partial được chọn cùng bundle, audit chỉ chấm ứng viên đã khóa. Forecast dùng một snapshot nhất quán và không fit model. Kế hoạch đã lưu không bị viết lại khi nhập dữ liệu hoặc đổi active.

Thay luật tiền, nhãn hoặc artifact phải xét version/schema, khả năng đọc dữ liệu cũ, replay và điều kiện hiệu chỉnh. Không sửa source hash/protocol của output lịch sử để làm phép kiểm vượt qua.

## Chọn phép kiểm có ý nghĩa

| Thay đổi | Bằng chứng cần thu |
|---|---|
| T0/T9 | Retry/trùng mã, nhiều-nhiều, trả từng phần, chéo khách, sửa/đảo, lệch 1 VND, snapshot lịch sử; dùng [bộ UAT](../../pilot/t0_t9_uat_20261110/README.md) |
| T1 + partial | Censoring, nhãn cố định 91 ngày, sửa rồi hoàn nguyên, validation/audit tách biệt, promotion đúng artifact, fallback và mốc sẵn sàng |
| T5/T6 | Phần còn phải trả, hoàn VAT tách thu, không cộng trùng, kỳ vọng/median/phân vị riêng, tài khoản và identity operating/calibration |
| T10/UI/export | Giải thích đúng forecast, kịch bản RNG ghép cặp, registry đang được tham chiếu, source/runtime mismatch, hiển thị/xuất đúng tiền và phạm vi |

Chạy nhóm kiểm phù hợp trong [hướng dẫn tests](../../tests/README.md). Khi đánh giá chất lượng tiền, dùng giao thức lock → predict → score ở [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md), cùng cohort và phạm vi tài khoản; lưu lý do tuần không đủ dữ liệu. Test cơ chế không thay cho benchmark hoặc UAT người thật.

## Điều kiện hoàn thành

Mô tả hành vi trước/sau, phạm vi và giới hạn; ghi rõ phép kiểm thực sự đã chạy. Cập nhật đúng tài liệu hợp đồng thay vì thêm nhật ký Markdown mới. Nêu bước cần dữ liệu thật hoặc nhãn chưa trưởng thành; không đánh dấu đã đạt bằng số synthetic. Bằng chứng chạy máy thuộc artifact riêng, không chép lặp vào README/sổ tay.

Đánh giá pilot và giá trị kinh tế theo [Evaluation](../03_Evaluation/README.md) và [bộ pilot](../../pilot/BO_PILOT_SME.md). Chưa có bằng chứng mới thì giữ nguyên trạng thái chưa nghiệm thu SME thật.
