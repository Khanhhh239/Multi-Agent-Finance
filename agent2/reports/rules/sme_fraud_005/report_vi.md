# Bộ luật và benchmark phát hiện SME

Dữ liệu v2.0, seed 20261012; test 25,000 quan sát, 125 gian lận (0.5%).
Đọc 6 nhóm A–F gồm 31 quy tắc; bổ sung P1/T1/T2 để giữ phạm vi sáu loại gian lận ban đầu.
Ngân sách validation 0.3%; bảng dưới so sánh cùng sức chứa 75 cảnh báo test.

| Phương án | AP | Phát hiện | Precision | Recall | Cảnh báo sai |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules | 0.6571 | 67 | 89.3% | 53.6% | 8 |
| IF | 0.0533 | 8 | 10.7% | 6.4% | 67 |
| Rules+Graph | 0.6700 | 67 | 89.3% | 53.6% | 8 |
| Rules+Graph+IF | 0.5004 | 45 | 60.0% | 36.0% | 30 |

## Ngưỡng validation và vấn đề điểm bằng nhau

| Phương án | Ngưỡng | Tỷ lệ cảnh báo validation | Cảnh báo test | Precision test | Recall test |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules | 14.000000 | 0.44% | 103 | 73.8% | 60.8% |
| IF | 0.527442 | 0.30% | 65 | 9.2% | 4.8% |
| Rules+Graph | 14.000000 | 0.44% | 105 | 72.4% | 60.8% |
| Rules+Graph+IF | 0.977180 | 0.30% | 80 | 58.8% | 37.6% |

Điểm luật rời rạc có nhiều trường hợp bằng nhau. Giữ mọi điểm bằng ngưỡng có thể vượt ngân sách; bảng sức chứa cố định chỉ dùng để so sánh thứ hạng, không lấy phân vị test để chọn ngưỡng vận hành.

Hàng đợi toàn kỳ: 2,821 hồ sơ, 4,013 quan sát có điểm ≥ 7.
Hàng đợi này dùng ngưỡng nghiệp vụ mặc định; không đồng nghĩa bộ cảnh báo đã hiệu chỉnh theo ngân sách.

## Phạm vi triển khai

| Rule | Trạng thái | Ghi chú |
| --- | --- | --- |
| A1 | implemented |  |
| A2 | implemented |  |
| A3 | partial | Gom TK/SĐT/người đại diện; địa chỉ chung đơn lẻ chỉ là tín hiệu yếu B5/E4. |
| A4 | implemented |  |
| A5 | implemented |  |
| A6 | implemented |  |
| B1 | partial | Đối chiếu TK ngân hàng; chưa có CCCD và mã ngân hàng để phân biệt số trùng giữa ngân hàng. |
| B2 | implemented |  |
| B3 | implemented |  |
| B4 | partial | Lịch sử trạng thái tổng hợp theo observed_at; chưa kết nối cổng thuế/ngành nghề. |
| B5 | implemented |  |
| B6 | implemented |  |
| B7 | partial | Có lịch đổi TK/callback/người duyệt; chưa có nguồn email BEC. |
| C1 | implemented |  |
| C2 | implemented |  |
| C3 | implemented |  |
| C4 | not_evaluable | Thiếu lịch nghỉ phép theo ngày và log thao tác; approved_leave_days tổng tháng không đủ. |
| D1 | implemented |  |
| D2 | implemented |  |
| D3 | partial | Hai chữ số đầu cận hạn mức theo từng người lập; sàng lọc thống kê, không chứng minh ý đồ. |
| D4 | partial | Dùng baseline đuôi thực nghiệm kỳ trước thay giả định đuôi phân bố đều. |
| D5 | implemented |  |
| D6 | implemented |  |
| E1 | implemented |  |
| E2 | not_evaluable | Thiếu ngày chấm dứt HĐLĐ, kỳ công và loại khoản quyết toán cuối cùng. |
| E3 | partial | SequenceMatcher trên tên chuẩn hóa là proxy, không phải Levenshtein/Jaro-Winkler. |
| E4 | implemented |  |
| F1 | partial | txn_type=adjustment là proxy thủ công; trọng yếu theo config hoặc hạn mức người lập. |
| F2 | not_evaluable | Thiếu log override, quyền đặc biệt và luồng phê duyệt chuẩn. |
| F3 | not_evaluable | ID giao dịch ngẫu nhiên không phải số chứng từ; thiếu sổ đăng ký số/hủy chứng từ. |
| F4 | not_evaluable | Thiếu liên kết thu tiền-hóa đơn, hạn thanh toán và giải trình công nợ. |
| P1 | implemented |  |
| T1 | implemented |  |
| T2 | implemented |  |

## Giới hạn

- Synthetic single-seed benchmark, not real SME performance.
- Existing test was inspected in prior iterations; use a fresh sealed dataset for final acceptance.
- No retroactive alerts on an earlier payment using a later transaction.
- D-group diagnostics are aggregate screens and do not add transaction scores.
- Queue is an offline snapshot with suggested ownership/SLA, no messages or automatic transaction blocks.
- Rule score/ensemble score are not calibrated fraud probabilities.

Kiểm định Chi-square: [SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html). Ngưỡng Benford là giả định rà soát từ file luật; kiểm tra phạm vi, độ đa dạng và tần suất kỳ vọng trước khi tính p-value; hiệu chỉnh BH theo mỗi thời điểm.
