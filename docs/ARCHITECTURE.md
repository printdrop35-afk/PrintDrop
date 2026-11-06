# PrintDrop — Architecture & plan de développement

## 1. Vue d'ensemble

```
┌──────────────────────┐   HTTPS /api (cookie httpOnly)   ┌────────────────────────────┐
│ Frontend React (Vite)│ ───────────────────────────────▶ │ Backend FastAPI (async)    │
│  • Portail client     │                                  │  routers/ auth, dashboard, │
│    /s/:slug, /suivi   │                                  │  public, admin             │
│  • Tableau de bord    │                                  │  lib/ authz (RBAC+tenant), │
│    /dashboard/*       │                                  │  pricing, storage, security│
│  • Super-admin        │                                  └──────┬───────────┬─────────┘
│    /superadmin        │                                         │           │
└──────────────────────┘                               MongoDB ◀─┘           └─▶ Stockage privé
                                                                               (disque, hors web)
┌──────────────────────────────┐   HTTPS (clé d'agent)  ── ÉTAPE 3 ──▶ /api/agent/*
│ PrintDrop Local Agent (Win.) │
└──────────────────────────────┘
```

Frontend et backend sont séparés (`frontend/`, `backend/`), dépôt compatible GitHub.

## 2. Sécurité & isolation

* **Deux portées de rôles distinctes** : `users.platform_role` (`superadmin`) et `memberships.role`
  (`owner` > `manager` > `operator`) par organisation. Jamais fusionnées.
* Principal reconstruit **à chaque requête** depuis la base (utilisateur actif, adhésion active,
  organisation active) → une suspension ou une révocation prend effet immédiatement.
* `TenantRepo` (lib/authz.py) injecte `org_id` dans **chaque** find / update / insert / aggregate
  (étape `$match` en tête, `$lookup` interdit). Une ressource d'une autre entreprise renvoie **404**.
* `org_id`, `shop_id`, prix, statut de paiement et chemins de fichiers sont **toujours** déterminés
  côté serveur. Les champs supplémentaires envoyés par le navigateur sont ignorés (Pydantic).
* Documents : type détecté par signature binaire (PDF/PNG/JPG), 25 Mo max, comptage de pages serveur
  (pypdf), stockés hors du répertoire web (chmod 600), accessibles uniquement via un lien HMAC signé
  de 5 minutes délivré après contrôle de locataire + audit. Chaque upload porte un jeton secret
  (haché en base) requis pour le rattacher à une commande ; un document ne peut être rattaché qu'une fois.
* Connexion : bcrypt, JWT HS256 en cookie httpOnly/SameSite=Lax/Secure, verrouillage après 5 échecs / 15 min.
* Journal d'audit : connexion, échecs, accès refusés, commandes, statuts, encaissements, ouverture de
  documents, tarifs, équipe, actions plateforme.
