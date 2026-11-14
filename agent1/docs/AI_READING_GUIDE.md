# Đọc tài liệu Agent 1 theo luồng hiện tại

Đối chiếu mã Workspace ngày **14/11/2026**. Ưu tiên hợp đồng/mã của `agent1/adaptive/` và `agent1_service/workspace/` khi xác định hành vi sản phẩm.

## Đọc trước

1. [Pipeline đầu-cuối](04_AI_Methods/01_pipeline_he_thong.md).
2. [T0/T9 và công nợ quan sát](04_AI_Methods/02_t0_t9_du_lieu_va_doi_soat.md).
3. [T1 + partial, học tiếp và audit](04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md).
4. [T5 và hoạt động](04_AI_Methods/04_t4_t5_thu_moi_va_chi.md), [T6](04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md).
5. [T10 và replay](04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

Luồng hiện tại: nạp/kiểm dữ liệu → quyết định T9 có duyệt → snapshot theo ngày biết → bundle T1 global/học tiếp + partial → T6 với T5/hoạt động đủ điều kiện → forecast bất biến → giải thích/kịch bản/export → chấm thực tế. Học định kỳ và tạo dự báo là thao tác riêng.

## Chọn nguồn theo câu hỏi

| Cần biết | Nơi đọc |
|---|---|
| Chạy dịch vụ | [README Agent 1](../README.md), [dịch vụ](../agent1_service/README.md) |
| API/schema/hành vi thực tế | `agent1_service/workspace/`, `agent1/adaptive/` và test tương ứng |
| Kiến trúc hiện tại | [AI Methods](04_AI_Methods/README.md) |
| Cách chấm/chất lượng/nghiệm thu | [Evaluation](03_Evaluation/README.md), [nghiệm thu](03_Evaluation/03_cong_nghiem_thu.md) |
| Nguồn và tồn kho | [Data](02_Data/README.md) |
| Bài toán/phạm vi nghiệp vụ | [BA](01_Business_Analyst/README.md) |
| Demo T0/T9/T10 | [Hướng dẫn demo](T0_T9_T10_DA_LAM_DUOC.md), kiểm ngày/version trong từng phần |

## Các ranh giới phải giữ

- T1 phục vụ dùng catalog global Neural/LightGBM/XGBoost và học tiếp; không chọn lại ensemble local học từ đầu. Workspace là ứng dụng, không là một ứng viên T1 hiện tại.
- Nhãn tất toán bằng tiền khác đóng do credit note/write-off; partial học riêng và được chọn/lưu cùng T1. Outcome 91 ngày khác knowledge cutoff; thiếu coverage phải censor.
- Catalog v3, adapter `settlement-partial-cash-v2`, luật fit `partial-empirical-prior-v3` và T6 `settlement-partial-paths-v4` có vai trò phiên bản khác nhau. Đọc manifest, không đoán theo tên file.
- Nạp dữ liệu mới đổi công nợ theo ngày biết, chưa tự đổi model. Audit hợp lệ mới thay bundle; đủ lịch mà thiếu nhãn giữ/chờ là hành vi bình thường.
- Kỳ vọng, median, raw quantile và dải đã hiệu chỉnh phải giữ riêng. SHAP tất toán không tự là attribution tiền hoặc hiệu quả liên hệ.
- Forecast cũ giữ dữ liệu/artifact/source/runtime; không dùng active hôm nay để viết lại giải thích hoặc chạy thay engine cũ.
- Kiểm thử phần mềm và kết quả synthetic chưa nghiệm thu chất lượng hoặc tác động trên SME thật. Chưa mở pilot thật từ các bằng chứng này.

## Tồn kho và hồ sơ lịch sử

Ngày 14/11/2026, `agent1/data/` còn 23 JSON: 10 cặp config/manifest được bộ dựng compact sử dụng và cohort/design/calibration. Không có raw hoặc Parquet tại đây; `raw/interim/processed` là các thư mục làm việc trống được mã tự tạo. Metadata không đủ chạy lại train/benchmark. Kiểm [tồn kho](02_Data/README.md), file và hash/source trước khi tái lập, không sinh đè prefix frozen.

`03_Evaluation/` giữ metric/quy trình, `04_AI_Methods/` giữ flow/hợp đồng hiện tại. Log, báo cáo chọn model và protocol cũ đã bỏ theo phạm vi dọn tài liệu. CSV/JSON/model/source snapshot trong `outputs/` giữ đúng bằng chứng phiên bản; không thay hash hoặc số đo để biến biên tập thành phép kiểm mới.

`05_Coding_Agent_Plan/` giữ quy trình phát triển/kiểm chứng; `06_Pilot/` giữ hướng dẫn vận hành và chuẩn bị thử nghiệm. Log Markdown và kế hoạch cũ trong hai thư mục này, cùng log review/fix ngoài docs, đã bỏ. [Bản đồ thí nghiệm](../experiments/README.md) phân biệt nghiên cứu còn mã với serving.

Các bản tổng quan có ngày còn lại ở gốc docs như `HIEU_DU_AN_AGENT1.md`, `METHODS.md`, `HANDOFF.md` có phần lịch sử; đối chiếu bộ flow ở đầu trang khi mô tả runtime. Số đo phải xác định rõ target, cohort, protocol và artifact gốc, không suy từ tên báo cáo đã bỏ.
