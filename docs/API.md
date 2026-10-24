# Contrat interne v1

JSON français/UTF-8. Dates ISO. Réponses objets, erreurs `{detail: string}` avec HTTP 400/404/409/503. GET `/api/state` fournit `csrf_token`; toute mutation envoie `X-CSRF-Token`. Même origine obligatoire. Tous les chemins relatifs sont confinés à la racine documentaire ou au client.

- `GET /api/state` → `{clients:[], messages:[], settings:{}, template:{id,version,folders:[string],initial_folders:[string],email_folder?:string}, templates:[], jobs:[], events:[], folders:[string], printers:[string], csrf_token, stats:{clients,messages,pending,errors}, last_scan, sync_error}`. `settings` contient uniquement la configuration sans mot de passe. Ne pas demander un secret au formulaire : utiliser variable d’environnement ou Trousseau documenté. `folders` et `printers` peuvent être vides avant le test de connexion.
- Client (dans `/api/state`) : `{id,name,mailbox,folder,status:ready|error|provisioning,error,template_version,folders:[string],existing_folders:[string],initial_folders?:[string],favorites:[string],starred:bool}`.
- Message: `{id,client_id,subject,sender,recipients,date,body,status:queued|ready|error,classification:pending|classified,destination,print_status:pending|partial|submitted|simulated|mixed|uncertain|error|preparing|submitting|historical|not_selected,print_progress:{total,submitted,simulated,pending,error,uncertain,preparing,submitting}, historical:bool,filing_version,classification_auto_print,error,documents:[Document],print_jobs:[{id,document_id,status,job_id,error,created_at}]}`.
- Document: `{id,kind:email|attachment,original_name,path,name,sha256,printable,inline,selected:bool,destination:string,classification:pending|classified,undo_filing?:{token,path,destination,classification,target_path}}`. `path` absolu uniquement pour affichage ; utiliser ID pour fichiers/actions.
- `POST /api/clients {name,mailbox?:str,initial_folders?:[string]}` → client, `POST /api/clients/{id}/retry {}` reprend la création.
- `GET /api/folders` → `{folders:[string]}` effectue la connexion et expose les erreurs.
- `POST /api/sync {}` → `{ok:true}` synchronise et traite ; `POST /api/process {}` relance le contrôle/export.
- `PUT /api/template {folders:[string],initial_folders?:[string],email_folder?:string}` → template versionné ; chemins avec `/` représentent la hiérarchie ; doublons, `..`, chemins absolus et noms vides rejetés.
- `POST /api/clients/{id}/template {}` → client, mémorise la version courante de façon additive sans créer de dossiers.
- `PUT /api/clients/{id}/favorites {folders:[string]}` → client.
- `PUT /api/clients/{id}/star {starred:bool}` → client. Booléen strict ; champ absent sur un ancien client exposé comme false sans réécriture. Indépendant des favoris de dossiers.
- `POST /api/classify {message_ids:[string],destination:string,document_ids?:[string]}` → `{ok:true}`. Dossier relatif au client, tous les messages du même client. Tous les documents sont éligibles, PDF du mail compris. `document_ids` omis sélectionne tous les documents des messages ; une liste cible seulement ces documents. Liste vide, identifiant étranger ou type incorrect : refus avant tout déplacement. Un message est classé seulement quand tous ses documents le sont ; un mail sans pièce attend le classement de son PDF. Aucun overwrite. La destination peut être absente : les parents sont créés lors de la publication du premier fichier. Les branches source vidées sont retirées par `rmdir`, sans nettoyage global.
- `POST /api/print {message_ids:[string]}` → `{ok:true}`. Ne réimprime jamais une soumission existante ; `POST /api/messages/{id}/reprint {confirm:true}` action explicite pour une nouvelle impression des documents cochés, après vérification par l’utilisatrice.
- `POST /api/documents/{id}/print {}` → travail `{id,message_id,document_id,status,job_id,error,created_at,options,printer,dry_run}`. Portée limitée au document, ignore sa case sans la modifier ; conserve la génération initiale et ne soumet pas à nouveau un résultat déjà envoyé ou incertain. Un échec certain peut être repris. Document inconnu : 404 ; non imprimable, non exporté ou fichier manquant/modifié : 400 avant soumission.
- `POST /api/documents/{id}/reprint {confirm:true}` → nouveau travail pour ce document seulement, avec les préférences actuelles. Confirmation booléenne explicite obligatoire. Les états error/uncertain du travail sont retournés même si le traitement HTTP a réussi ; l’interface doit les afficher.
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

