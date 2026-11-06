# Phạm vi WP và tiêu chí gốc — bản tham chiếu sau gộp

**Biên tập 06/11/2026 từ bộ kế hoạch 01–08 lập 15–16/10/2026.**
Đây là sổ yêu cầu/giả thuyết ban đầu, **không phải backlog hiện hành hoặc
lệnh giao việc cho AI**. Giữ mã WP và điều kiện quan trọng để truy vết;
các lệnh máy cũ, lịch 12 tuần, danh sách tạo file và phân công đã bỏ.

Trạng thái triển khai đọc ở [bảng sinh từ hồ sơ](TIEN_DO_TRIEN_KHAI.md),
[nhật ký 15–16/10](TIEN_DO_2026-10-16_lich_su.md) và
[nhật ký Sprint 1–6](NHAT_KY_SPRINT1_2026-10-20.md). Các bảng này là bằng
chứng theo thời điểm, không xác nhận bản v6 93 feature hoặc unified đã tích hợp.

Phương pháp đã gộp ở [AI Methods](../04_AI_Methods/README.md), kết quả ở
[Evaluation](../03_Evaluation/README.md), tồn kho ở [Data](../02_Data/README.md).
V4, v5/v6 và các holdout còn giữ; nguồn `data/T1/`, v3 và World đời đầu đã xóa.
Không sinh lại hoặc train chỉ để thực hiện checklist đã hết thời điểm.

<a id="wp-0-1"></a>

## WP-0/WP-1 — nền tảng và T1

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-0.1 | Khóa môi trường; lệnh phát triển lặp lại | Ghim phụ thuộc trực tiếp/đầy đủ; môi trường cài sạch chạy kiểm tra. |
| WP-0.2 | Hợp đồng dữ liệu World | Khóa/tham chiếu/ngày/tiền/số dư; ca lỗi chèn đối nghịch. Danh sách bảng và bất biến thực tế theo contract của phiên bản. |
| WP-0.3 | Chặn rò rỉ snapshot và nhãn | Bỏ dữ liệu tương lai không đổi feature quá khứ; kiểm event, censor và bad_known bằng ca tay. |
| WP-0.4 | Toán hazard, phân vị, CQR | Tổng PMF + survival = 1; quantile đơn điệu; ngày kỳ vọng hợp lệ; kiểm độ phủ trong thiết kế phù hợp. |
| WP-0.5 | Báo cáo từ CSV | CI theo cụm/công ty, mốc đơn giản và kết quả không thắng; sinh lại báo cáo không đổi nội dung với cùng đầu vào. |
| WP-1.1 | CDF từ nhiều phân vị/PCHIP | Đối chứng 9/19 phân vị; giả thuyết lợi thế IBS hazard còn ≥20%, ghi bác bỏ nếu <10%; không trộn giao thức đo. |
| WP-1.2 | Tuning và early stopping | Chọn trên calibration trước test; mục tiêu pinball giảm ≥3%, cov80/ECE không xấu. Bảng thử 50 trial và ngân sách cũ không là lệnh hiện tại. |
| WP-1.3 | CQR hai phía, cho phép thu hẹp | Mục tiêu gốc cov80 78–82%, IS80 không xấu; tiêu chí G3/fullweek sau đó là hồ sơ khác, không viết đè ngưỡng gốc. |
| WP-1.4 | Nhãn khoảng khi không có sao kê | So nhãn sổ, khoảng (last_seen_open, ledger_post_date] và nhãn NH; bản đề xuất EM 2 vòng chưa phải xác nhận trên dữ liệu doanh nghiệp thật. |
| WP-1.5 | Đối chứng AFT | Chọn sigma từ {0.2,0.3,0.5,0.8} trên calibration, giữ cố định khi chấm. |
| WP-1.6 | BPI/thiếu hạn | So feature thay thế và B1d; hạn ảo là giả định phải công bố. Không suy từ một bộ BPI sang mọi doanh nghiệp không có hạn. |
| WP-1.7 | Phân tầng | Khách mới/quen, tiền lớn, kỳ hạn, ngành, Tết/shock, posting/tail; nêu nhóm tệ nhất, yêu cầu gốc không nhóm cov80 <60%. |
| WP-1.8 | Độ bền seed | Seed LightGBM {3,7,11}; mục tiêu gốc CV pinball <0,5%. |
| WP-1.9 | Monotone, daily 28 ngày, mixture, EB học k, đa nhiệm | Các nhánh là đối chứng có điều kiện, không nâng cấp bắt buộc. Kiểm dấu/PDP và so cùng ngân sách; các lựa chọn thực tế ở bảng variant/protocol. |

