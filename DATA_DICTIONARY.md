# Dictionnaire des données

## Familiarisation facultative au pavé numérique (2.2.0)

- Configuration figée : `familiarization_enabled` (booléen, défaut `false`) et `familiarization_protocol` (`numpad_copy_v1`). Les anciennes configurations sans ces champs désactivent la phase.
- Table séparée `familiarization_trial` : tentative, position à partir de zéro, protocole, phase (`guided`, `guided_correction`, `measured`), cible et texte prérempli. Les 15 essais sont copiés à la création de la tentative ; aucune ligne n’est ajoutée aux items arithmétiques.
- `response_json` : réponse brute, exactitude, statut, horodatages, trois durées en millisecondes, nombres de frappes/corrections, événements et version logicielle. `record_hash` est l’empreinte SHA-256 du JSON canonique. Une réponse sauvegardée est immuable. Une valeur SQL NULL signifie « non présenté ».
- `keyboard_familiarization_trials.csv` : une ligne par essai prévu, y compris les non-présentés ; identifiants d’évaluation/tentative UUID et pseudonyme élève ; aucune identité directe. Les phases guidées restent identifiables et exclues des médianes.
- `keyboard_familiarization_summary.csv` : une ligne par tentative, y compris sans familiarisation. Les mêmes colonnes préfixées `familiarization_` sont jointes par UUID de tentative à `student_assessment_summary.csv` (dernière tentative retenue).
- `familiarization_status` : `disabled`, `not_started`, `in_progress`, `incomplete`, `completed`. « completed » signifie que les 15 essais ont un résultat non interrompu, même si certaines copies ont expiré ou sont fausses.
- `familiarization_measured_*` : nombres de copies présentées, correctes, incorrectes, omissions, expirations et corrections effectives. Les non-présentés ne sont pas comptés comme erreurs.
- `familiarization_1digit_valid_count` et `familiarization_2digit_valid_count` : nombres de copies correctes sans correction avec durées disponibles. Les médianes `familiarization_{1,2}digit_median_{reaction_time_first_key_ms,typing_time_ms,total_response_time_ms}` portent uniquement sur ces copies.
- Une médiane sans observation utilisable reste vide. Les comptes restent vides si la phase est désactivée ; zéro signifie aucune observation pour une phase activée. Dans l’essai guidé de suppression, le délai au premier chiffre peut être vide puisque seul Retour arrière puis Entrée est nécessaire.

Les deux nouveaux CSV et les colonnes facultatives ne sont jamais exigés par R. Le mode libre « Entraînement au clavier » ne crée aucune donnée en base et n’alimente aucun export.

## Conventions générales

- Encodage CSV : UTF-8 ; séparateur virgule ; première ligne = noms de colonnes.
- Dates/heures brutes : ISO 8601 en UTC quand un instant est enregistré.
- Dates d’évaluation : `AAAA-MM-JJ`.
- Durées : millisecondes (`_ms`) sauf limites de configuration en secondes (`_s`).
- Taux : proportion entre 0 et 1, sauf colonnes explicitement en pourcentage.
- Booléens SQLite/CSV : `0` faux, `1` vrai.
- Valeur CSV vide : mesure non applicable, non observée ou non récupérable ; le statut d’achèvement permet d’en préciser la cause.

## Niveaux d’identification

| Champ | Sens |
|---|---|
| `student_id` | Clé entière locale, interne à SQLite ; ne pas diffuser. |
| `student_internal_id` | Alias de compatibilité du pseudonyme stable dans le fichier long. |
| `student_export_id` | Pseudonyme stable aléatoire, par exemple `STU-A1B2C3D4E5`. |
| `first_name`, `last_name` | Identité réelle, uniquement dans la base d’identités et les fichiers `INTERNAL_ONLY`. |

## Base analytique SQLite

