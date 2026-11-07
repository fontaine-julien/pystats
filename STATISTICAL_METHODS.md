# Méthodes statistiques et choix scientifiques

## Familiarisation et aisance avec le pavé numérique

Le protocole facultatif `numpad_copy_v1` comprend trois essais guidés et douze copies mesurées, dont six à un chiffre et six à deux chiffres. Il constitue un compromis exploratoire de durée, à évaluer en pilote, et non une échelle validée de vitesse motrice. Les copies utilisent le même pavé numérique et sa touche Entrée que les calculs ; Retour arrière sert à corriger.

Les délais apparition → premier chiffre, premier chiffre → Entrée et apparition → Entrée décrivent aussi la reconnaissance du nombre, la recherche de touche, l’attention et la vérification. Ils ne séparent pas un temps de réaction pur et un temps de mouvement pur. Les médianes sont calculées séparément par longueur sur les copies correctes sans correction, accompagnées du nombre d’essais utilisables. Les erreurs, omissions, corrections et expirations restent disponibles dans les données brutes.

Les mesures sont conservées comme variables explicatives facultatives, sans soustraction automatique aux temps arithmétiques et sans modification des scores. Une familiarisation absente, désactivée ou incomplète ne doit exclure aucun élève des analyses arithmétiques ordinaires. Une analyse future utilisant explicitement ces variables devra rapporter ses propres données manquantes et son effectif.

Entre une référence et une évaluation finale, une amélioration peut être liée à une meilleure connaissance des faits arithmétiques, à l’habitude de l’outil, ou aux deux. Les mesures de copie ne démontrent pas que l’aisance a « libéré des ressources cognitives ». L’exposition au mode d’entraînement libre n’est pas enregistrée : si elle importe pour une étude, la documenter séparément. Pour tester une attribution causale, prévoir un protocole comparatif adapté et contrôler l’exposition à l’outil.

## Objet et population visée

PyStats suit l’exactitude et la fluidité de faits arithmétiques chez des élèves d’une même classe, typiquement environ 25 élèves observés à plusieurs reprises. Cette taille convient à une analyse pédagogique descriptive et longitudinale prudente. Elle ne suffit pas, à elle seule, à établir des normes, des diagnostics individuels, un modèle causal ou un étalonnage psychométrique complexe.

La fluidité est traitée comme une combinaison d’exactitude et d’efficacité/automaticité, conformément à la synthèse récente de McNeil et collègues. La vitesse n’est donc jamais interprétée indépendamment de l’exactitude, et une pratique chronométrée ne se justifie qu’après construction d’une réponse correcte.

## Variables temporelles

À partir de la version 2.3.0, l’écran élève utilise Verdana et une cible physique de 10 mm pour les chiffres, avec un clavier restreint. Cette cible est un choix de conception, non une norme validée. La version logicielle enregistrée avec chaque réponse permet d’identifier ce changement de présentation ; une comparaison longitudinale traversant ce changement doit le documenter. Aucun délai de transition n’est ajouté. Le chronométrage reste logiciel, sans synchronisation matérielle à l’affichage effectif de la dalle.

Pour chaque item, trois durées sont conservées en millisecondes :

- **latence du premier appui** : présentation → premier événement numérique ;
- **temps de saisie** : premier appui → validation ;
- **temps total de réponse** : présentation → validation ou expiration.

Le temps total est la variable principale de fluidité, car il est disponible selon une définition stable et inclut la décision puis la saisie. La latence du premier appui est un indicateur comportemental secondaire : elle dépend du processus cognitif, mais aussi de l’attention, du placement des mains et de l’interface. Le temps de saisie aide à repérer une difficulté motrice ou une correction sans la confondre avec la récupération du fait arithmétique.

Le chronométrage des durées emploie une horloge monotone à haute résolution ; les dates UTC servent seulement à la traçabilité. Cette séparation évite qu’un ajustement de l’horloge système produise une durée négative ou incohérente.

## Exactitude, omissions et dénominateurs

Les statuts sont exclusifs : `answered`, `omission`, `timeout`, `interrupted`, `not_presented`. La réussite principale est :

