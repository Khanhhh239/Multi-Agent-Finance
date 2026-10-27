"""M02: missing contact values are never evidence of an employee relationship."""
import copy
from types import SimpleNamespace
import unittest

from sme_fraud.accounting import enrich_accounting
from sme_fraud.features import FEATURE_DESCRIPTIONS, build_features
from sme_fraud.feature_contract import cache_contract, model_compatibility, require_model
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import normalize, score_rules


class FeatureContactIdentityTest(unittest.TestCase):
    def case(self):
        case = Case()
        row = case.pay()
        case.tables['transactions'] = case.rows
        enrich_accounting(case.tables, 20261013)
        return case, row

    def contacts(self, case, employee, vendor):
        for field in ('phone', 'address'):
            case.worker[field] = employee[field]
            case.vendor[field] = vendor[field]
        for edge in case.tables['entity_links']:
            if edge['link_type'] == 'phone':
                if edge['source_id'] == case.worker['employee_id']:
                    edge['target_id'] = employee['phone']
                elif edge['source_id'] == case.vendor['vendor_id']:
                    edge['target_id'] = vendor['phone']

    def feature(self, case):
        return build_features(case.tables)[0]

    def b2(self, case):
        config=dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='disabled',
                    cash_payment_policy='disabled', amount_baseline='log_mad', enable_graph=False)
        return [h for h in score_rules(case.tables, config=config)['hits'] if h['rule_id'] == 'B2']

    def test_all_empty_employee_and_vendor_contacts_do_not_overlap(self):
        case, _ = self.case()
        for row in (*case.tables['employees'], *case.tables['vendors']):
            row.update(phone='', address='')
        f = self.feature(case)
        self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current']), (0, 0))
        self.assertEqual(self.b2(case), [])

    def test_empty_whitespace_punctuation_and_null_values_never_match(self):
        for value in ('', ' \t\n', ' .-_:/ ', None):
            with self.subTest(value=value):
                case, _ = self.case()
                values=dict(phone=value, address=value)
                self.contacts(case, values, values)
                f=self.feature(case)
                self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current']), (0, 0))
                self.assertEqual(f['graph_employee_count_current'], 0)
                self.assertEqual(self.b2(case), [])

    def test_placeholder_contacts_never_become_direct_or_graph_evidence(self):
        for value in ('N/A', 'NULL', 'None', 'nan', 'UNKNOWN', 'không có', 'chưa có', 'not available'):
            with self.subTest(value=value):
                case, _ = self.case()
                values=dict(phone=value, address=value)
                self.contacts(case, values, values)
                f=self.feature(case)
                self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current'], f['graph_employee_count_current']), (0, 0, 0))
                self.assertEqual(self.b2(case), [])

    def test_non_string_contacts_are_unusable_without_implicit_conversion(self):
        for value in (0, 123456789, True, {'raw': 'phone'}, ['phone']):
            with self.subTest(value=value):
                case, _ = self.case()
                values=dict(phone=value, address=value)
                self.contacts(case, values, values)
                f=self.feature(case)
                self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current']), (0, 0))
                self.assertEqual(self.b2(case), [])

    def test_missing_contact_columns_are_unavailable(self):
        case, _ = self.case()
        for row in (*case.tables['employees'], *case.tables['vendors']):
            row.pop('phone', None); row.pop('address', None)
        f=self.feature(case)
        self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current']), (0, 0))

    def test_phone_country_code_and_formatting_match_like_b2(self):
        for employee, vendor in (('0912 345 678', '+84 912.345.678'),
                                 ('0912345678', '0084-912-345-678')):
            with self.subTest(employee=employee,vendor=vendor):
                case, _ = self.case()
                self.contacts(case,dict(phone=employee,address='EMP_ONLY'),dict(phone=vendor,address='VENDOR_ONLY'))
                self.assertEqual(self.feature(case)['employee_phone_overlap_current'], 1)
                hit,=self.b2(case)
                self.assertEqual(hit['points'], 3)
                self.assertEqual(hit['evidence']['direct_matches'], {'phone':[case.worker['employee_id']]})

    def test_address_case_accents_and_separators_match_like_b2(self):
        case, _ = self.case()
        self.contacts(case,dict(phone='EMP_PHONE',address=' Số 12, Đường Ánh Dương '),
                      dict(phone='VENDOR_PHONE',address='SO12DUONGANHDUONG'))
        self.assertEqual(self.feature(case)['employee_address_overlap_current'], 1)
        hit,=self.b2(case)
        self.assertEqual(hit['evidence']['direct_matches'], {'address':[case.worker['employee_id']]})

    def test_valid_same_contact_survives_while_the_other_field_is_empty(self):
        for field, token in (('phone','PHONE_SYN_VALID'),('address','ADDRESS_SYN_VALID')):
            with self.subTest(field=field):
                case, _ = self.case()
                values=dict(phone='',address='');values[field]=token
                self.contacts(case, values, values)
                f=self.feature(case)
                self.assertEqual((f['employee_phone_overlap_current'], f['employee_address_overlap_current']),
                                 (int(field=='phone'),int(field=='address')))
                hit,=self.b2(case)
                self.assertEqual(hit['evidence']['direct_matches'],{field:[case.worker['employee_id']]})

    def test_normalized_phone_edges_find_the_real_employee(self):
        case, _ = self.case()
        self.contacts(case,dict(phone='0912.345.678',address='EMP_ONLY'),
                      dict(phone='+84 912 345 678',address='VENDOR_ONLY'))
        self.assertEqual(self.feature(case)['graph_employee_count_current'], 1)

    def test_address_links_do_not_create_a_strong_graph_relationship(self):
        case, _ = self.case()
        for entity in (case.worker['employee_id'],case.vendor['vendor_id']):
            case.tables['entity_links'].append(dict(company_id='C001',source_id=entity,target_id='SHARED_ADDRESS',
                                                   link_type='address',observed_at=case.vendor['recorded_at']))
        self.assertEqual(self.feature(case)['graph_employee_count_current'], 0)

    def test_distinct_contacts_and_other_company_do_not_match(self):
        case, _ = self.case()
        self.contacts(case,dict(phone='0012345678',address='0012'),dict(phone='012345678',address='12'))
        f=self.feature(case)
        self.assertEqual((f['employee_phone_overlap_current'],f['employee_address_overlap_current']), (0,0))
        case.worker.update(company_id='C002',phone=case.vendor['phone'],address=case.vendor['address'])
        f=self.feature(case)
        self.assertEqual((f['employee_phone_overlap_current'],f['employee_address_overlap_current']), (0,0))

    def test_contact_tokens_cannot_collide_with_entity_ids_in_graph(self):
        case, _ = self.case()
        for edge in case.tables['entity_links']:
            if edge['source_id']==case.vendor['vendor_id'] and edge['link_type']=='phone':
                edge['target_id']=case.worker['employee_id']
        self.assertEqual(self.feature(case)['graph_employee_count_current'], 0)

    def test_synthetic_tokens_and_non_contact_normalization_remain_supported(self):
        self.assertEqual(normalize('PHONE_SYN_001','phone'),'PHONESYN001')
        self.assertEqual(normalize('Địa chỉ mô phỏng 001','address'),'DIACHIMOPHONG001')
        self.assertEqual(normalize('0012345','bank_account'),'0012345')
        self.assertEqual(normalize('N/A','text'),'NA')
        self.assertEqual(normalize('0000000000','phone'),'')

    def test_feature_build_does_not_mutate_raw_master_or_links(self):
        case, _ = self.case()
        self.contacts(case,dict(phone='0912.345.678',address=' Đường A '),
                      dict(phone='+84 912 345 678',address='DUONGA'))
        before=copy.deepcopy(case.tables)
        self.feature(case)
        self.assertEqual(case.tables,before)

    def test_same_width_v2_model_cannot_score_v3_contact_semantics(self):
        files={'transactions.csv':{'sha256':'tx'},'features.csv':{'sha256':'features'}}
        meta=dict(version='fixture',files=files,feature_columns=list(FEATURE_DESCRIPTIONS),feature_contract=cache_contract(files))
        artifact=dict(model=SimpleNamespace(n_features_in_=len(FEATURE_DESCRIPTIONS)),
                      feature_columns=list(FEATURE_DESCRIPTIONS),dataset_version='fixture',sklearn_version='runtime',
                      feature_contract_fingerprint='219c233e3eaca51ec667a4593a3e28f93bd9bd73dd697bef55a75f7b7d1b581f',
                      training_feature_fingerprint='V2_TRAIN',score_direction='higher_is_more_anomalous')
        result=model_compatibility(artifact,meta,'runtime')
        self.assertEqual(result['reasons'],['semantic_provenance_missing_or_mismatched'])
        with self.assertRaisesRegex(ValueError,'semantic_provenance'):
            require_model(artifact,meta,'runtime')
