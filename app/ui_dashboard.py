"""Tableau de bord et graphiques intégrés à Qt."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.dashboard_data import Snapshot, build_snapshot, load_cached_snapshot, median_center, median_value, ranking

# Les séries gardent leur sens en thème clair et sombre.
BLUE = ("#174f86", "#80bfff")
GRAY = ("#566570", "#bac6ce")
ORANGE = ("#89500d", "#ffb761")
PURPLE = ("#7639a2", "#d7a1ff")
GREEN = ("#007969", "#64daca")
PLOT_TITLES = ("01 · Évolution de la justesse", "02 · Évolution du temps de réponse",
               "03 · Positionnement vitesse–justesse", "04 · Classement des participants")


def number(value, unit="") -> str:
    return "—" if value is None else f"{value:.2f}{unit}"


@dataclass
class Series:
    label: str
    color: tuple[str, str]
    points: list[tuple[float, float, str]]
    connected: bool = False


@dataclass
class Plot:
    title: str
    x_label: str = ""
    y_label: str = ""
    series: list[Series] = field(default_factory=list)
    message: str = "Construisez les données pour afficher les résultats."
    note: str = ""
    x_ticks: dict[float, str] = field(default_factory=dict)
    percent: bool = False
    center: tuple[float, float] | None = None


class AnalysisPlot(QWidget):
    activated = Signal()
    coordinates = Signal(str)

    def __init__(self, title: str):
        super().__init__()
        self.model = Plot(title)
        self._axis_bounds = None
        self.hover = None
        self.setMinimumSize(300, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self.setAccessibleName(title)
        self.setToolTip("Cliquer pour agrandir • Échap pour revenir aux quatre graphiques")

    def set_model(self, model: Plot):
        self.model = model
        self._axis_bounds = None
        self.hover = None
        self.setToolTip("Cliquer pour agrandir • Échap pour revenir\n" + model.note)
        self.update()

    def plot_rect(self):
        return QRectF(62, 62, max(10, self.width() - 84), max(10, self.height() - 126))

    def bounds(self):
        if self._axis_bounds is not None:
            return self._axis_bounds
        points = [p for s in self.model.series for p in s.points]
        xs = [p[0] for p in points] or [0, 1]
        ys = [p[1] for p in points] or [0, 1]
        low, high = min(xs), max(xs)
        margin = max((high - low) * .06, .5 if self.model.x_ticks else .1)
        self._axis_bounds = (low - margin, high + margin, 0,
                             100 if self.model.percent else max(max(ys) * 1.12, 1))
        return self._axis_bounds

    def to_pixel(self, x, y):
        r = self.plot_rect()
        x0, x1, y0, y1 = self.bounds()
        return QPointF(r.left() + (x-x0)/(x1-x0)*r.width(), r.bottom() - (y-y0)/(y1-y0)*r.height())

    def from_pixel(self, point):
        r = self.plot_rect()
        x0, x1, y0, y1 = self.bounds()
        return x0 + (point.x()-r.left())/r.width()*(x1-x0), y0 + (r.bottom()-point.y())/r.height()*(y1-y0)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        background = palette.base().color()
        foreground = palette.text().color()
        variant = 1 if background.lightness() < 128 else 0
        grid = QColor(foreground)
        grid.setAlpha(44)
        p.fillRect(self.rect(), background)
        p.setPen(palette.mid().color())
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        p.setPen(foreground)
        p.drawText(QRectF(12, 5, self.width()-24, 25), Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.model.title, Qt.ElideRight, self.width()-24))
        font.setBold(False)
        p.setFont(font)
        if self.model.message:
            p.setPen(foreground)
            p.drawText(QRectF(24, 40, self.width()-48, self.height()-60),
                       Qt.AlignCenter | Qt.TextWordWrap, self.model.message)
            return
        r = self.plot_rect()
        x0, x1, y0, y1 = self.bounds()
        p.setPen(foreground)
        p.drawText(QRectF(12, 30, self.width()-24, 22), Qt.AlignLeft, self.model.y_label)
        for i in range(5):
            y = y0 + (y1-y0)*i/4
            py = self.to_pixel(x0, y).y()
            p.setPen(grid)
            p.drawLine(QPointF(r.left(), py), QPointF(r.right(), py))
            p.setPen(foreground)
            p.drawText(QRectF(2, py-9, 52, 18), Qt.AlignRight | Qt.AlignVCenter, f"{y:.1f}")
        ticks = self.model.x_ticks or {x0+(x1-x0)*i/4: f"{x0+(x1-x0)*i/4:.2f}" for i in range(5)}
        stride = max(1, (len(ticks) + max(1, int(r.width()/95)) - 1) // max(1, int(r.width()/95)))
        last_tick_pixel = -1000
        for index, (x, label) in enumerate(ticks.items()):
            if index % stride and index != len(ticks)-1:
                continue
            px = self.to_pixel(x, y0).x()
            if px - last_tick_pixel < 70:
                continue
            last_tick_pixel = px
            p.drawText(QRectF(px-47, r.bottom()+3, 94, 18), Qt.AlignCenter, label)
        p.setPen(QColor(GRAY[variant]))
        p.drawRect(r)
        p.save()
        p.setClipRect(r.adjusted(-5, -5, 5, 5))
        if self.model.center:
            center = self.to_pixel(*self.model.center)
            p.setPen(QPen(QColor(ORANGE[variant]), 1, Qt.DashLine))
            p.drawLine(QPointF(center.x(), r.top()), QPointF(center.x(), r.bottom()))
            p.drawLine(QPointF(r.left(), center.y()), QPointF(r.right(), center.y()))
        for series in self.model.series:
            color = QColor(series.color[variant])
            p.setPen(QPen(color, 1.6))
            p.setBrush(color)
            previous = None
            for x, y, _ in series.points:
                point = self.to_pixel(x, y)
                # Une passation manquante laisse une coupure dans la courbe.
                if series.connected and previous is not None and x - previous[0] <= 1:
                    p.drawLine(previous[1], point)
                radius = {BLUE: 4.5, PURPLE: 7, ORANGE: 5, GREEN: 9}.get(series.color, 3)
                p.drawEllipse(point, radius, radius)
                previous = x, point
        if self.hover is not None and r.contains(self.hover):
            p.setPen(QPen(foreground, 1, Qt.DotLine))
            p.drawLine(QPointF(self.hover.x(), r.top()), QPointF(self.hover.x(), r.bottom()))
            p.drawLine(QPointF(r.left(), self.hover.y()), QPointF(r.right(), self.hover.y()))
        p.restore()
        p.setPen(foreground)
        p.drawText(QRectF(62, r.bottom()+23, r.width(), 17), Qt.AlignCenter, self.model.x_label)
        legend_x = 10
        for series in self.model.series:
            if not series.label:
                continue
            p.setPen(QColor(series.color[variant]))
            text = p.fontMetrics().elidedText(series.label, Qt.ElideRight, max(0, self.width()-legend_x-12))
            p.drawText(QRectF(legend_x, self.height()-22, self.width()-legend_x-10, 18), Qt.AlignLeft, text)
            legend_x += p.fontMetrics().horizontalAdvance(text) + 14

    def mouseMoveEvent(self, event):
        self.hover = event.position()
        if self.plot_rect().contains(self.hover) and not self.model.message:
            x, y = self.from_pixel(self.hover)
            nearest = min(
                (((self.to_pixel(px, py)-self.hover).manhattanLength(), px, py, label)
                 for s in reversed(self.model.series) for px, py, label in s.points),
                key=lambda v: v[0], default=None)
            detail = ""
            if nearest and nearest[0] < 20:
                _, x, y, detail = nearest
                self.hover = self.to_pixel(x, y)
            message = f"{self.model.x_label} : {x:.3f}  |  {self.model.y_label} : {y:.3f}"
            if detail:
                message += "  |  " + detail
            self.coordinates.emit(message)
        else:
            self.coordinates.emit("")
        self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.coordinates.emit("")
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
        else:
            super().keyPressEvent(event)


class BuildWorker(QThread):
    built = Signal(object)
    failed = Signal(str)

    def __init__(self, path, project_id, revision, parent):
        super().__init__(parent)
        self.path, self.project_id, self.revision = path, project_id, revision

    def run(self):
        try:
            self.built.emit(build_snapshot(self.path, self.project_id, use_cache=True))
        except Exception as error:
            self.failed.emit(str(error))


class ResultsDashboard(QWidget):
    status = Signal(str)
    scope_changed = Signal(object)
    project_changed = Signal(object)
    edit_student_requested = Signal(int)
    remove_student_requested = Signal(int)
    delete_student_assessment_requested = Signal(int, int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.snapshot: Snapshot | None = None
        self.revision = 0
        self.worker = None
        self.students = []
        self.selected_student = None
        self.project_id = None
        self.advanced = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)
        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("Projet / classe"))
        self.projects = QComboBox()
        self.projects.setMinimumContentsLength(13)
        selectors.addWidget(self.projects, 1)
        selectors.addWidget(QLabel("Évaluation"))
        self.scope = QComboBox()
        self.scope.setMinimumContentsLength(24)
        selectors.addWidget(self.scope, 2)
        self.build_button = QPushButton("Actualiser les données")
        self.build_button.setToolTip("Charger les résultats enregistrés ou calculer les nouvelles passations.")
        self.build_button.clicked.connect(self.build)
        selectors.addWidget(self.build_button)
        root.addLayout(selectors)
        self.state = QLabel("Chargement des résultats…")
        self.state.setTextFormat(Qt.PlainText)
        root.addWidget(self.state)
        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter, 1)
        self.sidebar = QWidget()
        left = QVBoxLayout(self.sidebar)
        left.setContentsMargins(0, 0, 4, 0)
        self.roster_label = QLabel("Élèves")
        left.addWidget(self.roster_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un élève…")
        self.search.textChanged.connect(self.filter_students)
        left.addWidget(self.search)
        self.class_button = QPushButton("Vue de la classe entière")
        self.class_button.clicked.connect(self.select_class)
        left.addWidget(self.class_button)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Élève", "Justesse", "Moy. toutes (s)"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.select_student)
        self.table.cellDoubleClicked.connect(self.edit_student)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.student_context_menu)
        left.addWidget(self.table, 1)
        self.remove_button = QPushButton("Supprimer l’élève sélectionné…")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(lambda: self.remove_student_requested.emit(self.selected_student))
        left.addWidget(self.remove_button)
        hint = QLabel("Temps moyen de toutes les réponses\njustes et fausses chronométrées.\n— = mesure absente")
        left.addWidget(hint)
        self.splitter.addWidget(self.sidebar)
        self.right = QWidget()
        content = QVBoxLayout(self.right)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(5)
        self.summary = QPlainTextEdit("Chargement des résultats…")
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(95)
        self.summary.setMaximumHeight(112)
        self.summary.setContentsMargins(3, 3, 3, 3)
        content.addWidget(self.summary)
        chart_controls = QHBoxLayout()
        self.back = QPushButton("← Quatre graphiques (Échap)")
        self.back.clicked.connect(self.restore_grid)
        self.back.hide()
        chart_controls.addWidget(self.back)
        self.context = QLabel("Cliquer sur un graphique pour l’agrandir")
        self.context.setTextFormat(Qt.PlainText)
        chart_controls.addWidget(self.context, 1)
        chart_controls.addWidget(QLabel("Temps · 02"))
        self.time_metric = QComboBox()
        for text, metric in (("Moyenne · réponses justes", "mean_correct"),
                             ("Moyenne · réponses fausses", "mean_wrong"),
                             ("Moyenne · toutes les réponses", "mean_answered"),
                             ("Médiane · réponses justes", "seconds")):
            self.time_metric.addItem(text, metric)
        self.time_metric.currentIndexChanged.connect(self.render)
        chart_controls.addWidget(self.time_metric)
        chart_controls.addWidget(QLabel("Classement"))
        self.rank_metric = QComboBox()
        self.rank_metric.addItem("Justesse ↓", "accuracy")
        self.rank_metric.addItem("Temps ↑", "seconds")
        self.rank_metric.currentIndexChanged.connect(self.render)
        chart_controls.addWidget(self.rank_metric)
        content.addLayout(chart_controls)
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        content.addLayout(self.grid, 1)
        self.plots = [AnalysisPlot(title) for title in PLOT_TITLES]
        for index, plot in enumerate(self.plots):
            self.grid.addWidget(plot, index//2, index%2)
            plot.activated.connect(lambda i=index: self.expand(i))
            plot.coordinates.connect(self.status.emit)
        self.splitter.addWidget(self.right)
        self.splitter.setSizes([315, 1045])
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.projects.currentIndexChanged.connect(self.change_project)
        self.scope.currentIndexChanged.connect(self.change_scope)
        self.escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape.activated.connect(self.restore_grid)

    def reload(self, project_id, assessment_id=None):
        self.projects.blockSignals(True)
        self.projects.clear()
        for row in self.db.q("SELECT id,name FROM project ORDER BY id"):
            self.projects.addItem(row["name"], row["id"])
        self.projects.setCurrentIndex(self.projects.findData(project_id))
        self.projects.blockSignals(False)
        self.project_id = project_id
        self.students = [dict(r) for r in self.db.list_students(project_id)] if project_id else []
        self.scope.blockSignals(True)
        self.scope.clear()
        self.scope.addItem("Toute la base · toutes les évaluations du projet", None)
        if project_id:
            for row in self.db.list_assessments(project_id):
                self.scope.addItem(f"{row['assessment_date']} · #{row['id']} · {row['title']}", row["id"])
        self.scope.setCurrentIndex(max(0, self.scope.findData(assessment_id)))
        self.scope.blockSignals(False)
        self.snapshot = None
        self.selected_student = None
        self.mark_dirty("Chargement des résultats…" if project_id is not None else "Aucun projet sélectionné.")
        self.build_button.setEnabled(project_id is not None and not (self.worker and self.worker.isRunning()))
        if project_id is not None:
            saved = load_cached_snapshot(self.db.conn, project_id)
            if saved:
                self.display_snapshot(saved, "Résultats enregistrés chargés")
                return
            if not self.db.q("SELECT 1 FROM attempt att JOIN assessment a ON a.id=att.assessment_id "
                             "WHERE a.project_id=? LIMIT 1", (project_id,)):
                self.display_snapshot(build_snapshot(self.db.path, project_id, use_cache=True), "Projet chargé")
                return
        self.populate_students()
        self.render()
        self.build()

    def change_project(self):
        self.project_changed.emit(self.projects.currentData())

    def change_scope(self):
        self.scope_changed.emit(self.scope.currentData())
        self.populate_students()
        self.render()

    def mark_dirty(self, message="Nouvelles passations — résultats à actualiser."):
        self.revision += 1
        self.state.setText(message)
        font = self.state.font()
        font.setBold(True)
        self.state.setFont(font)

    def build(self):
        if self.project_id is None or (self.worker and self.worker.isRunning()):
            return
        self.build_button.setEnabled(False)
        self.state.setText("Construction des données en cours…")
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = BuildWorker(str(self.db.path), self.project_id, self.revision, self)
        self.worker.built.connect(self.accept_snapshot)
        self.worker.failed.connect(self.build_failed)
        self.worker.finished.connect(self.build_finished)
        self.worker.start()

    def build_failed(self, message):
        if self.sender() is self.worker and self.worker is not None and self.worker.revision == self.revision:
            self.state.setText(f"Construction impossible : {message}")

    def build_finished(self):
        if self.sender() is not self.worker:
            return
        self.build_button.setEnabled(self.project_id is not None)
        if self.worker.revision != self.revision:
            self.build()

    def accept_snapshot(self, snapshot):
        if self.worker is None or self.sender() is not self.worker or self.worker.revision != self.revision:
            return  # Le contexte a changé pendant le calcul.
        self.display_snapshot(snapshot, "Résultats actualisés")

    def display_snapshot(self, snapshot, message):
        self.snapshot = snapshot
        self.state.setText(f"{message} à {datetime.now():%H:%M:%S} · "
                           f"{len(snapshot.results)} résultats · {snapshot.excluded} tentative(s) en cours/interrompue(s) exclue(s)")
        font = self.state.font()
        font.setBold(False)
        self.state.setFont(font)
        self.populate_students()
        self.render()

    def name(self, student_id):
        row = next((r for r in self.students if r["id"] == student_id), None)
        return f"{row['last_name']} {row['first_name']}" if row else f"Élève #{student_id}"

    def populate_students(self):
        scope = self.scope.currentData()
        rows = self.snapshot.selected(scope) if self.snapshot else []
        if scope is not None:
            ids = {r["student_id"] for r in self.db.q(
                "SELECT student_id FROM assessment_roster WHERE assessment_id=?", (scope,))}
            ids.update(r.student_id for r in rows)
            students = [r for r in self.students if r["id"] in ids]
        else:
            students = self.students
        self.table.blockSignals(True)
        self.table.setRowCount(len(students))
        selection = None
        for index, student in enumerate(students):
            sid = student["id"]
            own = [r for r in rows if r.student_id == sid]
            item = QTableWidgetItem(self.name(sid))
            item.setData(Qt.UserRole, sid)
            item.setToolTip(f"{self.name(sid)} · {len(own)} résultat(s) retenu(s)")
            self.table.setItem(index, 0, item)
            accuracy = number(median_value(own, "accuracy"), " %")
            if scope is not None and own:
                accuracy += f" ({own[0].correct}/{own[0].answered})"
            self.table.setItem(index, 1, QTableWidgetItem(accuracy))
            count = sum(r.timed_count for r in own)
            mean_time = sum(r.mean_answered * r.timed_count for r in own if r.timed_count) / count if count else None
            self.table.setItem(index, 2, QTableWidgetItem("—" if mean_time is None else f"{mean_time:.3f}"))
            if sid == self.selected_student:
                selection = index
        self.table.clearSelection()
        if selection is not None:
            self.table.selectRow(selection)
        else:
            self.selected_student = None
        self.table.blockSignals(False)
        self.remove_button.setEnabled(self.selected_student is not None)
        self.roster_label.setText(f"Élèves · {len(students)} inscrits · {len({r.student_id for r in rows})} résultats")
        self.filter_students()

    def filter_students(self):
        text = self.search.text().casefold()
        for index in range(self.table.rowCount()):
            self.table.setRowHidden(index, text not in self.table.item(index, 0).text().casefold())

    def select_class(self):
        self.table.clearSelection()
        self.selected_student = None
        self.render()

    def select_student(self):
        selected = self.table.selectionModel().selectedRows()
        self.selected_student = self.table.item(selected[0].row(), 0).data(Qt.UserRole) if selected else None
        self.remove_button.setEnabled(self.selected_student is not None)
        self.render()

    def edit_student(self, row, column):
        if column == 0:
            self.edit_student_requested.emit(self.table.item(row, 0).data(Qt.UserRole))

    def student_context_menu(self, position):
        row = self.table.indexAt(position).row()
        if row < 0:
            return
        self.table.selectRow(row)
        student_id = self.table.item(row, 0).data(Qt.UserRole)
        assessment_id = self.scope.currentData()
        menu = QMenu(self)
        action = menu.addAction("Supprimer les résultats de l’évaluation sélectionnée…")
        available = assessment_id is not None and bool(self.db.q(
            "SELECT 1 FROM attempt WHERE student_id=? AND assessment_id=? LIMIT 1",
            (student_id, assessment_id)))
        action.setEnabled(available)
        if assessment_id is None:
            action.setText("Sélectionnez une évaluation pour supprimer ses résultats")
        elif not available:
            action.setText("Aucune passation à supprimer pour cette évaluation")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        menu.deleteLater()
        if chosen is action and available:
            self.delete_student_assessment_requested.emit(student_id, assessment_id)

    def expand(self, index):
        if self.advanced is not None:
            return
        self.advanced = index
        for plot in self.plots:
            self.grid.removeWidget(plot)
            plot.hide()
        self.grid.addWidget(self.plots[index], 0, 0, 2, 2)
        self.plots[index].show()
        self.sidebar.hide()
        self.summary.hide()
        self.back.show()
        self.context.setText("Vue avancée · survol : coordonnées et détail du point en barre d’état")

    def restore_grid(self):
        if self.advanced is None:
            return
        for index, plot in enumerate(self.plots):
            self.grid.removeWidget(plot)
            self.grid.addWidget(plot, index//2, index%2)
            plot.show()
        self.advanced = None
        self.sidebar.show()
        self.summary.show()
        self.back.hide()
        self.context.setText("Cliquer sur un graphique pour l’agrandir")

    def render(self):
        if not self.snapshot:
            self.summary.setPlainText("Chargement automatique des résultats du projet." if self.project_id
                                      else "Sélectionnez une base et un projet.")
            for index, plot in enumerate(self.plots):
                plot.set_model(Plot(PLOT_TITLES[index], message=self.summary.toPlainText()))
            return
        snapshot = self.snapshot
        scope = self.scope.currentData()
        assessments = snapshot.assessments
        focus = next((a for a in assessments if a["id"] == scope), None) if scope else (assessments[-1] if assessments else None)
        focus_id = focus["id"] if focus else None
        history = assessments[:assessments.index(focus)+1] if focus else []
        rows = snapshot.selected(scope)
        comparison = snapshot.selected(focus_id) if focus else []
        own = [r for r in rows if r.student_id == self.selected_student] if self.selected_student else rows
        label = self.name(self.selected_student) if self.selected_student else "Classe entière"
        correct, answered, total = sum(r.correct for r in own), sum(r.answered for r in own), sum(r.total for r in own)
        title = f"#{focus_id} · {focus['title']} ({focus['assessment_date']})" if focus else "Aucune évaluation"
        summary = (f"{label} — {'bilan général du projet' if scope is None else title}\n"
                   f"{len(own)} passation(s) · {len({r.student_id for r in own})} élève(s) · "
                   f"{correct}/{answered} réponses justes ({number(100*correct/answered if answered else None, ' %')}) · "
                   f"{answered}/{total} items répondus · temps médian : {number(median_value(own, 'seconds'), ' s')}\n"
                   f"Omissions : {sum(r.omitted for r in own)} · délais dépassés : {sum(r.timeout for r in own)} · "
                   f"non présentés : {sum(r.not_presented for r in own)}. ")
        selected = next((r for r in comparison if r.student_id == self.selected_student), None)
        center = median_center(comparison)
        if center:
            summary += f"Centre de la classe : {center[1]:.2f} % / {center[0]:.2f} s. "
        if selected and center and selected.seconds is not None and selected.accuracy is not None:
            summary += f"Écart au centre : {selected.accuracy-center[1]:+.2f} pts ; {selected.seconds-center[0]:+.2f} s. "
        elif self.selected_student and selected is None:
            summary += "Aucune passation retenue pour cet élève dans l’évaluation de comparaison. "
        summary += f"\nNuage et rangs : {title}. Justesse = correct/répondu ; temps = médiane des réponses justes (plus bas = plus rapide)."
        longitudinal = []
        for assessment in history:
            values = snapshot.selected(assessment["id"])
            if self.selected_student:
                values = [r for r in values if r.student_id == self.selected_student]
            if (self.selected_student and values) or len(values) >= 3:
                metrics = [median_value(values, metric) if self.selected_student or
                           sum(getattr(r, metric) is not None for r in values) >= 3 else None
                           for metric in ("accuracy", "seconds")]
                longitudinal.append((assessment, *metrics))
        if len(longitudinal) >= 2:
            first, last = longitudinal[0], longitudinal[-1]
            changes = []
            if first[1] is not None and last[1] is not None:
                changes.append(f"justesse {last[1]-first[1]:+.2f} points")
            if first[2] is not None and last[2] is not None:
                changes.append(f"médiane des réponses justes {last[2]-first[2]:+.2f} s")
            summary += f"\nÉvolution descriptive #{first[0]['id']} → #{last[0]['id']} : " + "; ".join(changes) + ". Difficultés / effectifs variables."
        self.summary.setPlainText(summary)
        self.summary.setToolTip("Dernière tentative terminée admissible par élève et évaluation. "
                                "Les interruptions enseignant et tentatives en cours sont exclues. "
                                "Le temps du bilan est la médiane des temps médians des passations. "
                                "Les différences de difficulté et les effectifs variables limitent la comparaison entre évaluations.")
        for index, metric in enumerate(("accuracy", self.time_metric.currentData())):
            model = Plot(PLOT_TITLES[index], "Évaluations (ordre chronologique)",
                         "Justesse (%)" if metric == "accuracy" else self.time_metric.currentText() + " (s)", message="", percent=metric == "accuracy")
            class_points, student_points = [], []
            for x, assessment in enumerate(history, 1):
                group = snapshot.selected(assessment["id"])
                valid = [r for r in group if getattr(r, metric) is not None]
                model.x_ticks[x] = f"#{assessment['id']} · {assessment['assessment_date'][5:]}"
                desc = f"#{assessment['id']} · {assessment['title']} · {assessment['assessment_date']}"
                if len(valid) >= 3:
                    value = median_value(valid, metric)
                    class_points.append((x, value, f"{desc} · classe n={len(valid)} · {value:.3f}"))
                student = next((r for r in group if r.student_id == self.selected_student), None)
                if student and getattr(student, metric) is not None:
                    value = getattr(student, metric)
                    counts = f"{student.correct} justes / {student.answered} répondues · {student.total} prévues"
                    student_points.append((x, value, f"{desc} · {label} · {value:.3f} · {counts}"))
            model.series = [Series("Classe : médiane (n ≥ 3)", GRAY, class_points, True),
                            Series("Élève" if self.selected_student else "", BLUE, student_points, True)]
            model.note = "Historique jusqu’à l’évaluation choisie · difficultés / effectifs variables"
            if len(class_points) < 2 and len(student_points) < 2:
                model.message = ("Échantillons insuffisants pour une évolution.\n"
                                 "Il faut 2 évaluations renseignées pour l’élève, ou 2 évaluations avec ≥ 3 élèves mesurables chacune.\n"
                                 f"Disponibles : élève {len(student_points)}/2 ; classe {len(class_points)}/2.")
            if index == 1 and len(history) >= 2 and student_points:
                model.message = ""
            self.plots[index].set_model(model)
        paired = [r for r in comparison if r.seconds is not None and r.accuracy is not None]
        scatter = Plot(PLOT_TITLES[2] + f" · #{focus_id or '—'}", "Temps médian correct (s) · rapide à gauche", "Justesse (%)",
                       message="", percent=True, center=center)
        scatter.series = [Series(f"Participants (n={len(paired)})", GRAY, [(r.seconds, r.accuracy,
                           f"{self.name(r.student_id)} · {r.seconds:.3f} s · {r.accuracy:.2f} %") for r in paired])]
        if selected in paired:
            scatter.series.append(Series("Élève", BLUE, [(selected.seconds, selected.accuracy,
                                  f"{label} · {selected.seconds:.3f} s · {selected.accuracy:.2f} %")]))
        if center:
            center_label = f"Centre {focus['title']} (n={len(paired)})"
            references = [(history[-2], "Précédent", PURPLE)] if len(history) > 1 else []
            if len(history) > 2:
                references.append((history[0], "Initial", GREEN))
            for previous, role, color in references:
                prior_rows = [r for r in snapshot.selected(previous["id"]) if r.seconds is not None and r.accuracy is not None]
                prior_center = median_center(prior_rows)
                if prior_center:
                    prior_label = f"Centre {previous['title']} (n={len(prior_rows)})"
                    scatter.series.append(Series(f"{role} #{previous['id']}", color, [
                        (*prior_center, f"{prior_label} · {prior_center[0]:.3f} s · {prior_center[1]:.2f} %")]))
                    if prior_center == center:
                        center_label += f" · identique au {prior_label}"
            scatter.series.append(Series(f"Centre #{focus_id}", ORANGE, [(*center,
                                  f"{center_label} · {center[0]:.3f} s · {center[1]:.2f} %")]))
        scatter.note = f"#{focus_id} · n={len(paired)} · centre = médianes des deux axes"
        if len(paired) < 3:
            scatter.message = f"Échantillons insuffisants : {len(paired)}/3 élèves avec justesse ET temps mesurables.\nLe nuage et le centre médian nécessitent au moins 3 élèves."
        self.plots[2].set_model(scatter)
        metric = self.rank_metric.currentData()
        ranks = ranking(comparison, metric)
        rank_plot = Plot(PLOT_TITLES[3] + f" · #{focus_id or '—'}", "Rang (ex æquo conservés)",
                         "Justesse (%)" if metric == "accuracy" else "Temps médian correct (s)", message="", percent=metric == "accuracy")
        rank_plot.series = [Series(f"Participants (n={len(ranks)})", GRAY, [(rank, getattr(r, metric),
                            f"{self.name(r.student_id)} · rang {rank}/{len(ranks)} · {number(getattr(r, metric))}") for rank, r in ranks])]
        own_rank = [(rank, r) for rank, r in ranks if r.student_id == self.selected_student]
        if own_rank:
            rank, r = own_rank[0]
            rank_plot.series.append(Series(f"Élève : {rank}/{len(ranks)}", BLUE, [(rank, getattr(r, metric),
                                    f"{label} · rang {rank}/{len(ranks)} · {number(getattr(r, metric))}")]))
        rank_plot.x_ticks = {rank: str(rank) for rank, _ in ranks}
        rank_plot.note = f"#{focus_id} · {len(ranks)} participants mesurables · aucun score composite"
        if len(ranks) < 2:
            rank_plot.message = f"Échantillons insuffisants : {len(ranks)}/2 élèves mesurables.\nLe classement nécessite au moins 2 participants."
        self.plots[3].set_model(rank_plot)
