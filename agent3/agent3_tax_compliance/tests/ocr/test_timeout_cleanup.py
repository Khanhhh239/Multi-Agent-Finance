import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from src.config import PROJECT
from src.ingestion.sandbox import run_bounded,worker_workspace
from src.ingestion.models import IngestionError


@unittest.skipUnless(os.name=='nt','Windows venv redirector regression')
class TimeoutCleanupTests(unittest.TestCase):
    def test_timeout_reaps_interpreter_before_removing_locked_response(self):
        with self.assertRaises(IngestionError) as error:
            with worker_workspace(prefix='ocr-timeout-test-') as directory:
                path=Path(directory)/'responses.jsonl'
                script="import json,sys,time; p=json.loads(sys.stdin.buffer.read())['path']; f=open(p,'w'); f.write('opened'); f.flush(); time.sleep(60)"
                try:
                    run_bounded([sys.executable,'-c',script],json.dumps({'path':str(path)}).encode(),3,256,PROJECT)
                except IngestionError:
                    self.assertTrue(path.exists(),'Worker must open the response before testing its lock')
                    raise
        self.assertEqual(error.exception.issue.code,'WORKER_TIMEOUT')
        self.assertFalse(Path(directory).exists())


if __name__=='__main__':unittest.main()
