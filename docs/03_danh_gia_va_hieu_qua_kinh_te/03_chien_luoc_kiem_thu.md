# Chiến lược kiểm thử

## Cập nhật vòng v4 ngày 2026-10-17

Kiểm thử đầy đủ hiện tại: **165 bài và 18 kiểm tra con qua**, 72,36 giây. Đã bổ sung bộ chọn, cổng niêm phong, thống kê ghép cặp, lược đồ, adapter, đầu vào theo thời gian, cách ly công ty, quyết định chỉ thêm và bảo vệ phản hồi; bằng chứng tại `results/v4/test_verification.json`. Các con số 84 bài và trạng thái chưa làm trong bảng lịch sử bên dưới thuộc lúc bàn giao ban đầu.

A5 đã hoàn tất, **G5 không đạt và M2 yêu cầu dừng toàn dự án**: recall S1 trung bình đều ba thế giới là 41,31%, dưới ngưỡng 50%; S2 là 63,87%. Không đổi ngưỡng, không chọn lại cấu hình, không huấn luyện v2 hoặc thí điểm. Báo cáo đầy đủ tại [kết quả niêm phong v4](07_ket_qua_niem_phong_v4.md). Các kiểm kỹ thuật đã qua không thay thế cổng hiệu năng mô hình hoặc kiểm chứng doanh nghiệp thật. Bảng cổng gốc phía dưới được giữ để truy vết tiêu chí đặt trước.

## 1. Kim tự tháp kiểm thử

| Tầng | Kiểm cái gì | Hiện có | Cần thêm |
|---|---|---|---|
| T1. Kiểm thử đơn vị | Hàm tính, chỉ số, bộ chọn cảnh báo | 84 bài qua: 20 bài `tests_agent2` (thế giới hợp lệ, không rò rỉ nhãn, đặc trưng nhân quả, ngân sách tuần, chỉ số, ECOD, EntityDeviation, conformal, khe cảnh báo, thứ tự lý do, đặc trưng bộ nhớ, trọng số họ, Novelty, thế giới niêm phong) và 64 bài `tests_sme_fraud` (kế toán, Benford, nhân quả, phản hồi, giao diện, 31 luật, kiểm định luật, sửa luật) | Bài kiểm tra cho `select_v4.py` và `sealed_v4.py` (chưa có) |
| T2. Kiểm thử dữ liệu | Thế giới sinh có hợp lệ | 12 phép kiểm V1 đến V12 (`validate_v4`) | Chạy tự động trong CI mỗi lần đổi bộ sinh |
| T3. Kiểm thử nhân quả | Không dùng thông tin tương lai | `test_engineered_features_are_causal`; `test_memory_features_*` | Phép thử đảo: dịch chuyển thời gian của tập kiểm thử, kết quả không đổi |
| T4. Kiểm thử bất biến (metamorphic) | Đổi cách biểu diễn không đổi kết quả | Chưa | (a) xáo trộn mã giao dịch; (b) đổi tên mã công ty; (c) nhân mọi số tiền với hệ số: hạng điểm của các đặc trưng theo tỷ lệ phải gần như giữ nguyên |
| T5. Kiểm thử mô hình | Giao thức E1 đến E14 (tệp 09 phần dữ liệu) | E1, E2, E4, E5, E7, E10, E12 đã chạy trên v3; E1, E2, E3 một phần trên v4 | E6 trên niêm phong v4, E9, E11, E14 |
| T6. Kiểm thử đường ống | Chạy đầu-cuối từ dữ liệu thô đến hàng đợi vụ | `pipeline.py` chạy trên v3 (`results/v3/example_run_precision`) | Chạy trên v4 với mô hình huấn luyện lại |
| T7. Kiểm thử hiệu năng | Thời gian, bộ nhớ | Đo thô ở tệp 08 dữ liệu | Đo 100.000 dòng mỗi công ty |
| T8. Kiểm thử chấp nhận người dùng (UAT) | Người dùng hiểu cảnh báo và hành động | Chưa | Thí điểm |
| T9. Kiểm thử bảo mật và riêng tư | Cách ly công ty, không lộ tên | Chưa | Rà soát thiết kế, thử thâm nhập nhẹ |

