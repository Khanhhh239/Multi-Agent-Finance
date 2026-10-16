"""Reproducible GL scan benchmark, separate from the pilot scale test.

Creates an isolated scratch DB. Repeated GL rows measure scans only: no
claim of realistic 5M-event subledgers or business correctness at this scale.
"""
import argparse
import json
import math
from pathlib import Path
from time import perf_counter
import duckdb
from agent4.engine.engine import ExecutionEngine
from agent4.engine.metrics import REGISTRY

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows',type=int,default=5_000_000)
    parser.add_argument('--source',type=Path,default=Path('data/cfo_warehouse.duckdb'))
    parser.add_argument('--out',type=Path,default=Path('data/benchmark_5m.duckdb'))
    args = parser.parse_args()
    if args.out.exists() or args.out.resolve()==args.source.resolve():
        raise SystemExit('Choose a new scratch output path.')
    con = duckdb.connect(str(args.out))
    try:
        source_literal = str(args.source.resolve()).replace("'","''")
        con.execute(f"ATTACH '{source_literal}' AS source (READ_ONLY)")
        for (name,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog='source' AND (table_name LIKE 'dim_%' OR table_name='company_info')").fetchall():
            con.execute(f'CREATE TABLE {name} AS SELECT * FROM source.{name}')
        count = con.execute('SELECT COUNT(*) FROM source.gl_wide').fetchone()[0]
        con.execute(f'CREATE TABLE gl_wide AS SELECT g.* FROM source.gl_wide g CROSS JOIN range({math.ceil(args.rows/count)}) LIMIT {args.rows}')
        con.execute('CREATE VIEW v_gl AS SELECT * FROM gl_wide')
        con.execute('CREATE VIEW v_mgmt AS SELECT * FROM v_gl')
        con.execute('CREATE VIEW v_tax AS SELECT * FROM v_gl WHERE tax_deductible')
    finally:
        con.close()
    metrics = [m.id for m in REGISTRY.values() if m.kind!='custom']
    samples = []
    with ExecutionEngine(args.out) as engine:
        # One measured pass, metric-specific queries, includes first execution.
        for metric in metrics:
            start = perf_counter()
            engine.query(metric,'2026-Q3')
            samples.append({'metric':metric,'ms':(perf_counter()-start)*1000})
    p95 = sorted(s['ms'] for s in samples)[math.ceil(.95*len(samples))-1]
    report = {'measured_on':'2026-10-16','rows':args.rows,'n':len(samples),'p95_ms':p95,
              'method':'materialized repeated gl_wide; linear/ratio metrics only; original subledgers not scaled',
              'threshold_ms':5000,'passed':p95<=5000,'samples':samples}
    output = Path('docs/5_handoff/measurements/g0_gl_scan_5m.json')
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'}))

if __name__=='__main__':
    main()
