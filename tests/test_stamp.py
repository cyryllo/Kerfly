#!/usr/bin/env python3
"""
Checks the stamp picture: frame unbroken, no streaks between the frame and the
text, pure black and white, text really drawn, bold heavier than regular.

Runs on its own so CI on Windows can use the real Windows platform (system
fonts, the renderer users get); tests/test_gui.py runs the same check offscreen.

Usage:
    .venv/bin/python tests/test_stamp.py
    QT_QPA_PLATFORM=windows .venv\\Scripts\\python tests\\test_stamp.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))

TEXT = "Prototypowanie i Fabrykacja\nCyryl Sochacki\nul. Szczyglewskiego 21/8\n80-625 Gdańsk"


def _dark(img, x, y):
    return img.pixelColor(x, y).lightness() < 128


def _ink(img, step=3):
    return sum(1 for y in range(0, img.height(), step) for x in range(0, img.width(), step) if _dark(img, x, y))


def _two_tone(img):
    return all(img.pixelColor(x, y).lightness() in (0, 255)
               for y in range(0, img.height(), 11) for x in range(0, img.width(), 11))


def clean_report():
    """[(name, ok, detail)] for the rectangular stamp (plain and editor text) and the round one."""
    from kerfly.gui import stamp
    clean = dict(preset="custom", width=95.0, height=40.0, text=TEXT, font="", bold=True, text_size=0.0,
                 picture="", place="left", frame=0.6, corner=1.0, margin=1.0, outline=True,
                 invert=False, mirror=False)
    rich = {k: v for k, v in clean.items() if k != "text"}
    rich["text_html"] = ""                              # the editor's default text (name bold, address)
    results = []
    for label, variant in (("plain text", clean), ("editor text", rich)):
        framed = stamp.render(variant)
        bare = stamp.render(dict(variant, frame=0.0))
        fw, fh = framed.width(), framed.height()
        band = int(0.6 / 25.4 * 1000)                   # the frame's width in pixels
        corner = int(1.5 / 25.4 * 1000)
        frame_ok = all(_dark(framed, x, y) for y in (band // 3, band // 2, fh - 1 - band // 2)
                       for x in range(corner, fw - corner, 7))
        frame_ok = frame_ok and all(_dark(framed, x, y) for x in (band // 2, fw - 1 - band // 2)
                                    for y in range(corner, fh - corner, 7))
        xs = [x for x in range(0, fw, 3) for y in range(0, fh, 6) if _dark(bare, x, y)]
        ys = [y for y in range(0, fh, 3) for x in range(0, fw, 6) if _dark(bare, x, y)]
        if not xs:
            results.append(("stamp %s: text drawn" % label, False, "(no ink at all, font %r)" % stamp.default_font()))
            continue
        tx0, tx1, ty0, ty1 = min(xs) - 4, max(xs) + 4, min(ys) - 4, max(ys) + 4
        inner = int(1.2 / 25.4 * 1000)
        stray = [(x, y) for y in range(inner, fh - inner, 5) for x in range(inner, fw - inner, 5)
                 if not (tx0 <= x <= tx1 and ty0 <= y <= ty1) and _dark(framed, x, y)]
        # the text spans most of the stamp (a missing font left it tiny or empty)
        wide = (tx1 - tx0) > fw * 0.5 and (ty1 - ty0) > fh * 0.4
        results.append(("stamp %s: unbroken frame, nothing between the frame and the text, black and white" % label,
                        frame_ok and not stray and wide and _two_tone(framed),
                        "(%s)" % [frame_ok, stray[:5], wide, _two_tone(framed)]))
    regular = _ink(stamp.render(dict(clean, frame=0.0, bold=False)))
    heavy = _ink(stamp.render(dict(clean, frame=0.0, bold=True)))
    results.append(("stamp: bold text heavier than regular", heavy > regular * 1.1, "(%d, %d)" % (regular, heavy)))
    ring = stamp.render_round(dict({f[0]: f[3] for f in stamp.ROUND_FIELDS}, invert=False, mirror=False, font=""))
    results.append(("round stamp: black and white, text drawn", _two_tone(ring) and _ink(ring) > 0,
                    "(%s)" % [_two_tone(ring), _ink(ring)]))
    return results


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    from kerfly.gui import stamp
    print("platform %s, font %s" % (QApplication.platformName(), stamp.default_font()))
    failed = 0
    for name, ok, detail in clean_report():
        print("%s  %s %s" % ("OK  " if ok else "FAIL", name, "" if ok else detail))
        failed += not ok
    print("All checks passed." if not failed else "%d check(s) failed." % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
