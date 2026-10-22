Tôi xác nhận chưa đọc mã, kết quả hay tài liệu phương pháp; chỉ đọc brief_v5.md, README.md và nguồn công khai đã dẫn.

# Kịch bản gian lận nội bộ cho tập niêm phong v5

## Thông tin chung

- Ngày soạn: 22/10/2026.
- Người viết: một phiên agent tách biệt (mô hình ngôn ngữ) đóng vai người viết kịch bản độc lập theo brief_v5.md. Người viết không phải kiểm toán viên hay kế toán trưởng con người. Việc có gắn nhãn "độc lập" cho bộ kịch bản này hay không do quy trình tiếp nhận quyết định; người viết đề nghị một kế toán trưởng có kinh nghiệm đọc lại các phiếu trước khi khóa.
- Phạm vi đọc: chỉ brief_v5.md, README.md trong thư mục independent_scenarios và các nguồn công khai liệt kê ở cuối tệp. Không đọc mã, kết quả, bảng sai sót, tài liệu phương pháp hay dữ liệu của dự án.
- Số kịch bản: 10. Mỗi kịch bản theo phiếu 11 mục của README.md, có ba mức che giấu (dễ, vừa, khó), hai tình huống hợp lệ trông giống và 10 dòng giao dịch mẫu bịa đặt.
- Thông tin định danh: mọi mã nhân viên, khách hàng, nhà cung cấp, số tài khoản, số hóa đơn, biển số xe đều là mã giả. Tên người trong các vụ việc báo chí được lược bỏ.

### Quy ước dữ liệu dùng trong các phiếu

- Chỉ dùng các bảng ở mục 1 của brief: công ty, nhân viên, nhà cung cấp, khách hàng, giao dịch, thay đổi tài khoản nhà cung cấp, tạm ứng. Mọi dữ liệu ngoài các bảng này được ghi ở mục 10 của từng phiếu.
- Hệ thống tài khoản theo Thông tư 133/2016/TT-BTC (chế độ kế toán doanh nghiệp nhỏ và vừa): 111 tiền mặt, 112 tiền gửi ngân hàng, 131 phải thu khách hàng, 141 tạm ứng, 152 nguyên vật liệu, 154 chi phí sản xuất dở dang, 156 hàng hóa, 1331 thuế GTGT được khấu trừ, 211 tài sản cố định, 214 hao mòn, 2293 dự phòng phải thu khó đòi, 331 phải trả người bán, 3331 thuế GTGT đầu ra, 3335 thuế thu nhập cá nhân, 334 phải trả người lao động, 511 doanh thu, 515 doanh thu tài chính, 632 giá vốn, 635 chi phí tài chính, 6421 chi phí bán hàng, 6422 chi phí quản lý doanh nghiệp, 711 thu nhập khác, 811 chi phí khác.
- Thuế suất GTGT trong dòng mẫu là giả định minh họa (10 phần trăm, riêng phiếu KB10 dùng 5 phần trăm); bộ sinh có thể thay bằng thuế suất đúng theo mặt hàng.
- Mã tài khoản ngân hàng: TKCT-01 là tài khoản của công ty; TKNV-xx là tài khoản của nhân viên xx trong bảng nhân viên; TKNCC-xx, TKKH-xx là tài khoản trong bảng nhà cung cấp, khách hàng; TKX-xx là tài khoản không có trong bất kỳ bảng nào.
- Số hóa đơn điện tử dạng "1C25TAA-0000412": ký hiệu gồm năm lập hóa đơn (25 là năm 2025) theo Nghị định 123/2020/NĐ-CP, sau dấu gạch là số thứ tự.
- Cột trong bảng 10 dòng mẫu:
  - "Tạo", "Duyệt", "Ghi sổ": ba thời điểm của dòng giao dịch.
  - "Loại nghiệp vụ": giá trị nằm ngoài ngoặc là loại trong danh sách của brief; phần trong ngoặc chỉ là diễn giải cho người duyệt.
  - "Nợ / Có": cặp tài khoản; khi một vế có nhiều tài khoản thì ghi số tiền từng tài khoản.
  - "Chứng từ kèm (mô tả)": brief chỉ có trường "số chứng từ kèm theo". Phần mô tả trong cột này giúp người duyệt hiểu bối cảnh, **không phải trường dữ liệu**. Nội dung nào cần đưa vào dữ liệu thì đã được ghi ở mục 10.
  - "Đơn giá; SL": đơn giá và số lượng trên dòng giao dịch.
  - "Vai trò dòng": nhãn để người duyệt, không thuộc dữ liệu. GL-dễ, GL-vừa, GL-khó là dòng gian lận theo mức; HL1, HL2 là dòng của tình huống hợp lệ trông giống; Nền là dòng bình thường cần có để hiểu dòng gian lận.

### Số liệu ACFE 2024 dùng làm căn cứ quy mô

Theo *Occupational Fraud 2024: A Report to the Nations* (ACFE), qua các bản tóm tắt công khai dẫn ở cuối tệp:

- 1.921 vụ ở 138 quốc gia, điều tra từ tháng 01/2022 đến tháng 9/2023; tổn thất trung vị 145.000 USD; thời gian kéo dài trung vị 12 tháng; tổ chức ước mất 5 phần trăm doanh thu mỗi năm.
- Tổ chức dưới 100 nhân sự: tổn thất trung vị 141.000 USD; kiểm soát nội bộ yếu phổ biến hơn.
- Biển thủ tài sản: 89 phần trăm số vụ, trung vị 120.000 USD. Trong đó gian lận hóa đơn 22 phần trăm số vụ, trung vị 100.000 USD, kéo dài trung vị 18 tháng; biển thủ tài sản không phải tiền 22 phần trăm, trung vị 66.000 USD, kéo dài 12 tháng.
- Tham nhũng: 48 phần trăm số vụ, trung vị 200.000 USD, kéo dài khoảng 13 tháng.
- Gian lận báo cáo tài chính: 5 phần trăm số vụ, trung vị 766.000 USD.
- Theo cấp bậc người thực hiện: nhân viên 60.000 USD, quản lý 184.000 USD, chủ sở hữu hoặc lãnh đạo 500.000 USD (một bản tóm tắt khác ghi 459.000 USD).
- 89 phần trăm vụ có hành vi che giấu; phổ biến nhất là tạo hoặc sửa chứng từ giấy (41 phần trăm), tạo chứng từ điện tử (31 phần trăm), sửa chứng từ điện tử (28 phần trăm), hủy hoặc giữ lại chứng từ (23 phần trăm).
- Phát hiện qua tố giác 43 phần trăm; hơn một nửa số vụ gắn với thiếu kiểm soát hoặc lãnh đạo vượt quyền kiểm soát.

Quy đổi tham khảo theo tỷ giá giả định 25.000 đồng/USD: 141.000 USD tương đương khoảng 3,5 tỷ đồng. Doanh nghiệp mục tiêu của bộ kịch bản có 10 đến 80 nhân sự, doanh thu vài chục tỷ đồng, nên quy mô trong các phiếu được đặt thấp hơn trung vị ACFE và bám theo các vụ việc Việt Nam đã dẫn (phổ biến từ vài trăm triệu đến vài tỷ đồng).

## Danh mục kịch bản

| Mã | Tên kịch bản | Nhánh ACFE |
|---|---|---|
| V5-KB01 | Thu tiền công nợ ngoài sổ, che bằng giảm giá, chiết khấu và xóa nợ | Biển thủ tiền thu: skimming khoản phải thu, che bằng ghi giảm và xóa sổ |
| V5-KB02 | Chặn tiền hoàn cọc của nhà cung cấp khi đơn hàng bị hủy hoặc giảm | Biển thủ tiền thu: skimming khoản thu ngoài bán hàng (tiền hoàn từ nhà cung cấp) |
| V5-KB03 | Kê tăng ngày và quãng đường trong quyết toán công tác phí | Thanh toán gian lận: hoàn ứng chi phí, dạng kê tăng |
| V5-KB04 | Kê tăng trợ cấp thôi việc và đổi lý do chấm dứt hợp đồng | Thanh toán gian lận: lương, dạng khai sai khoản chi khi chấm dứt hợp đồng |
| V5-KB05 | Gắn khách hàng sẵn có cho cộng tác viên để chi hoa hồng giới thiệu | Thanh toán gian lận: khoản chi cho bên ngoài dựa trên căn cứ sai (hoa hồng), có yếu tố xung đột lợi ích |
| V5-KB06 | Thanh lý tài sản cố định còn giá trị cho người mua có quan hệ | Tài sản không phải tiền: chiếm đoạt qua chuyển giao và bán thanh lý giả |
| V5-KB07 | Dùng xe tải của công ty chở hàng thuê ngoài sổ | Tài sản không phải tiền: sử dụng sai mục đích |
| V5-KB08 | Đòi "phí" nhà cung cấp để được thanh toán đúng hạn | Tham nhũng: hối lộ, dạng tống tiền kinh tế |
| V5-KB09 | Dời ghi nhận chi phí và nợ phải trả cuối năm để đạt điều kiện tín dụng | Báo cáo tài chính: khai tăng lợi nhuận bằng che giấu chi phí và nợ phải trả (chênh lệch thời điểm) |
| V5-KB10 | Nới hạn nợ và tiếp tục bán chịu cho khách hàng có quan hệ với người duyệt tín dụng | Tham nhũng: xung đột lợi ích, dạng bán hàng |

Ghi chú về phân biệt với danh sách "đã dùng" trong brief:

- KB01 không phải "gối đầu công nợ" (không dùng tiền của khách khác để bù), không phải "trả hàng và hoàn tiền khống" (không có trả hàng, không có tiền chi ra), không phải "bán không ghi doanh thu" (doanh thu được ghi đầy đủ).
- KB02 không phải "thanh toán trùng", "đổi tài khoản nhà cung cấp tạm thời" hay "sửa người nhận": khoản tiền đi ra là đúng, đúng tài khoản nhà cung cấp; khoản bị chiếm là tiền đi vào.
- KB04 không phải "nghỉ việc vẫn nhận lương" hay "chi lương ngoài kỳ": trợ cấp thôi việc vốn được chi khi chấm dứt hợp đồng theo luật; điểm sai là điều kiện hưởng, căn cứ tính và lý do chấm dứt.
- KB05 không phải "nhà cung cấp ma" hay "danh sách thưởng khống": cộng tác viên là người thật, khách hàng và doanh thu là thật; chỉ việc ghi công giới thiệu là sai.
- KB06 không phải "bán giá thấp nhận lại quả": đối tượng là tài sản cố định, thủ đoạn là khai sai tình trạng và giá trị tài sản để thanh lý.
- KB09 không phải "bút toán tay cuối kỳ" hay "doanh thu khống cuối quý": không tạo bút toán mới, mà trì hoãn hoặc bỏ sót ghi nhận chi phí và nợ phải trả có thật.
- KB10 không phải "bán giá thấp nhận lại quả": giá bán đúng bảng giá; lợi ích nằm ở điều khoản tín dụng.

---

## V5-KB01. Thu tiền công nợ ngoài sổ, che bằng giảm giá, chiết khấu và xóa nợ

**1. Mã, tên và ngày soạn:** V5-KB01; "Thu tiền công nợ ngoài sổ, che bằng giảm giá, chiết khấu và xóa nợ"; 22/10/2026. Nhánh ACFE: biển thủ tiền thu, skimming khoản phải thu, che bằng ghi giảm và xóa sổ.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Báo Pháp luật Việt Nam: hai nhân viên kinh doanh của một công ty thiết bị vệ sinh ở Hà Nội thu tiền công nợ nhưng không nộp; một người năm 2018 thu hơn 1,5 tỷ đồng tại 18 cửa hàng, chỉ nộp 90 triệu đồng; do không có giấy nhận tiền, cơ quan điều tra chỉ kết luận được gần 1 tỷ đồng từ 4 khách hàng.
- Báo Văn hóa: nhân viên nhận tiền để chuyển về công ty nhưng chỉ nộp một phần, giữ lại hơn 975 triệu đồng, đồng thời tự thu tiền của khách khi không được giao việc thu.
- ACFE: nhánh skimming khoản phải thu, thủ đoạn che bằng ghi giảm và xóa nợ.
- Thông tư 48/2019/TT-BTC về trích lập dự phòng và xử lý nợ phải thu khó đòi (mức trích 30, 50, 70, 100 phần trăm theo tuổi nợ quá hạn từ 6 tháng, 1 năm, 2 năm, 3 năm).

