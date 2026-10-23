# Contrat interne v1

JSON français/UTF-8. Dates ISO. Réponses objets, erreurs `{detail: string}` avec HTTP 400/404/409/503. GET `/api/state` fournit `csrf_token`; toute mutation envoie `X-CSRF-Token`. Même origine obligatoire. Tous les chemins relatifs sont confinés à la racine documentaire ou au client.

- `GET /api/state` → `{clients:[], messages:[], settings:{}, template:{id,version,folders:[string]}, templates:[], jobs:[], events:[], folders:[string], printers:[string], csrf_token, stats:{clients,messages,pending,errors}, last_scan, sync_error}`. `settings` contient uniquement la configuration sans mot de passe. Ne pas demander un secret au formulaire : utiliser variable d’environnement ou Trousseau documenté. `folders` et `printers` peuvent être vides avant le test de connexion.
- Client: `{id,name,mailbox,folder,status:ready|error|provisioning,error,template_version,folders:[string],favorites:[string]}`.
- Message: `{id,client_id,subject,sender,recipients,date,body,status:queued|ready|error,classification:pending|classified,destination,print_status:pending|submitted|simulated|uncertain|error|historical, historical:bool,error,documents:[Document],print_jobs:[{id,document_id,status,job_id,error,created_at}]}`.
- Document: `{id,kind:email|attachment,original_name,path,name,sha256,printable,inline,selected:bool}`. `path` absolu uniquement pour affichage ; utiliser ID pour fichiers/actions.
- `POST /api/clients {name,mailbox?:str}` → client, `POST /api/clients/{id}/retry {}` reprend la création.
- `GET /api/folders` → `{folders:[string]}` effectue la connexion et expose les erreurs.
- `POST /api/sync {}` → `{ok:true}` synchronise et traite ; `POST /api/process {}` relance le contrôle/export.
- `PUT /api/template {folders:[string]}` → template versionné ; chemins avec `/` représentent la hiérarchie ; doublons, `..`, chemins absolus et noms vides rejetés.
- `POST /api/clients/{id}/template {}` → client, applique la version courante de façon additive.
- `PUT /api/clients/{id}/favorites {folders:[string]}` → client.
- `POST /api/classify {message_ids:[string],destination:string}` → `{ok:true}`. Dossier relatif au client, tous les messages du même client. Les documents restent associés ; aucun overwrite.
- `POST /api/print {message_ids:[string]}` → `{ok:true}`. Ne réimprime jamais une soumission existante ; `POST /api/messages/{id}/reprint {confirm:true}` seule action explicite pour une nouvelle impression, après vérification par l’utilisatrice.
- `PUT /api/documents/{id} {selected:bool}` → document, choix pièces à imprimer.
- `GET /api/documents/{id}/file` → fichier, `?download=true` pour téléchargement. Inline uniquement PDF/image sûr ; pas HTML actif. `POST /api/documents/{id}/reveal {}` → ouvre Finder.
- `GET /api/clients/{id}/history` → `{candidates:[{path,name,size}],note:string}`. Recherche PDF non suivis, aucune association automatique.
- `POST /api/history/associate {message_id,path}` → `{ok:true}` : association explicite d’un PDF valide contenu dans le dossier client.
- `PUT /api/settings {archive_root?,connector?,mail_account?,imap_host?,imap_port?,imap_user?,imap_password_env?,printer?,dry_run?,print_policy?,poll_seconds?,date_source?,prefix_format?,print_attachments?,client_folder_pattern?}` → settings. connector demo|imap|apple_mail, print_policy manual|after_classify|after_export, date_source received|sent, préfixes %Y-%m-%d ou %Y%m%d, client_folder_pattern contient {name} une fois sans séparateurs. Racine/connexion non modifiables quand des clients existent (nouvel espace pour migration). poll 15..3600.

Le premier scan d’un dossier marque les messages déjà présents historiques : export et classement possibles mais pas d’impression automatique. Les suivants sont nouveaux. Les identifiants métier proviennent d’une empreinte du MIME ; les identifiants source seuls ne déterminent pas une nouvelle impression.

Les modèles ont un numéro de version et une liste de chemins normalisés. L’éditeur peut ajouter, renommer, déplacer, supprimer ou dupliquer une branche en manipulant cette liste, puis enregistrer. Les anciens clients ne changent que par application additive explicite. Les favoris sont propres à chaque client. Les règles d’expéditeurs sont configurées dans Mail ; le connecteur respecte leur classement.

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
