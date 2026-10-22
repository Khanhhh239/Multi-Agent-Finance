# Kết quả hiện hành

Bảng dưới được sinh trực tiếp từ CSV bởi `scripts/make_report.py`. Các phép đo có
`measurement_version`; CI lấy mẫu lại theo công ty (hoặc đơn vị cụm được ghi rõ).
Một số mục còn thiếu giao thức hoặc thí nghiệm; không coi việc có mã là đã nghiệm thu.

- [Cổng GO/NO-GO hiện hành](GATES_CURRENT.md).
- [Kết quả chưa đạt và giới hạn bằng chứng](KET_QUA_CHUA_DAT.md).
- [Bản lịch sử trước sửa cách đo](04_ket_qua_2026-10-15_lich_su.md).
- [Tiến độ và phần chưa hoàn thành](../05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md).

Kết quả tổng hợp không chứng minh hiệu quả trên doanh nghiệp thật. Nguồn thật tương tự
không thay thế UAT/pilot tại Việt Nam. Không chọn tham số dựa vào điểm kiểm tra đích.

<!-- AUTO:IMPLEMENTATION_RESULTS -->

## T1-A rolling-origin, miền nguồn src

Nguồn: `outputs/t1/A_rolling_origin_src.csv`

Giao thức: asof-pchip-v3-point-mass-fullweek

| setting | model | MAE_p50 | pinball_avg | cov80 | IS80 | IBS_13w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | pinball_ci_low | pinball_ci_high | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_src_origin_2023-07-03 | B0-due | 46.2 | 23.1 | 0.0330 | 462.2 | 0.4152 | 0.4933 | 0.4690 | 1.6395 | 0.8158 | 20.6 | 25.4 | -19.6 | -23.9 | -15.7 | 40 | 300 |
| A_src_origin_2023-07-03 | B1-cust-median | 44.9 | 22.4 | 0.0467 | 448.9 | 0.4018 | 0.4704 | 0.4791 | 1.5251 | 0.8107 | 20.1 | 24.6 | -16.1 | -19.2 | -12.8 | 40 | 300 |
| A_src_origin_2023-07-03 | B1d-cust-quantiles | 44.9 | 19.3 | 0.5061 | 355.5 | 0.3328 | 0.3139 | 0.4795 | 1.3543 | 0.7018 | 16.8 | 21.7 | 0.0000 | 0.0000 | 0.0000 | 40 | 300 |
| A_src_origin_2023-07-03 | DH-GBM | 19.9 | 5.9009 | 0.8769 | 77.7 | 0.1230 | 0.0563 | 0.7826 | 0.4461 | 0.7089 | 5.3989 | 6.3713 | 69.5 | 64.0 | 74.6 | 40 | 300 |
| A_src_origin_2023-07-03 | DH-LR | 21.9 | 6.7272 | 0.8559 | 92.4 | 0.1387 | 0.0323 | 0.7535 | 0.5170 | 0.7326 | 6.3569 | 7.1082 | 65.2 | 58.7 | 70.2 | 40 | 300 |
| A_src_origin_2023-07-03 | QLGBM | 37.7 | 14.8 | 0.4949 | 255.9 | 0.2610 | 0.2052 | 0.5863 | 0.7781 | 0.8025 | 13.1 | 16.8 | 23.3 | 20.7 | 25.8 | 40 | 300 |
| A_src_origin_2023-07-03 | AFT | 21.4 | 8.2752 | 0.4779 | 141.5 | 0.1558 | 0.1370 | 0.7710 | 0.7180 | 0.8507 | 7.4900 | 9.0832 | 57.2 | 48.6 | 64.7 | 40 | 300 |
| A_src_origin_2023-07-03 | ENS DH-GBM+QLGBM | 27.5 | 9.8309 | 0.5969 | 157.5 | 0.1569 | 0.0307 | 0.7700 | 0.5264 | 1.1275 | 9.0852 | 10.7 | 49.1 | 46.2 | 51.6 | 40 | 300 |
| A_src_origin_2023-07-03 | B1d-cust-quantiles+CQR | 44.9 | 11.3 | 0.9138 | 114.2 | 0.2506 | 0.1820 | 0.4795 | 0.9826 | 0.7104 | 10.5 | 12.0 | 41.6 | 37.6 | 44.6 | 40 | 300 |
| A_src_origin_2023-07-03 | DH-GBM+CQR | 19.9 | 5.9228 | 0.8857 | 78.4 | 0.1278 | 0.0687 | 0.7793 | 0.5199 | 0.7739 | 5.4218 | 6.3896 | 69.4 | 63.8 | 74.5 | 40 | 300 |
| A_src_origin_2023-07-03 | QLGBM+CQR | 37.7 | 10.3 | 0.7661 | 121.8 | 0.2146 | 0.1007 | 0.5863 | 0.6668 | 0.7595 | 9.5825 | 11.2 | 46.5 | 43.2 | 49.0 | 40 | 300 |
| A_src_origin_2023-07-03 | AFT+CQR | 21.4 | 7.3845 | 0.7679 | 114.7 | 0.1490 | 0.1108 | 0.7710 | 0.6157 | 0.8235 | 6.6852 | 8.1426 | 61.8 | 54.0 | 68.6 | 40 | 300 |
| A_src_origin_2023-07-03 | ENS DH-GBM+QLGBM+CQR | 27.5 | 7.8360 | 0.7787 | 97.6 | 0.1482 | 0.0594 | 0.7700 | 0.5409 | 1.0012 | 7.5483 | 8.1136 | 59.5 | 54.6 | 63.1 | 40 | 300 |
| A_src_origin_2024-07-01 | B0-due | 35.5 | 17.8 | 0.0407 | 355.2 | 0.3249 | 0.4115 | 0.5221 | 1.2305 | 0.8867 | 15.9 | 19.9 | -23.5 | -28.7 | -19.2 | 40 | 300 |
| A_src_origin_2024-07-01 | B1-cust-median | 34.1 | 17.0 | 0.0528 | 340.5 | 0.3102 | 0.3862 | 0.5384 | 1.1660 | 0.8383 | 15.1 | 19.2 | -18.4 | -22.2 | -15.6 | 40 | 300 |
| A_src_origin_2024-07-01 | B1d-cust-quantiles | 34.0 | 14.4 | 0.5957 | 261.3 | 0.2549 | 0.2204 | 0.5387 | 1.0401 | 0.7397 | 12.5 | 16.5 | 0.0000 | 0.0000 | 0.0000 | 40 | 300 |
| A_src_origin_2024-07-01 | DH-GBM | 16.5 | 5.1834 | 0.8510 | 72.9 | 0.1100 | 0.0161 | 0.7752 | 0.4098 | 0.6928 | 4.7275 | 5.6659 | 64.0 | 56.8 | 70.1 | 40 | 300 |
| A_src_origin_2024-07-01 | DH-LR | 19.4 | 6.1795 | 0.8439 | 88.6 | 0.1318 | 0.0294 | 0.7301 | 0.5078 | 0.7620 | 5.8045 | 6.5527 | 57.0 | 49.8 | 63.3 | 40 | 300 |
| A_src_origin_2024-07-01 | QLGBM | 28.2 | 10.3 | 0.5902 | 169.4 | 0.1918 | 0.1225 | 0.6676 | 0.6069 | 0.8099 | 9.1344 | 11.7 | 28.1 | 25.3 | 31.2 | 40 | 300 |
| A_src_origin_2024-07-01 | AFT | 18.3 | 7.1364 | 0.4668 | 122.5 | 0.1361 | 0.1074 | 0.7707 | 0.6793 | 0.8085 | 6.3369 | 7.9904 | 50.4 | 39.3 | 59.0 | 40 | 300 |
| A_src_origin_2024-07-01 | ENS DH-GBM+QLGBM | 21.8 | 7.5404 | 0.6702 | 117.3 | 0.1315 | 0.0251 | 0.7802 | 0.4923 | 0.9546 | 6.9340 | 8.1178 | 47.6 | 43.7 | 51.4 | 40 | 300 |
| A_src_origin_2024-07-01 | B1d-cust-quantiles+CQR | 34.0 | 9.4558 | 0.9462 | 113.5 | 0.2048 | 0.1291 | 0.5387 | 0.7971 | 0.7581 | 8.7985 | 10.2 | 34.3 | 29.5 | 38.2 | 40 | 300 |
| A_src_origin_2024-07-01 | DH-GBM+CQR | 16.5 | 5.1834 | 0.8510 | 72.9 | 0.1130 | 0.0331 | 0.7836 | 0.4719 | 0.7708 | 4.7275 | 5.6659 | 64.0 | 56.8 | 70.1 | 40 | 300 |
| A_src_origin_2024-07-01 | QLGBM+CQR | 28.2 | 8.5195 | 0.8101 | 114.6 | 0.1735 | 0.0643 | 0.6676 | 0.5565 | 0.7999 | 7.8586 | 9.2026 | 40.8 | 36.5 | 44.6 | 40 | 300 |
| A_src_origin_2024-07-01 | AFT+CQR | 18.3 | 6.1732 | 0.8190 | 93.6 | 0.1283 | 0.0473 | 0.7707 | 0.5397 | 0.8051 | 5.4808 | 7.0141 | 57.1 | 47.2 | 64.5 | 40 | 300 |
| A_src_origin_2024-07-01 | ENS DH-GBM+QLGBM+CQR | 21.8 | 6.6641 | 0.8143 | 91.0 | 0.1290 | 0.0527 | 0.7802 | 0.4902 | 0.9308 | 6.3104 | 6.9988 | 53.7 | 48.7 | 58.1 | 40 | 300 |

## T1-B domain adaptation, miền đích tgt (onboard 2024-07)

Nguồn: `outputs/t1/B_domain_adaptation_tgt.csv`

Giao thức: asof-pchip-v3-point-mass-fullweek

| months_history | model | MAE_p50 | pinball_avg | cov80 | IBS_13w | ECE_4w | WAPE_collect_w1_4 | WAPE_collect_w5_13 | pinball_ci_low | pinball_ci_high | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | B1-cust-median | 32.3 | 16.1 | 0.0501 | 0.2954 | 0.3426 | 1.1395 | 0.7187 | 14.2 | 18.5 | -17.9 | -24.1 | -11.2 | 14 | 300 |
| 0 | B1d-cust-quantiles | 32.3 | 13.7 | 0.4651 | 0.2416 | 0.2204 | 1.0820 | 0.6416 | 11.6 | 16.6 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 |
| 0 | Customer-EB | 32.4 | 16.2 | 0.0004 | 0.2947 | 0.3458 | 1.0973 | 0.8001 | 14.2 | 18.7 | -18.3 | -24.1 | -11.6 | 14 | 300 |
| 0 | SRC-only DH-GBM (zero-shot) | 21.1 | 6.4436 | 0.8227 | 0.1313 | 0.0366 | 0.4698 | 0.6145 | 5.6283 | 6.9573 | 53.0 | 41.4 | 63.4 | 14 | 300 |
| 0 | SRC-only QLGBM | 25.7 | 8.5049 | 0.6687 | 0.1597 | 0.0259 | 0.5500 | 0.7119 | 7.5385 | 9.7733 | 37.9 | 34.2 | 43.4 | 14 | 300 |
| 3 | B1-cust-median | 31.4 | 15.7 | 0.0525 | 0.2860 | 0.3285 | 1.0779 | 0.7108 | 13.7 | 18.1 | -27.5 | -36.0 | -18.7 | 14 | 300 |
| 3 | B1d-cust-quantiles | 31.4 | 12.3 | 0.5650 | 0.2239 | 0.1909 | 1.0104 | 0.6361 | 10.2 | 15.0 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 |
| 3 | Customer-EB | 31.6 | 15.8 | 0.0000 | 0.2869 | 0.3340 | 0.9747 | 0.7998 | 13.9 | 18.2 | -28.5 | -37.0 | -19.0 | 14 | 300 |
| 3 | SRC-only DH-GBM (zero-shot) | 22.0 | 6.5184 | 0.8321 | 0.1319 | 0.0528 | 0.4562 | 0.6038 | 5.4147 | 7.3817 | 47.0 | 29.0 | 61.5 | 14 | 300 |
| 3 | SRC-only QLGBM | 25.9 | 8.5198 | 0.6710 | 0.1610 | 0.0265 | 0.5521 | 0.7141 | 7.5187 | 9.8016 | 30.8 | 25.7 | 35.5 | 14 | 300 |
| 3 | TGT-only DH-GBM | 32.5 | 10.2 | 0.6324 | 0.2011 | 0.1248 | 0.5987 | 0.7183 | 9.0659 | 11.1 | 17.4 | 0.0008 | 31.6 | 14 | 300 |
| 3 | POOLED (tgt-upweighted) | 21.6 | 6.4784 | 0.8299 | 0.1314 | 0.0550 | 0.4522 | 0.5967 | 5.3780 | 7.3010 | 47.4 | 30.0 | 61.7 | 14 | 300 |
| 3 | FINE-TUNE src->tgt | 22.2 | 6.9413 | 0.7583 | 0.1395 | 0.0409 | 0.4433 | 0.6101 | 5.8018 | 7.7517 | 43.6 | 27.8 | 57.6 | 14 | 300 |
| 3 | IW-POOLED (density-ratio) | 21.6 | 6.4784 | 0.8299 | 0.1314 | 0.0550 | 0.4522 | 0.5967 | 5.3780 | 7.3010 | 47.4 | 30.0 | 61.7 | 14 | 300 |
| 3 | S5 ENS fine-tune+B1d | 25.4 | 9.0555 | 0.6329 | 0.1645 | 0.0681 | 0.5702 | 0.7228 | 8.0133 | 10.5 | 26.4 | 20.6 | 31.8 | 14 | 300 |
| 6 | B1-cust-median | 31.1 | 15.5 | 0.0521 | 0.2834 | 0.3242 | 1.0187 | 0.7383 | 13.6 | 17.9 | -33.4 | -43.2 | -23.4 | 14 | 300 |
| 6 | B1d-cust-quantiles | 31.1 | 11.6 | 0.6221 | 0.2162 | 0.1697 | 0.9635 | 0.6391 | 9.5583 | 14.4 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 |
| 6 | Customer-EB | 31.4 | 15.7 | 0.0000 | 0.2851 | 0.3301 | 0.9532 | 0.8660 | 13.9 | 18.0 | -34.9 | -45.9 | -22.9 | 14 | 300 |
| 6 | SRC-only DH-GBM (zero-shot) | 22.7 | 6.6345 | 0.8305 | 0.1338 | 0.0604 | 0.4614 | 0.6095 | 5.4177 | 7.6264 | 43.0 | 22.1 | 59.9 | 14 | 300 |
| 6 | SRC-only QLGBM | 25.7 | 8.4553 | 0.6732 | 0.1596 | 0.0296 | 0.5470 | 0.7121 | 7.4276 | 9.7824 | 27.4 | 22.1 | 33.6 | 14 | 300 |
| 6 | TGT-only DH-GBM | 25.7 | 7.5468 | 0.8017 | 0.1508 | 0.0357 | 0.4970 | 0.6417 | 6.5891 | 8.1457 | 35.2 | 16.8 | 50.5 | 14 | 300 |
| 6 | POOLED (tgt-upweighted) | 22.1 | 6.5008 | 0.8469 | 0.1315 | 0.0514 | 0.4436 | 0.5946 | 5.4296 | 7.3095 | 44.2 | 24.9 | 59.7 | 14 | 300 |
| 6 | FINE-TUNE src->tgt | 23.2 | 6.7381 | 0.8330 | 0.1376 | 0.0462 | 0.4539 | 0.6048 | 5.3789 | 7.8774 | 42.2 | 19.7 | 60.2 | 14 | 300 |
| 6 | IW-POOLED (density-ratio) | 22.1 | 6.5008 | 0.8469 | 0.1315 | 0.0514 | 0.4436 | 0.5946 | 5.4296 | 7.3095 | 44.2 | 24.9 | 59.7 | 14 | 300 |
| 6 | S5 ENS fine-tune+B1d | 25.0 | 8.4489 | 0.6966 | 0.1560 | 0.0350 | 0.5496 | 0.7499 | 7.5936 | 9.4998 | 27.5 | 19.2 | 34.3 | 14 | 300 |
| 12 | B1-cust-median | 31.0 | 15.5 | 0.0520 | 0.2823 | 0.3220 | 0.9964 | 0.7385 | 13.6 | 17.9 | -36.2 | -46.9 | -25.0 | 14 | 300 |
| 12 | B1d-cust-quantiles | 31.0 | 11.4 | 0.6563 | 0.2134 | 0.1630 | 0.9478 | 0.6358 | 9.3413 | 14.1 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 |
| 12 | Customer-EB | 31.7 | 15.8 | 0.0005 | 0.2871 | 0.3263 | 0.9291 | 0.8925 | 14.0 | 18.0 | -39.0 | -52.5 | -24.8 | 14 | 300 |
| 12 | SRC-only DH-GBM (zero-shot) | 22.3 | 6.5524 | 0.8308 | 0.1334 | 0.0545 | 0.4517 | 0.5951 | 5.4096 | 7.4177 | 42.5 | 22.1 | 58.7 | 14 | 300 |
| 12 | SRC-only QLGBM | 25.8 | 8.5587 | 0.6702 | 0.1609 | 0.0275 | 0.5453 | 0.7141 | 7.4630 | 10.0 | 24.9 | 19.1 | 32.1 | 14 | 300 |
| 12 | TGT-only DH-GBM | 34.4 | 10.1 | 0.6851 | 0.2020 | 0.1154 | 0.6276 | 0.7157 | 8.0264 | 11.6 | 11.1 | -20.6 | 36.5 | 14 | 300 |
| 12 | POOLED (tgt-upweighted) | 22.1 | 6.5219 | 0.8383 | 0.1328 | 0.0547 | 0.4568 | 0.6019 | 5.4332 | 7.3398 | 42.7 | 22.9 | 58.7 | 14 | 300 |
| 12 | FINE-TUNE src->tgt | 24.8 | 7.1109 | 0.7992 | 0.1435 | 0.0633 | 0.4893 | 0.6082 | 5.4495 | 8.3743 | 37.6 | 12.6 | 58.3 | 14 | 300 |
| 12 | IW-POOLED (density-ratio) | 22.2 | 6.5449 | 0.8402 | 0.1329 | 0.0572 | 0.4568 | 0.6050 | 5.3965 | 7.4658 | 42.5 | 21.7 | 59.1 | 14 | 300 |
| 12 | FINE-TUNE src->tgt+CQR | 24.8 | 7.1109 | 0.7992 | 0.1505 | 0.0669 | 0.5541 | 0.6824 | 5.4495 | 8.3743 | 37.6 | 12.6 | 58.3 | 14 | 300 |
| 12 | POOLED (tgt-upweighted)+CQR | 22.1 | 6.5219 | 0.8383 | 0.1384 | 0.0588 | 0.5255 | 0.6843 | 5.4332 | 7.3398 | 42.7 | 22.9 | 58.7 | 14 | 300 |
| 12 | S5 ENS fine-tune+B1d | 25.3 | 8.4717 | 0.6978 | 0.1570 | 0.0368 | 0.5668 | 0.7545 | 7.6258 | 9.4961 | 25.6 | 16.1 | 33.6 | 14 | 300 |
| 24 | B1-cust-median | 31.1 | 15.5 | 0.0538 | 0.2828 | 0.3236 | 1.0170 | 0.7448 | 13.6 | 17.9 | -35.9 | -46.6 | -25.2 | 14 | 300 |
| 24 | B1d-cust-quantiles | 31.0 | 11.4 | 0.6550 | 0.2142 | 0.1656 | 0.9542 | 0.6332 | 9.3729 | 14.2 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 |
| 24 | Customer-EB | 31.7 | 15.9 | 0.0002 | 0.2875 | 0.3290 | 0.9253 | 0.8657 | 14.1 | 18.0 | -38.7 | -51.7 | -25.1 | 14 | 300 |
| 24 | SRC-only DH-GBM (zero-shot) | 22.5 | 6.6038 | 0.8265 | 0.1339 | 0.0497 | 0.4515 | 0.5938 | 5.4406 | 7.5688 | 42.2 | 21.0 | 59.0 | 14 | 300 |
| 24 | SRC-only QLGBM | 26.0 | 8.7771 | 0.6637 | 0.1639 | 0.0295 | 0.5492 | 0.7040 | 7.5709 | 10.3 | 23.2 | 18.1 | 29.9 | 14 | 300 |
| 24 | TGT-only DH-GBM | 25.2 | 7.4223 | 0.8135 | 0.1493 | 0.0570 | 0.5178 | 0.6351 | 6.3123 | 8.1527 | 35.0 | 15.6 | 51.0 | 14 | 300 |
| 24 | POOLED (tgt-upweighted) | 21.8 | 6.4709 | 0.8345 | 0.1307 | 0.0363 | 0.4389 | 0.5827 | 5.3478 | 7.3587 | 43.4 | 23.5 | 59.3 | 14 | 300 |
| 24 | FINE-TUNE src->tgt | 22.8 | 6.7394 | 0.8121 | 0.1362 | 0.0418 | 0.4620 | 0.5971 | 5.4467 | 7.7182 | 41.0 | 20.0 | 57.7 | 14 | 300 |
| 24 | IW-POOLED (density-ratio) | 22.1 | 6.5276 | 0.8320 | 0.1321 | 0.0386 | 0.4483 | 0.5871 | 5.4131 | 7.3910 | 42.9 | 23.2 | 58.6 | 14 | 300 |
| 24 | FINE-TUNE src->tgt+CQR | 22.8 | 6.7394 | 0.8121 | 0.1411 | 0.0447 | 0.5357 | 0.6767 | 5.4467 | 7.7182 | 41.0 | 20.0 | 57.7 | 14 | 300 |
| 24 | POOLED (tgt-upweighted)+CQR | 21.8 | 6.4709 | 0.8345 | 0.1360 | 0.0397 | 0.5128 | 0.6729 | 5.3478 | 7.3587 | 43.4 | 23.5 | 59.3 | 14 | 300 |
| 24 | S5 ENS fine-tune+B1d | 25.3 | 8.4800 | 0.7084 | 0.1577 | 0.0370 | 0.5616 | 0.7382 | 7.5878 | 9.6477 | 25.8 | 17.7 | 32.5 | 14 | 300 |

## T1-C LEGACY v1, chỉ kiểm toán

Nguồn: `outputs/t1/C_real_domains.csv`

Giao thức: asof-pchip-v3-point-mass **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| setting | model | MAE_p50 | pinball_avg | cov80 | IBS_13w | C_index | pinball_ci_low | pinball_ci_high | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C_real_customer_invoices | B0-due | 5.0701 | 2.5350 | 0.1922 | 0.0460 | 0.7339 | 2.3236 | 4.3650 | -74.2 | -174.3 | -27.4 | 4 | 300 |
| C_real_customer_invoices | B1-cust-median | 3.7956 | 1.8978 | 0.2643 | 0.0354 | 0.8314 | 1.7801 | 4.3645 | -30.4 | -31.1 | -26.5 | 4 | 300 |
| C_real_customer_invoices | B1d-cust-quantiles | 3.7940 | 1.4552 | 0.7886 | 0.0317 | 0.8313 | 1.3574 | 3.4273 | 0.0000 | 0.0000 | 0.0000 | 4 | 300 |
| C_real_customer_invoices | DH-GBM | 4.1825 | 1.5012 | 0.7495 | 0.0298 | 0.8190 | 1.3803 | 2.8715 | -3.1611 | -46.8 | 16.2 | 4 | 300 |
| C_real_customer_invoices | DH-LR | 105.1 | 47.5 | 0.0001 | 0.8601 | 0.7649 | 46.8 | 50.6 | -3164.9 | -3385.6 | -1265.5 | 4 | 300 |
| C_real_customer_invoices | QLGBM | 4.6298 | 1.7550 | 0.6042 | 0.0377 | 0.8135 | 1.6099 | 4.3119 | -20.6 | -42.7 | -18.0 | 4 | 300 |
| C_real_customer_invoices | AFT | 4.8227 | 1.6776 | 0.6475 | 0.0444 | 0.8183 | 1.5332 | 3.0999 | -15.3 | -75.6 | 9.5537 | 4 | 300 |
| C_real_customer_invoices | ENS DH-GBM+QLGBM | 4.1977 | 1.5425 | 0.7465 | 0.0326 | 0.8384 | 1.4128 | 3.4288 | -6.0017 | -39.0 | -0.0425 | 4 | 300 |
| C_real_bpi2019 | B0-due | 40.1 | 20.1 | 0.0012 | 0.4040 | 0.5000 | 9.7500 | 55.3 | -317.9 | -339.3 | 0.0000 | 3 | 300 |
| C_real_bpi2019 | B1-cust-median | 13.3 | 6.6471 | 0.0557 | 0.1304 | 0.8060 | 6.3750 | 54.7 | -38.5 | -41.0 | 0.0000 | 3 | 300 |
| C_real_bpi2019 | B1d-cust-quantiles | 13.3 | 4.7993 | 0.7136 | 0.0997 | 0.8057 | 4.5202 | 54.1 | 0.0000 | 0.0000 | 0.0000 | 3 | 300 |
| C_real_bpi2019 | DH-GBM | 33.3 | 15.1 | 0.1044 | 0.3349 | 0.7634 | 8.1589 | 22.3 | -214.4 | -232.9 | 58.8 | 3 | 300 |
| C_real_bpi2019 | DH-LR | 18.8 | 6.2095 | 0.6168 | 0.1426 | 0.7777 | 6.0868 | 42.1 | -29.4 | -332.2 | 48.6 | 3 | 300 |
| C_real_bpi2019 | QLGBM | 32.2 | 14.8 | 0.0633 | 0.3039 | 0.7501 | 3.2441 | 40.8 | -209.3 | -225.2 | 66.7 | 3 | 300 |
| C_real_bpi2019 | AFT | 32.6 | 15.2 | 0.0577 | 0.2935 | 0.6793 | 8.6781 | 37.4 | -216.2 | -233.0 | 30.8 | 3 | 300 |
| C_real_bpi2019 | ENS DH-GBM+QLGBM | 32.8 | 15.0 | 0.0910 | 0.2934 | 0.7811 | 4.9958 | 31.5 | -211.5 | -228.7 | 48.8 | 3 | 300 |

## T1-C v2 fullweek, refit và BLEND chọn trên quá khứ

Nguồn: `outputs/t1/real_v2/C_real_v2.csv`

Giao thức: C-real-fullweek-refit-blend-v2

| setting | model | pinball_avg | MAE_p50 | cov80 | IS80 | improvement_vs_B1d_pct | improvement_ci_low | improvement_ci_high |
|---|---|---|---|---|---|---|---|---|
| bpi | B1d | 4.7993 | 13.3 | 0.7136 | 77.6 | 0.0000 | 0.0000 | 0.0000 |
| bpi | DH-GBM | 7.7997 | 25.6 | 0.7589 | 106.2 | -62.5 | -90.4 | -37.4 |
| bpi | DH-LR | 6.0144 | 19.1 | 0.8363 | 85.0 | -25.3 | -43.8 | -11.9 |
| bpi | QLGBM | 14.8 | 32.2 | 0.0633 | 284.3 | -209.3 | -284.8 | -146.5 |
| bpi | ENS | 5.8162 | 17.1 | 0.6908 | 89.1 | -21.2 | -43.2 | -3.3619 |
| bpi | BLEND(DH-GBM,B1d) w=0.25 | 4.4871 | 12.9 | 0.8078 | 70.1 | 6.5047 | 2.1444 | 11.0 |
| bpi | BLEND(DH-GBM,B1d)+CQR | 5.2111 | 12.9 | 0.9601 | 91.9 | -8.5798 | -17.8 | 0.8023 |
| bpi | BLEND(ENS,B1d) w=0.5 | 4.6727 | 13.2 | 0.7506 | 74.2 | 2.6384 | -6.2264 | 9.4144 |
| bpi | BLEND(ENS,B1d)+CQR | 5.1746 | 13.2 | 0.9548 | 89.3 | -7.8187 | -19.9 | 2.1717 |
| bpi | B1d+CQR | 5.6623 | 13.3 | 0.9693 | 103.4 | -18.0 | -28.8 | -8.3949 |
| ci | B1d | 1.4552 | 3.7940 | 0.7886 | 24.7 | 0.0000 | 0.0000 | 0.0000 |
| ci | DH-GBM | 1.2642 | 3.5906 | 0.7925 | 20.0 | 13.1 | 8.2939 | 17.9 |
| ci | DH-LR | 1.7384 | 5.2122 | 0.8990 | 26.1 | -19.5 | -34.1 | -7.9094 |
| ci | QLGBM | 1.3103 | 3.4435 | 0.4900 | 22.1 | 9.9532 | 4.0441 | 16.0 |
| ci | ENS | 1.2167 | 3.4198 | 0.7285 | 19.4 | 16.4 | 11.4 | 21.4 |
| ci | BLEND(DH-GBM,B1d) w=0.5 | 1.2453 | 3.3920 | 0.8345 | 20.4 | 14.4 | 11.7 | 17.4 |
| ci | BLEND(DH-GBM,B1d)+CQR | 1.2466 | 3.3920 | 0.8387 | 20.4 | 14.3 | 11.6 | 17.4 |
| ci | BLEND(ENS,B1d) w=0.25 | 1.3183 | 3.5393 | 0.7764 | 21.9 | 9.4033 | 7.9242 | 10.6 |
| ci | BLEND(ENS,B1d)+CQR | 1.3213 | 3.5393 | 0.8456 | 21.9 | 9.1966 | 7.7725 | 10.6 |
| ci | B1d+CQR | 1.4495 | 3.7940 | 0.8449 | 24.5 | 0.3868 | -0.1157 | 1.0006 |

## G3 CQR hai phía theo kỳ đáo hạn, nguồn

Nguồn: `outputs/t1/G3/metrics.csv`

Giao thức: G3-source-mondrian-two-sided-v1-fullweek

| origin | model | cov80 | cov80_ci_low | cov80_ci_high | IS80 | vs_global_IS_improvement_pct | improvement_ci_low | improvement_ci_high | n | n_firms | bootstrap_n | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-07-03 | raw | 0.8769 | 0.8689 | 0.8867 | 77.7 | 0.8375 | 0.5686 | 1.1488 | 76324 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |
| 2023-07-03 | global_two_sided | 0.8857 | 0.8782 | 0.8949 | 78.4 | 0.0000 | 0.0000 | 0.0000 | 76324 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |
| 2023-07-03 | mondrian_two_sided | 0.8671 | 0.8555 | 0.8780 | 81.3 | -3.7331 | -5.0038 | -2.7338 | 76324 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |
| 2024-07-01 | raw | 0.8510 | 0.8372 | 0.8649 | 72.9 | 0.0000 | 0.0000 | 0.0000 | 68425 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |
| 2024-07-01 | global_two_sided | 0.8510 | 0.8372 | 0.8649 | 72.9 | 0.0000 | 0.0000 | 0.0000 | 68425 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |
| 2024-07-01 | mondrian_two_sided | 0.8439 | 0.8295 | 0.8574 | 72.9 | -0.0484 | -0.1334 | 0.0219 | 68425 | 40 | 300 | False | G3-source-mondrian-two-sided-v1-fullweek |

## P4 đặc trưng dừng, cùng cohort và ngân sách

Nguồn: `outputs/t1/P4/metrics.csv`

Giao thức: P4-stationary-matched-protocol-v1-fullweek