**Bối cảnh doanh nghiệp (giả định):** phân phối thiết bị vệ sinh và gạch ốp lát cho khoảng 150 cửa hàng bán lẻ ở 4 tỉnh; 35 nhân sự; doanh thu 55 đến 70 tỷ đồng mỗi năm; kỳ hạn công nợ khách hàng 30 ngày; trả lương ngày 05.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện chính: nhân viên kinh doanh tuyến (NV12), được giao thu tiền mặt công nợ tại cửa hàng (thực tế phổ biến với cửa hàng nhỏ ở tỉnh), tự đối chiếu công nợ với khách, được đề xuất giảm giá và gia hạn.
- Người lập điều chỉnh: kế toán công nợ (NV05). Người duyệt: kế toán trưởng (NV02) với điều chỉnh nhỏ, giám đốc (NV01) với xóa nợ và giảm giá.
- Mức dễ và vừa: không thông đồng; NV05 lập điều chỉnh theo đề nghị có chữ ký của NV12. Mức khó: NV12 thông đồng với NV05, người kiểm soát việc gửi và nhận thư xác nhận công nợ.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: chiếm tiền khách đã trả cho công ty.
- Bước 1 (tháng 0): NV12 thu tiền mặt của khách cho một hóa đơn cũ, ký biên nhận viết tay hoặc không ký, không nộp quỹ. Số dư phải thu của khách trên sổ giữ nguyên. Các lần trả sau của khách được NV12 nộp đúng để quan hệ bình thường.
- Bước 2 (tháng 1 đến 3): khi hóa đơn cũ quá hạn, NV12 báo khách "khó khăn, xin khất".
- Bước 3, tùy mức che giấu: đề nghị giảm giá hàng bán với lý do lỗi chất lượng; hoặc chiết khấu thanh toán; hoặc chuyển nợ sang một khách đã ngừng kinh doanh rồi xóa nợ; hoặc đề nghị xóa nợ trực tiếp.
- Bước 4 (tháng 9 đến 14): xóa nợ phần còn lại trước kỳ kiểm toán hoặc trước khi gửi thư xác nhận công nợ cuối năm.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: thiếu dòng "thu tiền" (Nợ 111 hoặc 112, Có 131) cho khoản khách đã trả. Có thêm dòng "điều chỉnh" giảm giá (Nợ 511, 3331 / Có 131, kèm số hóa đơn điều chỉnh giảm), "điều chỉnh" chiết khấu thanh toán (Nợ 635 / Có 131), "điều chỉnh" cấn trừ công nợ giữa hai khách (Nợ 131 khách A / Có 131 khách B), "xóa nợ" (Nợ 2293 hoặc 6422 / Có 131).
- Bảng khách hàng: hạn nợ có thể bị nâng từ 30 lên 60 đến 90 ngày cho khách bị chiếm tiền.
- Thời điểm quan sát: việc thu tiền thật không bao giờ xuất hiện trong sổ. Các dòng ghi giảm xuất hiện 20 đến 120 ngày sau hóa đơn gốc; xóa nợ xuất hiện 6 đến 14 tháng sau lần thu đầu; cấn trừ thường được đặt vào tháng cuối quý hoặc cuối năm.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 4 đến 9 khách hàng; 15 đến 40 lần thu ngoài sổ; mỗi lần 8 đến 60 triệu đồng (giá trị một hóa đơn của cửa hàng nhỏ); tổng 300 triệu đến 1,5 tỷ đồng; kéo dài 10 đến 20 tháng.
- Lý do: vụ báo Pháp luật cho thấy khoảng 1,5 tỷ đồng từ 18 cửa hàng trong một năm là khả thi với một nhân viên; ACFE cho thời gian kéo dài trung vị 12 tháng. Với doanh thu 60 tỷ đồng, 1,5 tỷ đồng bằng 2,5 phần trăm doanh thu, nằm dưới mức 5 phần trăm mà ACFE ước cho mọi loại gian lận, nên được dùng làm cận trên.
- Tổn thất: tổng tiền khách xác nhận đã trả (biên nhận, sao kê của khách) mà không có dòng thu tương ứng; đối chiếu với tổng các khoản giảm giá, chiết khấu, cấn trừ và xóa nợ không có căn cứ; trừ phần đã bồi hoàn.

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** một khách, 3 đến 5 lần thu, tổng 120 đến 250 triệu đồng. Không che trong 6 đến 9 tháng; sau đó NV12 trình đề nghị xóa nợ "cửa hàng đã đóng cửa", không có hồ sơ giải thể và không có dự phòng trích trước. Sổ vẫn có hóa đơn bán mới cho chính khách đó trước và sau ngày xóa nợ.
- **Vừa:** 3 đến 5 khách. Mỗi hóa đơn cũ bị chiếm tiền được giảm giá 5 đến 12 phần trăm (5 đến 25 triệu đồng mỗi lần) với lý do "lỗi men, khách khiếu nại"; có biên bản điều chỉnh có chữ ký khách (khách không thiệt nên sẵn sàng ký). Giảm giá chỉ tập trung ở khách do NV12 phụ trách; không có giảm giá hay trả hàng tương ứng với nhà cung cấp cho cùng mặt hàng.
- **Khó:** 6 đến 9 khách, có thông đồng với NV05. Che bằng hỗn hợp: (a) chiết khấu thanh toán đúng tỷ lệ chính sách 1 đến 2 phần trăm cho các khoản thực tế trả muộn; (b) cấn trừ chuyển phần còn lại sang một khách đã ngừng kinh doanh thật (thường là cửa hàng của người thân của chủ cửa hàng đang hoạt động) bằng "biên bản thỏa thuận ba bên"; (c) xóa nợ khách đã ngừng kinh doanh với hồ sơ đóng mã số thuế thật. Tổng xóa nợ không vượt mức dự phòng đã trích theo tuổi nợ. Thư xác nhận công nợ do NV05 gửi và nhận. Từng dòng đều có chứng từ và đúng chính sách.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, xóa nợ thật:** khách đã giải thể hoặc phá sản; dự phòng đã trích theo tuổi nợ; khách ngừng mua hàng trước khi quá hạn; không có khoản tiền nào khách xác nhận đã trả mà thiếu trên sổ. Bằng chứng phân biệt: giao dịch cuối với khách diễn ra trước thời điểm quá hạn; không có hóa đơn mới sau khi quá hạn 90 ngày; hồ sơ giải thể hoặc phá sản.
- **HL2, giảm giá do lỗi lô hàng của nhà cung cấp:** nhiều khách của nhiều nhân viên kinh doanh khác nhau được giảm giá cùng mặt hàng trong cùng 2 đến 6 tuần; có điều chỉnh giảm giá mua vào hoặc trả hàng với nhà cung cấp cho cùng lô; tỷ lệ giảm giá đồng đều.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Brief không có trường "nhân viên phụ trách khách hàng". Đề nghị quy ước "người lập" của hóa đơn bán là nhân viên kinh doanh phụ trách, hoặc bổ sung trường này vào bảng khách hàng. Cần hỏi lại.
- Biến thể vừa và HL2 cần mã mặt hàng hoặc mã lô trên dòng giao dịch; bảng hiện chỉ có đơn giá và số lượng.
- Bảng khách hàng chỉ có hạn nợ hiện hành, không có lịch sử thay đổi.
- Trạng thái khách (đang hoạt động, đã giải thể, ngày giải thể) cần cho HL1 và mức khó; brief không có trường này.
- Khoản tiền khách đã trả cho NV12 nằm ngoài sổ; nhãn tổn thất phải được sinh trong bảng nhãn riêng, không đưa vào dữ liệu giao dịch.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Khoản bị chiếm không có dòng "thu tiền" nào; các dòng ghi giảm có người lập là kế toán công nợ, người duyệt đúng cấp.
- Cặp tài khoản đúng Thông tư 133 (giảm giá ghi giảm trực tiếp 511; chiết khấu thanh toán vào 635; xóa nợ đã có dự phòng qua 2293).
- Số học khớp: đơn giá nhân số lượng cộng thuế bằng số tiền; tổng xóa nợ ở mức khó bằng nợ thật cộng phần cấn trừ.
- Thời gian hợp lý: giảm giá sau hóa đơn gốc 20 đến 120 ngày; xóa nợ sau ít nhất 6 tháng quá hạn ở mức khó.
- Dòng HL có đủ dấu hiệu phân biệt nêu ở mục 9; dòng dễ thể hiện được hóa đơn mới sau xóa nợ.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV02 kế toán trưởng; NV05 kế toán công nợ; NV12 nhân viên kinh doanh (người thực hiện); NV14 nhân viên kinh doanh khác; KH031, KH047, KH058 khách bị chiếm tiền; KH052 khách đã ngừng kinh doanh thật; KH063, KH070 khách khác; NCC08 nhà cung cấp gạch men.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-02-10 09:20 | 2025-02-10 10:05 | 2025-02-10 | Hóa đơn bán | 48.400.000 | 131 / 511 44.000.000, 3331 4.400.000 | NV12 | NV02 | KH031 | — | — | 1C25TAA-0000412 | Đơn đặt hàng ĐH-0210; khách đã trả tiền mặt cho NV12 ngày 12/03/2025, không có dòng thu | 1.100.000; 40 | Nền |
| 2 | 2025-05-22 14:10 | 2025-05-30 17:45 | 2025-05-30 | Điều chỉnh (giảm giá hàng bán) | 5.808.000 | 511 5.280.000, 3331 528.000 / 131 | NV05 | NV01 | KH031 | — | — | 1C25TAA-0000655 (điều chỉnh giảm cho 0000412) | Biên bản điều chỉnh BB-0522 có chữ ký khách; đề nghị của NV12 "lỗi men" | 132.000; 40 | GL-vừa |
| 3 | 2025-11-14 10:30 | 2025-11-14 16:20 | 2025-11-14 | Xóa nợ | 176.000.000 | 6422 / 131 | NV05 | NV01 | KH058 | — | — | — | Tờ trình của NV12 "cửa hàng đã đóng cửa"; không có hồ sơ giải thể; chưa từng trích dự phòng | — | GL-dễ |
| 4 | 2025-11-27 08:50 | 2025-11-27 09:30 | 2025-11-27 | Hóa đơn bán | 22.000.000 | 131 / 511 20.000.000, 3331 2.000.000 | NV12 | NV02 | KH058 | — | — | 1C25TAA-0001187 | Đơn đặt hàng ĐH-1127, 13 ngày sau khi KH058 bị xóa nợ | 500.000; 40 | GL-dễ |
| 5 | 2025-06-30 16:00 | 2025-06-30 17:10 | 2025-06-30 | Điều chỉnh (chiết khấu thanh toán) | 1.320.000 | 635 / 131 | NV05 | NV02 | KH047 | — | — | — | Bảng tính chiết khấu quý II: 2 phần trăm cho HĐ 1C25TAA-0000530 trị giá 66.000.000 "trả trong 10 ngày"; khách thực tế trả cho NV12 sau 45 ngày | — | GL-khó |
| 6 | 2025-09-29 15:20 | 2025-09-30 08:40 | 2025-09-30 | Điều chỉnh (cấn trừ công nợ) | 86.500.000 | 131 (KH052) / 131 (KH047) | NV05 | NV02 | KH047, KH052 | — | — | — | Biên bản thỏa thuận ba bên TT-0929 "KH052 nhận nợ thay KH047" | — | GL-khó |
| 7 | 2025-12-26 10:00 | 2025-12-29 11:15 | 2025-12-31 | Xóa nợ | 112.300.000 | 2293 / 131 | NV05 | NV01 | KH052 | — | — | — | Quyết định xóa nợ XN-12/2025; thông báo đóng mã số thuế của KH052; gồm 25.800.000 nợ thật và 86.500.000 chuyển từ KH047 | — | GL-khó |
| 8 | 2025-12-26 10:05 | 2025-12-29 11:15 | 2025-12-31 | Xóa nợ | 41.250.000 | 2293 / 131 | NV05 | NV01 | KH070 | — | — | — | Hồ sơ phá sản; dự phòng 100 phần trăm từ 09/2025; giao dịch cuối với KH070 tháng 6/2023 | — | HL1 |
| 9 | 2025-08-12 09:40 | 2025-08-12 15:00 | 2025-08-12 | Điều chỉnh (giảm giá hàng bán) | 3.960.000 | 511 3.600.000, 3331 360.000 / 131 | NV05 | NV01 | KH063 (do NV14 phụ trách) | — | — | 1C25TAA-0000931 | Biên bản BB-0812: lỗi men lô L2507 của NCC08; cùng tuần có 6 khách của 3 nhân viên được giảm giá cùng lô | 90.000; 40 | HL2 |
| 10 | 2025-08-14 10:10 | 2025-08-14 16:30 | 2025-08-14 | Điều chỉnh (giảm giá hàng mua) | 18.700.000 | 331 / 156 17.000.000, 1331 1.700.000 | NV05 | NV02 | NCC08 | — | — | 1C25TNC-0002216 (điều chỉnh giảm của NCC08) | Biên bản với NCC08 về lô L2507 | 85.000; 200 | HL2 |

---

## V5-KB02. Chặn tiền hoàn cọc của nhà cung cấp khi đơn hàng bị hủy hoặc giảm

**1. Mã, tên và ngày soạn:** V5-KB02; "Chặn tiền hoàn cọc của nhà cung cấp khi đơn hàng bị hủy hoặc giảm"; 22/10/2026. Nhánh ACFE: biển thủ tiền thu, skimming khoản thu ngoài bán hàng; gần với dạng "trả rồi đòi lại" (pay and return) của nhánh hóa đơn với nhà cung cấp không thông đồng.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- ACFE: nhánh skimming và dạng "pay and return" trong nhánh hóa đơn với nhà cung cấp không thông đồng.
- Tuổi Trẻ: một kế toán tự ý chuyển 2,9 tỷ đồng của công ty vào tài khoản người thân rồi yêu cầu chuyển lại vào tài khoản cá nhân để chiếm đoạt; minh họa việc dùng tài khoản người thân làm trung gian cho dòng tiền ngoài sổ.
- Hiểu biết nghiệp vụ: hợp đồng mua khuôn mẫu, máy móc, nguyên liệu theo lô ở doanh nghiệp sản xuất nhỏ thường yêu cầu đặt cọc 20 đến 50 phần trăm; khi đơn hàng hủy hoặc giảm, việc hoàn cọc được thỏa thuận qua điện thoại và công văn, ít khi có bên thứ ba kiểm tra.

**Bối cảnh doanh nghiệp (giả định):** sản xuất bao bì nhựa, 60 nhân sự, doanh thu 80 đến 120 tỷ đồng mỗi năm; mua hạt nhựa, khuôn mẫu, phụ tùng máy; kỳ hạn công nợ nhà cung cấp 45 ngày.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện chính: trưởng phòng mua hàng (NV09), đầu mối liên lạc với nhà cung cấp, có quyền đề xuất hủy hoặc giảm đơn và soạn công văn gửi nhà cung cấp.
- Kế toán thanh toán (NV04) lập lệnh chi và điều chỉnh; kế toán trưởng (NV03) và giám đốc (NV01) duyệt.
- Mức dễ và vừa: NV09 làm một mình, lợi dụng việc giám đốc ký hàng loạt công văn. Mức khó: NV09 thông đồng với NV04 để ghi nhận quyết toán hợp đồng theo số liệu sai.
- Nhà cung cấp không thông đồng; họ hoàn tiền theo công văn có vẻ hợp lệ.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: chiếm tiền cọc mà nhà cung cấp hoàn lại.
- Bước 1 (tháng 0): công ty chuyển cọc hợp lệ, đúng tài khoản nhà cung cấp.
- Bước 2 (tháng 1 đến 3): đơn hàng bị hủy hoặc giảm số lượng, với lý do thật (khách của công ty hủy đơn) hoặc do NV09 tạo ra (chê mẫu thử).
- Bước 3: NV09 gửi nhà cung cấp công văn "đề nghị hoàn tiền vào tài khoản..." là tài khoản người thân, hoặc nhận tiền mặt kèm giấy ủy quyền.
- Bước 4: khoản ứng trước treo trên tài khoản 331 (dư Nợ) của nhà cung cấp.
- Bước 5 (cuối quý hoặc cuối năm): khoản treo được chuyển vào chi phí khác với lý do "mất cọc" hoặc "phí hủy, giảm đơn", dựa trên biên bản thanh lý hợp đồng giả hoặc tờ trình nội bộ.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: dòng "thanh toán nhà cung cấp" ứng trước (Nợ 331 / Có 112, không có số hóa đơn) là thật; thiếu dòng nhận tiền hoàn từ nhà cung cấp (Nợ 112 / Có 331); có thêm dòng "điều chỉnh" Nợ 811 / Có 331.
- Bảng nhà cung cấp và bảng thay đổi tài khoản nhà cung cấp: không thay đổi, vì tiền chi ra đi đúng tài khoản đã đăng ký.
- Thời điểm quan sát: khoản hoàn tiền thật không xuất hiện. Dấu vết trên sổ là khoản ứng trước treo 2 đến 12 tháng rồi bị ghi vào chi phí; nhà cung cấp vẫn tiếp tục giao hàng và được thanh toán bình thường sau khi được ghi là "giữ cọc".

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 2 đến 6 lần trong 12 đến 24 tháng; mỗi lần 40 đến 350 triệu đồng (cọc 30 phần trăm của đơn 150 triệu đến 1,2 tỷ đồng); tổng 150 đến 900 triệu đồng.
- Lý do: hủy hoặc giảm đơn có cọc chỉ xảy ra vài lần mỗi năm ở doanh nghiệp quy mô này, nên số lần ít; ACFE cho nhánh hóa đơn trung vị 100.000 USD và 18 tháng, phù hợp cận trên khi quy đổi về doanh nghiệp nhỏ.
- Tổn thất: tổng tiền nhà cung cấp đã hoàn (theo xác nhận và sao kê của nhà cung cấp) không về tài khoản công ty; cộng phần phí phạt ghi nhận vượt mức thực tế.

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** một nhà cung cấp, cọc 120 triệu đồng, nhà cung cấp hoàn tiền mặt cho NV09 theo giấy ủy quyền. Khoản ứng trước treo 11 tháng không đối trừ; cuối năm kế toán chuyển vào 811 theo tờ trình "nhà cung cấp không hoàn cọc", không có biên bản của nhà cung cấp.
- **Vừa:** 2 đến 3 nhà cung cấp. Mỗi lần có "biên bản thanh lý hợp đồng" (giả) ghi "bên mua chịu mất toàn bộ cọc"; điều chỉnh 811 được lập trong 30 đến 60 ngày sau khi hủy; nhà cung cấp tiếp tục giao hàng và được thanh toán bình thường sau đó.
- **Khó:** có thông đồng với NV04. Đơn hàng không hủy mà giảm số lượng: cọc 300 triệu đồng cho đơn 1 tỷ đồng, đơn còn 200 triệu đồng; nhà cung cấp thu phí 5 phần trăm phần hủy (40 triệu đồng) và hoàn 40 triệu đồng vào tài khoản ngoài. Trên sổ, cọc được đối trừ bằng hóa đơn 220 triệu đồng (gồm thuế), phần còn lại 80 triệu đồng ghi là "phí giảm số lượng 10 phần trăm" theo phụ lục giả. Số dư 331 về 0, mức phí nằm trong khoảng thường gặp, từng dòng đều có chứng từ.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, mất cọc thật:** công ty chủ động hủy đơn vì khách của công ty hủy; hợp đồng có điều khoản phạt; biên bản thanh lý có chữ ký và dấu của nhà cung cấp; mức mất cọc đúng điều khoản; thư xác nhận công nợ cuối năm của nhà cung cấp ghi đã giữ cọc. Bằng chứng phân biệt: tỷ lệ phạt khớp hợp đồng; người duyệt là giám đốc tại thời điểm hủy; xác nhận độc lập của nhà cung cấp.
- **HL2, ứng trước được tất toán đúng:** ứng trước cho máy hoặc khuôn có thời gian sản xuất dài (3 đến 9 tháng), sau đó được đối trừ bằng hóa đơn mua; hoặc cọc được hoàn về tài khoản công ty (có dòng "thu tiền" với đối tượng là nhà cung cấp, tài khoản trả là tài khoản nhà cung cấp).

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Không có trường "số hợp đồng hoặc đơn đặt hàng" để nối khoản ứng trước với hóa đơn đối trừ; cần bổ sung hoặc quy ước nối qua đối tượng và thứ tự thời gian.
- Cần xác nhận loại nghiệp vụ dùng cho tiền nhận từ nhà cung cấp: "thu tiền" với đối tượng nhà cung cấp, hay "hoàn tiền" theo chiều ngược.
- Khoản phạt hợp đồng không có hóa đơn GTGT; cần quy ước để trống số hóa đơn.
- Điều khoản phạt trong hợp đồng không có trong dữ liệu; bộ sinh cần tham số này để phân biệt HL1.
- Tiền hoàn về tài khoản ngoài nằm ngoài sổ; nhãn tổn thất cần bảng riêng.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Dòng ứng trước đi đúng tài khoản nhà cung cấp đã đăng ký, không có thay đổi tài khoản nhà cung cấp.
- Không có dòng nhận tiền hoàn ở các dòng gian lận; dòng HL2 có dòng nhận tiền hoàn đúng tài khoản công ty.
- Ở mức khó, ứng trước bằng hóa đơn đối trừ cộng phí ghi nhận; số dư 331 về 0.
- Thời gian treo khoản ứng trước khớp mức: dễ khoảng 11 tháng, vừa 1 đến 3 tháng, khó vài ngày sau hóa đơn đối trừ.
- Nhà cung cấp ở mức vừa vẫn phát sinh giao dịch mua bình thường sau khi "giữ cọc".

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV03 kế toán trưởng; NV04 kế toán thanh toán; NV05 kế toán kho; NV09 trưởng phòng mua hàng (người thực hiện); NCC15 khuôn mẫu; NCC21 hạt nhựa; NCC27 máy; NCC30, NCC33 nhà cung cấp khác.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-01-14 09:00 | 2025-01-14 14:30 | 2025-01-14 | Thanh toán nhà cung cấp (ứng trước 30 phần trăm) | 135.000.000 | 331 / 112 | NV04 | NV01 | NCC15 | TKNCC-15 | TKCT-01 | — | Hợp đồng khuôn HĐK-0114 trị giá 450.000.000; đề nghị ứng trước | — | Nền |
| 2 | 2025-04-22 10:15 | 2025-04-25 16:00 | 2025-04-30 | Điều chỉnh (mất cọc) | 135.000.000 | 811 / 331 | NV04 | NV03 | NCC15 | — | — | — | "Biên bản thanh lý HĐK-0114: bên mua chịu mất toàn bộ cọc"; thực tế NCC15 đã hoàn 135.000.000 vào TKX-01 ngày 10/04 | — | GL-vừa |
| 3 | 2025-05-08 08:30 | 2025-05-08 11:00 | 2025-05-08 | Mua hàng | 52.800.000 | 152 48.000.000, 1331 4.800.000 / 331 | NV05 | NV03 | NCC15 | — | — | 1C25TKM-0000377 | Phiếu nhập PN-0508; NCC15 vẫn giao hàng bình thường sau khi được ghi là giữ cọc | 4.800.000; 10 | GL-vừa |
| 4 | 2025-02-03 09:10 | 2025-02-03 15:20 | 2025-02-03 | Thanh toán nhà cung cấp (ứng trước 40 phần trăm) | 120.000.000 | 331 / 112 | NV04 | NV01 | NCC27 | TKNCC-27 | TKCT-01 | — | Đơn đặt máy ĐĐH-0203 trị giá 300.000.000; NCC27 hoàn tiền mặt cho NV09 ngày 17/03 theo giấy ủy quyền | — | Nền |
| 5 | 2025-12-29 16:30 | 2025-12-30 09:00 | 2025-12-31 | Điều chỉnh (mất cọc) | 120.000.000 | 811 / 331 | NV04 | NV01 | NCC27 | — | — | — | Tờ trình của NV09 "NCC27 không hoàn cọc"; không có biên bản của nhà cung cấp; khoản ứng trước treo 11 tháng | — | GL-dễ |
| 6 | 2025-06-10 09:30 | 2025-06-10 15:10 | 2025-06-10 | Thanh toán nhà cung cấp (ứng trước 30 phần trăm) | 300.000.000 | 331 / 112 | NV04 | NV01 | NCC21 | TKNCC-21 | TKCT-01 | — | Hợp đồng hạt nhựa HĐH-0610 trị giá 1.000.000.000 | — | Nền |
| 7 | 2025-08-19 10:00 | 2025-08-19 14:00 | 2025-08-19 | Mua hàng | 220.000.000 | 152 200.000.000, 1331 20.000.000 / 331 | NV05 | NV03 | NCC21 | — | — | 1C25THN-0003318 | Phụ lục 01 giảm số lượng còn 5.000 kg; phiếu nhập PN-0819 | 40.000; 5.000 | GL-khó |
| 8 | 2025-08-20 15:45 | 2025-08-21 09:20 | 2025-08-31 | Điều chỉnh (phí giảm số lượng) | 80.000.000 | 811 / 331 | NV04 | NV03 | NCC21 | — | — | — | "Phụ lục 02: phí 10 phần trăm phần hủy 800.000.000"; thực tế NCC21 thu 5 phần trăm (40.000.000) và hoàn 40.000.000 vào TKX-02 | — | GL-khó |
| 9 | 2025-09-15 10:20 | 2025-09-15 10:20 | 2025-09-15 | Thu tiền (hoàn cọc) | 45.000.000 | 112 / 331 | NV04 | NV03 | NCC30 | TKCT-01 | TKNCC-30 | — | Biên bản thanh lý đơn ĐĐH-0702 có xác nhận của NCC30 | — | HL2 |
| 10 | 2025-10-06 09:00 | 2025-10-06 16:40 | 2025-10-06 | Điều chỉnh (mất cọc) | 60.000.000 | 811 / 331 | NV04 | NV01 | NCC33 | — | — | — | Biên bản thanh lý có chữ ký, dấu của NCC33; điều 7 hợp đồng phạt 20 phần trăm của 300.000.000; quyết định hủy do khách của công ty hủy đơn | — | HL1 |

