"""Blind sampling and human-outcome validation must never manufacture independent reviews."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.independent_ml_review import (choose_units,unit_key,row_available,public_row,evidence_for,
                                            validate_reviews,PRIMARY_FIELDS,ADJ_FIELDS)
from sme_fraud.compare_shadow import simulation,write_csv
from sme_fraud.feature_contract import sha
from sme_fraud.shadow_scoring import instant
import test_compare_shadow as fixtures


class IndependentMlReviewTest(unittest.TestCase):
    def test_reference_sampling_is_deterministic_and_excludes_disagreements(self):
        values = [9,8,1,2,3,4,7,6,5]
        cases = [fixtures.case(chr(65+i),20-i,float(score)) for i,score in enumerate(values)]
        snapshots = fixtures.snapshots([cases,cases])
        selected = simulation(snapshots,5)['selections']
        # Frozen CSV values are text; sampling must validate the same costs.
        selected = [{k:str(v) for k,v in r.items()} for r in selected]
        first,populations = choose_units(snapshots,selected,'001',seed=20261022)
        second,_ = choose_units(snapshots,selected,'001',seed=20261022)
        self.assertEqual(set(first),set(second))
        groups = [r['sample_group'] for r in first.values()]
        self.assertIn('disagreement',groups)
        self.assertEqual(groups.count('reference_common_selected'),1)
        self.assertEqual(groups.count('reference_neither_selected'),1)
        self.assertEqual(len(first),len(set(first)))
        for row in first.values():
            if row['sample_group'].startswith('reference_'):
                self.assertEqual(row['inclusion_probability'],1/row['stratum_population'])
        self.assertTrue(all(n>0 for n in populations.values()))

    def test_frozen_selected_scope_cannot_be_changed(self):
        cases = [fixtures.case('A')]
        snapshots = fixtures.snapshots([cases])
        selected = simulation(snapshots,5)['selections']
        selected[0]['case_scope_hash'] = 'changed'
        with self.assertRaisesRegex(ValueError,'scope/cost/cutoff'):
            choose_units(snapshots,selected,'001',seed=1)

    def test_unit_identity_uses_instants_not_timezone_spelling(self):
        self.assertEqual(unit_key('001','CASE','scope','2025-07-02T00:00:00+07:00'),
                         unit_key('001','CASE','scope','2025-07-01T17:00:00+00:00'))

    def test_future_and_unversioned_rows_are_not_backfilled(self):
        cutoff = instant('2025-07-02T00:00:00+07:00')
        self.assertFalse(row_available(dict(recorded_at='2025-07-02T00:00:00+07:00'),'invoices',cutoff))
        self.assertFalse(row_available(dict(observed_at='2025-07-01T10:00:00+07:00',verified_at='2025-07-03T10:00:00+07:00'),'changes',cutoff))
        self.assertFalse(row_available(dict(name='unknown'),'vendors',cutoff))
        self.assertTrue(row_available(dict(date='2025-12-31'),'calendar',cutoff))
        self.assertTrue(row_available(dict(observed_at='2025-07-01T10:00:00+07:00',effective_to='2026-01-01'),'policy',cutoff))

    def test_public_source_rows_remove_predictions_and_company_linkage(self):
        row = public_row(dict(company_id='C001',amount_vnd='50',if_score='.8',priority='cao',
                              is_fraud='1',expected_condition='true',role='accountant'),'DN03')
        self.assertEqual(row,dict(company_id='DN03',amount_vnd='50',role='accountant'))

    def test_evidence_context_is_company_scoped_and_as_of(self):
        row = fixtures.case('T1')
        descriptor = dict(case=row,company_id='C001',cutoff_exclusive='2025-07-02T00:00:00+07:00')
        tx = dict(transaction_id='T1',company_id='C001',posted_at='2025-07-01T10:00:00+07:00',invoice_id='I1',vendor_id='V1')
        tables = dict(transactions=[tx],vendors=[dict(company_id='C001',vendor_id='V1',recorded_at='2025-07-01T09:00:00+07:00'),
            dict(company_id='C002',vendor_id='OTHER',recorded_at='2025-07-01T09:00:00+07:00')],
            invoices=[dict(company_id='C001',invoice_id='I1',recorded_at='2025-07-03T09:00:00+07:00')])
        evidence = evidence_for(descriptor,tables,'DN01')
        self.assertEqual(len(evidence['tables']['vendors']),1)
        self.assertEqual(evidence['tables']['vendors'][0]['company_id'],'DN01')
        self.assertNotIn('invoices',evidence['tables'])
        self.assertNotIn('excluded_rows',evidence)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.prepared = self.root/'prepared'
        public,private = self.prepared/'public',self.prepared/'private'
        folder = public/'evidence/R1';folder.mkdir(parents=True);private.mkdir()
        (folder/'evidence.json').write_text(json.dumps(dict(tables=dict(member_transactions=[]))),encoding='utf-8')
        unit = dict(review_unit_id='R1',company_code='DN01',cutoff_exclusive='2025-07-02T00:00:00+07:00',
                    evidence_sha256=sha(folder/'evidence.json'))
        manifest = dict(units=[unit],source_origin='synthetic_process_simulation',
                        readonly_sha256={'evidence/R1/evidence.json':sha(folder/'evidence.json')})
        (public/'review_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (private/'unit_mapping.json').write_text(json.dumps([dict(review_unit_id='R1',sample_group='disagreement')]),encoding='utf-8')
        commitment = dict(public_manifest_sha256=sha(public/'review_manifest.json'),mapping_sha256=sha(private/'unit_mapping.json'))
        (private/'prepared_commitment.json').write_text(json.dumps(commitment),encoding='utf-8')
        (private/'reviewer_assignment.json').write_text(json.dumps(dict(primary_reviewer_id='HUMAN_R1',adjudicator_id='HUMAN_R2')),encoding='utf-8')
        self.primary = dict(unit,condition_present='true',actionable='true',document_request_needed='false',
            missing_evidence='',business_action='Đối chiếu khoản chi với hóa đơn',rationale='Nguồn cần đối chiếu',
            evidence_refs='member_transactions',timing_method='measured_interval',active_review_minutes='12',started_at='2026-10-22T09:00:00+07:00',
            finished_at='2026-10-22T09:15:00+07:00',paused_minutes='3',primary_reviewer_id='HUMAN_R1',
            reviewed_at='2026-10-22T09:16:00+07:00',independent_of_development='true',blind_to_arm_and_score='true')
        self.adjudication = dict(unit,adjudication_status='confirmed',condition_present='true',actionable='true',
            document_request_needed='false',missing_evidence='',business_action='Đối chiếu khoản chi',rationale='Đồng ý theo nguồn',
            evidence_refs='member_transactions',timing_method='measured_stopwatch',active_adjudication_minutes='5',adjudicator_id='HUMAN_R2',
            adjudicated_at='2026-10-22T09:30:00+07:00',independent_of_development='true',blind_to_arm_and_score='true')

    def validate(self,p=None,a=None,name='result'):
        p = self.primary if p is None else p
        a = self.adjudication if a is None else a
        primary,adj = self.root/(name+'_p.csv'),self.root/(name+'_a.csv')
        write_csv(primary,[p],PRIMARY_FIELDS);write_csv(adj,[a],ADJ_FIELDS)
        return validate_reviews(self.prepared,primary,adj,self.root/name)

    def test_blank_forms_do_not_create_outcomes_or_zero_minutes(self):
        unit = {k:self.primary[k] for k in ('review_unit_id','company_code','cutoff_exclusive','evidence_sha256')}
        result = self.validate(unit,unit)
        self.assertEqual(result['validated_independent_units'],0)
        self.assertEqual(result['pending_units'],1)
        self.assertIsNone(result['measured_primary_minutes'])
        self.assertIsNone(result['actionable_gain'])

    def test_valid_attested_measured_review_and_adjudication_are_separate(self):
        result = self.validate()
        self.assertEqual(result['validated_independent_units'],1)
        self.assertEqual(result['measured_primary_minutes'],12)
        self.assertEqual(result['measured_adjudication_minutes'],5)
        self.assertEqual(result['real_sme_reviews'],0)

    def test_unknown_outcome_with_missing_documents_is_not_a_negative(self):
        p,a = copy.deepcopy(self.primary),copy.deepcopy(self.adjudication)
        for row in (p,a):
            row.update(condition_present='unknown',actionable='unknown',document_request_needed='true',missing_evidence='Hóa đơn gốc')
        a['adjudication_status']='unresolved'
        result = self.validate(p,a)
        self.assertEqual(result['validated_independent_units'],1)
        self.assertEqual(result['known_actionable_outcomes'],0)
        self.assertEqual(result['unresolved_outcomes'],1)
        self.assertEqual(result['missing_evidence_units'],1)

    def test_same_nonindependent_or_unblinded_reviewer_cannot_count(self):
        for i,(field,value) in enumerate((('adjudicator_id','HUMAN_R1'),('independent_of_development','false'),
                                          ('blind_to_arm_and_score','false'))):
            a = dict(self.adjudication,**{field:value})
            result = self.validate(a=a,name='bad'+str(i))
            self.assertEqual(result['validated_independent_units'],0)
            self.assertEqual(result['invalid_units'],1)

    def test_invalid_or_estimated_time_cannot_pass_as_measured_active_minutes(self):
        for i,value in enumerate(('0','-2','nan','inf','10')):
            result = self.validate(p=dict(self.primary,active_review_minutes=value),name='time'+str(i))
            self.assertEqual(result['validated_independent_units'],0)
        result = self.validate(p=dict(self.primary,timing_method='estimated'),name='estimate')
        self.assertEqual(result['validated_independent_units'],0)

    def test_evidence_binding_or_unknown_reference_is_rejected(self):
        result = self.validate(p=dict(self.primary,evidence_refs='NOT_IN_PACKET'))
        self.assertEqual(result['invalid_units'],1)
        with self.assertRaisesRegex(ValueError,'binding changed'):
            self.validate(p=dict(self.primary,evidence_sha256='changed'),name='changed')

    def test_readonly_evidence_modification_is_detected(self):
        (self.prepared/'public/evidence/R1/evidence.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'evidence changed'):
            self.validate()

    def test_private_validation_cannot_be_written_into_public_packet(self):
        primary,adj = self.root/'p.csv',self.root/'a.csv'
        write_csv(primary,[self.primary],PRIMARY_FIELDS);write_csv(adj,[self.adjudication],ADJ_FIELDS)
        with self.assertRaisesRegex(ValueError,'must not be published'):
            validate_reviews(self.prepared,primary,adj,self.prepared/'public/private_validation')


if __name__=='__main__':
    unittest.main()
