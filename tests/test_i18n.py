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
        subprocess.run([pybabel, "-q", "extract", "-k", "_", "-k", "N_", "--no-location",
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
    from kerfly import i18n
    i18n.setup("pl")
    ok = i18n._("Vector cut") == "Cięcie wektorowe" and \
        i18n.tr_message("Sending Data to Laser = 45.0%") == "Wysyłanie danych do lasera: 45.0%"
    print("%-5s compiled Polish catalog is loaded and upstream messages are translated" % ("OK" if ok else "FAIL"))
    failures += 0 if ok else 1
    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
