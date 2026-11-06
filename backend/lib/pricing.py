"""Server-side pricing. All amounts are integer euro cents; the browser never supplies a price."""

PAPER_SIZES = ["A4", "A3", "A5", "Letter", "Legal"]
PAPER_LABELS = {"A4": "A4", "A3": "A3", "A5": "A5", "Letter": "Lettre US", "Legal": "Légal US"}


def default_pricing() -> dict:
    return {
        "print": {
            "A4": {"bw": 15, "color": 60},
            "A3": {"bw": 30, "color": 120},
            "A5": {"bw": 10, "color": 40},
            "Letter": {"bw": 15, "color": 60},
            "Legal": {"bw": 20, "color": 80},
        },
        "duplex_discount_pct": 10,
        "photocopy": {"bw": 10, "color": 50},
        "scan_cents": 20,
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


def price_print(pricing: dict, filename: str, document_id: str, page_count: int, opts: dict) -> dict:
    pages = parse_page_range(opts.get("page_range", ""), page_count)
    n = len(pages)
    copies = opts["copies"]
    unit = pricing["print"][opts["paper_size"]][opts["color"]]
    gross = n * copies * unit
    if opts["duplex"] and n > 1:
        sheets = ((n + 1) // 2) * copies
        subtotal = _round(gross * (100 - pricing["duplex_discount_pct"]) / 100)
    else:
        sheets = n * copies
        subtotal = gross
    color_label = "Couleur" if opts["color"] == "color" else "N&B"
    duplex_label = "Recto-verso" if opts["duplex"] else "Recto"
    return {
        "kind": "print",
        "label": f"Impression {PAPER_LABELS[opts['paper_size']]} {color_label} · {duplex_label}",
        "document_id": document_id,
        "filename": filename,
        "options": opts,
        "pages": n,
        "copies": copies,
        "sheets": sheets,
        "unit_cents": unit,
        "subtotal_cents": subtotal,
    }


def price_services(pricing: dict, services: dict) -> list[dict]:
    lines = []
    for key, color, label in (("photocopy_bw", "bw", "Photocopie N&B"), ("photocopy_color", "color", "Photocopie couleur")):
        qty = services.get(key, 0)
        if qty:
            unit = pricing["photocopy"][color]
            lines.append({"kind": "photocopy", "label": label, "document_id": None, "filename": None, "options": None,
                          "pages": qty, "copies": 1, "sheets": qty, "unit_cents": unit, "subtotal_cents": unit * qty})
    qty = services.get("scan_pages", 0)
    if qty:
        unit = pricing["scan_cents"]
        lines.append({"kind": "scan", "label": "Numérisation (scan)", "document_id": None, "filename": None, "options": None,
                      "pages": qty, "copies": 1, "sheets": 0, "unit_cents": unit, "subtotal_cents": unit * qty})
    return lines
