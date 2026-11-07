# Journal des modifications

## 2.5.0 — 2026-11-04

- Entrée sur un champ vide conserve le calcul et son chronomètre. Les omissions volontaires nécessitent l'option de l'évaluation et la touche moins du pavé numérique. Le journal de réponse enregistre alors `keypad_skip`.

## 2.4.0 — 2026-11-03

- Consultation des paramètres et modification jusqu’au lancement de la première passation élève.
- Essai enseignant rejouable sur les items enregistrés. Clonage exact du protocole et des inscriptions pour une autre date.
- Exclusion des tentatives ouvertes ou interrompues des exports et des analyses. Une interruption permet une reprise et conserve le verrou sur le protocole.

## Poste d’analyse — 2026-09-18

- Accueil enseignant maximisé, présentation Windows classique, accès direct aux évaluations, passations et entraînement ; gestion et exports en menus.
- Sélection base / projet / évaluation / élève, liste recherchable et résumé statistique dans l’application.
- Quatre graphiques Qt sans dépendance supplémentaire : évolutions justesse et temps, nuage avec centre médian marginal, classement avec ex æquo. Vue agrandie au clic, retour Échap, curseur croix et coordonnées en barre d’état.
- Construction explicite en arrière-plan sur connexion SQLite en lecture seule, instantané conservé en mémoire, indication des résultats à actualiser après passation et rejet des calculs rendus obsolètes par un changement de contexte.
- Seuils par graphique, valeurs manquantes distinctes de zéro, dernière tentative terminée admissible par élève / évaluation. Les données brutes et le schéma restent inchangés.
- Tests des petits effectifs, reprises / interruptions, rangs, centre, navigation, curseur, construction asynchrone et invalidation ; aperçus sur données fictives en HD, Full HD et espace utile à 125 %.

## 2.3.0 — 2026-09-15

- Interface élève en Verdana, cible de 10 mm de hauteur visible des chiffres, adaptée aux dimensions de l’écran et à l’échelle Windows ; repli estimé à 15,6 pouces si les dimensions sont absentes ou incohérentes.
- Calculs compacts, dimensions constantes par série, champ blanc à contour gris, sans curseur clignotant ni sélection/déplacement du point d’insertion. Compléments présentés avec le champ manquant avant le signe égal.
- Même filtrage dans les calculs, copies et entraînement : chiffres du pavé, Entrée du pavé, Retour arrière et Échap. Suppression, flèches, opérateurs, point et chiffres du haut ignorés.
- Interception Windows temporaire des autres touches ordinaires lorsque la fenêtre élève est au premier plan ; Verr Num activé pendant la session et état précédent restauré au retour. Les séquences sécurisées Windows et commandes matérielles ne sont pas garanties bloquées.
- Échap conserve l’interruption et ferme la fenêtre élève en un appui ; clavier libéré avant le retour à l’enseignant. Aucun fondu ni délai de transition ajouté.
- Version logicielle actualisée pour distinguer les nouvelles conditions de présentation dans les réponses enregistrées. Schéma de données inchangé.

## 2.2.0 — 2026-09-15

- Familiarisation facultative, décochée par défaut : trois essais guidés et douze copies au pavé numérique avant les calculs, hors score et hors temps de l’épreuve.
- Conservation séparée des copies, événements et durées, exports pseudonymisés et médianes par longueur. Aucune donnée clavier requise pour les statistiques et graphiques existants.
- Menu et bouton « Entraînement au clavier » : copies aléatoires à un/deux chiffres sans fin, correction et retour immédiat, sortie par Échap, sans enregistrement.
- Chiffres et Entrée du pavé numérique, Retour arrière pour corriger ; répétitions automatiques ignorées.
- Schéma SQLite 4 : ajout non destructif de la table de familiarisation, sauvegarde avant migration et compatibilité des évaluations existantes.

## 2.1.0 — 2026-08-01

### Graphique final

