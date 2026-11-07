"""Passation plein écran avec chronomètre masqué."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QFont, QFontMetricsF, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.timing import ResponseTimer
from app.familiarization import MEASURED_LIMIT_MS
from app.student_display import AnswerField, ScreenSizing, digit_font
from app.student_keyboard import StudentKeyboard


@dataclass
class StudentContext:
    attempt_id: int | None
    student_id: int | None
    student_label: str
    assessment_title: str
    items: list[dict]
    global_time_limit_s: float | None
    item_time_limit_s: float | None
    allow_omissions: bool = False


class StudentWindow(QWidget):
    def __init__(self, db, ctx: StudentContext, on_finish: Callable[[], None], *, preview_trials=None):
        super().__init__()
        self.db = db
        self.ctx = ctx
        self.on_finish = on_finish
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.BlankCursor)
        self.setFont(QFont("Verdana"))

        self.idx = -1
        self._item_timer: ResponseTimer | None = None
        self._scored_start_ns: int | None = None
        self._finished_once = False
        self._result_visible = False
        self._submission_locked = False
        self._allow_close = False
        self._copy_trials = preview_trials if db is None else db.load_familiarization_trials(ctx.attempt_id)
        self._copy_index: int | None = None
        self._copy_done = not bool(self._copy_trials)
        self._advance_timer = QTimer(self)
        self._advance_timer.setSingleShot(True)
        self._advance_timer.timeout.connect(self._advance_after_feedback)
        self._ticker = QTimer(self)
        self._ticker.setInterval(20)
        self._ticker.timeout.connect(self._check_limits)

        self.header = QLabel("")
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setWordWrap(True)
        self.student_line = QLabel("")
        self.student_line.setAlignment(Qt.AlignCenter)
        self.left1 = QLabel("")
        self.op_lbl = QLabel("")
        self.left2 = QLabel("")
        self.eq_lbl = QLabel("=")
        for widget in (self.left1, self.op_lbl, self.left2, self.eq_lbl):
            widget.setAlignment(Qt.AlignCenter)
        self.answer = AnswerField()
        self.right_const = QLabel("")
        self.right_const.setAlignment(Qt.AlignCenter)

        equation = QHBoxLayout()
        self.equation = equation
        equation.addStretch(1)
        for widget in (self.left1, self.op_lbl, self.left2, self.eq_lbl, self.answer, self.right_const):
            equation.addWidget(widget)
        equation.addStretch(1)
        self.feedback = QLabel("")
        self._practice_correct: bool | None = None
        self.feedback.setAlignment(Qt.AlignCenter)
        self.feedback.setWordWrap(True)
        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        root = QVBoxLayout(self)
        root.addWidget(self.header, 1)
        root.addWidget(self.student_line, 1)
        root.addLayout(equation, 3)
        root.addWidget(self.feedback, 1)
        root.addWidget(self.hint, 1)
        self.keyboard = StudentKeyboard(self, self._handle_student_key)
        self.sizing = ScreenSizing(self, self._apply_display)
        self.sizing.refresh()
        self._render_intro()

    def _apply_display(self, metrics) -> None:
        self.display_metrics = metrics
        digit_height = metrics.logical_digit_height()
        # La largeur constante du champ masque la longueur de la réponse attendue.
        operand_digits = max([2] + [len(str(abs(int(item.get(k) or 0))))
                                   for item in self.ctx.items for k in ("a", "b")])
        answer_digits = max([3] + [len(str(abs(int(item["expected"])))) for item in self.ctx.items])
        for _ in range(30):
            font = digit_font(digit_height)
            fm = QFontMetricsF(font)
            unit = max(fm.horizontalAdvance(str(n)) for n in range(10))
            pad = max(6, round(digit_height * 0.3))
            gap = max(6, round(digit_height * 0.3))
            operand_width = round(unit * operand_digits + 4)
            symbol_width = round(max(fm.horizontalAdvance(s) for s in ("×", "−", "+", "÷", "=")) + 4)
            answer_width = round(unit * answer_digits + 2 * pad + 4)
            width = 2 * operand_width + 2 * symbol_width + answer_width + 4 * gap
            if width <= max(300, self.width() - 48):
                break
            digit_height *= 0.95
        for widget in (self.left1, self.left2, self.op_lbl, self.eq_lbl, self.right_const, self.answer):
            widget.setFont(font)
        for widget in (self.left1, self.left2, self.right_const):
            widget.setFixedWidth(operand_width)
        for widget in (self.op_lbl, self.eq_lbl):
            widget.setFixedWidth(symbol_width)
        self.answer.setFixedWidth(answer_width)
        self.answer.setFixedHeight(round(fm.height() + 2 * pad + 4))
        self.answer.setTextMargins(pad, pad, pad, pad)
        self.equation.setSpacing(gap)
        for widget, factor in ((self.header, .46), (self.student_line, .40),
                               (self.feedback, .46), (self.hint, .34)):
            secondary = QFont("Verdana")
            secondary.setPixelSize(max(14, round(font.pixelSize() * factor)))
            widget.setFont(secondary)

    def _set_practice_color(self, correct: bool | None) -> None:
        self._practice_correct = correct
        palette = QPalette()
        if correct is not None:
            dark = self.palette().window().color().lightness() < 128
            light_color, dark_color = ("#14652b", "#86dfa1") if correct else ("#973100", "#ffae87")
            palette.setColor(QPalette.WindowText, QColor(dark_color if dark else light_color))
        self.feedback.setPalette(palette)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange and getattr(self, "_practice_correct", None) is not None:
            self._set_practice_color(self._practice_correct)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.keyboard.start()

    def _handle_student_key(self, action: str) -> None:
        if action == "escape":
            self.keyboard.stop()
            if not self._result_visible:
                self._abort_attempt()
            self._finish_and_exit()
            return
        if action == "enter":
            if self._copy_index is not None:
                self._submit_current()
            elif self._result_visible:
                self._finish_and_exit()
            elif self.idx == -1:
                if not self._copy_done:
                    self._copy_index = 0
                    self._render_familiarization()
                else:
                    self.idx = 0
                    self._render_item()
            else:
                self._submit_current()
            return
        if self._item_timer is None or self._submission_locked:
            return
        if action == "skip":
            if self.ctx.allow_omissions and self._copy_index is None and not self.answer.text():
                self._submit_current(omit=True)
            return
        if action == "backspace":
            if self.answer.text():
                self._item_timer.record_correction("backspace")
                self.answer.erase_last()
        elif len(self.answer.text()) < self.answer.maxLength():
            self._item_timer.record_digit(action)
            self.answer.append_digit(action)

    def _render_intro(self) -> None:
        self.header.setText(self.ctx.assessment_title)
        self.student_line.setText(self.ctx.student_label)
        for widget in (self.left1, self.op_lbl, self.left2, self.right_const):
            widget.setText("")
        self.eq_lbl.setVisible(False)
        self.answer.setVisible(False)
        self.right_const.setVisible(False)
        self.feedback.setText("")
        if not self._copy_done:
            self.header.setText("Familiarisation au pavé numérique")
            self.hint.setText(
                "Recopie le nombre puis valide avec Entrée du pavé numérique.\n"
                "Retour arrière pour corriger.\n"
                "3 essais guidés puis 12 copies. Entrée du pavé numérique pour commencer."
            )
        else:
            self.hint.setText("Appuie sur Entrée du pavé numérique pour commencer les calculs")

    def _render_familiarization(self) -> None:
        assert self._copy_index is not None
        trial = self._copy_trials[self._copy_index]
        guided = trial["phase"] != "measured"
        self.header.setText(
            f"Pavé numérique — essai guidé {self._copy_index + 1}/3" if guided
            else f"Pavé numérique — copie {self._copy_index - 2}/12"
        )
        self.left1.setText(trial["target"])
        self.left1.setVisible(True)
        self.op_lbl.setVisible(False)
        self.left2.setVisible(False)
        self.op_lbl.setText("")
        self.left2.setText("")
        self.eq_lbl.setVisible(False)
        self.right_const.setVisible(False)
        self.answer.setVisible(True)
        self.answer.setEnabled(True)
        self.answer.setText(trial["initial_text"])
        self.answer.setCursorPosition(len(trial["initial_text"]))
        self.feedback.setText("")
        self.hint.setText(
            "Efface le 8 avec Retour arrière, puis valide avec Entrée du pavé numérique."
            if trial["phase"] == "guided_correction" else
            "Recopie au pavé numérique, puis Entrée du pavé numérique.\n"
            "Aussi vite que possible, sans te tromper."
        )
        self._submission_locked = False
        self._item_timer = ResponseTimer()
        self._item_timer.start()
        self.answer.setFocus()
        self._ticker.start()

    def _submit_familiarization(self, status: str | None = None) -> None:
        if self._copy_index is None or self._item_timer is None or self._submission_locked:
            return
        # Vérifie le délai à la validation, entre deux réveils du minuteur.
        trial = self._copy_trials[self._copy_index]
        if status is None and trial["phase"] == "measured" and self._item_timer.elapsed_ms() >= MEASURED_LIMIT_MS:
            status = "timeout"
        raw = self.answer.text().strip()
        if status is None and not raw:
            return
        status = status or "answered"
        self._submission_locked = True
        self._ticker.stop()
        timing = self._item_timer.finalize("validate" if status == "answered" else status)
        if self.db is not None:
            self.db.save_familiarization_response(trial["id"], raw, timing, status)
        self._item_timer = None
        if status == "interrupted":
            return
        correct = raw == trial["target"] and status == "answered"
        if trial["phase"] == "guided_correction":
            correct = correct and timing.correction_count > 0
        if trial["phase"] != "measured":
            self.feedback.setText("Bien !" if correct else f"À recopier : {trial['target']}")
            self.answer.setEnabled(False)
            self._advance_timer.start(650)
        else:
            self._advance_familiarization()

    def _advance_familiarization(self) -> None:
        if self._finished_once or self._copy_index is None:
            return
        self._copy_index += 1
        if self._copy_index == len(self._copy_trials):
            self._copy_index = None
            self._copy_done = True
            self._render_intro()
            self.setFocus()
        else:
            self._render_familiarization()

    def _advance_after_feedback(self) -> None:
        if self._finished_once:
            return
        if self._copy_index is not None:
            self._advance_familiarization()
        else:
            self._advance()

    def _render_item(self) -> None:
        if self.idx >= len(self.ctx.items):
            self._show_completion("completed")
            return
        item = self.ctx.items[self.idx]
        is_practice = bool(item["is_practice"])
        scored_position = sum(not bool(row["is_practice"]) for row in self.ctx.items[: self.idx + 1])
        scored_total = sum(not bool(row["is_practice"]) for row in self.ctx.items)
        if is_practice:
            practice_position = sum(bool(row["is_practice"]) for row in self.ctx.items[: self.idx + 1])
            self.header.setText(f"Essai {practice_position}/2")
        else:
            self.header.setText(f"Série {scored_position}/{scored_total}")
            if self._scored_start_ns is None:
                self._scored_start_ns = time.perf_counter_ns()
        self.student_line.setText(self.ctx.student_label)
        self.eq_lbl.setVisible(True)
        self.answer.setVisible(True)
        self.answer.setEnabled(True)
        self.answer.clear()
        self.feedback.setText("")
        self._set_practice_color(None)
        hint = "Tape ta réponse, puis valide avec Entrée du pavé numérique."
        if self.ctx.global_time_limit_s is None and self.ctx.item_time_limit_s is None:
            hint = "Tu as le temps de réfléchir. " + hint
        if self.ctx.allow_omissions:
            hint += "\nPour passer ce calcul, laisse la case vide et appuie sur − du pavé numérique."
        self.hint.setText(hint)
        self._render_equation(item)
        self._submission_locked = False
        self._item_timer = ResponseTimer()
        self._item_timer.start()
        self.answer.setFocus()
        self._ticker.start()

    def _render_equation(self, item: dict) -> None:
        op = str(item["op"])
        first = int(item["a"])
        second = int(item.get("b") or 0)
        self.right_const.setVisible(False)
        self.left1.setVisible(True)
        self.op_lbl.setVisible(True)
        self.left2.setVisible(True)
        for widget in (self.left1, self.op_lbl, self.left2, self.eq_lbl, self.answer, self.right_const):
            self.equation.removeWidget(widget)
        if op in {"complement_10", "complement_100", "add100"}:
            target = 100 if op in {"complement_100", "add100"} else 10
            self.left1.setText(str(first))
            self.op_lbl.setText("+")
            self.left2.setText("")
            self.right_const.setText(str(target))
            self.right_const.setVisible(True)
            self.left2.setVisible(False)
            order = (self.left1, self.op_lbl, self.answer, self.eq_lbl, self.right_const)
        else:
            symbol = {"addition": "+", "subtraction": "−", "multiplication": "×", "mul": "×", "division": "÷"}.get(op, op)
            self.left1.setText(str(first))
            self.op_lbl.setText(symbol)
            self.left2.setText(str(second))
            order = (self.left1, self.op_lbl, self.left2, self.eq_lbl, self.answer)
        for index, widget in enumerate(order, 1):
            self.equation.insertWidget(index, widget)

    def _submit_current(self, *, omit: bool = False) -> None:
        if self._copy_index is not None:
            self._submit_familiarization()
            return
        if self._submission_locked or self._item_timer is None or not (0 <= self.idx < len(self.ctx.items)):
            return
        raw_text = self.answer.text().strip()
        if not raw_text and not omit:
            return
        if omit and (not self.ctx.allow_omissions or raw_text):
            return
        self._submission_locked = True
        self._ticker.stop()
        item = self.ctx.items[self.idx]
        completion = "omission" if omit else "answered"
        answer_value = int(raw_text) if raw_text else None
        correct = answer_value == int(item["expected"]) if answer_value is not None else None
        timing = self._item_timer.finalize("keypad_skip" if omit else "validate")
        if self.db is not None:
            self.db.save_response(
                int(item["attempt_item_id"]), answer_value, correct, raw_text, timing, completion, "none"
            )
        if bool(item["is_practice"]):
            if correct is True:
                self.feedback.setText("Juste")
                self._set_practice_color(True)
            elif correct is False:
                self.feedback.setText(f"Réponse attendue : {item['expected']}")
                self._set_practice_color(False)
            else:
                self.feedback.setText("Aucune réponse — on continue")
            self.answer.setEnabled(False)
            self._advance_timer.start(650)
        else:
            self._advance()

    def _advance(self) -> None:
        self._item_timer = None
        self.idx += 1
        self._render_item()

    def _check_limits(self) -> None:
        if self._copy_index is not None:
            trial = self._copy_trials[self._copy_index]
            if (trial["phase"] == "measured" and self._item_timer is not None
                    and not self._submission_locked and self._item_timer.elapsed_ms() >= MEASURED_LIMIT_MS):
                self._submit_familiarization("timeout")
            return
        if self._item_timer is None or self._submission_locked or not (0 <= self.idx < len(self.ctx.items)):
            return
        item = self.ctx.items[self.idx]
        if bool(item["is_practice"]):
            return
        if self.ctx.global_time_limit_s is not None and self._scored_start_ns is not None:
            elapsed_global = (time.perf_counter_ns() - self._scored_start_ns) / 1_000_000_000
            if elapsed_global >= self.ctx.global_time_limit_s:
                self._store_timeout("global")
                self._show_completion("global_time_limit")
                return
        if self.ctx.item_time_limit_s is not None:
            if self._item_timer.elapsed_ms() >= self.ctx.item_time_limit_s * 1000:
                self._store_timeout("item")
                self.idx += 1
                self._render_item()

    def _store_timeout(self, timeout_status: str) -> None:
        if self._submission_locked or self._item_timer is None:
            return
        self._submission_locked = True
        self._ticker.stop()
        item = self.ctx.items[self.idx]
        timing = self._item_timer.finalize(f"{timeout_status}_timeout")
        completion = "global_timeout" if timeout_status == "global" else "timeout"
        if self.db is not None:
            self.db.save_response(
                int(item["attempt_item_id"]), None, None, self.answer.text(), timing, completion, timeout_status
            )
        self._item_timer = None

    def _abort_attempt(self) -> None:
        if self._result_visible:
            self._finish_and_exit()
            return
        if self._copy_index is not None:
            self._submit_familiarization("interrupted")
            self._copy_index = None
        if self._item_timer is not None and not self._submission_locked and 0 <= self.idx < len(self.ctx.items):
            self._submission_locked = True
            timing = self._item_timer.finalize("teacher_abort")
            item = self.ctx.items[self.idx]
            if self.db is not None:
                self.db.save_response(
                    int(item["attempt_item_id"]), None, None, self.answer.text(), timing, "interrupted", "none"
                )
            self._item_timer = None
        self._show_completion("teacher_abort")

    def _show_completion(self, ended_reason: str) -> None:
        self._finish_attempt(ended_reason)
        self._result_visible = True
        self.idx = len(self.ctx.items)
        self.header.setText("Passation terminée")
        self.student_line.setText(self.ctx.student_label)
        for widget in (self.left1, self.op_lbl, self.left2, self.right_const):
            widget.setText("")
        self.eq_lbl.setVisible(False)
        self.answer.setVisible(False)
        self.right_const.setVisible(False)
        self.feedback.setText("Merci")
        self._set_practice_color(None)
        self.hint.setText("Appuyer sur Entrée pour revenir à l’administration" if self.db is None else
                          "Appuyer sur Entrée pour passer à l’élève suivant")

    def _finish_attempt(self, ended_reason: str) -> None:
        if self._finished_once:
            return
        self._finished_once = True
        self._advance_timer.stop()
        self._ticker.stop()
        duration_ms = 0.0
        if self._scored_start_ns is not None:
            duration_ms = (time.perf_counter_ns() - self._scored_start_ns) / 1_000_000
        if self.db is not None:
            self.db.finish_attempt(self.ctx.attempt_id, ended_reason, duration_ms)

    def _finish_and_exit(self) -> None:
        if self._allow_close:
            return
        self._allow_close = True
        self.keyboard.stop()
        self.close()
        self.on_finish()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Enregistre une interruption si la fenêtre est fermée pendant la passation."""

        if not self._allow_close and not self._finished_once:
            self._abort_attempt()
        self.keyboard.stop()
        event.accept()
        if not self._allow_close and self.db is None:
            self._allow_close = True
            self.on_finish()
