# 04 · AI Methods — Phương pháp theo phiên bản

**Bước 7, T10 ngày 13/11:** [Bằng chứng bundle đã lưu và kịch bản T6](T10_BUNDLE_EVIDENCE_2026-11-13.md).
Đã có phân rã adapter tất toán/partial, hỗ trợ dữ liệu, snapshot phiên bản và
kịch bản so kỳ vọng/P10/P50/P90/Δ xác suất thiếu tiền bằng nguồn ngẫu nhiên
chung. Bảng chỉ dịch kỳ vọng cũ đã gỡ; chưa nghiệm thu chất lượng SME thật.

**T1 phục vụ mới:** [Global → local và chu kỳ cập nhật](T1_GLOBAL_LOCAL_RUNTIME_2026-11-13.md)
đã bỏ catalog/ensemble local cũ theo yêu cầu mới nhất, giữ ba họ global và học
tiếp, audit với incumbent và chờ nhãn cho challenger. Quyết định này thay phần
T1 có Workspace trong bản chốt trước; các số đo lịch sử giữ nguyên.

**Bản chốt kiến trúc trước yêu cầu bỏ Workspace, ngày 13/11/2026:**
[T1 → T6 → T10 với global và học local theo doanh nghiệp](T1_T6_T10_GLOBAL_LOCAL_PIPELINE_2026-11-13.md).
Giữ nhiều ứng viên T1, Workspace local và audit với incumbent; phân biệt
T6 engine với learner/profile/calibrator local và T10 giải thích đúng bundle.
Phần T1 có Workspace đã được thay bởi hợp đồng runtime ở đầu trang; bảng
trạng thái của quyết định cũ giữ phần đã đo và phần dự kiến tại thời điểm chốt.

**Cập nhật 06/11/2026.** Tài liệu phương pháp giải thích mô hình/contract;
[kết quả Evaluation](../03_Evaluation/README.md) ghi số đo, lựa chọn và
[cổng sản phẩm](../03_Evaluation/GATES_CURRENT.md). Có mô tả hoặc code không
đồng nghĩa đã tích hợp, qua gate hoặc có dữ liệu SME thật để kiểm chứng.

**Quyết định bổ sung 12/11/2026:** [Chọn T1 cho T6/SHAP](../03_Evaluation/T1_T6_SHAP_SELECTION_2026-11-12.md)
chốt ensemble 18 feature làm cấu hình tổng quát của nhánh nghiên cứu sau đối
chiếu Workspace trên ba World/18 doanh nghiệp/108 origin. Bản local vẫn cần
validation tại doanh nghiệp; quyết định không tự đổi model dịch vụ/gate pilot.

## T1 v5/v6, practical và unified v2

Lượt [refit và thích nghi local ngày 13/11](../03_Evaluation/T1_REFIT_LOCAL_ADAPTATION_2026-11-13.md)
ghi hợp đồng feature chung, nhãn Paid theo ngày tiền thực thu, replay/validation/audit
local và đối chứng Workspace. Phân biệt global hiện tại với ứng viên refit không
qua audit; không suy diễn kết quả synthetic thành nghiệm thu doanh nghiệp thật.

| Tài liệu | Phạm vi |
|---|---|
| [Competing risks v5/v6](T1_COMPETING_RISKS_V5_V6.md) | Công thức, event/risk set, feature/calibration/cash head; v6 gốc 64 feature |
| [Protocol practical P0–P4](T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md) | Ngành + ledger, 93 feature; selector, amendment và fresh đã khóa; giữ nguyên protocol |
| [B2B feature access](T1_V6_B2B_FEATURE_ACCESS_2026-11-05.md) | Đầu vào doanh nghiệp có thể biết, tenant/known_at, khoảng cách tới luồng thật |
| [Contract unified v2/r3](UNIFIED_COLLECTION_V2_CONTRACT_2026-11-04.md) | Tiền bank/AR, thứ tự thời gian, streams và source gate; giữ nguyên contract |

