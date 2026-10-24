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

Ouvrez « Modèle de dossiers » pour définir votre structure. Sélectionnez un dossier pour le renommer, le déplacer, le dupliquer ou ajouter un sous-dossier ; le glisser-déposer déplace une branche. Cochez dans l’arbre les dossiers à préparer par défaut pour les nouveaux clients. Enregistrez pour créer une nouvelle version. Les changements de présélection ne créent pas de dossiers chez les anciens clients. Le modèle courant est proposé à tous les clients, avec leurs destinations mémorisées et leurs dossiers déjà présents. « Mémoriser le modèle » conserve ses destinations pour un client même si le modèle change ensuite, sans créer de répertoire.

Créez ensuite un client, ou reliez son dossier mail existant. Le formulaire reprend les dossiers cochés dans le modèle ; initialement, seul `02 CORRESPONDANCES` est coché. Vous pouvez modifier ces choix pour chaque client, y compris tout décocher pour ne créer aucun dossier vide. Dans « Créer des dossiers dès maintenant (facultatif) », cochez les dossiers à préparer immédiatement. Les parents nécessaires sont créés automatiquement ; cocher un parent ne sélectionne pas ses enfants. « Tout cocher » et « Tout décocher » permettent de préparer rapidement la sélection. Ces choix sont conservés en cas de reprise de création et les dossiers sélectionnés restent présents même vides. Le PDF du mail et ses pièces jointes attendent dans `00 - À classer`, créé au besoin. Cliquez sur « Choisir un dossier… » sous le PDF ou la pièce jointe concernée. Un seul sélecteur se déplie à la fois, directement sous ce document. Recherchez un nom dans toute l’arborescence (accents et majuscules indifférents), utilisez les favoris/récents ou dépliez les branches avec leurs chevrons. Un dossier parent reste sélectionnable indépendamment de ses enfants. Aucun dossier n’est présélectionné : choisissez une destination puis « Classer ici ». Seul ce document est déplacé ; le sélecteur se replie après réussite. Pour le déplacer à nouveau, cliquez sur son dossier affiché. Les cases à gauche concernent uniquement l’impression. En cas d’erreur, le message apparaît sous le document et le choix reste disponible pour réessayer ; les actualisations en arrière-plan conservent la recherche et la sélection. Chaque document en attente affiche un badge « À CLASSER », un nom en gras et un fond ambré, dans le détail ; la liste des mails porte aussi un badge contrasté. Le mail est entièrement classé lorsque tous ses documents, y compris son PDF, le sont. Sans pièce jointe, son PDF attend également votre choix. Le sélecteur indique « Sur le Mac » ou « Sera créé ». Une destination absente reste sélectionnable, y compris ses dossiers parents. Au rangement, seule la branche nécessaire est créée. Les répertoires laissés vides par les déplacements de l’outil sont retirés en remontant la branche source ; un fichier caché, tout autre contenu ou un dossier sélectionné à la création (et ses parents) arrête ce nettoyage. Les anciens dossiers vides ne sont pas nettoyés en masse. Les favoris et les destinations récentes accélèrent les classements suivants. `J`/`K` parcourent les mails, `C` ouvre le sélecteur du premier document restant à classer (ou du premier document si tous sont classés), Échap le replie, Tab parcourt les commandes et Entrée active le choix ou valide depuis la recherche lorsqu’une destination est choisie. Espace sélectionne un mail, `/` recherche un client.

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

Avant utilisation quotidienne, essayez sur le Mac cible : un mail texte, un mail HTML, un PDF joint, une image jointe, un format non imprimable, le classement séparé du PDF et d’une pièce jointe, un réveil après veille, puis une impression de quelques pages. Comparez les PDF aux mails originaux. Le service et ses adaptateurs sont testés automatiquement ; ce contrôle confirme les permissions, les formats du compte et le comportement réel de l’imprimante.

Références techniques : [IMAP Python](https://docs.python.org/3/library/imaplib.html), [RFC 3501](https://datatracker.ietf.org/doc/html/rfc3501), [CUPS lp](https://www.cups.org/doc/man-lp.html), [CUPS lpstat](https://www.cups.org/doc/man-lpstat.html). Le dictionnaire Apple Mail du Mac a été inspecté et le script JXA compilé sans lire de messages personnels.

## Mises à jour sans terminal

Les lancements habituels utilisent désormais un superviseur local. Après une première installation de cette fonctionnalité, fermer puis relancer une fois le service. Configurer le dépôt et la branche dans **Mises à jour**. Voir [le guide des mises à jour](UPDATES.md) pour le bouton, les accès privés et les limites du retour automatique. Conserver le dossier d’installation initial et sa `.venv` : ils servent de lanceur stable.

## Recto verso, couleur et pièces jointes

Dans **Réglages → Impression**, choisir les **Faces à imprimer** : réglage de l’imprimante, recto seul, recto verso avec retournement sur le bord long (comme un livre) ou le bord court (comme un bloc-notes). Choisir ensuite **Couleur** : réglage de l’imprimante, noir et blanc ou couleur. Enregistrer les réglages ; ils sont conservés au redémarrage et s’appliquent aux prochaines soumissions. Ils ne modifient ni les documents archivés ni les préférences des autres applications.

Le service imprime **le PDF du mail et les pièces jointes imprimables cochées**. Les PDF valides, images et textes compatibles sont pris en charge. Les documents Word/Excel et autres formats non compatibles sont archivés mais pas convertis pour impression. Les images intégrées aux messages (par exemple les signatures) sont exclues par défaut. Chaque document apparaît avec sa propre case dans le détail du mail : il est possible de n’imprimer que le mail, que certaines pièces jointes, ou les deux.

**Inclure les pièces jointes imprimables** définit leur sélection lors des prochains exports. Pour un mail déjà présent, utiliser les cases de ses documents. Chaque fichier constitue un travail séparé : le recto verso concerne ses pages et ne place pas automatiquement la première pièce jointe au dos du mail. Changer ces préférences ne relance aucune impression déjà soumise.

Le mode simulation reste actif par défaut et n’imprime aucun papier. La prise en charge physique du recto verso et de la couleur dépend de l’imprimante et de son pilote ; elle reste à essayer sur le matériel cible. Le service transmet les [options CUPS par travail](https://openprinting.github.io/cups/doc/options.html) et les options `Duplex` / `ColorModel` reconnues quand elles sont annoncées par le pilote. Les options globales du Mac ne sont pas modifiées. Un mode absent des choix reconnus du pilote est refusé avec une erreur lisible ; si aucune description du pilote n’est disponible, les options standard sont transmises.

### Passage au classement manuel de tous les documents

Cette mise à jour conserve les emplacements et les statuts des PDF et pièces jointes déjà suivis, ainsi que les présélections des modèles et les impressions existantes. Les anciens PDF rangés automatiquement dans Correspondances peuvent désormais être déplacés avec le même bouton que les autres documents. Les nouveaux exports attendent tous le choix de l’utilisateur. Le contrôle reprend les intentions de déplacement interrompues et répare les fichiers manquants à leur emplacement enregistré ; il ne redistribue pas les archives à cause de cette mise à jour.

L’impression « Quand tous les documents sont classés » attend le PDF du mail et toutes ses pièces jointes, même celles décochées pour l’impression. Pour un nouveau mail sans pièce jointe, elle attend le classement de son PDF. L’option « Dès que les fichiers sont exportés » reste disponible si l’impression doit précéder le classement. L’historique reste exclu des impressions automatiques ; aucun ancien document n’est réimprimé à cause de cette mise à jour.
