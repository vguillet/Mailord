# Installer et utiliser Auto-secrétaire sur Mac

## Installation

Prérequis : macOS, Python 3.11 ou plus, un navigateur récent. Le service doit fonctionner dans la session de l’utilisatrice. Le Mac doit être allumé ; après une veille, la relève reprend au réveil.

1. Copiez le projet dans un dossier permanent du Mac.
2. Exécutez `bash scripts/install-macos.sh` dans ce dossier. L’installation crée un environnement Python isolé et installe les dépendances. Une connexion internet est nécessaire pour cette étape.
3. Double-cliquez `scripts/start.command` pour essayer la démonstration. Lors du premier essai, macOS peut demander d’autoriser l’ouverture du script.
4. Pour l’espace réel, lancez `.venv/bin/python -m autosecretaire --open`. Ce lancement est distinct de la démonstration. Une seule instance peut utiliser un même espace ; utilisez un autre port si la démo tourne encore.

Par défaut, le registre et les messages originaux résident dans `~/Library/Application Support/Auto-secretaire/data`. La démonstration utilise `.../demo`. Une racine `Archives` est créée dans cet espace jusqu’à modification. Ces données ne sont jamais enregistrées dans le dépôt de code.

Options utiles : `--data-dir /chemin/prive` pour un autre espace, `--archive-root /chemin/archives` lors de son premier lancement, `--port 8766` pour une seconde instance distincte. Une racine déjà enregistrée dans les réglages reste prioritaire.

## Choisir l’origine des messages

**Apple Mail** est le choix adapté aux dossiers « Sur mon Mac ». Dans Réglages, choisissez Apple Mail. Laissez le nom de compte vide pour les boîtes locales ; sinon saisissez le nom exact du compte affiché dans Mail. Testez ensuite la liste des dossiers depuis « Nouveau client → Relier un dossier existant → Actualiser ».

À la première connexion, macOS peut demander l’autorisation de contrôler Mail. Acceptez-la pour le processus de lancement utilisé. En cas de refus, vérifiez Réglages Système → Confidentialité et sécurité → Automatisation, pour Terminal ou le processus Python concerné. Mail doit avoir téléchargé le contenu intégral des messages et pièces jointes. L’adaptateur utilise le dictionnaire de script public de Mail, jamais sa base privée. Vérifiez sur quelques mails représentatifs le contenu et les caractères accentués, notamment les anciens encodages.

**Orange IMAP** convient si les dossiers existent sur le serveur Orange : serveur `imap.orange.fr`, port `993`, connexion TLS, adresse mail complète. Les dossiers uniquement « Sur mon Mac » ne sont pas visibles par IMAP. Le mot de passe dédié aux applications est configuré hors du navigateur, via la variable `AUTOSECRETAIRE_IMAP_PASSWORD` au lancement. Ne le saisissez pas dans le champ « Nom de la variable » : ce champ contient uniquement le nom de la variable.

Exemple de lancement interactif zsh, sans enregistrer le mot de passe dans l’historique :

```sh
read -s 'AUTOSECRETAIRE_IMAP_PASSWORD?Mot de passe dédié Orange : '
export AUTOSECRETAIRE_IMAP_PASSWORD
.venv/bin/python -m autosecretaire --open
unset AUTOSECRETAIRE_IMAP_PASSWORD
```

Cette variable doit rester disponible dans l’environnement du service pendant son fonctionnement. Le LaunchAgent fourni ne stocke pas le secret : pour un démarrage automatique IMAP, préparez un mécanisme local de chargement du secret, ou utilisez Apple Mail qui gère déjà le compte. Ne placez pas les identifiants dans le dépôt, les archives ou le fichier LaunchAgent.

Les lectures IMAP utilisent une sélection en lecture seule et `BODY.PEEK` pour ne pas marquer les mails comme lus. Les opérations de création concernent uniquement les dossiers demandés. Aucun mail n’est envoyé, supprimé ou déplacé par ce service.

## Configurer le rangement

Avant le premier client, choisissez dans Réglages le dossier local que votre fournisseur cloud synchronise déjà. Gardez le registre privé hors de cette racine. Le service refuse le changement de racine ou de source après création de clients pour ne pas casser leurs associations ; une migration utilise un nouvel espace privé et le rattachement explicite des dossiers existants.

Ouvrez « Modèle de dossiers » pour définir votre structure. Sélectionnez un dossier pour le renommer, le déplacer, le dupliquer ou ajouter un sous-dossier ; le glisser-déposer déplace une branche. Enregistrez pour créer une nouvelle version. « Compléter les dossiers » applique cette version à un client en ajoutant les dossiers manquants. Aucun dossier existant n’est renommé ou supprimé automatiquement.

Créez ensuite un client, ou reliez son dossier mail existant. Les messages en attente arrivent dans `00 - À classer`, créé au besoin. Choisissez une destination par mail ou sélectionnez plusieurs mails d’un même client. Les favoris et les destinations récentes accélèrent les classements suivants. `J`/`K` parcourent les mails, `C` ouvre le classement, Espace sélectionne, `/` recherche un client.

