# Hiểu toàn bộ dự án Agent 2 trong một tệp

Cập nhật 2026-10-24 (16:10, sau khi chấm niêm phong v6). Phần 7.5 là kết quả cuối; các phần khác đến Phần 7.4 mô tả diễn biến v5. Tệp này viết cho người **không cần biết lập trình**. Mục tiêu: đọc xong bạn kể lại được dự án cho người khác nghe, và biết hôm nay đang ở đâu.

Mọi con số là **dữ liệu tổng hợp** (dữ liệu do chương trình tự sinh), trừ khi có ghi rõ khác. Không con số nào là kết quả trên doanh nghiệp thật.

---

## Phần 0. Bản đồ một trang (đọc phần này trước)

```
VẤN ĐỀ        Doanh nghiệp nhỏ thiếu người kiểm soát; gian lận nội bộ kéo dài trung vị 12 tháng
   |
SẢN PHẨM      Mỗi tuần đọc sổ giao dịch, đưa tối đa 3 câu hỏi đối chiếu cho mỗi công ty
   |          (kèm lý do tiếng Việt kiểm được số). Con người quyết định.
   |
BẰNG CHỨNG    Chưa có dữ liệu gian lận thật, nên tự sinh "thế giới" giả để đo
   |
V4 (xong)     Chấm thi niêm phong một lần: TRƯỢT cổng G5 (S1 41%, S2 64%)
   |
V5            Làm lại có kỷ luật hơn. R2 đã xong: chốt chặn trước niêm phong KHÔNG ĐẠT
   |
KẾT QUẢ      R2 KHÔNG đạt --> DỪNG, không sinh đề niêm phong, đổi hướng sang
              "dịch vụ rà soát cho đơn vị kế toán" (chờ chủ dự án quyết)
```

Năm điều cần nhớ nhất:

1. Công cụ **gợi ý chỗ đáng hỏi lại**, không kết luận ai gian lận.
2. Ngân sách cứng: **3 câu hỏi mỗi công ty mỗi tuần**.
3. Dữ liệu là **giả**, nên mọi kết quả chỉ chứng minh "chạy được trong mô phỏng", chưa chứng minh "dùng được ngoài đời".
4. Bài thi niêm phong v4 **đã trượt**; kết luận này giữ nguyên, không được sửa lại cho đẹp.
5. Quy tắc vàng của v5: **ghi luật trước, chạy sau, không chỉnh theo kết quả**.

---

## Phần 1. Bài toán và sản phẩm

### 1.1 Vấn đề (nói bằng một ví dụ)

Hình dung một công ty phân phối 40 nhân viên. Kế toán trưởng vừa lập chứng từ, vừa duyệt chi, vừa giữ sổ. Không có kiểm toán nội bộ, không có đường dây tố giác. Nếu một người gian lận (ví dụ trả tiền cho nhà cung cấp ma), không ai nhìn thấy cho đến khi quá muộn.

Số liệu nền (ACFE 2024, báo cáo quốc tế về gian lận nội bộ):

| Điều | Giá trị |
|---|---|
| Thời gian gian lận kéo dài trung vị | 12 tháng |
| Tổ chức dưới 100 nhân sự: tổn thất trung vị | 141.000 USD |
| Dưới 100 nhân sự: có giám sát dữ liệu chủ động | 19% (so với 53% ở tổ chức lớn) |

Chỗ trống đó là chỗ sản phẩm lấp vào: **giám sát dữ liệu chủ động** cho doanh nghiệp nhỏ.

### 1.2 Sản phẩm làm gì

Mỗi tuần, với mỗi công ty:

1. Đọc toàn bộ giao dịch mới (lương, thanh toán nhà cung cấp, chi tiền mặt, tạm ứng, bán hàng, thu tiền, hoàn tiền, hủy hàng).
2. Chấm điểm "đáng hỏi lại" cho từng giao dịch.
3. Giữ lại **tối đa 3 mục** có điểm cao nhất.
4. Viết cho mỗi mục một lý do bằng tiếng Việt, ví dụ "Đơn giá cao hơn 35% so với trung vị sáu lần mua gần nhất của nhà cung cấp". Mọi con số trong câu được máy tự kiểm với dữ liệu; sai thì dừng chứ không in.
5. Đưa vào hàng đợi cho kế toán viên xem chứng từ và ghi kết luận.

