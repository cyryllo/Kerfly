#!/usr/bin/env python3
"""
Translation checks: the template is up to date with the source code, every
language has every message, and placeholders match.

Usage:
    .venv/bin/python tests/test_i18n.py
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    from babel.messages.pofile import read_po
    pybabel = os.path.join(os.path.dirname(sys.executable), "pybabel")
    with tempfile.TemporaryDirectory() as tmp:
        pot = os.path.join(tmp, "now.pot")
        subprocess.run([pybabel, "-q", "extract", "-k", "_", "-k", "N_", "-k", "C_:1c,2", "--no-location",
                        "-o", pot, "kerfly"], check=True, cwd=ROOT)
        now = {m.id for m in read_po(open(pot, "rb")) if m.id}
    stored = {m.id for m in read_po(open(os.path.join(ROOT, "kerfly/locale/kerfly.pot"), "rb")) if m.id}
    failures = 0
    if now != stored:
        failures += 1
        print("FAIL  kerfly.pot is out of date; run: python tools/i18n.py")
        for s in sorted(now - stored)[:20]:
            print("      new:     %r" % s)
        for s in sorted(stored - now)[:20]:
            print("      removed: %r" % s)
    else:
        print("OK    kerfly.pot matches the source (%d messages)" % len(now))
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "i18n.py"), "--check"], cwd=ROOT)
    failures += rc.returncode
    # a text marked inside another translation call is not found by the extraction (the generators' Insert
    # button stayed English): every N_( must stand on its own
    import re
    hidden = []
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "kerfly")):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                for n, line in enumerate(open(path, encoding="utf-8"), 1):
                    if re.search(r"\b_\([^()]*\([^()]*N_\(|\b_\([^()]*N_\(", line):
                        hidden.append("%s:%d" % (os.path.relpath(path, ROOT), n))
    print("%-5s no text hidden from the translations inside another call %s"
          % ("FAIL" if hidden else "OK", hidden if hidden else ""))
    failures += 1 if hidden else 0
    from kerfly import i18n
    i18n.setup("pl")
    ok_insert = i18n._("Insert") == "Wstaw"
    print("%-5s the generators' Insert button is translated (%s)" % ("OK" if ok_insert else "FAIL", i18n._("Insert")))
    failures += 0 if ok_insert else 1
    ok = i18n._("Vector engrave") == "Obrys" and \
        i18n.tr_message("Sending Data to Laser = 45.0%") == "Wysyłanie danych do lasera: 45.0%"
    print("%-5s compiled Polish catalog is loaded and upstream messages are translated" % ("OK" if ok else "FAIL"))
    failures += 0 if ok else 1
    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
