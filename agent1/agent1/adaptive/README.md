# Adaptive: mã đang phục vụ web và pipeline

## Bước 7: T10 theo forecast đã lưu

`t10_explanations.py` nối SHAP T1, bằng chứng adapter tất toán/partial và phân
rã kế toán với snapshot bundle/dữ liệu/T6. Kịch bản phát lại baseline rồi chạy
T6 bằng cùng nguồn ngẫu nhiên, so kỳ vọng, P10/P50/P90 và xác suất thiếu tiền.
Đã gỡ bộ sinh `timing_comparison` chỉ dịch kỳ vọng. Xem
[hợp đồng T10](../../docs/04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

## T1 hiện tại: global → local, chọn cùng partial adapter

T1 phục vụ không còn catalog/ensemble học từ đầu bằng local. `t1_catalog.py`
nạp gói Neural/LightGBM/XGBoost có hash; `t1_data.py` dựng landmark và risk
row đã quan sát; `t1_update.py` chọn theo cash13/IBS, audit và refit theo cửa
sổ trượt. `agent1_service/workspace/t1_lifecycle.py` lưu phiên bản từng doanh
nghiệp, lịch cập nhật và challenger chờ nhãn 91 ngày. Job định kỳ:
`python -m agent1_service.jobs.t1_update`.

`cash_adapter.py` học xác suất/tỷ lệ partial riêng, điều chuẩn về prior global;
validation, audit và T6 dùng cùng engine, gồm mô phỏng nhiều lần thu. Bundle v2
lưu cả T1 và partial. `payment_coverage.py` yêu cầu phạm vi thanh toán đã xác
nhận; thiếu thông tin bị censor. Override cohort partial trong runtime đã bỏ.

Xem [hợp đồng T1 + partial v2](../../docs/04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md).
Phần hoàn thiện T6, P50/phân vị, `serving_manifest` và quy trình lock → predict
→ score được ghi ở [hợp đồng T6](../../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md).
Các source snapshot trong output là bằng chứng lịch sử, không phải catalog
được đưa lại vào quá trình lựa chọn của dịch vụ.

Điểm vào web là `agent1_service/workspace/api.py` và `train_worker.py`.
Pipeline nạp dữ liệu dùng `data_pipeline/stage.py`; các script kiểm định nằm
trong `scripts/business/` và `experiments/t1_compact/`.

| Nhóm file | Ứng dụng hiện tại |
| --- | --- |
| `data.py` | Ghép cột, nạp/kiểm tra dữ liệu, lịch sử phiên bản và công nợ tại ngày chốt; dùng chung với pipeline. |
| `methods.py`, `t1_catalog.py`, `t1_data.py`, `t1_update.py` | T1 global → local, lựa chọn/audit và dự báo T6; không fit catalog local cũ. |
| `risk.py`, `collections.py` | Rủi ro xóa nợ và metric phân luồng; không fit một T1 customer riêng. |
| `cash_history.py` | Lịch sử tiền đã đối chiếu, đánh giá dự báo và hiệu chỉnh dải số dư. |
| `cash_adapter.py`, `payment_coverage.py` | Nhánh partial global/local, tiền kỳ vọng và nhiều lần thu; xác nhận phạm vi nhãn. |
| `operating.py`, `new_credit.py` | Ước lượng bán thu ngay, chi biến đổi và thu từ hóa đơn mới khi bật dự báo hoạt động. |
| `obligations.py`, `obligation_imports.py` | Lịch nghĩa vụ T5, phần chưa thanh toán và định danh chống nạp trùng. |
| `explanations.py`, `explanation_reference.py`, `landmark_explanations.py` | SHAP của đúng landmark T1 đang dùng, mẫu nền và độ nhạy. Bộ giải thích T1 năm feature cũ đã bỏ. |
| `collection_explanations.py`, `cash_explanations.py` | Giải thích xếp hạng thu hồi và phân rã dòng tiền được lưu/xuất trên web. |
| `compact_t1.py`, `compact_ensemble.py`, `landmark_features.py`, `landmark_explanations.py` | Đặc trưng, artifact, pooling và grouped SHAP dùng chung cho catalog global và các nhánh học tiếp; không còn override bằng allowlist research. |
| `ledger_bridge.py` | Chuyển ledger nghiên cứu sang ngữ nghĩa kế toán Workspace để huấn luyện/kiểm định cùng hợp đồng dữ liệu. |
| `landmark_adaptation.py` | Học tiếp Neural/cây từ global, giữ scaler/cây cũ và pooling có kiểm soát. |
| `training_report.py` | Tạo báo cáo huấn luyện mã hóa khi dịch vụ đã cấu hình nơi lưu và mật khẩu. |

## Phần đã gộp

- `landmark_serving.py` đã gộp vào `compact_t1.py`, cùng nơi có
  `load_workspace_bundle`. Dùng
  `from agent1.adaptive.compact_t1 import load_research_t1_bundle`.
  Các bên gọi nghiên cứu và đọc artifact lịch sử dùng đường dẫn này; API hiện nạp catalog global.
- Hai schema T1 dùng chung `compact_t1.feature_context` cho lịch sử quan sát,
  cohort tất toán 180 ngày, công nợ mở và thang giá trị. Thứ tự đặc trưng của
  schema 10 và 18 cột vẫn riêng để đọc đúng artifact hiện có.
- `Method` local cũ đã bỏ khỏi serving. Adapter trong `experiments/` chỉ đọc
  nguồn frozen khi cần kiểm chứng thí nghiệm lịch sử.

Schema 10 cột và lựa chọn SHAP `legacy24` vẫn có bên gọi trong pipeline kiểm định
và so sánh mẫu nền. Các lớp mô hình hiện tại còn là đường dẫn giải tuần tự hóa
artifact, vì vậy không xóa chỉ dựa vào tên cũ. Cache `__pycache__/` và `*.pyc`
có thể xóa và đã được Git bỏ qua.

## Kiểm tra

Lượt kiểm tra dọn trước khi đổi pipeline: 322 đạt, 3 bỏ qua. Bằng chứng T1 +
partial hiện tại nằm trong `outputs/implementation/t1_partial_bundle_v2_20261113/`;
output smoke T1 v1 đã dọn ngày 14/11/2026.
Kiểm tra Ruff nhóm lỗi `E9,F` trên adaptive và các nơi đổi import đều đạt;
quét import Python không có tham chiếu tới mô-đun adaptive bị thiếu.
