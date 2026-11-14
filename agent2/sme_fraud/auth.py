"""Backend authorization adapter for validation; no login UI or user database.

Trusted administrators/identity services provision hashed credentials and explicit
company memberships. Browser-supplied roles, tenants and permissions are ignored.
Policy is read on every request, so membership revocation takes effect immediately.
"""
from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import re
from datetime import datetime, timezone

from finance_input import AccessScope
from finance_input.json_io import loads
from finance_input.validation import stamp

ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
PERMISSIONS = {"data.import", "evidence.verify", "model.fit"}


class AuthError(Exception):
    def __init__(self, status, code, message, action):
        super().__init__(message)
        self.status, self.code, self.message, self.action = status, code, message, action


def _denied(status=401):
    if status == 401:
        return AuthError(401, "AUTH_REQUIRED", "Chưa có thông tin xác thực hợp lệ hoặc thông tin đã hết hạn.",
                         "Dùng credential còn hiệu lực do backend/identity service cấp; không gửi vai trò trong dữ liệu nhập.")
    return AuthError(403, "ACCESS_DENIED", "Không có quyền nhập dữ liệu cho doanh nghiệp này.",
                     "Yêu cầu quản lý cấp membership active và quyền data.import đúng doanh nghiệp.")


def _config_error():
    return AuthError(503, "AUTH_POLICY_UNAVAILABLE", "Backend chưa có cấu hình quyền hợp lệ.",
                     "Người vận hành kiểm tra auth policy phía server; dữ liệu chưa được đọc hoặc lưu.")


def _identifier(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


@dataclass(frozen=True)
class Membership:
    company_id: str
    role: str
    status: str
    permissions: frozenset[str]


@dataclass(frozen=True)
class Principal:
    actor_id: str
    tenant_id: str
    token_sha256: str
    status: str
    expires_at: datetime
    memberships: tuple[Membership, ...]


def parse_policy(value):
    """Strict server configuration, deliberately not a client request DTO."""
    if not isinstance(value, dict) or set(value) != {"policy_version", "principals"}:
        raise ValueError("policy fields")
    if value["policy_version"] != "1.0.0" or not isinstance(value["principals"], list) or len(value["principals"]) > 256:
        raise ValueError("policy version/principals")
    principals = []; actors = set(); hashes = set()
    for row in value["principals"]:
        fields = {"actor_id", "tenant_id", "token_sha256", "status", "expires_at", "memberships"}
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("principal fields")
        if not _identifier(row["actor_id"]) or not _identifier(row["tenant_id"]):
            raise ValueError("principal identifier")
        digest = row["token_sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("credential hash")
        actor_key = (row["tenant_id"], row["actor_id"])
        if actor_key in actors or digest in hashes:
            raise ValueError("duplicate principal/credential")
        actors.add(actor_key); hashes.add(digest)
        if row["status"] not in {"active", "revoked"}:
            raise ValueError("principal status")
        if not isinstance(row["memberships"], list) or len(row["memberships"]) > 1024:
            raise ValueError("memberships")
        memberships = []; companies = set()
        for member in row["memberships"]:
            if not isinstance(member, dict) or set(member) != {"company_id", "role", "status", "permissions"}:
                raise ValueError("membership fields")
            if not _identifier(member["company_id"]) or member["company_id"] in companies:
                raise ValueError("membership company")
            if member["role"] not in {"accountant", "director"} or member["status"] not in {"active", "suspended", "revoked"}:
                raise ValueError("membership role/status")
            permissions = member["permissions"]
            if not isinstance(permissions, list) or not all(isinstance(p, str) and p in PERMISSIONS for p in permissions):
                raise ValueError("permissions")
            companies.add(member["company_id"])
            memberships.append(Membership(member["company_id"], member["role"], member["status"], frozenset(permissions)))
        principals.append(Principal(row["actor_id"], row["tenant_id"], digest, row["status"],
                                    stamp(row["expires_at"]), tuple(memberships)))
    return tuple(principals)


class FileAuthorizer:
    def __init__(self, path, clock=None):
        self.path = Path(path) if path else None
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def configured(self):
        return self.path is not None

    def _authorized_principal(self, authorization):
        if not isinstance(authorization, str) or len(authorization) > 4096:
            raise _denied()
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer" or len(parts[1]) < 32:
            raise _denied()
        if self.path is None:
            raise _denied()
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("policy limit")
            principals = parse_policy(loads(raw))
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
            raise _config_error() from None
        digest = hashlib.sha256(parts[1].encode("utf-8")).hexdigest()
        principal = None
        for candidate in principals:
            if hmac.compare_digest(digest, candidate.token_sha256):
                principal = candidate
        if principal is None or principal.status != "active" or principal.expires_at <= self.clock():
            raise _denied()
        return principal

    def describe(self, authorization):
        """Own active import memberships only; never credentials or policy internals."""
        principal = self._authorized_principal(authorization)
        return dict(actor_id=principal.actor_id, companies=[m.company_id for m in principal.memberships
                    if m.status == 'active' and 'data.import' in m.permissions])

    def _authorized_member(self, authorization, company_id):
        principal = self._authorized_principal(authorization)
        member = next((m for m in principal.memberships if m.company_id == company_id), None)
        if member is None or member.status != "active" or "data.import" not in member.permissions:
            raise _denied(403)
        return principal,member

    def authorize(self, authorization, company_id):
        principal,member=self._authorized_member(authorization,company_id)
        return AccessScope(principal.tenant_id, frozenset({company_id}), principal.actor_id, member.permissions)

    def authorize_director(self, authorization, company_id):
        """Technical analysis is a separate backend role check, not a client flag."""
        principal,member=self._authorized_member(authorization,company_id)
        if member.role!='director':
            raise AuthError(403,'TECHNICAL_VIEW_DENIED','Chưa có quyền xem chi tiết kỹ thuật phân tích.',
                'Dùng kết quả nghiệp vụ hoặc tài khoản quản lý có quyền đúng doanh nghiệp.')
        return AccessScope(principal.tenant_id,frozenset({company_id}),principal.actor_id,member.permissions)