| dataset | model | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | n | n_firms | bootstrap_groups | ci_low | ci_high | bootstrap_n | improvement_pct | improvement_ci_low | improvement_ci_high | measurement_version | test_used_for_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_2023-07-03 | baseline | 3.0144 | 9.9327 | 4.7557 | 5.9009 | 19.9 | 22.2 | 0.8769 | 77.7 | 76324 | 40 | firm_id | 5.3989 | 6.3713 | 300 | 0.0000 | 0.0000 | 0.0000 | P4-stationary-matched-protocol-v1-fullweek | False |
| A_2023-07-03 | stationary | 3.1007 | 10.1 | 4.7311 | 5.9852 | 20.2 | 22.6 | 0.8718 | 78.3 | 76324 | 40 | firm_id | 5.4082 | 6.4992 | 300 | -1.4280 | -2.6672 | -0.0605 | P4-stationary-matched-protocol-v1-fullweek | False |
| A_2024-07-01 | baseline | 2.4651 | 8.2621 | 4.8228 | 5.1834 | 16.5 | 15.6 | 0.8510 | 72.9 | 68425 | 40 | firm_id | 4.7275 | 5.6659 | 300 | 0.0000 | 0.0000 | 0.0000 | P4-stationary-matched-protocol-v1-fullweek | False |
| A_2024-07-01 | stationary | 2.4638 | 8.2271 | 4.8001 | 5.1637 | 16.5 | 15.5 | 0.8577 | 72.6 | 68425 | 40 | firm_id | 4.7134 | 5.6423 | 300 | 0.3799 | -0.8074 | 1.8809 | P4-stationary-matched-protocol-v1-fullweek | False |
| B_M12 | baseline | 3.7519 | 12.4 | 5.1850 | 7.1109 | 24.8 | 25.2 | 0.7992 | 89.4 | 39304 | 14 | firm_id | 5.4495 | 8.3743 | 300 | 0.0000 | 0.0000 | 0.0000 | P4-stationary-matched-protocol-v1-fullweek | False |
| B_M12 | stationary | 3.9190 | 13.4 | 5.2722 | 7.5248 | 26.8 | 28.1 | 0.7995 | 91.9 | 39304 | 14 | firm_id | 5.7084 | 8.9146 | 300 | -5.8199 | -7.3109 | -3.0509 | P4-stationary-matched-protocol-v1-fullweek | False |
| ci | baseline | 0.8078 | 1.6960 | 1.2320 | 1.2453 | 3.3920 | 3.3920 | 0.8345 | 20.4 | 17922 | 610 | customer_id | 1.0799 | 1.4814 | 300 | 0.0000 | 0.0000 | 0.0000 | P4-stationary-matched-protocol-v1-fullweek | False |
| ci | stationary | 0.8112 | 1.7032 | 1.2193 | 1.2445 | 3.4063 | 3.4063 | 0.8339 | 20.3 | 17922 | 610 | customer_id | 1.0798 | 1.4799 | 300 | 0.0596 | -0.5040 | 0.6490 | P4-stationary-matched-protocol-v1-fullweek | False |
| bpi | baseline | 2.1974 | 6.4480 | 4.8161 | 4.4871 | 12.9 | 11.3 | 0.8078 | 70.1 | 353512 | 1374 | customer_id | 4.0320 | 5.0757 | 300 | 0.0000 | 0.0000 | 0.0000 | P4-stationary-matched-protocol-v1-fullweek | False |
| bpi | stationary | 2.1214 | 5.9306 | 4.5668 | 4.2063 | 11.9 | 10.2 | 0.7887 | 66.9 | 353512 | 1374 | customer_id | 3.6839 | 4.8845 | 300 | 6.2591 | 2.2960 | 9.4727 | P4-stationary-matched-protocol-v1-fullweek | False |

## T9 P5 lỗi phân bổ trên DN nguồn

Nguồn: `outputs/t9/sprint3/source_allocation_diagnostics.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| category | n_txns | tp | fp | fn | exact_set_rate | automatic_rate |
|---|---|---|---|---|---|---|
| bank_fee | 413 | 413 | 2 | 71 | 0.8692 | 0.8717 |
| grouped_invoices | 879 | 1512 | 109 | 907 | 0.7179 | 0.7509 |
| invoice_set | 7893 | 6974 | 58 | 919 | 0.8836 | 0.8871 |
| noise | 1050 | 0 | 30 | 0 | 0.9714 | 0.0286 |
| partial_payment | 611 | 21 | 84 | 1346 | 0.0000 | 0.0458 |
| wrong_customer | 124 | 0 | 124 | 151 | 0.0000 | 1.0000 |

## T9 P5 đường precision–coverage và chọn tau trên nguồn

Nguồn: `outputs/t9/sprint3/source_precision_coverage.csv`

Giao thức: T9-source-allocation-v1-fullweek

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | settled_invoice_coverage | pay_date_MAE_ledger_days | method | link_precision_ci_low | link_precision_ci_high | link_recall_ci_low | link_recall_ci_high | link_f1_ci_low | link_f1_ci_high | pay_date_MAE_ci_low | pay_date_MAE_ci_high | auto_coverage_ci_low | auto_coverage_ci_high | bootstrap_n | n_firms | tau | variant | auto_txn_coverage | n_review | selection_domain | target_used | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9552 | 0.7271 | 0.8257 | 9373 | 12314 | 0.0295 | 0.8027 | 0.9725 | 0.7986 | 6.6735 | Hybrid source heldout | 0.9409 | 0.9716 | 0.6846 | 0.7865 | 0.7937 | 0.8689 | 0.4657 | 1.1671 | 0.7125 | 0.7895 | 300 | 28 | 0.5000 | baseline | 0.7490 | 2753 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9554 | 0.7258 | 0.8250 | 9355 | 12314 | 0.0295 | 0.8036 | 0.9726 | 0.7972 | 6.6735 | Hybrid source heldout | 0.9415 | 0.9716 | 0.6840 | 0.7857 | 0.7928 | 0.8683 | 0.4666 | 1.1684 | 0.7122 | 0.7890 | 300 | 28 | 0.6000 | baseline | 0.7486 | 2758 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9557 | 0.7260 | 0.8252 | 9354 | 12314 | 0.0286 | 0.7916 | 0.9729 | 0.7972 | 6.6735 | Hybrid source heldout | 0.9420 | 0.9715 | 0.6846 | 0.7853 | 0.7932 | 0.8684 | 0.4614 | 1.1459 | 0.7126 | 0.7888 | 300 | 28 | 0.7000 | baseline | 0.7487 | 2757 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9564 | 0.7244 | 0.8244 | 9327 | 12314 | 0.0286 | 0.7773 | 0.9736 | 0.7948 | 6.6735 | Hybrid source heldout | 0.9430 | 0.9716 | 0.6830 | 0.7823 | 0.7927 | 0.8665 | 0.4528 | 1.1262 | 0.7119 | 0.7878 | 300 | 28 | 0.8000 | baseline | 0.7479 | 2766 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9564 | 0.7244 | 0.8244 | 9327 | 12314 | 0.0286 | 0.7773 | 0.9736 | 0.7948 | 6.6735 | Hybrid source heldout | 0.9430 | 0.9716 | 0.6830 | 0.7823 | 0.7927 | 0.8665 | 0.4528 | 1.1262 | 0.7119 | 0.7878 | 300 | 28 | 0.8500 | baseline | 0.7479 | 2766 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9564 | 0.7244 | 0.8244 | 9327 | 12314 | 0.0286 | 0.7773 | 0.9736 | 0.7948 | 6.6735 | Hybrid source heldout | 0.9430 | 0.9716 | 0.6830 | 0.7823 | 0.7927 | 0.8665 | 0.4528 | 1.1262 | 0.7119 | 0.7878 | 300 | 28 | 0.9000 | baseline | 0.7479 | 2766 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9563 | 0.7134 | 0.8172 | 9186 | 12314 | 0.0286 | 0.7770 | 0.9737 | 0.7826 | 6.6735 | Hybrid source heldout | 0.9423 | 0.9709 | 0.6711 | 0.7705 | 0.7863 | 0.8583 | 0.4527 | 1.1264 | 0.7080 | 0.7823 | 300 | 28 | 0.9500 | baseline | 0.7429 | 2820 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9580 | 0.7059 | 0.8129 | 9074 | 12314 | 0.0295 | 0.7485 | 0.9752 | 0.7733 | 6.6735 | Hybrid source heldout | 0.9439 | 0.9713 | 0.6621 | 0.7636 | 0.7802 | 0.8542 | 0.4454 | 1.0724 | 0.7038 | 0.7787 | 300 | 28 | 0.9750 | baseline | 0.7388 | 2865 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9592 | 0.7012 | 0.8101 | 9001 | 12314 | 0.0305 | 0.7324 | 0.9758 | 0.7675 | 6.6735 | Hybrid source heldout | 0.9455 | 0.9724 | 0.6560 | 0.7594 | 0.7763 | 0.8521 | 0.4182 | 1.0567 | 0.7012 | 0.7759 | 300 | 28 | 0.9900 | baseline | 0.7360 | 2896 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9509 | 0.7733 | 0.8530 | 10015 | 12314 | 0.0295 | 0.9511 | 0.9669 | 0.8212 | 6.6735 | Hybrid source heldout | 0.9372 | 0.9686 | 0.7336 | 0.8235 | 0.8239 | 0.8886 | 0.5548 | 1.3005 | 0.7671 | 0.8267 | 300 | 28 | 0.5000 | candidate | 0.7959 | 2239 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9511 | 0.7714 | 0.8519 | 9987 | 12314 | 0.0295 | 0.9441 | 0.9670 | 0.8194 | 6.6735 | Hybrid source heldout | 0.9371 | 0.9686 | 0.7312 | 0.8227 | 0.8232 | 0.8881 | 0.5553 | 1.2804 | 0.7655 | 0.8259 | 300 | 28 | 0.6000 | candidate | 0.7945 | 2254 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9514 | 0.7713 | 0.8520 | 9983 | 12314 | 0.0286 | 0.9325 | 0.9673 | 0.8193 | 6.6735 | Hybrid source heldout | 0.9375 | 0.9686 | 0.7311 | 0.8226 | 0.8236 | 0.8879 | 0.5555 | 1.2550 | 0.7654 | 0.8255 | 300 | 28 | 0.7000 | candidate | 0.7943 | 2256 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9518 | 0.7684 | 0.8503 | 9941 | 12314 | 0.0286 | 0.9291 | 0.9677 | 0.8167 | 6.6735 | Hybrid source heldout | 0.9380 | 0.9688 | 0.7279 | 0.8192 | 0.8213 | 0.8859 | 0.5419 | 1.2651 | 0.7625 | 0.8239 | 300 | 28 | 0.8000 | candidate | 0.7921 | 2281 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9518 | 0.7684 | 0.8503 | 9941 | 12314 | 0.0286 | 0.9291 | 0.9677 | 0.8167 | 6.6735 | Hybrid source heldout | 0.9380 | 0.9688 | 0.7279 | 0.8192 | 0.8213 | 0.8859 | 0.5419 | 1.2651 | 0.7625 | 0.8239 | 300 | 28 | 0.8500 | candidate | 0.7921 | 2281 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9518 | 0.7684 | 0.8503 | 9941 | 12314 | 0.0286 | 0.9291 | 0.9677 | 0.8167 | 6.6735 | Hybrid source heldout | 0.9380 | 0.9688 | 0.7279 | 0.8192 | 0.8213 | 0.8859 | 0.5419 | 1.2651 | 0.7625 | 0.8239 | 300 | 28 | 0.9000 | candidate | 0.7921 | 2281 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9526 | 0.7542 | 0.8419 | 9749 | 12314 | 0.0286 | 0.8777 | 0.9689 | 0.8031 | 6.6735 | Hybrid source heldout | 0.9384 | 0.9682 | 0.7123 | 0.8052 | 0.8125 | 0.8778 | 0.5153 | 1.2054 | 0.7534 | 0.8168 | 300 | 28 | 0.9500 | candidate | 0.7833 | 2377 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9531 | 0.7441 | 0.8357 | 9614 | 12314 | 0.0295 | 0.8709 | 0.9693 | 0.7939 | 6.6735 | Hybrid source heldout | 0.9389 | 0.9689 | 0.7007 | 0.7969 | 0.8048 | 0.8727 | 0.5070 | 1.1968 | 0.7465 | 0.8101 | 300 | 28 | 0.9750 | candidate | 0.7768 | 2449 | src_company_holdout | False | T9-source-allocation-v1-fullweek |
| 0.9538 | 0.7369 | 0.8314 | 9514 | 12314 | 0.0295 | 0.8614 | 0.9695 | 0.7876 | 6.6735 | Hybrid source heldout | 0.9393 | 0.9696 | 0.6930 | 0.7917 | 0.8000 | 0.8700 | 0.4731 | 1.1956 | 0.7414 | 0.8060 | 300 | 28 | 0.9900 | candidate | 0.7717 | 2504 | src_company_holdout | False | T9-source-allocation-v1-fullweek |

## T9 P5 chính sách nguồn trên tgt/retention/COD, không chọn lại trên test

Nguồn: `outputs/t9/sprint3/target_metrics.csv`

Giao thức: T9-source-selected-allocation-v1-fullweek

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | settled_invoice_coverage | pay_date_MAE_ledger_days | method | link_precision_ci_low | link_precision_ci_high | link_recall_ci_low | link_recall_ci_high | link_f1_ci_low | link_f1_ci_high | pay_date_MAE_ci_low | pay_date_MAE_ci_high | auto_coverage_ci_low | auto_coverage_ci_high | bootstrap_n | n_firms | world | auto_txn_coverage | tau | selected_on | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9654 | 0.4716 | 0.6336 | 3820 | 7821 | 0.0211 | 0.5771 | 0.9837 | 0.5146 | 11.8 | R1 | 0.9542 | 0.9789 | 0.3868 | 0.5639 | 0.5504 | 0.7153 | 0.1801 | 0.9343 | 0.5224 | 0.6406 | 300 | 14 | tgt | 0.5832 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 1.0000 | 0.2124 | 0.3503 | 1661 | 7821 | 0.0000 | 0.0000 | 1.0000 | 0.2279 | 11.8 | R2 | 1.0000 | 1.0000 | 0.1650 | 0.2373 | 0.2833 | 0.3836 | 0.0000 | 0.0000 | 0.1746 | 0.2439 | 300 | 14 | tgt | 0.2240 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.9405 | 0.6607 | 0.7761 | 5494 | 7821 | 0.0211 | 1.2580 | 0.9586 | 0.7398 | 11.8 | Hybrid baseline tau=.9 | 0.9144 | 0.9734 | 0.5445 | 0.7633 | 0.6851 | 0.8541 | 0.4055 | 1.9569 | 0.6548 | 0.7496 | 300 | 14 | tgt | 0.7096 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.9246 | 0.6994 | 0.7964 | 5916 | 7821 | 0.0211 | 1.8526 | 0.9429 | 0.7719 | 11.8 | Deployment source-selected | 0.8837 | 0.9715 | 0.5819 | 0.7999 | 0.7055 | 0.8742 | 0.4861 | 3.2066 | 0.6990 | 0.7813 | 300 | 14 | tgt | 0.7507 | 0.5000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.8889 | 0.3587 | 0.5111 | 6238 | 15459 | 0.0620 | 2.5947 | 0.9624 | 0.4825 | 64.4 | R1 | 0.8466 | 0.9491 | 0.3064 | 0.4583 | 0.4517 | 0.6176 | 1.0237 | 4.0395 | 0.3984 | 0.4825 | 300 | 12 | hc_retention | 0.4301 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 1.0000 | 0.1800 | 0.3051 | 2783 | 15459 | 0.0000 | 0.0000 | 1.0000 | 0.2329 | 64.4 | R2 | 1.0000 | 1.0000 | 0.1416 | 0.2153 | 0.2480 | 0.3543 | 0.0000 | 0.0000 | 0.1426 | 0.2211 | 300 | 12 | hc_retention | 0.1843 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.8274 | 0.4407 | 0.5751 | 8234 | 15459 | 0.0613 | 5.3859 | 0.9375 | 0.6084 | 64.4 | Hybrid baseline tau=.9 | 0.7838 | 0.9070 | 0.3990 | 0.5154 | 0.5327 | 0.6561 | 2.2760 | 7.7380 | 0.4872 | 0.5401 | 300 | 12 | hc_retention | 0.5144 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.8155 | 0.5680 | 0.6696 | 10767 | 15459 | 0.0830 | 6.1955 | 0.9237 | 0.6612 | 64.4 | Deployment source-selected | 0.7697 | 0.8970 | 0.5223 | 0.6476 | 0.6279 | 0.7479 | 2.6968 | 8.5755 | 0.6260 | 0.7017 | 300 | 12 | hc_retention | 0.6652 | 0.5000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.9357 | 0.4440 | 0.6022 | 6613 | 13938 | 0.0327 | 1.7449 | 0.9549 | 0.5299 | 9.5770 | R1 | 0.8708 | 0.9848 | 0.3498 | 0.5724 | 0.4989 | 0.7219 | 0.3633 | 3.6925 | 0.4640 | 0.5994 | 300 | 12 | hc_cod_realistic | 0.5330 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 1.0000 | 0.2589 | 0.4114 | 3609 | 13938 | 0.0000 | 0.0000 | 1.0000 | 0.2946 | 9.5770 | R2 | 1.0000 | 1.0000 | 0.2285 | 0.2970 | 0.3720 | 0.4579 | 0.0000 | 0.0000 | 0.2289 | 0.3001 | 300 | 12 | hc_cod_realistic | 0.2709 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.9052 | 0.5602 | 0.6921 | 8626 | 13938 | 0.0336 | 2.5443 | 0.9254 | 0.6899 | 9.5770 | Hybrid baseline tau=.9 | 0.8327 | 0.9740 | 0.4817 | 0.6658 | 0.6102 | 0.7880 | 0.7177 | 4.5154 | 0.5900 | 0.6587 | 300 | 12 | hc_cod_realistic | 0.6241 | 0.9000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |
| 0.8985 | 0.6523 | 0.7559 | 10119 | 13938 | 0.0327 | 3.0278 | 0.9099 | 0.7429 | 9.5770 | Deployment source-selected | 0.8295 | 0.9695 | 0.5868 | 0.7755 | 0.6904 | 0.8588 | 0.8532 | 5.3000 | 0.6980 | 0.7613 | 300 | 12 | hc_cod_realistic | 0.7231 | 0.5000 | src_company_holdout | False | T9-source-selected-allocation-v1-fullweek |

## T2 cure: P(không bao giờ trả | quá hạn)

Nguồn: `outputs/t1/D_t2_cure.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| world | model | n | base_rate | PR_AUC | ROC_AUC | Brier | ECE | expected_loss_vs_actual |
|---|---|---|---|---|---|---|---|---|
| src | TT48 aging rule | 54650 | 0.3188 | 0.6029 | 0.7325 | 0.2378 | 0.2646 | 0.1895 |
| src | Logistic | 54650 | 0.3188 | 0.8121 | 0.9104 | 0.1048 | 0.0224 | 1.0322 |
| src | Cure-GBM | 54650 | 0.3188 | 0.9646 | 0.9754 | 0.0480 | 0.0358 | 0.8819 |
| tgt | TT48 aging rule | 20809 | 0.4465 | 0.6817 | 0.7288 | 0.3339 | 0.3732 | 0.1765 |
| tgt | Logistic | 20809 | 0.4465 | 0.8620 | 0.8859 | 0.1379 | 0.0526 | 1.1538 |
| tgt | Cure-GBM | 20809 | 0.4465 | 0.9762 | 0.9735 | 0.0534 | 0.0332 | 0.9527 |

## T8 lời hứa trả / T9 nguồn nhãn

Nguồn: `outputs/t1/EF_t8_t9.csv`

Giao thức: asof-pchip-v3-point-mass-fullweek

| setting | model | MAE_p50 | MAE_p50_promised_only | IBS_13w | cov80 | WAPE_collect_w1_4 | pinball_ci_low | pinball_ci_high | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|
| E_T8 | DH-GBM with promises (T8) | 15.4 | 11.2 | 0.1050 | 0.8598 | 0.4038 | 4.6046 | 5.2844 | 40 | 300 |
| E_T8 | DH-GBM without promises | 15.9 | 13.8 | 0.1085 | 0.8511 | 0.4155 | 4.7316 | 5.4694 | 40 | 300 |
| F_T9_label_source | DH-GBM trained on LEDGER dates | 15.8 |  | 0.1080 | 0.8510 | 0.4299 | 4.6805 | 5.4444 | 40 | 300 |
| F_T9_label_source | DH-GBM trained on BANK dates (T9) | 15.4 |  | 0.1050 | 0.8598 | 0.4038 | 4.6046 | 5.2844 | 40 | 300 |

## T2 SBA 7(a) thật + T3

Nguồn: `outputs/t2_t3/t2_t3_results.csv`

Giao thức: sba-exempt-matured-v3, t3-asof-resolved-v2

| task | model | n_test | ROC_AUC | PR_AUC | Brier | ECE | mean_p | base_rate | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 105084 | 0.5000 | 0.0287 | 0.0280 | 0.0120 | 0.0167 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 25475 | 0.5000 | 0.0007 | 0.0010 | 0.0160 | 0.0167 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 105084 | 0.7178 | 0.0625 | 0.0276 | 0.0103 | 0.0198 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 25475 | 0.6992 | 0.0014 | 0.0007 | 0.0009 | 0.0016 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 105084 | 0.9113 | 0.1705 | 0.0275 | 0.0206 | 0.0174 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 25475 | 0.8824 | 0.0108 | 0.0007 | 0.0001 | 0.0008 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 105084 | 0.9108 | 0.1665 | 0.0282 | 0.0222 | 0.0203 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 25475 | 0.8630 | 0.0091 | 0.0007 | 0.0004 | 0.0003 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 166591 | 0.5000 | 0.0181 | 0.0178 | 0.0019 | 0.0162 | 0.0181 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 56668 | 0.5000 | 0.0003 | 0.0006 | 0.0159 | 0.0162 | 0.0003 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 166591 | 0.7602 | 0.0507 | 0.0175 | 0.0024 | 0.0169 | 0.0181 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 56668 | 0.7121 | 0.0007 | 0.0003 | 0.0011 | 0.0014 | 0.0003 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 166591 | 0.9298 | 0.1477 | 0.0176 | 0.0124 | 0.0122 | 0.0181 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 56668 | 0.8944 | 0.0093 | 0.0003 | 0.0003 | 0.0006 | 0.0003 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 166591 | 0.9290 | 0.1428 | 0.0182 | 0.0134 | 0.0145 | 0.0181 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 56668 | 0.8826 | 0.0048 | 0.0003 | 0.0000 | 0.0003 | 0.0003 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 105084 | 0.5000 | 0.0287 | 0.0280 | 0.0120 | 0.0167 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 25475 | 0.5000 | 0.0007 | 0.0010 | 0.0160 | 0.0167 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 105084 | 0.7178 | 0.0625 | 0.0276 | 0.0103 | 0.0198 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 25475 | 0.6992 | 0.0014 | 0.0007 | 0.0009 | 0.0016 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 105084 | 0.9113 | 0.1705 | 0.0275 | 0.0206 | 0.0174 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 25475 | 0.8824 | 0.0108 | 0.0007 | 0.0001 | 0.0008 | 0.0007 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 105084 | 0.9108 | 0.1665 | 0.0282 | 0.0222 | 0.0203 | 0.0287 |  | 300.0 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 25475 | 0.8630 | 0.0091 | 0.0007 | 0.0004 | 0.0003 | 0.0007 |  | 300.0 |
| T3 dispute at issue (synthetic tgt, resolved cohort) | Base rate (src) | 4536 | 0.5000 | 0.0227 | 0.0223 | 0.0081 | 0.0146 | 0.0227 | 14.0 | 300.0 |
| T3 dispute at issue (synthetic tgt, resolved cohort) | Customer history rate (EB) | 4536 | 0.6675 | 0.0500 | 0.0219 | 0.0043 | 0.0186 | 0.0227 | 14.0 | 300.0 |
| T3 dispute at issue (synthetic tgt, resolved cohort) | LightGBM (src->tgt) | 4536 | 0.5258 | 0.0285 | 0.0224 | 0.0098 | 0.0132 | 0.0227 | 14.0 | 300.0 |
| T3 partial at issue (synthetic tgt, resolved cohort) | Base rate (src) | 4536 | 0.5000 | 0.0957 | 0.0880 | 0.0379 | 0.1336 | 0.0957 | 14.0 | 300.0 |
| T3 partial at issue (synthetic tgt, resolved cohort) | Customer history rate (EB) | 4536 | 0.7177 | 0.1940 | 0.0826 | 0.0214 | 0.0931 | 0.0957 | 14.0 | 300.0 |
| T3 partial at issue (synthetic tgt, resolved cohort) | LightGBM (src->tgt) | 4536 | 0.6777 | 0.1579 | 0.0847 | 0.0188 | 0.1038 | 0.0957 | 14.0 | 300.0 |
| T3 collected/invoiced ratio (src) | descriptive | 61294 |  |  |  |  | 0.9981 | 0.0270 |  |  |
| T3 collected/invoiced ratio (tgt) | descriptive | 4407 |  |  |  |  | 0.9978 | 0.0251 |  |  |

## T4 doanh thu mới

Nguồn: `outputs/t4/t4_revenue_forecast.csv`

Giao thức: revenue-source-calibration-v2

| setting | model | SPL | SPL_h1_4 | SPL_h5_13 | cov80 | WAPE_p50 | bootstrap_n |
|---|---|---|---|---|---|---|---|
| synthetic src (in-domain) | Global-LGBM-Q | 0.2596 | 0.2600 | 0.2594 | 0.7868 | 0.3283 | 300 |
| synthetic src (in-domain) | Global-LGBM-Q+CQR | 0.2608 | 0.2611 | 0.2607 | 0.8371 | 0.3283 | 300 |
| synthetic src (in-domain) | Seasonal-naive | 0.3271 | 0.3342 | 0.3240 | 0.8055 | 0.4050 | 300 |
| synthetic src (in-domain) | Mean-13w | 0.2701 | 0.2655 | 0.2722 | 0.8217 | 0.3402 | 300 |
| synthetic src (in-domain) | Chronos-Bolt (zero-shot) | 0.2628 | 0.2618 | 0.2632 | 0.8206 | 0.3355 | 300 |
| synthetic src (in-domain) | Ensemble LGBM+Chronos | 0.2563 | 0.2570 | 0.2560 | 0.8154 | 0.3269 | 300 |
| synthetic tgt (zero-shot transfer from src) | Global-LGBM-Q | 0.3483 | 0.3427 | 0.3509 | 0.7465 | 0.3721 | 300 |
| synthetic tgt (zero-shot transfer from src) | Global-LGBM-Q+CQR | 0.3474 | 0.3419 | 0.3498 | 0.7951 | 0.3721 | 300 |
| synthetic tgt (zero-shot transfer from src) | Seasonal-naive | 0.4249 | 0.4040 | 0.4342 | 0.7771 | 0.4718 | 300 |
| synthetic tgt (zero-shot transfer from src) | Mean-13w | 0.3861 | 0.3762 | 0.3906 | 0.7661 | 0.3895 | 300 |
| synthetic tgt (zero-shot transfer from src) | Chronos-Bolt (zero-shot) | 0.3667 | 0.3571 | 0.3710 | 0.7912 | 0.3798 | 300 |
| synthetic tgt (zero-shot transfer from src) | Ensemble LGBM+Chronos | 0.3524 | 0.3467 | 0.3549 | 0.7567 | 0.3709 | 300 |
| real Online Retail II (trained on own past) | Global-LGBM-Q | 0.2928 | 0.2579 | 0.3083 | 0.6660 | 0.3647 | 300 |
| real Online Retail II (trained on own past) | Global-LGBM-Q+CQR | 0.2875 | 0.2542 | 0.3024 | 0.8316 | 0.3647 | 300 |
| real Online Retail II (trained on own past) | Seasonal-naive | 0.3638 | 0.3216 | 0.3826 | 0.7005 | 0.2961 | 300 |
| real Online Retail II (trained on own past) | Mean-13w | 0.2823 | 0.2450 | 0.2989 | 0.8136 | 0.3593 | 300 |
| real Online Retail II (trained on own past) | Chronos-Bolt (zero-shot) | 0.2641 | 0.2316 | 0.2785 | 0.7877 | 0.2752 | 300 |
| real Online Retail II (trained on own past) | Ensemble LGBM+Chronos | 0.2685 | 0.2372 | 0.2824 | 0.6907 | 0.3065 | 300 |
| real Online Retail II (pretrain synthetic + own past) | Global-LGBM-Q | 0.2818 | 0.2464 | 0.2975 | 0.6181 | 0.3263 | 300 |
| real Online Retail II (pretrain synthetic + own past) | Global-LGBM-Q+CQR | 0.2794 | 0.2457 | 0.2944 | 0.8536 | 0.3263 | 300 |
| real Online Retail II (pretrain synthetic + own past) | Ensemble LGBM+Chronos | 0.2684 | 0.2351 | 0.2832 | 0.6440 | 0.2957 | 300 |

## T6 số dư 13 tuần — khoảng

Nguồn: `outputs/t6/t6_interval_metrics.csv`

Giao thức: cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek

| model | horizon | cov80 | IS80 | pinball | MAE_p50 | bootstrap_n |
|---|---|---|---|---|---|---|
| Direct LGBM-Q (src) | w1-4 | 0.5913 | 12.1 | 0.8178 | 2.4965 | 300 |
| Direct LGBM-Q (src) | w5-13 | 0.5504 | 21.8 | 1.4278 | 4.2123 | 300 |
| MC with B1 point dates | w1-4 | 0.1865 | 23.3 | 1.2353 | 2.7561 | 300 |
| MC with B1 point dates | w5-13 | 0.4626 | 21.8 | 1.3021 | 3.4579 | 300 |
| MC-copula-t (T1+T4+T5) | w1-4 | 0.5093 | 9.9757 | 0.6511 | 1.9116 | 300 |
| MC-copula-t (T1+T4+T5) | w5-13 | 0.6137 | 16.6 | 1.0869 | 3.1936 | 300 |
| MC-copula-t + ACI | w1-4 | 0.7462 | 9.4868 | 0.6348 | 1.9116 | 300 |
| MC-copula-t + ACI | w5-13 | 0.7521 | 16.8 | 1.0917 | 3.1936 | 300 |
| MC-copula-t + calibrated cure | w1-4 | 0.5117 | 9.9699 | 0.6506 | 1.9099 | 300 |
| MC-copula-t + calibrated cure | w5-13 | 0.6128 | 16.7 | 1.0871 | 3.1921 | 300 |
| MC-independent (rho=0) | w1-4 | 0.3280 | 12.2 | 0.7177 | 1.8697 | 300 |
| MC-independent (rho=0) | w5-13 | 0.5208 | 18.6 | 1.1527 | 3.2049 | 300 |
| Naive (known out + avg in) | w1-4 | 0.6703 | 13.6 | 0.8821 | 2.5689 | 300 |
| Naive (known out + avg in) | w5-13 | 0.6470 | 31.0 | 2.0575 | 6.1374 | 300 |

## T6 xác suất thiếu hụt

Nguồn: `outputs/t6/t6_shortfall_metrics.csv`

Giao thức: cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek

| model | measurement_version | seed | shortfall_rate_4w | Brier_4w | AUC_4w | shortfall_rate_13w | Brier_13w | AUC_13w |
|---|---|---|---|---|---|---|---|---|
| Direct LGBM-Q (src) | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0540 | 0.9174 | 0.2514 | 0.1282 | 0.7919 |
| MC with B1 point dates | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0621 | 0.8650 | 0.2514 | 0.1041 | 0.8796 |
| MC-copula-t (T1+T4+T5) | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0392 | 0.9783 | 0.2514 | 0.0918 | 0.9023 |
| MC-copula-t + calibrated cure | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0392 | 0.9784 | 0.2514 | 0.0918 | 0.9024 |
| MC-independent (rho=0) | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0394 | 0.9708 | 0.2514 | 0.0930 | 0.9009 |
| Naive (known out + avg in) | cash-asof-outflows-owner-tcopula-v5-true-labels-fullweek | 7 | 0.1731 | 0.0577 | 0.9510 | 0.2514 | 0.1447 | 0.8211 |

## T7 điểm gãy

Nguồn: `outputs/t7/t7_changepoint.csv`

Giao thức: changepoint-consensus-v2

| detector | params | world | detection_rate_180d | median_lag_days | false_alarms_per_cust_year | macro_alarms_per_cust_year | n_eligible_shifted | measurement_version | seed |
|---|---|---|---|---|---|---|---|---|---|
| CUSUM [pit] | {'k': 0.25, 'h': 5} | src (tuned) | 0.5556 | 61.0 | 0.4664 | 0.1503 | 18 | changepoint-consensus-v2 | 7 |
| CUSUM [pit] | {'k': 0.25, 'h': 5} | held-out (tgt+sens_uk+sens_coface) | 0.5238 | 50.0 | 0.6334 | 0.2021 | 21 | changepoint-consensus-v2 | 7 |
| Page-Hinkley [pit] | {'delta': 0.1, 'lam': 6} | src (tuned) | 0.5000 | 75.0 | 0.3041 | 0.1002 | 18 | changepoint-consensus-v2 | 7 |
| Page-Hinkley [pit] | {'delta': 0.1, 'lam': 6} | held-out (tgt+sens_uk+sens_coface) | 0.4286 | 65.0 | 0.4244 | 0.1349 | 21 | changepoint-consensus-v2 | 7 |
| BOCPD [pit] | {'hazard': 0.03333333333333333, 'thr': 0.3} | src (tuned) | 0.1111 | 89.0 | 0.0985 | 0.0287 | 18 | changepoint-consensus-v2 | 7 |
| BOCPD [pit] | {'hazard': 0.03333333333333333, 'thr': 0.3} | held-out (tgt+sens_uk+sens_coface) | 0.0952 | 108.0 | 0.1322 | 0.0400 | 21 | changepoint-consensus-v2 | 7 |
| Consensus 2-of-3 [pit] | {'window_days': 45} | src (tuned) | 0.1111 | 102.5 | 0.0351 | 0.0043 | 18 | changepoint-consensus-v2 | 7 |
| Consensus 2-of-3 [pit] | {'window_days': 45} | held-out (tgt+sens_uk+sens_coface) | 0.0476 | 163.0 | 0.0400 | 0.0096 | 21 | changepoint-consensus-v2 | 7 |