<a id="wp-2-3"></a>

## WP-2/WP-3 — rủi ro và thích nghi miền

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-2.1 | SBA EXEMPT | Drop/keep/censor; kỳ hạn ≤120 và >120 tháng; mục tiêu gốc PR-AUC/nền ≥5, lệch hiệu chỉnh FY <40%; không dùng tỷ lệ charge-off tương lai. |
| WP-2.2 | Cure trong T6 cũ | Bản đề xuất có nhánh thu hồi 25%, trễ 120–360 ngày và sai khác tổn thất kỳ vọng <2%. Đây là giả định thiết kế cũ; không thêm một lượt T2 vào competing risks/unified. |
| WP-2.3 | T3 và Home Credit | Giữ EB làm mốc; kiểm partial/late trên nguồn có giấy phép. Tiêu chí gốc LGBM thắng EB ≥3% AUC trước khi thay; Home Credit từng bị hoãn do điều kiện truy cập. |
| WP-2.4 | Tranh chấp → T1 | Feature chỉ từ lịch sử biết tại ngày lập; so pinball nhóm tranh chấp; có ablation không đồng nghĩa bật mặc định. |
| WP-3.1 | Đường cong thích nghi | So chiến lược theo M={0,3,6,12,24} tháng, mốc theo cùng lịch sử; thời gian fit và CI theo DN. |
| WP-3.2 | DA1–DA7 | Định nghĩa/tiêu chí ở tài liệu DA; trạng thái từ CSV, không đánh dấu hoàn thành từ việc có code. |
| WP-3.3 | Domain randomization | 1 World ×400 so 20×20, cùng số hóa đơn; tiêu chí gốc pinball zero-shot giảm ≥5% hoặc bác bỏ. |
| WP-3.4 | Khoảng cách miền | Báo domain AUC và feature phân biệt; chính sách lựa chọn chỉ học trên nguồn/quá khứ hợp lệ, không dùng điểm đích để quyết định. |
| WP-3.5 | Thích nghi nhanh | Đối chứng EWM 30 ngày/phần dư 7 ngày trong 2021-07→10 và 2022-10→2023-06; giữ protocol riêng. |
| WP-3.6 | Scaling | 1M/3M/10M hàng khai triển, không gọi là số hóa đơn; đường cong và điểm bão hòa, không mặc định nhiều dữ liệu tốt hơn. |
| WP-3.7 | Onboarding | Chính sách theo M, số dòng và khoảng cách miền; không chọn bằng tập test đã xem. |

<a id="wp-4-5-7-8"></a>

