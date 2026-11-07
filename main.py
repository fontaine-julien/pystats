"""Point d’entrée de PyStats."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.db import Database
from app.ui_admin import AdminWindow, BDD_DIR, LAST_DB_FILE, _load_last_db_path, _save_last_db_path


def main() -> None:
    application = QApplication(sys.argv)
    if sys.platform == "win32":
        # Fusion suit les changements de palette Windows.
        application.setStyle("Fusion")
    os.makedirs(BDD_DIR, exist_ok=True)
    last_path = _load_last_db_path()
    if last_path and os.path.exists(last_path):
        database_path = last_path
    elif os.path.isfile(LAST_DB_FILE):
        QMessageBox.information(None, "Base locale introuvable",
                                "Sélectionnez la base de classe à utiliser sur ce poste.")
        database_path, _ = QFileDialog.getOpenFileName(None, "Ouvrir la base de classe", BDD_DIR, "SQLite (*.sqlite *.db)")
        if not database_path:
            return
        _save_last_db_path(database_path)
    else:
        database_path = os.path.join(BDD_DIR, "default.sqlite")
        _save_last_db_path(database_path)
    database = Database(database_path)
    window = AdminWindow(database)
    window.showMaximized()
    exit_code = application.exec()
    database.close()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
