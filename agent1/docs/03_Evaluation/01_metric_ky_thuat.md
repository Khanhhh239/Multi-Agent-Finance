# Metric kỹ thuật theo pipeline hiện tại

Chấm đúng đối tượng và phạm vi: xác suất tất toán khác tiền thu partial, thu AR khác số dư bank, dải phục vụ khác phân vị Monte Carlo gốc. Mã chính ở [t1_data.score](../../agent1/adaptive/t1_data.py), [cash_history](../../agent1/adaptive/cash_history.py) và [runner T6](../../scripts/business/evaluate_t6_new_company.py).

## T1 + partial: chọn bằng tiền, chặn suy giảm phân phối

Với origin o, `A_i` là dư nợ, `c_hat[i,k]`/`c[i,k]` là tỷ lệ tiền dự báo/thực tế của tuần k. Đặt `e_k = Σ_i A_i × (c_hat[i,k] − c[i,k]) / Σ_i A_i`:

```text
cash13(o) = 0,5 × (Σ_k |e_k| + mean_k |Σ_{j≤k} e_j|)
IBS13(o)  = mean theo hóa đơn, có trọng số A_i,
            của mean_k (F_hat_i(7k) − 1[paid_days_i ≤ 7k])²
```

Điểm nhiều origin là trung bình điểm từng origin; cash13 không là MAE mỗi hóa đơn. Validation dùng cùng partial đã fit cho mọi T1; audit so đúng hai bundle thực tế. Xem [T1](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md) cho guard/policy.

Chỉ chấm khoản đủ 91 ngày follow-up có coverage. Tuần chưa đủ quan sát bị censor. Báo cáo cùng số snapshot, hóa đơn duy nhất, dư nợ và origin. Không kẹp outcome chưa biết thành 120 ngày để chấm như ngày trả thật; Q90 vượt chân trời chưa tự là lỗi ghi phân vị và không được giải quyết chất lượng bằng nâng trần hiển thị.

| Chỉ số bổ sung | Cách đọc |
|---|---|
| Brier tại 4/13 tuần | Bình phương sai số xác suất so nhãn đã biết; thấp tốt |
| Calibration/ECE | Ghi binning, trọng số và cohort; không đồng nghĩa xếp hạng tốt |
| Sai số thu tuần/lũy kế VND | Tính trên cùng origin và danh mục, không đánh đồng với pinball ngày tất toán |
| Partial incidence/tỷ lệ | Theo trạng thái và mức hỗ trợ; cần kiểm cả tiền và phân phối, không chỉ nhãn có/không |
| Pinball/MAE ngày trả | Chỉ có nghĩa với target/censoring hợp lệ; chưa là tiêu chí chọn mặc định runtime |

## T6: số dư, phân phối và cảnh báo

Đối chiếu trên cùng phạm vi tài khoản, cutoff, số dư đầu, T5 và trạng thái hoạt động. Tách score thu AR và score số dư. Outcome thiếu sao kê/phạm vi không gán 0.

| Chỉ số | Công thức/ý nghĩa |
|---|---|
| MAE kỳ vọng/median | Sai số so số dư thật; ghi rõ dùng kỳ vọng hay P50 |
| Coverage80 | Tỷ lệ số dư thật trong [P10,P90]; báo riêng raw và dải phục vụ |
| Interval score | `(hi−lo) + 2/α × (lo−y) khi y<lo + 2/α × (y−hi) khi y>hi`, α=0,2 |
| Pinball q | `max(q × (y−y_hat), (q−1) × (y−y_hat))` |
| CRPS | `E|X−y| − 0,5 E|X−X'|`, tính từ mẫu tiền theo tuần |
| Energy score | Chấm cả vector số dư; khoảng cách Euclid chia căn số tuần |
| Brier tuần/cả kỳ | So xác suất với sự kiện dưới cash floor tương ứng; nguy cơ cả kỳ lấy từ cùng đường danh mục |
| Báo giả/bỏ sót/lead time | Cần khóa cash floor, ngưỡng xác suất và cách gom sự kiện trước khi mở outcome |

Không cộng P10 hóa đơn hoặc nhân xác suất các tuần. Không gán dải đã hiệu chỉnh là raw quantile; hiệu chỉnh low/high chưa hiệu chỉnh xác suất cảnh báo. Số đường mô phỏng và sai số MC phải ghi cùng kết quả; kịch bản paired có sai số chuẩn Δ xác suất cả kỳ.

Runner `evaluate_t6_new_company.py` tổng hợp trọng số bằng nhau giữa doanh nghiệp. Chấm dùng snapshot truth chung cho bank/AR/T5/hoạt động; hoàn VAT thực nhận giữ riêng để tránh chẩn đoán sai nguồn lỗi. Kết quả trên cùng doanh nghiệp lặp nhiều tuần không là nhiều doanh nghiệp độc lập.

## T0/T9/T5/T10 và vận hành

| Khối | Cần kiểm/đo |
|---|---|
| T0 | Precision/recall lỗi có nhãn, lỗi số tiền/ngày/quan hệ, nguyên tử lần nạp, lịch sử nguồn |
| T9 | Precision/recall/F1 liên kết trên bộ có đáp án; thêm số tiền phân bổ sai, mơ hồ/không ghép và thao tác duyệt/đảo. Mức đề xuất `auto` chưa là tỷ lệ tự ghi |
| T5 | Nghĩa vụ còn lại, phạm vi lịch, không đếm đôi tiền đã trả/hoàn; test ngày/hồ sơ chưa thay xác minh pháp lý |
| T10 | Cộng khớp SHAP và tiền, đúng snapshot/hash, thiếu hỗ trợ phải hiện thiếu, replay no-op và paired scenario |
| Vận hành | Thời gian/RAM, độ trễ dữ liệu, lỗi nạp, job/CAS, trạng thái challenger, raw/calibrated và phiên bản |

Phân tầng theo lượng lịch sử, khách mới, dư nợ, tuổi nợ, scope, bật/tắt hoạt động và chế độ stress; công bố nhóm xấu. So paired trên cùng origin/doanh nghiệp, bootstrap theo doanh nghiệp/World phù hợp; công bố CI và số cụm. Không coi WAPE giảm là bằng chứng trực tiếp vốn đệm hoặc DSO giảm.