## WP-4/WP-5/WP-7/WP-8 — đối soát, nghĩa vụ và lời hứa

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-4.1 | Tách lỗi khách và lỗi phân bổ | Chấm chọn khách, rồi phân bổ với oracle khách; tránh gán lỗi sai tập hóa đơn cho classifier khách. |
| WP-4.2 | Phân bổ có trọng số/DP/ILP | Đề xuất gốc tập ≤6 trên ≤15 hóa đơn, oracle precision ≥0,95. Các nhánh hazard/FIFO sau đó đã được đối chứng; không gán thiết kế này cho T9 v2 cap=2. |
| WP-4.3 | Ngưỡng và hàng chờ | Isotonic trên nguồn, precision–coverage; mục tiêu precision ≥0,95, tự động ≥60%. |
| WP-4.4 | Lai R2/R1/ML | Quy tắc chắc chắn trước, ML phần còn lại; không ghi đè liên kết đã quyết ở tầng trước. |
| WP-4.5 | Hard case T9 | Đo recall riêng từng tình huống; World cũ đã xóa, kết quả lưu không thay đầu vào tái lập. |
| WP-4.6 | Nhãn NH ước lượng → T1 | Ngày suy ra từ liên kết không tự là truth; so lan truyền sai số. Mục tiêu gốc thu hẹp ≥50% khoảng cách WAPE oracle so sổ. |
| WP-5.1 | Quy tắc theo phiên bản | Effective dates, source, verified; ≥2 ca trước/sau mỗi phiên bản. Code chạy đúng chưa xác minh pháp lý. |
| WP-5.2 | Nghĩa vụ mở rộng | TNCN, nhà thầu, hoàn VAT, thưởng, thuê nhiều bậc, gốc/lãi vay; hồ sơ/known_at và chống tính trùng. |
| WP-5.3 | Nhật ký và kiểm nguồn luật | Theo dõi nguồn, ngày kiểm, điều chưa verified; không coi nguồn cũ là hiệu lực hiện tại. |
| WP-5.4 | Dự phòng tuổi nợ/T2 | Bracket 30/50/70/100% là quy ước trong thiết kế cũ; nguồn và phạm vi chuyên gia cần kiểm, không là lời tư vấn pháp lý hiện tại. |
| WP-7.1 | Bằng chứng danh mục/cụm | Gộp PIT hoặc xác nhận 2/3 bộ phát hiện; mục tiêu detection ≥50%, FA ≤0,5/khách-năm trên giữ lại. |
| WP-7.2 | Tách sốc chung khỏi khách | Phần dư riêng không lẫn sốc danh mục; protocol/chỉ số theo phiên bản. |
| WP-7.3 | Điểm gãy trên dữ liệu thật | Berka/chèn shift và tín hiệu macro là thiết kế kiểm tra; báo động không có nhãn thật không tự thành tỷ lệ phát hiện. |
| WP-7.4 | Controller chế độ | Normal/alert/crisis; đề xuất EWM 30 ngày và ACI gamma ×3; mục tiêu gốc cov80 ≥70% ở hai cửa sổ khủng hoảng. |
| WP-8.1 | Lời hứa nhiễu | Mơ hồ, partial, hứa lặp và thỏa thuận không ghi; không để phép đo chỉ thắng vì lời hứa tổng hợp quá sạch. |
| WP-8.2 | Reliability | Đối chứng Beta–Binomial/recency với mốc; Brier của giữ lời khác chất lượng trích xuất chat. |
| WP-8.3 | Thí nghiệm E | Tiêu chí gốc MAE P50 giảm ≥10% cả với lời hứa nhiễu; đọc CI và G17, không tự thay ngưỡng. |
| WP-8.4 | Nhập lời hứa | Nháp → người duyệt → API; không tự gán ngày mơ hồ hoặc outcome giữ lời. |

<a id="wp-6"></a>

## WP-6 — mô phỏng, giải thích và đầu-cuối

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-6.1 | T6 chạy theo đầu vào as-of | Tách truth chỉ để chấm, B0 tại cutoff; demo/CSV và các đối chứng giữ cùng ngân sách. |
| WP-6.2 | Đối chứng theo triệu chứng | Độ phủ thiếu/dư, cash kernel/cure, bất định chi và hiệu năng; không sửa theo điểm test để cho đạt. |
| WP-6.3 | T10, chính sách và cổng số | Top-50 theo tiền × P(trễ >2 tuần), CRN; P0/P1/P2 với q=.3/.5/.7. Delta giả định không phải nhân quả/ROI; số trong lời phải có trong bảng. |
| WP-6.4 | Ước df từ SEC | Thiết kế dùng dòng tiền hoạt động chuẩn hóa theo tài sản; df=4 vẫn là giả định nếu chưa có nguồn/phép đo hợp lệ. |
| WP-6.5 | Copula phân tầng | Rho danh mục/khách chọn trên nguồn theo IS; không coi một cấu hình đề xuất là tham số đã chọn. |
| WP-6.6 | Đối chứng thêm | ETS/ARIMA, Chronos zero-shot và B0; so đúng cohort, thông tin được cung cấp và mẫu số. |
| WP-6.7 | Chính sách cảnh báo | PR/ROC, chi phí miss/false {2,5,10}; lead time/báo giả theo sự kiện, ngưỡng chọn trên nguồn. |
| WP-6.8 | E2E | XML/sao kê → T9 ước lượng → T1/T4/T5/T6/T10; G12/G13 trên nhãn ước lượng, oracle chỉ là đối chứng; không dùng smoke thay kết quả đầy đủ. |
| WP-6.9 | Berka | Phân vị trực tiếp + ACI trên dòng ròng tuần; phép thử cash thật không kiểm mô hình hóa đơn SME Việt Nam. |

