"""Saisie, taille des chiffres et fin de la session élève."""

import math
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QEvent, QSizeF, QRect
from PySide6.QtGui import QFontMetricsF, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from app.student_display import DisplayMetrics, digit_font
from app.student_keyboard import WindowsNumLock, native_key_allowed, key_action
from app.ui_student import StudentWindow, StudentContext
from conftest import create_sample_assessment


@pytest.fixture
def pupil(database, qapp):
    db, project, students = database
    assessment = create_sample_assessment(db, project, students)
    attempt = db.create_attempt(assessment, students[0])
    finished = Mock()
    context = StudentContext(attempt, students[0], "Élève test", "Tables",
                             [dict(r) for r in db.load_attempt_items(attempt)], None, None)
    window = StudentWindow(db, context, finished)
    window.show()
    qapp.processEvents()
    yield window, finished
    if not window._allow_close:
        window._handle_student_key("escape")


def test_only_keypad_digits_enter_and_backspace_are_recorded(pupil, database, qapp):
    window, finished = pupil
    QTest.keyClick(window, Qt.Key_Return)
    assert window.idx == -1
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    assert window.idx == 0
    for key, mods in [(Qt.Key_9, Qt.NoModifier), (Qt.Key_A, Qt.NoModifier),
                      (Qt.Key_Period, Qt.KeypadModifier), (Qt.Key_Plus, Qt.KeypadModifier),
                      (Qt.Key_Minus, Qt.KeypadModifier), (Qt.Key_Slash, Qt.KeypadModifier),
                      (Qt.Key_Asterisk, Qt.KeypadModifier), (Qt.Key_3, Qt.ControlModifier | Qt.KeypadModifier)]:
        QTest.keyClick(window.answer, key, mods)
    assert window.answer.text() == ""
    assert window._item_timer is not None
    QTest.keyClick(window.answer, Qt.Key_4, Qt.KeypadModifier)
    for key in (Qt.Key_Delete, Qt.Key_Left, Qt.Key_Home, Qt.Key_Tab, Qt.Key_NumLock):
        QTest.keyClick(window.answer, key)
    QTest.keyClick(window.answer, Qt.Key_2, Qt.KeypadModifier)
    assert window.answer.text() == "42"
    QTest.keyClick(window.answer, Qt.Key_Backspace)
    assert window.answer.text() == "4"
    QTest.keyClick(window.answer, Qt.Key_Return)
    assert window.idx == 0
    QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
    db, _, _ = database
    response = db.q("SELECT * FROM attempt_response WHERE attempt_item_id=?",
                    (window.ctx.items[0]["attempt_item_id"],))[0]
    assert response["raw_answer_text"] == "4"
    assert response["keystroke_count"] == 3 and response["correction_count"] == 1
    QTest.keyClick(window.answer, Qt.Key_Escape)
    assert not window.isVisible() and window.keyboard.closed
    finished.assert_called_once()
    ordinary = QLineEdit()
    QTest.keyClicks(ordinary, "abc123")
    assert ordinary.text() == "abc123"


def test_answer_has_no_native_editing_and_no_answer_length_hint(pupil, qapp):
    window, _ = pupil
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    width = window.answer.width()
    assert window.answer.isReadOnly()  # En lecture seule, Qt masque le curseur.
    assert window.answer.font().family() == "Verdana"
    qapp.clipboard().setText("987")
    QTest.keyClick(window.answer, Qt.Key_V, Qt.ControlModifier)
    assert window.answer.text() == ""
    held = QKeyEvent(QEvent.KeyPress, Qt.Key_9, Qt.KeypadModifier, "9", True)
    qapp.sendEvent(window.answer, held)
    assert window.answer.text() == ""
    for item in window.ctx.items:
        window._render_equation(item)
        assert window.answer.width() == width


@pytest.mark.parametrize("allow_skip", [False, True])
def test_empty_enter_never_advances_and_skip_requires_opt_in(pupil, database, qapp, allow_skip):
    window, _ = pupil
    window.ctx.allow_omissions = allow_skip
    window.idx = 2  # Premier item noté, suivi d’une transition immédiate.
    window._render_item()
    timer = window._item_timer
    for _ in range(3):
        QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
    QTest.keyClick(window.answer, Qt.Key_Minus, Qt.NoModifier)
    qapp.sendEvent(window.answer, QKeyEvent(QEvent.KeyPress, Qt.Key_Minus, Qt.KeypadModifier, "-", True))
    assert window.idx == 2 and window._item_timer is timer
    QTest.keyClick(window.answer, Qt.Key_0, Qt.KeypadModifier)
    QTest.keyClick(window.answer, Qt.Key_Minus, Qt.KeypadModifier)
    assert window.idx == 2 and window.answer.text() == "0"
    QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
    QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
    assert window.idx == 3
    QTest.keyClick(window.answer, Qt.Key_Minus, Qt.KeypadModifier)
    rows = database[0].q("SELECT completion_status,event_json,answer FROM attempt_response ORDER BY id")
    assert rows[0]["answer"] == 0 and rows[0]["completion_status"] == "answered"
    assert window.idx == (4 if allow_skip else 3)
    assert len(rows) == (2 if allow_skip else 1)
    if allow_skip:
        assert rows[1]["completion_status"] == "omission" and "keypad_skip" in rows[1]["event_json"]


@pytest.mark.parametrize("resolution,scale", [((1920, 1080), 1), ((1920, 1080), 1.25),
                                              ((1920, 1080), 1.5), ((3840, 2160), 2.5)])
