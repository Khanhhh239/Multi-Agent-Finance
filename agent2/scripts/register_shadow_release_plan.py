"""Register an enterprise-produced immutable validation/policy package; no approval.

Token is read from an environment variable. The CLI never prints credentials,
key material, model payloads or study rows. No active pointer is changed.
"""
import argparse
import os
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent),str(ROOT.parent/'shared/finance_input/src')]
from finance_input.json_io import loads
from sme_fraud.auth import FileAuthorizer
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.pipeline_release import ReleaseService
from experiments.he_inference.registry_export import ReadOnlySnapshots


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('package','auth-file','company','release-config','snapshot-db','model-db','request-id'):p.add_argument('--'+name,required=True)
    p.add_argument('--token-env',default='AGENT2_CLI_TOKEN');args=p.parse_args()
    token=os.environ.get(args.token_env)
    if not token:p.error('Set the existing authorized token in the selected environment variable; do not place it in argv.')
    auth=FileAuthorizer(args.auth_file);header='Bearer '+token
    recheck=lambda:auth.authorize_director(header,args.company);scope=recheck()
    raw=Path(args.package).read_bytes()
    if len(raw)>10*1024*1024:p.error('Package exceeds 10 MB')
    service=ReleaseService.from_config(args.release_config,ReadOnlySnapshots(args.snapshot_db),AnalysisResources(args.model_db))
    value=service.register_plan(scope,loads(raw),args.request_id,recheck)
    print(json.dumps(value,ensure_ascii=True))


if __name__=='__main__':main()