---

## V5-KB03. Kê tăng ngày và quãng đường trong quyết toán công tác phí

**1. Mã, tên và ngày soạn:** V5-KB03; "Kê tăng ngày và quãng đường trong quyết toán công tác phí"; 22/10/2026. Nhánh ACFE: thanh toán gian lận, hoàn ứng chi phí, dạng kê tăng (overstated expenses).

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Hướng dẫn công khai về quy chế khoán công tác phí trong doanh nghiệp: phụ cấp tính theo số ngày công tác thực tế ghi trên quyết định cử đi, giấy đi đường; khi khoán, người lao động không phải nộp hóa đơn cho phần được khoán nhưng vẫn phải có hồ sơ chứng minh chuyến đi (Thư viện Pháp luật; Kế toán Lê Ánh).
- Thông tư 96/2015/TT-BTC: khoản chi từ 20 triệu đồng phải có chứng từ thanh toán không dùng tiền mặt để được trừ; các khoản khoán nhỏ thường chi tiền mặt.
- ACFE: nhánh hoàn ứng chi phí có bốn dạng (khai sai bản chất, kê tăng, khống, trùng); dạng kê tăng chưa có trong danh sách đã dùng của brief.

**Bối cảnh doanh nghiệp (giả định):** phân phối thức ăn chăn nuôi và thuốc thú y ở Đồng bằng sông Cửu Long; 45 nhân sự; 8 nhân viên kinh doanh vùng đi tuyến. Quy chế khoán: phụ cấp lưu trú 200.000 đồng/ngày; tiền phòng khoán 350.000 đồng/đêm (không cần hóa đơn); xe cá nhân 3.000 đồng/km theo bảng cự ly của công ty. Tạm ứng đầu chuyến, quyết toán trong 5 ngày sau chuyến.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện: nhân viên kinh doanh vùng (NV21, NV22, NV23) và trưởng phòng kinh doanh (NV08).
- Kiểm soát: NV08 ký xác nhận giấy đi đường của nhân viên; kế toán thanh toán (NV04) kiểm tra theo đơn giá khoán; giám đốc (NV01) duyệt quyết toán của trưởng phòng.
- Mức dễ và vừa: không thông đồng. Mức khó: trưởng phòng cùng kê tăng cho mình và làm ngơ cho cấp dưới; đại lý quen ký xác nhận nơi đến cho cả ngày không ghé.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: nhận thêm tiền khoán mà không cần hóa đơn.
- Chuyến công tác có thật. Người thực hiện kê thêm 1 đến 2 ngày (đi sớm hoặc về muộn trên giấy), kê đêm nghỉ khoán cho đêm thực tế về nhà, kê quãng đường theo tuyến dài hơn (vòng qua tỉnh không ghé).
- Chuỗi: đề nghị tạm ứng, đi chuyến thật, lập giấy đi đường với ngày và tuyến kê tăng, xin chữ ký xác nhận nơi đến, quyết toán theo đơn giá khoán, chi bổ sung phần vượt tạm ứng nếu có. Lặp lại mỗi tuần.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng tạm ứng và bảng giao dịch: dòng "tạm ứng" (Nợ 141 / Có 111); dòng "quyết toán tạm ứng" (Nợ 6421 / Có 141), mỗi khoản khoán một dòng. Trường bị khai sai: số lượng (số ngày, số đêm, số km); đơn giá đúng quy chế.
- Thời điểm quan sát: khi quyết toán. Ở mức dễ, thời điểm tạo của dòng quyết toán có thể sớm hơn ngày kết thúc chuyến được kê.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- Mỗi chuyến kê tăng 0,4 đến 1,5 triệu đồng; 4 đến 8 chuyến mỗi tháng mỗi người; 1 đến 3 người; kéo dài 12 đến 30 tháng; tổng 30 đến 400 triệu đồng.
- Lý do: đơn giá khoán nhỏ nên mỗi lần ít tiền, nhưng lặp đều và khó bị kiểm tra; thời gian kéo dài dài hơn trung vị chung 12 tháng của ACFE vì từng khoản nhỏ ít gây chú ý.
- Tổn thất: tổng số ngày, đêm, km kê khai trừ số thực tế (theo lịch trình xác minh với đại lý, định vị xe, hóa đơn bán trong ngày) nhân đơn giá khoán.

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** một nhân viên. Ngày kê bao gồm Chủ nhật hoặc ngày lễ khi đại lý đóng cửa; dòng quyết toán được tạo trước ngày kết thúc chuyến được kê (lập ngày 14/03 cho chuyến kê đến 16/03).
- **Vừa:** đều đặn kê thêm đúng 1 ngày, 1 đêm mỗi chuyến; quãng đường tăng 15 đến 25 phần trăm so với bảng cự ly; tổng mỗi chuyến vẫn trong mức trưởng phòng được duyệt.
- **Khó:** 2 đến 3 nhân viên và trưởng phòng. Quãng đường kê theo tuyến "hợp lý" có ghé thêm 1 đến 2 đại lý thật (đại lý có hóa đơn bán trong tháng nhưng không trong ngày đó); ngày kê thêm là ngày làm việc; có chữ ký xác nhận của đại lý quen; tổng công tác phí của phòng tăng chậm 10 đến 15 phần trăm mỗi năm, song hành với doanh thu tăng.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, chuyến kéo dài thật do sự cố:** xe hỏng, mưa lũ, đại lý dời lịch. Có hóa đơn khách sạn cho đêm thêm, biên bản sửa xe, hóa đơn bán hoặc thu tiền tại đại lý trong ngày kéo dài; xảy ra đơn lẻ, không lặp đều.
- **HL2, cao điểm mùa vụ:** trước Tết hoặc mùa dịch bệnh vật nuôi, mọi nhân viên vùng cùng tăng số ngày công tác, có thể làm cả Chủ nhật; số hóa đơn bán và doanh thu ở các tỉnh tăng tương ứng.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Không có trường ngày bắt đầu và kết thúc chuyến; cần bổ sung vào bảng tạm ứng hoặc dòng quyết toán.
- Không có tỉnh hoặc địa chỉ của khách hàng để đối chiếu tuyến; bảng khách hàng chỉ có tài khoản và hạn nợ.
- Không có bảng cự ly quy chế và lịch ngày lễ; cần tham số.
- Nếu phần mềm cho phép lập chứng từ từ xa, thời điểm tạo của các dòng khác do nhân viên lập không chứng minh được nhân viên có mặt ở văn phòng; cần hỏi lại trước khi dùng thời điểm tạo làm dấu vết.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Đơn giá đúng quy chế khoán; chỉ số lượng bị kê tăng.
- Mỗi dòng quyết toán có tạm ứng tương ứng của cùng nhân viên; người duyệt đúng cấp (trưởng phòng tự quyết toán thì giám đốc duyệt).
- Mức dễ có ít nhất một dấu hiệu thời gian bất khả (quyết toán trước ngày kết thúc chuyến).
- Mức khó không có dấu hiệu bất khả trên từng dòng.
- Dòng HL có bằng chứng phân biệt: hóa đơn khách sạn, biên bản sửa xe, hoặc nhiều nhân viên cùng tăng.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV04 kế toán thanh toán; NV08 trưởng phòng kinh doanh; NV21, NV22, NV23 nhân viên kinh doanh vùng (người thực hiện ở các mức); NV24, NV25 nhân viên kinh doanh khác.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-03-10 08:05 | 2025-03-10 08:30 | 2025-03-10 | Tạm ứng | 3.000.000 | 141 / 111 | NV04 | NV08 | NV21 | — | Quỹ tiền mặt | — | Đề nghị tạm ứng TU-0310, chuyến Sóc Trăng, Bạc Liêu | — | Nền |
| 2 | 2025-03-14 16:40 | 2025-03-17 08:10 | 2025-03-17 | Quyết toán tạm ứng (phụ cấp lưu trú) | 1.400.000 | 6421 / 141 | NV04 | NV08 | NV21 | — | — | — | Giấy đi đường GĐĐ-0310 ghi từ 10/03 đến 16/03 (16/03 là Chủ nhật); quyết toán tạo ngày 14/03 | 200.000; 7 | GL-dễ |
| 3 | 2025-03-14 16:42 | 2025-03-17 08:10 | 2025-03-17 | Quyết toán tạm ứng (phòng khoán) | 2.100.000 | 6421 / 141 | NV04 | NV08 | NV21 | — | — | — | Cùng giấy đi đường GĐĐ-0310 | 350.000; 6 | GL-dễ |
| 4 | 2025-06-23 15:30 | 2025-06-24 09:00 | 2025-06-24 | Quyết toán tạm ứng (phụ cấp lưu trú) | 600.000 | 6421 / 141 | NV04 | NV08 | NV22 | — | — | — | GĐĐ-0619 ghi từ 19/06 đến 21/06; thực tế 19/06 đến 20/06 | 200.000; 3 | GL-vừa |
| 5 | 2025-06-23 15:31 | 2025-06-24 09:00 | 2025-06-24 | Quyết toán tạm ứng (phòng khoán) | 700.000 | 6421 / 141 | NV04 | NV08 | NV22 | — | — | — | GĐĐ-0619; thực tế nghỉ 1 đêm | 350.000; 2 | GL-vừa |
| 6 | 2025-06-23 15:32 | 2025-06-24 09:00 | 2025-06-24 | Quyết toán tạm ứng (xe cá nhân) | 1.380.000 | 6421 / 141 | NV04 | NV08 | NV22 | — | — | — | GĐĐ-0619; bảng cự ly của tuyến là 380 km | 3.000; 460 | GL-vừa |
| 7 | 2025-11-18 10:00 | 2025-11-18 14:00 | 2025-11-18 | Quyết toán tạm ứng (xe cá nhân) | 1.920.000 | 6421 / 141 | NV04 | NV01 | NV08 | — | — | — | Tuyến kê ghé thêm KH112, KH118; hai đại lý có hóa đơn trong tháng nhưng không trong ngày của chuyến | 3.000; 640 | GL-khó |
| 8 | 2025-11-18 10:20 | 2025-11-18 16:00 | 2025-11-18 | Quyết toán tạm ứng (phụ cấp lưu trú) | 800.000 | 6421 / 141 | NV04 | NV08 | NV23 | — | — | — | GĐĐ-1111 ghi 4 ngày, ngày thứ tư (14/11) là ngày làm việc, có chữ ký xác nhận của đại lý quen | 200.000; 4 | GL-khó |
| 9 | 2025-09-08 14:00 | 2025-09-09 09:00 | 2025-09-09 | Quyết toán tạm ứng (khách sạn có hóa đơn) | 1.650.000 | 6421 1.500.000, 1331 150.000 / 141 | NV04 | NV08 | NV25 | — | — | 1C25TKS-0001877 | Biên bản sửa xe của garage; đại lý xác nhận dời lịch nghiệm thu; có hóa đơn bán tại đại lý trong ngày kéo dài | 500.000; 3 | HL1 |
| 10 | 2026-01-12 15:00 | 2026-01-13 08:30 | 2026-01-13 | Quyết toán tạm ứng (phụ cấp lưu trú) | 1.400.000 | 6421 / 141 | NV04 | NV08 | NV24 | — | — | — | GĐĐ-0105 từ 05/01 đến 11/01/2026; cao điểm trước Tết, 7 nhân viên vùng cùng tăng ngày công tác; hóa đơn bán ở các tỉnh tăng tương ứng | 200.000; 7 | HL2 |

---

## V5-KB04. Kê tăng trợ cấp thôi việc và đổi lý do chấm dứt hợp đồng

**1. Mã, tên và ngày soạn:** V5-KB04; "Kê tăng trợ cấp thôi việc và đổi lý do chấm dứt hợp đồng"; 22/10/2026. Nhánh ACFE: thanh toán gian lận, lương, dạng khai sai khoản chi khi chấm dứt hợp đồng (falsified wages); có thông đồng với người lao động nghỉ việc.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Bộ luật Lao động 2019, Điều 46: trợ cấp thôi việc cho người làm việc thường xuyên từ đủ 12 tháng, mỗi năm làm việc được nửa tháng tiền lương. Thời gian tính trợ cấp là tổng thời gian làm việc thực tế trừ thời gian đã tham gia bảo hiểm thất nghiệp và thời gian đã được chi trả. Tiền lương tính là bình quân 6 tháng liền kề theo hợp đồng. Người tự ý bỏ việc không được hưởng.
- Điều 47: trợ cấp mất việc làm khi cắt giảm do thay đổi cơ cấu, công nghệ hoặc lý do kinh tế, mỗi năm một tháng lương, thấp nhất hai tháng.
- Điều 48: thanh toán trong 14 ngày làm việc kể từ ngày chấm dứt, có thể kéo dài nhưng không quá 30 ngày.
- Nghị định 145/2020/NĐ-CP: thời gian làm việc có tháng lẻ đến 6 tháng tính là nửa năm, trên 6 tháng tính là một năm.
- Tổng hợp quy định trên trang MISA AMIS.
- Hiểu biết nghiệp vụ: phần lớn người lao động ở doanh nghiệp đóng bảo hiểm đầy đủ có thời gian tính trợ cấp thôi việc rất ngắn (chủ yếu thời gian thử việc), nên số tiền đúng thường nhỏ; người lập bảng tính có thể lợi dụng việc lãnh đạo không nắm quy tắc trừ thời gian bảo hiểm thất nghiệp.

