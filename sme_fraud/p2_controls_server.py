"""Local P2 UAT web; can also be mounted in the regular review server."""
import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from .p2_controls_web import P2Controls, PROJECT

WEB = PROJECT/'review_ui'
SOURCE = PROJECT/'data/p2_controls_20261018_v2'
REPORT = PROJECT/'reports/p2_controls_20261018'


class P2Routes:
    """Shared routes; host, origin and CSRF checks belong to the host handler."""
    def controls_get(self, path, query):
        assets = {'/p2-controls': ('p2_controls.html', 'text/html; charset=utf-8'),
                  '/review_explanations.js': ('review_explanations.js', 'text/javascript; charset=utf-8'),
                  '/p2_controls.js': ('p2_controls.js', 'text/javascript; charset=utf-8'),
                  '/p2_controls.css': ('p2_controls.css', 'text/css; charset=utf-8')}
        store = self.p2_controls
        if path in assets:
            filename, mime = assets[path]
            self.respond(200, (WEB/filename).read_bytes(), mime)
        elif path == '/api/p2-controls/meta':
            self.respond(200, store.metadata() | dict(csrf_token=self.p2_csrf))
        elif path in {'/api/p2-controls', '/api/p2-controls/export'}:
            result = store.list_controls(**{key: query.get(key, '') for key in ('group', 'category', 'verdict', 'q')})
            if path.endswith('/export'):
                stream = io.StringIO(newline='')
                writer = csv.writer(stream)
                writer.writerow(['control_id', 'group', 'title', 'transactions', 'automated_match',
                                 'uat_verdict', 'reviewer', 'reason', 'reviewed_at'])
                for row in result['items']:
                    review = row['review'] or {}
                    cells = [row['control_id'], row['group'], row['title_vi'], row['transactions'], row['matched'],
                             *[review.get(key, '') for key in ('verdict', 'reviewer', 'reason', 'reviewed_at')]]
                    writer.writerow(["'"+value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for value in cells])
                self.respond(200, '\ufeff'+stream.getvalue(), 'text/csv; charset=utf-8',
                             {'Content-Disposition': 'attachment; filename="p2-uat.csv"'})
            else:
                self.respond(200, result)
        elif path == '/api/p2-controls/detail':
            self.respond(200, store.detail(query.get('id', '')))
        else:
            return False
        return True


def make_server(store, port=8767):
    token = secrets.token_urlsafe(32)

    class Handler(P2Routes, BaseHTTPRequestHandler):
        p2_controls, p2_csrf = store, token

        def respond(self, status, body, content_type='application/json; charset=utf-8', extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            elif isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(status)
            for name, value in {'Content-Type': content_type, 'Content-Length': str(len(body)),
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'", **(extra or {})}.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def context(self):
            port = self.server.server_port
            if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                raise PermissionError('Chỉ truy cập qua localhost của máy này.')
            url = urlsplit(self.path)
            return url.path, {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}

        def error(self, error):
            code = 403 if isinstance(error, PermissionError) else 404 if isinstance(error, KeyError) else 409 if isinstance(error, RuntimeError) else 400 if isinstance(error, (ValueError, TypeError)) else 503
            self.respond(code, dict(error=str(error) if code != 503 else 'Chưa thể đọc hoặc lưu dữ liệu nghiệm thu.'))

        def do_GET(self):
            try:
                path, query = self.context()
                if path == '/':
                    path = '/p2-controls'
                if self.controls_get(path, query):
                    return
                if path == '/styles.css':
                    self.respond(200, (WEB/'styles.css').read_bytes(), 'text/css; charset=utf-8')
                elif path == '/api/health':
                    self.respond(200, dict(status='ok', application='p2-control-uat', snapshot_id=store.snapshot_id))
                else:
                    raise KeyError('Không tìm thấy trang nghiệm thu.')
            except Exception as error:
                self.error(error)

        def do_POST(self):
            try:
                path, _ = self.context()
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), token):
                    raise PermissionError('Phiên đã thay đổi. Tải lại trang để tiếp tục.')
                if self.headers.get('Origin') not in {None, 'http://'+self.headers['Host']}:
                    raise PermissionError('Nguồn yêu cầu không hợp lệ.')
                length = int(self.headers.get('Content-Length', 0))
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or not 0 < length <= 16_384:
                    raise ValueError('Nội dung JSON không hợp lệ hoặc quá dài.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Nội dung yêu cầu phải là một đối tượng.')
                if path == '/api/p2-controls/review':
                    self.respond(200, store.save_review(body))
                elif path == '/api/shutdown':
                    self.respond(200, dict(status='stopping'))
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    raise KeyError('Không có thao tác này.')
            except Exception as error:
                self.error(error)

        def log_message(self, fmt, *args):
            print(f'HTTP {self.command} {urlsplit(self.path).path}', flush=True)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--database', type=Path, default=PROJECT/'.runtime/p2_controls_web/reviews.sqlite3')
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    store = P2Controls(args.source, args.report, args.database)
    server = make_server(store, args.port)
    print(f'P2 controls ready: http://127.0.0.1:{server.server_port}/p2-controls', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
