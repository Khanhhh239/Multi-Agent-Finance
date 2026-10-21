# Lịch nghĩa vụ bổ sung từ hồ sơ

`agent1/rules/obligations.py` nhận bảy nhóm: TNCN khấu trừ, thuế nhà thầu,
hoàn VAT, thưởng lương/tháng 13, thuê nhiều bậc, lãi vay và gốc vay. Số tiền,
hạn thanh toán và nguồn phải có trong hồ sơ đầu vào; mô-đun không tự suy mức
thuế, gross-up, điều kiện hoàn VAT hay quyền hưởng thưởng tháng 13.

Mỗi khoản có `obligation_id`, `known_at`, `due_date`, `amount`, `source` và
`verified`. Lịch tại T bỏ hồ sơ chưa biết tại T; hoàn VAT còn cần ngày quyết
định `refund_approved_at <= T`. Không dự đoán ngày nhận tiền bằng cách cộng
một thời hạn xử lý pháp lý vào ngày nộp hồ sơ. Hồ sơ sửa đổi phải giữ phiên
bản lịch sử; không gán lại ngày biết của bản sửa cho bản cũ.

`rent_events` chọn giá theo đầu kỳ tháng, chặn bậc thiếu/chồng lấn, cắt ngày
31 theo cuối tháng. Đợt thay đổi giá giữa tháng cần các sự kiện phân bổ cụ
thể từ hợp đồng. `loan_events` giữ gốc/lãi riêng. Quy ước dời ngày làm việc
do hợp đồng cung cấp. `weekly_extended_cash` trả hai mảng thu/chi trong
(T+7k,T+7(k+1)], không cộng hoàn VAT vào chi âm.

Đây là lịch độc lập và bộ chuyển thành dòng tiền tuần; chưa thay đổi các
dự báo nghiên cứu đã công bố hoặc tự cộng vào dự báo dịch vụ. Khi tích hợp
phải loại trùng với khoản thuê, `loan_service`, thuế và thưởng đã có trong
bảng chi; tiền hoàn đã có trong số dư không được cộng lần nữa.

Chạy `.venv/Scripts/python.exe scripts/run_obligation_cases.py`; bằng chứng
ở `outputs/rules/extended_obligation_cases.csv`. Kiểm thử kiểm tra phép tính,
chống dữ liệu tương lai và bảo toàn thu/chi; không thay xác minh chuyên gia.

Bộ hồi quy lịch sử riêng: `.venv/Scripts/python.exe scripts/run_rules_business_cases.py`.
Có 54 tình huống với kết quả kỳ vọng cố định, hai tình huống cho mỗi trong
27 phiên bản quy tắc. Kiểm các vùng lương, biên kỳ VAT, ngành loại trừ,
lương ròng/BHXH, ngưỡng doanh thu 50 tỷ, hạn thuế trùng ngày nghỉ, mức và
ngày bỏ môn bài, Tết và dự phòng theo tháng. Giá trị kỳ vọng không lấy từ
registry đang kiểm. CSV `outputs/rules/business_cases.csv` và độ phủ đi kèm
chỉ xác nhận hồi quy quy ước lịch sử; mọi quy tắc vẫn `verified=false`.

Đối chiếu nguồn ngày 20/10/2026:

- [Luật 38/2019/QH14](https://vanban.chinhphu.vn/?pageid=27160&docid=197312),
  [NĐ126/2020](https://chinhphu.vn/default.aspx?docid=201402&pageid=27160),
  [TT111/2013](https://vanban.chinhphu.vn/?pageid=27160&docid=169566) và
  [TT103/2014](https://vbpl.vn/botuphap/Pages/vbpq-toanvan.aspx?ItemID=46348&Keyword=)
  là các đầu mối lịch sử để chuyên gia kiểm hồ sơ TNCN/nhà thầu.
- [Quan hệ sửa đổi TT80/2021 trên CSDL Bộ Tài chính](https://vbpl.moj.gov.vn/botaichinh/Pages/vbpq-luocdo.aspx?ItemID=151086)
  liệt kê TT94/2025; không coi TT80 bản gốc là đủ cho mọi kỳ sau này.
- [Luật 108/2025/QH15](https://vanban.chinhphu.vn/?docid=216541&orggroupid=1&pageid=27160)
  có hiệu lực chính từ 01/07/2026. [Hướng dẫn thời hạn theo NĐ252/2026 của Chính phủ](https://xaydungchinhsach.chinhphu.vn/quy-dinh-thoi-han-nop-ho-so-khai-thue-119260703120801722.htm)
  nêu hạn tháng/quý. Bộ mới này chưa được chuyên gia xác nhận trong registry;
  mô-đun nhận hạn trên hồ sơ thay vì tự mở rộng quy tắc lịch sử sang năm 2026.