## Présélections et classement manuel par document

Le modèle versionné contient `initial_folders` (présélections des nouveaux clients). Un ancien modèle sans ce champ expose `02 CORRESPONDANCES` comme unique présélection si ce chemin figure dans sa liste ; sinon la présélection est vide. La lecture ne réécrit pas le modèle. Un PUT sans présélections conserve les anciennes, en retirant les chemins supprimés du catalogue ; les options explicites sont validées avant enregistrement. `email_folder` reste accepté pour compatibilité comme métadonnée sans effet sur le classement : s’il est fourni, son chemin doit appartenir au modèle, parents implicites compris. Il n’impose plus l’ajout d’une rubrique Correspondances et n’est plus proposé dans l’interface.

La reprise d’un client utilise ses propres `initial_folders` figés, même après modification du modèle. Répéter sa création sans sélection explicite ne lui applique pas de nouveaux défauts.

Chaque nouveau message utilise `filing_version=3`. Son PDF et toutes ses pièces jointes commencent dans `00 - À classer`, avec `classification=pending`. Chaque document possède `destination` et `classification` ; `message.destination` résume tous les documents (vide si plusieurs destinations). Les intentions par document `move_to`/`move_destination` sont persistées ensemble avant déplacement et reprises par le contrôle ; une nouvelle demande ne peut pas écraser une intention en cours. Les anciennes intentions de classement groupé sont encore reprises.

Au premier contrôle des anciens messages, l’adaptation vers `filing_version=3` conserve les chemins et classifications de chaque document existant ; si ces métadonnées manquent, elle reprend le parent réel et l’état du message. Elle retire l’ancien `email_destination` sans déplacer le PDF. `classification_auto_print` préserve la protection contre une impression due à l’adaptation seule. Les identifiants et impressions antérieures sont conservés ; les réparations retrouvent la destination enregistrée de chaque document. La politique `after_classify` attend désormais tous les documents, PDF du mail inclus, indépendamment de leur sélection pour l’impression.


## Progression courante et annulation de classement

`message.print_progress` compte les documents imprimables cochés ainsi que les documents décochés ayant déjà une tentative. Chaque document contribue une fois, selon sa dernière intention (ordre de création dans le registre). `submitted` et `simulated` sont distincts ; `partial` signifie qu’une partie seulement est terminée, `mixed` que les résultats complets mêlent simulation et soumission. Sans document éligible : `not_selected`. Une incertitude reste visible même si sa case est décochée. Les tentatives antérieures restent dans `print_jobs` ; elles ne maintiennent plus à elles seules un statut d’erreur. Une commande print ordinaire reprend uniquement la dernière intention en erreur certaine ou préparée ; elle ne réactive jamais une ancienne génération dépassée. Une soumission reste distincte de la sortie physique du papier.

`POST /api/documents/{id}/undo-filing {token:string}` → document restauré. Utiliser le jeton `undo_filing.token` du dernier classement ; le bouton apparaît seulement lorsqu’un classement effectué depuis cette version est annulable. Le chemin, la destination et le statut antérieurs sont conservés après redémarrage. Répéter le même jeton déjà appliqué est sans effet supplémentaire. Une nouvelle opération de classement remplace cet historique d’un seul niveau.

Document inconnu : 404. Jeton absent/obsolète, fichier manquant/modifié, ancienne destination occupée, lien symbolique ou déplacement non résolu : 400 sans écrasement. Après interruption, le contrôle reprend `move_to`, `move_destination` et `move_classification`. L’annulation ne crée pas de travail d’impression et désactive le déclenchement après classement pour ce message jusqu’au prochain classement explicite ; une impression déjà envoyée reste inchangée. Archives antérieures : aucun déplacement, aucune nouvelle impression, aucune migration de table.
