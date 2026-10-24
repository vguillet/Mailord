# Vérification de la version locale — 23 octobre 2026

## Résultats observés

- Suite complète : **99 tests réussis**, aucun échec ni test sauté.
- Installation dans un environnement Python isolé à partir des dépendances verrouillées : réussie.
- JavaScript : syntaxe vérifiée par Node ; tests des transformations de l’arbre, échappement du contenu, contrats et structure accessible.
- Scripts de lancement : syntaxe shell vérifiée ; aide du programme exécutée ; LaunchAgent généré dans un dossier temporaire et validé par `plutil`, sans activation.
- Connecteur Apple Mail : script JXA compilé par `osacompile` sans exécuter Mail.

Le test avec Python 3.14 signale un avertissement de dépréciation de l’adaptateur de test Starlette/httpx. Il n’empêche aucun test ; il concerne le client utilisé par les tests, pas une erreur constatée du service.

## Parcours vérifié dans Chrome

Service réellement lancé sur `127.0.0.1:8765`, espace de démonstration temporaire, sans compte personnel ni impression papier.

1. Affichage de trois clients et sept mails fictifs avec leurs fichiers PDF et pièces jointes.
2. Création de « Test Parcours » depuis le formulaire : dossier mail de démonstration et arborescence locale créés.
3. Ajout de deux messages fictifs au dossier surveillé puis relève : deux exports prêts, fichiers distincts malgré les pièces de même nom.
4. Classement d’un mail vers Documents, puis classement groupé des deux mails vers Facturation : chemins actualisés et impressions simulées suivies sans double soumission.
5. Ajout visuel de « 05 - Juridique » au modèle, enregistrement de la version 2 et application additive au client.
6. Ouverture de l’aperçu PDF dans l’interface. Aucun avertissement ni erreur de console constaté pendant ces parcours.
7. Contrôle de la largeur de page : aucun débordement horizontal à 500 px de largeur effective ni à la largeur de bureau. Le navigateur a imposé un minimum de 500 px au redimensionnement ; aucun essai physique sur téléphone n’est revendiqué.

Un arrêt volontaire du service a également été testé : l’interface a affiché « Le service local ne répond pas » sans confirmer la relève.

Les API sont aussi exercées automatiquement : protection d’origine et de session, paramètres, création de client, fichiers PDF, classement, impression simulée et refus d’une réimpression non confirmée.

## Reprise et sécurité des documents

Tests de fichiers manquants/corrompus, conservation des originaux, doublons, collisions de noms, reprise d’un déplacement interrompu, refus des traversées de chemins et des liens symboliques internes ou externes. Les essais de panne distinguent préparation non soumise, rejet confirmé et soumission incertaine. Une seconde instance est refusée avant toute récupération du registre. Les corrections issues de la revue sont enregistrées dans les exécutions MDSE.

## Essais restant à réaliser sur le Mac cible

Ce sont des **validations terrain non effectuées**, distinctes de la vérification logicielle :

- Compte Orange, mot de passe dédié et droits de création des dossiers ; présence effective des dossiers IMAP.
- Dossiers Apple Mail « Sur mon Mac » ou compte nommé, autorisations d’automatisation, encodages et pièces jointes effectivement téléchargées.
- Imprimante réelle, USB ou réseau, options et sortie papier ; permissions lors du démarrage automatique.
- Arborescence choisie par l’utilisatrice, volume réel de mails et comportement du fournisseur de synchronisation.

Aucun compte de messagerie personnel n’a été consulté, aucun mail envoyé et aucune page imprimée pendant le développement.

## Limites explicites

- Rendu HTML sous forme de texte structuré ; pas de fidélité graphique exacte.
- PDF, images et texte imprimables ; formats Office et autres conservés sans conversion automatique.
- Reclassements à effectuer dans l’interface. Un déplacement manuel de fichier déclenche sa régénération à l’emplacement suivi, avec rapprochement explicite possible.
- Copies de messages identiques dédupliquées par empreinte MIME. Un mail réécrit par un serveur avec un contenu MIME différent peut être considéré comme distinct. Les copies identiques vues chez plusieurs clients restent associées au client d’origine et produisent un événement d’avertissement.
- Service natif macOS, sans paquet Docker ni application signée. Le service s’arrête quand le Mac est éteint.