**Ví von:** như một thanh tra viên chỉ có ba lá phiếu mỗi tuần. Cô ấy phải chọn ba giao dịch đáng nghi nhất trong hàng nghìn dòng, và giải thích được vì sao chọn.

### 1.3 Sản phẩm không làm gì

- Không nói "ai gian lận". Cách nói đúng: "cần đối chiếu thêm chứng từ".
- Không tự động chặn thanh toán.
- Không hứa thu hồi tổn thất.
- Không đảm bảo bắt được mọi loại gian lận.

---

## Phần 2. Dữ liệu: vì sao phải tự sinh "thế giới"

### 2.1 Không có dữ liệu thật có nhãn

Để biết công cụ giỏi đến đâu, cần sổ sách thật mà người ta **đã biết dòng nào gian lận**. Loại dữ liệu này cực hiếm: doanh nghiệp không công bố, và chưa có tệp mẫu thật nào được cung cấp cho dự án.

Cách giải quyết: viết một **bộ sinh dữ liệu** tạo ra "thế giới" giả, mỗi thế giới gồm:

- 30 đến 60 công ty giả, tổng 200.000 giao dịch;
- nhân viên, nhà cung cấp, khách hàng, tạm ứng, hóa đơn;
- khoảng 0,4% giao dịch là gian lận thuộc các kịch bản theo cây phân loại ACFE (billing, payroll, cash larceny, corruption, v.v.);
- thêm nhiều **giao dịch hợp lệ nhưng trông giống gian lận** (ví dụ chiết khấu thương mại lớn, rút tiền mặt mua nông sản, thưởng cuối năm). Đây gọi là **ca hợp lệ khó**.

Thời gian chia như đề thi:

| Giai đoạn | Thời gian | Vai trò |
|---|---|---|
| train | năm 2024 | học |
| validation | nửa đầu 2025 | chỉnh |
| test | nửa cuối 2025 | chấm điểm |

### 2.2 Điểm yếu cốt lõi của dữ liệu giả

**Mô hình có thể học thuộc "tật" của bộ sinh thay vì học cách phát hiện gian lận.** Ví dụ thật đã gặp (ghi là L11 trong hạn chế dữ liệu): bộ sinh chỉ điền trường `applied_invoice_id` ở các dòng trả hàng **gian lận**, nên mô hình chỉ cần hỏi "trường này có trống không?" là đoán đúng. Ngoài đời không như vậy.

**Ví von:** học sinh luyện đề của một thầy, rồi phát hiện thầy luôn đặt đáp án đúng ở câu C. Điểm cao, nhưng không biết gì. Vì thế phải có bài kiểm **V13** (kiểm xem sự có mặt của một trường có tách được gian lận không).

### 2.3 Hai loại "đề thi"

| Loại | Dùng để | Ghi chú |
|---|---|---|
| Thế giới phát triển (v5: 1001 đến 1020) | Chọn phương pháp, thử ý tưởng | Được xem kết quả thoải mái |
| Thế giới niêm phong | Chấm điểm cuối cùng | **Chỉ chấm một lần.** Xem điểm xong là mất tính niêm phong |

Các thế giới niêm phong v4 (seed 931 đến 933) đã được chấm nên giờ chỉ còn dùng để chẩn đoán, không còn là đề thi.

---

## Phần 3. Các khái niệm đo lường (phần khó nhất, đọc chậm)

### 3.1 Recall tại ngân sách 3 (viết tắt R)

> Trong tất cả dòng gian lận, bao nhiêu phần trăm nằm trong ba mục được chọn mỗi tuần?

Ví dụ: có 100 dòng gian lận, ba mục mỗi tuần của công cụ trúng 60 dòng, thì R bằng 60%.

### 3.2 Ba chế độ vận hành: S1, S2, Cold

Ví von **một bác sĩ**:

| Chế độ | Bác sĩ ví von | Thực chất |
|---|---|---|
| **S1** | Bệnh nhân cũ, đã có hồ sơ bệnh án | Công ty này đã có một số vụ được điều tra và xác nhận; học từ chính công ty đó |
| **S2** | Bệnh nhân mới, nhưng bác sĩ đã khám hàng trăm bệnh nhân khác | Công ty mới chưa có nhãn; mô hình học từ các công ty khác rồi áp vào. **Đây là chế độ chính của v5** |
| **Cold** | Bác sĩ chưa khám ai, chỉ có sách và quan sát "người này khác bình thường của chính họ" | Không dùng nhãn nào; chỉ dùng luật cộng độ lệch so với lịch sử của chính đối tượng |

