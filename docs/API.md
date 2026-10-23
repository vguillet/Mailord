# Contrat interne v1

JSON français/UTF-8. Dates ISO. Réponses objets, erreurs `{detail: string}` avec HTTP 400/404/409/503. GET `/api/state` fournit `csrf_token`; toute mutation envoie `X-CSRF-Token`. Même origine obligatoire. Tous les chemins relatifs sont confinés à la racine documentaire ou au client.

- `GET /api/state` → `{clients:[], messages:[], settings:{}, template:{id,version,folders:[string],initial_folders:[string],email_folder:string}, templates:[], jobs:[], events:[], folders:[string], printers:[string], csrf_token, stats:{clients,messages,pending,errors}, last_scan, sync_error}`. `settings` contient uniquement la configuration sans mot de passe. Ne pas demander un secret au formulaire : utiliser variable d’environnement ou Trousseau documenté. `folders` et `printers` peuvent être vides avant le test de connexion.
- Client (dans `/api/state`) : `{id,name,mailbox,folder,status:ready|error|provisioning,error,template_version,folders:[string],existing_folders:[string],initial_folders?:[string],favorites:[string]}`.
- Message: `{id,client_id,subject,sender,recipients,date,body,status:queued|ready|error,classification:pending|classified,destination,print_status:pending|submitted|simulated|uncertain|error|historical, historical:bool,email_destination,filing_version,classification_auto_print,error,documents:[Document],print_jobs:[{id,document_id,status,job_id,error,created_at}]}`.
- Document: `{id,kind:email|attachment,original_name,path,name,sha256,printable,inline,selected:bool,destination:string,classification:pending|classified}`. `path` absolu uniquement pour affichage ; utiliser ID pour fichiers/actions.
- `POST /api/clients {name,mailbox?:str,initial_folders?:[string]}` → client, `POST /api/clients/{id}/retry {}` reprend la création.
- `GET /api/folders` → `{folders:[string]}` effectue la connexion et expose les erreurs.
- `POST /api/sync {}` → `{ok:true}` synchronise et traite ; `POST /api/process {}` relance le contrôle/export.
- `PUT /api/template {folders:[string],initial_folders?:[string],email_folder?:string}` → template versionné ; chemins avec `/` représentent la hiérarchie ; doublons, `..`, chemins absolus et noms vides rejetés.
- `POST /api/clients/{id}/template {}` → client, mémorise la version courante de façon additive sans créer de dossiers.
- `PUT /api/clients/{id}/favorites {folders:[string]}` → client.
- `POST /api/classify {message_ids:[string],destination:string,document_ids?:[string]}` → `{ok:true}`. Dossier relatif au client, tous les messages du même client. Seules les pièces jointes sont déplacées ; le PDF du mail reste dans Correspondances. `document_ids` omis sélectionne toutes les pièces des messages ; une liste cible seulement ces pièces. Liste vide, PDF de mail, identifiant étranger ou type incorrect : refus avant tout déplacement. Un message est classé seulement quand toutes ses pièces le sont ; un mail sans pièce est classé après export. Aucun overwrite. La destination peut être absente : les parents sont créés lors de la publication du premier fichier. Les branches source vidées sont retirées par `rmdir`, sans nettoyage global.
- `POST /api/print {message_ids:[string]}` → `{ok:true}`. Ne réimprime jamais une soumission existante ; `POST /api/messages/{id}/reprint {confirm:true}` seule action explicite pour une nouvelle impression, après vérification par l’utilisatrice.
- `PUT /api/documents/{id} {selected:bool}` → document, choix pièces à imprimer.
- `GET /api/documents/{id}/file` → fichier, `?download=true` pour téléchargement. Inline uniquement PDF/image sûr ; pas HTML actif. `POST /api/documents/{id}/reveal {}` → ouvre Finder.
- `GET /api/clients/{id}/history` → `{candidates:[{path,name,size}],note:string}`. Recherche PDF non suivis, aucune association automatique.
- `POST /api/history/associate {message_id,path}` → `{ok:true}` : association explicite d’un PDF valide contenu dans le dossier client.
- `PUT /api/settings {archive_root?,connector?,mail_account?,imap_host?,imap_port?,imap_user?,imap_password_env?,printer?,dry_run?,print_policy?,poll_seconds?,date_source?,prefix_format?,print_attachments?,client_folder_pattern?}` → settings. connector demo|imap|apple_mail, print_policy manual|after_classify|after_export, date_source received|sent, préfixes %Y-%m-%d ou %Y%m%d, client_folder_pattern contient {name} une fois sans séparateurs. Racine/connexion non modifiables quand des clients existent (nouvel espace pour migration). poll 15..3600.

Le premier scan d’un dossier marque les messages déjà présents historiques : export et classement possibles mais pas d’impression automatique. Les suivants sont nouveaux. Les identifiants métier proviennent d’une empreinte du MIME ; les identifiants source seuls ne déterminent pas une nouvelle impression.

Les modèles ont un numéro de version et une liste de chemins normalisés. L’éditeur peut ajouter, renommer, déplacer, supprimer ou dupliquer une branche en manipulant cette liste, puis enregistrer. Le modèle courant est proposé à tous les clients ; son application additive explicite mémorise aussi ces destinations pour les conserver après un changement de modèle. Les favoris sont propres à chaque client. Les règles d’expéditeurs sont configurées dans Mail ; le connecteur respecte leur classement.

