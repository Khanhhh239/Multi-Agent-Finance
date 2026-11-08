import argparse
from pathlib import Path
from ..config import Settings
from ..domain.taxpayer import AccessContext
from .workflow import Workflow
from .contracts import EvaluationCommand


def main():
    parser=argparse.ArgumentParser()
    for name in ('tenant-id','taxpayer-id','actor-id','record-id','idempotency-key'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--revision',type=int,required=True)
    args=parser.parse_args()
    if not args.database.is_file():parser.error('Existing capture database required')
    ctx=AccessContext(actor_id=args.actor_id,tenant_id=args.tenant_id,taxpayer_ids=frozenset({args.taxpayer_id}),permissions=frozenset({'READ','WRITE'}))
    result=Workflow(Settings(database_path=args.database)).work(ctx,args.taxpayer_id,args.record_id,EvaluationCommand(expected_record_revision=args.revision),args.idempotency_key)
    print(result.model_dump_json(indent=2))


if __name__=='__main__':main()