| Table | Clé et rôle | Champs essentiels |
|---|---|---|
| `meta` | `key` ; version et dernier contexte utilisé. | `key`, `value`. |
| `project` | `id` ; classe/projet local. | `name`, `created_at`. |
| `student` | `id` ; élève pseudonymisé. | `project_id`, `export_id`, `group_id`, `active`; les champs historiques de nom restent vides. |
| `assessment` | `id` ; protocole figé. | `assessment_uuid`, `title`, `config_json`, `assessment_version`, `assessment_date`, `academic_period`, `group_id`, `random_seed`, `software_version`, `frozen_at`, `items_hash`, `deleted_at`, `deletion_reason`. |
| `assessment_item` | `(assessment_id, idx)` ; item prévu. | `item_uuid`, `position`, `op`, `a`, `b`, `expected`, `kind`, `is_practice`, `is_anchor`, `fact_family`, `difficulty_category`, `fact_key`. |
| `assessment_roster` | `(assessment_id, student_id)` ; population figée. | Identifiants de l’évaluation et de l’élève. |
| `attempt` | `id` ; passation d’un élève. | `attempt_uuid`, dates, `duration_ms`, score, compteurs par statut, `ended_reason`, `integrity_hash`. |
| `attempt_item` | `(attempt_id, idx)` ; copie immuable de l’item pour la tentative. | Même sémantique que `assessment_item`. |
| `attempt_response` | `id` ; observation brute d’un item. | réponse, exactitude, horodatages, trois temps, événements, corrections, statuts, `record_hash`. |
| `response_key_event` | `(response_id, event_index)` ; journal de saisie. | `event_type`, `key_value`, `elapsed_ms`. |
| `audit_event` | `id` ; journal technique. | date, type d’événement, entité, détails JSON. |

La base latérale `identity.student_identity` associe `student_id`, `project_id`, `last_name`, `first_name`, `internal_export_id` et `created_at`.

## `responses_long_pseudonymized.csv`

Une ligne correspond à un item copié dans une tentative, y compris s’il n’a pas été présenté.

| Colonne | Définition |
|---|---|
| `assessment_id` | UUID stable de l’évaluation. |
| `assessment_version` | Version définie par l’enseignant. |
| `assessment_date` | Date prévue de passation. |
| `academic_period` | Période/libellé longitudinal. |
| `student_internal_id` | Pseudonyme stable, conservé pour compatibilité. |
| `student_export_id` | Pseudonyme stable recommandé pour les jointures. |
| `group_id` | Groupe pédagogique. |
| `item_id` | UUID stable de l’item. |
| `item_position` | Rang présenté, à partir de 1. |
| `is_practice_item` | Item d’entraînement, exclu des scores si 1. |
| `is_anchor_item` | Item repris d’une session de référence si 1. |
| `operation_type` | `addition`, `subtraction`, `multiplication`, `division`, `complement_10` ou `complement_100`. |
| `operand_1`, `operand_2` | Opérandes enregistrés ; `operand_2` peut être 0 pour un complément. |
| `expected_answer` | Réponse correcte entière. |
| `entered_answer` | Réponse entière validée ; vide sinon. |
| `is_correct` | 1/0 pour une réponse validée ; vide sinon. |
| `reaction_time_first_key_ms` | Présentation → premier appui numérique. |
| `typing_time_ms` | Premier appui → validation. |
| `total_response_time_ms` | Présentation → validation/expiration. |
| `keystroke_count` | Nombre d’événements de saisie retenus. |
| `correction_count` | Nombre de retours arrière/suppressions. |
| `timeout_status` | `none`, `item_limit` ou `global_limit`. |
| `completion_status` | `answered`, `omission`, `timeout`, `interrupted` ou `not_presented`. |
| `random_seed` | Graine de génération de l’évaluation. |
| `software_version` | Version PyStats ayant écrit la réponse. |
| `attempt_id` | UUID de la tentative. |
| `attempt_duration_ms` | Durée totale de la tentative. |
| `fact_family` | Famille/table pédagogique. |
| `difficulty_category` | Catégorie de difficulté issue de la génération. |

L’export nominatif long ajoute `last_name` et `first_name` devant ces colonnes, sans modifier leur sémantique.

## `student_assessment_summary.csv`

Une ligne correspond à la dernière tentative d’un élève pour une évaluation.

| Groupe de colonnes | Colonnes et sens |
|---|---|
| Contexte | `assessment_id`, `assessment_date`, `academic_period`, `student_export_id`, `group_id`, `attempt_id`. |
| Effectifs | `items_total`, `items_presented`, `items_answered`, `items_correct`, `items_incorrect`, `items_not_presented`. |
| Exactitude | `success_rate` = correctes/réponses validées. |
| Temps corrects | `mean_correct_time_ms`, `median_correct_time_ms`, `correct_time_sd_ms`, `correct_time_iqr_ms`, `correct_time_q10_ms`, `correct_time_q90_ms`. |
| Fluidité | `correct_per_minute`; indicateur secondaire combinant vitesse et exactitude. |
| Qualité | `omission_rate`, `timeout_rate`, `time_coefficient_variation`. |
| Évolution | `change_success_rate`, `change_median_correct_time_ms` par rapport à la session précédente de l’élève. |

