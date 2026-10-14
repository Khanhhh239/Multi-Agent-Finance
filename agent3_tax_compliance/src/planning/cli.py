"""Local authenticated-owner CLI for planning stored CFR revisions."""
import argparse
from pathlib import Path
from ..config import Settings
from ..domain.taxpayer import AccessContext
from .repository import PlanningRepository


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--tenant-id',required=True)
    parser.add_argument('--taxpayer-id',required=True)
    parser.add_argument('--actor-id',required=True)
    parser.add_argument('--record-id',required=True)
    parser.add_argument('--revision',type=int,required=True)
    args=parser.parse_args()
    if not args.database.is_file():parser.error('Existing foundation database required')
    settings=Settings(database_path=args.database)
    ctx=AccessContext(actor_id=args.actor_id,tenant_id=args.tenant_id,taxpayer_ids=frozenset({args.taxpayer_id}),permissions=frozenset({'READ','WRITE'}))
    result=PlanningRepository(settings).work(ctx,args.taxpayer_id,args.record_id,args.revision)
    print(result.model_dump_json(indent=2))


if __name__=='__main__':main()
