"""Plans now advertise printer-slot limits ("PRINTER 1/3/10") instead of shop counts, prices unchanged."""

EXPECTED = {
    "starter": ("PRINTER 1", 1900, 19000),
    "pro": ("PRINTER 3", 3900, 39000),
    "business": ("PRINTER 10", 7900, 79000),
}


def test_plans_feature_printer_slots_and_prices_unchanged(client):
    r = client.get("/public/plans")
    assert r.status_code == 200, r.text
    plans = {p["code"]: p for p in r.json()}
    assert set(EXPECTED) <= set(plans)
    for code, (feature0, monthly, yearly) in EXPECTED.items():
        p = plans[code]
        assert p["features"][0] == feature0, f"{code}: features[0]={p['features'][0]!r}"
        assert p["monthly_ht_cents"] == monthly
        assert p["yearly_ht_cents"] == yearly


def test_bastille_org_printer_plan_is_printer_3(client):
    """Owner A (seed_facts: plan pro) must be labelled PRINTER 3 wherever printer_plan is surfaced."""
    r = client.post("/auth/login", json={"email": "proprio@bastille.fr", "password": "Bastille2026!"})
    assert r.status_code == 200, r.text
    me = client.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    shops = body.get("shops") or []
    bastille = next((s for s in shops if s.get("slug") == "cybercafe-bastille"), None)
    assert bastille, body
    assert body.get("printer_plan") == "PRINTER 3", body.get("printer_plan")
    # NOTE: deliberately no /auth/logout here — logout revokes ALL sessions of this shared seeded
    # account (spec_deviations), which would race with other test files/workers also logged in as Owner A.
