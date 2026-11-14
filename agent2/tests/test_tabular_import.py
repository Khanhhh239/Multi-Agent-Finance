import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from openpyxl import load_workbook
from sme_fraud.import_files import parse_file,canonical,mapping_contract,ImportFailure
from sme_fraud.tabular_templates import sample
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle,scope
from test_snapshots import commit_fields


class Tabular(unittest.TestCase):
    def setUp(self):self.data=bundle('C001');self.scope=scope()

    def test_csv_and_excel_round_trip_same_canonical_data(self):
        for kind in ('csv','xlsx'):
            with self.subTest(kind=kind):
                raw=sample(self.data,kind);parsed,report=parse_file(raw,{},self.scope,'input.'+kind)
                self.assertNotEqual(report['status'],'rejected',report['errors']);self.assertEqual(json.loads(parsed),self.data)

    def test_large_signed_vnd_and_leading_zero_text_remain_exact(self):
        self.data['transactions'][0]['amount_vnd']=-123456789012345678
        self.data['transactions'][0].pop('accounting_lines',None)
        self.data['transactions'][0]['bank_account']='000012345678'
        for kind in ('csv','xlsx'):
            parsed,report=parse_file(sample(self.data,kind),{},self.scope,'input.'+kind)
            # Other business checks may reject an unbound adjustment; parsing
            # alone must never round/change this exact source number.
            from sme_fraud.tabular_import import parse
            data,_=parse(sample(self.data,kind),'input.'+kind,{})
            self.assertEqual(data['transactions'][0]['amount_vnd'],-123456789012345678)
            self.assertEqual(data['transactions'][0]['bank_account'],'000012345678')

    def workbook(self):return load_workbook(io.BytesIO(sample(self.data,'xlsx')))
    def bytes(self,book):out=io.BytesIO();book.save(out);return out.getvalue()

    def test_formulas_and_numeric_ids_rejected_with_sheet_row_field(self):
        for field,value,code in (('record_id',123,'IDENTIFIER_TEXT'),('amount_vnd','=1+2','EXCEL_FORMULA')):
            book=self.workbook();sheet=book['transactions'];names=[c.value for c in sheet[1]];sheet.cell(2,names.index(field)+1,value)
            parsed,report=parse_file(self.bytes(book),{},self.scope,'input.xlsx')
            self.assertIsNone(parsed);self.assertEqual(report['errors'][0]['code'],code);self.assertEqual(report['errors'][0]['sheet'],'transactions');self.assertEqual(report['errors'][0]['row'],2)

    def test_ambiguous_date_requires_explicit_format_and_mapping_recheck(self):
        book=self.workbook();sheet=book['transactions'];names=[c.value for c in sheet[1]]
        for row in range(2,sheet.max_row+1):
            sheet.cell(row,names.index('effective_at')+1,'10/10/2026 09:00');sheet.cell(row,names.index('observed_at')+1,'10/10/2026 09:00')
        raw=self.bytes(book);_,report=parse_file(raw,{},self.scope,'input.xlsx');self.assertEqual(report['errors'][0]['code'],'TIME_FORMAT')
        from sme_fraud.tabular_import import parse
        data,_=parse(raw,'input.xlsx',mapping_contract(dict(date_format='dmy')))
        self.assertEqual(data['transactions'][0]['effective_at'],'2026-10-10T09:00:00+07:00')

    def test_missing_code_reports_actual_source_row(self):
        book=self.workbook();sheet=book['transactions'];names=[c.value for c in sheet[1]];sheet.cell(2,names.index('record_id')+1).value=None
        _,report=parse_file(self.bytes(book),{},self.scope,'input.xlsx')
        issue=next(e for e in report['errors'] if e.get('sheet')=='transactions' and e.get('row')==2)
        self.assertIn('record_id',issue['path'])

    def test_original_excel_bytes_and_stale_preview_and_repeated_save(self):
        with tempfile.TemporaryDirectory() as root:
            store=SnapshotStore(Path(root)/'snapshots.sqlite3');raw=sample(self.data,'xlsx')
            draft=store.upload(self.scope,raw,'input.xlsx','upload-tabular-1');preview=store.preview(self.scope,draft['import_id'],1)
            self.assertNotEqual(preview['status'],'rejected',preview['errors'])
            request=commit_fields(preview);saved=store.commit(self.scope,draft['import_id'],request,'save-tabular-001')
            self.assertEqual(store.commit(self.scope,draft['import_id'],request,'save-tabular-001'),saved)
            other=store.upload(self.scope,raw,'input.xlsx','upload-tabular-2');old=store.preview(self.scope,other['import_id'],1)
            store.revise(self.scope,other['import_id'],1,'tabular-mapping-new',mapping={'date_format':'dmy'})
            with self.assertRaises(ImportFailure):store.commit(self.scope,other['import_id'],commit_fields(old),'stale-save-001')
