# PyStats

PyStats est un logiciel de bureau libre et gratuit pour évaluer la fluence en calcul. Il permet aux enseignants de préparer des exercices, de suivre les progrès d’une classe ou d’un élève et de comparer la justesse et les temps de réponse au fil des évaluations.

- **Préparer une évaluation** avec des additions, des soustractions, des multiplications, des divisions ou des compléments à 10 ou à 100. Une même liste est présentée à tous les élèves. Des calculs communs peuvent servir de points de comparaison entre deux évaluations.
- **Faire passer l’épreuve** au pavé numérique, avec deux essais et des limites de temps facultatives. PyStats distingue le délai avant la première touche, la durée de saisie et le temps total.
- **Consulter les résultats** dans le tableau de bord, avec des vues par classe et par élève. Les analyses R ajoutent des graphiques et des rapports.
- **Exporter les données** en CSV pseudonymisés ou sous forme de statistiques agrégées. L’application sépare les identités des résultats dans deux bases locales.

## Est-ce que le programme a été généré partiellement ou intégralement par IA ?

Le projet PyStats a été assisté par intelligence artificielle. Mon travail s'est concentré sur l'architecture, la méthode, les outils et les inombrables essais afin de parvenir à une version exploitable.

## Installation

Depuis le [dépôt PyStats](https://github.com/fontaine-julien/pystats), choisissez **Code → Download ZIP**, puis décompressez le fichier dans un dossier où vous pouvez écrire. Si vous utilisez Git, vous pouvez aussi cloner le dépôt.

```bash
git clone https://github.com/fontaine-julien/pystats.git
cd pystats
```

Ouvrez un terminal dans le dossier qui contient `main.py`.

| Élément | Version ou rôle |
| --- | --- |
| Python | 3.11 ou plus récent |
| PySide6 | 6.8 ou plus récent, série 6. Installé via `requirements.txt` |
| SQLite | Fourni avec Python |
| R | 4.2 ou plus récent, uniquement pour les rapports et graphiques R |
| pytest | Installé avec les dépendances, utilisé pour les tests |

L’installation des dépendances demande un accès à Internet. Ensuite, l’application fonctionne hors connexion.

### Windows

Installez [Python pour Windows](https://www.python.org/downloads/windows/) et vérifiez que la commande `python --version` fonctionne dans PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Pour activer les rapports, installez [R pour Windows](https://cran.r-project.org/bin/windows/base/) et ajoutez le dossier contenant `Rscript.exe` à la variable `PATH`. Ouvrez un nouveau terminal et lancez `Rscript analysis/install_dependencies.R`.

### Linux

Utilisez une session graphique et un Python récent. Sur Debian ou Ubuntu, les paquets suivants fournissent Python et les bibliothèques Qt courantes pour X11.

```bash
sudo apt update
sudo apt install python3 python3-venv libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Les paquets système varient selon la distribution. Si Qt signale une bibliothèque manquante, consultez la [liste des dépendances Qt sous Linux](https://doc.qt.io/qt-6/linux-requirements.html).

Pour activer les rapports sous Debian ou Ubuntu, installez `r-base`, puis lancez `Rscript analysis/install_dependencies.R`. Pendant une passation sous Linux, activez Verr Num manuellement. L’interception globale des touches et la gestion automatique de Verr Num sont propres à Windows.

Le script `install_dependencies.R` vérifie les paquets fournis avec R. Pour le calcul du centre robuste du graphique final, vous pouvez ajouter le paquet facultatif `robustbase` depuis R avec `install.packages("robustbase")`.

## Première utilisation

1. Au démarrage, PyStats crée une base vide dans `BDD/`. Créez un projet pour votre classe et ajoutez les élèves ou importez une liste.
2. Choisissez **Nouvelle évaluation**, définissez les calculs, puis utilisez **Tester l’évaluation…** pour essayer le parcours.
3. Lancez la passation, puis ouvrez le tableau de bord pour comparer les résultats. Le menu **Rapports / exports** donne accès aux exports CSV et aux rapports R.

Conservez les bases, sauvegardes et exports d’élèves dans votre environnement de travail. Les exports pseudonymisés restent des données personnelles.

## Classe fictive de démonstration

L’exemple présente 25 élèves fictifs qui passent une évaluation étalon puis une évaluation finale, chacune avec 24 multiplications notées.

- [Résultats des deux évaluations en CSV](demo/resultats-classe-fictive.csv)
- [Graphique de position finale et de progression](demo/progression-classe-fictive.png)

Pour générer localement une base de démonstration et ses exports, lancez le script avec le Python de votre environnement virtuel.

```text
python scripts/generate_synthetic_example.py --skip-r
```

Ouvrez ensuite `examples/synthetic_class.sqlite` depuis **Ouvrir une base…**. Retirez `--skip-r` pour produire aussi les rapports. Les fichiers de démonstration générés restent dans `examples/`.

## Documentation

- [Guide utilisateur](USER_GUIDE_FR.md)
- [Méthodes statistiques](STATISTICAL_METHODS.md) et [limites](LIMITATIONS.md)
- [Dictionnaire des données](DATA_DICTIONARY.md) et [confidentialité des exports](ANONYMIZATION_METHOD.md)
- [Reproduction des analyses et tests](REPRODUCIBILITY.md)

## Licence et contributions

**Créateur d’origine de PyStats 2** · Julien Fontaine. [Profil GitHub de Julien Fontaine](https://github.com/fontaine-julien) · [Dépôt d’origine de PyStats](https://github.com/fontaine-julien/pystats)

Le code est libre et gratuit sous [licence MIT](LICENSE). Vous pouvez l’utiliser, le modifier et le redistribuer en conservant la licence et le crédit d’origine, avec le nom de Julien Fontaine et son lien GitHub, dans vos copies.

Les forks, les contributions et les retours d’expérience sont les bienvenus. Pour signaler un problème ou suggérer une amélioration, ouvrez une issue sur GitHub avec une description et, si possible, un exemple fictif.
