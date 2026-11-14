"""Archived synthetic native outputs re-bound to isolated snapshot/job stores."""
import json
from pathlib import Path
from experiments.he_inference.registry_demo import commit

EVIDENCE=Path(__file__).resolve().parents[2]/'Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113'


def seed_run(f,company,key):
    scope=f.h.authorizer.authorize('Bearer '+f.h.token,company)
    source=json.loads((EVIDENCE/(company+'-source.json')).read_text('utf-8'))
    sid=commit(f.h.store,scope,source,'comparison-source-'+key)
    result=json.loads((EVIDENCE/(company+'-result.json')).read_text('utf-8'))
    job=f.node.jobs.store.create(scope,key,dict(snapshot_id=sid,as_of=result['as_of'],artifact_id=f.pair.env['artifacts'][company]))
    _,data=f.node.jobs.store.get(scope,job);result.update(snapshot_id=sid,run_id=job);data['result']=result;f.node.jobs.store.save(scope,job,data,'completed')
    return job