`INTERNAL_ONLY_student_assessment_summary_nominative.csv` ajoute les deux colonnes d’identité réelle.

## Autres exports

### `fact_family_summary.csv`

`assessment_id`, `assessment_date`, `academic_period`, `fact_family`, `student_count`, `item_response_count`, `answered_count`, `success_rate`, `mean_correct_time_ms`, `median_correct_time_ms`, `correct_time_iqr_ms`, `correct_per_minute`, `students_below_80_percent`, `progress_success_rate`, `relative_rank`.

### `item_difficulty_summary.csv`

`assessment_id`, `fact_key`, opération/opérandes/réponse attendue, famille, difficulté, nombres de présentations/réponses, réussite, médiane/IQR des temps corrects, taux d’omission/délai, nombre et trois réponses erronées les plus fréquentes, position moyenne.

### `student_longitudinal_summary.csv`

Pseudonyme, nombre et bornes des sessions, réussite initiale/récente, pente de réussite par évaluation, temps médian initial/récent et pente temporelle. Une pente calculée sur deux ou trois dates reste descriptive.

### `class_longitudinal_summary.csv`

Évaluation/date/effectif, médiane et IQR des réussites individuelles, médiane et IQR des temps médians individuels.

### `assessment_items_frozen.csv`

UUID/version/graine/empreinte de l’évaluation puis UUID, position, type, drapeaux entraînement/ancrage, opération, opérandes, réponse, famille, difficulté et clé factuelle de chaque item.

### `public_anonymized_dataset.csv`

`session_number`, `fact_family`, `student_count_band`, `response_count_rounded_5`, `success_rate_rounded_5_percent`, `median_correct_time_rounded_250_ms`, `transformation_note`. Ce fichier ne comporte aucune ligne individuelle.

## Fichiers produits par R

| Fichier | Contenu |
|---|---|
| `correlation_results.csv` | méthode, variables, session éventuelle, estimateur, bornes bootstrap, effectif élèves/observations. |
| `position_effect_summary.csv` | position, réussite, temps médian correct et nombre d’observations. |
| `analysis_metadata.csv` | version, graine R, effectifs, période d’analyse et paramètres. |
| `R_SESSION_INFO.txt` | version R, plateforme et paquets chargés. |
| `r_analysis.log` | journal de l’analyse R. |
| `MANIFEST.json` | chemins relatifs, tailles et empreintes SHA-256 des entrées/sorties. |

## `final_performance_scatter_data.csv`

Une ligne unique par pseudonyme appartenant à l’union de l’étalonnage et de l’évaluation finale.

| Groupe | Colonnes principales |
|---|---|
| Appariement | `student_export_id`, `display_id`, `baseline_assessment_id`, `final_assessment_id`, `pairing_status`, `plot_eligible`. |
| Exactitude | `baseline_correct_count`, `final_correct_count`, `baseline_items_presented`, `final_items_presented`, `baseline_accuracy`, `final_accuracy`, `accuracy_change_raw`, `accuracy_change_proportion`. |
| Débit | `baseline_exact_rate_per_second`, `final_exact_rate_per_second`, durées valides et nombres d’items répondus valides. |
| Statuts | nombres d’omissions, expirations, interruptions et non-présentations à chaque date. |
| Position bivariée | `z_performance`, `performance_group`, `robust_distance`, centre, direction principale, écart-type de projection et méthode du centre. |
| Couleur | `accuracy_change_display`, `color_value_clipped`, `color_symmetric_limit`. La valeur brute n’est jamais remplacée. |

`pairing_status` vaut `complete`, `missing_baseline`, `missing_final` ou `invalid_duration`. Les items d’essai sont exclus. Les omissions et expirations comptent comme occasions présentées pour l’exactitude mais leur durée n’entre pas dans le débit ; interruptions techniques et items non présentés sont exclus des deux dénominateurs valides.

## `graph_generation_status.csv`

Une ligne par graphique demandé : `graph_name`, `file_stem`, `status`, `reason`, `comment`. `status` vaut `generated` ou `not_generated`. Un échec attendu porte la raison `manque de données`; une exception de fonction porte `code` et son message exact.
