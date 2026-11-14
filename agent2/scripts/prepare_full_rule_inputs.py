"""Package synthetic full-rule inputs; never relabel a real enterprise export."""
import argparse
import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance_input import AccessScope
from sme_fraud.import_files import canonical, digest
from sme_fraud.native_rule_demo import scenario
from sme_fraud.rule_snapshot import CONTRACT, validate


def wrap(source):
    source = deepcopy(source)
    if source.get('is_simulated') is not True or source['tenant_id'] != 'native-demo':
        raise ValueError('Only the native-demo synthetic producer is allowed')
    source['tenant_id'] = 'demo'
    data = dict(contract_version=CONTRACT, tenant_id='demo', company_id=source['company_id'],
                source=source, candidate_transaction_ids=[source['tables']['transactions'][-1]['transaction_id']])
    return data


def checked(data):
    scope = AccessScope('demo', frozenset({data['company_id']}), 'synthetic-input-preparer', frozenset({'data.import'}))
    result = validate(data, scope)
    if result['status'] == 'rejected':
        raise ValueError(result['errors'])
    return canonical(data)


def run(inputs, output):
    manifest = json.loads((inputs / 'manifest.json').read_bytes())
    if manifest['version'] != 'native-rule-demo/1.0.0' or len(manifest['cases']) != 120:
        raise ValueError('Complete synthetic source manifest required')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(output / 'full_rule_inputs_C001_C002.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for case in manifest['cases']:
            path = inputs / case['source_file']
            if path.resolve().parent != inputs.resolve() or digest(path.read_bytes()) != case['source_sha256']:
                raise ValueError('Synthetic source checksum/path mismatch')
            data = wrap(json.loads(path.read_bytes()))
            raw = checked(data)
            name = case['case_id'] + '.json'
            archive.writestr(name, raw)
            records.append(dict(file=name, company_id=data['company_id'], sha256=digest(raw)))
        archive.writestr('manifest.json', canonical(dict(version='synthetic-rule-inputs/1.0.0', tenant_id='demo',
                         is_simulated=True, contract_version=CONTRACT, files=records)))
    samples = [('C001', 'B1'), ('C002', 'B1'), ('C001', 'C2'), ('C001', 'E2'), ('C001', 'F4')]
    for company, rule in samples:
        source, _ = scenario(rule, True, company)
        (output / f'{company}_{rule}_signal.json').write_bytes(checked(wrap(source)))
    source, _ = scenario('B1', True, 'C001')
    unknown = wrap(source)
    for coverage in unknown['source']['coverage'].values():
        coverage['status'] = 'unknown'
    (output / 'C001_coverage_unknown.json').write_bytes(checked(unknown))
    report = dict(status='passed', wrapped_sources_validated=len(records), standalone_examples=6,
                  tenant_id='demo', source_kind='simulated', source_contract=CONTRACT,
                  schema_sha256=digest((ROOT / 'sme_fraud/rule_snapshot.schema.json').read_bytes()),
                  validator_sha256=digest((ROOT / 'sme_fraud/rule_snapshot.py').read_bytes()),
                  zip_sha256=digest((output / 'full_rule_inputs_C001_C002.zip').read_bytes()))
    (output / 'validation-report.json').write_bytes(canonical(report))
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=ROOT / '.runtime/native_rules_demo_20261114')
    parser.add_argument('--output', type=Path, default=ROOT / 'examples/full_rules')
    args = parser.parse_args()
    run(args.inputs.resolve(), args.output.resolve())
