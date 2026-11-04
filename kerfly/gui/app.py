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
QPushButton#start, QPushButton#stop { font-size: 14px; }
QPushButton#jog { font-size:22px; font-weight:bold; }
QPushButton#corner { font-size:17px; }
QGroupBox { font-weight:bold; }
QToolBar#main_toolbar { spacing: 1px; padding: 2px; }
QToolBar#main_toolbar QToolButton { padding: 2px 1px; font-size: 11px; min-width: 40px; }
QLineEdit#layer_name { background: transparent; }
QLineEdit#layer_name:focus { background: palette(base); }
QToolBar#tool_strip { padding: 2px 4px 2px 2px; spacing: 2px; }
QLabel#bed_warning { color: #c62828; font-weight: bold; padding: 2px 0; }
QLabel#node_hint { color: #4b5563; }
QWidget#top_bar { background: #eef0f3; border-bottom: 1px solid #c4c9d0; }
QLabel#tool_options_title { font-weight: bold; }
QLabel#ribbon_caption { color: #6b7280; font-size: 10px; padding-bottom: 1px; }
QFrame#ribbon_separator { color: #c4c9d0; margin: 4px 1px; }
QGroupBox QLabel, QGroupBox QCheckBox { font-weight:normal; }
"""


def desktop_font():
    """(family, point size) of the Linux desktop's interface font, or None.
    Qt from pip has no KDE/GNOME integration, so it would fall back to a
    generic small font that does not match the rest of the desktop."""
    if not sys.platform.startswith("linux"):
        return None
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    try:                                                      # KDE: kdeglobals [General] font=
        path = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kdeglobals")
        section = None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    section = line
                elif section == "[General]" and line.startswith("font="):
                    parts = line[5:].split(",")
                    return parts[0], float(parts[1])
    except (OSError, ValueError, IndexError):
        pass
    if "KDE" in desktop:
        return "Noto Sans", 10.0                              # Plasma's default
    try:                                                      # GNOME and others
        import subprocess
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "font-name"],
                             capture_output=True, text=True, timeout=3).stdout.strip().strip("'")
        if out:
            name, _sep, size = out.rpartition(" ")
            return name.rstrip(", ") or out, float(size)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def apply_desktop_font(app):
    if app.font().family() not in ("Sans Serif", "Sans", "Helvetica"):
        return                                                # a platform theme already set it
    found = desktop_font()
    if found:
        from PySide6.QtGui import QFont
        family, size = found
        font = QFont(family)
        font.setPointSizeF(size)
        app.setFont(font)


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
    if "--self-test" in argv:
        from kerfly import selftest
        return selftest.run()
    from kerfly import __version__
    from kerfly.core import diag
    diag.setup(__version__)
    app = QApplication(argv)
    app.setApplicationName("Kerfly")
    app.setStyle("Fusion")
    apply_desktop_font(app)
    app.setStyleSheet(STYLE)

    values = config.load_user_settings()
    language = i18n.setup(values.get("language", ""))
    install_qt_translations(app, language)
    from PySide6.QtCore import qVersion
    diag.log.info("Qt %s (%s), language %s, font %s; board %s, bed %s x %s %s",
                  qVersion(), app.platformName(), language or "en", app.font().family(),
                  values.get("board_name"), values.get("LaserXsize"), values.get("LaserYsize"),
                  values.get("units"))

    from kerfly.gui.main_window import MainWindow
    window = MainWindow(values)
    window.remember_geometry = True
    window._restore_window_geometry()          # also brings back the maximized state
    window.show()
    files = [a for a in argv[1:] if not a.startswith("-")]
    if files:
        window.load_design(files[0])
    rc = app.exec()
    diag.log.info("==== Kerfly closed (exit code %s)", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