## Mises à jour — 24 octobre 2026

- Suite complète : **136 tests réussis**, aucun échec ni test sauté (Python 3.11 et environnement installé Python 3.14). Ce dernier émet l’avertissement Starlette/httpx déjà connu, sans échec.
- Git réel sur dépôts temporaires : détection de branche, commit sélectionné conservé même après un autre commit, copie isolée, manifeste incompatible et erreurs de transport.
- Processus et HTTP réels : bascule réussie, nouvelle session CSRF, conservation des clients et documents, relancement ultérieur depuis le lanceur initial ; candidate volontairement défectueuse restaurée automatiquement. Environnement Python partagé dans ces deux tests de processus pour ne pas télécharger de dépendances à chaque exécution.
- Installation réelle des dépendances verrouillées dans un environnement Python 3.14 neuf : réussie ; imports applicatifs vérifiés.
- Parcours Chrome réel sur démonstration isolée : panneau non configuré, détection d’une version sur dépôt Git de test local, clic **Mettre à jour**, installation effective des dépendances, bascule et rechargement automatique du navigateur. Version cible `b511994610c2b2a053ea5c5b1a6f6f81840f0bb0`, état final `current`, 3 clients et 7 mails conservés, intention de mise à jour effacée après succès. Ce commit appartient uniquement au dépôt temporaire de validation.
- Les routes de contrôle privées refusent un jeton absent/invalide ; la probation bloque l’API métier et ne récupère pas les impressions avant activation.
- Le dépôt distant définitif et ses éventuels identifiants restent à configurer. Aucun push réel, compte Orange, autorisation Apple Mail ou périphérique d’impression n’a été utilisé pour cet essai. Le rollback est limité à la phase précédant l’activation ; une régression après activation demande une version corrective.

## Préférences d’impression — 24 octobre 2026

- **154 tests réussis**, dont 18 nouveaux cas de préférences, dans l’environnement Python 3.14 installé. Avertissement Starlette/httpx déjà présent, sans échec.
- Contrôle de la persistance API et du redémarrage, des valeurs invalides et de l’atomicité des réglages ; vérification des arguments CUPS et des choix de pilotes simulés, du mode simulation sans appel système, de la reprise des intentions et de l’absence de doublons après changement des préférences.
- Chrome réel sur une démonstration isolée : sélection et enregistrement « Recto verso · bord long » + « Noir et blanc », rechargement puis relecture des choix. Impression simulée du PDF d’un mail et de sa pièce jointe texte : deux travaux `simulated` portant les mêmes options `two-sided-long-edge` et `monochrome`. Aucune erreur console.
- Aucun travail matériel soumis. Le comportement physique sur le pilote et l’imprimante cible reste à vérifier ; les modes standard CUPS sont transmis, avec traduction des choix `ColorModel` / `Duplex` reconnus quand le pilote les annonce.

## Modèle du cabinet — 24 octobre 2026

- Les quatre pages du PDF fourni ont été lues et rendues visuellement. Sa première page est transcrite dans le modèle initial : 37 chemins, dont huit rubriques métier, sept catégories de correspondances, quatorze sous-rubriques par juridiction et la zone d’attente. Les annotations sont séparées des noms de dossiers ; voir `docs/FOLDER_TEMPLATE.md`.
- Inspection sur un registre temporaire : création effective des 37 dossiers ; modèle personnalisé conservé après réinstanciation du moteur ; refus de `../hors-racine` sans modification ; application additive conservant un fichier témoin et le préfixe `%Y-%m-%d`.
- Suite complète : **154 tests réussis**, aucun échec ni test sauté, Python 3.14 installé. Les destinations des fixtures suivent les nouveaux noms ; assertions de collision, reprise, impression et API conservées. Avertissement Starlette/httpx préexistant.
- Chrome réel sur la démonstration isolée du port 8877 : 37 nœuds affichés, repères de classement accessibles et texte vérifié ; branche de juridiction renommée `TJ Paris`, dupliquée puis renommée `CA Paris`, enregistrée avec ses 14 enfants dans chaque branche. Création depuis le formulaire de `DUPONT-MARTIN (div)` : état prêt, dossier mail de démonstration et 52 dossiers locaux. Aperçu des chemins et formulaire contrôlés visuellement. Aucun compte réel ni imprimante sollicité.
- Les règles de rédaction, double classement, classement indépendant des pièces jointes et fusion d’annexes du PDF ne sont pas des automatismes livrés par cette modification de modèle.

