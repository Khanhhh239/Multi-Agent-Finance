# Pha A. Hoàn tất so sánh phương pháp, đóng băng, niêm phong v4

Mục tiêu: có **một cấu hình được chọn bằng quy trình sạch**, đã kiểm thử một lần trên tập niêm phong v4, và mô hình huấn luyện sẵn cho v4. Các nhiệm vụ làm tuần tự.

---

## A1. Tái lập môi trường và dữ liệu (0,5 ngày)

**Đầu vào:** `00_thiet_lap_va_quy_tac.md`.
**Các bước:**
1. Cài môi trường, chạy `pytest tests_agent2 tests_sme_fraud -q` → phải thấy `84 passed`.
2. Sinh `w4_s411..413` và `s4_s931..933` (mục 3 của tệp 00). Kiểm dấu vân tay trong `validation_v4.json`.
3. Nếu dấu vân tay lệch: **dừng**, ghi nhật ký (phiên bản Python, thư viện), thử Python 3.12.x khác; không tiếp tục với dữ liệu lệch vì kết quả `results/` sẽ không so được.

**Xong khi:** 84 bài qua; 6 thế giới khớp dấu vân tay; kết quả ghi trong nhật ký mục mới.

---

## A2. Hoàn tất so sánh phương pháp trên tập phát triển (1 ngày chạy máy, 0,5 ngày công)

**Giả thuyết:** H1 (L4, L4-FB so với L3), H2 (cân bằng họ), H3 (hai tầng). Tiêu chí thành công ở tệp `04_phuong_phap_va_pipeline/08_gia_thuyet_can_thi_nghiem.md`.
**Mã đã có:** `agent2/eval_v4.py` (xem docstring). Mỗi giao thức lưu JSON sau khi xong; chạy lại tự bỏ qua giao thức đã có.

**Các bước:**
1. Vì dữ liệu sinh lại có thể khác chút ít bản đã dùng cho kết quả một phần, **chạy lại từ đầu** để các thế giới nhất quán. Không sao chép `results/v4/method_study_partial` vào `work/results/v4_methods` (chỉ để đối chiếu).
2. Chạy bằng tiến trình tách rời, ghi log:
   ```powershell
   $p = Start-Process -FilePath python -ArgumentList "-m agent2.eval_v4 --data work/data/w4_s411 work/data/w4_s412 work/data/w4_s413 --out work/results/v4_methods --protocols P1,P2,P3" -RedirectStandardOutput work/v4_methods.log -RedirectStandardError work/v4_methods.err -WindowStyle Hidden -PassThru
   ```
   Thứ tự: P1 và P2 từng thế giới, rồi P3 (nạp cả 3 thế giới). Ước tính thời gian: P1 khoảng 8 phút, P2 khoảng 25 đến 50 phút, P3 khoảng 20 phút mỗi thế giới (máy 20 luồng).
3. Theo dõi `work/v4_methods.log`; nếu thấy `MemoryError`, đóng chương trình khác (mã đã ép float32). Nếu tiến trình bị ngắt, chạy lại đúng lệnh: tiếp tục từ giao thức chưa xong.
4. Khi xong, kiểm `work/results/v4_methods/w4_s41{1,2,3}.json` đều có khóa `P1`, `P2`, `P3`.

**Việc phải thêm (tệp mới `agent2/stats_v4.py`):** kiểm định ghép cặp.
- Hàm `paired_bootstrap(te, alerts_a, alerts_b, reps=2000, seed=0)`: lấy lại mẫu **các vụ** (và dòng hợp lệ), trả khoảng tin cậy 95% của hiệu recall@B3 và hiệu vụ tìm thấy.
- Để có được cờ cảnh báo từng cấu hình, `eval_v4.p1_temporal` cần lưu thêm cờ (mảng bool) vào đĩa: thêm tùy chọn `--save-alerts` ghi `.npz`.
- Kiểm thử `tests_agent2/test_stats_v4.py`: hai chuỗi cờ giống nhau cho hiệu 0 và khoảng chứa 0; cờ A luôn tốt hơn B cho khoảng dương.

**Xong khi:** đủ JSON; bảng hiệu L4 − L3, L4-FB − L3, L3-FB − L3, C-L4 − L3 ở P1 kèm khoảng tin cậy; ghi nhật ký.

---

## A3. Chọn cấu hình và đóng băng (0,5 ngày)

**Mã đã có:** `agent2/select_v4.py` (**chưa chạy lần nào**).
**Các bước:**
1. Đọc `select_v4.py` và đối chiếu với quy tắc trong `AGENT2_WORKLOG.md` mục 14. Nếu phát hiện lỗi, sửa **trước** khi chạy lần đầu và ghi nhật ký.
2. Viết `tests_agent2/test_select_v4.py` với kết quả giả (3 dict `P1/P2/P3`) kiểm: ràng buộc báo nhầm loại ứng viên; chênh dưới 0,01 chọn cái đứng trước; chọn riêng cấu hình khởi đầu lạnh trong ba ứng viên không nhãn.
3. Chạy `python -m agent2.select_v4`. Sinh `work/results/v4_frozen.json` (cấu hình chọn, băm tệp, điểm phát triển) và `work/results/v4_methods/selection_table.csv`.
4. Chép `v4_frozen.json` và `selection_table.csv` vào `results/v4/` để đưa lên Git.
5. Ghi vào nhật ký: cấu hình được chọn, cấu hình khởi đầu lạnh, bảng điểm. **Không** đổi quy tắc nếu kết quả không như mong muốn.

**Xong khi:** có tệp đóng băng; kiểm thử qua.

---

## A4. Thử khô `sealed_v4.py` trên thế giới giả (0,5 ngày)