Vì sao S2 là chính: khách hàng thật gần như luôn là công ty mới, chưa có vụ nào được xác nhận.

### 3.3 P2: thử với loại gian lận chưa từng thấy

Cây phân loại ACFE có 10 nhánh. P2 lần lượt **giấu một nhánh khỏi nhãn học**, rồi đo xem mô hình có bắt được nhánh bị giấu không. Mục đích: kiểm khả năng bắt kiểu gian lận **mới**, vì kẻ gian không làm đúng kịch bản mà ta đã dạy.

Kết quả của P2 là chỉ số **B**: trung bình recall của các nhánh bị giấu.

### 3.4 PU: nhãn không đầy đủ

Trong dữ liệu thật, dòng "không có nhãn" **không có nghĩa là sạch**; nó có thể là gian lận chưa bị phát hiện. Cách gọi: **P** (positive, đã xác nhận) và **U** (unlabeled, chưa biết).

Cách xử lý: khi huấn luyện, **giảm trọng số của dòng U** xuống w. v5 thử ba mức w bằng 0,1; 0,2; 0,5 và chọn một.

### 3.5 Q và J: chấm theo học sinh yếu

- **Q = (R + B) / 2** cho mỗi thế giới: nửa điểm là bắt gian lận chung, nửa điểm là bắt loại chưa thấy.
- **J = trung bình Q của 20% thế giới tệ nhất.**

Dùng J thay cho trung bình chung vì mô hình tốt ở nhiều thế giới nhưng sụp ở vài thế giới thì vẫn nguy hiểm. **Ví von:** đánh giá một lớp học theo điểm trung bình của các em yếu nhất, không theo điểm trung bình cả lớp.

### 3.6 Trần ca hợp lệ khó: 15%

Công cụ không được cảnh báo nhầm quá 15% trong số các giao dịch hợp lệ khó, ở từng thế giới. Nếu vượt, ứng viên bị loại, vì kế toán viên sẽ chán và bỏ không xem nữa.

---

## Phần 4. Lịch sử: từ v4 đến v5

### 4.1 V4: thi niêm phong và trượt

| Chế độ | Kết quả niêm phong v4 | Ghi chú |
|---|---:|---|
| S1 | 41,31% | dưới ngưỡng dừng 50% |
| S2 | 63,87% | không đạt cổng G5 |
| S2 trên kịch bản mới | 31,22% | điểm yếu lớn nhất |

Kết luận **G5 không đạt, kích hoạt dừng M2**. Quy tắc: không chạy lại, không đổi mô hình để tìm số đẹp hơn.

Hậu kiểm (R0) cho thấy mô hình tốt hơn khi phát triển (khoảng 80 đến 100% ở nhiều kịch bản đã biết) nhưng tụt mạnh khi gặp công ty và kịch bản mới. Nguyên nhân chia nhỏ ra nhiều yếu tố, không quy hết cho một lỗi.

### 4.2 Vì sao v5 khác v4

| v4 | v5 |
|---|---|
| 3 thế giới phát triển | **20 thế giới** với bối cảnh ngẫu nhiên hóa (số công ty, quy mô tiền, lịch lương, mức che giấu) |
| Chọn bằng điểm trung bình | Chọn bằng **J** (nhóm tệ nhất) |
| Chọn xong mới biết có đủ tốt không | Có **chốt chặn trước niêm phong**: không đạt thì không được chấm niêm phong |
| Kịch bản mới tự nghĩ | Kịch bản mới do **một phiên viết độc lập** viết, rồi khóa bằng mã băm |
| Đề xuất đổi hướng chưa có | Có sẵn **phương án sản phẩm dự phòng** |

### 4.3 Những bài học đắt giá của v5 (nên nhớ)

