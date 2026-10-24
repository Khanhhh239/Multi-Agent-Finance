# Đăng ký trước vòng v6: dùng ca hợp lệ khó đã xác nhận để giảm cảnh báo nhầm

Soạn 2026-10-22, **trước khi viết mã hay chạy bất kỳ thí nghiệm nào của vòng này**. Mọi số là **dữ liệu tổng hợp**.

## 0. Thẩm quyền và quan hệ với v5

- Kết quả v5 **giữ nguyên, không viết lại**: chốt chặn trước niêm phong v5 KHÔNG ĐẠT (`docs/03_danh_gia_va_hieu_qua_kinh_te/09_ket_qua_niem_phong_v5.md`). Mục 7 của đăng ký v5 cấm tự mở vòng mới.
- Ngày 2026-10-22, chủ dự án chỉ đạo bằng lời: "cải thiện tiếp tục". Đó là lý do mở vòng này. **Chi tiết đăng ký này chưa được chủ dự án duyệt**; chủ dự án có quyền bác bỏ hoặc sửa trước khi chạy tầng chọn (mục 6). Phần đã chạy trước khi bác bỏ sẽ bị bỏ, không dùng.
- Vòng v6 là **vòng cuối**. Nếu chốt chặn v6 không đạt thì dừng hẳn, không mở v7.
- Seed niêm phong 5101 đến 5104, thử khô 5199 và văn xuôi 10 kịch bản (SHA-256 `3723fb9d...02cc`) **chưa từng được sinh hay chấm**, và không có số đo nào của vòng này dựa vào chúng. Vòng v6 dùng lại chúng.

## 1. Chẩn đoán (chỉ trên 8 thế giới sàng lọc 1001 đến 1008, đã có từ R2)

1. Cả bốn ứng viên v5 đều có recall chung 82 đến 90% và B 56 đến 59%, vượt ngưỡng, nhưng vượt trần 15% ca hợp lệ khó ở 4 hoặc 5 trên 8 thế giới (cao nhất 18,8%).
2. Cảnh báo nhầm **tập trung ở vài loại ca hợp lệ khó**, ví dụ với L3-PU ở giao thức S2: thanh toán của công ty liên kết hợp lệ 73,5%, hủy hàng tồn kho hợp lệ 66,0%, trả hàng hợp lệ 59,7%, quyết toán thôi việc 42,2%, tạm ứng giám đốc 32,3%, trong khi nhiều loại khác dưới 10%. Tổng hợp: 4.351 trên 33.148 dòng ca khó bị cảnh báo (13,1%) ở S2 và 5.222 trên 33.148 (15,8%) ở giao thức `expense`.
3. Nguyên nhân trong mã: `observed_labels` gán **cùng trọng số w = 0,1** cho mọi dòng không phải gian lận, kể cả các ca hợp lệ khó đã được xác nhận hợp lệ ở thế giới nguồn. Mô hình vì thế gần như không bị phạt khi cho điểm cao các ca này.
4. Hạn chế đã biết: một số ca (thanh toán công ty liên kết, trả hàng) **gần như không phân biệt được** với gian lận bằng trường dữ liệu quan sát sau khi đã loại lối tắt L11. Giảm cảnh báo nhầm ở các ca này có thể làm mất recall của họ gian lận tương ứng. Đây là đánh đổi thật, không phải lỗi, và kết quả phải báo cả hai phía.

## 2. Thay đổi duy nhất

Ở **thế giới nguồn**, dòng có `is_fraud = 0` và `hard_negative_type` khác rỗng (ca hợp lệ khó đã xác nhận) nhận trọng số huấn luyện **h** thay cho w. Các dòng không nhãn còn lại giữ w = 0,1. Dòng dương giữ trọng số cũ. Mọi thứ khác (400 cây cố định, hai cấu hình lá, đặc trưng, ngân sách ba dòng, lấy mẫu âm 0,1 với mọi ca hợp lệ khó được giữ nguyên) không đổi.

