# 1. Kinh tế học của dòng tiền SME — vì sao "lãi mà vẫn thiếu tiền"

## 1.1 Dồn tích và tiền mặt là hai đại lượng khác nhau

Chuẩn mực kế toán (VAS/IFRS) ghi nhận doanh thu khi chuyển giao hàng hoá/dịch vụ, không phải khi nhận tiền. Một lô
hàng 2 tỷ bán chịu 60 ngày làm báo cáo tháng này có ngay 2 tỷ doanh thu, nhưng tài khoản ngân hàng chưa có đồng nào;
trong khi lương, BHXH, thuế GTGT trên chính hoá đơn đó, tiền nguyên liệu vẫn đến hạn **đúng ngày**.

Phương trình dòng tiền hoạt động của một tuần:

```
Tiền cuối tuần = Tiền đầu tuần
               + Σ thu từ hoá đơn cũ (phụ thuộc HÀNH VI khách: khi nào, bao nhiêu, có trả không)
               + thu từ doanh thu mới phát sinh trong tuần (COD, trả trước)
               − chi cố định có lịch (lương, BHXH, thuế, thuê, lãi vay)   ← biết trước, tất định
               − chi nhà cung cấp (theo kỳ hạn NCC)
               − chi bất thường (sửa chữa, đầu tư)
```

Phần khó và gây thiếu hụt là dòng thứ hai: nó là **biến ngẫu nhiên** phụ thuộc hàng trăm quyết định trả tiền của khách.

## 1.2 Vốn lưu động và chu kỳ chuyển đổi tiền (CCC)

```
CCC = DSO (số ngày phải thu) + DIO (số ngày tồn kho) − DPO (số ngày phải trả)
Vốn bị "khách giữ hộ" = Doanh thu bán chịu/ngày × DSO hành vi
```

- **DSO danh nghĩa** = kỳ hạn hợp đồng (45 ngày trung bình ở VN theo Atradius 2025).
- **DSO hành vi** = kỳ hạn + trễ thực tế (Atradius: khách trả chậm thêm "khoảng một tháng") → ~75 ngày.
- Chênh lệch 30 ngày × doanh thu bán chịu/ngày chính là khoản tín dụng không lãi mà SME đang cấp cho khách.

Ví dụ SME doanh thu 40 tỷ/năm, 65% bán chịu: doanh thu bán chịu/ngày ≈ 71 triệu. Mỗi ngày DSO hành vi tăng thêm
khoá thêm ~71 triệu vốn; 30 ngày trễ ≈ **2,1 tỷ** bị khách giữ — xấp xỉ 19 ngày tổng chi của công ty.

## 1.3 Ba loại rủi ro mà bảng tính dòng tiền truyền thống bỏ qua

| Rủi ro | Bản chất kinh tế | Hệ quả nếu bỏ qua |
|---|---|---|
| **Rủi ro thời điểm** | Tiền về theo phân phối xác suất, không đúng ngày hạn; có thói quen (trả ngày 10/25, cuối tháng, trước Tết) | Bảng tính "giả định trả đúng hạn" dự báo thừa tiền đúng những tuần nguy hiểm |
| **Rủi ro tương quan** | Khách cùng thiếu thanh khoản khi thị trường căng (COVID 2020–2021, đóng băng trái phiếu 2022–2023); 47% nguyên nhân trễ ở VN là thanh khoản của khách | Cộng các khoản trễ độc lập → đánh giá thấp đuôi rủi ro; thiếu hụt xảy ra theo cụm |
| **Rủi ro không thu được** (cure/default) | Một phần khoản phải thu sẽ không bao giờ về (nợ xấu 3% giá trị ở VN) | Nhầm "trả rất chậm" với "mất trắng" → số dư dự báo ảo |

Thêm hai rủi ro dữ liệu đặc thù SME VN (Phần 2/3): **ghi sổ theo lô** (kế toán gạch nợ cuối tháng → ngày trên sổ sai
lệch ngày tiền về) và **thoả thuận miệng** (giám đốc đồng ý khất nợ qua Zalo, không có trong hệ thống).

## 1.4 Vì sao SME chịu đòn nặng hơn doanh nghiệp lớn

1. **Đệm tiền mặt mỏng**: dữ liệu giao dịch thật của 597.000 SME Mỹ cho thấy trung vị chỉ giữ đủ tiền chi **27 ngày**
   nếu dòng thu dừng hẳn, một phần tư dưới 13 ngày ([JPMorgan Chase Institute](https://www.jpmorganchase.com/institute/all-topics/business-growth-and-entrepreneurship/report-cash-flows-balances-and-buffer-days)).
   Một tháng trễ thanh toán xấp xỉ toàn bộ đệm này (minh hoạ; không có số tương đương cho VN).
2. **Tập trung khách**: SME thường có vài khách chiếm phần lớn doanh thu; một khách lớn trễ là một cú sốc hệ thống.
3. **Quyền lực đàm phán yếu**: không ép được khách lớn trả đúng hạn, nhưng phải trả nhà cung cấp và thuế đúng hạn.
4. **Không có phòng tài chính**: chủ DN hoặc kế toán kiêm nhiệm tự dự báo bằng Excel; khoá sổ chậm (trung vị 6,4 ngày,
   nhóm cuối 10+ ngày — [APQC](https://www.apqc.org/)).
5. **Chi phí vốn cao khi thiếu hụt khẩn cấp**: vay nóng, thấu chi, chiết khấu hoá đơn (45% DN VN dùng invoice financing
   theo Atradius) hoặc trễ nghĩa vụ thuế (tiền chậm nộp 0,03%/ngày ≈ 10,95%/năm theo Luật Quản lý thuế).

## 1.5 Mô hình kinh tế của giá trị dự báo

Giá trị của một dự báo dòng tiền tốt đến từ **quyết định tốt hơn**, không từ bản thân con số:

| Quyết định | Không có dự báo xác suất | Có dự báo xác suất + cảnh báo sớm |
|---|---|---|
| Giữ bao nhiêu tiền đệm | Giữ nhiều "cho chắc" → vốn nhàn rỗi, hoặc giữ ít → vỡ | Đệm = phân vị thấp của số dư dự báo → đủ mà không thừa |
| Khi nào vay / thấu chi | Vay khẩn khi đã thiếu (lãi cao, phí, mất uy tín) | Vay có kế hoạch trước 4–8 tuần, rẻ hơn |
| Đòi khoản nào trước | Đòi khoản to nhất hoặc cũ nhất | Đòi khoản giảm xác suất thiếu hụt nhiều nhất trên mỗi giờ công |
| Giãn chi | Trễ lương/NCC/thuế khi đã cạn | Chủ động đàm phán giãn NCC trước, giữ đúng hạn thuế và lương |

Lý thuyết nền: mô hình tồn quỹ tiền mặt (Baumol 1952, Miller–Orr 1966) cho thấy đệm tối ưu tỷ lệ với **độ bất định**
của dòng tiền ròng; giảm sai số dự báo trực tiếp giảm đệm cần giữ. Đó là cơ chế kinh tế chính mà sản phẩm khai thác
(định lượng ở 03_Evaluation/06).