```text
réponses correctes / réponses effectivement validées
```

Les taux d’omission et de délai dépassé sont rapportés séparément, et le nombre d’items présentés apparaît à côté du nombre total prévu. Cette convention évite de transformer silencieusement une interruption technique en erreur arithmétique. Pour un usage plus sévère, l’enseignant peut recalculer un taux « correct / items prévus » à partir du fichier long.

Les deux items d’entraînement sont identifiés et exclus des scores. Les tentatives multiples restent toutes dans les données brutes ; les tableaux pédagogiques utilisent la dernière tentative de chaque élève et de chaque évaluation afin de ne pas compter deux fois le même élève.

## Description des distributions

Les temps de réponse sont positifs, souvent asymétriques et susceptibles de présenter une longue queue. PyStats ne leur superpose donc pas automatiquement une loi normale. Les statistiques principales sont la médiane, l’écart interquartile et les quantiles 10 % et 90 %. Moyenne, écart-type et coefficient de variation restent disponibles comme descriptions secondaires, pas comme preuve de normalité.

Les graphiques privilégient distributions empiriques, boîtes, trajectoires et cartes de chaleur. Un diagramme quantile–quantile ou une distribution ajustée peut être utilisé lors d’une analyse spécialisée, mais ni un test de Shapiro–Wilk ni un histogramme isolé ne doit déterminer automatiquement la méthode : avec peu d’observations, le test manque de puissance ; avec beaucoup d’items, il détecte des écarts minimes.

Le modèle lognormal est souvent plausible pour une description exploratoire, tandis que les familles gamma, inverse-gaussienne, ex-gaussienne ou Weibull peuvent parfois mieux convenir. Leur paramètre ne reçoit cependant pas une interprétation cognitive automatique : la synthèse de De Boeck et Jeon souligne que plusieurs distributions et processus peuvent produire des formes proches.

## Valeurs extrêmes et qualité

Les réponses ne sont jamais supprimées du fichier brut. Les sorties descriptives robustes réduisent l’influence des valeurs extrêmes sans fixer un seuil arbitraire. Les contrôles portent notamment sur :

- temps nul, négatif ou incohérent ;
- premier appui postérieur à la validation ;
- taux inhabituel d’omissions ou de délais dépassés ;
- effet de position suggérant fatigue, apprentissage pendant la session ou limite globale ;
- taux de réussite proche de 0 ou de 1, signalant un effet plancher ou plafond ;
- nombre excessif de corrections ou de tentatives.

Une exclusion scientifique éventuelle doit être définie avant l’analyse, appliquée dans une copie dérivée et documentée avec une analyse de sensibilité. Les recommandations classiques de Ratcliff et de Baayen & Milin montrent qu’une suppression mécanique des temps longs peut modifier substantiellement les résultats.

## Vitesse et exactitude

Les deux dimensions sont montrées côte à côte. Le graphique vitesse–exactitude place le taux de réussite face au temps médian correct ; les trajectoires indiquent si un élève devient plus rapide sans perdre en exactitude.

Le nombre de réponses correctes par minute est fourni comme indicateur secondaire facilement lisible. Il n’est pas un score pur : il combine exactitude, vitesse et parfois le comportement d’omission. Aucun score d’efficacité inverse imposé n’est utilisé. Bruyer et Brysbaert ont montré ses limites, notamment lorsque les taux d’erreur varient ou que vitesse et exactitude ne répondent pas aux hypothèses requises. Les scores composites discutés par Liesefeld et Janczyk peuvent être utiles dans certains protocoles expérimentaux, mais un score unique ferait ici disparaître des profils distincts : précis et lent, rapide et imprécis, ou rapide et précis.

Le seuil de 80 % dans le résumé par famille est un drapeau pédagogique, et non une norme validée ou un seuil diagnostique.

## Mesures répétées et évolution

Chaque mesure appartient à un élève et à une session. Il est incorrect de calculer une corrélation naïve sur toutes les lignes comme si elles étaient indépendantes. Les sorties comprennent :

