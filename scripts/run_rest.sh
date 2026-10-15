#!/usr/bin/env bash
# Chạy phần còn lại tuần tự, giới hạn luồng (máy dùng chung). Mỗi bước ghi log riêng.
cd "$(dirname "$0")/.."
export AGENT1_THREADS=${AGENT1_THREADS:-4} OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
PY=.venv/Scripts/python.exe
$PY -W ignore scripts/run_t2_t3.py   > outputs/t2_t3.log 2>&1
$PY -W ignore scripts/run_t1.py --exp D > outputs/t1_D.log 2>&1
$PY -W ignore scripts/run_t1.py --exp E > outputs/t1_E.log 2>&1
$PY -W ignore scripts/run_t1.py --exp B > outputs/t1_B.log 2>&1
$PY -W ignore scripts/run_t6.py      > outputs/t6.log 2>&1