## T9 khớp sao kê

Nguồn: `outputs/t9/t9_reconciliation_tgt.csv`

Giao thức: t9-asof-known-customers-v5

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | settled_invoice_coverage | pay_date_MAE_ledger_days | method | link_precision_ci_low | link_precision_ci_high | link_recall_ci_low | link_recall_ci_high | link_f1_ci_low | link_f1_ci_high | pay_date_MAE_ci_low | pay_date_MAE_ci_high | auto_coverage_ci_low | auto_coverage_ci_high | bootstrap_n | n_firms | txn_customer_recall | auto_txn_coverage | n_review | measurement_version | seed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9521 | 0.5739 | 0.7161 | 4695 | 7789 | 0.0032 | 1.3325 | 0.9598 | 0.6548 | 12.6 | ML customer + subset (src->tgt) | 0.9165 | 0.9830 | 0.4285 | 0.7073 | 0.5848 | 0.8200 | 0.4038 | 2.1836 | 0.5440 | 0.6857 | 300 | 14 | 0.9702 |  |  | t9-asof-known-customers-v5 | 1 |
| 0.9644 | 0.4386 | 0.6029 | 3542 | 7789 | 0.0226 | 0.6972 | 0.9830 | 0.4893 | 12.6 | R1 observed unique-amount rule | 0.9527 | 0.9765 | 0.3391 | 0.5435 | 0.5005 | 0.6981 | 0.3827 | 0.9436 | 0.4990 | 0.6173 | 300 | 14 |  |  |  | t9-asof-known-customers-v5 | 1 |
| 1.0000 | 0.1973 | 0.3296 | 1537 | 7789 | 0.0000 | 0.0000 | 1.0000 | 0.2163 | 12.6 | R2 observed memo rule | 1.0000 | 1.0000 | 0.1446 | 0.2278 | 0.2526 | 0.3711 | 0.0000 | 0.0000 | 0.1711 | 0.2366 | 300 | 14 |  |  |  | t9-asof-known-customers-v5 | 1 |
| 0.9399 | 0.6102 | 0.7400 | 5057 | 7789 | 0.0274 | 1.4532 | 0.9592 | 0.6972 | 12.6 | Hybrid rules+ML auto (tau=.9) | 0.9126 | 0.9686 | 0.4719 | 0.7263 | 0.6261 | 0.8280 | 0.6700 | 2.0502 | 0.6196 | 0.7213 | 300 | 14 |  | 0.6823 | 1997.0 | t9-asof-known-customers-v5 | 1 |
| 0.9424 | 0.5903 | 0.7259 | 4879 | 7789 | 0.0000 | 1.6859 | 0.9537 | 0.6779 | 12.6 | Oracle customer / subset allocation | 0.8903 | 0.9778 | 0.4388 | 0.7273 | 0.5916 | 0.8316 | 0.5273 | 3.2697 | 0.5583 | 0.7001 | 300 | 14 |  |  |  | t9-asof-known-customers-v5 | 1 |

## WP-0 hợp đồng dữ liệu

Nguồn: `outputs/wp0/world_contract_summary.csv`

Kiểm tra dữ liệu, không phải đo chất lượng mô hình.

| world | checks | passed | failed |
|---|---|---|---|
| sens_coface | 68 | 68 | 0 |
| sens_uk | 68 | 68 | 0 |
| src | 68 | 68 | 0 |
| tgt | 68 | 68 | 0 |

## Cổng hiện hành

Nguồn: `outputs/implementation/gates.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| gate | status | reason | evidence |
|---|---|---|---|
| G1 | passed | Giảm WAPE >=30% ở hai origin | outputs/t1/A_rolling_origin_src.csv |
| G2 | passed | IBS so với B1 trên hai origin | outputs/t1/A_rolling_origin_src.csv |
| G3 | failed | Mondrian CQR nguồn: cov80 75–85% ở hai gốc và IS80 không xấu hơn CQR hai phía toàn cục | outputs/t1/G3/metrics.csv |
| G4 | failed | ECE4 <=0.05 trên cả hai origin | outputs/t1/A_rolling_origin_src.csv |
| G5 | passed | BLEND w chọn trên calibration; G5 CI: pinball so B1 >=10% và CI thấp so B1d >0; G6 cả ci/bpi: CI cao >=0 và điểm >=-2% | outputs/t1/real_v2/C_real_v2.csv |
| G6 | passed | BLEND w chọn trên calibration; G5 CI: pinball so B1 >=10% và CI thấp so B1d >0; G6 cả ci/bpi: CI cao >=0 và điểm >=-2% | outputs/t1/real_v2/C_real_v2.csv |
| G7 | failed | Fine-tune M12 cải thiện pinball >=10% | outputs/t1/B_domain_adaptation_tgt.csv |
| G8 | failed | SBA drop EXEMPT, kỳ hạn <=120 tháng, nhãn chín trước test | outputs/t2_t3/t2_sba_variants.csv |
| G9 | passed | So mốc doanh thu trên nguồn và đích | outputs/t4/t4_revenue_forecast.csv |
| G10 | passed | Đối chứng thật, có phân biệt cụm series | outputs/t4/t4_revenue_forecast.csv |
| G11 | failed | Quy tắc cần cả hồi quy và xác minh chuyên môn; hiện chưa xác minh | outputs/rules/rules_review.csv |
| G12 | passed | Nhãn T9 ước lượng: cov80 75–85%, IS80 thắng đủ bốn đối chứng, Brier thắng naive | outputs/e2e/e2e_metrics.csv |
| G13 | failed | Isotonic + xác nhận 1 tuần, τ=0.3, chọn trên backtest src; phát hiện 0.94 [0.87; 1.00], báo giả 2.08/công ty-năm | outputs/e2e/protocol/alert_policy_v2.csv |
| G14 | failed | Bộ phát hiện chọn ngưỡng trên nguồn; kết quả giữ lại | outputs/t7/t7_changepoint.csv |
| G15 | failed | T9 P5: tau/ứng viên chọn trên DN nguồn; F1 >=.8, precision >=.95, coverage >=.6, MAE ngày <=3; chưa đổi pipeline E2E | outputs/t9/sprint3/target_metrics.csv |
| G16 | passed | Chèn lỗi có nhãn, precision/recall >=.95 | outputs/wp0/T0_quality_metrics.csv |
| G17 | failed | Giảm MAE >=10% trên lời hứa sạch và nhiễu | outputs/t1/EF_t8_t9*.csv |
| G18 | passed | Điểm ước lượng: T9 thu hẹp >=50% khoảng cách WAPE với oracle ở cả hai chân trời; CI xa còn rộng, không bảo đảm cho mọi DN | outputs/t1/T9_T1_gap_reduction.csv |
| G5_v1 | failed | LEGACY v1: Ensemble vs B1 trên AR thật, cohort đã chín | outputs/t1/C_real_domains.legacy_expand.csv |
| G6_v1 | failed | LEGACY v1: Ensemble không thua B1d trên hai bộ thật | outputs/t1/C_real_domains.legacy_expand.csv |
| G13_v1 | failed | v1 (kiểm toán): ngưỡng theo chi phí từng tuần trên 144 điểm nguồn | outputs\e2e\protocol\alert_policy.csv |
| G13_tgt2 | passed | THAM KHẢO, nhãn oracle (cận trên): 71 sự kiện, phát hiện 0.75 [0.59; 0.84], báo giả 0.75 [0.43; 1.10] | outputs/tgt2/alert_policy_tgt2.csv |
| G15_v1 | failed | LEGACY allocation: WP4: F1 >=.80 và thắng quy tắc, precision >=.95, tự động >=.6, MAE ngày <=3 | outputs/t9/t9_reconciliation_tgt.csv |
| G15_tgt3 | failed | T9 v2 chọn trên nguồn, đo một lần trên tgt3 niêm phong: P 0.962, R 0.557, F1 0.706, tự động 0.689, MAE 0.82 ngày | outputs/t9/v2/target_metrics.csv |

## Kiểm thử môi trường hiện có và môi trường mới

Nguồn: `outputs/implementation/test_summary.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| environment | tests | failures | skipped | evidence |
|---|---|---|---|---|
| workspace_venv | 316 | 0 | 0 | implementation\tests.xml |
| fresh_venv_from_requirements | 316 | 0 | 0 | implementation\tests_clean.xml |

## Berka thật: phân vị trực tiếp + ACI

Nguồn: `outputs/berka/cash_metrics.csv`

Giao thức: berka-train-through1996-test1997-98-v1

| model | cov80 | IS80 | ci_low | ci_high | bootstrap_n | cluster_unit | n_accounts | measurement_version | seed |
|---|---|---|---|---|---|---|---|---|---|
| Direct LGBM-Q | 0.7685 | 17.0 | 0.7636 | 0.7729 | 300 | account | 1478 | berka-train-through1996-test1997-98-v1 | 7 |
| Direct LGBM-Q + ACI | 0.7692 | 16.9 | 0.7646 | 0.7733 | 300 | account | 1478 | berka-train-through1996-test1997-98-v1 | 7 |

## SBA nhiều chính sách EXEMPT

Nguồn: `outputs/t2_t3/t2_sba_variants.csv`

Giao thức: sba-exempt-matured-v3

| task | model | n_test | exempt_policy | stratum | n_unobserved_excluded | seed | measurement_version | train_last_fy | calibration_fy | ROC_AUC | PR_AUC | Brier | logloss | ECE | mean_p | base_rate | expected_vs_actual_default_amount | PR_AUC_over_base | Brier_ci_low | Brier_ci_high | bootstrap_n | company_bootstrap_status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 105084 | drop | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0287 | 0.0280 | 0.1338 | 0.0120 | 0.0167 | 0.0287 | 1.1678 | 1.0000 | 0.0269 | 0.0290 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 25475 | drop | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0007 | 0.0010 | 0.0197 | 0.0160 | 0.0167 | 0.0007 | 20.9 | 1.0000 | 0.0007 | 0.0013 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 105084 | drop | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.7178 | 0.0625 | 0.0276 | 0.1244 | 0.0103 | 0.0198 | 0.0287 | 0.7438 | 2.1805 | 0.0265 | 0.0285 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 25475 | drop | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.6992 | 0.0014 | 0.0007 | 0.0064 | 0.0009 | 0.0016 | 0.0007 | 0.8906 | 2.0278 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 105084 | drop | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9113 | 0.1705 | 0.0275 | 0.1081 | 0.0206 | 0.0174 | 0.0287 | 0.5574 | 5.9432 | 0.0265 | 0.0284 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 25475 | drop | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8824 | 0.0108 | 0.0007 | 0.0051 | 0.0001 | 0.0008 | 0.0007 | 0.7229 | 15.3 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 105084 | drop | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9108 | 0.1665 | 0.0282 | 0.1107 | 0.0222 | 0.0203 | 0.0287 | 0.6295 | 5.8065 | 0.0273 | 0.0291 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 25475 | drop | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8630 | 0.0091 | 0.0007 | 0.0055 | 0.0004 | 0.0003 | 0.0007 | 0.1880 | 12.9 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 166591 | keep | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0181 | 0.0178 | 0.0906 | 0.0019 | 0.0162 | 0.0181 | 2.1128 | 1.0000 | 0.0171 | 0.0184 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 56668 | keep | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0003 | 0.0006 | 0.0177 | 0.0159 | 0.0162 | 0.0003 | 43.0 | 1.0000 | 0.0004 | 0.0007 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 166591 | keep | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.7602 | 0.0507 | 0.0175 | 0.0831 | 0.0024 | 0.0169 | 0.0181 | 1.1865 | 2.8043 | 0.0169 | 0.0182 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 56668 | keep | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.7121 | 0.0007 | 0.0003 | 0.0036 | 0.0011 | 0.0014 | 0.0003 | 1.8082 | 2.1656 | 0.0002 | 0.0005 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 166591 | keep | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9298 | 0.1477 | 0.0176 | 0.0711 | 0.0124 | 0.0122 | 0.0181 | 0.7431 | 8.1646 | 0.0170 | 0.0182 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 56668 | keep | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8944 | 0.0093 | 0.0003 | 0.0026 | 0.0003 | 0.0006 | 0.0003 | 1.2471 | 29.3 | 0.0002 | 0.0005 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 166591 | keep | term<=120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9290 | 0.1428 | 0.0182 | 0.0721 | 0.0134 | 0.0145 | 0.0181 | 0.8599 | 7.8905 | 0.0176 | 0.0188 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 56668 | keep | term>120 | 0 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8826 | 0.0048 | 0.0003 | 0.0026 | 0.0000 | 0.0003 | 0.0003 | 0.4888 | 15.1 | 0.0002 | 0.0005 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 105084 | censor | term<=120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0287 | 0.0280 | 0.1338 | 0.0120 | 0.0167 | 0.0287 | 1.1678 | 1.0000 | 0.0269 | 0.0290 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 25475 | censor | term>120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.5000 | 0.0007 | 0.0010 | 0.0197 | 0.0160 | 0.0167 | 0.0007 | 20.9 | 1.0000 | 0.0007 | 0.0013 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 105084 | censor | term<=120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.7178 | 0.0625 | 0.0276 | 0.1244 | 0.0103 | 0.0198 | 0.0287 | 0.7438 | 2.1805 | 0.0265 | 0.0285 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 25475 | censor | term>120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.6992 | 0.0014 | 0.0007 | 0.0064 | 0.0009 | 0.0016 | 0.0007 | 0.8906 | 2.0278 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 105084 | censor | term<=120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9113 | 0.1705 | 0.0275 | 0.1081 | 0.0206 | 0.0174 | 0.0287 | 0.5574 | 5.9432 | 0.0265 | 0.0284 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 25475 | censor | term>120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8824 | 0.0108 | 0.0007 | 0.0051 | 0.0001 | 0.0008 | 0.0007 | 0.7229 | 15.3 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 105084 | censor | term<=120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.9108 | 0.1665 | 0.0282 | 0.1107 | 0.0222 | 0.0203 | 0.0287 | 0.6295 | 5.8065 | 0.0273 | 0.0291 | 300 | borrower_name_address_proxy |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2014) | 25475 | censor | term>120 | 144908 | 1 | sba-exempt-matured-v3 | 2013 | 2014 | 0.8630 | 0.0091 | 0.0007 | 0.0055 | 0.0004 | 0.0003 | 0.0007 | 0.1880 | 12.9 | 0.0004 | 0.0011 | 300 | borrower_name_address_proxy |

## T9 precision–coverage (ngưỡng định trước .9)

Nguồn: `outputs/t9/precision_coverage.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| tau | threshold_chosen | n_auto_txns | auto_coverage | link_precision | link_recall | link_f1 | n_pred | n_true |
|---|---|---|---|---|---|---|---|---|
| 0.5000 | False | 4307 | 0.6853 | 0.9305 | 0.6133 | 0.7393 | 5134 | 7789 |
| 0.7000 | False | 4297 | 0.6837 | 0.9319 | 0.6111 | 0.7382 | 5108 | 7789 |
| 0.8000 | False | 4289 | 0.6824 | 0.9386 | 0.6101 | 0.7395 | 5063 | 7789 |
| 0.9000 | True | 4288 | 0.6823 | 0.9399 | 0.6102 | 0.7400 | 5057 | 7789 |
| 0.9500 | False | 4256 | 0.6772 | 0.9439 | 0.6005 | 0.7340 | 4955 | 7789 |
| 0.9900 | False | 4218 | 0.6711 | 0.9457 | 0.5906 | 0.7271 | 4864 | 7789 |

## T6 chính sách cảnh báo theo sự kiện

Nguồn: `outputs/t6/alert_policy.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| model | cost_ratio | horizon | threshold | calibration_cost | threshold_selected_on | n_events | detected_at_least_4w | median_lead_weeks | false_alarms_per_firm_year |
|---|---|---|---|---|---|---|---|---|---|
| Direct LGBM-Q (src) | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.1250 | 0.7143 | 0.2150 |
| MC with B1 point dates | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.0625 | 0.0000 | 0.0000 |
| MC-copula-t (T1+T4+T5) | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.1250 | 2.1429 | 0.0717 |
| MC-copula-t + calibrated cure | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.1250 | 2.1429 | 0.0717 |
| MC-independent (rho=0) | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.1250 | 2.0714 | 0.0000 |
| Naive (known out + avg in) | 2 | 4 | 0.6000 | 0.1944 | source_only | 16 | 0.1250 | 2.1429 | 0.0000 |
| Direct LGBM-Q (src) | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.9375 | 11.6 | 3.6554 |
| MC with B1 point dates | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.7500 | 8.7857 | 1.5768 |
| MC-copula-t (T1+T4+T5) | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.9375 | 12.1 | 2.5086 |
| MC-copula-t + calibrated cure | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.9375 | 12.1 | 2.4369 |
| MC-independent (rho=0) | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.9375 | 12.1 | 2.4369 |
| Naive (known out + avg in) | 2 | 13 | 0.1000 | 0.3333 | source_only | 16 | 0.9375 | 12.1 | 2.1502 |
| Direct LGBM-Q (src) | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.1875 | 3.1429 | 3.0103 |
| MC with B1 point dates | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.1875 | 2.2857 | 0.2150 |
| MC-copula-t (T1+T4+T5) | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.1875 | 3.1429 | 1.5768 |
| MC-copula-t + calibrated cure | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.1875 | 3.1429 | 1.5052 |
| MC-independent (rho=0) | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.1875 | 3.1429 | 0.7167 |
| Naive (known out + avg in) | 5 | 4 | 0.0500 | 0.2986 | source_only | 16 | 0.2500 | 3.1429 | 2.4369 |
| Direct LGBM-Q (src) | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.9375 | 11.6 | 3.6554 |
| MC with B1 point dates | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.8750 | 11.1 | 2.1502 |
| MC-copula-t (T1+T4+T5) | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.9375 | 12.3 | 3.0103 |
| MC-copula-t + calibrated cure | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.9375 | 12.3 | 2.9386 |
| MC-independent (rho=0) | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.9375 | 12.1 | 2.5803 |
| Naive (known out + avg in) | 5 | 13 | 0.0300 | 0.4861 | source_only | 16 | 0.9375 | 12.1 | 2.1502 |
| Direct LGBM-Q (src) | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.1875 | 3.1429 | 3.0103 |
| MC with B1 point dates | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.1875 | 2.2857 | 0.2150 |
| MC-copula-t (T1+T4+T5) | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.1875 | 3.1429 | 1.5768 |
| MC-copula-t + calibrated cure | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.1875 | 3.1429 | 1.5052 |
| MC-independent (rho=0) | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.1875 | 3.1429 | 0.7167 |
| Naive (known out + avg in) | 10 | 4 | 0.0500 | 0.4375 | source_only | 16 | 0.2500 | 3.1429 | 2.4369 |
| Direct LGBM-Q (src) | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.9375 | 11.6 | 3.6554 |
| MC with B1 point dates | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.8750 | 11.1 | 2.1502 |
| MC-copula-t (T1+T4+T5) | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.9375 | 12.3 | 3.0103 |
| MC-copula-t + calibrated cure | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.9375 | 12.3 | 2.9386 |
| MC-independent (rho=0) | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.9375 | 12.1 | 2.5803 |
| Naive (known out + avg in) | 10 | 13 | 0.0300 | 0.6597 | source_only | 16 | 0.9375 | 12.1 | 2.1502 |

## E2E nguồn→fine-tune từ XML/CSV; trạng thái giao thức trong CSV

Nguồn: `outputs/e2e/e2e_metrics.csv`

Giao thức: cash-e2e-estimated_T9-v1-fullweek, cash-e2e-oracle_bank_same_inputs-v1-fullweek

| model | horizon | cov80 | IS80 | pinball | MAE_p50 | seed | measurement_version | cov80_ci_low | cov80_ci_high | bootstrap_n | full_protocol | label_mode | n_firms | weeks | seconds | source_training_budget | limitation | oracle_ablation_completed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Direct LGBM-Q (src) | w1-4 | 0.5982 | 12.5 | 0.8396 | 2.5413 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.5506 | 0.6421 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Direct LGBM-Q (src) | w5-13 | 0.5395 | 22.4 | 1.4849 | 4.4266 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.4692 | 0.5975 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC with B1 point dates | w1-4 | 0.0361 | 170.2 | 8.5833 | 17.5 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.0223 | 0.0496 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC with B1 point dates | w5-13 | 0.2007 | 89.2 | 4.6667 | 10.2 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.1265 | 0.2646 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t (T1+T4+T5) | w1-4 | 0.4523 | 12.2 | 0.7713 | 2.1834 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.3492 | 0.5287 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t (T1+T4+T5) | w5-13 | 0.6305 | 20.6 | 1.3526 | 3.9934 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.4986 | 0.7275 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + ACI | w1-4 | 0.7545 | 12.0 | 0.7639 | 2.1834 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.6514 | 0.8352 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + ACI | w5-13 | 0.7669 | 21.0 | 1.3641 | 3.9934 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.6483 | 0.8567 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + calibrated cure | w1-4 | 0.4691 | 11.9 | 0.7598 | 2.1743 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.3690 | 0.5488 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + calibrated cure | w5-13 | 0.6424 | 20.2 | 1.3352 | 3.9651 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.5142 | 0.7385 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-independent (rho=0) | w1-4 | 0.3098 | 13.6 | 0.7881 | 2.0080 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.2498 | 0.3658 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-independent (rho=0) | w5-13 | 0.4608 | 23.5 | 1.3985 | 3.6930 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.3430 | 0.5608 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Naive (known out + avg in) | w1-4 | 0.6703 | 13.6 | 0.8821 | 2.5689 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.6239 | 0.7143 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Naive (known out + avg in) | w5-13 | 0.6470 | 31.0 | 2.0575 | 6.1374 | 7 | cash-e2e-estimated_T9-v1-fullweek | 0.5499 | 0.7419 | 300 | True | estimated_T9 | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Direct LGBM-Q (src) | w1-4 | 0.6047 | 11.9 | 0.8122 | 2.4885 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.5585 | 0.6491 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Direct LGBM-Q (src) | w5-13 | 0.5569 | 21.6 | 1.4207 | 4.2117 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.4779 | 0.6341 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC with B1 point dates | w1-4 | 0.1477 | 30.4 | 1.5957 | 3.4899 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.0949 | 0.1988 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC with B1 point dates | w5-13 | 0.4333 | 23.2 | 1.3748 | 3.6115 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.3541 | 0.5044 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t (T1+T4+T5) | w1-4 | 0.5096 | 9.9619 | 0.6487 | 1.9000 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.4222 | 0.5837 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t (T1+T4+T5) | w5-13 | 0.6245 | 16.5 | 1.0760 | 3.1640 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.5255 | 0.7039 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + ACI | w1-4 | 0.7452 | 9.5137 | 0.6338 | 1.9000 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.6561 | 0.8227 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + ACI | w5-13 | 0.7563 | 16.8 | 1.0857 | 3.1640 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.6519 | 0.8396 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + calibrated cure | w1-4 | 0.5130 | 9.9522 | 0.6481 | 1.8984 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.4246 | 0.5883 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-copula-t + calibrated cure | w5-13 | 0.6241 | 16.5 | 1.0756 | 3.1613 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.5249 | 0.7036 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-independent (rho=0) | w1-4 | 0.3348 | 12.1 | 0.7154 | 1.8668 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.2783 | 0.3901 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| MC-independent (rho=0) | w5-13 | 0.5304 | 18.3 | 1.1384 | 3.1784 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.4388 | 0.6160 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Naive (known out + avg in) | w1-4 | 0.6703 | 13.6 | 0.8821 | 2.5689 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.6239 | 0.7143 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |
| Naive (known out + avg in) | w5-13 | 0.6470 | 31.0 | 2.0575 | 6.1374 | 7 | cash-e2e-oracle_bank_same_inputs-v1-fullweek | 0.5499 | 0.7419 | 300 | True | oracle_bank_same_inputs | 14 | 52 | 2768.3 | 40000 | synthetic;declared_schedule_and_observed_balances_required;source_budget_limited | True |

## 12 hard-case worlds

Nguồn: `outputs/data/hard_cases.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| world | case | n_firms | n_invoices | checks | passed | smoke | seed |
|---|---|---|---|---|---|---|---|
| hc_lumpy_customer | lumpy_customer | 12 | 76887 | 68 | 68 | False | 901 |
| hc_group_payer | group_payer | 12 | 68481 | 68 | 68 | False | 901 |
| hc_heterogeneity | heterogeneity | 12 | 68481 | 68 | 68 | False | 901 |
| hc_cod_realistic | cod_realistic | 12 | 68481 | 68 | 68 | False | 901 |
| hc_discount_early | discount_early | 12 | 68481 | 68 | 68 | False | 901 |
| hc_retention | retention | 12 | 68481 | 68 | 68 | False | 901 |
| hc_fx | fx | 12 | 68481 | 70 | 70 | False | 901 |
| hc_credit_note | credit_note | 12 | 68481 | 68 | 68 | False | 901 |
| hc_verbal | verbal | 12 | 68481 | 68 | 68 | False | 901 |
| hc_supply_shock | supply_shock | 12 | 68481 | 68 | 68 | False | 901 |
| hc_seasonal_extreme | seasonal_extreme | 12 | 67883 | 68 | 68 | False | 901 |
| hc_new_company | new_company | 12 | 7318 | 68 | 68 | False | 901 |

## Hard-case: kiểm tra riêng mục tiêu tình huống

Nguồn: `outputs/data/hard_case_fidelity.csv`

Giao thức: hard-case-observed-fidelity-v1

| case | metric | value | target_low | target_high | point_target_met | limitation | measurement_version | world |
|---|---|---|---|---|---|---|---|---|
| lumpy_customer | firms_with_anchor_revenue_share_40_60 | 1.0000 | 1.0000 | 1.0000 | True | Tỷ trọng doanh thu thực hiện, không chỉ trọng số sinh | hard-case-observed-fidelity-v1 | hc_lumpy_customer_v2 |
| group_payer | different_group_payer_share | 0.6124 | 0.0100 | 1.0000 | True | Chưa đo lại recall T9 trên hard case | hard-case-observed-fidelity-v1 | hc_group_payer |
| heterogeneity | customer_between_variance_share | 0.3796 | 0.5500 | 0.6500 | False | ANOVA mô tả trên nhãn thật tổng hợp; chưa chứng minh nhân quả | hard-case-observed-fidelity-v1 | hc_heterogeneity |
| cod_realistic | COD_invoice_count_share | 0.2191 | 0.2000 | 0.3000 | True | nan | hard-case-observed-fidelity-v1 | hc_cod_realistic |
| discount_early | discounted_invoices_with_net30_terms | 1.0000 | 1.0000 | 1.0000 | True | nan | hard-case-observed-fidelity-v1 | hc_discount_early_v2 |
| discount_early | discounted_invoices_paid_on_business_day_10 | 1.0000 | 1.0000 | 1.0000 | True | nan | hard-case-observed-fidelity-v1 | hc_discount_early_v2 |
| discount_early | discounted_paid_fraction_mean | 0.9800 | 0.9799 | 0.9801 | True | Làm tròn nghìn VND | hard-case-observed-fidelity-v1 | hc_discount_early_v2 |
| retention | retained_fraction_mean | 0.0500 | 0.0499 | 0.0501 | True | Kịch bản tổng hợp; cần lịch hợp đồng thật | hard-case-observed-fidelity-v1 | hc_retention |
| fx | USD_invoice_count_share | 0.1493 | 0.1200 | 0.1800 | True | Tỷ giá tổng hợp, sổ quy về VND | hard-case-observed-fidelity-v1 | hc_fx |
| fx | relative_currency_conversion_error | 0.0000 | 0.0000 | 0.0000 | True | nan | hard-case-observed-fidelity-v1 | hc_fx |
| credit_note | adjustment_references_present_in_invoice_chain | 0.0000 | 1.0000 | 1.0000 | False | Hiện chỉ đổi mã/tham chiếu thay thế; chưa giữ đủ bản gốc, huỷ, điều chỉnh | hard-case-observed-fidelity-v1 | hc_credit_note |
| verbal | customers_with_verbal_extension | 0.1712 | 0.1200 | 0.1800 | True | nan | hard-case-observed-fidelity-v1 | hc_verbal |
| verbal | unrecorded_extension_invoices_with_recorded_promise | 0.0000 | 0.0000 | 0.0000 | True | nan | hard-case-observed-fidelity-v1 | hc_verbal |
| supply_shock | sector_localization_implemented | 1.0000 | 1.0000 | 1.0000 | True | Cần thêm đánh giá tác động T6/T7 | hard-case-observed-fidelity-v1 | hc_supply_shock_v2 |
| seasonal_extreme | revenue_in_four_focus_months | 0.5850 | 0.5700 | 0.6300 | True | nan | hard-case-observed-fidelity-v1 | hc_seasonal_extreme |
| new_company | max_observed_history_days | 359.0 | 0.0000 | 365.0 | True | nan | hard-case-observed-fidelity-v1 | hc_new_company |

## C2ST cấu trúc

Nguồn: `outputs/data/c2st.csv`

Giao thức: structural-company-split-v1

| world | AUC | ci_low | ci_high | seed | n_train | n_test | bootstrap_n | measurement_version |
|---|---|---|---|---|---|---|---|---|
| src | 0.9964 | 0.8847 | 0.9978 | 7 | 120189 | 29809 | 300 | structural-company-split-v1 |
| sens_uk | 0.9957 | 0.8439 | 0.9966 | 7 | 101889 | 37140 | 300 | structural-company-split-v1 |
| sens_coface | 0.9968 | 0.8858 | 0.9982 | 7 | 100381 | 20200 | 300 | structural-company-split-v1 |

## Benchmark máy phát

Nguồn: `outputs/data/generator_benchmark.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| n_firms | n_invoices | legacy_seconds | vectorized_seconds | speedup | meets_5x | value_tables_equal | seed | scope |
|---|---|---|---|---|---|---|---|---|
| 6 | 29817 | 13.4 | 8.6570 | 1.5450 | False | True | 314 | full_world_small_not_1M |

## Lời hứa nhiễu: tính bất biến bảng tài chính

Nguồn: `outputs/data/noisy_promise_coupling.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| table | unchanged | n_rows |
|---|---|---|
| invoices | True | 193469 |
| payments | True | 202810 |
| bank_txns | True | 188260 |
| outflows | True | 35217 |
| daily_cash | True | 102280 |
| firms | True | 40 |
| customers | True | 3427 |
| macro | True | 366 |
| events | True | 2436 |

## Cổng số của 200 mẫu cảnh báo

Nguồn: `outputs/service/alert_gate_summary.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| cases | passed | failed | human_naturalness_review |
|---|---|---|---|
| 200 | 200 | 0 | False |

## DA1–DA7: kết luận và bằng chứng còn thiếu

Nguồn: `outputs/t1/DA_hypotheses.csv`

Giao thức: da-asof-evidence-v2-fullweek

| hypothesis | status | measured_value | paired_ci_low | paired_ci_high | target | evidence | limitation | measurement_version |
|---|---|---|---|---|---|---|---|---|
| DA1 | supported | 59.1 | 46.6 | 65.6 | WAPE giảm >=20% so B1 ở M0 | outputs/t1/DA_paired_comparisons.csv | Xác nhận riêng: tối đa 40k snapshot nguồn/đích, 300 vòng, FT 150; không thay bảng B cũ. CI phải đạt ngưỡng giả thuyết, không chỉ ước lượng điểm. | da-asof-evidence-v2-fullweek |
| DA2 | rejected | -7.8251 | -16.9 | -2.7142 | Pinball fine-tune M3 giảm >=10% so zero-shot | outputs/t1/DA_paired_comparisons.csv | Xác nhận riêng: tối đa 40k snapshot nguồn/đích, 300 vòng, FT 150; không thay bảng B cũ. CI phải đạt ngưỡng giả thuyết, không chỉ ước lượng điểm. | da-asof-evidence-v2-fullweek |
| DA3 | rejected | -11.0 | -15.0 | 44.0 | Fine-tune thắng ở M3/M6 và TGT-only bắt kịp tại M24 | outputs/t1/DA_paired_comparisons.csv | Xác nhận riêng: tối đa 40k snapshot nguồn/đích, 300 vòng, FT 150; không thay bảng B cũ. DA3 là giao của M3/M6/M24. | da-asof-evidence-v2-fullweek |
| DA4 | not_demonstrated | -0.4279 | -1.0169 | 1.2843 | IW thắng pooled khi khoảng cách miền lớn | outputs/t1/DA_paired_comparisons.csv | Xác nhận riêng: tối đa 40k snapshot nguồn/đích, 300 vòng, FT 150; không thay bảng B cũ. DA4 yêu cầu cả sens_uk và sens_coface có CI >0; tgt là đối chứng. | da-asof-evidence-v2-fullweek |
| DA5 | not_measured |  |  |  | CQR M3 có cov80 75–85% | nan | M3 không đủ cửa sổ hiệu chỉnh tách 120 ngày; không dùng test để lấp | da-asof-evidence-v2-fullweek |
| DA6 | not_demonstrated | 0.0000 |  |  | Nguồn lớn >=5x giảm M*; bootstrap cặp theo công ty | nan | M*: zero-shot tại M0, fine-tune khi M>0; ngưỡng pinball <=0.9 B1d; kiểm trên tổng hợp; cả ba đã ở sàn M*=0, chưa thể chứng minh giảm thêm lịch sử | da-asof-evidence-v2-fullweek |
| DA7 | not_demonstrated | -2.1484 |  |  | Đặc trưng sốc chung giảm pinball ở cả hai giai đoạn khủng hoảng; CI cặp >0 | nan | Nguồn trước mỗi origin 120 ngày; cùng ngân sách; tổng hợp; fast_30d_7d là đối chứng phụ, không chọn cấu hình theo tgt | da-asof-evidence-v2-fullweek |