**Bối cảnh doanh nghiệp (giả định):** may gia công xuất khẩu, 80 nhân sự (công nhân chiếm 85 phần trăm); biến động lao động 25 đến 35 phần trăm mỗi năm; trả lương ngày 10; đóng bảo hiểm thất nghiệp từ khi ký hợp đồng chính thức sau 2 tháng thử việc.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện chính: nhân viên hành chính nhân sự kiêm tính lương (NV06), lập bảng tính trợ cấp, soạn quyết định chấm dứt, cập nhật bảng nhân viên.
- Giám đốc (NV01) ký quyết định và duyệt chi; kế toán (NV03) lập lệnh chi theo bảng tính.
- Thông đồng: với chính người lao động nghỉ việc, người này trả lại 30 đến 50 phần trăm phần chênh lệch bằng tiền mặt. Mức khó có thể thêm quản đốc xưởng (lập danh sách cắt giảm).

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: rút tiền công ty qua khoản chi hợp pháp về hình thức, chia với người nghỉ việc.
- Bước 1: người lao động xin nghỉ hoặc tự ý bỏ việc.
- Bước 2: NV06 thỏa thuận ngầm với người lao động, lập hồ sơ với một trong các sai lệch: không trừ thời gian đã đóng bảo hiểm thất nghiệp; dùng tháng lương cao nhất (có tăng ca) thay vì bình quân 6 tháng theo hợp đồng; sửa ngày vào làm sớm hơn; đổi lý do từ tự ý bỏ việc thành thỏa thuận, hoặc thành cắt giảm do thay đổi cơ cấu.
- Bước 3: giám đốc ký; kế toán chi vào tài khoản người lao động trong thời hạn luật định.
- Bước 4: người lao động rút tiền mặt trả lại phần đã thỏa thuận cho NV06.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng nhân viên: ngày vào (có thể bị sửa sớm hơn), ngày nghỉ, lương.
- Bảng giao dịch: dòng "lương" (Nợ 334 / Có 112) cho khoản trợ cấp, với đơn giá là tiền lương tính trợ cấp, số lượng là số tháng trợ cấp; dòng ghi nhận chi phí (Nợ 6422 / Có 334).
- Thời điểm quan sát: khi chi, thường 2 đến 30 ngày sau ngày nghỉ. Việc sửa ngày vào không quan sát được nếu không có lịch sử thay đổi.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 6 đến 15 trường hợp trong 12 đến 24 tháng; mỗi trường hợp kê tăng 8 đến 45 triệu đồng (lương công nhân 7 đến 9 triệu đồng, 2 đến 5 năm làm việc); tổng 80 đến 450 triệu đồng; NV06 hưởng 30 đến 50 phần trăm.
- Lý do: với 80 nhân sự và biến động 25 phần trăm, có khoảng 20 người nghỉ mỗi năm; chỉ chọn một phần nhỏ để quỹ trợ cấp không tăng đột biến. Thời gian dài hơn trung vị 12 tháng của ACFE vì sự kiện nghỉ việc phân tán.
- Tổn thất: số đã chi trừ số phải chi theo Điều 46, 47 với dữ liệu gốc (ngày vào theo hợp đồng, thời gian đóng bảo hiểm thất nghiệp, lương bình quân 6 tháng theo hợp đồng, lý do chấm dứt thật).

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** công nhân tự ý bỏ việc (không có đơn), đã đóng bảo hiểm thất nghiệp toàn bộ thời gian chính thức, vẫn được chi trợ cấp nửa tháng lương nhân 3 năm. Khoản chi lập 3 ngày sau ngày nghỉ.
- **Vừa:** lý do ghi "thỏa thuận chấm dứt"; lương tính trợ cấp lấy tháng cao nhất có tăng ca (11,5 triệu đồng) thay vì bình quân theo hợp đồng (8,2 triệu đồng); ngày vào trong bảng nhân viên bị sửa sớm hơn 12 tháng để tạo thời gian "chưa đóng bảo hiểm thất nghiệp".
- **Khó:** trong một đợt cắt giảm thật 6 đến 10 người (có phương án sử dụng lao động), thêm 1 đến 2 người vốn đã xin nghỉ tự nguyện vào danh sách; họ hưởng trợ cấp mất việc làm tối thiểu hai tháng lương. Công thức đúng, lương đúng, ngày đúng, cùng ngày chi với cả đợt; chỉ lý do chấm dứt là sai.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, trợ cấp thôi việc thật cho thời gian chưa đóng bảo hiểm thất nghiệp:** người vào làm trước khi công ty đăng ký bảo hiểm thất nghiệp cho họ, hoặc có thời gian thử việc chưa đóng. Số tiền nhỏ, đúng công thức; ngày vào khớp hợp đồng.
- **HL2, đợt cắt giảm thật:** mất đơn hàng, nhiều người nghỉ cùng ngày, trợ cấp mất việc làm theo Điều 47, có thông báo cơ quan lao động; mọi người trong đợt cùng công thức, nhiều người có thâm niên khác nhau.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Thời gian tham gia bảo hiểm thất nghiệp của từng người không có trong bảng nhân viên. Có thể giả định "đóng từ ngày vào cộng 2 tháng thử việc", nhưng HL1 cần ngoại lệ; cần hỏi lại.
- Lý do chấm dứt hợp đồng không có trường riêng; cần bổ sung vào bảng nhân viên.
- Lịch sử sửa ngày vào không có; biến thể vừa chỉ thể hiện được nếu có bảng lịch sử hoặc ngày vào theo hợp đồng gốc.
- Lương bình quân 6 tháng cần các dòng lương theo từng người từng tháng; cần xác nhận bộ sinh nền có tạo dòng lương theo người.
- Phần tiền người lao động trả lại cho NV06 nằm ngoài sổ.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Số tiền bằng đơn giá nhân số tháng; số tháng khớp với công thức người lập đã dùng (dù sai luật).
- Ngày chi nằm trong 30 ngày sau ngày nghỉ.
- Mức khó có cùng thời điểm tạo và duyệt với các dòng thật của đợt cắt giảm.
- HL1 có số tiền nhỏ và căn cứ thời gian chưa đóng bảo hiểm; HL2 có nhiều người cùng ngày.
- Dòng lương tháng thường cho thấy chênh lệch giữa lương hợp đồng và tháng có tăng ca.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV03 kế toán; NV06 hành chính nhân sự kiêm tính lương (người thực hiện); NV33, NV47, NV52, NV55, NV56, NV57, NV61 người lao động.

Trích bảng nhân viên cho dòng mẫu (dữ liệu bịa):

| Mã | Vai trò | Ngày vào (trên bảng) | Ngày nghỉ | Lương hợp đồng | Ghi chú cho người duyệt |
|---|---|---|---|---|---|
| NV47 | Công nhân | 2022-03-01 | 2025-04-11 | 8.200.000 | Đóng bảo hiểm thất nghiệp từ 05/2022; tự ý bỏ việc |
| NV52 | Tổ trưởng | 2021-06-01 | 2025-07-18 | 8.200.000 | Ngày vào theo hợp đồng gốc là 2022-06-01; đóng bảo hiểm thất nghiệp từ 08/2022 |
| NV55 | Công nhân | 2023-02-01 | 2025-09-30 | 8.200.000 | Nộp đơn xin nghỉ tự nguyện ngày 15/08/2025 |
| NV33 | Công nhân | 2019-01-02 | 2025-05-09 | 8.200.000 | Công ty đăng ký bảo hiểm thất nghiệp cho NV33 từ 07/2019 |
| NV61 | Công nhân | 2021-10-01 | 2025-11-07 | 7.900.000 | Đóng bảo hiểm thất nghiệp toàn bộ thời gian chính thức |

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-04-14 10:00 | 2025-04-14 15:30 | 2025-04-14 | Lương (trợ cấp thôi việc) | 12.300.000 | 334 / 112 | NV03 | NV01 | NV47 | TKNV-47 | TKCT-01 | — | Bảng tính TCTV-0414 do NV06 lập: 3 năm nhân nửa tháng; không có đơn xin nghỉ | 8.200.000; 1,5 | GL-dễ |
| 2 | 2025-04-14 10:02 | 2025-04-14 15:30 | 2025-04-14 | Điều chỉnh (ghi nhận chi phí trợ cấp) | 12.300.000 | 6422 / 334 | NV03 | NV01 | NV47 | — | — | — | Như dòng 1 | — | GL-dễ |
| 3 | 2025-07-21 09:15 | 2025-07-22 16:00 | 2025-07-22 | Lương (trợ cấp thôi việc) | 23.000.000 | 334 / 112 | NV03 | NV01 | NV52 | TKNV-52 | TKCT-01 | — | Quyết định chấm dứt theo thỏa thuận TT-0718; bảng tính dùng lương 11.500.000 (tháng 3/2025 có tăng ca) và 4 năm làm việc | 11.500.000; 2 | GL-vừa |
| 4 | 2025-06-10 08:00 | 2025-06-10 08:30 | 2025-06-10 | Lương (kỳ tháng 5) | 9.850.000 | 334 / 112 | NV03 | NV01 | NV52 | TKNV-52 | TKCT-01 | — | Bảng lương tháng 5: lương hợp đồng 8.200.000 cộng tăng ca 1.650.000 | — | Nền |
| 5 | 2025-09-30 14:00 | 2025-09-30 16:30 | 2025-09-30 | Lương (trợ cấp mất việc làm) | 16.400.000 | 334 / 112 | NV03 | NV01 | NV55 | TKNV-55 | TKCT-01 | — | Quyết định cắt giảm CC-09/2025, danh sách 8 người; NV55 đã nộp đơn nghỉ tự nguyện ngày 15/08 (lưu ở phòng nhân sự) | 8.200.000; 2 | GL-khó |
| 6 | 2025-09-30 14:01 | 2025-09-30 16:30 | 2025-09-30 | Lương (trợ cấp mất việc làm) | 17.000.000 | 334 / 112 | NV03 | NV01 | NV56 | TKNV-56 | TKCT-01 | — | Quyết định cắt giảm CC-09/2025; phương án sử dụng lao động; thông báo cơ quan lao động | 8.500.000; 2 | HL2 |
| 7 | 2025-09-30 14:02 | 2025-09-30 16:30 | 2025-09-30 | Lương (trợ cấp mất việc làm) | 25.200.000 | 334 / 112 | NV03 | NV01 | NV57 | TKNV-57 | TKCT-01 | — | Như dòng 6; thâm niên 3 năm | 8.400.000; 3 | HL2 |
| 8 | 2025-05-12 09:00 | 2025-05-12 14:00 | 2025-05-12 | Lương (trợ cấp thôi việc) | 2.050.000 | 334 / 112 | NV03 | NV01 | NV33 | TKNV-33 | TKCT-01 | — | Bảng tính: 6 tháng chưa đóng bảo hiểm thất nghiệp (01/2019 đến 06/2019), tính nửa năm | 8.200.000; 0,25 | HL1 |
| 9 | 2025-11-11 09:30 | 2025-11-12 15:00 | 2025-11-12 | Lương (trợ cấp thôi việc) | 18.600.000 | 334 / 112 | NV03 | NV01 | NV61 | TKNV-61 | TKCT-01 | — | Quyết định thỏa thuận chấm dứt; bảng tính dùng lương 9.300.000 (tháng cao nhất có tăng ca), 4 năm, không trừ thời gian bảo hiểm thất nghiệp | 9.300.000; 2 | GL-vừa |
| 10 | 2025-10-10 08:00 | 2025-10-10 08:30 | 2025-10-10 | Lương (kỳ tháng 9) | 7.900.000 | 334 / 112 | NV03 | NV01 | NV61 | TKNV-61 | TKCT-01 | — | Bảng lương tháng 9: lương hợp đồng, không tăng ca | — | Nền |

---

## V5-KB05. Gắn khách hàng sẵn có cho cộng tác viên để chi hoa hồng giới thiệu

**1. Mã, tên và ngày soạn:** V5-KB05; "Gắn khách hàng sẵn có cho cộng tác viên để chi hoa hồng giới thiệu"; 22/10/2026. Nhánh ACFE: thanh toán gian lận, khoản chi cho bên ngoài dựa trên căn cứ sai (hoa hồng); có yếu tố xung đột lợi ích vì cộng tác viên là người thân của người duyệt.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Báo Pháp luật TP.HCM: hai chuyên viên tuyển dụng ở Hà Nội lập danh sách chi thưởng giới thiệu ứng viên khống, đi qua nhiều bước phê duyệt qua email, chiếm đoạt hơn 770 triệu đồng. Vụ này thuộc dạng "danh sách khống" đã dùng; kịch bản ở đây khác ở chỗ mọi đối tượng đều thật, chỉ có việc ghi công giới thiệu là sai.
- Thông tư 111/2013/TT-BTC: khấu trừ thuế thu nhập cá nhân 10 phần trăm khi trả từ 2 triệu đồng trở lên cho cá nhân không ký hợp đồng lao động.
- Hiểu biết nghiệp vụ: doanh nghiệp lắp điện mặt trời áp mái, nội thất, thiết bị thường dùng mạng cộng tác viên hưởng 2 đến 5 phần trăm doanh thu khách mới.

**Bối cảnh doanh nghiệp (giả định):** lắp đặt điện mặt trời áp mái và thiết bị tiết kiệm năng lượng cho hộ kinh doanh, nhà xưởng nhỏ; 25 nhân sự; doanh thu 25 đến 40 tỷ đồng mỗi năm. Chính sách: hoa hồng 3 phần trăm doanh thu chưa thuế của khách mới do cộng tác viên giới thiệu, trả hàng tháng trong 12 tháng đầu kể từ hóa đơn đầu tiên; khách ngừng mua trên 18 tháng được tính là khách mới.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện: trưởng phòng kinh doanh (NV07), quản lý danh sách cộng tác viên, ký bảng kê hoa hồng hàng tháng.
- Kế toán (NV03) lập lệnh chi theo bảng kê; giám đốc (NV01) duyệt.
- Thông đồng: NV07 với cộng tác viên là người thân (người thật, có giấy tờ, tài khoản đứng tên mình); hai bên chia lại hoa hồng.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: rút tiền công ty dưới dạng hoa hồng hợp lệ về hình thức.
- Bước 1: NV07 đăng ký người thân làm cộng tác viên (thêm vào bảng nhà cung cấp dạng cá nhân).
- Bước 2: hàng tháng, NV07 gán vào cộng tác viên này các khách không do họ giới thiệu: khách đã có giao dịch từ trước; khách mới do nhân viên khác tìm hoặc tự liên hệ qua hotline; hoặc khách do chính NV07 tìm trong khi đang hưởng lương.
- Bước 3: kế toán chi hoa hồng, khấu trừ 10 phần trăm thuế thu nhập cá nhân, chuyển vào tài khoản cộng tác viên.
- Bước 4: cộng tác viên chuyển lại một phần cho NV07.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng nhà cung cấp: cộng tác viên cá nhân với ngày đăng ký, tài khoản, người đại diện là chính họ.
- Bảng giao dịch: dòng "thanh toán nhà cung cấp" (Nợ 6421 / Có 112 và 3335) với đối tượng là cộng tác viên. Các hóa đơn bán đến khách được gán là thật và không bị sửa.
- Thời điểm quan sát: khi chi hoa hồng hàng tháng. Ngày hóa đơn đầu tiên của khách so với ngày đăng ký cộng tác viên quan sát được từ sổ, nếu dòng chi hoa hồng nối được với khách (xem mục 10).

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- Doanh thu bị gán 2 đến 8 tỷ đồng mỗi năm, tương ứng hoa hồng 60 đến 240 triệu đồng mỗi năm; 1 đến 3 hợp đồng mỗi tháng (mỗi hợp đồng 150 đến 900 triệu đồng); kéo dài 12 đến 30 tháng; tổng 100 đến 500 triệu đồng.
- Lý do: tỷ lệ hoa hồng nhỏ trên doanh thu thật nên tổng chi tăng chậm; quy mô nằm dưới trung vị nhánh hóa đơn của ACFE (100.000 USD), phù hợp doanh nghiệp 25 nhân sự.
- Tổn thất: tổng hoa hồng đã chi cho khách không đủ điều kiện (khách cũ, khách tự đến, khách do nhân viên tìm), trừ khoản thưởng doanh số nội bộ lẽ ra công ty phải trả cho nhân viên tìm được khách (nếu có).

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** gán khách đã có hóa đơn trước ngày đăng ký cộng tác viên; hoa hồng tính cả cho hóa đơn mở rộng của khách cũ.
- **Vừa:** gán khách mới thật do nhân viên kinh doanh khác tìm (nhân viên này vẫn nhận thưởng doanh số nội bộ, nên công ty trả hai lần cho cùng một khách) hoặc khách tự liên hệ qua hotline.
- **Khó:** gán khách mới do chính NV07 tìm; NV07 không nhận thưởng doanh số nội bộ cho các khách này để tránh hưởng trùng; cộng tác viên nhận 3 phần trăm so với mức thưởng nội bộ 1 phần trăm. Ngày đăng ký, thời hạn 12 tháng, tỷ lệ, khấu trừ thuế đều đúng chính sách.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, cộng tác viên thật:** khách có hóa đơn đầu tiên sau ngày đăng ký cộng tác viên; cộng tác viên có nhiều khách ở nhiều khu vực; hoa hồng dừng sau 12 tháng.
- **HL2, khách cũ được kích hoạt lại:** khách ngừng mua trên 18 tháng được cộng tác viên giới thiệu lại, theo quy chế được tính là khách mới; có khoảng trống giao dịch dài trước lần mua lại.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Không có trường nối dòng chi hoa hồng với khách được giới thiệu; cần bổ sung trường "khách hàng liên quan" trên dòng chi, hoặc bảng phụ cộng tác viên và khách hàng.
- Tham số chính sách (tỷ lệ, thời hạn 12 tháng, ngưỡng 18 tháng) không có trong bảng công ty.
- Quan hệ thân thích giữa cộng tác viên và NV07 không có trường; bảng nhà cung cấp không có điện thoại, địa chỉ. Nếu muốn có dấu vết quan hệ thì cần thêm trường; nếu không, mức khó giữ nguyên không có dấu vết.
- Thưởng doanh số nội bộ thường trả cùng dòng lương; cần tách để thể hiện biến thể vừa.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Hoa hồng bằng 3 phần trăm doanh thu chưa thuế; thuế thu nhập cá nhân bằng 10 phần trăm; thực chi bằng hoa hồng trừ thuế.
- Mức dễ: hóa đơn đầu tiên của khách sớm hơn ngày đăng ký cộng tác viên.
- Mức vừa: người lập hóa đơn bán là nhân viên kinh doanh khác.
- Mức khó: người lập hóa đơn bán là NV07; không có dấu hiệu bất thường trên từng dòng.
- HL2 có khoảng trống giao dịch trên 18 tháng.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV03 kế toán; NV07 trưởng phòng kinh doanh (người thực hiện); NV15, NV16 nhân viên kinh doanh; NCC41 cộng tác viên là người thân của NV07 (đăng ký 2025-04-01); NCC44 cộng tác viên thật (đăng ký 2025-02-10); KH188, KH205, KH219, KH224, KH230 khách hàng.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2024-11-20 10:10 | 2024-11-20 14:00 | 2024-11-20 | Hóa đơn bán | 594.000.000 | 131 / 511 540.000.000, 3331 54.000.000 | NV15 | NV07 | KH205 | — | — | 1C24TAA-0000981 | Hợp đồng lắp đặt hệ 60 kWp | 540.000.000; 1 | Nền |
| 2 | 2025-05-05 09:30 | 2025-05-05 11:00 | 2025-05-05 | Hóa đơn bán | 132.000.000 | 131 / 511 120.000.000, 3331 12.000.000 | NV15 | NV07 | KH205 | — | — | 1C25TAA-0000214 | Phụ lục mở rộng 15 kWp | 120.000.000; 1 | Nền |
| 3 | 2025-06-03 10:00 | 2025-06-04 09:00 | 2025-06-04 | Thanh toán nhà cung cấp (hoa hồng tháng 5) | 3.600.000 | 6421 / 112 3.240.000, 3335 360.000 | NV03 | NV01 | NCC41 | TKNCC-41 | TKCT-01 | — | Bảng kê hoa hồng tháng 5 do NV07 ký: KH205; KH205 có hóa đơn từ 20/11/2024, trước ngày đăng ký NCC41 | 3%; 120.000.000 | GL-dễ |
| 4 | 2025-08-11 09:00 | 2025-08-11 15:00 | 2025-08-11 | Hóa đơn bán | 418.000.000 | 131 / 511 380.000.000, 3331 38.000.000 | NV15 | NV07 | KH219 | — | — | 1C25TAA-0000402 | Khách mới do NV15 tìm; NV15 nhận thưởng doanh số nội bộ | 380.000.000; 1 | Nền |
| 5 | 2025-09-02 10:30 | 2025-09-03 09:10 | 2025-09-03 | Thanh toán nhà cung cấp (hoa hồng tháng 8) | 11.400.000 | 6421 / 112 10.260.000, 3335 1.140.000 | NV03 | NV01 | NCC41 | TKNCC-41 | TKCT-01 | — | Bảng kê hoa hồng tháng 8 do NV07 ký: KH219 | 3%; 380.000.000 | GL-vừa |
| 6 | 2025-10-15 08:40 | 2025-10-15 10:00 | 2025-10-15 | Hóa đơn bán | 902.000.000 | 131 / 511 820.000.000, 3331 82.000.000 | NV07 | NV01 | KH224 | — | — | 1C25TAA-0000533 | Khách do NV07 tìm; NV07 không ghi nhận thưởng nội bộ cho khách này | 820.000.000; 1 | Nền |
| 7 | 2025-11-03 10:15 | 2025-11-04 08:50 | 2025-11-04 | Thanh toán nhà cung cấp (hoa hồng tháng 10) | 24.600.000 | 6421 / 112 22.140.000, 3335 2.460.000 | NV03 | NV01 | NCC41 | TKNCC-41 | TKCT-01 | — | Bảng kê hoa hồng tháng 10 do NV07 ký: KH224 | 3%; 820.000.000 | GL-khó |
| 8 | 2025-07-14 09:20 | 2025-07-14 11:30 | 2025-07-14 | Hóa đơn bán | 286.000.000 | 131 / 511 260.000.000, 3331 26.000.000 | NV16 | NV07 | KH230 | — | — | 1C25TAA-0000351 | Khách do NCC44 giới thiệu; hóa đơn đầu tiên sau ngày đăng ký NCC44 | 260.000.000; 1 | Nền |
| 9 | 2025-08-04 10:00 | 2025-08-05 09:00 | 2025-08-05 | Thanh toán nhà cung cấp (hoa hồng tháng 7) | 7.800.000 | 6421 / 112 7.020.000, 3335 780.000 | NV03 | NV01 | NCC44 | TKNCC-44 | TKCT-01 | — | Bảng kê hoa hồng tháng 7: KH230 | 3%; 260.000.000 | HL1 |
| 10 | 2025-12-02 10:00 | 2025-12-03 09:00 | 2025-12-03 | Thanh toán nhà cung cấp (hoa hồng tháng 11) | 6.300.000 | 6421 / 112 5.670.000, 3335 630.000 | NV03 | NV01 | NCC44 | TKNCC-44 | TKCT-01 | — | Bảng kê hoa hồng tháng 11: KH188, hóa đơn trước đó gần nhất tháng 3/2024 (ngừng 20 tháng) | 3%; 210.000.000 | HL2 |

