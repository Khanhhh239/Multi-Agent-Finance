import tempfile
from pathlib import Path
import unittest
from experiments.he4.vault import seal,open_private


class Vault(unittest.TestCase):
    def test_large_roundtrip_restart_and_wrong_binding(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'context.sealed';key=b'k'*32;raw=b'native HE secret\x00'*100000;binding=dict(tenant='t',company='C001',circuit='abc')
            seal(path,key,binding,raw)
            self.assertEqual(open_private(path,key,binding),raw)
            self.assertNotIn(b'native HE secret',path.read_bytes())
            for changed in (dict(binding,company='C002'),dict(binding,circuit='other')):
                with self.assertRaises(ValueError):open_private(path,key,changed)
            with self.assertRaises(Exception):open_private(path,b'x'*32,binding)
            with self.assertRaises(ValueError):seal(path,key,binding,raw)
            data=bytearray(path.read_bytes());data[-17]^=1;path.write_bytes(data)
            with self.assertRaises(Exception):open_private(path,key,binding)
