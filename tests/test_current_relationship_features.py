"""Current relationship semantics, compared with causal B2 on raw revisions."""
import copy
from datetime import timedelta
import unittest

from sme_fraud.features import build_features, FEATURE_DESCRIPTIONS
from sme_fraud.feature_contract import current_contract
from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


RENAMED = {name: name + '_current' for name in (
    'employee_phone_overlap', 'employee_address_overlap', 'graph_employee_count', 'linked_vendor_count')}


class CurrentRelationshipFeaturesTest(unittest.TestCase):
    def case(self, *, phone=True, address=True):
        case=Case();case.config=dict(noise_policy='phase2',spec_policy='phase3')
        if phone:case.vendor['phone']=case.worker['phone']
        if address:case.vendor['address']=case.worker['address']
        for edge in case.tables['entity_links']:
            if edge['source_id']==case.vendor['vendor_id'] and edge['link_type']=='phone':edge['target_id']=case.vendor['phone']
        return case

    def version(self,case,record,days=1,**values):
        revision=dict(record,recorded_at=stamp(case.at+timedelta(days=days)),**values)
        case.tables['employees' if 'employee_id' in record else 'vendors'].append(revision)
        return revision

    def f(self,case,row):
        values=next(f for f in case.features if f['transaction_id']==row['transaction_id'])
        return {old: values[new] if new in values else values[old] for old,new in RENAMED.items()}

    def b2(self,result,row):return [h for h in result['hits'] if h['rule_id']=='B2' and h['transaction_id']==row['transaction_id']]

    def c2(self,case):
        case.tables['companies'].append(dict(case.tables['companies'][0],company_id='C002'))
        for person,key in ((case.maker,'M03_C2_MAKER'),(case.director,'M03_C2_DIRECTOR')):
            case.tables['employees'].append(dict(person,employee_id=key,company_id='C002'))

    def test_employee_replacement_retires_phone_address_and_graph(self):
        case=self.case();earlier=case.pay()
        self.version(case,case.worker,phone='M03_NEW_PHONE',address='M03_NEW_ADDRESS')
        later=case.pay(case.at+timedelta(days=2));result=case.score()
        self.assertEqual((self.f(case,earlier)['employee_phone_overlap'],self.f(case,earlier)['employee_address_overlap']),(1,1))
        self.assertEqual((self.f(case,later)['employee_phone_overlap'],self.f(case,later)['employee_address_overlap'],self.f(case,later)['graph_employee_count']),(0,0,0))
        self.assertEqual(self.b2(result,later),[])

    def test_vendor_replacement_or_clear_splits_graph(self):
        for replacement in ('M03_NEW_VENDOR_PHONE',''):
            with self.subTest(replacement=replacement):
                case=self.case(address=False);earlier=case.pay()
                self.version(case,case.vendor,phone=replacement)
                later=case.pay(case.at+timedelta(days=2));result=case.score()
                self.assertEqual(self.f(case,earlier)['graph_employee_count'],1)
                self.assertEqual(self.f(case,later)['graph_employee_count'],0)
                self.assertEqual(self.b2(result,later),[])

    def test_employee_clear_retires_old_tokens(self):
        case=self.case();case.pay()
        self.version(case,case.worker,phone='',address='')
        later=case.pay(case.at+timedelta(days=2));case.score()
        self.assertEqual((self.f(case,later)['employee_phone_overlap'],self.f(case,later)['employee_address_overlap']),(0,0))

    def test_shared_contact_survives_for_remaining_current_employee(self):
        case=self.case();remaining=case.tables['employees'][11]
        remaining.update(phone=case.worker['phone'],address=case.worker['address'])
        earlier=case.pay();self.version(case,case.worker,phone='',address='')
        later=case.pay(case.at+timedelta(days=2));result=case.score()
        self.assertEqual(self.f(case,earlier)['graph_employee_count'],2)
        self.assertEqual(self.f(case,later)['graph_employee_count'],1)
        self.assertEqual(self.f(case,later)['employee_phone_overlap'],1)
        self.assertEqual(self.b2(result,later)[0]['evidence']['direct_matches']['phone'],[remaining['employee_id']])

    def test_transfer_removes_old_company_membership_and_matches_new_company(self):
        case=self.case();self.c2(case);earlier=case.pay()
        self.version(case,case.worker,company_id='C002')
        old=case.pay(case.at+timedelta(days=2))
        vendor=dict(case.vendor,vendor_id='M03_C2_VENDOR',company_id='C002');case.tables['vendors'].append(vendor)
        new=case.pay(case.at+timedelta(days=2),vendor=vendor,company_id='C002',creator_id='M03_C2_MAKER',approver_id='M03_C2_DIRECTOR')
        result=case.score()
        self.assertEqual(self.f(case,earlier)['graph_employee_count'],1)
        self.assertEqual((self.f(case,old)['employee_phone_overlap'],self.f(case,old)['employee_address_overlap'],self.f(case,old)['graph_employee_count']),(0,0,0))
        self.assertEqual((self.f(case,new)['employee_phone_overlap'],self.f(case,new)['graph_employee_count']),(1,1))
        self.assertEqual(self.b2(result,old),[])

    def test_transfer_back_restores_membership_without_double_counting(self):
        case=self.case();self.c2(case);first=case.pay()
        moved=self.version(case,case.worker,company_id='C002')
        middle=case.pay(case.at+timedelta(days=2))
        self.version(case,moved,days=3,company_id='C001')
        last=case.pay(case.at+timedelta(days=4));case.score()
        self.assertEqual([self.f(case,row)['graph_employee_count'] for row in (first,middle,last)],[1,0,1])

    def test_bank_code_replacement_also_splits_old_graph_component(self):
        case=self.case(phone=False,address=False)
        case.worker.update(bank_account='001234567',bank_code='BANK_A')
        case.vendor.update(bank_account='001234567',bank_code='BANK_A')
        for edge in case.tables['entity_links']:
            if edge['source_id'] in {case.worker['employee_id'],case.vendor['vendor_id']} and edge['link_type']=='bank_account':
                edge.update(target_id='001234567',bank_code='BANK_A')
        first=case.pay(recipient_account='001234567',recipient_bank_code='BANK_A')
        self.version(case,case.worker,bank_code='BANK_B')
        last=case.pay(case.at+timedelta(days=2),recipient_account='001234567',recipient_bank_code='BANK_A');case.score()
        self.assertEqual(self.f(case,first)['graph_employee_count'],1)
        self.assertEqual(self.f(case,last)['graph_employee_count'],0)

    def test_representative_replacement_removes_old_two_hop_path(self):
        case=self.case(phone=False,address=False)
        for edge in case.tables['entity_links']:
            if edge['source_id']==case.vendor['representative_id'] and edge['link_type']=='phone':edge['target_id']=case.worker['phone']
        first=case.pay();self.version(case,case.vendor,representative_id='M03_NEW_REP')
        last=case.pay(case.at+timedelta(days=2));result=case.score()
        self.assertEqual(self.f(case,first)['graph_employee_count'],1)
        self.assertEqual(self.f(case,last)['graph_employee_count'],0)
        self.assertEqual(self.b2(result,last),[])

    def test_external_link_replacement_and_revocation_are_current(self):
        for status,target in (('active','M03_OTHER_PHONE'),('revoked',''),('deleted',''),('inactive','')):
            with self.subTest(status=status):
                case=self.case(phone=False,address=False);rep=case.vendor['representative_id']
                for edge in case.tables['entity_links']:
                    if edge['source_id']==rep and edge['link_type']=='phone':edge['target_id']=case.worker['phone']
                first=case.pay()
                case.tables['entity_links'].append(dict(company_id='C001',source_id=rep,target_id=target,link_type='phone',status=status,
                                                       observed_at=stamp(case.at+timedelta(days=1))))
                last=case.pay(case.at+timedelta(days=2));result=case.score()
                self.assertEqual(self.f(case,first)['graph_employee_count'],1)
                self.assertEqual(self.f(case,last)['graph_employee_count'],0)
                self.assertEqual(self.b2(result,last),[])

    def test_revoking_old_target_does_not_cancel_current_replacement(self):
        case=self.case(phone=False,address=False);rep=case.vendor['representative_id']
        original=next(e for e in case.tables['entity_links'] if e['source_id']==rep and e['link_type']=='phone')
        case.tables['entity_links'].append(dict(original,target_id=case.worker['phone'],observed_at=stamp(case.at-timedelta(days=1))))
        first=case.pay()
        case.tables['entity_links'].append(dict(original,status='revoked',observed_at=stamp(case.at+timedelta(days=1))))
        middle=case.pay(case.at+timedelta(days=2))
        case.tables['entity_links'].append(dict(original,target_id=case.worker['phone'],status='revoked',observed_at=stamp(case.at+timedelta(days=3))))
        last=case.pay(case.at+timedelta(days=4));case.score()
        self.assertEqual([self.f(case,r)['graph_employee_count'] for r in (first,middle,last)],[1,1,0])

    def test_changes_at_cutoff_apply_to_entire_simultaneous_batch(self):
        case=self.case();cutoff=case.at+timedelta(days=1);earlier=case.pay(cutoff-timedelta(seconds=1))
        self.version(case,case.worker,phone='',address='')
        batch=[case.pay(cutoff),case.pay(cutoff)];case.score()
        self.assertEqual(self.f(case,earlier)['graph_employee_count'],1)
        for row in batch:self.assertEqual((self.f(case,row)['employee_phone_overlap'],self.f(case,row)['employee_address_overlap'],self.f(case,row)['graph_employee_count']),(0,0,0))

    def test_future_master_and_link_updates_preserve_all_historical_features(self):
        case=self.case();earlier=case.pay();before=copy.deepcopy(case.score());features=copy.deepcopy(case.features)
        self.version(case,case.worker,phone='',address='')
        case.tables['entity_links'].append(dict(company_id='C001',source_id=case.vendor['representative_id'],target_id='',link_type='phone',status='revoked',
                                               observed_at=stamp(case.at+timedelta(days=1))))
        case.pay(case.at+timedelta(days=2));after=case.score()
        self.assertEqual(features,[f for f in case.features if f['transaction_id']==earlier['transaction_id']])
        self.assertEqual(before['hits'],[h for h in after['hits'] if h['detected_at']<=earlier['posted_at']])
        self.assertEqual(before['scores'],[s for s in after['scores'] if s['posted_at']<=earlier['posted_at']])

    def test_old_or_equal_time_mirrors_do_not_resurrect_cleared_master(self):
        for days in (0,1):
            with self.subTest(mirror_days=days):
                case=self.case();case.pay();self.version(case,case.worker,phone='',address='')
                case.tables['entity_links'].append(dict(company_id='C001',source_id=case.worker['employee_id'],target_id=case.worker['phone'],
                                                       link_type='phone',observed_at=stamp(case.at+timedelta(days=days))))
                last=case.pay(case.at+timedelta(days=2));case.score()
                self.assertEqual(self.f(case,last)['graph_employee_count'],0)

    def test_disconnected_vendors_split_linked_vendor_count(self):
        case=self.case();other=case.tables['vendors'][13];other['phone']=case.vendor['phone']
        for edge in case.tables['entity_links']:
            if edge['source_id']==other['vendor_id'] and edge['link_type']=='phone':edge['target_id']=other['phone']
        earlier=case.pay();self.version(case,other,phone='M03_SEPARATE_VENDOR')
        first=case.pay(case.at+timedelta(days=2));second=case.pay(case.at+timedelta(days=2),vendor=other);case.score()
        self.assertEqual(self.f(case,earlier)['linked_vendor_count'],2)
        self.assertEqual([self.f(case,r)['linked_vendor_count'] for r in (first,second)],[1,1])
        self.assertEqual(self.f(case,second)['graph_employee_count'],0)

    def test_vendor_transfer_removes_old_company_vendor_membership(self):
        case=self.case();self.c2(case);other=case.tables['vendors'][13];other['phone']=case.vendor['phone']
        for edge in case.tables['entity_links']:
            if edge['source_id']==other['vendor_id'] and edge['link_type']=='phone':edge['target_id']=other['phone']
        first=case.pay();self.version(case,other,company_id='C002')
        last=case.pay(case.at+timedelta(days=2));case.score()
        self.assertEqual([self.f(case,r)['linked_vendor_count'] for r in (first,last)],[2,1])

    def test_master_snapshot_relationships_work_without_link_mirrors(self):
        case=self.case();case.tables['entity_links']=[];row=case.pay();result=case.score()
        self.assertEqual(self.f(case,row)['graph_employee_count'],1)
        self.assertTrue(self.b2(result,row)[0]['graph_path'])

    def test_source_order_and_identical_revisions_do_not_change_counts(self):
        case=self.case();case.pay();case.score();before=copy.deepcopy(case.features)
        case.tables['employees'].append(dict(case.worker))
        for name in ('employees','vendors','entity_links'):case.tables[name].reverse()
        self.assertEqual(build_features(case.tables),before)

    def test_conflicting_employee_or_vendor_snapshots_are_rejected(self):
        for role in ('employee','vendor'):
            with self.subTest(role=role):
                case=self.case();case.pay();record=case.worker if role=='employee' else case.vendor
                case.tables['employees' if role=='employee' else 'vendors'].append(dict(record,address='CONFLICT'))
                with self.assertRaisesRegex(ValueError,'Conflicting'):
                    case.score()

    def test_explicit_current_schema_has_no_ambiguous_or_unbounded_history_aliases(self):
        self.assertTrue(set(RENAMED.values())<=set(FEATURE_DESCRIPTIONS))
        self.assertTrue(set(RENAMED).isdisjoint(FEATURE_DESCRIPTIONS))
        policy=current_contract()['relationship_semantics']
        self.assertEqual(policy['state'],'current_as_of_posted_at')
        self.assertEqual(policy['historical_features'],[])
        self.assertIsNone(policy['historical_window_days'])
