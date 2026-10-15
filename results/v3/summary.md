# Tổng hợp 5 seed

## Giao thức theo thời gian (huấn luyện 2024, kiểm thử nửa cuối 2025)

| Phương pháp | Chế độ | AP | R-precision | P@B3 (%) | Recall@B3 (%) | Vụ tìm thấy@B3 (%) | Báo nhầm ca hợp lệ giống gian lận (%) | Cảnh báo/1000 dòng |
|---|:-:|---:|---:|---:|---:|---:|---:|---:|
| Rules | R | 0.240 ± 0.019 | 0.235 ± 0.020 | 3.6 ± 0.2 | 30.9 ± 1.5 | 43.4 ± 2.1 | 2.9 ± 0.5 | 25.9 ± 0.0 |
| Rules+Graph | R | 0.245 ± 0.013 | 0.240 ± 0.009 | 3.8 ± 0.2 | 32.8 ± 1.5 | 45.4 ± 1.8 | 3.0 ± 0.5 | 25.9 ± 0.0 |
| IF[friend190] (friend baseline) | U | 0.021 ± 0.013 | 0.029 ± 0.011 | 1.1 ± 0.2 | 9.9 ± 1.5 | 14.7 ± 1.9 | 13.1 ± 0.4 | 25.9 ± 0.0 |
| IF[U] | U | 0.021 ± 0.009 | 0.064 ± 0.022 | 1.7 ± 0.5 | 14.9 ± 4.8 | 20.3 ± 5.3 | 17.5 ± 0.9 | 25.9 ± 0.0 |
| ECOD[U] | U | 0.005 ± 0.001 | 0.008 ± 0.012 | 0.6 ± 0.6 | 5.1 ± 5.2 | 4.4 ± 3.6 | 5.3 ± 0.8 | 25.9 ± 0.0 |
| AE[U] | U | 0.065 ± 0.020 | 0.101 ± 0.033 | 3.8 ± 0.7 | 32.8 ± 5.7 | 45.8 ± 7.4 | 20.3 ± 3.9 | 25.9 ± 0.0 |
| HBOS[U] | U | 0.004 ± 0.001 | 0.005 ± 0.007 | 0.5 ± 0.4 | 4.3 ± 3.5 | 5.1 ± 4.1 | 5.5 ± 0.9 | 25.9 ± 0.0 |
| EntityDeviation | U | 0.012 ± 0.002 | 0.021 ± 0.015 | 1.9 ± 0.2 | 16.5 ± 1.5 | 11.2 ± 2.0 | 7.8 ± 1.5 | 25.9 ± 0.0 |
| Gate(Rules,ECOD) | H | 0.242 ± 0.013 | 0.229 ± 0.011 | 3.8 ± 0.2 | 32.8 ± 1.8 | 45.0 ± 2.5 | 3.0 ± 0.5 | 25.9 ± 0.0 |
| Blend .8 Rules + .2 IF (friend ensemble) | H | 0.163 ± 0.023 | 0.205 ± 0.015 | 3.9 ± 0.1 | 33.9 ± 1.2 | 49.4 ± 2.3 | 7.7 ± 0.4 | 25.9 ± 0.0 |
| Fusion max(Rules,Entity) | H | 0.190 ± 0.058 | 0.240 ± 0.025 | 4.4 ± 0.4 | 38.4 ± 3.8 | 45.8 ± 2.1 | 6.1 ± 1.0 | 25.9 ± 0.0 |
| Rules (weights learned) | S | 0.387 ± 0.019 | 0.400 ± 0.019 | 5.5 ± 0.4 | 47.5 ± 3.1 | 64.2 ± 3.7 | 3.7 ± 1.3 | 25.9 ± 0.0 |
| LGBM[friend190] | S | 0.633 ± 0.046 | 0.613 ± 0.041 | 8.7 ± 0.5 | 74.9 ± 4.4 | 86.8 ± 3.8 | 11.9 ± 2.2 | 25.9 ± 0.0 |
| LGBM[friend190+eng] | S | 0.805 ± 0.049 | 0.760 ± 0.051 | 10.2 ± 0.3 | 88.0 ± 2.7 | 93.6 ± 4.9 | 18.4 ± 1.9 | 25.9 ± 0.0 |
| LGBM[friend190+eng+rules] | S | 0.817 ± 0.022 | 0.763 ± 0.037 | 10.3 ± 0.3 | 88.8 ± 2.2 | 94.9 ± 2.9 | 16.1 ± 1.3 | 25.9 ± 0.0 |
| Fusion max(L3,Rules,Entity) | H | 0.521 ± 0.159 | 0.523 ± 0.118 | 9.8 ± 0.5 | 85.1 ± 3.9 | 92.8 ± 2.4 | 10.0 ± 0.9 | 25.9 ± 0.0 |
| Fusion max(Rules,Entity,AE) | H | 0.173 ± 0.048 | 0.248 ± 0.024 | 5.1 ± 0.7 | 43.7 ± 6.4 | 55.0 ± 4.7 | 14.6 ± 1.9 | 25.9 ± 0.0 |

## Recall@B3 (%) theo họ gian lận