| Sự cố | Bài học |
|---|---|
| Dừng sớm trong LightGBM làm mô hình sập xuống 1 cây | Chuyển sang 400 cây cố định (ghi trong sửa đổi v1.2). Recall từ khoảng 34% lên 50,8% ở phép thử. |
| Bộ sinh để lộ "lối tắt" (trường chỉ điền ở dòng gian lận) | Loại các đặc trưng liên quan (sửa đổi v1.3), ghi hạn chế L11, thêm kiểm V13 |
| Nhân viên được ghi trước ngày vào làm (thế giới 1017) | Thêm chốt `hire_guard`; thế giới cũ giống từng byte |
| pandas 3 lưu thời gian theo mili giây | Mọi cửa sổ thời gian từng bị sai; đã sửa bằng phép chia Timedelta và có kiểm thử |
| Máy tắt giữa chừng | Mọi bước có điểm lưu; kiểm lại mã băm rồi chạy tiếp |

---

## Phần 5. Cách hệ thống hoạt động bên trong (sơ đồ)

```
Sổ giao dịch (CSV)
      |
      v
[1] Kiểm tra đầu vào (schema)
      |
      v
[2] Luật nghiệp vụ     ---> ví dụ: nhà cung cấp trùng tài khoản với nhân viên
      |
[3] Đặc trưng          ---> số tiền, thời điểm, người lập/duyệt, độ lệch so với lịch sử của chính đối tượng
      |
[4] Mô hình xếp hạng   ---> điểm "đáng hỏi lại" (học từ các thế giới khác)
      |
[5] Ngân sách 3 mục/công ty/tuần + gộp vụ
      |
[6] Lý do tiếng Việt   ---> mọi số được máy kiểm lại với dữ liệu
      |
[7] Hàng đợi cho kế toán viên ---> ghi kết luận + số phút + "đáng kiểm tra hay không"
```

### 5.1 Ba lớp phát hiện

| Lớp | Cần nhãn? | Mạnh ở | Yếu ở |
|---|---|---|---|
| **Luật** | Không | Trùng tài khoản, lương sau nghỉ việc, thanh toán trùng | Gian lận "sạch", không vi phạm luật nào |
| **Độ lệch so với chính đối tượng** (EntityDeviation, EntityDeviation2) | Không | Lương tăng, đơn giá tăng, khách mua thấp bất thường | Tín hiệu yếu, nhiều báo nhầm |
| **Mô hình có giám sát** (LightGBM) | Có (từ thế giới khác) | Kết hợp nhiều dấu hiệu | Học thuộc tật của bộ sinh, yếu với kịch bản mới |

### 5.2 Điều mới trong v5: phát hiện thay đổi

Thay vì hỏi "số tiền này lớn không", hỏi "**số tiền này khác thường so với chính nhân viên, chính nhà cung cấp, chính khách hàng đó chưa**". Gồm: lương tăng vọt, đơn giá tăng dần, hóa đơn bán thấp bất thường, công nợ quá hạn mà vẫn xuất hóa đơn mới, tạm ứng chồng tạm ứng.

Chẩn đoán trên dữ liệu tổng hợp: các đặc trưng này giúp mô hình có giám sát thêm khoảng 1,9 điểm recall chung và 2,1 điểm trên kịch bản mới, ổn định qua các seed. Là cải thiện nhỏ nhưng đáng tin.

---

## Phần 6. Giao thức v5: luật chơi đã khóa

Tài liệu gốc: `05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md` (hiện là bản v1.3).

### 6.1 Hai tầng chọn

| Tầng | Thế giới | Seed | Làm gì |
|---|---|---|---|
| **Sàng lọc** | 8 thế giới (1001 đến 1008) | 1 (seed 0) | 4 ứng viên có giám sát, giữ 3 ứng viên đứng đầu |
| **Chọn** | 20 thế giới (1001 đến 1020) | 5 (seed 0 đến 4) | Chọn 1 cấu hình có giám sát cuối cùng; chọn riêng 1 cấu hình Cold |

Mỗi thế giới làm "đích" một lần, học từ 19 thế giới còn lại.

### 6.2 Ứng viên

