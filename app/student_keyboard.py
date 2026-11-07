"""Filtrage du pavé numérique pendant la session élève."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
import threading

from PySide6.QtCore import QObject, QEvent, Qt, QTimer, Slot
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox


# Les codes physiques du pavé restent stables avec Verr Num. Le préfixe E0 distingue les touches de navigation.
KEYPAD_SCAN_DIGITS = {
    0x52: "0", 0x4F: "1", 0x50: "2", 0x51: "3", 0x4B: "4",
    0x4C: "5", 0x4D: "6", 0x47: "7", 0x48: "8", 0x49: "9",
}


def key_action(event):
    key = event.key()
    if key == Qt.Key_Escape:
        return "escape"
    if event.isAutoRepeat():
        return None
    if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier | Qt.MetaModifier):
        return None
    if key == Qt.Key_Backspace:
        return "backspace"
    if sys.platform == "win32" and event.nativeScanCode():
        digit = KEYPAD_SCAN_DIGITS.get(event.nativeScanCode())
        if digit is not None:
            return digit
    keypad = bool(event.modifiers() & Qt.KeypadModifier)
    if key == Qt.Key_Minus and (keypad or (sys.platform == "win32" and event.nativeScanCode() == 0x4A)):
        return "skip"
    if key == Qt.Key_Enter or (key == Qt.Key_Return and keypad):
        return "enter"
    if keypad and Qt.Key_0 <= key <= Qt.Key_9:
        return str(key - Qt.Key_0)
    return None


def native_key_allowed(vk, scan, flags):
    if vk in (0x1B, 0x08):  # Échap et Retour arrière.
        return True
    if vk == 0x0D:
        return bool(flags & 1)  # Entrée du pavé numérique.
    if vk == 0x6D and scan == 0x4A:
        return True
    # Verr Num désactivé, Qt retrouve les chiffres grâce aux codes physiques du pavé.
    return scan in KEYPAD_SCAN_DIGITS and not (flags & 1)


class WindowsKeypadGuard:
    """Interception Windows sur un fil dédié. Échap coupe aussitôt le filtrage."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread = None
        self.thread_id = None
        self.error = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name="PyStats keypad", daemon=True)
        self.thread.start()
        if not self.ready.wait(2):
            self.stopping.set()
            raise RuntimeError("Le filtre clavier Windows ne répond pas.")
        if self.error:
            raise RuntimeError(self.error)

    def stop(self):
        self.stopping.set()
        if self.thread_id:
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT réveille GetMessage.
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _run(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        result_type = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(result_type, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyData(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("extra", ctypes.c_size_t)]

        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = result_type
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user.GetForegroundWindow.restype = wintypes.HWND
        user.IsWindow.argtypes = [wintypes.HWND]
        user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                     wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = result_type
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        marker = 0x50595354
        hook = None
        escaped = False

        @callback_type
        def callback(code, message, pointer):
            nonlocal escaped
            if code >= 0 and not self.stopping.is_set() and not escaped:
                event = ctypes.cast(pointer, ctypes.POINTER(KeyData)).contents
                if event.extra != marker and user.GetForegroundWindow() == self.hwnd:
                    if event.vk == 0x1B:
                        escaped = True
                    elif event.vk == 0x90:
                        return 1  # Bloque Verr Num à l’appui et au relâchement.
                    elif not (event.flags & 0x80) and not native_key_allowed(event.vk, event.scan, event.flags):
                        # Laisse passer les relâchements pour éviter de bloquer un modificateur Windows.
                        return 1
            return user.CallNextHookEx(hook, code, message, pointer)

        try:
            message = wintypes.MSG()
            user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # Crée la file de messages du fil.
            self.thread_id = kernel.GetCurrentThreadId()
            hook = user.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self.ready.set()
            while not self.stopping.is_set():
                status = user.GetMessageW(ctypes.byref(message), None, 0, 0)
                if status <= 0:
                    break
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        except Exception as error:
            self.error = str(error)
        finally:
            if hook:
                user.UnhookWindowsHookEx(hook)
            self.thread_id = None
            self.ready.set()


class WindowsNumLock:
    """Lit l’état de Verr Num depuis le fil de l’interface."""

    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetKeyState.argtypes = [ctypes.c_int]
        self.user.GetKeyState.restype = ctypes.c_short
        self.user.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
        self.original = None

    def _set(self, enabled):
        if bool(self.user.GetKeyState(0x90) & 1) != enabled:
            # Les événements marqués contournent le filtre.
            self.user.keybd_event(0x90, 0x45, 1, 0x50595354)
            self.user.keybd_event(0x90, 0x45, 3, 0x50595354)

    def ensure(self):
        if self.original is None:
            self.original = bool(self.user.GetKeyState(0x90) & 1)
        self._set(True)

    def restore(self):
        if self.original is not None:
            self._set(self.original)
            self.original = None


class StudentKeyboard(QObject):
    """Filtre les touches jusque dans les écrans d’accueil, de retour et de fin."""

    def __init__(self, window, handler):
        super().__init__(window)
        self.window, self.handler = window, handler
        self.native = None
        self.closed = False
        self.native_error = None
        self.numlock = None
        self._native_cleanup = None
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._ensure_numlock)
        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.stop)

    def start(self):
        if self.closed or sys.platform != "win32":
            return
        if QApplication.platformName() != "windows":  # Les tests hors écran laissent le clavier du poste libre.
            return
        hwnd = int(self.window.winId())
        if self.native and self.native.hwnd == hwnd:
            return
        if self.native:
            self._release_native()  # Le plein écran peut changer l’identifiant de fenêtre.
        if self.numlock is not None:
            return
        guard = WindowsKeypadGuard(hwnd)
        self.numlock = WindowsNumLock()
        numlock = self.numlock
        # Le réglage de Verr Num fonctionne aussi sans interception native.
        self._native_cleanup = lambda *_: (guard.stop(), numlock.restore())
        self.window.destroyed.connect(self._native_cleanup)
        self._ensure_numlock()
        self.timer.start()
        if self.native_error:
            return
        try:
            guard.start()
            self.native = guard
        except RuntimeError as error:
            guard.stop()
            self.native_error = str(error)
            logging.error("Filtre clavier Windows indisponible : %s", error)
            QTimer.singleShot(0, self._show_native_error)

    def _show_native_error(self):
        if not self.closed:
            QMessageBox.warning(self.window, "Clavier",
                                "Le verrouillage des raccourcis Windows est indisponible.\n"
                                "Les touches restent filtrées dans l’exercice.\n" + self.native_error)

    def _ensure_numlock(self):
        if self.numlock and self.window.isActiveWindow():
            self.numlock.ensure()

    def _release_native(self):
        self.timer.stop()
        if self.native:
            self.native.stop()
            self.native = None
        if self.numlock:
            self.numlock.restore()
            self.numlock = None
        if self._native_cleanup is not None:
            self.window.destroyed.disconnect(self._native_cleanup)
            self._native_cleanup = None

    @Slot()
    def stop(self):
        self._release_native()
        if not self.closed:
            self.closed = True
            QApplication.instance().removeEventFilter(self)

    def eventFilter(self, watched, event):
        if self.closed or not isinstance(watched, QWidget) or watched.window() is not self.window:
            return False
        if event.type() == QEvent.ShortcutOverride:
            event.accept()
            return True
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_NumLock:
                QTimer.singleShot(0, self._ensure_numlock)
                return True
            action = key_action(event)
            if action:
                self.handler(action)
            return True
        if event.type() == QEvent.Hide and watched is self.window:
            self._release_native()  # Garde le filtre Qt lors d’un masquage temporaire.
        elif event.type() in (QEvent.WindowActivate, QEvent.Show) and watched is self.window:
            self.start()
        elif event.type() == QEvent.WinIdChange and watched is self.window:
            if self.window.isVisible():
                QTimer.singleShot(0, self.start)
        elif event.type() == QEvent.WindowDeactivate and watched is self.window:
            self._release_native()
        return False
