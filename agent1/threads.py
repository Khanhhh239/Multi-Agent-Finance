import os

# so luong cho LightGBM/XGBoost: tranh qua tai luong khi may dang ban
NT = max(1, min(6, int(os.environ.get("AGENT1_THREADS", "6"))))
os.environ.setdefault("OMP_NUM_THREADS", str(min(NT, 4)))
