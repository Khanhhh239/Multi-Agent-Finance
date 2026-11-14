"""Isolated real Portal + embedded DN node + ciphertext-only worker fixture."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT.parent)]
from test_portal_auth import PortalHarness
from portal import server as portal
from experiments.he_inference.enterprise_server import load_node
from experiments.he_inference.protocol import read_json
from experiments.he_inference.services_demo import Pair
from sme_fraud.he_workbench import HEWorkbench
from sme_fraud.review_server import make_server


class WebHarness:
    def __init__(self,*,state_key_file=None):self.state_key_file=state_key_file
    def __enter__(self):
        self.stack = ExitStack()
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='he-web-')))
        self.pair = Pair(root,state_key_file=self.state_key_file); self.stack.callback(self.pair.close); self.pair.start()
        # Only one process/object may open the enterprise state directory.
        self.pair._stop(self.pair.node_process)
        self.h = self.stack.enter_context(PortalHarness())
        self.h.agent.shutdown(); self.h.agent.server_close()
        self.h.store = self.pair.env['snapshots']
        self.bindings = self.pair.enterprise / 'ui-bindings.json'
        self.pins = dict(version='he-ui-bindings/1.0.0', bindings=[dict(tenant_id='demo', company_id=c,
            artifact_id=self.pair.env['artifacts'][c]) for c in ('C001','C002')])
        self.write_pins()
        self.node = load_node(read_json(self.pair.node_config), self.h.authorizer)
        self.stack.callback(lambda: self.backend.node.jobs.close())
        self.backend = HEWorkbench(self.node, self.bindings)
        self.h.agent = make_server(0, self.h.authorizer, self.h.store, he_backend=self.backend)
        portal.CFG['agents']['agent2']['port'] = self.h.agent.server_port
        thread = threading.Thread(target=self.h.agent.serve_forever, daemon=True); thread.start(); self.h.threads.append(thread)
        return self

    def write_pins(self):
        self.bindings.write_text(json.dumps(self.pins), encoding='utf-8')

    def __exit__(self, *args):
        self.stack.close()

    def request(self, tail='datasets', company='C001', body=None, **kwargs):
        return self.h.request(self.h.url('he/'+tail, company), body, **kwargs)
