#!/usr/bin/env python3
"""
Take the screenshots used by the README and the user guide, in English and
Polish, from the real window with a sample layout:

    xvfb-run -a -s "-screen 0 1920x1200x24" python tools/make_screenshots.py

Writes docs/screenshot.png, docs/screenshot_pl.png (README) and
docs/img/<language>/*.png (user guide). Run it again after the window
changes; the settings of the user are not touched (a temporary home folder
is used).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
LANGUAGES = ("en", "pl")
WINDOW = (1560, 989)          # narrower hides the Help group of the (Polish) toolbar


def take(lang):
    """Runs in a child process: the language must be set before the window
    module is imported."""
    sys.path.insert(0, ROOT)
    from kerfly import i18n
    i18n.setup(lang)
    from PySide6.QtWidgets import QApplication, QToolBar
    from kerfly.core import config
    from kerfly.core.shapes import ShapeSpec
    from kerfly.gui.main_window import MainWindow
    from kerfly.gui.text_shapes import update_text_spec

    app = QApplication([])

    def settle(n=20):
        for _ in range(n):
            app.processEvents()
            time.sleep(0.02)

    values = dict(config.DEFAULT_VALUES)
    values["language"] = lang
    w = MainWindow(values)
    w.resize(*WINDOW)
    w.show()
    os.chdir(ROOT)
    w.load_design(os.path.join("tests", "fixtures", "shapes.svg"))
    w.elements[0].x, w.elements[0].y = 7 / 25.4, -7 / 25.4
    w._layout_changed()
    w._add_drawn_element(ShapeSpec(kind="rectangle", width=65, height=44, corner_radius=6, operation="cut"),
                         "rectangle", 128, 9)
    w._add_drawn_element(ShapeSpec(kind="ellipse", width=52, height=32, operation="engrave"), "ellipse", 134.5, 15)
    w._add_drawn_element(ShapeSpec(kind="polygon", width=40, height=40, sides=6, operation="cut"), "polygon", 210, 11)
    text = ShapeSpec(kind="text", text="Kerfly", font_size=30, bold=True, operation="fill")
    update_text_spec(text)
    w._add_drawn_element(text, "text", 128, 72)
    w.status(i18n._("Ready"))
    settle()

    out = os.path.join(DOCS, "img", lang)
    os.makedirs(out, exist_ok=True)
    w.grab().save(os.path.join(DOCS, "screenshot.png" if lang == "en" else "screenshot_%s.png" % lang))
    w.findChild(QToolBar, "main_toolbar").grab().save(os.path.join(out, "toolbar.png"))
    w.top_bar.grab().save(os.path.join(out, "options.png"))
    w.tabs.setCurrentIndex(0)
    settle(5)
    w.tabs.grab().save(os.path.join(out, "design.png"))
    w.layers_panel.parentWidget().grab().save(os.path.join(out, "layers.png"))
    w.tabs.setCurrentIndex(1)
    settle(5)
    w.tabs.grab().save(os.path.join(out, "laser.png"))
    strip = [t for t in w.findChildren(QToolBar) if t.objectName() != "main_toolbar"][0]
    strip.grab().save(os.path.join(out, "tools.png"))
    w._dirty = False
    w.close()

    # pattern fills, with the Fill tool in use
    from PySide6.QtCore import QPointF
    f = MainWindow(values)
    f.resize(*WINDOW)
    f.show()
    shapes = [(ShapeSpec(kind="rectangle", width=70, height=50, corner_radius=6, operation="cut"), "rectangle", 10, 10),
              (ShapeSpec(kind="ellipse", width=70, height=50, operation="cut"), "ellipse", 95, 10),
              (ShapeSpec(kind="polygon", width=55, height=55, sides=6, operation="engrave"), "polygon", 180, 8),
              (ShapeSpec(kind="ellipse", width=50, height=50, operation="cut"), "ellipse", 20, 80),
              (ShapeSpec(kind="rectangle", width=70, height=45, operation="cut"), "rectangle", 95, 82)]
    for spec, tool, left, top in shapes:
        f._add_drawn_element(spec, tool, left, top)
    f.set_tool("fill")
    for (x, y), pattern, spacing in (((45, 35), "honeycomb", 6), ((130, 35), "waves", 4), ((207, 35), "bricks", 5),
                                     ((45, 105), "circles", 4), ((130, 105), "diamonds", 5)):
        f.fill_defaults.fill_pattern, f.fill_defaults.fill_spacing = pattern, spacing
        f._fill_clicked(QPointF(x, y))
    f._update_tool_options(force=True)
    settle()
    f.grab().save(os.path.join(out, "fill.png"))
    f._dirty = False
    f.close()

    # text on a path: around the top of a circle, and above a curve
    from kerfly.core import curves
    tp = MainWindow(values)
    tp.resize(*WINDOW)
    tp.show()
    tp._add_drawn_element(ShapeSpec(kind="ellipse", width=80, height=80, operation="cut"), "ellipse", 20, 25)
    wave = ShapeSpec(kind="path", operation="cut",
                     subpaths=[{"nodes": [curves.node(0, 30, None, (25, -10)), curves.node(110, 20, (85, 40), None)],
                                "closed": False}])
    tp._add_drawn_element(wave, "pen", 120, 40)
    for guide, words, size in ((0, "KERFLY · LASER", 9), (1, "Text on a path" if lang == "en" else "Tekst na ścieżce", 8)):
        t = ShapeSpec(kind="text", text=words, font_size=size, bold=True, operation="engrave")
        update_text_spec(t)
        tp._add_drawn_element(t, "text", 40, 160)
        tp.preview.select_element([tp.elements[guide], tp.elements[-1]])
        tp.selected = tp.elements[-1]
        tp.put_text_on_path()
    tp._update_tool_options(force=True)
    settle()
    tp.grab().save(os.path.join(out, "textpath.png"))
    tp._dirty = False
    tp.close()
    print("screenshots (%s) written" % lang)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--lang":
        take(sys.argv[2])
        return 0
    rc = 0
    for lang in LANGUAGES:
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="kerfly-shots-"), LANG="C.UTF-8",
                   LC_ALL="C.UTF-8", APPDATA=tempfile.mkdtemp(prefix="kerfly-shots-"))
        env.setdefault("QT_QPA_PLATFORM", "xcb")
        rc |= subprocess.call([sys.executable, os.path.abspath(__file__), "--lang", lang], env=env)
    return rc


if __name__ == "__main__":
    sys.exit(main())
