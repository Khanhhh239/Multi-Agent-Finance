# Hướng dẫn đọc và hiểu project Agent 1

> **Tài liệu lưu trữ — nhánh Khanh:** hướng dẫn gốc dưới đây mô tả checkout `agent1-Khanh` tại thời điểm viết. Các tham chiếu không có ở checkout này được ghi rõ tên nhánh. Dùng [hướng dẫn hiện tại](../getting-started.md) để đọc bộ file đang có trên `agent1-Thắng`.

Cập nhật 17/10/2026, đối chiếu tài liệu, mã và file hiện có trong checkout. Đây là lộ trình đọc; không phải xác nhận đã chạy lại mô hình hoặc các kiểm thử.

## 1. Trước hết, project đang làm gì?

Project xây dựng **Trợ lý dòng tiền cho SME Việt Nam có bán chịu B2B**. Mục tiêu là trả lời: **13 tuần tới tuần nào có nguy cơ thiếu tiền, xác suất bao nhiêu, vì sao, nên thu khoản nào trước và nếu khách trả chậm thì sao?**

Tư tưởng chính: dự báo hành vi thanh toán của từng hóa đơn, bổ sung tiền từ doanh thu mới và lịch chi, rồi mô phỏng nhiều đường số dư. Quan hệ cần nhớ:

```text
Số dư cuối tuần = số dư đầu tuần + tiền thực thu − tiền thực chi
```

Doanh thu được ghi nhận chưa chắc đã thu được tiền; hóa đơn đến hạn chưa chắc được trả đúng ngày. Vì vậy, dự án dự báo cả **thời điểm, số tiền và mức bất định**, thay vì chỉ cộng hóa đơn theo ngày đến hạn.

Hiện trạng phù hợp để hiểu là **mã nghiên cứu/thử nghiệm, dữ liệu mô phỏng, kết quả đã lưu và kế hoạch phát triển sản phẩm**. Có nhiều module chạy thí nghiệm; chưa có bằng chứng hệ thống đã vận hành đầy đủ tại doanh nghiệp thật. API/dashboard sản phẩm, tích hợp thực tế và pilot còn trong kế hoạch; demo T10 hiện có lỗi.

## 2. Đọc nhanh trong khoảng 45–60 phút

Thời lượng là gợi ý, tùy nền tảng người đọc. Bảy bước dưới đủ để trình bày lại mục tiêu, cách làm và giới hạn của dự án.

| Thứ tự | Đọc gì? | Đọc để trả lời câu hỏi nào? |
|---|---|---|
| **1** | Problem statement (`docs/01_Business_Analyst/02_problem_statement.md`, nhánh `agent1-Khanh`) | Ai cần sản phẩm, đang đau ở đâu, cần đầu ra gì? Chú ý N1–N7 và các giả thuyết chưa được pilot xác nhận |
| **2** | Yêu cầu và phạm vi (`docs/01_Business_Analyst/06_yeu_cau_va_pham_vi.md`, nhánh `agent1-Khanh`) | Mỗi T có nhiệm vụ gì? Tách mục tiêu sản phẩm khỏi trạng thái thực hiện |
| **3** | Data Card (`docs/DATA_CARD.md`, nhánh `agent1-Khanh`), sau đó mục **5.1** của [báo cáo đối chiếu](../reports/agent1-khanh-thang-comparison.md) | Dữ liệu là gì, nguồn nào, synthetic hay quan sát thật, có cùng domain không? Bản đối chiếu bổ sung các giới hạn nguồn gốc dễ bị bỏ qua ở tài liệu cũ |
| **4** | Pipeline hệ thống (`docs/04_AI_Methods/01_pipeline_he_thong.md`, nhánh `agent1-Khanh`) | Dữ liệu đi qua những bước nào? Hiểu snapshot as-of, nhãn và vai trò của LLM |
| **5** | Tổng quan phương pháp (`docs/METHODS.md`, nhánh `agent1-Khanh`) | Vì sao dùng hazard, mô hình phân vị, copula, CQR/ACI và đối chứng đơn giản? Các mô hình liệt kê là lựa chọn nghiên cứu, không mặc định đã tích hợp hết |
| **6** | Cổng nghiệm thu (`docs/03_Evaluation/03_cong_nghiem_thu.md`, nhánh `agent1-Khanh`) và kết quả hiện có (`docs/03_Evaluation/04_ket_qua_hien_co.md`, nhánh `agent1-Khanh`) | Đánh giá tốt/xấu bằng gì? Có phần thua baseline, chưa đo hoặc cần đo lại không? Đọc cảnh báo CSV cũ trước khi dùng các con số |
| **7** | Nhật ký triển khai (`docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md`, nhánh `agent1-Khanh`) và phần đầu kế hoạch coding (`docs/05_Coding_Agent_Plan/README.md`, nhánh `agent1-Khanh`) | Mã đã thay đổi gì sau lần đo đầu? Việc nào còn tồn đọng? |

