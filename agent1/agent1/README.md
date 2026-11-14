# Bản đồ mã nguồn Agent 1

Mô tả module đang có; [pipeline](../docs/04_AI_Methods/01_pipeline_he_thong.md) là nguồn mô tả flow phục vụ.

| Phạm vi | Mã | Vai trò |
|---|---|---|
| Workspace runtime | [adaptive](adaptive/README.md), `../agent1_service/workspace/` | Snapshot, bundle T1/partial, T5/T6, T10 và API `/v1` |
| T0 | `data/schema.py`, `../agent1_service/ingest/` | Chuẩn hóa/kiểm chứng từ, nguồn và vòng đời; Workspace dùng lại phần ingest |
| T5 | `rules/obligations.py`, `adaptive/obligations.py`, `adaptive/obligation_imports.py` | Lịch từ hồ sơ và từng lần đến hạn, thanh toán/phần còn lại |
| T9 runtime | `reconciliation/`, `../agent1_service/workspace/reconciliation.py` | Constrained flow, sổ quyết định, duyệt/từ chối/đảo và lịch sử |
| T9 nghiên cứu | `models/t9_recon.py`, `t9_fast.py`, `t9_source_policy.py`, `t9_research.py` | Benchmark, chính sách nguồn, hàng chờ/nhãn mềm và mô phỏng người duyệt; không thay quy trình duyệt thực |
| Metric/nghiên cứu | `eval/`, `models/`, `jobs/retrain.py` | Các phép đo và runner có caller riêng; xem [scripts](../scripts/README.md) |

`reconciliation/_thang/` chứa nguồn có provenance/hash và phụ thuộc gián tiếp; không cắt module chỉ vì không thấy import trực tiếp. Artifact cũ có thể cần đường dẫn lớp để giải tuần tự hóa. Module nghiên cứu không được coi là bỏ dùng chỉ từ tên phiên bản; việc dọn Markdown không xóa mã hoặc trọng số.

Các lần tái lập giữ đúng source/runtime/protocol; không sửa hash để coi số đo cũ là kết quả của mã hiện tại. Kiểm thử theo [tests](../tests/README.md), phát triển theo [quy trình](../docs/05_Coding_Agent_Plan/01_quy_trinh_phat_trien_va_kiem_chung.md).
