"""One joint classifier, band calibration, source monetary/probability guards."""
import numpy as np
from experiments.t1_competing_v6.features import V6_FEATURES
from .calibration import fit_calibration, transform, log_loss

BANDS = [(1,1),(2,4),(5,13)]


class TransitionModel:
    def __init__(self,booster,vocabulary,calibration=None,batch_rows=50000):
        self.booster,self.vocabulary = booster,vocabulary
        self.calibration,self.batch_rows = calibration,batch_rows

    def predict(self,x,week=None):
        if not len(x):
            return np.empty((0,len(self.vocabulary)))
        p = np.vstack([self.booster.predict(x[i:i+self.batch_rows],num_threads=4) for i in range(0,len(x),self.batch_rows)])
        if self.calibration is None:
            return p
        # The week feature immediately follows the 64 frozen origin features.
        weeks = np.full(len(x),week) if week is not None else x[:,len(V6_FEATURES)].astype(int)
        for low,high in BANDS:
            take = (weeks>=low)&(weeks<=high)
            if take.any():
                p[take] = transform(p[take],self.calibration[f"{low}_{high}"])
        return p


def guards(probability,y,cash_fraction,opening,actual):
    valid = y>=0
    p_positive = probability[:,cash_fraction>0].sum(1)
    p_full = probability[:,cash_fraction>=1].sum(1)
    return {"logloss":log_loss(probability[valid],y[valid]),
            "brier_positive":float(np.mean((p_positive-(actual>0))**2)),
            "brier_full":float(np.mean((p_full-(actual>=opening-1))**2)),
            "cash_bias":float(((probability@cash_fraction)*opening).sum()/max(actual.sum(),1)-1)}


def calibrate(fit,selection,raw_model,protocol):
    result = {}
    cash = np.array([v["cash_fraction"] for v in raw_model.vocabulary])
    for low,high in BANDS:
        fx,fy,fd = fit
        sx,sy,sd = selection
        ft = fd.week.between(low,high).to_numpy()
        st = sd.week.between(low,high).to_numpy()
        fp,sp = raw_model.predict(fx[ft]),raw_model.predict(sx[st])
        candidate = fit_calibration(fp,fy[ft],sp,sy[st],protocol)
        before = guards(sp,sy[st],cash,sd.opening.to_numpy()[st],sd.cash_actual.to_numpy()[st])
        after = guards(transform(sp,candidate),sy[st],cash,sd.opening.to_numpy()[st],sd.cash_actual.to_numpy()[st])
        passed = (abs(after["cash_bias"]) <= abs(before["cash_bias"])+protocol["cash_bias_absolute_tolerance"] and
            after["brier_positive"] <= before["brier_positive"]*1.02+1e-5 and
            after["brier_full"] <= before["brier_full"]*1.02+1e-5)
        if not passed:
            candidate["selected"] = "identity"
        candidate.update(source_before=before,source_after_candidate=after,monetary_and_brier_guards=passed,
                         fit_rows=int(ft.sum()),selection_rows=int(st.sum()))
        result[f"{low}_{high}"] = candidate
    return result
