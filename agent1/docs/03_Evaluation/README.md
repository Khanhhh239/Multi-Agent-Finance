# 03 · Evaluation — Kết quả, tiêu chí và lịch sử đối chứng

**Định hướng tiếp theo từ session 13/11/2026:**
[Pipeline T1 → T6 → T10, global và học local](../04_AI_Methods/T1_T6_T10_GLOBAL_LOCAL_PIPELINE_2026-11-13.md)
tổng hợp kết quả A0/A1/A2, Neural/LightGBM/XGBoost và T6, rồi chốt kiến
trúc thích nghi theo doanh nghiệp. Đây là quyết định thiết kế, không phải
lượt đo mới hoặc thay đổi các report/artifact/gate lịch sử bên dưới.

**Cập nhật 06/11/2026.** Phân biệt ứng viên nghiên cứu, trạng thái pipeline
triển khai và hồ sơ lịch sử. Các đợt gộp tài liệu không tạo kết quả đo mới,
không đổi model hoặc trạng thái nghiệm thu.

## Đọc để chọn mô hình

| Tài liệu | Phạm vi |
|---|---|
| [Fine-tune trên Đại Phát so với Workspace ngày 13/11](T1_DAI_PHAT_FINETUNE_VS_WORKSPACE_2026-11-13.md) | Học tiếp bằng lịch sử Đại Phát trước bốn origin; đối chiếu Workspace đã train và global gốc; kết quả AR, xác suất, dải tiền và từng kỳ |
| [Chốt phiên bản T1 ngày 13/11](T1_CHOT_2026-11-13.md) | Khóa global 18 feature 75/25 cho nghiên cứu; giữ Workspace mặc định và cho Đại Phát; chưa mặc định refit/fine-tune; tách quyết định T1 khỏi nghiệm thu T6/pilot |
| [Backtest T6 global, không dự thu hóa đơn mới ngày 13/11](T6_GLOBAL_SCOPE_NO_NEW_INVOICES_2026-11-13.md) | Tách thu danh mục mở/số dư ngân hàng; Workspace tại từng origin; dữ liệu Đại Phát gốc và stress phản thực tế; dải tiền, cảnh báo và phân rã phạm vi |
| [Refit, học tiếp local và T6 ngày 13/11](T1_REFIT_LOCAL_ADAPTATION_2026-11-13.md) | Đồng bộ 18 feature, sửa nhãn ngày tiền thực thu, refit/audit và so sánh global–global thích nghi–Workspace trên bốn World mới; tách kết quả sau sửa nhãn và kiểm tải danh mục lớn |
| [Chốt T1 cho T6/SHAP ngày 12/11](T1_T6_SHAP_SELECTION_2026-11-12.md) | Ensemble 18 feature; Workspace trên ba World/18 doanh nghiệp/108 origin, phục vụ thực tế và SHAP; ứng viên nghiên cứu, không tự kích hoạt dịch vụ |
| [Khánh và V6 hiện tại](T1_V6_PROGRESS_VS_KHANH_2026-11-05.md) | Bản `both`, 93 feature; Paid/phân vị trên 65.221 anchor; đã gộp quyết định chốt nghiên cứu và bỏ các bản nháp lặp |
| [V6 gốc và Khánh](T1_V6_PROGRESS_VS_KHANH_V6_ORIGINAL_DETAIL_2026-11-05.md) | Bản 64 feature khóa 01/11; số đo riêng và cash head lịch sử |
| [Practical v6](T1_V6_PRACTICAL_FEATURES_2026-11-05.md) | Ablation ngành/ledger, chọn trên nguồn, augmentation và bốn fresh World |
| [V6 gốc](T1_V6_COMPETING_RISKS_2026-11-01.md) | So v4/v5, calibration, cash head, hai seed mới và tiêu chí chưa đạt |
| [Chẩn đoán nguyên nhân v6](T1_V6_CAUSE_DIAGNOSIS_2026-11-05.md) | Risk set, feature shift, hazard và phân nhóm hồi cứu trên `test_000` |
| [V5 competing risks](T1_V5_COMPETING_RISKS_2026-10-28.md) | Event/risk set và đối chứng v4 trên cùng cohort |
| [V4 censor-aware](T1_V4_CENSOR_AWARE_2026-10-28.md) | Sửa cách chấm xác suất và phân vị có kiểm duyệt |
| [V4 survival 365 ngày](T1_V4_PAYMENT_SURVIVAL_DIAGNOSTIC_2026-10-28.md) | Đuôi trả đủ/survival/hazard trên 45.498 hóa đơn, khác batch inference cuối 2025 |
| [Unified collection v2/r3](UNIFIED_COLLECTION_V2_2026-11-04.md) | Sửa adapter, learning curve và bốn World mới; chưa thắng v6 về CRPS bank |
| [Chọn cấu hình và audit gate](UNIFIED_MODEL_SELECTION_GATE_AUDIT_2026-11-04.md) | Đề xuất lõi v6 và giới hạn tích hợp; chưa nghiệm thu cấu hình mới |

