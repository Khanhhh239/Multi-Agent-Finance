import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src import local_web


class LocalWebTests(unittest.TestCase):
    def test_persistent_random_credential_and_scoped_configuration(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(local_web,'LOCAL',Path(directory)),patch.dict(os.environ,{},clear=True):
            token=local_web.credential()
            self.assertGreaterEqual(len(token),32)
            self.assertEqual(local_web.credential(),token)
            database=Path(directory)/'demo.sqlite3'
            settings,ctx=local_web.configure(token,database)
            self.assertEqual(settings.database_path,database.resolve())
            self.assertEqual(ctx.tenant_id,'demo-tenant');self.assertEqual(ctx.taxpayer_ids,frozenset({'demo-payer'}))
            self.assertNotIn(token,os.environ['CAPTURE_AUTH_GRANTS_JSON'])
            jobs=local_web.provision(settings,ctx)
            local_web.provision(settings,ctx)
            with jobs.base.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM taxpayer_masters').fetchone()[0],1)

    def test_runtime_probe_rejects_non_local_port_values(self):
        for port in ('8000',0,70000):
            with self.assertRaises(ValueError):local_web.request_runtime(port,'not-used')

    def test_corrupt_credential_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(local_web,'LOCAL',Path(directory)):
            path=Path(directory)/'credentials.json';path.write_text(json.dumps({'token':'short'}))
            with self.assertRaises(ValueError):local_web.credential()
            self.assertEqual(json.loads(path.read_text())['token'],'short')


if __name__=='__main__':unittest.main()