## 3. Đọc sâu về phương pháp theo thứ tự này

| Thứ tự | Tài liệu | Điều cần nắm sau khi đọc |
|---|---|---|
| **1. Nền dữ liệu** | Chiến lược dữ liệu (`docs/02_Data/01_chien_luoc_du_lieu.md`, nhánh `agent1-Khanh`) → bộ sinh (`docs/02_Data/04_may_phat_tong_hop.md`, nhánh `agent1-Khanh`) → bộ đánh giá (`docs/02_Data/07_bo_danh_gia.md`, nhánh `agent1-Khanh`) | Phân biệt nguồn quan sát với synthetic; `src/tgt/sens_*`; cách chia thời gian/công ty và nhãn do bộ sinh biết sẵn |
| **2. T1 — trọng tâm thứ nhất** | Hazard thời điểm trả (`docs/04_AI_Methods/02_t1_hazard_thoi_diem_tra.md`, nhánh `agent1-Khanh`) | Hazard là xác suất trả trong một tuần với điều kiện chưa trả trước đó. Từ hazard suy ra phân phối thời điểm trả; so với LightGBM phân vị, AFT và baseline |
| **3. T2/T3/T8** | Các xác suất cấp hóa đơn (`docs/04_AI_Methods/03_t2_t3_t8_xac_suat_hoa_don.md`, nhánh `agent1-Khanh`) | Tách không trả khỏi trả trễ; lịch sử khách/empirical Bayes; Beta–Binomial cho độ tin cậy lời hứa. Chú ý T3 có trường hợp baseline thắng ML |
| **4. T4/T5** | Thu mới và chi (`docs/04_AI_Methods/04_t4_t5_thu_moi_va_chi.md`, nhánh `agent1-Khanh`) | T4 dự báo doanh thu rồi cần chuyển thành dòng thu; T5 chủ yếu là quy tắc, không phải mô hình học máy |
| **5. T6 — trọng tâm thứ hai** | Monte Carlo và conformal (`docs/04_AI_Methods/06_t6_monte_carlo_conformal.md`, nhánh `agent1-Khanh`) | Lấy mẫu nhiều đường thu/chi; copula biểu diễn phụ thuộc giữa khoản thu; Student-t mô tả đuôi dày; ACI điều chỉnh khoảng theo sai số đã quan sát |
| **6. Chuyển miền** | Domain adaptation (`docs/04_AI_Methods/05_domain_adaptation.md`, nhánh `agent1-Khanh`) | Zero-shot, chỉ dữ liệu đích, pooled, fine-tune và trọng số miền. Đây là các phương án cần so sánh, không có bảo đảm chuyển từ synthetic sang SME thật sẽ thành công |
| **7. T7/T9/T10** | Điểm gãy, đối soát và giải thích (`docs/04_AI_Methods/07_t7_t9_t10.md`, nhánh `agent1-Khanh`) | Detector thay đổi, quy tắc/ML đối soát, đóng góp đặc trưng và hành động mô phỏng |
| **8. Hướng nghiên cứu tiếp** | Thí nghiệm đề xuất (`docs/04_AI_Methods/08_thi_nghiem_de_xuat.md`, nhánh `agent1-Khanh`) → tham số/tối ưu (`docs/04_AI_Methods/09_tham_so_va_toi_uu.md`, nhánh `agent1-Khanh`) | Phân biệt giả thuyết đang chờ chứng minh với kết quả đã có; hiểu các lựa chọn kỹ thuật sau khi đã hiểu bài toán |

**Những khái niệm quan trọng nhất:**

- **Snapshot as-of:** chỉ dùng thông tin đã biết tại ngày dự báo; không để số liệu tương lai lọt vào đặc trưng hoặc calibration.
- **Kiểm duyệt phải:** hóa đơn chưa trả tại lúc hết quan sát không đồng nghĩa không bao giờ trả. Nhãn của bộ SBA còn là một bài toán khác: charge-off khoản vay trong chân trời cố định.
- **Phân vị P10/P50/P90:** mô tả các mức của phân phối dự báo. Khoảng P10–P90 có mục tiêu độ phủ 80%; độ phủ thực tế phải đo, không mặc định đúng cho mọi tuần/doanh nghiệp hay cả đường 13 tuần cùng lúc.
- **CQR và ACI:** các cách hiệu chỉnh khoảng dự báo; vẫn phải kiểm tra giao thức calibration, độ trễ lộ diện nhãn và độ phủ ngoài mẫu.
- **Tương quan:** nhiều khách có thể cùng trả chậm; mô phỏng độc lập có thể bỏ sót rủi ro chung. Mức cải thiện của mô hình phụ thuộc phải được so với đối chứng.
- **Baseline:** đúng hạn, lịch sử trung vị/phân vị khách, trung bình doanh thu, quy tắc đối soát… là các mốc phải so; mô hình phức tạp không tự động có giá trị hơn.
- **LLM:** vai trò thiết kế là diễn đạt số đã tính/ hỗ trợ xử lý văn bản; lõi dự báo là mô hình thống kê, ML, quy tắc và mô phỏng. Xem mã để biết chức năng nào đã có.

