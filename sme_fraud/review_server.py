"""Loopback-only case review MVP, using Python's standard library."""
from __future__ import annotations

import argparse
import csv
import io
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .review_store import ReviewStore

WEB_ROOT = Path(__file__).resolve().parents[1] / 'review_ui'


def make_server(store, port=8765, qa=False, instance_id=''):
    csrf = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body, content_type='application/json; charset=utf-8', extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            elif isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header('Referrer-Policy', 'no-referrer')
            if extra:
                for key, value in extra.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            expected_port = self.server.server_port
            return self.headers.get('Host') in {f'127.0.0.1:{expected_port}', f'localhost:{expected_port}'}

        def context(self):
            if not self.allowed_host():
                raise PermissionError('Chỉ truy cập ứng dụng qua địa chỉ localhost của máy này.')
            parsed = urlsplit(self.path)
            query = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
            return parsed.path, query

        def error_response(self, error):
            status = 403 if isinstance(error, PermissionError) else 404 if isinstance(error, KeyError) else 429 if isinstance(error, OverflowError) else 409 if isinstance(error, RuntimeError) else 400 if isinstance(error, (ValueError, TypeError)) else 503
            message = str(error) if status != 503 else 'Chưa thể đọc hoặc lưu dữ liệu. Kiểm tra nhật ký ứng dụng và thử lại.'
            self.respond(status, dict(error=message))

        def do_GET(self):
            try:
                path, query = self.context()
                assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
                if path in assets:
                    filename, mime = assets[path]
                    self.respond(200, (WEB_ROOT / filename).read_bytes(), mime)
                elif path == '/api/health':
                    self.respond(200, dict(status='ok', application='sme-case-review', qa=qa, instance_id=instance_id))
                elif path == '/api/meta':
                    self.respond(200, store.metadata() | dict(csrf_token=csrf, qa=qa))
                elif path == '/api/cases':
                    self.respond(200, store.list_cases(query.get('scenario', '003'), company=query.get('company', ''),
                        status=query.get('status', 'active'), priority=query.get('priority', ''), rule=query.get('rule', ''),
                        query=query.get('q', ''), offset=int(query.get('offset', 0)), limit=int(query.get('limit', 30))))
                elif path == '/api/case':
                    self.respond(200, store.detail(query.get('scenario', '003'), query.get('id', '')))
                elif path == '/api/transaction':
                    self.respond(200, store.transaction(query.get('scenario', '003'), query.get('id', '')))
                elif path == '/api/coverage':
                    self.respond(200, json.loads((store.report(query.get('scenario', '003')) / 'rule_coverage.json').read_text(encoding='utf-8')))
                elif path == '/api/export':
                    parameters = dict(company=query.get('company', ''), status=query.get('status', 'active'),
                                      priority=query.get('priority', ''), rule=query.get('rule', ''), query=query.get('q', ''))
                    scenario, rows, offset = query.get('scenario', '003'), [], 0
                    while True:
                        page = store.list_cases(scenario, **parameters, offset=offset, limit=100)
                        rows.extend(page['items'])
                        offset += 100
                        if offset >= page['total']:
                            break
                    output = io.StringIO(newline='')
                    fields = ['case_id', 'company_id', 'status', 'priority', 'max_score', 'opened_at', 'last_seen_at',
                              'owner_name', 'observation_count', 'explanation_vi']
                    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
                    writer.writeheader()
                    for row in rows:
                        # A text cell from feedback/master data must not become an Excel formula.
                        writer.writerow({k: ('\'' + str(row.get(k, ''))) if isinstance(row.get(k), str) and row[k].lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) else row.get(k, '') for k in fields})
                    self.respond(200, ('\ufeff' + output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8',
                                 {'Content-Disposition': 'attachment; filename="review_cases.csv"'})
                else:
                    raise KeyError('Không tìm thấy nội dung yêu cầu.')
            except Exception as error:
                self.error_response(error)

        def do_POST(self):
            try:
                path, _ = self.context()
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), csrf):
                    raise PermissionError('Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.')
                origin = self.headers.get('Origin')
                if origin and origin != f"http://{self.headers['Host']}":
                    raise PermissionError('Nguồn yêu cầu không hợp lệ.')
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Chỉ nhận nội dung JSON.')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 16_384:
                    raise ValueError('Nội dung yêu cầu không hợp lệ hoặc quá dài.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Nội dung yêu cầu phải là một đối tượng.')
                scenario = body.get('scenario', '003')
                if path == '/api/admit':
                    result = store.admit(scenario, body.get('case_id', ''))
                elif path == '/api/feedback':
                    result = store.save_feedback(scenario, body.get('case_id', ''), body.get('decision', ''),
                        body.get('reviewer', ''), body.get('reason', ''), body.get('expected_hash', ''))
                elif path == '/api/budget':
                    result = dict(daily_budget=store.set_budget(body.get('daily_budget')))
                elif path == '/api/shutdown':
                    self.respond(200, dict(status='stopping'))
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                else:
                    raise KeyError('Không tìm thấy thao tác yêu cầu.')
                self.respond(200, result)
            except Exception as error:
                self.error_response(error)

        def log_message(self, fmt, *args):
            # Avoid logging reviewer names/reasons or query data.
            print(f'HTTP {self.command} {urlsplit(self.path).path}', flush=True)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--reports-root', type=Path, default=Path('reports/rules'))
    parser.add_argument('--database', type=Path, default=Path('.runtime/review/review.sqlite3'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--qa', action='store_true')
    parser.add_argument('--instance-id', default='')
    args = parser.parse_args()
    store = ReviewStore(args.data_root, args.reports_root, args.database)
    store.prepare()
    if args.prepare_only:
        return
    server = make_server(store, args.port, args.qa, args.instance_id)
    print(f'Review UI ready: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
