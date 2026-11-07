# Reproduction complète des analyses

## Environnement

Suivez les [instructions d’installation pour Windows ou Linux](README.md#installation). Lancez les commandes ci-dessous depuis le dossier du projet, avec le Python de votre environnement virtuel et `Rscript` dans le `PATH`. Le fichier `R_SESSION_INFO.txt` indique les versions utilisées pour chaque analyse.

## Validation Python et R

```powershell
python -m pytest -q
```

Les tests qui lancent les analyses utilisent R. Ils génèrent leurs données fictives dans des dossiers temporaires.

## Régénérer l’exemple complet

```powershell
python scripts/generate_synthetic_example.py
```

Cette commande génère dans `examples/` les fichiers suivants.

- une base de 25 élèves fictifs et sa base d’identités ;
- deux évaluations datées, une étalon et une finale, avec six items d’ancrage ;
- réponses exactes, erreurs, omissions, délais dépassés et profils longitudinaux ;
- tous les CSV, y compris les deux exemples nominatifs marqués internes ;
- les graphiques, les vues HTML et les rapports PDF ;
- un manifeste SHA-256.

La graine synthétique et les graines d’évaluation sont fixées dans le script. Deux exécutions avec les mêmes versions doivent reproduire les mêmes données logiques. Les identifiants, horodatages de création et fichiers graphiques peuvent varier d’une exécution à l’autre. Le manifeste inventorie les fichiers obtenus.

## Régénérer R à partir de CSV existants

```powershell
Rscript analysis/run_all.R examples/csv examples/r-resultats
```

Pour choisir explicitement les évaluations en ligne de commande, ajoutez en troisième et quatrième arguments les UUID de l’évaluation finale et de l’évaluation étalon. Par défaut, R utilise la dernière et la première date présentes dans les CSV. Dans l’application, le pool est toujours coché manuellement puis ces UUID sont transmis explicitement. Le script ne dépend pas du répertoire de travail R ni de variables cachées.

Le bootstrap utilise 2 000 réplications par défaut. Pour un contrôle rapide non destiné à un rapport final :

```powershell
$env:PYSTATS_BOOTSTRAP_REPLICATES=100
Rscript analysis/run_all.R examples/csv examples/r-resultats
Remove-Item Env:PYSTATS_BOOTSTRAP_REPLICATES
```

Pour une extraction créée par l’application, remplacer les deux chemins par le dossier contenant les CSV et un dossier de résultats vide.

## Flux de traçabilité

```text
config_json + random_seed
  → assessment_items_frozen.csv + items_hash
  → attempt_item (copie exacte)
  → attempt_response + record_hash
  → CSV pseudonymisés
  → run_all.R
  → figures/rapports/résultats
  → MANIFEST.json + R_SESSION_INFO.txt + journaux
```

`items_hash` vérifie la liste figée ; `record_hash` protège chaque observation brute ; `integrity_hash` résume la tentative ; `MANIFEST.json` inventorie les fichiers de l’analyse. Les déclencheurs SQLite empêchent la modification ou suppression des réponses brutes par l’application.

## Contrôles manuels recommandés

1. Comparer `random_seed`, `items_hash` et le nombre de lignes d’`assessment_items_frozen.csv`.
2. Vérifier que chaque élève d’une session possède les mêmes `item_id` et positions.
3. Contrôler que les noms sont absents de tous les fichiers hors `INTERNAL_ONLY`.
4. Vérifier que `reaction_time_first_key_ms + typing_time_ms` est cohérent avec `total_response_time_ms` pour les réponses validées.
5. Examiner `completion_status` avant de recalculer un taux.
6. Lire les journaux et le fichier de session R avant d’archiver une analyse.
7. Ouvrir au minimum le rapport de classe, un rapport individuel et une figure vectorielle.
8. Vérifier `graph_generation_status.csv`, le PNG final 3000 × 2100, son PDF et son HTML.
