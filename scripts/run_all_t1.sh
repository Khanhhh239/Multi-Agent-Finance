#!/usr/bin/env bash
set -e
# Chạy tuần tự các thí nghiệm nặng với số luồng giới hạn (máy dùng chung)
cd "$(dirname "$0")/.."
export AGENT1_THREADS=${AGENT1_THREADS:-6} OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
PY=.venv/Scripts/python.exe
[ -f outputs/t4/t4_revenue_forecast.csv ] || $PY -W ignore scripts/run_t4.py > outputs/t4.log 2>&1
for e in ${EXPS:-C A B D E}; do
  $PY -W ignore scripts/run_t1.py --exp $e > outputs/t1_$e.log 2>&1
done
