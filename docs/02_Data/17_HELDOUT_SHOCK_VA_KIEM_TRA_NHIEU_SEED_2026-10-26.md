# Shock held-out và kiểm tra xu hướng trên nhiều seed (26/10/2026)

## Hai kịch bản dành riêng cho test

`scripts/build_final_train.py` nay đưa các episode **cầu, cung, giá** vào train/validation và giữ họ **tín dụng** ngoài hai vai trò đó. `test_000` dùng siết tín dụng đơn lẻ (rise 1, peak 6, recovery 9 tuần; severity 1,3). `test_001` dùng tín dụng kết hợp tăng giá (rise 3, peak 4, recovery 10 tuần; severity lần lượt 1,1 và 0,9), bắt đầu sau Test A bốn tuần. Hai lịch bắt đầu sau mốc chia `origin` và có `reference_event` riêng. Cường độ, độ dài và cơ chế kết hợp là **giả định thử nghiệm synthetic**, chưa phải ước lượng thị trường Việt Nam. Test B giữ riêng tổ hợp cơ chế, không phải một họ shock thứ hai độc lập.

Runner kiểm `shock_truth` thực tế: họ giữ kín phải vắng mặt ở cả train và validation, hai test phải khác lịch và mỗi test phải có tuần shock giữ kín trong cửa sổ cutoff đánh giá. `readiness.json` trước lúc khóa split chỉ chứa outcome audit của train/validation; test chỉ được kiểm manifest, config và lịch shock, tránh nhìn kết cục test để chỉnh máy phát. Cổng held-out cũng áp dụng cho cửa sổ smoke ngắn. Test được sinh bằng seed và manifest riêng, chỉ được dùng để đánh giá sau khi chốt model.

Phạm vi giữ kín là **episode `ShockEpisode('credit')`**, không phải mọi dạng khó khăn tín dụng: đường `credit_crunch` nền 2022–2023 vẫn có trong các World train. Do đó phép thử đo khả năng chuyển sang một episode tín dụng mới và tổ hợp giá–tín dụng, không chứng minh mô hình chưa từng thấy bất kỳ tín hiệu tín dụng nào.

Pilot kiểm kỹ thuật `v3_heldout_pilot_20261026` gồm 1 train, 1 validation, 2 test, 2 doanh nghiệp/World, 2023–2024, seed 97001–97004. Cohort đã khóa tại `data/synthetic/v3_heldout_pilot_20261026_cohort.json`; chi tiết tại `outputs/data/v3_heldout_pilot_20261026/readiness.json`. Cổng held-out **đạt**: train/validation có `demand, supply, price`; `credit` chỉ ở test; Test A có 10 tuần và Test B có 6 tuần tín dụng hoạt động trong cửa sổ đánh giá. Pilot này **không chạy train**, không kiểm cổng xu hướng đủ 2019–2025, không phải bộ train cuối.

## Mười seed đối chứng không episode mới

Ba World v5 đã có (`94317`–`94319`) được ghép với bảy World v6 mới (`94320`–`94326`). Mỗi World gồm 24 doanh nghiệp, 2019–2025, RNG v2, cùng calibration và hash đầu vào OxCGRT/WDI; config chỉ khác `name` và `seed`. Bảy World mới đã qua hợp đồng dữ liệu và có manifest riêng. Hash **toàn bộ code** giữa hai đợt khác nhau vì runner/script audit được sửa giữa hai đợt; mã máy phát không bị sửa trong đợt này. Bảng máy đọc được: `outputs/data/v6_multiseed_trend_20261026.csv`; audit gốc: `outputs/data/v5_lifecycle_audit_20261026.json` và `outputs/data/v6_lifecycle_audit_20261026.json`.

| Seed | Doanh thu thuần 2025/2019 | Khách có hóa đơn 2025/2019 | Doanh thu 2025/2024 |
|---|---:|---:|---:|
| 94317 | 1,173 | 0,942 | 1,040 |
| 94318 | 1,443 | 1,051 | 1,032 |
| 94319 | 0,886 | 0,802 | 0,395 |
| 94320 | 1,042 | 0,930 | 0,875 |
| 94321 | 1,886 | 1,013 | 1,160 |
| 94322 | 1,622 | 0,938 | 0,973 |
| 94323 | 1,715 | 1,039 | 1,056 |
| 94324 | 1,748 | 1,063 | 0,990 |
| 94325 | 1,624 | 1,007 | 1,118 |
| 94326 | 1,537 | 1,064 | 1,140 |

Tỷ số doanh thu 2025/2019 có **min 0,886; trung vị 1,579; max 1,886**. Chỉ **1/10** World có doanh thu 2025 dưới 2019; **0/10** dưới ngưỡng phát hiện sụp đổ 0,6 của cổng nội bộ. Khách có hóa đơn giảm trong **4/10** World; trung vị tỷ số 2025/2019 là **1,010**. Doanh thu năm 2021 dưới 2019 trong **7/10** World, phù hợp việc 2020–2021 có stress vĩ mô trong cấu hình. Doanh thu 2025 thấp hơn 2024 trong **4/10** World; vì thế không được hiểu kết quả dài hạn là mọi năm đều tăng.

Seed `94319` là cảnh báo: doanh thu 2025/2024 chỉ 0,395, trung vị tỷ số này ở cấp doanh nghiệp khoảng 0,424 nên không do một doanh nghiệp lớn duy nhất. `macro.common_factor` của seed này có bình quân 2025 là −1,114; đây là tín hiệu synthetic, chưa phải bằng chứng nguyên nhân thị trường. Cần kiểm thêm độ nhạy của nhân tố chung và nhiều seed độc lập trước khi dùng đuôi phân phối cho train cuối.

## Giới hạn và việc chưa hoàn thành

Mười seed đủ bác bỏ giả thuyết **máy phát luôn ép suy giảm dài hạn**, nhưng chưa đủ để ước xác suất suy giảm hiếm hoặc khoảng tin cậy hẹp; ba seed v5 và bảy seed v6 còn khác hash toàn bộ code. Các World không shock không chứng minh phân phối phù hợp Việt Nam. Pilot held-out chỉ chứng minh tách vai trò và hoạt động của hai kịch bản, chưa đo hiệu năng dự báo trên stress ngoài mẫu. Cần cohort 2019–2025 nhiều seed cho mỗi kịch bản test, cổng fidelity/đối chiếu AR/AP Việt Nam và đánh giá model sau khi khóa train. Không dùng kết quả pilot để chọn lại cường độ shock hay siêu tham số trên test.

Kiểm thử liên quan: `tests/test_final_pipeline.py` và `tests/test_shock_episodes.py` **12 passed**, gồm ca phát hiện họ shock lọt vào train và ca shock không xuất hiện trong kỳ test. Trạng thái hiện tại: **đã có thiết kế, code và pilot held-out; chưa có bộ train cuối được xác thực**.
