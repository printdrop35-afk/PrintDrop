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

## Agent release (installer link, version, update notices)
- db.platform_settings {id:"agent_release", url, version, notes, updated_at}; fallback env AGENT_DOWNLOAD_URL / AGENT_VERSION.
- GET/PUT /api/admin/agent-release (super-admin; url must be https and end in .exe, or "" = download off; version x.y.z). Audited as platform.agent_release.
- GET /api/agent-download (tenant) → {available,url,version,notes}; Devices page « Télécharger l'agent » button.
- AgentOut.update_available / latest_version: active agent with readable version older than latest → notice + badge on Imprimantes page.
- GitHub workflow signs PrintDrop.exe + installer with signtool when repo secrets WINDOWS_CERT_PFX_BASE64 / WINDOWS_CERT_PASSWORD exist; otherwise unsigned build + warning. Publishes Release agent-v<version> with stable PrintDrop-Setup.exe.
- Tests: backend/tests/test_agent_release.py.

## Brand v2 (official logo) — LIVE (approved)
- Assets: brand/build_brand.py → frontend/public/brand/ (SVG + PNG: light, dark, mono, icon, app icons, favicons in brand/favicon/, OG image). Source: brand/source/logo-original.webp (already transparent).
- Config: src/lib/brand.ts (BRAND, COMPANY — address « OREGRES » to verify, SIREN 800646697; COMPANY_PENDING = missing legal info, rendered « À compléter »).
- Theme: brand tokens are non-inline @theme vars; <html class="brand-v2"> (index.html) applies the official palette everywhere. Public site: / (LandingV2), /contact, /mentions-legales, /confidentialite, /cgu, /cookies. Old /apercu/* links redirect. Company: ORGÈRES, R.C.S. Rennes 800 646 697.
- New API: GET /api/public/plans, POST /api/public/contact (stores db.contact_messages, emails CONTACT_EMAIL=contact@printdrop.fr, honeypot + 5/h/IP).

## Privacy: no downloads, selected pages only, retention
- POST /api/orders/{id}/documents/{doc}/link → 403 (downloads disabled; print only via « IMPRIMER DIRECTEMENT »).
- Agent fetches GET /api/agent/jobs/{job_id}/file?lease=… (agent key + own active lease): PDF reduced to the customer's page_range (pypdf, in memory); job.pages renumbered 1..n.
- lib/retention.py: on picked_up/cancelled → purge_order (files deleted, documents.status=purged, customer_name « Client anonymisé », phone/email/note cleared, order.purged_at). Hourly cron /api/cron/retention also purges orders older than 7 days and orphan uploads > 24 h. Amounts/status kept for reports.
- crons.yml fixed: all entries use `cron:` (subscriptions-sweep previously used the invalid `schedule:` key).
- Tests: backend/tests/test_retention_pages.py.

## Contact inbox & legal cleanup
- GET /api/admin/contact-messages (platform:read, newest first, IP hidden), PATCH /api/admin/contact-messages/{id} {handled} (platform:manage, audited platform.contact_handled). UI: SuperAdmin « Messages du site » (À traiter / Démos / Tous, reply by mailto, mark handled).
- Legal pages: owner asked NOT to show legal form, capital, VAT, publication director, hosting provider, nor a recipients/subprocessors section — removed (not placeholders).

## Retention countdown, message badge, Word on prod, footer
- OrderPublicOut.documents_delete_at / documents_days_left (created_at + RETENTION_DAYS, server clock) on create + track; Tracking page « N jours avant la suppression automatique ».
- SuperAdmin header « Messages » badge (unhandled count, polled 30 s, toast on new arrival) → #messages-du-site.
- Word → PDF: lib/storage.convert_docx → ConvertAPI EU (CONVERTAPI_TOKEN, CONVERTAPI_BASE_URL default https://eu-v2.convertapi.com, StoreFile=false, in-memory) when the token is set; otherwise local LibreOffice (preview). French errors on 401/403/5003.
- Footer « Informations » column: Contact link only (legal pages still reachable by URL, no longer linked).

## Print workflow v3 (brief A–L) — supersedes "no downloads" and "7-day / anonymise" rules
- Pickup/order code: 4 digits, unique among in-progress orders (orders.active_code + partial unique index; migration 003_pickup_codes dropped the old unique `code` index). Legacy PD-XXXXXX codes still tracked.
- Customer contact: phone and email optional (name required). Tracking: code alone if the order has no phone, code + phone otherwise; 30 lookups / 10 min / IP.
- QuoteLine.document_pages + selected_pages (customer order preserved, duplicates removed); price = selected pages × copies.
- Staff (documents:read, cookie session) GET /api/orders/{id}/documents/{doc}/file?variant=original|print&disposition=attachment|inline — print = in-memory PDF of selected pages. POST …/link returns that URL. Never creates a print job.
- No automatic printing: status changes never enqueue jobs; printing only via « IMPRIMER DIRECTEMENT » (confirmation step) or « Imprimer… » (system print dialog in a hidden iframe).
- Pickup: picked_up requires confirm_code == order code (QR on ticket encodes it); mismatch → 409 + audit order.pickup_mismatch.
- Retention: files deleted only when picked_up/cancelled (lib/retention.py); order data incl. name/phone/email kept; failures logged + retried by hourly cron; old links → 410.
- Pickup ticket (components/PickupTicket.tsx): official logo, 4-digit code, QR, shop, prints alone (.pd-print-area).

## Counter flow v4
- Customer portal « Services au comptoir »: photocopies N&B/couleur removed; public quote/order with photocopy_* > 0 → 422 (photocopy pricing still editable in Tarifs, used at the counter only).
- Order sheet: « Étape 1 — Statut de la commande » then « Étape 2 — Mode de paiement » (Espèce / Carte), payment disabled while status is pending.
- Orders page « Code client » scan box → GET /api/shops/{shop_id}/orders/by-code/{code} (tenant-scoped, in-progress order first). The scanned/confirmed code is kept for that order in page state (one transaction); pickup reuses it instead of prompting again; next scan replaces it. Backend still requires confirm_code for picked_up.
- QR poster (Boutique & QR code) shows the official logo above the QR; pickup ticket already had it.

## Pickup receipt
- components/PickupReceipt.tsx shown in the order sheet once status = picked_up: logo, shop name/address, code, pickup date, lines, HT/TVA/TTC, payment method (Espèce/Carte), paid date. Print window opens once automatically right after pickup (user confirms), plus « Imprimer le reçu » button.
- lib/printElement.ts prints a single element in a clean hidden iframe (app styles copied, 72 mm for the receipt, 12 cm for the pickup ticket) — used by receipt and pickup ticket.
- i18n: method.cash « Espèce », method.card_terminal « Carte ».

## Counter services v5: Photocopie & Scan (dashboard « Comptoir », /dashboard/comptoir)
- Tabs: Impression depuis le téléphone (→ Commandes) · Photocopie · Scan document. No customer account/code needed; staff session + tenant scope authorise everything.
- Photocopy: POST /api/shops/{id}/counter/copy/quote and /counter/copy (CopyIn: color, A4/A3, duplex, originals, copies). Order service="copy", status printing → agent clicks « Copies sorties du copieur » (ready) → pay Espèce/Carte → « Terminer » (picked_up). Copy is made with the copier's own Copy button (Windows drivers expose no copy function); never auto-marked done.
- Scan: scan_sessions + scan_pages (temp JPEGs). POST /shops/{id}/scan-sessions, POST /scan-sessions/{id}/scan (agent command "scan" via WIA, 409 if agent offline / already scanning), agent POST /api/agent/scan-sessions/{id}/pages, staff import fallback POST /scan-sessions/{id}/upload, PATCH/DELETE pages (rotate/remove), GET page image, POST /finalize (one PDF or single JPG, idempotent) → order service="scan", status ready, delivery_token. Raw pages deleted at finalize; abandoned sessions after 24 h.
- Delivery: public /scan/:token page, GET /api/public/scans/{token}(/file) (402 until paid, 410 after deletion); first download → status "delivered" + scan_downloaded_at; POST /orders/{id}/scan-email.
- Retention: picked_up/cancelled → files deleted at once; delivered scans 24 h after first download; undownloaded scans kept.
- Pickup: customer code NO LONGER required for authenticated staff (confirm_code ignored); scan box only finds the order. Payment idempotent (409 on second).
- Agent v0.3.0: WIA scanning (flatbed / feeder), scanners listed in heartbeat. UNTESTED on real hardware.
- Tests: backend/tests/test_counter.py.

## Clôture de caisse
- GET /api/shops/{id}/reports/cash?day=YYYY-MM-DD (reports:read, Europe/Paris day): payments split cash / card_terminal / other, totals, every payment (time, order code, service, method, amount). 422 future day, 404 other tenant.
- Reports page « Clôture de caisse » card (components/CashSummary.tsx), same day picker, live refresh today, « Imprimer la clôture » via printElement (logo + shop + date header).
- Tests: test_counter.py::test_cash_summary_by_method.

## Document storage (fix "Fichier supprimé" on print)
- Root cause (prod RCA): files were written to the container's local disk (STORAGE_DIR), which is per-replica and wiped on each redeploy → documents still referenced in Mongo were missing → 410 "Fichier supprimé" when staff opened/printed.
- Now: lib/storage.save_file/read_file/delete_file (async) store bytes in MongoDB GridFS (bucket `files`, key `gridfs:<ObjectId>`), shared by all replicas and persistent. Legacy local-disk keys are still readable when present.
- Lifecycle: original kept until order picked_up/cancelled (lib/retention.purge_order); print-ready PDF (selected pages only) built in memory on each request. Deletion idempotent, retried hourly, order/payment/history kept.
- Test: backend/tests/test_document_lifecycle.py (wipes local disk, 4-page PDF, 1-1 / 1-2, agent print, pickup deletes only that order).
- Lost files (pre-fix uploads): GET /api/orders/{id}/documents/health → per-document `available` (file really in storage). Order sheet (OrderPrintTools) shows an amber "fichier perdu" box with « Demander au client de renvoyer » → POST /api/orders/{id}/request-resend (orders:update): e-mails the customer (and SMS if Twilio configured) a link to the shop upload page /s/{slug}, stores order.resend_requested_at (button becomes « Relancer le client »), returns the link for staff to copy. 409 if nothing is lost or order finished. Customer's re-upload creates a new order; staff cancel the old one.

## Printer integration v2 (agent 0.4.0)
- « Ajouter une imprimante » (PrinterManager): POST /api/shops/{id}/printers/discover-all → agent `discover_all` returns {installed (Windows queues), network (TCP 9100/631/515 + IPP printer-make-and-model), usb_missing_driver (PnP errors)}. « Connecter cette imprimante »: installed → POST /printers/connect (enable + test_connection); network → POST /printers/install kind=network (Add-Printer -IppURL, driverless Microsoft IPP class driver; UAC elevation if needed) then connect; USB w/o driver → install kind=usb (pnputil /scan-devices). Failure → DriverGuide with official manufacturer link only. Manual IP config kept under « Configuration avancée ».
- Printer status « Prête » only when online AND verified_at (set by a successful test_connection command result). Buttons: Renommer, Reconnecter (test_connection), Tester l'imprimante (test page), défaut, activer, supprimer, Actualiser. French fix hints per Windows status.
- Automatic photocopy: POST /shops/{id}/counter/copy with printer_id → order service=copy, status printing, total 0, copy_job{state running}; agent command `copy` (WIA scan original → PDF via Pillow → Sumatra print N copies → spool wait). Result → done (pages = scanned × copies, priced with photocopy bw/color, status ready) only if spool confirmed & copies complete; otherwise needs_confirmation → staff POST /orders/{id}/copy/confirm {originals, copies} (0 = cancelled, free). Nothing scanned → failed + cancelled, no charge. Payment refused (409) until copy_job.state=done. Agent silent 30 min → expire_copy_commands (worker). Refused if printer offline/agent offline/no scanner/feeder missing/one copy already running. Manual copy (copier's own button) kept as fallback when automatic is unavailable.
- Scan: duplex option (feeder) and feeder/glass shown only per agent scanner_caps (WIA 3086). Pricing: scan_cents = N&B, scan_color_cents = couleur. Scan file deleted right after the customer's first download (retention SCAN_GRACE=0 + purge in /public/scans/{token}/file). Status chips: Scan en cours → Scan terminé → Paiement effectué → Document disponible → Document récupéré.
- Tests: backend/tests/test_auto_copy.py. Real hardware NOT tested (no Windows machine in this environment).
