# 05 · Phạm vi công việc và lịch sử triển khai

**Dọn/gộp ngày 06/11/2026.** Đây là bản đồ yêu cầu gốc và bằng chứng
triển khai theo thời điểm, không là một chuỗi prompt phải tiếp tục chạy.
Các lệnh giao việc/publish trong nhật ký không cấp quyền thực hiện công
việc mới khi chỉ đọc tài liệu.

## Chọn đúng hồ sơ

| Tài liệu | Vai trò |
|---|---|
| [Phạm vi WP và tiêu chí gốc](PHAM_VI_WP_VA_TIEU_CHI_GOC.md) | Gộp 01–08: đủ 68 mã WP, tiêu chí/giả thuyết và bối cảnh Q1–Q8; bỏ lệnh máy cũ, lịch 12 tuần và checklist tạo file đã thay thế |
| [Tiến độ sinh từ hồ sơ](TIEN_DO_TRIEN_KHAI.md) | Bảng WP từ `scripts/implementation_status.py`; giữ nguyên byte để đối chiếu CSV gốc, không coi là kiểm tra đầy đủ hiện trạng 06/11 |
| [Nhật ký 15–16/10](TIEN_DO_2026-10-16_lich_su.md) | Sửa as-of/CDF, hợp đồng, smoke và bước đầu dịch vụ; giữ vì có phát hiện riêng |
| [Nhật ký Sprint 1–6](NHAT_KY_SPRINT1_2026-10-20.md) | Sửa fullweek, BLEND, T9/G13/G15, các thử nghiệm đã loại, bảo mật; gộp bối cảnh hai prompt 21/22 vào phụ lục |
| [Quyết định đổi hướng 20–24/10](CHIEN_LUOC_TIEP_THEO_2026-10-24.md) | Gộp chẩn đoán sprint 20/10, đề xuất gate và chiến lược/luật dừng 24/10; giữ tách các mốc, không giữ lịch và phân công cũ |
| [Mốc code Khánh 25/10](HIEN_TRANG_AGENT1_KHANH_2026-10-25.md) | Commit `70c0ceb`, bằng chứng kiểm thử tại thời điểm đó và phát hiện bảo mật/provenance; không là kết luận về máy hiện tại |

## Công việc nghiên cứu hiện nay đọc ở đâu?

- [Báo cáo Khánh–v6 đã chốt](../03_Evaluation/T1_V6_PROGRESS_VS_KHANH_2026-11-05.md): ứng viên 93 feature, phạm vi sử dụng và bước kiểm đầu vào/tích hợp thử nghiệm.
- [Evaluation](../03_Evaluation/README.md): số đo riêng của v5/v6, practical, unified v2 và gate triển khai.
- [AI Methods](../04_AI_Methods/README.md): công thức và protocol, khác với checklist kế hoạch gốc.
- [Data](../02_Data/README.md): tồn kho còn giữ; không lấy số World/hóa đơn trong sổ cũ làm đầu vào hiện có.
- [Hướng dẫn đọc](../AI_READING_GUIDE.md): phân biệt thiết kế, kết quả đo, lựa chọn nghiên cứu và nghiệm thu.

Các bảng tiến độ cũ có thể ghi 14/18 job fullweek, 316 test hoặc một công
việc “đang chạy/chưa làm”. Chúng phản ánh hồ sơ mà bộ sinh đã đọc ở lần
đó, không xác nhận tiến trình đang hoạt động hoặc trạng thái của nghiên
cứu v6 ngày 05/11. Đợt dọn docs không train, chạy lại benchmark, sinh
nguồn, thay gate hoặc làm mới các CSV/JUnit để khớp cách viết mới.

## Phần đã bỏ và phần phải giữ

Đã bỏ tám file kế hoạch 01–08, kế hoạch sprint 20/10 và hai prompt bàn
giao sau khi chuyển yêu cầu/tiêu chí, lý do đổi hướng và nội dung giao
thức còn giá trị vào các hồ sơ trên. Prompt nguyên văn, đường dẫn máy
cũ, ước lượng lịch và phân công/publish đã hết mục đích sử dụng.

Giữ các số đo, CI, thời gian chạy, kết luận không thắng, luật dừng và
giới hạn dữ liệu. Giữ nguyên protocol/preregistration ở Evaluation và
AI Methods: bỏ prompt không có nghĩa bỏ bằng chứng tiêu chí trước test.
Các đề xuất đổi gate trong kế hoạch cũ không tự là quyết định đã duyệt.
Pilot thật, UAT và hiệu quả kinh tế vẫn cần bằng chứng thực tế riêng.
