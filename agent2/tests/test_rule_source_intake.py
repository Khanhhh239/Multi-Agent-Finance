"""Multi-source import, declared coverage and actual rule availability."""
import base64
from copy import deepcopy
import csv
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sme_fraud.import_files import canonical,digest,parse_file,mapping_contract,ImportFailure
from sme_fraud.native_rule_demo import scenario
from sme_fraud.rule_source_intake import catalogue,inspect,PACKAGE,ENGINE_FIELDS
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.snapshot_analysis import analyze_snapshot
from test_native_rule_node import scope
from test_snapshots import commit_fields


def csv_bytes(rows,fields):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else str(v).lower() if type(v) is bool else v for k,v in row.items()})
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def package(source,*,rename=False,omit=()):
    entries=[];fields=catalogue()
    for table,rows in source['tables'].items():
        if table in omit:continue
        cols=sorted({k for row in rows for k in row}) if rows else fields[table]
        exported=deepcopy(rows);name=table+'.csv'
        if rename and table=='transactions':
            name='so-chi.csv';cols=[('MaGD' if c=='transaction_id' else c) for c in cols]
            for row in exported:row['MaGD']=row.pop('transaction_id')
        entries.append(dict(name=name,content_b64=base64.b64encode(csv_bytes(exported,cols)).decode()))
    return canonical(dict(format=PACKAGE,files=entries))


def settings(source,*,rename=False,coverage=True):
    result=dict(profile='rule_sources',metadata={k:source[k] for k in ('as_of','source_id','is_simulated')},sources={},tables={},
                candidate_transaction_ids=[source['tables']['transactions'][-1]['transaction_id']])
    if coverage:result['coverage']={name:{k:v for k,v in claim.items() if k not in ('record_count','records_sha256')} for name,claim in source['coverage'].items()}
    if rename:result.update(sources={'so-chi.csv':'transactions'},tables={'transactions':{'MaGD':'transaction_id'}})
    return mapping_contract(result)