* Super-admin : vue agrégée uniquement (pas d'accès aux documents/clients). L'impersonation auditée
  est prévue plus tard si nécessaire.

## 3. Schéma de données (MongoDB, ids `uuid4` en chaîne, montants en centimes d'euro)

| Collection | Champs principaux |
|---|---|
| users | id, email (unique global), name, password_hash, platform_role, active, created_at |
| organizations | id, name, status (active/suspended), plan (essai/starter/pro), owner_id, created_at |
| memberships | id, org_id, user_id, role (owner/manager/operator), active, created_at |
| shops | id, org_id, slug (unique, QR), name, city, address, accepting_orders, pricing{print{A4..Legal:{bw,color}}, duplex_discount_pct, photocopy{bw,color}, scan_cents} |
| documents | id, org_id, shop_id, order_id, filename, kind, page_count, size_bytes, storage_key, token_hash, status (uploaded/attached) |
| orders | id, code (PD-XXXXXX), org_id, shop_id, customer_name, customer_phone, phone_digits, lines[], total_cents, status, payment_status, payment_method, paid_at, history[] |
| payments | id, org_id, shop_id, order_id (unique), amount_cents, currency, method, source (counter/online), recorded_by |
| audit_logs | id, at, org_id, actor_id, actor_email, action, resource_type, resource_id, outcome, details |
| login_attempts | email, at (TTL 1 h) |

Statuts de commande : `pending → printing → ready → picked_up`, `cancelled` ; réimpression `ready → printing` ;
retrait impossible tant que la commande n'est pas payée.

## 4. Tâches de fond

Étape 1 : tâche asynchrone dans le processus API qui supprime toutes les 30 min les fichiers déposés
mais jamais commandés depuis 24 h. Étapes suivantes : file de tâches dédiée (notifications, webhooks,
rétention des documents après retrait).

## 5. PrintDrop Local Agent (Windows) — implémenté (v0.1, voir agent/README.md)

* Service Windows (.NET 8 ou Python + pywin32) installé sur le poste du comptoir.
* **Appairage** : le propriétaire génère un code d'appairage à usage unique dans le tableau de bord ;
  l'agent l'échange contre une clé d'agent (principal machine `principal_type=agent`, lié à 1 boutique,
  portée `jobs:read jobs:report` uniquement), stockée via DPAPI.
* **Récupération** : long-polling HTTPS `GET /api/agent/jobs` → ne renvoie que les travaux de sa
  boutique au statut `printing` ; chaque travail est **réservé** atomiquement (`lease_id`, expiration)
  pour éviter les doubles impressions ; téléchargement via lien signé court.
* **Impression** : via les pilotes installés (Win32 spooler / SumatraPDF en ligne de commande pour les
  PDF), options format/couleur/recto-verso/copies mappées sur DEVMODE.
* **Remontée d'état** : `POST /api/agent/jobs/{id}/report` (spooled, printed, failed + code erreur),
  heartbeat imprimantes (en ligne / hors ligne / bourrage / plus de papier).
* **Anti-doublon** : clé d'idempotence par travail + journal local ; un travail `printed` n'est jamais
  relancé automatiquement. **Réimpression** uniquement par action manuelle auditée (nouveau job_id).
* ⚠️ Nécessite des **tests matériels réels** (pilotes, imprimantes multiples, coupure réseau, imprimante
  hors ligne, file bloquée) — rien de cela n'est simulé dans l'Étape 1. L'impression navigateur
  (ouvrir le document + Ctrl+P) n'est PAS équivalente et n'est proposée qu'en solution manuelle.

## 6. Plan par étapes

| Étape | Contenu | État |
|---|---|---|
| 1 Fondations | Modèle de données, auth, organisations/boutiques/adhésions, isolation, portail client QR, dépôt privé, options d'impression, tarification serveur, gestion des commandes, encaissement comptoir, équipe, audit, super-admin de base, tests automatisés | **Implémenté** |
| 2a Notifications | E-mail (Resend géré) + SMS (Twilio) « commande prête », file de tâches avec relances | **Implémenté** (SMS actif dès que les clés Twilio sont fournies) |
| 2b Paiements | Paiement en ligne (Stripe) avec webhooks signés et idempotents, remboursements | À faire |
| 3 Agent local | Appairage, API agent, gestion imprimantes/appareils, réimpressions contrôlées, programme Python Windows (`agent/`) | **Implémenté, testé en simulation uniquement** — tests matériels requis |
| 4 Caisse & analytique | POS comptoir (ventes libres), clôture de caisse, rapports CA/opérations, export | À faire |
| 5 SaaS | Abonnements facturés, limites par plan, impersonation auditée, multilingue (en, ar…) | À faire |

## 7. Ce qui n'est PAS prêt pour la production

Aucune prétention de mise en production : il manque des tests d'intrusion, la revue de sécurité, les
tests de paiement réels, les tests matériels de l'agent, le stockage objet chiffré + sauvegardes, la
politique RGPD de rétention des documents et la limitation de débit globale.