## Ổn định theo seed

Nguồn: `outputs/t1/A_seed_cv.csv`

Giao thức: asof-pchip-v3-point-mass **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| metric | cv | meets_005 | measurement_version |
|---|---|---|---|
| pinball_avg | 0.0016 | True | asof-pchip-v3-point-mass |

## T8/T9 trên lời hứa nhiễu

Nguồn: `outputs/t1/EF_t8_t9_src_noisy_promises.csv`

Giao thức: asof-pchip-v3-point-mass-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | MAE_p50_promised_only |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E_T8 | DH-GBM with promises (T8) | 68425 | 7 | asof-pchip-v3-point-mass-fullweek | 2.4853 | 7.8571 | 4.7461 | 5.0295 | 15.7 | 14.6 | 0.8552 | 72.3 | 0.1071 | 0.1071 | 4.6914 | 5.3914 | 300 | 40 |  | 0.8428 | 0.8644 | 0.1467 | 0.0143 | 0.7794 | 0.4161 | 0.6989 | 12.9 |
| E_T8 | DH-GBM without promises | 68425 | 7 | asof-pchip-v3-point-mass-fullweek | 2.4998 | 7.9663 | 4.7954 | 5.0871 | 15.9 | 14.8 | 0.8511 | 73.0 | 0.1085 | 0.1085 | 4.7316 | 5.4694 | 300 | 40 |  | 0.8373 | 0.8618 | 0.1493 | 0.0132 | 0.7782 | 0.4155 | 0.6996 | 13.9 |

## T9 chẩn đoán phân bổ trên nguồn

Nguồn: `outputs/t9/source_allocation_diagnostics.csv`

Giao thức: t9-asof-known-customers-v5

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | settled_invoice_coverage | pay_date_MAE_ledger_days | method | link_precision_ci_low | link_precision_ci_high | link_recall_ci_low | link_recall_ci_high | link_f1_ci_low | link_f1_ci_high | pay_date_MAE_ci_low | pay_date_MAE_ci_high | auto_coverage_ci_low | auto_coverage_ci_high | bootstrap_n | n_firms | n_review | measurement_version | split | tau_auto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9466 | 0.6612 | 0.7786 | 3293 | 4714 | 0.0294 | 2.2498 | 0.9647 | 0.7341 | 8.3223 | Hybrid opening_only | 0.9254 | 0.9668 | 0.5661 | 0.7454 | 0.7047 | 0.8405 | 1.2218 | 3.5571 | 0.6826 | 0.7726 | 300 | 12 | 1072 | t9-asof-known-customers-v5 | source_calibration_diagnostic_not_independent_test | 0.9000 |
| 0.9743 | 0.6988 | 0.8138 | 3381 | 4714 | 0.0204 | 0.4296 | 0.9853 | 0.7591 | 8.3223 | Hybrid asof | 0.9647 | 0.9844 | 0.5911 | 0.7964 | 0.7338 | 0.8787 | 0.1547 | 0.7269 | 0.6710 | 0.7713 | 300 | 12 | 1084 | t9-asof-known-customers-v5 | source_calibration_diagnostic_not_independent_test | 0.9000 |

## Sinh thế giới lớn

Nguồn: `outputs/data/big_worlds.csv`

Giao thức: big-world-rng2-v2-streamed

| world | n_firms | n_invoices | bytes | tables_sha256 | seconds | resumed | contracts_passed | seed | shard_size | measurement_version | reported_seconds_before_fix | timing_valid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| big_000 | 150 | 894958 | 112447979 | b2147cf53bc466beb7076d5cf5eea08d77644969aaef995441e07da43043f9ab |  | False | True | 81000 | 12 | big-world-rng2-v2-streamed | 3878.8 | False |
| big_001 | 150 | 893872 | 113242754 | 0c13b4a48e5511df33e9cab071c7014b157335a8a6a75b43b0c03b96f103a901 |  | False | True | 81001 | 12 | big-world-rng2-v2-streamed | 4519.5 | False |
| big_002 | 150 | 926841 | 116312202 | df729317939f9382a9e26ce255f376a924b1b22f89fc38170d64cd6844fb6127 |  | False | True | 81002 | 12 | big-world-rng2-v2-streamed | 4963.7 | False |
| big_003 | 150 | 785008 | 101305223 | 7090a2df1736de6d5733c1556c1357fedcc74e47aa5be652d9bc1bbe6f91d079 |  | False | True | 81003 | 12 | big-world-rng2-v2-streamed | 5326.1 | False |

## T1 tuned và mặc định cùng ngân sách nguồn

Nguồn: `outputs/t1/A_tuned_equal_budget.csv`

Giao thức: asof-pchip-v3-point-mass **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | n_train | selection_origin | training_budget_limited | test_used_for_selection | parameters_sha256 | vs_default_improvement_pct | vs_default_improvement_ci_low | vs_default_improvement_ci_high |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| source_tuned_equal_budget | DH-GBM default (equal budget) | 68425 | 7 | asof-pchip-v3-point-mass | 2.5204 | 8.0974 | 5.1794 | 5.2657 | 16.2 | 15.0 | 0.8173 | 77.0 | 0.1111 | 0.1111 | 4.8771 | 5.6638 | 300 | 40 | 63.4 | 56.7 | 69.0 | B1d-cust-quantiles | 0.8028 | 0.8292 | 0.1486 | 0.0154 | 0.7814 | 0.4222 | 0.7005 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d |  |  |  |
| source_tuned_equal_budget | DH-GBM default (equal budget)+CQR | 68425 | 7 | asof-pchip-v3-point-mass | 2.5204 | 8.0974 | 5.0993 | 5.2390 | 16.2 | 15.0 | 0.8352 | 76.2 | 0.1130 | 0.1130 | 4.8543 | 5.6277 | 300 | 40 | 63.6 | 57.0 | 69.2 | B1d-cust-quantiles | 0.8228 | 0.8459 | 0.1517 | 0.0239 | 0.7814 | 0.4826 | 0.7668 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d |  |  |  |
| source_tuned_equal_budget | DH-GBM tuned | 68425 | 7 | asof-pchip-v3-point-mass | 2.5143 | 8.1417 | 5.3257 | 5.3272 | 16.3 | 15.1 | 0.8037 | 78.4 | 0.1120 | 0.1120 | 4.8969 | 5.7619 | 300 | 40 | 63.0 | 56.1 | 68.8 | B1d-cust-quantiles | 0.7860 | 0.8175 | 0.1492 | 0.0199 | 0.7802 | 0.4272 | 0.7007 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d | -1.1681 | -2.3684 | -0.0386 |
| source_tuned_equal_budget | DH-GBM tuned+CQR | 68425 | 7 | asof-pchip-v3-point-mass | 2.5143 | 8.1417 | 5.1786 | 5.2782 | 16.3 | 15.1 | 0.8275 | 76.9 | 0.1135 | 0.1135 | 4.8627 | 5.6961 | 300 | 40 | 63.3 | 56.4 | 69.1 | B1d-cust-quantiles | 0.8124 | 0.8399 | 0.1520 | 0.0244 | 0.7802 | 0.4834 | 0.7653 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d | -0.2371 | -1.2849 | 0.7879 |
| source_tuned_equal_budget | B1-cust-median | 68425 | 7 | asof-pchip-v3-point-mass | 5.2343 | 17.0 | 28.8 | 17.0 | 34.1 | 17.2 | 0.0528 | 340.5 | 0.3102 | 0.3102 | 15.1 | 19.2 | 300 | 40 | -18.4 | -22.2 | -15.6 | B1d-cust-quantiles | 0.0460 | 0.0593 | 0.3862 | 0.3862 | 0.5384 | 1.1660 | 0.8383 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d |  |  |  |
| source_tuned_equal_budget | B1d-cust-quantiles | 68425 | 7 | asof-pchip-v3-point-mass | 4.0177 | 17.0 | 22.1 | 14.4 | 34.0 | 17.2 | 0.5957 | 261.3 | 0.2549 | 0.2549 | 12.5 | 16.5 | 300 | 40 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5545 | 0.6346 | 0.3012 | 0.2204 | 0.5387 | 1.0401 | 0.7397 | 40000 | 2024-07-01 | True | False | 2da8428afd1917e66b165d88792afae919b878c6ada1ffdc41c829a444273d5d |  |  |  |

## Kiểm tra mục tiêu tuning

Nguồn: `outputs/t1/tuning_comparison.csv`

Giao thức: tuning-source-equal-budget-v1 **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| pinball_gain_pct | target_pct | candidate_cov80 | baseline_cov80 | candidate_ECE | baseline_ECE | improvement_ci_low | improvement_ci_high | meets_target | candidate_adopted | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|
| -1.1681 | 3.0000 | 0.8037 | 0.8173 | 0.0199 | 0.0154 | -2.3684 | -0.0386 | False | False | False | tuning-source-equal-budget-v1 |

## Onboarding: chỉ chọn bằng công ty nguồn giữ lại

Nguồn: `outputs/t1/onboarding_source_validation.csv`

Giao thức: asof-pchip-v3-point-mass-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | months_history | n_target_rows | selection_domain | target_used |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| onboarding_source_company_holdout | zero-shot | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.8002 | 9.7775 | 6.1321 | 6.2366 | 19.6 | 17.2 | 0.8273 | 89.3 | 0.1341 | 0.1341 | 5.7028 | 6.8673 | 300 | 8 | 36.9 | 27.6 | 45.0 | B1d-cust-quantiles | 0.8062 | 0.8469 | 0.1773 | 0.0818 | 0.7103 | 0.4882 | 0.8450 | 0 | 0 | src_company_holdout | False |
| onboarding_source_company_holdout | B1d-cust-quantiles | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 3.1587 | 11.6 | 14.9 | 9.8839 | 23.2 | 18.4 | 0.4073 | 180.4 | 0.1830 | 0.1830 | 7.8891 | 12.1 | 300 | 8 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.3067 | 0.4925 | 0.2355 | 0.1918 | 0.6620 | 0.8431 | 0.8352 | 0 | 0 | src_company_holdout | False |
| onboarding_source_company_holdout | zero-shot | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6752 | 9.3213 | 5.8771 | 5.9579 | 18.6 | 16.2 | 0.8407 | 85.5 | 0.1264 | 0.1264 | 5.3699 | 6.6703 | 300 | 8 | 32.7 | 23.4 | 42.0 | B1d-cust-quantiles | 0.8191 | 0.8641 | 0.1700 | 0.0677 | 0.7251 | 0.4424 | 0.8036 | 3 | 1988 | src_company_holdout | False |
| onboarding_source_company_holdout | B1d-cust-quantiles | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.8662 | 11.1 | 12.6 | 8.8532 | 22.1 | 17.1 | 0.5442 | 155.0 | 0.1689 | 0.1689 | 7.0816 | 11.0 | 300 | 8 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4501 | 0.6210 | 0.2161 | 0.1514 | 0.6685 | 0.7808 | 0.8212 | 3 | 1988 | src_company_holdout | False |
| onboarding_source_company_holdout | target-only | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.9508 | 10.8 | 8.2507 | 7.3458 | 21.7 | 17.7 | 0.7123 | 112.0 | 0.1541 | 0.1541 | 6.2340 | 8.7702 | 300 | 8 | 17.0 | 12.0 | 23.1 | B1d-cust-quantiles | 0.6713 | 0.7407 | 0.2049 | 0.0940 | 0.6676 | 0.5229 | 0.8520 | 3 | 1988 | src_company_holdout | False |
| onboarding_source_company_holdout | fine-tune | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6758 | 9.2172 | 5.9859 | 5.9596 | 18.4 | 15.7 | 0.8272 | 86.6 | 0.1264 | 0.1264 | 5.2476 | 6.8345 | 300 | 8 | 32.7 | 25.1 | 41.1 | B1d-cust-quantiles | 0.8109 | 0.8508 | 0.1676 | 0.0378 | 0.7270 | 0.4542 | 0.7845 | 3 | 1988 | src_company_holdout | False |
| onboarding_source_company_holdout | ensemble-b1d | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7127 | 9.6220 | 7.6063 | 6.6470 | 19.2 | 15.3 | 0.7174 | 103.2 | 0.1351 | 0.1351 | 5.6003 | 8.0032 | 300 | 8 | 24.9 | 21.2 | 28.2 | B1d-cust-quantiles | 0.6605 | 0.7600 | 0.1770 | 0.0464 | 0.7228 | 0.5294 | 0.8339 | 3 | 1988 | src_company_holdout | False |
| onboarding_source_company_holdout | zero-shot | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6528 | 9.2845 | 5.8872 | 5.9415 | 18.6 | 16.0 | 0.8445 | 85.4 | 0.1255 | 0.1255 | 5.3557 | 6.5943 | 300 | 8 | 30.4 | 18.7 | 42.1 | B1d-cust-quantiles | 0.8249 | 0.8697 | 0.1698 | 0.0674 | 0.7253 | 0.4418 | 0.8004 | 6 | 4709 | src_company_holdout | False |
| onboarding_source_company_holdout | B1d-cust-quantiles | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.8604 | 11.0 | 11.7 | 8.5396 | 22.1 | 17.1 | 0.5968 | 145.9 | 0.1664 | 0.1664 | 6.8180 | 10.8 | 300 | 8 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5031 | 0.6683 | 0.2131 | 0.1283 | 0.6671 | 0.7664 | 0.8044 | 6 | 4709 | src_company_holdout | False |
| onboarding_source_company_holdout | target-only | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7600 | 9.7304 | 8.4566 | 6.9823 | 19.5 | 14.9 | 0.7195 | 112.2 | 0.1426 | 0.1426 | 5.4988 | 8.8130 | 300 | 8 | 18.2 | 15.4 | 21.4 | B1d-cust-quantiles | 0.6533 | 0.7713 | 0.1864 | 0.0681 | 0.7111 | 0.4862 | 0.7982 | 6 | 4709 | src_company_holdout | False |
| onboarding_source_company_holdout | fine-tune | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6522 | 8.7818 | 5.8967 | 5.7769 | 17.6 | 14.4 | 0.8161 | 85.5 | 0.1220 | 0.1220 | 4.8019 | 6.9821 | 300 | 8 | 32.4 | 26.0 | 42.0 | B1d-cust-quantiles | 0.7818 | 0.8474 | 0.1601 | 0.0279 | 0.7475 | 0.4414 | 0.7556 | 6 | 4709 | src_company_holdout | False |
| onboarding_source_company_holdout | ensemble-b1d | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7166 | 9.5697 | 7.5725 | 6.6196 | 19.1 | 15.0 | 0.7234 | 102.9 | 0.1358 | 0.1358 | 5.3804 | 8.1570 | 300 | 8 | 22.5 | 19.8 | 26.3 | B1d-cust-quantiles | 0.6445 | 0.7833 | 0.1768 | 0.0627 | 0.7334 | 0.5328 | 0.8224 | 6 | 4709 | src_company_holdout | False |
| onboarding_source_company_holdout | zero-shot | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6673 | 9.3673 | 5.7387 | 5.9244 | 18.7 | 16.2 | 0.8340 | 84.1 | 0.1261 | 0.1261 | 5.2815 | 6.4982 | 300 | 8 | 28.4 | 15.3 | 40.8 | B1d-cust-quantiles | 0.8078 | 0.8673 | 0.1721 | 0.0693 | 0.7206 | 0.4513 | 0.8121 | 12 | 14286 | src_company_holdout | False |
| onboarding_source_company_holdout | B1d-cust-quantiles | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.8385 | 10.9 | 11.1 | 8.2765 | 21.8 | 16.9 | 0.6291 | 139.2 | 0.1628 | 0.1628 | 6.5672 | 10.5 | 300 | 8 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5280 | 0.7046 | 0.2093 | 0.1175 | 0.6679 | 0.7386 | 0.7971 | 12 | 14286 | src_company_holdout | False |
| onboarding_source_company_holdout | target-only | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7277 | 9.4061 | 6.0407 | 6.0582 | 18.8 | 15.8 | 0.8386 | 87.7 | 0.1270 | 0.1270 | 4.9591 | 7.2891 | 300 | 8 | 26.8 | 17.3 | 35.2 | B1d-cust-quantiles | 0.8013 | 0.8682 | 0.1621 | 0.0215 | 0.7328 | 0.4657 | 0.7553 | 12 | 14286 | src_company_holdout | False |
| onboarding_source_company_holdout | fine-tune | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6447 | 8.6254 | 5.6610 | 5.6437 | 17.3 | 14.5 | 0.8479 | 83.1 | 0.1185 | 0.1185 | 4.8600 | 6.5964 | 300 | 8 | 31.8 | 22.7 | 41.8 | B1d-cust-quantiles | 0.8273 | 0.8696 | 0.1543 | 0.0198 | 0.7484 | 0.4419 | 0.7495 | 12 | 14286 | src_company_holdout | False |
| onboarding_source_company_holdout | ensemble-b1d | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7004 | 9.2892 | 6.9310 | 6.3069 | 18.6 | 14.7 | 0.7689 | 96.3 | 0.1297 | 0.1297 | 5.2774 | 7.6216 | 300 | 8 | 23.8 | 18.9 | 28.3 | B1d-cust-quantiles | 0.7099 | 0.8136 | 0.1668 | 0.0370 | 0.7398 | 0.5188 | 0.8246 | 12 | 14286 | src_company_holdout | False |
| onboarding_source_company_holdout | zero-shot | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6614 | 9.1590 | 5.7011 | 5.8405 | 18.3 | 15.6 | 0.8401 | 83.6 | 0.1240 | 0.1240 | 5.2686 | 6.4832 | 300 | 8 | 28.6 | 16.0 | 40.3 | B1d-cust-quantiles | 0.8232 | 0.8643 | 0.1687 | 0.0663 | 0.7256 | 0.4400 | 0.8043 | 24 | 20000 | src_company_holdout | False |
| onboarding_source_company_holdout | B1d-cust-quantiles | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.8438 | 10.9 | 10.8 | 8.1857 | 21.7 | 16.9 | 0.6607 | 136.9 | 0.1618 | 0.1618 | 6.4255 | 10.4 | 300 | 8 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5504 | 0.7429 | 0.2096 | 0.1190 | 0.6673 | 0.7220 | 0.7923 | 24 | 20000 | src_company_holdout | False |
| onboarding_source_company_holdout | target-only | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7083 | 9.0298 | 5.6080 | 5.7820 | 18.1 | 15.4 | 0.8525 | 83.2 | 0.1228 | 0.1228 | 4.9328 | 6.8018 | 300 | 8 | 29.4 | 18.6 | 39.9 | B1d-cust-quantiles | 0.8284 | 0.8725 | 0.1594 | 0.0233 | 0.7356 | 0.4590 | 0.7584 | 24 | 20000 | src_company_holdout | False |
| onboarding_source_company_holdout | fine-tune | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.6686 | 8.5907 | 5.4874 | 5.5822 | 17.2 | 14.4 | 0.8450 | 81.6 | 0.1189 | 0.1189 | 4.8625 | 6.4533 | 300 | 8 | 31.8 | 21.3 | 41.7 | B1d-cust-quantiles | 0.8295 | 0.8643 | 0.1539 | 0.0224 | 0.7448 | 0.4399 | 0.7520 | 24 | 20000 | src_company_holdout | False |
| onboarding_source_company_holdout | ensemble-b1d | 6128 | 7 | asof-pchip-v3-point-mass-fullweek | 2.7160 | 9.2400 | 6.7436 | 6.2332 | 18.5 | 14.6 | 0.7805 | 94.6 | 0.1289 | 0.1289 | 5.2454 | 7.4942 | 300 | 8 | 23.9 | 18.2 | 29.2 | B1d-cust-quantiles | 0.7285 | 0.8206 | 0.1659 | 0.0360 | 0.7397 | 0.5215 | 0.8239 | 24 | 20000 | src_company_holdout | False |

## Scaling nguồn cùng phân phối, hàng khai triển lồng nhau

Nguồn: `outputs/t1/scaling_results.csv`

Giao thức: scaling-nested-expanded-v1-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | expanded_rows | source_world | source_fingerprint | months_history | n_target_rows | pretraining_seconds | pretraining_rounds | test_used_for_selection | n_source_firms_used | experiment_version | loaded_model_checkpoint |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.2333 | 16.1 | 20.7 | 13.7 | 32.3 | 20.3 | 0.4651 | 249.6 | 0.2416 | 0.2416 | 11.6 | 16.6 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.3685 | 0.5225 | 0.2719 | 0.2204 | 0.6057 | 1.0820 | 0.6416 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3631 | 10.2 | 5.2261 | 6.2773 | 20.5 | 18.0 | 0.8350 | 85.9 | 0.1280 | 0.1280 | 5.6527 | 6.7150 | 300 | 14 | 54.2 | 43.0 | 64.3 | B1d-cust-quantiles | 0.8106 | 0.8767 | 0.1410 | 0.0230 | 0.7564 | 0.4579 | 0.6026 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0690 | 15.7 | 17.2 | 12.3 | 31.4 | 19.5 | 0.5650 | 212.3 | 0.2239 | 0.2239 | 10.2 | 15.0 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4692 | 0.6267 | 0.2492 | 0.1909 | 0.6138 | 1.0104 | 0.6361 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3128 | 10.1 | 5.0805 | 6.1590 | 20.2 | 17.7 | 0.8441 | 83.9 | 0.1254 | 0.1254 | 5.5165 | 6.6509 | 300 | 14 | 50.0 | 36.1 | 62.1 | B1d-cust-quantiles | 0.8225 | 0.8791 | 0.1381 | 0.0316 | 0.7622 | 0.4294 | 0.5759 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3658 | 10.6 | 6.3189 | 6.7503 | 21.1 | 17.3 | 0.7618 | 96.8 | 0.1347 | 0.1347 | 5.8809 | 7.3099 | 300 | 14 | 45.2 | 31.2 | 57.4 | B1d-cust-quantiles | 0.7408 | 0.7944 | 0.1454 | 0.0349 | 0.7457 | 0.4403 | 0.5896 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0556 | 15.5 | 15.4 | 11.6 | 31.1 | 19.3 | 0.6221 | 194.1 | 0.2162 | 0.2162 | 9.5583 | 14.4 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5219 | 0.6817 | 0.2402 | 0.1697 | 0.6138 | 0.9635 | 0.6391 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3123 | 10.1 | 5.1232 | 6.1921 | 20.3 | 17.9 | 0.8449 | 84.4 | 0.1259 | 0.1259 | 5.5330 | 6.6855 | 300 | 14 | 46.8 | 31.3 | 59.5 | B1d-cust-quantiles | 0.8225 | 0.8797 | 0.1381 | 0.0382 | 0.7607 | 0.4299 | 0.5736 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.2458 | 11.1 | 5.2724 | 6.5262 | 22.1 | 20.3 | 0.8260 | 85.2 | 0.1336 | 0.1336 | 5.5276 | 7.3661 | 300 | 14 | 44.0 | 24.9 | 59.4 | B1d-cust-quantiles | 0.8047 | 0.8538 | 0.1426 | 0.0287 | 0.7442 | 0.4343 | 0.5820 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0286 | 15.5 | 14.6 | 11.4 | 31.0 | 19.4 | 0.6563 | 186.7 | 0.2134 | 0.2134 | 9.3413 | 14.1 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5578 | 0.7152 | 0.2369 | 0.1630 | 0.6135 | 0.9478 | 0.6358 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3307 | 10.3 | 5.1045 | 6.2552 | 20.7 | 18.7 | 0.8428 | 84.4 | 0.1268 | 0.1268 | 5.5477 | 6.7967 | 300 | 14 | 45.1 | 28.1 | 58.6 | B1d-cust-quantiles | 0.8166 | 0.8827 | 0.1382 | 0.0409 | 0.7592 | 0.4340 | 0.5749 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.2666 | 11.0 | 5.2958 | 6.5084 | 21.9 | 20.4 | 0.8551 | 85.6 | 0.1318 | 0.1318 | 5.6275 | 7.1498 | 300 | 14 | 42.9 | 24.8 | 57.0 | B1d-cust-quantiles | 0.8317 | 0.8897 | 0.1405 | 0.0434 | 0.7459 | 0.4460 | 0.5825 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0225 | 15.5 | 14.7 | 11.4 | 31.0 | 19.4 | 0.6550 | 187.6 | 0.2142 | 0.2142 | 9.3729 | 14.2 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5549 | 0.7166 | 0.2381 | 0.1656 | 0.6137 | 0.9542 | 0.6332 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3229 | 10.3 | 5.1563 | 6.2733 | 20.7 | 18.9 | 0.8444 | 84.8 | 0.1270 | 0.1270 | 5.5553 | 6.8186 | 300 | 14 | 45.1 | 28.1 | 58.7 | B1d-cust-quantiles | 0.8193 | 0.8822 | 0.1383 | 0.0445 | 0.7604 | 0.4319 | 0.5764 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.2784 | 10.9 | 5.3044 | 6.4914 | 21.8 | 20.3 | 0.8558 | 85.8 | 0.1320 | 0.1320 | 5.5106 | 7.2107 | 300 | 14 | 43.2 | 24.4 | 58.1 | B1d-cust-quantiles | 0.8282 | 0.8972 | 0.1410 | 0.0477 | 0.7465 | 0.4560 | 0.5909 | 1000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 12.3 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.2333 | 16.1 | 20.7 | 13.7 | 32.3 | 20.3 | 0.4651 | 249.6 | 0.2416 | 0.2416 | 11.6 | 16.6 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.3685 | 0.5225 | 0.2719 | 0.2204 | 0.6057 | 1.0820 | 0.6416 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.4012 | 10.3 | 5.2706 | 6.3273 | 20.6 | 17.9 | 0.8302 | 86.7 | 0.1286 | 0.1286 | 5.6577 | 6.7844 | 300 | 14 | 53.8 | 42.3 | 64.0 | B1d-cust-quantiles | 0.8019 | 0.8775 | 0.1411 | 0.0258 | 0.7552 | 0.4590 | 0.6055 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0690 | 15.7 | 17.2 | 12.3 | 31.4 | 19.5 | 0.5650 | 212.3 | 0.2239 | 0.2239 | 10.2 | 15.0 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4692 | 0.6267 | 0.2492 | 0.1909 | 0.6138 | 1.0104 | 0.6361 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3595 | 10.2 | 5.1046 | 6.2146 | 20.4 | 17.6 | 0.8391 | 84.6 | 0.1260 | 0.1260 | 5.5156 | 6.7419 | 300 | 14 | 49.5 | 35.4 | 61.6 | B1d-cust-quantiles | 0.8104 | 0.8820 | 0.1380 | 0.0335 | 0.7604 | 0.4326 | 0.5797 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.4099 | 10.7 | 6.2562 | 6.8015 | 21.5 | 17.8 | 0.7599 | 96.7 | 0.1357 | 0.1357 | 5.9103 | 7.3988 | 300 | 14 | 44.7 | 30.6 | 57.2 | B1d-cust-quantiles | 0.7342 | 0.7955 | 0.1455 | 0.0362 | 0.7429 | 0.4436 | 0.6001 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0556 | 15.5 | 15.4 | 11.6 | 31.1 | 19.3 | 0.6221 | 194.1 | 0.2162 | 0.2162 | 9.5583 | 14.4 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5219 | 0.6817 | 0.2402 | 0.1697 | 0.6138 | 0.9635 | 0.6391 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3644 | 10.2 | 5.0975 | 6.2106 | 20.3 | 17.9 | 0.8404 | 84.6 | 0.1259 | 0.1259 | 5.5186 | 6.7170 | 300 | 14 | 46.7 | 31.0 | 59.3 | B1d-cust-quantiles | 0.8149 | 0.8786 | 0.1377 | 0.0389 | 0.7605 | 0.4309 | 0.5744 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.2554 | 11.0 | 5.2868 | 6.5146 | 22.0 | 20.1 | 0.8269 | 85.4 | 0.1323 | 0.1323 | 5.5221 | 7.3220 | 300 | 14 | 44.1 | 25.5 | 59.1 | B1d-cust-quantiles | 0.7992 | 0.8639 | 0.1413 | 0.0265 | 0.7450 | 0.4337 | 0.5813 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0286 | 15.5 | 14.6 | 11.4 | 31.0 | 19.4 | 0.6563 | 186.7 | 0.2134 | 0.2134 | 9.3413 | 14.1 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5578 | 0.7152 | 0.2369 | 0.1630 | 0.6135 | 0.9478 | 0.6358 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3747 | 10.4 | 5.1195 | 6.3130 | 20.9 | 18.9 | 0.8393 | 84.9 | 0.1272 | 0.1272 | 5.5654 | 6.8640 | 300 | 14 | 44.6 | 27.5 | 58.1 | B1d-cust-quantiles | 0.8076 | 0.8864 | 0.1381 | 0.0429 | 0.7572 | 0.4356 | 0.5740 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3159 | 11.0 | 5.3338 | 6.5471 | 22.0 | 20.4 | 0.8505 | 86.5 | 0.1322 | 0.1322 | 5.6082 | 7.2266 | 300 | 14 | 42.5 | 24.1 | 57.0 | B1d-cust-quantiles | 0.8194 | 0.8948 | 0.1405 | 0.0473 | 0.7459 | 0.4479 | 0.5821 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0225 | 15.5 | 14.7 | 11.4 | 31.0 | 19.4 | 0.6550 | 187.6 | 0.2142 | 0.2142 | 9.3729 | 14.2 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5549 | 0.7166 | 0.2381 | 0.1656 | 0.6137 | 0.9542 | 0.6332 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3768 | 10.4 | 5.1663 | 6.3289 | 20.9 | 19.1 | 0.8401 | 85.4 | 0.1271 | 0.1271 | 5.5569 | 6.9103 | 300 | 14 | 44.6 | 27.3 | 58.4 | B1d-cust-quantiles | 0.8083 | 0.8856 | 0.1378 | 0.0455 | 0.7586 | 0.4340 | 0.5765 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3235 | 11.0 | 5.3342 | 6.5477 | 22.0 | 20.8 | 0.8507 | 86.6 | 0.1324 | 0.1324 | 5.4920 | 7.3106 | 300 | 14 | 42.7 | 23.6 | 58.0 | B1d-cust-quantiles | 0.8188 | 0.8986 | 0.1407 | 0.0509 | 0.7467 | 0.4596 | 0.5890 | 10000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 116.0 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.2333 | 16.1 | 20.7 | 13.7 | 32.3 | 20.3 | 0.4651 | 249.6 | 0.2416 | 0.2416 | 11.6 | 16.6 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.3685 | 0.5225 | 0.2719 | 0.2204 | 0.6057 | 1.0820 | 0.6416 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3863 | 10.3 | 5.2487 | 6.3063 | 20.6 | 18.0 | 0.8363 | 86.4 | 0.1283 | 0.1283 | 5.6515 | 6.7677 | 300 | 14 | 54.0 | 42.6 | 64.2 | B1d-cust-quantiles | 0.8096 | 0.8801 | 0.1412 | 0.0279 | 0.7564 | 0.4569 | 0.6033 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 0 | 0 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0690 | 15.7 | 17.2 | 12.3 | 31.4 | 19.5 | 0.5650 | 212.3 | 0.2239 | 0.2239 | 10.2 | 15.0 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4692 | 0.6267 | 0.2492 | 0.1909 | 0.6138 | 1.0104 | 0.6361 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3400 | 10.2 | 5.0815 | 6.1919 | 20.3 | 17.8 | 0.8439 | 84.2 | 0.1257 | 0.1257 | 5.4927 | 6.7264 | 300 | 14 | 49.7 | 35.4 | 62.0 | B1d-cust-quantiles | 0.8175 | 0.8835 | 0.1381 | 0.0360 | 0.7624 | 0.4297 | 0.5782 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.4063 | 10.8 | 6.0423 | 6.7480 | 21.6 | 18.3 | 0.7680 | 94.5 | 0.1353 | 0.1353 | 5.8730 | 7.3457 | 300 | 14 | 45.2 | 30.6 | 57.9 | B1d-cust-quantiles | 0.7442 | 0.8050 | 0.1456 | 0.0342 | 0.7413 | 0.4423 | 0.6069 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 3 | 5220 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0556 | 15.5 | 15.4 | 11.6 | 31.1 | 19.3 | 0.6221 | 194.1 | 0.2162 | 0.2162 | 9.5583 | 14.4 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5219 | 0.6817 | 0.2402 | 0.1697 | 0.6138 | 0.9635 | 0.6391 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3527 | 10.2 | 5.1394 | 6.2300 | 20.4 | 17.9 | 0.8424 | 84.9 | 0.1263 | 0.1263 | 5.5296 | 6.7479 | 300 | 14 | 46.5 | 30.7 | 59.3 | B1d-cust-quantiles | 0.8175 | 0.8795 | 0.1379 | 0.0408 | 0.7606 | 0.4289 | 0.5758 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.2482 | 11.0 | 5.3067 | 6.5236 | 22.0 | 20.0 | 0.8347 | 85.5 | 0.1329 | 0.1329 | 5.5330 | 7.3360 | 300 | 14 | 44.0 | 25.2 | 59.1 | B1d-cust-quantiles | 0.8145 | 0.8623 | 0.1418 | 0.0278 | 0.7434 | 0.4317 | 0.5818 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 6 | 15864 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0286 | 15.5 | 14.6 | 11.4 | 31.0 | 19.4 | 0.6563 | 186.7 | 0.2134 | 0.2134 | 9.3413 | 14.1 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5578 | 0.7152 | 0.2369 | 0.1630 | 0.6135 | 0.9478 | 0.6358 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3652 | 10.4 | 5.1573 | 6.3060 | 20.8 | 18.7 | 0.8392 | 85.2 | 0.1274 | 0.1274 | 5.5673 | 6.8471 | 300 | 14 | 44.6 | 27.7 | 58.0 | B1d-cust-quantiles | 0.8084 | 0.8840 | 0.1384 | 0.0436 | 0.7581 | 0.4334 | 0.5756 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3225 | 11.1 | 5.3642 | 6.6024 | 22.2 | 20.7 | 0.8455 | 86.9 | 0.1328 | 0.1328 | 5.6560 | 7.2860 | 300 | 14 | 42.0 | 23.8 | 56.5 | B1d-cust-quantiles | 0.8140 | 0.8895 | 0.1408 | 0.0471 | 0.7434 | 0.4479 | 0.5837 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 12 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | B1d-cust-quantiles | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 4.0225 | 15.5 | 14.7 | 11.4 | 31.0 | 19.4 | 0.6550 | 187.6 | 0.2142 | 0.2142 | 9.3729 | 14.2 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5549 | 0.7166 | 0.2381 | 0.1656 | 0.6137 | 0.9542 | 0.6332 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | pretrained zero-shot | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3554 | 10.4 | 5.1668 | 6.3061 | 20.8 | 18.9 | 0.8416 | 85.2 | 0.1272 | 0.1272 | 5.5691 | 6.8622 | 300 | 14 | 44.8 | 27.7 | 58.4 | B1d-cust-quantiles | 0.8125 | 0.8844 | 0.1383 | 0.0476 | 0.7599 | 0.4312 | 0.5777 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |
| pretraining_scaling_fixed_source | fine-tuned | 39304 | 7 | scaling-nested-expanded-v1-fullweek | 3.3104 | 11.0 | 5.3078 | 6.5335 | 22.0 | 20.6 | 0.8512 | 86.2 | 0.1324 | 0.1324 | 5.4930 | 7.2860 | 300 | 14 | 42.8 | 23.9 | 58.1 | B1d-cust-quantiles | 0.8194 | 0.8977 | 0.1410 | 0.0496 | 0.7462 | 0.4551 | 0.5887 | 3000000 | big_000 | 6dd1cc9d743413958506234bed89d3022aaaf56da8cd1252b7fe45755c1798c7 | 24 | 40000 | 51.2 | 300 | False | 150 | scaling-nested-expanded-v1 | False |

