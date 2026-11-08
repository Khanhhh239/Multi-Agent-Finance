import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sme_fraud.evidence_cases import EvidenceCase, prepare as evidence_case
from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.feature_contract import cache_contract
from sme_fraud.generate import write_csv
from sme_fraud.real_source_acceptance import (
    COVERAGE_FIELDS, PACKET_FIELDS, RULES, RULE_SOURCES, _coverage_by_rule,
    _metric, _validate_reviews, canonical_sha, evaluate,
    predictions_for_packet, prepare, review_universe,
)
from sme_fraud.rules import INPUT_TABLES


class RealSourceAcceptanceTest(unittest.TestCase):
    def make_minimal_dataset(self, folder):
        case = EvidenceCase(810)
        case.pay()
        case.score()
        for name in INPUT_TABLES:
            write_csv(folder/f'{name}.csv', case.tables[name])
        write_csv(folder/'features.csv', case.features,
                  ['transaction_id', *FEATURE_DESCRIPTIONS])
        files = {}
        for path in folder.glob('*.csv'):
            files[path.name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (folder/'manifest.json').write_text(json.dumps(dict(version='real-test', files=files,
            feature_columns=list(FEATURE_DESCRIPTIONS), feature_contract=cache_contract(files))),
                                           encoding='utf-8')

    def test_prepare_does_not_claim_real_acceptance_or_disclose_predictions(self):
        runtime = Path('.runtime').resolve()
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as source, tempfile.TemporaryDirectory(dir=runtime) as target:
            data, output = Path(source), Path(target)/'prepared'
            self.make_minimal_dataset(data)
            result = prepare(data, output, '2025-01-01T00:00:00+07:00',
                             '2025-12-31T23:59:59+07:00')
            self.assertEqual(result['status'], 'awaiting_real_data')
            with (output/'review_packet.csv').open(encoding='utf-8-sig', newline='') as stream:
                fields = csv.DictReader(stream).fieldnames
            self.assertNotIn('prediction', fields)
            commitment = json.loads((output/'prediction_commitment.json').read_text(encoding='utf-8'))
            self.assertIn('prediction_sha256', commitment)
            self.assertNotIn('predictions', commitment)

    def test_evaluate_empty_real_source_packet_stays_not_accepted(self):
        runtime = Path('.runtime').resolve()
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as source, tempfile.TemporaryDirectory(dir=runtime) as target:
            data, root = Path(source), Path(target)
            prepared, result_folder = root/'prepared', root/'result'
            self.make_minimal_dataset(data)
            prepare(data, prepared, '2025-01-01T00:00:00+07:00',
                    '2025-12-31T23:59:59+07:00')
            reviews, coverage, criteria = root/'reviews.csv', root/'coverage.csv', root/'criteria.json'
            write_csv(reviews, [], list(PACKET_FIELDS))
            write_csv(coverage, [], list(COVERAGE_FIELDS))
            gates = dict(min_evaluable=2, min_condition_present=1,
                         min_condition_absent=1, min_precision=.8, min_recall=.8,
                         max_information_gap_rate=.05)
            criteria.write_text(json.dumps(dict(policy_status='draft', approved_by='',
                approved_at='', rules={rule:gates for rule in RULES})), encoding='utf-8')
            result = evaluate(data, prepared, reviews, coverage, criteria, result_folder)
            self.assertEqual(result['status'], 'not_accepted')
            self.assertTrue(all(item['status'] == 'awaiting_real_data'
                                for item in result['rules'].values()))

    def test_criteria_cannot_be_changed_after_predictions_are_frozen(self):
        runtime = Path('.runtime').resolve()
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as source, tempfile.TemporaryDirectory(dir=runtime) as target:
            data, root = Path(source), Path(target)
            prepared = root/'prepared'
            self.make_minimal_dataset(data)
            gates = dict(min_evaluable=2, min_condition_present=1,
                         min_condition_absent=1, min_precision=.8, min_recall=.8,
                         max_information_gap_rate=.05)
            criteria = root/'criteria.json'
            policy = dict(policy_status='draft', approved_by='', approved_at='',
                          rules={rule:gates for rule in RULES})
            criteria.write_text(json.dumps(policy), encoding='utf-8')
            prepare(data, prepared, '2025-01-01T00:00:00+07:00',
                    '2025-12-31T23:59:59+07:00', criteria)
            policy.update(policy_status='approved', approved_by='OWNER',
                          approved_at='2026-01-01T00:00:00+07:00')
            criteria.write_text(json.dumps(policy), encoding='utf-8')
            reviews, coverage = root/'reviews.csv', root/'coverage.csv'
            write_csv(reviews, [], list(PACKET_FIELDS))
            write_csv(coverage, [], list(COVERAGE_FIELDS))
            with self.assertRaisesRegex(ValueError, 'criteria differ'):
                evaluate(data, prepared, reviews, coverage, criteria, root/'result')

    def test_source_scope_predictions_cover_f3_and_f4(self):
        for rule, variant, unit_type in [('F3', 'positive', 'document_series'),
                                         ('F4', 'positive', 'receivable_invoice')]:
            with self.subTest(rule=rule):
                case, row, _, _ = evidence_case(rule, variant, 811)
                case.score()
                packet = review_universe(case.tables, '2025-01-01T00:00:00+07:00',
                                         row['posted_at'], 'manifest')
                predictions = predictions_for_packet(case.tables, case.features, packet,
                                                     row['posted_at'])
                target = next(p for p in predictions if p['rule_id'] == rule and
                              p['unit_type'] == unit_type)
                self.assertTrue(target['prediction'])
                self.assertEqual(target['detector_status'], 'evaluated')

    def test_transaction_prediction_uses_confirmed_c4_source(self):
        case, row, _, _ = evidence_case('C4', 'positive', 812)
        case.score()
        packet = review_universe(case.tables, '2025-01-01T00:00:00+07:00',
                                 row['posted_at'], 'manifest')
        prediction = next(p for p in predictions_for_packet(case.tables, case.features,
                          packet, row['posted_at']) if p['rule_id'] == 'C4')
        self.assertTrue(prediction['prediction'])

    def test_f1_acceptance_ignores_proxy_and_uses_three_confirmed_sources(self):
        case = EvidenceCase(813)
        case.at = case.at.replace(day=28)
        row = case.pay(kind='adjustment', amount=50_000_000)
        case.score()
        packet = [dict(company_id='C001', rule_id='F1', unit_type='transaction',
                       unit_id=row['transaction_id'])]
        proxy = predictions_for_packet(case.tables, case.features, packet, row['posted_at'])[0]
        self.assertFalse(proxy['prediction'])

        case.tables['journal_audit_log'] = [dict(audit_id='AUD', company_id='C001',
            employee_id=case.maker['employee_id'], transaction_id=row['transaction_id'],
            entry_origin='manual', entered_at=row['created_at'], observed_at=row['posted_at'],
            evidence_id='AUDIT_LOG')]
        case.tables['closing_periods'] = [case.approved(closing_id='CLOSE',
            period_start='2025-09-01', period_end='2025-09-30',
            closing_at='2025-09-30T23:59:59+07:00')]
        case.tables['materiality_policies'] = [case.approved(policy_id='MAT',
            effective_from='2025-01-01', effective_to='2025-12-31',
            materiality_vnd=10_000_000)]
        confirmed = predictions_for_packet(case.tables, case.features, packet,
                                           row['posted_at'])[0]
        self.assertTrue(confirmed['prediction'])

    def test_review_requires_two_people_and_a_frozen_manifest(self):
        packet = [{field: '' for field in PACKET_FIELDS}]
        packet[0].update(review_id='R1', company_id='C1', rule_id='F1',
                         unit_type='transaction', unit_id='T1',
                         source_manifest_sha256='manifest', sample_weight='1')
        review = dict(packet[0], condition_present='1', information_gap='0',
                      primary_reviewer_id='same', adjudicator_id='same',
                      reviewed_at='2026-01-02T00:00:00+07:00',
                      adjudicated_at='2026-01-03T00:00:00+07:00',
                      rationale='Hồ sơ xác nhận', blind_to_prediction='1',
                      sample_weight='1', evidence_id='EV1')
        _, errors = _validate_reviews(packet, [review],
            '2025-12-31T23:59:59+07:00', 'manifest')
        self.assertTrue(any('reviewers_not_independent' in error for error in errors))
        review['adjudicator_id'] = 'second'
        _, errors = _validate_reviews(packet, [review],
            '2025-12-31T23:59:59+07:00', 'different')
        self.assertTrue(any('manifest_mismatch' in error for error in errors))

    def test_coverage_requires_every_company_and_all_rule_sources(self):
        base = dict(coverage_id='CV', rule_id='F1',
            covered_from='2025-01-01T00:00:00+07:00',
            covered_through='2025-12-31T23:59:59+07:00',
            source_names='|'.join(RULE_SOURCES['F1']), completeness_status='complete',
            data_origin='real_sme_export', attested_by='OWNER',
            attested_at='2026-01-02T00:00:00+07:00', evidence_id='EXPORT',
            source_manifest_sha256='manifest', notes='')
        ready, _ = _coverage_by_rule([{**base, 'company_id':'C1'}], {'C1','C2'},
            base['covered_from'], base['covered_through'], 'manifest')
        self.assertFalse(ready['F1'])

    def test_metric_distinguishes_acceptance_from_quality_failure(self):
        packet = [dict(review_id='P', company_id='C1', rule_id='F1',
                       unit_type='transaction', unit_id='P'),
                  dict(review_id='N', company_id='C1', rule_id='F1',
                       unit_type='transaction', unit_id='N')]
        reviews = {
            'P': dict(information_gap='0', condition_present='1', sample_weight='1'),
            'N': dict(information_gap='0', condition_present='0', sample_weight='1'),
        }
        predictions = {
            ('C1','F1','transaction','P'): dict(prediction=True),
            ('C1','F1','transaction','N'): dict(prediction=False),
        }
        gates = dict(min_evaluable=2, min_condition_present=1,
                     min_condition_absent=1, min_precision=.9, min_recall=.9,
                     max_information_gap_rate=0)
        metric, _ = _metric('F1', packet, reviews, predictions, gates, True, True, True)
        self.assertEqual(metric['status'], 'accepted')
        predictions[('C1','F1','transaction','P')]['prediction'] = False
        metric, _ = _metric('F1', packet, reviews, predictions, gates, True, True, True)
        self.assertEqual(metric['status'], 'rejected')
        self.assertIn('min_recall_not_met', metric['reasons'])

    def test_commitment_hash_is_order_stable_but_value_sensitive(self):
        first = [{'rule_id':'F1', 'prediction':True, 'unit_id':'A'}]
        reordered = [{'unit_id':'A', 'prediction':True, 'rule_id':'F1'}]
        changed = [{'rule_id':'F1', 'prediction':False, 'unit_id':'A'}]
        self.assertEqual(canonical_sha(first), canonical_sha(reordered))
        self.assertNotEqual(canonical_sha(first), canonical_sha(changed))


if __name__ == '__main__':
    unittest.main()
