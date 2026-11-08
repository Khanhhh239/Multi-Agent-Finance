"""Open an isolated 001/003 + P2 demo for manual browser acceptance."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from sme_fraud.notifications import Notifications
from sme_fraud.p2_controls_server import SOURCE, REPORT
from sme_fraud.p2_controls_web import P2Controls
from sme_fraud.review_backup import restore_backup, restored_store
from sme_fraud.review_server import make_server

DEMO = PROJECT / '.runtime/browser_acceptance_20261019/demo'
BUNDLE = PROJECT / '.runtime/backup_restore_20261019/final/backup_live_demo'


def stores():
    if not DEMO.exists():
        restore_backup(BUNDLE, DEMO)
    store = restored_store(DEMO)
    controls = P2Controls(SOURCE, REPORT, DEMO.parent / 'p2_uat.sqlite3')
    return store, controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8771)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    store, controls = stores()
    if args.prepare_only:
        print('Isolated browser acceptance data ready.', flush=True)
        return
    # No worker, recipients, provider configuration or automatic dispatch.
    notifications = Notifications(store, dict(dry_run=True, recipients={}))
    server = make_server(store, args.port, qa=True,
                         instance_id='BROWSER_ACCEPTANCE_20261019',
                         notifications=notifications, p2_controls=controls)
    notifications.config['case_url'] = f'http://127.0.0.1:{server.server_port}/'
    print(f'Browser acceptance: http://127.0.0.1:{server.server_port}/', flush=True)
    print('P2: /p2-controls; simulation only; notifications dry-run.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
