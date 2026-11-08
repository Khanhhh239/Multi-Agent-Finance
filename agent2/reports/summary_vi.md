# Benchmark tổng hợp SME Việt Nam v2

Seed 20261012. Mỗi bộ 100.000 quan sát, 5.000 hard negatives; nhãn/splits giữ nguyên so với v1.
IF 300 cây, max_samples=2048, 190 đặc trưng. Ngưỡng lấy từ validation chưa gán nhãn với ngân sách 0,3%.

| Prevalence | Gian lận test | AP | Precision | Recall | Cảnh báo sai | Tổng cảnh báo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1% | 25 | 0.0067 | 1.5% | 4.0% | 64 | 65 |
| 0.3% | 75 | 0.0342 | 6.4% | 6.7% | 73 | 78 |
| 0.5% | 125 | 0.0533 | 9.2% | 4.8% | 59 | 65 |

| Prevalence | AP v1 | AP v2 | Precision v1 → v2 | Recall v1 → v2 |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 0.0174 | 0.0067 | 2.3% → 1.5% | 8.0% → 4.0% |
| 0.3% | 0.0457 | 0.0342 | 10.0% → 6.4% | 10.7% → 6.7% |
| 0.5% | 0.0817 | 0.0533 | 20.3% → 9.2% | 9.6% → 4.8% |

AP/precision/recall v2 giảm trong seed này. Sửa biểu diễn kế toán và thêm cột chưa cải thiện IF; không chọn lại ngưỡng theo test.
Đây là đo trên dữ liệu tổng hợp, không ước lượng hiệu quả thực địa. Test 0,1% chỉ có 25 dòng gian lận.

Kiểm chứng: 15 tests về kế toán, tái lập và chống rò rỉ; kiểm tra toàn bộ 3 bộ dữ liệu; nạp lại 3 model và đối chiếu 300 điểm test/model.
Cặp tài khoản multi-hot bao gồm dòng VAT/dự phòng; 641/642 chuẩn hóa ở lớp ML, sổ cái giữ mã TT133/TT200.
Báo cáo metrics.json từng bộ có FPR riêng theo chế độ kế toán, nhóm hard negative và recall theo vụ/biến thể.