`agent2/sealed_v4.py` **chưa từng chạy**; không được để lần chạy thật là lần chạy đầu tiên.
**Các bước:**
1. Sinh một thế giới thử khô **không dùng seed niêm phong**:
   ```powershell
   python -c "from agent2.world_v4_sealed import generate_v4_sealed; generate_v4_sealed('work/data/v4s_smoke', n=80000, rate=.004, seed=939, companies=16)"
   ```
2. Sao tệp đóng băng thành `work/results/v4_frozen_dryrun.json` (cùng nội dung).
3. Chạy thử với thế giới thử khô thay cho thế giới niêm phong và một đầu ra khác:
   ```powershell
   python -m agent2.sealed_v4 --dev work/data/w4_s411 work/data/w4_s412 work/data/w4_s413 --sealed work/data/v4s_smoke --frozen work/results/v4_frozen_dryrun.json --out work/results/sealed_v4_dryrun.json
   ```
4. Kiểm: không lỗi; JSON có `S1`, `S2`, `known_recall`, `novel_recall`, `new_decoy_alert_rate`, `by_family`; số `test_novel_rows` khớp số dòng của 7 kịch bản mới trong tập kiểm thử của thế giới thử khô (đếm bằng pandas).
5. Viết `tests_agent2/test_sealed_v4.py` kiểm: tập lệnh từ chối chạy khi tệp ra đã tồn tại; từ chối khi băm không khớp (sửa một ký tự trong bản sao tệp đóng băng); `report()` tính đúng `known_recall` và `novel_recall` trên bảng nhỏ.
6. Các điểm nên soi kỹ khi đọc mã: (a) nhãn 7 kịch bản mới bị ẩn đúng ở huấn luyện và kiểm định của S1 nhưng giữ ở kiểm thử; (b) S2 dùng lịch sử chưa gán nhãn của thế giới đích làm tham chiếu; (c) mã giao dịch có tiền tố tên thế giới để không trùng khi gộp; (d) `alerts_for` dùng `s_va` đúng tập.

**Xong khi:** thử khô chạy đầu-cuối và kiểm thử qua.

---

## A5. Chạy niêm phong v4 đúng một lần (0,5 ngày chạy máy)

**Điều kiện:** A3 xong, A4 xong, `git status` sạch với 6 tệp bị đóng băng (không thay đổi từ lúc đóng băng).
```powershell
python -m agent2.sealed_v4 --dev work/data/w4_s411 work/data/w4_s412 work/data/w4_s413 --sealed work/data/s4_s931 work/data/s4_s932 work/data/s4_s933 --frozen work/results/v4_frozen.json --out work/results/sealed_v4.json
```
**Quy tắc:**
- Nếu tiến trình chết do hạ tầng (hết bộ nhớ, mất điện) **trước khi** `sealed_v4.json` được ghi và bạn chưa đọc con số nào, được chạy lại. Nếu đã đọc số từng phần, ghi nhận "đã lộ" trong nhật ký và coi các số đó là phát triển, không phải niêm phong.
- Sau khi có kết quả, **không chỉnh gì**.

**Báo cáo (tệp mới `docs/03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md`):**
1. Bảng cấu hình đã chọn: recall@B3 chung, kịch bản đã biết, kịch bản mới, vụ tìm thấy, báo nhầm ca hợp lệ mới (S1 và S2).
2. Bảng theo kịch bản cho 7 kịch bản mới, cho mọi ứng viên (để biết cái nào mạnh, nhưng **không** được đổi lựa chọn).
3. So với cổng G5 (tệp `03_chien_luoc_kiem_thu.md`) và so với kết quả phát triển: chênh bao nhiêu điểm phần trăm.
4. Thành thật về hạn chế: người viết kịch bản trùng người viết phương pháp; kịch bản `overtime_inflation_group` gần `payroll_padding`.
5. Cập nhật `STATUS.md`, `METHODS.md`, `AGENT2_WORKLOG.md`.

**Xong khi:** có `sealed_v4.json` trong `results/v4/`, báo cáo, và nhật ký.

---

## A6. Huấn luyện mô hình huấn luyện sẵn cho v4 (1 ngày)

**Vì sao:** `models/pretrained_v1.joblib` huấn luyện trên v3 (8 công ty, 12 bộ phát hiện). Hồ sơ `precision` và `wide` của `pipeline.py` cần mô hình trên v4 với cấu hình đã chọn.
**Các bước:**
1. Đọc `agent2/train_pretrained.py` và `agent2/final_eval.py::pretrain`; viết `agent2/train_pretrained_v4.py` huấn luyện: (a) CES với 25 bộ phát hiện; (b) mô hình có giám sát theo cấu hình đã chọn (L3 hoặc L4, kèm các thành phần không nhãn cần thiết); (c) cấu hình khởi đầu lạnh.
2. Huấn luyện trên **w4_s411, w4_s412**; giữ **w4_s413** để kiểm thử; **không dùng thế giới niêm phong**. (Sau khi đã báo cáo niêm phong, được phép huấn luyện bản cuối trên cả 3 thế giới phát triển; ghi rõ.)
3. Lưu `models/pretrained_v2.joblib` kèm `models/pretrained_v2.card.json`: phiên bản mã (băm), thế giới huấn luyện, tham số, danh sách đặc trưng, số liệu phát triển, ngày. Lưu ý đối tượng có `lambda` (như `Supervised.cols_fn`) đã được loại khi lưu (`__getstate__`); cần cung cấp lại hàm chọn cột khi nạp.
4. Chạy `pipeline.py --profile precision --pretrained models/pretrained_v2.joblib` trên w4_s413 và kiểm `case_queue.csv`.

**Xong khi:** mô hình và thẻ mô hình có trong Git; kiểm thử nạp và chấm trên 100 dòng; nhật ký.
