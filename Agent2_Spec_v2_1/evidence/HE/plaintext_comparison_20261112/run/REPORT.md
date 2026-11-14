# Đối chiếu chấm rõ và chấm mã hóa

**Kết quả đo: PARTIAL**. Dùng cùng model, snapshot, feature và thời điểm nguồn của từng doanh nghiệp.

| Doanh nghiệp | Số GD | Lượt đo | Sai số lớn nhất | Cùng thứ tự mọi lượt | Cặp đảo thứ tự đáng kể | Chấm rõ p50 (ms) | HE p50 (ms) | HE p95 (ms) |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| C001 | 5 | 5 | 1.446e-06 | Có | 0 | 117.79 | 1977.61 | 2072.64 |
| C002 | 5 | 5 | 1.446e-06 | Có | 0 | 116.29 | 2016.48 | 2601.16 |

## C001

Model: `mth_edd87b751e5a56d18e535633650b6026f36ceccd8446c649e0898c594631018b`. Snapshot: `snp_de7dabce8b1d42378e38b4f3a001107a`. `as_of`: 2026-11-12T09:18:57.070816+00:00.

Ngưỡng sai số: |HE − rõ| ≤ 0.001 + 1e-05 × |điểm rõ|. Tất cả lượt đạt: có.

| Mã GD | Điểm rõ | Điểm HE (lượt 1) | Sai số tuyệt đối | Hạng rõ | Hạng HE |
|---|---:|---:|---:|---:|---:|
| T0 | 1.790003676 | 1.790005116 | 1.440e-06 | 1 | 1 |
| T1 | 0.631573548 | 0.631574056 | 5.077e-07 | 4 | 4 |
| T2 | 1.536894734 | 1.536895966 | 1.231e-06 | 2 | 2 |
| T3 | 0.500690433 | 0.500690833 | 3.994e-07 | 5 | 5 |
| T4 | 1.518211245 | 1.518212465 | 1.221e-06 | 3 | 3 |

Thứ tự từ đáng kiểm tra nhất (rõ): T0 → T2 → T4 → T1 → T3.
Thứ tự từ đáng kiểm tra nhất (HE): T0 → T2 → T4 → T1 → T3.
Spearman lượt đầu: 0.9999999999999999. Top-5 trùng 5/5; top-k gồm toàn bộ mẫu: True.

## C002

Model: `mth_8295f280b1cdf994dcd20765954083db9dd93de7e9e012cc26e939459131d983`. Snapshot: `snp_29122f87a21b4829a2c92f145c28e00d`. `as_of`: 2026-11-12T09:18:58.549025+00:00.

Ngưỡng sai số: |HE − rõ| ≤ 0.001 + 1e-05 × |điểm rõ|. Tất cả lượt đạt: có.

| Mã GD | Điểm rõ | Điểm HE (lượt 1) | Sai số tuyệt đối | Hạng rõ | Hạng HE |
|---|---:|---:|---:|---:|---:|
| T0 | 1.790003591 | 1.790005031 | 1.441e-06 | 1 | 1 |
| T1 | 0.631573492 | 0.631574000 | 5.085e-07 | 4 | 4 |
| T2 | 1.536894704 | 1.536895941 | 1.237e-06 | 2 | 2 |
| T3 | 0.500690429 | 0.500690831 | 4.020e-07 | 5 | 5 |
| T4 | 1.518211253 | 1.518212475 | 1.222e-06 | 3 | 3 |

Thứ tự từ đáng kiểm tra nhất (rõ): T0 → T2 → T4 → T1 → T3.
Thứ tự từ đáng kiểm tra nhất (HE): T0 → T2 → T4 → T1 → T3.
Spearman lượt đầu: 0.9999999999999999. Top-5 trùng 5/5; top-k gồm toàn bộ mẫu: True.

## Khôi phục

| Loại sự cố | Thành công / lần ngắt xác nhận | Lần ngắt chưa xác nhận | Tỷ lệ quan sát | Thời gian khôi phục p50 (ms) |
|---|---:|---:|---:|---:|
| Khởi động lại có chờ hoàn tất phép tính | 2/2 | 0 | 100% | 660.99 |
| Mất worker trước khi nhận phép tính | 2/2 | 0 | 100% | 1904.56 |
| Worker chết giữa phép tính, chưa lưu kết quả | 0/2 | 0 | 0% | — |

Không gộp các loại sự cố thành một tỷ lệ chung. Hai doanh nghiệp cho hai ca mặc định mỗi loại; chưa đủ để ước lượng độ tin cậy vận hành.

## Cách đo

- Chấm rõ: kiểm scope, đọc/kiểm model, tạo feature từ snapshot, chuẩn hóa và tính điểm.
- Chấm HE: từ submit tới kết quả đã giải mã/lưu tại DN; gồm kiểm worker, đọc model/feature, mã hóa, checkpoint, HTTP worker và polling.
- Mỗi DN chạy một lượt làm nóng rồi đo 5 lượt mới; đổi thứ tự chạy rõ/HE xen kẽ. Không lấy cache làm số đo lượt chấm mới.
- Timing bình thường không gồm khởi động dịch vụ, fit hoặc Portal/trình duyệt. Timing khôi phục có khởi động lại worker/node.
- Khởi động lại có kiểm soát dùng Jobs.close chờ phép tính xong rồi mở lại cùng state. Ca bấm nút Portal đã có bằng chứng riêng ở lượt nghiệm thu trước.
- Điểm và thứ tự đối chiếu theo mã giao dịch + revision trong đúng DN. Cặp có khoảng cách nhỏ hơn ngân sách sai số không tính là đảo hạng đáng kể.

## Giới hạn

- Dữ liệu mô phỏng, Mahalanobis hai feature; không phải tỷ lệ phát hiện đúng sai phạm.
- Top-5 trên 5 giao dịch luôn bao phủ toàn bộ, không chứng minh ML chọn thêm giao dịch hữu ích.
- Chỉ đo loopback. p95 từ số lượt nhỏ là mô tả mẫu, chưa phải cam kết thời gian cloud.
- Worker chết trước commit vẫn là ca khôi phục không thành công; không đổi nonce, không tự chấm rõ để che lỗi.
- Model, snapshot nguồn và khóa giữ nguyên. Không thay cấu hình hoặc dừng dịch vụ live.

[Dữ liệu đầy đủ từng lượt, thời gian và ca sự cố](comparison.json).
