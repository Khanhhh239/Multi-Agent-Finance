# Giao việc R3: viết kịch bản gian lận nội bộ cho tập niêm phong v5

Người nhận: một phiên agent **tách biệt** (hoặc một kiểm toán viên). Chỉ được đọc tệp này và các nguồn công khai nêu ở mục 3. **Không được đọc** thư mục `agent2/`, `docs/04_*`, `results/`, báo cáo hậu kiểm, hay bất kỳ số đo mô hình nào. Ghi rõ ở đầu bản nộp: "Tôi xác nhận chưa đọc mã, kết quả hay tài liệu phương pháp."

## 1. Bối cảnh (đủ để viết, không hơn)
Một công cụ đọc sổ giao dịch của doanh nghiệp nhỏ và vừa Việt Nam (10 đến 80 nhân sự) và đưa ra vài câu hỏi rà soát mỗi tuần. Dữ liệu là sổ giao dịch tổng hợp gồm các bảng:
- **công ty**: ngành, quy mô, ngày trả lương, kỳ hạn công nợ;
- **nhân viên**: vai trò, ngày vào, ngày nghỉ, lương, tài khoản ngân hàng, điện thoại, địa chỉ;
- **nhà cung cấp**: ngày đăng ký, tài khoản, người đại diện;
- **khách hàng**: tài khoản, hạn nợ;
- **giao dịch**, mỗi dòng có:
  - thời điểm tạo, duyệt, ghi sổ;
  - loại nghiệp vụ (lương, thanh toán nhà cung cấp, chi tiền mặt, hóa đơn bán, thu tiền, trả hàng, hoàn tiền, xóa nợ, hủy hàng, rút tiền về quỹ, nộp thuế, thuê nhà, tạm ứng, quyết toán tạm ứng, điều chỉnh, khấu hao, mua hàng...);
  - số tiền, cặp tài khoản Nợ và Có;
  - người lập, người duyệt;
  - đối tượng (nhà cung cấp, khách hàng hoặc nhân viên);
  - tài khoản nhận và tài khoản trả;
  - số hóa đơn, số chứng từ kèm theo, đơn giá và số lượng;
- **thay đổi tài khoản nhà cung cấp**, **tạm ứng**.

## 2. Việc cần làm
Viết **8 đến 10 kịch bản gian lận nội bộ** có thể xảy ra ở doanh nghiệp nhỏ Việt Nam, mỗi kịch bản theo phiếu 11 mục trong `README.md` cùng thư mục, kèm **hai tình huống hợp lệ trông giống** cho mỗi kịch bản.

Yêu cầu:
- Mỗi kịch bản phải thể hiện được **chỉ bằng các bảng ở mục 1** (nếu cần dữ liệu khác, ghi ở mục 10 của phiếu).
- Có ba mức che giấu: dễ, vừa, khó. Mức khó phải giống hoạt động bình thường đến mức một kế toán trưởng có kinh nghiệm cũng khó nhận ra nếu chỉ đọc từng dòng.
- Nêu quy mô tiền và thời gian kéo dài thực tế, có nguồn hoặc lý do.
- Đa dạng nhánh theo cây gian lận ACFE: biển thủ tiền mặt và tiền thu, thanh toán gian lận (hóa đơn, chi phí, lương, sửa lệnh chi), tài sản không phải tiền, tham nhũng (xung đột lợi ích, hối lộ), báo cáo tài chính.
- **Không trùng ý tưởng** với danh sách đã dùng dưới đây. Một biến thể chỉ đổi tên không được tính là mới.

Danh sách đã dùng (chỉ để tránh trùng; đây không phải gợi ý): nhà cung cấp ma; mua hóa đơn của doanh nghiệp ma; chi thêm sau ký duyệt; mua đồ cá nhân; thanh toán trùng; sửa người nhận trên lệnh chi; đổi tài khoản nhà cung cấp tạm thời; chia nhỏ khoản chi; loạt chi buổi tối; nhân sự ma; nâng lương một người; nghỉ việc vẫn nhận lương; danh sách thưởng khống; chi lương ngoài kỳ; chứng từ tiếp khách khống; chi tiền mặt sát hạn mức tự duyệt; nộp trùng chứng từ chi phí; tạm ứng không hoàn; gối đầu công nợ; bán không ghi doanh thu khai hàng hỏng; trả hàng và hoàn tiền khống; thủ quỹ rút quỹ với chứng từ khống; thủ kho xuất khống; nâng giá mua nhận lại quả; tăng giá dần; quân xanh quân đỏ; nhà cung cấp sân sau; bút toán tay cuối kỳ; doanh thu khống cuối quý rồi đảo; giám đốc tự duyệt tạm ứng lớn; hóa đơn bán khống cho đại lý thật; bán giá thấp nhận lại quả; rút tiền về quỹ ngoài kế hoạch; tạm ứng xoay vòng; nâng lương cả nhóm; thuê kho khống; nộp thuế khống.

## 3. Nguồn được phép dùng
- ACFE, *Occupational Fraud 2024: A Report to the Nations* (cây gian lận, tỷ lệ theo quy mô, thời gian kéo dài, cách che giấu).
- Báo chí và bản án Việt Nam công khai về gian lận trong doanh nghiệp (ghi đường dẫn; ẩn tên người).
- Hiểu biết nghiệp vụ kế toán Việt Nam (Thông tư 133, 200; hóa đơn điện tử; thanh toán không tiền mặt từ 20 triệu đồng).

## 4. Nộp bài
Một tệp `scenarios_v5.md` gồm:
- dòng xác nhận độc lập;
- 8 đến 10 phiếu kịch bản;
- với mỗi kịch bản, 10 dòng giao dịch mẫu dạng bảng (dữ liệu bịa, không có thông tin người thật), dùng để duyệt sau khi mã hóa.

Không đánh giá hay đoán xem công cụ có bắt được kịch bản hay không.
