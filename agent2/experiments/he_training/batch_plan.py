"""Explicit chronological train/holdout partition using the existing PIT builder."""
from .protocol import require, fields, canonical, sha
from .snapshot_adapter import prepare_snapshot_training, VERSION as SNAPSHOT_VERSION, utc

VERSION='snapshot-he-batch-plan/0.1.0'


def prepare_batch_plan(store,scope,request,recheck=None):
    fields(request,{'version','snapshot_id','as_of','training_start','training_end','evaluation_start','evaluation_end','training_batches','evaluation_batches'})
    require(request['version']==VERSION,'BATCH_PLAN_VERSION')
    start,end,ev_start,ev_end,as_of=(utc(request[k]) for k in ('training_start','training_end','evaluation_start','evaluation_end','as_of'))
    require(start<end<=ev_start<ev_end<=as_of,'BATCH_TIME_SPLIT')
    require(isinstance(request['training_batches'],list) and 2<=len(request['training_batches'])<=4,'BATCH_COUNT')
    require(isinstance(request['evaluation_batches'],list) and 1<=len(request['evaluation_batches'])<=4,'EVALUATION_BATCH_COUNT')
    seen=set();parts={};mappings=set();modes=set();all_ready=True
    for kind,first,last in [('training',start,end),('evaluation',ev_start,ev_end)]:
        parts[kind]=[]
        for selected in request[kind+'_batches']:
            require(isinstance(selected,list) and len(selected)==4,'BATCH_ROWS_EXACTLY_FOUR')
            for row in selected:
                fields(row,{'record_id','revision'})
                require(isinstance(row['record_id'],str) and row['record_id'] not in seen,'TRAIN_EVALUATION_OVERLAP_OR_DUPLICATE')
                seen.add(row['record_id'])
            child=dict(version=SNAPSHOT_VERSION,snapshot_id=request['snapshot_id'],as_of=request['as_of'],
                       training_start=first.isoformat(),training_end=last.isoformat(),rows=selected)
            plan=prepare_snapshot_training(store,scope,child,recheck)
            all_ready &= plan['status']=='ready'
            mappings.add(plan['mapping']['fingerprint']);modes.add(plan['simulated'])
            parts[kind].append(dict(request=child,plan=plan))
    require(len(mappings)==1,'BATCH_FEATURE_CONTRACT_MISMATCH')
    require(len(modes)==1 and type(next(iter(modes))) is bool,'BATCH_SOURCE_MODE_MISMATCH')
    value=dict(version=VERSION,status='ready' if all_ready else 'rejected',tenant_id=scope.tenant_id,
        company_id=next(iter(scope.company_ids)),snapshot=parts['training'][0]['plan']['snapshot'],request=request,
        simulated=next(iter(modes)),mapping_fingerprint=next(iter(mappings)),parts=parts,
        training_rows=4*len(parts['training']),evaluation_rows=4*len(parts['evaluation']),
        evaluation_sent_to_training_worker=False,labels_included=False)
    value['plan_sha256']=sha(canonical(value))
    return value
