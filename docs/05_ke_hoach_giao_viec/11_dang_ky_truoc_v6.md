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
