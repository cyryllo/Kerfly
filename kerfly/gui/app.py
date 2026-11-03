"""
Kerfly application entry point.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import sys

# the laser core still imports top-level modules (egv, svg_reader, ...)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kerfly import i18n  # noqa: E402
from kerfly.core import config  # noqa: E402

STYLE = """
QPushButton#start { background:#2e7d32; color:white; font-weight:bold; border-radius:4px; }
QPushButton#start:disabled { background:#9e9e9e; }
QPushButton#stop { background:#c62828; color:white; font-weight:bold; border-radius:4px; }
QPushButton#stop:disabled { background:#bdbdbd; }
QPushButton#jog { font-size:22px; font-weight:bold; }
QPushButton#corner { font-size:17px; }
QGroupBox { font-weight:bold; }
QGroupBox QLabel, QGroupBox QCheckBox { font-weight:normal; }
"""


def install_qt_translations(app, language):
    """Translate Qt's own texts (standard buttons, file dialogs) and use the
    language's number format."""
    QLocale.setDefault(QLocale(language))
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    if translator.load("qtbase_" + language, path):
        app.installTranslator(translator)
        app._kerfly_qt_translator = translator      # keep a reference


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("Kerfly")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    values = config.load_user_settings()
    language = i18n.setup(values.get("language", ""))
    install_qt_translations(app, language)

    from kerfly.gui.main_window import MainWindow
    window = MainWindow(values)
    window.show()
    files = [a for a in argv[1:] if not a.startswith("-")]
    if files:
        window.load_design(files[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
