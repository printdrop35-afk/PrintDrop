# PrintDrop — SPEC (Stage 1)

Multi-tenant SaaS for print shops / cybercafés. French UI (i18n dictionary in frontend/src/i18n). EUR, amounts stored in cents.
Full architecture: /app/docs/ARCHITECTURE.md.

## Apps / routes
- Public landing `/`, login `/login`, register `/inscription` (creates org + first shop + owner).
- Customer portal (no account) `/s/:slug` — upload PDF/PNG/JPG, options (format A4/A3/A5/Letter/Legal, N&B/couleur, recto-verso, copies, page range), counter services (photocopies N&B/couleur, scan), live server quote, order → `/suivi/:code` (tracking requires code + phone).
- Dashboard `/dashboard` (orders + KPIs + detail sheet w/ status/payment/signed doc link), `/dashboard/tarifs`, `/dashboard/boutique` (settings + printable QR poster + new shop), `/dashboard/equipe`, `/dashboard/journal`.
- Super-admin `/superadmin` — stats, orgs list, suspend/reactivate, plan, platform audit.

## Roles
- platform_role superadmin (user field): /api/admin/* only, NO tenant data access (GET /api/shops → 403).
- tenant roles (membership): owner (all), manager (orders, pricing, shop edit, staff read, audit), operator (orders read/update/pay, docs, shop read).
- Cross-tenant ids → 404. Missing permission → 403. Suspended org → tenant routes 403, public portal 404.

## Business rules
- Prices computed server-side only; duplex discount % applied when duplex and >1 page.
- Status: pending→printing/ready/cancelled; printing→ready/pending/cancelled; ready→picked_up/printing/cancelled. picked_up requires paid.
- Payment Stage 1: counter only (cash / card_terminal) recorded by staff; online payment NOT implemented (no simulation).
- Upload token required to attach a doc; a doc attaches to one order only. Orphan uploads deleted after 24h (background task).
- Document files served only through /api/files/{id}?exp&sig (HMAC, 5 min).

## Seed (python backend/seed.py, idempotent)
- Shops: `cybercafe-bastille` (org CyberCafé Bastille SARL), `copyprint-bellecour` (org CopyPrint Lyon). Default pricing A4 N&B 0,15 €, A4 couleur 0,60 €, duplex -10 %, photocopie 0,10/0,50 €, scan 0,20 €.
- No seeded orders. Accounts in memory/test_credentials.md.

## Tests
backend/tests/test_stage1.py — auth, pricing, upload validation, token binding, tracking, tenant isolation, role limits, lifecycle, double-payment guard, signed links, super-admin scope, suspension.
