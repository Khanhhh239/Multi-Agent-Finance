"""Trạm huấn luyện mã hóa (máy chủ trạm) — web riêng, cổng 8890.

Giao diện tối giản cho người vận hành trạm: doanh nghiệp nào đã gửi dữ liệu (đã mã hóa), số nhãn, nút huấn luyện,
tiến độ, kết quả kiểm định và lịch sử phiên bản trọng số (chỉ cập nhật khi tốt hơn).
Trạm gọi backend Agent 2 qua cổng loopback bằng khóa trạm cục bộ; trạm không có khóa giải mã của doanh nghiệp.
Chạy: python station/server.py [--port 8890]
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
SECRET = Path(os.environ.get('AGENT2_STATION_SECRET_FILE')
              or ROOT.parent / 'agent2' / '.runtime' / 'station-secret.txt')
AGENT2 = 'http://127.0.0.1:8766'
OPENER = build_opener(ProxyHandler({}))
PAGES = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
         '/style.css': ('style.css', 'text/css; charset=utf-8')}


def agent2(method, path, body=None):
    if not SECRET.is_file():
        return 503, {'error': 'Chưa có khóa trạm. Bật Agent 2 một lần để tạo khóa trạm.'}
    data = json.dumps(body or {}).encode() if method == 'POST' else None
    headers = {'X-Station-Token': SECRET.read_text().strip()}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with OPENER.open(Request(AGENT2 + path, data=data, method=method, headers=headers), timeout=60) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {'error': 'Agent 2 trả lỗi.'}
    except (URLError, OSError):
        return 503, {'error': 'Không kết nối được backend Agent 2 (cổng 8766). Bật web chung trước.'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, mime='application/json; charset=utf-8'):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in PAGES:
            name, mime = PAGES[self.path]
            return self.send(200, (ROOT / name).read_bytes(), mime)
        if self.path == '/api/status':
            return self.send(*agent2('GET', '/api/v1/station/status'))
        self.send(404, {'error': 'Không có trang này.'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(length) or b'{}') if 0 < length < 65536 else {}
        if self.path == '/api/run':
            return self.send(*agent2('POST', '/api/v1/station/run', {'rounds': int(body.get('rounds') or 2)}))
        if self.path == '/api/job':
            return self.send(*agent2('POST', '/api/v1/station/job', {'run_id': str(body.get('run_id') or '')}))
        self.send(404, {'error': 'Không có thao tác này.'})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8890)
    a = p.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'Trạm huấn luyện: http://127.0.0.1:{a.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