<a id="wp-d"></a>

## WP-D — dữ liệu và máy phát

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-D1 | Tối ưu generator | Profile, vector hóa và đối soát cùng seed; mục tiêu gốc ≥5× ở 1M hóa đơn chưa tự thành kết quả đã đo. |
| WP-D2 | 12 hard case | Đặc tả/nhãn/cách đo tra danh mục Data; hợp đồng cấu trúc khác kiểm nghiệp vụ. Các tỷ lệ COD/độ tập trung/FX trong kế hoạch là giả định gốc. |
| WP-D3 | Nguồn lớn/C2ST | Thiết kế ≥24 World, DR/big, nguồn/seed có hash; mục tiêu C2ST cấu trúc <0,75 và marginal ±3 điểm % là ngưỡng gốc, không xác nhận đại diện SME Việt Nam. |
| WP-D4 | Nguồn bổ sung | Home Credit/M5, SEC, BCTC VN, UNU-WIDER, Payment Times Úc và khảo sát văn phòng kế toán; giấy phép/vintage/định nghĩa quyết định khả năng dùng. |
| WP-D5 | Niêm phong | Tạo seed/World test và khóa protocol trước đánh giá; các tgt đã xem không lại thành fresh, registry cũ không là tồn kho hiện tại. |

<a id="wp-9-10"></a>

## WP-9/WP-10 — sản phẩm và pilot

| Mã | Phạm vi yêu cầu gốc | Điều kiện / giới hạn cần giữ |
|---|---|---|
| WP-9.1 | Tách khoa học và dịch vụ | API/jobs/store/UI, model registry; mục tiêu Docker local cần kiểm chạy thực tế, không suy từ có Dockerfile. |
| WP-9.2 | Nạp dữ liệu | XML nhiều phiên bản, sao kê CSV/Excel, sổ ERP; ánh xạ cột, HMAC/tenant và round-trip trên mẫu tổng hợp. |
| WP-9.3 | Dashboard | Dải số dư, nguồn/độ tin cậy, dữ liệu và hàng chờ, what-if, drift; UAT U1–U6 cần người thật. |
| WP-9.4 | Cảnh báo | Ngưỡng theo chi phí, gộp nguyên nhân, mục tiêu cũ ≤2/tuần/DN; kênh thật không tự được nối từ việc có file mô phỏng. |
| WP-9.5 | Diễn giải | Bảng số → câu, cổng đối chiếu; mục tiêu 200 mẫu, 100% số đúng và đánh giá tự nhiên bởi 3 người. |
| WP-9.6 | MLOps | Hash/as-of/params/metrics, drift/retrain; mục tiêu batch ≤5 phút/DN cần đo ở quy mô sử dụng. |
| WP-9.7 | Dữ liệu và quyền | Mã hóa, tenant, audit/xóa, luồng dữ liệu; không coi code bảo mật hoặc bản cam kết nháp là đã được nghiệm thu. |
| WP-10.1 | Đối tác và hồ sơ | Gói dữ liệu/đồng ý/bảo mật; tiêu chí gốc ≥10 lao động, B2B và ≥12 tháng lịch sử; không tạo đối tác giả. |
| WP-10.2 | Giao thức pilot | Chạy bóng 8–12 tuần, hiển thị 12–24 tuần là thiết kế gốc; baseline và chỉ số K1–K9 cần dữ liệu thực. |
| WP-10.3 | Kinh tế | Thay giả định ROI bằng số đo khi có pilot; mô phỏng chính sách không tự thành tác động kinh tế. |
| WP-10.4 | Dự phòng | Thiếu/bẩn dữ liệu, ít sử dụng, báo giả, lệch model và sự cố; các ngưỡng cũ là đề xuất, không quyền tự thay gate. |