def test_t590_glyphs_keep_ten_mm_across_resolution_and_scaling(qapp, resolution, scale):
    height_mm = 15.6 * 25.4 * 9 / math.sqrt(16**2 + 9**2)
    width_mm = height_mm * 16 / 9
    metrics = DisplayMetrics(resolution[0] / scale, resolution[1] / scale,
                             scale, width_mm, height_mm)
    font = digit_font(metrics.logical_digit_height())
    ink_height = QFontMetricsF(font).tightBoundingRect("0123456789").height()
    actual_mm = ink_height * height_mm / metrics.logical_height
    assert abs(actual_mm - 10) < .3


def test_missing_screen_dimensions_use_explicit_fallback():
    screen = Mock()
    screen.geometry.return_value = QRect(0, 0, 1536, 864)
    screen.physicalSize.return_value = QSizeF(0, 0)
    screen.devicePixelRatio.return_value = 1.25
    metrics = DisplayMetrics.from_screen(screen)
    assert metrics.estimated
    assert metrics.diagonal_inches == pytest.approx(15.6)


def test_windows_physical_key_policy():
    assert native_key_allowed(0x6D, 0x4A, 0)
    assert native_key_allowed(0x61, 0x4F, 0)  # 1 du pavé numérique.
    assert not native_key_allowed(0x31, 0x02, 0)  # 1 de la rangée supérieure.
    assert native_key_allowed(0x0D, 0x1C, 1)
    assert not native_key_allowed(0x0D, 0x1C, 0)
    for vk in (0x90, 0x6E, 0x6B, 0x6D, 0x6F, 0x6A, 0x2E, 0x5B, 0x09, 0x10, 0x11, 0x12):
        assert not native_key_allowed(vk, 0, 0)


@pytest.mark.parametrize("original", [False, True])
def test_numlock_restores_original_state(original):
    controller = WindowsNumLock.__new__(WindowsNumLock)
    controller.original = None
    state = [original]
    user = Mock()
    user.GetKeyState.side_effect = lambda _: int(state[0])
    def inject(vk, scan, flags, extra):
        if flags == 1:
            state[0] = not state[0]
    user.keybd_event.side_effect = inject
    controller.user = user
    controller.ensure()
    controller.ensure()
    assert state[0]
    controller.restore()
    controller.restore()
    assert state[0] == original


def test_native_guard_and_numlock_are_released_before_completion_callback(pupil):
    window, finished = pupil
    guard, numlock = Mock(), Mock()
    window.keyboard.native, window.keyboard.numlock = guard, numlock
    def after():
        guard.stop.assert_called_once()
        numlock.restore.assert_called_once()
        assert window.keyboard.closed
    finished.side_effect = after
    window._handle_student_key("escape")
    finished.assert_called_once()


# Verr Num désactivé, le 5 du pavé émet VK_CLEAR et la touche décimale émet VK_DELETE.
NUMLOCK_OFF_KEYS = [
    ("0", 0x52, 0x2D, Qt.Key_Insert), ("1", 0x4F, 0x23, Qt.Key_End),
    ("2", 0x50, 0x28, Qt.Key_Down), ("3", 0x51, 0x22, Qt.Key_PageDown),
    ("4", 0x4B, 0x25, Qt.Key_Left), ("5", 0x4C, 0x0C, Qt.Key_Clear),
    ("6", 0x4D, 0x27, Qt.Key_Right), ("7", 0x47, 0x24, Qt.Key_Home),
    ("8", 0x48, 0x26, Qt.Key_Up), ("9", 0x49, 0x21, Qt.Key_PageUp),
]


@pytest.mark.parametrize("digit,scan,vk,key", NUMLOCK_OFF_KEYS)
def test_physical_keypad_always_numeric_but_navigation_cluster_blocked(monkeypatch, digit, scan, vk, key):
    monkeypatch.setattr("app.student_keyboard.sys.platform", "win32")
    # Le code physique suffit quand Qt omet KeypadModifier.
    event = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, scan, vk, 0, "")
    assert key_action(event) == digit
    assert native_key_allowed(vk, scan, 0)
    navigation = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, 0xE000 | scan, vk, 0, "")
    assert key_action(navigation) is None
    assert not native_key_allowed(vk, scan, 1)


def test_numlock_off_recovery_preserves_response_and_timing(pupil, qapp, database, monkeypatch):
    monkeypatch.setattr("app.student_keyboard.sys.platform", "win32")
    window, _ = pupil
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    QTest.keyClick(window.answer, Qt.Key_4, Qt.KeypadModifier)
    QTest.keyClick(window.answer, Qt.Key_NumLock)
    for scan, vk, key in [(0x4C, 0x0C, Qt.Key_Clear), (0x52, 0x2D, Qt.Key_Insert)]:
        qapp.sendEvent(window.answer, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, scan, vk, 0, ""))
    assert window.answer.text() == "450"
    qapp.sendEvent(window.answer, QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.KeypadModifier, 0x53, 0x2E, 0, ""))
    qapp.sendEvent(window.answer, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier, 0x50, 0x28, 0, "", True))
    assert window.answer.text() == "450"
    QTest.keyClick(window.answer, Qt.Key_Backspace)
    QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
    response = database[0].q("SELECT * FROM attempt_response WHERE attempt_item_id=?",
                             (window.ctx.items[0]["attempt_item_id"],))[0]
    assert response["raw_answer_text"] == "45"
    assert response["keystroke_count"] == 4 and response["correction_count"] == 1


def test_temporary_hide_does_not_permanently_disable_keyboard(pupil, qapp):
    window, _ = pupil
    window.hide()
    assert not window.keyboard.closed
    window.show()
    qapp.processEvents()
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    assert window.idx == 0
    QTest.keyClick(window.answer, Qt.Key_9)
    assert window.answer.text() == ""
    QTest.keyClick(window.answer, Qt.Key_9, Qt.KeypadModifier)
    assert window.answer.text() == "9"
