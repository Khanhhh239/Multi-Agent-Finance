"""Flat CSV/JSON parameter tables shared by rule runs and scheduled updates."""
import csv
import json
from pathlib import Path


def write_parameters(output, rows, policy, sources):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ['company_id', 'account_code', 'measurement', 'family',
                                        'as_of', 'window_days', 'phase', 'status', 'threshold_vnd']
    with (output/'dynamic_threshold_parameters.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for name, value in (('dynamic_threshold_parameters.json', rows),
                        ('dynamic_threshold_policy.json', dict(policy=policy, sources=sources))):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
