# Bàn giao nhánh `agent2-v5-drivers` (2026-10-21)

Người làm: phiên hỗ trợ của chủ dự án. Mọi số đo là **dữ liệu tổng hợp**. Các số trên thế giới niêm phong v4 (931 đến 933) là **hậu kiểm chẩn đoán**, không phải bằng chứng chọn cấu hình v5.

## 1. Đã làm

| # | Việc | Tệp | Kiểm thử |
|---|---|---|---|
| D1 | Sửa tận gốc lỗi "nhân viên chưa vào làm" (seed 1017): chốt chung `hire_guard` ở `emit` và `put`. Xung đột cùng ngày được dời dòng sang 1 phút sau giờ vào làm (không tiêu số ngẫu nhiên, nên thế giới sạch giữ nguyên từng byte); xung đột khác ngày báo lỗi kèm tên đường mã | `agent2/world_v5_dev.py` | `test_world_v5_hire_guard.py`: 4 bài đơn vị; kiểm thử thuộc tính 12 thế giới nhỏ (seed 7001 đến 7012) qua khi đặt `AGENT2_SLOW=1` |
| D2 | `change_detect.py`: 23 đặc trưng thay đổi theo thực thể (lương, đơn giá, khách hàng, nhóm cùng người lập, công nợ, khoản định kỳ, tạm ứng) và `EntityDeviation2` (đuôi trái và phải, 21 bộ phát hiện) | `agent2/change_detect.py` | `test_change_detect.py`: so vét cạn, **bất biến tiền tố trên thế giới thật**, quy tắc cùng thời điểm, đơn vị thời gian, đuôi trái |
| D3 | `base_v5.py`: ứng viên `L4-PU` và `L4-PU-E2-AR` (tên đã đăng ký), ma trận đặc trưng mới `{split}_cd.npy`, tùy chọn số cây cố định (`early_stop=None`), lấy mẫu âm có hiệu chỉnh (`negative_fraction`), cảnh báo khi mô hình ít hơn 20 cây; CLI `--prepare-change-world` | `agent2/base_v5.py` | `test_base_v5_drivers.py` cộng các bài cũ |
| D4 | Công cụ kiểm tương đương lấy mẫu | `scripts/check_subsample_equivalence.py` | Chạy trên thế giới thật (việc của Agent 2) |

Toàn bộ: **206 bài qua**, 12 bỏ qua (kiểm thử thuộc tính chậm), 18 kiểm tra con.

## 2. Phát hiện quan trọng (phải đọc trước khi sàng lọc)

1. **Lỗi đơn vị thời gian pandas 3.** `to_datetime(...).astype('int64')` nay ra **mili giây**, không phải nano giây. Đã tìm thấy và sửa trong `change_detect.py`; quét toàn bộ `agent2`, `sme_fraud`, `scripts` không còn chỗ nào khác.
2. **Dừng sớm theo AP trên tập kiểm định làm sụp mô hình.** Trong chẩn đoán chuyển giao (huấn luyện 411 đến 413, chấm 931 đến 933, trọng số PU 0,2, mô hình gọn khoảng 70 cột), dừng sớm có lúc dừng ở **1 cây**. Recall trung bình 3 seed chỉ khoảng 34%, dao động lớn. Huấn luyện 400 cây cố định cho **50,8%**, chênh giữa các seed khoảng ±1,5 điểm. `base_v5.fit_source` mặc định vẫn dừng sớm (`early_stop=60`), nên **cần đăng ký và bật `early_stop=None` trước khi sàng lọc**.
3. **Đặc trưng thay đổi giúp ít nhưng ổn định khi dùng cho mô hình có giám sát.** Cùng thiết lập, 3 seed: recall 50,8% → 52,7%; kịch bản mới 12,3% → 14,4%; báo nhầm ca khó 14,9% → 15,2%. Các đặc trưng có gain lớn: `price_cusum_up`, `price_slope6`, `price_lr2`, `pay_cusum_up`, `grp_pay_up_share`, `pay_lr`.
4. **Ở chế độ không nhãn, `EntityDeviation2` không cải thiện tổng recall.** Trên 931 đến 933:
   - `EntityDeviation2` một mình: recall 12%, nhưng tốt nhất ở kịch bản mới (17%);
   - Novelty cũ: 28,5%;
   - ghép max-rank hoặc chia khe theo kênh: 24 đến 29%.

   **Cổng Cold 40% gần như chắc trượt**; báo trước cho chủ dự án.
5. Đặc trưng thay đổi bắt tốt "bán giá thấp cho một khách" (64%) và "hóa đơn bán khống" (45%) khi đứng riêng, nhưng thua trong ngân sách 3 cảnh báo khi ghép với các kênh khác.

**Về các tệp trong `results/v5/drivers_diagnostics/`:**
- `diag_cd_transfer.json` là lượt **trước khi sửa** lỗi đơn vị thời gian và vẫn dừng sớm; chỉ giữ để truy vết, **không dùng**.
- Số đúng ở mục 2.2 và 2.3 là từ `scripts/diag_cd_seed_check.py` (3 seed, 400 cây cố định, sau khi sửa); đầu ra in ra màn hình, đã chép vào mục trên.
- `diag_cd_sealedv4_fixed.json` là kênh không nhãn sau khi sửa.

## 3. Việc Agent 2 phải làm, theo thứ tự

1. **Merge** `agent2-v5-drivers` vào `agent2-Khanh`. Chạy `pytest tests_agent2 tests_sme_fraud -q`.
2. **Chứng minh bất biến byte của bộ sinh.** `world_v5_dev.py` đổi nên `generation_plan.json` đổi băm và `run()` sẽ từ chối.
   - Sinh lại hai thế giới đã đạt (1001 và 1016) bằng mã mới vào thư mục tạm, so băm mọi CSV với `world_*.json`; phải giống hệt.
   - Ghi bằng chứng `results/v5/development/hire_guard_parity.json`.
   - Cập nhật kế hoạch sinh có ghi chú sửa đổi, không xóa lịch sử.
   - Sinh 1017 đến 1020.
3. **Đăng ký R1 v1.2 trước mọi so sánh:**
   - (a) chính sách số cây cố định 400 cây, lưới lá (7, 15) chọn theo AP kiểm định, kèm lý do ở mục 2.2;
   - (b) lấy mẫu âm có hiệu chỉnh nếu cần cho thời gian chạy, chỉ khi `check_subsample_equivalence.py` đạt (Spearman ≥ 0,95, chênh recall@B3 ≤ 2 điểm) trên 1001 với `L4-PU`; nếu không đạt thì thử 0,2;
   - (c) định nghĩa đầy đủ `L4-PU-E2-AR` = cột L4 + `change_feature_names()`;
   - (d) Cold-Rules-E2 = max hạng (luật, `u_entity`, `ed2_score`) so với kiểm định của chính thế giới đích.
4. Chuẩn bị ma trận: `python -m agent2.base_v5 --prepare-world S` rồi `--prepare-change-world S` cho từng thế giới, mỗi tiến trình một thế giới.
5. Đo khối lượng một lượt (1001, 11 giao thức) **với chính sách đã đăng ký**; báo ước tính giờ máy; dừng chờ duyệt nếu vượt 72 giờ.
6. Chọn w, sàng lọc, tầng chọn, chốt chặn theo đăng ký.

## 4. Không được làm
Không dùng các số hậu kiểm ở mục 2 để chọn cấu hình v5 (chỉ dùng để quyết định đưa gì vào danh sách đăng ký). Không sửa ngưỡng hay cổng. Không chạy niêm phong.