| Nhóm | Tên | Ý chính |
|---|---|---|
| Có giám sát | L3-PU | Nền: luật cộng đặc trưng cơ bản, có xử lý PU |
| Có giám sát | L4-FB-PU | Thêm phản hồi và đặc trưng v4 |
| Có giám sát | L4-PU-E2-AR | Thêm độ lệch thực thể EntityDeviation2 và công nợ |
| Có giám sát | L4-PU-E2-AR-2plus1 | Như trên, ngân sách theo chính sách "2 theo mô hình, 1 theo không nhãn" |
| Cold | Cold-Rules-E2 | Luật cộng EntityDeviation2 (đã loại đặc trưng lối tắt) |
| Cold | Cold-v4 | Luật cộng bộ phát hiện v4 |

Việc chọn trọng số PU w (0,1; 0,2; 0,5) làm trước, dùng L4-FB-PU trên 8 thế giới sàng lọc, rồi khóa.

### 6.3 Hai chốt chặn

**Chốt chặn trước niêm phong (sau R2)**: ứng viên đã chọn phải đạt đồng thời:

| Điều kiện | S2 (có giám sát) | Cold (không nhãn) |
|---|---:|---:|
| Recall trung bình (R) | từ 65% | từ 40% |
| Trung bình B (loại gian lận bị giấu) | từ 40% | từ 33% |
| Thế giới tệ nhất | từ 50% | từ 30% |
| Ca hợp lệ khó, từng thế giới | không quá 15% | không quá 15% |

- **S2 không đạt** thì **không sinh và không chấm niêm phong v5**, chuyển sang đề xuất đổi hướng.
- **Cold không đạt** thì bỏ Cold; S2 vẫn đi tiếp nếu đạt.

**Cổng niêm phong v5 (sau R4, trên 4 thế giới niêm phong mới)**:

| Cổng | Điều kiện |
|---|---|
| S2 chung | recall trung bình từ 60% |
| S2 mới | recall trung bình trên kịch bản mới từ 35% |
| S2 sàn | từng thế giới từ 45% |
| S2 lệch dev | chênh với kết quả phát triển không quá 15 điểm |
| S2 báo nhầm | ca hợp lệ khó không quá 15% ở từng thế giới |
| Cold | 35% chung, 30% trên kịch bản mới, mỗi thế giới 25%, ca khó 15% |

### 6.4 Năm nguyên tắc không được vi phạm

1. **Ghi trước, chạy sau.** Mọi thay đổi luật phải ghi vào tài liệu đăng ký trước khi nhìn bất kỳ so sánh nào.
2. **Không chỉnh theo thế giới niêm phong.** Chấm một lần, xong là xong.
3. **Không đọc nhãn của công ty đích** để chọn mô hình hay ngưỡng.
4. **Giữ cả kết quả xấu**, không loại thế giới vì mô hình làm kém.
5. **Không mở vòng v6** để tìm số đạt sau khi v5 trượt.

---

## Phần 7. Tình hình hiện tại (2026-10-22)

### 7.1 Việc đã xong

| Hạng mục | Trạng thái |
|---|---|
| 20 thế giới phát triển 1001 đến 1020 | Xong, đạt kiểm V1 đến V12 |
| Ma trận đặc trưng nền và đặc trưng thay đổi cho cả 20 thế giới | Xong; sau khi máy tắt đã kiểm lại SHA-256, khớp hết |
| Kiểm tương đương lấy mẫu âm 10% | **Đạt** (Spearman 0,957, lệch recall 0,82 điểm); tỷ lệ 0,1 được dùng |
| Đặc trưng thay đổi và câu giải thích tiếng Việt v5 | Xong, có kiểm thử |
| Quan sát biến động gắn vào lý do tuần của pipeline | Xong (chỉ giải thích, không đổi cảnh báo) |
| Dịch vụ rà soát (API, giao diện, trang nhiều khách, KPI thí điểm) | Xong |
| Kịch bản niêm phong độc lập (10 kịch bản) | Đã viết và **khóa văn xuôi bằng mã băm** |
| Khung mã hóa niêm phong, kiểm V13, nhánh báo cáo "không đạt" | Xong, có kiểm thử |
| Bộ kiểm thử | 179 bài qua, 12 bỏ qua (lần chạy toàn bộ gần nhất) |

### 7.2 Kết quả R2 (xong lúc 17:43 ngày 2026-10-22)