## Scaling: M* theo tiêu chí định trước

Nguồn: `outputs/t1/scaling_M_star.csv`

Giao thức: scaling-nested-expanded-v1-fullweek

| expanded_rows | M_star | criterion | measurement_version | M_star_ci_low | M_star_ci_high | prob_reaches_by_24m | paired_prob_largest_needs_less_history_than_smallest | bootstrap_n | unreached_encoded_as |
|---|---|---|---|---|---|---|---|---|---|
| 1000000 | 0 | zero-shot M0, fine-tune M>0; pinball <=0.9*B1d at same M (predeclared) | scaling-nested-expanded-v1-fullweek | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 300 | inf |
| 3000000 | 0 | zero-shot M0, fine-tune M>0; pinball <=0.9*B1d at same M (predeclared) | scaling-nested-expanded-v1-fullweek | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 300 | inf |
| 10000000 | 0 | zero-shot M0, fine-tune M>0; pinball <=0.9*B1d at same M (predeclared) | scaling-nested-expanded-v1-fullweek | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 300 | inf |

## Khác biệt miền: snapshot giữ lại nguyên công ty

Nguồn: `outputs/t1/domain_distance.csv`

Giao thức: domain-snapshot-company-heldout-v1

| domain | feature_set | AUC | AUC_ci_low | AUC_ci_high | n_train | n_test | n_source_test_firms | n_target_test_firms | bootstrap_n | target_used_for_policy_selection | measurement_version | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tgt | all_T1 | 0.6073 | 0.3364 | 0.8114 | 8308 | 6113 | 12 | 4 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| tgt | shared_without_promises | 0.6064 | 0.3294 | 0.8085 | 8308 | 6113 | 12 | 4 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| sens_uk | all_T1 | 0.8879 | 0.6186 | 1.0000 | 8158 | 6115 | 12 | 3 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| sens_uk | shared_without_promises | 0.8812 | 0.5953 | 1.0000 | 8158 | 6115 | 12 | 3 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| sens_coface | all_T1 | 0.5212 | 0.3212 | 0.9490 | 7746 | 4474 | 12 | 3 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| sens_coface | shared_without_promises | 0.5794 | 0.4004 | 0.9742 | 7746 | 4474 | 12 | 3 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance |
| Customer Invoices | all_T1 | 1.0000 | 1.0000 | 1.0000 | 19348 | 3155 | 12 | 1 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance;ledger_labels;only_one_heldout_real_company |
| Customer Invoices | shared_without_promises | 1.0000 | 1.0000 | 1.0000 | 19348 | 3155 | 12 | 1 | 300 | False | domain-snapshot-company-heldout-v1 | domain_diagnostic_not_performance;ledger_labels;only_one_heldout_real_company |

## Khác biệt miền: top-10 đặc trưng theo gain

Nguồn: `outputs/t1/domain_top_features.csv`

Giao thức: domain-snapshot-company-heldout-v1 **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| domain | feature_set | rank | feature | gain | measurement_version |
|---|---|---|---|---|---|
| tgt | all_T1 | 1 | f_resid_28d | 42794.2 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 2 | f_n_hist | 37844.5 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 3 | f_delay_mean | 25213.4 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 4 | f_open_n | 7399.3 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 5 | f_resid_trend | 3155.3 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 6 | c_n_hist | 1069.6 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 7 | c_open_share | 130.3 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 8 | c_life_med | 118.2 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 9 | c_tenure_days | 72.9 | domain-snapshot-company-heldout-v1 |
| tgt | all_T1 | 10 | c_days_since_last_pay | 40.0 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 1 | f_resid_28d | 42545.6 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 2 | f_n_hist | 38028.5 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 3 | f_delay_mean | 25381.0 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 4 | f_open_n | 7343.9 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 5 | f_resid_trend | 3088.8 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 6 | c_n_hist | 1100.7 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 7 | c_open_share | 133.6 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 8 | c_life_med | 125.9 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 9 | c_tenure_days | 72.4 | domain-snapshot-company-heldout-v1 |
| tgt | shared_without_promises | 10 | c_days_since_last_pay | 38.8 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 1 | f_delay_mean | 94720.7 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 2 | f_open_n | 8693.7 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 3 | f_n_hist | 7919.9 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 4 | c_delay_std | 1824.8 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 5 | f_resid_28d | 1162.8 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 6 | c_life_med | 369.9 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 7 | c_payrun_strength | 310.1 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 8 | f_resid_trend | 274.8 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 9 | c_n_hist | 231.3 | domain-snapshot-company-heldout-v1 |
| sens_uk | all_T1 | 10 | c_open_overdue_n | 155.4 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 1 | f_delay_mean | 94754.9 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 2 | f_open_n | 8704.6 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 3 | f_n_hist | 7826.8 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 4 | c_delay_std | 1842.3 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 5 | f_resid_28d | 1168.5 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 6 | c_life_med | 371.1 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 7 | c_payrun_strength | 308.9 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 8 | f_resid_trend | 306.5 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 9 | c_n_hist | 231.9 | domain-snapshot-company-heldout-v1 |
| sens_uk | shared_without_promises | 10 | c_open_overdue_n | 155.5 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 1 | f_delay_mean | 79482.3 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 2 | f_open_n | 16112.4 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 3 | f_n_hist | 12516.8 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 4 | f_resid_28d | 892.9 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 5 | c_max_dpd | 707.5 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 6 | f_resid_trend | 131.6 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 7 | c_promise_rel | 99.7 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 8 | c_open_overdue_n | 80.6 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 9 | c_open_n | 24.8 | domain-snapshot-company-heldout-v1 |
| sens_coface | all_T1 | 10 | days_to_tet | 8.2322 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 1 | f_delay_mean | 79501.9 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 2 | f_open_n | 16086.8 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 3 | f_n_hist | 12532.7 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 4 | f_resid_28d | 890.7 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 5 | c_max_dpd | 765.3 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 6 | f_resid_trend | 144.1 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 7 | c_open_overdue_n | 106.1 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 8 | c_open_n | 26.5 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 9 | c_n_hist | 2.3494 | domain-snapshot-company-heldout-v1 |
| sens_coface | shared_without_promises | 10 | c_late30_share | 2.2655 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 1 | paid_frac_so_far | 274925.8 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 2 | log_amount_rel | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 3 | age_days | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 4 | days_to_due | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 5 | c_n_hist | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 6 | c_delay_mean | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 7 | c_late_share | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 8 | c_delay_std | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 9 | c_payrun_strength | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | all_T1 | 10 | days_past_due | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 1 | paid_frac_so_far | 274925.8 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 2 | log_amount_rel | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 3 | age_days | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 4 | days_to_due | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 5 | c_n_hist | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 6 | c_delay_mean | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 7 | c_late_share | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 8 | c_delay_std | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 9 | c_payrun_strength | 0.0000 | domain-snapshot-company-heldout-v1 |
| Customer Invoices | shared_without_promises | 10 | days_past_due | 0.0000 | domain-snapshot-company-heldout-v1 |

## DA7: ablation sốc chung và đặc trưng nhanh trong khủng hoảng

Nguồn: `outputs/t1/crisis_ablation.csv`

Giao thức: crisis-source-only-locked-ablation-v1-fullweek

| world | regime_start | regime_end | model | pinball | pinball_ci_low | pinball_ci_high | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | n_test | n_train | rounds | bootstrap_n | training_label_end | target_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| src | 2021-07-01 | 2021-10-31 | B1d | 21.6 | 18.8 | 24.4 | -332.9 | -413.6 | -264.9 | 40 | 40649 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2021-07-01 | 2021-10-31 | no_shock | 4.9919 | 4.6305 | 5.3138 | 0.0000 | 0.0000 | 0.0000 | 40 | 40649 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2021-07-01 | 2021-10-31 | shock_28d | 5.0769 | 4.6765 | 5.4300 | -1.7023 | -3.4653 | -0.4371 | 40 | 40649 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2021-07-01 | 2021-10-31 | fast_30d_7d | 5.0184 | 4.6598 | 5.3174 | -0.5296 | -1.5069 | 0.6071 | 40 | 40649 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2021-07-01 | 2021-10-31 | B1d | 21.7 | 18.2 | 24.6 | -245.0 | -302.8 | -168.5 | 14 | 12312 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2021-07-01 | 2021-10-31 | no_shock | 6.2845 | 5.4844 | 7.7546 | 0.0000 | 0.0000 | 0.0000 | 14 | 12312 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2021-07-01 | 2021-10-31 | shock_28d | 6.4196 | 5.5803 | 7.9580 | -2.1484 | -3.7637 | -0.8184 | 14 | 12312 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2021-07-01 | 2021-10-31 | fast_30d_7d | 6.3257 | 5.5211 | 7.7806 | -0.6549 | -2.1369 | 1.4637 | 14 | 12312 | 40000 | 300 | 300 | 2021-03-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2022-10-01 | 2023-06-30 | B1d | 21.7 | 19.6 | 23.8 | -218.6 | -261.6 | -179.4 | 40 | 105618 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2022-10-01 | 2023-06-30 | no_shock | 6.8024 | 6.4534 | 7.2086 | 0.0000 | 0.0000 | 0.0000 | 40 | 105618 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2022-10-01 | 2023-06-30 | shock_28d | 6.8197 | 6.4407 | 7.2382 | -0.2540 | -0.9708 | 0.5714 | 40 | 105618 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| src | 2022-10-01 | 2023-06-30 | fast_30d_7d | 6.8118 | 6.4598 | 7.2132 | -0.1374 | -1.0184 | 0.6262 | 40 | 105618 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2022-10-01 | 2023-06-30 | B1d | 14.4 | 11.9 | 19.4 | -125.9 | -260.3 | -68.3 | 14 | 23795 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2022-10-01 | 2023-06-30 | no_shock | 6.3699 | 5.0991 | 7.2729 | 0.0000 | 0.0000 | 0.0000 | 14 | 23795 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2022-10-01 | 2023-06-30 | shock_28d | 6.3384 | 5.0738 | 7.2262 | 0.4940 | -0.3918 | 1.0947 | 14 | 23795 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |
| tgt | 2022-10-01 | 2023-06-30 | fast_30d_7d | 6.3011 | 5.0692 | 7.1254 | 1.0801 | -1.1918 | 2.4554 | 14 | 23795 | 40000 | 300 | 300 | 2022-06-03 | False | crisis-source-only-locked-ablation-v1-fullweek |

## Dịch vụ local: kiểm tra một công ty demo, không thay UAT

Nguồn: `outputs/service/local_validation.csv`

Giao thức: service-local-synthetic-research-v1

| check | value | cutoff | target_met | measurement_version | limitation |
|---|---|---|---|---|---|
| stored_model_loaded_by_forecast | 1.0000 | 2024-07-01 | True | service-local-synthetic-research-v1 | one_firm_demo_with_user_supplied_opening_balance;not_pilot_or_UAT_evidence |
| forecast_seconds | 19.4 | 2024-07-01 | True | service-local-synthetic-research-v1 | one_firm_demo_with_user_supplied_opening_balance;not_pilot_or_UAT_evidence |
| realized_coverage_single_company_demo | 0.0769 | 2024-10-01 | nan | service-local-synthetic-research-v1 | one_firm_demo_with_user_supplied_opening_balance;not_pilot_or_UAT_evidence |

## T1: monotone/PDP, daily 28 ngày, mixture và EB ML-II

Nguồn: `outputs/t1/T1_variants.csv`

Giao thức: T1-locked-source-variants-v1-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | vs_default_improvement_pct | vs_default_improvement_ci_low | vs_default_improvement_ci_high | fit_seconds | n_train_budget | rounds | test_used_for_selection | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| src | B1d-cust-quantiles | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 3.9838 | 16.7 | 21.0 | 13.9 | 33.5 | 18.0 | 0.5957 | 249.9 | 0.2491 | 0.2491 | 12.4 | 15.4 | 300 | 40 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5625 | 0.6285 | 0.2989 | 0.2237 | 0.5500 | 1.0272 | 0.7461 | -156.4 | -189.6 | -130.0 | 0.0000 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | B1-cust-median | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 5.1138 | 16.7 | 28.3 | 16.7 | 33.5 | 18.0 | 0.0539 | 334.6 | 0.3067 | 0.3067 | 15.1 | 18.4 | 300 | 40 | -20.3 | -23.3 | -17.9 | B1d-cust-quantiles | 0.0471 | 0.0604 | 0.3886 | 0.3886 | 0.5496 | 1.1463 | 0.8246 | -208.6 | -243.7 | -181.4 | 0.0000 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | DH-GBM default | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 2.6560 | 8.5217 | 5.0888 | 5.4222 | 17.0 | 15.8 | 0.8414 | 77.4 | 0.1154 | 0.1154 | 5.0945 | 5.7252 | 300 | 40 | 61.0 | 56.5 | 65.5 | B1d-cust-quantiles | 0.8331 | 0.8503 | 0.1544 | 0.0147 | 0.7674 | 0.4281 | 0.7221 | 0.0000 | 0.0000 | 0.0000 | 11.7 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | DH-GBM monotone PDP | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 2.6532 | 8.4996 | 5.0950 | 5.4159 | 17.0 | 15.7 | 0.8408 | 77.5 | 0.1152 | 0.1152 | 5.1027 | 5.7108 | 300 | 40 | 61.0 | 56.6 | 65.4 | B1d-cust-quantiles | 0.8326 | 0.8505 | 0.1546 | 0.0128 | 0.7668 | 0.4319 | 0.7191 | 0.1149 | -0.4803 | 0.8340 | 14.0 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | Due-window mixture | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 2.6570 | 8.5474 | 5.0259 | 5.4101 | 17.1 | 15.9 | 0.8447 | 76.8 | 0.1155 | 0.1155 | 5.0864 | 5.7072 | 300 | 40 | 61.1 | 56.6 | 65.6 | B1d-cust-quantiles | 0.8368 | 0.8530 | 0.1552 | 0.0203 | 0.7661 | 0.4385 | 0.7266 | 0.2233 | -0.5304 | 1.0917 | 11.4 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | DH-GBM EB ML-II | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 2.6519 | 8.4731 | 5.1094 | 5.4115 | 16.9 | 15.6 | 0.8416 | 77.6 | 0.1151 | 0.1151 | 5.1067 | 5.7155 | 300 | 40 | 61.1 | 56.5 | 65.5 | B1d-cust-quantiles | 0.8332 | 0.8511 | 0.1546 | 0.0143 | 0.7671 | 0.4308 | 0.7181 | 0.1978 | -0.7810 | 1.2925 | 10.8 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| src | DH daily28 + weekly tail | 139946 | 7 | T1-locked-source-variants-v1-fullweek | 2.6803 | 8.4660 | 5.0192 | 5.3885 | 16.9 | 15.6 | 0.8516 | 77.0 | 0.1154 | 0.1154 | 5.0784 | 5.6843 | 300 | 40 | 61.2 | 56.8 | 65.6 | B1d-cust-quantiles | 0.8424 | 0.8604 | 0.1559 | 0.0247 | 0.7650 | 0.4513 | 0.7319 | 0.6210 | 0.0845 | 1.1678 | 21.8 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | B1d-cust-quantiles | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 4.9373 | 21.0 | 25.7 | 17.2 | 42.0 | 20.9 | 0.5649 | 306.8 | 0.3012 | 0.3012 | 14.1 | 22.3 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4814 | 0.6199 | 0.3257 | 0.2717 | 0.5146 | 1.2743 | 0.6066 | -191.8 | -335.7 | -118.5 | 0.0000 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | B1-cust-median | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 6.6934 | 21.0 | 35.3 | 21.0 | 42.0 | 20.9 | 0.0446 | 419.6 | 0.3744 | 0.3744 | 18.1 | 25.6 | 300 | 14 | -21.8 | -28.7 | -14.0 | B1d-cust-quantiles | 0.0353 | 0.0525 | 0.4212 | 0.4212 | 0.5144 | 1.3865 | 0.6667 | -255.6 | -402.0 | -179.4 | 0.0000 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | DH-GBM default | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 3.1340 | 9.7229 | 4.8434 | 5.9001 | 19.4 | 19.1 | 0.8423 | 79.8 | 0.1202 | 0.1202 | 4.9822 | 6.6039 | 300 | 14 | 65.7 | 54.2 | 77.0 | B1d-cust-quantiles | 0.8191 | 0.8742 | 0.1303 | 0.0288 | 0.7863 | 0.4214 | 0.5515 | 0.0000 | 0.0000 | 0.0000 | 11.7 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | DH-GBM monotone PDP | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 3.1399 | 9.7797 | 4.8211 | 5.9136 | 19.6 | 19.4 | 0.8406 | 79.6 | 0.1202 | 0.1202 | 4.9902 | 6.6430 | 300 | 14 | 65.7 | 54.0 | 77.2 | B1d-cust-quantiles | 0.8186 | 0.8713 | 0.1305 | 0.0285 | 0.7851 | 0.4231 | 0.5517 | -0.2285 | -0.8754 | 0.6252 | 14.0 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | Due-window mixture | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 3.1162 | 9.6367 | 4.8102 | 5.8544 | 19.3 | 19.1 | 0.8440 | 79.3 | 0.1198 | 0.1198 | 4.9356 | 6.5895 | 300 | 14 | 66.0 | 54.3 | 77.5 | B1d-cust-quantiles | 0.8202 | 0.8778 | 0.1304 | 0.0270 | 0.7867 | 0.4222 | 0.5551 | 0.7747 | 0.1259 | 1.9960 | 11.4 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | DH-GBM EB ML-II | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 3.1194 | 9.7599 | 4.7358 | 5.8717 | 19.5 | 19.5 | 0.8515 | 78.6 | 0.1199 | 0.1199 | 5.0115 | 6.5748 | 300 | 14 | 65.9 | 54.5 | 76.8 | B1d-cust-quantiles | 0.8344 | 0.8768 | 0.1306 | 0.0307 | 0.7865 | 0.4219 | 0.5497 | 0.4815 | -1.5925 | 1.9955 | 10.8 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |
| tgt | DH daily28 + weekly tail | 52481 | 7 | T1-locked-source-variants-v1-fullweek | 3.1448 | 9.5642 | 4.7735 | 5.8275 | 19.1 | 18.8 | 0.8538 | 79.2 | 0.1194 | 0.1194 | 4.9618 | 6.5033 | 300 | 14 | 66.2 | 54.9 | 77.1 | B1d-cust-quantiles | 0.8308 | 0.8847 | 0.1306 | 0.0295 | 0.7892 | 0.4342 | 0.5542 | 1.2303 | -0.0255 | 1.7394 | 21.8 | 40000 | 300 | False | budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption |

## T1: CI cặp so mặc định, không tự chọn theo tgt

Nguồn: `outputs/t1/T1_variant_decisions.csv`

Giao thức: T1-locked-source-variants-v1-fullweek

| world | model | improvement_pct | ci_low | ci_high | candidate_adopted | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|
| src | B1d-cust-quantiles | -156.4 | -189.6 | -130.0 | False | False | T1-locked-source-variants-v1-fullweek |
| src | B1-cust-median | -208.6 | -243.7 | -181.4 | False | False | T1-locked-source-variants-v1-fullweek |
| src | DH-GBM default | 0.0000 | 0.0000 | 0.0000 | False | False | T1-locked-source-variants-v1-fullweek |
| src | DH-GBM monotone PDP | 0.1149 | -0.4803 | 0.8340 | False | False | T1-locked-source-variants-v1-fullweek |
| src | Due-window mixture | 0.2233 | -0.5304 | 1.0917 | False | False | T1-locked-source-variants-v1-fullweek |
| src | DH-GBM EB ML-II | 0.1978 | -0.7810 | 1.2925 | False | False | T1-locked-source-variants-v1-fullweek |
| src | DH daily28 + weekly tail | 0.6210 | 0.0845 | 1.1678 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | B1d-cust-quantiles | -191.8 | -335.7 | -118.5 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | B1-cust-median | -255.6 | -402.0 | -179.4 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | DH-GBM default | 0.0000 | 0.0000 | 0.0000 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | DH-GBM monotone PDP | -0.2285 | -0.8754 | 0.6252 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | Due-window mixture | 0.7747 | 0.1259 | 1.9960 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | DH-GBM EB ML-II | 0.4815 | -1.5925 | 1.9955 | False | False | T1-locked-source-variants-v1-fullweek |
| tgt | DH daily28 + weekly tail | 1.2303 | -0.0255 | 1.7394 | False | False | T1-locked-source-variants-v1-fullweek |

## T9→T1: ngân hàng/sổ/nhãn ước lượng, chấm tiền thật

Nguồn: `outputs/t1/T9_T1_error_propagation.csv`

Giao thức: T9-T1-observed-cash-equal-budget-v1-fullweek

| label_mode | horizon | WAPE | WAPE_ci_low | WAPE_ci_high | bootstrap_n | n_firms | weeks | n_target_train | source_budget | target_budget | truth_used_only_scoring | measurement_version | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T9_estimated | w1-4 | 0.5169 | 0.4404 | 0.6621 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |
| T9_estimated | w5-13 | 0.6483 | 0.5278 | 0.9777 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |
| bank_oracle | w1-4 | 0.4289 | 0.3656 | 0.5574 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |
| bank_oracle | w5-13 | 0.5581 | 0.4276 | 0.9249 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |
| ledger_observed | w1-4 | 0.7293 | 0.5736 | 0.8823 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |
| ledger_observed | w5-13 | 0.8923 | 0.7655 | 1.1588 | 300 | 14 | 52 | 40000 | 40000 | 40000 | True | T9-T1-observed-cash-equal-budget-v1-fullweek | synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included |

## T9→T1: thu hẹp khoảng cách so nhãn sổ

Nguồn: `outputs/t1/T9_T1_gap_reduction.csv`

Giao thức: T9-T1-observed-cash-equal-budget-v1-fullweek

| horizon | bank_WAPE | ledger_WAPE | T9_WAPE | distance_reduction_fraction | reduction_ci_low | reduction_ci_high | bootstrap_n | bootstrap_valid | target_met | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|
| w1-4 | 0.4289 | 0.7293 | 0.5169 | 0.7070 | 0.4241 | 0.8009 | 300 | 300 | True | T9-T1-observed-cash-equal-budget-v1-fullweek |
| w5-13 | 0.5581 | 0.8923 | 0.6483 | 0.7300 | 0.3000 | 0.9297 | 300 | 300 | True | T9-T1-observed-cash-equal-budget-v1-fullweek |

## BPI: ablation trường hợp không có hạn thanh toán

Nguồn: `outputs/t1/BPI_no_due_ablation.csv`

Giao thức: BPI-no-due-age-proxy-v2-streamed **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| setting | model | n | n_firms | pinball_avg | pinball_ci_low | pinball_ci_high | MAE_p50 | cov80 | cov80_ci_low | cov80_ci_high | IS80 | IBS_13w | improvement_pct | improvement_ci_low | improvement_ci_high | vs_current_improvement_pct | vs_current_improvement_ci_low | vs_current_improvement_ci_high | bootstrap_n | n_train | origin | test_used_for_selection | measurement_version | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BPI_no_due_locked_ablation | B1d-cust-quantiles | 385323 | 3 | 4.9325 | 4.6452 | 54.7 | 13.7 | 0.7128 | 0.0000 | 0.7168 | 79.7 | 0.1026 | 0.0000 | 0.0000 | 0.0000 | 53.0 | -437.4 | 55.7 | 300 | 40000 | 2018-07-26 | False | BPI-no-due-age-proxy-v2-streamed | virtual_due_is_proxy_not_contract;no_CQR_when_120d_calibration_gap_unavailable;BPI_payables_not_VN_AR |
| BPI_no_due_locked_ablation | DH-GBM missing due (current) | 385323 | 3 | 10.5 | 10.2 | 19.6 | 25.0 | 0.1205 | 0.1168 | 0.7678 | 190.0 | 0.2257 | -112.8 | -126.0 | 81.4 | 0.0000 | 0.0000 | 0.0000 | 300 | 40000 | 2018-07-26 | False | BPI-no-due-age-proxy-v2-streamed | virtual_due_is_proxy_not_contract;no_CQR_when_120d_calibration_gap_unavailable;BPI_payables_not_VN_AR |
| BPI_no_due_locked_ablation | DH-GBM virtual30 age/no_due | 385323 | 3 | 11.6 | 8.5424 | 14.1 | 26.9 | 0.1020 | 0.0980 | 0.8035 | 212.4 | 0.2482 | -134.5 | -149.3 | 84.4 | -10.2 | -10.3 | 28.1 | 300 | 40000 | 2018-07-26 | False | BPI-no-due-age-proxy-v2-streamed | virtual_due_is_proxy_not_contract;no_CQR_when_120d_calibration_gap_unavailable;BPI_payables_not_VN_AR |

## T8: Brier giữ lời, lịch sử đóng băng hàng tuần

Nguồn: `outputs/t8/reliability_metrics.csv`

Giao thức: T8-weekly-prequential-v1

| world | model | n | n_firms | Brier | Brier_ci_low | Brier_ci_high | improvement_pct | improvement_ci_low | improvement_ci_high | ECE | base_rate | mean_p | bootstrap_n | test_used_for_selection | measurement_version | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| src | Customer historical rate | 6169 | 40 | 0.2366 | 0.2256 | 0.2480 | 0.0000 | 0.0000 | 0.0000 | 0.0486 | 0.5252 | 0.5284 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| src | Firm Beta prior | 6169 | 40 | 0.2536 | 0.2483 | 0.2597 | -7.2024 | -12.5 | -2.2334 | 0.0892 | 0.5252 | 0.4360 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| src | T8 hierarchical recency EB | 6169 | 40 | 0.2256 | 0.2161 | 0.2358 | 4.6283 | 2.9306 | 6.5550 | 0.0256 | 0.5252 | 0.5009 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| src_noisy_promises | Customer historical rate | 6749 | 40 | 0.1821 | 0.1715 | 0.1951 | 0.0000 | 0.0000 | 0.0000 | 0.0365 | 0.2320 | 0.2313 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| src_noisy_promises | Firm Beta prior | 6749 | 40 | 0.1797 | 0.1683 | 0.1931 | 1.3224 | -0.9333 | 3.6360 | 0.0425 | 0.2320 | 0.1895 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| src_noisy_promises | T8 hierarchical recency EB | 6749 | 40 | 0.1750 | 0.1652 | 0.1868 | 3.8924 | 2.3350 | 5.7916 | 0.0150 | 0.2320 | 0.2218 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| tgt | Customer historical rate | 2125 | 13 | 0.2262 | 0.2145 | 0.2533 | 0.0000 | 0.0000 | 0.0000 | 0.0431 | 0.4452 | 0.4452 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| tgt | Firm Beta prior | 2125 | 13 | 0.2525 | 0.2411 | 0.2626 | -11.6 | -17.6 | 1.3916 | 0.0655 | 0.4452 | 0.3859 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |
| tgt | T8 hierarchical recency EB | 2125 | 13 | 0.2175 | 0.2096 | 0.2304 | 3.8252 | 1.0468 | 10.8 | 0.0457 | 0.4452 | 0.4128 | 300 | False | T8-weekly-prequential-v1 | synthetic_kept_labels;weekly_frozen_history;not_human_promise_validation |

## T3→T1: lịch sử tranh chấp tại ngày lập

Nguồn: `outputs/t1/T3_T1_ablation.csv`

