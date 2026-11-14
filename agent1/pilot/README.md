# Bộ dữ liệu và biểu mẫu diễn tập

| Tài nguyên | Mục đích |
|---|---|
| [Bộ pilot](BO_PILOT_SME.md) | Bài quan sát kế toán, mốc trước pilot và quy trình chạy song song |
| [Biên bản](quyet_dinh.md) | Chốt phạm vi/tiêu chí trước, quyết định sau quan sát |
| Phiếu quan sát và sổ dự báo | Công cụ đóng gói sinh hai CSV trống trong ZIP; lưu kết quả ở kho thử riêng |
| `fixtures/` | Bài nhỏ phân bổ 100 triệu vào hai hóa đơn 30/70; kiểm thao tác, không dùng chọn model |
| [Đại Phát](demo_dai_phat/README.md) | Sáu CSV synthetic để diễn tập luồng lớn |
| [UAT T0/T9](t0_t9_uat_20261110/README.md) | Bộ có đáp án kiểm nhập/đối soát/vòng đời và các ca âm |

[Hướng dẫn vận hành](../docs/06_Pilot/README.md), dữ liệu cần chuẩn bị và bảo vệ dữ liệu tập trung trong docs/06. [Nghiệm thu](../docs/03_Evaluation/03_cong_nghiem_thu.md) giữ điều kiện dùng thật; có biểu mẫu/dữ liệu mẫu không có nghĩa pilot đã triển khai.

`analysis.py` là helper phân tích ngoại tuyến khi đủ đầu vào: `economic_metrics` cần bảng hóa đơn có ngày trả/xóa nợ, `amount_gross`, `term_days` và bảng số dư theo ngày; không nhận trực tiếp sáu CSV Workspace. `difference_in_differences` cần panel có nhóm dùng/đối chứng và kỳ trước/sau. Số thiếu giữ trống; K3 cần phân phối dự báo phù hợp. DiD không tự chứng minh tác động nhân quả. Không tự liên hệ doanh nghiệp hoặc gửi dữ liệu ra ngoài từ việc đọc bộ này.

Từ gốc repository, chạy `.\.venv\Scripts\python.exe agent1/scripts/business/package_pilot.py` để dựng `agent1_service/ui/workspace/agent1-pilot.zip` bên trong `agent1/`. Gói đọc ba Markdown và bốn fixture hiện tại, sinh `uat_observations.csv` và `shadow_runs.csv` chỉ có hàng tiêu đề; không đọc kho doanh nghiệp hoặc kết quả quan sát. ZIP diễn tập nhỏ không bao gồm bộ Đại Phát/UAT lớn hay helper phân tích.

Chỉ giữ Đại Phát, fixture nhỏ và UAT có đáp án. Bộ Minh An đã nghỉ dùng; không lưu receipt kiểm thử hoặc nhật ký quan sát trong thư mục nguồn này.