| Hạng mục | Kết quả |
|---|---|
| Chọn trọng số PU | Cả ba w (0,1; 0,2; 0,5) đều vượt trần ca hợp lệ khó 15%; khóa w = 0,1 là w có J cao nhất (làm rõ đã ghi vào đăng ký trước khi có kết quả sàng lọc) |
| Sàng lọc 4 ứng viên có giám sát | Recall chung 82 đến 90%, nhánh bị ẩn 56 đến 59%, vượt ngưỡng 65% và 40%. Nhưng **4 hoặc 5 trên 8 thế giới vượt trần 15%** (cao nhất 18,8%), nên không ứng viên nào hợp lệ |
| Cold (không nhãn) | Recall chung 21,8% (Cold-Rules-E2) và 37,4% (Cold-v4), dưới ngưỡng 40%; cũng không hợp lệ |
| Tầng chọn | Không có ứng viên nào để chạy |
| Chốt chặn trước niêm phong | **KHÔNG ĐẠT** |

Hiểu đúng kết quả này: mô hình **bắt gian lận khá tốt trên dữ liệu phát triển** (kinh nghiệm v4 cho thấy con số sẽ tụt khi sang đề thi mới), nhưng **cảnh báo nhầm quá nhiều trên các giao dịch hợp lệ trông giống gian lận**, nhất là nhóm chi phí (`expense`). Mức vượt chỉ vài điểm phần trăm so với trần, nhưng trần được áp cho từng thế giới và từng giao thức nên rất nghiêm. Luật đã khóa không cho nới trần sau khi thấy kết quả.

### 7.3 Điều gì xảy ra tiếp theo

Theo mục 4 và mục 7 của đăng ký: **không sinh và không chấm niêm phong v5, không mở vòng v6.** Kịch bản độc lập đã viết được giữ làm tư liệu, không mã hóa. Việc còn lại là đề xuất đổi hướng (Phần 8) để chủ dự án quyết định. Báo cáo: `03_danh_gia_va_hieu_qua_kinh_te/09_ket_qua_niem_phong_v5.md` và `10_ket_qua_R2_v5.md`.

### 7.4 Cây quyết định (đã đi đến nhánh dưới)

```
R2 xong
  |
  +-- S2 đạt chốt chặn   (không xảy ra)
  |
  +-- S2 KHÔNG đạt   <--- Ở ĐÂY
         |
         +-- KHÔNG sinh, KHÔNG chấm niêm phong
         +-- Báo cáo 09_ket_qua_niem_phong_v5.md đã viết
         +-- Trình hướng đổi hướng: dịch vụ rà soát cho đơn vị kế toán
```

---

### 7.5 Kết quả cuối: vòng v6 (cập nhật 2026-10-24)

Sau v5 trượt chốt chặn, vòng v6 sửa đúng nguyên nhân (dạy mô hình bằng các ca hợp lệ đã được xác nhận) và **đạt chốt chặn trước niêm phong**. Thi thật (4 bộ dữ liệu mới, chấm một lần):

| Điều kiện | Kết quả | Yêu cầu | |
|---|---:|---:|:-:|
| Bắt gian lận chung | 64,5% | từ 60% | Đạt |
| Bắt loại gian lận mới | 41,2% | từ 35% | Đạt |
| Bộ dữ liệu thấp nhất | 58,9% | từ 45% | Đạt |
| Báo nhầm | 12,8% | dưới 15% | Đạt |
| Không chênh quá xa so với lúc thi thử (88,4%) | chênh 23,9 điểm | không quá 15 | **Trượt** |

**Kết luận chính thức: trượt cổng niêm phong vì một điều kiện.** Không chấm lại, không có v7. Điều rút ra: khi gặp dữ liệu mới, hệ thống bắt được khoảng 64% gian lận (không phải 88%), và rất khác nhau giữa các loại: có loại bắt gần hết, có loại gần như không bắt được. Báo cáo: `03_danh_gia_va_hieu_qua_kinh_te/13_ket_qua_niem_phong_v6.md`.

---

## Phần 8. Phương án sản phẩm dự phòng: "dịch vụ rà soát cho đơn vị kế toán"

Nếu mô hình học máy chưa đạt cổng, vẫn có sản phẩm hữu ích mà không cần hứa quá nhiều:

- **Bán cho đơn vị dịch vụ kế toán**, không bán thẳng cho chủ doanh nghiệp siêu nhỏ.
- Mỗi tuần mỗi khách có tối đa 3 câu hỏi đối chiếu, **có bằng chứng và lý do**, kế toán viên đi hỏi lại khách.
- Dựa chủ yếu vào luật, độ lệch so với lịch sử, và lý do kiểm được số; học máy chỉ là lớp xếp thứ tự thêm.
- Cần thí điểm thật để đo: tỷ lệ "đáng kiểm tra" (ngưỡng giả định từ 15%), thời gian rà soát (không quá 30 phút mỗi khách mỗi tuần), mức sẵn lòng trả (ít nhất 3 trên 5 đơn vị).
- **Chưa thí điểm được** cho đến khi có thẩm định pháp lý (Nghị định 13/2023/NĐ-CP về dữ liệu cá nhân) và thỏa thuận với doanh nghiệp.

Recall đo được của kênh không nhãn (từ thế giới niêm phong v4 đã mở), ví dụ: `overbilling_excess_payment` 100% (4 vụ), `terminated_still_paid` 90,5% (6 vụ), `bank_detail_switch` 27,8% (3 vụ). Số vụ rất nhỏ nên chỉ dùng để xếp thứ tự ưu tiên, không dùng để chào bán.

---

## Phần 9. Sơ đồ thư mục: tìm gì ở đâu

### 9.1 Tài liệu (`docs/`)

| Thư mục | Nội dung | Đọc khi |
|---|---|---|
| `STATUS.md` | Trạng thái mới nhất | Luôn đọc đầu tiên |
| `01_phan_tich_kinh_te_va_nghiep_vu/` | Thị trường, nhu cầu, đề xuất đổi hướng | Cần hiểu vì sao làm |
| `02_du_lieu/` | Cách sinh dữ liệu, kịch bản, hạn chế | Cần hiểu dữ liệu |
| `03_danh_gia_va_hieu_qua_kinh_te/` | Kết quả v4, R2, kinh tế | Cần xem số |
| `04_phuong_phap_va_pipeline/` | Kiến trúc, đặc trưng, luật, thí nghiệm | Cần hiểu kỹ thuật |
| `05_ke_hoach_giao_viec/` | Kế hoạch, đăng ký v5, hướng dẫn vận hành | Cần làm việc tiếp |
| `06_ghi_chep_lam_viec/` | Nhật ký cũ | Chỉ khi tra lịch sử |

### 9.2 Mã (`agent2/`) cho người tò mò

| Tệp | Làm gì |
|---|---|
| `world_v5_dev.py`, `world_v5_sealed.py` | Sinh thế giới phát triển và thế giới niêm phong |
| `change_detect.py` | Đặc trưng thay đổi, EntityDeviation2 |
| `base_v5.py`, `screen_v5.py`, `select_v5.py` | Huấn luyện, sàng lọc, chọn ứng viên, chốt chặn |
| `sealed_v5.py` | Khóa mã, chấm niêm phong một lần |
| `explain_v5.py`, `change_ops.py` | Câu lý do tiếng Việt cho thay đổi |
| `pipeline_v4.py`, `service.py` | Pipeline tuần và dịch vụ rà soát |

---

## Phần 10. Từ điển nhanh

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| ACFE | Hiệp hội kiểm toán gian lận quốc tế; có "cây gian lận" 10 nhánh |
| Thế giới | Một bộ dữ liệu giả hoàn chỉnh (30 đến 60 công ty, 200.000 giao dịch) |
| Niêm phong | Đề thi chưa ai thấy kết quả, chỉ chấm một lần |
| Recall | Bắt được bao nhiêu phần trăm gian lận thật |
| Ngân sách B3 | Tối đa 3 mục mỗi công ty mỗi tuần |
| S1, S2, Cold | Chế độ vận hành: đã có hồ sơ, công ty mới học từ nơi khác, hoàn toàn không nhãn |
| P2 | Giấu một nhánh gian lận để thử bắt loại chưa thấy |
| PU | Dữ liệu có nhãn dương đã xác nhận, còn lại là "chưa biết" |
| J, Q | Điểm chọn: nửa chung nửa loại chưa thấy, rồi lấy nhóm thế giới tệ nhất |
| Ca hợp lệ khó | Giao dịch đúng nhưng trông giống gian lận |
| Chốt chặn | Điều kiện phải qua trước khi được sinh và chấm đề niêm phong |
| Lối tắt của bộ sinh | Tật của dữ liệu giả mà mô hình có thể học thuộc |
| LightGBM | Thuật toán xếp hạng dùng nhiều cây quyết định |

