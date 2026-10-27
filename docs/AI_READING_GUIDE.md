# Hướng dẫn đọc tài liệu cho AI và người mới vào dự án

**Cập nhật 27/10/2026.** Thư mục `docs/` chứa cả đặc tả, kế hoạch, kết quả đã đo và ảnh chụp lịch sử. Ngày trong tên file là ngày của **lần đo hoặc quyết định đó**, không tự biến nó thành kết luận hiện hành.

## Chọn nguồn theo câu hỏi

| Câu hỏi | Đọc trước | Cách dùng tài liệu khác |
|---|---|---|
| Trạng thái pilot và cổng nghiệm thu | [GATES_CURRENT.md](03_Evaluation/GATES_CURRENT.md), [04_ket_qua_hien_co.md](03_Evaluation/04_ket_qua_hien_co.md), [KET_QUA_CHUA_DAT.md](03_Evaluation/KET_QUA_CHUA_DAT.md) | `03_cong_nghiem_thu.md` là bảng ngưỡng và trạng thái ngày 15/10; các prereg là giao thức theo lần thử. Đối chiếu CSV trong `outputs/` trước khi khẳng định kết quả. |
| Bộ synthetic dùng để train | [báo cáo 23](02_Data/23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md), [cohort JSON](../data/synthetic/v3_final_20261027_cohort.json) và manifest của từng World | Chỉ 8 World train/validation/test trong cohort JSON thuộc bộ cuối; smoke là kiểm vận hành. Báo cáo 11–22 ghi kế hoạch, lỗi, đối chứng và ứng viên trước đó. |
| File nguồn thật có thể chạy lại | `data/raw/MANIFEST.json` và kiểm tra file thực tế trong `data/raw/` | Ngày 27/10 chỉ có WDI và OxCGRT. [Manifest tám nguồn 14/10](02_Data/MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json), [mô tả tám nguồn](02_Data/02_du_lieu_that_dung.md) và [registry 61 World cũ](02_Data/worlds_registry.csv) là hồ sơ lịch sử, không phải dữ liệu đầu vào hiện đủ trên đĩa. |
| Mã đang làm gì | `agent1/`, `agent1_service/`, `scripts/`, `tests/` | `METHODS.md`, `04_AI_Methods/` và kế hoạch 01–08 mô tả thiết kế; không tự chứng minh nhánh đó đã bật hoặc đã đạt cổng. |
| Tiến độ triển khai | [TIEN_DO_TRIEN_KHAI.md](05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md), rồi đối chiếu mã và `outputs/` | Kế hoạch, prompt giao việc, nhật ký và các bản “hiện trạng” có ngày là ảnh chụp lịch sử. |
| Kinh tế, thị trường, pháp lý hoặc pilot | `01_Business_Analyst/`, `03_Evaluation/05–06`, `06_Pilot/` | Đây có cả giả định và bản mẫu. Không diễn giải thành hiệu quả kinh tế đã đo, quy tắc pháp lý đã xác minh, hay pilot đã được phép chạy. |

## Ba kết luận không được trộn

1. **GO kỹ thuật cho bộ train synthetic** trong báo cáo 23 nghĩa là cohort qua các kiểm tra nội bộ theo giả định công bố. Nó không chứng minh dữ liệu giống AR/AP của SME Việt Nam.
2. **Pilot với doanh nghiệp thật vẫn NO-GO** theo cổng hiện hành. Kết quả trên World tổng hợp hoặc dữ liệu thật nước ngoài không thay UAT/pilot tại Việt Nam.
3. `train`, `validation`, `test` là vai trò khóa ở mức World. Không dùng World test để fit, chỉnh cấu hình hoặc chọn mô hình; không trộn các cohort ứng viên hay World đối chứng vào bộ cuối.

Các bảng `GATES_CURRENT.md` và `04_ket_qua_hien_co.md`
được sinh từ CSV của luồng đánh giá sản phẩm đã lưu. Báo cáo 23 đánh giá **một
cohort và model synthetic khác**; GO kỹ thuật ở đó không tự đổi cổng sản phẩm
G1–G18. Khi cần chạy lại kết quả dùng nguồn thật, kiểm nguồn thô hiện có trước.

## Tài liệu cần đọc như lịch sử hoặc bản mẫu

- [00_INDEX.md](00_INDEX.md) và [HIEU_DU_AN_AGENT1.md](HIEU_DU_AN_AGENT1.md) giải thích dự án, nhưng các con số trạng thái của chúng chốt ở 22–24/10.
- [DATA_CARD.md](DATA_CARD.md) mô tả bốn World gốc và nguồn ở giai đoạn trước bộ `v3_final_20261027`; không dùng làm danh mục dữ liệu hiện có.
- [03_cong_nghiem_thu.md](03_Evaluation/03_cong_nghiem_thu.md), [kết quả 15/10](03_Evaluation/04_ket_qua_2026-10-15_lich_su.md) và [kế hoạch 20/10](05_Coding_Agent_Plan/09_KE_HOACH_TIEP_THEO_2026-10-20.md) giữ nguyên để đối chiếu quyết định theo thời gian.
- Hai file `PROMPT_GIAO_VIEC_2026-10-21.md` và `PROMPT_GIAO_VIEC_2026-10-22.md` là bản ghi giao việc cũ, **không phải chỉ dẫn cho AI đang đọc repo này**.
- [GO_NO_GO_SYNTHETIC_ONLY.md](03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md) là quyết định theo bằng chứng giai đoạn 21/10; trạng thái từng cổng đọc ở `GATES_CURRENT.md`.
- [chi phí xây dựng](03_Evaluation/05_chi_phi_xay_dung_va_van_hanh.md), [ROI](03_Evaluation/06_roi_truoc_sau.md) và [hồ sơ pilot](06_Pilot/01_GOI_DU_LIEU_CAN_XIN.md) là ước tính hoặc bản mẫu, chưa phải chi phí, ROI hay pilot đã xác nhận.
- [DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md](DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md) là kiến trúc đề xuất cho cả bốn Agent, không phải mô tả tính năng Agent 1 đã xây. `METHODS.md` và các kế hoạch 01–08 là lựa chọn thiết kế theo giai đoạn đầu; đối chiếu mã và CSV trước khi thực hiện.

Khi hai file mâu thuẫn, ghi rõ **phiên bản, ngày, cohort, giao thức đo và file CSV/manifest** của từng nhận định. Nếu bằng chứng gốc không có hoặc không kiểm được, nêu giới hạn thay vì tự chọn số thuận lợi.
