# Plan de mise à niveau — traitement quotidien

1. Corriger le suivi : dernier essai par document, compteurs réels et simulés séparés, état partiel, ancienne erreur conservée seulement dans l’historique. Une demande ordinaire ne rejoue pas une génération dépassée.
2. Réduire l’en-tête et les statistiques. Montrer le corps du mail ouvert en premier, puis ses documents (préférence utilisateur du 24 octobre), afficher la progression et libeller les cases d’inclusion.
3. Rechercher aussi les noms de pièces et leurs destinations, sans distinction d’accents ou de casse.
4. Rechercher et replier les branches du modèle, conserver les présélections masquées, résumer les dossiers initiaux à la création d’un client.
5. Annuler le dernier classement par document, avec jeton persistant, reprise, contrôle de fichier et refus d’écrasement. L’annulation ne retire pas du papier déjà envoyé à l’imprimante.
6. Vérifier en simulation isolée, puis redémarrer le service local avec conservation des données.

L’installation guidée d’un nouvel espace, les variables de juridiction, l’alignement des anciens dossiers, les suggestions, les affaires archivées et la source Git réelle restent des améliorations ultérieures. Elles ne sont pas requises pour cette mise à niveau du traitement quotidien.

Implémentation vérifiée : 224 tests, parcours navigateur isolés et contrôle des données existantes au redémarrage. Voir `docs/VALIDATION.md` et le work item `WI-daily-processing`.

Suivi MDSE réconcilié. Proposition de prochain point de référence : baseline « as-built » de ce lot vérifié, à approuver explicitement par le responsable si souhaité ; aucune baseline approuvée automatiquement.