Giao thức: T3-T1-at-issue-locked-ablation-v1-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | vs_default_improvement_pct | vs_default_improvement_ci_low | vs_default_improvement_ci_high | stratum | n_train | fit_seconds | rounds | test_used_for_selection | limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| src | B1d-cust-quantiles | 139946 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 3.9838 | 16.7 | 21.0 | 13.9 | 33.5 | 18.0 | 0.5957 | 249.9 | 0.2491 | 0.2491 | 12.4 | 15.4 | 300 | 40 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5625 | 0.6285 | 0.2989 | 0.2237 | 0.5500 | 1.0272 | 0.7461 | -156.4 | -189.6 | -130.0 | all | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM default | 139946 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 2.6560 | 8.5217 | 5.0888 | 5.4222 | 17.0 | 15.8 | 0.8414 | 77.4 | 0.1154 | 0.1154 | 5.0945 | 5.7252 | 300 | 40 | 61.0 | 56.5 | 65.5 | B1d-cust-quantiles | 0.8331 | 0.8503 | 0.1544 | 0.0147 | 0.7674 | 0.4281 | 0.7221 | 0.0000 | 0.0000 | 0.0000 | all | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM + dispute EB at issue | 139946 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 2.6549 | 8.5913 | 5.0872 | 5.4445 | 17.2 | 15.9 | 0.8458 | 77.4 | 0.1159 | 0.1159 | 5.1246 | 5.7459 | 300 | 40 | 60.8 | 56.1 | 65.4 | B1d-cust-quantiles | 0.8363 | 0.8554 | 0.1548 | 0.0130 | 0.7663 | 0.4299 | 0.7202 | -0.4108 | -1.1795 | 0.3116 | all | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | B1d-cust-quantiles | 6204 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 8.5186 | 41.1 | 65.2 | 38.3 | 82.2 | 36.1 | 0.1294 | 736.8 | 0.6196 | 0.6196 | 35.4 | 41.4 | 300 | 40 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.1039 | 0.1590 | 0.6367 | 0.6984 | 0.4234 | 5.0425 | 1.3463 | -330.5 | -381.2 | -283.4 | disputed | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM default | 6204 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 4.9087 | 14.2 | 7.5475 | 8.8867 | 28.4 | 26.9 | 0.7905 | 124.6 | 0.1693 | 0.1693 | 8.1836 | 9.6989 | 300 | 40 | 76.8 | 73.9 | 79.2 | B1d-cust-quantiles | 0.7680 | 0.8127 | 0.1576 | 0.1906 | 0.7903 | 2.1166 | 1.6468 | 0.0000 | 0.0000 | 0.0000 | disputed | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM + dispute EB at issue | 6204 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 4.9099 | 14.6 | 7.6402 | 9.0427 | 29.2 | 27.3 | 0.7874 | 125.5 | 0.1726 | 0.1726 | 8.2842 | 9.9036 | 300 | 40 | 76.4 | 73.3 | 79.0 | B1d-cust-quantiles | 0.7630 | 0.8118 | 0.1598 | 0.1950 | 0.7849 | 2.1229 | 1.6407 | -1.7555 | -3.7404 | 0.3461 | disputed | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | B1d-cust-quantiles | 133742 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 3.7734 | 15.6 | 19.0 | 12.8 | 31.2 | 17.6 | 0.6173 | 227.3 | 0.2320 | 0.2320 | 11.3 | 14.3 | 300 | 40 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.5842 | 0.6496 | 0.2832 | 0.2018 | 0.5659 | 0.9749 | 0.7529 | -142.8 | -176.2 | -115.3 | not_disputed | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM default | 133742 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 2.5515 | 8.2581 | 4.9748 | 5.2615 | 16.5 | 15.5 | 0.8438 | 75.3 | 0.1129 | 0.1129 | 4.9241 | 5.5802 | 300 | 40 | 58.8 | 53.6 | 63.8 | B1d-cust-quantiles | 0.8354 | 0.8529 | 0.1543 | 0.0197 | 0.7682 | 0.4271 | 0.7276 | 0.0000 | 0.0000 | 0.0000 | not_disputed | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| src | DH-GBM + dispute EB at issue | 133742 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 2.5503 | 8.3135 | 4.9688 | 5.2775 | 16.6 | 15.6 | 0.8486 | 75.2 | 0.1133 | 0.1133 | 4.9389 | 5.6035 | 300 | 40 | 58.7 | 53.3 | 63.6 | B1d-cust-quantiles | 0.8387 | 0.8582 | 0.1546 | 0.0194 | 0.7668 | 0.4288 | 0.7256 | -0.3054 | -1.0712 | 0.4509 | not_disputed | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | B1d-cust-quantiles | 52481 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 4.9373 | 21.0 | 25.7 | 17.2 | 42.0 | 20.9 | 0.5649 | 306.8 | 0.3012 | 0.3012 | 14.1 | 22.3 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4814 | 0.6199 | 0.3257 | 0.2717 | 0.5146 | 1.2743 | 0.6066 | -191.8 | -335.7 | -118.5 | all | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM default | 52481 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 3.1340 | 9.7229 | 4.8434 | 5.9001 | 19.4 | 19.1 | 0.8423 | 79.8 | 0.1202 | 0.1202 | 4.9822 | 6.6039 | 300 | 14 | 65.7 | 54.2 | 77.0 | B1d-cust-quantiles | 0.8191 | 0.8742 | 0.1303 | 0.0288 | 0.7863 | 0.4214 | 0.5515 | 0.0000 | 0.0000 | 0.0000 | all | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM + dispute EB at issue | 52481 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 3.1079 | 9.5773 | 4.7027 | 5.7960 | 19.2 | 18.8 | 0.8486 | 78.1 | 0.1183 | 0.1183 | 4.9299 | 6.4472 | 300 | 14 | 66.3 | 55.3 | 77.3 | B1d-cust-quantiles | 0.8297 | 0.8755 | 0.1293 | 0.0202 | 0.7892 | 0.4175 | 0.5483 | 1.7649 | -0.1597 | 3.1380 | all | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | B1d-cust-quantiles | 2637 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 8.0750 | 38.2 | 54.3 | 33.5 | 76.4 | 36.4 | 0.2328 | 624.0 | 0.5503 | 0.5503 | 29.2 | 40.9 | 300 | 11 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.1052 | 0.3013 | 0.5544 | 0.6137 | 0.4596 | 4.4183 | 1.3257 | -302.4 | -440.5 | -225.4 | disputed | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM default | 2637 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 5.1084 | 14.2 | 5.6818 | 8.3332 | 28.4 | 25.1 | 0.8259 | 107.9 | 0.1540 | 0.1540 | 7.1826 | 9.0889 | 300 | 11 | 75.2 | 69.3 | 81.5 | B1d-cust-quantiles | 0.7986 | 0.8617 | 0.1231 | 0.1392 | 0.7888 | 1.7427 | 1.4726 | 0.0000 | 0.0000 | 0.0000 | disputed | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM + dispute EB at issue | 2637 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 5.1556 | 14.7 | 5.9449 | 8.5927 | 29.4 | 24.5 | 0.8290 | 111.0 | 0.1587 | 0.1587 | 7.3432 | 9.4002 | 300 | 11 | 74.4 | 68.4 | 80.8 | B1d-cust-quantiles | 0.8025 | 0.8702 | 0.1287 | 0.1532 | 0.7827 | 1.7888 | 1.4625 | -3.1141 | -4.5765 | -0.7444 | disputed | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | B1d-cust-quantiles | 49844 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 4.7713 | 20.1 | 24.2 | 16.4 | 40.1 | 20.4 | 0.5825 | 290.0 | 0.2880 | 0.2880 | 13.2 | 21.6 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4969 | 0.6408 | 0.3136 | 0.2536 | 0.5254 | 1.2184 | 0.6101 | -183.4 | -328.8 | -109.3 | not_disputed | 40000 | 0.0000 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM default | 49844 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 3.0295 | 9.4855 | 4.7991 | 5.7714 | 19.0 | 19.0 | 0.8432 | 78.3 | 0.1184 | 0.1184 | 4.8676 | 6.4628 | 300 | 14 | 64.7 | 52.2 | 76.7 | B1d-cust-quantiles | 0.8193 | 0.8753 | 0.1307 | 0.0377 | 0.7889 | 0.4269 | 0.5586 | 0.0000 | 0.0000 | 0.0000 | not_disputed | 40000 | 6.9840 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |
| tgt | DH-GBM + dispute EB at issue | 49844 | 7 | T3-T1-at-issue-locked-ablation-v1-fullweek | 2.9995 | 9.3075 | 4.6370 | 5.6480 | 18.6 | 18.6 | 0.8497 | 76.4 | 0.1162 | 0.1162 | 4.7950 | 6.2695 | 300 | 14 | 65.5 | 53.8 | 77.1 | B1d-cust-quantiles | 0.8303 | 0.8763 | 0.1293 | 0.0290 | 0.7936 | 0.4222 | 0.5559 | 2.1376 | -0.0069 | 3.4730 | not_disputed | 40000 | 6.9540 | 300 | False | synthetic_dispute_labels_evaluation_only;feature_closed_history_at_issue;no_automatic_adoption |

## DA1–DA4: xác nhận cặp, ngân sách cố định riêng

Nguồn: `outputs/t1/DA_paired_metrics.csv`

Giao thức: DA-paired-locked-budget-v1-fullweek

| world | months_history | model | n_test | n_firms | n_source | n_target | pinball_avg | pinball_ci_low | pinball_ci_high | WAPE_collect_w1_4 | WAPE_collect_w5_13 | fit_seconds | bootstrap_n | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tgt | 0 | zero-shot | 39304 | 14 | 40000 | 0 | 6.3739 | 5.6862 | 6.8333 | 0.4666 | 0.6275 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 0 | B1 | 39304 | 14 | 40000 | 0 | 16.1 | 14.2 | 18.5 | 1.1395 | 0.7187 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 0 | B1d | 39304 | 14 | 40000 | 0 | 13.7 | 11.6 | 16.6 | 1.0820 | 0.6416 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 3 | zero-shot | 39304 | 14 | 40000 | 5220 | 6.3193 | 5.4367 | 6.9381 | 0.4458 | 0.6030 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 3 | B1 | 39304 | 14 | 40000 | 5220 | 15.7 | 13.7 | 18.1 | 1.0779 | 0.7108 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 3 | B1d | 39304 | 14 | 40000 | 5220 | 12.3 | 10.2 | 15.0 | 1.0104 | 0.6361 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 3 | target-only | 39304 | 14 | 40000 | 5220 | 10.4 | 9.2850 | 11.9 | 0.5915 | 0.7230 | 0.9370 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 3 | fine-tune | 39304 | 14 | 40000 | 5220 | 6.8138 | 5.6887 | 7.6546 | 0.4538 | 0.6183 | 0.9060 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | zero-shot | 39304 | 14 | 40000 | 15864 | 6.3215 | 5.4638 | 6.9608 | 0.4494 | 0.6063 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | B1 | 39304 | 14 | 40000 | 15864 | 15.5 | 13.6 | 17.9 | 1.0187 | 0.7383 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | B1d | 39304 | 14 | 40000 | 15864 | 11.6 | 9.5583 | 14.4 | 0.9635 | 0.6391 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | target-only | 39304 | 14 | 40000 | 15864 | 7.7257 | 6.7029 | 8.2785 | 0.5050 | 0.6476 | 2.8440 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | fine-tune | 39304 | 14 | 40000 | 15864 | 6.6813 | 5.5240 | 7.6489 | 0.4570 | 0.6045 | 4.2030 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | pooled | 39304 | 14 | 40000 | 15864 | 6.3218 | 5.5172 | 6.8871 | 0.4413 | 0.5946 | 18.1 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 6 | IW-pooled | 39304 | 14 | 40000 | 15864 | 6.3218 | 5.5172 | 6.8871 | 0.4413 | 0.5946 | 18.8 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 24 | zero-shot | 39304 | 14 | 40000 | 40000 | 6.3252 | 5.4669 | 6.9724 | 0.4356 | 0.5881 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 24 | B1 | 39304 | 14 | 40000 | 40000 | 15.5 | 13.6 | 17.9 | 1.0170 | 0.7448 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 24 | B1d | 39304 | 14 | 40000 | 40000 | 11.4 | 9.3729 | 14.2 | 0.9542 | 0.6332 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 24 | target-only | 39304 | 14 | 40000 | 40000 | 7.2958 | 5.8498 | 8.5384 | 0.5254 | 0.6400 | 8.7180 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| tgt | 24 | fine-tune | 39304 | 14 | 40000 | 40000 | 6.5748 | 5.4388 | 7.4313 | 0.4571 | 0.5933 | 9.6880 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | zero-shot | 60967 | 12 | 40000 | 18902 | 5.3355 | 4.9704 | 5.6848 | 0.3426 | 0.6316 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | B1 | 60967 | 12 | 40000 | 18902 | 14.3 | 12.4 | 16.9 | 0.9837 | 0.7849 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | B1d | 60967 | 12 | 40000 | 18902 | 11.8 | 10.0 | 14.4 | 0.9333 | 0.6775 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | target-only | 60967 | 12 | 40000 | 18902 | 8.3740 | 6.9157 | 10.4 | 0.5101 | 0.6455 | 2.6250 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | fine-tune | 60967 | 12 | 40000 | 18902 | 5.5424 | 4.9706 | 6.2015 | 0.3724 | 0.6124 | 3.1100 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | pooled | 60967 | 12 | 40000 | 18902 | 5.2709 | 4.9016 | 5.6475 | 0.3523 | 0.6271 | 14.5 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | IW-pooled | 60967 | 12 | 40000 | 18902 | 5.2934 | 4.8994 | 5.6993 | 0.3458 | 0.6272 | 14.8 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | zero-shot | 29159 | 12 | 40000 | 9992 | 6.4031 | 5.5484 | 6.9540 | 0.3526 | 0.8736 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | B1 | 29159 | 12 | 40000 | 9992 | 17.2 | 14.6 | 19.6 | 0.9917 | 0.8805 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | B1d | 29159 | 12 | 40000 | 9992 | 14.7 | 12.3 | 16.7 | 0.9017 | 0.7806 | 0.0000 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | target-only | 29159 | 12 | 40000 | 9992 | 7.9201 | 6.7354 | 8.8032 | 0.3868 | 0.8849 | 1.7500 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | fine-tune | 29159 | 12 | 40000 | 9992 | 6.7143 | 5.7519 | 7.4640 | 0.3490 | 0.8187 | 2.0780 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | pooled | 29159 | 12 | 40000 | 9992 | 6.4203 | 5.4672 | 7.0711 | 0.3415 | 0.8449 | 12.1 | 300 | False | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | IW-pooled | 29159 | 12 | 40000 | 9992 | 6.3963 | 5.4662 | 7.0014 | 0.3440 | 0.8450 | 12.3 | 300 | False | DA-paired-locked-budget-v1-fullweek |

## DA1–DA4: CI cặp theo công ty

Nguồn: `outputs/t1/DA_paired_comparisons.csv`

Giao thức: DA-paired-locked-budget-v1-fullweek

| hypothesis | world | months_history | model | baseline | metric | threshold_pct | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | bootstrap_n | status | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DA1 | tgt | 0 | zero-shot | B1 | cash_error_w1_4 | 20 | 59.1 | 46.6 | 65.6 | 14 | 300 | supported | False | DA-paired-locked-budget-v1-fullweek |
| DA2 | tgt | 3 | fine-tune | zero-shot | pinball_sum | 10 | -7.8251 | -16.9 | -2.7142 | 14 | 300 | rejected | False | DA-paired-locked-budget-v1-fullweek |
| DA3 | tgt | 3 | fine-tune | target-only | pinball_sum | 0 | 34.6 | 28.2 | 44.0 | 14 | 300 | supported | False | DA-paired-locked-budget-v1-fullweek |
| DA3 | tgt | 6 | fine-tune | target-only | pinball_sum | 0 | 13.5 | 7.0245 | 22.8 | 14 | 300 | supported | False | DA-paired-locked-budget-v1-fullweek |
| DA4 | tgt | 6 | IW-pooled | pooled | pinball_sum | 0 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | rejected | False | DA-paired-locked-budget-v1-fullweek |
| DA3 | tgt | 24 | target-only | fine-tune | pinball_sum | 0 | -11.0 | -15.0 | -3.5081 | 14 | 300 | rejected | False | DA-paired-locked-budget-v1-fullweek |
| DA4 | sens_uk | 6 | IW-pooled | pooled | pinball_sum | 0 | -0.4279 | -1.0169 | 0.0705 | 12 | 300 | not_demonstrated | False | DA-paired-locked-budget-v1-fullweek |
| DA4 | sens_coface | 6 | IW-pooled | pooled | pinball_sum | 0 | 0.3740 | -0.5612 | 1.2843 | 12 | 300 | not_demonstrated | False | DA-paired-locked-budget-v1-fullweek |

## IW: trọng số và số mẫu hiệu dụng, không phải chỉ số test

Nguồn: `outputs/t1/IW_weight_diagnostics.csv`

Giao thức: DA-paired-locked-budget-v1-fullweek

| world | months_history | n_source | n_target | weight_min | weight_max | weight_mean | weight_std | effective_sample_size | constant_weights | classifier | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tgt | 6 | 40000 | 15864 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 40000.0 | True | in-sample density ratio, fixed 200 trees; saturation can erase differences | DA-paired-locked-budget-v1-fullweek |
| sens_uk | 6 | 40000 | 18902 | 1.0000 | 1.9829 | 1.0000 | 0.0050 | 39999.0 | False | in-sample density ratio, fixed 200 trees; saturation can erase differences | DA-paired-locked-budget-v1-fullweek |
| sens_coface | 6 | 40000 | 9992 | 0.9997 | 3.6348 | 1.0000 | 0.0205 | 39983.2 | False | in-sample density ratio, fixed 200 trees; saturation can erase differences | DA-paired-locked-budget-v1-fullweek |

## T9: recall riêng các hard cases, nguồn/ngưỡng cố định

Nguồn: `outputs/t9/hard_case_recall.csv`

Giao thức: T9-hard-case-post-calibration-v1 Đã đo 12/12 tình huống; giao thức đầy đủ hoàn tất = True. Kỳ test sau calibration: 2024-07→2025-06, không bao phủ đợt supply_shock 2022; DN mới có lịch sử ngắn hơn (ngày sao kê thực tế trong bảng).

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | settled_invoice_coverage | pay_date_MAE_ledger_days | method | link_precision_ci_low | link_precision_ci_high | link_recall_ci_low | link_recall_ci_high | link_f1_ci_low | link_f1_ci_high | pay_date_MAE_ci_low | pay_date_MAE_ci_high | auto_coverage_ci_low | auto_coverage_ci_high | bootstrap_n | n_firms | case | world | n_bank | auto_txn_coverage | n_review | test_start | test_end | tau_auto | test_used_for_selection | observed_first_bank_date | observed_last_bank_date | measurement_version | seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9776 | 0.5499 | 0.7039 | 9399 | 16708 | 0.0276 | 0.6231 | 0.9874 | 0.5939 | 10.1 | R1 unique amount | 0.9532 | 0.9904 | 0.3497 | 0.7268 | 0.5135 | 0.8380 | 0.1531 | 1.5845 | 0.5749 | 0.7253 | 300 | 12 | lumpy_customer | hc_lumpy_customer_v2 | 14110 | 0.6661 | 4711 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 481.9 |
| 1.0000 | 0.2538 | 0.4049 | 4241 | 16708 | 0.0000 | 0.0000 | 1.0000 | 0.2706 | 10.1 | R2 memo | 1.0000 | 1.0000 | 0.1795 | 0.3317 | 0.3043 | 0.4981 | 0.0000 | 0.0000 | 0.2523 | 0.3319 | 300 | 12 | lumpy_customer | hc_lumpy_customer_v2 | 14110 | 0.2862 | 10072 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 481.9 |
| 0.9705 | 0.6447 | 0.7747 | 11098 | 16708 | 0.0276 | 0.7108 | 0.9823 | 0.6998 | 10.1 | Hybrid frozen tau=.9 | 0.9439 | 0.9872 | 0.4351 | 0.8113 | 0.5967 | 0.8906 | 0.2250 | 1.6134 | 0.6647 | 0.7910 | 300 | 12 | lumpy_customer | hc_lumpy_customer_v2 | 14110 | 0.7433 | 3622 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 481.9 |
| 0.9762 | 0.5750 | 0.7237 | 8018 | 13613 | 0.0299 | 0.5648 | 0.9854 | 0.6313 | 8.7693 | R1 unique amount | 0.9631 | 0.9906 | 0.5259 | 0.6784 | 0.6824 | 0.8045 | 0.1887 | 0.9008 | 0.6129 | 0.6874 | 300 | 12 | group_payer | hc_group_payer | 12593 | 0.6367 | 4575 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 840.6 |
| 1.0000 | 0.3340 | 0.5008 | 4547 | 13613 | 0.0000 | 0.0000 | 1.0000 | 0.3613 | 8.7693 | R2 memo | 1.0000 | 1.0000 | 0.2754 | 0.3791 | 0.4319 | 0.5498 | 0.0000 | 0.0000 | 0.2679 | 0.3911 | 300 | 12 | group_payer | hc_group_payer | 12593 | 0.3380 | 8336 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 840.6 |
| 0.9671 | 0.6915 | 0.8064 | 9734 | 13613 | 0.0290 | 0.7874 | 0.9760 | 0.7666 | 8.7693 | Hybrid frozen tau=.9 | 0.9461 | 0.9883 | 0.6621 | 0.7493 | 0.7825 | 0.8516 | 0.2426 | 1.2515 | 0.6748 | 0.7505 | 300 | 12 | group_payer | hc_group_payer | 12593 | 0.7160 | 3577 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 840.6 |
| 0.9740 | 0.5736 | 0.7220 | 7953 | 13504 | 0.0324 | 0.7417 | 0.9848 | 0.6302 | 11.2 | R1 unique amount | 0.9599 | 0.9896 | 0.5227 | 0.6798 | 0.6788 | 0.8043 | 0.2337 | 1.2019 | 0.6149 | 0.6836 | 300 | 12 | heterogeneity | hc_heterogeneity | 12467 | 0.6379 | 4514 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 779.8 |
| 1.0000 | 0.3318 | 0.4982 | 4480 | 13504 | 0.0000 | 0.0000 | 1.0000 | 0.3585 | 11.2 | R2 memo | 1.0000 | 1.0000 | 0.2813 | 0.3739 | 0.4390 | 0.5443 | 0.0000 | 0.0000 | 0.2697 | 0.3835 | 300 | 12 | heterogeneity | hc_heterogeneity | 12467 | 0.3342 | 8300 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 779.8 |
| 0.9538 | 0.7237 | 0.8230 | 10246 | 13504 | 0.0315 | 1.2370 | 0.9653 | 0.8106 | 11.2 | Hybrid frozen tau=.9 | 0.9324 | 0.9835 | 0.7001 | 0.7774 | 0.8012 | 0.8674 | 0.4521 | 1.8876 | 0.7019 | 0.7730 | 300 | 12 | heterogeneity | hc_heterogeneity | 12467 | 0.7413 | 3225 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 779.8 |
| 0.9357 | 0.4440 | 0.6022 | 6613 | 13938 | 0.0327 | 1.7449 | 0.9549 | 0.5299 | 9.5770 | R1 unique amount | 0.8708 | 0.9848 | 0.3498 | 0.5724 | 0.4989 | 0.7219 | 0.3633 | 3.6925 | 0.4640 | 0.5994 | 300 | 12 | cod_realistic | hc_cod_realistic | 12406 | 0.5330 | 5793 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 801.5 |
| 1.0000 | 0.2589 | 0.4114 | 3609 | 13938 | 0.0000 | 0.0000 | 1.0000 | 0.2946 | 9.5770 | R2 memo | 1.0000 | 1.0000 | 0.2285 | 0.2970 | 0.3720 | 0.4579 | 0.0000 | 0.0000 | 0.2289 | 0.3001 | 300 | 12 | cod_realistic | hc_cod_realistic | 12406 | 0.2709 | 9045 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 801.5 |
| 0.9050 | 0.5602 | 0.6920 | 8628 | 13938 | 0.0336 | 2.5545 | 0.9252 | 0.6900 | 9.5770 | Hybrid frozen tau=.9 | 0.8327 | 0.9740 | 0.4817 | 0.6658 | 0.6101 | 0.7880 | 0.7177 | 4.5190 | 0.5900 | 0.6589 | 300 | 12 | cod_realistic | hc_cod_realistic | 12406 | 0.6242 | 4662 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 801.5 |
| 0.9650 | 0.4689 | 0.6312 | 6459 | 13292 | 0.0323 | 0.7515 | 0.9782 | 0.5065 | 7.8538 | R1 unique amount | 0.9493 | 0.9825 | 0.4369 | 0.5363 | 0.6001 | 0.6923 | 0.3161 | 1.1291 | 0.4777 | 0.5575 | 300 | 12 | discount_early | hc_discount_early_v2 | 12293 | 0.5254 | 5834 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 219.6 |
| 1.0000 | 0.2762 | 0.4328 | 3671 | 13292 | 0.0000 | 0.0000 | 1.0000 | 0.2915 | 7.8538 | R2 memo | 1.0000 | 1.0000 | 0.2173 | 0.3179 | 0.3570 | 0.4824 | 0.0000 | 0.0000 | 0.2123 | 0.3229 | 300 | 12 | discount_early | hc_discount_early_v2 | 12293 | 0.2780 | 8876 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 219.6 |
| 0.9394 | 0.5871 | 0.7226 | 8307 | 13292 | 0.0342 | 1.2437 | 0.9530 | 0.6508 | 7.8538 | Hybrid frozen tau=.9 | 0.9077 | 0.9764 | 0.5194 | 0.6298 | 0.6741 | 0.7616 | 0.3902 | 1.9583 | 0.5237 | 0.6557 | 300 | 12 | discount_early | hc_discount_early_v2 | 12293 | 0.6064 | 4839 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 219.6 |
| 0.8889 | 0.3587 | 0.5111 | 6238 | 15459 | 0.0620 | 2.5947 | 0.9624 | 0.4825 | 64.4 | R1 unique amount | 0.8466 | 0.9491 | 0.3064 | 0.4583 | 0.4517 | 0.6176 | 1.0237 | 4.0395 | 0.3984 | 0.4825 | 300 | 12 | retention | hc_retention | 14503 | 0.4301 | 8265 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 108.0 |
| 1.0000 | 0.1800 | 0.3051 | 2783 | 15459 | 0.0000 | 0.0000 | 1.0000 | 0.2329 | 64.4 | R2 memo | 1.0000 | 1.0000 | 0.1416 | 0.2153 | 0.2480 | 0.3543 | 0.0000 | 0.0000 | 0.1426 | 0.2211 | 300 | 12 | retention | hc_retention | 14503 | 0.1843 | 11830 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 108.0 |
| 0.8274 | 0.4407 | 0.5751 | 8234 | 15459 | 0.0613 | 5.3859 | 0.9375 | 0.6084 | 64.4 | Hybrid frozen tau=.9 | 0.7838 | 0.9070 | 0.3990 | 0.5154 | 0.5327 | 0.6561 | 2.2760 | 7.7380 | 0.4872 | 0.5401 | 300 | 12 | retention | hc_retention | 14503 | 0.5144 | 7043 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 108.0 |
| 0.9685 | 0.5202 | 0.6769 | 7312 | 13613 | 0.0299 | 0.8305 | 0.9795 | 0.5747 | 8.7693 | R1 unique amount | 0.9530 | 0.9868 | 0.4807 | 0.6088 | 0.6403 | 0.7523 | 0.3283 | 1.2418 | 0.5572 | 0.6203 | 300 | 12 | fx | hc_fx | 12593 | 0.5806 | 5281 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.3 |
| 1.0000 | 0.2995 | 0.4609 | 4077 | 13613 | 0.0000 | 0.0000 | 1.0000 | 0.3239 | 8.7693 | R2 memo | 1.0000 | 1.0000 | 0.2476 | 0.3402 | 0.3969 | 0.5076 | 0.0000 | 0.0000 | 0.2413 | 0.3533 | 300 | 12 | fx | hc_fx | 12593 | 0.3052 | 8749 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.3 |
| 0.9409 | 0.6414 | 0.7628 | 9279 | 13613 | 0.0271 | 1.5923 | 0.9539 | 0.7272 | 8.7693 | Hybrid frozen tau=.9 | 0.9199 | 0.9772 | 0.6139 | 0.6872 | 0.7435 | 0.8019 | 0.7163 | 2.1356 | 0.6229 | 0.7061 | 300 | 12 | fx | hc_fx | 12593 | 0.6667 | 4197 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.3 |
| 0.9762 | 0.5750 | 0.7237 | 8018 | 13613 | 0.0299 | 0.5648 | 0.9854 | 0.6313 | 8.7693 | R1 unique amount | 0.9631 | 0.9906 | 0.5259 | 0.6784 | 0.6824 | 0.8045 | 0.1887 | 0.9008 | 0.6129 | 0.6874 | 300 | 12 | credit_note | hc_credit_note | 12593 | 0.6367 | 4575 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.8 |
| 1.0000 | 0.3234 | 0.4888 | 4403 | 13613 | 0.0000 | 0.0000 | 1.0000 | 0.3498 | 8.7693 | R2 memo | 1.0000 | 1.0000 | 0.2690 | 0.3666 | 0.4239 | 0.5365 | 0.0000 | 0.0000 | 0.2615 | 0.3789 | 300 | 12 | credit_note | hc_credit_note | 12593 | 0.3279 | 8464 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.8 |
| 0.9556 | 0.7183 | 0.8201 | 10232 | 13613 | 0.0290 | 1.1387 | 0.9655 | 0.8049 | 8.7693 | Hybrid frozen tau=.9 | 0.9372 | 0.9866 | 0.6930 | 0.7735 | 0.7979 | 0.8666 | 0.3528 | 1.5811 | 0.6933 | 0.7702 | 300 | 12 | credit_note | hc_credit_note | 12593 | 0.7341 | 3348 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 202.8 |
| 0.9718 | 0.5657 | 0.7151 | 7914 | 13595 | 0.0328 | 0.7229 | 0.9806 | 0.6239 | 8.8175 | R1 unique amount | 0.9560 | 0.9886 | 0.5156 | 0.6727 | 0.6715 | 0.8001 | 0.2130 | 1.1932 | 0.6052 | 0.6825 | 300 | 12 | verbal | hc_verbal | 12565 | 0.6298 | 4651 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 121.9 |
| 1.0000 | 0.3293 | 0.4955 | 4477 | 13595 | 0.0000 | 0.0000 | 1.0000 | 0.3560 | 8.8175 | R2 memo | 1.0000 | 1.0000 | 0.2709 | 0.3745 | 0.4263 | 0.5449 | 0.0000 | 0.0000 | 0.2634 | 0.3830 | 300 | 12 | verbal | hc_verbal | 12565 | 0.3322 | 8391 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 121.9 |
| 0.9486 | 0.7130 | 0.8141 | 10218 | 13595 | 0.0328 | 1.4747 | 0.9601 | 0.8033 | 8.8175 | Hybrid frozen tau=.9 | 0.9232 | 0.9843 | 0.6865 | 0.7700 | 0.7902 | 0.8620 | 0.3601 | 2.2113 | 0.6878 | 0.7703 | 300 | 12 | verbal | hc_verbal | 12565 | 0.7324 | 3363 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-27 | T9-hard-case-post-calibration-v1 | 121.9 |
| 0.9761 | 0.5750 | 0.7237 | 8020 | 13614 | 0.0301 | 0.5685 | 0.9853 | 0.6314 | 8.7682 | R1 unique amount | 0.9630 | 0.9905 | 0.5259 | 0.6785 | 0.6824 | 0.8045 | 0.1944 | 0.9042 | 0.6130 | 0.6877 | 300 | 12 | supply_shock | hc_supply_shock_v2 | 12585 | 0.6373 | 4565 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 123.2 |
| 1.0000 | 0.3343 | 0.5011 | 4551 | 13614 | 0.0000 | 0.0000 | 1.0000 | 0.3616 | 8.7682 | R2 memo | 1.0000 | 1.0000 | 0.2766 | 0.3791 | 0.4334 | 0.5498 | 0.0000 | 0.0000 | 0.2704 | 0.3908 | 300 | 12 | supply_shock | hc_supply_shock_v2 | 12585 | 0.3387 | 8323 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 123.2 |
| 0.9557 | 0.7187 | 0.8204 | 10238 | 13614 | 0.0292 | 1.1371 | 0.9656 | 0.8053 | 8.7682 | Hybrid frozen tau=.9 | 0.9372 | 0.9863 | 0.6932 | 0.7741 | 0.7982 | 0.8670 | 0.3533 | 1.5840 | 0.6941 | 0.7706 | 300 | 12 | supply_shock | hc_supply_shock_v2 | 12585 | 0.7349 | 3336 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 123.2 |
| 0.9777 | 0.5629 | 0.7145 | 7660 | 13304 | 0.0232 | 0.7624 | 0.9846 | 0.6198 | 8.9835 | R1 unique amount | 0.9672 | 0.9904 | 0.5148 | 0.6709 | 0.6731 | 0.7990 | 0.3976 | 1.0822 | 0.6004 | 0.6899 | 300 | 12 | seasonal_extreme | hc_seasonal_extreme | 12128 | 0.6316 | 4468 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 111.5 |
| 1.0000 | 0.3288 | 0.4949 | 4374 | 13304 | 0.0000 | 0.0000 | 1.0000 | 0.3563 | 8.9835 | R2 memo | 1.0000 | 1.0000 | 0.2817 | 0.3696 | 0.4396 | 0.5397 | 0.0000 | 0.0000 | 0.2753 | 0.3853 | 300 | 12 | seasonal_extreme | hc_seasonal_extreme | 12128 | 0.3384 | 8024 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 111.5 |
| 0.9573 | 0.7127 | 0.8171 | 9905 | 13304 | 0.0223 | 1.2757 | 0.9650 | 0.8000 | 8.9835 | Hybrid frozen tau=.9 | 0.9413 | 0.9836 | 0.6833 | 0.7781 | 0.7925 | 0.8686 | 0.6072 | 1.7278 | 0.6880 | 0.7692 | 300 | 12 | seasonal_extreme | hc_seasonal_extreme | 12128 | 0.7304 | 3270 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2024-07-01 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 111.5 |
| 0.9965 | 0.7793 | 0.8746 | 2016 | 2578 | 0.0037 | 0.0427 | 0.9985 | 0.8193 | 4.9862 | R1 unique amount | 0.9944 | 0.9991 | 0.7162 | 0.8580 | 0.8336 | 0.9230 | 0.0014 | 0.1119 | 0.6635 | 0.7156 | 300 | 12 | new_company | hc_new_company | 2950 | 0.6834 | 934 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2025-01-02 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 14.7 |
| 1.0000 | 0.3549 | 0.5239 | 915 | 2578 | 0.0000 | 0.0000 | 1.0000 | 0.3724 | 4.9862 | R2 memo | 1.0000 | 1.0000 | 0.3164 | 0.3865 | 0.4806 | 0.5576 | 0.0000 | 0.0000 | 0.2559 | 0.3334 | 300 | 12 | new_company | hc_new_company | 2950 | 0.3000 | 2065 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2025-01-02 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 14.7 |
| 0.9920 | 0.8654 | 0.9244 | 2249 | 2578 | 0.0056 | 0.1402 | 0.9964 | 0.9117 | 4.9862 | Hybrid frozen tau=.9 | 0.9833 | 0.9984 | 0.8438 | 0.8920 | 0.9116 | 0.9400 | 0.0059 | 0.3928 | 0.6955 | 0.7410 | 300 | 12 | new_company | hc_new_company | 2950 | 0.7210 | 823 | 2024-07-01 | 2025-06-29 | 0.9000 | False | 2025-01-02 | 2025-06-28 | T9-hard-case-post-calibration-v1 | 14.7 |