Les règles d’expéditeur se configurent dans Mail : une règle « De contient l’adresse → Déplacer vers le dossier client » permet au service de détecter le message au prochain contrôle. Les règles Mail peuvent nécessiter que Mail reste ouvert.

## Date et noms

Par défaut : `2026-10-23 - Nom du document.pdf`. Les pièces jointes conservent leur nom de base ; le PDF du mail utilise son objet. La date est celle de réception, dans le fuseau Europe/Paris. Repli : date du mail, puis première découverte persistée. La date d’envoi et le préfixe compact `AAAAMMJJ -` sont proposés dans les réglages. Les nouvelles règles concernent les futurs exports ; les fichiers déjà suivis gardent leur nom lors des réparations ou reclassements.

Les séparateurs dangereux sont neutralisés et les collisions reçoivent un suffixe stable ou numéroté. Le registre et une empreinte du contenu permettent de distinguer une reprise d’un nouveau document.

## Impression

Commencez avec « Simuler les impressions » activé. Pour du papier réel, choisissez « Rechercher » puis le nom exact d’une imprimante configurée sur le Mac et désactivez la simulation. Une imprimante vide ne permet pas l’impression réelle. Le mode de démonstration conserve obligatoirement la simulation.

Choisissez le moment : à la demande, après classement (défaut) ou après export. Les mails déjà présents à la première relève sont historiques et ne sont jamais imprimés automatiquement. Vous pouvez les imprimer explicitement. Cochez les documents souhaités ; les images intégrées aux signatures et les formats non pris en charge sont exclus par défaut.

« Soumis » confirme que CUPS a reçu le document ; cela ne prouve pas une sortie papier. Si le résultat est incertain, vérifiez la file du Mac et les feuilles sorties avant « Réimprimer ». Une nouvelle impression nécessite confirmation et concerne les documents cochés. « Imprimer » reprend les échecs confirmés sans renvoyer les documents déjà soumis. Les erreurs et incertitudes sont visibles dans le détail.

Une impression simulée reste enregistrée comme simulée. Après désactivation de la simulation, utilisez « Réimprimer » pour obtenir volontairement un exemplaire papier d’un document déjà simulé.

## Anciens PDF et fichiers modifiés

Dans un client, « Retrouver des PDF existants » liste les PDF locaux non suivis. Vérifiez le fichier dans le Finder, choisissez son mail et confirmez l’association. Les doublons et ressemblances ne sont pas assimilés automatiquement à une preuve d’archivage.

« Contrôler les fichiers » vérifie les empreintes et les PDF puis remet en file ce qui manque. Un fichier suivi modifié est copié dans `quarantine` de l’espace privé avant réparation. Les liens symboliques sont refusés. Utilisez l’interface pour déplacer les fichiers suivis : un déplacement manuel dans le Finder sera vu comme une absence, et provoquera la régénération à l’emplacement enregistré. L’ancien fichier déplacé reste conservé et peut être associé explicitement.

## Démarrage automatique facultatif

Après essai de l’espace réel, générez son LaunchAgent :

```sh
.venv/bin/python scripts/launchagent.py --data-dir "$HOME/Library/Application Support/Auto-secretaire/data"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/fr.autosecretaire.local.plist"
```

Le générateur refuse d’écraser un fichier existant. Il ne lance rien lui-même. Pour désactiver le lancement :

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/fr.autosecretaire.local.plist"
```

Les journaux sont dans l’espace privé. Les autorisations Mail du lancement automatique doivent être testées séparément. Le dossier du projet doit rester au même endroit, car le LaunchAgent référence son environnement Python.

## Sauvegarde et contrôle sur place

Arrêtez le service avant de sauvegarder l’ensemble de l’espace privé (registre SQLite, messages originaux, quarantaine) et les archives. La copie cloud des seuls PDF ne suffit pas à restaurer le suivi des impressions. Pour restaurer, replacez registre et fichiers aux mêmes chemins ; sinon utilisez un nouvel espace et le rapprochement historique.

Avant utilisation quotidienne, essayez sur le Mac cible : un mail texte, un mail HTML, un PDF joint, une image jointe, un format non imprimable, un classement en lot, un réveil après veille, puis une impression de quelques pages. Comparez les PDF aux mails originaux. Le service et ses adaptateurs sont testés automatiquement ; ce contrôle confirme les permissions, les formats du compte et le comportement réel de l’imprimante.

Références techniques : [IMAP Python](https://docs.python.org/3/library/imaplib.html), [RFC 3501](https://datatracker.ietf.org/doc/html/rfc3501), [CUPS lp](https://www.cups.org/doc/man-lp.html), [CUPS lpstat](https://www.cups.org/doc/man-lpstat.html). Le dictionnaire Apple Mail du Mac a été inspecté et le script JXA compilé sans lire de messages personnels.
