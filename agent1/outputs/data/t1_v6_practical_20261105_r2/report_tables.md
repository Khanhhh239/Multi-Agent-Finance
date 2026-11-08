## source_models

| model | fit_n | joint_brier365 | writeoff_brier365 | joint_improvement_pct | writeoff_improvement_pct |
| --- | --- | --- | --- | --- | --- |
| v6 | 200000 | 0.134753 | 0.041910 | 0.000000 | 0.000000 |
| industry | 200000 | 0.134218 | 0.041879 | 0.397095 | 0.074403 |
| behavior | 200000 | 0.134886 | 0.041843 | -0.098936 | 0.159674 |
| both | 200000 | 0.133687 | 0.041794 | 0.790888 | 0.277358 |
| aug_v6 | 300000 | 0.134348 | 0.043305 | 0.300318 | -3.329264 |
| aug_both | 300000 | 0.133098 | 0.042560 | 1.228235 | -1.551442 |

## fresh_models

| model | fit_n | joint_brier365 | writeoff_brier365 | joint_improvement_pct | writeoff_improvement_pct |
| --- | --- | --- | --- | --- | --- |
| v6 | 200000 | 0.189867 | 0.067089 | 0.000000 | 0.000000 |
| industry | 200000 | 0.189825 | 0.067149 | 0.022070 | -0.089637 |
| behavior | 200000 | 0.189494 | 0.066743 | 0.196441 | 0.515279 |
| both | 200000 | 0.188946 | 0.066521 | 0.485186 | 0.845481 |
| aug_v6 | 300000 | 0.188324 | 0.066791 | 0.812812 | 0.443500 |
| aug_both | 300000 | 0.188140 | 0.066220 | 0.909619 | 1.294319 |

## fresh_worlds_selected

| world | n | joint_brier365_v6 | joint_brier365_selected | actual_writeoff365_pct | pred_writeoff365_pct | writeoff_gap365_pp | max_paid_ece | max_short_paid_brier_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| practical_v6_20261105_fresh_000 | 4109 | 0.099582 | 0.100625 | 6.716963 | 8.013100 | 1.296137 | 0.059540 | 1.005186 |
| practical_v6_20261105_fresh_001 | 3612 | 0.150932 | 0.149363 | 13.427464 | 11.638004 | -1.789460 | 0.044525 | 1.000676 |
| practical_v6_20261105_fresh_002 | 5556 | 0.229685 | 0.227232 | 9.017279 | 8.219065 | -0.798213 | 0.079942 | 0.998175 |
| practical_v6_20261105_fresh_003 | 2189 | 0.279270 | 0.278565 | 19.963454 | 13.828970 | -6.134484 | 0.193220 | 1.008707 |

## source_support

| fit | feature | train_max | source_outside_range_pct |
| --- | --- | --- | --- |
| primary | c_n_hist | 1801.000000 | 1.533540 |
| primary | c_tenure_days | 1629.000000 | 80.327406 |
| primary | f_n_hist | 11856.000000 | 0.000000 |
| augmented | c_n_hist | 1997.000000 | 0.000000 |
| augmented | c_tenure_days | 1629.000000 | 80.327406 |
| augmented | f_n_hist | 11856.000000 | 0.000000 |

## fresh_bootstrap365

| world | model | day | firms | ci_low | ci_high | replicates | resampling_unit | delta_brier_vs_v6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| practical_v6_20261105_fresh_000 | both | 365 | 20 | -0.000437 | 0.002608 | 400 | firm within World; does not establish uncertainty across unseen Worlds | 0.001043 |
| practical_v6_20261105_fresh_001 | both | 365 | 20 | -0.003797 | 0.000040 | 400 | firm within World; does not establish uncertainty across unseen Worlds | -0.001570 |
| practical_v6_20261105_fresh_002 | both | 365 | 20 | -0.004496 | 0.000299 | 400 | firm within World; does not establish uncertainty across unseen Worlds | -0.002453 |
| practical_v6_20261105_fresh_003 | both | 365 | 20 | -0.003349 | 0.001534 | 400 | firm within World; does not establish uncertainty across unseen Worlds | -0.000705 |

