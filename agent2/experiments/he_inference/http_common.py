"""Bounded loopback HTTP transport shared by the two experimental services."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from urllib.parse import urlsplit

from .protocol import HEUnavailable, MAX_PACKET, _object, canonical


class ServiceError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, HEUnavailable, RecursionError) as exc:
        raise ServiceError(400, 'INVALID_JSON') from exc


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, handler):
        self._request_slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', port), handler)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'HE-Local-Experiment'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # Never log URLs, credentials, bodies, keys or source identifiers.

    def guard(self):
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1 or hosts[0] not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            raise ServiceError(403, 'HOST_DENIED')
        if self.headers.get_all('Origin', []):
            raise ServiceError(403, 'BROWSER_ORIGIN_DENIED')
        if '?' in self.path or '#' in self.path:
            raise ServiceError(400, 'QUERY_NOT_SUPPORTED')

    def body(self, limit=MAX_PACKET):
        if self.headers.get_all('Transfer-Encoding', []):
            raise ServiceError(400, 'TRANSFER_ENCODING_DENIED')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise ServiceError(411, 'CONTENT_LENGTH_REQUIRED')
        size = int(lengths[0])
        if not 0 < size <= limit:
            raise ServiceError(413, 'BODY_LIMIT')
        content = self.headers.get_all('Content-Type', [])
        if len(content) != 1 or content[0].split(';')[0].strip().lower() != 'application/json':
            raise ServiceError(415, 'JSON_REQUIRED')
        try:
            raw = self.rfile.read(size)
        except (OSError, socket.timeout) as exc:
            raise ServiceError(408, 'BODY_TIMEOUT') from exc
        if len(raw) != size:
            raise ServiceError(400, 'BODY_INCOMPLETE')
        return decode(raw)

    def reply(self, status, value):
        packed = canonical(value)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(packed)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(packed)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A completed ciphertext job remains retrievable on retry.

    def failure(self, error):
        self.reply(error.status, dict(status='unavailable', reason=dict(code=error.code)))

    def do_OPTIONS(self):
        self.failure(ServiceError(405, 'METHOD_NOT_ALLOWED'))

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS


def worker_address(url):
    value = urlsplit(url)
    if (value.scheme != 'http' or value.hostname not in ('127.0.0.1', 'localhost')
            or not value.port or value.path not in ('', '/') or value.query or value.fragment or value.username):
        raise ServiceError(503, 'WORKER_URL_REQUIRES_LOOPBACK')
    return value.hostname, value.port


def post(url, path, payload, *, timeout=20):
    host, port = worker_address(url)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request('POST', path, canonical(payload), {'Content-Type': 'application/json'})
        result = connection.getresponse()
        raw = result.read(MAX_PACKET + 1)
        if len(raw) > MAX_PACKET:
            raise ServiceError(502, 'WORKER_RESPONSE_LIMIT')
        try:
            value = decode(raw)
        except ServiceError as exc:
            raise ServiceError(502, 'WORKER_RESPONSE_INVALID') from exc
        if result.status != 200:
            code = value.get('reason', {}).get('code', 'WORKER_UNAVAILABLE') if isinstance(value, dict) else 'WORKER_UNAVAILABLE'
            raise ServiceError(503 if result.status in (409, 503) else 502, code)
        return value
    except (http.client.HTTPException, OSError) as exc:
        raise ServiceError(503, 'WORKER_CONNECTION_UNAVAILABLE') from exc
    finally:
        connection.close()
