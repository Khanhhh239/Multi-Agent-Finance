import unittest
import numpy as np
from experiments.he4 import circuits as c


class Reference(unittest.TestCase):
    def test_signed_money_roundtrip_and_exact_large_arithmetic(self):
        values=[-(2**63),-1001,-1,0,1,1000,2**63-1]
        for a in values:
            for b in values:
                aa,bb=c.encode_money(a),c.encode_money(b)
                self.assertEqual(c.decode_money(c.add_word(aa,bb)),a+b)
                self.assertEqual(c.decode_money(c.subtract_word(aa,bb)),a-b)
                self.assertEqual(bool(c.signed_gt(aa,bb)),a>b)

    def test_p1_boundary_adjustments_and_group_mode(self):
        def run(prior,current,cap,group=0,kinds=None):
            def rows(values):return np.array([c.encode_money(v) for v in values+[0]*(4-len(values))])
            return c.p1(rows(prior),rows(current),rows(cap),np.array((kinds or [1]*len(prior))+[0]*(4-len(prior))),c.encode_money(1000),group)
        for prior,current,cap,expected in (([60000],[41000],[100000],False),([60000],[41001],[100000],True),([60000,-20000],[41001],[100000],False),([],[110000],[100000],False),([200000],[-1],[100000],False)):
            value=run(prior,current,cap);self.assertEqual(bool(value[0]),expected)
            self.assertEqual(c.decode_money(value[2:2+c.WORD_DIGITS]),sum(prior))
        self.assertTrue(run([],[110000],[100000],1)[0])

    def test_graph_requires_known_active_attributes_and_transitive_strong_links(self):
        tokens=np.zeros((4,4,c.TOKEN_DIGITS),dtype=np.int64);known=np.ones((4,4),dtype=np.int64);active=np.ones(4,dtype=np.int64)
        # Make each node unique initially.
        for i in range(4):tokens[i,:,:]=i
        tokens[1,0]=tokens[0,0];tokens[2,1]=tokens[1,1];tokens[3,2]=tokens[0,2]
        result=c.graph(tokens,known,active);links=result[:64].reshape(4,4,4);reach=result[64:].reshape(4,4)
        self.assertTrue(reach[0,2]);self.assertFalse(reach[0,3]);self.assertTrue(links[2,0,3])
        known[1,0]=0;self.assertFalse(c.graph(tokens,known,active)[64:].reshape(4,4)[0,2])
        active[0]=0;self.assertFalse(np.any(c.graph(tokens,known,active)[64:].reshape(4,4)[0]))

    def test_robust_z_math(self):
        self.assertEqual(c.robust_z(np.array([-12000,100])),10340)


if __name__=='__main__':unittest.main()
