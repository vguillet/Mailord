# Modèle de dossiers du cabinet

Source fournie le 24 octobre 2026 : « Template - Structure de dossier standard.pdf », 4 pages, lues intégralement et contrôlées visuellement. Le PDF source reste inchangé et n’est pas distribué avec le logiciel.

Empreinte SHA-256 : `c1a4239811645985a6e897100074ab2db5de9bd79a80fac199137a5a06f78983`.

## Arborescence fournie

Le modèle initial propose 37 destinations : les huit rubriques métier du PDF, leurs sous-dossiers et la zone d’attente de l’outil. Les étoiles des rubriques 05 et 07 et les annotations explicatives ne sont pas des caractères à inclure dans les noms. Les abréviations des actes figurent dans les repères ci-dessous. Le tiret typographique de « reçues du client – à trier » est normalisé en tiret simple.

```text
NOM CLIENT-NOM PARTIE ADVERSE (mention éventuelle)
  00 - À classer/
  01 CONSULTATIONS/
  02 CORRESPONDANCES/
    Avocat/
    Notaire/
    Tribunal ou cour d'appel/
    Administrations/
    Clients/
    Huissiers - Commissaires de justice/
    Divers/
  03 MAILS (PDF)/
  04 PROCÉDURE/
    LO et MED/
    [JURIDICTION + lieu]/
      01 CONCLUSIONS/
      01 bis CONCLUSIONS ADV/
      02 REQUÊTES/
      03 ASSIGNATIONS/
      04 SOMMATIONS/
      05 DOSSIER DE PLAIDOIRIES/
      06 BORDEREAUX DE COMMUNICATION DE PIÈCES/
      07 CONSTITUTIONS/
      08 JUGEMENTS - ORDONNANCES - ARRÊTS/
      09 SIGNIFICATIONS À AVOCAT/
      10 ACTES D'HUISSIER - CJ/
      11 EXPERTISE/
      12 NOTAIRE/
      13 LETTRES AU JUGE/
  05 PIÈCES/
    Pièces client/
    Pièces adverses/
    Pièces reçues du client - à trier/
  06 PROJETS ET VERSIONS DÉFINITIVES/
    Projets/
    Versions définitives/
  07 FACTURES/
  08 NOTES INTERNES/
```

## Créer une affaire

Utiliser une entrée distincte pour chaque affaire. Saisir `NOM CLIENT-NOM PARTIE ADVERSE` dans le champ « Nom du client / de l’affaire » ; ajouter les initiales en cas de patronyme fréquent et div, succ, LRM ou saisie si utile. Retirer les civilités Me, M. et Mme. Le même nom sert par défaut au dossier mail et au dossier local.

Avant de créer l’affaire, adapter `[JURIDICTION + lieu]` dans **Modèle de dossiers** : TJ, TJ réf, CA, CAAA, JAF, JEX, JAP, JI, TC ou T Com selon le dossier, avec le lieu. Ce nom est un repère littéral, pas une variable déduite automatiquement. La commande **Dupliquer la branche** conserve ses 14 sous-dossiers pour une autre instance. Ne pas créer toutes les juridictions possibles systématiquement.

L’éditeur reste libre et versionné. Le modèle courant est proposé au classement pour toutes les affaires, même si les dossiers n’existent pas sur le Mac. La création d’une affaire réserve par défaut son chemin local sans créer son arborescence. Le formulaire permet de cocher un premier ensemble de dossiers à créer immédiatement, même vides : seuls ces choix et leurs parents sont matérialisés. Aucun dossier n’est coché par défaut ; sélectionner un parent ne sélectionne pas ses enfants. Tous les autres dossiers apparaissent au premier document. **Mémoriser le modèle** garde ces destinations pour une affaire même après un changement du modèle, sans écriture de répertoires. Les branches vidées par les déplacements de l’outil sont retirées si elles sont réellement vides ; les dossiers explicitement sélectionnés à la création et leurs parents restent présents même vides, et les autres fichiers et branches sont conservés. Une mise à jour du logiciel ne remplace pas un modèle déjà enregistré ; dans la démonstration ouverte, le nouveau modèle a été enregistré explicitement à la demande de l’utilisateur.

## Repères de classement

