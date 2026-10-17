"""Reject malformed authority sources before they can affect C2/C3 decisions."""
import copy
import unittest

from sme_fraud.authority_policy import ApprovalAuthority
from sme_fraud.rule_audit_cases import Case


class AuthorityValidationTest(unittest.TestCase):
    def setUp(self):
        self.case = Case()
        self.case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3'}
        self.row = self.case.pay(approver_id=self.case.maker['employee_id'])
        proof = dict(company_id='C001', status='approved', evidence_on_file=1,
                     evidence_id='SIGNED_MATRIX', approver_id=self.case.director['employee_id'],
                     approved_at='2025-08-07T11:00:00+07:00',
                     observed_at='2025-08-08T11:00:00+07:00')
        self.coverage = dict(proof, coverage_id='COVERAGE', covered_actions='self_approve,approve',
                             covered_from='2025-01-01', covered_through='2025-12-31')
        self.authority = dict(proof, authority_id='AUTHORITY',
                              subject_employee_id=self.case.maker['employee_id'], subject_role='',
                              action='self_approve', txn_type='*', department='', project_id='',
                              min_amount_vnd=0, max_amount_vnd=10_000_000, self_approval_allowed=1,
                              authority_level='standard', authority_type='policy', delegated_by_id='',
                              effective_from='2025-01-01', effective_to='2025-12-31')
        self.case.tables['approval_authorities'] = [self.authority]
        self.case.tables['approval_authority_coverage'] = [self.coverage]

    def decision(self):
        return ApprovalAuthority(self.case.tables).self_approval(self.row)

    def reject(self, record, field, values):
        original = record[field]
        for value in values:
            with self.subTest(field=field, value=value):
                record[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    self.decision()
        record[field] = original

    def test_invalid_boolean_cannot_grant_self_approval(self):
        self.authority['self_approval_allowed'] = 2
        with self.assertRaisesRegex(ValueError, 'self_approval_allowed'):
            self.case.score()

    def test_boolean_domain_is_strict(self):
        self.reject(self.authority, 'self_approval_allowed',
                    [2, -1, '2', '-1', 'true', 'False', '', None, 1.0, .5, '01', ' 1', [], {}])

    def test_evidence_flags_are_checked_in_both_tables(self):
        for record in (self.authority, self.coverage):
            self.reject(record, 'evidence_on_file', [2, -1, '2', 'yes', None, 1.0, .5, '1.0'])

    def test_valid_native_and_csv_boolean_values_preserve_permission(self):
        for enabled in (0, 1, '0', '1', False, True):
            with self.subTest(enabled=enabled):
                self.authority['self_approval_allowed'] = enabled
                self.assertEqual(self.decision()['permitted'], enabled in (1, '1', True))

    def test_missing_proof_does_not_grant_authority(self):
        for record in (self.authority, self.coverage):
            for field, value in (('evidence_on_file', '0'), ('evidence_id', ''), ('approver_id', '')):
                with self.subTest(source=record.get('authority_id', 'coverage'), field=field):
                    previous = record[field]
                    record[field] = value
                    self.assertIsNot(self.decision()['permitted'], True)
                    record[field] = previous

    def test_authority_enums_are_checked(self):
        for field, values in {
                'action': ['self_approved', '', 'APPROVE', None, []],
                'authority_level': ['superuser', '', None, 1],
                'authority_type': ['delegated', '', None, {}],
                'status': ['active', 'Approved', '', None]}.items():
            self.reject(self.authority, field, values)

    def test_coverage_status_is_checked(self):
        self.reject(self.coverage, 'status', ['active', '', None, [], 1])

    def test_coverage_actions_require_known_unique_tokens(self):
        self.reject(self.coverage, 'covered_actions',
                    ['', 'all', 'self_approve,unknown', 'approve,,self_approve',
                     ',approve', 'approve,', 'approve,approve', None, ['approve']])

    def test_amounts_are_nonnegative_whole_vnd(self):
        for field in ('min_amount_vnd', 'max_amount_vnd'):
            self.reject(self.authority, field,
                        [-1, '-1', 1.5, 1.0, '1.5', '1e6', '1,000', True, None, '',
                         float('nan'), float('inf'), [], ' 100'])

    def test_reversed_amount_range_is_rejected(self):
        self.authority['min_amount_vnd'] = 10_000_001
        with self.assertRaisesRegex(ValueError, 'max_amount_vnd'):
            self.decision()

    def test_csv_amount_boundaries_are_inclusive(self):
        self.authority.update(min_amount_vnd='09000000', max_amount_vnd='9000000')
        self.assertTrue(self.decision()['permitted'])
        self.authority['max_amount_vnd'] = '8999999'
        self.authority['min_amount_vnd'] = '0'
        self.assertFalse(self.decision()['permitted'])

    def test_dates_must_be_real_calendar_dates(self):
        for record, fields in ((self.authority, ('effective_from', 'effective_to')),
                               (self.coverage, ('covered_from', 'covered_through'))):
            for field in fields:
                self.reject(record, field, ['2025-02-29', '2025-13-01', '2025-00-01',
                                           '2025-1-01', '20250801', '', None,
                                           '2025-08-01T00:00:00+07:00'])

    def test_reversed_effective_and_coverage_ranges_are_rejected(self):
        for record, field in ((self.authority, 'effective_to'),
                               (self.coverage, 'covered_through')):
            self.reject(record, field, ['2024-12-31'])

    def test_times_must_be_real_local_timestamps_with_seconds(self):
        for record in (self.authority, self.coverage):
            for field in ('approved_at', 'observed_at'):
                self.reject(record, field,
                            ['', None, '2025-08-07', '2025-08-07T11:00:00',
                             '2025-08-07T11:00:00Z', '2025-08-07T11:00:00+00:00',
                             '2025-08-07 11:00:00+07:00', '2025-08-07T25:00:00+07:00',
                             '2025-02-29T11:00:00+07:00', '2025-08-07T11:00:00.5+07:00'])

    def test_observation_cannot_precede_approval(self):
        for record in (self.authority, self.coverage):
            self.reject(record, 'observed_at', ['2025-08-07T10:59:59+07:00'])

    def test_future_and_revoked_records_do_not_grant_permission(self):
        for record in (self.authority, self.coverage):
            previous = copy.deepcopy(record)
            for updates in ({'status': 'revoked'},
                            {'approved_at': '2025-09-01T00:00:00+07:00',
                             'observed_at': '2025-09-02T00:00:00+07:00'}):
                with self.subTest(source=record.get('authority_id', 'coverage'), updates=updates):
                    record.update(updates)
                    self.assertIsNot(self.decision()['permitted'], True)
                    record.update(previous)

    def test_malformed_future_or_revoked_records_are_still_rejected(self):
        for status in ('approved', 'revoked'):
            self.authority.update(status=status, observed_at='2025-09-02T00:00:00+07:00',
                                  self_approval_allowed=2)
            with self.assertRaisesRegex(ValueError, 'self_approval_allowed'):
                self.decision()

    def test_identifier_and_scope_fields_are_strings(self):
        for field in ('authority_id', 'company_id', 'subject_employee_id', 'subject_role',
                      'txn_type', 'department', 'project_id', 'delegated_by_id',
                      'evidence_id', 'approver_id'):
            self.reject(self.authority, field, [None, [], 123])
        self.reject(self.authority, 'authority_id', ['', ' '])
        self.reject(self.coverage, 'company_id', ['', ' '])

    def test_equivalent_csv_revisions_do_not_conflict_or_mutate_input(self):
        csv_record = dict(self.authority, self_approval_allowed='1', evidence_on_file='1',
                          min_amount_vnd='0', max_amount_vnd='10000000')
        self.case.tables['approval_authorities'].append(csv_record)
        before = copy.deepcopy(self.case.tables)
        self.assertTrue(self.decision()['permitted'])
        self.assertEqual(self.case.tables, before)

    def test_same_revision_conflict_and_changed_bindings_still_fail(self):
        for updates, message in (({'evidence_id': 'OTHER'}, 'Conflicting authority revision'),
                                 ({'max_amount_vnd': 20_000_000,
                                   'observed_at': '2025-08-09T11:00:00+07:00'},
                                  'Authority binding changed')):
            with self.subTest(updates=updates):
                self.case.tables['approval_authorities'] = [self.authority, dict(self.authority, **updates)]
                with self.assertRaisesRegex(ValueError, message):
                    self.decision()
