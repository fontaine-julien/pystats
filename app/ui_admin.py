"""Interface de gestion des classes, des évaluations et des exports."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import secrets
import sqlite3
from typing import Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.assessment_service import assessment_started, clone_assessment, create_assessment, load_assessment_config, update_assessment
from app.config import AssessmentConfig, parse_integer_values
from app.familiarization import copy_trials
from app.schema import ELIGIBLE_ATTEMPT_SQL
from app.export import export_analysis_bundle
from app.graph import generate_analysis_outputs
from app.ui_student import StudentContext, StudentWindow
from app.ui_keyboard_training import KeyboardTrainingWindow
from app.ui_dashboard import ResultsDashboard
from app.version import SOFTWARE_VERSION


BASE_DIR = Path(__file__).resolve().parents[1]
BDD_DIR = str(BASE_DIR / "BDD")
EXTRACTIONS_DIR = str(BASE_DIR / "extractions")
GRAPH_DIR = str(BASE_DIR / "analysis_outputs")
LAST_DB_FILE = str(Path(BDD_DIR) / "last_db.txt")


def _ensure_dirs() -> None:
    for directory in (BDD_DIR, EXTRACTIONS_DIR, GRAPH_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)


def _load_last_db_path() -> Optional[str]:
    _ensure_dirs()
    path = Path(LAST_DB_FILE)
    if not path.exists():
        return None
    try:
        value = path.read_text(encoding="utf-8-sig").strip()
        if not value:
            return None
        saved = Path(value)
        if saved.is_absolute():
            # Ramène les anciens chemins absolus au dossier BDD courant.
            parts = saved.parts
            bdd = [i for i, part in enumerate(parts) if part.casefold() == "bdd"]
            if not bdd:
                return None
            saved = Path(*parts[bdd[-1] + 1:])
        root = Path(BDD_DIR).resolve()
        local = (root / saved).resolve()
        if not local.is_relative_to(root) or not local.is_file():
            return None
        if value != local.relative_to(root).as_posix():
            _save_last_db_path(str(local))
        return str(local)
    except OSError:
        return None


def _save_last_db_path(path: str) -> None:
    _ensure_dirs()
    root = Path(BDD_DIR).resolve()
    selected = Path(path).resolve()
    if selected.is_relative_to(root):
        Path(LAST_DB_FILE).write_text(selected.relative_to(root).as_posix(), encoding="utf-8")


class StudentSelectionDialog(QDialog):
    def __init__(self, parent, students: list[dict], title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._students = students
        root = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher (nom ou prénom)…")
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)
        buttons = QHBoxLayout()
        all_button = QPushButton("Tout cocher")
        none_button = QPushButton("Tout décocher")
        all_button.clicked.connect(self.check_all)
        none_button.clicked.connect(self.uncheck_all)
        buttons.addWidget(all_button)
        buttons.addWidget(none_button)
        root.addLayout(buttons)
        self.listw = QListWidget()
        root.addWidget(self.listw, 1)
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)
        root.addWidget(dialog_buttons)
        for student in self._students:
            item = QListWidgetItem(f"{student['last_name']} {student['first_name']}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, int(student["id"]))
            self.listw.addItem(item)

    def _apply_filter(self, text: str) -> None:
        query = (text or "").strip().lower()
        for index in range(self.listw.count()):
            item = self.listw.item(index)
            item.setHidden(bool(query and query not in item.text().lower()))

    def check_all(self) -> None:
        for index in range(self.listw.count()):
            item = self.listw.item(index)
            if not item.isHidden():
                item.setCheckState(Qt.Checked)

    def uncheck_all(self) -> None:
        for index in range(self.listw.count()):
            item = self.listw.item(index)
            if not item.isHidden():
                item.setCheckState(Qt.Unchecked)

    def selected_student_ids(self) -> list[int]:
        return [
            int(self.listw.item(index).data(Qt.UserRole))
            for index in range(self.listw.count())
            if self.listw.item(index).checkState() == Qt.Checked
        ]


class AssessmentSelectionDialog(QDialog):
    """Sélection explicite des évaluations à comparer."""

    def __init__(self, parent, assessments: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Sélection des évaluations à analyser")
        self.setModal(True)
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        explanation = QLabel(
            "Cochez uniquement les évaluations à inclure. La première date sélectionnée servira "
            "d’étalonnage et la dernière d’évaluation finale. Les graphiques longitudinaux ne "
            "considéreront aucune autre évaluation."
        )
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        toggle_row = QHBoxLayout()
        all_button = QPushButton("Tout cocher")
        none_button = QPushButton("Tout décocher")
        all_button.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_button.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        toggle_row.addWidget(all_button)
        toggle_row.addWidget(none_button)
        root.addLayout(toggle_row)
        self.listw = QListWidget()
        root.addWidget(self.listw, 1)
        for assessment in assessments:
            label = (
                f"{assessment['assessment_date']} — #{assessment['id']} — {assessment['title']} "
                f"(version {assessment['assessment_version']})"
            )
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, int(assessment["id"]))
            self.listw.addItem(item)
        self.nominative_labels = QCheckBox(
            "Créer aussi les figures, rapports et tableaux enseignant avec nom et prénom"
        )
        self.nominative_labels.setChecked(True)
        root.addWidget(self.nominative_labels)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_selected)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _set_all(self, state: Qt.CheckState) -> None:
        for index in range(self.listw.count()):
            self.listw.item(index).setCheckState(state)

    def _accept_if_selected(self) -> None:
        if not self.selected_assessment_ids():
            QMessageBox.information(self, "Sélection requise", "Cochez au moins une évaluation.")
            return
        self.accept()

    def selected_assessment_ids(self) -> list[int]:
        return [
            int(self.listw.item(index).data(Qt.UserRole))
            for index in range(self.listw.count())
            if self.listw.item(index).checkState() == Qt.Checked
        ]

    def include_nominative_labels(self) -> bool:
        return self.nominative_labels.isChecked()


class AssessmentConfigDialog(QDialog):
    OPERATION_LABELS = {
        "addition": "Addition",
        "subtraction": "Soustraction",
        "multiplication": "Multiplication",
        "division": "Division",
        "complement_10": "Compléments à 10",
        "complement_100": "Compléments à 100",
    }

    def __init__(self, parent, prior_assessments: list[dict], *, title="", config=None, locked=False):
        super().__init__(parent)
        self.setWindowTitle("Paramètres de l’évaluation" if config else "Créer une évaluation reproductible")
        self.setMinimumWidth(620)
        self._result: tuple[str, AssessmentConfig] | None = None
        self.original = config
        root = QVBoxLayout(self)
        if locked:
            root.addWidget(QLabel("Lecture seule · Une passation élève a déjà commencé."))
        fields = QWidget()
        form = QFormLayout(fields)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Ex. Tables — période 2")
        form.addRow("Nom de l’évaluation :", self.title)
        operation_box = QGroupBox("Opérations évaluées")
        operation_layout = QGridLayout(operation_box)
        self.operation_checks: dict[str, QCheckBox] = {}
        for index, (operation, label) in enumerate(self.OPERATION_LABELS.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(operation == "multiplication")
            self.operation_checks[operation] = checkbox
            operation_layout.addWidget(checkbox, index // 2, index % 2)
        form.addRow(operation_box)
        self.operand_1 = QLineEdit("1-10")
        self.operand_2 = QLineEdit("1-10")
        form.addRow("Premiers opérandes/tables :", self.operand_1)
        form.addRow("Seconds opérandes :", self.operand_2)
        operand_help = QLabel("Notation acceptée : 1-10,12,15")
        form.addRow("", operand_help)
        self.n_items = QSpinBox()
        self.n_items.setRange(1, 1000)
        self.n_items.setValue(50)
        form.addRow("Items notés :", self.n_items)
        form.addRow("Items d’essai :", QLabel("2 (obligatoires, non comptabilisés)"))
        self.allow_omissions = QCheckBox("Autoriser à passer un calcul avec la touche − du pavé numérique")
        form.addRow("", self.allow_omissions)
        self.familiarization = QCheckBox("Familiarisation au pavé numérique (facultative)")
        self.familiarization.setToolTip(
            "Avant les calculs : 3 essais guidés puis 12 copies mesurées. "
            "Chiffres et Entrée au pavé numérique, Retour arrière pour corriger. "
            "Hors score et hors temps de l’épreuve ; aucune statistique ne l’exige."
        )
        form.addRow("", self.familiarization)
        self.anchor_count = QSpinBox()
        self.anchor_count.setRange(0, 500)
        form.addRow("Items d’ancrage :", self.anchor_count)
        self.anchor_source = QComboBox()
        self.anchor_source.addItem("Aucun", None)
        for assessment in prior_assessments:
            self.anchor_source.addItem(f"#{assessment['id']} — {assessment['title']}", int(assessment["id"]))
        form.addRow("Évaluation source des ancrages :", self.anchor_source)
        self.global_limit = QDoubleSpinBox()
        self.global_limit.setRange(0, 7200)
        self.global_limit.setDecimals(1)
        self.global_limit.setSuffix(" s")
        self.global_limit.setSpecialValueText("0 — illimitée")
        form.addRow("Limite globale :", self.global_limit)
        self.item_limit = QDoubleSpinBox()
        self.item_limit.setRange(0, 300)
        self.item_limit.setDecimals(1)
        self.item_limit.setSuffix(" s")
        self.item_limit.setSpecialValueText("0 — illimitée")
        form.addRow("Limite par item :", self.item_limit)
        self.order_mode = QComboBox()
        self.order_mode.addItem("Aléatoire équilibré puis figé", "balanced_random")
        self.order_mode.addItem("Ordre déterministe puis figé", "fixed")
        form.addRow("Ordre :", self.order_mode)
        if config:
            categories = {"easy": "facile", "medium": "moyenne", "hard": "difficile"}
            form.addRow("Catégories de difficulté :", QLabel(", ".join(
                categories.get(value, value) for value in config.difficulty_categories)))
        self.assessment_date = QDateEdit(QDate.currentDate())
        self.assessment_date.setCalendarPopup(True)
        self.assessment_date.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Date :", self.assessment_date)
        self.period = QLineEdit()
        self.period.setPlaceholderText("Ex. Période 2")
        form.addRow("Période pédagogique :", self.period)
        self.group_id = QLineEdit("classe")
        form.addRow("Groupe :", self.group_id)
        self.version = QLineEdit("1")
        form.addRow("Version de l’évaluation :", self.version)
        self.seed = QLineEdit(str(secrets.randbits(63)))
        form.addRow("Graine aléatoire :", self.seed)
        if config:
            self.title.setText(title)
            for op, box in self.operation_checks.items():
                box.setChecked(op in config.operations)
            self.operand_1.setText(",".join(map(str, config.operand_1_values)))
            self.operand_2.setText(",".join(map(str, config.operand_2_values)))
            for box, value in ((self.n_items, config.n_scored_items), (self.anchor_count, config.anchor_count),
                               (self.item_limit, config.item_time_limit_s or 0),
                               (self.global_limit, config.global_time_limit_s or 0)):
                if isinstance(box, QDoubleSpinBox):
                    box.setDecimals(max(1, -Decimal(str(value)).as_tuple().exponent))
                box.setMaximum(max(box.maximum(), value))
                box.setValue(value)
            self.familiarization.setChecked(config.familiarization_enabled)
            self.allow_omissions.setChecked(config.allow_omissions)
            source_id = config.anchor_source_assessment_id
            if source_id is not None and self.anchor_source.findData(source_id) < 0:
                self.anchor_source.addItem(f"#{source_id} (source archivée)", source_id)
            self.anchor_source.setCurrentIndex(self.anchor_source.findData(source_id))
            self.order_mode.setCurrentIndex(self.order_mode.findData(config.order_mode))
            self.assessment_date.setDate(QDate.fromString(config.assessment_date, "yyyy-MM-dd"))
            self.period.setText(config.academic_period)
            self.group_id.setText(config.group_id)
            self.version.setText(config.assessment_version)
            self.seed.setText(str(config.random_seed))
        fields.setEnabled(not locked)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(fields)
        root.addWidget(scroll)
        self.resize(650, min(740, self.screen().availableGeometry().height() - 80))
        buttons = QDialogButtonBox(QDialogButtonBox.Close if locked else QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        if not locked:
            buttons.button(QDialogButtonBox.Save).setText("Enregistrer" if config else "Créer")
            buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        try:
            operations = tuple(operation for operation, box in self.operation_checks.items() if box.isChecked())
            if self.original and set(operations) == set(self.original.operations):
                operations = self.original.operations
            title = self.title.text().strip()
            if not title:
                raise ValueError("Le nom de l’évaluation est obligatoire.")
            anchor_source = self.anchor_source.currentData()
            if self.anchor_count.value() and anchor_source is None:
                raise ValueError("Sélectionnez une évaluation source pour les items d’ancrage.")
            config = AssessmentConfig(
                operations=operations,
                operand_1_values=self._operand_values(self.operand_1, "operand_1_values"),
                operand_2_values=self._operand_values(self.operand_2, "operand_2_values"),
                n_scored_items=self.n_items.value(),
                n_practice_items=2,
                familiarization_enabled=self.familiarization.isChecked(),
                allow_omissions=self.allow_omissions.isChecked(),
                anchor_count=self.anchor_count.value(),
                anchor_source_assessment_id=anchor_source,
                global_time_limit_s=self.global_limit.value() or None,
                item_time_limit_s=self.item_limit.value() or None,
                order_mode=str(self.order_mode.currentData()),
                assessment_date=self.assessment_date.date().toString("yyyy-MM-dd"),
                academic_period=self.period.text().strip(),
                group_id=self.group_id.text().strip() or "classe",
                difficulty_categories=self.original.difficulty_categories if self.original else ("easy", "medium", "hard"),
                random_seed=int(self.seed.text().strip()),
                assessment_version=self.version.text().strip() or "1",
            )
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Configuration invalide", str(error))
            return
        self._result = (title, config)
        self.accept()

    def _operand_values(self, field, key):
        if self.original:
            values = getattr(self.original, key)
            if field.text() == ",".join(map(str, values)):
                return values
        return parse_integer_values(field.text())

    def result_config(self) -> tuple[str, AssessmentConfig] | None:
        return self._result


class AdminWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        _ensure_dirs()
        self.db = db
        self.setWindowTitle(f"PyStats {SOFTWARE_VERSION} — Poste d’analyse")
        self.resize(1440, 900)
        self.setMinimumSize(1060, 650)
        self.setFont(QFont("Tahoma", 9))
        self.setObjectName("teacherWorkstation")
        self.project_id: int | None = None
        self.assessment_id: int | None = None
        self._queue: list[dict] | None = None
        self._student_win: StudentWindow | None = None
        self._keyboard_training_win: KeyboardTrainingWindow | None = None
        self._build_menu()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        toolbar = QToolBar("Fonctions essentielles", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        open_action = toolbar.addAction("Ouvrir une base…")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.menu_open_db)
        toolbar.addSeparator()
        actions = [
            ("Créer un projet", self.create_project),
            ("Importer le CSV des élèves", self.import_csv),
            ("Créer une évaluation", self.create_assessment),
            ("Paramètres de l’évaluation…", self.assessment_settings),
            ("Tester l’évaluation…", self.preview_assessment),
            ("Cloner l’évaluation…", self.clone_assessment_flow),
            ("Lancer la passation", self.launch_with_selection),
            ("Entraînement au clavier", self.launch_keyboard_training),
            ("Reprendre une évaluation", self.resume_assessment_flow),
            ("Supprimer une évaluation", self.delete_assessment_flow),
            ("Exporter les données pseudonymisées", self.export_stats_flow),
            ("Exporter une copie nominative interne", self.export_nominative_flow),
            ("Produire l’analyse et les graphiques R", self.graph_flow),
        ]
        self.buttons: dict[str, QPushButton] = {}
        management = self.menuBar().addMenu("Gestion")
        reports = self.menuBar().addMenu("Rapports / exports")
        for label, handler in actions:
            if label in ("Créer une évaluation", "Lancer la passation", "Reprendre une évaluation", "Entraînement au clavier"):
                button = QPushButton(label)
                button.clicked.connect(handler)
                self.buttons[label] = button
                button.setText({"Créer une évaluation": "Nouvelle évaluation", "Lancer la passation": "Faire passer",
                                "Reprendre une évaluation": "Reprendre", "Entraînement au clavier": "Entraînement clavier"}[label])
                toolbar.addWidget(button)
            else:
                menu = reports if label.startswith(("Exporter", "Produire")) else management
                action = menu.addAction(label)
                action.triggered.connect(handler)
        self.dashboard = ResultsDashboard(self.db)
        layout.addWidget(self.dashboard, 1)
        self.dashboard.project_changed.connect(self._select_project)
        self.dashboard.scope_changed.connect(self._select_scope)
        self.dashboard.status.connect(self._coordinate_status)
        self.dashboard.edit_student_requested.connect(self.edit_student)
        self.dashboard.remove_student_requested.connect(self.remove_student)
        self.dashboard.delete_student_assessment_requested.connect(self.delete_student_assessment)
        self.statusBar().setSizeGripEnabled(True)
        self._coordinate_status("")
        self._load_default_project()
        self.refresh()

    def _coordinate_status(self, message: str) -> None:
        self.statusBar().showMessage(message or "Prêt · double-cliquez sur un nom pour le modifier, ou cliquez sur un graphique pour l’agrandir")

    def _select_project(self, project_id) -> None:
        self.project_id = project_id
        self.assessment_id = None
        self.db.set_meta("last_project_id", str(project_id) if project_id is not None else "")
        self.refresh()

    def _select_scope(self, assessment_id) -> None:
        self.assessment_id = assessment_id
        self.db.set_meta("last_assessment_id", str(assessment_id) if assessment_id is not None else "")
        self.buttons["Lancer la passation"].setEnabled(assessment_id is not None)
        self._update_info()

    def closeEvent(self, event) -> None:
        if self.dashboard.worker:
            self.dashboard.worker.wait()
            self.dashboard.worker = None
        super().closeEvent(event)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Fichier")
        for label, handler in (
            ("Nouvelle base…", self.menu_new_db),
            ("Ouvrir une base…", self.menu_open_db),
            ("Ouvrir la dernière base", self.menu_open_last_db),
            ("Créer une sauvegarde locale", self.menu_backup),
        ):
            action = QAction(label, self)
            action.triggered.connect(handler)
            menu.addAction(action)
        training_menu = self.menuBar().addMenu("Entraînement")
        training_action = QAction("Entraînement au clavier", self)
        training_action.triggered.connect(self.launch_keyboard_training)
        training_menu.addAction(training_action)

    def launch_keyboard_training(self) -> None:
        if self._keyboard_training_win is not None and self._keyboard_training_win.isVisible():
            self._keyboard_training_win.raise_()
            return
        self._keyboard_training_win = KeyboardTrainingWindow(self.show)
        self.hide()
        self._keyboard_training_win.showFullScreen()
        self._keyboard_training_win.answer.setFocus()

    def menu_new_db(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvelle base", "Nom du fichier (sans extension) :")
        if not ok or not name.strip():
            return
        safe = "".join(character for character in name.strip() if character.isalnum() or character in "-_")
        if not safe:
            QMessageBox.warning(self, "Erreur", "Nom invalide.")
            return
        self._open_db_path(str(Path(BDD_DIR) / f"{safe}.sqlite"))

    def menu_open_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une base", BDD_DIR, "SQLite (*.sqlite *.db);;Tous (*.*)")
        if path:
            self._open_db_path(path)

    def menu_open_last_db(self) -> None:
        path = _load_last_db_path()
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Erreur", "Aucune dernière base trouvée.")
            return
        self._open_db_path(path)

    def menu_backup(self) -> None:
        main_path, identity_path = self.db.create_local_backup("manual")
        QMessageBox.information(
            self,
            "Sauvegarde créée",
            f"Données : {main_path}\nIdentités : {identity_path or 'aucune'}",
        )

    def _open_db_path(self, path: str) -> None:
        self.db.open(path)
        _save_last_db_path(path)
        self.project_id = None
        self.assessment_id = None
        self._queue = None
        self._load_default_project()
        self.assessment_id = None
        self.refresh()

    def _load_default_project(self) -> None:
        project_meta = self.db.get_meta("last_project_id")
        if project_meta and project_meta.isdigit() and self.db.q("SELECT id FROM project WHERE id=?", (int(project_meta),)):
            self.project_id = int(project_meta)
        else:
            rows = self.db.q("SELECT id FROM project ORDER BY id LIMIT 1")
            self.project_id = int(rows[0]["id"]) if rows else None
        assessment_meta = self.db.get_meta("last_assessment_id")
        if assessment_meta and assessment_meta.isdigit() and self.db.q(
            "SELECT id FROM assessment WHERE id=? AND project_id=? AND deleted_at IS NULL",
            (int(assessment_meta), self.project_id)
        ):
            self.assessment_id = int(assessment_meta)

    def refresh(self) -> None:
        self._update_info()
        self.dashboard.reload(self.project_id, self.assessment_id)

    def _update_info(self) -> None:
        database_name = Path(self.db.path).name if self.db.path else "?"
        if self.db.path and not Path(self.db.path).is_relative_to(Path(BDD_DIR)):
            database_name = f"{self.db.path} (base externe, pour cette session)"
        self.info.setToolTip(str(self.db.path or ""))
        if self.project_id is None:
            self.info.setText(f"Base : {database_name} — aucun projet")
        else:
            count = len(self.db.list_students(self.project_id))
            self.info.setText(
                f"Base : {database_name} — projet #{self.project_id} — {count} élèves — "
                f"évaluation active : {self.assessment_id or 'aucune'}"
            )
        self.buttons["Lancer la passation"].setEnabled(self.assessment_id is not None)

    def create_project(self) -> None:
        name, ok = QInputDialog.getText(self, "Projet", "Nom du projet :")
        if not ok or not name.strip():
            return
        self.project_id = self.db.exec(
            "INSERT INTO project(name,created_at) VALUES(?,datetime('now'))", (name.strip(),)
        )
        self.db.set_meta("last_project_id", str(self.project_id))
        self.assessment_id = None
        self.refresh()

    def edit_student(self, student_id: int) -> None:
        student = self.db.get_student_identity(student_id)
        if student is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Modifier l’identité de l’élève")
        form = QFormLayout(dialog)
        last = QLineEdit(student["last_name"])
        first = QLineEdit(student["first_name"])
        form.addRow("Nom", last)
        form.addRow("Prénom", first)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        def validate():
            buttons.button(QDialogButtonBox.Save).setEnabled(bool(last.text().strip() and first.text().strip()))
        last.textChanged.connect(validate)
        first.textChanged.connect(validate)
        validate()
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            self.db.rename_student(student_id, last.text(), first.text())
            self.refresh()

    def remove_student(self, student_id: int) -> None:
        name = self.dashboard.name(student_id)
        if QMessageBox.question(self, "Supprimer définitivement l’élève",
                f"Supprimer définitivement {name} de la base ouverte ?\n\n"
                "Son identité, ses inscriptions et toutes ses passations seront effacées, "
                "y compris les pré-tests, les réponses et les données d’entraînement associées.\n\n"
                "Cette action est irréversible dans la base ouverte.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            try:
                self.db.remove_student(student_id)
            except (sqlite3.Error, ValueError) as error:
                QMessageBox.warning(self, "Suppression impossible", str(error))
                return
            self.refresh()

    def delete_student_assessment(self, student_id: int, assessment_id: int) -> None:
        assessment = next((r for r in self.db.list_assessments(self.project_id) if r["id"] == assessment_id), None)
        if assessment is None or not any(r["id"] == student_id for r in self.db.list_students(self.project_id)):
            return
        name = self.dashboard.name(student_id)
        if QMessageBox.question(self, "Supprimer les résultats de cet élève",
                f"Supprimer définitivement les résultats de {name} pour "
                f"« {assessment['title']} » du {assessment['assessment_date']} ?\n\n"
                "Tous ses essais pour cette évaluation, leurs réponses et leurs données "
                "d’entraînement associées seront effacés. L’élève restera inscrit pour pouvoir la repasser.\n\n"
                "Cette action est irréversible dans la base ouverte.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.db.delete_student_assessment(student_id, assessment_id)
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "Suppression impossible", str(error))
            return
        self.refresh()

    def import_csv(self) -> None:
        if self.project_id is None:
            QMessageBox.warning(self, "Erreur", "Créez d’abord un projet.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "CSV des élèves", "", "CSV (*.csv)")
        if not path:
            return
        imported = 0
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(stream, delimiter=delimiter)
            fields = {str(column).lower(): column for column in (reader.fieldnames or [])}
            if "nom" not in fields or "prenom" not in fields:
                QMessageBox.warning(self, "Erreur", "Colonnes requises : nom, prenom. Colonne optionnelle : groupe.")
                return
            for row in reader:
                last_name = str(row.get(fields["nom"]) or "").strip()
                first_name = str(row.get(fields["prenom"]) or "").strip()
                group_field = fields.get("groupe")
                group_id = str(row.get(group_field) or "classe").strip() if group_field else "classe"
                if last_name and first_name:
                    self.db.create_student(self.project_id, last_name, first_name, group_id)
                    imported += 1
        QMessageBox.information(self, "Import terminé", f"{imported} élèves importés.")
        self.refresh()

    def create_assessment(self) -> None:
        if self.project_id is None:
            QMessageBox.warning(self, "Erreur", "Créez d’abord un projet.")
            return
        prior = [
            dict(row)
            for row in self.db.q(
                "SELECT id,title FROM assessment WHERE project_id=? AND deleted_at IS NULL ORDER BY id DESC",
                (self.project_id,),
            )
        ]
        dialog = AssessmentConfigDialog(self, prior)
        if dialog.exec() != QDialog.Accepted or dialog.result_config() is None:
            return
        title, config = dialog.result_config()
        try:
            self.assessment_id = create_assessment(self.db, self.project_id, title, config)
        except Exception as error:
            QMessageBox.warning(self, "Création impossible", str(error))
            return
        self.db.set_meta("last_assessment_id", str(self.assessment_id))
        self.refresh()
        QMessageBox.information(
            self,
            "Évaluation créée",
            f"Évaluation #{self.assessment_id} créée.\nGraine : {config.random_seed}\n"
            "Vous pouvez la tester et modifier ses paramètres jusqu’à la première passation élève.",
        )

    def _target_assessment(self, action):
        if self.assessment_id is not None:
            return self.assessment_id
        picked = self._choose_assessment(action)
        return picked[0] if picked else None

    def assessment_settings(self):
        assessment_id = self._target_assessment("Paramètres de l’évaluation")
        if assessment_id is None:
            return
        row = self.db.q("SELECT title,project_id FROM assessment WHERE id=?", (assessment_id,))[0]
        prior = [a for a in self.db.list_assessments(row["project_id"]) if a["id"] != assessment_id]
        dialog = AssessmentConfigDialog(self, prior, title=row["title"], config=load_assessment_config(self.db, assessment_id),
                                        locked=assessment_started(self.db, assessment_id))
        if dialog.exec() == QDialog.Accepted and dialog.result_config():
            try:
                update_assessment(self.db, assessment_id, *dialog.result_config())
            except (ValueError, RuntimeError, OverflowError) as error:
                QMessageBox.warning(self, "Modification impossible", str(error))
                return
            self.refresh()

    def clone_assessment_flow(self):
        source = self._target_assessment("Cloner l’évaluation")
        if source is None:
            return
        row = self.db.q("SELECT title,academic_period FROM assessment WHERE id=?", (source,))[0]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Cloner « {row['title']} »")
        form = QFormLayout(dialog)
        form.addRow(QLabel("La copie reprend les mêmes items, dans le même ordre, et les mêmes élèves inscrits."))
        title = QLineEdit(f"{row['title']} — copie")
        date = QDateEdit(QDate.currentDate())
        date.setCalendarPopup(True)
        period = QLineEdit(row["academic_period"])
        form.addRow("Nom de la copie", title)
        form.addRow("Date de passation", date)
        form.addRow("Période pédagogique", period)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.assessment_id = clone_assessment(self.db, source, title.text(), date.date().toString("yyyy-MM-dd"),
                                                  period.text().strip())
        except ValueError as error:
            QMessageBox.warning(self, "Copie impossible", str(error))
            return
        self.db.set_meta("last_assessment_id", str(self.assessment_id))
        self.refresh()

    def preview_assessment(self):
        assessment_id = self._target_assessment("Tester l’évaluation")
        if assessment_id is None:
            return
        try:
            with self.db.transaction():
                config = load_assessment_config(self.db, assessment_id)
                if not self.db.verify_assessment_integrity(assessment_id):
                    raise ValueError("L’empreinte de la liste enregistrée est invalide.")
                title = self.db.q("SELECT title FROM assessment WHERE id=?", (assessment_id,))[0]["title"]
                items = self.db.assessment_items_payload(assessment_id)
        except ValueError as error:
            QMessageBox.warning(self, "Test impossible", str(error))
            return
        trials = [asdict(t) for t in copy_trials(config.familiarization_protocol)] if config.familiarization_enabled else []
        context = StudentContext(None, None, "Mode test · hors recherche", title, items,
                                 config.global_time_limit_s, config.item_time_limit_s, config.allow_omissions)
        self._student_win = StudentWindow(None, context, self.show, preview_trials=trials)
        self.hide()
        self._student_win.show()

    def _choose_assessment(self, title: str) -> Optional[Tuple[int, str]]:
        conditions = "WHERE deleted_at IS NULL"
        params: tuple[int, ...] = ()
        if self.project_id is not None:
            conditions += " AND project_id=?"
            params = (self.project_id,)
        rows = self.db.q(
            f"SELECT id,title,assessment_date FROM assessment {conditions} ORDER BY assessment_date DESC,id DESC",
            params,
        )
        if not rows:
            QMessageBox.warning(self, "Erreur", "Aucune évaluation dans cette base.")
            return None
        choices = [f"#{row['id']} — {row['title']} ({row['assessment_date']})" for row in rows]
        choice, ok = QInputDialog.getItem(self, title, "Choisir l’évaluation :", choices, 0, False)
        if not ok:
            return None
        index = choices.index(choice)
        return int(rows[index]["id"]), str(rows[index]["title"])

    def _roster_students(self, assessment_id: int, unfinished_only: bool = False) -> list[dict]:
        roster = self.db.q("SELECT student_id FROM assessment_roster WHERE assessment_id=?", (assessment_id,))
        ids = [int(row["student_id"]) for row in roster]
        if unfinished_only and ids:
            finished = {
                int(row["student_id"])
                for row in self.db.q(
                    f"SELECT DISTINCT student_id FROM attempt att WHERE assessment_id=? AND {ELIGIBLE_ATTEMPT_SQL}",
                    (assessment_id,),
                )
            }
            ids = [student_id for student_id in ids if student_id not in finished]
        if not ids:
            return []
        project_id = int(self.db.q("SELECT project_id FROM assessment WHERE id=?", (assessment_id,))[0]["project_id"])
        return [dict(row) for row in self.db.list_students(project_id, student_ids=ids)]

    def launch_with_selection(self) -> None:
        if self.assessment_id is None:
            return
        self._launch_roster(self.assessment_id, self._roster_students(self.assessment_id), "Sélection des élèves")

    def resume_assessment_flow(self) -> None:
        picked = self._choose_assessment("Reprendre une évaluation")
        if picked is None:
            return
        assessment_id, _ = picked
        roster = self._roster_students(assessment_id, unfinished_only=True)
        if not roster:
            QMessageBox.information(self, "Reprise", "Tous les élèves ont déjà une tentative terminée.")
            return
        self._launch_roster(assessment_id, roster, "Élèves restant à évaluer")

    def _launch_roster(self, assessment_id: int, roster: list[dict], title: str) -> None:
        if not roster:
            QMessageBox.warning(self, "Erreur", "Aucun élève disponible.")
            return
        dialog = StudentSelectionDialog(self, roster, title)
        if dialog.exec() != QDialog.Accepted:
            return
        selected_ids = dialog.selected_student_ids()
        if not selected_ids:
            return
        self.assessment_id = assessment_id
        self.db.set_meta("last_assessment_id", str(assessment_id))
        project_id = int(self.db.q("SELECT project_id FROM assessment WHERE id=?", (assessment_id,))[0]["project_id"])
        self._queue = [dict(row) for row in self.db.list_students(project_id, student_ids=selected_ids)]
        self.dashboard.scope.setCurrentIndex(max(0, self.dashboard.scope.findData(assessment_id)))
        self._start_next_student()

    def _export(self, nominative: bool) -> None:
        picked = self._choose_assessment("Exporter les données")
        if picked is None:
            return
        assessment_id, _ = picked
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = str(Path(EXTRACTIONS_DIR) / f"assessment_{assessment_id}_{stamp}")
        outputs = export_analysis_bundle(self.db, output_dir, assessment_id, nominative, organized=True)
        message = "\n".join(str(Path(path).relative_to(output_dir)) for path in outputs.values())
        QMessageBox.information(self, "Exports créés", f"Dossier : {output_dir}\n\n{message}")

    def export_stats_flow(self) -> None:
        self._export(False)

    def export_nominative_flow(self) -> None:
        answer = QMessageBox.question(
            self,
            "Export nominatif interne",
            "Ce fichier contient les noms et prénoms réels. Il doit rester sur l’ordinateur de l’enseignant "
            "et ne doit pas être transmis. Continuer ?",
        )
        if answer == QMessageBox.Yes:
            self._export(True)

    def delete_assessment_flow(self) -> None:
        picked = self._choose_assessment("Supprimer une évaluation")
        if picked is None:
            return
        assessment_id, title = picked
        reason, ok = QInputDialog.getMultiLineText(
            self,
            "Justification obligatoire",
            f"Motif de suppression de « {title} » :",
        )
        if not ok:
            return
        if not reason.strip():
            QMessageBox.information(
                self,
                "Suppression non effectuée",
                "Un motif est obligatoire afin de conserver une trace exploitable.",
            )
            return
        confirmation = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "L’évaluation sera masquée dans l’application, mais ses items, tentatives et réponses seront "
            "conservés avec le motif et l’horodatage. Continuer ?",
        )
        if confirmation != QMessageBox.Yes:
            return
        try:
            deleted_at = self.db.soft_delete_assessment(assessment_id, reason)
        except Exception as error:
            QMessageBox.warning(self, "Suppression impossible", str(error))
            return
        if self.assessment_id == assessment_id:
            self.assessment_id = None
            self.db.set_meta("last_assessment_id", "")
        self.refresh()
        QMessageBox.information(
            self,
            "Évaluation supprimée",
            f"« {title} » est masquée depuis {deleted_at}.\nLes données et la justification sont conservées.",
        )

    def graph_flow(self) -> None:
        if self.project_id is None:
            QMessageBox.information(self, "Analyse impossible", "Sélectionnez d’abord un projet.")
            return
        assessments = [dict(row) for row in self.db.list_assessments(self.project_id)]
        if not assessments:
            QMessageBox.information(self, "Analyse impossible", "Aucune évaluation disponible dans ce projet.")
            return
        dialog = AssessmentSelectionDialog(self, assessments)
        if dialog.exec() != QDialog.Accepted:
            return
        assessment_ids = dialog.selected_assessment_ids()
        include_nominative_labels = dialog.include_nominative_labels()
        if include_nominative_labels:
            confirmation = QMessageBox.question(
                self,
                "Copie graphique nominative interne",
                "Les tableaux, figures et rapports du dossier Enseignant contiendront les noms et prénoms et devront rester "
                "sur l’ordinateur sécurisé de l’enseignant. Continuer ?",
            )
            if confirmation != QMessageBox.Yes:
                return
        selected = [row for row in assessments if int(row["id"]) in assessment_ids]
        selected.sort(key=lambda row: (str(row["assessment_date"]), int(row["id"])))
        final_assessment_id = int(selected[-1]["id"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = str(Path(GRAPH_DIR) / f"analysis_{final_assessment_id}_{stamp}")
        try:
            outputs = generate_analysis_outputs(
                self.db,
                final_assessment_id,
                output_dir,
                assessment_ids=assessment_ids,
                include_nominative_final_labels=include_nominative_labels,
            )
        except Exception as error:
            QMessageBox.information(
                self,
                "Analyse terminée avec une erreur de code",
                f"Graphiques non générés\nraison : code\ncommentaire : {error}",
            )
            return
        lines = [
            f"Dossier : {outputs['output_dir']}",
            f"Évaluations sélectionnées : {len(assessment_ids)}",
        ]
        skipped = outputs.get("skipped_graphs", [])
        if skipped:
            lines.append("")
            for status in skipped:
                lines.append(f"{status['graph_name']} non généré")
                lines.append(f"raison : {status['reason']}")
                if status.get("comment"):
                    lines.append(f"commentaire : {status['comment']}")
                lines.append("")
        else:
            lines.append("Tous les graphiques demandés ont été générés.")
        QMessageBox.information(self, "Analyse terminée", "\n".join(lines).strip())

    def _start_next_student(self) -> None:
        if not self._queue:
            QMessageBox.information(self, "Terminé", "Passation terminée.")
            self._queue = None
            self.show()
            return
        assert self.assessment_id is not None
        student = self._queue.pop(0)
        attempt_id = self.db.create_attempt(self.assessment_id, int(student["id"]))
        assessment = self.db.q("SELECT title FROM assessment WHERE id=?", (self.assessment_id,))[0]
        config = load_assessment_config(self.db, self.assessment_id)
        items = [dict(row) for row in self.db.load_attempt_items(attempt_id)]
        context = StudentContext(
            attempt_id=attempt_id,
            student_id=int(student["id"]),
            student_label=f"{student['first_name']} {student['last_name']}",
            assessment_title=str(assessment["title"]),
            items=items,
            global_time_limit_s=config.global_time_limit_s,
            item_time_limit_s=config.item_time_limit_s,
            allow_omissions=config.allow_omissions,
        )
        self.hide()
        self._student_win = StudentWindow(self.db, context, self._on_student_finish)
        self._student_win.show()

    def _on_student_finish(self) -> None:
        self.dashboard.mark_dirty()
        self.dashboard.build()
        self.show()
        self._start_next_student()