- **Không đọc nhãn của thế giới đích** ở bất kỳ bước nào.
- Ý nghĩa nghiệp vụ: đại diện cho các kết luận "hợp lệ" mà kế toán viên đã xác nhận ở **các khách hàng khác**. Khi triển khai thật, cần một kho phản hồi dùng chung giữa các khách; công ty hoàn toàn mới chưa có phản hồi riêng vẫn được lợi từ kho này. Đây là điều kiện sản phẩm, phải ghi vào tài liệu vận hành nếu v6 đạt.
- Các ca hợp lệ khó của thế giới niêm phong có **loại mới** (`NEW_DECOYS_V5`) mà mô hình chưa từng thấy nhãn xác nhận; cảnh báo nhầm trên các loại mới được báo riêng và vẫn tính vào trần 15%.

## 3. Ứng viên và cách chọn

| Bước | Nội dung |
|---|---|
| Khóa w | Giữ **w = 0,1** từ làm rõ khóa w của v5; không chọn lại |
| Khóa h | Lưới **h = 0,5; 1; 2**. Ứng viên L4-FB-PU, 8 thế giới 1001 đến 1008, seed 0, 11 giao thức mỗi thế giới. Chọn h có J cao nhất trong các h hợp lệ; hòa thì theo thứ tự lưới. **Không h nào hợp lệ thì dừng v6**, không đổi lưới |
| Sàng lọc | Ba ứng viên có giám sát, mỗi ứng viên dùng h đã khóa: `L3-PU`, `L4-FB-PU`, `L4-PU-E2-AR`. Cấu hình 2plus1 **bỏ** vì đã kém nhất ở v5 và không liên quan thay đổi này. Chuyển sang tầng chọn mọi ứng viên hợp lệ, tối đa 3, xếp theo J, hòa theo thứ tự danh sách |
| Tầng chọn | 20 thế giới, năm seed 0 đến 4, giữ đúng mục 4 của v5; chọn một cấu hình bằng J với quy tắc gần hòa 0,01 của v5 |
| Cold | **Không theo đuổi** trong v6: cả hai Cold v5 không hợp lệ và thay đổi này không áp được cho kênh không nhãn. Không chào bán Cold |

Quy tắc hợp lệ, định nghĩa R, B, Q, J, 20% thế giới thấp nhất và trần 15% cho từng thế giới, từng giao thức **giữ nguyên v5**. Trần không được nới ở bất kỳ bước nào.

## 3a. Sửa đổi v6.1 (2026-10-23 23:15, theo chỉ đạo của chủ dự án, trước khi có bất kỳ kết quả tầng chọn nào)

- **Nội dung:** `L3-PU` bị **loại khỏi tầng chọn**. Tầng chọn chỉ gồm `L4-FB-PU` và `L4-PU-E2-AR`. Lý do duy nhất là thời gian chạy (máy chỉ chịu hai tiến trình cùng lúc; ba ứng viên cần thêm khoảng 18 giờ), không phải kết quả.
- **Tình trạng kết quả khi ghi:** tầng chọn mới có khoảng 55 trên 220 giao thức cho `L4-FB-PU`, 48 cho `L4-PU-E2-AR` và 9 cho `L3-PU`. **Chưa tổng hợp J, R, B hay tỷ lệ cảnh báo nhầm của tầng chọn cho bất kỳ ứng viên nào**, và tôi không xem chúng. Chín giao thức đã xong của `L3-PU` bị bỏ, không dùng.
- **Không đổi:** sàng lọc đã chạy với ba ứng viên và bảng kết quả (L3-PU J 0,687, hợp lệ) giữ nguyên trong báo cáo; mọi quy tắc chọn, trần 15%, chốt chặn và cổng giữ nguyên. Quy tắc gần hòa 0,01 áp cho hai ứng viên còn lại.
- **Rủi ro đã nêu cho chủ dự án:** ở sàng lọc, ba ứng viên chỉ cách nhau 0,011 J; bỏ một ứng viên có thể bỏ lỡ lựa chọn đơn giản hơn. Chủ dự án chấp nhận.
- Mã: tham số `--drop` của giai đoạn `select`, bộ điều phối `scripts/run_r6_master.py` truyền `--drop L3-PU`.

