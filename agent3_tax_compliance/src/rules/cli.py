import argparse
from pathlib import Path
from ..config import Settings
from ..domain.taxpayer import AccessContext
from .repository import ExecutionRepository


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--tenant-id',required=True)
    parser.add_argument('--taxpayer-id',required=True)
    parser.add_argument('--actor-id',required=True)
    parser.add_argument('--evaluation-id',required=True)
    args=parser.parse_args()
    if not args.database.is_file():parser.error('Existing foundation database required')
    ctx=AccessContext(actor_id=args.actor_id,tenant_id=args.tenant_id,taxpayer_ids=frozenset({args.taxpayer_id}),permissions=frozenset({'READ','WRITE'}))
    result=ExecutionRepository(Settings(database_path=args.database)).work(ctx,args.taxpayer_id,args.evaluation_id)
    print(result.model_dump_json(indent=2))


if __name__=='__main__':main()
