"""Trusted local operator import. HTTP clients cannot submit legal/payment assertions."""
import argparse
import json
import os
from pathlib import Path
from ..config import Settings
from ..ingestion.auth import authenticate
from .contracts import ReviewDossier
from .repository import BusinessReviewRepository


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('import','assess'))
    parser.add_argument('--taxpayer-id',required=True)
    parser.add_argument('--record-id',required=True)
    parser.add_argument('--token-env',default='AGENT3_ACCESS_TOKEN')
    parser.add_argument('--dossier',type=Path)
    parser.add_argument('--evidence-root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    settings=Settings.from_env()
    ctx=authenticate(settings,'Bearer '+os.environ.get(args.token_env,''))
    repository=BusinessReviewRepository(settings)
    if args.command=='import':
        if not args.dossier or not args.evidence_root:parser.error('import needs --dossier and --evidence-root')
        if args.dossier.stat().st_size>4*1024*1024:parser.error('dossier too large')
        dossier=ReviewDossier.model_validate_json(args.dossier.read_text(encoding='utf-8'))
        result=repository.import_local(ctx,args.taxpayer_id,args.record_id,dossier,args.evidence_root)
    else:result=repository.assess(ctx,args.taxpayer_id,args.record_id)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print('Business review result saved. No tax-rule publication or legacy evaluation changes.')


if __name__=='__main__':main()