## Dossiers créés à la demande — 24 octobre 2026

Cette évolution remplace la création physique immédiate décrite dans la vérification précédente du modèle du cabinet. Le modèle de 37 destinations est inchangé ; son utilisation sur disque devient progressive.

- TDD ciblé : premier passage de 9 tests, 8 échecs attendus et 1 protection déjà assurée ; après implémentation, 9 réussites. Une vérification supplémentaire d’un nom de dossier importé contenant des espaces a révélé un rejet excessif de l’inventaire ; corrigé en conservant la validation stricte pour les écritures seulement.
- Suite complète après le comportement à la demande : **164 tests réussis**, aucun échec ni test sauté, Python 3.14 installé. Avertissement Starlette/httpx préexistant. Les fixtures de collisions et de mises à jour créent désormais explicitement leurs fichiers/dossiers préexistants ; leurs assertions de conservation restent présentes.
- `tests/test_lazy_folders.py` : création/reprise sans racine client vide, parents virtuels, modèle courant pour ancien client, favoris et version mémorisée après redémarrage, création d’une seule branche au classement, empreintes conservées, nettoyage des ancêtres vides, maintien des fichiers cachés et branches sans rapport, échec d’export et source absente sans dossier inutile, liens symboliques rejetés, reprise d’un déplacement interrompu, échec de publication puis reprise, inventaire API sans écritures et compatibilité des noms existants.
- Chrome réel sur espace temporaire `mailord-lazy-browser`, port 8878 : 37 destinations proposées alors que Camille Moreau ne possède que `00 - À classer` et `03 MAILS (PDF)`. Recherche Expertise, sélection de la branche absente marquée « Créé au classement », ajout aux favoris puis validation. Deux fichiers (mail et pièce jointe) rangés, empreintes inchangées, trois répertoires nécessaires créés sous `04 PROCÉDURE` ; l’ancien dossier `03 MAILS (PDF)` vidé a disparu. Les autres mails de la zone d’attente sont conservés. À la réouverture du sélecteur, la destination est marquée « Sur le Mac », toujours favorite. Impression historique inchangée.
- Aucun nettoyage global des anciens répertoires, aucune connexion à une messagerie personnelle et aucune impression papier. Les nouveaux dossiers mail de surveillance restent créés normalement ; la règle de création à la demande concerne les archives locales.

### Sélection initiale facultative — 24 octobre 2026

- Extension demandée pendant le travail : choix de dossiers vides à créer immédiatement. Les dix cas supplémentaires ont d’abord échoué, puis les vingt cas de `tests/test_lazy_folders.py` ont réussi. Suite complète finale : **174 tests réussis**, zéro échec ou test sauté ; même avertissement Starlette/httpx préexistant. Syntaxe JavaScript contrôlée.
- Couverture : sélection d’un parent sans ses enfants, parents implicites, absence de sélection par défaut, chemins invalides refusés avant effets, API rejetant null et types incorrects, reprise après création partielle sans perte de fichier, ajout idempotent de choix pour un client existant, persistance et protection des branches volontairement vides après changement de modèle, redémarrage et reclassement.
- Chrome réel, port 8878 : formulaire avec 37 cases toutes décochées ; Tout cocher donne 37, Tout décocher donne 0. Sélection de `02 CORRESPONDANCES` et `04 PROCÉDURE/[JURIDICTION + lieu]/11 EXPERTISE`, puis création de « Test dossiers choisis ». État prêt, dossier mail présent après inventaire ; exactement quatre répertoires vides sur disque (deux choix et deux parents), aucun des enfants de Correspondances créé. Les 37 destinations restent proposées. Formulaire contrôlé visuellement.
- Aucune acceptation humaine ou validation matérielle revendiquée. L’historique des sections précédentes décrit les versions antérieures ; les nouvelles créations suivent désormais cette sélection facultative et la création à la demande.

## Correspondances, présélections et pièces jointes — 24 octobre 2026

