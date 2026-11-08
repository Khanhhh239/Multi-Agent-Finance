# Tiến độ triển khai kế hoạch 01–08

Sinh bởi `scripts/implementation_status.py`. Phân biệt mã đã làm, thí nghiệm đã chạy và điều kiện nghiệm thu. **Chưa hoàn thành toàn bộ; chưa đủ điều kiện pilot.**

Bảng kết quả chi tiết: [kết quả hiện có](../03_Evaluation/04_ket_qua_hien_co.md); [cổng hiện hành](../03_Evaluation/GATES_CURRENT.md); [kết quả chưa đạt](../03_Evaluation/KET_QUA_CHUA_DAT.md).

**Chạy lại expand fullweek ngày 21/10/2026: 14/18 job đã hoàn tất.** CSV hazard trước sửa chỉ dùng kiểm toán; xem hậu tố `-fullweek` và nhật ký Sprint 1. G5/G6 v2 dùng giao thức riêng đã sửa.

- workspace_venv: 316 ca, 0 lỗi, bằng chứng `outputs/implementation\tests.xml`.
- fresh_venv_from_requirements: 316 ca, 0 lỗi, bằng chứng `outputs/implementation\tests_clean.xml`.
- Nguồn lớn: 4 thế giới, 600 công ty, 3,500,679 hoá đơn; kết quả trong `outputs/data/big_worlds.csv`.
- E2E: đủ 14 công ty × 52 tuần = True; lượt oracle cùng ngân sách hoàn thành = True. Số và CI ở `outputs/e2e/e2e_metrics.csv`.
- Scaling: dữ liệu lồng nhau [1000000, 3000000, 10000000], hoàn tất lấy mẫu = True. Đã có bảng kết quả huấn luyện.