Phương pháp/công thức dùng chung đọc ở
[T1 competing risks v5/v6](../04_AI_Methods/T1_COMPETING_RISKS_V5_V6.md).
Khánh trong benchmark là bản mặc định tái train từ mã, chưa phải booster
lịch sử hoặc toàn bộ pipeline tuned/BLEND/CQR. Không trộn kết quả V6 gốc,
nhánh 93 feature và unified v2 như cùng một artifact.

## Tiêu chí, kết quả triển khai và giả định kinh tế

| Tài liệu | Vai trò |
|---|---|
| [Metric kỹ thuật](01_metric_ky_thuat.md) | Định nghĩa chỉ số từng năng lực |
| [Metric kinh tế](02_metric_kinh_te.md) | Định nghĩa hiệu quả tiền, vận hành và sản phẩm |
| [Ngưỡng nghiệm thu gốc](03_cong_nghiem_thu.md) | Tiêu chí và trạng thái 15/10; giữ để truy vết thay đổi |
| [Cổng hiện hành](GATES_CURRENT.md) | Sinh từ CSV pipeline triển khai; pilot thật vẫn NO-GO |
| [Bảng kết quả từ CSV](04_ket_qua_hien_co.md) | Bảng chi tiết sinh tự động, gồm cả các phương pháp không thắng |
| [Kết quả trước sửa giao thức](04_ket_qua_2026-10-15_lich_su.md) | Ảnh chụp lịch sử; không thay kết quả đã sửa cách đo |
| [Kết quả chưa đạt](KET_QUA_CHUA_DAT.md) | Chẩn đoán/giới hạn sinh từ CSV |
| [Chi phí](05_chi_phi_xay_dung_va_van_hanh.md) | Mô hình chi phí xây dựng/vận hành, chưa phải số kinh doanh đã đo |
| [ROI](06_roi_truoc_sau.md) | Ví dụ giả định và độ nhạy, không phải tác động nhân quả đã xác nhận |
| [Kế hoạch kiểm thử](07_ke_hoach_kiem_thu.md) | Unit, tích hợp, backtest, UAT, A/B và giám sát |

Bảng CSV gốc, giao thức và phép tính trong các tài liệu trên phục vụ những
câu hỏi khác nhau; giữ chúng để kiểm tra kết luận, không gộp điểm của các
lần chạy khác nhau. Cập nhật bảng tự động bằng `scripts/make_report.py`,
`scripts/analyze_results.py` và công cụ sinh gate tương ứng; không sửa
bảng kết quả bằng tay để phù hợp kết luận.

## Protocol và chẩn đoán lịch sử cần giữ

- [GO/NO-GO synthetic ngày 21/10](GO_NO_GO_SYNTHETIC_ONLY.md): phạm vi vận hành và quyết định tại thời điểm đó.
- [Chính sách G13](G13_ALERT_POLICY.md) và [chẩn đoán T9](T9_RECALL_DIAGNOSIS.md): lý do chưa đạt và phân rã lỗi.
- [G8/T2](G8_T2_PREREG.md), [G14/T7](G14_T7_PREREG.md), [G15/T9 v2](G15_T9_V2_PREREG.md), [G17/T8](G17_T8_PREREG.md).
- [G13 end-to-end](G13_E2E_T9V2_PREREG.md), [review queue](G13_REVIEW_QUEUE_PREREG.md), [soft labels](G13_SOFT_LABELS_PREREG.md).
- [Sprint 6](SPRINT6_PREREG_2026-10-22.md): tiêu chí được ghi trước phép thử, không phải yêu cầu chạy hiện nay.

Các protocol giữ bằng chứng tiêu chí có trước khi xem test; không xóa chỉ
vì phép thử đã xong. Kết quả synthetic không thay UAT/pilot Việt Nam.
Một số đầu vào lịch sử đã xóa; xem [tồn kho dữ liệu](../02_Data/README.md)
trước khi chạy lại. Các giới hạn, kết quả xấu và cách tổng hợp theo
World/công ty phải được đọc cùng mức cải thiện trung bình.