---

## Phần 11. Câu hỏi thường gặp

**Vì sao không dùng dữ liệu thật?**
Chưa có tệp mẫu thật có nhãn, và dữ liệu thật cần thẩm định pháp lý (dữ liệu nhân viên là dữ liệu cá nhân) cùng thỏa thuận với doanh nghiệp. Đây là việc của giai đoạn thí điểm.

**Vì sao v4 trượt mà vẫn làm tiếp?**
Chủ dự án duyệt một vòng v5 có kỷ luật hơn, với 20 thế giới, chốt chặn trước niêm phong và phương án dự phòng. Nếu v5 cũng trượt thì dừng, không mở v6.

**Số 77% trong bản tóm tắt điều hành cũ có đáng tin không?**
Không nên dùng. Đó là số đo ở giai đoạn phát triển sớm, trước khi v4 trượt niêm phong. Số đáng tin hơn cho khả năng chuyển sang công ty mới là kết quả niêm phong v4: 63,87% (S2).

**Có thể cải thiện kết quả bằng cách chỉnh mô hình thêm không?**
Chỉ trong R2 và chỉ theo luật đã ghi. Sau khi nhìn thế giới niêm phong thì không được chỉnh nữa.

**Nếu R2 không đạt thì coi như thất bại?**
Là thất bại của phương pháp học máy trên dữ liệu tổng hợp, không phải của sản phẩm. Phương án dự phòng dựa vào luật, bằng chứng và con người, vẫn có thể thí điểm.

**Còn lại gì ngoài máy tính?**
Thí điểm thật với đơn vị kế toán, thẩm định pháp lý, báo giá thử. Phần này nằm ngoài phần trăm hoàn thành của phần mã.

---

## Phần 12. Bảng nhớ nhanh (10 con số)

| Con số | Ý nghĩa |
|---:|---|
| 3 | câu hỏi mỗi công ty mỗi tuần |
| 12 | tháng gian lận kéo dài trung vị (ACFE 2024) |
| 41,31% và 63,87% | S1 và S2 của v4 niêm phong (trượt) |
| 20 | thế giới phát triển của v5 |
| 400 | cây cố định mỗi mô hình (thay cho dừng sớm) |
| 0,1 | tỷ lệ giữ lại dòng âm khi lấy mẫu (đã kiểm tương đương) |
| 20% | nhóm thế giới tệ nhất dùng cho J |
| 15% | trần báo nhầm trên ca hợp lệ khó |
| 65 / 40 / 50 | chốt chặn S2: R trung bình, B trung bình, thế giới tệ nhất (tính theo %) |
| 60 / 35 / 45 | cổng niêm phong S2: chung, kịch bản mới, từng thế giới (tính theo %) |

---

## Phần 13. Bạn cần làm gì tiếp

R2 đã xong và chốt chặn không đạt, nên không còn việc chờ máy chạy. Có ba quyết định thuộc về chủ dự án:

1. **Chấp nhận kết luận v5 hay không.** Luật đã khóa nói: không nới trần 15%, không mở vòng v6, không chấm niêm phong. Đọc `03_danh_gia_va_hieu_qua_kinh_te/09_ket_qua_niem_phong_v5.md` (bảng bằng chứng chỉ một trang).
2. **Có đi theo hướng "dịch vụ rà soát cho đơn vị kế toán" không.** Nội dung ở `01_phan_tich_kinh_te_va_nghiep_vu/09_de_xuat_doi_huong_dich_vu_ra_soat.md` và Phần 8 của tệp này. Hướng này cần thẩm định pháp lý và 3 đến 5 đơn vị kế toán thử nghiệm ở chế độ chỉ xem.
3. **Có muốn mở một vòng mới ngoài khuôn v5 không** (ví dụ giảm cảnh báo nhầm ở nhóm chi phí). Việc này phải là một đăng ký mới do chủ dự án duyệt, không phải sửa v5 sau khi thấy kết quả.

Kịch bản độc lập đã viết (10 kịch bản, văn xuôi đã khóa) được giữ làm tư liệu, chưa mã hóa.
