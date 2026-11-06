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

## Notifications ("commande prête")
- Triggered when an order becomes `ready` (staff click or agent auto-complete). Queued in `notification_jobs` (unique per order+event+channel → sent once), delivered by background worker (server.py job_worker, every 5 s, 3 retries).
- E-mail: Emergent managed Resend (EMERGENT_EMAIL_KEY, EMAIL_FROM_NAME=PrintDrop), only if customer gave an optional e-mail. Tracking link uses the origin the customer ordered from (`order.public_origin`).
- SMS: Twilio REST (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER). French numbers normalised to +33. Without keys → job `skipped` ("SMS non configuré").
- Customer can opt out (`notify=false`). Dashboard order sheet shows per-channel status.

## Local print agent (agent/printdrop_agent.py, guide agent/README.md)
- Pairing: dashboard `/dashboard/imprimantes` → single-use 8-char code (10 min) → `POST /api/agent/pair` → api key `pda_…` (sha256 stored, DPAPI on Windows). Revocable.
- Agent API (Bearer key, bound to one shop): heartbeat (printers + status), jobs/claim (atomic lease 120 s), jobs/{id}/report {lease_id, printing|printed|failed|requeue}.
- Jobs created ONLY when staff moves order pending→printing and the shop has an active agent; one `initial` job per order line (unique index). All lines printed → order auto `ready` (+ notifications).
- No duplicates: lease_id checked; printing job whose lease expires → `failed` (statut inconnu), never re-queued; agent local journal written before spooling. Reprint = manual, reason required, audited (`jobs:reprint`: owner/manager/operator). Pairing/printer settings: `devices:manage` (owner/manager).
- `--dry-run` = SIMULATION (virtual printer, files copied to disk). Real printing (SumatraPDF + Windows drivers) NOT hardware-tested.

## Printer alerts
- GET /api/shops/{id}/alerts (orders:read): agent_offline (active agent, no heartbeat 90 s), printer_offline (enabled printer of an online agent not `online`), job_failed (failed in last 24 h, no newer job for that line, order still open). Red banner on /dashboard (polls 10 s); job alert opens the order.

## Paper stock (low-paper reminder)
- shops.paper_stock {size: {sheets, set_at}}, shops.paper_alert_pct (default 80). GET/PUT /api/shops/{id}/paper-stock (PUT perm paper:manage = all staff roles; null removes a size; setting a value resets the counter from now).
- Used sheets = sheets of non-cancelled orders created since set_at (print lines of that size; photocopies count as A4). level ok/low (≥ alert %)/out → `low_paper` alert in the orders-page banner + "Stock papier" strip with "Mettre à jour".

## Pricing v2 (shops enter TTC prices; VAT from platform settings)
- shops.pricing: print{size:{bw,color,active}}, duplex_discount_pct, photocopy{bw,color,active}, scan_cents, min_order_cents,
  services[{id,name,category typing|binding|lamination|custom,unit page|unit|document,price_cents,price_from,description,active}],
  rules[{id,name,min_pages,discount_pct,active}] (volume discount on print, best one), discounts[{id,name,code|null,kind percent|fixed,value,min_order_cents,active}] (one per order, most advantageous of auto + promo code).
- Engine lib/pricing.py finalize(): lines → rule → discount → minimum complement → HT/VAT split (vat_rate_bp, 2000=20 %). Quote/Order carry total_ht_cents, vat_cents, vat_rate_bp, discount_cents.
- Public view lib/pricing.public_pricing hides inactive items & promo codes. Endpoints: PUT /api/shops/{id}/pricing (ids server-assigned), GET /api/shops/{id}/pricing/export (CSV TTC/HT), POST /api/shops/{id}/pricing/copy-from/{src} (same tenant only).
- Example prices (new shops + untouched shops migrated): A4 0,10/0,50 · A3 0,25/1,00 · scan 0,20 · saisie 3,00/page · plastification A4 2,00 · reliure dès 2,00.

