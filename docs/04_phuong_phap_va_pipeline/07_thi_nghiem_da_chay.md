# Các thí nghiệm đã chạy và điều rút ra

Số liệu chi tiết: [03_danh_gia_va_hieu_qua_kinh_te/06_ket_qua_hien_co.md](../03_danh_gia_va_hieu_qua_kinh_te/06_ket_qua_hien_co.md). Dữ liệu thô: `results/`.

| # | Thí nghiệm | Giả thuyết | Kết quả [M] | Kết luận |
|---|---|---|---|---|
| X1 | Luật của bạn bạn: v2 so với v3 | Luật viết cho đúng kịch bản chèn là vòng tròn | AP 0,60 (v2) → 0,24 (v3) | Đúng: đánh giá phải trên họ không có luật viết sẵn |
| X2 | Sửa blend 80/20 của bạn bạn bằng Gate | IF yếu không nên kéo tụt dòng đã trúng luật | Trên dữ liệu của chính họ: 0,665 so với 0,4525 | Đúng; giữ Gate |
| X3 | Bảy phương pháp không giám sát trên v3 | Có phương pháp tốt nhất | AP IF 0,021, ECOD 0,005, HBOS 0,004, AE 0,065, EntityDeviation 0,012 | Không có phương pháp nào thắng; khớp ADBench |
| X4 | Luật học lại trọng số (logistic khoảng 34 hit) | Hiệu chỉnh luật bằng ít nhãn có lợi | AP 0,240 → 0,387 (v3) | Đúng; ít tham số nên ít quá khớp |
| X5 | LightGBM các bộ đặc trưng | Baseline thực thể giúp mô hình học | v3: 190 đặc trưng 0,633 → + thực thể + luật 0,817; v4: 0,069 → 0,577 | Đúng; **nhưng là giới hạn trên** |
| X6 | Bỏ-một-họ (v3, 9 họ) | LightGBM thuần mù trước họ mới | recall họ chưa thấy: LightGBM thuần 16%, luật 34%, LightGBM+luật+thực thể 51%, max(luật, thực thể) 43% | Đúng: cần kênh không nhãn |
| X7 | Chéo thế giới (v3) | CES chuyển giao tốt | CES 2+1 recall 68%, báo nhầm 6,3%; LightGBM 2+1 90%, 12,6% | CES an toàn hơn; LightGBM mạnh hơn |
| X8 | Khe thăm dò (1+2, 2+1) | Dành khe cho kênh mới lạ tăng độ phủ họ mới | `results/v3/mixed_slots.csv` | Giữ 2+1 |
| X9 | **Niêm phong v3** (chạy một lần) | Cấu hình đóng băng chuyển giao sang họ mới | CES 2+1 53% (họ mới 17,5%); LightGBM 2+1 83% (58,7%); luật 29% | Kết luận trung thực: LightGBM thắng recall; phần thắng một phần do bộ sinh chia sẻ cơ chế |
| X10 | Phản hồi 52 tuần | Học trọng số hơn nới ngưỡng | 83 so với 58 so với 52 | Đúng khi nhiễu thấp |
| X11 | Dữ liệu ngoài | Bộ sinh của ta có dễ hơn thật không | ERP Fraud Data, DFKI: không phương pháp nào thắng ổn định | Cảnh báo: không tin AP trong phân phối |
| X12 | **v4 benchmark theo thời gian** | Dữ liệu khó hơn | Luật AP 0,079; L3 0,577 | Đúng |
| X13 | v4 bỏ-một-kịch bản (thế giới 411) | Kênh không nhãn bổ sung | L3 62,2%; hợp nhất 70,2%; `ghost_employee` 0% mọi phương pháp | Hợp nhất tốt nhất; còn khoảng trống |
| X14 | v4 phương pháp lai, P1 và P2 một phần | L4, FB, hai tầng cải thiện | L4 +2 đến 4 điểm P1 (trong sai số); P2 411: 52% → 63 đến 70%; hai tầng không giúp | Chưa kết luận; tiếp tục (H1 đến H3) |

