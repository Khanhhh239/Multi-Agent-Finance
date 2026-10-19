# Trạng thái Agent 2 (cập nhật 2026-10-19)

## Vòng v5, cập nhật ngày 2026-10-19

**ĐIỂM DỪNG R1: CHỜ CHỦ DỰ ÁN DUYỆT.** Chủ dự án đã cho phép làm R0 và soạn R1 sau M2. R0 đã hoàn tất; R1 đã có bản đề xuất, chưa được duyệt. Không bắt đầu R2, R3, tải dữ liệu ngoài hoặc R4 trước phạm vi được phép. Kết luận **v4 không đạt G5** giữ nguyên; mọi kết quả R0 là **hậu kiểm, không phải niêm phong**, trên **dữ liệu tổng hợp**.

- **Bước 0 hoàn tất:** đã push bốn commit v4, giữ cả lịch sử cập nhật và hoàn tác của remote, không force-push. Commit đồng bộ cuối `3a3cfe3`; bằng chứng `results/v5/step0_merge_verification.json`.
- **R0 hoàn tất, commit `58d99ba`:** mã `agent2/postmortem_v4.py`; đủ 15 giao thức của L3, L4-FB và Novelty max(R,E). Chỉ số cảnh báo, recall, vụ, ca khó và từng họ của 18 cặp gốc khớp; AP lượt hoàn chỉnh cũng khớp. Hai lượt dừng vì AP rất nhỏ và lỗi mã hóa thông báo cuối được ghi lại, không xóa dấu vết. Tệp v4 và sáu mã nguồn khóa không đổi băm.
- **Kết quả R0:** loại dòng mới chỉ khỏi huấn luyện làm recall L4-FB tăng 5,59 điểm, khoảng 95% từ 1,41 đến 9,91; giảm trọng số nhãn 0 xuống 0,2 tăng 10,07 điểm, khoảng từ 6,86 đến 13,40. Đây là chẩn đoán tổng hợp, không phải kết quả triển khai. Phân rã mô tả mức tụt 39,50 điểm cộng đúng; không quy toàn bộ cho nhiễu nhãn hoặc lịch lương.
- Báo cáo: [08_mo_xe_niem_phong_v4.md](03_danh_gia_va_hieu_qua_kinh_te/08_mo_xe_niem_phong_v4.md). JSON hoàn chỉnh tại `results/v5/postmortem_v4/run3/`; hai manifest đã dừng được giữ riêng. Có bảng theo lịch lương, quy mô, đủ 30 kịch bản đã biết, cấu trúc seed 933 và bootstrap theo vụ.
- **Kiểm chứng R0:** 174 bài và 18 kiểm tra con qua, 401,98 giây; bốn cảnh báo bỏ dần API LightGBM ở phép kiểm công thức gốc, không lỗi. Đủ 18 bảng Markdown hợp lệ. Bằng chứng `results/v5/r0_verification.json` xác nhận băm mọi đầu vào và mã R0, tập vụ không đổi, đối chứng Novelty không đổi và đồng nhất thức phân rã.
- **R1 đã soạn, chờ duyệt chủ dự án:** [08_dang_ky_truoc_v5.md](05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md). Đề xuất S2 là chính; S1 phụ dùng nhãn chưa biết; chọn minimax trên đủ 20 thế giới, trần ca khó 15% ở từng thế giới; cổng v5 và điều kiện đổi hướng được ghi bằng số trước R2. Chỉ tiếp tục R2 sau câu trả lời “duyệt” của chủ dự án. Trạng thái đề xuất máy đọc tại `results/v5/r1_review_state.json`; đây không phải cấu hình đã được phép chạy.

Phần tiếp nhận v4 bên dưới giữ nguyên kết luận lịch sử M2; quyền hậu kiểm R0 và soạn đề xuất R1 là phạm vi mới chủ dự án đã chỉ định, không phải thay cổng v4.

## Tiến độ tiếp nhận ngày 2026-10-16 và 2026-10-17

**DỪNG THEO M2:** A5 đã hoàn tất ngày 2026-10-17. Recall trung bình S1 là **41,31%**, dưới ngưỡng dừng 50%; S2 là **63,87%**. G5 không đạt. Dừng huấn luyện A6, cải tiến B, sản phẩm hóa tiếp và triển khai thí điểm theo điều kiện dừng trong `05_ke_hoach_giao_viec/06_checklist_va_lich.md`. Cần chủ dự án xem lại bài toán trước một hướng công việc mới. Không thay mô hình hoặc chạy lại ba seed niêm phong để tìm kết quả tốt hơn. Báo cáo: [kết quả niêm phong v4](03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md); dữ liệu máy đọc tại `results/v4/sealed_gates.json` và `results/v4/sealed_v4.json`.

