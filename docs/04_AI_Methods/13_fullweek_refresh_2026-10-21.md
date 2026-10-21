# Chạy lại hazard sau sửa tuần bị kiểm duyệt — 21/10/2026

Nguồn sự thật: nhật ký Sprint 1 và yêu cầu bàn giao ngày 21/10. Không sửa
`expand`, `HazardLR._prep` hoặc `scripts/sprint1/run_real_v2.py`.
Hash hai file khoá được lưu ở `outputs/implementation/fullweek_protected.json`.
181 CSV cũ được giữ nguyên byte với đuôi `.legacy_expand.csv`; manifest có hash
tại `outputs/implementation/legacy_expand_backups.json`.

## Chuỗi chạy lại

```powershell
$env:AGENT1_THREADS='4'
.venv/Scripts/python.exe -u scripts/sprint1/fullweek_refresh.py
```

Lần lượt A, B, DA-paired, T1-variants, onboarding, EF, noisy-EF, T9-T1,
T3-T1, crisis-ablation, DR-eval, E2E-full, T6, regime-cash, collection-policy,
copula-hierarchy, IW-oof, scaling. Mỗi job qua `run_plan.py`; chỉ khởi chạy
khi RAM khả dụng >=3 GiB. Không dừng tiến trình dự án khác để lấy RAM.
Mỗi job hoàn tất ghi thời gian, trước/sau và phạm vi số vào mục 7 nhật ký.
CSV hazard mới có hậu tố `-fullweek`; riêng E2E phải giữ chữ này để bộ chờ
của agent1-Khanh nhận biết. Trạng thái đang chạy/chờ không được xem là xong.

Đã sửa bộ đếm quần thể scaling để cùng điều kiện tuần quan sát đủ với
`expand`; kiểm thử có sự kiện trong tuần bị cắt dở. Không đổi số hàng chọn
hoặc các ngưỡng sau khi xem kết quả. Bảng scaling bỏ qua các file backup
legacy khi ghép để không trộn hai giao thức.

## Các việc tiếp theo đã đăng ký

- `C-v2`: script gốc khoá nguyên trạng. `real_v2_b1_reference.py` chỉ tính
  mốc B1 trên đúng cohort CI; không huấn luyện hay đổi BLEND. G5: BLEND giảm
  pinball >=10% so B1 và CI thấp vs B1d >0 trên CI. G6: cả CI/BPI có CI cao
  >=0 và điểm >=-2%. G5_v1/G6_v1 giữ để kiểm toán. Registry tiêu chí ở
  `outputs/implementation/real_v2_gate_registration.json`.
  CSV v2 của Sprint 1 đã có expand mới nên không thuộc 18 job phải chạy lại;
  không huấn luyện lại toàn bộ LR/QLGBM của v2 chỉ để đăng ký job. Mốc BLEND
  sẽ được tái lập trong ablation P4 và kiểm chênh lệch <=0,5%.
- `P4`: `StationaryFeatures` fit phân vị 99 từ train; log1p số lịch sử/tuổi
  khách; ẩn tháng lịch nếu tuổi lịch sử DN <24 tháng theo lịch. Hai gốc A,
  B M12, CI/BPI v2 dùng cùng cohort/budget/params. Fine-tune giữ cùng biến
  đổi của mô hình nguồn. CI/BPI chuyển các cột float64 sang float32 đúng
  giao thức v2 trước cả hai nhánh để tránh nhiễu do độ chính xác số. CI cặp
  300 lần theo DN; CI/BPI dùng cụm khách như
  giao thức v2. Mặc định vẫn tắt. Tiêu chí: không xấu >1% ở đâu và cải thiện
  >=2% ở ít nhất một bộ thật; không chọn thêm phép biến đổi theo test.
- `G3`: từ dự báo A nguồn đóng băng, so khoảng thô, CQR hai phía toàn cục,
  Mondrian theo đã quá hạn / hạn 0–14 / 15–42 / >42 ngày. Mỗi nhóm >=100
  hàng calibration; nhóm ít hoặc chưa thấy dùng offset toàn cục. Cho phép
  offset âm để thu hẹp; không lấy q-hat từ mô hình chọn dữ liệu thật ngắn.
  Tiêu chí: hai gốc cov80 75–85%, IS80 không tăng so CQR toàn cục.
- `T9-source-policy`: chẩn đoán trên DN nguồn ngoài tập fit, kỳ 2024H1;
  cache riêng `outputs/t9/sprint3/source_reconciler` ghi rõ 12 DN học nguồn
  và kỳ học/hiệu chỉnh; cache cũ thiếu danh sách DN không đủ để xác nhận
  holdout nên không được dùng cho phép đo này.
  chọn tau/ứng viên chỉ ở đây. Lưới tau .5/.6/.7/.8/.85/.9/.95/.975/.99.
  Giữ tiền giữ lại mở sau thu một phần có số HĐ và khách đủ tin cậy; COD
  dùng ngày lập/số tiền duy nhất trong ba ngày. Nghiệm subset mơ hồ chỉ
  được ưu tiên nếu prior T1 đóng băng có tỷ lệ score >=3, còn lại vào hàng
  chờ. Prior dùng lịch sử ngày sổ trước giao dịch, không dùng ngày trả thật.
  Chỉ tách nghĩa vụ retention theo hợp đồng có known_at/source; không lấy
  annotation retention tương lai của máy phát làm điều khoản đã biết.
  Đánh giá cuối trên tgt và hai hard case, không đổi tau sau khi xem.

G13 thuộc agent1-Khanh. Các việc P4/G3/T9 chưa có CSV đo đủ không được nhận
là đã xong chỉ vì mã và kiểm thử đã có. G7/G8/G17 và yêu cầu coverage T9
không tự viết lại. UAT, chuyên gia, pilot và Docker vẫn cần điều kiện thực tế.

## Tiến trình nền và publish

`scripts/sprint1/launch_fullweek.ps1` chỉ chuyển bộ điều phối lúc nó đang
chờ RAM, không dừng job huấn luyện đang chạy hay dự án khác. Hai tiến trình
ẩn đọc điểm tiếp tục; log ở `outputs/implementation/fullweek_*.detached.log`.
Sau đủ chuỗi, bộ hoàn tất chạy P4/T9 còn thiếu, kiểm thử cả hai môi trường,
Ruff, hash backup và báo cáo tái lập. `--publish` chỉ commit/push khi tất cả
điều kiện này đủ; không yêu cầu các giả thuyết xấu phải bị sửa thành đạt.

Publish dùng clone riêng `.publish-repo`, nhánh `agent1-Khanh`, không dùng
Git thư mục cha. Chỉ sao chép mã/docs/CSV tổng hợp/cấu hình; kiểm đường dẫn
cấm và chuỗi có dấu hiệu khoá truy cập trước commit. Không force-push hoặc
trộn thay đổi remote chưa kiểm thử. Commit có footer Co-Authored-By.
Trạng thái cuối ghi ở `outputs/implementation/publish_status.json`; nếu
bất kỳ job, kiểm tra hay push thất bại, bộ chạy dừng và ghi lỗi, không nhận
là đã hoàn tất.
