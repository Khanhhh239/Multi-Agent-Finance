# Kết quả v5: chốt chặn trước niêm phong KHÔNG ĐẠT, không sinh và không chấm niêm phong

Tự sinh bởi `scripts/report_r2.py`. Mọi số là **dữ liệu tổng hợp**. Theo mục 5 và mục 7 của đăng ký (`docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md`): giữ nguyên kết quả, không sửa rồi chấm lại, không mở vòng v6, **không sinh và không chấm thế giới niêm phong v5**.

## 1. Ứng viên S2 đã chọn: không có (không ứng viên nào hợp lệ)

Không còn ứng viên hợp lệ dưới trần ca khó 15%.

## Bằng chứng: tầng sàng lọc (8 thế giới, seed 0)

| Cấu hình | R trung bình | R nhỏ nhất | B trung bình | Thế giới vượt trần 15% | Mức cảnh báo nhầm cao nhất | Hợp lệ |
|---|---:|---:|---:|---:|---:|:-:|
| L3-PU | 89,3 | 84,5 | 58,2 | 4 trên 8 | 18,8 | Không |
| L4-FB-PU | 89,5 | 82,3 | 59,3 | 5 trên 8 | 18,6 | Không |
| L4-PU-E2-AR | 89,7 | 84,5 | 58,7 | 4 trên 8 | 16,9 | Không |
| L4-PU-E2-AR-2plus1 | 82,4 | 77,5 | 55,9 | 4 trên 8 | 17,9 | Không |

Recall chung và recall nhánh bị ẩn của cả bốn ứng viên đều cao hơn ngưỡng chốt chặn (65% và 40%), nhưng **không ứng viên nào giữ được cảnh báo nhầm trên ca hợp lệ khó dưới 15% ở mọi thế giới và mọi giao thức**. Trần này là điều kiện hợp lệ trước mọi so sánh, nên không có ứng viên vào tầng chọn. Đây là số trên dữ liệu phát triển; kinh nghiệm v4 cho thấy điểm niêm phong thường thấp hơn nhiều.

## Cold (không nhãn, 20 thế giới)

| Cold | R trung bình | R nhỏ nhất | B trung bình | Hợp lệ |
|---|---:|---:|---:|:-:|
| Cold-Rules-E2 | 21,8 | 12,1 | 21,8 | Không |
| Cold-v4 | 37,4 | 24,9 | 37,8 | Không |

Chốt chặn Cold (R từ 40%, B từ 33%, thế giới tệ nhất từ 30%, trần 15%) không đạt: không ứng viên Cold nào hợp lệ. Vì S2 không đạt, Cold không được chào bán riêng và cũng không được chấm niêm phong.

## 2. Đề xuất đổi hướng

Hướng trình chủ dự án là **dịch vụ rà soát định kỳ cho đơn vị kế toán**: quy tắc bằng chứng rõ, đối chiếu chứng từ, hàng đợi để con người quyết định. Chưa quảng bá phát hiện gian lận tự động hoặc thu hồi tổn thất dựa trên dữ liệu tổng hợp. Chi tiết: [đề xuất đổi hướng](../01_phan_tich_kinh_te_va_nghiep_vu/09_de_xuat_doi_huong_dich_vu_ra_soat.md).

| Nội dung mục 7 yêu cầu | Ở đâu trong đề xuất |
|---|---|
| Công việc kế toán được hỗ trợ | Mục 2 |
| Phần vẫn phải do con người | Mục 3 |
| Ngân sách cảnh báo và thời gian | Mục 4 |
| Phép đo đáng kiểm tra, thời gian rà soát, mức sẵn lòng trả cần thu trong thí điểm | Mục 5 |

Các con số thí điểm chỉ được xác lập sau đồng ý pháp lý và doanh nghiệp; không thay bằng số tổng hợp.

