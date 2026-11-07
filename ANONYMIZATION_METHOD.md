# Méthode de pseudonymisation et d’anonymisation

## Principe

PyStats distingue trois niveaux qui ne doivent pas être confondus :

1. **nominatif interne** : prénom et nom réels accessibles à l’enseignant ;
2. **pseudonymisé analytique** : identifiant stable aléatoire, sans nom ni prénom ;
3. **agrégé pour diffusion** : aucun identifiant individuel, dates retirées, petits groupes supprimés et valeurs arrondies.

La pseudonymisation reste un traitement de données personnelles : une personne qui possède la table de correspondance peut réidentifier l’élève. L’anonymisation exige au contraire que l’identification ne soit plus raisonnablement possible en tenant compte du contexte et des données auxiliaires disponibles.

## Conservation de l’usage nominatif par l’enseignant

La base principale `nom_classe.sqlite` ne contient que le pseudonyme analytique. Les prénom et nom sont stockés dans :

```text
_identities/nom_classe.identities.sqlite
```

L’application attache cette base localement pour afficher la liste de classe, annoncer le prochain élève et produire, sur demande explicite, deux fichiers :

- `INTERNAL_ONLY_responses_long_nominative.csv` ;
- `INTERNAL_ONLY_student_assessment_summary_nominative.csv`.

Les noms sont utilisés uniquement pour les libellés du rendu enseignant. Les analyses conservent le pseudonyme comme clé de calcul, y compris pour les élèves homonymes. L’enseignant retrouve figures, tableaux et rapports nominatifs sous `Enseignant`. Les résultats de travail et graphiques de `Publication` sont pseudonymisés. La table agrégée pour diffusion y figure séparément.

La base analytique et la base d’identités doivent être sauvegardées ensemble pour préserver l’usage nominatif. Elles doivent au contraire être séparées lors d’une transmission analytique autorisée.

## Pseudonyme stable

Chaque élève reçoit à sa création ou à la migration un identifiant aléatoire de forme `STU-XXXXXXXXXX`. Il n’est dérivé ni du nom, ni du prénom, ni de la date de naissance. Il reste stable dans une base de classe afin de permettre les trajectoires longitudinales.

La correspondance `student_id ↔ prénom ↔ nom ↔ pseudonyme` est limitée au fichier latéral. Les colonnes historiques `first_name` et `last_name` de la base analytique sont vidées lors de la migration afin d’éviter une duplication silencieuse de l’identité.

Ce dispositif suit la recommandation de la CNIL consistant à remplacer les identifiants directs par un identifiant non signifiant et à conserver séparément la table de correspondance.

## Export pseudonymisé analytique

Le fichier long et les synthèses conservent : pseudonyme, identifiants de session/item/tentative, date d’évaluation, groupe, réponses, temps et progression. Cette richesse est nécessaire à l’analyse répétée, mais signifie que ces fichiers ne sont **pas anonymes**.

Pour une classe de 25 élèves, un profil rare — par exemple un temps extrême, une absence connue ou une combinaison de difficultés — peut permettre une inférence. Les fichiers pseudonymisés doivent donc rester dans un espace de travail autorisé et ne pas être publiés.

## Export agrégé pour diffusion

`public_anonymized_dataset.csv` applique automatiquement :

- suppression de tout identifiant d’élève, d’item et de tentative ;
- remplacement de la date et de l’identifiant d’évaluation par un numéro de session ;
- regroupement par session et famille de faits ;
- suppression des cellules représentant moins de cinq élèves ;
- classe d’effectif (`5-9`, `10-19`, `20+`) au lieu de l’effectif exact ;
- nombre de réponses arrondi au multiple de 5 ;
- réussite arrondie par pas de 5 points de pourcentage ;
- temps médian arrondi par pas de 250 ms.

Le seuil de cinq est une règle de minimisation, pas une garantie mathématique d’anonymat. Le k-anonymat de Sweeney protège contre l’individualisation par des quasi-identifiants définis, mais pas contre toutes les inférences, la connaissance préalable ou la liaison avec d’autres publications.

## Vérification avant diffusion

Avant toute diffusion, le responsable doit évaluer les trois critères proposés par le G29 et repris par la CNIL :

- **individualisation** : peut-on isoler une personne ?
- **corrélation** : peut-on relier deux enregistrements concernant la même personne ?
- **inférence** : peut-on déduire une information personnelle avec une probabilité significative ?

Il faut également rechercher les quasi-identifiants contextuels : intitulé unique de classe, événement scolaire connu, dates publiées ailleurs, petit sous-groupe, famille de faits très rare ou résultats déjà communiqués. Si l’un de ces risques subsiste, il faut agréger davantage, regrouper des sessions/familles, augmenter le seuil ou ne pas diffuser.

## Mesures opérationnelles

- Activer le chiffrement du disque du poste et verrouiller le compte enseignant.
- Ne pas synchroniser le dossier `_identities` vers un espace personnel non autorisé.
- Conserver les sauvegardes nominatives dans un emplacement institutionnel protégé.
- Transmettre seulement le sous-ensemble nécessaire et par un canal approuvé.
- Ne jamais joindre un export nominatif à un rapport R pseudonymisé.
- Détruire les copies de travail conformément à la durée de conservation définie par l’établissement.
- Réévaluer le risque si plusieurs classes ou années sont assemblées.

## Limites

PyStats ne chiffre pas lui-même SQLite et ne gère pas les comptes utilisateurs. Une personne ayant accès au dossier complet possède à la fois les mesures et la correspondance. L’export public est une transformation prudente, mais son anonymat dépend du contexte de publication ; il ne doit pas être présenté comme irréversible sans analyse spécifique.

## Références

- CNIL. *L’anonymisation de données personnelles*. https://www.cnil.fr/fr/technologies/lanonymisation-de-donnees-personnelles
- CNIL. *Recherche scientifique hors santé : enjeux et avantages de l’anonymisation et de la pseudonymisation*. https://www.cnil.fr/fr/recherche-scientifique-hors-sante-enjeux-et-avantages-de-lanonymisation-et-de-la-pseudonymisation
- Sweeney, L. (2002). k-Anonymity: A Model for Protecting Privacy. *International Journal of Uncertainty, Fuzziness and Knowledge-Based Systems*, 10(5), 557–570. https://epic.org/privacy/reidentification/Sweeney_Article.pdf
