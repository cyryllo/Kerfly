"""
Self-test:  python kerfly.py --self-test   (Windows: start_kerfly.bat --self-test)

Checks what Kerfly needs on this computer and prints a short report:
Python and library versions, the USB driver, whether a K40 is plugged in,
Inkscape, the settings folder, translations, and that the main window opens
and loads a design. Exit code 0 when everything required works.

The laser is only looked for, never opened or moved.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import platform
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "shapes.svg")

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class Report:
    def __init__(self, echo=True):
        self.lines = []
        self.failed = False
        self.echo = echo

    def add(self, status, what, detail=""):
        self.lines.append((status, what, detail))
        if status == FAIL:
            self.failed = True
        if self.echo:
            print("%-4s  %-22s %s" % (status, what, detail), flush=True)


def _check_imports(r):
    r.add(OK, "Python", "%s (%s, %s)" % (platform.python_version(), platform.architecture()[0],
                                         platform.platform()))
    for name, module, required in (("PySide6", "PySide6", True), ("lxml", "lxml.etree", True),
                                   ("Pillow", "PIL", True), ("pyusb", "usb", True),
                                   ("svgelements", "svgelements", True),
                                   ("pyclipper", "pyclipper", False)):
        try:
            mod = __import__(module, fromlist=["_"])
            version = getattr(mod, "__version__", "") or getattr(mod, "LXML_VERSION", "") \
                or getattr(mod, "SVGELEMENTS_VERSION", "")
            if isinstance(version, tuple):
                version = ".".join(str(v) for v in version)
            r.add(OK, name, str(version))
        except Exception as e:
            r.add(FAIL if required else WARN, name,
                  ("not installed: %s" % e) if required else "not installed (optional: trace offset)")


def _check_usb(r):
    try:
        import usb.backend.libusb0
        import usb.core
    except Exception as e:
        r.add(FAIL, "USB library", str(e))
        return
    # nano_library connects with pyusb's default backend; on Windows that is
    # libusb0.dll from the libusb-win32 driver (or one next to python.exe)
    if os.name == "nt" and usb.backend.libusb0.get_backend() is None:
        os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"]
    try:
        devices = list(usb.core.find(idVendor=0x1A86, idProduct=0x5512, find_all=True))
    except usb.core.NoBackendError:
        hint = ("install the libusb-win32 driver with Zadig (see INSTALL.md)" if os.name == "nt"
                else "install libusb (Debian: sudo apt install libusb-1.0-0)")
        r.add(WARN, "USB driver", "no libusb found: " + hint)
        return
    except Exception as e:
        r.add(WARN, "K40 laser", "could not list USB devices: %s" % e)
        return
    r.add(OK, "USB driver", "libusb found")
    if devices:
        where = ", ".join("bus %s address %s" % (d.bus, d.address) for d in devices)
        r.add(OK, "K40 laser", "found (%s)" % where)
    else:
        r.add(WARN, "K40 laser", "not found (plugged in and switched on?)")


def _check_inkscape(r, values):
    try:
        sys.path.insert(0, ROOT)
        import svg_reader
        reader = svg_reader.SVG_READER()
        reader.set_inkscape_path(values.get("inkscape_path") or None)
        if reader.inkscape_exe:
            r.add(OK, "Inkscape", reader.inkscape_exe)
        else:
            r.add(OK, "Inkscape", "not installed (optional; SVG files use the built-in renderer)")
    except Exception as e:
        r.add(WARN, "Inkscape", "check failed: %s" % e)


def _check_settings(r):
    from kerfly.core import config, materials
    path = config.user_config_path()
    r.add(OK, "Settings file", path + ("" if os.path.isfile(path) else " (not created yet)"))
    folder = os.path.dirname(materials.library_path())
    try:
        os.makedirs(folder, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".kerfly_selftest_"):
            pass
        r.add(OK, "Settings folder", folder + " (writable)")
    except OSError as e:
        r.add(FAIL, "Settings folder", "%s is not writable: %s" % (folder, e))
    return config.load_user_settings()


def _check_gui(r, values):
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QTimer, qVersion
    from PySide6.QtWidgets import QApplication

    from kerfly import i18n
    from kerfly.gui import app as appmod

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    appmod.apply_desktop_font(app)
    app.setStyleSheet(appmod.STYLE)
    language = i18n.setup(values.get("language", ""))
    appmod.install_qt_translations(app, language)
    r.add(OK, "Qt", "%s (PySide6 %s, platform %s)" % (qVersion(), pyside_version, app.platformName()))
    r.add(OK, "Language", language or "en")
    font = app.font()
    r.add(OK, "Font", "%s %g pt" % (font.family(), font.pointSizeF()))

    from kerfly.gui.main_window import MainWindow
    window = MainWindow(dict(values))
    window.show()
    for _ in range(5):
        app.processEvents()
    if os.path.isfile(FIXTURE):
        # never ask questions in a self-test
        window.values["use_inkscape"] = "0"
        window.load_design(FIXTURE)
        for _ in range(5):
            app.processEvents()
        count = len(window.elements) if hasattr(window, "elements") else 0
        if count:
            r.add(OK, "Open design", "%s (%d element)" % (os.path.basename(FIXTURE), count))
        else:
            r.add(FAIL, "Open design", "%s did not load" % FIXTURE)
    r.add(OK, "Main window", "%d x %d" % (window.width(), window.height()))
    window._dirty = False
    QTimer.singleShot(0, window.close)
    app.processEvents()
    window.close()
    window.deleteLater()
    app.processEvents()


def checks_without_window():
    """The self-test checks that do not open a window (for the diagnostic
    report of a running Kerfly): list of (status, what, detail)."""
    r = Report(echo=False)
    try:
        _check_imports(r)
        values = _check_settings(r)
        _check_usb(r)
        _check_inkscape(r, values)
    except Exception as e:
        r.add(FAIL, "Unexpected error", repr(e))
    return r.lines


def run():
    print("Kerfly self-test\n", flush=True)
    r = Report()
    try:
        _check_imports(r)
        values = _check_settings(r)
        _check_usb(r)
        _check_inkscape(r, values)
        if not r.failed:
            _check_gui(r, values)
    except Exception:
        r.add(FAIL, "Unexpected error", "")
        traceback.print_exc()
    print("\n" + ("Self-test FAILED: see the lines marked FAIL." if r.failed
                  else "Self-test passed. WARN lines are optional or need the laser."), flush=True)
    return 1 if r.failed else 0
