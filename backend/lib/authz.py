"""Authorization: server-derived principal, role permissions, tenant-scoped repository, audit log.

Two separate role scopes:
- platform_role (on the user): "superadmin" — platform administration only, never tenant data.
- tenant_role (on the membership): owner | manager | operator — scoped to one organization.
The principal is re-read from the database on every request, so a revoked membership or a
suspended organization stops working immediately (not at token expiry).
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from lib.db import db
from lib.security import COOKIE_NAME, decode_session_token

ROLE_PERMS: dict[str, set[str]] = {
    "owner": {
        "orders:read", "orders:update", "orders:pay", "documents:read",
        "shop:read", "shop:edit", "shop:create", "pricing:edit",
        "staff:read", "staff:manage", "audit:read", "devices:read", "devices:manage", "jobs:reprint",
        "reports:read", "reports:manage", "paper:manage",
    },
    "manager": {
        "orders:read", "orders:update", "orders:pay", "documents:read",
        "shop:read", "shop:edit", "pricing:edit", "staff:read", "audit:read", "devices:read", "devices:manage", "jobs:reprint",
        "reports:read", "paper:manage",
    },
    "operator": {"orders:read", "orders:update", "orders:pay", "documents:read", "shop:read", "devices:read", "jobs:reprint", "paper:manage"},
}
ROLE_RANK = {"operator": 1, "manager": 2, "owner": 3}
PLATFORM_PERMS: dict[str, set[str]] = {"superadmin": {"platform:read", "platform:manage"}}


class Principal(BaseModel):
    user_id: str
    email: str
    name: str
    platform_role: str | None = None
    org_id: str | None = None
    org_status: str | None = None
    tenant_role: str | None = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def audit(
    action: str,
    *,
    principal: Principal | None = None,
    org_id: str | None = None,
    resource_type: str = "",
    resource_id: str = "",
    outcome: str = "allow",
    details: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "at": now_utc(),
        "org_id": org_id if org_id is not None else (principal.org_id if principal else None),
        "actor_id": principal.user_id if principal else None,
        "actor_email": principal.email if principal else (actor or "client-public"),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
        "details": details or {},
    })


async def load_principal(user_id: str) -> Principal | None:
    user = await db.users.find_one({"id": user_id, "active": True}, {"_id": 0})
    if not user:
        return None
    p = Principal(user_id=user["id"], email=user["email"], name=user["name"], platform_role=user.get("platform_role"))
    membership = await db.memberships.find_one({"user_id": user["id"], "active": True}, {"_id": 0})
    if membership:
        org = await db.organizations.find_one({"id": membership["org_id"]}, {"_id": 0})
        if org:
            p.org_id = org["id"]
            p.org_status = org["status"]
            p.tenant_role = membership["role"]
    return p


async def get_principal(request: Request) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_session_token(token) if token else None
    principal = await load_principal(user_id) if user_id else None
    if not principal:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return principal


def require_tenant(perm: str):
    async def dep(p: Principal = Depends(get_principal)) -> Principal:
        if not p.org_id or not p.tenant_role:
            raise HTTPException(status_code=403, detail="Accès réservé aux membres d'une entreprise")
        if p.org_status != "active":
            raise HTTPException(status_code=403, detail="Organisation suspendue — contactez PrintDrop")
        if perm not in ROLE_PERMS.get(p.tenant_role, set()):
            await audit("authz.denied", principal=p, outcome="deny", details={"perm": perm})
            raise HTTPException(status_code=403, detail="Permission insuffisante")
        return p
    return dep


def require_platform(perm: str):
    async def dep(p: Principal = Depends(get_principal)) -> Principal:
        if perm not in PLATFORM_PERMS.get(p.platform_role or "", set()):
            await audit("authz.denied", principal=p, org_id=None, outcome="deny", details={"perm": perm})
            raise HTTPException(status_code=403, detail="Accès réservé au super-administrateur")
        return p
    return dep


class TenantRepo:
    """Every query goes through here: org_id is injected into every filter, insert and pipeline."""

    def __init__(self, org_id: str):
        self.org_id = org_id

    def _f(self, f: dict | None) -> dict:
        return {**(f or {}), "org_id": self.org_id}

    async def find(self, coll: str, f: dict | None = None, sort: list | None = None, limit: int = 500) -> list[dict]:
        cur = db[coll].find(self._f(f), {"_id": 0})
        if sort:
            cur = cur.sort(sort)
        return await cur.to_list(limit)

    async def find_one(self, coll: str, f: dict) -> dict | None:
        return await db[coll].find_one(self._f(f), {"_id": 0})

    async def insert(self, coll: str, doc: dict) -> dict:
        doc = {**doc, "org_id": self.org_id}
        await db[coll].insert_one(dict(doc))
        return doc

    async def update_one(self, coll: str, f: dict, update: dict) -> int:
        res = await db[coll].update_one(self._f(f), update)
        return res.matched_count

    async def update_many(self, coll: str, f: dict, update: dict) -> int:
        res = await db[coll].update_many(self._f(f), update)
        return res.modified_count

    async def count(self, coll: str, f: dict | None = None) -> int:
        return await db[coll].count_documents(self._f(f))

    async def aggregate(self, coll: str, pipeline: list[dict]) -> list[dict]:
        for stage in pipeline:
            if any(k in stage for k in ("$lookup", "$unionWith", "$graphLookup")):
                raise ValueError("Cross-collection stages are not allowed in tenant pipelines")
        return await db[coll].aggregate([{"$match": {"org_id": self.org_id}}, *pipeline]).to_list(1000)


def tenant_repo(p: Principal) -> TenantRepo:
    assert p.org_id
    return TenantRepo(p.org_id)


def request_origin(request: Request) -> str:
    """Public origin of the current request (behind the ingress), used for links in notifications."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"
