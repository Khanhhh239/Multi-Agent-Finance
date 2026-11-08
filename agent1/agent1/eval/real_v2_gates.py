"""G5/G6 đăng ký theo yêu cầu 21/10/2026; BLEND được chọn trên quá khứ."""
import numpy as np


def real_v2_decisions(frame,b1_reference=None):
    selected=frame[frame.model.str.startswith('BLEND(DH-GBM,B1d) w=',na=False)]
    valid=(set(selected.setting)=={'ci','bpi'} and len(selected)==2 and
        selected.measurement_version.str.contains('fullweek').all() and
        'expand_full_week_only' in selected and selected.expand_full_week_only.eq(True).all())
    columns=['improvement_vs_B1d_pct','improvement_ci_low','improvement_ci_high','pinball_avg','n']
    valid=valid and np.isfinite(selected[columns].to_numpy(float)).all()
    if not valid:return dict(G5=False,G6=False,reason='Thiếu BLEND v2 đầy đủ/tuần quan sát đủ')
    ci=selected[selected.setting=='ci'].iloc[0]
    g6=bool((selected.improvement_ci_high>=0).all() and (selected.improvement_vs_B1d_pct>=-2).all())
    g5=False;gain=None
    if b1_reference is not None:
        reference=b1_reference[(b1_reference.setting=='ci')&(b1_reference.model=='B1-cust-median')]
        if len(reference)==1 and reference.n.iloc[0]==ci.n and reference.pinball_avg.iloc[0]>0:
            gain=100*(1-ci.pinball_avg/reference.pinball_avg.iloc[0])
            g5=bool(ci.pinball_avg<=.9*reference.pinball_avg.iloc[0] and ci.improvement_ci_low>0)
    return dict(G5=g5,G6=g6,improvement_vs_B1_pct=gain,
        reason='BLEND w chọn trên calibration; G5 CI: pinball so B1 >=10% và CI thấp so B1d >0; G6 cả ci/bpi: CI cao >=0 và điểm >=-2%')