<a id="quyet-dinh-1516"></a>

## Bối cảnh quyết định 15–16/10/2026

Bảng sau giữ câu hỏi/phương án của kế hoạch gốc, không là câu hỏi đang chờ
người dùng trả lời trong phiên hiện tại hoặc bằng chứng về quyền truy cập hôm nay.

| # | Quyết định | Phương án mặc định nếu không có trả lời |
|---|---|---|
| Q1 | Có tài khoản Kaggle để tải Home Credit/M5? | Bỏ qua D4.1–4.2, ghi vào báo cáo |
| Q2 | Email/tổ chức dùng làm User-Agent SEC? | Bỏ qua WP-6.4; dùng df=4, ghi giả định |
| Q3 | Có đối tác pilot hoặc dữ liệu DN thật (ẩn danh)? | Chỉ làm tới WP-9 trên dữ liệu giả lập |
| Q4 | Được dùng LLM nào/ngân sách token? | Dùng mẫu câu (không LLM) |
| Q5 | Kênh Zalo OA có sẵn? | Mô phỏng gửi vào file |
| Q6 | Giá thuê bao mục tiêu (9–18 triệu/năm)? | Giữ giả định hiện tại |
| Q7 | Cho phép fine-tune Chronos? | Chỉ zero-shot |
| Q8 | Chọn nền tảng triển khai (Windows/Linux, cloud)? | Docker local |

### Ghi nhận tại ngày 16/10

- Q1/Q2: người giao việc trả lời chưa có Home Credit và SEC_USER_AGENT.
  Theo phương án mặc định, chưa tải Kaggle/SEC và không tự điền thông tin liên hệ.
- Q3/Q4/Q5: chưa có dữ liệu pilot, đánh giá của ba người, tài khoản LLM hoặc Zalo OA.
  Hiện dùng dữ liệu tổng hợp, mẫu câu và file cảnh báo mã hoá; chưa có gửi tin thật.
- Q6: giữ giả định kinh tế hiện hành; chưa thay bằng ROI đo trên DN thật.
- Q8: đã có cấu hình Docker local, nhưng Docker daemon trên máy chưa hoạt động;
  kiểm tra CLI trả lỗi thiếu pipe `dockerDesktopLinuxEngine`. Tiếp tục xác minh dịch vụ bằng Python local.
- Không coi kết quả smoke E2E là bằng chứng GO. Xem trạng thái sinh từ CSV tại
  `../03_Evaluation/GATES_CURRENT.md` và nhật ký `outputs/implementation/run_status.json`.

## Phụ thuộc và cách đánh giá hoàn thành

Nền/contract/as-of đi trước thí nghiệm; nhãn T9 và lịch chi tác động E2E;
sản phẩm/pilot cần dữ liệu, người dùng và điều kiện nghiệm thu riêng. Đây
là quan hệ phụ thuộc, không lịch chạy hoặc yêu cầu mở nhiều agent.

DoD tổng của kế hoạch gốc từng đòi ≥24 World +12 hard-case, ≥5 nguồn thật,
≥100 test, E2E ≤5 phút/DN, các gate đã đo, báo cáo CI và ROI thật hoặc ghi
rõ giả định. DoD WP-5 từng đặt ≥40 ca quy tắc; WP-6 từng đặt E2E ≤60 phút
trên `tgt`. Chúng là tiêu chí theo phạm vi gốc, không thay tiêu chí đã khóa
của lần thử sau hoặc cho phép sửa gate theo kết quả. Một giả thuyết bị bác
bỏ vẫn là một thí nghiệm hoàn tất; có code/test không tự là nghiệm thu.