## 3b. Quyết định mã hóa R3 (v6.2, 2026-10-24, chủ dự án đồng ý phương án đơn giản nhất, ghi trước khi viết mã mã hóa)

Chốt chặn trước niêm phong v6 đã đạt (07:49 ngày 2026-10-24). Hai việc còn mở của R3 được quyết như sau:
- **Kịch bản dài hơn kỳ test:** vụ được **cắt trong kỳ test** (giữ cách gán vụ vào một kỳ của bộ sinh và cách chấm đã đăng ký). Giai đoạn sau của vụ nằm ngoài kỳ (ví dụ xóa nợ cuối cùng của KB10) không được sinh; ghi rõ trong hồ sơ mã hóa.
- **Kế hoạch mã hóa:** chấp nhận `independent_scenarios/encoding_plan_v5.md`. **Không thêm bảng hay trường mới.** KB06 (tài sản cố định) và KB07 (xe tải) được mã hóa bản rút gọn bằng lược đồ hiện có; mọi phần không thể hiện được bằng lược đồ hiện có được liệt kê trong `independent_scenarios/encoding_notes_v5.md` (cái gì bỏ, vì sao) và gửi tác giả để biết, không để sửa kịch bản.
- Mã hóa đúng ý văn xuôi đã khóa (SHA-256 `3723fb9d...02cc`); không chỉnh độ khó cho thuận lợi với bộ phát hiện. Mọi ca hợp lệ giống tuân theo mục Làm rõ thực thi R3 của đăng ký v5.

## 4. Chốt chặn và cổng

Chốt chặn trước niêm phong S2: R trung bình ít nhất 65%, B trung bình ít nhất 40%, R của thế giới tệ nhất ít nhất 50%, trần 15%, **giống hệt v5 mục 5**. Cổng niêm phong sau R4: **giống hệt v5 mục 5** (chung 60%, kịch bản mới 35%, từng thế giới 45%, lệch phát triển không quá 15 điểm, trần 15%).

Chốt chặn không đạt: không sinh, không chấm niêm phong, dừng, viết kết quả. Chốt chặn đạt: R3, R4 theo mục 6 của v5 với seed và văn xuôi đã khóa, **sau khi chủ dự án quyết hai việc còn mở**: (a) cách xử lý kịch bản dài hơn kỳ test (cắt trong kỳ hay cho bắt đầu trước kỳ test), (b) chấp nhận kế hoạch mã hóa `independent_scenarios/encoding_plan_v5.md`.

## 5. Điều không được làm

- Không chọn h, ứng viên hay lưới sau khi thấy thế giới niêm phong; không dùng thế giới niêm phong để chọn gì.
- Không dùng nhãn của thế giới đích; không dùng `hard_negative_type` của đích.
- Không thêm đặc trưng, ứng viên hay lưới ngoài mục 3 trong vòng này.
- Không nới trần 15% hay ngưỡng chốt chặn.
- Giữ cả kết quả xấu: nếu cải thiện cảnh báo nhầm làm recall tụt dưới ngưỡng, báo đúng như vậy.

## 6. Hạ tầng, thời gian, mã

- Mã cần thêm: tham số trọng số ca hợp lệ khó trong `observed_labels`, `SourcePool.fit_score`, `run_supervised`; giai đoạn `hn` và chế độ v6 trong `screen_v5`; bộ điều phối `scripts/run_r6_master.py`; kiểm thử máy móc. Thư mục kết quả `results/v6/R6/`. Ma trận dữ liệu `work/v5_matrices` dùng lại, không sửa.
- Ước tính (không phải cam kết): khóa h khoảng 1,5 giờ; sàng lọc khoảng 1,5 giờ; tầng chọn khoảng 12 đến 20 giờ tùy số ứng viên và tốc độ máy. Tiến trình tách rời, có điểm lưu; máy tắt thì chạy lại điều phối.
- **Điểm chủ dự án có thể bác bỏ**: trước khi tầng chọn bắt đầu (sau báo cáo sàng lọc).
- Báo cáo: sau khóa h; sau sàng lọc (bảng J, ba ứng viên); sau tầng chọn (quyết định chốt chặn).
