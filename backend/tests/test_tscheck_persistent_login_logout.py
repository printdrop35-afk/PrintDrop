"""Persistent login session (cookie max-age ~400 days, renewed by /auth/me) and explicit logout
revokes the session server-side so a replayed old cookie is rejected.

Uses a fresh tscheck- registered account (not a shared seeded one): logout revokes ALL sessions of
that account (spec_deviations), which would otherwise race with other test files/workers logged in
as the same shared seeded owner concurrently under xdist.
"""

import re
import uuid

import httpx

COOKIE_NAME = "pd_session"


def _register_tscheck_user(c: httpx.Client) -> str:
    suffix = uuid.uuid4().hex[:10]
    email = f"tscheck-login-{suffix}@example.com"
    r = c.post("/auth/register", json={
        "org_name": f"tscheck-org-{suffix}", "shop_name": f"tscheck-shop-{suffix}", "city": "Paris",
        "owner_name": "Tscheck Owner", "email": email, "password": "Tscheck2026!",
    })
    assert r.status_code == 200, r.text
    return email


def test_login_cookie_has_long_max_age_and_me_renews_it(client):
    with httpx.Client(base_url=client.base_url, timeout=30.0) as c:
        email = _register_tscheck_user(c)  # register() already logs the new account in (sets the cookie)
        me0 = c.get("/auth/me")
        assert me0.status_code == 200
        assert me0.json()["user"]["email"] == email

        r = c.post("/auth/login", json={"email": email, "password": "Tscheck2026!"})
        assert r.status_code == 200, r.text
        login_set_cookie = r.headers.get("set-cookie", "")
        assert COOKIE_NAME in login_set_cookie
        m = re.search(r"[Mm]ax-[Aa]ge=(\d+)", login_set_cookie)
        assert m, login_set_cookie
        max_age_days = int(m.group(1)) / 86400
        assert max_age_days > 300, f"expected ~400 day cookie, got {max_age_days:.0f} days"

        me = c.get("/auth/me")
        assert me.status_code == 200
        renew = me.headers.get("set-cookie", "")
        assert COOKIE_NAME in renew, "GET /auth/me should renew (reissue) the session cookie"


def test_logout_revokes_session_old_cookie_gets_401(client):
    with httpx.Client(base_url=client.base_url, timeout=30.0) as c:
        email = _register_tscheck_user(c)
        r = c.post("/auth/login", json={"email": email, "password": "Tscheck2026!"})
        assert r.status_code == 200, r.text
        old_cookie_value = c.cookies.get(COOKIE_NAME)
        assert old_cookie_value

        me_before = c.get("/auth/me")
        assert me_before.status_code == 200

        out = c.post("/auth/logout")
        assert out.status_code == 200, out.text

        # Replay the pre-logout cookie value explicitly: the server revoked the session, not just the browser's cookie jar.
        with httpx.Client(base_url=client.base_url, timeout=30.0, cookies={COOKIE_NAME: old_cookie_value}) as replay:
            me_after = replay.get("/auth/me")
            assert me_after.status_code == 401, me_after.text
