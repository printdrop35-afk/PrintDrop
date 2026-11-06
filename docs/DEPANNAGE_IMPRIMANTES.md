# Dépannage des imprimantes PrintDrop

| Symptôme | Cause probable | Que faire |
|---|---|---|
| « Agent Windows hors ligne » | PC éteint, PrintDrop fermé, pas d'Internet | Rallumez le PC, lancez PrintDrop (icône Bureau). Il redémarre seul avec Windows si l'option a été cochée. |
| Imprimante absente de la liste | Pilote non installé / imprimante non ajoutée à Windows | Installez le pilote du fabricant, vérifiez qu'elle apparaît dans *Paramètres Windows → Imprimantes*, puis « Détecter les imprimantes USB ». |
| Découverte réseau vide | Imprimante sur un autre réseau/VLAN, pare-feu, Wi-Fi invité | Mettez le PC et l'imprimante sur le même réseau. Imprimez la page de configuration réseau de l'imprimante pour lire son IP, puis « Configuration manuelle ». |
| « injoignable depuis ce PC » | Mauvaise IP, imprimante en veille profonde, port fermé | Vérifiez l'IP (elle peut changer : réservez-la dans la box), essayez IPP (631) puis RAW (9100). |
| Connexion affichée « Réseau (à préciser) » | Windows ne sait pas si l'imprimante est en Wi-Fi ou en Ethernet | Choisissez « Wi-Fi » ou « Ethernet » sur la fiche de l'imprimante. |
| « ne prend pas en charge le format A3 / la couleur / le recto-verso » | Capacités lues dans le pilote | Choisissez une autre imprimante proposée, ou créez une règle d'affectation. |
| « En attente de réessai » | Imprimante hors ligne au moment de l'envoi | Rien n'a été imprimé. Remettez l'imprimante en ligne : le travail repart seul (30 s) ou réaffectez-le dans la File d'impression. |
| « Statut inconnu (agent déconnecté pendant l'impression) » | Coupure pendant l'envoi | Vérifiez le bac de sortie AVANT de cliquer « Réimprimer » (pas de réimpression automatique, pour éviter les doublons). |
| « Travail toujours en file après 10 min » | Bourrage, papier, file Windows bloquée | Résolvez le problème sur l'imprimante ; au besoin videz la file Windows, puis réimprimez. |
| Statut « terminé selon le pilote » mais rien en sortie | Le pilote a accepté le travail sans l'imprimer | Imprimez une page de test ; réinstallez le pilote. PrintDrop ne peut pas voir le papier sortir. |

Fichiers : journal `%LOCALAPPDATA%\PrintDrop\agent.log` (aucun contenu de document), temporaires `%LOCALAPPDATA%\PrintDrop\tmp` (vidés après chaque travail et au démarrage).