## 2. Cổng chấp nhận (đề xuất, có số)

Mỗi cổng phải đạt trước khi sang cổng kế tiếp. Số là **[G]** neo vào kết quả hiện có; điều chỉnh khi có thêm dữ liệu.

| Cổng | Điều kiện | Mức hiện tại (nếu đã đo) |
|---|---|---|
| **G0. Chức năng** | 100% bài kiểm thử đơn vị và V1 đến V12 qua | 84/84 |
| **G1. Phát triển, cùng phân phối** (3 thế giới v4, P1) | Recall@B3 từ 70%, vụ tìm thấy từ 85%, báo nhầm ca khó không quá 20% | L3: 77,5%, 87,0%, 16,5% (đạt) |
| **G2. Khởi đầu lạnh** (kênh không nhãn) | Recall@B3 từ 35% với báo nhầm không quá 20% | Novelty max(R,E) trên thế giới 411: 34,5%, 14,9%; 412: 52,6%, 15,6% (sát ngưỡng) |
| **G3. Chưa từng thấy** (P2 và bỏ-một-kịch bản) | Trung bình recall@B3 từ 50% | L3 P2 thế giới 411: 52,3%; bỏ-một-kịch bản: hợp nhất 70,2%, L3 62,2% |
| **G4. Công ty mới** (P3) | Recall@B3 từ 60% | Chưa đo xong |
| **G5. Niêm phong v4** | Recall chung từ 65%; kịch bản mới từ 30%; báo nhầm ca khó mới không quá 20%; chênh với cổng G1 không quá 15 điểm phần trăm | Chưa chạy |
| **G6. Giải thích** | 100% con số trong lý do có trong bằng chứng | Chưa có phép kiểm |
| **G7. Thí điểm** | K2 từ 15%, K5 không quá 30 phút mỗi tuần, K7 không có phát hiện nghiêm trọng, K6 ít nhất 3 trên 5 | Chưa làm |

**Quy tắc cổng:** nếu G5 thất bại, **không** chỉnh mô hình trên niêm phong rồi chạy lại; ghi nhận thất bại, quay lại phát triển, và tạo tập niêm phong mới để thử vòng sau.

## 3. Kiểm thử hồi quy kết quả
Lưu tệp JSON kết quả trong `results/`. Mọi thay đổi mã phải chạy lại E1 trên 3 thế giới phát triển và so với JSON đã lưu; chênh lớn hơn 2 điểm phần trăm recall phải có giải thích trong `AGENT2_WORKLOG.md`.

## 4. Kiểm thử trong thí điểm
1. **Chế độ chỉ xem:** hệ thống chạy song song, không tác động; chủ doanh nghiệp xem cảnh báo.
2. **Chèn có kiểm soát (có sự đồng ý bằng văn bản):** kế toán trưởng hoặc chủ tạo vài giao dịch thử giống kịch bản (ví dụ chi tiền mặt sát hạn mức, thanh toán trùng một hóa đơn) để đo tỷ lệ phát hiện thực; sau đó hủy.
3. **Ghi thời gian:** bấm giờ rà soát mỗi tuần.
4. **Phỏng vấn:** sau 4 và 12 tuần; hỏi lý do có hiểu không, có hành động không, có trả tiền không.
5. **Đánh giá mù:** kế toán độc lập chấm một mẫu ngẫu nhiên các cảnh báo chưa xem kết quả mô hình.

## 5. Nhật ký thất bại cần giữ
Mỗi lần kiểm thử thất bại hoặc kết quả bất ngờ ghi vào nhật ký (ví dụ: C-L4 hai tầng không cải thiện AP so với L3; lỗi hết bộ nhớ khi nạp 3 thế giới). Mục đích: người sau không lặp lại.
