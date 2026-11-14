"""Enterprise-side numerical/ranking metrics; never a fraud accuracy measure."""
import math
import numpy as np
from scipy.stats import rankdata

from .protocol import ABS_TOLERANCE, REL_TOLERANCE


def compare_rows(reference, encrypted, budget=5):
    """Join by scoped caller context plus record/revision, never row position.

    Caller must lock company/model/snapshot/as_of before supplying these rows.
    Missing/unavailable scores fail the comparison instead of disappearing.
    """
    def index(rows):
        result={}
        for row in rows:
            key=(row['record_id'],row['revision'])
            if key in result:raise ValueError('duplicate row identity')
            score=row['score']
            if not row['available'] or type(score) not in (int,float) or not math.isfinite(score):
                raise ValueError('comparison requires every row to have a finite score')
            result[key]=float(score)
        return result
    clear,he=index(reference),index(encrypted)
    if not clear or clear.keys()!=he.keys():raise ValueError('row identities differ or are empty')
    if type(budget) is not int or budget<1:raise ValueError('invalid review budget')
    identities=sorted(clear);a=np.array([clear[k] for k in identities]);b=np.array([he[k] for k in identities])
    error=np.abs(a-b);tolerance=ABS_TOLERANCE+REL_TOLERANCE*np.abs(a)
    order=lambda values:sorted(identities,key=lambda k:(-values[k],k))
    ca,cb=order(clear),order(he);ra={k:i+1 for i,k in enumerate(ca)};rb={k:i+1 for i,k in enumerate(cb)}
    x,y=rankdata(-a,method='average'),rankdata(-b,method='average')
    correlation=float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 and np.std(y)>0 else None
    inversions=comparable=0
    for i in range(len(a)):
        for j in range(i+1,len(a)):
            # Exact ties and gaps below the declared numerical error budget
            # cannot support a claim that priority materially changed.
            if abs(a[i]-a[j])>tolerance[i]+tolerance[j]:
                comparable+=1
                inversions+=int((a[i]-a[j])*(b[i]-b[j])<=0)
    k=min(budget,len(a));overlap=len(set(ca[:k]) & set(cb[:k]))
    nonzero=np.abs(a)>1e-12
    return dict(row_count=len(a),absolute_tolerance=ABS_TOLERANCE,relative_tolerance=REL_TOLERANCE,
        all_scores_within_tolerance=bool(np.all(error<=tolerance)),
        maximum_absolute_error=float(error.max()),mean_absolute_error=float(error.mean()),
        maximum_relative_error=float(np.max(error[nonzero]/np.abs(a[nonzero]))) if nonzero.any() else None,
        relative_error_undefined_rows=int((~nonzero).sum()),spearman=correlation,
        exact_order_equal=ca==cb,material_pair_inversions=inversions,comparable_pairs=comparable,
        top_k=k,top_k_overlap=overlap,top_k_overlap_fraction=overlap/k,
        top_k_covers_entire_dataset=k==len(a),
        plaintext_order=[list(k) for k in ca],encrypted_order=[list(k) for k in cb],
        rows=[dict(record_id=k[0],revision=k[1],plaintext_score=clear[k],encrypted_score=he[k],
            absolute_error=abs(clear[k]-he[k]),allowed_error=float(tolerance[i]),
            within_tolerance=bool(error[i]<=tolerance[i]),plaintext_rank=ra[k],encrypted_rank=rb[k])
            for i,k in enumerate(identities)])


def timing_summary(samples):
    if not samples or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in samples):
        raise ValueError('invalid timing samples')
    return dict(count=len(samples),median_ms=float(np.median(samples)),
                p95_ms=float(np.percentile(samples,95)),minimum_ms=min(samples),maximum_ms=max(samples),samples_ms=samples)


def recovery_summary(cases):
    groups=[]
    for mode in sorted({c['mode'] for c in cases}):
        attempts=[c for c in cases if c['mode']==mode]
        valid=[c for c in attempts if c['injection_confirmed']]
        successes=[c for c in valid if c['recovered']]
        groups.append(dict(mode=mode,attempted=len(attempts),confirmed=len(valid),
            inconclusive=len(attempts)-len(valid),successful=len(successes),
            success_fraction=len(successes)/len(valid) if valid else None,
            successful_recovery_time=timing_summary([c['recovery_ms'] for c in successes]) if successes else None))
    return groups
