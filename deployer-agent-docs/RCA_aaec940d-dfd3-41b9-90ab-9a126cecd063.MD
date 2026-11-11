# RCA — printdrop.fr / www.printdrop.fr "site can't be reached"

## Summary
The outage is **not** a deploy failure and **not** an app problem. The latest deployment succeeded and the app is live. The custom domains are correctly linked, verified, and SSL-active on the Emergent side. The break is entirely in the user's **Cloudflare DNS**: the records resolve to Cloudflare's own proxy IPs (orange cloud ON) instead of Emergent's origin, so traffic never reaches the app (first 404, now connection-refused / "can't be reached").

## Evidence

### 1. Deploy & pod status — HEALTHY
- `describe_deployment_state`: active_run_id `aaec940d-dfd3-41b9-90ab-9a126cecd063`, `run_status: success`, redeploy, completed `2026-11-11T11:50:39Z`.
- The "just initiated async deployment" is this run — it completed green, not failed, not mid-rollout.
- Image deployed, tier_0, kubernetes frontend, farm_ts_react_mongo_base_image.

### 2. Default Emergent URL — SERVES THE APP
- `preview_health_check` on `https://print-drop-6.emergent.host/` → **200**, 608ms, real PrintDrop HTML (title "PrintDrop — Logiciel de gestion pour imprimeries et photocopies").
- Confirms backend + frontend are fine; the problem is purely how the custom domain reaches us.

### 3. Emergent-side custom domain binding — CORRECT
- `list_domains`:
  - `www.printdrop.fr` → verified: true, ssl_status: **active**, provider cloudflare, ssl_validation_method http, root_redirect_enabled true.
  - `printdrop.fr` → verified: true, ssl_status: **active**, provider cloudflare, ssl_validation_method http, root_redirect_enabled true.
- Both hostnames are linked and their SSL certs are issued and active. Nothing to fix on the Emergent side.

### 4. Live DNS check — THE ROOT CAUSE
- `check_domain_status`:
  - `www.printdrop.fr` → **linked: false**, "A records do not point to expected IPs"
  - `printdrop.fr` → **linked: false**, "A records do not point to expected IPs"
- Resolvers return **162.159.142.117** and **172.66.2.113** — these are **Cloudflare anycast/proxy IPs**, i.e. the records are proxied (orange cloud ON) and/or pointing at Cloudflare's edge rather than Emergent's origin target.
- This double-proxy (user's Cloudflare zone proxying in front of Emergent's Cloudflare-for-SaaS custom hostname) is what produced the 404 → then the "site can't be reached" / failed TLS handshake.

### 5. Nameservers / DNSSEC
- Not directly queryable with my tooling. User-side verification: confirm Hostinger has delegated the domain to Cloudflare nameservers, and that **DNSSEC is not half-configured** (DS record at registrar with no matching keys at Cloudflare, or vice-versa, will also produce "can't be reached"). If DNSSEC was enabled at Hostinger but the zone is served by Cloudflare, the DS record must match Cloudflare's DNSSEC keys or be removed.

## Root cause
User's Cloudflare DNS for both the apex (`printdrop.fr`) and `www` host points to Cloudflare proxy IPs with the **orange-cloud proxy enabled**, not to the Emergent target. Requests therefore never reach the Emergent origin. Emergent's deployment, domain binding, and SSL are all healthy.

## Fix (user action in Cloudflare — then re-check)
Emergent uses Cloudflare-for-SaaS custom hostnames with **HTTP validation**, which requires the record to resolve to Emergent's origin **DNS-only (grey cloud)**, not proxied.

1. In the **Emergent Deployment Panel → Domains** tab, open each domain and copy the **exact DNS target shown there verbatim** (the CNAME/A target Emergent displays for `printdrop.fr` and `www.printdrop.fr`). Use those exact values — do not reuse the current Cloudflare IPs.
2. In **Cloudflare DNS** for the zone `printdrop.fr`:
   - Set `www` → **CNAME** to the Emergent target shown in the Domains tab.
   - Set `@` (apex `printdrop.fr`) → **CNAME** to the same Emergent target (Cloudflare CNAME-flattening handles the apex), or the A record(s) exactly as shown in the panel.
   - For **both** records, set the proxy status to **DNS only (grey cloud)** — turn the orange cloud **OFF**.
   - Remove any stale/extra A records pointing to 162.159.142.117 / 172.66.2.113.
3. Confirm nameservers at **Hostinger** still delegate to Cloudflare, and that **DNSSEC** is either fully consistent between Hostinger (DS) and Cloudflare, or disabled.
4. Wait for propagation (a few minutes up to the record TTL), then re-verify with the Domains tab. The default URL `https://print-drop-6.emergent.host` keeps working throughout.

## Not the cause (ruled out)
- App source / routing — no change needed; default URL serves 200.
- Deploy pipeline — latest run succeeded.
- SSL on Emergent — certs active for both hostnames.
- Secrets / tier — unrelated; app is healthy.
