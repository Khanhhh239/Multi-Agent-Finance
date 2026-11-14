# Máy phát synthetic: kiến trúc và quy tắc dữ liệu

Mã chính: [world.py](../../agent1/synth/world.py), [decisions.py](../../agent1/synth/decisions.py), [shocks.py](../../agent1/synth/shocks.py), [accounting.py](../../agent1/data/accounting.py), [contracts.py](../../agent1/data/contracts.py). Đây là mô phỏng tác tử có chung trạng thái thị trường trong mỗi World. Các tham số hành vi là giả định mô phỏng nếu chưa có nguồn/ước lượng riêng.

## Sáu lớp sinh

| Lớp | Nội dung |
|---|---|
| L0 · Lịch/vĩ mô | Ngày làm việc, Tết, thanh khoản chung, đường COVID/tín dụng và lịch episode |
| L1 · Doanh nghiệp | Ngành, quy mô, nhân sự, đệm tiền, ghi sổ, các mức phơi nhiễm |
| L2 · Khách hàng | Kỳ hạn, lịch trả, thanh khoản riêng, độ nhạy shock, tranh chấp, hoạt động/rời/quay lại |
| L3 · Hóa đơn | Đơn hàng tuần, lượng có thể đáp ứng, giá bán, ngày lập và giá trị |
| L4 · Thanh toán | Trả đúng hạn, cơ hội trả theo tuần, nhiều lần partial, thu hồi và đóng nợ |
| L5 · Quan sát | Sao kê, ghi sổ theo lô/FIFO, lời hứa, nghĩa vụ, tồn kho và số dư |

Không lấy ngày trả, doanh thu hay trạng thái vỡ nợ tương lai làm đầu vào quyết định ở tuần hiện tại. Vòng đời khách có gia nhập/rời/quay lại, giữ/mở lại bán chịu theo tín hiệu quan sát; `customers.default_date` giữ lần đầu, sự kiện lặp nằm trong `events`. Đơn hàng hiện tại và tồn đầu tuần quyết định mua hàng; chưa liên kết từng hóa đơn tới SKU.

## Nhãn và bất biến kế toán

- `paid_date_true` chỉ xuất hiện khi tiền đủ nghĩa vụ sau giảm trừ có hiệu lực. Đợt tên `final` nhưng còn dư vẫn chưa tất toán; phần short-pay tiếp tục có cơ hội thanh toán.
- Đóng do `credit_note` và `writeoff` là các kết cục riêng, không tự tạo tiền. Hóa đơn còn mở tại `observation_end` là `censored`; chỉ xóa nợ đã xảy ra mới thành nhãn bad debt.
- `paid_amount` theo nghĩa vụ, `cash_received_amount` và `payments.fx_adjustment` giữ phần tiền/chênh lệch khi có FX. Truy lại phân bổ tới `payments.txn_id` và giao dịch bank.
- `daily_cash.balance` là số dư **một tài khoản vận hành**, không phải thanh khoản hợp nhất. Phân loại AR, thu khác, vay, nội bộ và nộp tiền mặt riêng; giao dịch ngoài cửa sổ chỉ phục vụ outcome về sau.
- Số dư đầu tính từ thông tin mở kỳ; chi, rút vốn và dòng bank phải cộng khớp số dư từng ngày. Không dùng bình quân chi cả tương lai để đặt đệm đầu kỳ.

`validate_world` kiểm schema/khóa/tham chiếu, ngày, nhãn quan sát, số tiền, inventory và cân đối bank/cash. Qua contract xác nhận nhất quán kỹ thuật, chưa xác nhận phân phối thực tế.

## Bốn kênh shock

`WorldConfig.shock_schedule` chứa `ShockEpisode`: họ, ngày bắt đầu thứ Hai, số tuần tăng/đỉnh/hồi phục, severity, ngành/vùng và sự kiện tham chiếu. Mặc định danh sách rỗng; episode có thể chồng nhau trong một World.

| Họ | Đường truyền |
|---|---|
| `demand` | Giảm đơn và thanh khoản khách theo phơi nhiễm |
| `supply` | Giảm khả năng đáp ứng, tăng sức ép đầu vào |
| `price` | Đổi giá bán/đầu vào theo hệ số khác nhau, thay lượng cầu |
| `credit` | Giảm thanh khoản, siết giữ bán chịu, tăng chi phí khoản vay |

`shock_truth.parquet` và phơi nhiễm ẩn chỉ cho sinh/kiểm toán. Biên độ, thời gian, truyền dẫn sang tiền vẫn là giả định; tên sự kiện lịch sử không biến replay thành quan sát lịch sử. Vùng lương không phải tọa độ thiên tai hay mạng cung ứng.

Thiết kế [v4](../../data/synthetic/v4_shortpay_4shock_20261028_design.json) phát lại bốn template trong train và có lịch/tổ hợp test riêng. Các họ đã xuất hiện ở train nên test này không chứng minh xử lý họ shock hoàn toàn chưa thấy. Runner chung `build_final_train.py` có protocol giữ episode tín dụng ngoài train/validation; đó là protocol khác, không gán sang v4. Đường credit nền vẫn có thể hiện diện dù episode credit được giữ riêng.

