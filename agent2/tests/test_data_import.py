"""Real parser/feature/SQLite/API acceptance cases for company uploads."""
import base64
import csv
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from sme_fraud.company_ml import CompanyML
from sme_fraud.data_import import DataImport, REQUIRED, OPTIONAL, VERSION, timestamp
from sme_fraud.feature_contract import sha, current_contract
from sme_fraud.generate import write_csv
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_server import make_server
from company_ml_fixture import fixture, CHIEF, ACCOUNTANT, label_text
from unittest.mock import patch
import test_company_ml_web as web_helpers


def import_fixture(root):
    store,data,_=fixture(root)
    write_csv(data/'employees.csv', [dict(employee_id='E01', company_id='C001', recorded_at='2023-01-01T00:00:00+07:00',
        self_approval_limit_vnd=0,contract_on_file=0,bank_account='000123',phone='',address=''),
        dict(employee_id='E02',company_id='C002',recorded_at='2023-01-01T00:00:00+07:00',
        self_approval_limit_vnd=0,contract_on_file=0,bank_account='000456',phone='',address='')])
    write_csv(data/'vendors.csv', [dict(vendor_id='V01',company_id='C001',recorded_at='2023-01-01T00:00:00+07:00',
        registered_at='2022-01-01T00:00:00+07:00',onboarded_at='2023-01-01T00:00:00+07:00',
        related_party_disclosed_at='',bank_account='000999',phone='',address='')])
    return store,data


def upload_rows(company='C001',count=15):
    result=[]
    for i in range(count):
        day=(datetime(2024,1,1)+timedelta(days=i)).date().isoformat()
        result.append(dict(transaction_id=f'000{i:03}',company_id=company,created_at=day+' 08:00',
            approved_at=day+' 09:00',posted_at=day+' 12:00',txn_type='vendor_payment',
            amount_vnd=str(1_000_000+i*10000),approval_limit_vnd='20000000',creator_id='E01' if company=='C001' else 'E02',
            approver_id='E01' if company=='C001' else 'E02',vendor_id='V01' if company=='C001' else '',
            is_financial_entry='1',debit_account='331',credit_account='112',journal_signature='331/112',accounting_purpose='vendor_payment',
            recognised_input_vat_vnd='0',recognised_output_vat_vnd='0',writeoff_provision_vnd='0',production_cost_vnd='0',recipient_account='000999'))
    return result


def csv_bytes(rows,fields=None,delimiter=',',encoding='utf-8-sig'):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,delimiter=delimiter)
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode(encoding)


def xlsx_bytes(rows,fields=None,transform=None):
    from openpyxl import Workbook
    book=Workbook();sheet=book.active;sheet.title='transactions'
    fields=fields or list(rows[0]);sheet.append(fields)
    for row in rows: sheet.append([row.get(k,'') for k in fields])
    if transform: transform(sheet,fields)
    stream=io.BytesIO();book.save(stream);book.close();return stream.getvalue()


class DataImportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,self.data=import_fixture(Path(self.temp.name))
        self.ml=CompanyML(self.store);self.t=[0.];self.service=DataImport(self.ml,monotonic=lambda:self.t[0])
    def preview(self,rows=None,**kw):
        content=kw.pop('content',None) or csv_bytes(rows if rows is not None else upload_rows())
        return self.service.preview('003','C001',kw.pop('principal',CHIEF),filename=kw.pop('filename','test.csv'),
            content_base64=base64.b64encode(content).decode(),expected_revision=kw.pop('expected_revision',None),**kw)
    def commit(self,value,**kw):
        return self.service.commit('003','C001',kw.pop('principal',CHIEF),token=value['token'],acknowledge=kw.pop('acknowledge',True))
    def no_data(self):
        self.assertIsNone(self.ml.status('003','C001',CHIEF)['data'])

    def test_preview_creates_real_features_but_no_database_writes_and_commit_keeps_raw(self):
        source={p.name:sha(p) for p in self.data.iterdir() if p.is_file()}
        value=self.preview();self.assertTrue(value['valid'],value);self.no_data()
        self.assertEqual(value['normalized_preview'][0]['transaction_id'],'000000')
        self.assertEqual(value['normalized_preview'][0]['posted_at'],'2024-01-01T12:00:00+07:00')
        self.assertEqual(value['feature_count'],len(current_contract()['columns']))
        result=self.commit(value);status=result['status'];self.assertEqual(status['data']['rows'],15)
        self.assertEqual(status['data']['dataset_version'],VERSION)
        self.assertIsNone(status['active_version']);self.assertIn('company=C001',result['next_url'])
        with self.store.connection() as db:
            _,meta,records,x,labels=self.ml._data(db,'C001')
            self.assertEqual(x.shape,(15,len(meta['columns'])));self.assertEqual(labels,{})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM company_ml_imports').fetchone()[0],1)
            cols=meta['columns'];self.assertEqual(x[0,cols.index('support_docs_known')],0)
            self.assertEqual(x[0,cols.index('invoice_known')],0)
        self.assertEqual({p.name:sha(p) for p in self.data.iterdir() if p.is_file()},source)
        self.assertIsNone(self.ml.status('003','C002',CHIEF)['data'])

    def test_bad_rows_report_column_row_reason_fix_and_do_not_stage_or_save(self):
        rows=upload_rows();rows[1]['transaction_id']=rows[0]['transaction_id'];rows[2]['company_id']='C002'
        rows[3]['creator_id']='E02';rows[4]['amount_vnd']='1,000';rows[5]['approved_at']='2023-01-01 00:00'
        rows[6]['posted_at']='03/04/2024 12:00';rows[7]['approval_limit_vnd']='0';rows[8]['creator_id']=''
        result=self.preview(rows);self.assertFalse(result['valid']);self.assertIsNone(result['token'])
        for column in ('transaction_id','company_id','creator_id','amount_vnd','posted_at','approval_limit_vnd'):
            self.assertTrue(any(e['column']==column for e in result['errors']),column)
        self.assertTrue(all(e['fix'] and e['message'] and e['row'] for e in result['errors']))
        self.no_data();self.assertFalse(self.service.pending)

    def test_missing_duplicate_unknown_headers_and_malformed_csv(self):
        for content in (b'transaction_id,transaction_id\nx,y\n',b'transaction_id,bogus\nx,y\n',b'\n'):
            value=self.preview(content=content);self.assertFalse(value['valid']);self.assertTrue(value['errors'])
        with self.assertRaises(ValueError):self.preview(content=b'transaction_id,amount_vnd\n"unterminated',delimiter=',')
        self.no_data()

    def test_date_timezone_day_order_blank_rows_trim_and_encoding(self):
        rows=upload_rows();rows[0]['transaction_id']=' 000000 ';rows[0]['created_at']='01/01/2024 01:00'
        rows[0]['approved_at']='2024-01-01T02:00:00Z';rows[0]['posted_at']='01/01/2024 12:00'
        rows[0]['business_purpose']='Thanh toán'
        result=self.preview(content=csv_bytes(rows,delimiter=';',encoding='cp1258')+b'\r\n',encoding='cp1258',date_order='dmy')
        self.assertTrue(result['valid'],result);self.assertEqual(result['summary']['delimiter'],';')
        self.assertEqual(result['summary']['trimmed_cells'],1);self.assertEqual(result['summary']['skipped_blank_rows'],1)
        self.assertEqual(timestamp('2024-01-01T01:00:00Z','iso'),'2024-01-01T08:00:00+07:00')

    def test_excel_actual_dates_text_identifiers_and_optional_empty_trailing_cells(self):
        rows=upload_rows();rows[0]['created_at']=datetime(2024,1,1,8)
        value=self.preview(filename='test.xlsx',content=xlsx_bytes(rows,fields=list(rows[0])+['invoice_number']))
        self.assertTrue(value['valid'],value);self.assertEqual(value['summary']['format'],'xlsx')
        self.assertEqual(value['normalized_preview'][0]['transaction_id'],'000000')

    def test_excel_formula_numeric_ids_cell_errors_and_multiple_sheets_block(self):
        def mutate(sheet,fields):
            sheet.cell(2,fields.index('transaction_id')+1,123)
            sheet.cell(3,fields.index('amount_vnd')+1,'=1+2')
        value=self.preview(filename='test.xlsx',content=xlsx_bytes(upload_rows(),transform=mutate))
        self.assertFalse(value['valid']);self.assertTrue(any('Text' in e['fix'] for e in value['errors']))
        self.assertTrue(any('công thức' in e['message'] for e in value['errors']))
        with self.assertRaises(ValueError):self.preview(filename='test.xlsx',content=xlsx_bytes(upload_rows(),transform=lambda sheet,fields:sheet.parent.create_sheet('other')))
        for filename,content in [('bad.xlsx',b'notazip'),('bad.xls',b'old'),('bad.xlsm',b'macro')]:
            with self.assertRaises(ValueError):self.preview(filename=filename,content=content)
        self.no_data()

    def test_acknowledgement_actor_company_expiry_and_replay(self):
        value=self.preview()
        with self.assertRaises(ValueError):self.commit(value,acknowledge=False)
        other=ReviewPrincipal('OTHER','P','other','director',('C001',))
        with self.assertRaises(PermissionError):self.commit(value,principal=other)
        with self.assertRaises(PermissionError):self.service.commit('003','C002',CHIEF,token=value['token'],acknowledge=True)
        self.t[0]=1201
        with self.assertRaises(RuntimeError):self.commit(value)
        value=self.preview();self.commit(value)
        with self.assertRaises(RuntimeError):self.commit(value)

    def test_stale_revision_source_changes_and_contract_changes_never_commit(self):
        other=ReviewPrincipal('OTHER','P','other','director',('C001',))
        a=self.preview();b=self.preview(principal=other);self.commit(a)
        with self.assertRaises(RuntimeError):self.commit(b,principal=other)
        revision=self.ml.status('003','C001',CHIEF)['data']['revision']
        value=self.preview(expected_revision=revision)
        with (self.data/'calendar.csv').open('w',encoding='utf-8') as f:f.write('date\n2024-01-01\n')
        with self.assertRaises(RuntimeError):self.commit(value)
        self.assertEqual(self.ml.status('003','C001',CHIEF)['data']['revision'],revision)

    def test_feature_contract_or_active_model_change_requires_new_preview(self):
        value=self.preview()
        changed=dict(current_contract(),fingerprint='different')
        with patch('sme_fraud.data_import.current_contract',return_value=changed):
            with self.assertRaises(RuntimeError):self.commit(value)
        self.no_data()
        data=self.ml.update_data('003','C001',CHIEF,expected_revision=None)
        revision=data['data']['revision'];value=self.preview(expected_revision=revision)
        data=self.ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='ecod',
            train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00',alert_budget=.1)
        self.ml.activate('003','C001',CHIEF,expected_revision=revision,expected_active=None,version_id=data['versions'][0]['version_id'])
        with self.assertRaises(RuntimeError):self.commit(value)
        self.assertEqual(self.ml.status('003','C001',CHIEF)['data']['revision'],revision)

    def test_reviewed_labels_do_not_replace_imported_records_features_or_raw_history(self):
        data=self.commit(self.preview())['status'];revision=data['data']['revision']
        with self.store.connection() as db:
            _,_,records,x,_=self.ml._data(db,'C001')
            raw=tuple(db.execute('SELECT * FROM company_ml_imports').fetchone())
        data=self.ml.update_labels('003','C001',CHIEF,expected_revision=revision,labels_text=label_text(records))
        self.assertEqual(data['data']['source'],'csv_excel_upload');self.assertEqual(data['data']['labels_count'],15)
        with self.store.connection() as db:
            _,_,after,y,labels=self.ml._data(db,'C001')
            self.assertEqual(after,records);self.assertTrue((x==y).all());self.assertEqual(len(labels),15)
            self.assertEqual(tuple(db.execute('SELECT * FROM company_ml_imports').fetchone()),raw)
        with self.assertRaises(RuntimeError):self.ml.update_labels('003','C001',CHIEF,expected_revision=revision,labels_text=label_text(records))
        with self.assertRaises(PermissionError):self.ml.update_labels('003','C001',ACCOUNTANT,expected_revision=data['data']['revision'],labels_text=label_text(records))

    def test_file_row_and_stage_limits_are_explained(self):
        with self.assertRaises(ValueError):self.preview(content=b'x'*10_485_761)
        with self.assertRaises(ValueError):self.preview(content=b'a,b\n'+b'x,y\n'*10001)
        for i in range(10):self.preview()  # rechecking replaces this actor/company's old preview
        self.assertEqual(len(self.service.pending),1)
        for i in range(7):self.preview(principal=ReviewPrincipal('USER'+str(i),'P','other','director',('C001',)))
        with self.assertRaises(OverflowError):self.preview(principal=ReviewPrincipal('NINTH','P','other','director',('C001',)))
        self.t[0]=1201
        self.assertTrue(self.preview()['valid'])

    def test_incomplete_or_future_master_needs_source_correction(self):
        write_csv(self.data/'employees.csv',[dict(employee_id='E01',company_id='C001',recorded_at='2023-01-01T00:00:00+07:00')])
        value=self.preview();self.assertFalse(value['valid']);self.assertIn('self_approval_limit_vnd',str(value['errors']))
        write_csv(self.data/'employees.csv',[dict(employee_id='E01',company_id='C001',recorded_at='2025-01-01T00:00:00+07:00',self_approval_limit_vnd=0)])
        value=self.preview();self.assertFalse(value['valid']);self.assertIn('thời điểm',str(value['errors']))

    def test_future_and_invalid_boolean_money_and_evidence_do_not_become_known(self):
        rows=upload_rows();rows[0]['posted_at']='2099-01-01 12:00';rows[1]['is_financial_entry']='2'
        rows[2]['recognised_input_vat_vnd']='';rows[3]['support_docs_observed_at']='2024-01-04 12:00'
        value=self.preview(rows);self.assertFalse(value['valid']);self.no_data()

    def test_existing_binding_retained_but_incompatible_connected_model_cannot_score(self):
        data=self.ml.update_data('003','C001',CHIEF,expected_revision=None)
        revision=data['data']['revision']
        data=self.ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='ecod',
            train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00',alert_budget=.1)
        version=data['versions'][0]['version_id']
        self.ml.activate('003','C001',CHIEF,version_id=version,expected_active=None,expected_revision=revision)
        value=self.preview(expected_revision=revision);self.assertTrue(value['summary']['model_needs_evaluation'])
        data=self.commit(value)['status'];self.assertEqual(data['active_version'],version)
        with self.assertRaises(ValueError):self.ml.score('003','C001',CHIEF,expected_revision=data['data']['revision'],expected_active=version)

    def test_import_evaluate_activate_score_then_refresh_preserves_frozen_artifact(self):
        data=self.commit(self.preview())['status'];revision=data['data']['revision']
        windows=data['data']['suggested_windows']
        data=self.ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='isolation_forest',alert_budget=.1,**windows)
        version=data['versions'][0]['version_id'];checksum=data['versions'][0]['artifact_sha256']
        self.ml.activate('003','C001',CHIEF,expected_revision=revision,expected_active=None,version_id=version)
        first=self.ml.score('003','C001',CHIEF,expected_revision=revision,expected_active=version)
        rows=upload_rows(count=16);value=self.preview(rows,expected_revision=revision)
        self.assertFalse(value['summary']['model_needs_evaluation'])
        data=self.commit(value)['status'];self.assertEqual(data['active_version'],version)
        self.assertEqual(data['versions'][0]['artifact_sha256'],checksum)
        second=self.ml.score('003','C001',CHIEF,expected_revision=data['data']['revision'],expected_active=version)
        self.assertEqual(second['items'][:len(first['items'])],first['items'])


