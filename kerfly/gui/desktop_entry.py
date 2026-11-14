"""
Linux AppImage: put Kerfly into the desktop's applications menu and make it the
program for .kerfly projects (an AppImage is a single file, nothing installs
that for it). Everything goes into the user's own folders (~/.local/share), no
administrator password needed; the menu entry runs this AppImage file.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import shutil
import subprocess
import sys

MIME_TYPE = "application/x-kerfly"
DESKTOP_NAME = "kerfly.desktop"

MIME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-kerfly">
    <comment>Kerfly project</comment>
    <comment xml:lang="pl">Projekt Kerfly</comment>
    <comment xml:lang="de">Kerfly-Projekt</comment>
    <comment xml:lang="es">Proyecto de Kerfly</comment>
    <comment xml:lang="fr">Projet Kerfly</comment>
    <icon name="kerfly"/>
    <glob pattern="*.kerfly"/>
  </mime-type>
</mime-info>
"""


def appimage_path():
    """The AppImage file Kerfly runs from, or None."""
    path = os.environ.get("APPIMAGE", "")
    return path if path and os.path.isfile(path) else None


def applies():
    return sys.platform.startswith("linux") and appimage_path() is not None


def data_home():
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def desktop_text(program):
    quoted = '"%s"' % program.replace('"', '\\"') if " " in program else program
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Kerfly",
        "GenericName=Laser cutter control",
        "GenericName[pl]=Sterowanie laserem",
        "Comment=Control K40 laser cutters: draw, place and cut",
        "Comment[pl]=Sterowanie laserami K40: rysowanie, układanie i cięcie",
        "Exec=%s %%F" % quoted,
        "Icon=kerfly",
        "Terminal=false",
        "Categories=Graphics;Engineering;",
        "MimeType=%s;image/svg+xml;image/vnd.dxf;" % MIME_TYPE,
        "Keywords=laser;K40;engraving;cutting;",
        "StartupWMClass=Kerfly",
        "",
    ])


def installed_for():
    """The program path of an existing menu entry, or None."""
    path = os.path.join(data_home(), "applications", DESKTOP_NAME)
    try:
        for line in open(path, encoding="utf-8"):
            if line.startswith("Exec="):
                return line[5:].rsplit(" %F", 1)[0].strip().strip('"')
    except OSError:
        return None
    return None


def install(program=None, icon_file=None, run=subprocess.run):
    """Write the menu entry, the .kerfly file type and the icon; make Kerfly the default
    program for .kerfly. Returns the list of written files. Tools that are missing
    (update-mime-database, xdg-mime) are skipped: the files alone work after a new login."""
    program = program or appimage_path()
    if not program:
        raise RuntimeError("not running from an AppImage")
    base = data_home()
    written = []
    for folder in ("applications", os.path.join("mime", "packages"),
                   os.path.join("icons", "hicolor", "256x256", "apps")):
        os.makedirs(os.path.join(base, folder), exist_ok=True)
    desktop = os.path.join(base, "applications", DESKTOP_NAME)
    with open(desktop, "w", encoding="utf-8") as f:
        f.write(desktop_text(program))
    written.append(desktop)
    mime = os.path.join(base, "mime", "packages", "kerfly.xml")
    with open(mime, "w", encoding="utf-8") as f:
        f.write(MIME_XML)
    written.append(mime)
    if icon_file is None:
        icon_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "kerfly.png")
    if os.path.isfile(icon_file):
        icon = os.path.join(base, "icons", "hicolor", "256x256", "apps", "kerfly.png")
        shutil.copyfile(icon_file, icon)
        written.append(icon)
    for command in (["update-mime-database", os.path.join(base, "mime")],
                    ["update-desktop-database", os.path.join(base, "applications")],
                    ["xdg-mime", "default", DESKTOP_NAME, MIME_TYPE]):
        if shutil.which(command[0]):
            try:
                run(command, timeout=30, capture_output=True)
            except Exception:
                pass
    return written
