import time
import unittest
from web_support import WebHarness


class ReviewAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=WebHarness().__enter__()
        cls.company='C001';snapshot=cls.f.pair.env['queries'][cls.company]
        status,value=cls.f.request('jobs',body={'snapshot_id':snapshot},headers={'Idempotency-Key':'review-api-run-1'})
        if status!=202:raise AssertionError(value)
        cls.job=value['job_id'];end=time.monotonic()+50
        while time.monotonic()<end:
            status,cls.result=cls.f.request('jobs/'+cls.job+'/result')
            if status==200:return
            time.sleep(.1)
        raise AssertionError('HE result timed out')

    @classmethod
    def tearDownClass(cls):cls.f.__exit__()

    def test_review_round_trip_and_replay(self):
        prefix='jobs/'+self.job+'/reviews';status,packet=self.f.request(prefix)
        self.assertEqual(status,200,packet);self.assertEqual(len(packet['cases']),5)
        self.assertFalse(packet['training_eligible']);case=packet['cases'][0]
        for evidence in case['evidence']:
            self.assertTrue(evidence['simulated']);self.assertFalse(evidence['original_verified'])
        path=prefix+'/'+case['case_id'];status,lease=self.f.request(path+'/start',body={})
        self.assertEqual(status,200,lease)
        body=dict(lease=lease['lease'],expected_revision=0,request_id='review-save-0001',feedback=dict(outcome='inconclusive',usefulness='not_assessed',explanation='Original document absent',action='Request invoice from AP',missing_materials='Original invoice',evidence_ids=[],checks_completed=False))
        status,saved=self.f.request(path+'/save',body=body);self.assertEqual(status,200,saved)
        self.assertEqual(self.f.request(path+'/save',body=body)[1],saved)
        status,again=self.f.request(prefix);self.assertEqual(status,200,again)
        self.assertEqual(again['cases'][0]['review']['revision'],1)
        self.assertEqual(self.f.request(prefix,company='C002')[0],404)
        self.assertEqual(self.f.request(prefix,token=False)[0],401)

    def test_client_cannot_replace_pinned_evidence(self):
        prefix='jobs/'+self.job+'/reviews';case=self.f.request(prefix)[1]['cases'][1]
        path=prefix+'/'+case['case_id'];lease=self.f.request(path+'/start',body={})[1]['lease']
        body=dict(lease=lease,expected_revision=0,request_id='review-foreign-1',feedback=dict(outcome='legitimate',usefulness='no',explanation='Claimed original',action='',missing_materials='',evidence_ids=['foreign'],checks_completed=True))
        self.assertEqual(self.f.request(path+'/save',body=body)[0],422)
        self.assertEqual(self.f.request(path+'/start',body={'actor_id':'boss'})[0],400)


if __name__=='__main__':unittest.main()
