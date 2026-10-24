# Kết quả niêm phong v6: S2 TRƯỢT một cổng (lệch với phát triển), bốn cổng còn lại ĐẠT

Chấm đúng một lần lúc 15:54 ngày 2026-10-24 trên bốn thế giới niêm phong 5101 đến 5104 (`results/v6/sealed_v6.json`). Mọi số là **dữ liệu tổng hợp**. Cấu hình và mã đã khóa trước khi sinh dữ liệu (`results/v6/v6_frozen.json`, commit `355496c`): L4-FB-PU, w = 0,1, h = 0,5, huấn luyện trên cả 20 thế giới phát triển, năm seed. Theo mục 7 của đăng ký v5 và đăng ký v6: **giữ nguyên kết quả, không sửa rồi chấm lại, không mở vòng v7.** Bốn thế giới niêm phong nay đã dùng hết.

## 1. Quyết định theo cổng

| Cổng V5-S2 (giống hệt v5 mục 5) | Giá trị đo | Yêu cầu | Kết quả |
|---|---:|---:|:-:|
| Recall chung trung bình bốn thế giới | 64,5% | từ 60% | **Đạt** |
| Recall trên kịch bản mới của tác giả | 41,2% | từ 35% | **Đạt** |
| Recall thế giới thấp nhất | 58,9% | từ 45% | **Đạt** |
| Lệch với recall phát triển (88,4%) | 23,9 điểm | không quá 15 điểm | **KHÔNG ĐẠT** |
| Cảnh báo nhầm trên ca hợp lệ khó, thế giới cao nhất | 12,8% | không quá 15% | **Đạt** |
| Cold | không chạy | không chào bán Cold | không áp dụng |

Các cổng là điều kiện đồng thời, nên **kết luận chính thức của v6 là S2 trượt cổng niêm phong.** Cần đọc đúng: bốn trên năm điều kiện đạt, và điều kiện trượt là điều kiện về **độ lệch giữa phát triển và đề mới**, không phải về mức bắt gian lận tuyệt đối.

## 2. Từng thế giới niêm phong

| Thế giới | Recall chung (khoảng 95%) | Kịch bản đã biết | Kịch bản mới | Báo nhầm ca hợp lệ khó | Báo nhầm riêng ca hợp lệ mới của tác giả |
|---|---:|---:|---:|---:|---:|
| 5101 | 67,1% (57,4 đến 76,4) | 86,8% | 46,4% | 7,6% | 12,5% |
| 5102 | 69,1% (58,9 đến 79,1) | 96,9% | 43,8% | 12,8% | 18,3% |
| 5103 | 58,9% (49,2 đến 69,7) | 81,7% | 40,3% | 12,3% | 18,4% |
| 5104 | 62,7% (51,8 đến 74,3) | 96,6% | 34,4% | 12,8% | 19,7% |
| Trung bình | **64,5%** | khoảng 91% | **41,2%** | cao nhất 12,8% | 12,5% đến 19,7% |

Khoảng 95% tính theo vụ, mỗi thế giới chỉ có 78 đến 87 vụ, nên khoảng rộng khoảng 20 điểm. Chênh lệch giữa các thế giới nằm trong sai số.

## 3. Từng kịch bản mới của tác giả (trung bình bốn thế giới)

| Kịch bản | Recall | Nhận xét |
|---|---:|---|
| KB05 hoa hồng cho cộng tác viên giả | 98,6% | bắt gần hết, nhà cung cấp cá nhân mới và khoản chi định kỳ |
| KB07 xe tải chở thuê | 66,0% | |
| KB08 đòi phí để thanh toán đúng hạn | 57,5% | |
| KB01 thu tiền công nợ ngoài sổ | 55,7% | |
| KB04 trợ cấp thôi việc kê tăng | 48,2% | mức khó gần như không phân biệt được bằng số tiền |
| KB06 thanh lý tài sản cho người có quan hệ | 46,9% | bản mã hóa rút gọn (không có sổ tài sản) |
| KB02 chặn tiền hoàn cọc | 44,9% | |
| KB09 dời chi phí cuối kỳ | 26,2% | thể hiện ở cuối quý, không phải cuối năm |
| KB10 nới hạn nợ cho khách có quan hệ | 12,2% | vụ bị cắt trong kỳ test, mất giai đoạn xóa nợ |
| KB03 kê tăng công tác phí | 0,0% | kê thêm 1 đến 2 ngày khoán, dấu vết quá nhỏ trong sổ |

## 4. Điều cần đọc thẳng

- **Mức bắt gian lận thật nằm khoảng 64%, không phải 88%.** Số 88,4% của phát triển cao hơn khoảng 24 điểm, đúng như đợt v4 (khoảng 90% phát triển xuống 64% niêm phong). Mọi con số quảng bá hay kế hoạch kinh tế phải dùng mức niêm phong.
- **Tiến bộ so với v4 là có thật nhưng khiêm tốn:** S2 tổng 64,5% so với 63,9% của v4; kịch bản mới 41,2% so với 31,2% của v4. Đề khác nhau (tác giả và kịch bản khác), nên không so trực tiếp được.
- **Cải tiến về cảnh báo nhầm giữ được trên đề mới:** 12,8% so với trần 15%, trong khi v5 vượt 18,8% ở phát triển. Nhưng riêng các tình huống hợp lệ **mới** của tác giả, mô hình chưa từng thấy nhãn, cảnh báo nhầm vẫn 12,5% đến 19,7% và vượt 15% ở ba trên bốn thế giới. Cổng chỉ đo trên tổng ca hợp lệ khó nên đạt, nhưng đây là rủi ro khi triển khai.
- **Mức che giấu thể hiện trong dữ liệu quan sát rất khác nhau giữa các kịch bản**: có kịch bản bắt gần hết (KB05), có kịch bản gần như không bắt được (KB03, KB10, KB09). Phần lớn lý do là cách dữ liệu quan sát thể hiện chúng, như ghi trong `encoding_notes_v5.md`.

## 5. Hệ quả cho sản phẩm

Theo mục 7: không quảng bá phát hiện gian lận tự động. Hướng phù hợp là **dịch vụ rà soát định kỳ cho đơn vị kế toán**: kết quả xếp hạng làm công cụ **gợi ý thứ tự ưu tiên** cho kế toán viên, kèm lý do kiểm được số, con người quyết định. Chi tiết và các việc cần đo trong thí điểm: `01_phan_tich_kinh_te_va_nghiep_vu/09_de_xuat_doi_huong_dich_vu_ra_soat.md`.

Điều kiện triển khai của mô hình v6: cần một kho kết luận "hợp lệ" do kế toán viên xác nhận, dùng chung giữa các khách. Không có dữ liệu thật hay thí điểm nào được dùng trong báo cáo này.
