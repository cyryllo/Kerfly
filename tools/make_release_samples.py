#!/usr/bin/env python3
"""
Make the sample projects of the release tests (tests/fixtures/release/*.kerfly):
every kind of shape, every fill pattern, the living hinges, bridges and
combined shapes, raster engraving, and texts. tests/test_references.py
compares what Kerfly makes of them (laser data, cut order, bed view) with
saved references; the laser test card is made from them too.

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_release_samples.py

Run it again only when the samples themselves should change (then update the
references, see tests/test_references.py --update).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="kerfly_samples_cfg_")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from kerfly.core import config, curves, project  # noqa: E402
from kerfly.core.shapes import ShapeSpec  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from kerfly.gui.text_shapes import update_text_spec  # noqa: E402

OUT = os.path.join(ROOT, "tests", "fixtures", "release")


def window():
    values = dict(config.DEFAULT_VALUES)
    values.update(grid_mm="0", language="en")
    return MainWindow(values)


def add(w, left, top, **spec):
    kind = spec.get("kind", "rectangle")
    tool = {"path": "pen"}.get(kind, kind)
    s = ShapeSpec(**spec)
    if kind == "text":
        update_text_spec(s)
    w._add_drawn_element(s, tool, left, top)
    return w.elements[-1]


def save(w, name):
    path = os.path.join(OUT, name + ".kerfly")
    project.save_project(path, w.elements, w.layers)
    print("written", os.path.relpath(path, ROOT), "(%d elements)" % len(w.elements))
    w._dirty = False
    w.close()


def shapes():
    """Every shape, cut and outline engraving, a hole inside a part, an open line,
    rotated, scaled and mirrored elements."""
    w = window()
    add(w, 10, 10, kind="rectangle", width=40, height=30, operation="cut")
    add(w, 20, 18, kind="ellipse", width=20, height=14, operation="cut")          # a hole: cut first
    add(w, 60, 10, kind="rectangle", width=40, height=25, corner_radius=5, operation="engrave")
    p = add(w, 110, 10, kind="polygon", width=30, height=30, sides=7, operation="cut")
    w._rotate(p, 30)
    add(w, 10, 60, kind="line", width=50, height=0, operation="cut")              # open: from the nearer end
    add(w, 70, 50, kind="polyline", width=30, height=25, operation="engrave",
        points=[(0, 25), (15, 0), (30, 25)], closed_path=True)
    add(w, 120, 55, kind="path", operation="cut",
        subpaths=[{"nodes": [curves.node(0, 20, None, (15, -10)), curves.node(40, 20, (25, 40), None)],
                   "closed": False}])
    e = add(w, 175, 10, kind="ellipse", width=30, height=18, operation="cut")
    e.scale_x, e.scale_y = -1.5, 1.5                                             # mirrored and larger
    w._layout_changed()
    save(w, "shapes")


def fills():
    """The eight fill patterns; one without its outline."""
    w = window()
    patterns = ("lines", "cross", "waves", "zigzag", "circles", "honeycomb", "diamonds", "bricks")
    for n, pattern in enumerate(patterns):
        kind = "ellipse" if n % 3 == 1 else "rectangle"
        add(w, 10 + 45 * (n % 4), 10 + 35 * (n // 4), kind=kind, width=38, height=28, operation="cut",
            fill_pattern=pattern, fill_spacing=2.5, fill_angle=15 * n, fill_outline=(n != 7))
    save(w, "fills")


def hinges():
    """The three hinge patterns, across and along, and a hinge in a band."""
    w = window()
    add(w, 10, 10, kind="rectangle", width=80, height=40, operation="cut", hinge_pattern="straight")
    add(w, 100, 10, kind="rectangle", width=60, height=40, operation="cut", hinge_pattern="wave", hinge_angle=0)
    add(w, 10, 60, kind="ellipse", width=70, height=40, operation="cut", hinge_pattern="zigzag")
    add(w, 100, 60, kind="rectangle", width=80, height=40, operation="cut", hinge_pattern="straight",
        hinge_band=30, hinge_band_offset=10)
    save(w, "hinges")


def bridges_and_combined():
    """Bridges on cut parts; union and difference of two shapes."""
    w = window()
    add(w, 10, 10, kind="rectangle", width=40, height=30, operation="cut", tabs=4, tab_width=2)
    add(w, 60, 10, kind="ellipse", width=35, height=30, operation="cut", tabs=3, tab_width=1.5)
    for left, op in ((110, "union"), (170, "difference")):
        a = add(w, left, 10, kind="rectangle", width=30, height=30, operation="cut")
        b = add(w, left + 15, 20, kind="ellipse", width=30, height=25, operation="cut")
        w.preview.select_element([a, b])
        w.boolean_selected(op)
    save(w, "bridges_combined")


def raster():
    """Shapes engraved as a raster (filled)."""
    w = window()
    add(w, 10, 10, kind="rectangle", width=30, height=20, corner_radius=4, operation="fill")
    add(w, 50, 10, kind="ellipse", width=25, height=20, operation="fill")
    add(w, 85, 8, kind="polygon", width=24, height=24, sides=5, operation="fill")
    save(w, "raster")


def texts():
    """Texts (depend on the fonts of the computer: pictures only, no byte references)."""
    w = window()
    add(w, 10, 10, kind="text", text="Kerfly 1.0 źdźbło", font_size=8, operation="engrave")
    circle = add(w, 120, 10, kind="ellipse", width=50, height=50, operation="cut")
    add(w, 20, 60, kind="text", text="ON A CIRCLE", font_size=6, operation="engrave", text_spacing=0.5)
    w.preview.select_element([circle, w.elements[-1]])
    w.put_text_on_path()
    add(w, 10, 30, kind="text", text="Raster", font_size=10, bold=True, operation="fill")
    save(w, "texts")


def card():
    """The laser test card (tests/fixtures/release_card.kerfly): every operation on a
    piece of 3 mm plywood of about 150 x 105 mm, cut before a feature release.
    What to measure and look at: DEVELOPMENT.md, "Laser test card"."""
    w = window()
    # 1. size: a 50 mm square with a 20 mm hole in its middle (the hole is cut first)
    add(w, 5, 5, kind="rectangle", width=50, height=50, operation="cut")
    add(w, 20, 20, kind="ellipse", width=20, height=20, operation="cut")
    # 2. ruler: 100 mm with a mark every 10 mm (outline engraving)
    ruler = [{"nodes": [curves.node(0, 0, None, None), curves.node(100, 0, None, None)], "closed": False}]
    for n in range(11):                              # one element: the line and its marks
        ruler.append({"nodes": [curves.node(10 * n, 0, None, None),
                                curves.node(10 * n, 4 if n % 5 else 6, None, None)], "closed": False})
    add(w, 62, 6, kind="path", operation="engrave", subpaths=ruler)
    add(w, 104, 13, kind="text", text="100 mm", font_size=3, operation="engrave")
    # 3. raster: a filled block and a filled text
    add(w, 62, 22, kind="rectangle", width=30, height=10, corner_radius=2, operation="fill")
    add(w, 98, 22, kind="text", text="Kerfly", font_size=8, bold=True, operation="fill")
    # 4. fill patterns: four small squares, outline cut
    for n, pattern in enumerate(("lines", "honeycomb", "waves", "circles")):
        add(w, 62 + 22 * n, 38, kind="rectangle", width=18, height=18, operation="cut",
            fill_pattern=pattern, fill_spacing=2.0, fill_margin=0.5)
    # 5. living hinge
    add(w, 5, 62, kind="rectangle", width=60, height=30, corner_radius=2, operation="cut",
        hinge_pattern="straight", hinge_cut=12, hinge_gap=2.5, hinge_spacing=1.5, hinge_margin=3)
    # 6. text on a path: around the top of a circle
    circle = add(w, 75, 62, kind="ellipse", width=30, height=30, operation="cut")
    add(w, 75, 100, kind="text", text="KERFLY TEST", font_size=4, operation="engrave", text_path_distance=1)
    w.preview.select_element([circle, w.elements[-1]])
    w.put_text_on_path()
    # 7. bridges: the part stays in the sheet
    add(w, 112, 62, kind="rectangle", width=25, height=18, operation="cut", tabs=2, tab_width=1.5)
    # 8. turned outline engraving
    p = add(w, 114, 84, kind="polygon", width=16, height=16, sides=5, operation="engrave")
    w._rotate(p, 20)
    # 9. an open line cut (it starts at the end nearer the head)
    add(w, 5, 100, kind="line", width=60, height=0, operation="cut")
    path = os.path.join(ROOT, "tests", "fixtures", "release_card.kerfly")
    project.save_project(path, w.elements, w.layers)
    print("written", os.path.relpath(path, ROOT), "(%d elements)" % len(w.elements))
    w._dirty = False
    w.close()


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication([])
    for make in (shapes, fills, hinges, bridges_and_combined, raster, texts, card):
        make()
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
