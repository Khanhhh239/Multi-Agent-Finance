"""Native/canonical parity and causal snapshot integration for B5/E4."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
from finance_input import schema,check_core,AccessScope
from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.vendor_identity_demo import prepare,MODES
from sme_fraud.snapshot_features import build_feature_rows
from sme_fraud.rule_sources import _resolve
from sme_fraud.rule_evaluation import _evaluate
from sme_fraud.rules import score_rules
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.snapshot_analysis import analyze_snapshot
from test_snapshots import commit_fields

ROOT=Path(__file__).resolve().parents[1]
RESULT_SCHEMA=json.loads((ROOT/'sme_fraud/rule_results.schema.json').read_text('utf-8'))


def scope(company='C001'):return AccessScope('native-demo',frozenset({company}),'snapshot-review',frozenset({'data.import'}))


def evaluate(data,as_of,company='C001'):
    frame=build_feature_rows(data,scope(company),as_of);private,public=_resolve(data,frame,scope(company));outputs=[]
    for meta in frame['rows']:
        key=meta['record_id'],meta['revision'];r=_evaluate(private[key],public[key],scope(company),meta);jsonschema.validate(r,RESULT_SCHEMA);outputs.append(r)
    return outputs


def rule(output,code='B5'):return next(r for r in output['rules'] if r['rule_id']==code)


def commit(store,data,company='C001'):
    authority=scope(company);d=store.upload(authority,canonical(data),'vendor-identity.json','vendor-upload');p=store.preview(authority,d['import_id'],1)
    return store.commit(authority,d['import_id'],commit_fields(p),'vendor-commit')['snapshot']['snapshot_id']


class VendorIdentitySnapshot(unittest.TestCase):
    def test_opt_in_schema_does_not_mutate_old_versions_or_default(self):
        self.assertEqual(schema()['properties']['contract_version']['const'],'1.1.0')
        self.assertNotIn('phone',schema('1.1.0')['$defs']['vendor']['properties'])
        data,_,_=prepare();self.assertFalse(check_core(data,scope()))
        data['contract_version']='1.1.0';self.assertTrue(check_core(data,scope()))

    def test_same_sources_same_time_match_native_evidence_points_and_alias(self):
        for company in ('C001','C002'):
            for mode in MODES:
                with self.subTest(company=company,mode=mode):
                    data,native,as_of=prepare(mode,company);self.assertNotEqual(validate_input(data,scope(company))['status'],'rejected')
                    reference=score_rules(native);hits=[h for h in reference['hits'] if h['rule_id']=='B5'];output=evaluate(data,as_of,company)[0]
                    for code in ('B5','E4'):
                        actual=rule(output,code);self.assertEqual(actual['matched'],bool(hits));self.assertTrue(actual['available']);self.assertEqual(actual['score'],0)
                        self.assertEqual(actual['intrinsic_points'],hits[0]['intrinsic_points'] if hits else 0)
                        if hits:
                            self.assertEqual(actual['details']['evidence'],hits[0]['evidence']);self.assertEqual(actual['details']['hits'][0]['evidence_id'],hits[0]['evidence_id'])
                            self.assertEqual(actual['details']['hits'][0]['aliases'],['E4']);self.assertEqual(actual['details']['hits'][0]['score_reason'],hits[0]['score_reason'])
                    self.assertEqual(rule(output,'B5')['details'],rule(output,'E4')['details']);self.assertIsNone(output['aggregate']['score'])

    def test_missing_identity_fields_are_unavailable_never_false_or_zero(self):
        for field in ('phone','related_party_disclosed_at','address','bank_account'):
            for missing in ('absent','null','flag'):
                data,_,as_of=prepare()
                if missing=='null':data['vendors'][1][field]=None
                else:data['vendors'][1].pop(field)
                if missing=='flag':data['vendors'][1]['missing_fields']={field:'unknown'}
                output=evaluate(data,as_of)[0]
                for code in ('B5','E4'):
                    r=rule(output,code);self.assertFalse(r['available']);self.assertIsNone(r['matched']);self.assertIsNone(r['score']);self.assertTrue(any(g['field']==field for g in r['gaps']))

    def test_future_vendor_and_late_revision_do_not_change_past_results(self):
        data,_,as_of=prepare('control');before=evaluate(data,as_of)
        future=deepcopy(data['vendors'][1]);future['revision']=2;future['bank_account']=data['vendors'][0]['bank_account'];future['observed_at']='2026-01-01T00:00:00+07:00'
        data['vendors'].append(future);self.assertEqual(evaluate(data,as_of),before)
        future['record_id']='FUTURE_ONLY';future['source']['record_id']='FUTURE_ONLY';self.assertEqual(evaluate(data,as_of),before)

    def test_effective_date_and_noncurrent_reference_are_resolved_before_matching(self):
        data,_,as_of=prepare();future=deepcopy(data['vendors'][1]);future['revision']=2;future['observed_at']='2025-01-01T00:00:00+07:00';future['effective_at']='2026-01-01T00:00:00+07:00';future['phone']='0902333333';future['bank_account']='DIFFERENT';data['vendors'].append(future)
        self.assertTrue(rule(evaluate(data,as_of)[0])['matched'])
        data['transactions'][0]['vendor_ref']['revision']=99
        self.assertEqual(validate_input(data,scope())['status'],'rejected')
        with self.assertRaises(ImportFailure):evaluate(data,as_of)

    def test_late_known_master_is_unavailable_instead_of_retimed_native_source(self):
        data,_,as_of=prepare();data['transactions'][0]['observed_at']='2025-08-14T00:00:00+07:00';data['vendors'][1]['observed_at']='2025-08-13T00:00:00+07:00'
        r=rule(evaluate(data,'2025-08-14T00:00:00+07:00')[0]);self.assertFalse(r['available']);self.assertTrue(any(g['code']=='native_master_not_known_at_event' for g in r['gaps']))

    def test_scope_and_source_integrity_are_checked_before_evaluation(self):
        data,_,as_of=prepare();frame=build_feature_rows(data,scope(),as_of);private,public=_resolve(data,frame,scope());meta=frame['rows'][0];key=meta['record_id'],meta['revision']
        with self.assertRaises(ImportFailure):_evaluate(private[key],public[key],scope('C002'),meta)
        changed=deepcopy(private[key]);changed['vendors'][1]['phone']='CHANGED'
        with self.assertRaises(ValueError):_evaluate(changed,public[key],scope(),meta)

    def test_empty_known_phone_is_not_fabricated_and_bad_disclosure_time_rejected(self):
        data,_,as_of=prepare('control');data['vendors'][1]['phone']='';self.assertFalse(rule(evaluate(data,as_of)[0])['matched'])
        data['vendors'][0]['related_party_disclosed_at']='2025-09-01T00:00:00+07:00'
        r=validate_input(data,scope());self.assertEqual(r['status'],'rejected');self.assertTrue(any(e['code']=='DISCLOSURE_TIME' for e in r['errors']))

    def test_unknown_contact_placeholder_is_not_a_negative_finding(self):
        for field in ('phone','address'):
            data,_,as_of=prepare('control');data['vendors'][1][field]='UNKNOWN';r=rule(evaluate(data,as_of)[0])
            self.assertFalse(r['available']);self.assertIsNone(r['matched']);self.assertTrue(any(g['code']=='identity_content_unknown' for g in r['gaps']))

    def test_old_snapshot_retains_missing_sources_without_fake_upgrade(self):
        data,_,as_of=prepare();data['contract_version']='1.1.0'
        for v in data['vendors']:v.pop('phone');v.pop('related_party_disclosed_at')
        r=evaluate(data,as_of)[0]
        for code in ('B5','E4'):self.assertFalse(rule(r,code)['available']);self.assertTrue(any(g['code']=='field_not_in_input_contract' for g in rule(r,code)['gaps']))

    def test_immutable_snapshot_pipeline_keeps_all_rows_does_not_fit_or_double_score(self):
        for company in ('C001','C002'):
            data,_,as_of=prepare('signal',company)
            for i in range(4):
                extra=deepcopy(data['transactions'][0]);extra['record_id']='EXTRA_'+str(i);extra['source']['record_id']=extra['record_id'];data['transactions'].append(extra)
            before=canonical(data)
            with tempfile.TemporaryDirectory() as directory:
                store=SnapshotStore(Path(directory)/'snapshot.sqlite3');identity=commit(store,data,company)
                with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('No inference fit')) as fit:
                    output=score_snapshot(store,scope(company),identity,as_of,methods=('ecod',))
                fit.assert_not_called();self.assertEqual(output['row_count'],5)
                for row in output['rows']:
                    r=row['methods']['rules']['details']['rule_results'];self.assertEqual(len(r['rules']),35)
                    for code in ('B5','E4'):self.assertTrue(rule(r,code)['matched']);self.assertEqual(rule(r,code)['score'],0)
                    self.assertEqual(row['methods']['ecod']['reason']['code'],'artifact_missing');self.assertIsNone(row['methods']['rules']['score'])
                analyzed=analyze_snapshot(store,scope(company),identity,as_of,technical=True)
                self.assertEqual(analyzed['row_count'],5)
                for row in analyzed['rows']:
                    self.assertTrue(all(next(r for r in row['rule_coverage']['rules'] if r['rule_id']==code)['status']=='evaluated_hit' for code in ('B5','E4')))
            self.assertEqual(before,canonical(data))


if __name__=='__main__':unittest.main()
