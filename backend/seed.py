"""Idempotent seed: super-admin + two demo organizations (for tenant-isolation testing).
Run: cd /app/backend && python seed.py"""

import asyncio
import uuid
from datetime import timedelta

from lib.authz import now_utc
from lib.db import db, ensure_indexes
from lib.pricing import default_pricing
from lib.security import hash_password

ACCOUNTS = [
    # email, password, name, platform_role
    ("printdrop35@gmail.com", "Admin2026!", "Super Admin PrintDrop", "superadmin"),
    ("proprio@bastille.fr", "Bastille2026!", "Camille Martin", None),
    ("employe@bastille.fr", "Employe2026!", "Lucas Bernard", None),
    ("proprio@copylyon.fr", "Lyon2026!", "Sophie Durand", None),
]

ORGS = [
    # org name, owner email, shop name, city, address, slug, staff
    ("CyberCafé Bastille SARL", "proprio@bastille.fr", "CyberCafé Bastille", "Paris", "12 rue de la Roquette, 75011 Paris",
     "cybercafe-bastille", [("employe@bastille.fr", "operator")]),
    ("CopyPrint Lyon", "proprio@copylyon.fr", "CopyPrint Bellecour", "Lyon", "4 place Bellecour, 69002 Lyon",
     "copyprint-bellecour", []),
]


async def upsert_user(email: str, password: str, name: str, platform_role: str | None) -> str:
    existing = await db.users.find_one({"email": email})
    if existing:
        await db.users.update_one({"email": email}, {"$set": {
            "password_hash": hash_password(password), "active": True, "platform_role": platform_role}})
        return existing["id"]
    uid = str(uuid.uuid4())
    await db.users.insert_one({"id": uid, "email": email, "name": name, "password_hash": hash_password(password),
                               "platform_role": platform_role, "active": True, "created_at": now_utc()})
    return uid


async def main() -> None:
    await ensure_indexes()
    ids = {email: await upsert_user(email, pw, name, role) for email, pw, name, role in ACCOUNTS}
    await db.login_attempts.delete_many({})
    # Former placeholder super-admin replaced by the real platform owner account.
    await db.users.update_one({"email": "admin@printdrop.fr"}, {"$set": {"active": False, "platform_role": None}})
    for org_name, owner_email, shop_name, city, address, slug, staff in ORGS:
        owner_id = ids[owner_email]
        org = await db.organizations.find_one({"owner_id": owner_id})
        if not org:
            org = {"id": str(uuid.uuid4()), "name": org_name, "status": "active", "plan": "starter",
                   "owner_id": owner_id, "created_at": now_utc()}
            await db.organizations.insert_one(dict(org))
        else:
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"status": "active"}})
        # Demo owners use fictitious addresses: no nightly report e-mail for them.
        await db.organizations.update_one({"id": org["id"]}, {"$set": {"report_email": False, "demo": True}})
        await db.organizations.update_one({"id": org["id"], "subscription.granted_by_admin": {"$ne": True}}, {"$set": {
            "plan": "pro", "subscription": {"plan_code": "pro", "period": "monthly", "status": "active", "granted_by_admin": True,
                                             "current_period_end": now_utc() + timedelta(days=365), "trial_ends_at": None}}})
        for email, role in [(owner_email, "owner"), *staff]:
            if not await db.memberships.find_one({"user_id": ids[email]}):
                await db.memberships.insert_one({"id": str(uuid.uuid4()), "org_id": org["id"], "user_id": ids[email],
                                                 "role": role, "active": True, "created_at": now_utc()})
            else:
                await db.memberships.update_one({"user_id": ids[email]}, {"$set": {"active": True, "role": role}})
        if not await db.shops.find_one({"slug": slug}):
            await db.shops.insert_one({"id": str(uuid.uuid4()), "org_id": org["id"], "slug": slug, "name": shop_name,
                                       "city": city, "address": address, "accepting_orders": True,
                                       "pricing": default_pricing(), "created_at": now_utc()})
        else:
            await db.shops.update_one({"slug": slug}, {"$set": {"accepting_orders": True}})
    print("Seed OK")


if __name__ == "__main__":
    asyncio.run(main())
