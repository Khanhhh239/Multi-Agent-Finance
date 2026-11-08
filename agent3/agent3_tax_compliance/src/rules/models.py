"""Small, auditable boolean decision tables; every supported input has a row."""
import json
from pathlib import Path
from ..persistence.repository import digest
from .contracts import ModelPackage

ROOT = Path(__file__).resolve().parents[2] / 'rules/models'


def jdm(bindings, review_condition_id=None):
    ids = [b.condition_id for b in bindings]
    if review_condition_id is not None and review_condition_id not in ids:
        raise ValueError('Review condition must be declared')
    inputs = [dict(id=i, name=i, type='expression', field='facts.' + i) for i in ids]
    outputs = [dict(id='o_result', name='result', type='expression', field='result')]
    rows = []
    for identifier in ids:
        if identifier == review_condition_id:
            continue
        row = {'_id': 'fail-' + identifier, **{i: '' for i in ids}, 'o_result': '"FAIL"'}
        row[identifier] = '== false'
        rows.append(row)
    if review_condition_id:
        rows.append({'_id': 'review-policy', **{i: '== true' for i in ids}, 'o_result': '"REVIEW"'})
    rows.append({'_id': 'pass-all', **{i: '== false' if i == review_condition_id else '== true' for i in ids}, 'o_result': '"PASS"'})
    return dict(contentType='application/vnd.gorules.decision', nodes=[
        dict(id='input', name='Verified adapter facts', type='inputNode', position=dict(x=0, y=0)),
        dict(id='table', name='Explicit result table', type='decisionTableNode', position=dict(x=300, y=0),
             content=dict(hitPolicy='first', inputs=inputs, outputs=outputs, rules=rows)),
        dict(id='output', name='Outcome', type='outputNode', position=dict(x=600, y=0))],
        edges=[dict(id='edge-in', type='edge', sourceId='input', targetId='table'),
               dict(id='edge-out', type='edge', sourceId='table', targetId='output')])


def validate_model(model):
    expected = jdm(model.bindings, model.review_condition_id)
    if json.loads(model.jdm_json) != expected:
        raise ValueError('Only the pinned restricted boolean-table contract is supported')
    if digest(model.jdm_json.encode()) != model.jdm_sha256:
        raise ValueError('Model content hash changed')
    return model


def load_package():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    models = []
    for row in manifest.pop('models'):
        name = row.pop('file')
        if Path(name).name != name:
            raise ValueError('Model file must be in registry')
        row['jdm_json'] = (ROOT / name).read_text(encoding='utf-8')
        models.append(row)
    package = ModelPackage.model_validate({**manifest, 'models': models})
    for model in package.models:
        validate_model(model)
    return package