- **A1 hoàn tất:** Python 3.12.14, đúng tám phiên bản thư viện gốc; sáu thế giới sinh lại đều qua kiểm định và khớp số dòng gian lận, vụ, kịch bản. Bằng chứng: `results/v4/a1_repro.json`.
- **A2 hoàn tất:** đủ P1, 10 nhánh ACFE P2 và P3 của cả ba thế giới, 24 cấu hình; bootstrap ghép cặp 2.000 lần. Kết quả `results/v4/method_study/`, `results/v4/paired_bootstrap.json`; báo cáo 06 thư mục 03. H1 chưa đạt: chưa thể kết luận L4 vượt L3 chắc chắn.
- **A3 hoàn tất:** khóa **L4-FB**, khởi đầu lạnh **Novelty max(R,E)** theo đúng quy tắc đăng ký trước. Tệp `results/v4/v4_frozen.json`; giữ nguyên sáu băm.
- **A4 hoàn tất:** thử khô seed 939, 80.000 dòng, đủ S1/S2 và 24 cấu hình; 47 dòng gian lận mới khớp nhãn. Thử khô lại với giới hạn bộ nhớ đã qua ngày 2026-10-17; toàn bộ kết quả S1 và S2 giống chính xác lần trước. Bằng chứng: `results/v4/bounded_dryrun_verification.json`, `results/v4/sealed_v4_bounded_dryrun.json`.
- **A5 hoàn tất, G5 không đạt, M2 yêu cầu dừng:** đủ ba thế giới, S1/S2 và 24 cấu hình; lựa chọn vẫn là L4-FB. Khôi phục hạ tầng thành công với một ứng viên đồng thời; hồi quy P3 413 có **1.020 chỉ số giống chính xác**. Sáu băm không thay đổi. Không tạo `models/pretrained_v2.joblib` hoặc `configs/agent2_default.json`.
- C1: bộ nạp vận hành không nhãn theo công ty và tuần ISO; 273 cột số khớp trên 2.113 dòng. QA đầu-cuối bằng Rules đã qua; kiểm tích hợp cấu hình v2 chính thức bị dừng theo M2, chưa hoàn tất C1.
- C3: bộ kiểm tra lược đồ; 200.000 dòng tổng hợp của 411 qua. Đã nối chế độ giảm vào pipeline: chỉ dùng lại C2/C3 khi đủ bằng chứng; tắt các luật và mô hình khác, ghi rõ trong báo cáo. Hợp đồng đầy đủ ở `configs/v4_input_columns.json`.
- C4: chủ dự án xác nhận chưa có mẫu thật. CSV ánh xạ đã qua vòng nhập 1.000 dòng tổng hợp; có khung XML trích dòng hàng, **chưa kiểm chứng với tệp xuất thật**. Xem `05_ke_hoach_giao_viec/adapters.md`.
- C2: đủ 15 mẫu v4, lý do luật và thực thể có bằng chứng, đã nối pipeline; kiểm toàn bộ mẫu trên cảnh báo ba thế giới chưa chạy vì dừng theo M2.
- C5/C6: API Flask, SQLite, cách ly công ty, nhập/chấm/hàng đợi/phản hồi; quyết định chỉ thêm; giao diện gọi API. Học phản hồi có phiên bản riêng, mặc định tắt; chỉ nhận xác nhận hoặc hợp lệ, không coi chưa xem hoặc nghi vấn là âm tính. Biến thể học phản hồi chưa được đánh giá hiệu năng. Ngày 2026-10-17 đã kiểm trực quan lại chuyển công ty, hàng đợi và lưu phản hồi trên bộ QA tổng hợp riêng; ảnh và biên bản `results/v4/ui_review_qa.png`, `results/v4/ui_review_qa.json`. Kiểm tích hợp API với mô hình v2 chính thức bị dừng theo M2.
- C7/C8: có cơ chế băm mã, dữ liệu, mô hình, cấu hình và PSI; chưa đo mục tiêu 100.000 dòng một công ty hoặc mốc 200.000 và 1.000.000 dòng. Tập lệnh đo 100.000 dòng đã chuẩn bị nhưng không chạy sau M2. Không có thẻ mô hình v2 chính thức.
- Pha B chưa bắt đầu các cải tiến B1 đến B12; pha D chưa mở rộng quy mô. Chủ dự án xác nhận **chưa có người viết độc lập cho D4**; mẫu bàn giao tại `05_ke_hoach_giao_viec/independent_scenarios/`. Chưa tải dữ liệu ngoài cho D5; cần đồng ý về nguồn, tệp, dung lượng và giấy phép.
- E2: đã soạn sáu mẫu thí điểm, chưa được luật sư duyệt. Hồ sơ pháp lý phải cập nhật Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP theo nguồn trong `05_ke_hoach_giao_viec/templates/README.md`.
- Kiểm thử cuối ngày 2026-10-17: **165 bài và 18 kiểm tra con qua**, 72,36 giây; không lỗi hoặc cảnh báo trong log. Bằng chứng tại `results/v4/test_verification.json`. Python và JavaScript giao diện qua kiểm tra cú pháp; sáu băm khóa vẫn khớp. Hướng dẫn cục bộ tại `05_ke_hoach_giao_viec/huong_dan_van_hanh.md`, có ghi rõ dừng theo M2.

