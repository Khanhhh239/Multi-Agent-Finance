import copy
import tempfile
import unittest
from pathlib import Path
from src.quality.evaluation_split import seal,verify


class EvaluationSplitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'invoice.txt').write_bytes(b'new invoice')
        self.row={'path':'invoice.txt','group_id':'new-invoice','source_group':'new-source','layout_group':'new-layout','split':'test'}

    def test_sealed_inputs_are_verified_and_changes_rejected(self):
        m=seal([self.row],{'used-source'},self.root);self.assertTrue(verify(m,self.root))
        (self.root/'invoice.txt').write_bytes(b'changed invoice')
        with self.assertRaises(ValueError):verify(m,self.root)

    def test_same_source_layout_or_invoice_cannot_leak_from_dev(self):
        for key in ('group_id','source_group','layout_group'):
            with self.assertRaises(ValueError):seal([{**self.row,key:'used-source'}],{'used-source'},self.root)

    def test_duplicates_paths_and_split_cannot_bypass_seal(self):
        for rows in ([self.row,self.row],[{**self.row,'path':'../outside.txt'}],[{**self.row,'split':'dev'}]):
            with self.assertRaises(ValueError):seal(rows,set(),self.root)
        m=seal([self.row],set(),self.root);m['entries'][0]['group_id']='changed'
        with self.assertRaises(ValueError):verify(m,self.root)

    def test_empty_dataset_is_pending_never_an_accuracy_pass(self):
        m=seal([],{'used-source'},self.root)
        self.assertEqual(m['status'],'PENDING_UNSEEN_DATA');self.assertFalse(m['accuracy_evaluated'])


if __name__=='__main__':unittest.main()