- La demande directe remplace le classement groupé : PDF du mail dans Correspondances, classement indépendant des pièces jointes et présélections modifiables dans le modèle. Les sections précédentes restent des preuves des anciennes versions.
- TDD : 12 nouveaux cas initialement en échec puis réussis. Compléments sur collisions dans un lot, protection des intentions en cours, lecture pure des modèles anciens et adaptation des archives après interruption. Un test de rapprochement de PDF a exposé l’ancien marquage global du mail comme classé ; corrigé pour conserver le statut des pièces en attente. **17 tests ciblés, suite complète finale : 191 réussites**, zéro échec, zéro test sauté. Avertissement Starlette/httpx préexistant ; syntaxe JavaScript et modèle MDSE contrôlés.
- Les tests historiques vérifiant les déplacements groupés ciblent désormais les pièces jointes et vérifient séparément que le PDF reste en Correspondances. Les fixtures de dossiers créés manuellement tolèrent la présélection Correspondances ; les preuves de conservation des fichiers et de reprise restent présentes. Un nom fictif de Message-ID a été corrigé en ASCII pour que le test de collisions s’exécute effectivement.
- Chrome réel, démonstration isolée port 8879 : seule Correspondances cochée initialement dans le modèle. Ajout de Factures aux présélections, renommage en `07 FACTURES ET HONORAIRES`, enregistrement ; les deux cases sont reprises dans Nouveau client. Correspondances décoché pour « TEST-CLASSEMENT » : seul le dossier Factures existe à la création.
- Mail fictif à deux pièces reçu : PDF dans `02 CORRESPONDANCES` créé au besoin, annexes en `00 - À classer`. Bouton Classer sur Facture présélectionnant seulement cette pièce ; rangement dans Factures, mail encore en attente. Puis Contrat dans `05 PIÈCES/Pièces client`, création de la seule branche nécessaire et suppression de la zone d’attente vidée. Statut final classé, chemin du PDF fixe et trois empreintes inchangées. Emplacements et statuts par pièce inspectés dans le détail et le sélecteur. Aucun papier imprimé.
- Tests d’adaptation des anciens registres : PDF suivi déplacé vers Correspondances sans perte, pièces déjà classées et travaux d’impression préservés, reprise après erreur de publication. Les modèles et présélections des clients existants ne sont pas réécrits par la lecture. Une adaptation seule n’active pas l’impression après classement. Les futurs changements du rôle Correspondances s’appliquent aux prochains mails, sans déplacer à nouveau les mails déjà adaptés.

## Classement manuel du PDF et visibilité — 24 octobre 2026

- Correction directe de l’utilisateur : le PDF du mail attend désormais le choix de destination, comme chaque pièce jointe. Les preuves de la section précédente décrivent la version antérieure ; son routage fixe ne constitue plus la règle actuelle.
- TDD ciblée : six cas rouges avant modification, puis six réussis dans `tests/test_manual_document_filing.py`. Les tests de l’ancien routage ont été adaptés à la nouvelle règle, en gardant les contrôles de contenu, de reprise, de confinement et d’absence de réimpression. Suite complète : **197 réussis, 0 échec, 0 ignoré** ; avertissement de dépréciation Starlette/httpx préexistant. Syntaxe JavaScript contrôlée avec `node --check`.
- Chrome réel sur démonstration isolée, port 8880 : PDF du mail et pièce jointe d’un contrat présents dans `00 - À classer`. Liste, détail et sélecteur inspectés visuellement : noms foncés en gras, badges « À CLASSER », fond ambré et bordure. Contraste effectif des badges de liste/détail/sélecteur : **8,45:1** (`#7b2d00` sur `#fff1cf`) ; noms de documents en attente : **11,60:1** (`#542a05` sur `#fff8e8`). Le libellé explicite complète la couleur.
- Bouton Classer du PDF : seul son document est coché ; validation désactivée tant qu’aucun dossier n’est choisi. Rangement du PDF dans `03 MAILS (PDF)`, pièce jointe laissée à sa place : mail encore en attente, seule la pièce est surlignée et le récapitulatif indique « 1 document à classer ». Le classement groupé présélectionne alors uniquement cette pièce. Rangement dans `05 PIÈCES/Pièces client` : statut entièrement classé, aucun document surligné, emplacement du PDF conservé. Les empreintes SHA-256 des deux fichiers servis par l’application restent identiques aux originaux ; impressions historiques inchangées.
- Modèle : Correspondances reste présélectionné à la création, avec choix modifiables ; le champ de destination automatique du PDF a disparu. La compatibilité API `email_folder` reste une métadonnée inerte, sans ajout forcé de dossier.
- Tests supplémentaires de conservation : registre antérieur version 2, PDF déjà rangé, ancien PDF sans métadonnées, PDF associé explicitement, réparation d’un fichier supprimé, reprise d’un classement interrompu et impression après classement du dernier document, PDF compris. Aucun compte personnel ni imprimante physique utilisé.

