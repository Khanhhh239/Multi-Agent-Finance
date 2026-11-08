# Tiến độ triển khai file 01–06

Phạm vi ban đầu: file 01–06. Từ 16/10/2026 đã có file 07–08 và mở rộng sang dịch vụ local cùng hồ sơ pilot.
Các mục chưa có thí nghiệm chuẩn không được coi là hoàn thành hoặc đổi cổng thành đạt.

## Nhật ký 15/10/2026

- Đã đọc tài liệu nền và đối chiếu mã, dữ liệu, CSV hiện có. Bộ kiểm thử trước sửa: 15 đạt.
- B, E/F, T6 đã có CSV trên đĩa; trạng thái “chưa chạy” trong tài liệu không đủ để kết luận.
- Phát hiện rò rỉ trung vị tiền: `SnapshotBuilder` dùng toàn bộ hoá đơn tương lai.
  Đã chuyển sang tập hoá đơn biết tại từng cutoff và cửa sổ onboarding; thêm ca đối nghịch.
- Phát hiện hiệu chỉnh A dùng các snapshot cùng cửa sổ train và lấy phân vị mốc từ ngày O
  cho cả những cutoff hiệu chỉnh trước O. Đã tách train trước cửa sổ hiệu chỉnh và thêm B1d as-of.
- Phát hiện ensemble/CQR kế thừa CDF của mô hình gốc dù đã đổi phân vị.
  Đã tính lại phân phối từ chính phân vị; thêm lưới 9 phân vị và PCHIP cho QLGBM.
- Đã thêm hợp đồng 10 bảng, ràng buộc khoá/tham chiếu/tiền/số dư và cột đặc trưng cấm.
  Dữ liệu gốc cả bốn thế giới đạt 68/68 kiểm tra mỗi thế giới.
  Ngày sổ FIFO có thể đi trước ngày tiền của HĐ bị gán nhầm: đo tỷ lệ này như nhiễu sổ,
  không dùng quan hệ `ledger_post_date >= pay_date_true` làm bất biến.
- Đã thêm phiên bản phụ thuộc, lệnh PowerShell và cache snapshot có dấu vết nguồn/tham số/mã.
- Thí nghiệm A đang chạy lại; giữ bản cũ tại `outputs/t1/A_rolling_origin_src.v1.csv`.
  Số cũ có lỗi as-of không được dùng để khẳng định các cổng sau khi sửa đo.

## Những điều phải giữ khi tiếp tục

## Cập nhật 16/10/2026

- A đã đo lại cả hai origin, có 300 bootstrap theo công ty và phân tầng.
  Mốc điểm được chấm bằng khối lượng xác suất điểm; giữ CSV trước sửa để đối chiếu.
- Đã thêm CQR hai phía, CDF PCHIP vector hoá, nhãn khoảng EM, cache theo nguồn/cấu hình,
  thử seed và chương trình Optuna nguồn. Tuning/seed/real-data chỉ xong khi có CSV tương ứng.
- Đã sửa SBA EXEMPT, thêm kiểm duyệt nhãn chưa biết, chia kỳ hạn; nhãn 3 năm phải chín
  trước FY2018 (train đến FY2013, hiệu chỉnh FY2014), không lấy kết quả 2018–19 để fit.
  Cụm bootstrap dùng proxy tên/địa chỉ người vay; không coi đó là mã pháp nhân hoàn hảo.
- T6: sửa biên tuần, số dư thật có rút vốn, copula giữ xác suất biên, không lấy chi NCC,
  thuế chưa đóng kỳ và tiện ích tương lai làm số tiền đã biết. Các thay đổi này phải đo lại.
- Đã sinh 12 hard-case × 12 công ty và thiết kế/sinh 20 thế giới LHS mới; kiểm hợp đồng,
  cấu hình và hash nằm trong `docs/02_Data/worlds_registry.csv`.
- Hard-case FX dùng tỷ giá **tổng hợp giả định**, chuẩn hoá sổ VND kèm nguyên tệ/rate;
  hard-case credit-note thử chuỗi **thay thế**. Chưa xác nhận đầy đủ nghiệp vụ huỷ/điều chỉnh thuế thật.
- RNG v2 tách từng pha/công ty cho hard-case; mặc định v1 giữ thế giới gốc.
  Benchmark so cùng seed/bảng giá trị, không tự nhận tốc độ >=5× trước khi đo.
- 107 kiểm thử đã đạt ở lượt kiểm gần nhất; thêm parser 5 ngân hàng CSV/Excel,
  HMAC, mã hoá SQLite, xác thực, cô lập DN, xoá dữ liệu và khoá NO-GO.
- E2E smoke đã chạy qua XML và CSV thật sự trong bộ tổng hợp; kết quả xấu giữ nguyên.
  Đây là luồng mô hình riêng DN, **chưa thay** giao thức nguồn→fine-tune + bốn đối chứng.
- Dịch vụ local và dashboard ở `agent1_service/`, hồ sơ pilot ở `pilot/`.
  Mặc định không phát dải dự báo cho pilot; chỉ nghiên cứu khi bật cấu hình rõ ràng.
- Chưa có chuyên gia xác minh 27 quy tắc, chưa có UAT ba người hoặc pilot thật.
  Không đánh dấu toàn bộ kế hoạch hoàn thành khi những điều kiện này còn thiếu.

## Nhật ký chạy và các phần còn lại

`scripts/run_plan.py` chạy tuần tự B, E/F, SBA, T6, T9, T7, C2ST và báo cáo.
`outputs/implementation/run_status.json` ghi exit code, thời gian và hash mã từng việc.
Các phần như scaling 1M/3M/10M, so sánh DR cùng số hoá đơn, PDP/mixture/daily-hazard,
quy trình nghiệp vụ thuế mở rộng và UAT người thật chưa được nhận là đã hoàn thành.

## Quy tắc tiếp tục

- `AGENT1_THREADS<=6`, `OMP_NUM_THREADS<=4`; hiện dùng 4 luồng.
- Không ghi đè thế giới `src/tgt/sens_*` khi sửa máy phát; sinh tên/seed riêng.
- Không dùng `tgt` để chọn tham số hoặc chiến lược; khoá thiết kế trước khi đánh giá.
- Không coi smoke test là bằng chứng đạt G1–G18. Kết quả và CI phải lấy từ CSV.
- Không tự điền SEC_USER_AGENT, chấp nhận điều khoản Kaggle hoặc gửi khảo sát cho người khác.
- Git hiện được nhận từ thư mục cha ngoài dự án; không stage/commit hay sửa dữ liệu ngoài Agent1.
