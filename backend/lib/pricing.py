"""Server-side pricing. All amounts are integer euro cents, TTC (VAT included) — the browser never
supplies a price. VAT is derived from the TTC total with the platform rate (basis points, 2000 = 20 %)."""

import uuid

PAPER_SIZES = ["A4", "A3", "A5", "Letter", "Legal"]
PAPER_LABELS = {"A4": "A4", "A3": "A3", "A5": "A5", "Letter": "Lettre US", "Legal": "Légal US"}
SERVICE_CATEGORIES = {"typing": "Saisie & mise en page", "binding": "Reliure", "lamination": "Plastification", "custom": "Autre service"}
UNIT_LABELS = {"page": "page", "unit": "unité", "document": "document"}

# Stage-1 defaults, kept to recognise shops whose prices were never edited (see migrations).
LEGACY_DEFAULT_PRINT = {
    "A4": {"bw": 15, "color": 60}, "A3": {"bw": 30, "color": 120}, "A5": {"bw": 10, "color": 40},
    "Letter": {"bw": 15, "color": 60}, "Legal": {"bw": 20, "color": 80},
}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def example_services() -> list[dict]:
    """Editable example catalogue (requested sample prices)."""
    return [
        {"id": new_id(), "name": "Saisie de document", "category": "typing", "unit": "page", "price_cents": 300,
         "price_from": False, "description": "Frappe et mise en page d'un document manuscrit ou papier", "active": True},
        {"id": new_id(), "name": "Plastification A4", "category": "lamination", "unit": "unit", "price_cents": 200,
         "price_from": False, "description": "Pochette 125 microns", "active": True},
        {"id": new_id(), "name": "Reliure", "category": "binding", "unit": "document", "price_cents": 200,
         "price_from": True, "description": "Reliure spirale, tarif de base jusqu'à 50 feuilles", "active": True},
    ]


def default_pricing() -> dict:
    return {
        "print": {
            "A4": {"bw": 10, "color": 50, "active": True},
            "A3": {"bw": 25, "color": 100, "active": True},
            "A5": {"bw": 10, "color": 40, "active": False},
            "Letter": {"bw": 15, "color": 60, "active": False},
            "Legal": {"bw": 20, "color": 80, "active": False},
        },
        "duplex_discount_pct": 10,
        "photocopy": {"bw": 10, "color": 50, "active": True},
        "scan_cents": 20,
        "min_order_cents": 0,
        "services": example_services(),
        "rules": [],
        "discounts": [],
    }


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """'1-3, 5' -> [1,2,3,5]. Empty -> all pages. Raises ValueError with a French message."""
    spec = (spec or "").replace(" ", "")
    if not spec:
        return list(range(1, page_count + 1))
    pages: list[int] = []
    for part in spec.split(","):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"Plage de pages invalide : « {part} »")
            start, end = int(a), int(b)
            if start > end:
                raise ValueError(f"Plage de pages inversée : « {part} »")
            pages.extend(range(start, end + 1))
        else:
            if not part.isdigit():
                raise ValueError(f"Numéro de page invalide : « {part} »")
            pages.append(int(part))
    if not pages:
        raise ValueError("Aucune page sélectionnée")
    if min(pages) < 1 or max(pages) > page_count:
        raise ValueError(f"Pages hors limites (le document contient {page_count} page(s))")
    return sorted(set(pages))


def _round(x: float) -> int:
    return int(x + 0.5)


def _line(kind: str, label: str, qty: int, unit: int, subtotal: int, sheets: int = 0, **extra) -> dict:
    return {"kind": kind, "label": label, "document_id": extra.get("document_id"), "filename": extra.get("filename"),
            "options": extra.get("options"), "pages": qty, "copies": extra.get("copies", 1), "sheets": sheets,
            "unit_cents": unit, "subtotal_cents": subtotal}