## Classement intégré sous chaque document — 24 octobre 2026

- Choix direct de l’utilisateur : un sélecteur individuel sous chaque document, sans dialogue de classement ni commande de classement groupé. Les cases et commandes d’impression restent distinctes ; le contrat API de classement multiple reste compatible.
- Deux tests de projection d’arborescence ont d’abord échoué, puis réussi : branches repliées avec parents sélectionnables, recherche dans les branches cachées, accents et résultats vides. Suite complète finale : **199 réussis, 0 échec, 0 ignoré**, avec le seul avertissement Starlette/httpx préexistant. Syntaxe JavaScript et modèle MDSE contrôlés.
- Chrome réel, espace fictif isolé sur le port 8881 : un seul sélecteur sous le document, aucun dialogue, aucune présélection, validation inactive avant choix. Recherche Expertise dans la branche de juridiction encore absente, ajout aux favoris, état vide explicite et changement de document avec réinitialisation du choix. Chevrons SVG agrandis à la demande de l’utilisateur : icône **20 × 20 px**, trait **2,4 px**, bouton **32 × 32 px** ; le clic révèle les enfants tout en laissant le parent sélectionnable.
- Refus 503 simulé du classement : erreur affichée sous le document, recherche et destination conservées, nouvel essai possible et aucun chemin modifié. Actualisation de l’état : même nœud de sélecteur, recherche, choix et focus conservés. Échap ferme le sélecteur, C ouvre celui d’un document ; validation depuis la recherche avec Entrée. Un PDF reclassé dans Factures : seul son chemin change, sélecteur refermé, empreinte SHA-256 du contenu servi et travaux d’impression inchangés.
- Requête de classement volontairement retardée : double clic produit une seule requête et désactive le sélecteur. Navigation vers une autre communication, ouverture de son PDF et choix de Factures ; libération de la requête initiale : seule la pièce jointe initiale est rangée dans Expertise, et le nouveau sélecteur garde son document et son choix. Le PDF du premier mail reste en attente.
- Le nœud conservé au rafraîchissement est lié à l’identifiant du document : changer de document ne récupère pas le sélecteur de son voisin. Moteur, modèles, archives et politique d’impression inchangés par cette évolution d’interface. Aucun compte personnel ni imprimante physique utilisé.

## Impression individuelle et clients favoris — 24 octobre 2026