## Mises à jour de l’application

`GET /api/state` inclut `updates`, également accessible par `GET /api/updates` : `status`, `repository`, `branch`, `current_commit`, `available_commit`, `checked_at`, `progress` (texte), `error`, `managed`. États : `unconfigured`, `idle`, `checking`, `available`, `current`, `installing`, `restarting`, `updated`, `error`.

- `PUT /api/updates/config` : `{repository, branch}` ; URL HTTPS sans identifiants ou SSH.
- `POST /api/updates/check` : lance la vérification en fond, renvoie l’état.
- `POST /api/updates/install` : `{commit}` ; commit sélectionné exact, installation en fond ; refuse session non supervisée et opération concurrente.

Mêmes protections Host, origine et CSRF que les autres mutations. Les routes privées `GET /api/health` et `POST /api/activate` exigent le jeton aléatoire `X-Supervisor-Token` transmis uniquement au processus enfant. Pendant la probation, toutes les autres routes répondent 503 ; aucune récupération ni traitement métier avant activation. Le jeton CSRF change au redémarrage : la page recharge son état avant toute nouvelle action.

## Préférences d’impression

`PUT /api/settings` et `GET /api/state.settings` incluent :

- `print_sides` : `printer` (défaut), `one-sided`, `two-sided-long-edge`, `two-sided-short-edge`.
- `print_color_mode` : `printer` (défaut), `monochrome`, `color`.

Une valeur invalide retourne 400 sans enregistrer les autres champs de la demande. Le défaut `printer` préserve les options du pilote sans modifier ses préférences globales. Chaque nouvelle intention d’impression mémorise `options: {sides, color_mode}`, `printer` et `dry_run` dans les enregistrements `print_jobs`. Une reprise `preparing` garde cet instantané ; un nouvel essai après refus certain ou une réimpression explicite prend les réglages courants. Les travaux déjà soumis, simulés ou incertains ne sont pas resoumis à cause d’un changement de préférence.

Les options s’appliquent à chaque document coché et imprimable : le PDF du mail et les pièces jointes sélectionnées. `print_attachments` définit la sélection initiale des prochaines pièces jointes exportées, sans changer les cases des documents déjà présents. La simulation ne consulte pas les imprimantes et ne soumet aucun travail.

## Destinations et existence locale

Dans `GET /api/state`, `client.folders` est le catalogue virtuel : modèle courant, destinations mémorisées, parents implicites, dossiers locaux et zone `00 - À classer`. `client.existing_folders` contient uniquement les dossiers présents sur le Mac (aucune écriture pendant cet inventaire). Les liens symboliques ne sont pas des dossiers locaux autorisés.

La création/reprise d’un client crée le dossier mail nécessaire à la surveillance, et prépare les dossiers présélectionnés ; son chemin documentaire reste réservé sans répertoire si la sélection est vide. `initial_folders` permet de créer immédiatement des dossiers vides choisis dans le modèle courant, y compris ses parents implicites. Valeur omise : présélections du modèle pour un nouveau client ; `[]` : décochage explicite ; `null`, types incorrects et chemins hors modèle : HTTP 400 avant tout effet. Seuls les choix et leurs parents sont créés, pas les enfants non cochés. La sélection persistée est rejouée par retry ; une nouvelle soumission du même client ajoute les choix sans effacer les précédents. Les dossiers sélectionnés et leurs parents sont protégés du nettoyage des branches vidées. L’application du modèle et l’ajout de favoris n’effectuent aucun `mkdir`. Les réponses de mutation client conservent leur forme de registre (modèle mémorisé) : relire `/api/state` pour obtenir le catalogue complet. Un changement de modèle ne crée ni ne déplace de fichier et ne déclenche pas d’impression.

## Correspondances et classement par pièce

Le modèle versionné contient `initial_folders` (présélections des nouveaux clients) et `email_folder` (rôle Correspondances). Les anciens modèles exposent `02 CORRESPONDANCES` comme rôle et unique présélection sans être réécrits lors de la lecture. Les options omises d’un PUT conservent les valeurs antérieures, en retirant les présélections supprimées du catalogue ; les options explicites sont validées avant enregistrement. Le dossier mail choisi doit appartenir au modèle, parents implicites compris. Le rôle est conservé dans le catalogue lors d’un PUT ancien ne fournissant que les chemins.

La reprise d’un client utilise ses propres `initial_folders` figés, même après modification du modèle. Répéter sa création sans sélection explicite ne lui applique pas de nouveaux défauts.

Au scan, `message.email_destination` fige la destination du PDF pour les réparations. Les pièces jointes commencent dans `00 - À classer`. Chaque document possède `destination` et `classification` ; `message.destination` reste un résumé des pièces (vide si plusieurs destinations ou aucune pièce). Les intentions par document `move_to`/`move_destination` sont persistées ensemble avant déplacement et reprises par le contrôle ; une nouvelle demande ne peut pas écraser une intention en cours. Les anciennes intentions de classement groupé sont encore reprises.

Au premier contrôle des anciens messages, `filing_version=2` permet leur adaptation : PDF suivi vers Correspondances, pièces et impressions préservées, aucun fichier non suivi déplacé. `classification_auto_print` évite qu’une adaptation seule déclenche une impression après classement. Les identifiants de documents et les impressions antérieures sont conservés ; les réparations retrouvent la destination de chaque pièce.