def price_print(pricing: dict, filename: str, document_id: str, page_count: int, opts: dict) -> dict:
    size = pricing["print"][opts["paper_size"]]
    if not size.get("active", True):
        raise ValueError(f"Le format {PAPER_LABELS[opts['paper_size']]} n'est pas proposé par cette boutique")
    pages = parse_page_range(opts.get("page_range", ""), page_count)
    n = len(pages)
    copies = opts["copies"]
    unit = size[opts["color"]]
    gross = n * copies * unit
    if opts["duplex"] and n > 1:
        sheets = ((n + 1) // 2) * copies
        subtotal = _round(gross * (100 - pricing["duplex_discount_pct"]) / 100)
    else:
        sheets = n * copies
        subtotal = gross
    color_label = "Couleur" if opts["color"] == "color" else "N&B"
    duplex_label = "Recto-verso" if opts["duplex"] else "Recto"
    return _line("print", f"Impression {PAPER_LABELS[opts['paper_size']]} {color_label} · {duplex_label}", n, unit, subtotal,
                 sheets=sheets, document_id=document_id, filename=filename, options=opts, copies=copies)


def price_services(pricing: dict, services: dict) -> list[dict]:
    lines = []
    photocopy = pricing["photocopy"]
    for key, color, label in (("photocopy_bw", "bw", "Photocopie N&B"), ("photocopy_color", "color", "Photocopie couleur")):
        qty = services.get(key, 0)
        if qty:
            if not photocopy.get("active", True):
                raise ValueError("La photocopie n'est pas proposée par cette boutique")
            unit = photocopy[color]
            lines.append(_line("photocopy", label, qty, unit, unit * qty, sheets=qty))
    qty = services.get("scan_pages", 0)
    if qty:
        unit = pricing["scan_cents"]
        lines.append(_line("scan", "Numérisation (scan)", qty, unit, unit * qty))
    return lines


def price_extras(pricing: dict, extras: list[dict]) -> list[dict]:
    catalog = {s["id"]: s for s in pricing.get("services", [])}
    lines = []
    for extra in extras:
        svc = catalog.get(extra["service_id"])
        if not svc or not svc.get("active", True):
            raise ValueError("Service inconnu ou désactivé — rechargez la page")
        qty = extra["quantity"]
        unit_label = UNIT_LABELS.get(svc["unit"], "unité")
        label = f"{svc['name']} ({qty} {unit_label}{'s' if qty > 1 else ''})"
        lines.append(_line("service", label, qty, svc["price_cents"], svc["price_cents"] * qty))
    return lines


def _discount_amount(d: dict, base: int) -> int:
    return min(base, _round(base * d["value"] / 100)) if d["kind"] == "percent" else min(base, d["value"])


def finalize(pricing: dict, lines: list[dict], promo_code: str | None, vat_rate_bp: int) -> dict:
    """Apply volume rule, one shop discount (the most advantageous of automatic + promo code), the
    minimum charge, then split VAT. Returns the full breakdown."""
    out = list(lines)
    subtotal = sum(line["subtotal_cents"] for line in lines)
    print_pages = sum(line["pages"] * line["copies"] for line in lines if line["kind"] == "print")
    print_total = sum(line["subtotal_cents"] for line in lines if line["kind"] == "print")

    rules = [r for r in pricing.get("rules", []) if r.get("active", True) and print_pages >= r["min_pages"]]
    if rules and print_total > 0:
        best = max(rules, key=lambda r: r["discount_pct"])
        amount = _round(print_total * best["discount_pct"] / 100)
        out.append(_line("discount", f"{best['name']} (−{best['discount_pct']} % sur l'impression)", 1, -amount, -amount))

    running = sum(line["subtotal_cents"] for line in out)
    promo_error = None
    code = (promo_code or "").strip().upper() or None
    candidates = [d for d in pricing.get("discounts", []) if d.get("active", True) and not d.get("code")]
    if code:
        match = next((d for d in pricing.get("discounts", []) if d.get("active", True) and d.get("code") == code), None)
        if not match:
            promo_error = "Code promo inconnu ou expiré"
        elif running < match.get("min_order_cents", 0):
            promo_error = f"Code valable dès {match['min_order_cents'] / 100:.2f} € d'achat".replace(".", ",")
        else:
            candidates.append(match)
    candidates = [d for d in candidates if running >= d.get("min_order_cents", 0)]
    applied_code = None
    if candidates and running > 0:
        best_d = max(candidates, key=lambda d: _discount_amount(d, running))
        amount = _discount_amount(best_d, running)
        if amount > 0:
            suffix = f" −{best_d['value']} %" if best_d["kind"] == "percent" else ""
            out.append(_line("discount", f"Remise : {best_d['name']}{suffix}", 1, -amount, -amount))
            applied_code = best_d.get("code")
            if code and applied_code != code and not promo_error:
                promo_error = "Une remise plus avantageuse est déjà appliquée"

    total = sum(line["subtotal_cents"] for line in out)
    minimum = pricing.get("min_order_cents", 0)
    has_items = any(line["kind"] not in ("discount", "minimum") for line in out)
    if has_items and total < minimum:
        diff = minimum - total
        out.append(_line("minimum", f"Complément minimum de commande ({minimum / 100:.2f} €)".replace(".", ","), 1, diff, diff))
        total = minimum
    total_ht = _round(total * 10000 / (10000 + vat_rate_bp))
    return {
        "lines": out, "subtotal_cents": subtotal,
        "discount_cents": -sum(line["subtotal_cents"] for line in out if line["kind"] == "discount"),
        "total_cents": total, "total_ht_cents": total_ht, "vat_cents": total - total_ht, "vat_rate_bp": vat_rate_bp,
        "promo_code_applied": applied_code, "promo_error": promo_error, "currency": "EUR",
    }


def ht_from_ttc(ttc: int, vat_rate_bp: int) -> int:
    return _round(ttc * 10000 / (10000 + vat_rate_bp))


def public_pricing(pricing: dict, vat_rate_bp: int) -> dict:
    """Customer-facing view: inactive items hidden, promo codes never exposed."""
    return {
        "print": pricing["print"],
        "duplex_discount_pct": pricing["duplex_discount_pct"],
        "photocopy": pricing["photocopy"],
        "scan_cents": pricing["scan_cents"],
        "min_order_cents": pricing.get("min_order_cents", 0),
        "services": [s for s in pricing.get("services", []) if s.get("active", True)],
        "rules": [r for r in pricing.get("rules", []) if r.get("active", True)],
        "auto_discounts": [{"name": d["name"], "kind": d["kind"], "value": d["value"], "min_order_cents": d.get("min_order_cents", 0)}
                           for d in pricing.get("discounts", []) if d.get("active", True) and not d.get("code")],
        "has_promo_codes": any(d.get("active", True) and d.get("code") for d in pricing.get("discounts", [])),
        "vat_rate_bp": vat_rate_bp,
    }
