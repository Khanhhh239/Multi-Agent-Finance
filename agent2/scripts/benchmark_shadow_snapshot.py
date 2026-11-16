"""Enterprise operator benchmark; no model/queue writes or plaintext cloud calls."""
import argparse
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from experiments.he_training.protocol import strict_json,canonical,atomic,require


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--token-file',type=Path,required=True)
    p.add_argument('--shadow-run-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'OUTPUT_EXISTS');cfg=strict_json(a.config.read_bytes())
    origin=urlsplit(cfg['portal_url'])
    require(origin.scheme=='http' and origin.hostname in ('127.0.0.1','localhost') and origin.port and not origin.username and origin.path in ('','/') and not origin.query and not origin.fragment,'PORTAL_LOOPBACK_REQUIRED')
    import re
    require(isinstance(cfg['company_id'],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',cfg['company_id']),'COMPANY_ID_INVALID')
    body=dict(shadow_run_id=a.shadow_run_id)
    if cfg.get('ml_method') is not None:body['ml_method']=cfg['ml_method']
    headers={'X-Session':a.token_file.read_text('utf-8').strip(),'X-Platform':'1','Content-Type':'application/json'}
    request=Request(cfg['portal_url'].rstrip('/')+'/agent2/api/v1/companies/'+cfg['company_id']+'/pipeline-benchmarks',data=canonical(body),headers=headers)
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=120) as response:
        result=strict_json(response.read(24*1024*1024+1))
    atomic(a.output,canonical(result))
    print('Technical benchmark saved; operational queue unchanged.')


if __name__=='__main__':main()