## T6: ETS/ARIMA/B0, cùng cohort và chuẩn hoá E2E

Nguồn: `outputs/t6/traditional/metrics.csv`

Giao thức: cash-traditional-same-E2E-cohort-v1

| model | horizon | n | n_firms | cov80 | cov80_ci_low | cov80_ci_high | IS80 | IS80_ci_low | IS80_ci_high | vs_E2E_ACI_improvement_pct | vs_E2E_ACI_improvement_ci_low | vs_E2E_ACI_improvement_ci_high | MAE_p50 | pinball | bootstrap_n | measurement_version | test_used_for_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARIMA (declared fallback) | w1-4 | 2912 | 14 | 0.7411 | 0.6930 | 0.7905 | 13.1 | 10.9 | 15.1 | -7.2244 | -35.0 | 13.0 | 2.4357 | 0.8416 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| ARIMA (declared fallback) | w5-13 | 6552 | 14 | 0.6458 | 0.5794 | 0.7074 | 24.9 | 19.0 | 31.7 | -19.6 | -52.2 | 5.9868 | 4.6440 | 1.6046 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| B0 due spreadsheet | w1-4 | 2912 | 14 | 0.0000 | 0.0000 | 0.0000 | 234.9 | 135.8 | 376.0 | -1826.8 | -2521.2 | -1211.3 | 23.5 | 11.7 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| B0 due spreadsheet | w5-13 | 6552 | 14 | 0.0000 | 0.0000 | 0.0000 | 244.6 | 151.6 | 377.5 | -1074.0 | -1518.5 | -677.5 | 24.5 | 12.2 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| ETS (declared fallback) | w1-4 | 2912 | 14 | 0.7785 | 0.7522 | 0.8136 | 12.8 | 11.1 | 14.4 | -4.8598 | -35.0 | 17.4 | 2.4392 | 0.8326 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| ETS (declared fallback) | w5-13 | 6552 | 14 | 0.7647 | 0.6888 | 0.8326 | 27.3 | 22.4 | 32.8 | -30.8 | -66.8 | -4.1169 | 5.1538 | 1.7677 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| MC-copula-t + ACI | w1-4 | 2912 | 14 | 0.7603 | 0.6579 | 0.8381 | 12.2 | 9.6412 | 15.4 | 0.0000 | 0.0000 | 0.0000 | 2.1625 | 0.7667 | 300 | cash-traditional-same-E2E-cohort-v1 | False |
| MC-copula-t + ACI | w5-13 | 6552 | 14 | 0.7744 | 0.6575 | 0.8612 | 20.8 | 16.1 | 26.4 | 0.0000 | 0.0000 | 0.0000 | 3.9132 | 1.3467 | 300 | cash-traditional-same-E2E-cohort-v1 | False |

## ETS/ARIMA: số fit hội tụ và lần dùng mốc dự phòng

Nguồn: `outputs/t6/traditional/fit_summary.csv`

Giao thức: cash-traditional-same-E2E-cohort-v1

| model | n_fits | fallback_count | converged_count | warning_count | measurement_version |
|---|---|---|---|---|---|
| ARIMA | 728 | 2 | 726 | 306 | cash-traditional-same-E2E-cohort-v1 |
| ETS | 728 | 0 | 728 | 0 | cash-traditional-same-E2E-cohort-v1 |

## T6: Chronos-Bolt Tiny zero-shot trên số dư tuần

Nguồn: `outputs/t6/chronos/metrics.csv`

Giao thức: chronos-bolt-tiny-zero-shot-E2E-v1

| model | horizon | n | n_firms | cov80 | cov80_ci_low | cov80_ci_high | IS80 | IS80_ci_low | IS80_ci_high | pinball | MAE_p50 | bootstrap_n | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chronos-Bolt Tiny zero-shot | w1-4 | 2912 | 14 | 0.7953 | 0.7577 | 0.8273 | 11.8 | 10.2 | 13.4 | 0.7900 | 2.3855 | 300 | False | chronos-bolt-tiny-zero-shot-E2E-v1 |
| Chronos-Bolt Tiny zero-shot | w5-13 | 6552 | 14 | 0.7424 | 0.6859 | 0.7961 | 18.7 | 15.3 | 22.4 | 1.2894 | 3.9969 | 300 | False | chronos-bolt-tiny-zero-shot-E2E-v1 |
| MC-copula-t + ACI | w1-4 | 2912 | 14 | 0.7603 | 0.6579 | 0.8381 | 12.2 | 9.6412 | 15.4 | 0.7667 | 2.1625 | 300 | False | chronos-bolt-tiny-zero-shot-E2E-v1 |
| MC-copula-t + ACI | w5-13 | 6552 | 14 | 0.7744 | 0.6575 | 0.8612 | 20.8 | 16.1 | 26.4 | 1.3467 | 3.9132 | 300 | False | chronos-bolt-tiny-zero-shot-E2E-v1 |

## T6: CI cặp mô hình chính so đối chứng thêm

Nguồn: `outputs/t6/additional_baseline_comparisons.csv`

Giao thức: cash-paired-additional-baselines-v1 **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**

| main | challenger | horizon | metric | main_loss | challenger_loss | main_improvement_pct | main_improvement_ci_low | main_improvement_ci_high | n_firms | bootstrap_n | main_beats_challenger_with_CI | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MC-copula-t + ACI | ARIMA (declared fallback) | w1-4 | IS80 | 12.2 | 13.1 | 6.7376 | -15.0 | 26.0 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ARIMA (declared fallback) | w1-4 | pinball | 0.7667 | 0.8416 | 8.8988 | -7.5348 | 23.5 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ARIMA (declared fallback) | w1-4 | MAE | 2.1625 | 2.4357 | 11.2 | 0.2247 | 22.6 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ARIMA (declared fallback) | w5-13 | IS80 | 20.8 | 24.9 | 16.4 | -6.3680 | 34.3 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ARIMA (declared fallback) | w5-13 | pinball | 1.3467 | 1.6046 | 16.1 | -3.8336 | 33.1 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ARIMA (declared fallback) | w5-13 | MAE | 3.9132 | 4.6440 | 15.7 | -2.2263 | 32.6 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w1-4 | IS80 | 12.2 | 234.9 | 94.8 | 92.4 | 96.2 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w1-4 | pinball | 0.7667 | 11.7 | 93.5 | 90.1 | 95.2 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w1-4 | MAE | 2.1625 | 23.5 | 90.8 | 85.6 | 93.4 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w5-13 | IS80 | 20.8 | 244.6 | 91.5 | 87.1 | 93.8 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w5-13 | pinball | 1.3467 | 12.2 | 89.0 | 83.6 | 91.6 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | B0 due spreadsheet | w5-13 | MAE | 3.9132 | 24.5 | 84.0 | 76.4 | 87.5 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w1-4 | IS80 | 12.2 | 11.8 | -3.5528 | -29.1 | 17.8 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w1-4 | pinball | 0.7667 | 0.7900 | 2.9398 | -15.8 | 19.3 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w1-4 | MAE | 2.1625 | 2.3855 | 9.3475 | -2.9847 | 21.5 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w5-13 | IS80 | 20.8 | 18.7 | -11.4 | -39.4 | 12.5 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w5-13 | pinball | 1.3467 | 1.2894 | -4.4472 | -29.4 | 14.2 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | Chronos-Bolt Tiny zero-shot | w5-13 | MAE | 3.9132 | 3.9969 | 2.0937 | -21.5 | 19.1 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w1-4 | IS80 | 12.2 | 12.8 | 4.6346 | -21.1 | 25.9 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w1-4 | pinball | 0.7667 | 0.8326 | 7.9098 | -10.2 | 23.9 | 14 | 300 | False | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w1-4 | MAE | 2.1625 | 2.4392 | 11.3 | 0.5800 | 21.5 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w5-13 | IS80 | 20.8 | 27.3 | 23.6 | 3.9537 | 40.1 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w5-13 | pinball | 1.3467 | 1.7677 | 23.8 | 9.1870 | 37.4 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |
| MC-copula-t + ACI | ETS (declared fallback) | w5-13 | MAE | 3.9132 | 5.1538 | 24.1 | 11.7 | 34.2 | 14 | 300 | True | False | cash-paired-additional-baselines-v1 |

## P0/P1/P2: mô phỏng chính sách thu nợ, không phải tác động nhân quả

Nguồn: `outputs/t6/collection_policy/metrics.csv`

Giao thức: collection-policy-known-settlement-v2-fullweek

| policy | q | metric | mean | baseline_mean | reduction_vs_P0 | reduction_ci_low | reduction_ci_high | n_firms | bootstrap_n | n_calls | cash_accelerated | evidence_type | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0 | 0.0000 | shortfall_events | 1.1429 | 1.1429 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | 0 | 0.0000 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P0 | 0.0000 | shortfall_weeks | 6.9286 | 6.9286 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | 0 | 0.0000 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P0 | 0.0000 | DSO | 63.0 | 63.0 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | 0 | 0.0000 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.3000 | shortfall_events | 0.9286 | 1.1429 | 0.2143 | -0.3232 | 0.6804 | 14 | 300 | 710 | 51870471000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.3000 | shortfall_weeks | 5.7857 | 6.9286 | 1.1429 | 0.2143 | 2.5036 | 14 | 300 | 710 | 51870471000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.3000 | DSO | 56.7 | 63.0 | 6.3532 | 4.4838 | 8.4994 | 14 | 300 | 710 | 51870471000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.5000 | shortfall_events | 0.8571 | 1.1429 | 0.2857 | -0.2857 | 0.8946 | 14 | 300 | 706 | 75526652000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.5000 | shortfall_weeks | 5.5000 | 6.9286 | 1.4286 | 0.2857 | 3.1429 | 14 | 300 | 706 | 75526652000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.5000 | DSO | 53.1 | 63.0 | 9.8822 | 6.8237 | 13.3 | 14 | 300 | 706 | 75526652000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.7000 | shortfall_events | 0.7857 | 1.1429 | 0.3571 | -0.2857 | 1.0375 | 14 | 300 | 703 | 93981802000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.7000 | shortfall_weeks | 5.3571 | 6.9286 | 1.5714 | 0.3571 | 3.3232 | 14 | 300 | 703 | 93981802000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P1-largest | 0.7000 | DSO | 50.2 | 63.0 | 12.9 | 9.0447 | 17.8 | 14 | 300 | 703 | 93981802000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.3000 | shortfall_events | 1.0000 | 1.1429 | 0.1429 | -0.3946 | 0.5000 | 14 | 300 | 710 | 51218316000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.3000 | shortfall_weeks | 5.8571 | 6.9286 | 1.0714 | 0.2143 | 2.3232 | 14 | 300 | 710 | 51218316000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.3000 | DSO | 56.6 | 63.0 | 6.4515 | 4.4993 | 9.0199 | 14 | 300 | 710 | 51218316000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.5000 | shortfall_events | 0.8571 | 1.1429 | 0.2857 | -0.2857 | 0.8946 | 14 | 300 | 706 | 73616401000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.5000 | shortfall_weeks | 5.5000 | 6.9286 | 1.4286 | 0.2857 | 3.1429 | 14 | 300 | 706 | 73616401000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.5000 | DSO | 53.4 | 63.0 | 9.6683 | 6.5485 | 13.1 | 14 | 300 | 706 | 73616401000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.7000 | shortfall_events | 0.7857 | 1.1429 | 0.3571 | -0.2857 | 1.0375 | 14 | 300 | 703 | 91191414000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.7000 | shortfall_weeks | 5.4286 | 6.9286 | 1.5000 | 0.2857 | 3.2518 | 14 | 300 | 703 | 91191414000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |
| P2-delta | 0.7000 | DSO | 50.4 | 63.0 | 12.6 | 8.7027 | 17.5 | 14 | 300 | 703 | 91191414000.0 | policy_simulation_not_causal | False | collection-policy-known-settlement-v2-fullweek |

## P2 so P1: cùng công ty và giả định phản hồi

Nguồn: `outputs/t6/collection_policy/P2_vs_P1.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| q | metric | mean_P1 | mean_P2 | reduction_P2_vs_P1 | reduction_ci_low | reduction_ci_high | n_firms | bootstrap_n | decision | evidence_type | test_used_for_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.3000 | shortfall_events | 0.9286 | 1.0714 | -0.1429 | -0.3571 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.3000 | shortfall_weeks | 5.7857 | 6.0714 | -0.2857 | -0.7518 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.3000 | DSO | 56.7 | 57.1 | -0.4427 | -1.2254 | 0.1085 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.5000 | shortfall_events | 0.8571 | 0.8571 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.5000 | shortfall_weeks | 5.5000 | 5.5714 | -0.0714 | -0.2143 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.5000 | DSO | 53.1 | 53.4 | -0.2788 | -0.7935 | 0.1569 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.7000 | shortfall_events | 0.7857 | 0.7857 | 0.0000 | 0.0000 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.7000 | shortfall_weeks | 5.3571 | 5.4286 | -0.0714 | -0.2143 | 0.0000 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |
| 0.7000 | DSO | 50.2 | 50.4 | -0.2760 | -0.6520 | 0.1083 | 14 | 300 | not_demonstrated | policy_simulation_not_causal | False |

## T7→T6: bộ điều khiển chế độ, hai cửa sổ khủng hoảng

Nguồn: `outputs/t7/regime_cash/metrics.csv`

Giao thức: regime-cash-source-cal-120gap-v1-fullweek

| window | horizon | model | n | n_firms | cov80 | cov80_ci_low | cov80_ci_high | coverage_change | coverage_change_ci_low | coverage_change_ci_high | IS80 | IS80_improvement_pct | IS80_improvement_ci_low | IS80_improvement_ci_high | point_coverage_target_met | bootstrap_n | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021-07-01 | all | with_controller | 3276 | 14 | 0.6587 | 0.5869 | 0.7228 | -0.0009 | -0.0024 | 0.0000 | 13.7 | 0.0569 | -0.0075 | 0.2102 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2021-07-01 | all | without_controller | 3276 | 14 | 0.6596 | 0.5875 | 0.7237 | 0.0000 | 0.0000 | 0.0000 | 13.7 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2021-07-01 | w1-4 | with_controller | 1008 | 14 | 0.6448 | 0.5709 | 0.7144 | 0.0020 | 0.0000 | 0.0050 | 9.2068 | 0.0653 | 0.0000 | 0.2161 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2021-07-01 | w1-4 | without_controller | 1008 | 14 | 0.6429 | 0.5693 | 0.7109 | 0.0000 | 0.0000 | 0.0000 | 9.2128 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2021-07-01 | w5-13 | with_controller | 2268 | 14 | 0.6649 | 0.5856 | 0.7344 | -0.0022 | -0.0057 | 0.0000 | 15.7 | 0.0547 | -0.0172 | 0.2177 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2021-07-01 | w5-13 | without_controller | 2268 | 14 | 0.6671 | 0.5870 | 0.7381 | 0.0000 | 0.0000 | 0.0000 | 15.7 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | all | with_controller | 7098 | 14 | 0.6331 | 0.5951 | 0.6751 | 0.0003 | 0.0000 | 0.0008 | 14.3 | 0.1126 | 0.0000 | 0.3498 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | all | without_controller | 7098 | 14 | 0.6329 | 0.5950 | 0.6750 | 0.0000 | 0.0000 | 0.0000 | 14.4 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | w1-4 | with_controller | 2184 | 14 | 0.5870 | 0.5453 | 0.6207 | 0.0009 | 0.0000 | 0.0027 | 8.7897 | 0.1806 | 0.0000 | 0.5502 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | w1-4 | without_controller | 2184 | 14 | 0.5861 | 0.5448 | 0.6207 | 0.0000 | 0.0000 | 0.0000 | 8.8056 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | w5-13 | with_controller | 4914 | 14 | 0.6536 | 0.6107 | 0.7041 | 0.0000 | 0.0000 | 0.0000 | 16.8 | 0.0968 | 0.0000 | 0.3037 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |
| 2022-10-01 | w5-13 | without_controller | 4914 | 14 | 0.6536 | 0.6107 | 0.7041 | 0.0000 | 0.0000 | 0.0000 | 16.8 | 0.0000 | 0.0000 | 0.0000 | False | 300 | False | regime-cash-source-cal-120gap-v1-fullweek |

## DR: 400 công ty mỗi nhánh, kiểm tra sinh dữ liệu

Nguồn: `outputs/data/DR_comparison_build.csv`

Giao thức: DR-400-firms-sharded-v1

| arm | world | n_firms | n_invoices | contracts_passed | validation_scope | measurement_version |
|---|---|---|---|---|---|---|
| one_world | dr_cmp_control_400 | 400 | 2362440 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_000 | 20 | 148619 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_001 | 20 | 74181 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_002 | 20 | 186973 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_003 | 20 | 109310 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_004 | 20 | 94042 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_005 | 20 | 93490 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_006 | 20 | 95628 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_007 | 20 | 76303 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_008 | 20 | 59318 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_009 | 20 | 93341 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_010 | 20 | 63335 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_011 | 20 | 117157 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_012 | 20 | 140288 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_013 | 20 | 128316 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_014 | 20 | 90467 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_015 | 20 | 155003 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_016 | 20 | 84203 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_017 | 20 | 105000 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_018 | 20 | 108690 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |
| twenty_worlds | dr_cmp_multi_019 | 20 | 163059 | True | per firm shard; logical IDs namespaced | DR-400-firms-sharded-v1 |

## DR: một thế giới so hai mươi thế giới, cùng ngân sách

Nguồn: `outputs/t1/DR/metrics.csv`

Giao thức: DR-400-matched-invoices-source-only-v1-fullweek

| setting | model | n | seed | measurement_version | pinball_q10 | pinball_q50 | pinball_q90 | pinball_avg | MAE_p50 | MAE_p50_paid | cov80 | IS80 | IBS_13w | IBS_13w_fair | pinball_ci_low | pinball_ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | baseline_model | cov80_ci_low | cov80_ci_high | Brier_4w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 | vs_one_world_improvement_pct | vs_one_world_improvement_ci_low | vs_one_world_improvement_ci_high | n_source_invoices_per_arm | n_source_firms_per_arm | n_train_per_arm | origin | test_used_for_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tgt | one_world | 52481 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 3.2234 | 9.6786 | 4.7008 | 5.8676 | 19.4 | 18.9 | 0.8553 | 79.2 | 0.1184 | 0.1184 | 5.1419 | 6.3755 | 300 | 14 | 65.9 | 55.6 | 76.3 | B1d-cust-quantiles | 0.8371 | 0.8841 | 0.1297 | 0.0365 | 0.7888 | 0.4107 | 0.5456 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| tgt | twenty_worlds | 52481 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 3.1923 | 9.5062 | 4.6865 | 5.7950 | 19.0 | 17.9 | 0.8538 | 78.8 | 0.1170 | 0.1170 | 5.0558 | 6.2905 | 300 | 14 | 66.3 | 56.2 | 77.0 | B1d-cust-quantiles | 0.8386 | 0.8747 | 0.1276 | 0.0220 | 0.7913 | 0.4052 | 0.5404 | 1.2381 | -0.6917 | 3.3712 | 983862 | 400 | 40000 | 2024-07-01 | False |
| tgt | B1d-cust-quantiles | 52481 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 4.9373 | 21.0 | 25.7 | 17.2 | 42.0 | 20.9 | 0.5649 | 306.8 | 0.3012 | 0.3012 | 14.1 | 22.3 | 300 | 14 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4814 | 0.6199 | 0.3257 | 0.2717 | 0.5146 | 1.2743 | 0.6066 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_uk | one_world | 71011 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 2.6594 | 8.1642 | 5.1667 | 5.3301 | 16.3 | 14.2 | 0.8323 | 78.3 | 0.1104 | 0.1104 | 4.9315 | 5.7491 | 300 | 12 | 64.8 | 56.6 | 71.7 | B1d-cust-quantiles | 0.8103 | 0.8512 | 0.1524 | 0.0275 | 0.7739 | 0.3436 | 0.6482 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_uk | twenty_worlds | 71011 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 2.6564 | 8.0247 | 5.0785 | 5.2532 | 16.0 | 13.6 | 0.8268 | 77.3 | 0.1089 | 0.1089 | 4.8639 | 5.6576 | 300 | 12 | 65.3 | 57.1 | 72.1 | B1d-cust-quantiles | 0.8089 | 0.8449 | 0.1504 | 0.0196 | 0.7786 | 0.3534 | 0.5966 | 1.4422 | -0.5305 | 3.2806 | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_uk | B1d-cust-quantiles | 71011 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 4.1049 | 17.5 | 23.8 | 15.1 | 35.0 | 16.4 | 0.5257 | 278.7 | 0.2635 | 0.2635 | 12.1 | 19.0 | 300 | 12 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4590 | 0.5780 | 0.3110 | 0.2633 | 0.5461 | 1.0474 | 0.6678 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_coface | one_world | 39435 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 3.3635 | 10.6 | 5.2167 | 6.3900 | 21.2 | 18.0 | 0.8533 | 85.8 | 0.1277 | 0.1277 | 5.6982 | 6.9697 | 300 | 12 | 67.8 | 59.4 | 74.6 | B1d-cust-quantiles | 0.8354 | 0.8704 | 0.1433 | 0.0468 | 0.7951 | 0.3782 | 0.9208 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_coface | twenty_worlds | 39435 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 3.3791 | 10.3 | 5.0698 | 6.2501 | 20.6 | 18.2 | 0.8697 | 84.5 | 0.1234 | 0.1234 | 5.4602 | 6.9095 | 300 | 12 | 68.5 | 60.3 | 75.3 | B1d-cust-quantiles | 0.8447 | 0.8942 | 0.1386 | 0.0265 | 0.7966 | 0.3643 | 0.8540 | 2.1893 | 0.0345 | 4.9458 | 983862 | 400 | 40000 | 2024-07-01 | False |
| sens_coface | B1d-cust-quantiles | 39435 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 5.1693 | 24.0 | 30.4 | 19.8 | 47.9 | 20.6 | 0.5369 | 355.5 | 0.3442 | 0.3442 | 15.9 | 23.6 | 300 | 12 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.4788 | 0.5837 | 0.3750 | 0.3158 | 0.4560 | 1.1694 | 0.7873 |  |  |  | 983862 | 400 | 40000 | 2024-07-01 | False |
| real_customer_invoices | one_world | 20185 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 1.1394 | 4.9670 | 4.7469 | 3.6177 | 9.9340 | 9.9340 | 0.8237 | 58.9 | 0.0857 | 0.0857 | 3.5736 | 4.1563 | 300 | 4 | -158.8 | -174.7 | -24.9 | B1d-cust-quantiles | 0.7878 | 0.8630 | 0.1398 | 0.2859 | 0.6143 | 0.4854 | 4.0530 |  |  |  | 110713 | 400 | 40000 | 2019-10-01 | False |
| real_customer_invoices | twenty_worlds | 20185 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 1.0791 | 3.0183 | 3.0193 | 2.3723 | 6.0367 | 6.0367 | 0.8595 | 41.0 | 0.0527 | 0.0527 | 2.3117 | 3.1392 | 300 | 4 | -69.7 | -82.7 | 5.6427 | B1d-cust-quantiles | 0.8321 | 0.8923 | 0.0706 | 0.1346 | 0.6578 | 0.3113 | 1.9651 | 34.4 | 24.3 | 35.3 | 110713 | 400 | 40000 | 2019-10-01 | False |
| real_customer_invoices | B1d-cust-quantiles | 20185 | 7 | DR-400-matched-invoices-source-only-v1-fullweek | 0.8345 | 1.8216 | 1.5381 | 1.3981 | 3.6432 | 3.6432 | 0.8045 | 23.7 | 0.0305 | 0.0305 | 1.3008 | 3.3270 | 300 | 4 | 0.0000 | 0.0000 | 0.0000 | B1d-cust-quantiles | 0.6786 | 0.8115 | 0.0455 | 0.0610 | 0.8316 | 0.1149 | 1.0656 |  |  |  | 110713 | 400 | 40000 | 2019-10-01 | False |

## DR: CI cặp và quyết định

Nguồn: `outputs/t1/DR/decisions.csv`

Giao thức: DR-400-matched-invoices-source-only-v1-fullweek

| target | origin | ci_low | ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | threshold_pct | status | candidate_adopted | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tgt | 2024-07-01 | 5.0558 | 6.2905 | 300 | 14 | 1.2381 | -0.6917 | 3.3712 | 5.0000 | rejected | False | False | DR-400-matched-invoices-source-only-v1-fullweek |
| sens_uk | 2024-07-01 | 4.8639 | 5.6576 | 300 | 12 | 1.4422 | -0.5305 | 3.2806 | 5.0000 | rejected | False | False | DR-400-matched-invoices-source-only-v1-fullweek |
| sens_coface | 2024-07-01 | 5.4602 | 6.9095 | 300 | 12 | 2.1893 | 0.0345 | 4.9458 | 5.0000 | rejected | False | False | DR-400-matched-invoices-source-only-v1-fullweek |
| real_customer_invoices | 2019-10-01 | 2.3117 | 3.1392 | 300 | 4 | 34.4 | 24.3 | 35.3 | 5.0000 | supported | False | False | DR-400-matched-invoices-source-only-v1-fullweek |

## SBA: cohort trước tại ngày phê duyệt, trễ công bố giả định 90 ngày

Nguồn: `outputs/t2_t3/sba_macro_metrics.csv`

Giao thức: sba-prior-cohort-asof-lag90-v1

| exempt_policy | model | stratum | n_test | bootstrap_n | Brier_ci_low | Brier_ci_high | ROC_AUC | PR_AUC | Brier | logloss | ECE | mean_p | base_rate | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop | without_prior_cohort | all | 130559 | 300 | 0.0222 | 0.0235 | 0.9260 | 0.1657 | 0.0229 | 0.0902 | 0.0180 | 0.0164 | 0.0232 | sba-prior-cohort-asof-lag90-v1 |
| drop | without_prior_cohort | term<=120 | 105084 | 300 | 0.0273 | 0.0291 | 0.9108 | 0.1665 | 0.0282 | 0.1107 | 0.0222 | 0.0203 | 0.0287 | sba-prior-cohort-asof-lag90-v1 |
| drop | without_prior_cohort | term>120 | 25475 | 300 | 0.0004 | 0.0011 | 0.8630 | 0.0091 | 0.0007 | 0.0055 | 0.0004 | 0.0003 | 0.0007 | sba-prior-cohort-asof-lag90-v1 |
| drop | with_prior_cohort | all | 130559 | 300 | 0.0223 | 0.0236 | 0.9251 | 0.1624 | 0.0230 | 0.0910 | 0.0188 | 0.0161 | 0.0232 | sba-prior-cohort-asof-lag90-v1 |
| drop | with_prior_cohort | term<=120 | 105084 | 300 | 0.0274 | 0.0292 | 0.9099 | 0.1632 | 0.0284 | 0.1116 | 0.0232 | 0.0199 | 0.0287 | sba-prior-cohort-asof-lag90-v1 |
| drop | with_prior_cohort | term>120 | 25475 | 300 | 0.0004 | 0.0011 | 0.8181 | 0.0133 | 0.0007 | 0.0060 | 0.0005 | 0.0002 | 0.0007 | sba-prior-cohort-asof-lag90-v1 |
| keep | without_prior_cohort | all | 223259 | 300 | 0.0132 | 0.0140 | 0.9444 | 0.1416 | 0.0136 | 0.0545 | 0.0100 | 0.0109 | 0.0136 | sba-prior-cohort-asof-lag90-v1 |
| keep | without_prior_cohort | term<=120 | 166591 | 300 | 0.0176 | 0.0188 | 0.9290 | 0.1428 | 0.0182 | 0.0721 | 0.0134 | 0.0145 | 0.0181 | sba-prior-cohort-asof-lag90-v1 |
| keep | without_prior_cohort | term>120 | 56668 | 300 | 0.0002 | 0.0005 | 0.8826 | 0.0048 | 0.0003 | 0.0026 | 0.0000 | 0.0003 | 0.0003 | sba-prior-cohort-asof-lag90-v1 |
| keep | with_prior_cohort | all | 223259 | 300 | 0.0134 | 0.0143 | 0.9443 | 0.1387 | 0.0139 | 0.0550 | 0.0107 | 0.0114 | 0.0136 | sba-prior-cohort-asof-lag90-v1 |
| keep | with_prior_cohort | term<=120 | 166591 | 300 | 0.0179 | 0.0191 | 0.9290 | 0.1394 | 0.0185 | 0.0727 | 0.0142 | 0.0152 | 0.0181 | sba-prior-cohort-asof-lag90-v1 |
| keep | with_prior_cohort | term>120 | 56668 | 300 | 0.0002 | 0.0005 | 0.7842 | 0.0033 | 0.0003 | 0.0030 | 0.0001 | 0.0002 | 0.0003 | sba-prior-cohort-asof-lag90-v1 |
| censor | without_prior_cohort | all | 130559 | 300 | 0.0222 | 0.0235 | 0.9260 | 0.1657 | 0.0229 | 0.0902 | 0.0180 | 0.0164 | 0.0232 | sba-prior-cohort-asof-lag90-v1 |
| censor | without_prior_cohort | term<=120 | 105084 | 300 | 0.0273 | 0.0291 | 0.9108 | 0.1665 | 0.0282 | 0.1107 | 0.0222 | 0.0203 | 0.0287 | sba-prior-cohort-asof-lag90-v1 |
| censor | without_prior_cohort | term>120 | 25475 | 300 | 0.0004 | 0.0011 | 0.8630 | 0.0091 | 0.0007 | 0.0055 | 0.0004 | 0.0003 | 0.0007 | sba-prior-cohort-asof-lag90-v1 |
| censor | with_prior_cohort | all | 130559 | 300 | 0.0223 | 0.0236 | 0.9251 | 0.1624 | 0.0230 | 0.0910 | 0.0188 | 0.0161 | 0.0232 | sba-prior-cohort-asof-lag90-v1 |
| censor | with_prior_cohort | term<=120 | 105084 | 300 | 0.0274 | 0.0292 | 0.9099 | 0.1632 | 0.0284 | 0.1116 | 0.0232 | 0.0199 | 0.0287 | sba-prior-cohort-asof-lag90-v1 |
| censor | with_prior_cohort | term>120 | 25475 | 300 | 0.0004 | 0.0011 | 0.8181 | 0.0133 | 0.0007 | 0.0060 | 0.0005 | 0.0002 | 0.0007 | sba-prior-cohort-asof-lag90-v1 |

## SBA: CI Brier cặp cho đặc trưng chu kỳ

Nguồn: `outputs/t2_t3/sba_macro_comparisons.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| exempt_policy | metric | ci_low | ci_high | bootstrap_n | n_firms | improvement_pct | improvement_ci_low | improvement_ci_high | decision | test_used_for_selection |
|---|---|---|---|---|---|---|---|---|---|---|
| drop | Brier | 0.0223 | 0.0236 | 300 | 120558 | -0.5451 | -0.9850 | -0.1942 | rejected | False |
| keep | Brier | 0.0134 | 0.0143 | 300 | 204357 | -1.7380 | -2.1682 | -1.2704 | rejected | False |
| censor | Brier | 0.0223 | 0.0236 | 300 | 120558 | -0.5451 | -0.9850 | -0.1942 | rejected | False |

