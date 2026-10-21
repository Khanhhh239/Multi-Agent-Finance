"""Cổng thoái lui theo doanh nghiệp: BLEND thua mốc B1d quá lâu thì dùng B1d (GO_NO_GO_SYNTHETIC_ONLY.md, mục 2).

Đầu vào là pinball theo tuần của hai phương pháp trên các hoá đơn ĐÃ đáo hạn trong tuần đó (không nhìn tương lai).
Trạng thái có độ trễ: thoái lui ở tuần t chỉ dựa trên dữ liệu đến hết tuần t-1.
"""
import numpy as np
import pandas as pd

WINDOW = 8        # tuần gần nhất để so sánh
MARGIN = 0.05     # BLEND thua B1d quá 5% thì tính là "thua"
PATIENCE = 4      # số tuần liên tiếp thua mới thoái lui
RECOVER = 4       # số tuần liên tiếp không thua mới quay lại BLEND


def fallback_states(blend_loss, base_loss, window=WINDOW, margin=MARGIN, patience=PATIENCE, recover=RECOVER):
    """blend_loss, base_loss: chuỗi pinball trung bình theo tuần. Trả về mảng bool: True = đang dùng B1d tại tuần đó."""
    b = pd.Series(blend_loss, dtype=float).reset_index(drop=True)
    r = pd.Series(base_loss, dtype=float).reset_index(drop=True)
    wb = b.rolling(window, min_periods=2).mean().shift(1)   # chỉ dữ liệu đến t-1
    wr = r.rolling(window, min_periods=2).mean().shift(1)
    losing = (wb > wr * (1 + margin)).fillna(False).to_numpy()
    state, bad, good, out = False, 0, 0, []
    for lose in losing:
        bad, good = (bad + 1, 0) if lose else (0, good + 1)
        if not state and bad >= patience:
            state = True
        elif state and good >= recover:
            state = False
        out.append(state)
    return np.array(out, dtype=bool)


def gated_loss(blend_loss, base_loss, **kw):
    s = fallback_states(blend_loss, base_loss, **kw)
    return np.where(s, np.asarray(base_loss, float), np.asarray(blend_loss, float)), s