---

## V5-KB06. Thanh lý tài sản cố định còn giá trị cho người mua có quan hệ

**1. Mã, tên và ngày soạn:** V5-KB06; "Thanh lý tài sản cố định còn giá trị cho người mua có quan hệ"; 22/10/2026. Nhánh ACFE: tài sản không phải tiền, chiếm đoạt qua chuyển giao và bán thanh lý giả (larceny of fixed assets through false disposal).

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Hướng dẫn công khai về quy trình thanh lý tài sản cố định (MISA AMIS): hội đồng thanh lý gồm thủ trưởng đơn vị, kế toán trưởng, người quản lý tài sản; đánh giá lại tình trạng; bán theo quy định. Ở doanh nghiệp nhỏ, hội đồng thường chỉ ký biên bản theo đề xuất của bộ phận kỹ thuật, và hình thức bán chỉ định là phổ biến.
- Thông tư 45/2013/TT-BTC: tài sản cố định có nguyên giá từ 30 triệu đồng; khấu hao theo khung thời gian; doanh nghiệp được thay đổi thời gian trích khấu hao một lần với lý do phù hợp.
- ACFE: nhánh tài sản không phải tiền chiếm 22 phần trăm số vụ, trung vị 66.000 USD, kéo dài trung vị 12 tháng.

**Bối cảnh doanh nghiệp (giả định):** cơ khí chế tạo và lắp dựng nhà thép; 50 nhân sự; tài sản cố định gồm 2 xe tải cẩu, xe bán tải, máy cắt CNC plasma, máy hàn tự động, máy phát điện; tổng nguyên giá 12 đến 18 tỷ đồng; khấu hao đường thẳng.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện chính: phó giám đốc kỹ thuật (NV02), chủ tịch hội đồng thanh lý, có quyền đề xuất thanh lý, đánh giá tình trạng và đề xuất thời gian sử dụng còn lại.
- Kế toán tài sản (NV05) lập bảng khấu hao và bút toán thanh lý; giám đốc (NV01) ký quyết định, thường tin vào đề xuất kỹ thuật.
- Người mua: cá nhân là người thân của NV02 hoặc một cơ sở mua bán máy cũ do người quen đứng tên.
- Mức dễ: không thông đồng trong công ty. Mức vừa: kế toán làm theo đề nghị rút ngắn thời gian khấu hao mà không biết mục đích. Mức khó: thêm một xưởng sửa chữa xác nhận "hỏng, không kinh tế để sửa" và một cơ sở thu mua đứng tên mua lô.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: chuyển tài sản còn dùng được về tay người có quan hệ với giá thấp.
- Bước 1 (6 đến 12 tháng trước, ở mức vừa và khó): tạo hồ sơ xuống cấp, bằng tờ trình đánh giá lại thời gian sử dụng còn lại hoặc chuỗi chi phí sửa chữa.
- Bước 2: biên bản kiểm định "hư hỏng"; quyết định thanh lý theo hình thức chỉ định (không đấu giá, không lấy ba báo giá độc lập).
- Bước 3: lập hóa đơn bán thanh lý giá thấp, thu tiền, ghi giảm tài sản.
- Bước 4 (1 đến 3 tháng sau): công ty mua hoặc thuê tài sản thay thế; người mua sửa nhẹ rồi dùng hoặc bán lại theo giá thị trường.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: dòng "khấu hao" (Nợ 154 hoặc 6422 / Có 214) có mức tăng đột ngột ở mức vừa; dòng "điều chỉnh" ghi giảm tài sản (Nợ 214, 811 / Có 211); dòng "hóa đơn bán" thanh lý (Nợ 131 / Có 711, 3331); dòng "thu tiền"; dòng "mua hàng" tài sản thay thế.
- Bảng khách hàng: người mua có thể là khách mới tạo ngay trước thanh lý (mức dễ) hoặc khách cũ có thật (mức khó).
- Thời điểm quan sát: tại thanh lý; ở mức vừa, việc thay đổi mức khấu hao quan sát được 6 đến 12 tháng trước đó.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 1 đến 4 tài sản trong 12 đến 36 tháng; chênh lệch giữa giá trị thị trường và giá bán 80 đến 600 triệu đồng mỗi tài sản; tổng 150 triệu đến 1,2 tỷ đồng.
- Lý do: xe tải cẩu 5 đến 7 năm tuổi có giá thị trường 600 đến 900 triệu đồng, máy CNC cùng đời 600 đến 700 triệu đồng. Trung vị ACFE nhánh này khoảng 1,65 tỷ đồng sau quy đổi; doanh nghiệp nhỏ có ít tài sản giá trị lớn nên đặt thấp hơn. Số lần ít vì thanh lý là sự kiện hiếm.
- Tổn thất: giá trị hợp lý tại ngày thanh lý (giá thị trường, giá người mua bán lại, thẩm định độc lập) trừ giá bán thanh lý; cộng chi phí thay thế phát sinh sớm.

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** xe bán tải 4 năm tuổi, giá trị còn lại 420 triệu đồng (55 phần trăm nguyên giá), thanh lý 90 triệu đồng cho một cá nhân là khách mới tạo 3 ngày trước; lỗ thanh lý 330 triệu đồng ghi một lần; một tháng sau mua xe mới cùng loại.
- **Vừa:** máy CNC nguyên giá 1,8 tỷ đồng, khấu hao 10 năm (15 triệu đồng mỗi tháng), đã dùng 4 năm. Từ tháng 01/2025, theo tờ trình "máy xuống cấp", thời gian sử dụng còn lại được rút từ 6 năm xuống 12 tháng, khấu hao tăng lên 90 triệu đồng mỗi tháng. Thanh lý tháng 12/2025 với giá 120 triệu đồng, gần giá trị còn lại 90 triệu đồng, có lãi nhỏ; giá thị trường 600 đến 700 triệu đồng.
- **Khó:** xe tải cẩu có 3 lần sửa chữa thật nhỏ trong năm, lần cuối xưởng sửa chữa kết luận "hộp số hỏng, không kinh tế để sửa". Xe được gộp vào đợt thanh lý cuối năm cùng 6 tài sản đã khấu hao hết thật, bán theo lô cho một cơ sở thu mua máy cũ có thật (đã từng mua phế liệu của công ty); cơ sở này chuyển lại xe cho người thân của NV02 với giá thấp. Mọi chứng từ đầy đủ, quy trình đúng hình thức.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, thanh lý thật:** tài sản đã khấu hao hết, hư hỏng, có kiểm định độc lập, lấy 2 đến 3 báo giá, bán cho người trả giá cao nhất; giá bán gần giá phế liệu hoặc giá máy cũ trên thị trường.
- **HL2, thay đổi thời gian khấu hao hợp lệ:** cường độ sử dụng tăng (máy chạy 3 ca) hoặc thay đổi công nghệ; áp dụng cho cả nhóm tài sản cùng loại; tài sản tiếp tục được dùng, không bị bán sớm cho người có quan hệ.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Brief không có bảng sổ tài sản cố định (mã tài sản, nguyên giá, ngày đưa vào sử dụng, thời gian khấu hao, giá trị còn lại). Đề nghị bổ sung, hoặc thêm trường mã tài sản trên các dòng khấu hao, ghi giảm, thanh lý.
- Giá trị thị trường không có trong dữ liệu; tổn thất phải ghi trong bảng nhãn riêng.
- Quan hệ giữa người mua và NV02 không có trường (bảng khách hàng không có người đại diện, địa chỉ).
- Cần xác nhận bộ sinh có áp dụng quy tắc "chỉ thay đổi thời gian khấu hao một lần" của Thông tư 45 hay không.
- Thanh lý theo lô gồm nhiều tài sản trên một hóa đơn: cần quy ước phân bổ giá bán cho từng tài sản.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Bút toán ghi giảm cân: Nợ 214 cộng Nợ 811 bằng Có 211.
- Lãi hoặc lỗ thanh lý bằng thu nhập 711 trừ giá trị còn lại 811.
- Khấu hao tháng trước và sau điều chỉnh khớp với nguyên giá và thời gian còn lại.
- Ngày tạo khách hàng (mức dễ) gần ngày thanh lý; tài sản thay thế được mua trong 1 đến 3 tháng.
- HL1 có báo giá cạnh tranh; HL2 áp dụng cho cả nhóm tài sản và không theo sau bởi thanh lý cho người có quan hệ.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV02 phó giám đốc kỹ thuật (người thực hiện); NV04 kế toán thanh toán; NV05 kế toán tài sản; KH301, KH305 người mua có quan hệ; KH118 cơ sở thu mua máy cũ có thật; KH120 người mua thật; NCC09 đại lý ô tô; NCC52 xưởng sửa chữa.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-03-10 09:00 | 2025-03-10 15:00 | 2025-03-10 | Điều chỉnh (ghi giảm tài sản TS-XBT02) | 760.000.000 | 214 340.000.000, 811 420.000.000 / 211 760.000.000 | NV05 | NV01 | — | — | — | — | Quyết định thanh lý TL-0310 (bán chỉ định); biên bản kiểm định "hư hỏng" do NV02 chủ trì | — | GL-dễ |
| 2 | 2025-03-10 09:20 | 2025-03-10 15:00 | 2025-03-10 | Hóa đơn bán (thanh lý TS-XBT02) | 99.000.000 | 131 / 711 90.000.000, 3331 9.000.000 | NV05 | NV02 | KH301 | — | — | 1C25TCK-0000188 | KH301 là cá nhân, tạo trong bảng khách hàng ngày 07/03/2025 | 90.000.000; 1 | GL-dễ |
| 3 | 2025-04-08 10:00 | 2025-04-08 16:00 | 2025-04-08 | Mua hàng (xe bán tải mới) | 902.000.000 | 211 820.000.000, 1331 82.000.000 / 331 | NV05 | NV01 | NCC09 | — | — | 1C25TOT-0000456 | Tờ trình thay thế xe đã thanh lý | 820.000.000; 1 | GL-dễ |
| 4 | 2024-12-31 16:00 | 2024-12-31 17:00 | 2024-12-31 | Khấu hao (TS-CNC01) | 15.000.000 | 154 / 214 | NV05 | NV02 | — | — | — | — | Bảng khấu hao tháng 12: nguyên giá 1.800.000.000, 10 năm | — | Nền |
| 5 | 2025-01-31 16:00 | 2025-01-31 17:00 | 2025-01-31 | Khấu hao (TS-CNC01) | 90.000.000 | 154 / 214 | NV05 | NV02 | — | — | — | — | Tờ trình của NV02: đánh giá lại thời gian sử dụng còn lại 12 tháng (giá trị còn lại 1.080.000.000) | — | GL-vừa |
| 6 | 2025-12-22 10:00 | 2025-12-22 15:30 | 2025-12-22 | Hóa đơn bán (thanh lý TS-CNC01) | 132.000.000 | 131 / 711 120.000.000, 3331 12.000.000 | NV05 | NV02 | KH305 | — | — | 1C25TCK-0000731 | Quyết định thanh lý TL-1222; giá trị còn lại 90.000.000 | 120.000.000; 1 | GL-vừa |
| 7 | 2025-10-14 09:30 | 2025-10-14 14:00 | 2025-10-14 | Thanh toán nhà cung cấp (sửa chữa xe cẩu TS-XC01) | 38.500.000 | 331 / 112 | NV04 | NV01 | NCC52 | TKNCC-52 | TKCT-01 | — | Hóa đơn sửa chữa 1C25TSC-0000912, lần thứ ba trong năm; kết luận "hộp số hỏng, không kinh tế để sửa" | — | GL-khó |
| 8 | 2025-12-29 10:00 | 2025-12-29 16:00 | 2025-12-29 | Hóa đơn bán (thanh lý lô 7 tài sản) | 154.000.000 | 131 / 711 140.000.000, 3331 14.000.000 | NV05 | NV01 | KH118 | — | — | 1C25TCK-0000745 | Quyết định thanh lý cuối năm TL-1229: TS-XC01 (giá trị còn lại 210.000.000) cùng 6 tài sản đã khấu hao hết; bán theo lô | 140.000.000; 1 | GL-khó |
| 9 | 2025-06-20 09:00 | 2025-06-20 14:00 | 2025-06-20 | Hóa đơn bán (thanh lý máy hàn TS-MH03) | 18.700.000 | 131 / 711 17.000.000, 3331 1.700.000 | NV05 | NV01 | KH120 | — | — | 1C25TCK-0000402 | Biên bản kiểm định; ba báo giá 12, 15, 17 triệu đồng; tài sản đã khấu hao hết | 17.000.000; 1 | HL1 |
| 10 | 2025-07-31 16:00 | 2025-07-31 17:00 | 2025-07-31 | Khấu hao (nhóm TS-MH05 đến TS-MH08) | 52.000.000 | 154 / 214 | NV05 | NV02 | — | — | — | — | Quyết định đánh giá lại thời gian sử dụng do chạy 3 ca từ 07/2025, áp dụng cả nhóm (mức cũ 40.000.000) | — | HL2 |

---

## V5-KB07. Dùng xe tải của công ty chở hàng thuê ngoài sổ

**1. Mã, tên và ngày soạn:** V5-KB07; "Dùng xe tải của công ty chở hàng thuê ngoài sổ"; 22/10/2026. Nhánh ACFE: tài sản không phải tiền, sử dụng sai mục đích (misuse); chi phí vận hành do công ty gánh.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Báo Pháp luật TP.HCM: tài xế xe bồn tấp vào điểm mua xăng dầu "chui" để rút dầu bán kiếm lời; doanh nghiệp đình chỉ công tác tài xế; tài xế giải thích việc tích lũy từ phần còn sót trong bồn, trong khi công ty chỉ kiểm soát bằng niêm chì. Các vụ này cho thấy tài sản vận tải dễ bị dùng sai mục đích khi kiểm soát chỉ dựa vào chứng từ của chính người lái.
- ACFE: dạng "misuse" trong nhánh tài sản không phải tiền; trung vị nhánh 66.000 USD, 12 tháng.
- Hiểu biết nghiệp vụ: doanh nghiệp vật liệu xây dựng nhỏ thường giao xe cho tài xế quản lý, nhiên liệu ghi nợ tại một cửa hàng theo hợp đồng và thanh toán cuối tháng theo bảng kê.