| Gói | Bằng chứng | Phạm vi và việc còn lại |
|---|---|---|
| WP-0 — Nền, hợp đồng, chống rò rỉ | `outputs/implementation/test_summary.csv` (có) | Môi trường khoá phiên bản; contract và kiểm thử. Xem số ca/exit code bên dưới. |
| WP-1 — T1 | `outputs/t1/A_rolling_origin_src.csv` (có) | Đã đo A/CQR/seed/tuning, bốn nhánh mô hình và BPI không hạn. Các nhánh chưa tự đưa vào mặc định. Còn phép đo nhãn khoảng từ last_seen_open thật; MLP đa nhiệm là nhánh điều kiện, chưa thử. |
| WP-2 — T2/T3 | `outputs/t2_t3/t2_sba_variants.csv` (có) | Đã đo SBA EXEMPT và ablation chu kỳ tại ngày phê duyệt với CI Brier theo proxy DN, hiệu chỉnh FY; trễ công bố 90 ngày là giả định, chưa có vintage SBA thật. T3 tranh chấp→T1 đã đo, chưa tự áp dụng. Home Credit bỏ theo Q1. |
| WP-3 — Thích nghi miền | `outputs/t1/B_domain_adaptation_tgt.csv` (có) | Đã đo DR 1×400 so 20×20 cùng số HĐ theo cặp DN, hai thời điểm nguồn riêng cho test thật/tổng hợp; có CI cặp. DA1–DA4, DA7, onboarding và scaling đã đo. DA5 M3 thiếu cửa sổ hiệu chỉnh hợp lệ. Đã đo thêm IW ngoài nguyên công ty so in-sample/pooled, M6 cùng ngân sách; ablation thăm dò, không tự đổi chính sách. |
| WP-4 — T9 | `outputs/t9/t9_reconciliation_tgt.csv` (có) | Đã đo lai R2/R1/ML, as-of, lan truyền T9→T1 và recall 12 thế giới hard-case trong kỳ 2024-07→2025-06 so R1/R2. G15 còn chưa đạt; đã đo thêm trước/trong/sau sốc cung ứng 2022 bằng mô hình học năm 2020, hiệu chỉnh 2021, giữ tau=.9. Có CI theo DN và nhóm thép/khác. Còn cải thiện phân bổ; chưa đổi G15 bằng kết quả test mới. Không chọn ngưỡng từ các test này. |
| WP-5 — T5 và quy tắc | `outputs/rules/rules_review.csv` (có) | Có registry 27 quy tắc và bộ lịch độc lập cho bảy loại nghĩa vụ bổ sung từ hồ sơ/hợp đồng; 18 tình huống CSV và kiểm thử as-of. Chưa tích hợp lịch mở rộng vào dự báo để tránh đếm trùng; đã có 54 ca nghiệp vụ cho 27 phiên bản quy tắc (tối thiểu hai ca/phiên bản). Còn chuyên gia xác minh, cập nhật pháp lý 2026 và tích hợp lịch mở rộng. |
| WP-6 — T6/T10/E2E | `outputs/e2e/e2e_metrics.csv` (có) | E2E đầy đủ và oracle cùng ngân sách đã xong; thêm ETS/ARIMA/B0 cùng 14 DN×52 tuần, CI theo công ty. Chronos-Bolt Tiny zero-shot đã đo, revision cố định. Trạng thái G12/G13 đọc từ CSV. Đã mô phỏng P0/P1/P2 đủ 14 DN×52 tuần, q=.3/.5/.7, CI cặp theo DN. Đây là giả lập phản hồi thu nợ với lịch thu lý tưởng, chưa chứng minh tác động nhân quả hoặc ROI. Đã chọn copula một/hai nhân tố bằng IS trên nguồn và đo CI cặp trên đích; đây là khoảng thô không ACI, lịch thu lý tưởng. Chưa tự áp dụng mô hình mới. |
| WP-7 — T7 | `outputs/t7/t7_changepoint.csv` (có) | Đã đo T6 có/không bộ điều khiển trong hai cửa sổ khủng hoảng; ngưỡng chọn trên nguồn, cách test >=120 ngày. Xem CSV độ phủ và IS với CI cặp. G14 giữ kết quả phát hiện riêng; còn xác nhận trên điểm gãy thật có nhãn. |
| WP-8 — T8 | `outputs/t1/EF_t8_t9_src_noisy_promises.csv` (có) | Đã đo Brier reliability sạch/nhiễu với lịch sử tuần as-of, CI cặp, API và đặc tả duyệt chat (docs/04_AI_Methods/09_promise_chat_review.md). E vẫn chưa đạt G17; chưa có UAT lời hứa người thật. |
| WP-D1 — Tốc độ máy phát | `outputs/data/generator_benchmark.csv` (có) | Đã vector hoá và đối chiếu seed; chưa chứng minh >=5× trên 1M HĐ. Thời gian big v2 sai do biến đếm vòng lặp đã được vô hiệu hoá, giữ số gốc để kiểm toán. |
| WP-D2 — Hard-case | `outputs/data/hard_case_fidelity.csv` (có) | Đã có 12 trường hợp và ba bản v2 sửa lumpy/discount/supply. Còn tỷ lệ phương sai khách và chuỗi gốc–thay thế–huỷ–điều chỉnh đầy đủ; contract không thay kiểm nghiệp vụ. |
| WP-D3 — Nguồn lớn/C2ST | `outputs/data/big_worlds.csv` (có) | Bốn big worlds qua contract; C2ST còn không đạt. Đã đối chiếu DSO độc lập ba DN-kỳ SMC2024/TCM2022/NTP2024, không chỉnh máy phát. Còn marginal độc lập đầy đủ và mẫu nhiều DN/ngành. |
| WP-D4 — Dữ liệu thật bổ sung | `outputs/berka/cash_metrics.csv` (có) | Đã đo Berka, nguồn thật hiện có và DSO/DPO mô tả từ ba BCTC chính chủ (SMC2024, TCM2022, NTP2024), chưa đại diện ngành/SME. Kaggle/SEC bỏ theo Q1/Q2. Còn mở rộng mẫu BCTC và khảo sát thực tế. |
| WP-9 — Dịch vụ local | `outputs/service/local_validation.csv` (có) | API/UI/nhập file/cảnh báo mã hoá/registry/retrain/weekly đã có. Mặc định NO_GO; mô hình dịch vụ riêng DN khác luồng khoa học nguồn→fine-tune. Docker engine chưa chạy; UAT ba người chưa có. |
| WP-10 — Chuẩn bị pilot | `outputs/pilot/pilot_metrics.csv` (chưa có) | Có biểu mẫu và mã phân tích; chưa có dữ liệu pilot, ROI đo thật hoặc người tham gia. Chưa hoàn tất nghiệm thu ngoài thực tế. |

## Cách tiếp tục

- `python scripts/run_plan.py --jobs <tên job> --fail-fast`; mặc định không chạy trùng các tên lịch sử. Smoke lưu riêng, không ghi đè E2E đầy đủ.
- Nhật ký: `outputs/implementation/run_status.json`; lịch sử lỗi được giữ lại. Thất bại cũ không đồng nghĩa lượt mới thất bại; tiến trình đang chạy chưa được nhận là đã xong.
- Giới hạn CPU, không dùng tgt để chọn tham số, không đổi số bằng cách đổi phép đo. Chạy lại report sau khi các CSV đã ghi xong.
- Không tự điền SEC_USER_AGENT, chấp nhận điều khoản Kaggle, gửi khảo sát/tin nhắn hoặc tạo số UAT/pilot. Dùng df=4, mẫu câu và file cảnh báo theo mặc định đã được cho phép.
- Git của thư mục cha nằm ngoài Agent1; chưa stage/commit hay thay dữ liệu ngoài dự án. Tiến độ cũ giữ ở `TIEN_DO_2026-10-16_lich_su.md`.
