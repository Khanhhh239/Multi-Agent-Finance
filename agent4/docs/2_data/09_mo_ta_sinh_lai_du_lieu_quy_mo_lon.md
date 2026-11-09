# Mô tả yêu cầu sinh lại dữ liệu quy mô lớn

## 1. Mục tiêu

Mở rộng bộ sinh dữ liệu tài chính hiện tại để tạo một kho dữ liệu tổng hợp mô phỏng doanh nghiệp phân phối thiết bị và cung cấp dịch vụ kỹ thuật có quy mô vừa–lớn tại Việt Nam.

Không được sinh dữ liệu bằng cách nhân bản các dòng hiện có. Dữ liệu phải được tạo từ các sự kiện nghiệp vụ liên kết với nhau, bảo đảm tính nhất quán giữa sổ cái, hóa đơn, thanh toán, tồn kho, nhân sự, tài sản, khoản vay và ngân sách.

## 2. Hồ sơ doanh nghiệp mục tiêu

- Loại hình: công ty cổ phần phân phối thiết bị CNTT, thiết bị văn phòng, vật tư tiêu hao và dịch vụ kỹ thuật.
- Chế độ kế toán: TT133, đơn vị tiền tệ VND.
- Thời gian dữ liệu: từ `01/01/2023` đến `14/10/2026`.
- Số dư đầu kỳ: `31/12/2022`.
- Các tháng trước `09/2026` đã khóa sổ; tháng `09/2026` và `10/2026` là kỳ mở.
- Quy mô doanh thu mục tiêu: khoảng `900–1.300 tỷ đồng/năm`.
- Tăng trưởng doanh thu bình quân: `8–15%/năm`.
- Biên lợi nhuận gộp: `17–22%`.
- Biên lợi nhuận ròng: `2–5%`.
- Có mùa vụ, tăng trưởng, suy giảm và biến động thực tế; không để doanh thu tăng đều một cách cơ học.

## 3. Quy mô danh mục

- 7 chi nhánh: Hà Nội, TP.HCM, Đà Nẵng, Hải Phòng, Bình Dương, Cần Thơ và Nghệ An.
- 10–12 phòng ban.
- Khoảng 450–600 nhân viên, có lịch sử tuyển mới, nghỉ việc, thay đổi phòng ban và điều chuyển chi nhánh.
- Khoảng 1.500–2.000 khách hàng, bao gồm:
  - doanh nghiệp lớn;
  - doanh nghiệp vừa và nhỏ;
  - cơ quan nhà nước và trường học;
  - đại lý;
  - khách bán lẻ.
- Khoảng 100–150 nhà cung cấp.
- Khoảng 300–450 mã hàng và dịch vụ.
- Khoảng 150–250 hợp đồng dịch vụ định kỳ.
- Khoảng 80–150 tài sản cố định.
- Có nhiều tài khoản ngân hàng, khoản vay ngắn hạn, trung hạn và tiền gửi có kỳ hạn.

## 4. Quy mô giao dịch mong muốn

Mục tiêu sau khi sinh:

| Bảng | Số dòng mục tiêu |
|---|---:|
| `gl_entry` | 1–2 triệu |
| `gl_journal` | 250.000–450.000 |
| `ar_invoice` | 100.000–180.000 |
| `ar_invoice_line` | 250.000–500.000 |
| `ar_receipt` | 90.000–170.000 |
| `ap_bill` | 15.000–30.000 |
| `inventory_txn` | 250.000–500.000 |

`payroll` phải có dữ liệu đầy đủ theo nhân viên và tháng. Các bảng tài sản, khoản vay, ngân sách, khóa sổ và `ground_truth` phải có quy mô tương ứng.

Các giới hạn trên là khoảng mục tiêu, không cần ép chính xác nếu làm ảnh hưởng tính hợp lý nghiệp vụ.

## 5. Yêu cầu về tính thực tế

Dữ liệu phải thể hiện được các quan hệ sau:

- Doanh thu khác nhau theo chi nhánh, phân khúc khách hàng, nhóm sản phẩm và mùa vụ.
- Các chi nhánh không tăng trưởng giống nhau; có chi nhánh hiệu quả cao, chi nhánh tăng trưởng chậm và ít nhất một chi nhánh có giai đoạn thua lỗ.
- Top 10 khách hàng chiếm khoảng 25–35% doanh thu, không tập trung quá cực đoan.
- Khách hàng lớn có đơn hàng lớn nhưng thời hạn thanh toán dài.
- Khách hàng nhà nước có doanh thu tập trung vào cuối năm và thường thanh toán chậm.
- Một phần khách hàng thanh toán sớm, đúng hạn, trễ hạn, trả nhiều lần hoặc trở thành nợ khó đòi.
- Tồn kho, mua hàng và công nợ nhà cung cấp phải thay đổi theo nhu cầu bán hàng.
- Giá mua, giá bán và biên lợi nhuận biến động theo thời gian.
- Chi phí lương tăng theo số nhân viên và điều chỉnh lương hằng năm.
- Chi phí vận chuyển, hoa hồng, marketing và dịch vụ liên quan phải tương quan với doanh thu.
- Tiền, công nợ, tồn kho và vay ngân hàng phải tạo thành dòng tiền hợp lý.
- Có áp lực thanh khoản trong một vài giai đoạn nhưng số dư tiền không được âm ngoài các tình huống cố ý có nhãn.
- Ngân sách phải được lập trước và độc lập tương đối với số thực tế, không đơn thuần lấy số thực tế rồi cộng nhiễu.

## 6. Các tình huống nghiệp vụ cần có

Giữ lại hoặc mở rộng những tình huống quan trọng đang có:

