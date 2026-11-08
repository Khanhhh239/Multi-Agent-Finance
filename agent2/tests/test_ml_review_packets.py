"""Exact frozen evidence population, CLI/web parity and atomic rejection."""
import copy
import csv
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.company_ml import CompanyML  # scientific runtime before legacy imports
from sme_fraud.company_ml_comparison import collect
from sme_fraud.feature_contract import sha
from sme_fraud.ml_review_packets import load_packet, SELECTION_FIELDS
from sme_fraud.ml_review_web import MLReview
from company_ml_fixture import CHIEF
from test_data_import import import_fixture, csv_bytes
from test_ml_review_web import packet_fixture


class MLReviewPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.shared.cleanup)
        cls.frozen=packet_fixture(Path(cls.shared.name),review_count=5,
            algorithms=['isolation_forest','autoencoder','ecod','lof'])
        cls.verified=load_packet(cls.frozen)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.packet=self.root/'packet';shutil.copytree(self.frozen,self.packet)
        self.store,_=import_fixture(self.root/'web')
        self.service=MLReview(self.store,[self.frozen],qa=True);self.pid=self.verified['packet_id']
        self.before=self.database_state();self.counter=0

    def database_state(self):
        with self.store.connection() as db:
            return {table:[tuple(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('ml_review_packets','ml_review_units','ml_review_work','ml_review_events')}

    def relock(self,extra=()):
        """Build internally inconsistent fixtures with valid file checksums."""
        path=self.packet/'manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
        for name in list(manifest['files'])+list(extra):manifest['files'][name]=sha(self.packet/name)
        manifest['comparison_sha256']=sha(self.packet/'private/comparison.json')
        path.write_text(json.dumps(manifest),encoding='utf-8')

    def report(self):return json.loads((self.packet/'private/comparison.json').read_text(encoding='utf-8'))
    def write_report(self,value):
        (self.packet/'private/comparison.json').write_text(json.dumps(value),encoding='utf-8');self.relock()
    def evidence(self):return sorted((self.packet/'public/evidence').glob('*.json'))
    def selections(self):
        return list(csv.DictReader(io.StringIO((self.packet/'private/selection.csv').read_text(encoding='utf-8-sig'))))
    def write_selections(self,rows,fields=SELECTION_FIELDS):
        (self.packet/'private/selection.csv').write_bytes(csv_bytes(rows,fields=fields));self.relock()

    def assert_blocked(self,message=None):
        with self.assertRaises(ValueError) as caught:load_packet(self.packet)
        if message:self.assertIn(message,str(caught.exception))
        with self.assertRaises(ValueError):self.service.import_packet(self.packet)
        self.counter+=1;output=self.root/f'bad_results_{self.counter}'
        with self.assertRaises(ValueError):collect(self.packet,self.packet/'human_reviews.csv',output)
        self.assertFalse(output.exists());self.assertEqual(self.database_state(),self.before)
        self.assertEqual(self.service.units(self.pid,CHIEF)['total'],12)

    def extra_evidence(self,name='AUDIT_EXTRA'):
        value=json.loads(self.evidence()[0].read_text(encoding='utf-8'))
        value.update(review_id=name,transaction_id='SIM_EXTRA_TRANSACTION')
        value['source_record']['transaction_id']=value['transaction_id']
        path=self.packet/f'public/evidence/{name}.json';path.write_text(json.dumps(value),encoding='utf-8')
        return path

    def test_valid_frozen_packet_stays_at_twelve_on_cli_and_web_reimport(self):
        self.assertEqual(len(self.verified['units']),12)
        packet=load_packet(self.packet);self.assertEqual(packet['packet_id'],self.pid)
        self.assertEqual(self.service.import_packet(self.packet),self.pid)
        result=collect(self.packet,self.packet/'human_reviews.csv',self.root/'valid_results')
        self.assertEqual(result['review_units'],12);self.assertEqual(result['completed_human_reviews'],0)
        self.assertEqual(result['source_comparison_sha256'],self.pid)
        self.assertEqual(self.database_state(),self.before)

    def test_thirteenth_unlisted_evidence_is_rejected_and_web_keeps_twelve(self):
        self.extra_evidence();self.assertEqual(len(self.evidence()),13)
        self.assert_blocked('thừa/thiếu so với manifest')

    def test_unlisted_nested_uppercase_and_non_json_files_are_also_rejected(self):
        for name in ('nested/extra.json','EXTRA.JSON','unlisted.txt'):
            path=self.packet/'public/evidence'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('{}',encoding='utf-8')
            try:
                with self.subTest(name=name):self.assert_blocked('thừa/thiếu so với manifest')
            finally:path.unlink()

    def test_missing_or_changed_locked_evidence_is_rejected(self):
        self.evidence()[0].unlink();self.assert_blocked('đã thay đổi')

    def test_modified_evidence_bytes_fail_checksum_before_ingestion(self):
        path=self.evidence()[0];value=json.loads(path.read_text(encoding='utf-8'))
        value['limitations'].append('SIM: changed after lock')
        path.write_text(json.dumps(value),encoding='utf-8');self.assert_blocked('đã thay đổi')

    def test_even_manifest_listed_evidence_must_belong_to_selected_review_ids(self):
        path=self.extra_evidence();self.relock(extra=[path.relative_to(self.packet).as_posix()])
        report=self.report();report['review_units']=13;self.write_report(report)
        self.assert_blocked('không khớp chính xác tập phiếu')

    def test_duplicate_review_id_or_filename_mismatch_is_rejected(self):
        first,second=self.evidence()[:2]
        value=json.loads(second.read_text(encoding='utf-8'));value['review_id']=first.stem
        second.write_text(json.dumps(value),encoding='utf-8');self.relock()
        self.assert_blocked('bị trùng hoặc sai')

    def test_two_review_ids_cannot_duplicate_one_company_transaction(self):
        pairs={}
        for path in self.evidence():
            value=json.loads(path.read_text(encoding='utf-8'));pairs.setdefault(value['company_id'],[]).append((path,value))
        (first,a),(second,b)=next(values[:2] for values in pairs.values() if len(values)>1)
        b['transaction_id']=a['transaction_id'];b['source_record']['transaction_id']=a['transaction_id']
        second.write_text(json.dumps(b),encoding='utf-8');self.relock()
        self.assert_blocked('bị trùng hoặc sai')

    def test_foreign_company_and_source_record_identity_mismatch_are_rejected(self):
        path=self.evidence()[0];original=path.read_bytes()
        for change in ('company','source_record'):
            value=json.loads(original)
            if change=='company':value['company_id']=value['source_record']['company_id']='C999'
            else:value['source_record']['transaction_id']='SIM_DIFFERENT_TRANSACTION'
            path.write_text(json.dumps(value),encoding='utf-8');self.relock()
            with self.subTest(change=change):self.assert_blocked('bị trùng hoặc sai')
        path.write_bytes(original)

    def test_duplicate_selected_id_and_cross_company_model_selection_are_rejected(self):
        original=self.report()
        for change in ('duplicate','foreign'):
            report=copy.deepcopy(original);model=next(m for m in report['models'] if m['company_id']=='C001')
            model['selected_review_ids'][0]=model['selected_review_ids'][1] if change=='duplicate' else next(
                m['selected_review_ids'][0] for m in report['models'] if m['company_id']=='C002')
            self.write_report(report)
            with self.subTest(change=change):self.assert_blocked('Tập chọn model')

    def test_duplicate_model_and_mismatched_review_total_are_rejected(self):
        report=self.report();original=copy.deepcopy(report)
        report['models'].append(copy.deepcopy(report['models'][0]));self.write_report(report)
        self.assert_blocked('Tập chọn model')
        original['review_units']+=1;self.write_report(original)
        self.assert_blocked('không khớp chính xác tập phiếu')

    def test_partial_model_budget_is_not_accepted_as_equal_review_budget(self):
        report=self.report();model=report['models'][0]
        model['selected_review_ids'].pop();model['selected_for_review']-=1
        self.write_report(report);self.assert_blocked('ngân sách')

    def test_selection_missing_duplicate_rank_company_or_hash_is_rejected(self):
        original=self.selections()
        cases=[original[:-1],original+[original[0]]]
        for changes in (dict(rank='999'),dict(company_id='C999'),dict(evidence_sha256='0'*64),dict(review_id='UNKNOWN')):
            cases.append([dict(original[0],**changes)]+original[1:])
        for i,rows in enumerate(cases):
            self.write_selections(rows)
            with self.subTest(case=i):self.assert_blocked()

    def test_selection_schema_and_row_width_are_exact(self):
        original=(self.packet/'private/selection.csv').read_bytes()
        cases=[original.replace(b'review_id,',b'review_id,review_id,',1),original+b'ONLY_ONE_CELL\n',
               original.rstrip()+b',EXTRA_CELL\n']
        for i,payload in enumerate(cases):
            (self.packet/'private/selection.csv').write_bytes(payload);self.relock()
            with self.subTest(case=i):self.assert_blocked()

    def test_manifest_aliases_and_escaping_paths_are_rejected(self):
        manifest_path=self.packet/'manifest.json';original=json.loads(manifest_path.read_text(encoding='utf-8'))
        for name in ('../outside.json','private/../public/README.md','public\\README.md','/absolute.json','private//comparison.json'):
            manifest=copy.deepcopy(original);manifest['files'][name]='0'*64
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            with self.subTest(name=name):self.assert_blocked('Tên tệp hoặc checksum')

    def test_duplicate_manifest_json_key_is_not_silently_overwritten(self):
        path=self.packet/'manifest.json';payload=path.read_text(encoding='utf-8').rstrip()
        path.write_text(payload[:-1]+',"version":"company-ml-comparison-v1"}',encoding='utf-8')
        self.assert_blocked('JSON của gói không hợp lệ')

    def test_changed_evidence_during_loading_is_rejected_without_web_writes(self):
        target=self.evidence()[0].resolve();original_read=Path.read_bytes;changed=[False]
        def read_then_change(path):
            payload=original_read(path)
            if path==target and not changed[0]:
                value=json.loads(payload);value['limitations'].append('SIM mutation during verification')
                path.write_text(json.dumps(value),encoding='utf-8');changed[0]=True
            return payload
        with patch.object(Path,'read_bytes',read_then_change):
            with self.assertRaisesRegex(ValueError,'thay đổi trong lúc kiểm tra'):self.service.import_packet(self.packet)
        self.assertTrue(changed[0]);self.assertEqual(self.database_state(),self.before)

    def test_changed_manifest_during_loading_is_rejected(self):
        path=(self.packet/'manifest.json').resolve();original_read=Path.read_bytes;changed=[False]
        def read_then_change(target):
            payload=original_read(target)
            if target==path and not changed[0]:
                path.write_bytes(payload+b'\n');changed[0]=True
            return payload
        with patch.object(Path,'read_bytes',read_then_change):
            with self.assertRaisesRegex(ValueError,'thay đổi trong lúc kiểm tra'):self.service.import_packet(self.packet)
        self.assertEqual(self.database_state(),self.before)

    def test_mutable_review_csv_is_not_part_of_frozen_evidence_inventory(self):
        path=self.packet/'human_reviews.csv';path.write_bytes(path.read_bytes()+b'\n')
        packet=load_packet(self.packet)
        self.assertEqual(packet['manifest_sha256'],self.verified['manifest_sha256'])
        self.assertEqual(len(packet['units']),12)


if __name__=='__main__':unittest.main()
