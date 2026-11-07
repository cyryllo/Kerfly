# PyInstaller build of Kerfly (Windows, Linux and macOS), one folder with the
# program and all its libraries (macOS: the Kerfly.app bundle). Run from the
# repository root:
#
#     pyinstaller packaging/kerfly.spec --noconfirm
#
# Result: dist/Kerfly/ with "Kerfly" (the window) and, on Windows, also
# "kerfly-console.exe" (the same program with a console, for --self-test).
# The Windows installer (packaging/windows/kerfly.iss) and the AppImage
# (packaging/linux/build-appimage.sh) are made from that folder; on macOS
# dist/Kerfly.app goes into a .dmg (.github/workflows/release.yml). For USB on
# macOS set LIBUSB_DYLIB to libusb-1.0's dylib (Homebrew), it is put in the app.
#
# Copyright (C) 2026 Kerfly contributors
# Licensed under the GNU General Public License v3 or later. See LICENSE.
import glob
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"


def files(pattern):
    """(source, folder in the package) for every file matching the pattern: the
    same folder as in the source tree, where the program looks for it."""
    return [(path, os.path.dirname(os.path.relpath(path, ROOT)))
            for path in glob.glob(os.path.join(ROOT, pattern))]


datas = (files("kerfly/locale/*/LC_MESSAGES/*.mo")
         + files("kerfly/gui/icons/tabler/*.svg")
         + files("kerfly/gui/icons/tabler/LICENSE")
         + files("kerfly/gui/icons/kerfly.*")
         + files("tests/fixtures/shapes.svg")          # used by --self-test
         + [(os.path.join(ROOT, name), ".") for name in ("LICENSE", "THIRD-PARTY-NOTICES.md")]
         + [(os.path.join(ROOT, "packaging", "licenses", "LGPL-3.0.txt"), "licenses")])   # Qt, PySide6

# the licence texts of the bundled libraries travel with them (their package metadata)
from PyInstaller.utils.hooks import copy_metadata
for dist in ("PySide6_Essentials", "shiboken6", "lxml", "pillow", "pyusb", "svgelements", "pyclipper"):
    try:
        datas += copy_metadata(dist)
    except Exception:            # optional library not installed (pyclipper)
        pass

binaries = []
if MACOS and os.environ.get("LIBUSB_DYLIB"):        # libusb-1.0 for pyusb (LGPL, licence in licenses/)
    binaries.append((os.environ["LIBUSB_DYLIB"], "."))
    datas.append((os.path.join(ROOT, "packaging", "licenses", "LGPL-3.0.txt"), "licenses"))

a = Analysis(
    [os.path.join(ROOT, "kerfly.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["PySide6.QtSvg", "usb.backend.libusb1", "usb.backend.libusb0", "kerfly.releasecheck", "segno"],
    excludes=[
        "tkinter", "_tkinter",                 # only the original K40 Whisperer window uses Tk
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(ROOT, "kerfly", "gui", "icons", "kerfly.ico")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kerfly", console=False,
          icon=icon if WINDOWS else None, upx=False)
executables = [exe]
if WINDOWS:
    # the same program with a console window: "kerfly-console.exe --self-test" prints its checks
    executables.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="kerfly-console", console=True,
                           icon=icon, upx=False))

coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="Kerfly")

if MACOS:
    sys.path.insert(0, ROOT)
    from kerfly import __version__
    app = BUNDLE(coll, name="Kerfly.app", icon=os.path.join(ROOT, "kerfly", "gui", "icons", "kerfly.icns"),
                 bundle_identifier="io.github.cyryllo.kerfly",
                 info_plist={"CFBundleName": "Kerfly", "CFBundleDisplayName": "Kerfly",
                             "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                             "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                             "NSHumanReadableCopyright": "GPL-3.0-or-later, Kerfly contributors"})
