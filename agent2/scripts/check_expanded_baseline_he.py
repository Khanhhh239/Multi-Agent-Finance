"""Fresh native HE checks plus enterprise-local expanded rules/ML comparison.

No Portal credentials, fit, production state changes or plaintext worker input.
E3/B5/E4 remain explicitly outside HE; this does not certify an all-HE baseline.
"""
import argparse,json,secrets,socket,sys,time
from html import escape
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical,digest
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshot_features import build_from_snapshot,feature_contract
from sme_fraud.method_preprocess import row_values
from sme_fraud.expanded_selection import compare
from experiments.he4.p1_demo import source,save_snapshot
from experiments.he4.snapshot_adapter import prepare_snapshot
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.inputs import decode_payment
from experiments.he4.client_transport import envelope,upload,download
from experiments.he4.bundle import build
from experiments.he_inference.prepared_demo import private_folder,worker_service
from experiments.he_inference.registry_export import export_snapshot,_load_model
from experiments.he_inference.registry_demo import database_dump
from experiments.he_inference.key_manager import load_key,PROVIDER
from experiments.he_inference.protocol import public_hex,sign,verify,sha
from experiments.he_inference.enterprise_server import REGISTRATION
from experiments.he_inference.http_common import post
from experiments.he_inference.comparison_metrics import compare_rows
from portal.agent2_he4_runtime import LinuxRuntime,linux_path


def expanded_source(company):
    data=source(company);data['contract_version']='1.2.0'
    # Explicit simulated export facts, not defaults injected by a validator.
    # Preserve transactions, amounts, dates, obligations and vendor cardinality.
    for vendor in data['vendors']:
        vendor.update(phone='0902000001' if company=='C001' else '0902000002',address='SIMULATED ADDRESS '+company,related_party_disclosed_at='')
    return data