- khách hàng lớn mất khả năng thanh toán;
- thanh toán trùng hóa đơn nhà cung cấp;
- chứng từ kế toán lệch Nợ/Có có chủ đích và được ghi rõ trong `ground_truth`;
- chia nhỏ khoản chi để né ngưỡng phê duyệt;
- giao dịch ngoài giờ hành chính;
- biên lợi nhuận một nhóm sản phẩm bị thu hẹp;
- chi phí marketing hoặc điện nước tăng bất thường;
- khách hàng trả trước rồi mới xuất hóa đơn;
- hàng bán bị trả lại và chiết khấu thương mại;
- chi phí không được trừ khi tính thuế;
- hạch toán thu tiền theo lô;
- kỳ chưa khóa sổ;
- nội dung mô tả chứng từ chứa prompt injection và phải được coi là dữ liệu không tin cậy.

Bổ sung thêm:

- đối tác trùng hoặc gần giống tên nhưng khác mã;
- hóa đơn điều chỉnh hoặc thay thế;
- bút toán được tạo sau nhưng ghi nhận vào kỳ trước;
- khách hàng đồng thời là nhà cung cấp;
- một chi nhánh tăng doanh thu nhờ chiết khấu sâu nhưng biên lợi nhuận giảm;
- nhân viên kinh doanh nghỉ việc và bàn giao khách hàng;
- khoản mua sắm tài sản lớn ảnh hưởng dòng tiền;
- ít nhất một giai đoạn vi phạm hoặc gần vi phạm hạn mức tín dụng.

Mỗi tình huống cố ý phải có ID, thời gian, thực thể liên quan, mô tả, kết quả kỳ vọng và cách kiểm tra trong bảng `ground_truth`.

## 7. Ràng buộc kỹ thuật và kế toán

- Giữ tương thích với schema hiện tại và `agent4/engine/metrics.py`.
- Không đổi tên hoặc bỏ các bảng, cột và view đang được sử dụng nếu không thật sự cần thiết.
- Mọi metric ID hiện có phải tiếp tục tính được.
- Mọi chứng từ thông thường phải cân bằng Nợ và Có.
- Các chứng từ cố ý sai phải có nhãn rõ ràng và không được trộn với lỗi ngoài ý muốn.
- Đối soát sổ cái với AR, AP và tồn kho phải bằng 0, ngoại trừ tình huống sai lệch đã công bố.
- Bảo đảm phương trình kế toán tại cuối mỗi tháng, có tính đến các ngoại lệ được gắn nhãn.
- Không tạo hóa đơn, thanh toán hoặc giao dịch kho mồ côi.
- Không để khóa ngoại nghiệp vụ trỏ đến mã khách hàng, nhân viên, chi nhánh, tài khoản hoặc mặt hàng không tồn tại.
- Không tạo SQL hoặc dữ liệu có khả năng ghi vào hệ thống bên ngoài.
- Không chứa thông tin thật, bí mật hoặc thông tin nhận dạng cá nhân.

## 8. Tính tái lập

- Dùng seed cố định và tập trung tất cả tham số trong cấu hình.
- Cùng profile và seed phải sinh ra kết quả giống nhau.
- Tính tái lập phải áp dụng cho toàn bộ kho, bao gồm cả bảng `budget`.
- Không sử dụng hàm ngẫu nhiên không được seed trực tiếp trong DuckDB.
- Ghi `profile_id`, `seed`, `data_version`, thời gian dữ liệu và cấu hình chính vào `company_info`.
- Tính hash cho các bảng quan trọng để kiểm tra tái lập.

## 9. Hiệu năng

Nếu cách sinh hiện tại không đáp ứng được quy mô mới, chỉ tối ưu những phần cần thiết:

- ghi dữ liệu theo batch;
- tránh insert từng dòng vào DuckDB;
- có thể phân mảnh theo tháng;
- chỉ vector hóa những vòng lặp có chi phí lớn;
- không hy sinh tính nhất quán nghiệp vụ để đạt số dòng.

Mục tiêu tham khảo: sinh khoảng một triệu dòng `gl_entry` trong dưới 10 phút trên máy phát triển thông thường.

## 10. Kiểm định sau khi sinh

Sau khi sinh, phải xuất báo cáo tối thiểu gồm:

- số dòng của từng bảng;
- doanh thu, lợi nhuận, biên gộp và biên ròng theo năm;
- doanh thu theo chi nhánh và nhóm sản phẩm;
- số dư tiền, phải thu, phải trả, tồn kho và vay cuối kỳ;
- DSO, DPO và tuổi nợ;
- số lượng chứng từ lệch;
- kết quả đối soát AR, AP và tồn kho;
- kết quả kiểm tra khóa ngoại nghiệp vụ;
- hash tái lập;
- danh sách và trạng thái kiểm tra các tình huống trong `ground_truth`.

Các tỷ lệ và phân phối phải được kiểm tra tính hợp lý, không chỉ xác nhận rằng chương trình chạy thành công.

## 11. Quản lý phiên bản

- Không ghi đè kho dữ liệu và baseline hiện tại.
- Sinh kho mới dưới tên hoặc thư mục có phiên bản riêng.
- Tăng `data_version`.
- Các benchmark chứa đáp án số tuyệt đối của kho cũ sẽ không còn tương thích; phải tạo baseline và ground truth mới thay vì sửa nhãn cũ để làm cho kiểm thử pass.
- Lưu cấu hình profile, seed và báo cáo kiểm định cùng artifact dữ liệu.

## 12. Kết quả mong đợi

Kết quả cuối cùng là một bộ dữ liệu có quy mô gần doanh nghiệp thật, có lịch sử đủ dài, các phân phối nghiệp vụ hợp lý và những tình huống khó có thể truy vết, đồng thời vẫn tương thích với hệ thống Text-to-SQL hiện tại.
