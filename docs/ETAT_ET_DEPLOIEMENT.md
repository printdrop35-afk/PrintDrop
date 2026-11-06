# PrintDrop — état des fonctionnalités, API et déploiement

## 1. Ce qui est réellement implémenté / ce qui ne l'est pas

| Fonctionnalité | État |
|---|---|
| Portail client QR, envoi PDF / images, prix calculés serveur (HT/TVA/TTC), suivi | ✅ Implémenté et testé |
| Documents Word (.docx) → PDF sur le serveur | ✅ Preview (LibreOffice installé). ⚠️ **Production : LibreOffice absent** → le client reçoit « enregistrez en PDF » |
| Tableau de bord, tarifs, rapports, équipe, journal, abonnements, super-admin | ✅ Implémenté et testé |
| Imprimantes et périphériques : Wi-Fi/Réseau, USB, IP manuelle, tests, défaut, désactivation, suppression protégée, règles d'affectation | ✅ Côté serveur + interface + agent. ⚠️ **Exécution Windows non testée sur matériel** |
| « IMPRIMER DIRECTEMENT » (contrôles serveur, choix d'imprimante, file, statuts spouleur) | ✅ Testé de bout en bout avec l'agent en **mode simulation** |
| Agent Windows v0.2 (fenêtre d'appairage, arrière-plan, nettoyage des fichiers temporaires) | ✅ Code source. ⚠️ **À tester sur Windows 10/11 réels** |
| Installateur .exe (PyInstaller + Inno Setup, démarrage auto, raccourci, désinstallation) | ⚠️ Script GitHub Actions fourni — **à exécuter sur GitHub** ; bouton « Télécharger » actif quand `AGENT_DOWNLOAD_URL` est défini |
| Notifications e-mail (commande prête, rapport, alertes imprimante/agent) | ✅ Actives (Resend géré). Alertes non envoyées aux comptes démo |
| SMS | 🔑 Nécessite les clés Twilio |
| Paiement des abonnements (Mollie) | 🔑 Nécessite `MOLLIE_API_KEY` — aucun paiement simulé |
| Paiement en ligne client → boutique | ❌ Non implémenté (paiement au comptoir uniquement) |
| Historique / reçus côté client, POS avancé, gestion clients, support | ❌ Non implémentés |
| Vérification physique de la sortie papier | ❌ Impossible sans capteur : « terminé selon le pilote » uniquement |
| Stack Next.js / PostgreSQL / Prisma | ❌ Volontairement non migrée (FastAPI + MongoDB en production) |

## 2. Tests matériels à réaliser (non faits)
Tests 1 à 5 et 8 à 12 du cahier des charges : détection USB, découverte réseau (balayage TCP 9100/631/515 du /24),
installation IP manuelle (PowerShell `Add-PrinterPort`/`Add-Printer`), page de test (`printui /k`), impression couleur/N&B/copies/recto-verso
via SumatraPDF, débranchement/rebranchement, nettoyage `%LOCALAPPDATA%\PrintDrop\tmp`. Le test 13 (isolation) est automatisé.

## 3. API principale (préfixe `/api`, cookie de session sauf agent)
- Agent (en-tête `Authorization: Bearer pda_…`) : `POST /agent/pair`, `/agent/heartbeat` (renvoie les commandes), `/agent/commands/{id}/result`,
  `/agent/jobs/claim`, `/agent/jobs/{id}/report` (`printing` → `spooled` → `printed` | `failed` | `requeue`→`retry_wait`).
- Imprimantes : `POST /shops/{id}/printers/discover` `{agent_id, kind: usb|network}`, `POST /shops/{id}/printers/manual`,
  `POST /printers/{id}/test-connection`, `POST /printers/{id}/test-page`, `GET /agent-commands/{id}`, `PATCH /printers/{id}`,
  `DELETE /printers/{id}?jobs=cancel|reassign`, `GET|PUT /shops/{id}/printer-rules`.
- Impression : `POST /orders/{id}/print-direct` `{printer_id?, dry_check}`, `GET /shops/{id}/print-queue`, `POST /print-jobs/{id}/reassign|reprint|cancel`.
- Démarrage : `GET /onboarding`, `POST /onboarding/{étape}/done`. Téléchargement agent : `GET /agent-download`.

## 4. Déploiement
Variables backend : `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STORAGE_DIR`, `EMERGENT_EMAIL_KEY`, `WEBHOOK_CRON_SECRET`, facultatives
`MOLLIE_API_KEY`, `TWILIO_*`, `AGENT_DOWNLOAD_URL`, `AGENT_VERSION`. Migrations automatiques au démarrage (`python -m migrations.runner`).
Crons : `.emergent/crons.yml`. Agent : pousser le dépôt sur GitHub → workflow « Agent Windows PrintDrop » → publier l'installateur → définir `AGENT_DOWNLOAD_URL`.