## SBA: hiệu chỉnh theo FY với/không cohort trước

Nguồn: `outputs/t2_t3/sba_macro_by_fy.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| fy | base_rate | mean_p | n | relative_calibration_error | model | exempt_policy |
|---|---|---|---|---|---|---|
| 2018 | 0.0214 | 0.0193 | 42237 | 0.1000 | without_prior_cohort | drop |
| 2019 | 0.0221 | 0.0216 | 31606 | 0.0243 | without_prior_cohort | drop |
| 2020 | 0.0132 | 0.0136 | 22892 | 0.0296 | without_prior_cohort | drop |
| 2021 | 0.0158 | 0.0078 | 20938 | 0.5093 | without_prior_cohort | drop |
| 2022 | 0.0618 | 0.0130 | 12886 | 0.7892 | without_prior_cohort | drop |
| 2018 | 0.0214 | 0.0190 | 42237 | 0.1116 | with_prior_cohort | drop |
| 2019 | 0.0221 | 0.0215 | 31606 | 0.0280 | with_prior_cohort | drop |
| 2020 | 0.0132 | 0.0132 | 22892 | 0.0029 | with_prior_cohort | drop |
| 2021 | 0.0158 | 0.0072 | 20938 | 0.5430 | with_prior_cohort | drop |
| 2022 | 0.0618 | 0.0125 | 12886 | 0.7977 | with_prior_cohort | drop |
| 2018 | 0.0167 | 0.0154 | 54195 | 0.0777 | without_prior_cohort | keep |
| 2019 | 0.0153 | 0.0166 | 45671 | 0.0846 | without_prior_cohort | keep |
| 2020 | 0.0083 | 0.0095 | 36464 | 0.1511 | without_prior_cohort | keep |
| 2021 | 0.0073 | 0.0048 | 45165 | 0.3469 | without_prior_cohort | keep |
| 2022 | 0.0191 | 0.0065 | 41764 | 0.6570 | without_prior_cohort | keep |
| 2018 | 0.0167 | 0.0159 | 54195 | 0.0484 | with_prior_cohort | keep |
| 2019 | 0.0153 | 0.0181 | 45671 | 0.1856 | with_prior_cohort | keep |
| 2020 | 0.0083 | 0.0098 | 36464 | 0.1795 | with_prior_cohort | keep |
| 2021 | 0.0073 | 0.0049 | 45165 | 0.3366 | with_prior_cohort | keep |
| 2022 | 0.0191 | 0.0066 | 41764 | 0.6549 | with_prior_cohort | keep |
| 2018 | 0.0214 | 0.0193 | 42237 | 0.1000 | without_prior_cohort | censor |
| 2019 | 0.0221 | 0.0216 | 31606 | 0.0243 | without_prior_cohort | censor |
| 2020 | 0.0132 | 0.0136 | 22892 | 0.0296 | without_prior_cohort | censor |
| 2021 | 0.0158 | 0.0078 | 20938 | 0.5093 | without_prior_cohort | censor |
| 2022 | 0.0618 | 0.0130 | 12886 | 0.7892 | without_prior_cohort | censor |
| 2018 | 0.0214 | 0.0190 | 42237 | 0.1116 | with_prior_cohort | censor |
| 2019 | 0.0221 | 0.0215 | 31606 | 0.0280 | with_prior_cohort | censor |
| 2020 | 0.0132 | 0.0132 | 22892 | 0.0029 | with_prior_cohort | censor |
| 2021 | 0.0158 | 0.0072 | 20938 | 0.5430 | with_prior_cohort | censor |
| 2022 | 0.0618 | 0.0125 | 12886 | 0.7977 | with_prior_cohort | censor |

## T5: tình huống hợp đồng/hồ sơ mở rộng, chưa xác minh luật

Nguồn: `outputs/rules/extended_obligation_cases.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| case | actual | expected | passed | evidence_type | expert_verified |
|---|---|---|---|---|---|
| pit_withholding_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| foreign_contractor_tax_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| salary_bonus_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| rent_contract_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| loan_interest_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| loan_principal_declared_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| refund_approval_None | 0.0000 | 0.0000 | True | configured_contract_arithmetic_not_legal_validation | False |
| refund_approval_2025-03-01 | 0.0000 | 0.0000 | True | configured_contract_arithmetic_not_legal_validation | False |
| refund_approval_2025-01-15 | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| rent_feb_amount | 100.0 | 100.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| rent_feb_day | 28.0 | 28.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| rent_mar_amount | 150.0 | 150.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| rent_mar_day | 31.0 | 31.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| loan_principal_separate | 1000.0 | 1000.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| loan_interest_separate | 70.0 | 70.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| week1_refund_inflow | 300.0 | 300.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| week1_principal_plus_interest_outflow | 1070.0 | 1070.0 | True | configured_contract_arithmetic_not_legal_validation | False |
| future_agreement_excluded | 0.0000 | 0.0000 | True | configured_contract_arithmetic_not_legal_validation | False |

## T5: 54 tình huống nghiệp vụ theo cấu hình lịch sử

Nguồn: `outputs/rules/business_cases.csv`

Giao thức: configured-rules-business-regression-v1

| case | rule | operation | expected | arguments | actual | passed | expert_verified | measurement_version |
|---|---|---|---|---|---|---|---|---|
| minimum_wage@2019-01-01:1 | minimum_wage@2019-01-01 | wage | 4180000 | ["2019-01-01", 1] | 4180000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2019-01-01:2 | minimum_wage@2019-01-01 | wage | 2920000 | ["2019-01-01", 4] | 2920000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2020-01-01:3 | minimum_wage@2020-01-01 | wage | 4420000 | ["2020-01-01", 1] | 4420000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2020-01-01:4 | minimum_wage@2020-01-01 | wage | 3070000 | ["2020-01-01", 4] | 3070000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2022-07-01:5 | minimum_wage@2022-07-01 | wage | 4680000 | ["2022-07-01", 1] | 4680000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2022-07-01:6 | minimum_wage@2022-07-01 | wage | 3250000 | ["2022-07-01", 4] | 3250000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2024-07-01:7 | minimum_wage@2024-07-01 | wage | 4960000 | ["2024-07-01", 1] | 4960000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2024-07-01:8 | minimum_wage@2024-07-01 | wage | 3450000 | ["2024-07-01", 4] | 3450000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2026-01-01:9 | minimum_wage@2026-01-01 | wage | 5310000 | ["2026-01-01", 1] | 5310000 | True | False | configured-rules-business-regression-v1 |
| minimum_wage@2026-01-01:10 | minimum_wage@2026-01-01 | wage | 3700000 | ["2026-01-01", 4] | 3700000 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2022-02-01:11 | vat_reduction@2022-02-01 | vat | 0.1 | ["2022-01-31", "textile_clothing"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2022-02-01:12 | vat_reduction@2022-02-01 | vat | 0.08 | ["2022-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2023-07-01:13 | vat_reduction@2023-07-01 | vat | 0.1 | ["2023-06-30", "textile_clothing"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2023-07-01:14 | vat_reduction@2023-07-01 | vat | 0.08 | ["2023-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2024-01-01:15 | vat_reduction@2024-01-01 | vat | 0.08 | ["2023-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2024-01-01:16 | vat_reduction@2024-01-01 | vat | 0.08 | ["2024-06-30", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2024-07-01:17 | vat_reduction@2024-07-01 | vat | 0.08 | ["2024-06-30", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2024-07-01:18 | vat_reduction@2024-07-01 | vat | 0.08 | ["2024-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2025-01-01:19 | vat_reduction@2025-01-01 | vat | 0.08 | ["2024-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2025-01-01:20 | vat_reduction@2025-01-01 | vat | 0.08 | ["2025-06-30", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2025-07-01:21 | vat_reduction@2025-07-01 | vat | 0.08 | ["2025-06-30", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_reduction@2025-07-01:22 | vat_reduction@2025-07-01 | vat | 0.08 | ["2026-12-31", "textile_clothing"] | 0.08 | True | False | configured-rules-business-regression-v1 |
| vat_base@2018-01-01:23 | vat_base@2018-01-01 | vat | 0.1 | ["2021-06-01", "textile_clothing"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| vat_base@2018-01-01:24 | vat_base@2018-01-01 | vat | 0.1 | ["2023-04-01", "textile_clothing"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| vat_excluded_industries@2018-01-01:25 | vat_excluded_industries@2018-01-01 | vat | 0.1 | ["2022-06-01", "steel_metals"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| vat_excluded_industries@2018-01-01:26 | vat_excluded_industries@2018-01-01 | vat | 0.1 | ["2025-06-01", "steel_metals"] | 0.1 | True | False | configured-rules-business-regression-v1 |
| social_insurance_employer@2018-01-01:27 | social_insurance_employer@2018-01-01 | employer | 21500000 | [100000000] | 21500000.0 | True | False | configured-rules-business-regression-v1 |
| social_insurance_employee@2018-01-01:28 | social_insurance_employee@2018-01-01 | net_payroll | 89500000 | [100000000] | 89500000.0 | True | False | configured-rules-business-regression-v1 |
| social_insurance_employer@2018-01-01:29 | social_insurance_employer@2018-01-01 | employer | 43000000 | [200000000] | 43000000.0 | True | False | configured-rules-business-regression-v1 |
| social_insurance_employee@2018-01-01:30 | social_insurance_employee@2018-01-01 | net_payroll | 179000000 | [200000000] | 179000000.0 | True | False | configured-rules-business-regression-v1 |
| monthly_vat_threshold@2018-01-01:31 | monthly_vat_threshold@2018-01-01 | vat_count | 0 | [50000000000] | 0 | True | False | configured-rules-business-regression-v1 |
| monthly_vat_threshold@2018-01-01:32 | monthly_vat_threshold@2018-01-01 | vat_count | 1 | [50000000001] | 1 | True | False | configured-rules-business-regression-v1 |
| vat_monthly_day@2018-01-01:33 | vat_monthly_day@2018-01-01 | vat_due | 2024-04-22 | ["2024-03-31"] | 2024-04-22 | True | False | configured-rules-business-regression-v1 |
| vat_monthly_day@2018-01-01:34 | vat_monthly_day@2018-01-01 | vat_due | 2025-02-20 | ["2025-01-31"] | 2025-02-20 | True | False | configured-rules-business-regression-v1 |
| cit_provisional_day@2018-01-01:35 | cit_provisional_day@2018-01-01 | cit_due | 2024-05-02 | ["2024-03-31"] | 2024-05-02 | True | False | configured-rules-business-regression-v1 |
| cit_provisional_day@2018-01-01:36 | cit_provisional_day@2018-01-01 | cit_due | 2024-07-30 | ["2024-06-30"] | 2024-07-30 | True | False | configured-rules-business-regression-v1 |
| cit_final_month@2018-01-01:37 | cit_final_month@2018-01-01 | cit_final | 2024-04-01 | [2023] | 2024-04-01 | True | False | configured-rules-business-regression-v1 |
| cit_final_month@2018-01-01:38 | cit_final_month@2018-01-01 | cit_final | 2025-03-31 | [2024] | 2025-03-31 | True | False | configured-rules-business-regression-v1 |
| license_fee_day@2018-01-01:39 | license_fee_day@2018-01-01 | license_due | 2023-01-30 | [2023] | 2023-01-30 | True | False | configured-rules-business-regression-v1 |
| license_fee_day@2018-01-01:40 | license_fee_day@2018-01-01 | license_due | 2024-01-30 | [2024] | 2024-01-30 | True | False | configured-rules-business-regression-v1 |
| license_fee_capital_threshold@2018-01-01:41 | license_fee_capital_threshold@2018-01-01 | license_amount | 2000000 | [2025, 10000000000] | 2000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_capital_threshold@2018-01-01:42 | license_fee_capital_threshold@2018-01-01 | license_amount | 3000000 | [2025, 10000000001] | 3000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_low@2018-01-01:43 | license_fee_low@2018-01-01 | license_amount | 2000000 | [2025, 0] | 2000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_low@2018-01-01:44 | license_fee_low@2018-01-01 | license_amount | 2000000 | [2025, 9000000000] | 2000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_high@2018-01-01:45 | license_fee_high@2018-01-01 | license_amount | 3000000 | [2025, 11000000000] | 3000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_high@2018-01-01:46 | license_fee_high@2018-01-01 | license_amount | 3000000 | [2025, 20000000000] | 3000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_abolished@2018-01-01:47 | license_fee_abolished@2018-01-01 | license_amount | 2000000 | [2025, 1000000000] | 2000000.0 | True | False | configured-rules-business-regression-v1 |
| license_fee_abolished@2018-01-01:48 | license_fee_abolished@2018-01-01 | license_amount | 0 | [2026, 1000000000] | 0.0 | True | False | configured-rules-business-regression-v1 |
| lunar_new_year@2018-01-01:49 | lunar_new_year@2018-01-01 | tet_days | 1 | ["2024-02-09"] | 1 | True | False | configured-rules-business-regression-v1 |
| lunar_new_year@2018-01-01:50 | lunar_new_year@2018-01-01 | tet_days | -1 | ["2025-01-30"] | -1 | True | False | configured-rules-business-regression-v1 |
| tet_break@2018-01-01:51 | tet_break@2018-01-01 | tet_break | True | ["2024-02-08"] | True | True | False | configured-rules-business-regression-v1 |
| tet_break@2018-01-01:52 | tet_break@2018-01-01 | tet_break | False | ["2024-02-15"] | False | True | False | configured-rules-business-regression-v1 |
| provisioning_months@2018-01-01:53 | provisioning_months@2018-01-01 | provision | 0 | [5] | 0.0 | True | False | configured-rules-business-regression-v1 |
| provisioning_months@2018-01-01:54 | provisioning_months@2018-01-01 | provision | 30000000 | [6] | 30000000.0 | True | False | configured-rules-business-regression-v1 |

## T5: độ phủ phiên bản quy tắc trong bộ hồi quy

Nguồn: `outputs/rules/business_case_coverage.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| rule | n_cases |
|---|---|
| cit_final_month@2018-01-01 | 2 |
| cit_provisional_day@2018-01-01 | 2 |
| license_fee_abolished@2018-01-01 | 2 |
| license_fee_capital_threshold@2018-01-01 | 2 |
| license_fee_day@2018-01-01 | 2 |
| license_fee_high@2018-01-01 | 2 |
| license_fee_low@2018-01-01 | 2 |
| lunar_new_year@2018-01-01 | 2 |
| minimum_wage@2019-01-01 | 2 |
| minimum_wage@2020-01-01 | 2 |
| minimum_wage@2022-07-01 | 2 |
| minimum_wage@2024-07-01 | 2 |
| minimum_wage@2026-01-01 | 2 |
| monthly_vat_threshold@2018-01-01 | 2 |
| provisioning_months@2018-01-01 | 2 |
| social_insurance_employee@2018-01-01 | 2 |
| social_insurance_employer@2018-01-01 | 2 |
| tet_break@2018-01-01 | 2 |
| vat_base@2018-01-01 | 2 |
| vat_excluded_industries@2018-01-01 | 2 |
| vat_monthly_day@2018-01-01 | 2 |
| vat_reduction@2022-02-01 | 2 |
| vat_reduction@2023-07-01 | 2 |
| vat_reduction@2024-01-01 | 2 |
| vat_reduction@2024-07-01 | 2 |
| vat_reduction@2025-01-01 | 2 |
| vat_reduction@2025-07-01 | 2 |

## T9: trước/trong/sau sốc cung ứng 2022, nguồn chốt trước 2022

Nguồn: `outputs/t9/supply_shock_2022/metrics.csv`

Giao thức: T9-supply-shock-pre2022-source-v1

| method | window | stratum | link_precision | link_precision_ci_low | link_precision_ci_high | link_recall | link_f1 | link_f1_ci_low | link_f1_ci_high | auto_txn_coverage | pay_date_MAE_est_days | n_firms | bootstrap_n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 unique amount | before | all | 0.9878 | 0.9796 | 0.9976 | 0.6766 | 0.8031 | 0.7575 | 0.8917 | 0.6754 | 0.1519 | 12 | 300 |
| R1 unique amount | before | steel_shock | 1.0000 | 1.0000 | 1.0000 | 0.8014 | 0.8898 | 0.8166 | 0.9542 | 0.7303 | 0.0000 | 3 | 300 |
| R1 unique amount | before | other_industries | 0.9866 | 0.9778 | 0.9956 | 0.6662 | 0.7953 | 0.7408 | 0.8734 | 0.6704 | 0.1671 | 9 | 300 |
| R1 unique amount | shock | all | 0.9734 | 0.9587 | 0.9910 | 0.6159 | 0.7544 | 0.7014 | 0.8392 | 0.6086 | 0.0479 | 12 | 300 |
| R1 unique amount | shock | steel_shock | 0.9898 | 0.9688 | 1.0000 | 0.7578 | 0.8584 | 0.7949 | 0.8992 | 0.6806 | 0.0000 | 3 | 300 |
| R1 unique amount | shock | other_industries | 0.9715 | 0.9558 | 0.9902 | 0.6025 | 0.7437 | 0.6818 | 0.8269 | 0.6011 | 0.0536 | 9 | 300 |
| R1 unique amount | after | all | 0.9660 | 0.9489 | 0.9903 | 0.5252 | 0.6805 | 0.6131 | 0.7828 | 0.5437 | 0.5653 | 12 | 300 |
| R1 unique amount | after | steel_shock | 0.9940 | 0.9615 | 1.0000 | 0.6707 | 0.8010 | 0.6618 | 0.9065 | 0.6245 | 0.0000 | 3 | 300 |
| R1 unique amount | after | other_industries | 0.9630 | 0.9464 | 0.9839 | 0.5129 | 0.6693 | 0.6052 | 0.7658 | 0.5363 | 0.6266 | 9 | 300 |
| R2 memo | before | all | 1.0000 | 1.0000 | 1.0000 | 0.3758 | 0.5463 | 0.5024 | 0.5993 | 0.3524 | 0.0000 | 12 | 300 |
| R2 memo | before | steel_shock | 1.0000 | 1.0000 | 1.0000 | 0.3899 | 0.5610 | 0.3673 | 0.6436 | 0.3487 | 0.0000 | 3 | 300 |
| R2 memo | before | other_industries | 1.0000 | 1.0000 | 1.0000 | 0.3747 | 0.5451 | 0.5025 | 0.5933 | 0.3527 | 0.0000 | 9 | 300 |
| R2 memo | shock | all | 1.0000 | 1.0000 | 1.0000 | 0.3450 | 0.5130 | 0.4564 | 0.5663 | 0.3150 | 0.0000 | 12 | 300 |
| R2 memo | shock | steel_shock | 1.0000 | 1.0000 | 1.0000 | 0.3203 | 0.4852 | 0.3077 | 0.5510 | 0.2847 | 0.0000 | 3 | 300 |
| R2 memo | shock | other_industries | 1.0000 | 1.0000 | 1.0000 | 0.3473 | 0.5156 | 0.4543 | 0.5810 | 0.3181 | 0.0000 | 9 | 300 |
| R2 memo | after | all | 1.0000 | 1.0000 | 1.0000 | 0.2684 | 0.4232 | 0.3532 | 0.4719 | 0.2537 | 0.0000 | 12 | 300 |
| R2 memo | after | steel_shock | 1.0000 | 1.0000 | 1.0000 | 0.2892 | 0.4486 | 0.4174 | 0.4815 | 0.2602 | 0.0000 | 3 | 300 |
| R2 memo | after | other_industries | 1.0000 | 1.0000 | 1.0000 | 0.2666 | 0.4210 | 0.3422 | 0.4733 | 0.2531 | 0.0000 | 9 | 300 |
| Hybrid frozen pre2022 tau=.9 | before | all | 0.9841 | 0.9747 | 0.9978 | 0.7966 | 0.8805 | 0.8553 | 0.9278 | 0.7486 | 0.1962 | 12 | 300 |
| Hybrid frozen pre2022 tau=.9 | before | steel_shock | 1.0000 | 1.0000 | 1.0000 | 0.8556 | 0.9222 | 0.8764 | 0.9542 | 0.7566 | 0.0000 | 3 | 300 |
| Hybrid frozen pre2022 tau=.9 | before | other_industries | 0.9827 | 0.9725 | 0.9949 | 0.7917 | 0.8769 | 0.8473 | 0.9222 | 0.7478 | 0.2138 | 9 | 300 |
| Hybrid frozen pre2022 tau=.9 | shock | all | 0.9606 | 0.9465 | 0.9863 | 0.7069 | 0.8144 | 0.7787 | 0.8739 | 0.6688 | 0.0863 | 12 | 300 |
| Hybrid frozen pre2022 tau=.9 | shock | steel_shock | 0.9903 | 0.9688 | 1.0000 | 0.7969 | 0.8831 | 0.7949 | 0.9403 | 0.7083 | 0.0000 | 3 | 300 |
| Hybrid frozen pre2022 tau=.9 | shock | other_industries | 0.9575 | 0.9416 | 0.9802 | 0.6984 | 0.8077 | 0.7713 | 0.8630 | 0.6648 | 0.0956 | 9 | 300 |
| Hybrid frozen pre2022 tau=.9 | after | all | 0.9527 | 0.9339 | 0.9808 | 0.6245 | 0.7544 | 0.7077 | 0.8211 | 0.6051 | 0.8585 | 12 | 300 |
| Hybrid frozen pre2022 tau=.9 | after | steel_shock | 0.9944 | 0.9667 | 1.0000 | 0.7149 | 0.8318 | 0.7273 | 0.9065 | 0.6468 | 0.0000 | 3 | 300 |
| Hybrid frozen pre2022 tau=.9 | after | other_industries | 0.9488 | 0.9289 | 0.9735 | 0.6168 | 0.7476 | 0.7033 | 0.8083 | 0.6012 | 0.9402 | 9 | 300 |

## BCTC niêm yết: DSO/DPO mô tả, ba DN-kỳ, chưa đại diện ngành

Nguồn: `outputs/data/vn_listed_accounting.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| issuer | industry | year | report | source_url | opening_short_trade_receivables | closing_short_trade_receivables | opening_short_trade_payables | closing_short_trade_payables | net_revenue | cost_of_sales | pdf_pages_balance | pdf_page_income | report_printed_pages | unit | transcription | audit_note | expert_verified | DSO_proxy | DPO_COGS_proxy | days_basis | pdf_sha256 | n_issuers_in_sector | used_for_generator_calibration |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SMC | steel_metals | 2024 | vn_listed/SMC_FY2024_consolidated_EN.pdf | https://smc.vn/wp-content/uploads/2025/05/BCTC-HOP-NHAT-SAU-KIEM-TOAN-2024-ENG.pdf | 1999235012077 | 1773566850606 | 2009778690862 | 1420521537782 | 8929794811796 | 8924084713782 | 7;9 | 11 | 5;7;9 | VND | Read from rendered original PDF pages; no independent second reviewer | Auditor emphasis on Novaland receivables and material going-concern uncertainty, PDF page 6 | False | 77.1 | 70.2 | 365 | 3889917644e61e9f03a93e66065f5063668de979dba90618b8029a040b80c399 | 1 | False |
| TCM | textile_clothing | 2022 | vn_listed/TCM_FY2022_consolidated.pdf | https://www.thanhcong.com.vn/wp-content/uploads/2023/03/20230324-TCM-BCTC-hop-nhat-nam-2022-da-kiem-toan_VN.pdf | 373421248475 | 345356640265 | 553869214628 | 176425047928 | 4337389009868 | 3627138944601 | 7;9 | 10 | 5;7;8 | VND | Read from rendered original PDF pages; no independent second reviewer | Unmodified opinion read on PDF page 6; FY2024 annual report has audit opinion but not full statements | False | 30.2 | 36.7 | 365 | 70215fd325b31978bcfdb2a747a3458b607b8a9f7214dcef0f6315d9eb2d6dca | 1 | False |
| NTP | plastic_rubber | 2024 | vn_listed/NTP_FY2024_annual_report.pdf | https://admin.nhuatienphong.vn/img/posts/1_f2284364f5cd0dd5e057ecb4e3e165f0BCTN%202024.pdf | 869315928192 | 388318659135 | 313255093379 | 313880517607 | 5656563814495 | 3886614549588 | 59;60 | 60 | 117;118;119 | VND | Read from rendered original PDF pages; no independent second reviewer | Unmodified KPMG opinion read on PDF page 59, printed page 116, dated 2025-03-25 | False | 40.6 | 29.4 | 365 | 8c7868b31a6f4fa3dd2f9d81c6fd38bcf98cfede329d0d2baf12362cf4487a99 | 1 | False |

## DSO máy phát so từng DN công khai, không dùng để hiệu chỉnh

Nguồn: `outputs/data/vn_listed_DSO_comparison.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| issuer | year | industry | world | n_synthetic_firms | issuer_DSO_proxy | synthetic_DSO_median | synthetic_DSO_p10 | synthetic_DSO_p90 | calibration_used | decision |
|---|---|---|---|---|---|---|---|---|---|---|
| SMC | 2024 | steel_metals | src | 10 | 77.1 | 38.1 | 24.5 | 56.6 | False | descriptive_only_no_sector_CI |
| SMC | 2024 | steel_metals | tgt | 4 | 77.1 | 49.6 | 27.9 | 64.3 | False | descriptive_only_no_sector_CI |
| TCM | 2022 | textile_clothing | src | 7 | 30.2 | 41.0 | 28.6 | 55.7 | False | descriptive_only_no_sector_CI |
| TCM | 2022 | textile_clothing | tgt | 4 | 30.2 | 29.1 | 19.9 | 39.6 | False | descriptive_only_no_sector_CI |
| NTP | 2024 | plastic_rubber | src | 8 | 40.6 | 52.6 | 39.5 | 82.1 | False | descriptive_only_no_sector_CI |
| NTP | 2024 | plastic_rubber | tgt | 4 | 40.6 | 54.9 | 48.0 | 89.2 | False | descriptive_only_no_sector_CI |

## Copula phân tầng: lưới IS trên nguồn

Nguồn: `outputs/t6/copula_hierarchy/source_grid.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| rho | rho_customer | IS80 | n |
|---|---|---|---|
| 0.0000 | 0.0000 | 14.2 | 676 |
| 0.0000 | 0.1000 | 13.9 | 676 |
| 0.0000 | 0.2500 | 13.7 | 676 |
| 0.1500 | 0.0000 | 12.4 | 676 |
| 0.1500 | 0.1000 | 12.3 | 676 |
| 0.1500 | 0.2500 | 12.2 | 676 |
| 0.3000 | 0.0000 | 11.9 | 676 |
| 0.3000 | 0.1000 | 11.8 | 676 |
| 0.3000 | 0.2500 | 11.8 | 676 |

## Copula phân tầng so một nhân tố: CI cặp trên đích

Nguồn: `outputs/t6/copula_hierarchy/metrics.csv`

Giao thức: copula-source-grid-full-cohort-v2-fullweek

| horizon | model | n | n_firms | IS80 | vs_one_factor_improvement_pct | vs_one_factor_improvement_ci_low | vs_one_factor_improvement_ci_high | cov80 | cov80_ci_low | cov80_ci_high | bootstrap_n | target_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | fixed_one_factor | 9464 | 14 | 15.9 | -3.0840 | -4.8741 | -1.1242 | 0.5355 | 0.4577 | 0.6055 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| all | source_selected_hierarchical | 9464 | 14 | 15.3 | 1.0678 | 0.1393 | 1.9899 | 0.5758 | 0.4982 | 0.6448 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| all | source_selected_one_factor | 9464 | 14 | 15.4 | 0.0000 | 0.0000 | 0.0000 | 0.5672 | 0.4883 | 0.6384 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w1-4 | fixed_one_factor | 2912 | 14 | 11.1 | -4.5256 | -5.9191 | -3.0124 | 0.4427 | 0.3686 | 0.5157 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w1-4 | source_selected_hierarchical | 2912 | 14 | 10.5 | 1.2915 | 0.3067 | 2.9362 | 0.5021 | 0.4153 | 0.5742 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w1-4 | source_selected_one_factor | 2912 | 14 | 10.7 | 0.0000 | 0.0000 | 0.0000 | 0.4911 | 0.4083 | 0.5638 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w5-13 | fixed_one_factor | 6552 | 14 | 18.0 | -2.6951 | -4.7822 | -0.5267 | 0.5768 | 0.4926 | 0.6533 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w5-13 | source_selected_hierarchical | 6552 | 14 | 17.4 | 1.0074 | 0.0975 | 1.8681 | 0.6085 | 0.5230 | 0.6817 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |
| w5-13 | source_selected_one_factor | 6552 | 14 | 17.6 | 0.0000 | 0.0000 | 0.0000 | 0.6010 | 0.5172 | 0.6753 | 300 | False | copula-source-grid-full-cohort-v2-fullweek |

## IW: dự đoán bộ phân loại miền ngoài nguyên công ty

Nguồn: `outputs/t1/IW_oof/weight_diagnostics.csv`

Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.

| world | method | n_source | n_target | weight_min | weight_max | weight_std | effective_sample_size | oof_domain_AUC |
|---|---|---|---|---|---|---|---|---|
| tgt | in-sample | 40000 | 15864 | 1.0000 | 1.0000 | 0.0000 | 40000.0 |  |
| tgt | company-OOF | 40000 | 15864 | 0.5189 | 20.0 | 0.3701 | 29602.3 | 1.0000 |
| sens_uk | in-sample | 40000 | 18902 | 1.0000 | 1.9829 | 0.0050 | 39999.0 |  |
| sens_uk | company-OOF | 40000 | 18902 | 0.1494 | 20.0 | 1.2601 | 1666.2 | 0.9771 |
| sens_coface | in-sample | 40000 | 9992 | 0.9997 | 3.6348 | 0.0205 | 39983.2 |  |
| sens_coface | company-OOF | 40000 | 9992 | 0.4023 | 20.0 | 0.4304 | 21209.5 | 0.9929 |

## IW ngoài công ty: cùng cohort/ngân sách M6

Nguồn: `outputs/t1/IW_oof/metrics.csv`

Giao thức: IW-company-OOF-M6-locked-budget-v1-fullweek

| world | model | n_test | n_source | n_target | pinball_avg | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|
| tgt | pooled | 39304 | 40000 | 15864 | 6.3218 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| tgt | IW-in-sample | 39304 | 40000 | 15864 | 6.3218 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| tgt | IW-company-OOF | 39304 | 40000 | 15864 | 6.4433 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_uk | pooled | 60967 | 40000 | 18902 | 5.2709 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_uk | IW-in-sample | 60967 | 40000 | 18902 | 5.2934 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_uk | IW-company-OOF | 60967 | 40000 | 18902 | 5.4062 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_coface | pooled | 29159 | 40000 | 9992 | 6.4203 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_coface | IW-in-sample | 29159 | 40000 | 9992 | 6.3963 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_coface | IW-company-OOF | 29159 | 40000 | 9992 | 6.4344 | False | IW-company-OOF-M6-locked-budget-v1-fullweek |

## IW ngoài công ty so pooled/in-sample: CI cặp

Nguồn: `outputs/t1/IW_oof/comparisons.csv`

Giao thức: IW-company-OOF-M6-locked-budget-v1-fullweek

| world | model | baseline | improvement_pct | improvement_ci_low | improvement_ci_high | n_firms | bootstrap_n | status | test_used_for_selection | measurement_version |
|---|---|---|---|---|---|---|---|---|---|---|
| tgt | IW-company-OOF | pooled | -1.9210 | -2.9444 | 0.1010 | 14 | 300 | not_demonstrated | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| tgt | IW-company-OOF | IW-in-sample | -1.9210 | -2.9444 | 0.1010 | 14 | 300 | not_demonstrated | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_uk | IW-company-OOF | pooled | -2.5676 | -4.0763 | -1.0898 | 12 | 300 | rejected | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_uk | IW-company-OOF | IW-in-sample | -2.1306 | -3.3600 | -0.8508 | 12 | 300 | rejected | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_coface | IW-company-OOF | pooled | -0.2197 | -1.0493 | 0.7987 | 12 | 300 | not_demonstrated | False | IW-company-OOF-M6-locked-budget-v1-fullweek |
| sens_coface | IW-company-OOF | IW-in-sample | -0.5959 | -1.8975 | 0.6885 | 12 | 300 | not_demonstrated | False | IW-company-OOF-M6-locked-budget-v1-fullweek |

<!-- /AUTO:IMPLEMENTATION_RESULTS -->
