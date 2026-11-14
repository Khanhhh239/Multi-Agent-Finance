import sys,tempfile,json,shutil,unittest,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from check_evidence import check
class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name)
  shutil.copytree(ROOT/'templates',self.r/'templates');shutil.copy(ROOT/'test_catalog.json',self.r/'test_catalog.json')
  self.f=self.r/'evidence/R1';self.f.mkdir(parents=True)
  ids=[x['id'] for x in json.loads((self.r/'test_catalog.json').read_text())['tests'] if x['stage']=='R1']
  self.xml='<testsuite>'+''.join('<testcase name="'+x+'"/>' for x in ids)+'</testsuite>'
  self.a={'spec_version':'2.1','stage':'R1','run_id':'selftest','tests':[{'id':x,'status':'pass','expected':'fixture assertion','observed':'test passed','evidence_path':'report.xml'} for x in ids]}
  self.result={'spec_version':'2.1','stage':'R1','run_id':'selftest','commit':'selftest-only','tool_versions':{'runner':'test'},'commands':[{'exit_code':0,'timed_out':False,'format':'junit','report_file':'report.xml','report_sha256':''}]}
 def tearDown(self):self.tmp.cleanup()
 def save(self):
  (self.f/'report.xml').write_text(self.xml);self.result['commands'][0]['report_sha256']=hashlib.sha256((self.f/'report.xml').read_bytes()).hexdigest()
  (self.f/'commands_result.json').write_text(json.dumps(self.result));(self.f/'acceptance.json').write_text(json.dumps(self.a))
 def reject(self):
  self.save()
  with self.assertRaises(Exception):check(self.r,'R1')
 def test_valid(self):self.save();self.assertEqual(check(self.r,'R1')['status'],'READY_FOR_REVIEW')
 def test_skip(self):self.xml=self.xml.replace('/>','><skipped/></testcase>',1);self.reject()
 def test_failure(self):self.xml=self.xml.replace('/>','><failure/></testcase>',1);self.reject()
 def test_empty_report(self):self.xml='<testsuite/>';self.reject()
 def test_missing_id(self):self.a['tests'].pop();self.reject()
 def test_stale_run(self):self.a['run_id']='old';self.reject()
 def test_nonzero(self):self.result['commands'][0]['exit_code']=1;self.reject()
 def test_timeout(self):self.result['commands'][0]['timed_out']=True;self.reject()
 def test_tamper(self):
  self.save();(self.f/'report.xml').write_text('<testsuite/>')
  with self.assertRaises(ValueError):check(self.r,'R1')
if __name__=='__main__':unittest.main()