## Ranh giới feature và ngày biết

World có cả truth lẫn quan sát. [SnapshotBuilder](../../agent1/models/features.py) chiếu view T1 nghiên cứu qua allowlist `MODEL_VISIBLE_COLUMNS`; chỉ feature đăng ký đi vào estimator. Ngày trả/đóng tương lai, `shock_truth`, phơi nhiễm và latent factor không vào X.

`macro` lưu `published_date` và `covid_source`; ngày công bố synthetic là quy ước, chưa là vintage lịch sử được xác minh. View công bố chỉ lấy chỉ báo đã có tại T với nguồn phù hợp, không dùng common factor/credit state ẩn. T1 mặc định nghiên cứu không tự dùng macro. Runtime global/local có contract feature riêng; xem [chiến lược dữ liệu](01_chien_luoc_du_lieu.md).

Lời hứa được tạo từ trạng thái còn nợ đã xảy ra, độ tin cậy và nhiễu mới. `kept` được đánh giá bằng thanh toán sau đó; giảm trừ/xóa nợ không là giữ lời hứa trả tiền.

## Hard case đang có trong mã

[hard_cases.py](../../agent1/synth/hard_cases.py) khai báo 12 case. Có mã sinh chưa có nghĩa Parquet hoặc benchmark vẫn còn trên đĩa.

| Case | Mục đích kiểm |
|---|---|
| `lumpy_customer` | Khách tập trung lớn; tỷ trọng đầu vào không bảo đảm đúng tỷ trọng doanh thu thực hiện |
| `group_payer` | Người chuyển tiền khác tên khách/hóa đơn |
| `heterogeneity` | Phân khúc hành vi và độ trễ khác nhau |
| `cod_realistic` | Cấu trúc bán thu ngay/bán chịu |
| `discount_early` | Trả sớm có giảm nghĩa vụ |
| `retention` | Giữ lại phần cuối rất lâu |
| `fx` | Chênh lệch tiền quy đổi; không mặc nhiên là mô hình ngày trả theo FX |
| `credit_note` | Chứng từ gốc bị đóng và chứng từ thay thế; không đại diện mọi vòng đời XML |
| `verbal` | Gia hạn không xuất hiện trong lời hứa quan sát |
| `supply_shock` | Kênh cung tác động đơn/chi/thu |
| `seasonal_extreme` | Mùa vụ mạnh |
| `new_company` | Thiếu lịch sử doanh nghiệp |

Đo từng case theo lỗi nó tạo: dư nợ/nhãn, precision/recall đối soát, sai số tiền, độ phủ hoặc cold start. Không tái dùng bảng tick “chưa có” từ đặc tả trước triển khai.

## Realism và đối chiếu độc lập

`WorldConfig.realism` mặc định `v1`; `v2` là tùy chọn đổi ngày lập cuối tuần, phân tán số tiền và đuôi hóa đơn nhỏ. `customer_realism` cũng là cờ thử nghiệm, chưa đủ cơ sở bật mặc định.

C2ST ở [c2st.py](../../agent1/synth/c2st.py) tách khác biệt thiết kế (`term_days`) khỏi hình dạng/hành vi. Phải so cùng cửa sổ quan sát bằng `match_window`, chia theo công ty và bootstrap theo cụm. Khác độ dài cửa sổ làm lệch số hóa đơn/khách và có thể đảo thứ hạng phiên bản. Bộ ERP tham chiếu trước đây chỉ có sáu business code, CI rộng; dừng dùng AUC đó để chọn tiếp máy phát. Giống ERP nước ngoài chưa xác nhận giống SME Việt Nam.

Hiệu chỉnh dùng thống kê công bố được nêu ở [nguồn tham khảo](08_tai_lieu_tham_khao.md). Tham số đuôi, Student-t, ghi sổ lô, lời hứa, tập trung khách và truyền dẫn shock cần kiểm bằng dữ liệu độc lập; không kiểm máy phát bằng chính tỷ lệ đã dùng để fit.

## Runner, manifest và split

1. Khôi phục nguồn đúng phiên bản, kiểm hash/license và calibration.
2. Khóa thiết kế, seed, cửa sổ và vai trò trước khi sinh; smoke trước khi sinh đầy đủ.
3. Kiểm contract, nhân quả, phân phối theo năm/ngành/seed và metadata từng World.
4. Readiness → khóa cohort → train chỉ trên `train` → chọn bằng `validation` → chấm `test` sau chốt.

[world_manifest.py](../../agent1/data/world_manifest.py) lưu cấu hình, hash nguồn/mã/từng bảng. Thay source/config phải dùng phiên bản/prefix mới, không ghi đè frozen. Hiện chỉ còn config/manifest; quy trình trên cần khôi phục Parquet/raw trước.

Mở rộng theo World/shard độc lập, tránh trùng khóa, giữ macro chung trong World và seed riêng giữa World. Không loại seed vì chỉ số xấu để ép khớp khảo sát. Runtime/RAM phải đo trên phiên bản dự định dùng; số hóa đơn không phải số mẫu độc lập.