1. des associations de Spearman séparées par session ;
2. une association répétée exploratoire, obtenue en classant les variables puis en les centrant à l’intérieur de chaque élève ;
3. un intervalle de confiance par rééchantillonnage des élèves entiers, ce qui conserve les observations répétées d’un même élève dans une même grappe.

La corrélation répétée publiée par Bakdash et Marusich motive cette séparation entre variation interindividuelle et intra-individuelle. L’implémentation par rangs centrés de PyStats est une approximation robuste et explicitement nommée comme telle, non l’estimateur paramétrique exact du paquet `rmcorr`.

Les pentes individuelles par session et les différences depuis la mesure précédente sont descriptives. Avec seulement trois dates, une pente est très sensible à une session atypique et ne constitue pas une trajectoire stable. Pour une étude confirmatoire plus riche, les choix recommandés seraient un modèle logistique mixte pour l’exactitude et un modèle mixte sur le logarithme des temps corrects, avec effets aléatoires d’élève et éventuellement d’item. Ces modèles ne sont pas automatisés ici : un effectif de classe, peu de sessions et des effets plafond peuvent rendre leur estimation instable.

## Items d’ancrage et comparabilité

Une évaluation peut réutiliser un petit ensemble d’items d’une session antérieure. Ces items d’ancrage doivent :

- représenter les opérations et difficultés visées ;
- rester strictement identiques dans leur formulation ;
- être répartis dans la séquence plutôt que regroupés ;
- être distingués des items renouvelés dans les exports ;
- rester assez peu nombreux pour limiter la mémorisation, typiquement 15 à 25 % des items notés selon l’objectif.

Les travaux d’ETS sur les ancres faibles ou localement dépendantes justifient cette prudence. Avec environ 25 élèves, PyStats utilise les ancres pour une comparaison descriptive, pas pour un équating formel ou une calibration IRT.

## Incertitude et petit effectif

Les résumés affichent toujours le nombre d’élèves et d’observations. Les intervalles de corrélation sont obtenus par 2 000 réplications bootstrap en grappes par défaut ; ils expriment l’incertitude d’échantillonnage dans cette classe, mais pas la validité externe vers d’autres écoles. Le nombre de réplications peut être réglé par `PYSTATS_BOOTSTRAP_REPLICATES` et est écrit dans les métadonnées. Lorsque les taux sont proches de 0 ou 1, leur variation apparente peut être faible malgré une incertitude réelle : le nombre de réponses et la distribution des élèves restent visibles.

Les analyses multiples sont exploratoires. Les valeurs de corrélation ne sont pas transformées en une série de décisions « significatif/non significatif », et aucun ajustement automatique ne remplace l’interprétation de l’ampleur, de l’intervalle et de la cohérence entre sessions.

## Visualisations retenues

Douze figures complémentaires sont produites en PNG, PDF et SVG : carte élève–item, nuage vitesse–exactitude, évolution des temps, évolution de la réussite, trajectoires conjointes, familles de faits, difficulté des items, corrélogramme, effet de position, coordonnées parallèles, évolution par famille et évolution des ancres.

Deux vues HTML interactives facilitent le repérage d’un pseudonyme. Les coordonnées parallèles ont été retenues comme vue multidimensionnelle, car elles laissent visibles réussite, temps, variabilité, omission et progression sans inventer de groupes. PCA, UMAP et partitionnement automatique ont été écartés : à l’échelle d’une classe, ils sont instables, sensibles aux choix de standardisation et trop faciles à surinterpréter.

### Synthèse bivariée finale

Le graphique final utilise le nombre d’items exacts lorsque tous les élèves ont le même dénominateur aux deux dates ; sinon l’axe horizontal bascule automatiquement vers le taux de réussite. L’axe vertical est le nombre d’items exacts divisé par la durée cumulée des réponses effectivement validées. Les essais, interruptions, pauses explicitement invalidées, omissions, expirations et non-présentations n’ajoutent pas de temps au dénominateur. Omissions et expirations restent toutefois des occasions présentées dans le dénominateur d’exactitude ; elles ne sont jamais transformées en temps de réponse exact.