## Thất bại và bất ngờ (giữ để người sau không lặp lại)
1. **Mô hình hai tầng (trí nhớ theo thực thể) không cải thiện.** Có thể vì điểm tầng 1 đã bão hòa ở hạng 0,99; thử dùng điểm không nhãn làm "trí nhớ" (H3).
2. **Autoencoder đưa vào kênh Novelty làm tăng báo nhầm lên 24 đến 25%**, vi phạm ràng buộc 20%. Nó phù hợp làm đặc trưng cho mô hình có giám sát hơn là làm kênh độc lập.
3. **`ghost_employee` không bị bắt khi chưa thấy** (cả 6 phương pháp): nhân sự ma có chấm công, lương, tài khoản giống hợp lệ. Cần đặc trưng danh tính (chung tài khoản, không có bảo hiểm, không có dòng thưởng...) hoặc bộ phát hiện đối chiếu với nguồn ngoài.
4. **AUC kiểm tra lối tắt 0,57 đến 0,8** là do cơ cấu loại nghiệp vụ, không phải lối tắt: phải đo mức tăng.
5. **Lỗi hết bộ nhớ** khi nạp 3 thế giới cùng lúc (xử lý bằng float32 và nạp từng thế giới).
6. **pandas 3:** `groupby().rolling()` đổi hình dạng chỉ mục, làm hỏng đặc trưng bộ nhớ; đã viết lại căn theo vị trí và kiểm thử với phép tính vét cạn.
7. **Mã định danh trùng giữa các thế giới** (cùng `T000000001`, `C001`): khi gộp thế giới phải thêm tiền tố (đã sửa trong `eval_v4.prepare`).


## Vòng v5 (2026-10-21 và 2026-10-22, phiên hỗ trợ; dữ liệu tổng hợp)

| # | Thí nghiệm | Giả thuyết | Kết quả | Kết luận |
|---|---|---|---|---|
| X15 | Chẩn đoán `EntityDeviation2` không nhãn trên 931 đến 933 (đã lộ, hậu kiểm) | Lệch hai phía và đổi bậc theo thực thể bắt kiểu mới | Một mình: recall 12%, kịch bản mới 17% (tốt nhất); bán giá thấp nhận lại quả 64%, hóa đơn bán khống 45% ở thế giới 931. Ghép max-rank hoặc chia khe: 24 đến 29%, không hơn Novelty cũ 28,5% | Tín hiệu có, nhưng thua trong ngân sách 3 cảnh báo; Cold khó đạt 40% |
| X16 | Chuyển giao mô hình gọn (khoảng 70 cột, PU 0,2) có hoặc không đặc trưng thay đổi, 3 seed | Đặc trưng thay đổi giúp S2 | 400 cây cố định: 50,8% → 52,7%; kịch bản mới 12,3% → 14,4%; ca khó 14,9% → 15,2% | Lợi ích nhỏ nhưng nhất quán; đưa vào ứng viên `L4-PU-E2-AR` |
| X17 | Cùng mô hình nhưng dừng sớm theo AP kiểm định | Dừng sớm vô hại | Có seed dừng ở **1 cây**; recall khoảng 34% và dao động mạnh | **Thất bại quan trọng:** bỏ dừng sớm, dùng 400 cây cố định (đăng ký v1.2) |
| X18 | Kiểm tra tiền tố và vét cạn cho đặc trưng thay đổi | Đặc trưng nhân quả | Qua; phát hiện lỗi đơn vị thời gian pandas 3 (mili giây) làm mọi cửa sổ sai 1.000 lần | Đã sửa, có kiểm thử hồi quy |
| X19 | Kiểm tra "có hay không có giá trị" theo trường (V13) | Bộ sinh không để lối tắt dạng trường | Trả hàng và xóa nợ chỉ trỏ hóa đơn gốc khi gian lận | Loại 3 đặc trưng và 3 bộ phát hiện (đăng ký v1.3); ghi vào hạn chế dữ liệu L11 |
| X20 | Sinh lại 1001 và 1016 sau khi sửa `hire_guard` | Sửa lỗi không đổi dữ liệu cũ | Giống từng byte | Sinh tiếp 1017 đến 1020, cả 20 thế giới đạt V1 đến V12 |
