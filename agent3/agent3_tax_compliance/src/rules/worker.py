"""Isolated native-engine worker. Parent enforces time/memory limits first."""
import sys
import json
import importlib.metadata
from pathlib import Path


def main():
    payload = json.loads(sys.stdin.buffer.read())
    if importlib.metadata.version('zen-engine') != '0.53.0':
        raise ValueError('Pinned ZEN 0.53.0 runtime required')
    facts = payload['facts']
    if not isinstance(facts, dict) or not facts or any(type(v) is not bool for v in facts.values()):
        raise ValueError('Strict boolean facts only')
    import zen
    response = zen.ZenEngine().create_decision(payload['jdm_json']).evaluate({'facts': facts}, {'trace': True})
    raw = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > payload['max_response_bytes']:
        raise ValueError('Engine response limit exceeded')
    with Path(payload['output_path']).open('xb') as handle:
        handle.write(raw)


if __name__ == '__main__':
    main()
