# Sprint 6: đăng ký trước T9 recall, G3/G4 và G7 (22/10/2026)

Giao việc: `PROMPT_GIAO_VIEC_2026-10-22.md`. GO chỉ bậc 0 bóng; không đổi cổng.
Tài liệu này phải được commit trên agent1-Khanh trước khi sinh tgt4. Không dùng
tgt, tgt2, tgt3 để chọn T9 hay hiệu chỉnh T1. Không sửa expand, HazardLR._prep hoặc run_real_v2.py.

## 1. T9 recall

- Mốc: T9 v2, tau=.5, max_guess_subset=2, hazard=false, FIFO=false; vẫn có memo_partial/COD.
- Ứng viên A: khôi phục tổ hợp 3–6 HĐ, xét tối đa 15 HĐ mở của khách đã gán;
  bắt buộc ít nhất một số HĐ rõ trong memo, mọi số HĐ nhận diện phải thuộc tổ hợp.
  Tổng số dư khớp khoản chuyển trong TOL hiện hành. Số HĐ trùng hoặc khách không nhất quán: giữ hàng chờ.
  Logistic riêng dự đoán tổ hợp đúng, học trên 12 DN src F000–F011, năm 2023.
  Đặc trưng: kích thước tổ hợp, tỷ lệ HĐ có memo, tuổi/hạn tương đối ngày giá trị NH,
  phân tán tuổi, tiền đã ghép trước đó và khoảng cách đến giao dịch đã ghép gần nhất.
- Ứng viên B: ghép phần cuối với một số dư khớp duy nhất của cùng khách, có bằng chứng
  phần đầu đã ghép từ giao dịch NH trước đó; không suy partial/final từ nhãn thật, không FIFO.
- Ứng viên C: bổ sung ngày trong tháng/ngày cuối tháng của ngày giá trị NH vào mô hình A,
  nhằm phục vụ DN ghi sổ theo tháng. Chỉ dùng ngày NH đã có tại thời điểm giao dịch.
- Replay 183 ngày trước cửa sổ chấm để duy trì số dư sau partial. Mọi mốc cùng replay;
  chỉ giao dịch trong cửa sổ chấm đi vào metric. Dữ liệu tương lai không đi vào trạng thái.
- Logistic C=1, chuẩn hoá trên train, seed=7. Hai bộ đặc trưng (có/không C),
  ngưỡng xác suất A {.90,.95,.99}, chênh lệch với ứng viên thứ hai >=.05;
  cộng mốc và chỉ-B: tổng 8 cấu hình. Không đổi lưới sau khi xem đích.
- Chọn trên 28 DN src còn lại, 2024H1: precision>=.975, auto coverage>=.60,
  từng phương pháp có >=30 liên kết phải precision>=.95. Tối đa F1, rồi coverage;
  nếu không cấu hình mới đủ điều kiện, giữ mốc T9 v2 và báo rõ.
- Báo source_grid, method diagnostics, precision–coverage, lựa chọn và hash mô hình.

## 2. tgt4 niêm phong

- Sao cấu hình tgt, chỉ thay name=tgt4, seed=2026102204, n_firms=30, write_xml=0.
- Trước sinh: kiểm tgt4 chưa tồn tại; xác minh tài liệu này đúng nội dung đã commit,
  lưu commit và hash cấu hình gốc. Sau chọn nguồn đóng băng mã/mô hình/lựa chọn.
- Đo một lần 2024-07-01–2025-06-29: R1, R2, T9 v2, T9 v3 chọn nguồn. Không đo lại tgt/tgt2/tgt3.
- G15_tgt4: F1>=.80 và lớn hơn R1/R2, precision>=.95, auto coverage>=.60, MAE ngày trả<=3.
  CI bootstrap 300 lần theo công ty, giữ mọi cổng cũ cho kiểm toán. Thất bại vẫn báo, không đổi ngưỡng.

## 3. G3/G4

- Dùng hai mô hình A fullweek đóng băng (2023-07-03, 2024-07-01); không fit lại hazard.
- CQR bất đối xứng, cho thu hẹp; nhóm overdue / 0–14 / 15–42 / >42 ngày;
  min_group=100, nhóm nhỏ dùng toàn cục. Fit trên 28 ngày cutoff cuối của cửa sổ nguồn
  đã chín trước origin, cùng y bị chặn CAP như phép đo. Không chọn độ dài từ test.
- Isotonic P(trả <=28 ngày): fit trên chính cửa sổ nguồn gần nhất này; giữ nguyên hazard gốc,
  chỉ xuất xác suất 4 tuần hiệu chỉnh. Kiểm cohort/nhãn biết trước origin, clip out-of-bounds.
- Chấm đúng hai cohort A: cov80 trong [.75,.85] và IS80 không xấu hơn global two-sided;
  ECE4<=.05 ở cả hai gốc. Báo đối chứng cũ cùng CI cụm công ty, không chọn lại khi trượt.

## 4. G7 M12

- Cùng cohort B M12 và nguồn; source model 600 rounds như B, không dùng tgt2/3/4.
- Target fit chỉ cutoff<cal_lo=O-183 ngày, nhãn censor tại cal_lo;
  calibration cutoff [O-183,O-120], nhãn tại O=2024-07-01. Test chỉ mở sau chọn.
- Trọng số hàng exp(-ln(2)*tuổi_cutoff/half_life) với half_life {30,90,180} ngày,
  chuẩn hoá trung bình 1. Fine-tune learning_rate=.02, tối đa 300 rounds;
  early stopping 50 theo binary logloss trên calibration, chọn half_life bằng pinball calibration.
- So source-only, fine-tune cũ 150 rounds, lựa chọn mới. G7 giữ >=10% pinball so source-only;
  CI bootstrap cặp 300 lần theo công ty. Không refit sau chọn để tránh thay số vòng đã khoá.

## 5. Vận hành và công bố

Một hàng đợi tuần tự duy nhất qua scripts/sprint5/wait_ram_then.sh 3:
T9 select -> tgt4 generate+evaluate -> G3/G4 -> G7 -> tests -> report -> commit/push.
AGENT1_THREADS=4, OMP_NUM_THREADS=4. Không khởi chạy chuỗi fullweek cũ.
CSV có measurement_version, protocol/hash, dòng nhật ký cho mỗi việc hoàn tất.
Không commit raw/parquet/log/.state/token. Footer commit Co-Authored-By.
