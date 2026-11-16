# CR-062 — Portal vào luồng bundle và giao task từ vụ

Giao việc trực tiếp16/11/2026: chọn DN/snapshot/Chạy phân tích, nhận vụ cần rà,
ghi kết quả và giao task ngay từ vụ; màn so sánh P1 cũ không đại diện 35 luật.

Đọc 00, tasks/R5,03,04,99 và các modules đã map R0. Tái sử dụng CR-061,
RemediationStore, Portal session/bridge, snapshot import và release lifecycle.
Không tạo pipeline riêng cho mỗi UI; không sửa phần Agent1/3/4.

Phạm vi kỹ thuật shadow. Không tự chốt ngân sách, SLA, chất lượng, label approval,
full HE bundle hoặc production. Không deploy/restart live/đổi model/key/phiên/
quyền; nghiệm thu bằng Portal thật trên port tạm và dữ liệu mô phỏng cô lập.