**Bối cảnh doanh nghiệp (giả định):** kinh doanh vật liệu xây dựng (xi măng, sắt thép, gạch); 30 nhân sự; 6 xe tải 5 đến 15 tấn giao hàng trong bán kính 80 km; doanh thu 70 đến 100 tỷ đồng mỗi năm. Nhiên liệu mua tại cửa hàng xăng dầu theo hợp đồng, thanh toán cuối tháng kèm bảng kê lượt đổ theo xe; sửa chữa tại một garage; phí đường bộ trả qua tài khoản thu phí điện tử của công ty.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Đội trưởng đội xe (NV10) điều phối xe, ký xác nhận bảng kê nhiên liệu và nhật trình.
- Tài xế (NV33 và các tài xế khác); nhân viên điều phối kho (NV11) lập phiếu giao hàng và phiếu điều chuyển kho.
- Kế toán (NV04) ghi nhận theo bảng kê; giám đốc (NV01) duyệt thanh toán.
- Mức dễ: một tài xế làm một mình. Mức vừa: tài xế cùng đội trưởng. Mức khó: đội trưởng cùng điều phối kho.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: thu tiền cước chở thuê cho bên ngoài bằng xe, nhiên liệu và thời gian của công ty.
- Người thực hiện nhận chở cát, gạch, đồ đạc cho chủ hàng bên ngoài; thu 1,5 đến 5 triệu đồng mỗi chuyến bằng tiền mặt hoặc chuyển khoản cá nhân.
- Nhiên liệu đổ tại cửa hàng hợp đồng và ghi nợ công ty; phí đường bộ trừ vào tài khoản của xe công ty; lốp và sửa chữa tăng.
- Chuyến ngoài được đặt vào ngày nghỉ (mức dễ), ghép vào chiều về của chuyến thật (mức vừa), hoặc ngụy trang thành chuyến điều chuyển nội bộ giữa hai kho (mức khó).

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: dòng "mua hàng" nhiên liệu (Nợ 6421, 1331 / Có 331) với đơn giá theo lít và số lượng lít; dòng "mua hàng" sửa chữa, lốp; dòng "thanh toán nhà cung cấp". Không có hóa đơn bán cho chuyến ngoài. Ở mức khó có thêm cặp dòng "điều chỉnh" điều chuyển hàng giữa hai kho.
- Thời điểm quan sát: cuối tháng, khi hóa đơn tổng hợp nhiên liệu và bảng kê được ghi sổ; tỷ lệ nhiên liệu trên khối lượng giao hàng thay đổi theo tháng.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 4 đến 12 chuyến ngoài mỗi tháng; chi phí công ty gánh 0,6 đến 2 triệu đồng mỗi chuyến (40 đến 120 lít dầu với giá giả định 20.000 đồng/lít chưa thuế, phí đường bộ, hao mòn); kéo dài 12 đến 36 tháng; chi phí 50 đến 800 triệu đồng; cước chở thuê bị chiếm 70 triệu đến 1,5 tỷ đồng.
- Lý do: cước vận tải vật liệu cự ly ngắn; xe được giao cho tài xế giữ qua đêm và ngày nghỉ; kiểm soát chủ yếu dựa vào bảng kê do chính đội xe ký.
- Tổn thất: ghi tách hai phần: (a) chi phí trực tiếp của chuyến ngoài (nhiên liệu, phí đường bộ, sửa chữa, khấu hao theo km); (b) cước chở thuê thu ngoài sổ (theo xác nhận của chủ hàng).

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** một tài xế; chuyến ngoài vào Chủ nhật hoặc ngày lễ; bảng kê nhiên liệu có lượt đổ 80 đến 150 lít của xe XE-03 vào Chủ nhật khi công ty không có hóa đơn bán hay phiếu giao hàng; lốp xe phải thay sớm so với định mức.
- **Vừa:** chuyến ngoài ghép vào chiều về của chuyến giao hàng thật trong ngày làm việc; số lít mỗi ngày của xe tăng 30 đến 50 phần trăm; nhật trình kê quãng đường lớn hơn để mức tiêu hao trên km vẫn trong định mức; đội trưởng ký bảng kê.
- **Khó:** đội trưởng và điều phối kho lập phiếu điều chuyển hàng từ kho 1 sang kho 2 và ngược lại vài ngày sau (không có nhu cầu thật); xe chạy chuyến ngoài trong thời gian đó. Nhiên liệu, km khớp với chuyến điều chuyển; tổng chi phí vận tải trên doanh thu tăng chậm 2 đến 4 phần trăm mỗi năm, phân bổ đều cho 6 xe.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, dịch vụ vận chuyển thuê thật:** công ty nhận chở thuê chiều về cho khách vãng lai và xuất hóa đơn dịch vụ vận chuyển cùng ngày với lượt đổ nhiên liệu.
- **HL2, giao hàng gấp ngày nghỉ:** công trình đổ bê tông Chủ nhật hoặc giao gấp trước Tết; có hóa đơn bán, phiếu giao hàng cùng ngày, nhiều xe cùng hoạt động.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Biển số xe, ngày đổ nhiên liệu theo từng lượt, nhật trình km không có trường riêng; cần bổ sung bảng phụ hoặc trường trên dòng nhiên liệu. Nếu chỉ có một dòng hóa đơn tổng hợp mỗi tháng thì mức dễ và vừa không thể hiện được theo ngày.
- Điều chuyển hàng giữa hai kho không có loại nghiệp vụ trong danh sách; cần quy ước dùng "điều chỉnh" hoặc thêm loại mới.
- Phí đường bộ điện tử thường là một dòng nạp tiền mỗi tháng, không có chi tiết trạm; cần dữ liệu trạm nếu muốn dùng.
- Định mức nhiên liệu và tuổi thọ lốp theo xe là tham số ngoài.
- Cước chở thuê thu ngoài sổ không có trong dữ liệu.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Số lít nhân đơn giá cộng thuế bằng số tiền; ngày đổ nhiên liệu thuộc tháng của bảng kê.
- Mức dễ: lượt đổ vào ngày nghỉ không có phiếu giao hàng cùng ngày.
- Mức vừa: lượt đổ lớn so với cự ly giao hàng của cùng ngày.
- Mức khó: cặp điều chuyển đi và về cùng mặt hàng, cùng số lượng, cách vài ngày.
- HL1 và HL2 có hóa đơn bán cùng ngày.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV02 kế toán trưởng; NV04 kế toán; NV10 đội trưởng đội xe; NV11 điều phối kho; NV33 tài xế; NCC60 cửa hàng xăng dầu; NCC61 garage; KH410, KH415, KH420, KH425 khách hàng; XE-01 đến XE-06 mã xe.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-04-03 08:10 | 2025-04-03 08:40 | 2025-04-03 | Hóa đơn bán | 21.120.000 | 131 / 511 19.200.000, 3331 1.920.000 | NV11 | NV02 | KH410 | — | — | 1C25TAA-0000390 | Phiếu giao hàng PGH-0403, XE-03, 12 tấn xi măng, cự ly 18 km | 1.600.000; 12 | Nền |
| 2 | 2025-04-30 16:00 | 2025-04-30 17:00 | 2025-04-30 | Mua hàng (nhiên liệu theo bảng kê) | 1.320.000 | 6421 1.200.000, 1331 120.000 / 331 | NV04 | NV10 | NCC60 | — | — | 1C25TXD-0004120 | Bảng kê tháng 4: XE-03 ngày 03/04, 60 lít | 20.000; 60 | Nền |
| 3 | 2025-04-30 16:01 | 2025-04-30 17:00 | 2025-04-30 | Mua hàng (nhiên liệu theo bảng kê) | 2.310.000 | 6421 2.100.000, 1331 210.000 / 331 | NV04 | NV10 | NCC60 | — | — | 1C25TXD-0004120 | Bảng kê tháng 4: XE-03 ngày 06/04 (Chủ nhật), 105 lít; không có phiếu giao hàng ngày 06/04 | 20.000; 105 | GL-dễ |
| 4 | 2025-05-20 10:00 | 2025-05-20 15:00 | 2025-05-20 | Mua hàng (thay 2 lốp XE-03) | 9.240.000 | 6421 8.400.000, 1331 840.000 / 331 | NV04 | NV10 | NCC61 | — | — | 1C25TGR-0000617 | Lốp thay sau 9 tháng; lần thay trước tháng 8/2024 | 4.200.000; 2 | GL-dễ |
| 5 | 2025-07-15 07:30 | 2025-07-15 08:00 | 2025-07-15 | Hóa đơn bán | 33.000.000 | 131 / 511 30.000.000, 3331 3.000.000 | NV11 | NV02 | KH415 | — | — | 1C25TAA-0000702 | PGH-0715, XE-05, 10 tấn thép, cự ly 25 km | 3.000.000; 10 | Nền |
| 6 | 2025-07-31 16:00 | 2025-07-31 17:00 | 2025-07-31 | Mua hàng (nhiên liệu theo bảng kê) | 3.080.000 | 6421 2.800.000, 1331 280.000 / 331 | NV04 | NV10 | NCC60 | — | — | 1C25TXD-0004790 | Bảng kê tháng 7: XE-05 ngày 15/07, 140 lít; nhật trình kê 520 km | 20.000; 140 | GL-vừa |
| 7 | 2025-09-12 07:00 | 2025-09-12 07:15 | 2025-09-12 | Điều chỉnh (điều chuyển kho 1 sang kho 2) | 18.600.000 | 1561 kho 2 / 1561 kho 1 | NV11 | NV10 | — | — | — | — | Phiếu điều chuyển ĐC-0912, XE-02, 300 bao xi măng | 62.000; 300 | GL-khó |
| 8 | 2025-09-14 16:30 | 2025-09-14 16:40 | 2025-09-14 | Điều chỉnh (điều chuyển kho 2 về kho 1) | 18.600.000 | 1561 kho 1 / 1561 kho 2 | NV11 | NV10 | — | — | — | — | Phiếu điều chuyển ĐC-0914, XE-02, "kho 2 thừa hàng"; cùng mặt hàng, cùng số lượng với ĐC-0912 | 62.000; 300 | GL-khó |
| 9 | 2025-08-09 15:00 | 2025-08-09 15:30 | 2025-08-09 | Hóa đơn bán (dịch vụ vận chuyển chiều về) | 3.300.000 | 131 / 511 3.000.000, 3331 300.000 | NV11 | NV02 | KH420 | — | — | 1C25TAA-0000877 | PGH-0809 (thứ bảy), XE-04, chở thuê chiều về; cùng ngày có lượt đổ nhiên liệu của XE-04 | 3.000.000; 1 | HL1 |
| 10 | 2026-02-01 06:30 | 2026-02-01 07:00 | 2026-02-01 | Hóa đơn bán | 52.800.000 | 131 / 511 48.000.000, 3331 4.800.000 | NV11 | NV02 | KH425 | — | — | 1C26TAA-0000061 | PGH-0201 (Chủ nhật), XE-01 và XE-06, giao gạch gấp trước Tết | 1.200; 40.000 | HL2 |

---

## V5-KB08. Đòi "phí" nhà cung cấp để được thanh toán đúng hạn

**1. Mã, tên và ngày soạn:** V5-KB08; "Đòi phí nhà cung cấp để được thanh toán đúng hạn"; 22/10/2026. Nhánh ACFE: tham nhũng, hối lộ, dạng tống tiền kinh tế (economic extortion), dựa trên quyền xếp lịch thanh toán.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Bộ luật Hình sự 2015 sửa đổi 2017, Điều 354 khoản 6: người có chức vụ, quyền hạn trong doanh nghiệp, tổ chức ngoài Nhà nước mà nhận hối lộ thì bị xử lý theo điều này; người bị ép buộc đưa hối lộ mà chủ động khai báo trước khi bị phát giác thì được coi là không có tội (Liên đoàn Luật sư Việt Nam).
- Viện Kiểm sát nhân dân tối cao: bài viết về tội phạm tham nhũng ngoài Nhà nước; chủ thể nhận hối lộ trong khu vực tư có thể là người làm việc ở bất kỳ cương vị nào.
- ACFE: tham nhũng có mặt ở 48 phần trăm số vụ, trung vị 200.000 USD, kéo dài khoảng 13 tháng.
- Hiểu biết nghiệp vụ: ở doanh nghiệp nhỏ, giám đốc thường duyệt danh sách thanh toán theo lô trên ngân hàng điện tử mà không xem tuổi nợ của từng hóa đơn; kế toán thanh toán quyết định hóa đơn nào được đưa vào lô.

**Bối cảnh doanh nghiệp (giả định):** chế biến thực phẩm (bánh kẹo, nước chấm); 70 nhân sự; 45 nhà cung cấp nguyên liệu, bao bì, dịch vụ; giá trị mua 40 đến 60 tỷ đồng mỗi năm; kỳ hạn công nợ nhà cung cấp 30 ngày; giám đốc duyệt lô thanh toán hai lần mỗi tuần.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Mức dễ: kế toán thanh toán (NV04) lập danh sách đề xuất thanh toán, chọn hóa đơn nào được trả.
- Mức vừa: NV04 cùng nhân viên kho hoặc kiểm soát chất lượng xác nhận hồ sơ giao nhận, tạo lý do "thiếu hồ sơ" hoặc "hóa đơn sai".
- Mức khó: kế toán trưởng (NV03), người soạn cả quy định ưu tiên thanh toán.
- Phía nhà cung cấp: bị ép buộc, không chủ động; nhiều nhà cung cấp nhỏ chấp nhận để giữ dòng tiền.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: thu tiền cá nhân từ nhà cung cấp bằng quyền xếp lịch thanh toán.
- Bước 1: người thực hiện ngầm báo cho nhà cung cấp "muốn nhanh thì gửi phí 1,5 đến 3 phần trăm".
- Bước 2: nhà cung cấp chịu chi chuyển khoản cá nhân, đưa tiền mặt hoặc thẻ quà tặng; họ được đưa vào lô thanh toán sớm hoặc đúng hạn.
- Bước 3: nhà cung cấp từ chối bị giữ lại với lý do "chưa đủ hồ sơ", "hóa đơn sai thông tin", "chờ giám đốc duyệt".
- Bước 4: công ty chịu lãi chậm trả, mất chiết khấu thanh toán; ở lần ký lại hợp đồng, nhà cung cấp chịu chi đưa "phí" vào đơn giá.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: thời điểm tạo và duyệt của dòng "thanh toán nhà cung cấp" so với dòng "mua hàng" tương ứng; dòng "điều chỉnh" lãi chậm trả (Nợ 635 / Có 331); hóa đơn thay thế (số hóa đơn mới thay số cũ).
- Bảng công ty: kỳ hạn công nợ dùng để tính số ngày quá hạn.
- Không có trường nào chứa khoản "phí"; khoản này nằm hoàn toàn ngoài sổ.
- Thời điểm quan sát: thứ tự thanh toán không theo tuổi nợ thấy được ở từng lô; độ trễ chỉ thấy sau khi quá hạn.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- 8 đến 15 nhà cung cấp chịu chi (chiếm 25 đến 40 phần trăm giá trị mua); người thực hiện thu 150 đến 700 triệu đồng mỗi năm ngoài sổ. Tổn thất trên sổ của công ty (lãi chậm trả, mất chiết khấu) 40 đến 250 triệu đồng mỗi năm. Kéo dài 12 đến 36 tháng.
- Lý do: tỷ lệ 1,5 đến 3 phần trăm là mức nhà cung cấp nhỏ có thể chịu mà không bỏ quan hệ; kéo dài hơn trung vị tham nhũng của ACFE vì nhà cung cấp ngại tố giác khi còn muốn bán hàng.
- Tổn thất: (a) lãi hoặc phạt chậm trả đã ghi nhận cho nhà cung cấp bị giữ; (b) chiết khấu thanh toán bị mất nếu hợp đồng có điều khoản; (c) phần tăng đơn giá của nhà cung cấp chịu chi so với giá thị trường cùng mặt hàng (ước tính, ghi riêng). Khoản "phí" người thực hiện nhận không phải tổn thất trực tiếp trên sổ.

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** 3 đến 4 nhà cung cấp bị giữ 60 đến 120 ngày quá hạn trong khi số dư tiền gửi của công ty dồi dào; xuất hiện bút toán lãi chậm trả; nhà cung cấp chịu chi được trả trong 10 đến 15 ngày.
- **Vừa:** việc giữ được hợp thức bằng yêu cầu lập lại hóa đơn (hóa đơn thay thế) 1 đến 3 lần cho nhà cung cấp từ chối; độ trễ 40 đến 75 ngày; không có lãi chậm trả vì nhà cung cấp ngại đòi.
- **Khó:** không nhà cung cấp nào bị quá hạn. Nhà cung cấp chịu chi được trả sớm 10 đến 20 ngày trước hạn mà không có chiết khấu; nhà cung cấp từ chối được trả đúng ngày đến hạn. Thứ tự vẫn hợp với quy định nội bộ "ưu tiên nhà cung cấp nguyên liệu chính" do chính NV03 soạn. Ở lần ký lại hợp đồng, đơn giá của nhà cung cấp chịu chi tăng 2 đến 3 phần trăm.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, thiếu tiền thật:** mùa thấp điểm, số dư tiền gửi thấp, mọi nhà cung cấp đều bị giãn thanh toán theo quyết định ưu tiên có văn bản; độ trễ đồng đều.
- **HL2, thanh toán sớm để hưởng chiết khấu:** mỗi lần trả sớm đi kèm chiết khấu thanh toán (Có 515) hoặc số tiền trả thấp hơn hóa đơn đúng tỷ lệ hợp đồng.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Bảng công ty chỉ có kỳ hạn công nợ chung; nếu kỳ hạn khác nhau theo nhà cung cấp thì cần trường ở bảng nhà cung cấp.
- Ngày lập hóa đơn của nhà cung cấp (khác thời điểm ghi sổ) cần thiết để tính tuổi nợ; brief chỉ có số hóa đơn.
- Điều khoản chiết khấu thanh toán và lãi chậm trả theo hợp đồng không có tham số.
- Số dư tiền gửi suy ra từ giao dịch cần số dư đầu kỳ.
- Liên kết giữa hóa đơn thay thế và hóa đơn bị thay thế cần trường riêng.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Mỗi dòng thanh toán đối ứng đúng một hóa đơn mua có thật; số tiền khớp.
- Số ngày từ hóa đơn đến thanh toán khớp mức: dễ có quá hạn trên 60 ngày, vừa 40 đến 75 ngày kèm hóa đơn thay thế, khó trả sớm không chiết khấu.
- Lãi chậm trả tính đúng (lãi suất ngày nhân số ngày quá hạn nhân số tiền).
- HL2 có chiết khấu đúng tỷ lệ; HL1 có độ trễ đồng đều và số dư tiền thấp.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV03 kế toán trưởng; NV04 kế toán thanh toán; NV05 kế toán kho; NCC70, NCC72 nhà cung cấp chịu chi; NCC71, NCC74 nhà cung cấp từ chối; NCC73 nhà cung cấp có điều khoản chiết khấu; NCC75 nhà cung cấp bị giãn trong mùa thấp điểm.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-03-03 10:00 | 2025-03-03 14:00 | 2025-03-03 | Mua hàng | 88.000.000 | 152 80.000.000, 1331 8.000.000 / 331 | NV05 | NV03 | NCC70 | — | — | 1C25TBB-0000731 | Phiếu nhập PN-0303, bao bì | 8.000; 10.000 | Nền |
| 2 | 2025-03-12 09:00 | 2025-03-12 16:00 | 2025-03-12 | Thanh toán nhà cung cấp | 88.000.000 | 331 / 112 | NV04 | NV01 | NCC70 | TKNCC-70 | TKCT-01 | — | Lô thanh toán 12/03; 9 ngày sau hóa đơn, trước hạn 21 ngày | — | GL-dễ |
| 3 | 2025-03-04 09:30 | 2025-03-04 15:00 | 2025-03-04 | Mua hàng | 165.000.000 | 152 150.000.000, 1331 15.000.000 / 331 | NV05 | NV03 | NCC71 | — | — | 1C25TCC-0002210 | Phiếu nhập PN-0304, đường | 15.000; 10.000 | Nền |
| 4 | 2025-06-25 09:00 | 2025-06-25 16:00 | 2025-06-25 | Thanh toán nhà cung cấp | 165.000.000 | 331 / 112 | NV04 | NV01 | NCC71 | TKNCC-71 | TKCT-01 | — | Lô thanh toán 25/06; 113 ngày sau hóa đơn, quá hạn 83 ngày; số dư tiền gửi trong thời gian này trên 3 tỷ đồng | — | GL-dễ |
| 5 | 2025-06-27 10:00 | 2025-06-27 15:00 | 2025-06-27 | Điều chỉnh (lãi chậm trả) | 6.847.500 | 635 / 331 | NV04 | NV03 | NCC71 | — | — | — | Công văn đòi lãi chậm trả của NCC71: 0,05 phần trăm mỗi ngày nhân 83 ngày | — | GL-dễ |
| 6 | 2025-08-05 11:00 | 2025-08-05 15:00 | 2025-08-05 | Mua hàng (hóa đơn thay thế) | 77.000.000 | 152 70.000.000, 1331 7.000.000 / 331 | NV05 | NV03 | NCC74 | — | — | 1C25TDD-0000415, thay thế 1C25TDD-0000388 lập ngày 07/07 | Yêu cầu lập lại lần thứ hai của NV04: "sai tên hàng" | 35.000; 2.000 | GL-vừa |
| 7 | 2025-09-15 09:00 | 2025-09-15 16:00 | 2025-09-15 | Thanh toán nhà cung cấp | 77.000.000 | 331 / 112 | NV04 | NV01 | NCC74 | TKNCC-74 | TKCT-01 | — | Lô thanh toán 15/09; 70 ngày sau hóa đơn gốc | — | GL-vừa |
| 8 | 2025-11-10 09:00 | 2025-11-10 16:00 | 2025-11-10 | Thanh toán nhà cung cấp | 132.000.000 | 331 / 112 | NV03 | NV01 | NCC72 | TKNCC-72 | TKCT-01 | — | Lô 10/11; hóa đơn 1C25TEE-0000902 lập 29/10; trả trước hạn 18 ngày, không có chiết khấu | — | GL-khó |
| 9 | 2025-11-12 09:00 | 2025-11-12 16:00 | 2025-11-12 | Thanh toán nhà cung cấp | 108.350.000 | 331 110.000.000 / 112 108.350.000, 515 1.650.000 | NV04 | NV01 | NCC73 | TKNCC-73 | TKCT-01 | — | Hợp đồng: chiết khấu 1,5 phần trăm nếu trả trong 10 ngày; hóa đơn lập 04/11 | — | HL2 |
| 10 | 2025-07-15 09:00 | 2025-07-15 16:00 | 2025-07-15 | Thanh toán nhà cung cấp | 96.800.000 | 331 / 112 | NV04 | NV01 | NCC75 | TKNCC-75 | TKCT-01 | — | Quyết định ưu tiên 07/2025 do thiếu vốn lưu động mùa thấp điểm: mọi nhà cung cấp giãn 20 đến 25 ngày; số dư tiền gửi dưới 300 triệu đồng | — | HL1 |

