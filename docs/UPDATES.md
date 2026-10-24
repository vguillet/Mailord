# Mettre à jour depuis l’interface

Après la première installation sur le Mac, ouvrir **Mises à jour** dans Mailord. Le mainteneur configure une fois l’adresse du dépôt de confiance et la branche publiée (par exemple `main`). Le dépôt peut être public en HTTPS, ou privé avec un accès Git déjà préparé sur ce Mac (trousseau ou clé SSH). Ne jamais mettre de mot de passe ou jeton dans l’adresse.

Le service recherche une nouvelle version au démarrage puis toutes les heures tant qu’il tourne. **Vérifier les versions** permet de ne pas attendre. Un commit doit être **poussé** sur le dépôt distant : les commits restés sur l’ordinateur du développeur ne sont pas visibles chez l’utilisatrice.

Lorsqu’une version est disponible, cliquer sur **Mettre à jour**. L’interface indique le téléchargement, la préparation puis le redémarrage, et se recharge automatiquement après la reconnexion. Aucun terminal n’est nécessaire pour cette opération. L’application doit rester lancée pendant la préparation ; le téléchargement peut prendre plusieurs minutes.

## Ce qui se passe

1. Le commit affiché est téléchargé dans un nouveau dossier privé, sans `git pull`, réinitialisation ni modification du dépôt d’origine. Si la branche avance entre-temps, le commit sélectionné reste celui installé.
2. Un environnement Python séparé reçoit les dépendances de `requirements.lock`. Une installation ratée laisse le service courant fonctionner.
3. Le service termine les opérations en cours, puis le lanceur sauvegarde le registre SQLite et démarre la candidate sur le même port avec les mêmes options.
4. Pendant ce contrôle, l’API métier, la récupération de fichiers, le traitement des mails et l’impression sont désactivés. Si le démarrage échoue, le registre sauvegardé et l’ancienne version sont restaurés.
5. Après le contrôle, le lanceur enregistre la version active avant d’autoriser le traitement. À partir de cette activation, aucune restauration automatique ne revient sur le travail de l’utilisatrice.

Les documents Finder et le dossier privé restent à leurs emplacements habituels. La configuration, les clients, les files et l’historique d’impression restent dans le même registre. Les sauvegardes de registre et anciennes versions sont conservées sous `updates/` dans le dossier privé. Elles ne remplacent pas une sauvegarde des documents et des messages : conserver la sauvegarde habituelle du Mac. Aucun nettoyage automatique de ces versions n’est effectué dans cette version.

## Installation initiale et lancement

Utiliser le lanceur existant (`scripts/start.command` pour la démonstration, ou le LaunchAgent documenté pour le compte réel). Il démarre désormais un superviseur qui garde l’application disponible pendant les changements de version. Après l’ajout initial de cette fonctionnalité à une installation existante, **fermer puis relancer une fois** le service. Le mode technique `--worker` ne doit pas être utilisé directement par l’utilisatrice.

Le dépôt d’origine et son environnement `.venv` servent de lanceur stable : **ne pas les déplacer ni les supprimer**. Les versions suivantes sont installées ailleurs. Git et Python doivent avoir été installés une fois par le mainteneur. En cas d’accès privé, tester cet accès au préalable sous le même compte macOS que l’application ; aucune invite interactive de mot de passe n’est ouverte pendant une mise à jour.

## Publier une version (mainteneur)

- Pousser le code testé sur la branche configurée. Une branche `stable` peut éviter de proposer tous les commits de développement.
- Mettre à jour et committer `requirements.lock` avec les changements de dépendances.
- Conserver `update.json` avec `update_protocol: 1` et `data_schema: 1` tant que la version est compatible avec ce lanceur et le registre existant. Une migration incompatible doit changer ce contrat et être accompagnée d’une procédure distincte ; elle sera refusée par ce mécanisme.
- Conserver les options de lancement et les routes privées de contrôle. Vérifier le démarrage en probation sans mutations et les tests de mise à jour avant publication.
- Ne pas inclure de données privées, de documents clients ni de secrets dans Git. L’adresse configurée désigne du code qui sera exécuté sur le Mac : utiliser son propre dépôt de confiance.

La détection s’appuie sur les références distantes [Git ls-remote](https://git-scm.com/docs/git-ls-remote) ; l’installation utilise un répertoire séparé et un commit fixé. Docker n’est pas requis.

## En cas d’échec

Une erreur réseau, un dépôt inaccessible, une branche absente ou une dépendance indisponible est indiquée dans le panneau. Corriger l’accès si nécessaire puis cliquer sur **Vérifier les versions**. Si la nouvelle application ne démarre pas avant activation, la précédente est relancée et le panneau l’indique.

Après une interruption brutale, le prochain lancement reprend le journal de bascule. Si un ancien processus tourne encore, le lanceur refuse de restaurer un registre en cours d’utilisation : fermer le service restant, ou redémarrer le Mac, puis relancer. Les erreurs après activation d’une version ne provoquent pas de retour automatique susceptible d’effacer des opérations récentes. Une régression fonctionnelle après activation nécessite une nouvelle version corrective ou une restauration accompagnée par le mainteneur.

Le dépôt distant définitif n’est pas encore configuré dans le projet livré. Les tests utilisent des dépôts locaux de test et des processus réels ; ils ne prétendent pas valider les accès au futur dépôt privé de l’utilisatrice.