**Các mục 1 đến 4 bên dưới là bản ghi lịch sử trước vòng tiếp nhận mới; trạng thái hiện tại nằm ở phần trên.** Mọi số liệu vẫn là tổng hợp; chưa có kiểm chứng doanh nghiệp thật hoặc thí điểm.

## 1. Đã hoàn thành và có kiểm chứng

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Đường ống phát hiện: đặc trưng quá khứ, 31 luật + đồ thị, lệch theo thực thể, mô hình không nhãn, mô hình có giám sát, chính sách cảnh báo 2+1, ca theo thực thể, lý do tiếng Việt | Chạy được đầu-cuối trên dữ liệu v3 | `agent2/pipeline.py`, thư mục `results/v3/example_run_precision` |
| Thế giới dữ liệu v3 (8 công ty) và tập niêm phong v3 (3 họ mới, đã chạy một lần) | Xong | `docs/06_ghi_chep_lam_viec/DATA.md`, `results/v3/final_sealed.json` |
| Thế giới dữ liệu v4: 30 kịch bản, 48 công ty ngẫu nhiên hóa, quy trình nền có liên kết, kiểm tra lối tắt | Xong, qua kiểm định | `agent2/world_v4*.py`, `agent2/validate_v4.py` |
| Benchmark theo thời gian trên 3 thế giới v4 | Xong | `results/v4/bench_w4/` |
| Bỏ-một-kịch bản trên thế giới v4 đầu tiên | Xong | `results/v4/lfo_w4_s411.json` |
| 3 thế giới niêm phong v4 (seed 931 đến 933, 7 kịch bản mới, 5 loại ca hợp lệ mới) | **Đã sinh và qua kiểm định, chưa chạy bộ phát hiện nào** | log sinh dữ liệu trong `docs/02_du_lieu/11_kiem_dinh_chat_luong_du_lieu.md` |
| Kiểm thử tự động | 84 bài qua (20 bài của `agent2`, 64 bài gốc của bạn bạn) | `pytest tests_agent2 tests_sme_fraud` |

## 2. Làm dở: cần coding agent kế tiếp hoàn tất

| Hạng mục | Đã có | Còn thiếu |
|---|---|---|
| So sánh phương pháp lai trên thế giới dev v4 (`agent2/eval_v4.py`) | Thế giới 411: xong P1 và P2. Thế giới 412: xong P1, P2 chạy dở (tiến trình bị ngắt) | P2 của 412 và 413, P1 của 413, P3 (doanh nghiệp mới) của cả ba |
| Chọn cấu hình theo quy tắc đăng ký trước (`agent2/select_v4.py`) | Mã viết xong, **chưa chạy lần nào** | Chạy sau khi đủ kết quả dev, ghi tệp đóng băng `work/results/v4_frozen.json` |
| Đánh giá niêm phong v4 một lần (`agent2/sealed_v4.py`) | Mã viết xong, **chưa chạy lần nào, chưa thử khô** | Thử khô trên thế giới `v4s_smoke` rồi chạy thật đúng một lần |
| Mô hình huấn luyện sẵn cho v4 | `models/pretrained_v1.joblib` huấn luyện trên v3 | Huấn luyện bản v2 trên v4 sau khi đóng băng |
| Lý do tiếng Việt cho 15 dấu hiệu đỏ của v4 | Chưa có | Bổ sung vào `ENTITY_REASONS` |

## 3. Chưa làm

- Dữ liệu doanh nghiệp thật (chưa có đối tác thí điểm); nhận dữ liệu từ MISA, hóa đơn điện tử XML.
- Chạy luật trên BPI 2019/2020 và bộ chi trả thành phố để đếm cảnh báo trên 1.000 giao dịch.
- Kiểm tra pháp lý Nghị định 13/2023/NĐ-CP cho giám sát ở mức nhân viên.
- Nối giao diện rà soát với hệ thống thật; dịch vụ API.
- Dòng hàng chi tiết trên hóa đơn (đơn giá theo mặt hàng), sao kê ngân hàng riêng.

## 4. Điều cần nói thẳng

1. AP khoảng 0,5 của mô hình có giám sát trên v4 là **giới hạn trên**: người viết bộ sinh dữ liệu cũng viết 15 đặc trưng dấu hiệu đỏ.
2. Kịch bản niêm phong v4 do cùng người viết nên chưa độc lập tuyệt đối. Biện pháp giảm thiên lệch: không thêm đặc trưng hay bộ phát hiện nào sau khi nghĩ ra các kịch bản đó, và nhãn các kịch bản đó bị ẩn khi huấn luyện.
3. Phương pháp lai (L4, hai tầng) mới có kết quả một phần; chênh lệch với L3 hiện nằm trong sai số (khoảng 3 điểm phần trăm trên khoảng 200 dòng dương). Chưa được kết luận là tốt hơn.
4. Chưa có bằng chứng về khả năng chi trả hay tần suất gian lận thật ở doanh nghiệp nhỏ Việt Nam; tính hiệu quả kinh tế dựa trên giả định (xem thư mục 03).
