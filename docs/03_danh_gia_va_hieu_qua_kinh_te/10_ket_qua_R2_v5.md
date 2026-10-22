# Kết quả R2 v5 trên dữ liệu tổng hợp

Tự sinh bởi `scripts/report_r2.py` từ `results/v5/R2/`. Mọi số là **dữ liệu tổng hợp**; quy tắc theo đăng ký R1 v1.2. R = recall@B3 ở S2; B = trung bình recall các nhánh ACFE bị ẩn (gộp nhánh nhỏ); Q = (R + B) / 2; J = trung bình Q của 20% thế giới thấp nhất.

## 1. Chọn trọng số PU (L4-FB-PU, 8 thế giới sàng lọc, seed 0)

| w | J | Hợp lệ |
|---:|---:|:-:|
| 0.1 | 70,3 | Không |
| 0.2 | 69,1 | Không |
| 0.5 | 67,2 | Không |

Khóa: **w = 0.1** (trạng thái `no_eligible_weight`). Không w nào hợp lệ theo trần ca khó 15%; áp mục Làm rõ khóa w của đăng ký (w có J cao nhất, trần không đổi).

## 2. Sàng lọc 4 ứng viên có giám sát

| Cấu hình | J | Q nhỏ nhất | Q trung bình | R trung bình | R nhỏ nhất | B trung bình | Hợp lệ (ca khó ≤ 15%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| L3-PU | 70,3 | 69,8 | 73,8 | 89,3 | 84,5 | 58,2 | Không |
| L4-FB-PU | 70,3 | 69,5 | 74,4 | 89,5 | 82,3 | 59,3 | Không |
| L4-PU-E2-AR | 70,3 | 70,3 | 74,2 | 89,7 | 84,5 | 58,7 | Không |
| L4-PU-E2-AR-2plus1 | 65,4 | 65,3 | 69,2 | 82,4 | 77,5 | 55,9 | Không |

Ba ứng viên vào tầng chọn: **không có**.

## 3. Cold (không nhãn), 20 thế giới

| Cấu hình | J | Q nhỏ nhất | Q trung bình | R trung bình | R nhỏ nhất | B trung bình | Hợp lệ (ca khó ≤ 15%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cold-Rules-E2 | 15,8 | 14,5 | 21,8 | 21,8 | 12,1 | 21,8 | Không |
| Cold-v4 | 29,8 | 27,7 | 37,6 | 37,4 | 24,9 | 37,8 | Không |

Chọn: **None**. Chốt chặn Cold: **không đạt**.

## 4. Tầng chọn có giám sát (20 thế giới, 5 seed)

| Cấu hình | J | Q nhỏ nhất | Q trung bình | R trung bình | R nhỏ nhất | B trung bình | Hợp lệ (ca khó ≤ 15%) |
|---|---:|---:|---:|---:|---:|---:|---:|

Chọn: **None**. Chốt chặn trước niêm phong: **KHÔNG ĐẠT** (quyết định `stop_without_generating_sealed_worlds`).

## Phụ lục: từng thế giới, tầng screening

| Thế giới | Cấu hình | R | B | Q | Ca khó tối đa | Hợp lệ |
|---|---|---:|---:|---:|---:|:-:|
| 1001 | L3-PU | 88,1 | 53,6 | 70,8 | 16,6 | Không |
| 1002 | L3-PU | 93,4 | 60,1 | 76,8 | 14,5 | Có |
| 1003 | L3-PU | 84,5 | 57,5 | 71,0 | 15,0 | Có |
| 1004 | L3-PU | 86,2 | 53,4 | 69,8 | 18,8 | Không |
| 1005 | L3-PU | 91,3 | 68,2 | 79,7 | 17,2 | Không |
| 1006 | L3-PU | 90,2 | 51,7 | 71,0 | 12,0 | Có |
| 1007 | L3-PU | 89,2 | 54,6 | 71,9 | 17,8 | Không |
| 1008 | L3-PU | 91,6 | 66,5 | 79,1 | 14,0 | Có |
| 1001 | L4-PU-E2-AR | 88,1 | 52,5 | 70,3 | 15,5 | Không |
| 1002 | L4-PU-E2-AR | 93,0 | 60,9 | 77,0 | 13,7 | Có |
| 1003 | L4-PU-E2-AR | 84,5 | 56,2 | 70,4 | 14,8 | Có |
| 1004 | L4-PU-E2-AR | 85,4 | 55,4 | 70,4 | 16,9 | Không |
| 1005 | L4-PU-E2-AR | 90,6 | 68,0 | 79,3 | 16,3 | Không |
| 1006 | L4-PU-E2-AR | 91,7 | 51,5 | 71,6 | 11,1 | Có |
| 1007 | L4-PU-E2-AR | 92,3 | 58,4 | 75,4 | 16,6 | Không |
| 1008 | L4-PU-E2-AR | 92,0 | 67,0 | 79,5 | 13,2 | Có |
| 1001 | L4-PU-E2-AR-2plus1 | 79,4 | 51,6 | 65,5 | 14,8 | Có |
| 1002 | L4-PU-E2-AR-2plus1 | 86,5 | 59,6 | 73,0 | 14,4 | Có |
| 1003 | L4-PU-E2-AR-2plus1 | 77,7 | 58,6 | 68,2 | 15,2 | Không |
| 1004 | L4-PU-E2-AR-2plus1 | 77,5 | 53,1 | 65,3 | 17,9 | Không |
| 1005 | L4-PU-E2-AR-2plus1 | 85,1 | 58,6 | 71,8 | 16,2 | Không |
| 1006 | L4-PU-E2-AR-2plus1 | 83,7 | 48,3 | 66,0 | 11,7 | Có |
| 1007 | L4-PU-E2-AR-2plus1 | 83,8 | 54,1 | 69,0 | 16,8 | Không |
| 1008 | L4-PU-E2-AR-2plus1 | 85,7 | 63,6 | 74,7 | 13,7 | Có |

## Phụ lục: từng thế giới, tầng selection

| Thế giới | Cấu hình | R | B | Q | Ca khó tối đa | Hợp lệ |
|---|---|---:|---:|---:|---:|:-:|
| 1001 | Cold-Rules-E2 | 22,2 | 23,9 | 23,1 | 13,1 | Có |
| 1002 | Cold-Rules-E2 | 30,7 | 28,8 | 29,8 | 12,9 | Có |
| 1003 | Cold-Rules-E2 | 17,7 | 17,2 | 17,5 | 12,3 | Có |
| 1004 | Cold-Rules-E2 | 12,1 | 16,9 | 14,5 | 16,2 | Không |
| 1005 | Cold-Rules-E2 | 15,6 | 20,5 | 18,1 | 14,9 | Có |
| 1006 | Cold-Rules-E2 | 20,7 | 17,0 | 18,8 | 10,7 | Có |
| 1007 | Cold-Rules-E2 | 23,9 | 24,7 | 24,3 | 14,7 | Có |
| 1008 | Cold-Rules-E2 | 30,3 | 27,8 | 29,0 | 11,2 | Có |
| 1009 | Cold-Rules-E2 | 29,1 | 27,6 | 28,4 | 15,9 | Không |
| 1010 | Cold-Rules-E2 | 22,4 | 18,1 | 20,3 | 12,5 | Có |
| 1011 | Cold-Rules-E2 | 22,2 | 22,4 | 22,3 | 12,0 | Có |
| 1012 | Cold-Rules-E2 | 15,2 | 18,8 | 17,0 | 12,8 | Có |
| 1013 | Cold-Rules-E2 | 24,5 | 24,2 | 24,3 | 18,5 | Không |
| 1014 | Cold-Rules-E2 | 12,9 | 18,8 | 15,8 | 11,8 | Có |
| 1015 | Cold-Rules-E2 | 13,9 | 17,5 | 15,7 | 15,9 | Không |
| 1016 | Cold-Rules-E2 | 25,9 | 18,5 | 22,2 | 13,4 | Có |
| 1017 | Cold-Rules-E2 | 28,5 | 23,9 | 26,2 | 15,9 | Không |
| 1018 | Cold-Rules-E2 | 25,4 | 23,0 | 24,2 | 14,1 | Có |
| 1019 | Cold-Rules-E2 | 20,0 | 23,0 | 21,5 | 10,9 | Có |
| 1020 | Cold-Rules-E2 | 22,1 | 23,1 | 22,6 | 16,2 | Không |
| 1001 | Cold-v4 | 40,7 | 42,4 | 41,6 | 13,9 | Có |
| 1002 | Cold-v4 | 40,2 | 37,5 | 38,8 | 13,1 | Có |
| 1003 | Cold-v4 | 32,7 | 33,9 | 33,3 | 12,9 | Có |
| 1004 | Cold-v4 | 26,7 | 30,1 | 28,4 | 16,4 | Không |
| 1005 | Cold-v4 | 38,0 | 42,5 | 40,3 | 15,3 | Không |
| 1006 | Cold-v4 | 43,1 | 42,6 | 42,9 | 11,0 | Có |
| 1007 | Cold-v4 | 42,3 | 43,4 | 42,9 | 16,1 | Không |
| 1008 | Cold-v4 | 42,0 | 39,8 | 40,9 | 12,5 | Có |
| 1009 | Cold-v4 | 42,2 | 42,7 | 42,5 | 16,2 | Không |
| 1010 | Cold-v4 | 41,4 | 38,2 | 39,8 | 13,6 | Có |
| 1011 | Cold-v4 | 33,3 | 32,9 | 33,1 | 12,8 | Có |
| 1012 | Cold-v4 | 29,6 | 30,2 | 29,9 | 13,6 | Có |
| 1013 | Cold-v4 | 44,2 | 47,7 | 45,9 | 18,9 | Không |
| 1014 | Cold-v4 | 24,9 | 30,5 | 27,7 | 12,8 | Có |
| 1015 | Cold-v4 | 32,5 | 38,3 | 35,4 | 16,2 | Không |
| 1016 | Cold-v4 | 37,9 | 30,1 | 34,0 | 14,8 | Có |
| 1017 | Cold-v4 | 42,7 | 40,6 | 41,6 | 16,0 | Không |
| 1018 | Cold-v4 | 40,4 | 39,0 | 39,7 | 15,6 | Không |
| 1019 | Cold-v4 | 35,1 | 35,1 | 35,1 | 12,0 | Có |
| 1020 | Cold-v4 | 37,8 | 39,4 | 38,6 | 17,2 | Không |

