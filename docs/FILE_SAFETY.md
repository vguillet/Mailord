# Conservation des documents

## Ce qui change

- Aucun dossier documentaire n’est supprimé, même vide après un classement, une annulation ou un échec. Le modèle reste un catalogue ; supprimer une rubrique du modèle ne supprime rien dans le Finder.
- Aucun document existant n’est écrasé. Un nom déjà occupé entraîne un autre nom affiché avant confirmation, ou un refus si le conflit apparaît ensuite.
- Le choix du dossier reste sous le document. Une confirmation distincte montre le nom, le départ et l’arrivée avant chaque classement ou annulation.
- **Récupération**, sous chaque document, donne accès aux versions conservées et à l’historique. Restaurer crée un nouveau fichier « récupéré … » à la racine du client, à classer ensuite. Le fichier courant et les anciennes versions restent présents.
- Un fichier absent ou différent de la version suivie est signalé. Le contrôle ne le régénère pas, ne le remplace pas et ne déduit pas son identité de son seul nom. Un déplacement Finder hors du chemin suivi reste donc à examiner.
- Classement, annulation et restauration ne lancent aucune impression. L’ancienne option après classement est traitée comme manuelle ; l’impression explicite et l’option après export initial restent disponibles.

## Avant de retirer l’ancien emplacement

1. Le service prépare un plan lié aux documents, chemins, empreintes et identités des dossiers. Aucun fichier ne bouge pendant la préparation. La confirmation expire après dix minutes.
2. Après confirmation, il revalide tout le lot. Le journal d’opérations est écrit dans SQLite avant les effets sur les fichiers, indépendamment des notifications limitées à 200 entrées.
3. Il conserve une copie indépendante dans `recovery/`, dans l’espace privé situé hors des archives. Il vérifie le contenu (SHA-256 et taille) et les métadonnées contrôlées : permissions, propriétaire/groupe, date de modification, attributs étendus dont les tags Finder, ACL et flags.
4. Il copie cette version vers un fichier temporaire exclusif à destination, vérifie la copie, puis publie par renommage exclusif. Un fichier arrivé entre-temps ne peut pas être remplacé.
5. Il déplace l’entrée source vers l’espace privé par renommage exclusif sur le même volume. **Il ne supprime jamais la source avec unlink.** La copie indépendante protège aussi la version confirmée lorsqu’un éditeur continue à écrire dans l’original conservé.
6. Il recontrôle la destination et l’original capturé, puis actualise le registre. Une répétition de la même confirmation terminée est sans effet supplémentaire.

Les opérations utilisent des descripteurs de dossiers avec refus des liens symboliques. Les fichiers ordinaires sont les seuls documents acceptés. Sur macOS, la copie native inclut données et métadonnées (`fcopyfile`, `COPYFILE_ALL`) et la publication utilise `renameatx_np`, `RENAME_EXCL` ; aucun repli vers un renommage susceptible d’écraser. Les appels sont conformes aux en-têtes du SDK Apple et à la [documentation Apple sur copyfile](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/copyfile.3.html).

## En cas d’anomalie

| Situation | Comportement |
|---|---|
| Dossier devenu vide | Conservé, sans nettoyage périodique ni suppression lors d’un échec |
| Destination déjà occupée | Autre nom proposé avant confirmation ; conflit tardif refusé |
| Fichier déplacé ou modifié dans Finder | Alerte ; aucune régénération ou réparation automatique |
| Dossier racine ou client déplacé/remplacé | Arrêt des écritures ; pas de recréation implicite d’une racine suivie |
| Copie incomplète, disque plein, accès refusé | Opération suspendue ; originaux et copies déjà écrites conservés |
| Source remplacée au dernier instant | L’objet capturé reste dans la récupération ; conflit signalé ; version confirmée conservée séparément |
| Destination disparue après vérification | Alerte ; copie indépendante et original capturé restent récupérables |
| Arrêt entre deux étapes | Journal conservé, opération signalée comme interrompue ; aucune reprise de retrait automatique |
| Ancienne intention `move_to` | Suspendue pour revue ; aucune reprise de l’ancien protocole de suppression |
| Copie de récupération modifiée | Non proposée comme restaurable ; accès Finder pour examen manuel |
| Restauration | Confirmation, nouvelle copie vérifiée, nouveau nom ; aucun remplacement du document courant |
| Plusieurs documents | Validation préalable de tout le lot ; si un échec intervient en cours, étapes déjà terminées conservées et autres suspendues, sans annulation destructive |

Pour un fichier modifié volontairement, conserver cette version dans le Finder. La restauration d’une version précédente ne l’efface pas. Le rapprochement historique d’un PDF existant reste explicite et conserve désormais une copie de récupération de ce PDF avant association. L’application ne recherche pas automatiquement les fichiers en dehors de la racine autorisée.

## Portée et limites

Ces protections couvrent le protocole documentaire du service local. Elles ne garantissent pas le risque zéro : une panne matérielle, une action externe, un fournisseur cloud ou une suppression manuelle dans l’espace privé peuvent encore endommager des données.

- Les déplacements protégés exigent un volume local macOS APFS ou HFS+, commun aux archives et à la récupération. Les volumes réseau, formats non reconnus et déplacements entre volumes sont refusés. La branche Linux sert aux développements et tests, sans promesse équivalente de métadonnées macOS.
- Les fichiers et les dossiers sont synchronisés avec `fsync`, le registre utilise WAL et `synchronous=FULL`. Aucun essai de coupure électrique matérielle n’a été réalisé ; les tests simulent les interruptions aux frontières du journal.
- La copie native conserve davantage de métadonnées que les champs vérifiés. La date de création, les politiques propres aux fournisseurs cloud et toutes les combinaisons de métadonnées ne sont pas garanties par ces tests.
- Les copies de récupération sont sur le même disque. **Elles ne remplacent pas Time Machine ou une sauvegarde indépendante.** La synchronisation cloud des archives n’est pas une sauvegarde de l’espace privé.
- Aucune purge automatique n’est prévue. Les versions, originaux capturés et fichiers temporaires laissés après échec occupent de l’espace ; un manque d’espace provoque un arrêt, pas un nettoyage.
- Un ancien document déjà perdu avant la première copie protégée ne peut pas être récupéré par cette fonction. Les fichiers existants sains sont protégés au prochain contrôle ; les exports initiaux le sont avant publication.
- La migration technique de tout l’espace avec `scripts/relocate_runtime.py` est refusée si le nouveau journal de conservation est présent : les identités de dossiers et copies doivent faire l’objet d’une migration spécifique. Pour les anciens espaces compatibles, la source et les copies partielles sont conservées et les copies sont vérifiées.

La matrice d’analyse comporte 145 scénarios et 25 règles. Cette livraison met en œuvre les invariants demandés et teste les fautes décrites dans `tests/test_file_safety.py` ; elle ne prétend pas certifier individuellement les 145 scénarios ni les intégrations Orange, imprimante, fournisseurs cloud et disques externes réels.