---

## V5-KB09. Dời ghi nhận chi phí và nợ phải trả cuối năm để đạt điều kiện tín dụng

**1. Mã, tên và ngày soạn:** V5-KB09; "Dời ghi nhận chi phí và nợ phải trả cuối năm để đạt điều kiện tín dụng"; 22/10/2026. Nhánh ACFE: gian lận báo cáo tài chính, khai tăng lợi nhuận bằng che giấu chi phí và nợ phải trả, qua chênh lệch thời điểm.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Báo Tiền Phong: nhiều doanh nghiệp dùng hai hệ thống sổ sách, "chế biến" số liệu trên báo cáo gửi các cơ quan khác nhau (thuế, ngân hàng); với ngân hàng thường trình số liệu "đẹp".
- VnEconomy: Luật Kế toán cấm lập hai hệ thống sổ kế toán tài chính trở lên hoặc cung cấp báo cáo tài chính có số liệu không đồng nhất trong cùng kỳ.
- Nghị định 123/2020/NĐ-CP: thời điểm lập hóa đơn bán hàng là thời điểm chuyển giao quyền sở hữu hoặc quyền sử dụng; hóa đơn dịch vụ lập khi hoàn thành cung ứng.
- ACFE: gian lận báo cáo tài chính chiếm 5 phần trăm số vụ, trung vị 766.000 USD; tổn thất trung vị khi người thực hiện là chủ sở hữu hoặc lãnh đạo khoảng 500.000 USD.

**Bối cảnh doanh nghiệp (giả định):** thương mại điện máy, điện lạnh; 40 nhân sự; doanh thu 90 đến 130 tỷ đồng mỗi năm; vay hạn mức ngân hàng 15 đến 25 tỷ đồng. Điều kiện tái cấp hạn mức (giả định): lợi nhuận trước thuế dương hai năm liền, tỷ lệ nợ phải trả trên vốn chủ không vượt 3 lần. Lương trả ngày 05 tháng sau; các tháng thường trích lương vào ngày cuối tháng.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Giám đốc kiêm chủ sở hữu (NV01) chỉ đạo; kế toán trưởng (NV02) thực hiện; kế toán mua hàng (NV05) giữ hóa đơn chưa ghi sổ.
- Thông đồng: chủ sở hữu và kế toán trưởng. Mức khó thêm 2 đến 3 nhà cung cấp thân thiết đồng ý lập hóa đơn và biên bản vào đầu tháng 1.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: báo cáo lợi nhuận và nợ phải trả đạt điều kiện tín dụng.
- Bước 1 (tháng 11 đến 12): ước tính lợi nhuận năm; xác định khoản thiếu so với điều kiện.
- Bước 2 (cuối tháng 12): trì hoãn ghi nhận chi phí và nợ phải trả có thật của tháng 12 sang tháng 1 bằng cách giữ hóa đơn chưa ghi sổ, bỏ bút toán trích trước của riêng tháng 12, hoặc nhờ nhà cung cấp lập chứng từ vào đầu tháng 1.
- Bước 3 (tháng 1 đến 3): lập báo cáo năm gửi ngân hàng.
- Bước 4: các khoản đã dời được ghi vào năm sau; cuối năm sau lặp lại để bù, tạo hiệu ứng lăn.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng giao dịch: dòng "mua hàng" chi phí có thời điểm tạo và ghi sổ ở tháng 1 trong khi ký hiệu hóa đơn mang năm cũ (mức dễ); thiếu dòng trích lương, trích lãi vay của tháng 12 (mức vừa); dòng "mua hàng" và "điều chỉnh" thưởng có chứng từ ngày tháng 1 cho công việc của tháng 12 (mức khó).
- Bảng công ty: ngày trả lương dùng để kiểm tra quy ước trích trước.
- Thời điểm quan sát: tháng 1 năm sau; so sánh chi phí tháng 12 với các tháng khác và cùng kỳ năm trước.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định sai lệch:**
- Mỗi năm lệch 0,8 đến 3 tỷ đồng (1 đến 3 phần trăm doanh thu), đủ biến lỗ nhỏ thành lãi nhỏ ở doanh nghiệp thương mại có biên lợi nhuận ròng 1 đến 2 phần trăm; 15 đến 40 dòng bị dời mỗi kỳ; lặp 2 đến 3 kỳ cuối năm (24 đến 36 tháng), có thể cả cuối quý nếu ngân hàng yêu cầu báo cáo quý.
- Lý do: mức đủ nhỏ để không lộ trên báo cáo năm, đủ lớn để vượt ngưỡng điều kiện; dưới trung vị ACFE vì quy mô doanh nghiệp nhỏ.
- Sai lệch: tổng chi phí thuộc năm N bị ghi vào năm N+1, tương đương chi phí bị khai thiếu và nợ phải trả bị khai thiếu tại 31/12. Kịch bản này không gây mất tiền trực tiếp cho doanh nghiệp; bên chịu rủi ro là ngân hàng và chủ sở hữu khác (nếu có).

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** 15 đến 30 hóa đơn chi phí tháng 12 (vận chuyển, quảng cáo, lắp đặt thuê ngoài) được ghi sổ từ 03/01 đến 10/01; ký hiệu hóa đơn mang năm 2025; tổng 0,6 đến 1 tỷ đồng.
- **Vừa:** thêm việc bỏ bút toán trích lương tháng 12 (1,1 đến 1,4 tỷ đồng) và lãi vay tháng 12; tháng 12 là tháng duy nhất không có trích lương cuối tháng, chi phí lương tháng 12 được ghi vào ngày chi 05/01.
- **Khó:** nhà cung cấp lắp đặt lập hóa đơn ngày 03/01 (ký hiệu năm 2026) cho công việc hoàn thành 20/12, biên bản nghiệm thu cũng ghi ngày tháng 1; quyết định thưởng Tết năm cũ ký ngày 06/01. Mọi chứng từ nhất quán; dấu vết duy nhất là tỷ lệ chi phí trên doanh thu tháng 12 thấp bất thường so với tháng 11, tháng 1 và cùng kỳ.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, hóa đơn theo chu kỳ cước:** điện, viễn thông, thuê bao phần mềm có hóa đơn phát hành sau kỳ; mọi tháng đều ghi sổ chậm 5 đến 12 ngày như nhau, không riêng tháng 12.
- **HL2, mùa vụ thật:** doanh nghiệp nhập trữ hàng tháng 10 đến 11 cho mùa cuối năm nên mua vào tháng 12 thấp; chi phí bán hàng tháng 12 vẫn tương ứng doanh thu; hoặc thưởng Tết được quyết định theo kết quả năm vào tháng 1 theo thông lệ ổn định nhiều năm.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Cần trường ngày lập hóa đơn của nhà cung cấp, khác thời điểm tạo và ghi sổ. Brief chỉ có số hóa đơn; ký hiệu chỉ mang năm, không mang tháng.
- Ngày giao hàng hoặc hoàn thành dịch vụ (căn cứ ghi nhận) không có trường.
- Điều kiện tín dụng là bối cảnh, không có trong dữ liệu.
- Quy ước trích lương phải thống nhất với bộ sinh nền: nếu nền ghi chi phí lương khi chi ở mọi tháng thì biến thể vừa không thể hiện được.
- Trả lãi vay không có loại nghiệp vụ riêng trong danh sách; dòng mẫu dùng "điều chỉnh", cần xác nhận.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Mức dễ: ký hiệu hóa đơn mang năm 2025, thời điểm tạo và ghi sổ ở năm 2026.
- Mức vừa: tháng 11 có trích lương cuối tháng, tháng 12 không có, chi phí lương tháng 12 ghi khi chi.
- Mức khó: chứng từ nhất quán ngày tháng 1; mô tả cho người duyệt ghi rõ ngày hoàn thành thật.
- HL1 có mẫu ghi sổ chậm đều mọi tháng; HL2 có lượng nhập trữ lớn trước tháng 12.

**Vai trò trong dòng mẫu:** NV01 giám đốc kiêm chủ sở hữu; NV02 kế toán trưởng; NV05 kế toán mua hàng; NCC80 vận chuyển thuê ngoài; NCC81 quảng cáo; NCC82 điện lực; NCC84 lắp đặt; NCC85 nhà cung cấp hàng điện máy.

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-01-06 09:00 | 2026-01-06 15:00 | 2026-01-06 | Mua hàng (vận chuyển tháng 12/2025) | 52.800.000 | 6421 48.000.000, 1331 4.800.000 / 331 | NV05 | NV02 | NCC80 | — | — | 1C25TEE-0001290 | Bảng kê chuyến từ 01/12 đến 31/12/2025; hóa đơn lập 31/12/2025 | 48.000.000; 1 | GL-dễ |
| 2 | 2026-01-07 10:00 | 2026-01-07 16:00 | 2026-01-07 | Mua hàng (quảng cáo tháng 12/2025) | 110.000.000 | 6421 100.000.000, 1331 10.000.000 / 331 | NV05 | NV02 | NCC81 | — | — | 1C25TFF-0000533 | Biên bản nghiệm thu chiến dịch tháng 12/2025 | 100.000.000; 1 | GL-dễ |
| 3 | 2025-11-30 16:00 | 2025-11-30 17:00 | 2025-11-30 | Lương (trích lương tháng 11) | 1.180.000.000 | 6421 520.000.000, 6422 660.000.000 / 334 | NV02 | NV01 | — | — | — | — | Bảng lương tháng 11; các tháng 1 đến 11 đều trích ngày cuối tháng | — | Nền |
| 4 | 2026-01-05 08:00 | 2026-01-05 08:30 | 2026-01-05 | Lương (lương tháng 12/2025, ghi chi phí khi chi) | 1.240.000.000 | 6421 550.000.000, 6422 690.000.000 / 112 | NV02 | NV01 | — | — | TKCT-01 | — | Bảng lương tháng 12/2025; không có bút toán trích ngày 31/12/2025 | — | GL-vừa |
| 5 | 2026-01-05 09:00 | 2026-01-05 09:30 | 2026-01-05 | Điều chỉnh (lãi vay kỳ 26/11 đến 25/12/2025) | 96.000.000 | 635 / 112 | NV02 | NV01 | — | — | TKCT-01 | — | Thông báo lãi của ngân hàng; tháng 1 đến 11 lãi được ghi trong tháng phát sinh | — | GL-vừa |
| 6 | 2026-01-03 10:00 | 2026-01-03 14:00 | 2026-01-03 | Mua hàng (lắp đặt cho dự án) | 418.000.000 | 632 380.000.000, 1331 38.000.000 / 331 | NV05 | NV02 | NCC84 | — | — | 1C26TGG-0000004 | Biên bản nghiệm thu ghi 03/01/2026; thực tế hoàn thành 20/12/2025; doanh thu dự án đã ghi 22/12/2025 | 380.000.000; 1 | GL-khó |
| 7 | 2026-01-06 15:00 | 2026-01-06 16:00 | 2026-01-06 | Điều chỉnh (thưởng Tết năm 2025) | 620.000.000 | 6422 / 334 | NV02 | NV01 | — | — | — | — | Quyết định thưởng Tết ký 06/01/2026; năm trước quyết định ký 20/12 | — | GL-khó |
| 8 | 2026-01-08 09:00 | 2026-01-08 11:00 | 2026-01-08 | Mua hàng (tiền điện kỳ 26/11 đến 25/12/2025) | 38.500.000 | 6422 35.000.000, 1331 3.500.000 / 331 | NV05 | NV02 | NCC82 | — | — | 1C25TEV-0098812 | Hóa đơn phát hành 30/12/2025, nhận 05/01/2026 | 35.000.000; 1 | HL1 |
| 9 | 2025-12-08 09:00 | 2025-12-08 11:00 | 2025-12-08 | Mua hàng (tiền điện kỳ 26/10 đến 25/11/2025) | 36.300.000 | 6422 33.000.000, 1331 3.300.000 / 331 | NV05 | NV02 | NCC82 | — | — | 1C25TEV-0087710 | Mọi tháng đều ghi sổ từ ngày 05 đến 10 tháng sau | 33.000.000; 1 | HL1 |
| 10 | 2025-10-20 10:00 | 2025-10-20 15:00 | 2025-10-20 | Mua hàng (nhập trữ hàng mùa cuối năm) | 4.620.000.000 | 156 4.200.000.000, 1331 420.000.000 / 331 | NV05 | NV01 | NCC85 | — | — | 1C25THH-0004410 | Kế hoạch nhập trữ quý IV; 1.400 máy | 3.000.000; 1.400 | HL2 |

---

## V5-KB10. Nới hạn nợ và tiếp tục bán chịu cho khách hàng có quan hệ với người duyệt tín dụng

**1. Mã, tên và ngày soạn:** V5-KB10; "Nới hạn nợ và tiếp tục bán chịu cho khách hàng có quan hệ với người duyệt tín dụng"; 22/10/2026. Nhánh ACFE: tham nhũng, xung đột lợi ích, dạng bán hàng (sales scheme), lợi ích nằm ở điều khoản tín dụng.

**2. Người viết, vai trò và xác nhận:** Phiên agent tách biệt (mô hình ngôn ngữ), đóng vai người viết kịch bản. Xác nhận chưa xem mã, kết quả hay tài liệu phương pháp.

**3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:**
- Luật Minh Khuê (tình huống tư vấn): nhân viên bán hàng khai đã bán nợ cho người quen; đến kỳ kiểm kê còn trên 600 triệu đồng không thu hồi được; câu hỏi đặt ra trách nhiệm của trưởng phòng và lãnh đạo.
- ACFE: tham nhũng có mặt ở 48 phần trăm số vụ, trung vị 200.000 USD, kéo dài khoảng 13 tháng; bản tóm tắt ghi 20 phần trăm người thực hiện có quan hệ gần gũi bất thường với nhà cung cấp hoặc khách hàng.
- Thông tư 48/2019/TT-BTC về dự phòng và xóa nợ phải thu khó đòi.
- Hiểu biết nghiệp vụ: phân phối vật tư nông nghiệp ở Tây Nguyên thường bán chịu theo mùa vụ cho đại lý cấp 2.

**Bối cảnh doanh nghiệp (giả định):** phân phối phân bón và thuốc bảo vệ thực vật cho đại lý cấp 2 ở Tây Nguyên; 30 nhân sự; doanh thu 80 đến 120 tỷ đồng mỗi năm; kỳ hạn chuẩn 30 ngày, chính sách mùa vụ 90 ngày cho đại lý vùng cà phê; vay ngân hàng lãi 8 đến 9 phần trăm mỗi năm để tài trợ vốn lưu động.

**4. Ai có thể thực hiện, quyền hạn và thông đồng:**
- Người thực hiện: phó giám đốc kinh doanh (NV02), có quyền đặt hạn nợ cho khách và duyệt bán vượt hạn. Đại lý liên quan do người thân của NV02 điều hành, không được khai báo.
- Kế toán công nợ (NV05) có cảnh báo nhưng không có quyền chặn bán; giám đốc (NV01) duyệt xóa nợ và chương trình bán hàng.
- Mức dễ: NV02 làm một mình. Mức vừa: thêm nhân viên kinh doanh tuyến (NV17) lập đơn hàng và phụ lục gia hạn. Mức khó: NV02 đề xuất "chương trình hỗ trợ đại lý chiến lược" được giám đốc ký, áp dụng cho 3 đại lý, trong đó 2 đại lý không liên quan làm bình phong.

