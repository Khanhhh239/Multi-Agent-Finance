"""Raw engine rows and adapter condition observations have different origins."""
import json
from ..persistence.repository import digest
from .contracts import ExecutionTrace
from .models import validate_model


def parse_response(raw, model, context):
    validate_model(model)
    response = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    if not isinstance(response, dict) or set(response) - {'result', 'trace', 'performance'}:
        raise ValueError('Malformed ZEN response envelope')
    result = response.get('result')
    if isinstance(result, list):
        if len(result) != 1:
            raise ValueError('ENGINE_NO_HIT' if not result else 'ENGINE_MULTIPLE_HITS')
        result = result[0]
    if not isinstance(result, dict) or set(result) != {'result'} or result['result'] not in ('PASS', 'FAIL', 'REVIEW'):
        raise ValueError('Malformed engine result; no fallback PASS')
    trace = response.get('trace')
    if not isinstance(trace, dict) or 'table' not in trace:
        raise ValueError('Required raw engine trace missing')
    table = trace['table']
    rows = table.get('traceData')
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError('Expected one engine matched-row observation')
    row_id = rows[0].get('rule', {}).get('_id')
    table_model = json.loads(model.jdm_json)['nodes'][1]['content']
    row = next((r for r in table_model['rules'] if r['_id'] == row_id), None)
    if row is None or json.loads(row['o_result']) != result['result']:
        raise ValueError('Result and model/engine row mismatch')
    facts = context.facts()
    if set(facts) != {b.condition_id for b in model.bindings} or any(type(v) is not bool for v in facts.values()):
        raise ValueError('Context fact shape mismatch')
    expected_row = next((r for r in table_model['rules'] if all(not r[i] or facts[i] == (r[i] == '== true') for i in facts)), None)
    if expected_row is None or expected_row['_id'] != row_id:
        raise ValueError('Engine row differs from restricted table truth conditions')
    raw_input=table.get('input')
    raw_facts=raw_input.get('facts') if isinstance(raw_input,dict) else None
    if not isinstance(raw_facts,dict) or any(type(v) is not bool for v in raw_facts.values()) or raw_input != {'facts': facts}:
        raise ValueError('Raw trace input differs from bound facts')
    if rows[0].get('index') != table_model['rules'].index(row):
        raise ValueError('Raw trace row index differs from pinned model')
    return result['result'], ExecutionTrace(raw_response_json=raw, raw_sha256=digest(raw.encode()),
        matched_row_id=row_id, conditions=context.conditions)