def run(output,packet,prepared,build_root):
    private_folder(output);sources=output/'sources';sources.mkdir();snapshots=SnapshotStore(output/'snapshots.sqlite3')
    config=json.loads((packet/'enterprise/node.json').read_bytes());saved=json.loads((packet/'prepared.json').read_bytes())
    if saved['data']!='synthetic_only':raise ValueError('Synthetic saved model packet required')
    before=database_dump(config['model_db']);key_pins={k:digest(Path(config[k]).read_bytes()) for k in ('provisioning_key_file','state_key_file')}
    token=secrets.token_urlsafe(32);header='Bearer '+token;policy=output/'auth.json'
    policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='expanded-check',tenant_id='demo',token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),memberships=[dict(company_id=c,role='accountant',status='active',permissions=['data.import']) for c in ('C001','C002')])])));auth=FileAuthorizer(policy)
    reports=[];contexts={};started=time.monotonic()
    with ExitStack() as stack:
        for name in ('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit','sme_fraud.ml_estimators.CompanyEstimator.fit','sme_fraud.method_store.MethodStore.begin_fit','sme_fraud.method_store.MethodStore.publish'):
            stack.enter_context(patch(name,side_effect=AssertionError('No fit/publish during inference')))
        url=stack.enter_context(worker_service(packet,output/'ckks-worker-state'))
        node_key=Ed25519PrivateKey.from_private_bytes(load_key(config['provisioning_key_file'],purpose='node-signing',required_provider=PROVIDER).material)
        for info in saved['companies']:
            company=info['company_id'];scope=auth.authorize(header,company);check=lambda c=company:auth.authorize(header,c)
            original=source(company);data=expanded_source(company);raw=canonical(data);(sources/(company+'.json')).write_bytes(raw)
            sid=save_snapshot(snapshots,company,data);original_sid=save_snapshot(snapshots,company,original)
            as_of='2026-10-09T00:00:00+07:00';frame=build_from_snapshot(snapshots,scope,sid,as_of,check);old_frame=build_from_snapshot(snapshots,scope,original_sid,as_of,check)
            if frame['features']!=old_frame['features'] or frame['contract']!=old_frame['contract']:raise AssertionError('Expanded master fields changed model inputs')
            local=score_snapshot(snapshots,scope,sid,as_of,methods=(),recheck=check)
            _,manifest,model=_load_model(config['model_db'],scope,info['artifact_id'],check)
            export=export_snapshot(config['model_db'],snapshots.path,auth,header,company,info['artifact_id'],sid,as_of,config['worker_verify_key'])
            if not export.ready:raise ValueError('Saved model unavailable: '+export.local_result()['status'])
            package=export.cloud_package();registration=sign(dict(version=REGISTRATION,node_verify_key=public_hex(node_key),expires_at=package['request']['payload']['expires_at'],policy=package['policy']),node_key)
            clock=time.monotonic();post(url,'/v1/sessions',registration);response=post(url,'/v1/evaluate',package['request']);ml=export.open(response);he_seconds=time.monotonic()-clock
            clear=[]
            for meta,vector,row in zip(frame['rows'],frame['features'],export.rows):
                values,_,reason=row_values(frame,vector,manifest['preprocess'])
                clear.append(dict(record_id=meta['record_id'],revision=meta['revision'],available=row['available'],score=float(model.score(np.asarray([values]))[0]) if row['available'] else None))
            opened=[dict(record_id=r['record_id'],revision=r['revision'],available=r['available'],score=r['raw_score']) for r in ml['rows']]
            parity=compare_rows([r for r in clear if r['available']],[r for r in opened if r['available']],5)
            parity['total_rows_retained']=len(opened);parity['unavailable_rows']=len(opened)-sum(r['available'] for r in opened)
            if not parity['all_scores_within_tolerance'] or parity['material_pair_inversions']:raise AssertionError('CKKS model parity failed')
            result=compare(local,ml,as_of,simulated_only=True);clear_ml=deepcopy(ml)
            for r,plain in zip(clear_ml['rows'],clear):r['raw_score']=plain['score']
            clear_selection=compare(local,clear_ml,as_of,simulated_only=True)
            if result['combined']!=clear_selection['combined']:raise AssertionError('HE changed selected transactions')
            result.update(ml_he_parity=parity,ml_he_seconds=he_seconds,selected_feature_vectors_unchanged=True,new_ml_he_scoring=True,all_rule_evaluations_he=False)
            result.pop('report_sha256');result['report_sha256']=digest(canonical(result));(output/(company+'-comparison.json')).write_bytes(canonical(result))
            (output/(company+'-rules.json')).write_bytes(canonical(local));safe_ml=dict(rows=opened,company_id=company,request_sha256=sha(canonical(package['request'])),worker_boundary=verify(response,config['worker_verify_key'])['worker']);(output/(company+'-ml-parity.json')).write_bytes(canonical(safe_ml))
            plan=prepare_snapshot(snapshots,scope,sid,as_of);contexts[company]=dict(scope=scope,local=local,plan=plan)
            reports.append(dict(company_id=company,baseline=[k[0] for k in result['baseline']],combined=[k[0] for k in result['combined']],added=[k[0] for k in result['added']],coverage=result['coverage'],ml_available=result['ml_available'],ml_unavailable=result['ml_unavailable'],ml_parity=parity,he_seconds=he_seconds))
            print(json.dumps(dict(stage='fresh_ml_and_comparison',company_id=company,baseline=reports[-1]['baseline'],combined=reports[-1]['combined'],max_error=parity['maximum_absolute_error'])),flush=True)
    # Actual Concrete arithmetic through isolated ciphertext-only WSL worker.
    cloud=output/'fhe-worker';cloud.mkdir();build(cloud/'bundle');node=Ed25519PrivateKey.generate();cloud_key=Ed25519PrivateKey.generate();(cloud/'signing.hex').write_text(cloud_key.private_bytes_raw().hex())
    (cloud/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='demo',company_id=c,node_verify_key=public_hex(node),active=True) for c in contexts])))
    builds={k:build_root/v for k,v in dict(statistics='build-statistics-v1',rules='build-rules-difference-v1',graph='build-graph-difference-v1').items()}
    cfg=cloud/'worker.json';cfg.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
    with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    runtime=LinuxRuntime(dict(bundle=str(cloud/'bundle'),config=str(cfg),port=port,distro='Debian',python='/home/sang/.local/share/agent2/he4/bin/python'),ROOT,output/'unused-node',output/'unused-config',Path(sys.executable),output/'logs');runtime.preflight=lambda keys_only=False:None
    bridge=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json');fhe_checks=[]
    try:
        runtime.start();url=f'http://127.0.0.1:{port}'
        for company,record in (('C001','P1_T03'),('C002','P1_T05')):
            ctx=contexts[company];scope=ctx['scope'];planned=next(r for r in ctx['plan']['rows'] if r['record_id']==record);req=planned['branches']['rules']['requests'][0]
            path=output/(company+'-p1');path.mkdir();bundle=builds['rules'];clock=time.monotonic();encrypted=bridge.encrypt(scope,bundle,req['values'],path/'input')
            upload(url,scope,node,public_hex(cloud_key),bridge.public_key(scope,bundle),'public_evaluation_keys')
            for i,h in enumerate(encrypted['arguments_sha256']):
                if upload(url,scope,node,public_hex(cloud_key),path/'input'/f'argument-{i}.cipher','ciphertext')!=h:raise AssertionError('Ciphertext hash mismatch')
            circuit=json.loads((bundle/'manifest.json').read_bytes())['files']['server.zip'];packet=envelope(scope,node,dict(profile='rules',circuit_sha256=circuit,evaluation_keys_sha256=encrypted['evaluation_keys_sha256'],arguments_sha256=encrypted['arguments_sha256'],session_id='expanded-'+company,nonce='request-1'))
            response=post(url,'/v1/evaluate',packet,timeout=600);value=verify(response,public_hex(cloud_key))
            expected=dict(version='he4-worker/0.1.0',tenant_id='demo',company_id=company,session_id='expanded-'+company,nonce='request-1',request_sha256=sha(canonical(packet)),result_sha256=value['result_sha256'],circuit_sha256=circuit)
            if value!=expected:raise AssertionError('FHE response binding')
            download(url,scope,node,value['result_sha256'],path/'result.cipher');actual=decode_payment(bridge.decrypt(scope,bundle,path/'result.cipher',value['result_sha256'],path/'opened.sealed',encrypted))
            from experiments.he4 import circuits
            clear=decode_payment(circuits.p1(*[np.asarray(v) for v in req['values']]))
            if actual!=clear:raise AssertionError('P1 encrypted/clear mismatch')
            local_row=next(r for r in ctx['local']['rows'] if r['record_id']==record);p1=next(r for r in local_row['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='P1')
            facts=p1['details']['invoice_checks'][0]
            if actual['matched']!=p1['matched'] or any(actual[k]!=facts[k] for k in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd')):raise AssertionError('P1 engine parity')
            again=post(url,'/v1/results',envelope(scope,node,dict(session_id='expanded-'+company,nonce='request-1',request_sha256=sha(canonical(packet)))))
            if again!=response:raise AssertionError('Committed ciphertext changed')
            fhe_checks.append(dict(company_id=company,record_id=record,actual_fhe=True,engine_parity=True,exact_integer_parity=True,same_committed_ciphertext=True,seconds=time.monotonic()-clock,actual=actual))
            (output/'fhe-progress.json').write_bytes(canonical(fhe_checks));print(json.dumps(dict(stage='fhe_p1',company_id=company,parity=True,seconds=fhe_checks[-1]['seconds'])),flush=True)
    finally:runtime.stop()
    if before!=database_dump(config['model_db']) or key_pins!={k:digest(Path(config[k]).read_bytes()) for k in key_pins}:raise AssertionError('Saved model or keys changed')
    result=dict(status='technical_pass_with_partial_he_coverage',companies=reports,p1_native_he=fhe_checks,baseline_rule_ids=['P1','E3','B5','E4'],rules_without_he=['E3','B5','E4'],all_rule_evaluations_he=False,full_he_baseline_available=False,new_model_fit=False,live_services_changed=False,supervisor_preflight_mocked=True,accuracy=None,seconds=time.monotonic()-started)
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');write_report(output,result);print(json.dumps(dict(status=result['status'],seconds=result['seconds'])),flush=True)


def write_report(output,result):
    lines=['# Kiểm chứng HE và baseline bốn luật','',
        '**Kết quả kỹ thuật trong phạm vi HE hiện có. Baseline P1/E3/B5/E4 tính tại DN; E3/B5/E4 chưa có HE.**','',
        '| DN | Luật chọn / tối đa | Kết hợp / tối đa | ML bổ sung | Sai lệch điểm ML lớn nhất |','|---|---:|---:|---|---:|']
    rows=[]
    for c in result['companies']:
        names=', '.join(c['added']);error=c['ml_parity']['maximum_absolute_error']
        lines.append(f"| {c['company_id']} | {len(c['baseline'])}/5 | {len(c['combined'])}/5 | {names} | {error:.8f} |")
        rows.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in (c['company_id'],str(len(c['baseline']))+'/5',str(len(c['combined']))+'/5',names,f'{error:.8f}'))+'</tr>')
    lines+=['','P1 native FHE: '+str(len(result['p1_native_he']))+'/2 ca khớp nguyên số tiền và matched. ML CKKS dùng model đã fit riêng DN, chấm mới; tập lựa chọn không đổi. Có đổi thứ tự các điểm gần nhau trong dung sai, không có đảo cặp vượt dung sai.','',
        'Cùng nguồn/kỳ, tối đa 5 lượt mỗi phương án. E3/B5/E4 là master-quality, không tự tăng điểm/ưu tiên giao dịch. Còn 31 luật chưa nối snapshot. Dữ liệu mô phỏng, chưa có đánh giá hữu ích hoặc thời gian rà thực tế; không kết luận tăng độ chính xác.','',
        'T06/T07 là nhóm đồng thời, không đếm thành hai vụ gian lận độc lập. T04 là điều chỉnh âm, P1 không áp dụng. Không gửi dữ liệu rõ lên worker, không fit/model/khóa/quyền hay queue live bị thay đổi.','']
    (output/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    page='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent2 — HE và baseline mở rộng</title>
<style>body{font:17px/1.65 system-ui,sans-serif;background:#f3f6fa;color:#20334b;margin:0}main{max-width:1120px;margin:30px auto;padding:30px;background:white;border-radius:16px}h1{font-size:29px}.notice{padding:18px;background:#fff3d8;border-radius:10px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #d5dee8;text-align:left;padding:12px}th{background:#e8f2ef}.scroll{overflow:auto}a{color:#05665d}</style>
<main><h1>Kiểm chứng tính mã hóa và so sánh luật với ML</h1><p><strong>C001/C002 · Dữ liệu mô phỏng · Ngân sách tối đa 5 giao dịch/phương án/DN</strong></p>
<p class="notice"><strong>Chưa có baseline bốn luật hoàn toàn HE.</strong> P1 và ML đã được tính trên bản mã trong lượt này. E3/B5/E4 vẫn được đánh giá tại node doanh nghiệp; không gửi dữ liệu rõ cho worker.</p>
<div class="scroll"><table><thead><tr><th>Doanh nghiệp</th><th>Chỉ luật</th><th>Luật + ML</th><th>ML bổ sung</th><th>Sai lệch ML lớn nhất</th></tr></thead><tbody>ROWS</tbody></table></div>
<p>P1 FHE: P1COUNT/2 ca khớp số tiền nguyên và kết luận với bản tính rõ/engine. ML CKKS dùng model riêng từng DN đã fit, chấm mới. Thứ tự tuyệt đối có đổi ở các điểm gần nhau trong dung sai; không có đảo cặp vượt dung sai và tập lựa chọn không đổi.</p>
<p>Baseline gồm P1/E3/B5/E4. Các kiểm tra master không tự trở thành cảnh báo giao dịch, nên baseline vẫn chọn 3 khoản. Hai khoản còn lại do ML bổ sung vào chỗ trống. Chưa có 31 evaluator snapshot còn lại.</p>
<p><strong>Chưa chứng minh ML tốt hơn.</strong> Chưa có phiếu rà xác minh lợi ích/thời gian thực tế. T04 là điều chỉnh âm; T06/T07 thuộc cùng một nhóm đồng thời. Không xem 5 khoản được chọn là 5 vụ gian lận.</p>
<p><a href="report.json">Báo cáo JSON</a> · <a href="C001-comparison.json">Chi tiết C001</a> · <a href="C002-comparison.json">Chi tiết C002</a></p></main></html>'''
    (output/'REPORT.html').write_text(page.replace('ROWS',''.join(rows)).replace('P1COUNT',str(len(result['p1_native_he']))),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--packet',type=Path,default=ROOT/'.runtime/he-company-demo');p.add_argument('--prepared',type=Path,default=ROOT.parent/'.runtime/he4/portal-key-contexts');p.add_argument('--build-root',type=Path,default=ROOT.parent/'.runtime/he4');a=p.parse_args();run(a.output.resolve(),a.packet.resolve(),a.prepared.resolve(),a.build_root.resolve())
