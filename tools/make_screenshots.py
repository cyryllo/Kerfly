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
WINDOW = (1840, 989)          # narrower hides the Help group of the (Polish) toolbar


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

    from PySide6.QtCore import QPoint, QRect, QRectF, Qt as _Qt

    def crop(win, widgets, path):
        """Save the part of a window covering these widgets (the website's pictures)."""
        rect = None
        for wd in widgets:
            r = QRect(wd.mapTo(win, QPoint(0, 0)), wd.size())
            rect = r if rect is None else rect.united(r)
        win.grab(rect).save(path)

    def zoom_to(win, elements, margin=8.0):
        """Fit the bed view to some elements (scene mm)."""
        x0 = min(e.bounds[0] for e in elements) * 25.4 - margin
        x1 = max(e.bounds[1] for e in elements) * 25.4 + margin
        y0 = -max(e.bounds[3] for e in elements) * 25.4 - margin
        y1 = -min(e.bounds[2] for e in elements) * 25.4 + margin
        win.preview.fitInView(QRectF(x0, y0, x1 - x0, y1 - y0), _Qt.KeepAspectRatio)
        settle(5)

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
    w.tabs.setCurrentIndex(0)
    # safety: an element sticking out of the bed is red, Start and Trace are locked
    w.preview.select_element([])
    w.elements[3].x += 95 / 25.4
    w._layout_changed()
    settle()
    w.grab().save(os.path.join(out, "site-safety.png"))
    w.elements[3].x -= 95 / 25.4
    w._layout_changed()
    # the job simulation, half way through
    w.simulate_job()
    settle(10)
    sim = w._simulation
    sim.timer.stop()
    sim.seek(sim.total * 0.55)
    settle(5)
    picture = w.grab()
    from PySide6.QtGui import QPainter as _QPainter
    panel = sim.grab()
    p = _QPainter(picture)
    corner = w.preview.mapTo(w, QPoint(w.preview.width() - panel.width() - 16, w.preview.height() - panel.height() - 16))
    p.drawPixmap(corner, panel)
    p.end()
    corner = w.preview.mapTo(w, QPoint(0, 0))
    picture.copy(QRect(corner, w.preview.size())).save(os.path.join(out, "site-simulation.png"))
    sim.close()
    w._dirty = False
    w.close()

    # node editing: a curve with its nodes and handles, close up
    from kerfly.core import curves as _curves
    nd = MainWindow(values)
    nd.resize(*WINDOW)
    nd.show()
    leaf = ShapeSpec(kind="path", operation="cut", subpaths=[{"closed": True, "nodes": [   # a heart
        _curves.node(45, 15, (30, -5), (60, -5)), _curves.node(85, 25, (90, 0), (80, 50)),
        _curves.node(45, 75, (60, 60), (30, 60)), _curves.node(5, 25, (10, 50), (0, 0))]}])
    nd._add_drawn_element(leaf, "pen", 60, 40)
    nd._edit_nodes_of(nd.elements[-1])
    settle()
    nd.preview.node_editor.select({(0, 1)})                 # the right lobe: its handles show
    settle()
    zoom_to(nd, nd.elements, 25)
    crop(nd, [nd.top_bar, nd.preview], os.path.join(out, "site-nodes.png"))
    nd._dirty = False
    nd.close()

    # generators on the bed: a material test, a finger-joint box, a gear and a stamp
    from kerfly.core import generators as _gen
    from kerfly.gui import stamp as _stamp
    gn = MainWindow(values)
    gn.resize(*WINDOW)
    gn.show()
    for (x, y), made in (((8, 8), _gen.material_test("engrave", 10, 50, 5, "passes", passes_min=1, passes_max=3,
                                                     rows=3, legend=i18n._("Speed (%s) / passes") % "mm/s")),
                         ((100, 8), _gen.finger_box(70, 50, 35, 3, 10, 0.15, lid=False)),
                         ((8, 75), _gen.gear(24, 2.0, 20, 6)),
                         ((8, 150), _stamp.make(dict(preset="47x18", text=i18n._(
                             "YOUR COMPANY\nStreet 1, 00-000 City\nphone 123 456 789"), font="DejaVu Sans", bold=True,
                             text_size=0, picture="", place="left", frame=0.6, corner=1, margin=1, invert=True,
                             mirror=True, outline=True), gn)),
                         ((62, 140), _stamp.make_round(dict(
                             {f[0]: f[3] for f in _stamp.ROUND_FIELDS}, top_text=i18n._("YOUR COMPANY NAME"),
                             bottom_text=i18n._("CITY"), text=i18n._("No. 123")), gn))):
        gn.head = (x / 25.4, -y / 25.4)
        gn.insert_generated(made)
    gn.head = (0.0, 0.0)
    gn.preview.select_element([])
    gn.refresh_preview()
    settle()
    zoom_to(gn, gn.elements, 6)
    crop(gn, [gn.preview], os.path.join(out, "site-generators.png"))
    gn._dirty = False
    gn.close()

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
    zoom_to(f, f.elements)
    crop(f, [f.top_bar, f.preview], os.path.join(out, "site-fill.png"))
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
    zoom_to(tp, tp.elements)
    crop(tp, [tp.top_bar, tp.preview], os.path.join(out, "site-textpath.png"))
    tp._dirty = False
    tp.close()

    # living hinges, with the tool in use
    hg = MainWindow(values)
    hg.resize(*WINDOW)
    hg.show()
    hg._add_drawn_element(ShapeSpec(kind="rectangle", width=120, height=60, corner_radius=4, operation="cut"),
                          "rectangle", 10, 10)
    hg._add_drawn_element(ShapeSpec(kind="rectangle", width=80, height=60, corner_radius=4, operation="cut"),
                          "rectangle", 140, 10)
    hg._add_drawn_element(ShapeSpec(kind="ellipse", width=100, height=60, operation="cut"), "ellipse", 10, 80)
    hg.set_tool("hinge")
    for (x, y), pattern in (((70, 40), "straight"), ((180, 40), "wave"), ((60, 110), "zigzag")):
        hg.hinge_defaults.hinge_pattern = pattern
        hg._hinge_clicked(QPointF(x, y))
    hg._update_tool_options(force=True)
    settle()
    hg.grab().save(os.path.join(out, "hinge.png"))
    zoom_to(hg, hg.elements)
    crop(hg, [hg.top_bar, hg.preview], os.path.join(out, "site-hinge.png"))
    hg._dirty = False
    hg.close()
    # the stamp generator's window
    from kerfly.gui.generators import GeneratorDialog
    st = MainWindow(values)
    st.resize(*WINDOW)
    dlg = GeneratorDialog(st, "stamp", remember=False)
    dlg.widgets["preset"].setCurrentIndex(dlg.widgets["preset"].findData("58x22"))
    dlg.widgets["picture"].edit.setText(os.path.join(ROOT, "kerfly", "gui", "icons", "kerfly.svg"))
    dlg.show()
    dlg.resize(1000, 640)
    settle()
    dlg._preview()
    settle()
    dlg.grab().save(os.path.join(out, "stamp.png"))
    dlg.close()
    dlg = GeneratorDialog(st, "round_stamp", remember=False)
    dlg.show()
    dlg.resize(1000, 700)
    settle()
    dlg._preview()
    settle()
    dlg.grab().save(os.path.join(out, "round-stamp.png"))
    dlg.close()
    st._dirty = False
    st.close()
    print("screenshots (%s) written" % lang)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--lang":
        take(sys.argv[2])
        return 0
    rc = 0
    for lang in LANGUAGES:
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="kerfly-shots-"), LANG="C.UTF-8",
                   LC_ALL="C.UTF-8", APPDATA=tempfile.mkdtemp(prefix="kerfly-shots-"),
                   XDG_CONFIG_HOME=tempfile.mkdtemp(prefix="kerfly-shots-"))
        env.setdefault("QT_QPA_PLATFORM", "xcb")
        rc |= subprocess.call([sys.executable, os.path.abspath(__file__), "--lang", lang], env=env)
    return rc


if __name__ == "__main__":
    sys.exit(main())
