"""Paper stock per shop and paper size. Usage = sheets of every non-cancelled order created since
the stock was last recorded (print lines by paper size; photocopies count as A4)."""

from lib.authz import TenantRepo
from lib.pricing import PAPER_SIZES

DEFAULT_ALERT_PCT = 80


async def paper_levels(org_id: str, shop: dict) -> list[dict]:
    repo = TenantRepo(org_id)
    stock: dict = shop.get("paper_stock") or {}
    alert_pct = shop.get("paper_alert_pct", DEFAULT_ALERT_PCT)
    levels = []
    for size in PAPER_SIZES:
        entry = stock.get(size)
        if not entry:
            continue
        rows = await repo.aggregate("orders", [
            {"$match": {"shop_id": shop["id"], "status": {"$ne": "cancelled"}, "created_at": {"$gte": entry["set_at"]}}},
            {"$unwind": "$lines"},
            {"$match": {"$or": [
                {"lines.kind": "print", "lines.options.paper_size": size},
                *([{"lines.kind": "photocopy"}] if size == "A4" else []),
            ]}},
            {"$group": {"_id": None, "sheets": {"$sum": "$lines.sheets"}}},
        ])
        used = rows[0]["sheets"] if rows else 0
        pct = round(used * 100 / entry["sheets"]) if entry["sheets"] else 100
        levels.append({
            "paper_size": size, "stock_sheets": entry["sheets"], "used_sheets": used,
            "remaining_sheets": max(entry["sheets"] - used, 0), "pct_used": min(pct, 100), "set_at": entry["set_at"],
            "level": "out" if used >= entry["sheets"] else ("low" if pct >= alert_pct else "ok"),
        })
    return levels