- Chaque PDF ou pièce jointe possède une icône imprimante à côté de l’aperçu et du Finder. La commande globale du bas du détail disparaît. Les étoiles de clients sont persistantes et indépendantes des favoris de destinations ; favoris en tête, puis autres clients, ordre alphabétique français dans chaque groupe.
- TDD ciblée : 11 cas rouges avant implémentation, avec une protection CSRF déjà assurée. Après implémentation, **31 tests ciblés réussis**. Suite complète : **211 réussis, 0 échec, 0 ignoré**, seul avertissement Starlette/httpx préexistant. Les tests ciblés et la syntaxe ont été revérifiés après amélioration du retour du focus sur les actions. Modèle MDSE validé.
- API : impression d’une pièce décochée sans changer sa case ni ses voisins, préférences recto verso/noir et blanc transmises, génération initiale idempotente, réimpression limitée au document avec confirmation booléenne, reprise d’un refus certain et absence de relance implicite d’un résultat incertain. Formats incompatibles, fichiers absents/modifiés, messages non exportés, identifiants inconnus et requêtes sans jeton refusés. Étoile enregistrée puis relue après fermeture/réouverture du service, favoris de dossiers et archives conservés ; valeurs invalides refusées.
- Chrome réel sur démonstration isolée, port 8882 : deux icônes pour les deux documents du mail, aucune commande globale dans le détail. Pièce jointe décochée, requête volontairement retardée, double clic et actualisation : une seule requête, bouton désactivé pendant le traitement. Après libération : un seul travail simulé pour la pièce, documents identiques et case toujours décochée. Nouvelle action ouvre une confirmation initialement désactivée ; confirmation donne exactement un second travail pour cette seule pièce. Le PDF voisin reste non imprimé. Les deux contenus servis ont été re-hachés et correspondent aux empreintes enregistrées.
- Chrome : étoile Sophie Laurent, groupe Favoris en tête, mail/client ouverts et nœud du sélecteur inchangés, recherche Expertise conservée. Après rechargement, étoile toujours présente. Recherche Sophie, refus 503 injecté : étoile conservée et erreur lisible ; focus revenu sur l’étoile. Retrait réussi : retour à l’ordre Atelier Beaumont, Camille Moreau, Sophie Laurent. Réactivation, aperçu visuel des étoiles et des trois actions par document ; aucune erreur console applicative observée.
- Les essais utilisent uniquement des données fictives et la simulation d’impression ; aucune page papier soumise et aucune acceptation humaine revendiquée.


## Traitement quotidien après revue — 24 octobre 2026

- Plan consigné dans `docs/DAILY_UPGRADE.md`, exigences et décision dans WI-daily-processing. Première passe TDD : 11 cas rouges et 21 réussis ; après implémentation, 32 réussis. La revue finale a ajouté deux scénarios : reprise de la dernière intention échouée (rouge puis corrigé) et annulation vers une destination déjà classée sans activer l’impression automatique (vert). **34 tests ciblés et 224 tests complets réussis, zéro échec, zéro ignoré, 17,20 s** ; avertissement Starlette/httpx préexistant.
- Tests : progression partielle, dernier échec remplacé par une réussite avec conservation de l’historique, cases décochées et incertitude, aucune sélection, distinction réel/simulé, non-rejeu d’une génération dépassée et reprise de la dernière intention. Recherche noms originaux/exportés, destinations, casse, accents, recherche vide et aucun résultat.
- Annulation : ancien chemin et classification retrouvés après redémarrage, contenu SHA-256 inchangé, répétition idempotente, route CSRF protégée, refus des collisions/fichiers modifiés/liens/jetons obsolètes. Intention interrompue reprise jusqu’au retour à pending ; retour vers une destination classified puis process sans travail d’impression.
- Navigateur intégré réel, espace fictif isolé port 8883, viewport 1265 × 712 : premier document visible sans défilement de page ; documents avant le corps repliable, cases nommées, compteurs distincts. Impression simulée d’un seul PDF : Simulés 1/2, autre document inchangé. Classement dans Factures puis annulation : retour À CLASSER et au chemin précédent, progression d’impression inchangée.
- Recherche « liste des documents » : trois mails trouvés par pièce jointe, puis un seul sous Camille Moreau ; requête inexistante : état vide explicite. Corps du mail ouvert et maintenu pendant changement de recherche. Espace neuf port 8884 : titre neutre, zéro mail/document et invitation à créer le premier client.
- Modèle : branches initialement repliées, ouverture de Correspondances, recherche Expertise révélant parents et destination profonde ; enregistrement avec présélection Correspondances masquée ; effacement de recherche rétablit les branches ouvertes. Les 37 destinations et le défaut Correspondances restent sauvegardés. Nouveau client indique « 1 sélectionné » sans création de données. Captures de la session conservées dans le dossier de sortie de cette conversation.
- Les essais utilisent des documents fictifs et une impression simulée ; le cas « soumis » emploie un transport simulé de test. L’intégration Orange/Apple Mail et l’imprimante physique restent à valider sur le Mac cible. Aucune acceptation humaine revendiquée.
- Déploiement local effectué : dépôt principal avancé au commit `73dd996`, service 8765 redémarré. Comparaison au registre sauvegardé : 3 clients, 7 messages, 13 documents, 2 modèles et aucun travail d’impression identiques ; les 13 fichiers ont exactement les mêmes SHA-256. Écran principal rouvert et capturé, sans modification des choix ou classements existants.


