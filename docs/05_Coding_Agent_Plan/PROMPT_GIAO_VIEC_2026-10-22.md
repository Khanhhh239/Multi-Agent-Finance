# Prompt giao việc tiếp theo cho Agent 1 (sau Sprint 5, 22/10/2026)

Dán nguyên phần trong khung cho coding agent kế tiếp.

---

> Bạn tiếp tục dự án Agent 1 tại `C:\Users\Admin\Downloads\Agent1`, nhánh git `agent1-Khanh` của
> `https://github.com/Khanhhh239/Multi-Agent-Finance.git` (đẩy qua clone riêng `.publish-repo`, dùng `scripts/sprint1/prepare_publish.py --copy`).
> **Đọc trước:** `docs/00_INDEX.md`, `docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md`, `docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md` (mục 8–13).
>
> **Bối cảnh:** không có dữ liệu doanh nghiệp VN thật. Quyết định hiện hành: GO bậc 0 "bóng", NO-GO mọi bậc hành động.
> Cổng: đạt G1, G2, G5, G6, G9, G10, G12, G16, G18; trượt G3, G4, G7, G8, G11, G13 (tgt), G14, G15, G17.
> `tgt2` (40 công ty) **đã dùng** cho luồng đóng băng — **không được** dùng để chọn bất cứ gì nữa. Muốn bộ đích mới thì sinh `tgt3` với seed mới.
>
> **Việc 1 — G15 (T9), gần đạt nhất.** Trên tgt: F1 0,796 (cần 0,80), precision 0,925 (cần 0,95).
> Đọc `docs/03_Evaluation/T9_RECALL_DIAGNOSIS.md` mục 2b–3. Đã biết: lớp chặn theo độ tin cậy vô tác dụng (mô hình khách trung vị 1,0 kể cả khi sai);
> liên kết sai đến từ `ML_subset` (precision nguồn 0,87) và `hazard_weighted_subset` (0,54); quy tắc theo số HĐ luôn đúng.
> Làm: (a) **đăng ký trước** luật "phương pháp có precision nguồn < 0,95 thì vào hàng chờ" + hiệu chỉnh lại xác suất gán khách;
> (b) sinh **`tgt3`** (seed mới, `write_xml>0`, cấu hình kiểu tgt) vì tgt đã bị nhìn cho quyết định này; đo một lần trên `tgt3`;
> (c) sau đó mới tới phân bổ thanh toán từng phần. Chọn mọi tham số trên DN nguồn giữ lại (2024H1).
>
> **Việc 2 — G3/G4 (hiệu chỉnh T1).** cov80 0,867/0,844 (khoảng hơi rộng), ECE4 > 0,05. Thử CQR bất đối xứng theo nhóm đáo hạn hiệu chỉnh trên
> cửa sổ nguồn gần nhất; isotonic cho xác suất 4 tuần. Tiêu chí trong `scripts/evaluate_gates.py` — không đổi tiêu chí.
>
> **Việc 3 — G7 (tinh chỉnh M12 ≥ 10%).** Hiện tinh chỉnh không thắng đủ trên tgt. Thử tinh chỉnh có trọng số theo độ gần thời gian và dừng sớm theo
> cửa sổ hiệu chỉnh đích trước O. Không mở rộng sang tgt2.
>
> **Việc 4 — ~~dải tiền mặt mặc định = copula-t + ACI~~ — XONG 22/10** (`agent1_service/jobs/aci_band.py`, `/forecast` lưu trạng thái ACI theo DN).
> Còn lại: hiển thị `band_note`/`aci_ready` trên dashboard (`agent1_service/ui/`).
>
> **Quy tắc bắt buộc:** không dùng tgt/tgt2/test để chọn; mỗi việc xong phải có CSV có `measurement_version` + dòng nhật ký + kiểm thử;
> chạy job nặng tuần tự bằng `scripts/sprint5/wait_ram_then.sh` (RAM máy 15,7 GB, thường chỉ trống 2–3 GB; hai job nặng chồng nhau đã làm chết tiến trình);
> không commit dữ liệu thô, parquet, log, `.state`, token; commit kết thúc bằng dòng `Co-Authored-By`.

---

## Ghi chú cho người giao việc
- Thứ tự gợi ý: Việc 1 (gần đạt, mở khoá G15) → Việc 2 → Việc 3; phần dashboard của Việc 4 nhỏ, làm xen kẽ.
- G8 (SBA, dữ liệu cho vay Mỹ), G11 (cần chuyên gia xác minh quy tắc) và G14, G17 cần dữ liệu hoặc con người, không giải được bằng mã.
