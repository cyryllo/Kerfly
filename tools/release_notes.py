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


def is_preview(version):
    """A development version (2.0.0a1, 2.0.0-beta2, ...): letters after the numbers."""
    return bool(re.match(r"^\d+(\.\d+)*[-.]?[A-Za-z]", version))


WARNING_PL = ("> [!WARNING]\n"
              "> **Wersja rozwojowa (pre-release), tylko do testów.** Może zawierać błędy i niedokończone funkcje; "
              "do codziennej pracy z laserem używaj najnowszej wersji 1.x. Na razie bez instalatora: AppImage dla "
              "Linuksa albo uruchomienie ze źródeł; Kerfly nie proponuje jej jako aktualizacji.")
WARNING_EN = ("> [!WARNING]\n"
              "> **Development version (pre-release), for testing only.** It may have bugs and unfinished "
              "features; for everyday work with the laser use the latest 1.x release. For now without an installer: "
              "an AppImage for Linux or running from source; Kerfly does not offer it as an update.")


def downloads_preview_pl(version):
    guide = "https://github.com/cyryllo/Kerfly/blob/v%s/DEVELOPMENT.md#running-from-source" % version
    return "\n".join([
        "### Pobieranie",
        "",
        "- **Linux:** `Kerfly-%s-x86_64.AppImage`: nadaj prawo uruchamiania i uruchom." % version,
        "- **Ze źródeł** (*Source code* poniżej, rozpakuj):",
        "  - **Windows 10 / 11:** zainstaluj Pythona 3.13 (64-bit, zaznacz *Add python.exe to PATH*) i "
        "kliknij dwa razy **`start_kerfly.bat`**. Pierwsze uruchomienie instaluje biblioteki (potrzebny "
        "internet, kilka minut). Sterownik USB lasera: z instalatora wersji 1.x albo przez Zadig.",
        "  - **Linux:** `sudo apt install python3-venv`, potem **`bash start_kerfly.sh`** w rozpakowanym folderze.",
        "",
        "Szczegóły: [uruchamianie ze źródeł](%s). Ustawienia są wspólne z wersją 1.x." % guide])


def downloads_preview_en(version):
    guide = "https://github.com/cyryllo/Kerfly/blob/v%s/DEVELOPMENT.md#running-from-source" % version
    return "\n".join([
        "### Downloads",
        "",
        "- **Linux:** `Kerfly-%s-x86_64.AppImage`: make it executable and run it." % version,
        "- **From source** (*Source code* below, unpack it):",
        "  - **Windows 10 / 11:** install Python 3.13 (64-bit, tick *Add python.exe to PATH*) and double-click "
        "**`start_kerfly.bat`**. The first start installs the libraries (needs internet, a few minutes). The "
        "laser's USB driver: from the 1.x installer or with Zadig.",
        "  - **Linux:** `sudo apt install python3-venv`, then **`bash start_kerfly.sh`** in the unpacked folder.",
        "",
        "Details: [running from source](%s). The settings are shared with the 1.x version." % guide])


def notes(version):
    """The release text: Polish first (CHANGELOG_pl.md), then English (CHANGELOG.md); a development version
    gets a warning at the top and in its downloads only the AppImage and running from source (start_kerfly.bat /
    start_kerfly.sh). The changelogs' section of a development
    version is that of its number (2.0.0 for 2.0.0a1)."""
    preview = is_preview(version)
    number = re.match(r"^\d+(\.\d+)*", version).group(0) if preview else version
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    english = section(version, text) or (section(number, text) if preview else "")
    if not english:
        sys.exit("CHANGELOG.md has no section for %s" % version)
    polish = ""
    pl_path = os.path.join(ROOT, "CHANGELOG_pl.md")
    if os.path.isfile(pl_path):
        with open(pl_path, encoding="utf-8") as f:
            text = f.read()
        polish = section(version, text) or (section(number, text) if preview else "")
    dl_pl = downloads_preview_pl(version) if preview else downloads_pl(version)
    dl_en = downloads_preview_en(version) if preview else downloads_en(version)
    parts = []
    if preview:
        parts += [WARNING_PL, "", WARNING_EN, ""]
    if polish:
        parts += ["## Po polsku", "", polish, "", dl_pl, "", "---", "", "## In English", ""]
    parts += [english, "", dl_en]
    return "\n".join(parts)


def main():
    print(notes(sys.argv[1].lstrip("v")))


if __name__ == "__main__":
    main()