**5. Thủ đoạn, mục đích và chuỗi hành động:**
- Mục đích: cho đại lý của người thân dùng vốn của công ty (hàng nhận trước, trả sau dài) để kinh doanh, cho vay lại hoặc mở rộng; NV02 hưởng lợi gián tiếp qua người thân.
- Bước 1: tạo khách mới hoặc nâng hạn nợ của khách lên 90 đến 120 ngày.
- Bước 2 (tháng 1 đến 12): bán hàng mùa vụ liên tục; đại lý trả chậm, trả nhỏ giọt.
- Bước 3 (tháng 12 đến 24): dư nợ tăng dần; NV02 duyệt bán tiếp dù quá hạn.
- Bước 4 (sau tháng 18 đến 24): đại lý báo "mất mùa, thua lỗ", ngừng hoạt động; công ty trích dự phòng rồi xóa nợ.

**6. Bảng và trường bị thay đổi hoặc thiếu; thời điểm quan sát:**
- Bảng khách hàng: hạn nợ của khách liên quan cao hơn chuẩn (mức dễ), hoặc đúng chuẩn nhưng từng hóa đơn có phụ lục gia hạn riêng (mức vừa), hoặc bằng mức của chương trình (mức khó).
- Bảng giao dịch: dòng "hóa đơn bán" tiếp tục dù quá hạn; dòng "thu tiền" nhỏ so với dư nợ; cuối cùng là dòng "xóa nợ".
- Thời điểm quan sát: hạn nợ bất thường thấy ngay khi tạo khách; dư nợ quá hạn thấy từ tháng 4 đến 6; xóa nợ thấy sau 18 đến 30 tháng.

**7. Số giao dịch, thời gian, khoảng tiền và cách xác định tổn thất:**
- Doanh thu với đại lý liên quan 4 đến 10 tỷ đồng mỗi năm (20 đến 60 hóa đơn); dư nợ vượt chuẩn bình quân 1,5 đến 4 tỷ đồng; chi phí vốn 120 đến 360 triệu đồng mỗi năm; nợ không thu hồi cuối cùng 0,6 đến 3 tỷ đồng; kéo dài 18 đến 36 tháng.
- Lý do: doanh nghiệp phân phối vật tư nông nghiệp bán chịu theo mùa với giá trị hóa đơn lớn; tình huống Luật Minh Khuê cho thấy hơn 600 triệu đồng không thu hồi được với một nhân viên bán hàng; kịch bản ở cấp phó giám đốc nên lớn hơn, nhưng vẫn quanh trung vị tham nhũng của ACFE sau quy đổi (khoảng 5 tỷ đồng).
- Tổn thất: (a) chi phí vốn bằng dư nợ vượt chuẩn bình quân nhân lãi suất vay nhân thời gian; (b) nợ phải thu không thu hồi được; trừ lãi trả chậm đại lý đã trả (nếu có).

**8. Biến thể dễ, vừa và khó:**
- **Dễ:** khách mới với hạn nợ 120 ngày ngay từ đầu (chuẩn 30 ngày); NV02 vừa đề xuất vừa duyệt; bán tiếp khi hóa đơn cũ quá hạn; dư nợ 2 đến 3 tỷ đồng; xóa nợ sau khoảng 20 tháng.
- **Vừa:** hạn nợ trên bảng khách hàng là 30 ngày, nhưng từng hóa đơn kèm "phụ lục gia hạn" 90 ngày do NV02 ký; khi đến hạn, đại lý trả một phần và nhận phụ lục gia hạn lần hai; công ty vẫn bán thêm.
- **Khó:** "chương trình hỗ trợ đại lý chiến lược" có quyết định của giám đốc, hạn nợ 90 ngày cho 3 đại lý; 2 đại lý không liên quan trả đúng hạn; đại lý liên quan cũng trả đúng hạn 90 ngày trong 18 tháng đầu, sau đó ở mùa cao điểm có dư nợ lớn nhất thì ngừng trả và giải thể.

**9. Hai tình huống hợp lệ trông giống:**
- **HL1, chính sách tín dụng mùa vụ chính thức:** mọi đại lý vùng cà phê được hạn 90 ngày, trả sau thu hoạch; nhiều khách cùng mẫu; nợ được thu sau mùa.
- **HL2, giãn nợ có cấu trúc:** đại lý lâu năm gặp thiên tai được giãn nợ có biên bản và lịch trả; công ty ngừng hoặc giảm bán chịu thêm trong thời gian giãn; có thể thu lãi trả chậm.

**10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:**
- Quan hệ giữa NV02 và đại lý không có trường; bảng khách hàng thiếu người đại diện, địa chỉ, điện thoại. Cần bổ sung nếu muốn có dấu vết quan hệ; nếu không, kịch bản chỉ thể hiện qua điều khoản tín dụng.
- Hạn mức tín dụng (số tiền) không có trường; chỉ có hạn nợ (số ngày).
- Lịch sử thay đổi hạn nợ và người duyệt hạn nợ không có.
- Phụ lục gia hạn theo từng hóa đơn (mức vừa) cần trường "hạn thanh toán của hóa đơn" trên dòng giao dịch.
- Lãi suất vay ngân hàng để tính chi phí vốn là tham số ngoài.

**11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:**
- Hóa đơn bán: đơn giá nhân số lượng cộng thuế bằng số tiền.
- Mức dễ có hóa đơn mới khi hóa đơn cũ đã quá hạn; dòng thu nhỏ so với dư nợ; có xóa nợ cuối kỳ.
- Mức vừa có phụ lục gia hạn ký bởi NV02 và thanh toán một phần.
- Mức khó có đại lý bình phong trong cùng chương trình, cùng điều khoản.
- HL1 có nhiều đại lý cùng hạn mùa vụ; HL2 không có hóa đơn bán chịu mới trong thời gian giãn nợ.

**Vai trò trong dòng mẫu:** NV01 giám đốc; NV02 phó giám đốc kinh doanh (người thực hiện); NV05 kế toán công nợ; NV17 nhân viên kinh doanh tuyến; KH501, KH503, KH504 đại lý liên quan (mỗi mức một đại lý); KH502 đại lý không liên quan trong chương trình; KH480 đại lý hưởng chính sách mùa vụ; KH455 đại lý được giãn nợ sau lũ.

Trích bảng khách hàng cho dòng mẫu (dữ liệu bịa):

| Mã | Hạn nợ (ngày) | Ghi chú cho người duyệt |
|---|---|---|
| KH501 | 120 | Tạo ngày 2025-01-06; đại lý do người thân của NV02 điều hành |
| KH504 | 30 | Đại lý do người thân của NV02 điều hành; các hóa đơn có phụ lục gia hạn riêng |
| KH503 | 90 | Trong chương trình hỗ trợ đại lý chiến lược; có quan hệ với NV02 |
| KH502 | 90 | Trong cùng chương trình; không có quan hệ |
| KH480 | 90 | Chính sách mùa vụ vùng cà phê, áp dụng cho 24 đại lý |
| KH455 | 30 | Giãn nợ sau lũ từ 08/2025 theo biên bản |

| # | Tạo | Duyệt | Ghi sổ | Loại nghiệp vụ | Số tiền (đ) | Nợ / Có | Người lập | Người duyệt | Đối tượng | TK nhận | TK trả | Số HĐ | Chứng từ kèm (mô tả) | Đơn giá; SL | Vai trò dòng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-02-14 09:00 | 2025-02-14 10:30 | 2025-02-14 | Hóa đơn bán | 630.000.000 | 131 / 511 600.000.000, 3331 30.000.000 | NV17 | NV02 | KH501 | — | — | 1C25TAA-0000201 | Đơn đặt hàng ĐH-0214; 50 tấn phân bón | 12.000.000; 50 | GL-dễ |
| 2 | 2025-07-18 09:30 | 2025-07-18 10:00 | 2025-07-18 | Hóa đơn bán | 840.000.000 | 131 / 511 800.000.000, 3331 40.000.000 | NV17 | NV02 | KH501 | — | — | 1C25TAA-0000622 | Hóa đơn 0000201 quá hạn 34 ngày so với hạn 120 ngày được cấp, quá 124 ngày so với hạn chuẩn 30 ngày; NV02 duyệt bán vượt | 12.500.000; 64 | GL-dễ |
| 3 | 2025-07-30 15:00 | 2025-07-30 15:00 | 2025-07-30 | Thu tiền | 50.000.000 | 112 / 131 | NV05 | NV05 | KH501 | TKCT-01 | TKKH-501 | — | Sao kê ngân hàng; dư nợ KH501 sau thu 1.420.000.000 | — | GL-dễ |
| 4 | 2025-09-12 08:45 | 2025-09-12 09:20 | 2025-09-12 | Hóa đơn bán | 472.500.000 | 131 / 511 450.000.000, 3331 22.500.000 | NV17 | NV02 | KH504 | — | — | 1C25TAA-0000795 | Đơn đặt hàng ĐH-0912; phụ lục gia hạn GH-0912 do NV02 ký: hạn thanh toán 90 ngày | 9.000.000; 50 | GL-vừa |
| 5 | 2025-12-30 14:00 | 2025-12-30 14:00 | 2025-12-30 | Thu tiền | 200.000.000 | 112 / 131 | NV05 | NV05 | KH504 | TKCT-01 | TKKH-504 | — | Thanh toán một phần hóa đơn 0000795; phụ lục gia hạn lần hai GH-1230 đến 31/03/2026 | — | GL-vừa |
| 6 | 2026-09-25 10:00 | 2026-09-28 16:00 | 2026-09-30 | Xóa nợ | 1.420.000.000 | 2293 / 131 | NV05 | NV01 | KH501 | — | — | — | Quyết định xóa nợ; xác nhận đại lý ngừng hoạt động; dự phòng đã trích | — | GL-dễ |
| 7 | 2025-11-20 09:00 | 2025-11-20 10:00 | 2025-11-20 | Hóa đơn bán | 1.050.000.000 | 131 / 511 1.000.000.000, 3331 50.000.000 | NV17 | NV02 | KH503 | — | — | 1C25TAA-0000910 | Chương trình hỗ trợ đại lý chiến lược (quyết định của giám đốc), hạn 90 ngày; mùa cao điểm | 12.500.000; 80 | GL-khó |
| 8 | 2025-11-21 09:00 | 2025-11-21 10:00 | 2025-11-21 | Hóa đơn bán | 735.000.000 | 131 / 511 700.000.000, 3331 35.000.000 | NV17 | NV02 | KH502 | — | — | 1C25TAA-0000918 | Cùng chương trình; KH502 trả đúng hạn các kỳ trước | 12.500.000; 56 | Nền |
| 9 | 2025-12-15 08:30 | 2025-12-15 09:00 | 2025-12-15 | Hóa đơn bán | 525.000.000 | 131 / 511 500.000.000, 3331 25.000.000 | NV17 | NV02 | KH480 | — | — | 1C25TAA-0001012 | Chính sách mùa vụ 90 ngày áp dụng 24 đại lý vùng cà phê; KH480 trả đủ sau mùa năm trước | 12.500.000; 40 | HL1 |
| 10 | 2025-10-10 15:00 | 2025-10-10 15:00 | 2025-10-10 | Thu tiền | 120.000.000 | 112 / 131 | NV05 | NV05 | KH455 | TKCT-01 | TKKH-455 | — | Lịch trả nợ giãn nợ sau lũ, kỳ 2 trên 6; không có hóa đơn bán chịu mới cho KH455 từ 08/2025 | — | HL2 |

---

## Nguồn tham khảo

### ACFE, Occupational Fraud 2024: A Report to the Nations

- Bản PDF gốc (người viết không đọc trực tiếp được do dung lượng lớn; số liệu lấy qua các bản tóm tắt dưới đây): https://www.ivey.uwo.ca/media/kjljj5cy/2024-report-to-the-nations.pdf
- CoStar, tóm tắt số vụ, tổn thất, tỷ lệ và trung vị theo nhánh, thời gian kéo dài: https://www.costar.com/article/1184241407/employee-committed-fraud-costs-companies-billions-in-losses-report-says
- GRF CPAs, tóm tắt tổn thất theo quy mô tổ chức, cấp bậc người thực hiện, phát hiện, kiểm soát: https://www.grfcpa.com/?p=4822
- Porte Brown, tóm tắt phương thức che giấu: https://www.portebrown.com/newsblog-archive/how-fraud-perpetrators-conceal-their-illicit-activities
- Mondaq, tóm tắt dấu hiệu hành vi và yếu tố kiểm soát: https://webiis10.mondaq.com/turkey/white-collar-crime-anti-corruption-fraud/1444736/an-overview-of-occupational-fraud-2024-a-report-to-the-nations-by-acfe

### Báo chí và tình huống Việt Nam (đã ẩn tên người)

- KB01: Báo Pháp luật Việt Nam, nhân viên kinh doanh chiếm đoạt tiền công nợ: https://baophapluat.vn/nhan-vien-kinh-doanh-chiem-doat-tien-ty-cua-cong-ty-de-tieu-xai-ca-nhan-post467395.html
- KB01: Báo Văn hóa, nhân viên chiếm đoạt hơn 1 tỷ đồng của công ty và khách hàng: https://baovanhoa.vn/phap-luat/bat-nhan-vien-chiem-doat-hon-1-ti-dong-cua-cong-ty-va-khach-hang-95811.html
- KB02: Tuổi Trẻ, kế toán chuyển tiền qua tài khoản người thân để chiếm đoạt: https://tuoitre.vn/ke-toan-rut-ruot-cong-ty-gan-3-ti-dong-lanh-an-20-nam-tu-20240610165721948.htm
- KB03: Thư viện Pháp luật, quy định khoán công tác phí: https://thuvienphapluat.vn/banan/tin-tuc/quy-dinh-ve-khoan-chi-cong-tac-phi-cho-nhan-vien-di-cong-tac-moi-nhat-2024-10059.html
- KB03: Kế toán Lê Ánh, chứng từ chi phí công tác: https://ketoanleanh.edu.vn/kinh-nghiem-ke-toan/cach-xu-ly-chi-phi-cong-tac-hop-ly.html
- KB04: MISA AMIS, trợ cấp thôi việc theo Bộ luật Lao động 2019: https://amis.misa.vn/160943/tro-cap-thoi-viec/
- KB05: Báo Pháp luật TP.HCM, lập khống danh sách chi thưởng giới thiệu: https://plo.vn/2-nhan-vien-lap-khong-danh-sach-chi-thuong-chiem-doat-770-trieu-dong-post739502.html
- KB06: MISA AMIS, quy trình thanh lý tài sản cố định: https://amis.misa.vn/30588/quy-trinh-thanh-ly-tai-san-co-dinh-theo-quy-dinh-moi-nhat/
- KB07: Báo Pháp luật TP.HCM, tài xế xe bồn rút dầu bán: https://plo.vn/vu-rut-ruot-xe-dau-tren-quoc-lo-1-dinh-chi-cong-tac-2-tai-xe-xe-bon-post817226.html
- KB07: Báo Pháp luật TP.HCM, đình chỉ tài xế trộm xăng: https://plo.vn/dinh-chi-tai-xe-trom-xang-tren-quoc-lo-post342535.html
- KB08: Viện Kiểm sát nhân dân tối cao, tội phạm tham nhũng ngoài Nhà nước: https://vksndtc.gov.vn/tin-tuc/cong-tac-kiem-sat/toi-pham-tham-nhung-ngoai-nha-nuoc-theo-phap-luat--d10-t13551.html
- KB08: Liên đoàn Luật sư Việt Nam, dấu hiệu định tội nhận hối lộ: https://lsvn.vn/quy-dinh-cua-bo-luat-hinh-su-ve-dau-hieu-dinh-toi-doi-voi-toi-nhan-hoi-lo1619001422-a103182.html
- KB09: Tiền Phong, doanh nghiệp gian lận bằng hai sổ sách: https://tienphong.vn/Kinh-Te/590095/Doanh-nghiep-gian-lan-bang-hai-so-sach-tpp.html
- KB09: VnEconomy, nghiêm cấm lập hai hệ thống sổ kế toán: https://vneconomy.vn/nghiem-cam-lap-hai-he-thong-so-ke-toan-tro-len.htm
- KB10: Luật Minh Khuê, nhân viên bán hàng không thu tiền về nộp quỹ: https://luatminhkhue.vn/viec-nhan-vien-ban-hang-khong-thu-tien-ve-nop-quy-cho-cong-ty--.aspx
- KB01, KB10: Caselaw, Thông tư 48/2019/TT-BTC: https://caselaw.vn/van-ban-phap-luat/331907-thong-tu-so-48-2019-tt-btc-ngay-08-08-2019-cua-bo-truong-bo-tai-chinh-huong-dan-viec-trich-lap-va-xu-ly-cac-khoan-du-phong-giam-gia-hang-ton-kho-ton-that-cac-khoan-dau-tu-no-phai-thu-kho-doi-va-bao-hanh-san-pham-hang-hoa-dich-vu-cong-trinh-xay-dung-tai-doanh-nghiep

### Văn bản pháp luật dẫn theo hiểu biết nghiệp vụ (mục 3 của brief)

- Luật Kế toán 2015, Điều 13 (hành vi bị nghiêm cấm).
- Bộ luật Lao động 2019, Điều 46, 47, 48; Nghị định 145/2020/NĐ-CP.
- Bộ luật Hình sự 2015 sửa đổi 2017, Điều 175, 353, 354.
- Thông tư 133/2016/TT-BTC và Thông tư 200/2014/TT-BTC (chế độ kế toán).
- Thông tư 45/2013/TT-BTC (tài sản cố định và khấu hao).
- Thông tư 48/2019/TT-BTC (dự phòng và xử lý nợ phải thu khó đòi).
- Thông tư 96/2015/TT-BTC (chứng từ thanh toán không dùng tiền mặt từ 20 triệu đồng).
- Thông tư 111/2013/TT-BTC (khấu trừ thuế thu nhập cá nhân 10 phần trăm).
- Nghị định 123/2020/NĐ-CP (hóa đơn điện tử, thời điểm lập hóa đơn).
