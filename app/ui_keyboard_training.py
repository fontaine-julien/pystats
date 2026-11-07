"""Entraînement libre au pavé numérique sans enregistrement des réponses."""

from __future__ import annotations

import random
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.student_display import AnswerField, ScreenSizing, digit_font
from app.student_keyboard import StudentKeyboard


class KeyboardTrainingWindow(QWidget):
    def __init__(self, on_finish: Callable[[], None]):
        super().__init__()
        self._on_finish = on_finish
        self._closed = False
        self._waiting = False
        self._rng = random.SystemRandom()
        self.target = ""
        self.setWindowTitle("Entraînement au clavier")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setFont(QFont("Verdana"))
        self.setCursor(Qt.BlankCursor)
        layout = QVBoxLayout(self)
        title = QLabel("Entraînement au clavier")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        instructions = QLabel(
            "Recopie le nombre au pavé numérique, puis valide avec son Entrée.\n"
            "Retour arrière pour corriger."
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        layout.addStretch()
        self.number = QLabel()
        self.number.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.number)
        self.answer = AnswerField()
        self.answer.setMaxLength(3)
        layout.addWidget(self.answer, alignment=Qt.AlignCenter)
        self.feedback = QLabel()
        self.feedback.setAlignment(Qt.AlignCenter)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        layout.addStretch()
        footer = QLabel("À ton rythme • Autant de nombres que tu veux • Échap pour quitter")
        footer.setAlignment(Qt.AlignCenter)
        footer.setWordWrap(True)
        layout.addWidget(footer)
        quit_button = QPushButton("Quitter l’entraînement (Échap)")
        quit_button.clicked.connect(self.close)
        layout.addWidget(quit_button)
        quit_button.setFocusPolicy(Qt.NoFocus)
        self._secondary_labels = (title, instructions, self.feedback, footer, quit_button)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._next_number)
        self.keyboard = StudentKeyboard(self, self._handle_student_key)
        self.sizing = ScreenSizing(self, self._apply_display)
        self.sizing.refresh()
        self._next_number()

    def _apply_display(self, metrics):
        self.display_metrics = metrics
        font = digit_font(min(metrics.logical_digit_height(), max(24, self.height() * .09)))
        self.number.setFont(font)
        self.answer.setFont(font)
        fm = QFontMetricsF(font)
        pad = max(6, round(fm.tightBoundingRect("0").height() * .3))
        self.answer.setTextMargins(pad, pad, pad, pad)
        self.answer.setFixedWidth(round(fm.horizontalAdvance("888") + 2 * pad + 4))
        self.answer.setFixedHeight(round(fm.height() + 2 * pad + 4))
        for widget, factor in zip(self._secondary_labels, (.46, .34, .46, .30, .30)):
            secondary = QFont("Verdana")
            secondary.setPixelSize(max(14, round(font.pixelSize() * factor)))
            widget.setFont(secondary)

    def showEvent(self, event):
        super().showEvent(event)
        self.keyboard.start()

    def _next_number(self) -> None:
        if self._closed:
            return
        previous = self.target
        while self.target == previous:
            self.target = str(self._rng.randrange(10) if self._rng.randrange(2) == 0 else self._rng.randrange(10, 100))
        self.number.setText(self.target)
        self.answer.clear()
        self.answer.setEnabled(True)
        self.feedback.setText("")
        self._waiting = False
        self.answer.setFocus()

    def _handle_student_key(self, action):
        if action == "escape":
            self.close()
        elif not self._waiting:
            if action == "enter":
                if self.answer.text() == self.target:
                    self.feedback.setText("Bien !")
                    self._waiting = True
                    self.answer.setEnabled(False)
                    self._next_timer.start(500)
                elif self.answer.text():
                    self.feedback.setText("Essaie encore : utilise Retour arrière pour corriger.")
            elif action == "backspace":
                self.answer.erase_last()
            elif action.isdigit():
                self.answer.append_digit(action)

    def closeEvent(self, event) -> None:
        self._next_timer.stop()
        self.keyboard.stop()
        if not self._closed:
            self._closed = True
            self._on_finish()
        event.accept()
