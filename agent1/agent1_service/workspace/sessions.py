"""Revocable browser sessions; API credentials stay in the server process."""

import hashlib
import secrets
import threading
import time

from fastapi import HTTPException


class WorkspaceSessions:
    def __init__(self, company, ttl=8 * 60 * 60, clock=None):
        self.company = company
        self.ttl = ttl
        self.clock = clock or time.monotonic
        self.rows = {}
        self.lock = threading.RLock()

    def cookie_name(self, request):
        # Cookies share a host across ports. Each company/service needs its own.
        scope = f"{self.company}|{request.url.netloc}"
        return "agent1_session_" + hashlib.sha256(scope.encode()).hexdigest()[:16]

    def check_origin(self, request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Phiên làm việc chỉ nhận yêu cầu từ trang Agent 1.")

    def credential(self, request):
        if request is None:
            raise HTTPException(401, "Cần kết nối doanh nghiệp.")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            self.check_origin(request)
        value = request.cookies.get(self.cookie_name(request), "")
        digest = hashlib.sha256(value.encode()).hexdigest()
        with self.lock:
            row = self.rows.get(digest)
            if not row or row[0] <= self.clock():
                self.rows.pop(digest, None)
                raise HTTPException(401, "Phiên kết nối đã hết hạn. Kết nối lại doanh nghiệp.")
            return row[1]

    def issue(self, request, response, credential):
        self.check_origin(request)
        self.revoke(request)
        value = secrets.token_urlsafe(32)
        with self.lock:
            now = self.clock()
            self.rows = {key: row for key, row in self.rows.items() if row[0] > now}
            if len(self.rows) >= 256:
                raise HTTPException(429, "Quá nhiều phiên kết nối. Đóng các phiên cũ rồi thử lại.")
            self.rows[hashlib.sha256(value.encode()).hexdigest()] = (now + self.ttl, credential)
        response.set_cookie(self.cookie_name(request), value, max_age=self.ttl,
                            httponly=True, secure=request.url.scheme == "https",
                            samesite="strict", path="/v1")

    def revoke(self, request, response=None):
        self.check_origin(request)
        value = request.cookies.get(self.cookie_name(request), "")
        with self.lock:
            self.rows.pop(hashlib.sha256(value.encode()).hexdigest(), None)
        if response is not None:
            response.delete_cookie(self.cookie_name(request), path="/v1",
                                   httponly=True, samesite="strict",
                                   secure=request.url.scheme == "https")