class DataImportWebTest(unittest.TestCase):
    call=web_helpers.CompanyMLWebTest.call
    close=web_helpers.CompanyMLWebTest.close
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,_=import_fixture(Path(self.temp.name))
        people={'chief':CHIEF,'accountant':ACCOUNTANT}
        self.server=make_server(self.store,port=0,identity_provider=lambda r:people.get(r.headers.get('X-Test-Actor')))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        self.token=self.call('GET','/api/meta')[1]['csrf_token']
        self.body=dict(scenario='003',company_id='C001',filename='test.csv',content_base64=base64.b64encode(csv_bytes(upload_rows())).decode(),expected_revision=None)
    def test_assets_context_template_permissions_csrf_and_scope(self):
        for path in ('/data-import','/data_import.js','/data_import.css','/api/data-import/context?company=C001','/api/data-import/template?company=C001'):
            self.assertEqual(self.call('GET',path)[0],200,path)
        for actor in ('','accountant'):
            self.assertEqual(self.call('POST','/api/data-import/preview',self.body,actor=actor)[0],403)
        self.assertEqual(self.call('GET','/api/data-import/context?company=C002',actor='accountant')[0],403)
        self.assertEqual(self.call('POST','/api/data-import/preview',self.body,token='bad')[0],403)
        self.assertEqual(self.call('POST','/api/data-import/preview',self.body|{'unexpected':True})[0],400)
        self.assertEqual(self.call('POST','/api/data-import/preview',self.body|{'scenario':'005'})[0],400)
    def test_http_preview_commit_and_replay(self):
        code,value=self.call('POST','/api/data-import/preview',self.body);self.assertEqual(code,200);self.assertTrue(value['valid'],value)
        body=dict(company_id='C001',scenario='003',token=value['token'],acknowledge=True)
        code,result=self.call('POST','/api/data-import/commit',body)
        self.assertEqual(code,200,result);self.assertEqual(result['status']['data']['rows'],15)
        self.assertEqual(self.call('POST','/api/data-import/commit',body)[0],409)


if __name__=='__main__':unittest.main()