class RuleSourceIntake(unittest.TestCase):
    def setUp(self):self.source,_=scenario('B1',True);self.scope=scope()
    def parse(self,raw=None,config=None):return parse_file(raw or package(self.source),config or settings(self.source),self.scope,'sources.json')
    def test_native_csv_columns_scope_and_signed_amounts_are_preserved(self):
        self.source,_=scenario('F1',True)
        self.source['tables']['transactions'][0]['amount_vnd']=-123456789012345678
        raw=package(self.source,rename=True);config=settings(self.source,rename=True)
        parsed,report=self.parse(raw,config)
        self.assertNotEqual(report['status'],'rejected',report['errors'])
        row=json.loads(parsed)['source']['tables']['transactions'][0]
        self.assertEqual(row['amount_vnd'],-123456789012345678)
        self.assertIs(type(row['amount_vnd']),int)
        self.assertNotIn('MaGD',row)
        self.assertEqual(len(report['rule_readiness']['checks']),35)
        self.assertNotIn('rule_id',canonical(report['rule_readiness']).decode())
    def test_inspect_returns_headers_and_counts_but_no_record_values(self):
        raw=package(self.source,rename=True);info=inspect(raw,'sources.json')
        tx=next(s for s in info['sources'] if s['key']=='so-chi.csv')
        self.assertIn('MaGD',tx['headers']);self.assertEqual(tx['row_count'],1)
        self.assertEqual(info['source_hash'],digest(raw))
        self.assertNotIn(self.source['tables']['transactions'][0]['transaction_id'],canonical(info).decode())
    def test_coverage_not_supplied_never_becomes_complete_automatically(self):
        parsed,report=self.parse(config=settings(self.source,coverage=False))
        self.assertNotEqual(report['status'],'rejected',report['errors'])
        self.assertEqual(json.loads(parsed)['source']['coverage'],{})
        self.assertEqual(report['rule_readiness']['summary']['ready'],0)
        self.assertTrue(all(r['status'] in ('needs_data','not_applicable') for r in report['rule_readiness']['checks']))
    def test_declared_coverage_partial_and_bounded_history_remain_explicit(self):
        cfg=settings(self.source);cfg['coverage']['vendors']['status']='partial'
        _,report=self.parse(config=cfg)
        name=next(c for c in report['rule_readiness']['checks'] if c['name']=='Tài khoản hoặc định danh NCC liên quan nhân viên')
        self.assertEqual(name['status'],'needs_data')
        self.assertIn('source_coverage_incomplete',{g['reason'] for g in name['gaps']})
    def test_coverage_counts_and_checksums_come_from_current_mapped_rows(self):
        parsed,report=self.parse(package(self.source,rename=True),settings(self.source,rename=True))
        self.assertNotEqual(report['status'],'rejected',report['errors'])
        data=json.loads(parsed)['source'];rows=data['tables']['transactions']
        self.assertEqual(data['coverage']['transactions']['records_sha256'],digest(canonical(rows)))
        self.assertEqual(data['coverage']['transactions']['record_count'],len(rows))
    def test_required_column_error_identifies_file_row_and_field(self):
        raw=json.loads(package(self.source));part=next(p for p in raw['files'] if p['name']=='transactions.csv')
        cols=sorted(set(self.source['tables']['transactions'][0])-{'transaction_id'})
        rows=[{k:v for k,v in r.items() if k!='transaction_id'} for r in self.source['tables']['transactions']]
        part['content_b64']=base64.b64encode(csv_bytes(rows,cols)).decode()
        parsed,report=self.parse(canonical(raw));self.assertIsNone(parsed)
        error=report['errors'][0];self.assertEqual(error['field'],'transaction_id');self.assertEqual(error['csv_row'],2);self.assertEqual(error['file'],'transactions.csv')
    def test_cross_company_and_tenant_are_not_remapped_by_metadata(self):
        changed=deepcopy(self.source);changed['tables']['transactions'][0]['company_id']='C002'
        parsed,report=self.parse(package(changed));self.assertIsNone(parsed);self.assertTrue(any(e['code']=='ACCESS_DENIED' for e in report['errors']))
        with self.assertRaises(ImportFailure):mapping_contract(dict(profile='rule_sources',metadata={'tenant_id':'other'}))
    def test_duplicate_mapped_tables_or_columns_cannot_overwrite_source(self):
        cfg=settings(self.source);cfg['sources']={'vendors.csv':'employees'}
        parsed,report=self.parse(config=cfg);self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'TABLE_DUPLICATE')
        cfg=settings(self.source,rename=True);cfg['tables']['transactions'].update(transaction_id='transaction_id')
        with self.assertRaises(ImportFailure):mapping_contract(cfg)
    def test_explicit_all_candidates_never_silently_truncates_history(self):
        cfg=settings(self.source);cfg.pop('candidate_transaction_ids');cfg['candidate_selection']='all'
        tx=self.source['tables']['transactions'][0]
        self.source['tables']['transactions']=[dict(tx,transaction_id=f'T{i}') for i in range(201)]
        parsed,report=self.parse(config=cfg);self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'RULE_CANDIDATES_INVALID')
    def test_save_retry_one_snapshot_and_mapping_change_invalidates_preview(self):
        raw=package(self.source,rename=True)
        with tempfile.TemporaryDirectory() as root:
            store=SnapshotStore(Path(root)/'store.db');draft=store.upload(self.scope,raw,'sources.json','upload-sources-1')
            store.revise(self.scope,draft['import_id'],1,'map-sources-001',mapping=settings(self.source,rename=True))
            report=store.preview(self.scope,draft['import_id'],2)
            self.assertNotEqual(report['status'],'rejected',report['errors'])
            request=commit_fields(report);saved=store.commit(self.scope,draft['import_id'],request,'save-sources-1')
            self.assertEqual(store.commit(self.scope,draft['import_id'],request,'save-sources-1'),saved)
            data=json.loads(store.get_snapshot(self.scope,saved['snapshot']['snapshot_id'],data=True))
            analyzed=analyze_snapshot(store,self.scope,saved['snapshot']['snapshot_id'],data['source']['as_of'],technical=True)
            self.assertEqual(len(analyzed['rows']),1)
            other=store.upload(self.scope,raw,'sources.json','upload-sources-2')
            store.revise(self.scope,other['import_id'],1,'map-sources-002',mapping=settings(self.source,rename=True))
            old=store.preview(self.scope,other['import_id'],2)
            changed=settings(self.source,rename=True);changed['coverage']['vendors']['status']='partial'
            store.revise(self.scope,other['import_id'],2,'map-sources-003',mapping=changed)
            with self.assertRaises(ImportFailure):store.commit(self.scope,other['import_id'],commit_fields(old),'stale-sources-1')
    def test_packaged_csv_bytes_are_kept_separate_from_normalized_snapshot(self):
        raw=package(self.source)
        with tempfile.TemporaryDirectory() as root:
            store=SnapshotStore(Path(root)/'db');draft=store.upload(self.scope,raw,'sources.json','bytes-sources-1')
            info=store.inspect_sources(self.scope,draft['import_id'],1)
            self.assertEqual(info['source_hash'],digest(raw))
            with self.assertRaises(ImportFailure):store.inspect_sources(scope('C002'),draft['import_id'],1)

    def test_metadata_and_coverage_types_cannot_crash_parser(self):
        for key,value in (('as_of',True),('source_id',{}),('is_simulated','yes')):
            cfg=settings(self.source);cfg['metadata'][key]=value
            with self.assertRaises(ImportFailure):mapping_contract(cfg)
        cfg=settings(self.source);cfg['coverage']['transactions']['covered_from']=[]
        with self.assertRaises(ImportFailure):mapping_contract(cfg)

    def test_subsecond_knowledge_time_is_rejected_not_rounded(self):
        self.source['tables']['transactions'][0]['observed_at']='2025-08-12T11:00:00.123+07:00'
        parsed,report=self.parse();self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'TIME_PRECISION')

    def test_blank_required_money_not_invented_as_zero(self):
        self.source['tables']['transactions'][0]['recognised_input_vat_vnd']=''
        parsed,report=self.parse();self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'VALUE_REQUIRED')

    def test_imported_complete_coverage_can_be_explicitly_withdrawn(self):
        rows=[dict(table_name=name,**{k:v for k,v in claim.items() if k not in ('record_count','records_sha256')}) for name,claim in self.source['coverage'].items()]
        payload=json.loads(package(self.source));payload['files'].append(dict(name='coverage.csv',content_b64=base64.b64encode(csv_bytes(rows,list(rows[0]))).decode()))
        cfg=settings(self.source,coverage=False);cfg['coverage']={'vendors':None}
        parsed,report=self.parse(canonical(payload),cfg)
        self.assertNotEqual(report['status'],'rejected',report['errors'])
        self.assertNotIn('vendors',json.loads(parsed)['source']['coverage'])
        check=next(c for c in report['rule_readiness']['checks'] if c['check_id']=='check_7')
        self.assertEqual(check['status'],'needs_data')
        self.assertIn('source_coverage_missing',{g['reason'] for g in check['gaps']})

    def test_numeric_excel_time_is_explained_not_a_server_exception(self):
        from sme_fraud.rule_source_intake import scalar
        from sme_fraud.tabular_import import TabularError
        with self.assertRaises(TabularError) as error:scalar(123,'as_of','iso',{})
        self.assertEqual(error.exception.code,'TIME_FORMAT')

    def test_ambiguous_csv_day_month_needs_explicit_mapping(self):
        self.source['tables']['transactions'][0]['posted_at']='12/08/2025 11:00:00'
        parsed,report=self.parse();self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'TIME_FORMAT')
        cfg=settings(self.source);cfg['date_format']='dmy'
        parsed,report=self.parse(config=cfg);self.assertNotEqual(report['status'],'rejected',report['errors'])
        self.assertEqual(json.loads(parsed)['source']['tables']['transactions'][0]['posted_at'],'2025-08-12T11:00:00+07:00')

    def test_leading_zero_bank_identifier_kept_exact(self):
        self.source['tables']['transactions'][0]['recipient_account']='000012345678'
        parsed,report=self.parse();self.assertNotEqual(report['status'],'rejected',report['errors'])
        self.assertEqual(json.loads(parsed)['source']['tables']['transactions'][0]['recipient_account'],'000012345678')

    def test_partial_readiness_matches_actual_snapshot_availability(self):
        good=self.source['tables']['transactions'][0]
        bad=dict(good,transaction_id='MISSING_INVOICE',invoice_gross_vnd=0)
        self.source['tables']['transactions'].append(bad)
        cfg=settings(self.source);cfg['candidate_transaction_ids']=[good['transaction_id'],bad['transaction_id']]
        raw=package(self.source)
        with tempfile.TemporaryDirectory() as root:
            store=SnapshotStore(Path(root)/'db');draft=store.upload(self.scope,raw,'sources.json','readiness-parity-upload')
            draft=store.revise(self.scope,draft['import_id'],1,'readiness-parity-mapping',mapping=cfg)
            report=store.preview(self.scope,draft['import_id'],draft['revision'])
            self.assertNotEqual(report['status'],'rejected',report['errors'])
            saved=store.commit(self.scope,draft['import_id'],commit_fields(report),'readiness-parity-save')
            actual=analyze_snapshot(store,self.scope,saved['snapshot']['snapshot_id'],self.source['as_of'],technical=True)
            p1=next(r for r in report['rule_readiness']['checks'] if r['name']=='Thanh toán và giá trị hóa đơn')
            self.assertEqual(p1['status'],'partial');self.assertEqual(p1['ready_count'],1);self.assertEqual(p1['missing_count'],1)
            statuses=[next(r for r in row['rule_coverage']['rules'] if r['rule_id']=='P1')['available'] for row in actual['rows']]
            self.assertEqual(statuses,[True,False])

    def test_readiness_never_fits_a_model_or_calls_cloud(self):
        with patch('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',side_effect=AssertionError('fit')), \
             patch('experiments.he_inference.http_common.post',side_effect=AssertionError('cloud')):
            parsed,report=self.parse();self.assertIsNotNone(parsed);self.assertEqual(len(report['rule_readiness']['checks']),35)

    def test_stale_file_cannot_reuse_old_preview(self):
        raw=package(self.source)
        with tempfile.TemporaryDirectory() as root:
            store=SnapshotStore(Path(root)/'db');draft=store.upload(self.scope,raw,'sources.json','replace-source-01')
            store.revise(self.scope,draft['import_id'],1,'replace-mapping-01',mapping=settings(self.source))
            report=store.preview(self.scope,draft['import_id'],2)
            changed=deepcopy(self.source);changed['tables']['transactions'][0]['amount_vnd']+=1
            store.revise(self.scope,draft['import_id'],2,'replace-source-02',raw=package(changed),filename='sources.json')
            with self.assertRaises(ImportFailure):store.commit(self.scope,draft['import_id'],commit_fields(report),'stale-source-save')

    def test_nonempty_cell_without_header_is_not_silently_ignored(self):
        payload=json.loads(package(self.source));tx=next(p for p in payload['files'] if p['name']=='transactions.csv')
        raw=base64.b64decode(tx['content_b64']).decode('utf-8-sig');rows=list(csv.reader(io.StringIO(raw)));rows[0].append('');rows[1].append('do not drop')
        stream=io.StringIO(newline='');csv.writer(stream).writerows(rows);tx['content_b64']=base64.b64encode(stream.getvalue().encode()).decode()
        parsed,report=self.parse(canonical(payload));self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],'COLUMN_HEADER')

    def test_template_contains_headers_for_every_required_source_field(self):
        from openpyxl import load_workbook
        from sme_fraud.rule_source_intake import required_fields
        path=Path(__file__).resolve().parents[1]/'sme_fraud/web/rule-sources.xlsx'
        book=load_workbook(path,read_only=True,data_only=False)
        try:
            for table,required in required_fields().items():
                actual={c.value for c in book[table][1]};self.assertFalse(required-actual,(table,required-actual))
        finally:book.close()

    def test_excel_typed_dates_identifiers_and_money_follow_the_source_clock(self):
        from openpyxl import load_workbook
        path=Path(__file__).resolve().parents[1]/'sme_fraud/web/rule-sources.xlsx'
        book=load_workbook(path)
        for name,rows in self.source['tables'].items():
            if not rows:continue
            sheet=book[name];names=sorted({k for r in rows for k in r});sheet.delete_rows(1,sheet.max_row);sheet.append(names)
            for row in rows:sheet.append([datetime.fromisoformat(row[k]).replace(tzinfo=None) if k.endswith('_at') and row.get(k) else str(row[k]) if k.endswith('_vnd') else row.get(k) for k in names])
        output=io.BytesIO();book.save(output);book.close();raw=output.getvalue()
        info=inspect(raw,'sources.xlsx');self.assertTrue(info['sources'])
        parsed,report=parse_file(raw,settings(self.source),self.scope,'sources.xlsx')
        self.assertNotEqual(report['status'],'rejected',report['errors'])
        actual=json.loads(parsed)['source']['tables']['transactions'][0]
        self.assertEqual(actual['posted_at'],self.source['tables']['transactions'][0]['posted_at'])
        self.assertEqual(actual['observed_at'],self.source['tables']['transactions'][0]['observed_at'])


