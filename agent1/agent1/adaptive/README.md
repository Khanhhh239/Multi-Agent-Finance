# Adaptive · Runtime Workspace

Điểm vào `/v1` là `agent1_service/workspace/api.py`; API, worker và job cập nhật dùng chung `methods.train`. Dự báo gọi `methods.forecast` với snapshot và bundle đã sẵn sàng, không fit trong lúc predict.

Đọc [pipeline](../../docs/04_AI_Methods/01_pipeline_he_thong.md) để theo luồng đầu-cuối. Hợp đồng hiện tại: [T0/T9](../../docs/04_AI_Methods/02_t0_t9_du_lieu_va_doi_soat.md), [T1 + partial](../../docs/04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md), [T5](../../docs/04_AI_Methods/04_t4_t5_thu_moi_va_chi.md), [T6](../../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md), [T10](../../docs/04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

| Module | Trách nhiệm |
|---|---|
| `data.py`, `payment_coverage.py` | Nhập/kiểm phiên bản, công nợ as-of và phạm vi nhãn; không suy thiếu payment là chưa trả |
| `t1_catalog.py`, `t1_data.py`, `t1_update.py` | Catalog global v3, landmark/risk rows, chọn/học tiếp/audit; lifecycle registry ở `workspace/t1_lifecycle.py` |
| `compact_t1.py`, `compact_ensemble.py`, `landmark_features.py`, `landmark_adaptation.py` | Artifact/pooling, 18 feature, học tiếp Neural/cây; không chọn ensemble local học từ đầu trong serving |
| `cash_adapter.py` | Partial có điều chuẩn về prior, cùng luật tiền cho validation/audit/T6; bundle giữ T1 và partial |
| `methods.py` | Huấn luyện bundle và ghép T1/partial/T5/operating thành forecast; T6 hiện là `settlement-partial-paths-v4` |
| `risk.py`, `collections.py` | Rủi ro xóa nợ và chính sách phân luồng; không nhân rủi ro lần nữa vào tiền thu |
| `cash_history.py` | Thực tế, đối chiếu và hiệu chỉnh dải theo cùng tài khoản/identity |
| `operating.py`, `new_credit.py` | Nhánh hoạt động tùy chọn/đủ điều kiện, tối đa 13 tuần; thu hóa đơn mới mặc định tắt |
| `obligations.py`, `obligation_imports.py` | Nghĩa vụ T5, thực trả/nhận và định danh chống trùng |
| `explanations.py`, `explanation_reference.py`, `landmark_explanations.py` | Grouped SHAP T1, reference và độ nhạy |
| `collection_explanations.py`, `cash_explanations.py`, `t10_explanations.py` | Giải thích ưu tiên/tiền, evidence và kịch bản replay từ forecast đã lưu |
| `bundle_metadata.py`, `training_report.py` | Identity/mốc dữ liệu và báo cáo huấn luyện mã hóa |
| `ledger_bridge.py` | Chiếu ledger nghiên cứu sang ngữ nghĩa Workspace cho các phép kiểm |

`compact_t1.feature_context` dùng chung cho schema 10/18 feature; thứ tự cột và loader artifact vẫn phải đúng schema. `load_research_t1_bundle` phục vụ caller nghiên cứu; API nạp catalog global. Mã cũ phục vụ artifact/caller còn tồn tại không đồng nghĩa được phép override catalog `/v1/predict`.

Kiểm thử theo [hướng dẫn](../../tests/README.md); chất lượng tiền theo [nghiệm thu](../../docs/03_Evaluation/03_cong_nghiem_thu.md). Không dùng số ca test trong log cũ làm trạng thái hiện hành.