## Lecture du mail en premier — 24 octobre 2026

- Préférence explicite de l’utilisateur : le corps du mail revient avant le PDF et les pièces jointes et est ouvert par défaut. Un repli reste possible ; la section DOCUMENTS sépare ensuite les cartes. Les compteurs, statuts et actions par document sont conservés. Cette préférence remplace uniquement l’ordre visuel décrit dans la vérification précédente.
- Syntaxe JavaScript valide ; 22 tests d’interface existants réussis. Pas de nouveaux tests pour ce changement de disposition. Parcours IAB sur espace fictif 8883 : corps développé avant les documents, repli volontaire conservé après recherche, autre mail ouvert développé, deux cartes présentes avec classement et impression individuels. Aucun déplacement ou travail d’impression déclenché par la vérification.
- Précision utilisateur intégrée : De, À, Reçu et Client sont au-dessus du corps. Ordre confirmé dans le navigateur après rechargement. Les 34 tests ciblés de traitement quotidien/interface passent ; les 224 tests complets du lot précédent restent la dernière exécution complète, sans nouvelle prétention de réexécution ici.

- Allègement rédactionnel demandé dans les cartes : retrait des descriptions fixes « Mail en PDF » et « Pièce jointe originale ». Nom, icône de format, état de classement et état d’impression conservés ; indication particulière des images intégrées maintenue. Aucun changement du traitement des documents.
- Ajustement visuel demandé : statut d’impression dans la même rangée de badges que le classement, style partagé, état en attente ambré, simulation/envoi en cours bleus et échec/incertitude rouges. Le détail des erreurs reste sous les badges. Aucun état métier modifié.


## 2026-10-24 — mail unifié et commandes documentaires

- Option 2 choisie, puis précisions utilisateur : mail/en-têtes/corps réunis, pied PDF attaché et disponible corps replié ; pièces jointes séparées, titre en pleine largeur, badges et actions alignés, destination en pleine largeur dessous. Icônes Lucide œil/dossier/imprimante locales, licences incluses. Retrait des labels fixes, du texte explicatif et du contrôle auto/groupé, sans modifier les choix persistés.
- Liste et détail : À classer et À imprimer, transmissions explicitement destinées à l’imprimante, simulations distinctes. Les états d’export en attente/erreur restent signalés. Neuf cas de suivi écrits avant le helper, échouant en son absence puis réussissant après implémentation.
- `python -m pytest tests/test_daily_upgrade.py tests/test_ui.py -q --tb=short` : **43 réussis**, 0 échec, 0 ignoré, 4,62 s. Avertissement Starlette/httpx préexistant. Syntaxe JS vérifiée par le test existant. Pas de nouvelle prétention de réexécution de la suite complète.
- IAB sur données fictives 8883 : sélecteur PDF inline ; recherche consultations, classement du seul PDF dans 01 CONSULTATIONS, pièce jointe inchangée dans 05 PIÈCES/Pièces client ; annulation restaure la destination précédente. Une impression simulée cible le PDF, sa pièce reste « Pas encore imprimé » et les comptes indiquent 1/2 en simulation. Nouvelle tentative ouvre la confirmation, annulée sans soumission. Repli du corps garde les outils ; mail sans pièce affiche zéro fichier et « Aucune pièce jointe ». Les tests métier existants couvrent aussi la portée et l’idempotence des impressions.
- Après simplification finale : absence des libellés retirés contrôlée dans le DOM, nom de pièce de même largeur que son conteneur, destination sous badges, icônes visibles. Largeurs CSS 1280×720, 720×634 et 390×844 : pas de débordement horizontal ; retour à la taille de fenêtre habituelle. Console : aucune erreur capturée. Comparaison visuelle et limites de capture dans `design-qa.md`.
- Construction locale d’un wheel avec setuptools : les trois SVG et leur licence sont présents dans le paquet. Aucun téléchargement requis à l’ouverture de l’interface.
- Déploiement local : fast-forward du dépôt principal vers `cff5171ca545dd62387fc3a8d26cfbb3abf7c0a7`, rechargement de 8765, pied PDF et pièces jointes confirmés ; fichiers statiques servis sans redémarrage. Comparaison SQLite et SHA-256 : 3 clients, 7 messages, 13 documents, zéro travail d’impression, 2 modèles, mêmes données et mêmes 13 empreintes. Capture principale : `16-main-app-final.png` dans le dossier de preuves de cette séance.


