import os

# so luong cho LightGBM/XGBoost: tranh qua tai luong khi may dang ban
NT = max(1, min(6, int(os.environ.get("AGENT1_THREADS", "6"))))
os.environ.setdefault("OMP_NUM_THREADS", str(min(NT, 4)))
os.environ['OMP_NUM_THREADS'] = str(max(1, min(4, int(os.environ['OMP_NUM_THREADS']))))
try:
    from threadpoolctl import threadpool_limits
    _blas_limit = threadpool_limits(limits=min(NT, 4), user_api='blas')
except ImportError:
    pass
