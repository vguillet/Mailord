# Auto-secrétaire

Un bureau local pour les communications clients : surveiller les dossiers mail, conserver les messages en PDF et leurs pièces jointes, ranger les documents et piloter leur impression depuis le Mac.

## Démarrer la démonstration

Sur macOS avec Python 3.11 ou plus :

```sh
bash scripts/install-macos.sh
./scripts/start.command
```

L’interface s’ouvre sur **http://127.0.0.1:8765** avec trois clients fictifs. Les impressions sont simulées. Les données de démonstration sont séparées des données réelles.

Pour lancer un espace réel vierge :

```sh
.venv/bin/python -m autosecretaire --open
```

Choisissez la messagerie et le dossier des archives dans **Réglages avant de créer les clients**. Le [guide d’installation](docs/INSTALLATION.md) décrit Apple Mail, Orange IMAP, le démarrage automatique et les sauvegardes.

## Ce que l’application fait

- Crée un client et son dossier mail, ou rattache un dossier mail existant. Reprend les présélections du modèle (Correspondances initialement), modifiables pour les dossiers à créer tout de suite, même vides ; les autres apparaissent au premier document, branche par branche.
- Exporte le PDF du mail et ses pièces jointes dans la zone À classer. Chaque document se range avec son sélecteur de dossier intégré, avec statut et destination visibles ; les documents en attente sont surlignés.
- Édite un modèle hiérarchique de dossiers : ajout, renommage, déplacement, duplication, suppression et versions. Toutes les destinations sont proposées aux clients existants, même absentes du Mac ; seules les branches utilisées ou cochées à la création sont créées.
- Surveille les messages lus comme non lus. Génère le PDF du mail, conserve les pièces jointes et préfixe les noms avec `AAAA-MM-JJ -`.
- Contrôle les fichiers, reprend les étapes interrompues et répare les exports manquants ou corrompus. Une copie modifiée est conservée dans la quarantaine privée avant réparation.
- Affiche les clients à gauche, avec étoiles persistantes et favoris en tête, les communications et leurs états, un aperçu et les fichiers. Classement individuel directement sous chaque document, recherche dans l’arborescence, raccourcis, favoris et destinations récentes.
- Imprime chaque document depuis son icône dédiée à côté de l’aperçu et du Finder, ou selon la politique automatique après classement ou après export. Suit chaque soumission et évite la relance implicite d’un résultat incertain.
- Réunit le mail et ses commandes PDF dans un même bloc, puis affiche les pièces jointes séparément. Les noms occupent la largeur disponible ; badges et icônes sont alignés, avec la destination dessous. Le suivi distingue À imprimer, Transmis à l’imprimante et Simulation.
- Recherche dans le mail, les noms de pièces et leurs dossiers, sans distinction de casse ou d’accents ; le modèle dispose aussi d’une recherche et de branches repliables.
- Permet d’annuler le dernier classement de chaque document, même après redémarrage, avec vérification des fichiers et sans écrasement ni nouvelle impression. Disponible pour les classements effectués depuis cette version.
- Propose le rapprochement explicite des anciens PDF présents dans les dossiers clients.

Les fichiers restent accessibles dans le Finder. Le service cloud habituel synchronise la racine documentaire ; Auto-secrétaire ne prétend pas vérifier cette synchronisation.

## Portée de cette version

Service **natif macOS**, interface web locale, Python/FastAPI et registre SQLite. Ce choix donne accès à Apple Mail et aux imprimantes du Mac. Docker n’est pas fourni dans cette version : son intégration nécessiterait un relais vers macOS.

Le rendu des mails est un **PDF de texte structuré avec en-têtes**, pas une reproduction exacte de leur mise en page HTML. Pièces jointes imprimables : PDF valides, images usuelles et texte. Les autres formats, dont Word et Excel, sont conservés et s’ouvrent dans leur application habituelle.

Les adaptateurs Orange IMAP, Apple Mail et CUPS sont implémentés et testés avec transports simulés. **La connexion au compte et l’impression sur le Mac de l’utilisatrice restent à vérifier sur place.** Voir le [rapport de validation](docs/VALIDATION.md).

## Développement et suivi

```sh
.venv/bin/python -m pytest -q
mdse validate .mdse
```

Le dossier `.mdse/` contient les exigences, décisions, tâches, preuves d’exécution et vérification. Gouvernance légère, mode autonome demandé par l’utilisateur. Le contrat de l’interface est décrit dans [docs/API.md](docs/API.md).

## Mises à jour

Le panneau **Mises à jour** permet de configurer le dépôt Git et la branche une fois, puis d’installer les versions publiées en un clic. Préparation séparée, redémarrage automatique et retour à la version précédente si le démarrage échoue. Voir [le guide](docs/UPDATES.md).
