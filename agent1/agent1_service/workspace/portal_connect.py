"""Short-lived, one-use handoff from the portal to an independent Agent 1 tab."""

import hashlib
import secrets
import threading
import time

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class TicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1, max_length=64)


class TicketRedemption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=40, max_length=128)


class PortalTickets:
    def __init__(self, ttl=60, limit=128, clock=None):
        self.ttl = ttl
        self.limit = limit
        self.clock = clock or time.monotonic
        self._tickets = {}
        self._lock = threading.Lock()

    def issue(self, company, key):
        with self._lock:
            now = self.clock()
            self._tickets = {digest: row for digest, row in self._tickets.items() if row[0] > now}
            if len(self._tickets) >= self.limit:
                raise HTTPException(429, "Đang có quá nhiều yêu cầu mở tab. Thử lại sau một phút.")
            ticket = secrets.token_urlsafe(32)
            digest = hashlib.sha256(ticket.encode()).digest()
            self._tickets[digest] = (now + self.ttl, company, key)
            return dict(ticket=ticket, company=company, expires_in=self.ttl)

    def redeem(self, ticket, company):
        digest = hashlib.sha256(ticket.encode()).digest()
        with self._lock:
            row = self._tickets.pop(digest, None)
            if not row or row[0] <= self.clock() or row[1] != company:
                raise HTTPException(401, "Mã kết nối đã hết hạn hoặc đã dùng. Mở tab mới từ workspace tổng.")
            return row[2]


def install_portal_connect(app, router, authorize, firm_id):
    tickets = PortalTickets()
    app.state.portal_tickets = tickets

    @router.post("/portal-connect/tickets", status_code=201)
    def issue(body: TicketRequest, authorization: str | None = Header(None), firm=Depends(authorize)):
        if body.company != firm:
            raise HTTPException(409, "Doanh nghiệp đã đổi. Mở lại Agent 1 từ workspace tổng.")
        return tickets.issue(firm, authorization.removeprefix("Bearer "))

    @router.post("/portal-connect/redeem")
    def redeem(body: TicketRedemption, request: Request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Yêu cầu kết nối không đến từ trang Agent 1.")
        key = tickets.redeem(body.ticket, firm_id)
        authorize("Bearer " + key)
        return dict(company=firm_id, key=key)
