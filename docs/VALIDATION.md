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
