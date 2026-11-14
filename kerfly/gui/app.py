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

# the style sheet of the light theme (kerfly/gui/theme.py has both themes)
from kerfly.gui.theme import style_sheet as _style_sheet  # noqa: E402
STYLE = _style_sheet("light")


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


def restore_system_libraries():
    """In the built program (AppImage, PyInstaller) LD_LIBRARY_PATH points to the
    libraries packed with Kerfly, and every program Kerfly starts inherited it:
    Inkscape then loaded Kerfly's older C++ library and failed, so SVG files did
    not open in the AppImage on systems with Inkscape (and a browser or pkexec
    could fail the same way). Kerfly's own libraries are loaded by then (the
    loader reads LD_LIBRARY_PATH only when a program starts), so the system's
    value is put back for the programs it starts."""
    import os
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("linux"):
        return
    original = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if original:
        os.environ["LD_LIBRARY_PATH"] = original
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)


class FileOpenApplication(QApplication):
    """macOS gives a file opened from Finder (double click on a .kerfly project) as an event, not as an
    argument; it can arrive before the window exists, so it waits for it."""

    def __init__(self, argv):
        super().__init__(argv)
        self._window = None
        self._pending = []

    def set_window(self, window):
        self._window = window
        for path in self._pending:
            window.load_design(path)
        self._pending = []

    def event(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.FileOpen and event.file():
            if self._window is None:
                self._pending.append(event.file())
            else:
                self._window.load_design(event.file())
            return True
        return super().event(event)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    restore_system_libraries()
    if "--self-test" in argv:
        from kerfly import selftest
        return selftest.run()
    if "--release-test" in argv:                   # a built package works through a short session
        from kerfly import releasecheck
        return releasecheck.run()
    from kerfly import __version__
    from kerfly.core import diag
    diag.setup(__version__)
    if sys.platform == "win32":
        # own taskbar entry and icon instead of python.exe's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kerfly.Kerfly")
        except Exception:
            pass
    app = FileOpenApplication(argv)
    app.setApplicationName("Kerfly")
    app.setDesktopFileName("kerfly")             # Wayland / KDE: match kerfly.desktop if installed
    from kerfly.gui import icons
    app.setWindowIcon(icons.app_icon())
    values = config.load_user_settings()
    from kerfly.gui import theme
    apply_desktop_font(app)
    theme.apply(app, values.get("theme", theme.DEFAULT))      # light, dark or as the system
    from kerfly.gui import viewstate
    viewstate.load(values)                     # grid, snapping, follow head: as left last time
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
    app.set_window(window)                     # macOS: a .kerfly double-clicked in Finder opens here
    files = [a for a in argv[1:] if not a.startswith("-")]
    if files:
        window.load_design(files[0])
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1500, window.check_updates_on_start)     # new version? (once a day, in the background)
    rc = app.exec()
    diag.log.info("==== Kerfly closed (exit code %s)", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
