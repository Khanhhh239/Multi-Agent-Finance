# T6: nhiều lần thu, số dư và xác suất thiếu tiền

Engine Workspace là `settlement-partial-paths-v4`, đối chiếu 14/11/2026. Điểm vào [methods.forecast](../../agent1/adaptive/methods.py); adapter [cash_adapter.py](../../agent1/adaptive/cash_adapter.py). Kết quả dựa trên snapshot và bundle đủ điều kiện tại cutoff, chưa là nghiệm thu chất lượng trên SME thật.

## Từ hóa đơn tới chuỗi tiền

`iter_cash_paths` sinh tiền, dư nợ và tuần tất toán từng hóa đơn; `sample_cash` cộng kết quả. Tuần tất toán lấy từ phân phối T1, gồm tail. Mỗi tuần còn nợ có thể nhận partial theo adapter; sau tất toán thu bằng 0. Bắt đầu từ dư nợ quan sát đã trừ tiền/giảm trừ hợp lệ trước cutoff.

| Bất biến | Ý nghĩa |
|---|---|
| Thu lũy kế + dư nợ = dư nợ đầu | Không thu vượt, không thu lại tiền cũ, dư nợ không âm/tăng |
| Tail vẫn có partial | Chưa tất toán trong kỳ không đồng nghĩa mất toàn bộ khoản nợ |
| Tất toán/partial cùng contract | Kỳ vọng giải tích và Monte Carlo dùng cùng hazard/q/tỷ lệ |
| Không nhân risk lần hai | Xác suất xóa nợ riêng không giảm tiếp dòng tiền đã có T1/partial |
| SHAP không cắt danh mục | Giới hạn hóa đơn được giải thích chỉ giới hạn chi phí SHAP |

Danh mục thu gồm mọi công nợ mở đủ điều kiện, kể cả khoản đang tạm hoãn liên hệ; write-off hợp lệ bị loại. Hàng đợi ưu tiên có bộ lọc/giới hạn riêng, không dùng làm danh mục T6.

Mặc định độc lập giữa hóa đơn. `shared_customer_risk` là stress theo khách có gắn nhãn, chưa là mô hình phụ thuộc đã được chọn/kiểm định. Engine giữ trạng thái RNG theo khách rồi phát lại cho hóa đơn đang tính, không giữ ma trận toàn danh mục; vẫn bảo toàn thứ tự rút và kết quả theo seed.

## Tổng hợp thu/chi

```text
Kỳ vọng số dư = số dư đầu
             + thu AR (tất toán + partial)
             + thu nghĩa vụ đã được duyệt trong T5
             + hoạt động nếu bật/đủ điều kiện
             − T5 còn phải trả
             − chi hoạt động bổ sung nếu bật/đủ điều kiện
```

[T5/hoạt động](04_t4_t5_thu_moi_va_chi.md) tách tiền thực trả khỏi lịch; số dư đầu phải đã gồm tiền xảy ra trước cutoff. Số dư chỉ đại diện tài khoản và phạm vi chi đã nêu, không tự là toàn bộ thanh khoản doanh nghiệp.

Forecast cho 1–52 tuần, mặc định 13; ngân sách mặc định 1.000 đường, seed 7, SHAP tối đa 30 hóa đơn. Kiểm input cho phép 100–10.000 đường và SHAP 0–30. Hoạt động chỉ hỗ trợ tối đa 13 tuần; danh mục AR vẫn theo horizon đã chọn. Các giá trị là budget vận hành, không bảo đảm sai số MC hoặc chất lượng ở mọi quy mô.

## Kỳ vọng, median và dải

| Trường | Ý nghĩa |
|---|---|
| `balance`, `expected_balance` | Kỳ vọng giải tích dùng cho phương trình phân rã |
| `median_balance` | Trung vị số dư Monte Carlo |
| `balance_quantiles` | P10/P50/P90 gốc |
| `low`, `high` | Dải phục vụ, có thể đã nới theo sai số ngoài mẫu |
| `raw_low`, `raw_high` | Dải gốc được giữ khi hiệu chỉnh |
| `any_below_floor_probability` | Tỷ lệ đường có ít nhất một tuần dưới ngưỡng trong kỳ |

Không dùng median thay kỳ vọng khi đối chiếu tiền. Không cộng P10 hóa đơn thành P10 danh mục; không nhân các xác suất tuần để tính nguy cơ cả kỳ. Kỳ vọng hoạt động lấy từ cùng residual/chặn âm/top-up như Monte Carlo.

## Hiệu chỉnh dải ngoài mẫu

[cash_history.calibrate_bands](../../agent1/adaptive/cash_history.py) chỉ lấy forecast đã lưu kịp origin, đủ outcome/sao kê và origin không chồng lấn. So ngày tạo theo `Asia/Ho_Chi_Minh`; timestamp có offset được đổi múi giờ, bản legacy naive dùng giờ Việt Nam, thiếu/sai timestamp không đủ bằng chứng prospective.

Các forecast phải cùng horizon, tài khoản, model/mode, scenario, xác nhận chi, adapter/partial/T6, trạng thái new-credit/operating và `operating_identity`. Operating thiếu version không tham gia pool sai số mới. Cần ít nhất 12 origin; thiếu thì `band_status=insufficient_out_of_sample_errors` và giữ dải gốc.

Đủ điều kiện thì nới low/high bằng phân vị sai số ngoài khoảng, lưu dải gốc và số origin. Hiệu chỉnh **không thay** kỳ vọng, median, raw quantile hoặc xác suất cảnh báo. Trạng thái calibrated chưa tự chứng minh độ phủ trên mọi doanh nghiệp hoặc dưới trôi.

## Phiên bản và chu kỳ

`serving_manifest` giữ T1/hash, partial/adapter, nguồn dữ liệu, policy/hash, ready date và thời gian nhánh phụ. Global dùng catalog hash làm nguồn; local dùng hash dữ liệu của lần học được chấp nhận. Một lần thử cập nhật không đạt giữ định danh T1/partial; metadata update và mốc nhánh phụ mới lưu riêng.

Thanh toán mới đổi dư nợ ngay theo ngày biết nhưng chưa đổi T1. Học định kỳ dùng chung API/worker/job, tách khỏi dự báo; xem [T1 + partial](T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md). Không kế thừa score/hiệu chỉnh của protocol v1/v2/v3 như score của v4.

## Chấm thực tế và chạy kịch bản

Chấm dùng cùng snapshot `as_of(truth_asof)` cho bank và các thành phần; sửa/xóa chỉ biết sau ngày đó không thay nhãn đã chốt. Hoàn VAT thực nhận là `actual_obligation_in`, có đối chiếu lũy kế riêng; không gọi là AR hoặc chi âm. Quy trình lock → predict → score nằm ở [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md).

[T10](T10_BUNDLE_EVIDENCE_2026-11-13.md) phát lại baseline/kịch bản từ artifact/dữ liệu/engine đã lưu với cùng RNG. Dời thu chuyển cả partial lẫn tất toán sau khi sinh; dời chi giữ top-up theo lịch gốc và chỉ chuyển khoản đã chọn. Thu/chi ra ngoài kỳ giữ riêng, không thành mất nợ/xóa nghĩa vụ.

Engine `models/t6_cash.py` và `/forecast` research còn bên gọi riêng; chúng không phải engine của `/v1/predict`. Bằng chứng từ pipeline đó phải ghi đúng phiên bản và không thay kết luận nghiệm thu của runtime này.
