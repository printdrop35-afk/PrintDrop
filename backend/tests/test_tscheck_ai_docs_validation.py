"""AI document generator (customer portal) — endpoint validation, no LLM calls here.

Covers acceptance criteria:
- templates list: 12 templates across 3 categories + ProDocOnline catalogue link.
- finalize with an unknown template code -> 404.
- generate with a missing required field -> 422 (does not touch the LLM: validation runs first).
- finalize with a valid template -> DocumentUploadOut usable as an item in /quote (same shop pricing flow).
"""

SLUG = "cybercafe-bastille"


def test_templates_catalogue_12_in_3_categories(client):
    r = client.get(f"/public/shops/{SLUG}/ai-docs/templates")
    assert r.status_code == 200, r.text
    body = r.json()
    templates = body["templates"]
    assert len(templates) == 12, f"expected 12 templates, got {len(templates)}: {[t['code'] for t in templates]}"
    categories = {t["category"] for t in templates}
    assert categories == {"Documents personnels", "Documents professionnels", "Documents administratifs"}, categories
    assert body["catalogue_url"] == "https://prodoconline.com/documents"


def test_finalize_unknown_template_is_404(client):
    r = client.post(f"/public/shops/{SLUG}/ai-docs/finalize", json={
        "template": "tscheck-unknown-template-code", "title": "x", "body": "Corps du document de test.",
    })
    assert r.status_code == 404, r.text
    assert "introuvable" in r.json()["detail"].lower()


def test_generate_missing_required_field_is_422(client):
    # "cv" template requires full_name (NAME field) among others — send an empty values dict.
    r = client.post(f"/public/shops/{SLUG}/ai-docs/generate", json={"template": "cv", "values": {}})
    assert r.status_code == 422, r.text
    assert "requis" in r.json()["detail"].lower() or "Champ requis" in r.json()["detail"]


def test_finalize_returns_document_usable_in_quote(client):
    body_text = "Ceci est un corps de document tscheck-aidoc généré pour test de finalisation et devis."
    r = client.post(f"/public/shops/{SLUG}/ai-docs/finalize", json={
        "template": "certificate", "title": "tscheck-aidoc-attestation", "body": body_text,
    })
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["kind"] == "pdf"
    assert doc["page_count"] >= 1
    assert doc["id"] and doc["upload_token"]

    q = client.post(f"/public/shops/{SLUG}/ai-docs/finalize".replace("/ai-docs/finalize", "/quote"), json={
        "items": [{
            "document_id": doc["id"], "upload_token": doc["upload_token"],
            "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": ""},
        }],
        "services": {}, "extras": [], "promo_code": None,
    })
    assert q.status_code == 200, q.text
    quote = q.json()
    assert quote["total_cents"] > 0
    assert any(line.get("document_id") == doc["id"] for line in quote["lines"]), quote["lines"]
