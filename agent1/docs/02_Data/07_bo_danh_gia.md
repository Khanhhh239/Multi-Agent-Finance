# Dữ liệu đánh giá và quy tắc tái lập

## Tách ba câu hỏi

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Phần mềm chạy đúng hợp đồng? | UAT/fixture/kiểm thử bất biến trên mã hiện tại |
| Dự báo có chất lượng? | Backtest đúng thời gian, nhãn và phạm vi; validation chọn riêng, audit/test chấm riêng |
| Có giá trị trên SME thật? | Dữ liệu đối tác độc lập và phép đo sử dụng/tác động |

Test xanh, readiness synthetic hoặc demo chưa thay kết quả chất lượng. Giới hạn bằng chứng ở [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md); định nghĩa chỉ số và quy trình chấm ở [Evaluation](../03_Evaluation/README.md).

## Bộ phục vụ kiểm hiện tại

| Khối | Dữ liệu/điểm vào | Điều phải đo |
|---|---|---|
| T0/T9 | [UAT core/lifecycle/large](../../pilot/t0_t9_uat_20261110/README.md) | Nạp và lỗi, vòng đời, tiền lớn chính xác, duyệt/từ chối/đảo, nguyên tử và truy vết |
| T1 + partial | Ledger theo cutoff qua `adaptive/t1_data.py`, phạm vi `payment_coverage.py`; test trong `tests/adaptive/` | Outcome 91 ngày và ngày biết riêng; IBS/xác suất tất toán, cash13, nhãn partial; validation/audit cùng adapter |
| T5 | Nghĩa vụ và `expense_payments` liên kết bank | Phần còn phải trả, ngày dự kiến, không đếm hai lần hoặc mặc định đã trả |
| T6 | Bundle đang phục vụ, scope tài khoản và lịch sử tiền đã đối chiếu | Sai số kỳ vọng/median, phân vị/coverage/CRPS, Brier và phạm vi thu chi |
| T10 | Snapshot đã lưu, SHAP/partial evidence và replay | Khớp công thức/phiên bản, phân rã tiền, không cộng phân vị, replay cùng nguồn ngẫu nhiên |
| Demo | [Đại Phát](../../pilot/demo_dai_phat/README.md) | Tính nhất quán của luồng; đây là doanh nghiệp mô phỏng, không là holdout thật |

T1 phục vụ dùng global → học tiếp local, chọn **bundle T1 + partial**. Chọn/huấn luyện tách khỏi tạo dự báo. Chu kỳ không đủ nhãn giữ/chờ theo audit; không ép chốt bằng test. Đánh giá tiền phải phân biệt AR hiện có, thu hoạt động và số dư bank. Hiệu chỉnh dải phải cùng scope và phiên bản operating/bundle hợp lệ; không mượn sai số của nhánh cũ.

## Quy tắc chia và nhãn

1. Khóa theo World/seed và thời gian. Doanh nghiệp trong cùng World chia sẻ shock, không coi là nhiều môi trường vĩ mô độc lập.
2. Giữ đúng ngày biết; đủ ngày theo dõi và xác nhận phạm vi mới tạo nhãn hoàn chỉnh. Chưa thấy thanh toán không đồng nghĩa sẽ không trả.
3. Không dùng test để chọn tham số hoặc chỉnh máy phát. Nếu đã xem lại holdout, công bố việc dùng lại; cần dữ liệu mới để có đánh giá độc lập tiếp theo.
4. So các model trên cùng ledger, origin, hóa đơn, phạm vi tiền và metric. Chấm tất toán khác chấm tiền partial; số dư bank khác AR.
5. Báo cáo theo doanh nghiệp/World, lịch sử ít/nhiều, tuổi nợ và chế độ shock; bootstrap theo cụm phù hợp.
6. Lưu cohort, schema/contract, feature order, source/hash, bundle, ngày fit/sẵn sàng, seed và budget mô phỏng. Artifact frozen giữ nguyên số đo/hash.

Không tái dùng pipeline tháng 10 `T9 → T1 fine-tune 12 tháng → T4 → T6 + ACI` làm mô tả mặc định ứng dụng. Kết quả BPI/Customer Invoices/SBA/Berka là benchmark lịch sử riêng; muốn chạy lại phải khôi phục nguồn theo protocol tương ứng.

## Provenance cohort v4

[Cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json) khóa 8 World: 4 train, 2 validation, 2 test; smoke ngoài split. Metadata có `source_code_sha256`, hash calibration/OxCGRT/WDI/design và hash manifest từng World; `origin=2024-07-01`, `label_horizon_days=120`, snapshot stride 28 ngày. Đây là protocol nghiên cứu v4, **không thay cửa sổ 91 ngày của runtime hiện tại**.

[Thiết kế v4](../../data/synthetic/v4_shortpay_4shock_20261028_design.json) sửa short-pay và replay bốn template shock giả định. Artifact lịch sử nằm ở `outputs/data/v4_shortpay_4shock_20261028/`; runner là [build_v4_shortpay_4shock.py](../../scripts/build_v4_shortpay_4shock.py). Tồn kho hiện chỉ có metadata, thiếu raw/Parquet; runner kiểm hash nguồn/code nên không có lệnh “chạy lại ngay” trong tài liệu này.

Điểm chất lượng cũ bị kẹp nhãn/phân vị tại 120 ngày không được dùng chứng nhận survival dài hạn. Q90 chạm trần có thể do xác suất tất toán chưa tới 90%, không thể sửa chất lượng bằng cách nâng trần hiển thị. Các nguyên tắc kiểm duyệt được giữ ở [metric kỹ thuật](../03_Evaluation/01_metric_ky_thuat.md); báo cáo Markdown chẩn đoán v4 đã bỏ, artifact/số đo nghiên cứu giữ đúng phiên bản trong `outputs/`.

Cohort v4 là nguồn cho nghiên cứu v5/v6, không tự xác định model active của tenant. GO kỹ thuật trên cohort không nghiệm thu dự báo tiền, cảnh báo hoặc pilot thật.