## Identité et dépôt Mailord — 24 octobre 2026

- Le module, la commande, les variables, les scripts, les guides et les futurs PDF utilisent Mailord. Marque « Mailord — Le seigneur des emails. », enveloppe couronnée SVG et favicon locaux. Avatar décoratif retiré à la demande du propriétaire. Les preuves historiques et le contenu des anciens mails restent intacts.
- Historique importé dans le dépôt cloné `vguillet/Mailord`, avec conservation de son origin et de son commit initial. Nouvel environnement Python créé dans ce dépôt. Aucun fichier de compte, archive, registre ou secret suivi par Git.
- Migration hors service vers Application Support/Mailord : 3 clients, 7 mails, 13 documents ; identifiants, classements, favoris, sélection et travaux conservés. Les 13 SHA-256 sont identiques. Source conservée comme sauvegarde. Les tests refusent les services actifs, destinations existantes/imbriquées et liens symboliques.
- TDD migration : quatre scénarios rouges avant création de l’outil, puis verts. Ancêtre distant faussement annoncé disponible : régression rouge puis corrigée ; version distante absente du checkout toujours proposée. Le test API sans configuration isole désormais la découverte origin.
- Suite complète dans le dépôt final : **239 réussis, zéro échec, zéro ignoré, 19,79 s**. Seul avertissement préexistant Starlette/httpx. Les 18 tests mise à jour/API passent également.
- Wheel contrôlé : paquet `mailord`, commande `mailord`, ressources SVG incluses, ancien module absent. IAB aux largeurs 1280, 599 et 390 : marque lisible, pas de débordement horizontal. Service supervisé 8765 depuis le dépôt final, avatar absent et statut « Votre application est à jour » face à l’ancêtre distant. Captures et comparaisons avant/après conservées dans les sorties locales de cette conversation.
- Aucune impression physique ni validation d’un compte réel effectuée. Une baseline de livraison peut être établie après revue du propriétaire ; aucune acceptation humaine n’est revendiquée.


## Emplacement local des nouveaux clients — 24 octobre 2026

- 19 nouveaux cas ciblés dans `tests/test_client_locations.py` : navigation en lecture seule, racine par défaut, parents imbriqués, création additive, persistance et classement après redémarrage, entrées invalides, liens, isolement entre clients, parent remplacé/disparu, reprise et CSRF.
- Suite finale : **258 tests réussis**, aucune erreur ; avertissement Starlette/httpx préexistant. Les tests d’intégration ont été exécutés avec autorisation des ports locaux temporaires.
- Syntaxe de `mailord/static/app.js` vérifiée. Parcours navigateur sur données fictives séparées : racine → Affaires → 2026, retour parent/racine, aperçu et création de DUPONT-MARTIN. Présence de `Affaires/2026/DUPONT-MARTIN/02 CORRESPONDANCES` vérifiée sur disque, sans création de client à la racine.
- Contrôle supplémentaire : une substitution du dossier client par un lien pendant la création mail est refusée avant de préparer les dossiers initiaux ; aucun contenu créé dans la cible extérieure.
- Aucune intégration Orange, Apple Mail réelle ou imprimante physique exercée. Cette évolution ne prétend pas implémenter la politique globale de conservation proposée séparément.
- MDSE : extension de WI-lazy-folders avec REQ-05/TASK-02/VM-05. Limitation documentée du validateur SM-07 : le rapport historique VER-01 est comparé aux exigences ajoutées ultérieurement. Il reste immuable ; le nouveau rapport décrit la vérification actuelle.

Après intégration, service local 8765 relancé et formulaire vérifié ; 3 clients, 7 messages et 13 documents conservés à chemins et empreintes identiques. Le nouveau REQ-05 est vérifié. VER-02 reste globalement partiel car REQ-04 AC-01 décrit encore un ancien défaut vide, remplacé par les présélections du modèle dans WI-correspondence-filing.
