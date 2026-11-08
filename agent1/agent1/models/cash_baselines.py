"""Đối chứng chuỗi thời gian cố định; mỗi lần fit chỉ nhận dòng ròng đã quan sát."""
import warnings
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


def time_series_paths(history, model, *, weeks=13, n=1000, seed=7):
    history=np.asarray(history,float)
    if history.ndim!=1 or len(history)<26 or not np.isfinite(history).all():
        raise ValueError('Cần >=26 tuần dòng ròng hữu hạn')
    if model not in {'ETS','ARIMA'}:raise ValueError('Đối chứng phải là ETS hoặc ARIMA')
    scale=max(float(np.mean(np.abs(history))),1.)
    values=history/scale;rng=np.random.default_rng(seed)
    info=dict(model=model,fallback=False,converged=True,n_history=len(history),warning_count=0)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            if model=='ETS':
                fitted=ExponentialSmoothing(values,trend='add',damped_trend=True,
                    initialization_method='estimated').fit(optimized=True)
                info['converged']=bool(fitted.mle_retvals.success)
                samples=fitted.simulate(weeks,anchor='end',repetitions=n,random_errors='bootstrap',rng=rng)
            else:
                fitted=SARIMAX(values,order=(1,0,1),trend='c',enforce_stationarity=True,
                    enforce_invertibility=True).fit(disp=False,maxiter=100)
                info['converged']=bool(fitted.mle_retvals.get('converged',False))
                samples=fitted.simulate(weeks,anchor='end',repetitions=n,rng=rng)
            info['warning_count']=len(captured)
        samples=np.asarray(samples).reshape(weeks,n).T*scale
        if not info['converged'] or not np.isfinite(samples).all():
            raise ValueError('Fit chưa hội tụ hoặc mô phỏng không hữu hạn')
    except (ValueError,RuntimeError,OverflowError,np.linalg.LinAlgError) as exc:
        # Mốc dự phòng khoá trước: trung bình lịch sử + bootstrap phần dư iid.
        info.update(fallback=True,converged=False,fallback_reason=str(exc))
        samples=(values.mean()+rng.choice(values-values.mean(),size=(n,weeks),replace=True))*scale
    return samples,info


def due_spreadsheet(snapshot, known_out, kernel, weekly_revenue, B0, *, weeks=13):
    """B0: thu đúng hạn (nợ quá hạn tuần 1) + TB doanh thu đã thấy → kernel lịch sử."""
    due=snapshot.days_to_due.to_numpy(float)
    amount=snapshot.amount_open.to_numpy(float)
    inflow=np.zeros(weeks)
    week=np.maximum(0,np.ceil(due/7).astype(int)-1)
    for k in range(weeks):inflow[k]=amount[week==k].sum()
    kernel=np.asarray(kernel,float)
    for issued in range(weeks):
        for lag in range(min(weeks-issued,len(kernel))):
            inflow[issued+lag]+=weekly_revenue*kernel[lag]
    return float(B0)+np.cumsum(inflow-np.asarray(known_out,float))
