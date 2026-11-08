import copy,json,tempfile,unittest
from pathlib import Path
from sme_fraud.assistant_evidence_review import factual_dossier,build_dossiers,sha


class AssistantEvidenceReviewTest(unittest.TestCase):
    def setUp(self):
        self.unit=dict(review_unit_id='R',company_code='DN1',cutoff_exclusive='2025-07-02T00:00:00+07:00',evidence_sha256='placeholder')
        self.tx=dict(company_id='DN1',transaction_id='T',posted_at='2025-07-01T10:00:00+07:00',txn_type='vendor_payment',
            amount_vnd='100',currency='VND',journal_document_id='D',invoice_id='I',invoice_number='N',vendor_id='V',
            recipient_account='paid',creator_id='A',approver_id='B')
        self.evidence=dict(company_code='DN1',cutoff_exclusive=self.unit['cutoff_exclusive'],source_object='',scope_transaction_ids=['T'],
            tables=dict(member_transactions=[self.tx],related_transactions=[]))

    def test_journal_imbalance_is_arithmetic_not_automated_outcome(self):
        self.evidence['tables']['journal_lines']=[dict(company_id='DN1',document_id='D',posted_at=self.tx['posted_at'],
            account_code='112',debit_vnd='0',credit_vnd='100'),dict(company_id='DN1',document_id='D',posted_at=self.tx['posted_at'],
            account_code='331',debit_vnd='90',credit_vnd='0')]
        dossier=factual_dossier(self.unit,self.evidence)
        self.assertEqual(dossier['journals'][0]['net'],-10)
        self.assertNotIn('actionable',dossier)

    def test_missing_journal_is_unknown_not_balanced_zero(self):
        row=factual_dossier(self.unit,self.evidence)['journals'][0]
        self.assertIsNone(row['net']);self.assertEqual(row['lines'],0)

    def test_foreign_company_future_or_unversioned_row_rejected(self):
        for bad in (dict(company_id='OTHER',recorded_at=self.tx['posted_at']),
                    dict(company_id='DN1',recorded_at=self.unit['cutoff_exclusive']),dict(company_id='DN1')):
            evidence=copy.deepcopy(self.evidence);evidence['tables']['vendors']=[bad]
            with self.assertRaises(ValueError):factual_dossier(self.unit,evidence)

    def test_invoice_and_payment_are_not_duplicate_payments(self):
        other=dict(self.tx,transaction_id='U',txn_type='purchase_invoice')
        self.evidence['tables']['related_transactions']=[other]
        self.assertEqual(factual_dossier(self.unit,self.evidence)['duplicate_payment_context'],[])
        other['txn_type']='vendor_payment'
        self.assertEqual(len(factual_dossier(self.unit,self.evidence)['duplicate_payment_context']),1)

    def test_bank_master_later_than_payment_not_used_as_historical_master(self):
        vendor=dict(company_id='DN1',vendor_id='V',recorded_at='2025-07-01T11:00:00+07:00',bank_account='new')
        self.evidence['tables']['vendors']=[vendor]
        self.assertEqual(factual_dossier(self.unit,self.evidence)['bank_master_differences'],[])
        vendor['recorded_at']='2025-06-01T11:00:00+07:00'
        self.assertEqual(len(factual_dossier(self.unit,self.evidence)['bank_master_differences']),1)

    def test_member_binding_and_duplicate_members_rejected(self):
        self.evidence['scope_transaction_ids']=['OTHER']
        with self.assertRaises(ValueError):factual_dossier(self.unit,self.evidence)

    def test_shared_bank_requires_same_bank_namespace(self):
        self.evidence['tables']['entity_links']=[dict(company_id='DN1',source_id=s,target_id='123',bank_code=b,
            link_type='bank_account',observed_at=self.tx['posted_at']) for s,b in [('V','B1'),('A','B2')]]
        self.assertEqual(factual_dossier(self.unit,self.evidence)['shared_entity_attributes'],[])
        self.evidence['tables']['entity_links'][1]['bank_code']='B1'
        self.assertEqual(len(factual_dossier(self.unit,self.evidence)['shared_entity_attributes']),1)
        self.evidence['scope_transaction_ids']=['T'];self.evidence['tables']['member_transactions'].append(self.tx)
        with self.assertRaises(ValueError):factual_dossier(self.unit,self.evidence)

    def test_committed_public_source_is_preserved_and_tampering_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);public=root/'public';folder=public/'evidence/R';folder.mkdir(parents=True)
            path=folder/'evidence.json';path.write_text(json.dumps(self.evidence),encoding='utf-8')
            self.unit['evidence_sha256']=sha(path)
            manifest=dict(units=[self.unit],readonly_sha256={'evidence/R/evidence.json':sha(path)})
            (public/'review_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            before={p:sha(p) for p in public.rglob('*') if p.is_file()}
            build_dossiers(public,root/'assistant')
            self.assertEqual(before,{p:sha(p) for p in before})
            path.write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):build_dossiers(public,root/'other')


if __name__=='__main__':unittest.main()
