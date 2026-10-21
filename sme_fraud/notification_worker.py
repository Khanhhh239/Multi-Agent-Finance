"""Run alert planning, weekly digests and the outbox without a browser session."""
import argparse
import json
from pathlib import Path
import time

from .review_store import ReviewStore
from .notifications import Notifications


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--reports-root', type=Path, default=Path('reports/rules'))
    parser.add_argument('--database', type=Path, default=Path('.runtime/review/review.sqlite3'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--scenario', choices=['001','003','005'], default='003')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval-seconds', type=int, default=60)
    parser.add_argument('--send', action='store_true', help='Explicitly enable configured live transports')
    args = parser.parse_args()
    if args.interval_seconds < 5:
        parser.error('Interval must be at least five seconds')
    while True:
        try:
            config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
            store = ReviewStore(args.data_root, args.reports_root, args.database, scenarios=[args.scenario])
            notifications = Notifications(store, config)
            if not notifications.config['dry_run'] and (not args.config or not args.send):
                parser.error('Live transport requires a config file and --send')
            if args.send and notifications.config['dry_run']:
                parser.error('--send conflicts with dry_run=true')
            store.prepare()
            planned = notifications.plan(args.scenario)
            delivered = notifications.dispatch(allow_live=args.send)
            print(json.dumps(dict(planned=planned, delivered=delivered,
                                  status=notifications.status(args.scenario)['counts']), ensure_ascii=False), flush=True)
        except Exception:
            # Transport/config secrets and provider response bodies never enter logs.
            if not args.watch:
                raise
            print(json.dumps(dict(status='worker_failed', action='Check configuration and source/audit integrity')), flush=True)
        if not args.watch:
            break
        time.sleep(args.interval_seconds)


if __name__ == '__main__':
    main()
