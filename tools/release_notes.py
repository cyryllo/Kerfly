#!/usr/bin/env python3
"""
Print the CHANGELOG.md section of a version, for the GitHub release page:

    python tools/release_notes.py 0.18.0 > notes.md

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def section(version, text):
    """The text under "## <version>" up to the next "## " heading."""
    m = re.search(r"^## %s\b.*?$\n(.*?)(?=^## |\Z)" % re.escape(version), text, re.M | re.S)
    return m.group(1).strip() if m else ""


def downloads_pl(version):
    return "\n".join([
        "### Pobieranie",
        "",
        "- **Windows 10 / 11:** `Kerfly-%s-windows-setup.exe` (instaluje Kerfly i, jeśli zaznaczysz, sterownik "
        "USB K40). Windows może ostrzec przed nieznanym wydawcą: wybierz *Więcej informacji → Uruchom mimo to*."
        % version,
        "- **Linux:** `Kerfly-%s-x86_64.AppImage`: nadaj prawo uruchamiania i uruchom. Raz zezwól na dostęp do "
        "portu USB lasera (Laser → Zezwól na dostęp do USB lasera…), zobacz "
        "[INSTALL_pl.md](https://github.com/cyryllo/Kerfly/blob/v%s/INSTALL_pl.md#linux-appimage)." % (version, version),
        "- **macOS 11 lub nowszy:** `Kerfly-%s-macos-arm64.dmg` (Apple Silicon, M1 i nowsze) albo "
        "`Kerfly-%s-macos-x86_64.dmg` (Intel): otwórz i przeciągnij Kerfly do Programów. Bez podpisu Apple: za "
        "pierwszym razem zobacz [INSTALL_pl.md](https://github.com/cyryllo/Kerfly/blob/v%s/INSTALL_pl.md#macos). "
        "Wersja próbna, jeszcze nie sprawdzona z laserem." % (version, version, version),
        "",
        "Instrukcja obsługi: https://cyryllo.github.io/Kerfly/pl/guide.html"])


def downloads_en(version):
    return "\n".join([
        "### Downloads",
        "",
        "- **Windows 10 / 11:** `Kerfly-%s-windows-setup.exe` (installs Kerfly and, if you tick it, the K40 "
        "USB driver). Windows may warn about an unknown publisher: choose *More info → Run anyway*." % version,
        "- **Linux:** `Kerfly-%s-x86_64.AppImage`: make it executable and run it. Allow the laser's USB port "
        "once (Laser → Allow USB access for the laser…), see "
        "[INSTALL.md](https://github.com/cyryllo/Kerfly/blob/v%s/INSTALL.md#linux-the-appimage)." % (version, version),
        "- **macOS 11 or newer:** `Kerfly-%s-macos-arm64.dmg` (Apple Silicon, M1 and later) or "
        "`Kerfly-%s-macos-x86_64.dmg` (Intel): open it and drag Kerfly to Applications. Not signed by Apple: "
        "the first time see [INSTALL.md](https://github.com/cyryllo/Kerfly/blob/v%s/INSTALL.md#macos). A preview, "
        "not yet tested with a laser." % (version, version, version),
        "",
        "User guide: https://cyryllo.github.io/Kerfly/guide.html "
        "([Polish](https://cyryllo.github.io/Kerfly/pl/guide.html))"])


def notes(version):
    """The release text: Polish first (CHANGELOG_pl.md), then English (CHANGELOG.md)."""
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        english = section(version, f.read())
    if not english:
        sys.exit("CHANGELOG.md has no section for %s" % version)
    polish = ""
    pl_path = os.path.join(ROOT, "CHANGELOG_pl.md")
    if os.path.isfile(pl_path):
        with open(pl_path, encoding="utf-8") as f:
            polish = section(version, f.read())
    parts = []
    if polish:
        parts += ["## Po polsku", "", polish, "", downloads_pl(version), "", "---", "", "## In English", ""]
    parts += [english, "", downloads_en(version)]
    return "\n".join(parts)


def main():
    print(notes(sys.argv[1].lstrip("v")))


if __name__ == "__main__":
    main()
