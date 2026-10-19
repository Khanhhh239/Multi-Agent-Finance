"""Record independent golden checks without rewriting accountant review files."""
import argparse,json,subprocess
from pathlib import Path
from datetime import date,datetime,timezone
import duckdb
from agent4.engine.engine import ExecutionEngine
from agent4.engine.metrics import REGISTRY
from eval.oracle import oracle
from eval.review_formulas import RANGES


def check(db):
    rows=[]
    with ExecutionEngine(db) as engine,duckdb.connect(str(db),read_only=True) as con:
        for metric,md in REGISTRY.items():
            for start,end in RANGES:
                gold=oracle(con,metric,date.fromisoformat(start),date.fromisoformat(end),md.default_view)
                actual=engine.query(metric,{'start_date':start,'end_date':end})['value']
                ok=actual is None and gold is None or actual is not None and gold is not None and abs(actual-gold)<=(.5 if md.unit=='VND' else 1e-9)
                rows.append({'metric':metric,'start':start,'end':end,'oracle':gold,'actual':actual,'passed':ok})
        info=engine.info
    return {'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT',
            'measured_at_utc':datetime.now(timezone.utc).isoformat(),
            'data_version':info['data_version'],'seed':info['seed'],
            'n':len(rows),'passed':sum(r['passed'] for r in rows),'results':rows}


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=Path('data/cfo_warehouse.duckdb'));p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();report=check(args.db)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    raise SystemExit(0 if report['n']==report['passed'] else 1)


if __name__=='__main__': main()