class RuleSourcePortal(unittest.TestCase):
    def setUp(self):
        from test_portal_auth import PortalHarness
        self.h=PortalHarness().__enter__();self.addCleanup(self.h.__exit__)
    def test_inspect_mapping_readiness_commit_via_portal_and_scope_guards(self):
        source,_=scenario('B1',True);source['tenant_id']='demo'
        raw=package(source,rename=True)
        status,draft=self.h.request(self.h.url('imports/upload'),raw,headers={'X-File-Name':'sources.json','Idempotency-Key':'source-portal-upload'})
        self.assertEqual(status,201)
        path='imports/'+draft['import_id']
        status,info=self.h.request(self.h.url(path+'/inspect'),{'expected_revision':1})
        self.assertEqual(status,200);self.assertTrue(info['sources'])
        self.assertEqual(self.h.request(self.h.url(path+'/inspect','C002'),{'expected_revision':1})[0],404)
        self.assertEqual(self.h.request(self.h.url(path+'/inspect'),{'expected_revision':1},token=False)[0],401)
        status,draft=self.h.request(self.h.url(path+'/mapping'),{'expected_revision':1,'mapping':settings(source,rename=True)},method='PUT',headers={'Idempotency-Key':'source-portal-mapping'})
        self.assertEqual(status,200)
        status,report=self.h.request(self.h.url(path+'/preview'),{'expected_revision':draft['revision']})
        self.assertEqual(status,200,report);self.assertEqual(len(report['rule_readiness']['checks']),35)
        body=commit_fields(report);headers={'Idempotency-Key':'source-portal-commit'}
        status,saved=self.h.request(self.h.url(path+'/commit'),body,headers=headers);self.assertEqual(status,200)
        self.assertEqual(self.h.request(self.h.url(path+'/commit'),body,headers=headers)[1],saved)
        self.assertEqual(self.h.count(),1)
    def test_new_static_assets_are_allowlisted_without_exposing_private_data(self):
        for path in ('assets/rule-source-intake.js','samples/rule-sources.xlsx'):
            self.assertEqual(self.h.request('/agent2/'+path,token=False)[0],200)
    def test_revoked_session_returns_401_without_forwarding_rejected_source_body(self):
        from test_portal_auth import portal
        portal.SESSIONS.pop(self.h.token)
        raw=package(scenario('B1',True)[0])
        with patch.object(portal.agent2_bridge,'open_backend',side_effect=AssertionError('Must not forward')):
            for i in range(3):
                status,body=self.h.request(self.h.url('imports/upload'),raw,headers={'X-File-Name':'sources.json','Idempotency-Key':'rejected-source-'+str(i)})
                self.assertEqual(status,401);self.assertTrue(body['locked'])
        self.assertEqual(self.h.count(),0)


class RejectedBodyDrain(unittest.TestCase):
    def handler(self,raw=b'x',length='1',transfer=False):
        from types import SimpleNamespace
        from email.message import Message
        from unittest.mock import Mock
        headers=Message();headers.add_header('Content-Length',length)
        if transfer:headers.add_header('Transfer-Encoding','chunked')
        connection=Mock();connection.gettimeout.return_value=10
        return SimpleNamespace(command='POST',headers=headers,connection=connection,rfile=io.BufferedReader(io.BytesIO(raw)))
    def test_valid_denied_body_is_discarded_and_timeout_restored(self):
        from portal.agent2_bridge import discard_rejected_body
        h=self.handler(b'x'*8193,'8193');discard_rejected_body(h)
        self.assertEqual(h.rfile.read(),b'');self.assertEqual(h.connection.settimeout.call_args.args,(10,))
    def test_oversize_or_chunked_denied_body_is_not_read(self):
        from portal.agent2_bridge import discard_rejected_body
        for h in (self.handler(length=str(10*1024*1024+1)),self.handler(transfer=True)):
            discard_rejected_body(h);self.assertEqual(h.rfile.read(),b'x');h.connection.settimeout.assert_not_called()


if __name__=='__main__':unittest.main()
