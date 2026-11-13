# Phạm vi triển khai và kiểm chứng — 13/11/2026

Kết luận và số đo cuối đọc trong [REPORT.md](REPORT.md). Chốt global hiện tại
Neural 75%/customer 25%; ứng viên refit Neural/customer/Neural-wide không qua
guard audit Brier. Học tiếp có lợi thế trung bình nhỏ, CI còn chứa 0, nên không
đặt thành thao tác mặc định cho mọi doanh nghiệp.

## Mã phục vụ

- `agent1/adaptive/ledger_bridge.py`: adapter kế toán World → Workspace và
  snapshot vector hóa đã đối chiếu với snapshot phục vụ.
- `agent1/adaptive/landmark_adaptation.py`: Neural continuation, scaler đóng
  băng, replay global và pooling; không sửa model global gốc.
- `agent1/adaptive/landmark_serving.py`: kiểm release/hash/ngày sẵn sàng,
  thay riêng T1 và giữ các learner còn lại của bundle doanh nghiệp.
- `agent1/adaptive/methods.py`: tham số Monte Carlo/SHAP/seed, mặc định
  1000/30/7, giữ danh sách 30 dòng và dự báo toàn bộ công nợ.
- `agent1_service/workspace/api.py`: nhận tham số dự báo và cấu hình research
  run theo allowlist tenant; lưu phiên bản T1 và bundle local riêng.
- `landmark_explanations.py` và UI: giữ feature schema độc lập với ID model
  đã lưu, hiển thị attribution theo sáu nhóm và trạng thái SHAP deferred.
- `data.as_of` và T0 `_date`: bỏ parse timestamp/ngày rỗng không cần thiết,
  giữ đường xử lý intraday. Kiểm thử date/known_at vẫn qua.

Không cấu hình `AGENT1_T1_RESEARCH_RUN`/`AGENT1_T1_RESEARCH_FIRMS` cho tenant
nào trong máy. Dịch vụ tiếp tục cơ chế active model hiện có khi không cấu hình
allowlist. Cổng pilot thật không thay đổi.

## Thí nghiệm

`run_corrected_study.py` dùng `build_corrected_study.py`, `refit_landmark.py`,
`compare_adaptation.py`, các worker theo doanh nghiệp và các verifier/report.
Giữ toàn bộ artifact trước sửa nhãn trong `aligned_refit_20261112`.

Lỗi thời điểm Paid được sửa trong builder thí nghiệm mới: sort receipt theo
ngày tiền thực thu, chỉ lấy receipt đã biết tại label_end và không coi credit
note là tiền thu. Mẫu, feature, split, seed và ngân sách giữ nguyên. Các model
global/thích nghi được train lại. Workspace có cơ chế nhãn riêng đã theo ngày
thực thu; cache được kiểm hash, cùng ledger/ngày chốt/đầu vào và tái tạo dự báo
khớp 1e-12 trước khi dùng lại.

Hai World cho trọng số sau refit, hai World audit, bốn World test (có startup
3/6/9 tháng). Cohort mới được dùng lại khi sửa nhãn độc lập với model, được
ghi rõ trong target_contract. Không dùng điểm test tổng hợp để đổi hyperparameter.

Đã so global hiện tại, refit, reweight local, fine-tune local, thích nghi qua
audit, Neural local 18 feature và Workspace. Neural local là đối chứng cùng
kiến trúc/cấu hình; Workspace giữ quy trình chọn đầy đủ hiện có. Không diễn
giải thành ablation nhân quả chỉ riêng pretraining.

## Kiểm chứng cuối

- 115 kiểm thử Python, 28 kiểm thử UI; `git diff --check` qua.
- Tái tạo độc lập cash score: sai khác tối đa 1,11e-16.
- Khối lượng xác suất bằng 1; nhãn Paid khớp thời điểm cash thu đủ.
- T1 → T6 → SHAP qua bốn context đầy đủ, bất biến khi bỏ dữ liệu tương lai.
- Bài tải 1136 công nợ mở/18184 hóa đơn lịch sử: SHAP p95 một hóa đơn
  0,320 giây; cả ba cấu hình giữ kỳ vọng tiền và thứ tự danh sách.
- Release thật đã được load lại qua loader, kiểm đủ hash, 18 feature,
  trọng số [0.75, 0.25] và provenance `research_global_retained`.

Các plan dùng số dư đầu 0, phạm vi AR; chưa chứng minh độ chính xác số dư
ngân hàng đầy đủ hoặc hiệu quả trên doanh nghiệp thật.
