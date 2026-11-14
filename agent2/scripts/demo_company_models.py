"""Two-company durable fit -> fresh-process inference, with synthetic sources."""
import argparse
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from demo_method_scores import canonical_source
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical
from sme_fraud.snapshots import SnapshotStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default=str(ROOT/'.runtime/company_model_demo'/uuid.uuid4().hex))
    args=parser.parse_args();out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    database=ROOT/'.runtime/company_model_demo'
    run=uuid.uuid4().hex;owner=secrets.token_urlsafe(32);reader=secrets.token_urlsafe(32)
    summaries=[]
    with tempfile.TemporaryDirectory(prefix='company_model_demo_') as temporary:
        temp=Path(temporary);policy=temp/'policy.json';owner_file=temp/'owner.token';reader_file=temp/'reader.token'
        owner_file.write_text(owner,encoding='utf-8');reader_file.write_text(reader,encoding='utf-8')
        def principal(actor,token,fit):
            return dict(actor_id=actor,tenant_id='demo',token_sha256=hashlib.sha256(token.encode()).hexdigest(),status='active',
                expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                memberships=[dict(company_id=c,role='director' if fit else 'accountant',status='active',
                                  permissions=['data.import','model.fit'] if fit else ['data.import']) for c in ('C001','C002')])
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[principal('fit-demo',owner,True),principal('score-demo',reader,False)])))
        auth=FileAuthorizer(policy);snapshots=SnapshotStore(database/'snapshots.sqlite3')
        for company,method in (('C001','isolation_forest'),('C002','ecod')):
            source=canonical_source()
            if company=='C002':
                for table,rows in source.items():
                    if isinstance(rows,list):
                        for row in rows:
                            row['company_id']=company
                            if table=='companies':row['record_id']=company;row['name']='Doanh nghiệp mô phỏng C002'
                            if 'amount_vnd' in row:row['amount_vnd']*=2
                            for line in row.get('accounting_lines',[]):line['debit_vnd']*=2;line['credit_vnd']*=2
            scope=auth.authorize('Bearer '+owner,company);check=lambda:auth.authorize('Bearer '+owner,company)
            draft=snapshots.upload(scope,canonical(source),'demo-'+company+'.json',run+company+'-upload',check)
            preview=snapshots.preview(scope,draft['import_id'],1,check)
            body={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')};body.update(expected_revision=1,acknowledge=True)
            identity=snapshots.commit(scope,draft['import_id'],body,run+company+'-commit',check)['snapshot']['snapshot_id']
            config=dict(version='company-fit-config/1.0.0',snapshot_id=identity,method_id=method,missing_policy='median_flags',
                minimum_history=5,profile_id='synthetic-technical-demo-not-D03-production',evaluation_mode='backtest',
                history_start='2026-09-02T00:00:00+07:00',history_end='2026-09-12T00:00:00+07:00',
                reference_start='2026-09-15T00:00:00+07:00',reference_end='2026-09-20T00:00:00+07:00',evaluation_start='2026-10-01T00:00:00+07:00')
            config_file=out/(company+'-fit-config.json');config_file.write_bytes(canonical(config))
            common=['--snapshot-db',str(database/'snapshots.sqlite3'),'--model-db',str(database/'models.sqlite3'),
                    '--auth-file',str(policy),'--company',company]
            fit_output=out/(company+'-fit.json')
            command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.method_jobs','fit',*common,'--token-file',str(owner_file),
                     '--config',str(config_file),'--idempotency-key',run+company+'-fit','--output',str(fit_output)]
            fitted=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            (out/(company+'-fit.log')).write_text(fitted.stdout+fitted.stderr,encoding='utf-8')
            if fitted.returncode:raise RuntimeError(fitted.stdout+fitted.stderr)
            result=json.loads(fit_output.read_text('utf-8'));assert result['job']['status']=='succeeded'
            artifact_id=result['job']['artifact_id'];manifest=result['manifest']
            mapping=out/(company+'-artifacts.json');mapping.write_bytes(canonical({method:artifact_id}))
            output=out/(company+'-scores.json')
            command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.method_jobs','score',*common,'--token-file',str(reader_file),
                     '--snapshot-id',identity,'--as-of','2026-10-06T00:00:00+07:00','--artifacts-file',str(mapping),'--output',str(output)]
            scored=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            (out/(company+'-score.log')).write_text(scored.stdout+scored.stderr,encoding='utf-8')
            if scored.returncode:raise RuntimeError(scored.stdout+scored.stderr)
            scores=json.loads(output.read_text('utf-8'));new=[r for r in scores['rows'] if r['record_id'].startswith('T')]
            assert len(new)==5 and all(r['methods'][method]['available'] for r in new)
            assert len(manifest['feature_contract']['columns'])==33
            summaries.append(dict(company_id=company,method_id=method,snapshot_id=identity,job_id=result['job']['job_id'],
                artifact_id=artifact_id,model_version=manifest['model_version'],feature_contract_fingerprint=manifest['feature_contract_fingerprint'],
                history_rows=manifest['history_rows'],reference_rows=manifest['reference_rows'],new_rows_scored=len(new),
                preprocess_version=manifest['preprocess_version'],missing_policy=manifest['preprocess']['policy'],
                input_feature_count=33,model_input_width=len(manifest['preprocess']['output_columns']),
                dropped_training_columns=manifest['preprocess']['dropped_columns'],separate_fit_and_score_processes=True))
            print(company,method,'| train:',manifest['history_rows'],'reference:',manifest['reference_rows'],'| chấm mới:',len(new),'/ 5')
        assert len({s['artifact_id'] for s in summaries})==2
    (out/'summary.json').write_bytes(canonical(dict(data_kind='synthetic_technical_demo_not_accuracy',companies=summaries,
        model_database=str(database/'models.sqlite3'),active_model_changed=False,labels_used=False)))
    print('Hai doanh nghiệp có artifact riêng; score nạp từ DB bằng tiến trình mới, không fit lại.')
    print('Báo cáo demo:',out/'summary.json')
    return 0


if __name__=='__main__':raise SystemExit(main())
