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


def main():
    version = sys.argv[1].lstrip("v")
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        body = section(version, f.read())
    if not body:
        sys.exit("CHANGELOG.md has no section for %s" % version)
    print(body)
    print("\n### Downloads\n")
    print("- **Windows 10 / 11:** `Kerfly-%s-windows-setup.exe` (installs Kerfly and, if you tick it, the K40 "
          "USB driver). Windows may warn about an unknown publisher: choose *More info → Run anyway*." % version)
    print("- **Linux:** `Kerfly-%s-x86_64.AppImage`: make it executable and run it. Allow the laser's USB port "
          "once (Laser → Allow USB access for the laser…), see "
          "[INSTALL.md](https://github.com/cyryllo/Kerfly/blob/v%s/INSTALL.md#linux-the-appimage)." % (version, version))
    print("\nUser guide: https://cyryllo.github.io/Kerfly/guide.html "
          "([Polish](https://cyryllo.github.io/Kerfly/pl/guide.html))")


if __name__ == "__main__":
    main()
