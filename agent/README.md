# PrintDrop Local Agent (Windows) — guide d'installation

L'agent est un petit programme installé sur le PC du comptoir. Il se connecte à **une** boutique
PrintDrop, récupère uniquement les travaux autorisés (commandes passées en « En impression » par un
employé) et les envoie aux imprimantes installées dans Windows, avec leurs pilotes habituels.

> ⚠️ **Version 0.1 — à valider sur votre matériel.** Le code a été testé de bout en bout en
> **mode simulation** (aucune imprimante). L'impression réelle (pilotes, recto-verso, couleur,
> formats, bacs) doit être vérifiée sur vos imprimantes — voir « Tests matériels obligatoires ».

## 1. Prérequis

| Élément | Version | Pourquoi |
|---|---|---|
| Windows 10 / 11 (64 bits) | à jour | spouleur d'impression Windows |
| Python | 3.10 à 3.12 — cochez « Add python.exe to PATH » | exécute l'agent |
| SumatraPDF | 3.5+ (installation « pour tous les utilisateurs ») | imprime PDF et images en silence via le pilote Windows |
| Imprimante(s) | installées et testées dans Windows (page de test OK) | l'agent utilise les pilotes existants |

## 2. Installation

Ouvrez **PowerShell en administrateur** :

```powershell
mkdir C:\PrintDrop; cd C:\PrintDrop
# copiez ici printdrop_agent.py et requirements.txt
python -m pip install -r requirements.txt
python printdrop_agent.py printers          # vérifie que vos imprimantes sont détectées
```

## 3. Appairage avec la boutique

1. Dans le tableau de bord : **Imprimantes & agent → Générer un code d'appairage** (valable 10 min, usage unique).
2. Sur le PC :
   ```powershell
   python printdrop_agent.py pair --server https://VOTRE-ADRESSE-PRINTDROP --code ABCD2345 --name "Comptoir 1"
   ```
   La clé de l'agent est chiffrée avec **DPAPI** (liée à cette machine) dans `C:\ProgramData\PrintDrop\config.json`.
3. Lancez un essai : `python printdrop_agent.py run --once` puis vérifiez dans le tableau de bord que
   l'agent est « En ligne » et que les imprimantes apparaissent. Choisissez l'imprimante par défaut.

## 4. Démarrage automatique (service Windows)

Avec [NSSM](https://nssm.cc) :

```powershell
nssm install PrintDropAgent "C:\Program Files\Python312\python.exe" "C:\PrintDrop\printdrop_agent.py run"
nssm set PrintDropAgent AppDirectory C:\PrintDrop
nssm set PrintDropAgent ObjectName ".\CompteImpression" "MotDePasse"   # compte local qui voit les imprimantes
nssm start PrintDropAgent
```

Les imprimantes réseau installées « par utilisateur » ne sont pas visibles du compte LocalSystem :
utilisez un compte local dédié ou installez les imprimantes pour tous les utilisateurs.
Journal : `C:\ProgramData\PrintDrop\agent.log`.

## 5. Fonctionnement et sécurité

* L'agent n'imprime **que** ce qu'un employé a lancé (« Lancer l'impression »). Pas d'impression à la commande.
* Chaque travail est **réservé** par le serveur (bail de 2 min) ; l'agent présente ce bail à chaque compte rendu.
* Un **journal local** est écrit *avant* l'envoi au spouleur : si le PC redémarre en pleine impression, le
  travail n'est **jamais relancé automatiquement**. Il apparaît « Échec / statut inconnu » et un employé
  décide d'une **réimpression manuelle** (motif obligatoire, tracée dans le journal d'audit).
* Imprimante hors ligne, bourrage, plus de papier : vérifié juste avant l'impression → le travail est remis
  en file, intact. L'état des imprimantes remonte au tableau de bord toutes les 5 s.
* Quand tous les documents d'une commande sont imprimés, la commande passe à « Prête » et le client est prévenu.
* Révocation : bouton **Révoquer** dans le tableau de bord → la clé est refusée immédiatement.
* « Imprimé » signifie **remis au spouleur Windows** : l'agent ne peut pas garantir que la feuille est sortie
  physiquement (bourrage après spool). Le personnel contrôle visuellement.

## 6. Mode simulation (tests sans imprimante)

```powershell
python printdrop_agent.py run --dry-run
```
Aucune impression : une imprimante virtuelle « PrintDrop-Simulation » est déclarée et les fichiers sont
copiés dans `C:\ProgramData\PrintDrop\dryrun_output`. **Ne jamais utiliser en production.**

## 7. Tests matériels obligatoires avant production

- [ ] PDF A4 N&B recto, 1 et 10 exemplaires — nombre de feuilles correct
- [ ] Recto-verso (bord long) sur une imprimante avec unité duplex ; comportement sans unité duplex
- [ ] Couleur vs N&B forcé (`monochrome`) sur imprimante couleur
- [ ] Formats A3 / A5 / Lettre / Légal (bacs, mise à l'échelle)
- [ ] Plages de pages (`1-3,5`)
- [ ] Images JPG/PNG (orientation, ajustement à la page)
- [ ] Imprimante éteinte, hors ligne, bourrage, plus de papier → travail remis en file / signalé
- [ ] Coupure réseau pendant téléchargement et pendant impression ; redémarrage du PC pendant impression
- [ ] Deux agents sur la même boutique : aucun travail imprimé deux fois
- [ ] Fonctionnement en service Windows après redémarrage, imprimantes réseau

## Publier l'installateur (GitHub)
1. Dans Emergent : **Save → Save to GitHub** (branche `main`).
2. GitHub compile automatiquement l'installateur (onglet **Actions → Agent Windows PrintDrop**, ~5 min ; ou « Run workflow »).
3. Il est publié dans **Releases** avec un lien permanent :
   `https://github.com/<compte>/<dépôt>/releases/latest/download/PrintDrop-Setup.exe`
   (le dépôt doit être **public** pour que les boutiques puissent le télécharger sans compte GitHub).
4. Communiquez ce lien : il est enregistré dans `AGENT_DOWNLOAD_URL` et le bouton « Télécharger l'agent » s'active.
Pour une nouvelle version : modifier `AGENT_VERSION` dans le workflow puis repousser.

## Signer l'installateur (supprime l'avertissement Windows)
1. Achetez un certificat de signature de code (OV ou EV) au nom de votre société, au format `.pfx`.
   Un certificat OV réduit l'avertissement SmartScreen au fil des téléchargements ; un EV le supprime immédiatement.
   Les certificats EV délivrés sur clé matérielle (USB/HSM) ne sont pas exportables en `.pfx` : il faut alors un service de signature cloud (ex. Microsoft Trusted Signing).
2. Sur GitHub : **Settings → Secrets and variables → Actions → New repository secret**
   - `WINDOWS_CERT_PFX_BASE64` : le fichier .pfx encodé en base64 (PowerShell : `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`)
   - `WINDOWS_CERT_PASSWORD` : le mot de passe du .pfx
3. Relancez le workflow : `PrintDrop.exe` et l'installateur sont signés (horodatage DigiCert) puis vérifiés. Sans ces secrets, la compilation continue sans signature et affiche un avertissement.

## Publier une mise à jour
1. Augmentez `AGENT_VERSION` dans le workflow (et `AGENT_VERSION` dans `printdrop_agent.py`), poussez sur GitHub.
2. Dans le **Super-admin → Agent Windows**, saisissez la nouvelle version (et le lien si besoin) : les boutiques dont l'agent est plus ancien voient un avis « Nouvelle version disponible » sur la page Imprimantes.