| Phương pháp | duplicate_payment | expense_padding | ghost_vendor | kickback_overpricing | long_outstanding_advance | payroll_padding | period_end_adjustment | risky_invoice | split_payments |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules | 47 | 0 | 51 | 0 | 62 | 0 | 70 | 28 | 18 |
| Rules+Graph | 47 | 0 | 62 | 0 | 60 | 0 | 70 | 28 | 24 |
| IF[friend190] (friend baseline) | 0 | 0 | 2 | 0 | 78 | 8 | 5 | 0 | 0 |
| IF[U] | 9 | 0 | 4 | 2 | 80 | 32 | 5 | 0 | 4 |
| ECOD[U] | 13 | 0 | 0 | 32 | 0 | 0 | 0 | 0 | 0 |
| AE[U] | 47 | 0 | 71 | 5 | 65 | 0 | 30 | 57 | 16 |
| HBOS[U] | 11 | 0 | 0 | 25 | 0 | 0 | 0 | 0 | 2 |
| EntityDeviation | 0 | 2 | 0 | 80 | 0 | 65 | 8 | 0 | 0 |
| Gate(Rules,ECOD) | 44 | 0 | 62 | 2 | 60 | 0 | 70 | 25 | 27 |
| Blend .8 Rules + .2 IF (friend ensemble) | 38 | 0 | 64 | 2 | 100 | 2 | 62 | 25 | 9 |
| Fusion max(Rules,Entity) | 42 | 0 | 51 | 65 | 52 | 40 | 68 | 20 | 9 |
| Rules (weights learned) | 40 | 5 | 100 | 12 | 100 | 10 | 72 | 52 | 31 |
| LGBM[friend190] | 91 | 92 | 82 | 2 | 100 | 65 | 85 | 95 | 60 |
| LGBM[friend190+eng] | 87 | 88 | 84 | 90 | 100 | 82 | 95 | 100 | 69 |
| LGBM[friend190+eng+rules] | 84 | 90 | 100 | 80 | 100 | 80 | 92 | 100 | 73 |
| Fusion max(L3,Rules,Entity) | 82 | 82 | 100 | 72 | 98 | 75 | 92 | 95 | 69 |
| Fusion max(Rules,Entity,AE) | 44 | 0 | 82 | 55 | 52 | 30 | 68 | 48 | 13 |

**Recall@B3 (%) trên họ gian lận chưa từng thấy khi huấn luyện (trung bình 5 seed)**

| Phương pháp (huấn luyện không có họ đó) | duplicate_payment | expense_padding | ghost_vendor | kickback_overpricing | long_outstanding_advance | payroll_padding | period_end_adjustment | risky_invoice | split_payments | trung bình |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LGBM[friend190] | 11 | 0 | 29 | 5 | 10 | 22 | 10 | 45 | 9 | 16 |
| L3 | 20 | 30 | 91 | 42 | 60 | 0 | 82 | 88 | 49 | 51 |
| Rules+Graph | 44 | 0 | 64 | 2 | 62 | 0 | 70 | 28 | 31 | 34 |
| EntityDeviation | 0 | 5 | 0 | 80 | 0 | 82 | 8 | 0 | 0 | 19 |
| Fusion max(Rules,Entity) | 42 | 0 | 53 | 68 | 52 | 78 | 68 | 18 | 13 | 43 |
| Fusion max(L3,Rules,Entity) | 47 | 8 | 89 | 65 | 57 | 72 | 75 | 70 | 42 | 58 |

**AP trên họ chưa từng thấy (nền: 0,003 nếu ngẫu nhiên; AP tính trên họ đó cùng toàn bộ dòng hợp lệ)**

| Phương pháp | duplicate_payment | expense_padding | ghost_vendor | kickback_overpricing | long_outstanding_advance | payroll_padding | period_end_adjustment | risky_invoice | split_payments | trung bình |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LGBM[friend190] | 0.00 | 0.00 | 0.04 | 0.00 | 0.00 | 0.01 | 0.00 | 0.02 | 0.00 | 0.01 |
| L3 | 0.01 | 0.00 | 0.42 | 0.03 | 0.16 | 0.00 | 0.56 | 0.31 | 0.06 | 0.17 |
| Rules+Graph | 0.40 | 0.00 | 0.45 | 0.00 | 0.50 | 0.00 | 0.65 | 0.01 | 0.01 | 0.22 |
| EntityDeviation | 0.00 | 0.00 | 0.00 | 0.03 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.01 |
| Fusion max(Rules,Entity) | 0.20 | 0.00 | 0.24 | 0.02 | 0.22 | 0.02 | 0.48 | 0.00 | 0.00 | 0.13 |
| Fusion max(L3,Rules,Entity) | 0.20 | 0.00 | 0.30 | 0.02 | 0.22 | 0.02 | 0.49 | 0.06 | 0.01 | 0.15 |

**Công ty chưa từng thấy (huấn luyện trên 7 công ty còn lại, cùng thế giới)**

| Phương pháp | AP | R-precision | P@B3 (%) | Recall@B3 (%) |
|---|---:|---:|---:|---:|
| LGBM[friend190] | 0.570 ± 0.052 | 0.541 ± 0.060 | 8.1 ± 0.5 | 69.6 ± 4.4 |
| LGBM[friend190+eng] | 0.752 ± 0.068 | 0.712 ± 0.069 | 10.0 ± 0.5 | 86.4 ± 4.0 |
| LGBM[friend190+eng+rules] | 0.779 ± 0.077 | 0.720 ± 0.091 | 10.0 ± 0.4 | 86.1 ± 3.3 |