Le centre et la covariance utilisent `robustbase::covMcd()` lorsque le paquet facultatif est disponible. Si le MCD échoue ou si le paquet est absent, le repli annoncé associe les médianes marginales à la covariance classique ; si celle-ci est singulière, axe, distances et ellipses sont omis plutôt que forcés. Le premier vecteur propre est orienté afin que la somme de ses composantes soit positive. La projection standardisée définit trois positions relatives : sous −1, entre −1 et +1, au-dessus de +1. Ces groupes décrivent la classe observée et ne sont pas des seuils scolaires.

Une ellipse à 68 % n’est tracée que pour un groupe d’au moins cinq élèves dont la covariance est inversible. Cette enveloppe est descriptive et ne garantit pas qu’une proportion fixe de la population y appartienne. La couleur des points représente le changement de taux de réussite en points de pourcentage, avec une palette divergente strictement centrée sur zéro et une limitation graphique robuste aux quantiles 5 %/95 % ; les valeurs non tronquées restent dans le CSV et les infobulles.

Le HTML relie chaque position d’étalonnage à la position finale par une flèche. Il montre une évolution observée, pas un effet causal de l’enseignement.

## Interprétation pédagogique et causalité

Une association entre rang de passation et temps ne démontre pas une fatigue ; une amélioration entre deux sessions ne démontre pas l’effet d’une intervention ; un élève lent n’est pas nécessairement en difficulté conceptuelle. Les résultats peuvent refléter familiarisation, contenu différent, environnement, stratégie, saisie ou limite temporelle. Les items d’ancrage et la métadonnée de session renforcent la comparabilité sans supprimer ces facteurs.

PyStats est un outil d’observation et de préparation pédagogique, pas un dispositif de décision automatisée. L’enseignant doit confronter les indicateurs aux productions, aux observations de classe et aux conditions de passation.

## Références

- Baayen, R. H., & Milin, P. (2010). *Analyzing Reaction Times*. International Journal of Psychological Research, 3(2), 12–28. https://doi.org/10.21500/20112084.807
- Bakdash, J. Z., & Marusich, L. R. (2017). Repeated Measures Correlation. *Frontiers in Psychology*, 8, 456. https://doi.org/10.3389/fpsyg.2017.00456
- Bruyer, R., & Brysbaert, M. (2011). Combining Speed and Accuracy in Cognitive Psychology: Is the Inverse Efficiency Score (IES) a Better Dependent Variable than the Mean Reaction Time (RT) and the Percentage of Errors (PE)? *Psychologica Belgica*, 51(1), 5–13. https://doi.org/10.5334/pb-51-1-5
- De Boeck, P., & Jeon, M. (2019). An Overview of Models for Response Times and Processes in Cognitive Tests. *Frontiers in Psychology*, 10, 102. https://doi.org/10.3389/fpsyg.2019.00102
- Liesefeld, H. R., & Janczyk, M. (2019). Combining speed and accuracy to control for speed–accuracy trade-offs. *Behavior Research Methods*, 51, 40–60. https://doi.org/10.3758/s13428-018-1076-x
- McNeil, N. M., et al. (2025). Arithmetic Fluency: A Review and Recommendations for Instruction. *Psychological Science in the Public Interest*, 26(1), 10–57. https://doi.org/10.1177/15291006241287726
- Ratcliff, R. (1993). Methods for dealing with reaction time outliers. *Psychological Bulletin*, 114(3), 510–532. https://doi.org/10.1037/0033-2909.114.3.510
- Roy, S., Guillaume, M., Van Rinsveld, A., Project iLead Consortium, & McCandliss, B. D. (2025). Evaluating arithmetic fluency with a tablet-based assessment in elementary school children. *npj Science of Learning*, 10, 19. https://doi.org/10.1038/s41539-025-00314-5
- Zu, J., & Liu, J. (2009). *A Comparison of Item Selection Procedures for Different Types of Anchor Tests in Test Equating*. ETS Research Report RR-09-30. https://doi.org/10.1002/j.2333-8504.2009.tb02201.x
