import unittest
import numpy as np
from experiments.he4 import inputs as p,circuits as c


class Inputs(unittest.TestCase):
    def test_payment_keeps_raw_negative_amounts_and_tolerance(self):
        values=p.payment([60000,-20000],[60002],[100000],['payment','adjustment'])
        result=p.decode_payment(c.p1(*values))
        self.assertTrue(result['matched']);self.assertEqual(result['prior_paid_vnd'],40000)
        self.assertFalse(p.decode_payment(c.p1(*p.payment([60000],[40001],[100000],['payment'])))['matched'])
        with self.assertRaises(p.InputUnavailable):p.payment([1]*5,[2],[10],['payment']*5)

    def test_statistics_never_silently_clips_missing_or_out_of_domain(self):
        self.assertEqual(p.statistics([5,3],[1,1],[2,2])[0].tolist(),[2048,1024])
        for values in ([None,1],[float('inf'),1],[1000,1]):
            with self.assertRaises(p.InputUnavailable):p.statistics(values,[0,0],[1,1])

    def test_graph_token_packing_keeps_missing_and_weak_links_separate(self):
        packed=p.graph([dict(bank_account='B|01',address='A'),dict(bank_account='B|01'),dict(address='A')])
        result=c.graph(*packed);links=result[:64].reshape(4,4,4);reach=result[64:].reshape(4,4)
        self.assertTrue(links[0,0,1]);self.assertTrue(links[2,0,2]);self.assertFalse(reach[0,2]);self.assertFalse(np.any(reach[3]))
        with self.assertRaises(p.InputUnavailable):p.graph([{}])
        with self.assertRaises(p.InputUnavailable):p.graph([dict(phone='x')]*5)
