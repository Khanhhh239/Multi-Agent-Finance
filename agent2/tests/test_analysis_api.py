"""HTTP snapshot analysis, role DTOs, causal evidence and read-only guarantees."""
from contextlib import closing
import copy
from email.message import Message
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import jsonschema

from sme_fraud.auth import FileAuthorizer
from sme_fraud.analysis_api import handle_analysis
from sme_fraud.import_files import canonical
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from finance_input import AccessScope
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.method_adapters import score_snapshot
from test_p1_evaluation import payments,refresh,DAY
from test_snapshot_features import scope,committed
from test_validation_backend import policy_for

SCHEMA=json.loads((Path(__file__).parents[1]/'sme_fraud/snapshot_analysis.schema.json').read_text('utf-8'))


def sample():
    data=payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))])
    data['vendors'][0]['name']='North Harbor Equipment'
    peer=copy.deepcopy(data['vendors'][0]);peer.update(record_id='V_PEER',name='North Harbour Equipment')
    peer['source']['record_id']='V_PEER';data['vendors'].append(peer)
    return data


class AnalysisApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.token=secrets.token_urlsafe(32);self.policy=policy_for(self.token)
        self.policy_path=self.root/'policy.json';self.save_policy()
        self.store=SnapshotStore(self.root/'snapshots.sqlite3');self.data=sample()
        self.sid=committed(self.store,data=self.data)
        self.authorizer=FileAuthorizer(self.policy_path)
        self.server=make_server(0,self.authorizer,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
    def save_policy(self):self.policy_path.write_text(json.dumps(self.policy),encoding='utf-8')
    def director(self):self.policy['principals'][0]['memberships'][0]['role']='director';self.save_policy()
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def call(self,body=None,*,company='C001',snapshot_id=None,headers=None,method='POST',suffix='',raw=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30);self.addCleanup(connection.close)
        path=f'/api/v1/companies/{company}/snapshots/{snapshot_id or self.sid}/analyze'+suffix
        h={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'};h.update(headers or {})
        connection.request(method,path,body=raw if raw is not None else canonical(body if body is not None else dict(as_of=DAY(5))),headers=h)
        response=connection.getresponse();data=response.read();return response.status,json.loads(data)
    def valid(self,**kwargs):
        status,result=self.call(**kwargs);self.assertEqual(status,200,result);jsonschema.validate(result,SCHEMA);return result
    def counts(self):
        with closing(sqlite3.connect(self.store.path)) as conn:
            return {t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('snapshots','imports','request_receipts','import_audit')}

    def test_review_business_DTO_and_zero_point_E3_signal(self):
        result=self.valid();self.assertEqual(result['row_count'],2)
        row=next(r for r in result['rows'] if r['transaction_id']=='NEW')
        self.assertEqual(row['checks']['payment_invoice']['status'],'needs_review')
        self.assertEqual(row['checks']['payment_invoice']['facts'][0]['excess_vnd'],1_000_000)
        self.assertEqual(row['checks']['vendor_names']['status'],'needs_review')
        self.assertFalse(result['summary']['analysis_complete']);self.assertNotIn('aggregate',result)
        forbidden={'P1','E3','score','intrinsic_points','rule_id','algorithm','threshold','implementation','configuration','features','methods','native_rule_diagnostics'}
        def check(value):
            if isinstance(value,dict):
                self.assertFalse(forbidden&set(value),forbidden&set(value))
                for item in value.values():check(item)
            elif isinstance(value,list):
                for item in value:check(item)
        check(result)

    def test_director_technical_view_contains_only_P1_E3_and_null_aggregate(self):
        self.director();result=self.valid(body=dict(as_of=DAY(5),view='technical'))
        self.assertTrue(result['implementation']);self.assertIsNone(result['aggregate']['score'])
        for row in result['rows']:
            self.assertEqual(set(row['rules']),{'P1','E3'})
            self.assertEqual(row['rules']['E3']['score'],0);self.assertTrue(row['rules']['E3']['matched'])
        self.assertEqual(result['rows'][-1]['rules']['P1']['score'],20)

    def test_opt_in_vendor_identity_snapshot_runs_through_authenticated_HTTP(self):
        from sme_fraud.vendor_identity_demo import prepare
        data,_,as_of=prepare();data['tenant_id']='demo'
        for records in data.values():
            if isinstance(records,list):
                for r in records:r['tenant_id']='demo'
        sid=committed(self.store,data=data,key='identity-http')
        with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('No fit')) as fit:
            review=self.valid(body=dict(as_of=as_of),snapshot_id=sid)
            self.director();result=self.valid(body=dict(as_of=as_of,view='technical'),snapshot_id=sid)
        fit.assert_not_called();self.assertEqual(result['row_count'],1);self.assertEqual(result['snapshot']['contract_version'],'1.2.0')
        for code in ('B5','E4'):
            r=next(r for r in result['rows'][0]['rule_coverage']['rules'] if r['rule_id']==code)
            self.assertEqual(r['status'],'evaluated_hit');self.assertEqual(r['score'],0);self.assertTrue(r['evidence_refs'])
            self.assertEqual(r['details']['source_rule_id'],'B5');self.assertTrue(r['details']['evidence'])
        self.assertNotIn('rule_coverage',review['rows'][0]);self.assertIsNone(result['aggregate']['score'])

    def test_full_rule_source_snapshot_runs_all_35_through_authenticated_HTTP(self):
        from sme_fraud.native_rule_demo import scenario
        from sme_fraud.rule_snapshot import CONTRACT
        b,_=scenario('B1',True);b['tenant_id']='demo';data=dict(contract_version=CONTRACT,tenant_id='demo',company_id='C001',source=b,candidate_transaction_ids=[b['tables']['transactions'][-1]['transaction_id']])
        sid=committed(self.store,data=data,key='native-profile-http')
        status,review=self.call(dict(as_of=b['as_of']),snapshot_id=sid);self.assertEqual(status,200,review)
        self.assertEqual(review['version'],'snapshot-rule-analysis/1.0.0');self.assertTrue(any(c['needs_review'] for c in review['rows'][0]['checks'].values()));self.assertNotIn('catalogue_results',review)
        denied,_=self.call(dict(as_of=b['as_of'],view='technical'),snapshot_id=sid);self.assertEqual(denied,403)
        self.director();status,technical=self.call(dict(as_of=b['as_of'],view='technical'),snapshot_id=sid);self.assertEqual(status,200,technical)
        self.assertEqual(len(technical['catalogue']),35);self.assertEqual(len(technical['catalogue_results']),35);self.assertFalse(technical['he_execution'])
        self.assertTrue(next(c for c in technical['catalogue_results'] if c['rule_id']=='B1')['matched'])

    def test_full_rule_catalogue_is_read_only_company_scoped_and_director_only(self):
        def get(company='C001',method='GET'):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30);self.addCleanup(conn.close)
            conn.request(method,f'/api/v1/companies/{company}/rules/catalogue',headers={'Authorization':'Bearer '+self.token});response=conn.getresponse();return response.status,json.loads(response.read())
        self.assertEqual(get()[0],403);self.director();status,data=get();self.assertEqual(status,200);self.assertEqual(len(data['rules']),35);self.assertTrue(all(r['implemented'] for r in data['rules']))
        self.assertEqual(get('C002')[0],403);self.assertEqual(get(method='POST')[0],405)

    def test_accountant_cannot_request_technical_view(self):
        with patch('sme_fraud.analysis_api.analyze_snapshot') as scorer:
            status,result=self.call(dict(as_of=DAY(5),view='technical'))
        self.assertEqual(status,403);self.assertEqual(result['errors'][0]['code'],'TECHNICAL_VIEW_DENIED');scorer.assert_not_called()

    def test_client_role_and_scores_are_rejected(self):
        for field in ('role','company_id','tenant_id','score','rules','artifacts','model_id','snapshot_id'):
            with self.subTest(field=field):
                status,_=self.call(dict(as_of=DAY(5),**{field:'forged'}));self.assertEqual(status,400)

    def test_foreign_company_denied_and_director_has_no_implicit_access(self):
        self.director()
        with patch('sme_fraud.analysis_api.analyze_snapshot') as scorer:
            status,_=self.call(company='C002')
        self.assertEqual(status,403);scorer.assert_not_called()

    def test_roles_and_same_transaction_ids_are_separate_per_company(self):
        from sme_fraud.p1_inputs import export_manifest
        data=copy.deepcopy(self.data)
        for records in data.values():
            if isinstance(records,list):
                for record in records:record['company_id']='C002'
        data['companies'][0]['record_id']='C002';data['companies'][0]['source']['record_id']='C002'
        data['transactions'][-1]['amount_vnd']=1_000_000;data['payment_allocations'][-1]['amount_vnd']=1_000_000
        for claim in data['payment_history_coverage']:claim['manifest']=export_manifest(data,claim)
        writer=AccessScope('demo',frozenset({'C002'}),'other-writer',frozenset({'data.import'}))
        from test_snapshots import commit_fields
        draft=self.store.upload(writer,canonical(data),'other.json','other-company-upload')
        preview=self.store.preview(writer,draft['import_id'],1)
        second=self.store.commit(writer,draft['import_id'],commit_fields(preview),'other-company-commit')['snapshot']['snapshot_id']
        self.policy['principals'][0]['memberships'].append(dict(company_id='C002',role='director',status='active',permissions=['data.import']))
        self.save_policy()
        first=self.valid();self.assertEqual(first['rows'][-1]['checks']['payment_invoice']['facts'][0]['excess_vnd'],1_000_000)
        other=self.valid(company='C002',snapshot_id=second,body=dict(as_of=DAY(5),view='technical'))
        self.assertEqual(other['rows'][-1]['rules']['P1']['score'],0)
        self.assertNotEqual(first['analysis_id'],other['analysis_id'])
        self.assertEqual(self.call(company='C002',body=dict(as_of=DAY(5),view='technical'))[0],404)
        self.assertEqual(self.call(dict(as_of=DAY(5),view='technical'))[0],403)

    def test_other_tenant_same_company_cannot_read_snapshot(self):
        self.policy['principals'][0]['tenant_id']='another';self.save_policy()
        status,result=self.call();self.assertEqual(status,404)
        self.assertNotIn(self.sid,json.dumps(result));self.assertNotIn('OLD',json.dumps(result))

    def test_unknown_snapshot_is_scoped_404(self):
        status,_=self.call(snapshot_id='snp_'+'f'*32);self.assertEqual(status,404)

    def test_missing_or_revoked_credentials_are_denied(self):
        self.assertEqual(self.call(headers={'Authorization':''})[0],401)
        self.policy['principals'][0]['status']='revoked';self.save_policy()
        self.assertEqual(self.call()[0],401)

    def test_unknown_role_or_permission_from_policy_cannot_bypass(self):
        self.policy['principals'][0]['memberships'][0]['permissions']=[];self.director()
        self.assertEqual(self.call(dict(as_of=DAY(5),view='technical'))[0],403)

    def test_host_origin_query_and_unsupported_methods(self):
        self.assertEqual(self.call(headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.call(headers={'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.call(suffix='?view=technical')[0],400)
        for method in ('GET','PUT'):self.assertEqual(self.call(method=method)[0],405)

    def test_invalid_body_view_time_and_snapshot_id(self):
        for body in ({},[],dict(as_of=True),dict(as_of='2026-10-02T09:00:00'),dict(as_of=DAY(5),view='admin')):
            with self.subTest(body=body):self.assertEqual(self.call(body)[0],400)
        self.assertEqual(self.call(snapshot_id='not-a-snapshot')[0],400)
        self.assertEqual(self.call(raw=b'{"as_of":"a","as_of":"b"}')[0],400)

    def test_equivalent_times_retry_and_views_have_same_analysis_binding(self):
        before=self.counts();first=self.valid();second=self.valid(body=dict(as_of='2026-10-05T02:00:00Z'))
        self.assertEqual(first,second)
        self.director();technical=self.valid(body=dict(as_of=DAY(5),view='technical'))
        self.assertEqual(technical['analysis_id'],first['analysis_id']);self.assertEqual(before,self.counts())

    def test_no_fit_and_all_available_method_adapters_are_requested(self):
        with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('Implicit fit')) as fit,patch('sme_fraud.method_adapters.score_snapshot',wraps=score_snapshot) as scorer:
            result=self.valid()
        from sme_fraud.method_adapters import METHODS
        fit.assert_not_called();self.assertEqual(scorer.call_args.kwargs['methods'],METHODS);self.assertEqual(result['row_count'],2)
        self.assertEqual(set(result['rows'][0]['branches']),{'rules','statistics','graph','ml'})

    def test_committed_verified_document_does_not_require_new_verification_permission(self):
        from test_p1_inputs import p1_bundle
        data=copy.deepcopy(self.data);doc=copy.deepcopy(p1_bundle()['supporting_documents'][0])
        doc.update(effective_at=DAY(1),observed_at=DAY(1),source_kind='original',verification_status='verified',
            subject_refs=[dict(table='transactions',record_id='OLD',revision=1)],
            verification=dict(verified_by='synthetic-writer',verified_at=DAY(1),basis='Authorization fixture only, not a real document'))
        doc['source']['is_simulated']=False;data['supporting_documents']=[doc]
        writer=AccessScope('demo',frozenset({'C001'}),'synthetic-writer',frozenset({'data.import','evidence.verify'}))
        from test_snapshots import commit_fields
        draft=self.store.upload(writer,canonical(data),'verified.json','verified-api-upload')
        preview=self.store.preview(writer,draft['import_id'],1)
        self.sid=self.store.commit(writer,draft['import_id'],commit_fields(preview),'verified-api-commit')['snapshot']['snapshot_id']
        before=self.store.get_snapshot(scope(),self.sid,data=True)
        result=self.valid();self.assertEqual(result['row_count'],2)
        self.assertEqual(before,self.store.get_snapshot(scope(),self.sid,data=True))

    def test_review_allowlist_excludes_new_internal_fields_recursively(self):
        def extra(*args,**kwargs):
            result=score_snapshot(*args,**kwargs)
            for row in result['rows']:
                for rule in row['methods']['rules']['details']['rule_results']['rules']:
                    rule['private_config']='DO_NOT_EXPOSE';rule['details']['private_model']={'algorithm':'DO_NOT_EXPOSE','threshold':1234}
            return result
        with patch('sme_fraud.method_adapters.score_snapshot',side_effect=extra):result=self.valid()
        self.assertNotIn('DO_NOT_EXPOSE',json.dumps(result));self.assertNotIn('private_model',json.dumps(result))

    def test_mismatched_analysis_snapshot_binding_is_rejected(self):
        def changed(*args,**kwargs):
            result=score_snapshot(*args,**kwargs);result['snapshot']['checksum']='0'*64;return result
        with patch('sme_fraud.method_adapters.score_snapshot',side_effect=changed):status,result=self.call()
        self.assertEqual(status,500);self.assertNotIn('rows',result)

    def test_large_signed_VND_values_are_preserved_as_integers(self):
        cap=90_071_992_547_409_932
        data=payments([('OLD',cap-2,DAY(1)),('NEW',4,DAY(2))],cap=cap)
        self.sid=committed(self.store,data=data,key='large-vnd-upload')
        result=self.valid();row=next(r for r in result['rows'] if r['transaction_id']=='NEW')
        fact=row['checks']['payment_invoice']['facts'][0]
        self.assertEqual(fact['invoice_gross_vnd'],cap);self.assertEqual(fact['cumulative_paid_vnd'],cap+2);self.assertEqual(fact['excess_vnd'],2)

    def test_negative_adjustment_is_returned_and_not_mislabeled_as_no_hit(self):
        data=payments([('OLD',12_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))],cap=12_000_000)
        self.sid=committed(self.store,data=data,key='signed-analysis-upload')
        result=self.valid();self.assertEqual(result['row_count'],3)
        adjustment=next(r for r in result['rows'] if r['transaction_id']=='REDUCE')
        self.assertEqual(adjustment['amount_vnd'],-2_000_000)
        self.assertEqual(adjustment['checks']['payment_invoice']['status'],'not_applicable')
        self.assertIsNone(adjustment['checks']['payment_invoice']['needs_review'])

    def test_partial_source_does_not_disable_E3_or_become_zero(self):
        data=copy.deepcopy(self.data);data['payment_history_coverage']=[]
        self.sid=committed(self.store,data=data,key='missing-coverage-upload')
        review=self.valid();self.director();technical=self.valid(body=dict(as_of=DAY(5),view='technical'))
        for row in review['rows']:
            p=row['checks']['payment_invoice'];self.assertEqual(p['status'],'unavailable');self.assertIsNone(p['needs_review']);self.assertTrue(p['missing_sources'])
            self.assertEqual(row['checks']['vendor_names']['status'],'needs_review')
        self.assertTrue(all(r['rules']['P1']['score'] is None for r in technical['rows']))

    def test_simultaneous_group_is_unique_with_refs_on_every_member(self):
        data=payments([('OLD',4_000_000,DAY(1)),('A',4_000_000,DAY(2)),('B',4_000_000,DAY(2))])
        self.sid=committed(self.store,data=data,key='simultaneous-upload')
        result=self.valid();self.assertEqual(len(result['groups']),1);group=result['groups'][0]
        self.assertTrue(group['needs_review']);self.assertEqual(group['cumulative_paid_vnd'],12_000_000)
        for row in result['rows'][1:]:
            p=row['checks']['payment_invoice'];self.assertEqual(p['status'],'needs_review');self.assertEqual(p['group_refs'],[group['group_id']])
        self.director();technical=self.valid(body=dict(as_of=DAY(5),view='technical'))
        self.assertEqual(len(technical['groups']),1)
        for row in technical['rows'][1:]:
            p=row['rules']['P1'];self.assertFalse(p['matched']);self.assertEqual(p['score'],0)
            self.assertNotIn('simultaneous_checks',p['details']);self.assertEqual(p['details']['simultaneous_group_refs'],[technical['groups'][0]['group_id']])

    def test_empty_asof_and_late_invoice_never_rewrite_past(self):
        empty=self.valid(body=dict(as_of='2026-09-01T00:00:00+07:00'));self.assertEqual(empty['row_count'],0);self.assertEqual(empty['groups'],[])
        data=copy.deepcopy(self.data);data['invoices'][0]['observed_at']=DAY(4);refresh(data)
        data['payment_history_coverage']=[c for c in data['payment_history_coverage'] if c['invoice_refs']]
        self.sid=committed(self.store,data=data,key='late-invoice-upload')
        before=self.valid(body=dict(as_of=DAY(2)));after=self.valid(body=dict(as_of=DAY(5)))
        self.assertEqual(before['rows'],after['rows'])
        self.assertTrue(all(r['checks']['payment_invoice']['status']=='unavailable' for r in after['rows']))

    def test_limits_reject_without_truncation_or_invoking_scorer(self):
        for constant in ('MAX_TRANSACTIONS','MAX_SOURCE_RECORDS'):
            with self.subTest(constant=constant),patch('sme_fraud.snapshot_analysis.'+constant,1),patch('sme_fraud.method_adapters.score_snapshot') as scorer:
                status,_=self.call();self.assertEqual(status,413);scorer.assert_not_called()
        with patch('sme_fraud.analysis_api.MAX_OUTPUT_BYTES',1):self.assertEqual(self.call()[0],413)

    def test_role_downgrade_during_compute_denies_entire_result(self):
        self.director()
        def downgrade(*args,**kwargs):
            result=score_snapshot(*args,**kwargs);self.policy['principals'][0]['memberships'][0]['role']='accountant';self.save_policy();return result
        with patch('sme_fraud.method_adapters.score_snapshot',side_effect=downgrade):
            status,result=self.call(dict(as_of=DAY(5),view='technical'))
        self.assertEqual(status,403);self.assertNotIn('rows',result);self.assertNotIn(self.token,json.dumps(result))

    def test_permission_revocation_during_compute_denies_review_result(self):
        def revoke(*args,**kwargs):
            result=score_snapshot(*args,**kwargs);self.policy['principals'][0]['status']='revoked';self.save_policy();return result
        with patch('sme_fraud.method_adapters.score_snapshot',side_effect=revoke):
            status,result=self.call()
        self.assertEqual(status,401);self.assertNotIn('rows',result)

    def test_storage_tamper_returns_integrity_error(self):
        with closing(sqlite3.connect(self.store.path)) as conn:
            conn.execute('DROP TRIGGER snapshots_update');conn.execute('UPDATE snapshots SET data_json=?',(b'{}',));conn.commit()
        status,result=self.call();self.assertEqual(status,500);self.assertEqual(result['errors'][0]['code'],'ARTIFACT_INTEGRITY');self.assertNotIn('rows',result)

    def test_internal_error_is_sanitized_and_does_not_return_partial_rows(self):
        with patch('sme_fraud.analysis_api.analyze_snapshot',side_effect=ValueError('private-secret-row')):
            status,result=self.call()
        self.assertEqual(status,500);self.assertNotIn('private-secret-row',json.dumps(result));self.assertNotIn('rows',result)

    def test_authorization_happens_before_body_and_snapshot_read(self):
        class NoBody:
            def read(self,*args):raise AssertionError('Unauthorized body read')
        headers=Message();headers['Host']='127.0.0.1:8766'
        handler=SimpleNamespace(path=f'/api/v1/companies/C001/snapshots/{self.sid}/analyze',server=SimpleNamespace(server_port=8766),headers=headers,rfile=NoBody(),respond=lambda status,value:captured.append((status,value)))
        captured=[]
        with patch('sme_fraud.analysis_api.analyze_snapshot') as scorer:
            self.assertTrue(handle_analysis(handler,self.authorizer,self.store,'POST'))
        self.assertEqual(captured[0][0],401);scorer.assert_not_called()

    def test_storage_unconfigured_is_503(self):
        handler=SimpleNamespace(path=f'/api/v1/companies/C001/snapshots/{self.sid}/analyze',server=SimpleNamespace(server_port=8766))
        from io import BytesIO
        body=canonical(dict(as_of=DAY(5)));handler.headers=Message()
        for k,v in {'Host':'127.0.0.1:8766','Authorization':'Bearer '+self.token,'Content-Type':'application/json','Content-Length':str(len(body))}.items():handler.headers[k]=v
        handler.rfile=BytesIO(body);handler.connection=SimpleNamespace(settimeout=lambda n:None)
        captured=[];handler.respond=lambda status,value:captured.append((status,value))
        self.assertTrue(handle_analysis(handler,self.authorizer,None,'POST'));self.assertEqual(captured[0][0],503)


if __name__=='__main__':unittest.main()
