"""Exercise real v2 scoring, ingestion, isolation and review on synthetic data."""
import io
import json
from pathlib import Path
import zipfile

import yaml

from agent2.pipeline_v4 import run, sha
from agent2.service import create_app


def main():
    root = Path('work/api_v4_smoke')
    root.mkdir(exist_ok=False)
    snapshot = Path('work/results/precision_v4_C001_W40/input_snapshot')
    mapping = {'timezone': 'Asia/Ho_Chi_Minh', 'tables': {}}
    archive = io.BytesIO()
    import csv
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(snapshot.glob('*.csv')):
            columns = next(csv.reader(path.open(encoding='utf-8-sig')))
            mapping['tables'][path.stem] = {'file': path.name, 'columns': dict(zip(columns, columns))}
            output.write(path, path.name)
    config = Path('configs/agent2_default.json')
    def scorer(data, out, company, week):
        return run(data, out, config, week, company)
    app = create_app(root / 'review.sqlite', root / 'storage',
                     {'C001': 'synthetic-only-C001', 'OTHER': 'synthetic-only-OTHER'},
                     scorer, scoring_version=sha(config), synthetic_demo=True)
    app.testing = True
    client = app.test_client()
    owner = {'Authorization': 'Bearer synthetic-only-C001'}
    other = {'Authorization': 'Bearer synthetic-only-OTHER'}
    assert client.get('/cases').status_code == 401
    assert client.get('/cases?company_id=OTHER', headers=owner).status_code == 403
    response = client.post('/ingest', headers=owner, data={
        'file': (io.BytesIO(archive.getvalue()), 'synthetic.zip'),
        'mapping': (io.BytesIO(yaml.safe_dump(mapping, allow_unicode=True).encode()), 'mapping.yaml')})
    assert response.status_code == 201, response.json
    ingest = response.json['ingest_id']
    response = client.post('/score?week=2025-W40', headers=owner, json={'ingest_id': ingest})
    assert response.status_code == 201, response.json
    scored = response.json
    assert scored['report']['profile'] == 'precision'
    assert scored['report']['chosen_policy'] == 'L4-FB'
    assert scored['report']['alert_rows'] <= 3
    repeat = client.post('/score?week=2025-W40', headers=owner, json={'ingest_id': ingest})
    assert repeat.status_code == 200 and repeat.json['cached']
    queue = client.get('/cases', headers=owner).json['cases']
    assert len(queue) == scored['cases'] and queue
    assert client.get('/cases', headers=other).json['cases'] == []
    assert client.post('/score?week=2025-W40', headers=other, json={'ingest_id': ingest}).status_code == 404
    case = queue[0]['case_id']
    payload = {'reviewer_id': 'QA_SYNTHETIC', 'conclusion': 'legitimate',
               'reason': 'Kiểm thử tích hợp bằng dữ liệu tổng hợp; không phải kết luận nghiệp vụ.',
               'review_minutes': 1.5, 'worth_review': False}
    assert client.post(f'/cases/{case}/decision', headers=other, json=payload).status_code == 404
    assert client.post(f'/cases/{case}/decision', headers=owner, json=payload).status_code == 201
    report = client.get('/report', headers=owner).json
    assert report['scores'] == 1 and report['decisions'] == 1
    assert report['worth_review_cases_measured'] == 1
    assert client.get('/decisions', headers=other).json['decisions'] == []
    result = {'status': 'passed', 'data_kind': 'synthetic', 'model_sha256': scored['report']['model_sha256'],
              'rows_scored': scored['report']['rows_scored'], 'alerts': scored['report']['alert_rows'],
              'cases': scored['cases'], 'duplicate_scoring_cached': True, 'cross_company_access_rejected': True,
              'decision_appended': True, 'decisions_are_QA_only': True,
              'numeric_explanation_check': scored['report']['explanation_numbers_supported']}
    Path('results/v4/end_to_end_api.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
