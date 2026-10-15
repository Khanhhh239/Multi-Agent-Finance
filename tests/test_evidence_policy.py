import copy
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sme_fraud.evidence_cases import SCENARIOS, prepare, decision
from sme_fraud.generate import stamp, write_csv
from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.rules import score_rules, load_inputs, INPUT_TABLES, OPTIONAL_INPUT_TABLES


class EvidencePolicyTest(unittest.TestCase):
    def test_predeclared_business_controls(self):
        for code, variants in SCENARIOS.items():
            for variant in variants:
                with self.subTest(rule=code, variant=variant):
                    c, row, expected, scope = prepare(code, variant, 701)
                    result = c.score()
                    self.assertEqual(decision(result, code, row, scope), expected)

    def test_no_future_sources_or_truth_can_change_past_evidence(self):
        for code in ('C4', 'E2', 'F2', 'F3', 'F4'):
            c, row, _, scope = prepare(code, 'positive', 702)
            result = c.score()
            future = copy.deepcopy(c.tables)
            from sme_fraud.evidence_policy import SOURCES
            for name, id_field in SOURCES.items():
                for original in c.tables.get(name, []):
                    future[name].append({**original, id_field: str(original[id_field])+'_FUTURE', 'observed_at': stamp(c.at+timedelta(days=5))})
            future['labels'] = [dict(is_fraud=1)]
            future['splits'] = []
            expanded = score_rules(future, features=c.features, config=c.config)
            self.assertEqual(result, expanded)

    def test_wrong_company_and_self_granted_leave_permission_cannot_exempt(self):
        for change in ('company_id', 'approver_id'):
            c, row, _, scope = prepare('C4', 'authorized', 703)
            permission = c.tables['leave_activity_authorizations'][0]
            permission[change] = 'C_OTHER' if change == 'company_id' else c.maker['employee_id']
            self.assertTrue(decision(c.score(), 'C4', row, scope))

    def test_source_diagnostics_do_not_invent_transaction_fraud(self):
        for code in ('F3', 'F4'):
            c, row, _, scope = prepare(code, 'positive', 704)
            result = c.score()
            self.assertTrue(decision(result, code, row, scope))
            self.assertFalse(any(h['rule_id'] == code for h in result['hits']))
            self.assertFalse(result['scores'][-1]['operational_alert'])
            self.assertTrue(all(f['points'] == 0 for f in result['evidence_findings']))

    def test_post_termination_salary_confirmed_but_final_pay_and_missing_period_not_hard(self):
        for variant, expected in [('positive', 1), ('final_payment', 0), ('missing_period', 0)]:
            c, row, _, _ = prepare('E2', variant, 705)
            hit = next(h for h in c.score()['hits'] if h['rule_id'] == 'E2')
            self.assertEqual(hit['hard_trigger'], expected)

    def test_revisions_and_bindings_fail_closed(self):
        c, row, _, _ = prepare('C4', 'positive', 706)
        c.tables['leave_periods'].append({**c.tables['leave_periods'][0], 'employee_id': c.worker['employee_id']})
        with self.assertRaises(ValueError):
            c.score()

    def test_future_receipt_coverage_cannot_claim_complete_bank_history(self):
        c, row, _, scope = prepare('F4', 'positive', 707)
        c.tables['receipt_coverage'][0]['covered_through'] = stamp(c.at+timedelta(days=1))
        self.assertIsNone(decision(c.score(), 'F4', row, scope))

    def test_disabled_policy_preserves_historical_capability(self):
        c, row, _, _ = prepare('E2', 'positive', 708)
        c.config['evidence_policy'] = 'disabled'
        result = c.score()
        self.assertFalse(any(h['rule_id'] == 'E2' for h in result['hits']))

    def test_unobserved_customer_cannot_establish_a_receivable_violation(self):
        c, row, _, scope = prepare('F4', 'positive', 709)
        c.tables['customers'][0]['recorded_at'] = stamp(c.at+timedelta(days=1))
        self.assertIsNone(decision(c.score(), 'F4', row, scope))

    def test_salary_over_entitlement_does_not_hide_post_termination_payment(self):
        c, row, _, scope = prepare('E2', 'positive', 710)
        c.tables['payroll_settlements'][0]['authorized_amount_vnd'] = 1
        self.assertTrue(decision(c.score(), 'E2', row, scope))

    def test_authorized_override_does_not_cover_a_second_control_without_policy(self):
        for order in ('authorized_first','unknown_first'):
            c, row, _, scope = prepare('F2', 'authorized', 712)
            original = c.tables['override_events'][0]
            unknown = {**original, 'override_id':'SECOND_CONTROL', 'control_id':'NO_KNOWN_POLICY'}
            c.tables['override_events'] = [original,unknown] if order=='authorized_first' else [unknown,original]
            self.assertIsNone(decision(c.score(),'F2',row,scope))

    def test_master_profile_update_does_not_erase_prior_leave_approval(self):
        c,row,_,scope = prepare('C4','positive',713)
        c.tables['employees'].append({**c.director,'phone':'UPDATED_PHONE','recorded_at':stamp(c.at-timedelta(days=1))})
        self.assertTrue(decision(c.score(),'C4',row,scope))

    def test_override_role_is_read_at_action_not_at_later_posting(self):
        c,row,_,scope = prepare('F2','positive',714)
        c.tables['workflow_policies'][0].update(allow_override=1,authorized_override_roles='director')
        c.tables['employees'].append({**c.maker,'role':'director','recorded_at':stamp(c.at-timedelta(minutes=30))})
        self.assertTrue(decision(c.score(),'F2',row,scope))

    def test_csv_source_loading_requires_complete_schema_and_manifest_checksum(self):
        c, row, _, scope = prepare('C4', 'positive', 711)
        c.score()
        with tempfile.TemporaryDirectory(dir=Path('.runtime').resolve()) as location:
            folder = Path(location).resolve()
            self.assertTrue(folder.is_relative_to(Path('.runtime').resolve()))
            for name in (*INPUT_TABLES,*OPTIONAL_INPUT_TABLES):
                records = c.tables.get(name,[])
                if name in INPUT_TABLES or records:
                    write_csv(folder/f'{name}.csv',records)
            write_csv(folder/'features.csv',c.features,['transaction_id',*FEATURE_DESCRIPTIONS])
            manifest = dict(files={p.name:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.glob('*.csv')})
            (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            tables,features,_ = load_inputs(folder)
            self.assertTrue(decision(score_rules(tables,features=features,config=c.config),'C4',row,scope))
            records = [{k:v for k,v in r.items() if k!='starts_at'} for r in c.tables['leave_periods']]
            write_csv(folder/'leave_periods.csv',records)
            with self.assertRaisesRegex(ValueError,'checksum'):
                load_inputs(folder)
            manifest['files']['leave_periods.csv']['sha256'] = hashlib.sha256((folder/'leave_periods.csv').read_bytes()).hexdigest()
            (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'schema'):
                load_inputs(folder)


if __name__ == '__main__':
    unittest.main()
