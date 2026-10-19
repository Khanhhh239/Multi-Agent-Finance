"""Build split warehouses; expose reconciliation aggregates, never test answers."""
import json
from datetime import datetime,timezone
from pathlib import Path
import duckdb
from agent4.datagen.build import build,_validate,DATA_VERSION

GAPS=('ar_gl_vs_subledger_gap','ap_gl_vs_subledger_gap','inventory_gl_vs_subledger_gap')


def reconciliation(stats):
    gaps={key:stats[key] for key in GAPS}
    if any(value!=0 for value in gaps.values()):
        raise ValueError('Reconciliation failed; do not generate evaluation labels.')
    return gaps


def main():
    root=Path(__file__).resolve().parents[1]
    report={'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT',
            'measured_at_utc':datetime.now(timezone.utc).isoformat(),'warehouses':[]}
    for split,seed,filename in [('train',20251,'cfo_warehouse'),('val',71,'val'),('test',9001,'test')]:
        path=root/'data'/f'{filename}.duckdb'
        if not path.exists(): build(path,seed=seed,quiet=True)
        with duckdb.connect(str(path),read_only=True) as con:
            info=dict(con.execute('SELECT key,value FROM company_info').fetchall())
            if info['seed']!=str(seed) or info['data_version']!=DATA_VERSION:
                raise ValueError('Existing warehouse has the wrong seed/version; preserve and inspect explicitly.')
            stats=_validate(con,quiet=True)
        report['warehouses'].append({'split':split,'seed':seed,'data_version':DATA_VERSION,
                                     'reconciliation_gaps':reconciliation(stats),'gl_rows':stats['gl_lines'],
                                     'intentional_A4_unbalanced_journals':stats['unbalanced_journals']})
    report['limitation']='A4 deliberately contains one unbalanced journal; this is not an AR/AP/inventory reconciliation gap. No test questions or answer results were inspected.'
    out=root/'docs/5_handoff/measurements/p2_warehouses.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__': main()
