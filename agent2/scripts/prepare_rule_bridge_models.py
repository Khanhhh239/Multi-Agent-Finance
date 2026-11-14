"""Prepare/check/activate explicitly simulated C001/C002 bridge models."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
from sme_fraud.rule_bridge_models import activate, check, prepare


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'activate'))
    parser.add_argument('--portal-config', type=Path, default=ROOT.parent / 'portal/config.local.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        settings = json.loads(args.portal_config.read_text(encoding='utf-8-sig'))['agents']['agent2']
        resolve = lambda value: (ROOT.parent / value).resolve()
        result = prepare(resolve(settings['snapshot_db']), resolve(settings['model_db']), resolve(settings['analysis_bindings']),
                         resolve(settings['access_file']), args.output.resolve())
        print(json.dumps(dict(status=result['status'], companies=[r['company_id'] for r in result['companies']],
                              feature_contract_fingerprint=result['feature_contract_fingerprint'])))
    else:
        print(json.dumps(check(args.output.resolve()) if args.action == 'check' else activate(args.output.resolve())))
