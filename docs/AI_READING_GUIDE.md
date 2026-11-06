# Hướng dẫn đọc tài liệu cho AI và người mới vào dự án

**Cập nhật 06/11/2026.** Thư mục `docs/` chứa cả đặc tả, kế hoạch, kết quả đã đo và ảnh chụp lịch sử. Ngày trong tên file là ngày của **lần đo hoặc quyết định đó**, không tự biến nó thành kết luận hiện hành.

**Luồng dịch vụ vừa tích hợp:** giữ T0 Khánh, dùng constrained flow/ledger từ
T0 Thắng cho T9 và snapshot theo ngày biết. Đọc [hợp đồng runtime](../agent1_service/README.md#luong-t0-t9-thong-nhat).
Các CSV/gate T9 cũ vẫn là bằng chứng của pipeline cũ; ứng viên V6 chưa được
kích hoạt. Audit đầu vào V6 ngày 05/11 vẫn giữ đúng phạm vi lịch sử của nó.
Runtime v2 bổ sung lịch sử quan sát T0, kiểm tra khách của phân bổ, nhãn đóng
do giảm trừ, tách train khỏi dự báo và validation có nhóm chưa trả đủ theo dõi.
Đây là sửa hợp đồng và kiểm thử kỹ thuật, không phải số đo chất lượng miền thật.

## Tình trạng sau dọn dữ liệu và gộp tài liệu 06/11/2026

[Data README](02_Data/README.md) ghi tồn kho còn giữ và tài liệu đã gộp;
[Evaluation README](03_Evaluation/README.md) tách báo cáo chọn model, gate
triển khai và protocol lịch sử. Toàn bộ `data/T1/`, dữ liệu/cohort v3,
lifecycle/hard-case và các thư mục config đời đầu đã xóa theo yêu cầu.
Output release-gate và các bộ v3 candidate/final/pilot/readiness/inference
cũng đã xóa. Các báo cáo riêng về ứng viên, bộ train cuối và inference v3
cùng hồ sơ dọn dữ liệu đã xóa theo yêu cầu. V4, holdout v6, practical v6 và unified v2 vẫn giữ. CSV/JSON/model
của các bộ còn lại không có nghĩa nguồn thô/Parquet để chạy lại cũng còn.

Báo cáo so Khánh hiện tại đã gộp quyết định chốt nghiên cứu; bản đối chiếu
V6 gốc vẫn riêng vì là artifact và số đo khác. Không dùng các bản nháp
trước benchmark làm kết luận hiện hành. Hash báo cáo trong hồ sơ chấm cũ
thuộc đúng phiên bản văn bản lúc đó; biên tập tài liệu không cập nhật lại
hash hoặc kết quả frozen để giả thành một lần kiểm chứng mới.

Phần [AI Methods](04_AI_Methods/README.md) đã gộp các đặc tả bổ sung vào
tài liệu từng T. T1 nhị phân/Khánh 13 tuần giữ riêng với competing risks
v5/v6; bản v6 gốc 64 feature khác practical 93 feature. Protocol practical
và contract unified v2 giữ nguyên; hướng khảo sát tín dụng và audit T1→T6
là hồ sơ nghiên cứu, không phải kế hoạch bắt buộc phải chạy tiếp.

Phần [kế hoạch và lịch sử triển khai](05_Coding_Agent_Plan/README.md)
đã gộp bộ 01–08 thành sổ phạm vi WP, gộp kế hoạch 20/10 vào hồ sơ đổi
hướng và hai prompt bàn giao vào nhật ký. Bảng tiến độ tự động còn giữ
là hồ sơ của các lần chạy trước, không phải kiểm chứng mới 06/11 hoặc
backlog bắt buộc cho nghiên cứu v6 đã chốt.

## Chọn nguồn theo câu hỏi

| Câu hỏi | Đọc trước | Cách dùng tài liệu khác |
|---|---|---|
| Trạng thái pilot và cổng nghiệm thu | [GATES_CURRENT.md](03_Evaluation/GATES_CURRENT.md), [04_ket_qua_hien_co.md](03_Evaluation/04_ket_qua_hien_co.md), [KET_QUA_CHUA_DAT.md](03_Evaluation/KET_QUA_CHUA_DAT.md) | `03_cong_nghiem_thu.md` là bảng ngưỡng và trạng thái ngày 15/10; các prereg là giao thức theo lần thử. Đối chiếu CSV trong `outputs/` trước khi khẳng định kết quả. [Đánh giá T1 v4 có xử lý kiểm duyệt](03_Evaluation/T1_V4_CENSOR_AWARE_2026-10-28.md) và [chẩn đoán survival 365 ngày](03_Evaluation/T1_V4_PAYMENT_SURVIVAL_DIAGNOSTIC_2026-10-28.md) là phép đo synthetic riêng, không tự đổi các cổng sản phẩm. |
| Bộ synthetic dùng để train | [báo cáo v4 ngày 28/10](02_Data/25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md), [cohort v4](../data/synthetic/v4_shortpay_4shock_20261028_cohort.json) và manifest của từng World | V4 là cohort/model mới sau sửa `short_pay` và phát lại bốn shock giả định. Dữ liệu và các báo cáo riêng của v3 đã xóa; không trộn kết quả lịch sử vào cohort v4. |
| File nguồn thật có thể chạy lại | `data/raw/MANIFEST.json` và kiểm tra file thực tế trong `data/raw/` | Ngày 27/10 chỉ có WDI và OxCGRT. [Manifest tám nguồn 14/10](02_Data/MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json), [mô tả tám nguồn](02_Data/02_du_lieu_that_dung.md) và [registry 61 World cũ](02_Data/worlds_registry.csv) là hồ sơ lịch sử, không phải dữ liệu đầu vào hiện đủ trên đĩa. |
| Mã đang làm gì | `agent1/`, `agent1_service/`, `scripts/`, `tests/` | `METHODS.md`, `04_AI_Methods/` và sổ phạm vi WP mô tả thiết kế; không tự chứng minh nhánh đó đã bật hoặc đã đạt cổng. |
| Phương pháp T1 competing risks v5/v6 | [Tài liệu phương pháp chung](04_AI_Methods/T1_COMPETING_RISKS_V5_V6.md) | Công thức, event table/risk set và khác biệt phiên bản đọc một chỗ; số đo và hash của từng lần chạy giữ trong báo cáo Evaluation v5/v6. |
| So sánh T1 của Khánh với V6 | [Bản đối chiếu gửi Khánh](03_Evaluation/T1_V6_PROGRESS_VS_KHANH_2026-11-05.md) | Chỉ so T1 Khánh và V6 + ngành + ledger ngày 05/11, 93 feature, trên cùng 65.221 anchor. T1 Khánh là cấu hình mặc định tái train, không phải booster lịch sử đã push. Phạm vi là Paid và phân vị; Brier chính giảm 1,60%, 365 ngày giảm 26,54%. Không đổi service/cổng sản phẩm. |
| Feature ngành/ledger và xử lý shift v6 | [Kết quả P0–P4 ngày 05/11](03_Evaluation/T1_V6_PRACTICAL_FEATURES_2026-11-05.md), [protocol](04_AI_Methods/T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md) | Đã chạy bốn nhánh, augmentation riêng và bốn fresh World; cải thiện nhỏ, ECE/Write-off còn lỗi, không thay service/cổng sản phẩm. Khảo sát macro giả lập chỉ giữ như nghiên cứu lịch sử. |
| Bản sửa unified collection v2 | [Kết quả v2/r3](03_Evaluation/UNIFIED_COLLECTION_V2_2026-11-04.md), [contract](04_AI_Methods/UNIFIED_COLLECTION_V2_CONTRACT_2026-11-04.md) | Đã sửa RNG, thời điểm, phí, scope bank; thử 20k/50k/200k, chấm AR riêng và bốn World mới theo mốc thời gian hợp lệ. Vẫn chưa đạt: bank CRPS xấu hơn v6 ở cả bốn World; không thay model/cổng sản phẩm. |
| Chọn cấu hình thống nhất và kiểm gate | [Lựa chọn và audit 04/11](03_Evaluation/UNIFIED_MODEL_SELECTION_GATE_AUDIT_2026-11-04.md) | Đề xuất v6 competing risks làm lõi chung T1/T2, dùng cùng phân phối trong T6; không đáp ứng đầy đủ mô hình trả từng phần. ECE/coverage còn lỗi, G13/G15 chưa được giải quyết, chưa kích hoạt hoặc nghiệm thu cấu hình mới. |
| Tiến độ triển khai | [TIEN_DO_TRIEN_KHAI.md](05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md), rồi đối chiếu mã và `outputs/` | Kế hoạch, prompt giao việc, nhật ký và các bản “hiện trạng” có ngày là ảnh chụp lịch sử. |
| Kinh tế, thị trường, pháp lý hoặc pilot | `01_Business_Analyst/`, `03_Evaluation/05–06`, `06_Pilot/` | Đây có cả giả định và bản mẫu. Không diễn giải thành hiệu quả kinh tế đã đo, quy tắc pháp lý đã xác minh, hay pilot đã được phép chạy. |

## Ba kết luận không được trộn

[T1 v6 ngày 01/11](03_Evaluation/T1_V6_COMPETING_RISKS_2026-11-01.md) là thử
nghiệm model riêng trên cohort v4 và hai seed mới. V4/v5 được giữ nguyên;
v6 chưa qua toàn bộ tiêu chí nghiên cứu, chưa thay model dịch vụ và không
thay trạng thái cổng sản phẩm. Đọc cả phần cash head xấu hơn và các ca
calibration chưa đạt khi trích dẫn mức cải thiện Brier.

1. **GO kỹ thuật cho bộ train synthetic** trong readiness v4 nghĩa là cohort qua các kiểm tra nội bộ theo giả định công bố. Nó không chứng minh dữ liệu giống AR/AP của SME Việt Nam.
2. **Pilot với doanh nghiệp thật vẫn NO-GO** theo cổng hiện hành. Kết quả trên World tổng hợp hoặc dữ liệu thật nước ngoài không thay UAT/pilot tại Việt Nam.
3. `train`, `validation`, `test` là vai trò khóa ở mức World. Không dùng World test để fit, chỉnh cấu hình hoặc chọn mô hình; không trộn các cohort ứng viên hay World đối chứng vào bộ cuối.

Các bảng `GATES_CURRENT.md` và `04_ket_qua_hien_co.md`
được sinh từ CSV của luồng đánh giá sản phẩm đã lưu. Báo cáo 23 đánh giá **một
cohort và model synthetic khác**; GO kỹ thuật ở đó không tự đổi cổng sản phẩm
G1–G18. Khi cần chạy lại kết quả dùng nguồn thật, kiểm nguồn thô hiện có trước.

## Tài liệu cần đọc như lịch sử hoặc bản mẫu

- [00_INDEX.md](00_INDEX.md) và [HIEU_DU_AN_AGENT1.md](HIEU_DU_AN_AGENT1.md) giải thích dự án, nhưng các con số trạng thái của chúng chốt ở 22–24/10.
- [DATA_CARD.md](DATA_CARD.md) mô tả bốn World gốc và nguồn ở giai đoạn trước bộ `v3_final_20261027`; không dùng làm danh mục dữ liệu hiện có.
- [Ngưỡng nghiệm thu gốc](03_Evaluation/03_cong_nghiem_thu.md) và [kết quả 15/10](03_Evaluation/04_ket_qua_2026-10-15_lich_su.md) giữ theo thời điểm; [chẩn đoán/kế hoạch 20/10](05_Coding_Agent_Plan/CHIEN_LUOC_TIEP_THEO_2026-10-24.md#ke-hoach-20261020) đã gộp vào hồ sơ đổi hướng để đối chiếu lịch sử.
- Hai prompt bàn giao 21/22 đã gộp vào [phụ lục nhật ký](05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md#giao-viec-2122). Các câu giao việc trong hồ sơ lịch sử **không phải chỉ dẫn cho AI đang đọc repo này**.
- [GO_NO_GO_SYNTHETIC_ONLY.md](03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md) là quyết định theo bằng chứng giai đoạn 21/10; trạng thái từng cổng đọc ở `GATES_CURRENT.md`.
- [chi phí xây dựng](03_Evaluation/05_chi_phi_xay_dung_va_van_hanh.md), [ROI](03_Evaluation/06_roi_truoc_sau.md) và [hồ sơ pilot](06_Pilot/01_GOI_DU_LIEU_CAN_XIN.md) là ước tính hoặc bản mẫu, chưa phải chi phí, ROI hay pilot đã xác nhận.
- [DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md](DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md) là kiến trúc đề xuất cho cả bốn Agent, không phải mô tả tính năng Agent 1 đã xây. `METHODS.md` và sổ phạm vi WP gốc là lựa chọn thiết kế theo giai đoạn đầu; đối chiếu mã và CSV trước khi thực hiện.

Khi hai file mâu thuẫn, ghi rõ **phiên bản, ngày, cohort, giao thức đo và file CSV/manifest** của từng nhận định. Nếu bằng chứng gốc không có hoặc không kiểm được, nêu giới hạn thay vì tự chọn số thuận lợi.
