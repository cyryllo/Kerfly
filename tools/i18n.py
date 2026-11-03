#!/usr/bin/env python3
"""
Update Kerfly translations.

    python tools/i18n.py            extract strings, update every .po, compile .mo
    python tools/i18n.py --check    fail if a translation is missing or broken

Needs Babel (pip install -r requirements-dev.txt). Translators edit
kerfly/locale/<lang>/LC_MESSAGES/kerfly.po (e.g. with Poedit), then run this
script to compile the .mo files that Kerfly loads.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE = os.path.join(ROOT, "kerfly", "locale")
POT = os.path.join(LOCALE, "kerfly.pot")
sys.path.insert(0, ROOT)
from kerfly.i18n import LANGUAGES  # noqa: E402

PYBABEL = os.path.join(os.path.dirname(sys.executable), "pybabel")


def run(*args):
    subprocess.run([PYBABEL, "-q"] + list(args), check=True, cwd=ROOT)


def extract():
    os.makedirs(LOCALE, exist_ok=True)
    run("extract", "-k", "_", "-k", "N_", "--no-location", "--sort-output",
        "--project", "Kerfly", "--copyright-holder", "Kerfly contributors",
        "--msgid-bugs-address", "https://github.com/cyryllo/Kerfly/issues",
        "-o", POT, "kerfly")


def update():
    for lang in LANGUAGES:
        if lang == "en":
            continue
        po = os.path.join(LOCALE, lang, "LC_MESSAGES", "kerfly.po")
        if os.path.exists(po):
            run("update", "--no-fuzzy-matching", "-D", "kerfly", "-i", POT, "-d", LOCALE, "-l", lang)
        else:
            run("init", "-D", "kerfly", "-i", POT, "-d", LOCALE, "-l", lang)


def compile_all():
    run("compile", "-D", "kerfly", "-d", LOCALE, "--statistics")


def check():
    """Every message translated, same %-placeholders as the English text."""
    from babel.messages.pofile import read_po
    placeholder = re.compile(r"%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdrfgx%]")
    problems = 0
    for lang in LANGUAGES:
        if lang == "en":
            continue
        with open(os.path.join(LOCALE, lang, "LC_MESSAGES", "kerfly.po"), "rb") as f:
            catalog = read_po(f)
        for msg in catalog:
            if not msg.id:
                continue
            if not msg.string or msg.fuzzy:
                print("%s: missing translation: %r" % (lang, msg.id))
                problems += 1
            elif sorted(placeholder.findall(msg.id)) != sorted(placeholder.findall(msg.string)):
                print("%s: placeholders differ: %r -> %r" % (lang, msg.id, msg.string))
                problems += 1
    print("%d problem(s)" % problems if problems else "All translations complete.")
    return problems


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
    extract()
    update()
    compile_all()
