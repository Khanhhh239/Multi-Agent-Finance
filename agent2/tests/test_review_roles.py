import unittest
from dataclasses import replace
from sme_fraud.review_roles import VERSION,ReviewPrincipal,require_permission,policy_status,validate_ml_review_pair


class ReviewRolesTest(unittest.TestCase):
    def setUp(self):
        self.accountant=ReviewPrincipal('AC01','PERSON01','Kế toán A','accountant',('C001',))
        self.chief=ReviewPrincipal('CH01','PERSON02','Kế toán trưởng B','chief_accountant',('C001',))
        self.director=ReviewPrincipal('DIR01','PERSON03','Giám đốc C','director',('C001',))

    def test_no_actor_does_not_create_an_account_or_grant(self):
        state=policy_status();self.assertIsNone(state['principal'])
        self.assertEqual(state['identity_status'],'awaiting_login_integration')
        for action in ('primary','finalize','return'):
            with self.assertRaises(PermissionError):require_permission(None,action,'C001')

    def test_role_matrix_is_enforced(self):
        require_permission(self.accountant,'primary','C001')
        for person in (self.chief,self.director):
            require_permission(person,'finalize','C001');require_permission(person,'return','C001')
            with self.assertRaises(PermissionError):require_permission(person,'primary','C001')
        for action in ('finalize','return','budget'):
            with self.assertRaises(PermissionError):require_permission(self.accountant,action,'C001')

    def test_explicit_company_scope_and_trusted_principal_required(self):
        with self.assertRaises(PermissionError):require_permission(self.chief,'finalize','C002')
        with self.assertRaises(PermissionError):require_permission({'role':'director'},'finalize','C001')
        with self.assertRaises(ValueError):replace(self.chief,company_ids=('*',))
        with self.assertRaises(ValueError):replace(self.chief,person_id='')

    def assignment(self,final_role='chief_accountant'):
        return dict(role_policy=VERSION,primary_reviewer_id='A',adjudicator_id='B',people={
            'A':dict(role='accountant',person_id='P1'),'B':dict(role=final_role,person_id='P2')})

    def test_ml_roles_accept_chief_or_director_but_not_accountant_final(self):
        for role in ('chief_accountant','director'):self.assertTrue(validate_ml_review_pair(self.assignment(role),'R1','A','B'))
        self.assertFalse(validate_ml_review_pair(self.assignment('accountant'),'R1','A','B'))

    def test_ml_role_labels_do_not_substitute_for_actual_people(self):
        config=self.assignment();config['people']={}
        self.assertFalse(validate_ml_review_pair(config,'R1','A','B'))
        config=self.assignment();config['people']['B']['person_id']=' p1 '
        self.assertFalse(validate_ml_review_pair(config,'R1','A','B'))
        config=self.assignment();config['people']['A']['role']='director'
        self.assertFalse(validate_ml_review_pair(config,'R1','A','B'))

    def test_per_unit_assignments_and_legacy_assignments_remain_explicit(self):
        config=self.assignment();config['units']={'R1':dict(primary_reviewer_id='A',adjudicator_id='B'),'R2':dict(primary_reviewer_id='B',adjudicator_id='A')}
        self.assertTrue(validate_ml_review_pair(config,'R1','A','B'))
        self.assertFalse(validate_ml_review_pair(config,'R2','A','B'))
        self.assertTrue(validate_ml_review_pair(dict(primary_reviewer_id='A',adjudicator_id='B'),'R1','A','B'))
        self.assertFalse(validate_ml_review_pair(dict(primary_reviewer_id=None,adjudicator_id=None),'R1','A','B'))


class MlRoleGateTest(unittest.TestCase):
    def setUp(self):
        import test_independent_ml_review as fixtures
        self.fixture=fixtures.IndependentMlReviewTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        import json
        self.json=json
        self.assignment=dict(role_policy=VERSION,primary_reviewer_id='HUMAN_R1',adjudicator_id='HUMAN_R2',people={
            'HUMAN_R1':dict(role='accountant',person_id='P1'),
            'HUMAN_R2':dict(role='chief_accountant',person_id='P2')})
        self.path=self.fixture.prepared/'private/reviewer_assignment.json'

    def save(self):self.path.write_text(self.json.dumps(self.assignment),encoding='utf-8')

    def test_actual_validator_checks_roles_without_waiving_blind_independence(self):
        self.save();self.assertEqual(self.fixture.validate(name='roles_valid')['validated_independent_units'],1)
        p=dict(self.fixture.primary,independent_of_development='false')
        self.assertEqual(self.fixture.validate(p=p,name='roles_not_independent')['validated_independent_units'],0)
        self.assignment['people']['HUMAN_R2']['role']='accountant';self.save()
        self.assertEqual(self.fixture.validate(name='roles_wrong_final')['validated_independent_units'],0)

    def test_configuring_roles_alone_does_not_add_real_reviews(self):
        self.assignment.update(primary_reviewer_id=None,adjudicator_id=None,people={});self.save()
        result=self.fixture.validate()
        self.assertEqual(result['validated_independent_units'],0)
        self.assertIsNone(result['measured_primary_minutes'])
