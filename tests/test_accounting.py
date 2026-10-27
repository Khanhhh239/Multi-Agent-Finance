import unittest
import copy
from collections import defaultdict

from sme_fraud.accounting import normalise_account,pair_supported,expense_account
from sme_fraud.features import build_features,FEATURE_DESCRIPTIONS
from sme_fraud.generate import Generator


class AccountingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = Generator(10_000,.005,20261012,5).finalize()
        cls.transactions = {r['transaction_id']:r for r in cls.tables['transactions']}
        cls.documents = {d['document_id']:d for d in cls.tables['journal_documents']}
        cls.lines = defaultdict(list)
        cls.incoming = defaultdict(list)
        for line in cls.tables['journal_lines']:
            cls.lines[line['document_id']].append(line)
        for link in cls.tables['document_links']:
            cls.incoming[link['target_document_id']].append(link['source_document_id'])

    def test_tt133_has_no_tt200_selling_or_cost_accounts(self):
        for docid,doc in self.documents.items():
            if doc['accounting_framework']=='TT133':
                self.assertTrue(all(l['account_code'] not in {'641','621','622','627'} for l in self.lines[docid]))
        self.assertEqual(expense_account('TT133','selling'),'6421')
        self.assertEqual(expense_account('TT133','admin'),'6422')
        self.assertEqual(normalise_account('641','TT200'),normalise_account('6421','TT133'))
        self.assertNotIn('debit_641',FEATURE_DESCRIPTIONS)

    def test_vat_purchase_is_a_balanced_compound_entry(self):
        r=next(r for r in self.transactions.values() if r['txn_type']=='stock_purchase')
        ls=self.lines[r['journal_document_id']]
        self.assertEqual(sum(l['debit_vnd'] for l in ls),r['amount_vnd'])
        self.assertEqual(sum(l['credit_vnd'] for l in ls),r['amount_vnd'])
        self.assertEqual(sum(l['debit_vnd'] for l in ls if l['account_code']=='1331'),r['invoice_vat_vnd'])
        self.assertEqual(sum(l['debit_vnd'] for l in ls if l['account_code']=='156'),r['invoice_net_vnd'])

    def test_standalone_low_value_equipment_is_not_fixed_asset(self):
        tools=[r for r in self.transactions.values() if r['txn_type']=='tools_purchase']
        self.assertTrue(tools)
        for r in tools:
            self.assertLess(r['invoice_net_vnd'],30_000_000)
            self.assertEqual(r['debit_account'],'153')
            self.assertTrue(any(l['account_code']=='1331' and l['debit_vnd']>0 for l in self.lines[r['journal_document_id']]))

    def test_payments_do_not_book_input_vat_twice(self):
        for r in self.transactions.values():
            if r['txn_type']=='vendor_payment':
                self.assertTrue(all(l['account_code'] not in {'1331','1332'} for l in self.lines[r['journal_document_id']]))
                linked = self.documents[r['linked_document_id']]
                self.assertEqual(linked['purpose'],'invoice_accrual')
                self.assertLessEqual(linked['posted_at'],r['posted_at'])

    def test_manufacturing_salary_and_material_flow_reaches_154(self):
        salaries=[d for d in self.documents.values() if d['company_id']=='C002' and d['purpose']=='salary_accrual']
        self.assertTrue(any(any(l['account_code']=='154' and l['debit_vnd']>0 for l in self.lines[d['document_id']]) for d in salaries))
        self.assertTrue(any(r['txn_type']=='material_issue' and r['company_id']=='C002' and r['debit_account']=='154' for r in self.transactions.values()))
        self.assertTrue(any(e['company_id']=='C002' and e['source_account']=='334' and e['target_account']=='154' for e in self.tables['account_flow_edges']))

    def test_real_writeoff_is_not_receivable_reclassification(self):
        for r in self.transactions.values():
            if r['txn_type']=='advance_writeoff':
                self.assertEqual(r['credit_account'],'1388')
                prior=self.documents[r['linked_document_id']]
                self.assertEqual(prior['purpose'],'advance_reclassification')
                self.assertLess(prior['posted_at'],r['posted_at'])
                self.assertEqual({l['account_code'] for l in self.lines[prior['document_id']]},{'1388','141'})

    def test_every_document_balances_and_every_flow_matches_its_scenario(self):
        for docid,ls in self.lines.items():
            self.assertEqual(sum(l['debit_vnd'] for l in ls),sum(l['credit_vnd'] for l in ls))
        for e in self.tables['account_flow_edges']:
            d=self.documents[e['document_id']]
            self.assertTrue(pair_supported(e['target_account'],e['source_account'],d['purpose'],d['accounting_framework']))

    def test_unusual_examples_are_not_supported_as_routine_expense_accrual(self):
        self.assertFalse(pair_supported('642','511','expense_accrual','TT200'))
        self.assertFalse(pair_supported('111','632','expense_accrual','TT200'))
        self.assertTrue(pair_supported('642','335','expense_accrual','TT200'))

    def test_features_include_current_writeoff_evidence_and_vat_lines(self):
        known = copy.deepcopy(self.tables)
        for row in known['transactions']:
            row['support_docs_observed_at'] = row['posted_at']
            row['invoice_observed_at'] = max(row['posted_at'], row['invoice_issued_at'])
        features={r['transaction_id']:r for r in build_features(known)}
        for r in self.transactions.values():
            f=features[r['transaction_id']]
            if r['txn_type']=='advance_writeoff':
                self.assertEqual(f['advance_writeoff_evidence_missing'],int(not r['evidence_on_file']))
            if r['txn_type']=='stock_purchase':
                self.assertEqual(f['debit_133'],1)
                self.assertEqual(f['pair_133_331'],1)
                self.assertEqual(f['pair_156_331'],1)
            if r['is_financial_entry']:
                self.assertEqual(f['pair_supported_for_scenario'],1)
                self.assertEqual(f['journal_balance_difference_ratio'],0)

    def test_untimed_writeoff_proof_is_missing_for_ml(self):
        features={r['transaction_id']:r for r in build_features(self.tables)}
        for row in self.transactions.values():
            if row['txn_type'] == 'advance_writeoff':
                self.assertEqual(features[row['transaction_id']]['support_docs_known'], 0)
                self.assertEqual(features[row['transaction_id']]['advance_writeoff_evidence_missing'], 1)


if __name__=='__main__':
    unittest.main()
