"""Portable, paginated offline review; invoice text never becomes HTML markup."""
import base64
import html
import io
import json
import os
from pathlib import Path
from urllib.parse import quote

from src.quality.ocr_evaluation import HEADER_FIELDS, ITEM_FIELDS, fingerprint


def write_index(target, inventory):
    cards = []
    for page in inventory:
        number = page['page']
        cards.append(f'<article><h2>Trang {number:03d} — {"Đã chọn" if page["selected"] else "Loại khỏi OCR hóa đơn"}</h2>'
                     f'<a href="pages/page_{number:03d}.pdf"><img loading="lazy" src="pages/page_{number:03d}.png" alt="Trang {number}"></a>'
                     f'<p>{html.escape(page["title_hint"])} · {page["input_kind"]}</p></article>')
    (target / 'index.html').write_bytes(('<!doctype html><html lang="vi"><meta charset="utf-8">'
        '<title>Danh mục trang hóa đơn</title><style>body{font:16px system-ui;margin:24px;background:#eef2f6}'
        'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}'
        'article{background:white;padding:12px;border-radius:8px}img{width:100%}h2{font-size:18px}</style>'
        '<h1>Danh mục PDF đã tách</h1><p>Nhấp ảnh để mở PDF. Mỗi file giữ nguyên một trang nguồn. '
        'Các trang thuộc cùng một hóa đơn được gom theo manifest khi chạy OCR.</p><main>'
        + ''.join(cards) + '</main></html>').encode())


def slim_field(field):
    if not isinstance(field, dict):
        return None
    return {'value': field.get('value'), 'status': field.get('status', 'MISSING')}


def slim_record(record):
    """Provenance/candidates stay in the immutable run, not in every DOM editor."""
    if not record:
        return None
    result = {}
    for path in HEADER_FIELDS:
        source = record
        for name in path.split('.'):
            source = source.get(name) if isinstance(source, dict) else None
        target = result
        parts = path.split('.')
        for name in parts[:-1]:
            target = target.setdefault(name, {})
        target[parts[-1]] = slim_field(source)
    result['items'] = [dict(line_number=item.get('line_number', index + 1),
                            **{name: slim_field(item.get(name)) for name in ITEM_FIELDS})
                       for index, item in enumerate(sorted(record.get('items', []), key=lambda item: item['line_number']))]
    return result


def embedded_preview(image_path, pdf_path, page_index):
    """Data URLs work in file, HTTP and editor previews without local-file access."""
    from PIL import Image
    try:
        with Image.open(image_path) as source:
            image = source.convert('RGB')
    except (OSError, ValueError):
        try:
            import pymupdf as fitz
            with fitz.open(pdf_path) as document:
                pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
        except (OSError, ValueError, IndexError, RuntimeError):
            return None
    with image:
        image.thumbnail((1500, 2100))
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=90, subsampling=0, optimize=True)
        png = io.BytesIO()
        image.save(png, format='PNG', optimize=True)
        # Flat invoice text is often smaller and sharper as PNG; photographs
        # usually compress better as JPEG. Embed whichever is smaller.
        content, mime = min(((output.getvalue(), 'image/jpeg'), (png.getvalue(), 'image/png')),
                            key=lambda candidate: len(candidate[0]))
    return 'data:' + mime + ';base64,' + base64.b64encode(content).decode('ascii')


def write_review(path, folder, report, manifest, prepared, annotations=None, scored=None):
    path = Path(path)
    root = Path(__file__).resolve().parents[1]
    cases = []
    entries = {entry['case_id']: entry for entry in manifest['entries']}
    scores = {case['case_id']: case['score'] for case in (scored or {}).get('cases', [])}
    for row in report['cases']:
        entry = entries[row['case_id']]
        artifact_path = folder / row['case_id'] / 'extraction.json'
        artifact = json.loads(artifact_path.read_text(encoding='utf-8')) if artifact_path.exists() else {}
        pdf_path = (root / entry['path']).resolve()
        cases.append({'case_id': row['case_id'], 'sha256': entry['sha256'], 'state': row['state'],
                      'error_code': row.get('error_code'), 'seconds': row.get('elapsed_seconds'),
                      'routes': row.get('routes', []), 'source_pages': entry['source_pages'],
                      'images': [embedded_preview(prepared / 'pages' / f'page_{number:03d}.png', pdf_path, index)
                                 for index, number in enumerate(entry['source_pages'])],
                      'pdf': quote(Path(os.path.relpath(pdf_path, path.parent)).as_posix(), safe='/.'),
                      'record': slim_record(artifact.get('record')),
                      'issues': [{name: issue.get(name) for name in ('code', 'field_path', 'message')}
                                 for issue in artifact.get('issues', [])],
                      'labels': (annotations or {}).get(row['case_id'], {}).get('labels', {}),
                      'outcomes': {outcome['field_path']: outcome['outcome']
                                   for outcome in scores.get(row['case_id'], {}).get('outcomes', [])}})
    payload = {'run_id': folder.name, 'run_state': report.get('run_state'), 'cases': cases,
               'headers': HEADER_FIELDS, 'item_fields': ITEM_FIELDS, 'scored': scored is not None,
               'annotation_revision': fingerprint({case['case_id']: [case['sha256'], case['labels'], case['outcomes']] for case in cases})}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c').replace('&', r'\u0026')
    template = Path(__file__).with_name('invoice_test_review_template.html').read_text(encoding='utf-8')
    content = template.replace('__PAYLOAD__', encoded).encode()
    temporary = path.with_suffix('.html.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)
