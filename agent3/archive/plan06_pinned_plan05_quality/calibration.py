"""Small, auditable binned calibrator. Detection scores are not text confidence.

Fit/HOLDOUT data must be disjoint by source, logical document AND template group.
Synthetic functional fixtures never produce a production-validated model.
"""
import math
from .contracts import CalibrationArtifact,CalibrationBin,ScoreSample
from ..canonicalization.derive import sha

def index(score,bins): return min(int(score*bins),bins-1)

def predict(model,scope,score,*,allow_functional=False):
    if model.scope!=scope or model.status=='UNAVAILABLE': return None
    if model.status!='VALIDATED' and not allow_functional: return None
    if not math.isfinite(score) or not 0<=score<=1: raise ValueError('invalid score')
    bucket=next((b for b in model.bins if b.index==index(score,model.bin_count)),None)
    return bucket.probability if bucket else None

def metrics(probabilities,labels,bins=5):
    if len(probabilities)!=len(labels) or not labels: raise ValueError('nonempty paired probabilities/labels required')
    if any(not math.isfinite(p) or not 0<=p<=1 for p in probabilities): raise ValueError('invalid probability')
    groups={}
    for probability,label in zip(probabilities,labels): groups.setdefault(index(probability,bins),[]).append((probability,int(label)))
    reliability=[];ece=0
    for bucket,pairs in sorted(groups.items()):
        mean=sum(p for p,y in pairs)/len(pairs);accuracy=sum(y for p,y in pairs)/len(pairs)
        ece+=len(pairs)/len(labels)*abs(mean-accuracy)
        reliability.append({'bin':bucket,'count':len(pairs),'mean_probability':mean,'observed_accuracy':accuracy})
    return {'brier':sum((p-int(y))**2 for p,y in zip(probabilities,labels))/len(labels),'ece':ece,'reliability':tuple(reliability)}

def precision_interval(correct,count):
    """95% Wilson interval, independent Bernoulli diagnostic; groups still matter."""
    if not count: return None
    if not 0<=correct<=count: raise ValueError('invalid correct/count')
    z=1.959963984540054;p=correct/count;den=1+z*z/count
    center=(p+z*z/(2*count))/den
    radius=z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/den
    return max(0,center-radius),min(1,center+radius)

def threshold_report(probabilities,labels,threshold):
    if len(probabilities)!=len(labels) or not 0<=threshold<=1: raise ValueError('invalid threshold input')
    accepted=[int(y) for p,y in zip(probabilities,labels) if p>=threshold]
    count=len(accepted);correct=sum(accepted)
    return {'threshold':threshold,'accepted':count,'false_acceptances':count-correct,
        'coverage':count/len(labels) if labels else None,'precision':correct/count if count else None,
        'precision_interval_95':precision_interval(correct,count)}

def fit(samples,scope,*,version,created_at,bin_count=5,min_fit=30,min_holdout=30,min_bin=5):
    samples=tuple(ScoreSample.model_validate_json(s.model_dump_json()) for s in samples)
    if not 1<=bin_count<=20 or min(min_fit,min_holdout,min_bin)<1: raise ValueError('invalid sample limits')
    if len({s.sample_id for s in samples})!=len(samples): raise ValueError('duplicate sample IDs')
    if any(s.scope!=scope for s in samples): raise ValueError('mixed calibration scope')
    if any(s.split not in ('FIT','HOLDOUT') for s in samples): raise ValueError('TEST/DEVELOPMENT data cannot fit calibration')
    train=[s for s in samples if s.split=='FIT'];holdout=[s for s in samples if s.split=='HOLDOUT']
    for attribute in ('logical_document_id','group_id','source_sha256'):
        if {getattr(s,attribute) for s in train}&{getattr(s,attribute) for s in holdout}: raise ValueError('split leakage: '+attribute)
    payload=dict(config_version=version,creator='quality-calibrator',stage='calibration',created_at=created_at,
        version=version,scope=scope,dataset_sha256=sha([s.model_dump(mode='json') for s in samples]),
        fit_count=len(train),holdout_count=len(holdout),bin_count=bin_count,
        fit_group_ids=tuple(sorted({s.group_id for s in train})),holdout_group_ids=tuple(sorted({s.group_id for s in holdout})))
    reasons=[]
    if scope.score_kind not in ('RECOGNITION','EXTRACTOR'): reasons.append('SCORE_NOT_TEXT_OR_FIELD_CONFIDENCE')
    if len(train)<min_fit or len(holdout)<min_holdout: reasons.append('INSUFFICIENT_SAMPLE')
    if any(not s.use_permitted or not s.independently_reviewed or not s.split_frozen for s in samples): reasons.append('DATASET_GATE_NOT_MET')
    if reasons: return CalibrationArtifact(**payload,status='UNAVAILABLE',reasons=tuple(reasons))
    buckets={}
    for sample in train: buckets.setdefault(index(sample.raw_score,bin_count),[]).append(sample)
    if any(len(bucket)<min_bin for bucket in buckets.values()):
        return CalibrationArtifact(**payload,status='UNAVAILABLE',reasons=('INSUFFICIENT_BIN_SUPPORT',))
    bins=tuple(CalibrationBin(index=n,count=len(bucket),correct=sum(s.correct for s in bucket),
        probability=(sum(s.correct for s in bucket)+1)/(len(bucket)+2)) for n,bucket in sorted(buckets.items()))
    probabilities=[]
    for sample in holdout:
        bucket=next((b for b in bins if b.index==index(sample.raw_score,bin_count)),None)
        if bucket is None: return CalibrationArtifact(**payload,status='UNAVAILABLE',reasons=('UNSUPPORTED_HOLDOUT_BIN',))
        probabilities.append(bucket.probability)
    result=metrics(probabilities,[s.correct for s in holdout],bin_count)
    return CalibrationArtifact(**payload,status='FUNCTIONAL_ONLY' if any(s.synthetic for s in samples) else 'VALIDATED',
        bins=bins,**result,reasons=('SYNTHETIC_NOT_PRODUCTION',) if any(s.synthetic for s in samples) else ())