## SaaS subscriptions (Mollie, manual renewal)
- plans collection (starter 19 € HT/mois, pro 39 €, business 79 €; yearly ×10), editable by super-admin: PUT /api/admin/plans/{code}. Limits max_shops/max_staff enforced (402).
- platform_settings (id=global): shop_vat_rate_bp, subscription_vat_rate_bp, trial_days 14, grace_days 7, seller identity for invoices. GET/PUT /api/admin/settings.
- organizations.subscription {plan_code, period, status trialing|active|past_due|expired|canceled (effective status computed from dates), trial_ends_at, current_period_end, granted_by_admin}. Register → 14-day trial. Expired/canceled → portal stops accepting orders. Admin: PATCH /api/admin/organizations/{id}/subscription (grant = no invoice, audited).
- Owner (billing:manage): GET /api/billing, POST /api/billing/checkout → invoice pending + Mollie payment (Idempotency-Key = invoice id) → redirect. POST /api/billing/mollie/webhook (form id) → status ALWAYS re-fetched from Mollie, amount/metadata checked, paid applied once (sequential number PD-YYYY-NNNNNN, period extended). GET /api/billing/invoices/{id} also re-syncs pending invoices. Without MOLLIE_API_KEY: checkout 503, nothing simulated.
- Cron subscriptions-sweep 08:00 Paris (.emergent/crons.yml) → persists statuses + reminder e-mails (J-3, expiry).
- Migrations: backend/migrations/runner.py (001_pricing_v2, 002_subscriptions), auto at startup, `python -m migrations.runner`. Demo orgs: subscription granted_by_admin until +1 year (seed).

## Daily report
- GET /api/shops/{id}/reports/daily?day=YYYY-MM-DD (reports:read = owner, manager; Europe/Paris day): revenue (cash/card), orders, pages N&B/couleur, sheets, photocopies, scans, agent jobs, unpaid, avg basket, 24 hourly buckets, busiest_hour. Page /dashboard/rapports (bar chart, day navigation).
- Nightly e-mail 21:00 Europe/Paris via platform cron `.emergent/crons.yml` → POST /api/cron/daily-report (Bearer WEBHOOK_CRON_SECRET, idempotent by X-Webhook-Id, work backgrounded). One e-mail per org per day (report_emails unique) to the owner account. Setting `organizations.report_email` (GET/PUT /api/reports/settings, manage = owner). "Envoyer maintenant" = POST /api/reports/email-now. Seeded demo orgs have report_email=false (fictitious owner addresses).

## Seed (python backend/seed.py, idempotent)
- Shops: `cybercafe-bastille` (org CyberCafé Bastille SARL), `copyprint-bellecour` (org CopyPrint Lyon). Default pricing A4 N&B 0,15 €, A4 couleur 0,60 €, duplex -10 %, photocopie 0,10/0,50 €, scan 0,20 €.
- No seeded orders. Accounts in memory/test_credentials.md.

## Tests
backend/tests/test_pricing_billing.py — pricing engine, promo hiding, server prices, CSV, tenant isolation, plans/settings admin, no simulated payment, forged webhook, trial/limits, migrations.
backend/tests/test_reports_alerts.py — report counts, perms/isolation, alerts, cron auth/idempotency.
backend/tests/test_agent_notify.py — pairing, agent isolation, leases, no duplicates, requeue, reprint, auto-ready, notification queue.
backend/tests/test_stage1.py — auth, pricing, upload validation, token binding, tracking, tenant isolation, role limits, lifecycle, double-payment guard, signed links, super-admin scope, suspension.

## Printers & devices v2 / direct printing (see docs/ETAT_ET_DEPLOIEMENT.md)
- printers: + display_name, connection_type (usb|wifi|ethernet|network|virtual|unknown; Windows only knows "network" → owner confirms Wi-Fi/Ethernet), manufacturer, model, ip_address, port_name, driver_name, capabilities {paper_sizes, color, duplex}.
- agent_commands (discover_usb, discover_network, add_network_printer, test_connection, test_page): queued → delivered in heartbeat response (sent) → agent posts result (done/failed); expired after 3 min.
- shops.printer_rules [{paper_size|any, color|any, printer_id}]; pick_printer: manual > rule > default > first usable; check_printer blocks offline/disabled/unsupported format/colour/duplex.
- POST /api/orders/{id}/print-direct (« IMPRIMER DIRECTEMENT », orders:update): dry_check or create one initial job per print line bound to printer_id; 409 on second call. Order pending→printing.
- Job statuses: queued, claimed (delivered to agent), spooled (Windows spooler), printing, printed (completed per driver — not physical proof), failed, retry_wait (requeue, retried after 30 s), cancelled.
- Owner alert e-mails (owner_alerts dedupe): printer online→offline, agent silent 3 min. Demo orgs: dashboard only.
- Word .docx upload → LibreOffice PDF (preview only; production lacks soffice → French error).
- Agent v0.2 (agent/printdrop_agent.py): tkinter pairing window, --background autostart, DPAPI key, private tmp cleanup, spool monitoring; --dry-run = SIMULATION. Installer: agent/installer/printdrop.iss + .github/workflows/windows-agent.yml.
- Tests: backend/tests/test_printers.py (uses a freshly registered org for isolation).