- Ajout de la synthèse « réussite, fluence et progression » en PNG 3000 × 2100, PDF et HTML interactif.
- Ajout du CSV élève apparié avec exactitude, débit exact par seconde, progression proportionnelle, score projeté, groupe relatif et distance bivariée.
- Centre MCD via `robustbase::covMcd()` lorsqu’il est disponible, avec repli médian/covariance documenté.
- Axe principal orienté, palette divergente centrée sur zéro, ellipses conditionnées à cinq élèves et trajectoires interactives étalonnage → finale.
- Copie nominative HTML/CSV disponible uniquement après option et confirmation explicites ; R reste alimenté par les pseudonymes.

### Sélection et résilience

- Sélection manuelle obligatoire des évaluations incluses dans chaque analyse.
- Filtrage des CSV, graphiques longitudinaux, métadonnées et manifeste sur ce seul pool.
- Ajout de `graph_generation_status.csv` et poursuite de l’analyse lorsqu’un graphique manque de données.
- Fenêtre finale informative distinguant `manque de données` et `code` avec le message exact.

### Suppression auditée

- Suppression logique d’une évaluation avec justification obligatoire et confirmation.
- Conservation intégrale des items, tentatives et réponses.
- Ajout de `deleted_at`, `deletion_reason` et de l’événement d’audit atomique `assessment_deleted`.
- Exclusion des évaluations supprimées des passations, ancres, exports et analyses ordinaires.

### Validation

- Extension à 16 tests automatisés, dont appariement, dénominateurs, résolution PNG, axe principal, confidentialité, pool sélectionné, suppression et données insuffisantes.

## 2.0.0 — 2026-07-31

### Architecture et intégrité

- Ajout d’un schéma SQLite versionné avec migration non destructive et sauvegarde préalable.
- Séparation physique des identités dans une base latérale `_identities`.
- Génération de pseudonymes aléatoires stables sans dérivation des noms.
- Figement de la configuration et des items, UUID et empreinte SHA-256.
- Copie des items dans chaque tentative et protection des réponses brutes par déclencheurs.
- Journal d’audit et sauvegarde cohérente après chaque tentative réelle.

### Évaluations

- Ajout des six familles d’opérations demandées.
- Configuration des opérandes, nombre d’items, date, période, groupe, version et graine.
- Deux items d’entraînement obligatoires.
- Ordre fixe ou randomisation équilibrée reproductible.
- Réutilisation et dispersion d’items d’ancrage.
- Sans limite, limite globale, limite par item ou limites combinées.

### Passation et temps

- Nouvelle interface élève plein écran avec minuteur caché.
- Chronométrage monotone à haute résolution.
- Enregistrement séparé du premier appui, de la saisie et du temps total.
- Journal des touches, corrections, anti-double-validation et filtrage numérique.
- Distinction des omissions, expirations, interruptions et items non présentés.
- File d’élèves et reprise des élèves non terminés.

### Exports et confidentialité

- Fichier long pseudonymisé et résumés élève, famille, item et longitudinaux.
- Export des items figés et export public agrégé.
- Ajout explicite de deux exports nominatifs internes réservés à l’enseignant.
- Exclusion automatique des fichiers sensibles dans `.gitignore`.

### Statistiques et R

- Remplacement des représentations gaussiennes imposées par des résumés robustes.
- Corrélations de Spearman par session et analyse répétée par rangs centrés avec bootstrap par élève.
- Douze figures en PNG/PDF/SVG, deux visualisations HTML et rapports de classe/individuels.
- Journaux, métadonnées R, informations de session et manifeste SHA-256.

### Qualité et documentation

- Tests de génération, chronométrage, stockage, migration, export, confidentialité et R.
- Jeu synthétique complet de 25 élèves sur trois sessions.
- Audit, méthodes statistiques, anonymisation, dictionnaire, guide, reproduction et limites.
- Copie stable du code historique dans `LEGACY_SOURCE_2026-07-31.zip`.

## Version historique auditée — janvier 2026

- Application de bureau PySide6 fonctionnelle centrée sur la multiplication et les compléments.
- Stockage SQLite, import d’élèves, passation séquentielle, CSV et premiers scripts graphiques R.
- Pas de garantie complète de reproductibilité, de séparation des identités, d’événements temporels fins ni de traitement des mesures répétées.