## 5. Sau đó mới đọc mã: đi theo một đường chạy

Nếu mới tiếp cận, bắt đầu bằng **T1 → T6**, rồi mở rộng sang các khối khác. Khi đọc một hàm, ghi lại: đầu vào, ngày nào được phép nhìn thấy, đầu ra, nơi được gọi và cách đo.

| Thứ tự | Mã | Nên tìm gì? |
|---|---|---|
| **1** | schema.py (`agent1/data/schema.py`, nhánh `agent1-Khanh`), contracts.py (`agent1/data/contracts.py`, nhánh `agent1-Khanh`) | `quality_gate`, `validate_world`, `validate_feature_columns`: dữ liệu hợp lệ và cột nào bị cấm |
| **2** | features.py (`agent1/models/features.py`, nhánh `agent1-Khanh`) | `SnapshotBuilder`, `add_labels`: phần quyết định đặc trưng và nhãn có rò rỉ không |
| **3** | t1.py (`agent1/models/t1.py`, nhánh `agent1-Khanh`) | `expand` → `HazardGBM` → `pmf_from_hazard`; sau đó mới đọc `QuantileLGBM`, CQR và `CureGBM` |
| **4** | run_t1.py (`scripts/run_t1.py`, nhánh `agent1-Khanh`) | `exp_A/B/C/D/EF`: cách nối dữ liệu–mô hình–đánh giá; train/cal/test được tạo ở đâu |
| **5** | t6_cash.py (`agent1/models/t6_cash.py`, nhánh `agent1-Khanh`) | `collection_kernel`, `simulate`, `ACI`: đầu vào phân phối tuần, dòng thu/chi và mẫu số dư |
| **6** | run_t6.py (`scripts/run_t6.py`, nhánh `agent1-Khanh`) | Cách dựng context/cash truth/đối chứng và ghi CSV; đối chiếu tham số thực sự truyền vào `simulate`, không chỉ khả năng hàm hỗ trợ |
| **7** | metrics.py (`agent1/eval/metrics.py`, nhánh `agent1-Khanh`), tests/ (`tests`, nhánh `agent1-Khanh`) | Công thức metric và các tình huống kiểm thử bất biến, as-of, hợp đồng, mô phỏng |
| **8** | real_loaders.py (`agent1/data/real_loaders.py`, nhánh `agent1-Khanh`), crawl.py (`scripts/crawl.py`, nhánh `agent1-Khanh`) | Dữ liệu ngoài bộ sinh được lấy từ đâu và chuyển thành nhãn gì |
| **9** | world.py (`agent1/synth/world.py`, nhánh `agent1-Khanh`), build_worlds.py (`scripts/build_worlds.py`, nhánh `agent1-Khanh`) | Đọc bộ sinh sau khi hiểu dữ liệu đầu vào mô hình; xác định kết quả nào có thể do giả định sinh tạo ra |

## 6. Đọc kết quả thế nào để không hiểu sai?

Đọc theo chuỗi: metric kỹ thuật (`docs/03_Evaluation/01_metric_ky_thuat.md`, nhánh `agent1-Khanh`) → cổng nghiệm thu (`docs/03_Evaluation/03_cong_nghiem_thu.md`, nhánh `agent1-Khanh`) → kết quả và cảnh báo (`docs/03_Evaluation/04_ket_qua_hien_co.md`, nhánh `agent1-Khanh`) → CSV tương ứng. RESULTS_TABLES.md (`docs/RESULTS_TABLES.md`, nhánh `agent1-Khanh`) là bảng tổng hợp, cần đọc cùng ghi chú phiên bản đo.

Không cần nhớ tất cả công thức ngay. Ban đầu chỉ cần phân biệt: **MAE** đo lệch ngày/giá trị điểm; **pinball** đo phân vị; **coverage** đo độ phủ; **interval score/CRPS** đánh giá khoảng/phân phối; **WAPE** đo sai số dòng tiền tương đối; **PR-AUC** đánh giá xếp hạng lớp hiếm; **Brier/ECE** xem chất lượng xác suất; **precision/recall/F1** xem đối soát. Luôn đọc định nghĩa trong mã và biết chỉ số nào càng thấp/cao càng tốt.



