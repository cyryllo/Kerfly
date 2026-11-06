"""
Release check of a built program:  Kerfly --release-test  (Windows: kerfly-console.exe --release-test)

Runs the self-test, then works with the real window the way the release
tests do, inside the packaged program, to find what only a package can
lack (fonts, Qt plugins, a library left out): draws every kind of shape and
a text, fills one with a pattern, cuts a hinge, adds bridges, combines two
shapes, opens an SVG and a picture, makes the laser data and the simulation,
and checks that the window shows what its data holds (kerfly.gui.truth).
Nothing is sent to a laser, and the settings are not saved.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import sys
import tempfile
import time
import traceback

from kerfly.selftest import FAIL, OK, WARN, Report


def _wait(app, condition, timeout=60.0):
    t0 = time.time()
    while not condition() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    return condition()


def _session(r, app):
    from kerfly.core import config
    from kerfly.core.shapes import ShapeSpec
    from kerfly.gui import truth
    from kerfly.gui.main_window import MainWindow
    from kerfly.gui.simulation import simulation_steps
    from kerfly.gui.text_shapes import update_text_spec

    values = dict(config.DEFAULT_VALUES)
    values.update(grid_mm="0")
    w = MainWindow(values)
    w.resize(1920, 1080)
    w.show()
    app.processEvents()

    def add(left, top, **spec):
        s = ShapeSpec(**spec)
        if s.kind == "text":
            update_text_spec(s)
        w._add_drawn_element(s, {"path": "pen"}.get(s.kind, s.kind), left, top)
        return w.elements[-1]

    add(10, 10, kind="rectangle", width=40, height=30, corner_radius=4, operation="cut", tabs=3, tab_width=1.5)
    add(60, 10, kind="ellipse", width=35, height=25, operation="cut", fill_pattern="honeycomb", fill_spacing=3)
    add(105, 10, kind="polygon", width=30, height=30, sides=6, operation="cut", hinge_pattern="wave")
    add(10, 50, kind="polyline", width=30, height=20, operation="engrave", points=[(0, 20), (15, 0), (30, 20)],
        closed_path=True)
    add(50, 50, kind="line", width=40, height=0, operation="cut")
    text = add(10, 80, kind="text", text="Kerfly ąęłóśżź", font_size=8, operation="engrave")
    r.add(OK if text.design.vector_engrave.ecoords else FAIL, "Text", "font %s" % text.shape.font_family)
    a = add(150, 10, kind="rectangle", width=30, height=30, operation="cut")
    b = add(165, 20, kind="ellipse", width=30, height=25, operation="cut")
    n = len(w.elements)
    w.preview.select_element([a, b])
    w.boolean_selected("union")
    r.add(OK if len(w.elements) == n - 1 else FAIL, "Combine shapes", "%d -> %d elements" % (n, len(w.elements)))
    filled = w.elements[1]
    r.add(OK if filled.design.vector_engrave.ecoords else FAIL, "Pattern fill", "honeycomb")
    r.add(OK if len(w.elements[2].design.vector_cut.ecoords) > 50 else FAIL, "Living hinge", "wavy cuts")

    folder = tempfile.mkdtemp(prefix="kerfly_release_check_")
    svg = os.path.join(folder, "check.svg")
    with open(svg, "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20">'
                '<rect x="1" y="1" width="38" height="18" fill="none" stroke="red" stroke-width="0.1"/>'
                '<circle cx="20" cy="10" r="6" fill="black"/></svg>')
    w.load_design(svg, add=True)
    svg_el = w.elements[-1]
    r.add(OK if svg_el.design.vector_cut.ecoords and svg_el.design.raster.image is not None else FAIL,
          "SVG (cut and raster)", os.path.basename(svg))
    from PySide6.QtGui import QColor, QImage
    png = os.path.join(folder, "check.png")
    img = QImage(80, 40, QImage.Format_RGB32)
    img.fill(QColor("white"))
    for x in range(20, 60):
        for y in range(10, 30):
            img.setPixelColor(x, y, QColor("black"))
    img.save(png)
    w._ask_image_dpi = lambda _name: 254.0
    w.load_design(png, add=True)
    r.add(OK if w.elements[-1].design.raster.image is not None else FAIL, "Picture (PNG)", "")

    problems = truth.check_window(w)
    r.add(OK if not problems else FAIL, "Window shows its data", "; ".join(problems[:3]))
    egv = os.path.join(folder, "check.egv")
    w.start_job(output_file=egv)
    _wait(app, lambda: w.worker is None)
    size = os.path.getsize(egv) if os.path.exists(egv) else 0
    r.add(OK if size > 1000 else FAIL, "Laser data (EGV)", "%d bytes" % size)
    steps = simulation_steps(w)
    r.add(OK if steps else FAIL, "Simulation", "%d moves, %.0f s" % (len(steps), sum(s.seconds for s in steps)))
    w.undo()
    w.redo()
    problems = truth.check_window(w)
    r.add(OK if not problems else FAIL, "Undo / redo", "; ".join(problems[:3]))
    w._dirty = False
    w.close()


def run():
    from kerfly import selftest
    rc = selftest.run()
    print("\nKerfly release check\n", flush=True)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    r = Report()
    try:
        _session(r, app)
    except Exception:
        r.add(FAIL, "Unexpected error", "")
        traceback.print_exc()
    print("\n" + ("Release check FAILED: see the lines marked FAIL." if r.failed or rc
                  else "Release check passed."), flush=True)
    return 1 if r.failed or rc else 0