Không trộn T1 nhị phân 13 tuần, V6 gốc, nhánh `both` 93 feature và unified
như cùng một model. Cash head gốc chưa được train lại cho nhánh 93 feature.
Protocol/preregistration cần giữ để kiểm tiêu chí trước khi xem test.

## Pipeline gốc, đối chứng và giao thức bổ sung

| Tài liệu | Nội dung sau gộp |
|---|---|
| [Pipeline và T0](01_pipeline_he_thong.md) | Luồng gốc, as-of, LLM, đề xuất vận hành và phạm vi quality gate |
| [T1 nhị phân / Khánh](02_t1_hazard_thoi_diem_tra.md) | 13 tuần, feature, đuôi/quantile; sửa mô tả fullweek theo code và gộp đăng ký C-v2/P4/G3 |
| [T2/T3/T8](03_t2_t3_t8_xac_suat_hoa_don.md) | Cure khác Write-off, EB, reliability; gộp giao thức SBA macro |
| [T4/T5](04_t4_t5_thu_moi_va_chi.md) | Doanh thu, lịch chi; gộp nghĩa vụ từ hồ sơ, known_at và chống tính trùng |
| [Domain adaptation](05_domain_adaptation.md) | DA1–DA7, DR và IW ngoài công ty; gộp mô tả cùng ngân sách và giới hạn |
| [T6 và đối chứng](06_t6_monte_carlo_conformal.md) | Copula/ACI gốc; gộp copula hai nhân tố, ETS/ARIMA/B0/Chronos Tiny |
| [T7/T9/T10](07_t7_t9_t10.md) | Điểm gãy, khớp tiền, giải thích; gộp T9 sốc cung, T7→T6, chính sách thu nợ và đăng ký source-policy |
| [Giả thuyết thí nghiệm](08_thi_nghiem_de_xuat.md) | Danh mục mã X/tiêu chí ban đầu và nơi tra phép thử đã có; không phải backlog phải chạy toàn bộ |
| [Hiệu năng và bẫy kỹ thuật](09_tham_so_va_toi_uu.md) | Giữ số đo/ước lượng và kinh nghiệm; bỏ bảng tham số lặp để tra theo đúng model/protocol |
| [Duyệt lời hứa từ chat](09_promise_chat_review.md) | Luồng nháp/người duyệt/API riêng; chưa có giao diện trích xuất chat được kiểm UAT |

Các số và nhận định trong bản thiết kế gốc được ghi rõ là lịch sử. Nhiều
World `src/tgt`, hard-case, DR/config đời đầu và toàn bộ `data/T1/` đã xóa;
trước khi chạy lệnh cũ phải kiểm [tồn kho dữ liệu](../02_Data/README.md),
manifest và snapshot mã. Không tái sinh/fit chỉ để làm mới cách trình bày.
Các nguồn luật trong đặc tả T5 là hồ sơ đối chiếu trước đây, không xác nhận
hiệu lực hiện tại hay thay kiểm tra chuyên gia.

## Nghiên cứu lịch sử còn giá trị

| Tài liệu | Lý do giữ |
|---|---|
| [T0–T10 ngày 25/10](T0_T10_PHUONG_PHAP_VA_KET_QUA_SYNTHETIC_2026-10-25.md) | Giữ toàn bộ bảng kết quả và giới hạn theo ngày; phần mô tả phương pháp lặp chuyển về tài liệu từng T |
| [Hướng thống nhất T1→T6 ngày 03/11](T1_T6_UNIFIED_DIRECTION_REVIEW_2026-11-03.md) | Audit sai khác tất toán/thu từng phần, support nhãn và throughput; giải thích vì sao thử unified |
| [Khảo sát tín dụng prototype](T1_V6_CREDIT_CONTEXT_RESEARCH_2026-11-05.md) | Thiết kế phép đo và audit độ trễ công bố; giải thích vì sao không dùng năm macro feature. Đề xuất fit đã được thay bằng protocol practical |

Giữ các số đo không thắng và giới hạn để tránh lặp lại lựa chọn đã loại.
Bảng phương pháp/siêu tham số không thay protocol của lần chạy; không cộng
điểm từ các estimand/World hoặc phiên bản khác nhau.
