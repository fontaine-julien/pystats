"""Taille physique des chiffres et champ de saisie élève."""

from __future__ import annotations

from dataclasses import dataclass
import math

from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QLineEdit


TARGET_DIGIT_MM = 10.0  # Cible ergonomique à vérifier sur le poste.


@dataclass(frozen=True)
class DisplayMetrics:
    logical_width: float
    logical_height: float
    scale: float
    width_mm: float
    height_mm: float
    estimated: bool = False

    @classmethod
    def from_screen(cls, screen):
        geometry = screen.geometry()
        size = screen.physicalSize()
        width_mm, height_mm = size.width(), size.height()
        ratio = geometry.width() / max(1, geometry.height())
        credible = (100 <= width_mm <= 2000 and 60 <= height_mm <= 1500
                    and abs(width_mm / height_mm / ratio - 1) < 0.15)
        if not credible:
            # À défaut de dimensions fiables, estime une diagonale de 15,6 pouces.
            diagonal = 15.6 * 25.4
            height_mm = diagonal / math.sqrt(1 + ratio * ratio)
            width_mm = height_mm * ratio
        return cls(geometry.width(), geometry.height(), screen.devicePixelRatio(),
                   width_mm, height_mm, not credible)

    @property
    def diagonal_inches(self):
        return math.hypot(self.width_mm, self.height_mm) / 25.4

    def logical_digit_height(self, height_mm=TARGET_DIGIT_MM):
        # Les dimensions Qt intègrent déjà la mise à l’échelle.
        return height_mm * self.logical_height / self.height_mm


def digit_font(height: float) -> QFont:
    """Ajuste la hauteur visible du chiffre en pixels logiques."""
    font = QFont("Verdana")
    font.setWeight(QFont.Normal)
    best_size, best_error = 12, float("inf")
    for size in range(max(8, int(height)), max(10, int(height * 2.2) + 5)):
        font.setPixelSize(size)
        ink = QFontMetricsF(font).tightBoundingRect("0123456789").height()
        error = abs(ink - height)
        if error < best_error:
            best_size, best_error = size, error
    font.setPixelSize(best_size)
    return font


class AnswerField(QLineEdit):
    """La lecture seule masque le curseur et bloque le collage. La saisie est gérée par l’exercice."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.setAcceptDrops(False)
        self.setMaxLength(9)
        self.setAccessibleName("Réponse au calcul")

    def append_digit(self, digit):
        if len(self.text()) < self.maxLength():
            self.setText(self.text() + digit)

    def erase_last(self):
        self.setText(self.text()[:-1])


class ScreenSizing(QObject):
    """Recalcule la taille à partir de l’écran qui affiche la fenêtre."""

    def __init__(self, window, apply):
        super().__init__(window)
        self.window, self.apply = window, apply
        self.screen = None
        self.handle = None
        self.pending = QTimer(self)
        self.pending.setSingleShot(True)
        self.pending.timeout.connect(self.refresh)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Resize, QEvent.ScreenChangeInternal):
            self.pending.start(0)
        return False

    def refresh(self, *_):
        handle = self.window.windowHandle()
        if handle is not None and handle is not self.handle:
            self.handle = handle
            handle.screenChanged.connect(self.refresh)
        screen = self.window.screen()
        if screen is not self.screen:
            if self.screen is not None:
                for signal in (self.screen.geometryChanged, self.screen.physicalDotsPerInchChanged,
                               self.screen.logicalDotsPerInchChanged):
                    try:
                        signal.disconnect(self.refresh)
                    except (RuntimeError, TypeError):
                        pass
            self.screen = screen
            for signal in (screen.geometryChanged, screen.physicalDotsPerInchChanged,
                           screen.logicalDotsPerInchChanged):
                signal.connect(self.refresh)
        self.apply(DisplayMetrics.from_screen(screen))
