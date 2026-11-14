import http.client,json
import threading,unittest
from sme_fraud.review_server import make_server


class TransitionServerTest(unittest.TestCase):
    def setUp(self):
        self.server=make_server(0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def request(self,method,path):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        c.request(method,path,body='{}' if method=='POST' else None);r=c.getresponse();body=r.read();code=r.status;c.close();return code,body
    def test_health_reports_core_only_not_a_ready_pipeline(self):
        code,body=self.request('GET','/api/health');self.assertEqual(code,200)
        value=json.loads(body);self.assertFalse(value['pipeline_ready']);self.assertFalse(value['active_delivery'])
    def test_legacy_reads_and_writes_are_retired(self):
        for method,path in [('GET','/api/cases'),('GET','/api/ml-reviews'),('POST','/api/data-import/commit'),('POST','/api/company-ml/evaluate')]:
            with self.subTest(path=path):self.assertEqual(self.request(method,path)[0],410)
    def test_root_is_the_new_import_workbench(self):
        code,body=self.request('GET','/');self.assertEqual(code,200);self.assertIn('Xác nhận lưu'.encode(),body)
        self.assertIn(b'assets/workbench.js',body)


if __name__=='__main__':unittest.main()