| Document | Destination et règle du PDF |
| --- | --- |
| Consultation | 01 CONSULTATIONS ; conserver Word et PDF, jamais en Correspondances. |
| Courrier | 02 CORRESPONDANCES selon le destinataire, pas selon l’objet. Avocat comprend confrères et postulant ; Administrations comprend notamment mairie, cadastre, hypothèques, CDI et CDF. PDF systématique ; Word également pour LO, consultation ou négociation. |
| Mail | 03 MAILS (PDF), nom simple avec objet résumé et date d’émission ou de réception ; une autre date si essentielle. La formule « ge postulant » du document est un exemple de nom, pas un sous-dossier. |
| LO ou MED | 04 PROCÉDURE/LO et MED ; double à ranger dans la catégorie de correspondances du destinataire. |
| Conclusions, conclusions adverses | 04 / juridiction / 01 ou 01 bis ; abréviation CCL. |
| Requête | 04 / juridiction / 02 ; REQ. |
| Assignation | 04 / juridiction / 03 ; ASS, ASS.JF, PAF ou ASS. IF. |
| Sommation | 04 / juridiction / 04 ; SOMM.COM ou SOMM.INTERP. |
| Dossier de plaidoiries | 04 / juridiction / 05 ; DP. |
| Bordereau | 04 / juridiction / 06 ; BORD N°X chronologique. |
| Constitution | 04 / juridiction / 07 ; CONST, SEAF si sur et aux fins. |
| Jugement, ordonnance, arrêt | 04 / juridiction / 08. |
| Signification à avocat | 04 / juridiction / 09 ; SIGN AA. |
| Acte d’huissier / CJ, PV de constat ou de signification | 04 / juridiction / 10 ; ASS, PV, PV CONST, PV SIGN. |
| Expertise | 04 / juridiction / 11 ; dires, rapport et tout ce que l’expert envoie (cote bleue dans le classement physique). |
| Acte ou lettre de notaire | 04 / juridiction / 12 ; RAP. NOT, DIRE. NOT ou ACTE LIQ. NOT. |
| Lettre au juge valant acte de procédure | 04 / juridiction / 13 ; les lettres à l’expert ou au notaire vont respectivement en 11 ou 12. |
| Pièces | 05 PIÈCES, client ou adverses ; numérotation par BORD N°X et sous-pièces a, b, c… ; pièces reçues à trier séparées. |
| Projet | 06 / Projets ; PJT numéroté, initiales si co-rédacteur, date. |
| Version définitive | 06 / Versions définitives ; VD, date, AR24 si cet envoi le nécessite. |
| Facture | 07 FACTURES avec exemplaire de l’envoi ; mail ou lettre d’envoi également en 02. |
| Note interne | 08 NOTES INTERNES ; dossier, objet si spécifique, initiales de l’auteur et date apparente. |

## Nommage et limites actuelles

La demande directe de l’utilisateur reste prioritaire : `AAAA-MM-JJ - nom d’origine.ext`, avec la date de réception par défaut (date d’envoi sélectionnable). Le PDF du mail prend son objet comme nom de base ; les pièces jointes gardent leur nom d’origine après assainissement et résolution des collisions. Les modèles métier du PDF complètent les pratiques manuelles : parties, destinataire, juridiction, nature de l’acte, objet et date ; inverser les parties quand le document est adverse. Les `/` qui séparent ces éléments sont à remplacer par des tirets dans le nom du fichier.

L’outil ne déduit pas la nature juridique d’un document. Le classement d’un mail déplace actuellement son PDF et ses pièces jointes ensemble. Les copies dans plusieurs rubriques, le classement indépendant des pièces jointes, la fusion de plusieurs annexes et le renommage selon la nature de l’acte ne sont pas automatisés par cette intégration du modèle.

Les règles transverses des pages 3 et 4 relèvent de la rédaction et du traitement du courrier : polices, page x/x, références du destinataire et juridiction, présentation des actes, filigranes de projets, mentions VD/AR24, formulation des dires, copies de mails et rangement dans deux espaces. Elles restent des consignes de travail dans le PDF source. Leur présence dans le document ne déclenche aucun envoi, aucune modification d’un acte ni aucune copie automatique vers une autre boîte ou un autre espace.
