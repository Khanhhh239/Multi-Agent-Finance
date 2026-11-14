# Nghiệm thu và kiểm thử pipeline hiện tại

## Trạng thái bằng chứng

Đối chiếu mã và tài liệu ngày **14/11/2026**. Có triển khai và kiểm thử chức năng cho T0/T9 → T1 + partial → T5/T6 → T10. Chưa có bộ đánh giá độc lập trên SME thật đủ để tuyên bố pipeline mới sẵn sàng pilot; giữ kết luận **chưa nghiệm thu/pilot thật NO-GO**. Dọn/gộp tài liệu không thay model active, trạng thái tenant hoặc số đo frozen.

Các bảng G1–G18 tháng 10, điểm Khánh/v4/v5/v6/unified và quyết định giữ Workspace cũ thuộc target/catalog/adapter khác. Đã bỏ các báo cáo Markdown đó khỏi thư mục hiện tại; CSV/JSON/source snapshot nghiên cứu còn có thể tra trong `outputs/` đúng phiên bản. Không kế thừa điểm cũ cho catalog v3/partial/T6 v4 hoặc đổi hash báo cáo để giả thành phép đo mới.

## Ba mức kiểm chứng

| Mức | Điều kiện |
|---|---|
| Chức năng | Bất biến dữ liệu/tiền, nguyên tử, cutoff, artifact và replay đúng; có lỗi thì sửa trước khi chấm chất lượng |
| Chất lượng dự báo | Protocol khóa trước outcome, baseline phù hợp, scope và nhãn đủ, báo cáo theo doanh nghiệp với độ bất định |
| Giá trị/triển khai thật | Ledger đối tác độc lập, quyền dùng dữ liệu, kiểm tra nghĩa vụ/pháp lý, UAT và phép đo tác động phù hợp |

Audit chọn bundle ở tenant chỉ là quyết định so model theo policy của doanh nghiệp đó; chưa thay nghiệm thu toàn sản phẩm. Runtime vẫn giữ `pilot_ready=false` khi chưa có kiểm định triển khai riêng.

## Bộ kiểm thử duy trì

| Nhóm | Vị trí và ca cần giữ |
|---|---|
| T0/T9 | [UAT](../../pilot/t0_t9_uat_20261110/README.md), `tests/adaptive/test_t0_t9_uat_pack.py`; lỗi nạp, vòng đời, duyệt/từ chối/đảo, số tiền lớn và lịch sử |
| T1/partial | `test_cash_adapter.py`, `test_t1_periodic.py`, `test_t1_review_fixes.py`, `test_t1_remaining_fixes.py`, `test_t1_registry_ui.py`; nhãn/coverage, prior, FIFO, ngày/registry và snapshot nhất quán |
| T5 | `test_t5_runtime.py`, `tests/test_obligations.py`; nghĩa vụ còn lại, bank/hoàn, định danh và không cộng hai lần |
| T6 | `test_t6_acceptance.py`, `test_t6_operating.py`, `test_t6_memory.py`; invariants thu/nợ, kỳ vọng/MC, scope, RNG và phần hoạt động |
| Chấm | `test_t6_new_company.py`, `test_t6_scope_backtest.py`; đóng băng, truth cutoff chung và phân rã tiền |
| T10/UI/export | `test_t10_bundle.py`, `test_cash_explanations.py`, các `.test.cjs` trong `tests/adaptive/`; SHAP/partial, hash, replay, kịch bản và Excel |

Đường dẫn test không có tiền tố đầy đủ trong bảng là dưới `agent1/tests/adaptive/`. Chạy nhóm liên quan với interpreter/môi trường dự án; không lấy số ca test trong log cũ làm kết quả lần chạy mới. Đợt dọn tài liệu chỉ kiểm nội dung/liên kết, không tạo nghiệm thu model.

## Quy trình lock → predict → score

Runner [evaluate_t6_new_company.py](../../scripts/business/evaluate_t6_new_company.py) tách ba pha:

1. **Lock:** khóa doanh nghiệp, dataset/catalog/source hash, policy, budget/seed, tài khoản, số dư/cash floor và quy tắc cảnh báo. Tách doanh nghiệp đã dùng chọn policy/global khỏi nhóm chấm.
2. **Predict:** chỉ dùng dữ liệu biết tại cutoff; thích nghi bằng validation/audit quá khứ. Lưu dự báo global/local, đường số dư, hash và receipt trước khi đọc outcome. Receipt hợp lệ ngăn học lại khi chạy tiếp.
3. **Score:** đọc dự báo frozen rồi mở nhãn đủ phạm vi tại `truth_asof`. Dùng cùng snapshot truth cho bank và thành phần; không dùng sửa đổi chỉ biết sau ngày chấm. Chấm theo [metric](01_metric_ky_thuat.md), tách AR, nghĩa vụ thu/chi và hoạt động.

Config ví dụ là mẫu để người đánh giá điền nguồn thực, không phải dữ liệu sẵn có:

```json
{
  "development_firms": ["FIRM_USED_FOR_POLICY"],
  "companies": [{
    "firm_id": "NEW_FIRM", "dataset": "new_firm.json",
    "cutoff": "2025-12-31", "truth_asof": "2026-04-30",
    "accounts": ["BANK_ACCOUNT"], "opening_balance": 100000000,
    "synthetic": false, "heldout_from_global_and_policy_selection": true
  }]
}
```

`dataset` tương đối với config. Từ gốc repo, khi đã có config/dữ liệu phù hợp:

```powershell
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py lock --config config.json --output agent1/outputs/t6/new_company_run
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py predict --output agent1/outputs/t6/new_company_run
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py score --output agent1/outputs/t6/new_company_run
```

Khai báo holdout là cam kết cần kiểm về nguồn, mã không tự chứng minh chưa từng xem dữ liệu. Không dùng ledger toy hoặc các stress lặp của cùng doanh nghiệp làm nhiều doanh nghiệp holdout thật. Tồn kho nghiên cứu hiện thiếu raw/Parquet; kiểm [Data README](../02_Data/README.md) trước tái lập.

## Điều kiện chốt một phép đo

- Khóa target, coverage/censoring, origin, scope và baseline trước test; model/partial/operating/T6 đúng version.
- Quyết định ngưỡng chấp nhận, gain/guard, số doanh nghiệp và cách báo CI trước outcome; chưa lấy ngưỡng lịch sử làm ngưỡng mới đã thông qua.
- Tách validation chọn cấu hình, audit chọn phiên bản và test/holdout đánh giá sản phẩm. Không đổi ứng viên hoặc protocol để cứu điểm đã thấy.
- Báo số mẫu/cụm, nhóm xấu, lỗi tiền và calibration/cảnh báo cùng nhau; đạt coverage riêng chưa đủ.
- UAT kiểm người dùng đọc đúng số dư kỳ vọng/P50, phạm vi chi, thiếu dữ liệu và kịch bản; không hứa liên hệ khách sẽ tạo tác động mô phỏng.

Kết quả kinh tế cần phép đo riêng theo [giá trị và chi phí](02_metric_kinh_te.md). Các script sinh gate/báo cáo nghiên cứu cũ không là công cụ cập nhật trạng thái nghiệm thu hiện tại.
