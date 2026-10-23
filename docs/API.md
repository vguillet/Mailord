# Contrat interne v1

JSON français/UTF-8. Dates ISO. Réponses objets, erreurs `{detail: string}` avec HTTP 400/404/409/503. GET `/api/state` fournit `csrf_token`; toute mutation envoie `X-CSRF-Token`. Même origine obligatoire. Tous les chemins relatifs sont confinés à la racine documentaire ou au client.

- `GET /api/state` → `{clients:[], messages:[], settings:{}, template:{id,version,folders:[string]}, templates:[], jobs:[], events:[], folders:[string], printers:[string], csrf_token, stats:{clients,messages,pending,errors}, last_scan, sync_error}`. `settings` contient uniquement la configuration sans mot de passe. Ne pas demander un secret au formulaire : utiliser variable d’environnement ou Trousseau documenté. `folders` et `printers` peuvent être vides avant le test de connexion.
- Client: `{id,name,mailbox,folder,status:ready|error|provisioning,error,template_version,folders:[string],favorites:[string]}`.
- Message: `{id,client_id,subject,sender,recipients,date,body,status:queued|ready|error,classification:pending|classified,destination,print_status:pending|submitted|simulated|uncertain|error|historical, historical:bool,error,documents:[Document]}`.
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
