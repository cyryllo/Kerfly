#!/usr/bin/env python3
"""
Tests the PySide6 GUI end to end (offscreen): jobs started from the new
window must produce the same laser data as the upstream baseline, and
pause/stop must work while a job is being sent.

Usage:
    .venv/bin/python tests/test_gui.py
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# never touch the user's real settings folder (material library) from tests
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="kerfly_test_cfg_")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QWidget, QFileDialog, QInputDialog, QLabel, QMessageBox, QToolButton  # noqa: E402

from kerfly.core import config  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from fakes import FakeK40, run_until_idle  # noqa: E402
from uidriver import bar_set, choose_layer, click_bar_button, select  # noqa: E402

FIX = os.path.join(TESTS_DIR, "fixtures")
BASE = os.path.join(TESTS_DIR, "baseline")


def read_usb_baseline(path):
    """[(power, bytes)] from a regression .usb capture."""
    blob = open(path, "rb").read()
    out, power, pos = [], None, 0
    while pos < len(blob):
        end = blob.index(b"\n", pos)
        line = blob[pos:end].decode()
        pos = end + 1
        m = re.match(r"#set_PWM_register (.*)", line)
        if m:
            power = float(m.group(1))
            continue
        m = re.match(r"#send_data .* len=(\d+)", line)
        if m:
            n = int(m.group(1))
            out.append((power, blob[pos:pos + n]))
            pos += n + 1
            power = None
    return out


def find_inkscape():
    """Inkscape the way Kerfly finds it (PATH or the usual install folders)."""
    import svg_reader
    reader = svg_reader.SVG_READER()
    reader.set_inkscape_path(shutil.which("inkscape"))
    return reader.inkscape_exe or ""


INKSCAPE = find_inkscape()


OPEN_WINDOWS = []          # checked by kerfly.gui.truth after every check (until closed)


def make_window(**overrides):
    values = dict(config.DEFAULT_VALUES)
    values["inkscape_path"] = INKSCAPE
    values.update(overrides)
    w = MainWindow(values)
    OPEN_WINDOWS.append(w)
    close = w.close

    def closed():
        if w in OPEN_WINDOWS:
            OPEN_WINDOWS.remove(w)
        return close()
    w.close = closed
    return w


def main():
    app = QApplication([])
    # "save changes first?" when replacing a design: discard in tests
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
    manifest = json.load(open(os.path.join(BASE, "manifest.json")))["cases"]
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        # every open window must show what its data holds (kerfly.gui.truth)
        from kerfly.gui import truth
        for _i in range(3):
            app.processEvents()                  # widgets added to a shown window appear a moment later
        for n, win in enumerate(list(OPEN_WINDOWS)):
            for problem in truth.check_window(win):
                print("TRUTH [%s] window %d: %s" % (name[:50], n, problem))
                ok = False                       # the window shows something else than it holds
        print("%-5s %s %s" % ("OK" if ok else "FAIL", name, detail))
        if not ok and os.environ.get("GITHUB_ACTIONS"):
            print("::error title=test_gui::%s %s" % (name, detail))     # shown as a CI annotation
        failures += 0 if ok else 1

    def skip(name):
        print("SKIP  %s (Inkscape not installed; the baseline raster was made with Inkscape)" % name)

    # 1. EGV file from the GUI == baseline (raster + vector engrave + vector cut)
    out = tempfile.mktemp(suffix=".egv")
    if INKSCAPE:
        w = make_window()
        w.load_design(os.path.join(FIX, "shapes.svg"))
        w.start_job(output_file=out)
        run_until_idle(app, w)
        digest = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
        check("gui_save_egv == svg_raster_vector_cut", digest == manifest["svg_raster_vector_cut"]["sha256"])
    else:
        skip("gui_save_egv == svg_raster_vector_cut")

    # 2. only vector cut selected, DXF
    w = make_window(include_Reng="0", include_Veng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    check("gui_save_egv dxf == dxf_vcut", digest == manifest["dxf_vcut"]["sha256"])
    os.remove(out)

    # 3. M3 power per stage through the laser path
    if INKSCAPE:
        w = make_window(board_name="LASER-M3", Reng_power="0.3", Veng_power="0.6", Vcut_power="0.9")
        w.load_design(os.path.join(FIX, "shapes.svg"))
        fake = FakeK40()
        w.laser.k40 = fake
        w.start_job()
        run_until_idle(app, w)
        expected = read_usb_baseline(os.path.join(BASE, "usb_m3_power_levels.usb"))
        check("gui_laser_job m3 == usb_m3_power_levels", fake.sent == expected,
              "(%d stages, powers %s)" % (len(fake.sent), [p for p, _ in fake.sent]))
    else:
        skip("gui_laser_job m3 == usb_m3_power_levels")

    # 4. Stop while sending: immediate e-stop, no pause, no question
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    asked = []
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(1), QMessageBox.No)[1])

    def wait_for_sending(w):
        t0 = time.time()
        while "Sending" not in w.statusBar().currentMessage() and time.time() - t0 < 60:
            app.processEvents()
            time.sleep(0.01)

    w.start_job()
    wait_for_sending(w)
    w.stop_job()
    run_until_idle(app, w)
    check("Stop: immediate e-stop", not asked and "pause" not in fake.calls and "e_stop" in fake.calls
          and fake.sent == [], "(calls %s, status %r)" % (fake.calls, w.statusBar().currentMessage()))

    # 5. Pause, then the same button resumes; the job finishes
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    w.start_job()
    wait_for_sending(w)
    w.pause_job()
    t0 = time.time()
    while not w._paused and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    paused_state = w._paused and w.btn_pause.isEnabled()
    w.pause_job()                                   # resume
    run_until_idle(app, w)
    check("Pause -> resume", paused_state and fake.calls.count("pause") == 2 and len(fake.sent) == 1
          and not asked, "(calls %s)" % fake.calls)

    # 5b. Pause, then Stop ends the job
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    w.start_job()
    wait_for_sending(w)
    w.pause_job()
    t0 = time.time()
    while not w._paused and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    w.stop_job()
    run_until_idle(app, w)
    check("Pause -> Stop", fake.calls.count("pause") == 1 and "e_stop" in fake.calls and fake.sent == []
          and not w._paused, "(calls %s)" % fake.calls)

    # 6. move head to a design corner, then a job first brings it back
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))      # 100 x 80 mm
    fake = FakeK40()
    w.laser.k40 = fake
    w.move_to_corner("LR")
    lr = list(fake.moves)
    w.start_job()
    run_until_idle(app, w)
    check("move to corner LR and back before job",
          lr == [(3937, -3150)] and fake.moves == [(3937, -3150), (-3937, 3150)]
          and w.head == (0.0, 0.0) and len(fake.sent) == 1, "(moves %s)" % fake.moves)

    # 7. go to position: home, then move to X 20 mm, Y 10 mm down
    w = make_window()
    fake = FakeK40()
    w.laser.k40 = fake
    w.goto_x.setValue(20.0)
    w.goto_y.setValue(10.0)
    w.goto_position()
    check("go to position", "home_position" in fake.calls and fake.moves == [(787, -394)]
          and w.head == (0.787, -0.394) and w.values["gotoY"] == "-10",
          "(moves %s, head %s)" % (fake.moves, w.head))

    # 7b. unit change converts the go-to fields
    from kerfly.core import config as cfg
    new = cfg.convert_units(w.values, "in")
    w.values.clear()
    w.values.update(new)
    w._reload_spin_values()
    check("go-to fields follow unit change", abs(w.goto_x.value() - 0.79) < 0.01
          and abs(w.goto_y.value() - 0.39) < 0.01, "(%s, %s)" % (w.goto_x.value(), w.goto_y.value()))

    # 8. time estimate: raster unknown until calculated
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    raster_row = w.layers_panel.rows[w._default_layer["raster"].id]
    cut_row = w.layers_panel.rows[w._default_layer["cut"].id]
    before = raster_row["time"].text()
    calc_shown = not raster_row["calc"].isHidden()
    vcut = cut_row["time"].text()
    w.calculate_raster_time()
    run_until_idle(app, w)
    raster_row = w.layers_panel.rows[w._default_layer["raster"].id]
    after = raster_row["time"].text()
    check("time estimate", before == "" and calc_shown and after not in ("", "?") and vcut.endswith("s")
          and raster_row["calc"].isHidden(), "(raster %r -> %r, cut %r, total %r)"
          % (before, after, vcut, w.layers_panel.total_label.text()))

    # 9. send an EGV file (3 passes)
    egv_path = os.path.join(BASE, "svg_vcut.egv")
    w = make_window()
    fake = FakeK40()
    w.laser.k40 = fake
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (egv_path, ""))
    QInputDialog.getInt = staticmethod(lambda *a, **k: (3, True))
    w.send_egv_file()
    run_until_idle(app, w)
    raw = open(egv_path, "rb").read()
    payload = raw[raw.index(b"%0%0%0%0%") + 9:]
    check("send EGV file", fake.sent == [(None, payload)] and fake.passes == [3] and fake.moves == [],
          "(sent %d bytes, passes %s)" % (len(fake.sent[0][1]) if fake.sent else 0, fake.passes))

    # 10. open a PNG through the window (size dialog accepted) and save EGV
    from kerfly.gui import image_dialog
    sys.path.insert(0, TESTS_DIR)
    from regression import synthetic_image
    png = tempfile.mktemp(suffix=".png")
    synthetic_image().save(png, dpi=(1000, 1000))
    image_dialog.ImageSizeDialog.exec = lambda self: True
    w = make_window()
    w.load_design(png)
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
    check("open PNG in window, save EGV == png_reng_halftone",
          digest == manifest["png_reng_halftone"]["sha256"], "(%s)" % w.design_label.text())
    os.remove(png)

    # 11. editor: two elements, drag one, the job first moves the head to the design
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))                  # 60 x 40 mm at home
    w.load_design(os.path.join(FIX, "sample.ngc"), add=True)        # G-code replaces, never combines
    only_gcode = len(w.elements) == 1 and w.elements[0].name == "sample.ngc"
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.head = (2.0, -1.0)
    w.load_design(os.path.join(FIX, "shapes.dxf"), add=True)        # second copy placed at the head
    a, b = w.elements
    w._preview_moved(a, 1.0, -0.5)                                  # drag the first one
    fake = FakeK40()
    w.laser.k40 = fake
    w.head = (0.0, 0.0)
    w.start_job()
    run_until_idle(app, w)
    check("editor: G-code is not combined", only_gcode)
    check("editor: two elements, head moves to the design first",
          (a.x, a.y) == (1.0, -0.5) and (b.x, b.y) == (2.0, -1.0) and w.origin == (1.0, -0.5)
          and fake.moves[:1] == [(1000, -500)] and len(fake.sent) == 1,
          "(origin %s, moves %s)" % (w.origin, fake.moves))

    # 12. place at head, rotate 90, delete
    w.laser.k40 = None
    w.head = (3.0, -2.0)
    w.place_at_head()
    placed = w.origin == (3.0, -2.0)
    select(w, b)
    size_before = b.size
    w.rotate_selected(90)
    rotated = abs(b.size[0] - size_before[1]) < 1e-9 and abs(b.size[1] - size_before[0]) < 1e-9
    w.delete_selected()
    check("editor: place at head, rotate 90, delete", placed and rotated and w.elements == [a]
          and w.selected is None)

    # 13. undo / redo, duplicate, hide, centre, snap to grid, arrow-key nudge
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))                  # 60 x 40 mm
    e = w.elements[0]
    w._preview_moved(e, 1.0, -1.0)
    w.undo()
    undo_ok = (e.x, e.y) == (0.0, 0.0)
    w.redo()
    redo_ok = (e.x, e.y) == (1.0, -1.0)
    w.duplicate_selected()
    dup = w.selected
    dup_ok = len(w.elements) == 2 and dup is not e and dup.design is e.design
    w.undo()
    undo_dup_ok = len(w.elements) == 1
    w.redo()
    w.element_list.item(1).setCheckState(Qt.Unchecked)       # untick it in the element list
    w._compiled = None
    hidden_ok = w.design is e.design or w.design.bounds == e.design.bounds   # only e compiled
    select(w, e)
    w.center_on_bed()
    bed_w, bed_h = 325 / 25.4, 220 / 25.4
    cx, cy = e.centre
    centre_ok = abs(cx - bed_w / 2) < 1e-9 and abs(cy + bed_h / 2) < 1e-9
    w.set_grid(5)
    w._preview_moved(e, 0.123, -0.077)
    g = 5 / 25.4
    snap_ok = abs(e.x / g - round(e.x / g)) < 1e-9 and abs(e.y / g - round(e.y / g)) < 1e-9
    x0 = e.x
    w.preview.select_element(e)
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(w.preview, _Qt.Key_Right)
    nudge_ok = abs((e.x - x0) - g) < 1e-9
    QTest.keyClick(w.preview, _Qt.Key_Right, _Qt.ShiftModifier)
    nudge10_ok = abs((e.x - x0) - 11 * g) < 1e-9
    check("editor: undo/redo", undo_ok and redo_ok and undo_dup_ok)
    check("editor: duplicate, hidden element left out of the job", dup_ok and hidden_ok)
    check("editor: centre on bed, snap to grid, arrow keys", centre_ok and snap_ok and nudge_ok and nudge10_ok,
          "(centre %s, snap %s, nudge %s/%s)" % (centre_ok, snap_ok, nudge_ok, nudge10_ok))

    # 14. drawing tools: shapes drawn in the bed view, edited from the options bar
    from PySide6.QtCore import QPointF
    w = make_window()
    w._preview_drawn("rectangle", QPointF(10, 10), QPointF(50, 30), False)
    rect = w.selected
    w._preview_drawn("ellipse", QPointF(60, 10), QPointF(80, 40), True)      # Shift: circle
    circle = w.selected
    w._preview_drawn("line", QPointF(10, 50), QPointF(60, 52), True)         # Shift: horizontal
    line = w.selected
    w._preview_drawn("text", QPointF(10, 70), QPointF(10, 70), False)
    text = w.selected
    sizes = [tuple(round(v * 25.4, 1) for v in e.size) for e in (rect, circle, line)]
    drawn_ok = (sizes[0] == (40.0, 20.0) and sizes[1] == (30.0, 30.0) and sizes[2][1] == 0.0
                and abs(rect.x * 25.4 - 10) < 1e-6 and abs(rect.y * 25.4 + 10) < 1e-6
                and text.design.raster.image is not None and w.preview.tool == "select")
    check("draw: rectangle, Shift-circle, Shift-line, text", drawn_ok, "(%s)" % sizes)
    select(w, rect)
    choose_layer(w, next(l for l in w.layers if l.kind == "engrave"))
    bar_set(w, "corner_radius", 4)
    engraved = bool(rect.design.vector_engrave.ecoords) and not rect.design.vector_cut.ecoords \
        and rect.shape.corner_radius == 4
    select(w, text)
    bar_set(w, "text", "Kerfly")
    wider = text.size[0] > 0 and text.shape.text == "Kerfly"
    w.undo()
    undone = text.shape.text != "Kerfly"
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    check("draw: options bar edits (operation, radius, text) and undo",
          engraved and wider and undone and os.path.exists(out) and os.path.getsize(out) > 1000)

    # 15. layers: an extra cut layer for a second element, materials, undo
    w = make_window(include_Reng="0", include_Veng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.head = (3.0, 0.0)
    w.load_design(os.path.join(FIX, "shapes.dxf"), add=True)          # selected
    second = w.selected
    n_rows = len(w.layers_panel.rows)
    extra = w.add_layer("cut")                                         # appended, nothing moved yet
    appended = len(w.layers_panel.rows) == n_rows + 1 and "cut" not in second.layers
    w._assign_layer("cut", extra.id)                                   # Layer choice above the bed
    assigned = appended and second.layers.get("cut") == extra.id
    extra.speed = 3.0
    extra.passes = 2
    w._layer_changed(extra)
    rows_ok = extra.id in w.layers_panel.rows and w._default_layer["cut"].id in w.layers_panel.rows
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    two_layers = os.path.getsize(out)
    w._assign_layer("cut", w._default_layer["cut"].id)                 # back via the bar above the bed
    back = "cut" not in second.layers
    w.undo()
    undone = second.layers.get("cut") == extra.id
    w.remove_layer(extra)
    removed = extra not in w.layers and "cut" not in second.layers
    check("layers: extra cut layer, assignment, undo, delete", assigned and rows_ok and back and undone
          and removed and two_layers > 1000, "(egv %d bytes)" % two_layers)
    plywood = [i for i, m in enumerate(w.materials) if m.name.startswith("Plywood 3")][0]
    w.apply_material(plywood)
    cut = w._default_layer["cut"]
    check("materials: applying a material sets the layers", cut.speed == 8.0 and cut.passes == 1
          and w.values["Vcut_feed"] == "8" and abs(cut.power - 0.6) < 1e-9,
          "(cut speed %s, Vcut_feed %s)" % (cut.speed, w.values["Vcut_feed"]))

    # 16. project file: save a layout and open it again in a new window
    from kerfly.gui import image_dialog as _imgdlg
    png2 = tempfile.mktemp(suffix=".png")
    synthetic_image().save(png2, dpi=(300, 300))
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    _imgdlg.ImageSizeDialog.exec = lambda self: True
    w.head = (4.2, -0.2)
    w.load_design(png2, add=True)
    w._rotate(w.selected, 30)
    w._preview_drawn("rectangle", QPointF(120, 100), QPointF(170, 130), False)
    w._assign_layer("cut", w.add_layer("cut").id)
    extra_id = w.selected.layers["cut"]
    w._preview_drawn("text", QPointF(20, 150), QPointF(20, 150), False)
    bar_set(w, "text", "Kerfly")
    title_dirty = w.windowTitle().startswith("*")
    egv1 = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=egv1)
    run_until_idle(app, w)
    proj = tempfile.mktemp(suffix=".kerfly")
    saved = w._write_project(proj)
    title_clean = not w.windowTitle().startswith("*")
    asked = []
    _imgdlg.ImageSizeDialog.exec = lambda self: (asked.append("image"), True)[1]
    w2 = make_window()
    w2.open_project(proj)
    egv2 = tempfile.mktemp(suffix=".egv")
    w2.start_job(output_file=egv2)
    run_until_idle(app, w2)
    same = open(egv1, "rb").read() == open(egv2, "rb").read()
    layout_same = [(e.name, round(e.x, 9), round(e.y, 9), e.rotation) for e in w.elements] == \
        [(e.name, round(e.x, 9), round(e.y, 9), e.rotation) for e in w2.elements]
    extra2 = [l for l in w2.layers if l.kind == "cut"]
    check("project: save and reopen gives the same layout and laser data",
          saved and title_dirty and title_clean and same and layout_same and not asked
          and len(extra2) == 2 and w2.elements[2].layers.get("cut") == extra2[1].id,
          "(egv %d bytes, same %s, asked %s)" % (os.path.getsize(egv1), same, asked))
    os.remove(png2)

    # 17. SVG without Inkscape: built-in renderer
    w = make_window(use_inkscape="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    # The built-in renderer anti-aliases edges slightly differently from Inkscape,
    # so after halftoning a few dots move: compare closely, not byte for byte.
    size = os.path.getsize(out) if os.path.exists(out) else 0
    ref_size = manifest["svg_raster_vector_cut"]["size"]
    if INKSCAPE:
        from PIL import ImageChops
        from kerfly.core import loaders as _loaders
        from kerfly.core.design import Design as _Design
        ref = _Design()
        _loaders.load_svg(os.path.join(FIX, "shapes.svg"), ref, inkscape_path=INKSCAPE)
        from kerfly.gui.svg_render import render_svg as _render_svg
        built = _Design()                       # freshly loaded: a job reorders the cut paths in place
        _loaders.load_svg(os.path.join(FIX, "shapes.svg"), built, svg_renderer=_render_svg, use_inkscape=False)
        diff = ImageChops.difference(ref.raster.image, built.raster.image)
        hist = diff.histogram()
        changed = sum(hist[1:])
        worst = max((v for v in range(256) if hist[v]), default=0)
        vectors_same = (ref.vector_cut.ecoords == built.vector_cut.ecoords
                        and ref.vector_engrave.ecoords == built.vector_engrave.ecoords)
        check("SVG without Inkscape: same vectors, raster within anti-aliasing tolerance",
              vectors_same and worst <= 32 and changed < 0.001 * ref.raster.image.width * ref.raster.image.height
              and abs(size - ref_size) < 0.01 * ref_size,
              "(%d edge pixels differ, max %d/255; EGV %d vs %d bytes)" % (changed, worst, size, ref_size))
    else:
        check("SVG without Inkscape: job size close to the Inkscape baseline", abs(size - ref_size) < 0.01 * ref_size,
              "(EGV %d vs %d bytes)" % (size, ref_size))
    errors = []
    QMessageBox.critical = staticmethod(lambda *a, **k: errors.append(a[2] if len(a) > 2 else ""))
    red_text = tempfile.mktemp(suffix=".svg")
    open(red_text, "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="20mm" '
                              'viewBox="0 0 50 20"><text x="2" y="15" fill="none" stroke="#ff0000">Hi</text></svg>')
    w.load_design(red_text)
    check("SVG without Inkscape: cut text gives a clear message",
          len(errors) == 1 and "paths" in errors[0], "(%s)" % errors)
    os.remove(red_text)

    # 18. material library import through the Settings menu
    from kerfly.core import materials as _ml
    lib_file = tempfile.mktemp(suffix=".json")
    _ml.export_library([_ml.Material("Test board 2 mm", 2.0, "", {"cut": _ml.OperationSettings(7.0, 2, 0.5)})],
                       lib_file)
    w = make_window()
    n_before = len(w.materials)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (lib_file, ""))
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    w.import_materials()
    names = [m.name for m in w.materials]
    saved = os.path.isfile(_ml.library_path())
    check("materials: import adds to the library and saves it", len(w.materials) == n_before + 1
          and "Test board 2 mm" in names and saved, "(%d materials)" % len(w.materials))
    os.remove(lib_file)

    # 19. element outside the work area: drawn red, Start and Trace locked
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    ok_before = w.btn_start.isEnabled() and not w.bed_warning.isVisibleTo(w)
    e = w.elements[0]
    e.x = 100.0                                                        # far right of any bed
    w._layout_changed()
    item = w.preview._items[0]
    locked = (not w.btn_start.isEnabled() and not w.btn_trace.isEnabled() and not w.act_start.isEnabled()
              and w.bed_warning.isVisibleTo(w) and item.off_bed())
    w.start_job(output_file=tempfile.mktemp(suffix=".egv"))
    not_started = w.worker is None
    e.x = 0.0
    w._layout_changed()
    unlocked = w.btn_start.isEnabled() and not w.bed_warning.isVisibleTo(w) and not w.preview._items[0].off_bed()
    check("outside the work area: red, Start/Trace locked, unlocked when back",
          ok_before and locked and not_started and unlocked)

    # 21. mirror, align, distribute from the window (several selected elements)
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    for x0, y0 in ((120, 20), (170, 60), (250, 100)):
        w._preview_drawn("rectangle", QPointF(x0, y0), QPointF(x0 + 20, y0 + 15), False)
    shapes = w.elements[1:]
    w.preview.select_element(shapes)
    w.align_selected("top")
    tops = [round(e.bounds[3], 6) for e in shapes]
    still_selected = len(w._selection()) == 3
    w.distribute_selected(True)
    gaps = [round(shapes[i + 1].bounds[0] - shapes[i].bounds[1], 6) for i in range(2)]
    w.undo()
    undone = [round(e.bounds[0] - shapes[0].bounds[1], 6) for e in shapes[1:2]] != gaps[:1]
    w.preview.select_element(w.elements[0])
    before = w.elements[0].scale_x
    w.mirror_selected(True)
    mirrored = w.elements[0].scale_x == -before
    check("arrange: align top, distribute, undo, mirror", len(set(tops)) == 1 and still_selected
          and gaps[0] == gaps[1] and undone and mirrored, "(tops %s, gaps %s)" % (tops, gaps))

    # 22. polyline tool: clicks in the bed view, close on the first point; open with Enter; saved in projects
    pass  # Qt: imported at the top
    from PySide6.QtTest import QTest
    w = make_window()
    w.resize(1200, 800)
    w.show()
    for _settle in range(5):             # the panel measures itself once more after showing: let it settle
        app.processEvents()              # (the bed view must not move between the clicks)
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    w.set_tool("polyline")

    def click(x, y, mods=Qt.NoModifier):
        pos = view.mapFromScene(QPointF(x, y))
        QTest.mouseMove(view.viewport(), pos)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, mods, pos)
        app.processEvents()

    for x, y in ((50, 50), (110, 50), (80, 100)):
        click(x, y)
    click(50, 50)                                                      # first point again: closes
    closed_el = w.elements[-1] if w.elements else None
    closed_ok = (closed_el is not None and closed_el.shape.kind == "polyline" and closed_el.shape.closed_path
                 and len(closed_el.shape.points) == 3 and abs(closed_el.size[0] * 25.4 - 60) < 0.5)
    w.set_tool("polyline")
    for x, y in ((150, 40), (190, 40), (190, 90)):
        click(x, y)
    QTest.keyClick(view.viewport(), Qt.Key_Return)
    app.processEvents()
    open_el = w.elements[-1]
    open_ok = (open_el is not closed_el and not open_el.shape.closed_path and len(open_el.shape.points) == 3
               and open_el.design.vector_cut.ecoords)
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, w.elements, w.layers)
    data, _folder = _project.read_project(proj)
    reread = _project.shape_from_item(data["elements"][0])
    check("polyline: click corners, close on the first point, Enter for open, saved in project",
          closed_ok and open_ok and reread.points == closed_el.shape.points and reread.closed_path,
          "(%d elements, closed %s, open %s, viewport %s)" % (len(w.elements), closed_ok, open_ok,
                                                             view.viewport().size().toTuple()))
    w.close()

    # 23. object snapping: drawing starts on another shape's corner; dragging snaps an element to it
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    view = w.preview
    p = view.snap_point(QPointF(60.4, 49.7))
    corner = abs(p.x() - 60) < 1e-6 and abs(p.y() - 50) < 1e-6 and view._snap_marker is not None
    w.toggle_snap_objects(False)
    free = view.snap_point(QPointF(60.4, 49.7))
    off = abs(free.x() - 60.4) < 1e-6
    w.toggle_snap_objects(True)
    w._preview_drawn("rectangle", QPointF(100, 100), QPointF(120, 120), False)
    second = view._items[-1]
    view.scene().clearSelection()
    second.setSelected(True)
    second._press_pos = second.pos()
    second._dragging = True
    r = second.sceneBoundingRect()                                     # top-left near the first one's corner
    second.setPos(second.pos() + QPointF(60.5 - r.left(), 50.4 - r.top()))
    r = second.sceneBoundingRect()
    dragged = abs(r.left() - 60) < 1e-6 and abs(r.top() - 50) < 1e-6 and view.last_move_snapped
    moved_el = second.element
    second.finish_drag()                                               # mouse released: the element moves
    dragged = dragged and abs(moved_el.x * 25.4 - 60) < 1e-6 and abs(moved_el.y * 25.4 + 50) < 1e-6
    check("snapping: draw from a corner, off switch, drag onto another element",
          corner and off and dragged, "(left %.3f)" % (moved_el.x * 25.4))
    view.last_move_snapped = False
    w.close()

    # 24. node tool: move a node of a rotated rectangle, insert, curve, smooth, delete, close, undo, snap
    from kerfly.core import curves as _curves
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 70), False)    # 40 x 30 mm
    rect = w.elements[-1]
    w._rotate(rect, 90)
    w.set_tool("nodes")
    view = w.preview
    ed = view.node_editor
    view.select_element(rect)
    app.processEvents()
    four = len(view.node_scene_points()) == 4
    before = view.node_scene_points()
    _curves.move_node(ed.path, 0, 0, before[0].x() - 10, before[0].y() - 5)
    ed.commit()
    after = view.node_scene_points()
    moved_ok = (rect.shape.kind == "path" and rect.rotation == 90 and abs(after[0].x() - before[0].x() + 10) < 1e-6
                and abs(after[0].y() - before[0].y() + 5) < 1e-6
                and all(abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6 for a, b in zip(after[1:], before[1:])))
    mid = (after[1] + after[2]) / 2.0
    inserted = ed.insert_at(mid) and len(view.node_scene_points()) == 5 and w.tool_options.spec.kind == "path"
    ed.select({(0, 1)})
    curved = ed.action("curve") and any(n[4] is not None for n in rect.shape.subpaths[0]["nodes"])
    ed.select({(0, 1)})
    smoothed = ed.action("smooth") and _curves._is_smooth(rect.shape.subpaths[0]["nodes"][1])
    ed.select({(0, 2)})
    deleted = ed.action("delete") and len(view.node_scene_points()) == 4
    ed.select({(0, 0)})
    opened = ed.action("close") and not rect.shape.subpaths[0]["closed"]
    w.undo(); w.undo(); w.undo(); w.undo(); w.undo(); w.undo()
    undone = (rect.shape.kind == "rectangle") if rect in w.elements else w.elements[-1].shape.kind == "rectangle"
    # snapping while dragging a node: onto its own corner, and in line with another one
    view.select_element(w.elements[-1])
    pts = view.node_scene_points()
    own = ed._snap(pts[2] + QPointF(0.3, 0.3), (0, 0))
    own_ok = abs(own.x() - pts[2].x()) < 1e-6 and abs(own.y() - pts[2].y()) < 1e-6
    far = pts[1] + QPointF(15, 0.4)
    lined = ed._snap(far, (0, 0))
    in_line = abs(lined.y() - pts[1].y()) < 1e-6 and abs(lined.x() - far.x()) < 1e-6
    view._remove_guides()
    view.hide_snap_marker()
    w._preview_drawn("text", QPointF(20, 120), QPointF(20, 120), False)
    w.set_tool("nodes")
    view.select_element(w.elements[-1])
    no_text_nodes = not view._node_handles
    results = [four, moved_ok, inserted, curved, smoothed, deleted, opened, undone, own_ok, in_line, no_text_nodes]
    check("node tool: move, insert, curve, smooth, delete, open, undo, snap; text has no nodes",
          all(results), "(%s)" % results)
    w.close()

    # 27. pen: click a corner, press and drag a smooth node, close on the first point; node buttons
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    w.set_tool("pen")
    vp = view.viewport()

    def at(x, y):
        return view.mapFromScene(QPointF(x, y))

    def drag(x0, y0, x1, y1):
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at(x0, y0))
        ev = QMouseEvent(QEvent.MouseMove, QPointF(at(x1, y1)), QPointF(vp.mapToGlobal(at(x1, y1))),
                         Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(vp, ev)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(x1, y1))
        app.processEvents()

    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(60, 60))       # corner
    drag(100, 40, 120, 40)                                                 # smooth node, handles 20 mm
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(100, 90))      # corner
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(60, 60))       # first point: close
    app.processEvents()
    pe = w.elements[-1] if w.elements else None
    pen_ok = (pe is not None and pe.shape.kind == "path" and pe.shape.subpaths[0]["closed"]
              and len(pe.shape.subpaths[0]["nodes"]) == 3
              and pe.shape.subpaths[0]["nodes"][1][4] is not None and pe.shape.subpaths[0]["nodes"][0][4] is None)
    w.set_tool("nodes")
    view.select_element(pe)
    view.node_editor.select({(0, 0)})
    w.tool_options.node_action.emit("smooth")
    buttons_ok = pe.shape.subpaths[0]["nodes"][0][4] is not None
    w._update_tool_options(force=True)                                 # rebuild the bar, then select nodes
    try:
        w._node_selection_changed(1)
    except RuntimeError:
        buttons_ok = False
    names = [b.text() for b in w.tool_options.findChildren(QToolButton)]
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, [pe], w.layers)
    data, _folder = _project.read_project(proj)
    back = _project.shape_from_item(data["elements"][0])
    saved_ok = back.kind == "path" and back.subpaths == pe.shape.subpaths
    check("pen: corner, smooth curve by dragging, close; node buttons; saved in projects",
          pen_ok and buttons_ok and len(names) >= 8 and saved_ok, "(%s)" % [pen_ok, buttons_ok, len(names), saved_ok])
    w.close()

    # 28. combine shapes: union, difference (hole), intersection, exclusion
    def two_squares(w):
        for e in list(w.elements):
            w.elements.remove(e)
        w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)    # 40 x 40
        w._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 80), False)    # overlaps 20 x 20
        w.preview.select_element(w.elements[-2:])
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    sizes = {}
    for op in ("union", "difference", "intersection", "exclusion"):
        two_squares(w)
        w.boolean_selected(op)
        e = w.elements[-1]
        sizes[op] = (len(w.elements), round(e.size[0] * 25.4, 3), round(e.size[1] * 25.4, 3),
                     len(e.shape.subpaths), e.shape.kind)
    ok = (sizes["union"][:4] == (1, 60.0, 60.0, 1) and sizes["difference"][:3] == (1, 40.0, 40.0)
          and sizes["intersection"][:4] == (1, 20.0, 20.0, 1) and sizes["exclusion"][1:3] == (60.0, 60.0)
          and all(v[4] == "path" for v in sizes.values()))
    w.undo()
    check("combine shapes: union, difference, intersection, exclusion", ok and len(w.elements) == 2, str(sizes))
    w.close()

    # 28b. Offset tool (right strip): click a shape -> a new outline around it (or inside it);
    # "Offset selected" for shapes selected before; a hole moves the other way
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()
    app.processEvents()

    def click_scene(x, y):
        vp = w.preview.viewport()
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, w.preview.mapFromScene(QPointF(x, y)))
        app.processEvents()
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)      # 40 x 40
    w.tool_actions["offset"].trigger()
    from kerfly.gui import truth as _otruth
    in_strip = w.preview.tool == "offset" and set(_otruth.bar_fields(w.tool_options)) == {
        "offset_distance", "offset_join", "offset_keep"}
    bar_set(w, "offset_distance", 2.0)
    bar_set(w, "offset_join", "miter")
    bar_set(w, "offset_keep", True)
    click_scene(40, 40)
    grown = w.elements[-1]
    out_ok = (len(w.elements) == 2 and grown.shape.kind == "path"
              and (round(grown.size[0] * 25.4, 2), round(grown.size[1] * 25.4, 2)) == (44.0, 44.0)
              and abs(grown.bounds[0] * 25.4 - 18.0) < 0.01)
    bar_set(w, "offset_distance", -5.0)
    bar_set(w, "offset_join", "round")
    bar_set(w, "offset_keep", False)
    w.preview.select_element([w.elements[0]])
    app.processEvents()
    click_bar_button(w, "Offset selected")
    inner = w.elements[0]
    in_ok = len(w.elements) == 2 and (round(inner.size[0] * 25.4, 2), round(inner.size[1] * 25.4, 2)) == (30.0, 30.0)
    w.undo()
    undo_ok = len(w.elements) == 2 and round(w.elements[0].size[0] * 25.4, 2) == 40.0
    # a frame (square with a hole): the outside grows, the hole shrinks
    for e in list(w.elements):
        w.elements.remove(e)
    w.set_tool("select")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    w._preview_drawn("rectangle", QPointF(30, 30), QPointF(50, 50), False)
    w.preview.select_element(w.elements[-2:])
    w.boolean_selected("difference")
    w.set_tool("offset")
    bar_set(w, "offset_distance", 1.0)
    bar_set(w, "offset_join", "miter")
    click_scene(25, 40)                                  # on the frame, not in its hole
    frame = w.elements[-1]
    holes = sorted(round(max(n[0] for n in sp["nodes"]) - min(n[0] for n in sp["nodes"]), 2)
                   for sp in frame.shape.subpaths)
    hole_ok = holes == [18.0, 42.0] and len(w.elements) == 1
    check("Offset tool: in the right strip, click a shape (2 mm out, kept), Offset selected (5 mm in, "
          "replaced), undo, a hole shrinks", in_strip and out_ok and in_ok and undo_ok and hole_ok,
          "(%s)" % [in_strip, out_ok, in_ok, undo_ok, holes])
    w.close()

    # 29. freehand: a circle drawn with the mouse becomes a closed smooth path with few nodes
    import math as _m
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    vp = view.viewport()
    w.set_tool("freehand")
    pts = [(100 + 30 * _m.cos(a / 60.0 * 2 * _m.pi), 100 + 30 * _m.sin(a / 60.0 * 2 * _m.pi)) for a in range(61)]
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(*pts[0])))
    for x, y in pts[1:]:
        q = view.mapFromScene(QPointF(x, y))
        QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(q), QPointF(vp.mapToGlobal(q)),
                                               Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(*pts[-1])))
    app.processEvents()
    fe = w.elements[-1] if w.elements else None
    fh_ok = (fe is not None and fe.shape.kind == "path" and fe.shape.subpaths[0]["closed"]
             and 6 <= len(fe.shape.subpaths[0]["nodes"]) <= 40 and abs(fe.size[0] * 25.4 - 60) < 2.0)
    check("freehand: drawn circle -> closed smooth path", fh_ok,
          "(%s nodes, %.1f mm wide)" % (len(fe.shape.subpaths[0]["nodes"]) if fe else 0, fe.size[0] * 25.4 if fe else 0))
    w.close()

    # 30. ruler: drag between two snapped corners, distance in the status bar
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(40, 40), QPointF(70, 80), False)    # 30 x 40: diagonal 50
    w.set_tool("measure")
    view = w.preview
    vp = view.viewport()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(40.3, 40.2)))
    q = view.mapFromScene(QPointF(69.8, 79.7))
    QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(q), QPointF(vp.mapToGlobal(q)),
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, q)
    msg = w.statusBar().currentMessage()
    check("ruler: snapped corners, 50 mm diagonal", "50.00" in msg or "50,00" in msg, "(%s)" % msg)
    w.close()

    # 31. lines without the outline (the former hatch) from the Fill section of the options bar:
    # its settings appear, only engraved lines, no cut; no separate Hatch section any more
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    bar_set(w, "fill_pattern", "lines")
    bar_set(w, "fill_spacing", 0.5)
    bar_set(w, "fill_outline", False)
    labels = [l.text() for l in w.tool_options.findChildren(QLabel)]
    e = w.selected
    lines_ok = e.design.vector_engrave.ecoords and not e.design.vector_cut.ecoords
    check("fill with lines, no outline (former hatch): settings shown, engraved lines only, no Hatch section",
          lines_ok and "Fill" in labels and "Hatch" not in labels, "(%s)" % labels)
    bar_set(w, "fill_outline", True)                     # back to a plain cut shape for the bridges
    bar_set(w, "fill_pattern", "")
    bar_set(w, "tabs", 2)
    labels = [l.text() for l in w.tool_options.findChildren(QLabel)]
    loops = {r[2] for r in w.selected.design.vector_cut.ecoords}
    check("bridges: set in the options bar, the cut has gaps", len(loops) == 2 and "Bridges" in labels,
          "(%d pieces, %s)" % (len(loops), labels))
    w.close()

    # 32. job simulation: dialog plays, draws on the bed view, seek to the end, closes cleanly
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    w.simulate_job()
    dlg = getattr(w, "_simulation", None)
    played = dlg is not None and dlg.total > 0 and dlg.timer.isActive()
    auto_speed = dlg.speed.currentData() >= 1
    dlg.skip_layer()
    skipped = dlg.time > 0
    dlg.seek(dlg.total)
    drawn = len(dlg.items) >= 2 and auto_speed and skipped
    dlg.close()
    app.processEvents()
    check("simulation: plays, draws the path, closes", played and drawn, "(%.1f s)" % (dlg.total if dlg else 0))
    w.close()

    # 33. opened DXF: double-click only explains; Ungroup splits it; a part can be dragged and node-edited
    w = make_window(grid_mm="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    src = w.elements[0]
    w._edit_nodes_of(src)
    explained = len(w.elements) == 1 and w.preview.tool == "select" and "Ungroup" in w.statusBar().currentMessage()
    w.preview.scene().clearSelection()
    w.ungroup_selected()                                                # nothing selected, one file: that one
    parts = list(w.elements)
    split = len(parts) > 1 and all(e.shape.kind == "path" and not e.group for e in parts)
    w.preview.select_element(parts[0])
    single = w._selection() == [parts[0]]
    x1 = parts[1].x
    w._preview_moved(parts[0], 0.3, 0.0)
    moved_alone = abs(parts[1].x - x1) < 1e-12
    w._edit_nodes_of(parts[0])
    app.processEvents()
    nodes_ok = w.preview.tool == "nodes" and bool(w.preview._node_handles)
    check("opened DXF: Ungroup splits it, a part moves alone, double-click edits its nodes",
          explained and split and single and moved_alone and nodes_ok,
          "(%s)" % [explained, split, single, moved_alone, nodes_ok])
    w.close()

    # 35. element list and bed selection follow each other (one, several, a group)
    w = make_window(grid_mm="0")
    for x0 in (20, 70, 120):
        w._preview_drawn("rectangle", QPointF(x0, 20), QPointF(x0 + 30, 50), False)
    e1, e2, e3 = w.elements
    lst = w.element_list

    def rows():
        return sorted(lst.row(i) for i in lst.selectedItems())
    w.preview.select_element(e2)
    one = rows() == [1]
    w.preview.select_element([e1, e3])
    several = rows() == [0, 2]
    lst.clearSelection()
    lst.item(2).setSelected(True)
    from_list = w.preview.selected_elements() == [e3] and w.selected is e3
    w.preview.select_element([e1, e2])
    w.group_selected()
    lst.clearSelection()
    lst.item(0).setSelected(True)                                       # a group member: the whole group
    group_rows = rows() == [0, 1] and len(w.preview.selected_elements()) == 2
    check("element list <-> bed selection: one, several, from the list, a group",
          one and several and from_list and group_rows, "(%s)" % [one, several, from_list, group_rows])
    w.close()

    # 36. zoom: the wheel cannot zoom out past the whole bed; zooming in works; the bed stays in view
    from PySide6.QtCore import QPoint as _QP
    from PySide6.QtGui import QWheelEvent
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    v = w.preview
    v.fit_all()
    fit = v.transform().m11()

    def wheel(n):
        for _i in range(abs(n)):
            pos = QPointF(v.viewport().rect().center())
            ev = QWheelEvent(pos, QPointF(v.viewport().mapToGlobal(pos.toPoint())), _QP(0, 0),
                             _QP(0, 120 if n > 0 else -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(v.viewport(), ev)
    wheel(-10)
    out_limit = abs(v.transform().m11() - fit) < 1e-6
    anchor = v.mapFromScene(QPointF(60, 40))
    under = v.mapToScene(anchor)
    for _i in range(3):
        ev = QWheelEvent(QPointF(anchor), QPointF(v.viewport().mapToGlobal(anchor)), _QP(0, 0), _QP(0, 120),
                         Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(v.viewport(), ev)
    after = v.mapToScene(anchor)
    zoomed_in = v.transform().m11() > fit * 1.9 and abs(after.x() - under.x()) < 1 and abs(after.y() - under.y()) < 1
    ev = QWheelEvent(QPointF(anchor), QPointF(v.viewport().mapToGlobal(anchor)), _QP(0, 0), _QP(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(v.viewport(), ev)                            # one step out: still about the cursor
    out_pt = v.mapToScene(anchor)
    zoomed_in = zoomed_in and abs(out_pt.x() - under.x()) < 1 and abs(out_pt.y() - under.y()) < 1
    wheel(-10)
    back = abs(v.transform().m11() - fit) < 1e-6 and v._bed_visible()
    check("zoom: not further out than the whole bed, zooms in and out about the cursor", out_limit and zoomed_in and back,
          "(%s)" % [out_limit, zoomed_in, back])
    w.close()

    # 37. a drawn shape can go on any layer of the left panel; its operation follows the layer's kind
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    e = w.selected
    extra = w.add_layer("cut")
    combo = w.layer_assign_box.findChildren(QComboBox)[0]
    names = [combo.itemText(i) for i in range(combo.count())]
    eng = [l for l in w.layers if l.kind == "engrave"][0]
    w._assign_shape_layer(eng.id)
    to_outline = e.shape.operation == "engrave" and bool(e.design.vector_engrave.ecoords) and not e.design.vector_cut.ecoords
    w._assign_shape_layer(extra.id)
    to_extra_cut = e.shape.operation == "cut" and e.layers.get("cut") == extra.id
    w.undo()
    undone = e.shape.operation == "engrave" if e in w.elements else w.elements[-1].shape.operation == "engrave"
    check("shape layer: all layers listed, outline layer makes it an outline, extra cut layer, undo",
          len(names) >= 4 and to_outline and to_extra_cut and undone, "(%s, %s)" % (names, [to_outline, to_extra_cut, undone]))
    w.close()

    # 38. Ungroup an SVG: lines become shapes, the picture splits into its separate parts, same place
    w = make_window(grid_mm="0", use_inkscape="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    src = w.elements[0]
    src.rotation = 0.0
    from kerfly.core.layout import compile_layout as _cl2

    def dark_box(elements):
        d, o = _cl2(elements, passthrough=False)
        im = d.raster.image.convert("L").point(lambda v: 255 if v < 128 else 0)
        l, t, r, b = im.getbbox()
        dpi = d.input_dpi
        return (o[0] + l / dpi, o[1] - t / dpi, o[0] + r / dpi, o[1] - b / dpi)
    before = dark_box([src])
    w.preview.select_element(src)
    w.ungroup_selected()
    pics = [e for e in w.elements if e.shape is None]
    shapes = [e for e in w.elements if e.shape is not None]
    after = dark_box(pics)
    same = max(abs(a - b) for a, b in zip(before, after)) < 0.012          # inches (0.3 mm)
    proj = tempfile.mktemp(suffix=".kerfly")
    w._write_project(proj) if hasattr(w, "_write_project") else None
    check("ungroup SVG: picture split into its parts in the same place, lines into shapes",
          len(pics) == 3 and len(shapes) >= 4 and same, "(%d pictures, %d shapes, %s / %s)"
          % (len(pics), len(shapes), [round(v, 3) for v in before], [round(v, 3) for v in after]))
    w.undo()
    check("ungroup SVG: undo gives the file back", w.elements == [src])
    w.close()

    # 25. groups: select one selects all, move, rotate and duplicate together, saved, ungroup, undo
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    for x0 in (20, 60, 100):
        w._preview_drawn("rectangle", QPointF(x0, 20), QPointF(x0 + 20, 40), False)
    a, b, c = w.elements[-3:]
    w.preview.select_element([a, b])
    w.group_selected()
    grouped = a.group and a.group == b.group and not c.group
    w.preview.select_element(a)                                         # one click selects the group
    whole = set(map(id, w.preview.selected_elements())) == {id(a), id(b)}
    bx, by = b.x, b.y
    w._preview_moved(a, 0.5, -0.25)
    moved = abs(b.x - bx - 0.5) < 1e-9 and abs(b.y - by + 0.25) < 1e-9
    w.preview.select_element(a)
    w.rotate_selected(90)
    turned = a.rotation == 90 and b.rotation == 90 and abs(a.centre[0] - b.centre[0]) < 1e-9
    w.preview.select_element(a)
    n = len(w.elements)
    w.duplicate_selected()
    copies = w.elements[n:]
    dup = len(copies) == 2 and copies[0].group == copies[1].group and copies[0].group != a.group
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, w.elements, w.layers)
    data, _folder = _project.read_project(proj)
    saved = [it.get("group") for it in data["elements"]] == [e.group for e in w.elements]
    w.preview.select_element(a)
    w.ungroup_selected()
    ungrouped = not a.group and not b.group and copies[0].group
    w.undo()
    regrouped = a.group and a.group == b.group
    check("groups: select, move, rotate, duplicate, save, ungroup, undo",
          grouped and whole and moved and turned and dup and saved and ungrouped and regrouped,
          "(%s)" % [grouped, whole, moved, turned, dup, saved, ungrouped, regrouped])
    w.close()

    # 26. break apart an opened file: one polyline per path, same place, grouped; image part stays; undo
    w = make_window(grid_mm="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    src = w.elements[0]
    src.rotation = 30.0
    w._layout_changed()
    before = w.preview._items[0].snap_shape()
    pts_before = sorted((round(x, 3), round(y, 3)) for x, y, k in before.points if k == "corner")[:6]
    from kerfly.core.layout import compile_layout as _cl
    def bed_points(elements):
        d, o = _cl(elements)
        return sorted({(round(r[0] + o[0], 4), round(r[1] + o[1], 4)) for r in d.vector_cut.ecoords + d.vector_engrave.ecoords})
    ref_pts = bed_points([src])                                 # rotated: coordinates on the bed
    w.preview.select_element(src)
    w.ungroup_selected()                                                # an opened file splits into shapes
    parts = list(w.elements)
    one_group = len(parts) > 1 and all(not e.group for e in parts) and all(e.shape.kind == "path" for e in parts)
    curved = any(n[4] is not None for e in parts for sp in e.shape.subpaths for n in sp["nodes"])   # real arcs
    corners = set()
    for item in w.preview._items:
        corners |= {(round(x, 3), round(y, 3)) for x, y, k in item.snap_shape().points if k == "corner"}
    new_pts = bed_points(parts)

    def box(pts):
        return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
    same_place = max(abs(a - b) for a, b in zip(box(ref_pts), box(new_pts))) < 0.003
    w.undo()
    back = len(w.elements) == 1 and w.elements[0] is src
    check("ungroup a file: separate curves in the same place, undo", one_group and curved and same_place and back,
          "(%d parts)" % len(parts))

    # 20. diagnostic log and report
    from kerfly.core import diag as _diag
    _diag.setup("test")
    _diag.log.info("laser: test entry for the report")
    report = tempfile.mktemp(suffix=".txt")
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (report, ""))
    w.save_report()
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""
    check("diagnostic report: checks, settings and log", "Kerfly diagnostic report" in text
          and "== Checks" in text and "board_name = " in text and "laser: test entry for the report" in text,
          "(%d bytes)" % len(text))

    # 39. a status message repeated by the laser library is logged once (it filled the log on the
    # first laser test); progress percentages fill the progress bar; an interrupted job warns
    before = _diag.read_log().count("Waiting for the laser to finish.")
    for _i in range(5):
        w.status("Waiting for the laser to finish.")
    after = _diag.read_log().count("Waiting for the laser to finish.")
    check("repeated status logged once", after - before == 1, "(%d new lines)" % (after - before))
    w.set_busy(True)
    w.status("Sending Data to Laser = 42.0%")
    pct = w.progress.value()
    w.status("Creating Scan Lines: 7.5 %")
    pct2 = w.progress.value()
    busy_shown = not w.progress.isHidden() and not w.busy_indicator.isHidden()
    w.set_busy(False)
    check("progress bar follows the percentages", pct == 42 and pct2 == 7 and busy_shown
          and w.busy_indicator.isHidden(), "(%s, %s)" % (pct, pct2))
    from kerfly.gui.worker import LayersJobWorker as _LJW
    for sent in (False, True):
        wk = _LJW(w.elements, w.layers, w.job_settings(), {}, laser=w.laser)
        wk.sending = sent
        w.worker = wk
        w._job_finished(False, "Action Stopped by User.")
        msg = w.statusBar().currentMessage()
        if sent:
            check("stopped job: head position unknown, press Home", "Home" in msg, "(%s)" % msg)
        else:
            check("job refused before sending: no position warning", "Home" not in msg, "(%s)" % msg)

    # 40. Help → Report a problem: saves the report, opens the laser problem form with the version filled in
    from PySide6.QtGui import QDesktopServices as _QDS
    opened = []
    _orig_open, _orig_exec = _QDS.openUrl, QMessageBox.exec
    _QDS.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)

    def _click(box, wanted=(_("The laser did something wrong"), "Close", _("Close"))):
        for b in box.buttons():
            if b.text().replace("&", "") in wanted:
                b.click()
                break
        return 0
    QMessageBox.exec = _click
    try:
        if os.path.exists(report):
            os.remove(report)
        w.report_problem()
    finally:
        _QDS.openUrl, QMessageBox.exec = _orig_open, _orig_exec
    url = opened[0] if opened else ""
    check("report a problem: report saved, laser form opened with version and board",
          os.path.exists(report) and "issues/new?template=laser_problem.yml" in url
          and "version=" + __import__("kerfly").__version__ in url and "board=" in url, "(%s)" % url[:90])
    check("report a problem: in the Help menu and the toolbar",
          w.act_report_problem in [a for m in w.menuBar().actions() for a in m.menu().actions()]
          and any(getattr(b, "defaultAction", lambda: None)() is w.act_report_problem
                  for b in w.findChildren(QToolButton)))

    # 44. Fill tool: click a closed shape to fill it with a pattern (one undo step), the outline
    # stays a cut; the options bar shows the patterns; an opened file must be ungrouped first
    from PySide6.QtCore import QPointF as _QPointF
    from kerfly.core.shapes import ShapeSpec as _Spec
    w3 = make_window(grid_mm="0")
    w3._add_drawn_element(_Spec(kind="ellipse", width=60, height=40, operation="cut"), "ellipse", 20, 20)
    w3._add_drawn_element(_Spec(kind="rectangle", width=30, height=30, operation="cut"), "rectangle", 120, 20)
    shape, square = w3.elements[0], w3.elements[1]       # the square is selected (just drawn)
    w3.set_tool("fill")
    combos = [c for c in w3.tool_options.findChildren(QComboBox) if c.findData("honeycomb") >= 0]
    if combos:
        combos[0].setCurrentIndex(combos[0].findData("honeycomb"))
        combos[0].activated.emit(combos[0].currentIndex())          # as a mouse choice does
    selected_got_it = square.shape.fill_pattern == "honeycomb" and shape.shape.fill_pattern == ""
    undo0 = len(w3._undo)
    w3._fill_clicked(_QPointF(50, 40))                    # inside the ellipse
    filled = shape.shape.fill_pattern == "honeycomb" and bool(shape.design.vector_cut.ecoords) \
        and len(shape.design.vector_engrave.ecoords) > 50 and len(w3._undo) == undo0 + 1
    w3.undo()
    shape = w3.elements[0]
    undone = shape.shape.fill_pattern == "" and not shape.design.vector_engrave.ecoords
    w3.load_design(os.path.join(FIX, "shapes.dxf"), add=True)
    file_el = [e for e in w3.elements if e.shape is None]
    if file_el:
        b = file_el[0].bounds
        w3._fill_clicked(_QPointF((b[0] + b[1]) / 2 * 25.4, -(b[2] + b[3]) / 2 * 25.4))
    msg = w3.statusBar().currentMessage()
    check("fill tool: patterns, click fills (one undo step), outline stays, files need Ungroup",
          bool(combos) and selected_got_it and filled and undone and bool(file_el) and "Ungroup" in msg,
          "(%s)" % ([bool(combos), selected_got_it, filled, undone, msg[:40]],))
    w3._dirty = False
    w3.close()

    # 45. order of elements = order of the job (top of the list first): down / up one place, to the
    # end / start, a message at the end, undo, toolbar
    w4 = make_window(grid_mm="0")
    for i in range(4):
        w4._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10 + 30 * i, 10)
    a, b, c, d = w4.elements
    select(w4, b)
    w4.reorder_selected("down")
    step = w4.elements == [a, c, b, d]
    w4.reorder_selected("last")
    last = w4.elements == [a, c, d, b]
    w4.reorder_selected("down")
    already = w4.statusBar().currentMessage() == _("Already at the end of the list.") \
        and w4.elements == [a, c, d, b]
    w4.reorder_selected("first")
    first = w4.elements == [b, a, c, d]
    w4.reorder_selected("up")
    already_top = w4.statusBar().currentMessage() == _("Already at the start of the list.")
    w4.undo()
    undone = w4.elements == [a, c, d, b]
    on_bar = any(getattr(t, "defaultAction", lambda: None)() is w4.act_order["up"]
                 for t in w4.findChildren(QToolButton))
    beside_list = any(b.defaultAction() is w4.act_order["up"] and w4.element_list_box.isAncestorOf(b)
                      for b in w4.findChildren(QToolButton))
    on_bar = on_bar and beside_list
    check("element order: down, to the end, already at the end, to the start, undo, buttons beside the list",
          step and last and already and first and already_top and undone and on_bar,
          "(%s)" % ([step, last, already, first, already_top, undone, on_bar],))
    w4._dirty = False
    w4.close()

    # 46. text on a path: centred above a line, stays in place when edited and after moving it,
    # other side below the line, back to straight text; saved in projects
    from kerfly.gui.text_shapes import update_text_spec as _uts
    from kerfly.core import project as _project
    w5 = make_window(grid_mm="0", follow_head="0")
    w5._add_drawn_element(_Spec(kind="line", width=100, height=0, operation="cut"), "line", 20, 60)
    t = _Spec(kind="text", text="KERFLY", font_size=10, operation="engrave")
    _uts(t)
    w5._add_drawn_element(t, "text", 10, 150)
    guide, text = w5.elements
    select(w5, guide, text)
    w5.put_text_on_path()
    b = [v * 25.4 for v in text.bounds]
    centred = abs((b[0] + b[1]) / 2 - 70.0) < 2.0 and abs(b[2] + 60.0) < 0.6 and b[3] > -60.0
    w5.sel_fields["x"].setValue(w5.sel_fields["x"].value() + 10)   # moved 10 mm right, then edited
    bar_set(w5, "text", "KERFLY!")
    b2 = [v * 25.4 for v in text.bounds]
    kept = abs(b2[0] - (b[0] + 10.0)) < 0.6 and abs(b2[2] - b[2]) < 0.6
    bar_set(w5, "text_path_flip", True)
    below = text.bounds[3] * 25.4 <= -60.0 + 0.6
    saved = _project._shape_from_dict(_project._shape_to_dict(text.shape))
    in_project = saved.text_path_flip and len(saved.text_path) == len(text.shape.text_path)
    click_bar_button(w5, _("Straight text"))
    # height of a 10 mm text in whatever font the system has (Windows has no DejaVu Sans)
    straight = not text.shape.text_path and 4.0 < text.size[1] * 25.4 < 14.0
    # the Text on a path tool: click near the line -> a new text on it; dragging slides it
    # along the line (it stays on it); spacing makes it longer; distance lifts it off the line
    select(w5)                                              # no text selected: the tool makes a new one
    w5.set_tool("textpath")
    tool_bar_text = w5._options_target == "textpath"
    w5.shape_defaults["textpath"].text = "ABC"
    n0 = len(w5.elements)
    w5._shape_picked("textpath", _QPointF(70, 61))           # 1 mm below the line
    t2 = w5.elements[-1]
    made = len(w5.elements) == n0 + 1 and t2.shape.text == "ABC" and bool(t2.shape.text_path) \
        and w5.preview.tool == "select"
    left0 = t2.bounds[0]
    select(w5, t2)
    w5._preview_moved(t2, 15 / 25.4, 8 / 25.4)               # drag right (and a bit up)
    slid = abs((t2.bounds[0] - left0) * 25.4 - 15.0) < 0.6 and abs(t2.bounds[2] * 25.4 + 60.0) < 0.6
    w_before = t2.size[0]
    bar_set(w5, "text_spacing", 2.0)
    bar_set(w5, "text_path_distance", 3.0)
    spaced = t2.size[0] * 25.4 > w_before * 25.4 + 3.5 and abs(t2.bounds[2] * 25.4 + 57.0) < 0.6
    check("text on a path tool: click puts a text on the line, drag slides along it, spacing, distance",
          tool_bar_text and made and slid and spaced, "(%s)" % ([tool_bar_text, made, slid, spaced],))
    # a selected text is moved onto the clicked shape: no second copy stays behind
    t3 = _Spec(kind="text", text="MOVE ME", font_size=8, operation="engrave")
    _uts(t3)
    w5._add_drawn_element(t3, "text", 20, 120)               # drawn: selected
    plain_text = w5.elements[-1]
    n1 = len(w5.elements)
    w5.set_tool("textpath")
    shows_it = w5._options_element is plain_text
    w5._shape_picked("textpath", _QPointF(30, 60))
    moved_on = len(w5.elements) == n1 and bool(plain_text.shape.text_path) \
        and abs(plain_text.bounds[2] * 25.4 + 60.0) < 0.6
    check("text on a path tool: the selected text goes onto the shape (no copy left)", shows_it and moved_on,
          "(%s)" % ([shows_it, moved_on, len(w5.elements) - n1],))

    # changing a text on a path in the options bar, several times in a row (the bar kept an old copy
    # of the path, so every change moved the text further: +10, +20, +30 mm; the font jumped too)
    from PySide6.QtGui import QFont as _QFont
    from PySide6.QtWidgets import QDoubleSpinBox as _QDSB
    select(w5, t2)
    off = [sp for sp in w5.tool_options.findChildren(_QDSB) if sp.toolTip().startswith(_("Position along the path"))]
    lefts = []
    for _i in range(3):
        off[0].setValue(off[0].value() + 10.0)
        lefts.append(t2.bounds[0] * 25.4)
    steps_ok = all(abs((b - a) - 10.0) < 0.3 for a, b in zip(lefts, lefts[1:]))
    width0, left0 = t2.size[0], t2.bounds[0]
    before_font = t2.shape.font_family
    # another font, set through the options bar the way its font list does it (on the Windows CI
    # the font list can be empty without a screen, so the family name comes from the font database)
    from PySide6.QtGui import QFontDatabase as _QFDB
    other = next((f for f in _QFDB.families() if f != before_font and "Symbol" not in f
                  and not f.startswith(("Wingdings", "Webdings", "Marlett"))), "Arial")
    bar_set(w5, "font_family", other)
    font_ok = t2.shape.font_family != before_font and abs(t2.bounds[0] - left0) * 25.4 < 1.0 \
        and abs(t2.bounds[2] * 25.4 + 57.0) < 0.6
    check("text on a path: changes in the options bar move it exactly, the font changes in place",
          bool(off) and steps_ok and font_ok, "(steps %s, font %s)" % ([round(b - a, 2) for a, b in zip(lefts, lefts[1:])],
                                                                      t2.shape.font_family))

    # the options of a selected text (all its sections) scroll instead of widening the window
    select(w5, text)
    narrow = w5.minimumSizeHint().width() < 1100
    check("text on a path: centred, kept when edited / moved, other side, saved, straight again",
          centred and kept and below and in_project and straight,
          "(%s)" % ([centred, kept, below, in_project, straight],))
    check("options bar scrolls: a selected text does not make the window wider",
          narrow, "(minimum width %d px)" % w5.minimumSizeHint().width())
    w5._dirty = False
    w5.close()

    # 47. Living hinge tool: click a closed shape -> cuts inside (one undo step), the Living hinge
    # section shows on that shape; a text gets none
    w6 = make_window(grid_mm="0")
    w6._add_drawn_element(_Spec(kind="rectangle", width=120, height=60, operation="cut"), "rectangle", 20, 20)
    box = w6.elements[0]
    select(w6)
    w6.set_tool("hinge")
    tool_bar = w6._options_target == "hinge"
    plain_n = len(box.design.vector_cut.ecoords)
    u0 = len(w6._undo)
    w6._shape_picked("hinge", _QPointF(80, 50))
    cut_in = box.shape.hinge_pattern == "straight" and len(box.design.vector_cut.ecoords) > plain_n * 20 \
        and len(w6._undo) == u0 + 1
    w6.set_tool("select")
    select(w6, box)
    section = any(c.findData("zigzag") >= 0 for c in w6.tool_options.findChildren(QComboBox))
    w6.undo()
    undone = not w6.elements[0].shape.hinge_pattern
    check("living hinge tool: click cuts a hinge (one undo step), its section on the shape, undo",
          tool_bar and cut_in and section and undone, "(%s)" % ([tool_bar, cut_in, section, undone],))
    w6._dirty = False
    w6.close()

    # 48. Fill tool with several shapes selected: the bar shows what they have ("no pattern", not the
    # pattern a click gives), every choice reaches all of them (the selection was lost after the
    # first change), and a number changed under "no pattern" fills nothing
    w7 = make_window(grid_mm="0")
    for i in range(4):
        w7._add_drawn_element(_Spec(kind="rectangle", width=30, height=30, operation="cut"), "rectangle",
                              10 + 40 * i, 10)
    boxes = list(w7.elements)
    select(w7, *boxes[:3])
    w7.set_tool("fill")
    combo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("waves") >= 0][0]
    shows_none = combo.currentData() == ""
    bar_set(w7, "fill_spacing", 3.0)                       # under "no pattern": nothing is filled
    none_kept = all(not e.shape.fill_pattern for e in w7.elements) and w7.fill_defaults.fill_pattern == "lines"
    seen = []
    for code in ("lines", "waves", "honeycomb"):
        bar_set(w7, "fill_pattern", code)
        seen.append([e.shape.fill_pattern for e in w7.elements[:3]])
    multi_ok = seen == [["lines"] * 3, ["waves"] * 3, ["honeycomb"] * 3]
    w7._fill_clicked(QPointF(10 + 120 + 15, 25))           # a click on the fourth gives the last choice
    clicked_ok = w7.elements[3].shape.fill_pattern == "honeycomb" and w7.elements[3].shape.fill_spacing == 3.0
    select(w7, *boxes[:3])
    w7.set_tool("hinge")
    hcombo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("wave") >= 0][0]
    hinge_none = hcombo.currentData() == ""
    # a selected shape clicked with the tool: the bar shows what it got (it stayed "no hinge")
    w7.set_tool("select")
    select(w7, boxes[0])
    w7.set_tool("hinge")
    w7._hinge_clicked(QPointF(25, 25))
    hcombo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("wave") >= 0][0]
    hinge_none = hinge_none and boxes[0].shape.hinge_pattern == "straight" and hcombo.currentData() == "straight"
    check("fill tool with several shapes: shows \"no pattern\", each choice reaches all of them",
          shows_none and none_kept and multi_ok and clicked_ok and hinge_none,
          "(none %s, kept %s, %s, click %s, hinge %s)" % (shows_none, none_kept, seen, clicked_ok, hinge_none))
    w7._dirty = False
    w7.close()

    # 51. the "window tells the truth" checks find what they should: a field not refreshed, an element
    # drawn elsewhere, a stale list row, a wrong layer list, a missing field; and a saved and reopened
    # project has the same state
    from kerfly.gui import truth as _truth
    w10 = make_window(grid_mm="0")
    w10._add_drawn_element(_Spec(kind="rectangle", width=30, height=20, operation="cut"), "rectangle", 10, 10)
    w10._add_drawn_element(_Spec(kind="ellipse", width=30, height=20, operation="cut"), "ellipse", 60, 10)
    r10, e10 = w10.elements
    select(w10, r10)
    clean = _truth.check_window(w10) == []
    found = {}
    spec = r10.shape.copy()                               # data changed behind the bar's back
    spec.tabs = 3
    r10.shape = spec
    found["bar"] = any("'tabs' shows 0, should be 3" in p for p in _truth.check_window(w10))
    spec.tabs = 0
    r10.x += 5 / 25.4                                     # moved without redrawing
    found["bed"] = any("bed view: Rectangle" in p for p in _truth.check_window(w10))
    found["fields"] = any("position fields: x" in p for p in _truth.check_window(w10))
    r10.x -= 5 / 25.4
    e10.visible = False                                   # left out of the job without the list knowing
    found["list"] = any("element list row 2" in p and "tick" in p for p in _truth.check_window(w10))
    e10.visible = True
    r10.layers["cut"] = w10.add_layer("cut").id           # the Layer list above the bed not updated
    w10.layer_assign_box.findChildren(QComboBox)[0].blockSignals(True)
    w10.layer_assign_box.findChildren(QComboBox)[0].setCurrentIndex(0)
    found["layer"] = any("layer choice for Rectangle" in p for p in _truth.check_window(w10))
    w10.refresh_preview()
    for f in w10.tool_options.findChildren(QWidget):     # a field gone from the bar
        if f.property("spec_attr") == "corner_radius":
            f.hide()
    found["missing"] = any("'corner_radius' is missing" in p for p in _truth.check_window(w10))
    w10._update_tool_options(force=True)
    before = _truth.state(w10)
    path = tempfile.mktemp(suffix=".kerfly")
    w10._write_project(path)
    w11 = make_window(grid_mm="0")
    w11.open_project(path)
    os.remove(path)
    same = _truth.difference(before, _truth.state(w11)) == ""
    check("truth checks: a clean window passes, each kind of wrong display is found, reopened project same",
          clean and all(found.values()) and same, "(%s, same %s)" % (found, same))
    for win in (w10, w11):
        win._dirty = False
        win.close()

    # 52. grid, snapping and "design follows the head" are remembered for the next start at once
    # (without "Save settings as default"); switching the grid on again uses the last size; the
    # Settings dialog (View tab) changes them too
    from kerfly.gui import viewstate as _viewstate
    v1 = make_window(grid_mm="0")
    v1.remember_geometry = True
    v1.set_grid(2)
    v1.toggle_snap(False)
    v1.act_snap.setChecked(False)
    v1.act_snap_objects.trigger()                           # off
    v1.act_follow_head.trigger()                            # on
    grid_off = v1.values["grid_mm"] == "0"
    v1._dirty = False
    v1.close()
    vals = _viewstate.load(dict(config.DEFAULT_VALUES))
    v2 = MainWindow(vals)
    OPEN_WINDOWS.append(v2)
    v2.remember_geometry = True
    remembered = (not v2.act_snap.isChecked() and not v2.act_snap_objects.isChecked()
                  and v2.act_follow_head.isChecked())
    v2.act_snap.trigger()                                    # grid on again: the last size
    last_size = v2._grid_mm() == 2.0
    v2.values["grid_mm"] = "10"                              # as the Settings dialog sets it
    v2.values["snap_objects"] = "1"
    v2._sync_view_actions()
    from_dialog = v2.act_snap.isChecked() and v2.act_snap_objects.isChecked() \
        and _viewstate.load({})["grid_mm"] in ("10", "10.0")
    v2._dirty = False
    OPEN_WINDOWS.remove(v2)
    v2.close()
    check("view settings remembered at once (grid on/off and size, snapping, follow head), Settings tab",
          grid_off and remembered and last_size and from_dialog,
          "(%s)" % ([grid_off, remembered, last_size, from_dialog],))

    # 52b. the language chosen in Settings is kept for the next start at once (it was lost unless the
    # settings were saved as default, so the new language never came after a restart)
    from kerfly.gui import settings_dialog as _sd
    lw = make_window(grid_mm="0")
    lw.remember_geometry = True
    _orig_exec, _orig_info = _sd.SettingsDialog.exec, QMessageBox.information

    def _pick_german(dlg):
        combo = next(c for c in dlg.findChildren(QComboBox) if c.findData("de") >= 0 and c.findData("") >= 0)
        combo.setCurrentIndex(combo.findData("de"))
        return True
    told = []
    _sd.SettingsDialog.exec = _pick_german
    QMessageBox.information = staticmethod(lambda *a, **k: told.append(a[2] if len(a) > 2 else ""))
    try:
        lw.edit_settings()
    finally:
        _sd.SettingsDialog.exec, QMessageBox.information = _orig_exec, _orig_info
    # the next start: the settings file (never saved here) and then window.ini
    next_start = _viewstate.load(config.load_user_settings())
    lang_ok = lw.values.get("language") == "de" and next_start.get("language") == "de" and bool(told)
    lw.values["language"] = ""                               # back to the system language
    lw._remember_view()
    lang_back = _viewstate.load({}).get("language") == ""
    lw._dirty = False
    lw.close()
    check("language from Settings is kept for the next start without Save settings as default",
          lang_ok and lang_back, "(%s)" % ([lang_ok, lang_back, next_start.get("language")],))

    # 52c. small screens (1366 x 768): the wheel changes a number field only after it was clicked
    # (scrolling down to Start changed the layer speeds on the way, a user's report); Start, Pause
    # and Stop stay visible below the scrolling panel
    from PySide6.QtCore import QPoint as _QPoint
    from PySide6.QtGui import QWheelEvent as _QWheelEvent
    sw = make_window(grid_mm="0")
    sw.resize(1366, 700)
    sw.show()
    sw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    app.processEvents()
    speed = next(r["speed"] for r in sw.layers_panel.rows.values() if "speed" in r)
    bar = sw.panel_scroll.verticalScrollBar()

    def _wheel(widget):
        pos = QPointF(widget.rect().center())
        QApplication.sendEvent(widget, _QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), _QPoint(0, 0),
                                                    _QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase,
                                                    False))
        app.processEvents()
    bar.setValue(0)
    before = speed.value()
    _wheel(speed)
    untouched = speed.value() == before and (bar.maximum() == 0 or bar.value() > 0)
    sw.activateWindow()
    app.processEvents()
    speed.setFocus()
    app.processEvents()
    _wheel(speed)
    clicked = speed.value() != before
    pinned = not sw.panel_scroll.isAncestorOf(sw.btn_start) and sw.btn_start.isVisible()
    check("wheel over a number field not clicked scrolls the panel; clicked, it changes the value; Start "
          "stays below the panel", untouched and clicked and pinned,
          "(%s)" % [untouched, clicked, pinned, bar.value(), bar.maximum()])
    sw._dirty = False
    sw.close()

    # 52d. new versions: a bar above the bed with a link to the release; skipping a version; the
    # manual check says when there is nothing new; switched off in Settings: no check at start
    from kerfly.core import updates as _upd
    from PySide6.QtGui import QDesktopServices
    uw = make_window(grid_mm="0")
    uw.remember_geometry = True
    uw.show()

    def _answer(version):
        return lambda current, timeout=6.0: _upd.Release(version, "https://github.com/cyryllo/Kerfly/releases/tag/v"
                                                         + version)

    def _run_check(**kw):
        uw.check_for_updates(**kw)
        uw._update_check.wait(5000)
        for _i in range(5):
            app.processEvents()
    _run_check(manual=True, fetch=_answer("99.0"))
    shown = uw.update_bar.isVisible() and "99.0" in uw.update_bar.text.text()
    opened = []
    _orig_open = QDesktopServices.openUrl
    QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
    try:
        uw.update_bar.open_button.click()
    finally:
        QDesktopServices.openUrl = _orig_open
    linked = opened == ["https://github.com/cyryllo/Kerfly/releases/tag/v99.0"]
    uw.update_bar.skip_button.click()
    skipped = not uw.update_bar.isVisible() and uw.values.get("update_skip") == "99.0"
    _run_check(manual=False, fetch=_answer("99.0"))
    not_again = not uw.update_bar.isVisible()
    from kerfly import __version__ as _kv
    _run_check(manual=True, fetch=_answer(_kv))
    newest = _kv in uw.statusBar().currentMessage() and not uw.update_bar.isVisible()

    def _offline(current, timeout=6.0):
        raise OSError("no internet")
    _run_check(manual=True, fetch=_offline)
    offline = "no internet" in uw.statusBar().currentMessage()
    asked = []
    _orig_check = uw.check_for_updates
    uw.check_for_updates = lambda **kw: asked.append(kw)
    uw.values["check_updates"], uw.values["update_last"] = "0", "0"
    uw.check_updates_on_start()
    off_ok = asked == []
    uw.values["check_updates"] = "1"
    uw.check_updates_on_start()
    on_ok = asked == [{"manual": False}]
    uw.check_for_updates = _orig_check
    check("new versions: bar with a link to the release, skip a version, nothing new / offline said, "
          "off in Settings", shown and linked and skipped and not_again and newest and offline and off_ok and on_ok,
          "(%s)" % [shown, linked, skipped, not_again, newest, offline, off_ok, on_ok])
    uw.values["check_updates"], uw.values["update_skip"] = "1", ""
    uw._dirty = False
    uw.close()

    # 52e. clipboard as in Inkscape: copy / paste (a new group, 5 mm further when the mouse is not on
    # the bed), paste in place, cut + undo, select all, Esc, layers by name; Ctrl+C in a text field
    # copies the text, not the elements
    from PySide6.QtTest import QTest as _QT
    from PySide6.QtWidgets import QLineEdit as _QLE
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor
    cw = make_window(grid_mm="0")
    cw.resize(1200, 800)
    cw.show()
    app.processEvents()
    cw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    cw._preview_drawn("ellipse", QPointF(80, 20), QPointF(120, 50), False)
    ca, cb = cw.elements
    cw.preview.select_element([ca, cb])
    cw.group_selected()
    from kerfly.core.layers import Layer as _Layer
    second = _Layer("cut", name="Cut 2", color="#2e7d32", speed=5.0)
    cw.layers.append(second)
    cb.layers = {"cut": second.id}
    cw.preview.select_element([ca])
    app.processEvents()
    QCursor.setPos(cw.mapToGlobal(QPoint(5, 5)))            # not over the bed
    cw.act_copy.trigger()
    cw.act_paste.trigger()
    p1, p2 = cw.elements[2], cw.elements[3]
    pasted = (len(cw.elements) == 4 and p1.group and p1.group == p2.group and p1.group != ca.group
              and abs((p1.x - ca.x) * 25.4 - 5) < 1e-6 and p2.layers.get("cut") == second.id)
    cw.act_paste_in_place.trigger()
    in_place = len(cw.elements) == 6 and abs(cw.elements[4].x - ca.x) < 1e-9
    cw.act_select_all.trigger()
    app.processEvents()
    all_sel = len(cw.preview.selected_elements()) == 6
    cw.preview.setFocus()
    _QT.keyClick(cw.preview.viewport(), Qt.Key_Escape)
    app.processEvents()
    esc = cw.preview.selected_elements() == []
    cw.preview.select_element([cw.elements[-1]])
    cw.act_cut.trigger()
    cut_ok = len(cw.elements) == 4
    cw.undo()
    undo_ok = len(cw.elements) == 6
    cw.layers.remove(second)                                # its layer gone: the copy goes to the cut layer
    cw.act_paste.trigger()
    no_layer = "cut" not in cw.elements[-1].layers
    field = _QLE("text")
    field.setParent(cw)
    field.show()
    field.setFocus()
    field.selectAll()
    app.processEvents()
    before = cw._clipboard
    cw.preview.select_element([ca])
    field.setFocus()
    app.processEvents()
    _QT.keyClick(field, Qt.Key_C, Qt.ControlModifier)
    text_only = cw._clipboard is before
    check("clipboard: copy and paste (new group, layers by name), paste in place, cut + undo, select all, "
          "Esc, Ctrl+C in a text field", pasted and in_place and all_sel and esc and cut_ok and undo_ok and no_layer
          and text_only, "(%s)" % [pasted, in_place, all_sel, esc, cut_ok, undo_ok, no_layer, text_only])
    cw._dirty = False
    cw.close()

    # 52f. right-click menu: a right click without moving opens it (a right drag pans); on an element
    # it selects it and offers its commands, Layer moves all selected elements at once; on the empty bed:
    # Move the head here (greyed out without the laser), Paste, Select all
    rw = make_window(grid_mm="0")
    rw.resize(1200, 800)
    rw.show()
    for _settle in range(5):
        app.processEvents()
    rw.preview.fit_all()
    app.processEvents()
    rw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    rw._preview_drawn("ellipse", QPointF(80, 20), QPointF(120, 50), False)
    r1, r2 = rw.elements
    from kerfly.core.layers import Layer as _Layer2, layer_of as _layer_of
    cut2 = _Layer2("cut", name="Cut 2", color="#2e7d32", speed=5.0)
    rw.layers.append(cut2)
    rvp = rw.preview.viewport()

    def _rclick(x, y):
        pos = rw.preview.mapFromScene(QPointF(x, y))
        QTest.mouseClick(rvp, Qt.RightButton, Qt.NoModifier, pos)
        for _i in range(3):
            app.processEvents()
        return rw._context_menu

    menu = _rclick(40, 40)
    texts = [a.text() for a in menu.actions()]
    on_element = (menu.isVisible() and rw.preview.selected_elements() == [r1] and rw.act_copy in menu.actions()
                  and _("Combine shapes") not in texts)
    menu.close()
    rw.preview.select_element([r1, r2])
    menu = _rclick(40, 40)                                 # on a selected element: the selection stays
    kept = len(rw.preview.selected_elements()) == 2 and _("Combine shapes") in [a.text() for a in menu.actions()]
    layer_menu = next(a.menu() for a in menu.actions() if a.menu() and a.menu().objectName() == "layer_submenu")
    next(a for a in layer_menu.actions() if a.text() == "Cut 2" and not a.isSeparator()).trigger()
    both = _layer_of(r1, "cut", rw.layers) is cut2 and _layer_of(r2, "cut", rw.layers) is cut2
    rw.undo()
    one_step = _layer_of(r1, "cut", rw.layers) is not cut2 and _layer_of(r2, "cut", rw.layers) is not cut2
    menu.close()
    menu = _rclick(250, 180)
    empty_texts = [a.text() for a in menu.actions()]
    here = next(a for a in menu.actions() if a.text() == _("Move the head here"))
    empty = rw.act_paste in menu.actions() and rw.act_select_all in menu.actions() and not here.isEnabled()
    menu.close()
    # a right drag pans and opens nothing
    rw._context_menu = None
    p0 = rw.preview.mapFromScene(QPointF(150, 150))
    QTest.mousePress(rvp, Qt.RightButton, Qt.NoModifier, p0)
    QApplication.sendEvent(rvp, QMouseEvent(QEvent.MouseMove, QPointF(p0 + QPoint(60, 40)),
                                            QPointF(rvp.mapToGlobal(p0 + QPoint(60, 40))), Qt.NoButton,
                                            Qt.RightButton, Qt.NoModifier))
    QTest.mouseRelease(rvp, Qt.RightButton, Qt.NoModifier, p0 + QPoint(60, 40))
    app.processEvents()
    drag_no_menu = rw._context_menu is None
    check("right-click menu: element (selected, its commands), Layer moves all selected in one step, empty bed, "
          "a right drag only pans", on_element and kept and both and one_step and empty and drag_no_menu,
          "(%s %s)" % ([on_element, kept, both, one_step, empty, drag_no_menu], empty_texts))
    rw._dirty = False
    rw.close()

    # 52g. Engrave / Outline / Cut only: hidden by default (Settings → View), below the scrolling panel
    # with Start, greyed out without a ticked layer of that kind that has something on it
    kw_ = make_window(grid_mm="0")
    hidden = not kw_.kind_row.isVisibleTo(kw_)
    kw_.values["kind_buttons"] = "1"
    kw_.kind_row.setVisible(True)
    kw_._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)       # a cut shape
    app.processEvents()
    states = {k: a.isEnabled() for k, a in kw_.act_run_kind.items()}
    pinned_k = not kw_.panel_scroll.isAncestorOf(kw_.kind_row)
    cut_layer = [l for l in kw_.layers if l.kind == "cut"][0]
    cut_layer.enabled = False
    kw_._update_bed_check()
    unticked = not kw_.act_run_kind["cut"].isEnabled()
    check("Engrave / Outline / Cut only: hidden by default, pinned with Start, greyed out without data",
          hidden and states == {"raster": False, "engrave": False, "cut": True} and pinned_k and unticked,
          "(%s)" % [hidden, states, pinned_k, unticked])
    kw_._dirty = False
    kw_.close()

    # 53. Linux: connecting fails for want of permission -> Kerfly offers the USB rule (pkexec); with
    # a rule already there, Laser → Allow USB access only says to plug the laser in again
    from kerfly.core import udev as _udev
    from kerfly.core.laser import LaserError as _LaserError
    u = make_window(grid_mm="0")
    saved = (_udev.installed, _udev.install, _udev.applies, QMessageBox.question, QMessageBox.information,
             u.laser.connect)
    asked, informed, installs = [], [], []
    try:
        _udev.applies = lambda: True
        _udev.installed = lambda dirs=None: False
        _udev.install = lambda: installs.append(1) or (True, "")
        QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: informed.append(a[2]))

        def refuse(init_home=True):
            raise _LaserError("USB error: [Errno 13] Access denied (insufficient permissions)")
        u.laser.connect = refuse
        u.connect_laser()
        for _i in range(5):
            app.processEvents()
        offered = bool(installs) and any("was found" in q for q in asked) and any("Unplug" in t for t in informed)
        _udev.installed = lambda dirs=None: True
        installs.clear()
        u.allow_usb_access()
        already = not installs and any("already installed" in t for t in informed)
    finally:
        (_udev.installed, _udev.install, _udev.applies, QMessageBox.question, QMessageBox.information,
         u.laser.connect) = saved
    check("Linux USB access: refused connection offers the rule (pkexec), an existing rule only a hint",
          offered and already, "(%s, %s, %s)" % (offered, already, asked[:1]))
    u._dirty = False
    u.close()

    # 54. generators: each one's dialog makes a design that goes on the bed as one group and one
    # undo step (with its layers), the window tells the truth; the dialog remembers its numbers
    from kerfly.gui.generators import GENERATORS as _GENS, GeneratorDialog as _GD
    from kerfly.gui import truth as _truth2
    gw = make_window(grid_mm="0")
    made = {}
    for key, *_rest in _GENS:
        dlg = _GD(gw, key, remember=False)
        before = _truth2.state(gw)
        els = gw.insert_generated(dlg.result_design())
        grouped = len(els) == 1 or len({e.group for e in els}) == 1 and bool(els[0].group)
        ok = bool(els) and grouped and not _truth2.check_window(gw)
        gw.undo()
        ok = ok and _truth2.difference(before, _truth2.state(gw)) == ""
        made[key] = ok
        dlg.deleteLater()
    from PySide6.QtTest import QTest as _QTest
    d0 = _GD(gw, "gear", remember=False)
    d0.show()
    app.processEvents()
    _QTest.keyClick(d0.widgets["teeth"].lineEdit(), Qt.Key_Return)      # Enter: the preview, not Insert
    app.processEvents()
    enter_stays = d0.isVisible() and d0.result() == 0
    d0.reject()
    gw.remember_geometry = True
    d1 = _GD(gw, "gear", remember=True)
    d1.widgets["teeth"].setValue(33)
    d1.accept()
    remembered = _GD(gw, "gear", remember=True).widgets["teeth"].value() == 33
    check("generators: every one inserts a group as one undo step, window tells the truth; numbers remembered",
          all(made.values()) and remembered and enter_stays,
          "(%s, remembered %s, Enter keeps the dialog %s)" % (made, remembered, enter_stays))
    gw._dirty = False
    gw.close()

    # 55. stamp: the picture is inverted (background burnt, text raised) and mirrored, black and white,
    # at the chosen size; it is kept as a file (projects can save it) and the outline is cut
    from kerfly.gui import stamp as _stamp
    base = dict(preset="custom", width=40.0, height=15.0, text="AB", font="DejaVu Sans", bold=True, text_size=0.0,
                picture="", place="left", frame=0.0, corner=0.0, margin=1.0, outline=True)
    plain = _stamp.render(dict(base, invert=False, mirror=False))
    stamp_img = _stamp.render(dict(base, invert=True, mirror=True))

    def dark(img):
        return sum(1 for y in range(0, img.height(), 4) for x in range(0, img.width(), 4)
                   if img.pixelColor(x, y).lightness() < 128)
    total = len(range(0, plain.height(), 4)) * len(range(0, plain.width(), 4))
    inverted = dark(plain) < total * 0.5 < dark(stamp_img)
    mirrored = all((plain.pixelColor(x, y).lightness() < 128) ==
                   (stamp_img.pixelColor(plain.width() - 1 - x, y).lightness() >= 128)
                   for y in range(0, plain.height(), 25) for x in range(0, plain.width(), 25))
    two_tone = all(plain.pixelColor(x, y).lightness() in (0, 255)
                   for y in range(0, plain.height(), 9) for x in range(0, plain.width(), 9))
    size_ok = abs(plain.width() / 1000 * 25.4 - 40) < 0.1 and abs(plain.height() / 1000 * 25.4 - 15) < 0.1
    sw = make_window(grid_mm="0")
    els = sw.insert_generated(_stamp.make(dict(base, invert=True, mirror=True), sw))
    kept = els and os.path.isfile(els[0].source_file) and els[0].design.raster.image is not None \
        and els[1].shape is not None and els[1].shape.operation == "cut"
    check("stamp: inverted, mirrored, black and white, its size, kept as a file, outline cut",
          inverted and mirrored and two_tone and size_ok and bool(kept),
          "(%s)" % ([inverted, mirrored, two_tone, size_ok, bool(kept)],))
    sw._dirty = False
    sw.close()

    # 55b. round stamp: text around the top (letters standing on the circle) and the bottom, the
    # middle text, the ready-made diameters, inverted and mirrored, a round outline cut
    rbase = {f[0]: f[3] for f in _stamp.ROUND_FIELDS}
    rbase.update(preset="40", top_text="TOP TEXT HERE", bottom_text="BOTTOM", text="MID", invert=False,
                 mirror=False, picture="")
    r_plain = _stamp.render_round(rbase)

    def region(img, y0, y1, x0=0.3, x1=0.7):
        return sum(1 for y in range(int(img.height() * y0), int(img.height() * y1), 4)
                   for x in range(int(img.width() * x0), int(img.width() * x1), 4)
                   if img.pixelColor(x, y).lightness() < 128)
    empty = _stamp.render_round(dict(rbase, top_text="", bottom_text="", text=""))
    texts_ok = (region(r_plain, 0.04, 0.2) > region(empty, 0.04, 0.2) + 50
                and region(r_plain, 0.8, 0.96) > region(empty, 0.8, 0.96) + 50
                and region(r_plain, 0.4, 0.6) > region(empty, 0.4, 0.6) + 50)
    r_size_ok = abs(r_plain.width() / 1000 * 25.4 - 40) < 0.1 and r_plain.width() == r_plain.height()
    small = _stamp.render_round(dict(rbase, preset="custom", diameter=25.0))
    r_burn = _stamp.render_round(dict(rbase, invert=True, mirror=True))
    r_mirrored = all((r_plain.pixelColor(x, y).lightness() < 128) ==
                     (r_burn.pixelColor(r_plain.width() - 1 - x, y).lightness() >= 128)
                     for y in range(0, r_plain.height(), 31) for x in range(0, r_plain.width(), 31))
    sw = make_window(grid_mm="0")
    els = sw.insert_generated(_stamp.make_round(dict(rbase, invert=True, mirror=True), sw))
    r_cut = (len(els) == 2 and els[1].shape.kind == "ellipse" and els[1].shape.operation == "cut"
             and abs(els[1].shape.width - 40) < 1e-6)
    check("round stamp: texts at the top, bottom and middle, its diameter, inverted and mirrored, round cut",
          texts_ok and r_size_ok and abs(small.width() / 1000 * 25.4 - 25) < 0.1 and r_mirrored and r_cut,
          "(%s)" % ([texts_ok, r_size_ok, small.width(), r_mirrored, r_cut],))
    sw._dirty = False
    sw.close()

    # 56. a path shape put on the bed starts at (0, 0) of its outline, so the node editor draws its
    # nodes on the shape (a curve whose handles stuck out was drawn shifted)
    from kerfly.core import curves as _cv
    pw = make_window(grid_mm="0")
    heart = _Spec(kind="path", operation="cut", subpaths=[{"closed": True, "nodes": [
        _cv.node(45, 15, (30, -5), (60, -5)), _cv.node(85, 25, (90, 0), (80, 50)),
        _cv.node(45, 75, (60, 60), (30, 60)), _cv.node(5, 25, (10, 50), (0, 0))]}])
    pw._add_drawn_element(heart, "pen", 40, 30)
    x0, _x1, y0, _y1 = _cv.bounds(pw.elements[-1].shape.subpaths)
    check("path shapes start at (0, 0) of their outline (node editor on the shape)",
          abs(x0) < 1e-6 and abs(y0) < 1e-6, "(%.3f, %.3f)" % (x0, y0))
    pw._dirty = False
    pw.close()

    # 50. the element list shows a single element too (it was hidden until there were two)
    w9 = make_window(grid_mm="0")
    w9._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10, 10)
    shown = not w9.element_list_box.isHidden() and w9.element_list.count() == 1
    w9.new_project()
    hidden_empty = w9.element_list_box.isHidden()
    check("element list: shown with one element, hidden when the bed is empty", shown and hidden_empty)
    w9._dirty = False
    w9.close()

    # 49. File → New project: asks about unsaved changes, then an empty bed, default layers, no undo
    w8 = make_window(grid_mm="0")
    w8._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10, 10)
    w8.add_layer("cut")                                   # an extra layer, gone in the new project
    asked = []
    _orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.Discard)
    try:
        w8.new_project()
    finally:
        QMessageBox.question = _orig_q
    kinds = sorted(l.kind for l in w8.layers)
    fresh = not w8.elements and not w8._undo and not w8.project_file and not w8._dirty \
        and kinds == sorted(set(kinds)) and bool(asked)
    on_bar = any(getattr(t, "defaultAction", lambda: None)() is w8.act_new for t in w8.findChildren(QToolButton))
    check("new project: asks first, empty bed, default layers, nothing to undo, toolbar button",
          fresh and on_bar, "(%s, %d layers, asked %s)" % (fresh, len(w8.layers), bool(asked)))
    w8._dirty = False
    w8.close()

    # 43. no keyboard shortcut is used twice (Qt then runs neither action)
    from PySide6.QtGui import QAction as _QAction
    seen, twice = {}, []
    for a in w.findChildren(_QAction):
        for sc in a.shortcuts():
            key = sc.toString()
            if key in seen and seen[key] is not a:
                twice.append("%s: %s / %s" % (key, seen[key].text(), a.text()))
            seen.setdefault(key, a)
    check("no keyboard shortcut is used twice", not twice, "(%s)" % "; ".join(twice))

    # 42. program icon: the logo renders, the bitmap icons exist
    from kerfly.gui import icons as _icons
    ico = os.path.join(ROOT_DIR, "kerfly", "gui", "icons", "kerfly.ico")
    png = os.path.join(ROOT_DIR, "kerfly", "gui", "icons", "kerfly.png")
    app_icon = _icons.app_icon()
    check("program icon: logo renders, kerfly.ico and kerfly.png exist",
          not app_icon.isNull() and not app_icon.pixmap(32, 32).toImage().isNull()
          and app_icon.pixmap(32, 32).toImage().pixelColor(16, 3).alpha() > 0
          and os.path.getsize(ico) > 1000 and os.path.getsize(png) > 1000)

    # 41. "Design follows the head": arrows and Home move the design too, corners only the head,
    # one undo step for switching it on, nothing moves when it is off
    w2 = make_window(follow_head="0", jog_step="10")
    w2.load_design(os.path.join(FIX, "shapes.dxf"))
    start = (w2.elements[0].x, w2.elements[0].y)
    w2.jog(1, 0)
    stays = (w2.elements[0].x, w2.elements[0].y) == start
    undo_before = len(w2._undo)
    w2.act_follow_head.trigger()
    at_head = w2.origin == w2.head and len(w2._undo) == undo_before + 1
    w2.jog(1, 0)
    w2.jog(0, -1)
    follows = w2.origin == w2.head and abs(w2.head[0] - 20 / 25.4) < 0.002 and len(w2._undo) == undo_before + 1
    w2.move_to_corner("LR")
    corner_only = w2.origin != w2.head
    w2.home()
    homed = w2.origin == (0.0, 0.0) == w2.head
    w2.jog(-1, 0)                                         # already at the left edge: stays on the bed
    on_bed = w2.origin == (0.0, 0.0)
    w2.act_follow_head.trigger()
    saved = w2.values["follow_head"] == "0"
    check("design follows the head: arrows, corners, Home, undo, setting",
          stays and at_head and follows and corner_only and homed and on_bed and saved,
          "(%s)" % ([stays, at_head, follows, corner_only, homed, on_bed, saved],))
    w2._dirty = False
    w2.close()
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

    # Let every worker thread finish: a QThread still running when the process
    # exits crashes it on Windows (access violation in exit).
    import gc
    from PySide6.QtCore import QThread
    running = [t for t in gc.get_objects() if isinstance(t, QThread) and t.isRunning()]
    for t in running:
        t.wait(10000)
    still = [type(t).__name__ for t in running if t.isRunning()]
    check("all worker threads finished", not still, "(%d were running, still: %s)" % (len(running), still))

    # close every window and let Qt delete them before the application goes away
    for top in QApplication.topLevelWidgets():
        if isinstance(top, MainWindow):
            top._dirty = False
        top.close()
        top.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()

    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        import traceback
        text = traceback.format_exc()
        print(text)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error title=test_gui crashed::" + text.replace("%", "%25").replace("\n", "%0A"))
        rc = 1
    sys.stdout.flush()
    sys.exit(rc)
