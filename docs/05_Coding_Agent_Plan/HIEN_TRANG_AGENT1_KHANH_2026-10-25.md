# Hiện trạng codebase trên `agent1-Khanh` — 25/10/2026

Đây là ảnh chụp trạng thái repository tại commit `70c0ceb` (`Security before real data: keys outside the data dir, HMAC pseudonymisation at ingest`). Branch local đang theo dõi `origin/agent1-Khanh` và không có commit đi trước/đi sau theo thông tin Git local. Chưa thực hiện `fetch`, nên chưa xác nhận trạng thái mới nhất trên remote.

## Trạng thái làm việc

- Trước khi tạo bản ghi này, working tree có **một file sửa chưa commit**: `.gitignore`. Thay đổi thêm quy tắc bỏ qua `data/T*/{raw,interim,processed}/` và một số file nghiên cứu T1/script/test local. Không đưa thay đổi này vào kết luận về commit `70c0ceb`.
- `git diff --check` không báo lỗi khoảng trắng trên thay đổi hiện có.
- Có 1.080 file được Git theo dõi trên branch này (đếm từ `git ls-files`).

## Code đang có

| Khu vực | Trạng thái |
|---|---|
| `agent1/data`, `agent1/synth` | Hợp đồng dữ liệu, nguồn thật tham chiếu, máy phát SME và hard cases. |
| `agent1/models`, `agent1/eval` | T1–T10, đặc trưng as-of, dự báo ngày thu và tiền mặt 13 tuần, đối soát T9, đánh giá theo công ty, cổng và chính sách cảnh báo. |
| `agent1/rules` | Registry quy tắc có phiên bản và lịch nghĩa vụ; còn cần chuyên gia xác minh trước pilot. |
| `agent1_service` | API/UI local, nhập XML/CSV/Excel, lưu trữ mã hoá, registry mô hình, monitoring và các job. `/forecast` mặc định trả `409 NO_GO`. |
| `scripts`, `tests`, `outputs` | Giao thức chạy lại, kiểm thử và CSV kết quả. `pilot/` có mã phân tích nhưng chưa có số liệu pilot thật. |

Commit mới nhất đưa khoá Fernet, HMAC và API token sang `AGENT1_KEY_DIR` (mặc định thư mục anh em `<data>-keys`), chuyển khoá cũ nếu không xung đột, và ẩn danh HMAC khi nạp. Đối chiếu T9 trên `tgt3` trong `outputs/pilot/privacy_t9_parity.csv`: F1 từ **0,7058** xuống **0,7002** sau ẩn danh; đây là số liệu trên dữ liệu tổng hợp, chưa phải kiểm chứng trên doanh nghiệp thật.

## Kết quả và điều kiện nghiệm thu

- Trạng thái pilot thật: **NO-GO**. Theo `docs/03_Evaluation/GATES_CURRENT.md`, trong 18 cổng G1–G18 có **9 passed, 8 failed, 1 out_of_scope (G11)**. G3, G4, G7, G8, G13, G14, G15, G17 còn failed. Giai đoạn chỉ dữ liệu tổng hợp cũng chưa đạt vì G13 và G15.
- T1 trên hai bộ dữ liệu thật tham chiếu sau sửa `expand`: BLEND cải thiện pinball so với B1d **6,5% (BPI)** và **14,4% (Customer Invoices)** theo `docs/03_Evaluation/KET_QUA_CHUA_DAT.md`. Các bộ này chưa đại diện SME Việt Nam.
- B1, hàng chờ duyệt T9, có đăng ký trước. Với giả định người duyệt hoàn hảo, 5 lượt duyệt tối đa/tuần cho báo giả **0,970/doanh nghiệp-năm trên `tgt6`**, nhưng **1,371 trên `tgt3`** (ngưỡng 1,0). Kết quả không vững trên cả hai thế giới; quy tắc dừng tối ưu G13 bằng dữ liệu sinh đã được áp dụng. Xem `docs/03_Evaluation/G13_REVIEW_QUEUE_PREREG.md`.
- Gói xin dữ liệu cho doanh nghiệp (A1) đã soạn. Cam kết bảo mật (A2) còn là **bản nháp cần pháp chế rà soát**. Chưa có dữ liệu pilot, UAT người thật, ROI đo thật hoặc kết quả 8 tuần chạy bóng.

## Kiểm thử và khả năng tái lập tại máy hiện tại

- Báo cáo kiểm thử được commit trong `outputs/implementation/test_summary.csv` và JUnit ngày 21/10 ghi **316 ca, 0 lỗi** trên cả môi trường workspace và môi trường cài sạch. Đây là bằng chứng cũ hơn commit mới nhất. Thông điệp commit `70c0ceb` ghi **373 tests pass**, nhưng chưa có artifact JUnit tương ứng trong hồ sơ đã kiểm tra.
- Máy của phiên kiểm tra này không có `python`/`py` trên PATH và không có `.venv/Scripts/python.exe`, nên **chưa chạy lại pytest trên HEAD**. `git diff --check` đã chạy đạt.
- README ghi chuỗi fullweek ngày 21/10 hoàn tất **14/18 job**; không coi những job còn lại là đã hoàn tất.

## Việc cần xử lý gần nhất

1. **Sửa đường dẫn khoá sau commit bảo mật.** `agent1_service/jobs/weekly.py` vẫn đọc `<state>/encryption.key`, trong khi `agent1_service/api.py` chuyển khoá sang `AGENT1_KEY_DIR`. README dịch vụ, README gốc và `docs/security_privacy.md` vẫn chỉ token/khoá trong `.state`; cần cập nhật theo đường dẫn mới.
2. **Kiểm tra Docker trước khi dùng.** Image chạy bằng user `agent` và chỉ cấp quyền ghi `/state`, còn `AGENT1_KEY_DIR` mặc định sẽ là `/state-keys` (thư mục con của `/`). Cần gắn volume và cấp quyền phù hợp hoặc đặt đường dẫn khoá ghi được, rồi build/chạy thực tế. Hồ sơ hiện ghi Docker daemon chưa được kiểm chứng.
3. Hoàn thành công cụ CSV đối chiếu mã ẩn danh cho Bên A, quy trình xoá và biên bản, kênh nhận file mã hoá, và rà soát pháp lý bản cam kết trước khi nhận dữ liệu thật; các mục này được ghi trong `docs/06_Pilot/02_CAM_KET_BAO_MAT.md`.
4. Tập trung A3/A4: nạp thử trọn luồng một doanh nghiệp và lập bảng theo dõi dự báo so với thực tế. Quyết định sửa định nghĩa cổng thuộc chủ dự án; giữ nguyên lịch sử đánh giá nếu thay đổi.

Nguồn chính: `README.md`, `docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md`, `docs/05_Coding_Agent_Plan/CHIEN_LUOC_TIEP_THEO_2026-10-24.md`, `docs/03_Evaluation/GATES_CURRENT.md`, `docs/03_Evaluation/G13_REVIEW_QUEUE_PREREG.md`, `docs/06_Pilot/02_CAM_KET_BAO_MAT.md`, các CSV nêu trên và mã ở `agent1_service/`.
