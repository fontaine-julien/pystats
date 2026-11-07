# Guide utilisateur de PyStats 2

## Installation

Suivez les [instructions pour Windows ou Linux](README.md#installation).
Le tableau de bord intégré fonctionne avec Python et PySide6. Les rapports du menu **Rapports / exports** nécessitent R.

## Poste d’analyse intégré

Pour transporter une installation, conservez le dossier `BDD` à côté de `main.py`. Le fichier `BDD/last_db.txt` mémorise le chemin de la base par rapport à ce dossier. Survolez le nom de la base dans l’interface pour lire son chemin complet. Une base extérieure ouverte manuellement sert uniquement à la session en cours.

L’accueil s’ouvre en fenêtre maximisée. La vue scindée est prévue en priorité pour un écran Full HD (1920 × 1080), avec une présentation Windows classique. En HD (1280 × 720), les quatre graphiques restent accessibles mais leur hauteur est réduite ; cliquer sur un graphique pour l’examiner en grand. Le séparateur vertical permet d’ajuster la largeur de la liste des élèves. La synthèse peut défiler si l’échelle Windows laisse moins de place.

1. **Ouvrir une base…** (Ctrl+O), puis sélectionner le **projet / classe**. Dans une base contenant plusieurs projets, les classes restent séparées.
2. Choisir **Toute la base · toutes les évaluations du projet**, ou une évaluation datée. La liste des élèves est disponible avant le calcul ; une évaluation précise affiche ses élèves inscrits.
3. Les résultats enregistrés dans la base se chargent dès l’ouverture du projet. Si les données ont changé, PyStats actualise les calculs automatiquement.
4. Sélectionner un élève pour superposer ses résultats en bleu aux résultats de la classe en gris. **Vue de la classe entière** annule la sélection. La recherche filtre la liste ; elle ne change pas la population statistique.
5. Cliquer sur un graphique pour l’agrandir. Le curseur croix donne les coordonnées exactes en barre d’état et, près d’un point, son élève ou son évaluation et ses valeurs. **Échap** ou **Quatre graphiques** rétablit la vue scindée.

Les quatre graphiques sont :

- **Évolution de la justesse** : pourcentage de réponses justes parmi les réponses effectivement données ; médiane des élèves pour la classe.
- **Évolution du temps de réponse**. Le sélecteur **Temps · 02** affiche la moyenne des réponses justes, des réponses fausses ou de toutes les réponses données. Il propose aussi la médiane des réponses justes. Les durées sont en secondes, de la présentation à la validation. Les exercices d’entraînement et les omissions sont exclus. Une catégorie sans durée mesurable laisse un point absent. La courbe de classe prend la médiane des valeurs individuelles disponibles pour la mesure choisie, à partir de trois élèves. Près d’un point, le réticule s’y accroche et affiche sa valeur exacte en barre d’état.
- **Positionnement vitesse–justesse** : chaque élève mesurable est placé dans le plan temps / justesse. Les lignes pointillées passent par le centre formé des médianes de chaque axe, calculées sur les mêmes élèves.
- **Classement des participants** : sélectionner justesse décroissante ou temps croissant. Les ex æquo gardent le même rang (1, 1, 3) ; aucun score composite n’est utilisé.

En vue générale, la synthèse et la liste portent sur toutes les évaluations du projet. La liste affiche la justesse médiane par évaluation et le temps moyen des réponses de chaque élève ; la synthèse donne aussi les nombres de réponses et leur taux de justesse agrégé. Le nuage et les rangs portent sur **la dernière évaluation chronologique**, dont le numéro est affiché, même si aucune passation n’y est encore disponible. Ils ne mélangent pas les résultats d’épreuves différentes. Lorsqu’une évaluation est sélectionnée, synthèse, nuage et rangs portent sur cette évaluation ; les deux courbes conservent l’historique **jusqu’à cette évaluation**, sans inclure les suivantes.

Le tableau de gauche indique le temps moyen de toutes les réponses données et chronométrées, justes et fausses. En vue projet, chaque réponse a le même poids. Le graphique 03 montre le centre médian actuel en orange et le précédent en violet, avec l’effectif de chaque évaluation au survol. Double-cliquez sur un nom dans la liste pour corriger le nom ou le prénom.

Pour effacer une passation erronée, sélectionnez l’évaluation puis faites un clic droit sur la ligne de l’élève. « Supprimer les résultats de l’évaluation sélectionnée » demande confirmation, en précisant l’élève et l’évaluation. Tous ses essais pour cette évaluation sont effacés, y compris les essais interrompus et l’entraînement associé. L’élève reste inscrit et peut repasser l’épreuve. Cette action retire les résultats de la base, sans créer de mention d’exclusion scientifique.

« Supprimer l’élève sélectionné » demande une confirmation distincte puis efface définitivement son identité, ses inscriptions et toutes ses passations dans la base ouverte, pré-tests inclus. Les statistiques sont automatiquement recalculées. Les fichiers déjà exportés sont des instantanés datés. Générez un nouvel export pour prendre en compte la suppression.

Seuils d’affichage : une évolution individuelle nécessite deux évaluations mesurables ; une évolution de classe nécessite deux évaluations ayant chacune au moins trois élèves mesurables ; le nuage et son centre nécessitent trois élèves ayant à la fois justesse et temps ; le classement nécessite deux élèves avec la mesure choisie. La zone concernée affiche le manque d’échantillons. Une mesure absente est affichée **—**, jamais remplacée par zéro.

Une seule tentative est retenue par élève et évaluation : la dernière terminée normalement ou par limite globale. Les tentatives en cours ou interrompues par l’enseignant, les items d’entraînement et les évaluations supprimées sont exclus. Une tentative interrompue plus récente n’efface donc pas une passation terminée antérieure. Les omissions, délais dépassés et items non présentés sont dénombrés séparément. Ces courbes sont descriptives : changements de difficulté, élèves absents et effectifs variables limitent l’interprétation des progrès.

La barre supérieure donne accès à **Nouvelle évaluation**, **Faire passer**, **Reprendre** et **Entraînement clavier**. Choisir une évaluation active pour activer **Faire passer**. Les commandes de création de projet, import CSV et suppression sont regroupées dans **Gestion** ; les rapports et exports restent dans **Rapports / exports**.

## Créer une classe

1. Dans **Fichier**, choisir **Nouvelle base…** et donner un nom sans extension.
2. Choisir **Gestion → Créer un projet**.
3. Préparer un CSV UTF-8 avec les colonnes `nom`, `prenom` et, facultativement, `groupe` :

```csv
nom,prenom,groupe
Martin,Alice,classe
Bernard,Nassim,classe
```

4. Choisir **Gestion → Importer le CSV des élèves**.

Les noms restent affichés à l’enseignant. Ils sont stockés séparément dans `_identities/<base>.identities.sqlite` ; le fichier principal utilise des pseudonymes aléatoires.

## Créer et figer une évaluation

Cliquer sur **Nouvelle évaluation**, puis définir :

- titre, date, période, groupe et version ;
- opérations : addition, soustraction, multiplication, division ou compléments ;
- valeurs autorisées des deux opérandes, par exemple `1-10` ou `2,5,10` ;
- nombre d’items notés ; deux items d’entraînement sont toujours ajoutés ;
- familiarisation au pavé numérique facultative, décochée par défaut ;
- graine entière de génération ;
- ordre équilibré aléatoire ou fixe ;
- éventuellement une évaluation source et un nombre d’items d’ancrage ;
- régime temporel : aucune limite, limite globale, limite par item, ou combinaison des deux.

Le bouton **Créer** enregistre la configuration, la liste ordonnée des items et son empreinte. Sélectionner l’évaluation sur l’accueil pour utiliser les commandes du menu **Gestion**.

- **Paramètres de l’évaluation…** permet de consulter et de modifier le protocole. Dès l’ouverture de la première passation élève, les paramètres passent définitivement en lecture seule, même si cette passation est interrompue.
- **Tester l’évaluation…** ouvre le parcours élève avec les items enregistrés, les délais et la familiarisation prévus. L’examinateur peut le répéter à volonté. Échap revient à l’administration. Les essais ne créent aucune tentative et laissent les paramètres modifiables.
- **Cloner l’évaluation…** crée une évaluation indépendante pour une autre date, par exemple la passation finale après T0. Renseigner le nom, la date et la période. La copie reprend le protocole, les inscriptions et les items à l’identique, ancrages et ordre compris. Elle démarre sans résultats.

Tous les élèves inscrits à cette évaluation reçoivent la même liste dans le même ordre. Le fichier `config/default_assessment.json` est un modèle documenté ; la configuration effectivement utilisée est celle enregistrée dans SQLite.

## Familiarisation facultative au pavé numérique

Cocher **Familiarisation au pavé numérique (facultative)** lors de la création pour ajouter, avant les calculs :

1. Trois essais guidés : copier `2`, copier `45`, puis effacer le `8` d’un champ prérempli `58` pour obtenir `5`.
2. Douze copies mesurées : six nombres à un chiffre et six à deux chiffres, dans une séquence identique pour tous.
3. Un écran de transition, puis les deux essais de calcul habituels et les questions notées.

Sous Windows, **Verr Num est activé automatiquement** pendant la session élève. Les chiffres et la validation utilisent exclusivement le **pavé numérique**, y compris sa touche **Entrée**. **Retour arrière (⌫)** permet de corriger. Dans les calculs, la touche **−** permet une omission uniquement si l’enseignant a activé cette option. Les copies et l’entraînement libre ignorent les opérateurs. **Échap** interrompt et ferme la fenêtre élève en un appui, en conservant les réponses enregistrées.

Le filtrage Windows des autres touches ordinaires est limité à la fenêtre élève au premier plan ; il est retiré à la fermeture et suspendu en cas de perte de premier plan. Il ne constitue pas un mode kiosque : Ctrl+Alt+Suppr et certaines commandes matérielles ne sont pas garanties bloquées. Si l’interception Windows échoue, un message le signale ; le filtrage dans l’exercice reste actif.

La phase vise environ une minute, selon l’élève. Chaque copie mesurée expire après huit secondes sans validation ; les essais guidés ne sont pas limités. Les erreurs, omissions et expirations sont conservées. Les essais guidés donnent un retour ; les copies mesurées passent à la suivante sans retour correct/incorrect. Échap interrompt la passation et conserve les réponses déjà enregistrées.

Cette phase est hors score et hors limite temporelle des calculs. Les exports et graphiques restent disponibles si elle est désactivée, absente ou incomplète, y compris pour les anciennes évaluations. Les évaluations déjà figées restent inchangées ; créer une nouvelle évaluation pour activer l’option.

Les exports ajoutent `keyboard_familiarization_trials.csv` (détail des copies) et `keyboard_familiarization_summary.csv` (synthèse par tentative). Les mesures facultatives figurent aussi dans `student_assessment_summary.csv`. Aucune correction automatique des temps de calcul n’est appliquée.

## Entraînement libre au clavier

Choisir **Entraînement → Entraînement au clavier**, ou le bouton du même nom sur l’accueil. Aucune sélection d’élève ou d’évaluation n’est nécessaire.

Des nombres à un ou deux chiffres apparaissent aléatoirement, sans limite de durée ni de nombre. L’élève recopie au pavé numérique, valide avec son Entrée et corrige avec Retour arrière. Après une erreur, il réessaie le même nombre ; après une réussite, un nouveau apparaît. **Échap** ou **Quitter l’entraînement** ramène à l’administration.

Ce mode n’enregistre ni tentative, ni score, ni mesure individuelle. Pour interpréter une évolution entre évaluations, noter séparément les conditions et l’exposition à cet entraînement si elles diffèrent entre élèves ou périodes.

## Choisir le régime temporel

### Affichage élève

Les chiffres sont présentés en **Verdana**, avec une cible initiale de **10 mm de hauteur visible** (choix ergonomique à essayer, pas norme scientifique). L’application utilise les dimensions physiques, la résolution et l’échelle de l’écran où se trouve la fenêtre, et recalcule lors d’un changement d’écran ou de résolution. Les pixels Qt tenant déjà compte de l’échelle Windows, celle-ci n’est pas appliquée deux fois. Sur un espace insuffisant, la taille est réduite pour garder le calcul entier visible.

Les dimensions fournies par le pilote peuvent être approximatives. Si elles sont absentes ou incohérentes, le programme estime une diagonale de **15,6 pouces** ; la hauteur réelle doit alors être vérifiée sur le poste. La distance des yeux n’est pas détectée. La cible est définie par `TARGET_DIGIT_MM` dans `app/student_display.py`.

Le fond est gris clair `#F3F3F3`, les chiffres noirs `#000000`, le champ blanc `#FFFFFF` et son contour gris `#767676`. La réponse s’ajoute en fin de nombre ; Retour arrière enlève le dernier chiffre. Le champ n’a pas de curseur clignotant. Sa largeur reste constante pendant toute la série pour ne pas suggérer la longueur de la réponse. Les changements de calcul restent immédiats.

### Limites de temps

- **Sans limite** : recommandé pour un diagnostic individuel ; l’élève va jusqu’au bout.
- **Limite globale** : à l’expiration, les items restants sont `not_presented` et ne deviennent pas artificiellement des erreurs.
- **Limite par item** : l’item courant est `timeout`, puis la passation continue.
- **Les deux limites** : la première atteinte s’applique et son origine est enregistrée.

Le chronomètre reste volontairement caché à l’élève. Les temps ne sont pas montrés pendant la passation afin de limiter la pression et les stratégies de surveillance.

## Faire passer l’évaluation

1. Cliquer sur **Lancer la passation**.
2. Cocher les élèves concernés et valider.
3. L’application affiche le prénom et le nom du prochain élève à l’enseignant.
4. L’élève réalise deux essais avec retour correct/incorrect, puis les items notés sans feedback.
5. Il saisit un entier puis valide avec Entrée du pavé numérique. Sur un champ vide, Entrée laisse le calcul et son chronomètre en cours, même après plusieurs appuis. Pour permettre de passer volontairement un calcul, cochez **Autoriser à passer un calcul avec la touche − du pavé numérique** à la création de l’évaluation. Cette option est décochée par défaut. Quand elle est active, l’élève peut appuyer sur − avec le champ vide pour enregistrer une omission. Avec un nombre déjà saisi, − conserve la saisie. Cette exception pour l’opérateur − concerne uniquement les calculs.
6. À la fin, l’application revient à la file d’attente et annonce l’élève suivant.

Une sauvegarde cohérente de la base analytique et de la base d’identités est créée après chaque tentative réelle terminée.

## Reprendre une session

Cliquer sur **Reprendre une évaluation**, choisir la session, puis sélectionner les élèves restant à évaluer. Les élèves possédant déjà une tentative terminée sont écartés de cette file. Les tentatives anciennes ne sont jamais écrasées.

Les calculs et les nouveaux exports excluent automatiquement les tentatives interrompues ou encore ouvertes. Une fin prévue par la limite globale compte comme une passation valide. L’élève peut reprendre si aucune passation valide n’existe pour cette évaluation. L’historique local conserve les interruptions et l’examinateur peut en consigner le motif dans ses notes de recherche. Pour corriger un ancien export, le générer à nouveau.

## Exporter les données

### Travail analytique courant

**Exporter les données pseudonymisées** crée les CSV sans prénom ni nom. Utiliser ce dossier pour R, un mémoire ou un échange interne autorisé. Un pseudonyme stable reste une donnée personnelle : ne pas publier ce dossier.

### Travail nominatif de l’enseignant

**Exporter une copie nominative interne** demande une confirmation puis crée, en plus des fichiers précédents :

- `INTERNAL_ONLY_responses_long_nominative.csv` ;
- `INTERNAL_ONLY_student_assessment_summary_nominative.csv`.

Ces deux fichiers permettent de travailler avec les prénom et nom réels. Ils doivent rester sur l’espace sécurisé de l’enseignant et ne doivent pas être envoyés avec un rapport ou déposés dans un espace public.

### Diffusion extérieure

Seul `public_anonymized_dataset.csv` est préparé pour une diffusion éventuelle. Il supprime les individus, les dates exactes et les petits groupes, puis arrondit les valeurs. Avant toute diffusion, lire `ANONYMIZATION_METHOD.md` : une petite classe ou un contexte connu peut encore rendre une information reconnaissable.

## Produire les graphiques et rapports

Cliquer sur **Produire l’analyse et les graphiques R**. Une fenêtre présente toutes les évaluations actives du projet : aucune n’est présélectionnée. Cocher explicitement le pool à analyser. La première date cochée devient l’évaluation d’étalonnage et la dernière l’évaluation finale ; les évaluations non cochées sont totalement exclues des CSV et des graphiques longitudinaux.

Les exports CSV et les analyses du poste enseignant utilisent trois dossiers.

- **Enseignant** contient les tableaux, les figures, les vues HTML et les rapports individuels avec le nom et le prénom. L’option de rendu nominatif est présélectionnée dans le dialogue d’analyse.
- **Publication** contient les CSV pseudonymisés dans **data**, les graphiques et rapports pseudonymisés dans **results**, et la table agrégée `public_anonymized_dataset.csv` à la racine.
- **Donnees_descriptives/figures** contient les figures collectives par famille, item ou position, le corrélogramme et, le cas échéant, la figure des ancrages.

La figure 07 situe chaque opération selon la réussite parmi les réponses saisies et le temps moyen de toutes les réponses chronométrées, justes ou fausses. La figure 06 conserve le temps médian des réponses justes pour la comparaison par table.

Le PDF **13_distribution_temps** présente jusqu’à quatre tables par page pour l’évaluation finale. Chaque point correspond au temps moyen d’un élève pour la table. Le trait indique la médiane de ces temps individuels et la bande va du premier au troisième quartile. Les temps moyens des réponses justes et fausses, calculés sur les réponses chronométrées, figurent sous chaque vignette avec leurs effectifs.

La figure 08 présente les corrélations de l’évaluation finale. Lorsque plusieurs évaluations sont sélectionnées, **08_correlogram_par_evaluation.pdf** consacre une page à chacune. La mention **NC** indique une corrélation non calculable. Dans le nuage final, le tableau sous la figure croise les évolutions de justesse et de débit des seuls élèves appariés.

Dans le graphique final interactif, survolez le point final pour lire le nombre de réussites sur les items présentés et le pourcentage à chacune des deux dates. Le graphique 01 du poste intégré calcule, lui, la justesse sur les réponses données. Une omission compte donc différemment entre les deux vues.

Le dossier créé contient :

- douze figures en PNG, PDF et SVG ;
- le graphique final de synthèse en PNG haute résolution 3000 × 2100, PDF et HTML interactif ;
- `final_performance_scatter_data.csv`, qui documente étalonnage, résultat final, débit, progression et groupe relatif ;
- deux explorations HTML interactives ;
- un rapport PDF de classe ;
- un rapport PDF par pseudonyme ;
- les corrélations, métadonnées, journaux et manifeste d’empreintes.

Les deux rendus utilisent les mêmes passations, les mêmes identifiants de calcul et les mêmes axes.

Si un graphique manque de données, l’analyse continue. La fenêtre finale indique son nom, `raison : manque de données` et une explication, par exemple un pool réduit à une seule évaluation. Si une fonction graphique rencontre réellement un défaut, elle indique `raison : code` et le message exact. Le même bilan est conservé dans `graph_generation_status.csv`.

## Supprimer une évaluation

Cliquer sur **Supprimer une évaluation**, choisir l’évaluation puis saisir un motif obligatoire. Après confirmation, l’évaluation disparaît des choix de passation, d’export et d’analyse.

La suppression est logique et traçable : aucun item, aucune tentative et aucune réponse brute n’est détruit. SQLite conserve `deleted_at`, `deletion_reason` et un événement `assessment_deleted` contenant le motif, l’horodatage, le titre et l’UUID. Une sauvegarde est créée lorsque les sauvegardes automatiques sont actives.

## Lire les principaux indicateurs

- Commencer par le nombre d’items présentés, répondus, omis et expirés.
- Lire la réussite avec le temps médian correct et son IQR ; ne pas réduire l’élève à « rapide/lent ».
- Vérifier la trajectoire plutôt qu’une session isolée.
- Distinguer les items d’ancrage des items renouvelés.
- Examiner les erreurs fréquentes et familles de faits avant un score global.
- Considérer les associations comme descriptives, jamais comme une preuve causale.

## Sauvegarde et restauration

**Fichier → Créer une sauvegarde locale** produit deux chemins lorsqu’une base d’identités existe. Conserver les deux fichiers. Pour restaurer :

1. fermer PyStats ;
2. copier la sauvegarde analytique vers `BDD/` avec l’extension `.sqlite` ;
3. copier sa base d’identités correspondante vers `BDD/_identities/` en respectant le nom `<base>.identities.sqlite` ;
4. rouvrir PyStats et choisir **Fichier → Ouvrir une base…**.

Ne jamais remplacer une base courante sans en conserver d’abord une copie. Les sauvegardes automatiques se trouvent dans un sous-dossier `backups` proche de la base.

## Dépannage

- **Rscript introuvable** : installer R, redémarrer le terminal et vérifier `Rscript --version`.
- **Graphique absent** : consulter `python_r_execution.log` puis `r_analysis.log`.
- **Noms absents** : vérifier que la base correspondante existe dans `_identities` ; les mesures pseudonymisées restent exploitables sans elle.
- **CSV élèves refusé** : contrôler les en-têtes `nom,prenom` et enregistrer en UTF-8.
- **Base historique** : la première ouverture déclenche une sauvegarde et une migration ; ne pas interrompre l’opération.
