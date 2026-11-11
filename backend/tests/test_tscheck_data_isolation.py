"""Strict per-organization data isolation across tenant and platform (super-admin) endpoints.

Owner A (cybercafe-bastille / org d19437ef-...) must never reach Owner B's (copyprint-bellecour)
shop/orders, nor the super-admin-only org detail route; a super-admin's view of org B must not leak
org A's documents, and a document link request must be scoped to the document's OWN org id.
"""

import httpx

ORG_A = "d19437ef-cf22-4318-bbb8-e243a95f4316"
OWNER_A = ("proprio@bastille.fr", "Bastille2026!")
OWNER_B = ("proprio@copylyon.fr", "Lyon2026!")
SUPERADMIN = ("printdrop35@gmail.com", "Admin2026!")


def _login(c: httpx.Client, email: str, password: str) -> dict:
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_a_cannot_reach_owner_b_shop_orders_or_admin_org_details(client):
    with httpx.Client(base_url=client.base_url, timeout=30.0) as a, httpx.Client(base_url=client.base_url, timeout=30.0) as b:
        _login(a, *OWNER_A)
        _login(b, *OWNER_B)
        shop_b = b.get("/shops").json()[0]
        org_b_id = shop_b["org_id"]

        # Owner A tries Owner B's shop orders -> 404 (tenant_repo scopes by org_id, shop not found for A)
        r = a.get(f"/shops/{shop_b['id']}/orders")
        assert r.status_code == 404, r.text

        # Owner A tries the super-admin-only organization detail route -> 403 (not platform role)
        r = a.get(f"/admin/organizations/{org_b_id}/details")
        assert r.status_code == 403, r.text
        # NOTE: deliberately no /auth/logout here — logout revokes ALL sessions of these shared
        # seeded accounts (spec_deviations), which would race with other test files/workers running
        # concurrently (xdist) as the same Owner A / Owner B accounts.


def test_superadmin_org_b_detail_excludes_org_a_data_and_doc_link_is_org_scoped(client):
    with httpx.Client(base_url=client.base_url, timeout=30.0) as sa, httpx.Client(base_url=client.base_url, timeout=30.0) as a, \
         httpx.Client(base_url=client.base_url, timeout=30.0) as b:
        _login(sa, *SUPERADMIN)
        _login(a, *OWNER_A)
        _login(b, *OWNER_B)
        org_b_id = b.get("/shops").json()[0]["org_id"]

        details_a = sa.get(f"/admin/organizations/{ORG_A}/details")
        assert details_a.status_code == 200, details_a.text
        doc_ids_a = {d["id"] for d in details_a.json()["documents"]}

        details_b = sa.get(f"/admin/organizations/{org_b_id}/details")
        assert details_b.status_code == 200, details_b.text
        body_b = details_b.json()
        order_ids_b = {o["id"] for o in body_b["orders"]}  # order ids (uuid) are globally unique, unlike the 4-digit pickup codes
        doc_ids_b = {d["id"] for d in body_b["documents"]}
        assert doc_ids_a.isdisjoint(doc_ids_b), f"org A documents leaked into org B detail: {doc_ids_a & doc_ids_b}"

        order_ids_a = {o["id"] for o in details_a.json()["orders"]}
        assert order_ids_a.isdisjoint(order_ids_b), f"org A orders leaked into org B detail: {order_ids_a & order_ids_b}"

        # A document that belongs to org A, requested through org B's id -> 404 (scoped by org_id, not just doc_id)
        if doc_ids_a:
            any_doc_a = next(iter(doc_ids_a))
            r = sa.post(f"/admin/organizations/{org_b_id}/documents/{any_doc_a}/link")
            assert r.status_code == 404, r.text
        # NOTE: no /auth/logout for OWNER_A / OWNER_B here either, for the same cross-worker reason above.
