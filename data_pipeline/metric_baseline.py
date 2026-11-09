"""Record fresh metric results; unsupported engine capabilities remain explicit."""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
import duckdb

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent4'))
from agent4.text2sql.catalog import CatalogSnapshot
from agent4.text2sql.compiler import SQLCompiler
from agent4.text2sql.models import ValidatedPlan,TimeDraft

def run(folder):
    catalog=CatalogSnapshot();compiler=SQLCompiler(catalog)
    db=duckdb.connect(str(folder/'warehouse.duckdb'),read_only=True)
    db.execute("SET memory_limit='1000MB'; SET threads=2")
    results=[]
    for metric in catalog.adapter:
        capability=catalog.capability(metric.id)
        item=dict(metric=metric.id,kind=metric.kind,engine_status=capability.synthetic_status)
        if capability.synthetic_status=='BLOCKED':
            item.update(status='unsupported_by_existing_engine',reason=capability.reason)
        else:
            scope=TimeDraft.as_of_date(date(2026,10,14)) if metric.period_type=='snapshot' else TimeDraft.range(date(2026,1,1),date(2026,10,14))
            plan=ValidatedPlan(metric_ids=(metric.id,),time=scope,dimensions=(),filters=(),view=metric.default_view,
                operation='aggregate',sort=None,top_k=None,comparison=None,tenant_id='MPX10',catalog_hash=catalog.hash,policy_hash='offline-dataset-baseline')
            start=time.monotonic()
            try:
                query=compiler.compile(plan)
                cur=db.execute(query.sql,list(query.params));columns=[d[0] for d in cur.description]
                rows=cur.fetchall()
                item.update(status='executed',rows=[dict(zip(columns,r)) for r in rows],seconds=round(time.monotonic()-start,3))
            except Exception as exc:item.update(status='error',error=f'{type(exc).__name__}: {exc}')
        results.append(item);print(metric.id,item['status'],flush=True)
    db.close()
    (folder/'metric_baseline.json').write_text(json.dumps(dict(catalog_hash=catalog.hash,metrics=results),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    if any(r['status']=='error' and r['engine_status']=='SUPPORTED' for r in results):raise RuntimeError('Supported metric failed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);run(p.parse_args().folder.resolve())
