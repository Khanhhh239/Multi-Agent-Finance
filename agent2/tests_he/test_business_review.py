"""Demo feedback must preserve unknowns, scope, revision history and provenance."""
from copy import deepcopy
from pathlib import Path
import unittest

from experiments.he_inference.business_review import (FEEDBACK,validate_packet,validate_feedback,
    merge_feedback,summarize,packet_hash)
from experiments.he_inference.protocol import read_json,canonical,sha

PACKET=Path(__file__).resolve().parents[2]/'Agent2_Spec_v2_1/evidence/HE/business_review_demo_20261112/packet/packet.json'


class BusinessReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet=read_json(PACKET)
    def row(self,index=0,revision=1):
        c=self.packet['cases'][index]
        return dict(case_id=c['case_id'],revision=revision,reviewer_name_declared='Người rà fixture',
            resolution='inconclusive',usefulness='not_assessed',explanation='Chỉ có bản ghi mô phỏng.',
            action='Yêu cầu kế toán bổ sung phê duyệt và chứng từ chuyển tiền.',missing_materials='Chưa có chứng từ gốc.',
            reviewed_evidence_ids=[c['evidence'][0]['evidence_id']],checks_completed=False,active_ms=60000,
            timer_basis='unverified_browser_active_time',submitted_at='2026-11-12T15:00:00+00:00')
    def feedback(self,*rows):return dict(version=FEEDBACK,packet_id=self.packet['packet_id'],reviews=list(rows))

    def test_blank_packet_is_not_zero_effectiveness_or_completed_reviews(self):
        result=summarize(self.packet,self.feedback())
        self.assertEqual(result['status'],'awaiting_human_review')
        self.assertEqual(sum(c['unreviewed'] for c in result['companies']),10)
        for c in result['companies']:
            self.assertIsNone(c['declared_useful_fraction']);self.assertIsNone(c['browser_active_minutes'])
        self.assertFalse(result['business_effectiveness_verified']);self.assertFalse(result['training_eligible'])

    def test_usefulness_is_independent_of_resolution_and_no_training_label(self):
        r=self.row();r['usefulness']='yes';s=summarize(self.packet,self.feedback(r))
        self.assertEqual(s['companies'][0]['inconclusive'],1)
        self.assertEqual(s['companies'][0]['declared_useful'],1)
        self.assertFalse(s['business_effectiveness_verified']);self.assertFalse(s['feature_expansion_recommended'])

    def test_unknown_usefulness_is_not_counted_as_no(self):
        s=summarize(self.packet,self.feedback(self.row()))['companies'][0]
        self.assertEqual(s['usefulness_not_assessed'],1);self.assertEqual(s['declared_not_useful'],0)
        self.assertIsNone(s['declared_useful_fraction']);self.assertIsNone(s['declared_useful_per_browser_active_minute'])

    def test_useful_requires_action_and_inconclusive_requires_missing_materials(self):
        for field,value in [('action',''),('missing_materials','')]:
            r=self.row();r[field]=value;r['usefulness']='yes'
            with self.subTest(field=field),self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))

    def test_conclusion_requires_references_and_completed_checks_declaration(self):
        for fields in [dict(checks_completed=False),dict(checks_completed=True,reviewed_evidence_ids=[])]:
            r=self.row();r.update(resolution='legitimate',**fields)
            with self.subTest(fields=fields),self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))

    def test_foreign_packet_case_and_evidence_are_rejected(self):
        foreign=next(c for c in self.packet['cases'] if c['company_id']=='C002')
        r=self.row();r['reviewed_evidence_ids']=[foreign['evidence'][0]['evidence_id']]
        with self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))
        r=self.row();r['case_id']='unknown'
        with self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))
        f=self.feedback(self.row());f['packet_id']='other'
        with self.assertRaises(ValueError):validate_feedback(self.packet,f)

    def test_extra_evidence_file_cannot_increase_case_count_or_be_cited(self):
        p=deepcopy(self.packet);p['cases'][0]['evidence'].append(p['cases'][0]['evidence'][0])
        with self.assertRaises(ValueError):validate_packet(p)
        r=self.row();r['reviewed_evidence_ids'].append('ev_outside_manifest')
        with self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))

    def test_simulated_record_cannot_be_promoted_to_verified_original(self):
        p=deepcopy(self.packet);p['cases'][0]['evidence'][0]['original_verified']=True;p['packet_id']='brp_'+packet_hash(p)
        with self.assertRaises(ValueError):validate_packet(p)

    def test_future_evidence_stays_invalid_even_when_json_checksums_recomputed(self):
        p=deepcopy(self.packet);e=p['cases'][0]['evidence'][0]
        e['source_record']['observed_at']='2030-01-01T00:00:00+07:00'
        e['evidence_id']='ev_'+sha(canonical(e['source_record']));p['packet_id']='brp_'+packet_hash(p)
        with self.assertRaises(ValueError):validate_packet(p)

    def test_additional_feedback_preserves_unrelated_reviews_and_deduplicates(self):
        a,b=self.row(0),self.row(5)
        merged=merge_feedback(self.packet,[self.feedback(a),self.feedback(b),self.feedback(a)])
        self.assertEqual(len(merged['reviews']),2)
        self.assertEqual(sum(c['reviewed'] for c in summarize(self.packet,merged)['companies']),2)

    def test_conflicts_and_missing_revision_history_are_explicit(self):
        a=self.row();b=deepcopy(a);b['explanation']='Kết quả khác cùng phiên bản.'
        with self.assertRaises(ValueError):merge_feedback(self.packet,[self.feedback(a),self.feedback(b)])
        with self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(self.row(revision=2)))

    def test_new_revision_preserves_audit_time_and_uses_latest_decision_once(self):
        a=self.row();b=self.row(revision=2);b.update(usefulness='yes',active_ms=30000)
        s=summarize(self.packet,self.feedback(a,b));self.assertEqual(s['review_revisions'],2)
        self.assertEqual(s['companies'][0]['reviewed'],1);self.assertEqual(s['companies'][0]['declared_useful'],1)
        self.assertEqual(s['companies'][0]['browser_active_minutes'],1.5)

    def test_browser_timing_and_identity_cannot_claim_verification_or_label(self):
        for field,value in [('timer_basis','server_verified'),('active_ms',0),('active_ms',float('inf')),('active_ms',1e-300),('training_label',1)]:
            r=self.row();r[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_feedback(self.packet,self.feedback(r))


if __name__=='__main__':unittest.main()
