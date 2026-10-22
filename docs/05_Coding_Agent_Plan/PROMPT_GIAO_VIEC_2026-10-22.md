# Prompt giao việc tiếp theo cho Agent 1 (sau Sprint 5, 22/10/2026)

Dán nguyên phần trong khung cho coding agent kế tiếp.

---

> Bạn tiếp tục dự án Agent 1 tại `C:\Users\Admin\Downloads\Agent1`, nhánh git `agent1-Khanh` của
> `https://github.com/Khanhhh239/Multi-Agent-Finance.git` (đẩy qua clone riêng `.publish-repo`, dùng `scripts/sprint1/prepare_publish.py --copy`).
> **Đọc trước:** `docs/00_INDEX.md`, `docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md`, `docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md` (mục 8–13).
>
> **Bối cảnh:** không có dữ liệu doanh nghiệp VN thật. Quyết định hiện hành: GO bậc 0 "bóng", NO-GO mọi bậc hành động.
> Cổng: đạt G1, G2, G5, G6, G9, G10, G12, G16, G18; trượt G3, G4, G7, G8, G11, G13 (tgt), G14, G15, G17.
> `tgt2` (luồng đóng băng) và `tgt3` (T9 v2) **đã dùng** — không chọn gì trên chúng. Bộ đích mới: `tgt4`, seed mới, đăng ký trước commit trước khi sinh.
>
> **Việc 1 — G15 (T9): precision đã sửa, recall còn thiếu.** T9 v2 (`G15_T9_V2_PREREG.md`): tgt3 sạch P 0,962 ✓ nhưng F1 0,706 (R 0,557) ✗.
> `tgt3` **đã dùng**. Đã thử và loại: lớp chặn theo độ tin cậy (vô tác dụng), FIFO cho thanh toán từng phần (precision 0,2).
> Hướng còn lại cho recall: (a) mô hình riêng cho chuyển khoản gộp ≥ 3 HĐ có số HĐ một phần trong nội dung CK; (b) ghép thanh toán phần cuối
> (`final`) theo số dư còn lại sau khi đã ghép phần đầu; (c) đặc trưng ngày giá trị NH cho DN ghi sổ theo tháng. Mọi lựa chọn trên DN nguồn;
> đo trên một bộ đích MỚI (`tgt4`, seed mới) với đăng ký trước commit trước khi sinh.
>
> **Việc 2 — G3/G4 (hiệu chỉnh T1).** cov80 0,867/0,844 (khoảng hơi rộng), ECE4 > 0,05. Thử CQR bất đối xứng theo nhóm đáo hạn hiệu chỉnh trên
> cửa sổ nguồn gần nhất; isotonic cho xác suất 4 tuần. Tiêu chí trong `scripts/evaluate_gates.py` — không đổi tiêu chí.
>
> **Việc 3 — G7 (tinh chỉnh M12 ≥ 10%).** Hiện tinh chỉnh không thắng đủ trên tgt. Thử tinh chỉnh có trọng số theo độ gần thời gian và dừng sớm theo
> cửa sổ hiệu chỉnh đích trước O. Không mở rộng sang tgt2.
>
> **Việc 4 — ~~dải tiền mặt mặc định = copula-t + ACI~~ — XONG 22/10** (`agent1_service/jobs/aci_band.py`, `/forecast` lưu trạng thái ACI theo DN).
> Dashboard đã hiển thị `band_method` và `band_note` (22/10).
>
> **Quy tắc bắt buộc:** không dùng tgt/tgt2/test để chọn; mỗi việc xong phải có CSV có `measurement_version` + dòng nhật ký + kiểm thử;
> chạy job nặng tuần tự bằng `scripts/sprint5/wait_ram_then.sh` (RAM máy 15,7 GB, thường chỉ trống 2–3 GB; hai job nặng chồng nhau đã làm chết tiến trình);
> không commit dữ liệu thô, parquet, log, `.state`, token; commit kết thúc bằng dòng `Co-Authored-By`.

---

## Ghi chú cho người giao việc
- Thứ tự gợi ý: Việc 1 (gần đạt, mở khoá G15) → Việc 2 → Việc 3; phần dashboard của Việc 4 nhỏ, làm xen kẽ.
- G8 (SBA, dữ liệu cho vay Mỹ), G11 (cần chuyên gia xác minh quy tắc) và G14, G17 cần dữ liệu hoặc con người, không giải được bằng mã.
