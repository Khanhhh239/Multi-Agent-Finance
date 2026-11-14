"""Generate opt-in B5/E4 inputs, commit snapshots and compare retained engine."""
import argparse,json,sys,tempfile
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finance_input import AccessScope
from sme_fraud.import_files import canonical,digest
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.vendor_identity_demo import prepare,MODES
from sme_fraud.rules import score_rules
from sme_fraud.method_adapters import score_snapshot


def run(output):
    output.mkdir(parents=True,exist_ok=False);sources=output/'sources';sources.mkdir();checks=[];missing=[]
    with tempfile.TemporaryDirectory(prefix='agent2-vendor-parity-') as tmp:
        store=SnapshotStore(Path(tmp)/'snapshots.sqlite3')
        for company in ('C001','C002'):
            scope=AccessScope('native-demo',frozenset({company}),'synthetic-check',frozenset({'data.import'}))
            for mode in MODES:
                data,native,as_of=prepare(mode,company);case_id=company+'_'+mode;source_bytes=canonical(data)
                (sources/(case_id+'.json')).write_bytes(source_bytes)
                draft=store.upload(scope,source_bytes,case_id+'.json',case_id+'-upload');preview=store.preview(scope,draft['import_id'],1)
                body={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')}
                body.update(expected_revision=preview['revision'],acknowledge=True)
                saved=store.commit(scope,draft['import_id'],body,case_id+'-commit');sid=saved['snapshot']['snapshot_id']
                result=score_snapshot(store,scope,sid,as_of,methods=('ecod',));reference=score_rules(native)
                native_hit=next((h for h in reference['hits'] if h['rule_id']=='B5'),None)
                r=result['rows'][0]['methods']['rules']['details']['rule_results']
                for code in ('B5','E4'):
                    actual=next(x for x in r['rules'] if x['rule_id']==code)
                    parity=actual['available'] and actual['matched']==bool(native_hit) and actual['score']==(native_hit['points'] if native_hit else 0) and actual['intrinsic_points']==(native_hit['intrinsic_points'] if native_hit else 0)
                    if native_hit:parity=parity and actual['details']['evidence']==native_hit['evidence'] and actual['details']['hits'][0]['evidence_id']==native_hit['evidence_id']
                    checks.append(dict(case_id=case_id,company_id=company,rule_id=code,source_sha256=digest(source_bytes),as_of=as_of,event_at=data['transactions'][0]['effective_at'],knowledge_at=data['transactions'][0]['observed_at'],status=actual['status'],matched=actual['matched'],score=actual['score'],intrinsic_points=actual['intrinsic_points'],evidence=actual['details'].get('evidence'),native_parity=bool(parity),source_unchanged=source_bytes==canonical(data)))
                (output/(case_id+'.result.json')).write_bytes(canonical(result))
                if mode=='signal':
                    from sme_fraud.snapshot_features import build_feature_rows
                    from sme_fraud.rule_sources import _resolve
                    from sme_fraud.rule_evaluation import _evaluate
                    changed=deepcopy(data);changed['vendors'][1].pop('phone');frame=build_feature_rows(changed,scope,as_of);private,public=_resolve(changed,frame,scope);meta=frame['rows'][0];key=meta['record_id'],meta['revision'];blocked=_evaluate(private[key],public[key],scope,meta)
                    for code in ('B5','E4'):
                        x=next(x for x in blocked['rules'] if x['rule_id']==code);missing.append(dict(company_id=company,rule_id=code,passed=x['status']=='unavailable' and x['matched'] is None and x['score'] is None))
    passed=len(checks)==20 and all(c['native_parity'] and c['source_unchanged'] for c in checks) and len(missing)==4 and all(c['passed'] for c in missing)
    report=dict(status='passed' if passed else 'failed',technical_only=True,is_simulated=True,source_packages=10,parity_checks=20,missing_source_checks=4,model_fit_performed=False,new_he_execution=False,portal_changed=False,checks=checks,missing=missing)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Đối chiếu B5/E4 trên snapshot','',f"Trạng thái: **{report['status']}**. 20 đối chiếu, 10 gói nguồn, 4 kiểm tra thiếu nguồn. Dữ liệu mô phỏng.",'','| Ca | Luật | Trạng thái | Điểm nội tại | Điểm giao dịch | Khớp engine |','|---|---|---|---:|---:|---|']
    lines += ['| '+c['case_id']+' | '+c['rule_id']+' | '+c['status']+' | '+str(c['intrinsic_points'])+' | '+str(c['score'])+' | '+str(c['native_parity'])+' |' for c in checks]
    lines+=['','B5/E4 dùng chung bằng chứng B5. Điểm giao dịch bằng 0 theo policy master-quality; không cộng lần hai. Nguồn sau cutoff không được dùng; thiếu trường trả unavailable. Chưa nối HE hoặc thay hàng đợi.','']
    (output/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ('checks','missing')}));return passed


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();raise SystemExit(0 if run(a.output_dir.resolve()) else 1)
